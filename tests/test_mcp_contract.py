from __future__ import annotations

import ast
import io
import json
import socket
from pathlib import Path

import pytest

import sonarchy_mcp_contract as contract
from sonarchy_backend.contracts import CAPABILITY_NAMES
from sonarchy_backend.local_mcp import MultiClientRuntime, _Client, load_mcp_permissions
from sonarchy_backend.protocol import PROTOCOL_OPERATIONS
from sonarchy_mcp.server import SonarchyMcp, ToolError, _permissions, tools

EXPECTED_MATRIX = (
    ("rooms_list", "state.refresh", "read"),
    ("room_state_get", "state.refresh", "read"),
    ("content_browse", "content.browse", "read"),
    ("apple_playlist_preflight", "playlist_plan.apple.validate", "read"),
    ("sonos_playlist_play_preflight", "playlists.play.validate", "read"),
    ("apple_playlist_create", "playlists.apple.create", "playlist-create"),
    ("sonos_playlist_play", "playlists.play.execute", "playlist-play"),
)

EXPECTED_PUBLIC_FIELDS = {
    "rooms_list": (set(), set()),
    "room_state_get": ({"roomUid"}, set()),
    "content_browse": ({"kind", "term", "limit", "context"}, {"roomUid"}),
    "apple_playlist_preflight": ({"roomUid", "name", "allowDuplicates", "tracks"}, set()),
    "sonos_playlist_play_preflight": ({"roomUid", "playlistId"}, set()),
    "apple_playlist_create": ({"planHandle", "approved"}, set()),
    "sonos_playlist_play": ({"planHandle", "approved"}, set()),
}

EXPECTED_BACKEND_FIELDS = {
    "state.refresh": (set(), set()),
    "content.browse": ({"roomUid", "kind", "limit"}, {"term", "context"}),
    "playlist_plan.apple.validate": (
        {"roomUid", "playlistName", "mode", "tracks"},
        {"allowDuplicates"},
    ),
    "playlists.play.validate": ({"roomUid", "playlistId"}, set()),
    "playlists.apple.create": ({"planToken", "approved"}, set()),
    "playlists.play.execute": ({"planToken", "approved"}, set()),
}


def test_exact_tool_operation_permission_matrix_is_pinned_independently():
    actual = tuple(
        (
            tool,
            contract.MCP_TOOL_OPERATIONS[tool],
            contract.MCP_OPERATION_PERMISSIONS[contract.MCP_TOOL_OPERATIONS[tool]],
        )
        for tool in contract.MCP_TOOL_ORDER
    )
    assert actual == EXPECTED_MATRIX
    assert set(contract.MCP_SOCKET_OPERATIONS) == {row[1] for row in EXPECTED_MATRIX}
    assert set(contract.MCP_DOMAIN_OPERATIONS) == {row[1] for row in EXPECTED_MATRIX} - {
        "state.refresh"
    }


@pytest.mark.parametrize(
    "raw,expected",
    [
        (b"", set()),
        (b"enabled = false\npermissions = []\n", set()),
        (b'enabled = true\npermissions = ["read"]\n', {"read"}),
        (
            b'enabled = true\npermissions = ["read", "playlist-create", "playlist-play"]\n',
            {"read", "playlist-create", "playlist-play"},
        ),
        (b'enabled = true\npermissions = ["playlist-play"]\n', {"read"}),
        (b'enabled = true\npermissions = ["read", "unknown"]\n', {"read"}),
        (b'enabled = true\npermissions = "read"\n', {"read"}),
        (b'enabled = true\npermissions = ["read", 1]\n', {"read"}),
        (b'enabled = true\npermissions = ["read", "read"]\n', {"read"}),
        (b"not toml =", {"read"}),
        (b"\xff", {"read"}),
    ],
)
def test_pure_permission_grammar(raw: bytes, expected: set[str]):
    assert contract.parse_mcp_permissions(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        (b'enabled = true\npermissions = ["read"]\n', {"read"}),
        (
            b'enabled = true\npermissions = ["read", "playlist-create"]\n',
            {"read", "playlist-create"},
        ),
        (b'enabled = true\npermissions = ["read", "playlist-play"]\n', {"read", "playlist-play"}),
        (b'enabled = true\npermissions = ["read", "read"]\n', {"read"}),
        (b"enabled = false\npermissions = []\n", set()),
        (b'enabled = true\npermissions = ["playlist-play"]\n', {"read"}),
        (b'enabled = true\npermissions = ["read", 1]\n', {"read"}),
        (b"not toml =", {"read"}),
        (b"\xff", {"read"}),
    ],
)
def test_two_secure_loaders_have_permission_grammar_parity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raw: bytes, expected: set[str]
):
    directory = tmp_path / contract.MCP_CONFIG_DIRECTORY
    directory.mkdir(mode=0o700)
    config = directory / contract.MCP_CONFIG_FILENAME
    config.write_bytes(raw)
    config.chmod(0o600)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert _permissions() == expected
    assert load_mcp_permissions(str(tmp_path)) == expected


@pytest.mark.parametrize("unsafe", ["oversized", "mode", "symlink"])
def test_two_secure_loaders_independently_fail_closed_on_unsafe_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, unsafe: str
):
    directory = tmp_path / contract.MCP_CONFIG_DIRECTORY
    directory.mkdir(mode=0o700)
    config = directory / contract.MCP_CONFIG_FILENAME
    if unsafe == "symlink":
        target = tmp_path / "outside"
        target.write_bytes(b'enabled = true\npermissions = ["read", "playlist-play"]\n')
        config.symlink_to(target)
    else:
        raw = (
            b"#" * (contract.MAX_MCP_CONFIG_BYTES + 1)
            if unsafe == "oversized"
            else b'enabled = true\npermissions = ["read", "playlist-play"]\n'
        )
        config.write_bytes(raw)
        config.chmod(0o644 if unsafe == "mode" else 0o600)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert _permissions() == {"read"}
    assert load_mcp_permissions(str(tmp_path)) == {"read"}


def test_exact_inventory_order_permissions_and_schema_field_contracts():
    permission_sets = (
        set(),
        {"read"},
        {"read", "playlist-create"},
        {"read", "playlist-play"},
        {"read", "playlist-create", "playlist-play"},
    )
    for permissions in permission_sets:
        inventory = tools(frozenset(permissions))
        expected = [
            tool for tool, _operation, required in EXPECTED_MATRIX if required in permissions
        ]
        assert [item["name"] for item in inventory] == expected
        for item in inventory:
            required, optional = EXPECTED_PUBLIC_FIELDS[item["name"]]
            schema = item["inputSchema"]
            assert set(schema["properties"]) == required | optional
            assert set(schema["required"]) == required
            assert schema["additionalProperties"] is False
            declared = contract.MCP_PUBLIC_FIELDS[item["name"]]
            assert set(declared.required) == required
            assert set(declared.optional) == optional


def test_backend_fields_and_protocol_inventories_are_exact():
    assert set(contract.MCP_BACKEND_FIELDS) == set(EXPECTED_BACKEND_FIELDS)
    for operation, (required, optional) in EXPECTED_BACKEND_FIELDS.items():
        fields = contract.MCP_BACKEND_FIELDS[operation]
        assert set(fields.required) == required
        assert set(fields.optional) == optional
    domain_operations = set(EXPECTED_BACKEND_FIELDS) - {"state.refresh"}
    assert domain_operations <= PROTOCOL_OPERATIONS
    assert domain_operations <= CAPABILITY_NAMES
    assert "state.refresh" not in PROTOCOL_OPERATIONS
    assert "state.refresh" not in CAPABILITY_NAMES


class _RecordingProtocol:
    revision = 1

    def __init__(self):
        self.calls: list[str] = []

    def handle(self, request, output):
        self.calls.append(request["op"])
        output.write(json.dumps({"type": "result", "id": request["id"], "ok": True}) + "\n")


@pytest.mark.parametrize(
    "operation,permissions,allowed",
    [
        (operation, frozenset(permissions), required in permissions and "read" in permissions)
        for operation, required in {
            "state.refresh": "read",
            "content.browse": "read",
            "playlist_plan.apple.validate": "read",
            "playlists.play.validate": "read",
            "playlists.apple.create": "playlist-create",
            "playlists.play.execute": "playlist-play",
        }.items()
        for permissions in (
            set(),
            {"read"},
            {"playlist-create"},
            {"playlist-play"},
            {"read", "playlist-create"},
            {"read", "playlist-play"},
        )
    ]
    + [
        ("session.panel_open.set", frozenset({"read", "playlist-create", "playlist-play"}), False),
        ("undeclared.operation", frozenset({"read", "playlist-create", "playlist-play"}), False),
    ],
)
def test_socket_runtime_independently_authorizes_exact_operation_permission(
    tmp_path: Path, operation: str, permissions: frozenset[str], allowed: bool
):
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(tmp_path / "listener"))
    protocol = _RecordingProtocol()
    runtime = MultiClientRuntime(protocol, listener, permissions)  # type: ignore[arg-type]
    server_sock, peer_sock = socket.socketpair()
    client = _Client(server_sock)
    runtime.clients[server_sock.fileno()] = client
    runtime.selector.register(server_sock, 1, client)
    runtime._dispatch(
        {"id": "matrix", "op": operation, "args": {}},
        socket_client=client,
        stdout=io.BytesIO(),
    )
    assert protocol.calls == ([operation] if allowed else [])
    if not allowed:
        assert json.loads(client.output_buffer.splitlines()[0])["error"]["code"] == (
            "permission_denied"
        )
    runtime._close_client(client)
    peer_sock.close()
    listener.close()


def test_adapter_denies_disabled_write_before_backend_dispatch():
    server = SonarchyMcp()
    server.permissions = frozenset({"read"})
    server.backend.call = lambda *_args: pytest.fail("backend must not receive disabled tool")
    assert "sonos_playlist_play" not in {item["name"] for item in tools(server.permissions)}
    with pytest.raises(ToolError, match="Unknown or disabled"):
        server.call_tool("sonos_playlist_play", {"planHandle": "x" * 40, "approved": True})


def test_neutral_contract_import_boundary_is_standard_library_only():
    source = Path(contract.__file__).read_text()
    tree = ast.parse(source)
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module != "__future__"
    }
    assert imports == {"tomllib", "dataclasses", "types"}
    assert not {"soco", "sonarchy_backend", "sonarchy_mcp"} & imports
