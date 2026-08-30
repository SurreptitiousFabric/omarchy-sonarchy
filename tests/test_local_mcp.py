from __future__ import annotations

import io
import json
import os
import socket
import stat
from pathlib import Path
from unittest.mock import Mock

import pytest

from sonarchy_backend.local_mcp import (
    BackendOwnership,
    MultiClientRuntime,
    OwnershipError,
    load_mcp_permissions,
)


class StubProtocol:
    revision = 3

    def __init__(self):
        self.calls = []

    def handle(self, request, output):
        self.calls.append(request["op"])
        output.write(json.dumps({"type": "result", "id": request["id"], "ok": True}) + "\n")
        output.write(
            json.dumps(
                {
                    "type": "snapshot",
                    "version": 1,
                    "revision": 4,
                    "status": {"state": "ready"},
                    "households": [],
                }
            )
            + "\n"
        )


def test_first_owner_has_exact_directory_lock_and_socket_modes(tmp_path: Path):
    with BackendOwnership.acquire(str(tmp_path)) as owner:
        listener = owner.open_listener()
        assert listener.family == socket.AF_UNIX
        assert stat.S_IMODE((tmp_path / "sonarchy").stat().st_mode) == 0o700
        assert stat.S_IMODE(owner.socket_path.stat().st_mode) == 0o600
        assert stat.S_IMODE((owner.runtime_dir / "backend.lock").stat().st_mode) == 0o600
        assert owner.socket_path.exists()
    assert not owner.socket_path.exists()


def test_second_owner_is_rejected_without_removing_active_socket(tmp_path: Path):
    with BackendOwnership.acquire(str(tmp_path)) as owner:
        owner.open_listener()
        identity = owner.socket_path.stat().st_ino
        with pytest.raises(OwnershipError, match="already owns"):
            BackendOwnership.acquire(str(tmp_path))
        assert owner.socket_path.stat().st_ino == identity


@pytest.mark.parametrize("artifact", ["sonarchy", "backend.lock"])
def test_runtime_symlinks_are_rejected(tmp_path: Path, artifact: str):
    target = tmp_path / "target"
    target.mkdir()
    runtime = tmp_path / "sonarchy"
    if artifact == "sonarchy":
        runtime.symlink_to(target, target_is_directory=True)
    else:
        runtime.mkdir(mode=0o700)
        (runtime / artifact).symlink_to(target / "lock")
    with pytest.raises(OwnershipError, match="symbolic link"):
        BackendOwnership.acquire(str(tmp_path))


def test_unsafe_stale_socket_path_is_not_replaced(tmp_path: Path):
    with BackendOwnership.acquire(str(tmp_path)) as owner:
        owner.socket_path.write_text("not a socket")
        with pytest.raises(OwnershipError, match="unsafe"):
            owner.open_listener()
        assert owner.socket_path.read_text() == "not a socket"


def _write_config(root: Path, text: str, mode: int = 0o600) -> None:
    directory = root / "sonarchy"
    directory.mkdir()
    path = directory / "mcp.toml"
    path.write_text(text)
    path.chmod(mode)


def test_no_config_defaults_to_read_only(tmp_path: Path):
    assert load_mcp_permissions(str(tmp_path)) == {"read"}


def test_explicit_playlist_permission_is_loaded_once(tmp_path: Path):
    _write_config(tmp_path, 'enabled = true\npermissions = ["read", "playlist-create"]\n')
    assert load_mcp_permissions(str(tmp_path)) == {"read", "playlist-create"}


@pytest.mark.parametrize(
    "text,mode",
    [
        ('enabled = true\npermissions = ["read", "playback"]\n', 0o600),
        ("not toml =", 0o600),
        ('enabled = true\npermissions = ["read", "playlist-create"]\n', 0o644),
    ],
)
def test_invalid_or_unsafe_config_fails_closed_to_read_only(tmp_path: Path, text: str, mode: int):
    _write_config(tmp_path, text, mode)
    assert load_mcp_permissions(str(tmp_path)) == {"read"}


def test_config_symlink_fails_closed(tmp_path: Path):
    directory = tmp_path / "sonarchy"
    directory.mkdir()
    target = tmp_path / "outside"
    target.write_text('enabled = true\npermissions = ["read", "playlist-create"]\n')
    (directory / "mcp.toml").symlink_to(target)
    assert load_mcp_permissions(str(tmp_path)) == {"read"}


def test_socket_owner_matches_current_user(tmp_path: Path):
    with BackendOwnership.acquire(str(tmp_path)) as owner:
        owner.open_listener()
        assert owner.socket_path.stat().st_uid == os.getuid()


def test_socket_snapshot_projection_omits_private_and_provider_fields():
    safe = MultiClientRuntime._safe_socket_snapshot(
        {
            "type": "snapshot",
            "version": 1,
            "revision": 4,
            "status": {"state": "ready", "discovery": {"hosts": ["192.0.2.1"]}},
            "households": [
                {
                    "id": "H1",
                    "rooms": [{"uid": "R1", "name": "Office", "ip": "192.0.2.1"}],
                    "groups": [],
                }
            ],
            "playback": {"artworkUrl": "http://192.0.2.1/art"},
            "favorites": {"items": [{"uri": "private"}]},
        }
    )
    rendered = repr(safe)
    assert "192.0.2.1" not in rendered
    assert "artworkUrl" not in rendered
    assert "favorites" not in safe


def test_service_acquires_ownership_before_controller_construction():
    source = (Path(__file__).parents[1] / "sonarchy_service.py").read_text()
    assert source.index("BackendOwnership.acquire()") < source.index("SonosController()")


def test_socket_permission_filter_denies_panel_and_unconfigured_create(tmp_path: Path):
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(tmp_path / "listener"))
    protocol = StubProtocol()
    runtime = MultiClientRuntime(protocol, listener, frozenset({"read"}))  # type: ignore[arg-type]
    server_sock, peer_sock = socket.socketpair()
    client = runtime.clients[server_sock.fileno()] = __import__(
        "sonarchy_backend.local_mcp", fromlist=["_Client"]
    )._Client(server_sock)
    runtime.selector.register(server_sock, 1, client)
    stdout = io.BytesIO()
    runtime._dispatch(
        {"id": "same", "op": "session.panel_open.set", "args": {"open": True}},
        socket_client=client,
        stdout=stdout,
    )
    runtime._dispatch(
        {"id": "same", "op": "playlists.apple.create", "args": {"planToken": "x"}},
        socket_client=client,
        stdout=stdout,
    )
    denied = [json.loads(line) for line in client.output_buffer.splitlines()]
    assert [item["error"]["code"] for item in denied] == [
        "permission_denied",
        "permission_denied",
    ]
    assert protocol.calls == []
    runtime._close_client(client)
    peer_sock.close()
    listener.close()


def test_socket_result_is_private_but_snapshot_broadcasts_to_qml(tmp_path: Path):
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(tmp_path / "listener"))
    protocol = StubProtocol()
    runtime = MultiClientRuntime(protocol, listener, frozenset({"read"}))  # type: ignore[arg-type]
    server_sock, peer_sock = socket.socketpair()
    client = runtime.clients[server_sock.fileno()] = __import__(
        "sonarchy_backend.local_mcp", fromlist=["_Client"]
    )._Client(server_sock)
    runtime.selector.register(server_sock, 1, client)
    stdout = io.BytesIO()
    runtime._dispatch(
        {"id": "duplicate", "op": "state.refresh", "args": {}},
        socket_client=client,
        stdout=stdout,
    )
    qml_messages = [json.loads(line) for line in stdout.getvalue().splitlines()]
    socket_messages = [json.loads(line) for line in client.output_buffer.splitlines()]
    assert [item["type"] for item in qml_messages] == ["snapshot"]
    assert [item["type"] for item in socket_messages] == ["result", "snapshot"]
    assert socket_messages[0]["id"] == "duplicate"
    runtime._close_client(client)
    peer_sock.close()
    listener.close()


def test_topology_events_refresh_authoritative_households_before_snapshot(tmp_path: Path):
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(tmp_path / "listener"))
    protocol = StubProtocol()
    protocol.event_queue = Mock()
    protocol.event_queue.drain_items.return_value = [
        {"subscriptionKey": "transport:R1"},
        {"subscriptionKey": "topology:H2"},
        {"subscriptionKey": "topology:H1"},
    ]
    protocol.application = Mock()
    runtime = MultiClientRuntime(protocol, listener, frozenset({"read"}))  # type: ignore[arg-type]
    runtime._refresh_and_broadcast = Mock()
    stdout = io.BytesIO()
    runtime._handle_events(stdout)
    protocol.application.refresh_event_topologies.assert_called_once_with({"H1", "H2"})
    runtime._refresh_and_broadcast.assert_called_once_with(stdout, rediscover=False)
    listener.close()
