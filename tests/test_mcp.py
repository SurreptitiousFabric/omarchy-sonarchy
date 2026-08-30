from __future__ import annotations

import ast
import copy
import time
from pathlib import Path

import pytest

from sonarchy_mcp.server import UNAVAILABLE, SonarchyMcp, ToolError, tools

ROOT = Path(__file__).parents[1]


class FakeBackend:
    def __init__(self):
        self.instance = "backend-a"
        self.calls = []
        self.snapshot = {
            "revision": 7,
            "households": [
                {
                    "id": "household",
                    "groups": [
                        {"uid": "group", "coordinatorUid": "R1", "memberUids": ["R1", "R2"]}
                    ],
                    "rooms": [
                        {"uid": "R1", "name": "Office", "groupUid": "group", "volume": 8},
                        {"uid": "R2", "name": "Office", "groupUid": "group", "volume": 9},
                    ],
                }
            ],
        }
        self.token = "backend-secret-ticket"  # noqa: S105 - deliberately opaque test ticket

    def call(self, operation, args):
        self.calls.append((operation, copy.deepcopy(args)))
        if operation == "playlist_plan.apple.validate":
            return {
                "planToken": self.token,
                "expiresAtEpochMs": int(time.time() * 1000) + 60_000,
                "tracks": args["tracks"],
                "queueMutation": False,
                "playbackMutation": False,
            }
        if operation == "playlists.apple.create":
            return {"playlist": {"id": "SQ:99", "tracks": []}}
        if operation == "content.browse":
            return {"items": [], "total": 0, "next_offset": None}
        return None


def _server(write: bool = False):
    server = SonarchyMcp()
    server.backend = FakeBackend()
    server.permissions = {"read", "playlist-create"} if write else {"read"}
    return server


def _track():
    return {
        "catalogId": "1452806384",
        "url": "https://music.apple.com/us/song/1452806384",
        "title": "Just Like Heaven",
        "artist": "The Cure",
        "album": "Kiss Me, Kiss Me, Kiss Me",
        "durationMs": 212000,
    }


def test_exact_read_only_inventory_and_write_inventory():
    assert tools(frozenset()) == []
    assert [item["name"] for item in tools({"read"})] == [
        "rooms_list",
        "room_state_get",
        "content_browse",
        "apple_playlist_preflight",
    ]
    assert [item["name"] for item in tools({"read", "playlist-create"})][-1] == (
        "apple_playlist_create"
    )
    assert all(item["inputSchema"]["additionalProperties"] is False for item in tools({"read"}))


def test_rooms_list_preserves_duplicate_names_and_exact_uids():
    value = _server().call_tool("rooms_list", {})
    rooms = value["households"][0]["rooms"]
    assert [(room["uid"], room["name"]) for room in rooms] == [
        ("R1", "Office"),
        ("R2", "Office"),
    ]


def test_room_state_requires_exact_current_uid():
    server = _server()
    assert server.call_tool("room_state_get", {"roomUid": "R2"})["room"]["volume"] == 9
    with pytest.raises(ToolError, match="no longer available"):
        server.call_tool("room_state_get", {"roomUid": "missing"})


def test_preflight_hides_token_and_create_claims_once_without_retry():
    server = _server(write=True)
    review = server.call_tool(
        "apple_playlist_preflight",
        {"roomUid": "R1", "name": "Morning", "allowDuplicates": False, "tracks": [_track()]},
    )
    rendered = repr(review)
    assert "backend-secret-ticket" not in rendered
    assert review["planHandle"]
    validate_call = server.backend.calls[0]
    assert validate_call[0] == "playlist_plan.apple.validate"
    assert validate_call[1]["mode"] == "save-only"
    created = server.call_tool(
        "apple_playlist_create", {"planHandle": review["planHandle"], "approved": True}
    )
    assert created["playlist"]["id"] == "SQ:99"
    assert server.backend.calls[-1] == (
        "playlists.apple.create",
        {"planToken": "backend-secret-ticket"},
    )
    with pytest.raises(ToolError, match="already been used"):
        server.call_tool(
            "apple_playlist_create", {"planHandle": review["planHandle"], "approved": True}
        )
    assert [call[0] for call in server.backend.calls].count("playlists.apple.create") == 1


def test_backend_restart_and_expiry_invalidate_handle():
    server = _server(write=True)
    review = server.call_tool(
        "apple_playlist_preflight",
        {"roomUid": "R1", "name": "Morning", "allowDuplicates": False, "tracks": [_track()]},
    )
    server.backend.instance = "backend-b"
    with pytest.raises(ToolError, match="restarted"):
        server.call_tool(
            "apple_playlist_create", {"planHandle": review["planHandle"], "approved": True}
        )


def test_read_only_mode_has_no_create_and_rejects_replacement_fields():
    with pytest.raises(ToolError, match="Unknown or disabled"):
        _server().call_tool("apple_playlist_create", {"planHandle": "x" * 40, "approved": True})
    with pytest.raises(ToolError, match="only planHandle"):
        _server(write=True).call_tool(
            "apple_playlist_create",
            {"planHandle": "x" * 40, "approved": True, "name": "replacement"},
        )


def test_mcp_import_boundary_has_no_soco_controller_or_qml_imports():
    forbidden = {"soco", "sonarchy_backend.controller", "PySide6", "qml"}
    for path in (ROOT / "sonarchy_mcp").glob("*.py"):
        tree = ast.parse(path.read_text())
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        assert not any(
            name == blocked or name.startswith(blocked + ".")
            for name in imports
            for blocked in forbidden
        )


def test_backend_absent_returns_safe_unavailable_without_starting_it(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    server = SonarchyMcp()
    with pytest.raises(ToolError, match="Quickshell is running") as error:
        server.call_tool("rooms_list", {})
    assert str(error.value) == UNAVAILABLE
