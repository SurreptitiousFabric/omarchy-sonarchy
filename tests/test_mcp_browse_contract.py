from __future__ import annotations

import io
import json
import os
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from sonarchy_backend.controller import SonosController
from sonarchy_backend.local_mcp import BackendOwnership, MultiClientRuntime
from sonarchy_backend.protocol import ProtocolServer
from sonarchy_backend.state import PersistentState
from sonarchy_mcp.server import SonarchyMcp, ToolError


@pytest.fixture
def browse_contract(tmp_path, monkeypatch, request):
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime_root))
    state = PersistentState(selected_room_uid="selected-room", cached_hosts=[])
    state.save = Mock()
    discovery = Mock(return_value=set())
    controller = SonosController(
        discover_fn=discovery,
        network_scan_fn=Mock(return_value=set()),
        soco_factory=Mock(side_effect=AssertionError("unexpected device access")),
        persistent_state=state,
    )
    payload = json.dumps(
        {
            "results": [
                {
                    "trackId": 123,
                    "trackName": "Song",
                    "artistName": "Artist",
                    "collectionName": "Album",
                    "trackTimeMillis": 180000,
                    "trackViewUrl": "https://music.apple.com/gb/album/album/456?i=123",
                }
            ]
        }
    ).encode()
    response = SimpleNamespace(
        status_code=200,
        raise_for_status=Mock(),
        headers={},
        iter_content=lambda **kwargs: iter([payload]),
        close=Mock(),
    )
    http = Mock(return_value=response)
    monkeypatch.setattr("requests.sessions.Session.request", http)
    read_fd, write_fd = os.pipe()
    stdin = os.fdopen(read_fd, "rb", buffering=0)
    output = io.BytesIO()
    with BackendOwnership.acquire(str(runtime_root)) as ownership:
        runtime = MultiClientRuntime(
            ProtocolServer(controller),
            ownership.open_listener(),
            getattr(request, "param", frozenset({"read"})),
        )
        thread = threading.Thread(target=runtime.serve, args=(stdin, output), daemon=True)
        thread.start()
        mcp = SonarchyMcp()
        mcp.permissions = {"read"}
        try:
            # The real runtime performs startup discovery before accepting clients.
            # Use a complete read round-trip as a barrier, not just socket connect.
            if "read" in runtime.permissions:
                mcp.call_tool("rooms_list", {})
            discovery.reset_mock()
            state.save.reset_mock()
            yield mcp, controller, state, discovery, http
        finally:
            mcp.backend.close()
            os.close(write_fd)
            thread.join(timeout=3)
            stdin.close()
            assert not thread.is_alive()


@pytest.mark.parametrize("room", ({}, {"roomUid": ""}))
@pytest.mark.parametrize("kind", ("apple", "apple-artist", "apple-album"))
def test_room_free_apple_browse_crosses_real_socket_and_domain(browse_contract, kind, room):
    mcp, _, state, discovery, http = browse_contract
    result = mcp.call_tool(
        "content_browse", {"kind": kind, "term": "123", "limit": 1, "context": {}, **room}
    )
    assert result["kind"] == kind
    assert isinstance(result["items"], list)
    if kind == "apple":
        assert result["items"][0]["title"] == "Song"
    assert http.called
    discovery.assert_not_called()
    assert state.selected_room_uid == "selected-room"
    state.save.assert_not_called()


@pytest.mark.parametrize("kind", ("queue", "library", "playlists", "playlist", "global"))
def test_room_bound_browse_without_room_explains_requirement(browse_contract, kind):
    mcp, _, _, _, http = browse_contract
    with pytest.raises(ToolError, match="roomUid is required"):
        mcp.call_tool("content_browse", {"kind": kind, "term": "", "limit": 1, "context": {}})
    http.assert_not_called()


def test_supplied_stale_apple_room_is_not_ignored(browse_contract):
    mcp, _, _, _, http = browse_contract
    with pytest.raises(ToolError, match="Unknown or offline room"):
        mcp.call_tool(
            "content_browse",
            {"kind": "apple", "term": "song", "limit": 1, "context": {}, "roomUid": "stale"},
        )
    http.assert_not_called()


def test_private_socket_also_requires_room_for_sonos_content(browse_contract):
    mcp, _, _, _, http = browse_contract
    with pytest.raises(ToolError, match="roomUid is required"):
        mcp.backend.call(
            "content.browse",
            {"kind": "queue", "term": "", "limit": 1, "context": {}, "roomUid": ""},
        )
    http.assert_not_called()


def test_browse_permission_remains_required(browse_contract):
    mcp, _, _, _, http = browse_contract
    mcp.permissions = set()
    with pytest.raises(ToolError, match="disabled"):
        mcp.call_tool(
            "content_browse", {"kind": "apple", "term": "song", "limit": 1, "context": {}}
        )
    http.assert_not_called()


def test_supplied_current_room_is_preserved(browse_contract):
    mcp, controller, state, discovery, _ = browse_contract
    controller._zones["available"] = SimpleNamespace(group=None)
    result = mcp.call_tool(
        "content_browse",
        {"kind": "apple", "term": "song", "limit": 1, "context": {}, "roomUid": "available"},
    )
    assert result["items"][0]["title"] == "Song"
    assert state.selected_room_uid == "selected-room"
    discovery.assert_not_called()


@pytest.mark.parametrize("room", (None, 123, False, " "))
def test_malformed_room_is_not_treated_as_omitted(browse_contract, room):
    mcp, _, _, _, http = browse_contract
    with pytest.raises(ToolError, match="roomUid"):
        mcp.call_tool(
            "content_browse",
            {"kind": "apple", "term": "song", "limit": 1, "context": {}, "roomUid": room},
        )
    http.assert_not_called()


@pytest.mark.parametrize("browse_contract", [frozenset()], indirect=True)
def test_backend_independently_rejects_browse_without_read_permission(browse_contract):
    mcp, _, _, _, http = browse_contract
    with pytest.raises(ToolError):
        mcp.call_tool(
            "content_browse", {"kind": "apple", "term": "song", "limit": 1, "context": {}}
        )
    http.assert_not_called()


@pytest.mark.parametrize("kind", ("apple", "apple-artist", "apple-album"))
@pytest.mark.parametrize("storefront", ("GB", "gb", "CH"))
def test_explicit_storefront_crosses_socket_to_every_provider_call(
    browse_contract, kind, storefront
):
    mcp, _, _, _, http = browse_contract
    result = mcp.call_tool(
        "content_browse",
        {"kind": kind, "term": "123", "limit": 6, "context": {}, "storefront": storefront},
    )
    assert result["storefront"] == storefront.upper()
    assert http.called
    assert {call.kwargs["params"]["country"] for call in http.call_args_list} == {
        storefront.upper()
    }


@pytest.mark.parametrize("configured,expected", [("CH", "CH"), ("us", "US"), ("bad", "CH")])
def test_omitted_storefront_uses_existing_configured_default(
    browse_contract, monkeypatch, configured, expected
):
    monkeypatch.setenv("SONARCHY_APPLE_COUNTRY", configured)
    mcp, _, _, _, http = browse_contract
    result = mcp.call_tool(
        "content_browse", {"kind": "apple", "term": "song", "limit": 1, "context": {}}
    )
    assert result["storefront"] == expected
    assert http.call_args.kwargs["params"]["country"] == expected
    assert os.environ["SONARCHY_APPLE_COUNTRY"] == configured


@pytest.mark.parametrize("value", (None, "", "GBR", " GB", "1B", "éB", False, 12, []))
@pytest.mark.parametrize("direct", (False, True))
def test_invalid_storefront_fails_at_each_boundary_before_http(browse_contract, value, direct):
    mcp, _, _, discovery, http = browse_contract
    args = {
        "kind": "apple",
        "term": "song",
        "limit": 1,
        "context": {},
        "roomUid": "",
        "storefront": value,
    }
    with pytest.raises(ToolError, match="storefront"):
        if direct:
            mcp.backend.call("content.browse", args)
        else:
            mcp.call_tool("content_browse", args)
    http.assert_not_called()
    discovery.assert_not_called()


@pytest.mark.parametrize("kind", ("queue", "library", "playlist", "playlists", "global"))
def test_storefront_is_not_silently_ignored_for_non_apple_kinds(browse_contract, kind):
    mcp, _, _, discovery, http = browse_contract
    with pytest.raises(ToolError, match="only supported for Apple"):
        mcp.call_tool(
            "content_browse",
            {
                "kind": kind,
                "term": "",
                "limit": 1,
                "context": {},
                "roomUid": "stale",
                "storefront": "GB",
            },
        )
    http.assert_not_called()
    discovery.assert_not_called()


def test_region_specific_identities_and_default_are_not_cross_contaminated(
    browse_contract, monkeypatch
):
    monkeypatch.setenv("SONARCHY_APPLE_COUNTRY", "CH")
    mcp, _, _, _, http = browse_contract

    def regional_response(method, url, **kwargs):
        country = kwargs["params"]["country"]
        identifier = 123 if country == "GB" else 789
        payload = json.dumps(
            {
                "results": [
                    {
                        "wrapperType": "track",
                        "trackId": identifier,
                        "trackName": "Song",
                        "trackViewUrl": f"https://music.apple.com/{country.lower()}/album/album/456?i={identifier}",
                    }
                ]
            }
        ).encode()
        return SimpleNamespace(
            status_code=200,
            headers={},
            raise_for_status=Mock(),
            iter_content=lambda **kwargs: iter([payload]),
            close=Mock(),
        )

    http.side_effect = regional_response
    args = {"kind": "apple", "term": "song", "limit": 1, "context": {}}
    british = mcp.call_tool("content_browse", {**args, "storefront": "GB"})
    default = mcp.call_tool("content_browse", args)
    assert british["storefront"] == "GB"
    assert british["items"][0]["id"] == "123"
    assert "/gb/" in british["items"][0]["url"]
    assert default["storefront"] == "CH"
    assert default["items"][0]["id"] == "789"
    assert "/ch/" in default["items"][0]["url"]
    assert os.environ["SONARCHY_APPLE_COUNTRY"] == "CH"
