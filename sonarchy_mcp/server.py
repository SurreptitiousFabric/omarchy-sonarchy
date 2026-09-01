from __future__ import annotations

import json
import os
import secrets
import socket
import stat
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAX_LINE = 64 * 1024
MAX_CONFIG = 8 * 1024
UNAVAILABLE = (
    "Sonarchy is unavailable. Ensure the Omarchy Sonarchy plugin is enabled and "
    "Quickshell is running."
)
READ_KINDS = frozenset(
    {
        "queue",
        "playlists",
        "playlist",
        "library",
        "global",
        "apple",
        "apple-album",
        "apple-artist",
    }
)


class ToolError(RuntimeError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


class BackendClient:
    def __init__(self) -> None:
        self.sock: socket.socket | None = None
        self.reader = None
        self.counter = 0
        self.snapshot: dict[str, Any] | None = None
        self.instance = ""

    @staticmethod
    def socket_path() -> Path:
        root = os.environ.get("XDG_RUNTIME_DIR", "")
        if not root:
            raise ToolError("unavailable", UNAVAILABLE)
        return Path(root) / "sonarchy" / "control.sock"

    def close(self) -> None:
        if self.reader is not None:
            self.reader.close()
        if self.sock is not None:
            self.sock.close()
        self.reader = None
        self.sock = None
        self.snapshot = None
        self.instance = ""

    def connect(self) -> None:
        if self.sock is not None:
            return
        path = self.socket_path()
        runtime_dir = path.parent
        try:
            directory_info = runtime_dir.stat(follow_symlinks=False)
            info = path.stat(follow_symlinks=False)
        except OSError as exc:
            raise ToolError("unavailable", UNAVAILABLE) from exc
        if (
            runtime_dir.is_symlink()
            or not stat.S_ISDIR(directory_info.st_mode)
            or directory_info.st_uid != os.getuid()
            or stat.S_IMODE(directory_info.st_mode) != 0o700
            or path.is_symlink()
            or not stat.S_ISSOCK(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise ToolError("unavailable", UNAVAILABLE)
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(8.0)
        try:
            sock.connect(str(path))
        except OSError as exc:
            sock.close()
            raise ToolError("unavailable", UNAVAILABLE) from exc
        self.sock = sock
        self.reader = sock.makefile("rb")
        self.instance = secrets.token_hex(16)

    def call(self, operation: str, args: dict[str, Any]) -> Any:
        self.connect()
        self.counter += 1
        request_id = f"mcp-{self.counter}"
        request = {"version": 1, "id": request_id, "op": operation, "args": args}
        encoded = (json.dumps(request, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        if len(encoded) > MAX_LINE:
            raise ToolError("invalid_argument", "The request is too large")
        try:
            sock = self.sock
            reader = self.reader
            if sock is None or reader is None:
                raise OSError
            sock.sendall(encoded)
            matched_value: Any = None
            refresh_revision: int | None = None
            while True:
                line = reader.readline(MAX_LINE + 1)
                if not line or len(line) > MAX_LINE:
                    raise OSError
                payload = json.loads(line)
                if payload.get("type") == "snapshot":
                    self.snapshot = payload
                    if (
                        refresh_revision is not None
                        and int(payload.get("revision", 0)) > refresh_revision
                    ):
                        return matched_value
                    continue
                if payload.get("type") != "result" or payload.get("id") != request_id:
                    continue
                if not payload.get("ok"):
                    error = payload.get("error") or {}
                    raise ToolError(
                        str(error.get("code", "backend_error")),
                        str(error.get("message", "Sonarchy could not complete the request")),
                        error.get("details") if isinstance(error.get("details"), dict) else {},
                    )
                matched_value = payload.get("value")
                if operation == "state.refresh":
                    refresh_revision = int(payload.get("revision", 0))
                    continue
                return matched_value
        except ToolError:
            raise
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self.close()
            raise ToolError("unavailable", UNAVAILABLE) from exc


@dataclass
class PlanHandle:
    token: str
    backend_instance: str
    expires_ms: int
    operation: str


def _permissions() -> frozenset[str]:
    root = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
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
            raw = os.read(config_fd, MAX_CONFIG + 1)
            if len(raw) > MAX_CONFIG:
                return frozenset({"read"})
        finally:
            os.close(config_fd)
        import tomllib

        data = tomllib.loads(raw.decode("utf-8"))
    except OSError, UnicodeDecodeError, ValueError:
        return frozenset({"read"})
    finally:
        os.close(directory_fd)
    if data.get("enabled") is not True:
        return frozenset()
    values = data.get("permissions")
    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
        return frozenset({"read"})
    result = frozenset(values)
    return (
        result
        if "read" in result and result <= {"read", "playlist-create", "playlist-play"}
        else frozenset({"read"})
    )


def _object_schema(
    properties: dict[str, Any], required: list[str], *, additional: bool = False
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": additional,
    }


TRACK_SCHEMA = _object_schema(
    {
        "catalogId": {"type": "string", "minLength": 1, "maxLength": 64},
        "url": {"type": "string", "format": "uri", "maxLength": 1024},
        "title": {"type": "string", "minLength": 1, "maxLength": 256},
        "artist": {"type": "string", "minLength": 1, "maxLength": 256},
        "album": {"type": "string", "minLength": 1, "maxLength": 256},
        "durationMs": {"type": "integer", "minimum": 1, "maximum": 86_400_000},
    },
    ["catalogId", "url", "title", "artist", "album", "durationMs"],
)


def tools(permissions: frozenset[str]) -> list[dict[str, Any]]:
    if "read" not in permissions:
        return []
    inventory = [
        {
            "name": "rooms_list",
            "description": (
                "List authoritative Sonos households, groups, and visible rooms "
                "with exact room UIDs. Read-only."
            ),
            "inputSchema": _object_schema({}, []),
            "annotations": {"readOnlyHint": True, "destructiveHint": False},
        },
        {
            "name": "room_state_get",
            "description": (
                "Get bounded authoritative state for one exact room UID without "
                "changing QML selection. Read-only."
            ),
            "inputSchema": _object_schema(
                {"roomUid": {"type": "string", "minLength": 1, "maxLength": 256}}, ["roomUid"]
            ),
            "annotations": {"readOnlyHint": True, "destructiveHint": False},
        },
        {
            "name": "content_browse",
            "description": (
                "Browse one explicitly allowed Sonarchy content kind using normalized "
                "provider-neutral items. Read-only."
            ),
            "inputSchema": _object_schema(
                {
                    "roomUid": {"type": "string", "maxLength": 256},
                    "kind": {"type": "string", "enum": sorted(READ_KINDS)},
                    "term": {"type": "string", "maxLength": 256},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                    "context": {"type": "object", "maxProperties": 16},
                },
                ["kind", "term", "limit", "context"],
            ),
            "annotations": {"readOnlyHint": True, "destructiveHint": False},
        },
        {
            "name": "apple_playlist_preflight",
            "description": (
                "Validate a reviewed ordered list of exact public Apple catalogue songs "
                "for one new native Sonos Playlist. Read-only; returns an opaque "
                "single-use local handle."
            ),
            "inputSchema": _object_schema(
                {
                    "roomUid": {"type": "string", "minLength": 1, "maxLength": 256},
                    "name": {"type": "string", "minLength": 1, "maxLength": 128},
                    "allowDuplicates": {"type": "boolean"},
                    "tracks": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 25,
                        "items": TRACK_SCHEMA,
                    },
                },
                ["roomUid", "name", "allowDuplicates", "tracks"],
            ),
            "annotations": {"readOnlyHint": True, "destructiveHint": False},
        },
        {
            "name": "sonos_playlist_play_preflight",
            "description": (
                "Validate one exact existing native Sonos Playlist for append-and-play in "
                "one exact standalone room. Read-only; returns an opaque single-use local handle."
            ),
            "inputSchema": _object_schema(
                {
                    "roomUid": {"type": "string", "minLength": 1, "maxLength": 256},
                    "playlistId": {
                        "type": "string",
                        "pattern": r"^SQ:\d+$",
                        "maxLength": 32,
                    },
                },
                ["roomUid", "playlistId"],
            ),
            "annotations": {"readOnlyHint": True, "destructiveHint": False},
        },
    ]
    if "playlist-create" in permissions:
        inventory.append(
            {
                "name": "apple_playlist_create",
                "description": (
                    "Create one new native Sonos Playlist from a current reviewed "
                    "preflight. This is mutating and non-idempotent and requires "
                    "explicit current user approval immediately before the call."
                ),
                "inputSchema": _object_schema(
                    {
                        "planHandle": {"type": "string", "minLength": 32, "maxLength": 128},
                        "approved": {"const": True},
                    },
                    ["planHandle", "approved"],
                ),
                "annotations": {
                    "readOnlyHint": False,
                    "destructiveHint": False,
                    "idempotentHint": False,
                },
            }
        )
    if "playlist-play" in permissions:
        inventory.append(
            {
                "name": "sonos_playlist_play",
                "description": (
                    "Append one reviewed exact native Sonos Playlist to an unchanged room "
                    "queue and start the first appended item. This is mutating and "
                    "non-idempotent and requires explicit current user approval immediately "
                    "before the call."
                ),
                "inputSchema": _object_schema(
                    {
                        "planHandle": {"type": "string", "minLength": 32, "maxLength": 128},
                        "approved": {"const": True},
                    },
                    ["planHandle", "approved"],
                ),
                "annotations": {
                    "readOnlyHint": False,
                    "destructiveHint": False,
                    "idempotentHint": False,
                },
            }
        )
    return inventory


class SonarchyMcp:
    def __init__(self) -> None:
        self.backend = BackendClient()
        self.permissions = _permissions()
        self.handles: dict[str, PlanHandle] = {}

    def _refresh(self) -> dict[str, Any]:
        self.backend.call("state.refresh", {})
        if self.backend.snapshot is None:
            raise ToolError("unavailable", UNAVAILABLE)
        return self.backend.snapshot

    @staticmethod
    def _project_rooms(snapshot: dict[str, Any]) -> dict[str, Any]:
        households = []
        for household in snapshot.get("households") or []:
            groups = []
            room_groups: dict[str, dict[str, Any]] = {}
            for group in household.get("groups") or []:
                projected_group = {
                    "uid": group.get("uid", ""),
                    "coordinatorUid": group.get("coordinatorUid", ""),
                    "memberUids": list(group.get("memberUids") or []),
                    "name": group.get("label", ""),
                    "transportState": group.get("playbackState", "UNKNOWN"),
                    "volume": group.get("volume"),
                    "mute": group.get("mute"),
                }
                groups.append(projected_group)
                for room_uid in projected_group["memberUids"]:
                    room_groups[str(room_uid)] = projected_group
            rooms = []
            for room in household.get("rooms") or []:
                group = room_groups.get(str(room.get("uid", "")), {})
                rooms.append(
                    {
                        "uid": room.get("uid", ""),
                        "name": room.get("name", ""),
                        "groupUid": group.get("uid", ""),
                        "coordinatorUid": group.get("coordinatorUid", ""),
                        "transportState": group.get("transportState", "UNKNOWN"),
                        "volume": room.get("volume"),
                        "mute": room.get("mute"),
                        "online": room.get("online"),
                        "capabilities": {
                            "lineInAvailable": room.get("lineInAvailable", False),
                        },
                    }
                )
            households.append({"uid": household.get("id", ""), "groups": groups, "rooms": rooms})
        return {"revision": snapshot.get("revision", 0), "households": households}

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        allowed_names = {tool["name"] for tool in tools(self.permissions)}
        if name not in allowed_names:
            raise ToolError("not_found", "Unknown or disabled Sonarchy tool")
        if name == "rooms_list":
            if arguments:
                raise ToolError("invalid_argument", "rooms_list accepts no inputs")
            return self._project_rooms(self._refresh())
        if name == "room_state_get":
            if set(arguments) != {"roomUid"}:
                raise ToolError("invalid_argument", "room_state_get accepts only roomUid")
            room_uid = str(arguments["roomUid"])
            projected = self._project_rooms(self._refresh())
            matches = [
                room
                for household in projected["households"]
                for room in household["rooms"]
                if room.get("uid") == room_uid
            ]
            if len(matches) != 1:
                raise ToolError(
                    "not_found" if not matches else "conflict",
                    "The exact Sonos room is no longer available",
                )
            return {"revision": projected["revision"], "room": matches[0]}
        if name == "content_browse":
            expected = {"kind", "term", "limit", "context"}
            if not set(arguments) <= expected | {"roomUid"} or not expected <= set(arguments):
                raise ToolError("invalid_argument", "Invalid content_browse inputs")
            kind = str(arguments["kind"])
            if kind not in READ_KINDS:
                raise ToolError("invalid_argument", "Unsupported content kind")
            return self.backend.call("content.browse", dict(arguments))
        if name == "apple_playlist_preflight":
            if set(arguments) != {"roomUid", "name", "allowDuplicates", "tracks"}:
                raise ToolError("invalid_argument", "Invalid preflight inputs")
            backend_args = dict(arguments)
            backend_args["playlistName"] = backend_args.pop("name")
            backend_args["mode"] = "save-only"
            value = self.backend.call("playlist_plan.apple.validate", backend_args)
            if not isinstance(value, dict) or not isinstance(value.get("planToken"), str):
                raise ToolError("backend_error", "Sonarchy returned an invalid preflight")
            token = value.pop("planToken")
            expires_ms = int(value.get("expiresAtEpochMs", int(time.time() * 1000)))
            handle = secrets.token_urlsafe(32)
            self.handles[handle] = PlanHandle(
                token, self.backend.instance, expires_ms, "playlists.apple.create"
            )
            return {**value, "planHandle": handle}
        if name == "sonos_playlist_play_preflight":
            if set(arguments) != {"roomUid", "playlistId"}:
                raise ToolError("invalid_argument", "Invalid playlist playback preflight inputs")
            value = self.backend.call("playlists.play.validate", dict(arguments))
            if not isinstance(value, dict) or not isinstance(value.get("planToken"), str):
                raise ToolError("backend_error", "Sonarchy returned an invalid playback preflight")
            token = value.pop("planToken")
            expires_ms = int(value.get("expiresAtEpochMs", int(time.time() * 1000)))
            handle = secrets.token_urlsafe(32)
            self.handles[handle] = PlanHandle(
                token, self.backend.instance, expires_ms, "playlists.play.execute"
            )
            return {**value, "planHandle": handle}
        if set(arguments) != {"planHandle", "approved"} or arguments.get("approved") is not True:
            action = "Creation" if name == "apple_playlist_create" else "Playback"
            raise ToolError(
                "invalid_argument", f"{action} requires only planHandle and approved: true"
            )
        handle = str(arguments["planHandle"])
        plan = self.handles.pop(handle, None)
        if plan is None:
            raise ToolError("conflict", "This plan handle is invalid or has already been used")
        if plan.backend_instance != self.backend.instance:
            raise ToolError(
                "conflict", "Sonarchy\u2019s backend connection changed; run a new preflight"
            )
        if plan.expires_ms <= int(time.time() * 1000):
            message = (
                "The reviewed playlist plan expired; run a new preflight"
                if name == "apple_playlist_create"
                else "The reviewed playback plan expired; run a new preflight"
            )
            raise ToolError("conflict", message)
        expected_operation = (
            "playlists.apple.create"
            if name == "apple_playlist_create"
            else "playlists.play.execute"
        )
        if plan.operation != expected_operation:
            raise ToolError("conflict", "This plan handle is bound to another operation")
        return self.backend.call(
            expected_operation,
            {
                "planToken": plan.token,
                "approved": True,
            },
        )

    def run(self) -> None:
        for raw in sys.stdin.buffer:
            try:
                if len(raw) > MAX_LINE:
                    continue
                request = json.loads(raw)
                request_id = request.get("id")
                method = request.get("method")
                if method == "initialize":
                    result = {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {"tools": {"listChanged": False}},
                        "serverInfo": {"name": "sonarchy", "version": "1.0.0"},
                    }
                elif method == "notifications/initialized":
                    continue
                elif method == "ping":
                    result = {}
                elif method == "tools/list":
                    result = {"tools": tools(self.permissions)}
                elif method == "tools/call":
                    params = request.get("params") or {}
                    value = self.call_tool(
                        str(params.get("name", "")), params.get("arguments") or {}
                    )
                    result = {
                        "content": [
                            {"type": "text", "text": json.dumps(value, ensure_ascii=False)}
                        ],
                        "structuredContent": value,
                        "isError": False,
                    }
                else:
                    raise ToolError("method_not_found", "Unsupported MCP method")
                response = {"jsonrpc": "2.0", "id": request_id, "result": result}
            except ToolError as exc:
                response = {
                    "jsonrpc": "2.0",
                    "id": request.get("id") if isinstance(request, dict) else None,
                    "result": {
                        "content": [{"type": "text", "text": str(exc)}],
                        "structuredContent": {
                            "code": exc.code,
                            "message": str(exc),
                            "details": exc.details,
                        },
                        "isError": True,
                    },
                }
            except OSError, ValueError, TypeError, json.JSONDecodeError:
                response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32603, "message": "Internal MCP error"},
                }
            sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()


def main() -> int:
    SonarchyMcp().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
