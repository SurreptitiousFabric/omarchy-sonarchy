from __future__ import annotations

import array
import fcntl
import json
import os
import selectors
import socket
import stat
import time
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO

from .contracts import MAX_PROTOCOL_LINE_BYTES, PROTOCOL_VERSION, protocol_line, result_payload
from .protocol import (
    EVENT_BACKGROUND_POLL_SEC,
    EVENT_PANEL_POLL_SEC,
    FALLBACK_BACKGROUND_POLL_SEC,
    FALLBACK_PANEL_POLL_SEC,
    ProtocolServer,
)

READ_OPERATIONS = frozenset({"state.refresh", "content.browse", "playlist_plan.apple.validate"})
PLAYLIST_CREATE_OPERATION = "playlists.apple.create"
MAX_SOCKET_CLIENTS = 4
MAX_PENDING_OUTPUT_BYTES = MAX_PROTOCOL_LINE_BYTES * 4
MAX_MCP_CONFIG_BYTES = 8 * 1024


class OwnershipError(RuntimeError):
    pass


def _require_safe_directory(path: Path) -> None:
    if path.is_symlink():
        raise OwnershipError("Sonarchy runtime directory must not be a symbolic link")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.stat(follow_symlinks=False)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise OwnershipError("Sonarchy runtime directory has an unsafe owner or type")
    if stat.S_IMODE(info.st_mode) != 0o700:
        os.chmod(path, 0o700)


@dataclass
class BackendOwnership:
    runtime_dir: Path
    lock_file: BinaryIO
    socket_path: Path
    listener: socket.socket | None = None
    socket_identity: tuple[int, int] | None = None

    @classmethod
    def acquire(cls, runtime_root: str | None = None) -> BackendOwnership:
        root = runtime_root or os.environ.get("XDG_RUNTIME_DIR", "")
        if not root:
            raise OwnershipError("XDG_RUNTIME_DIR is required")
        runtime_dir = Path(root) / "sonarchy"
        _require_safe_directory(runtime_dir)
        lock_path = runtime_dir / "backend.lock"
        if lock_path.is_symlink():
            raise OwnershipError("Sonarchy backend lock must not be a symbolic link")
        descriptor = os.open(
            lock_path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600
        )
        lock_file = os.fdopen(descriptor, "r+b", buffering=0)
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            lock_file.close()
            raise OwnershipError("Another Sonarchy backend already owns the controller") from exc
        os.fchmod(lock_file.fileno(), 0o600)
        return cls(runtime_dir, lock_file, runtime_dir / "control.sock")

    def open_listener(self) -> socket.socket:
        path = self.socket_path
        try:
            info = path.lstat()
        except FileNotFoundError:
            pass
        else:
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
                raise OwnershipError("Sonarchy control socket path is unsafe")
            path.unlink()
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM | socket.SOCK_NONBLOCK)
        try:
            listener.bind(str(path))
            os.chmod(path, 0o600, follow_symlinks=False)
            info = path.stat(follow_symlinks=False)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
                raise OwnershipError("Sonarchy control socket permissions are unsafe")
            listener.listen(MAX_SOCKET_CLIENTS)
        except Exception:
            listener.close()
            raise
        self.listener = listener
        self.socket_identity = (info.st_dev, info.st_ino)
        return listener

    def close(self) -> None:
        if self.listener is not None:
            self.listener.close()
            self.listener = None
        if self.socket_identity is not None:
            try:
                info = self.socket_path.stat(follow_symlinks=False)
                if (info.st_dev, info.st_ino) == self.socket_identity and stat.S_ISSOCK(
                    info.st_mode
                ):
                    self.socket_path.unlink()
            except FileNotFoundError:
                pass
            self.socket_identity = None
        fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
        self.lock_file.close()

    def __enter__(self) -> BackendOwnership:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def load_mcp_permissions(config_home: str | None = None) -> frozenset[str]:
    root = config_home or os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    directory = Path(root) / "sonarchy"
    try:
        directory_fd = os.open(
            directory, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
        )
    except OSError:
        return frozenset({"read"})
    try:
        directory_info = os.fstat(directory_fd)
        if not stat.S_ISDIR(directory_info.st_mode) or directory_info.st_uid != os.getuid():
            return frozenset({"read"})
        try:
            config_fd = os.open(
                "mcp.toml", os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=directory_fd
            )
        except OSError:
            return frozenset({"read"})
        try:
            info = os.fstat(config_fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                return frozenset({"read"})
            raw = os.read(config_fd, MAX_MCP_CONFIG_BYTES + 1)
            if len(raw) > MAX_MCP_CONFIG_BYTES:
                return frozenset({"read"})
        finally:
            os.close(config_fd)
        import tomllib

        value = tomllib.loads(raw.decode("utf-8"))
    except OSError, UnicodeDecodeError, ValueError:
        return frozenset({"read"})
    finally:
        os.close(directory_fd)
    if value.get("enabled") is not True:
        return frozenset()
    permissions = value.get("permissions")
    if not isinstance(permissions, list) or not all(isinstance(item, str) for item in permissions):
        return frozenset({"read"})
    selected = frozenset(permissions)
    if not selected <= {"read", "playlist-create"} or "read" not in selected:
        return frozenset({"read"})
    return selected


@dataclass
class _Client:
    sock: socket.socket
    input_buffer: bytearray = field(default_factory=bytearray)
    output_buffer: bytearray = field(default_factory=bytearray)


class MultiClientRuntime:
    """Serialize QML and bounded same-UID socket traffic through one ProtocolServer."""

    def __init__(
        self, protocol: ProtocolServer, listener: socket.socket, permissions: frozenset[str]
    ):
        self.protocol = protocol
        self.listener = listener
        self.permissions = permissions
        self.selector = selectors.DefaultSelector()
        self.clients: dict[int, _Client] = {}

    def _peer_is_current_user(self, sock: socket.socket) -> bool:
        if not hasattr(socket, "SO_PEERCRED"):
            return False
        size = array.array("i", [0, 0, 0]).itemsize * 3
        credentials = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, size)
        values = array.array("i")
        values.frombytes(credentials)
        return len(values) == 3 and values[1] == os.getuid()

    def _close_client(self, client: _Client) -> None:
        self.clients.pop(client.sock.fileno(), None)
        with suppress(KeyError, ValueError):
            self.selector.unregister(client.sock)
        client.sock.close()

    def _queue(self, client: _Client, payload: dict[str, Any]) -> None:
        encoded = protocol_line(payload).encode()
        if len(client.output_buffer) + len(encoded) > MAX_PENDING_OUTPUT_BYTES:
            self._close_client(client)
            return
        client.output_buffer.extend(encoded)
        self.selector.modify(client.sock, selectors.EVENT_READ | selectors.EVENT_WRITE, client)

    def _broadcast(self, payload: dict[str, Any], stdout: BinaryIO) -> None:
        stdout.write(protocol_line(payload).encode())
        stdout.flush()
        socket_payload = self._safe_socket_snapshot(payload)
        for client in list(self.clients.values()):
            self._queue(client, socket_payload)

    @staticmethod
    def _safe_socket_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
        households = []
        for household in payload.get("households") or []:
            rooms = [
                {
                    key: room.get(key)
                    for key in (
                        "uid",
                        "name",
                        "online",
                        "lineInAvailable",
                        "volume",
                        "mute",
                        "playbackState",
                    )
                    if key in room
                }
                for room in household.get("rooms") or []
            ]
            groups = [
                {
                    key: group.get(key)
                    for key in (
                        "uid",
                        "coordinatorUid",
                        "memberUids",
                        "label",
                        "volume",
                        "mute",
                        "playbackState",
                    )
                    if key in group
                }
                for group in household.get("groups") or []
            ]
            households.append({"id": household.get("id", ""), "rooms": rooms, "groups": groups})
        status = payload.get("status") or {}
        return {
            "type": "snapshot",
            "version": payload.get("version", PROTOCOL_VERSION),
            "revision": payload.get("revision", 0),
            "status": {
                key: status.get(key)
                for key in ("state", "message", "degraded", "lastRefreshEpochMs")
                if key in status
            },
            "households": households,
        }

    def _dispatch(
        self, request: dict[str, Any], *, socket_client: _Client | None, stdout: BinaryIO
    ) -> None:
        request_id = str(request.get("id", ""))
        operation = str(request.get("op", ""))
        if socket_client is not None:
            allowed = operation in READ_OPERATIONS or (
                operation == PLAYLIST_CREATE_OPERATION and "playlist-create" in self.permissions
            )
            if "read" not in self.permissions or not allowed:
                self._queue(
                    socket_client,
                    result_payload(
                        request_id,
                        revision=self.protocol.revision,
                        error={
                            "code": "permission_denied",
                            "message": "This operation is not permitted for local MCP clients",
                            "operation": operation,
                            "retryable": False,
                        },
                    ),
                )
                return
        import io

        output = io.StringIO()
        self.protocol.handle(request, output)
        for line in output.getvalue().splitlines():
            payload = json.loads(line)
            if payload.get("type") == "snapshot":
                self._broadcast(payload, stdout)
            elif socket_client is None:
                stdout.write((line + "\n").encode())
                stdout.flush()
            else:
                self._queue(socket_client, payload)

    def serve(self, stdin: BinaryIO, stdout: BinaryIO) -> None:
        self.selector.register(self.listener, selectors.EVENT_READ, None)
        self.selector.register(stdin, selectors.EVENT_READ, "qml")
        self.selector.register(self.protocol.event_queue.read_fd, selectors.EVENT_READ, "events")
        import io

        initial = io.StringIO()
        self.protocol.emit_snapshot(initial)
        self._broadcast(json.loads(initial.getvalue()), stdout)
        try:
            while True:
                for key, mask in self.selector.select(1.0):
                    if key.fileobj is self.listener:
                        sock, _ = self.listener.accept()
                        if (
                            len(self.clients) >= MAX_SOCKET_CLIENTS
                            or not self._peer_is_current_user(sock)
                            or ("read" not in self.permissions)
                        ):
                            sock.close()
                            continue
                        sock.setblocking(False)
                        client = _Client(sock)
                        self.clients[sock.fileno()] = client
                        self.selector.register(sock, selectors.EVENT_READ, client)
                        if self.protocol.last_snapshot is not None:
                            snapshot = self._safe_socket_snapshot(self.protocol.last_snapshot)
                            snapshot.update(
                                type="snapshot",
                                version=PROTOCOL_VERSION,
                                revision=self.protocol.revision,
                            )
                            self._queue(client, snapshot)
                        continue
                    if key.data == "qml":
                        line = stdin.readline(MAX_PROTOCOL_LINE_BYTES + 1)
                        if not line:
                            return
                        self._consume_line(line, None, stdout)
                        continue
                    if key.data == "events":
                        self._handle_events(stdout)
                        continue
                    client = key.data
                    if mask & selectors.EVENT_WRITE and client.output_buffer:
                        try:
                            sent = client.sock.send(client.output_buffer)
                        except BrokenPipeError, ConnectionResetError:
                            self._close_client(client)
                            continue
                        del client.output_buffer[:sent]
                        if not client.output_buffer:
                            self.selector.modify(client.sock, selectors.EVENT_READ, client)
                    if mask & selectors.EVENT_READ:
                        try:
                            chunk = client.sock.recv(8192)
                        except BlockingIOError, ConnectionResetError:
                            continue
                        if not chunk:
                            self._close_client(client)
                            continue
                        client.input_buffer.extend(chunk)
                        if len(client.input_buffer) > MAX_PROTOCOL_LINE_BYTES:
                            self._close_client(client)
                            continue
                        while b"\n" in client.input_buffer:
                            raw, _, rest = client.input_buffer.partition(b"\n")
                            client.input_buffer = bytearray(rest)
                            self._consume_line(raw + b"\n", client, stdout)
                live = self.protocol.event_subscriptions.complete
                interval = (
                    (
                        EVENT_PANEL_POLL_SEC
                        if self.protocol.panel_open
                        else EVENT_BACKGROUND_POLL_SEC
                    )
                    if live
                    else (
                        FALLBACK_PANEL_POLL_SEC
                        if self.protocol.panel_open
                        else FALLBACK_BACKGROUND_POLL_SEC
                    )
                )
                if time.monotonic() - self.protocol.last_refresh >= interval:
                    self._refresh_and_broadcast(stdout)
        finally:
            for client in list(self.clients.values()):
                self._close_client(client)
            self.selector.close()
            self.protocol.event_subscriptions.close()

    def _consume_line(self, raw: bytes, client: _Client | None, stdout: BinaryIO) -> None:
        try:
            request = json.loads(raw)
            if not isinstance(request, dict):
                raise ValueError
        except UnicodeDecodeError, json.JSONDecodeError, ValueError:
            payload = result_payload(
                "",
                revision=self.protocol.revision,
                error={
                    "code": "invalid_request",
                    "message": "Invalid protocol request",
                    "retryable": False,
                },
            )
            if client is None:
                stdout.write(protocol_line(payload).encode())
                stdout.flush()
            else:
                self._queue(client, payload)
            return
        self._dispatch(request, socket_client=client, stdout=stdout)

    def _refresh_and_broadcast(self, stdout: BinaryIO, *, rediscover: bool = True) -> None:
        import io

        output = io.StringIO()
        self.protocol.emit_snapshot(output, rediscover=rediscover)
        self._broadcast(json.loads(output.getvalue()), stdout)

    def _handle_events(self, stdout: BinaryIO) -> None:
        topology_households = {
            str(event.get("subscriptionKey", "")).removeprefix("topology:")
            for event in self.protocol.event_queue.drain_items()
            if isinstance(event, dict)
            and str(event.get("subscriptionKey", "")).startswith("topology:")
        }
        topology_households.discard("")
        if topology_households:
            self.protocol.application.refresh_event_topologies(topology_households)
        self._refresh_and_broadcast(stdout, rediscover=False)
