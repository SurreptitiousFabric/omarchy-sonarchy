from __future__ import annotations

import ast
import copy
import io
import json
import logging
import os
import threading
import time
from pathlib import Path

import pytest

from sonarchy_backend.domains.apple_playlist_plan import MAX_PENDING_PLAN_TICKETS
from sonarchy_backend.local_mcp import BackendOwnership, MultiClientRuntime
from sonarchy_backend.protocol import ProtocolServer
from sonarchy_mcp.server import (
    MAX_PENDING_MCP_HANDLES,
    UNAVAILABLE,
    SonarchyMcp,
    ToolError,
    tools,
)

ROOT = Path(__file__).parents[1]


class FakeBackend:
    def __init__(self, *, expires_at_epoch_ms=None):
        self.instance = "backend-a"
        self.calls = []
        self.expires_at_epoch_ms = expires_at_epoch_ms
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
                "expiresAtEpochMs": self.expires_at_epoch_ms or int(time.time() * 1000) + 60_000,
                "tracks": args["tracks"],
                "queueMutation": False,
                "playbackMutation": False,
            }
        if operation == "playlists.apple.create":
            if set(args) != {"planToken", "approved"} or args.get("approved") is not True:
                raise ValueError("Backend create requires exactly planToken and approved: true")
            return {"playlist": {"id": "SQ:99", "tracks": []}}
        if operation == "content.browse":
            return {"items": [], "total": 0, "next_offset": None}
        return None


def _server(write: bool = False, *, backend=None):
    server = SonarchyMcp()
    server.backend = backend or FakeBackend()
    server.permissions = {"read", "playlist-create"} if write else {"read"}
    return server


def _track():
    return {
        "catalogId": "1452806384",
        "url": ("https://music.apple.com/ch/album/kiss-me-kiss-me-kiss-me/1452806377?i=1452806384"),
        "title": "Just Like Heaven",
        "artist": "The Cure",
        "album": "Kiss Me, Kiss Me, Kiss Me",
        "durationMs": 212000,
    }


class RetentionBackend:
    def __init__(self, expires_at_epoch_ms, *, fail_operation=None):
        self.instance = "backend-a"
        self.expires_at_epoch_ms = expires_at_epoch_ms
        self.fail_operation = fail_operation
        self.calls = []
        self.issued_tokens = []

    def call(self, operation, args):
        self.calls.append((operation, copy.deepcopy(args)))
        if operation == self.fail_operation:
            self.instance = ""
            raise ToolError("unavailable", "Bounded backend failure")
        if operation in {"playlist_plan.apple.validate", "playlists.play.validate"}:
            token = f"backend-retention-token-{len(self.issued_tokens):06d}"
            self.issued_tokens.append(token)
            value = {
                "planToken": token,
                "expiresAtEpochMs": self.expires_at_epoch_ms,
            }
            if operation == "playlist_plan.apple.validate":
                value["tracks"] = args["tracks"]
            return value
        if operation in {"playlists.apple.create", "playlists.play.execute"}:
            return {"ok": True}
        return None


def _retention_server(backend):
    server = SonarchyMcp()
    server.backend = backend
    server.permissions = {"read", "playlist-create", "playlist-play"}
    return server


def _retention_preflight(server, index):
    if index % 2 == 0:
        return server.call_tool(
            "apple_playlist_preflight",
            {
                "roomUid": "R1",
                "name": f"Review {index}",
                "allowDuplicates": False,
                "tracks": [_track()],
            },
        )
    return server.call_tool(
        "sonos_playlist_play_preflight",
        {"roomUid": "R1", "playlistId": f"SQ:{index}"},
    )


def test_ten_thousand_unused_preflights_share_one_bounded_handle_capacity(monkeypatch):
    expected_capacity = MAX_PENDING_MCP_HANDLES
    now_ms = 1_700_000_000_000
    backend = RetentionBackend(now_ms + 120_000)
    server = _retention_server(backend)
    next_handle = iter(f"mcp-retention-handle-{index:010d}" for index in range(10_000))
    monkeypatch.setattr("sonarchy_mcp.server.time.time", lambda: now_ms / 1000)
    monkeypatch.setattr(
        "sonarchy_mcp.server.secrets.token_urlsafe", lambda _size: next(next_handle)
    )

    accepted_handles = []
    capacity_errors = []
    for index in range(10_000):
        try:
            accepted_handles.append(_retention_preflight(server, index)["planHandle"])
        except ToolError as error:
            capacity_errors.append(error)

    retained_tokens = [plan.token for plan in server.handles.values()]
    apple_count = sum(
        plan.operation == "playlists.apple.create" for plan in server.handles.values()
    )
    playback_count = sum(
        plan.operation == "playlists.play.execute" for plan in server.handles.values()
    )
    validation_count = sum(call[0].endswith(".validate") for call in backend.calls)
    evidence = {
        "accepted": len(accepted_handles),
        "capacity_errors": len(capacity_errors),
        "retained_handles": len(server.handles),
        "retained_token_objects": len(retained_tokens),
        "apple_handles": apple_count,
        "playback_handles": playback_count,
        "backend_validations": validation_count,
    }

    assert evidence == {
        "accepted": expected_capacity,
        "capacity_errors": 10_000 - expected_capacity,
        "retained_handles": expected_capacity,
        "retained_token_objects": expected_capacity,
        "apple_handles": expected_capacity // 2,
        "playback_handles": expected_capacity // 2,
        "backend_validations": expected_capacity,
    }
    assert list(server.handles) == accepted_handles
    assert retained_tokens == backend.issued_tokens
    assert all(error.code == "conflict" for error in capacity_errors)
    assert {str(error) for error in capacity_errors} == {
        "Too many reviewed plans are awaiting execution; wait for them to expire or restart "
        "the MCP adapter"
    }
    capacity_message = str(capacity_errors[0])
    assert not any(handle in capacity_message for handle in accepted_handles)
    assert not any(token in capacity_message for token in retained_tokens)
    assert "backend-a" not in capacity_message
    assert str(expected_capacity) not in capacity_message


def test_expired_handles_and_tokens_are_pruned_before_new_preflight(monkeypatch):
    now_ms = 1_700_000_000_000
    backend = RetentionBackend(now_ms + 1_000)
    server = _retention_server(backend)
    next_handle = iter(f"mcp-expiry-handle-{index:016d}" for index in range(4))
    monkeypatch.setattr("sonarchy_mcp.server.time.time", lambda: now_ms / 1000)
    monkeypatch.setattr(
        "sonarchy_mcp.server.secrets.token_urlsafe", lambda _size: next(next_handle)
    )

    expired_handles = [_retention_preflight(server, index)["planHandle"] for index in range(3)]
    expired_tokens = {plan.token for plan in server.handles.values()}
    backend.expires_at_epoch_ms = now_ms + 120_000
    monkeypatch.setattr("sonarchy_mcp.server.time.time", lambda: (now_ms + 2_000) / 1000)
    fresh_handle = _retention_preflight(server, 3)["planHandle"]

    assert list(server.handles) == [fresh_handle]
    assert len(server.handles) == 1
    assert server.handles[fresh_handle].token == backend.issued_tokens[-1]
    assert not expired_tokens & {plan.token for plan in server.handles.values()}
    assert not set(expired_handles) & server.handles.keys()
    assert not any(call[0].endswith(".execute") for call in backend.calls)


def test_new_preflight_after_backend_change_clears_all_old_handles(monkeypatch):
    now_ms = 1_700_000_000_000
    backend = RetentionBackend(now_ms + 120_000)
    server = _retention_server(backend)
    next_handle = iter(f"mcp-reconnect-handle-{index:013d}" for index in range(3))
    monkeypatch.setattr("sonarchy_mcp.server.time.time", lambda: now_ms / 1000)
    monkeypatch.setattr(
        "sonarchy_mcp.server.secrets.token_urlsafe", lambda _size: next(next_handle)
    )

    old_handles = [_retention_preflight(server, index)["planHandle"] for index in range(2)]
    old_tokens = {plan.token for plan in server.handles.values()}
    backend.instance = "backend-b"
    fresh_handle = _retention_preflight(server, 2)["planHandle"]

    assert list(server.handles) == [fresh_handle]
    assert server.handles[fresh_handle].backend_instance == "backend-b"
    assert not set(old_handles) & server.handles.keys()
    assert not old_tokens & {plan.token for plan in server.handles.values()}


def test_stale_claim_after_backend_change_clears_all_sibling_handles(monkeypatch):
    now_ms = 1_700_000_000_000
    backend = RetentionBackend(now_ms + 120_000)
    server = _retention_server(backend)
    next_handle = iter(f"mcp-stale-handle-{index:017d}" for index in range(2))
    monkeypatch.setattr("sonarchy_mcp.server.time.time", lambda: now_ms / 1000)
    monkeypatch.setattr(
        "sonarchy_mcp.server.secrets.token_urlsafe", lambda _size: next(next_handle)
    )

    stale_handles = [_retention_preflight(server, index)["planHandle"] for index in range(2)]
    old_tokens = {plan.token for plan in server.handles.values()}
    backend.instance = "backend-b"

    with pytest.raises(
        ToolError,
        match=r"^Sonarchy’s backend connection changed; run a new preflight$",
    ) as changed:
        server.call_tool(
            "apple_playlist_create", {"planHandle": stale_handles[0], "approved": True}
        )

    assert changed.value.code == "conflict"
    assert not any(handle in str(changed.value) for handle in stale_handles)
    assert not any(token in str(changed.value) for token in old_tokens)
    assert server.handles == {}
    assert not old_tokens & {plan.token for plan in server.handles.values()}
    assert not any(call[0].endswith(".execute") for call in backend.calls)


def test_mcp_handle_capacity_does_not_exceed_backend_ticket_capacity():
    assert MAX_PENDING_MCP_HANDLES <= MAX_PENDING_PLAN_TICKETS


@pytest.mark.parametrize(
    ("preflight_index", "tool_name", "expiry_message"),
    (
        (0, "apple_playlist_create", "The reviewed playlist plan expired; run a new preflight"),
        (1, "sonos_playlist_play", "The reviewed playback plan expired; run a new preflight"),
    ),
    ids=("apple-create", "playlist-playback"),
)
def test_expired_claim_consumes_presented_handle_and_prunes_expired_siblings(
    monkeypatch, preflight_index, tool_name, expiry_message
):
    now_ms = 1_700_000_000_000
    backend = RetentionBackend(now_ms + 1_000)
    server = _retention_server(backend)
    next_handle = iter(f"mcp-claim-expiry-handle-{index:011d}" for index in range(2))
    monkeypatch.setattr("sonarchy_mcp.server.time.time", lambda: now_ms / 1000)
    monkeypatch.setattr(
        "sonarchy_mcp.server.secrets.token_urlsafe", lambda _size: next(next_handle)
    )

    handles = [_retention_preflight(server, index)["planHandle"] for index in range(2)]
    tokens = {plan.token for plan in server.handles.values()}
    target = handles[preflight_index]
    monkeypatch.setattr("sonarchy_mcp.server.time.time", lambda: (now_ms + 2_000) / 1000)

    with pytest.raises(ToolError, match=f"^{expiry_message}$") as expired:
        server.call_tool(tool_name, {"planHandle": target, "approved": True})

    assert expired.value.code == "conflict"
    assert not any(handle in str(expired.value) for handle in handles)
    assert not any(token in str(expired.value) for token in tokens)
    assert server.handles == {}
    assert not any(call[0].endswith(".execute") for call in backend.calls)
    assert not any(call[0] == "playlists.apple.create" for call in backend.calls)

    with pytest.raises(
        ToolError, match=r"^This plan handle is invalid or has already been used$"
    ) as replay:
        server.call_tool(tool_name, {"planHandle": target, "approved": True})
    assert target not in str(replay.value)
    assert not any(token in str(replay.value) for token in tokens)


def test_pruning_preserves_live_handles_on_same_backend_connection(monkeypatch):
    now_ms = 1_700_000_000_000
    backend = RetentionBackend(now_ms + 1_000)
    server = _retention_server(backend)
    next_handle = iter(f"mcp-live-handle-{index:019d}" for index in range(3))
    monkeypatch.setattr("sonarchy_mcp.server.time.time", lambda: now_ms / 1000)
    monkeypatch.setattr(
        "sonarchy_mcp.server.secrets.token_urlsafe", lambda _size: next(next_handle)
    )

    expired_handle = _retention_preflight(server, 0)["planHandle"]
    backend.expires_at_epoch_ms = now_ms + 120_000
    live_handle = _retention_preflight(server, 1)["planHandle"]
    live_token = server.handles[live_handle].token
    monkeypatch.setattr("sonarchy_mcp.server.time.time", lambda: (now_ms + 2_000) / 1000)
    fresh_handle = _retention_preflight(server, 2)["planHandle"]

    assert list(server.handles) == [live_handle, fresh_handle]
    assert expired_handle not in server.handles
    assert server.handles[live_handle].token == live_token
    assert server.call_tool(
        "sonos_playlist_play", {"planHandle": live_handle, "approved": True}
    ) == {"ok": True}
    assert list(server.handles) == [fresh_handle]


def test_claim_releases_one_capacity_slot_without_making_handle_reusable(monkeypatch):
    now_ms = 1_700_000_000_000
    backend = RetentionBackend(now_ms + 120_000)
    server = _retention_server(backend)
    next_handle = iter(
        f"mcp-slot-release-handle-{index:010d}" for index in range(MAX_PENDING_MCP_HANDLES + 1)
    )
    monkeypatch.setattr("sonarchy_mcp.server.time.time", lambda: now_ms / 1000)
    monkeypatch.setattr(
        "sonarchy_mcp.server.secrets.token_urlsafe", lambda _size: next(next_handle)
    )

    handles = [
        _retention_preflight(server, index)["planHandle"]
        for index in range(MAX_PENDING_MCP_HANDLES)
    ]
    claimed = handles[0]
    assert server.call_tool("apple_playlist_create", {"planHandle": claimed, "approved": True}) == {
        "ok": True
    }
    replacement = _retention_preflight(server, MAX_PENDING_MCP_HANDLES)["planHandle"]

    assert len(server.handles) == MAX_PENDING_MCP_HANDLES
    assert claimed not in server.handles
    assert replacement in server.handles
    with pytest.raises(ToolError, match="invalid or has already been used"):
        server.call_tool("apple_playlist_create", {"planHandle": claimed, "approved": True})
    assert sum(call[0] == "playlists.apple.create" for call in backend.calls) == 1


def test_backend_call_failure_clears_old_handles_without_retry_or_secret_leak(monkeypatch):
    now_ms = 1_700_000_000_000
    backend = RetentionBackend(now_ms + 120_000)
    server = _retention_server(backend)
    next_handle = iter(f"mcp-failure-handle-{index:016d}" for index in range(2))
    monkeypatch.setattr("sonarchy_mcp.server.time.time", lambda: now_ms / 1000)
    monkeypatch.setattr(
        "sonarchy_mcp.server.secrets.token_urlsafe", lambda _size: next(next_handle)
    )

    handles = [_retention_preflight(server, index)["planHandle"] for index in range(2)]
    tokens = {plan.token for plan in server.handles.values()}
    backend.fail_operation = "playlists.apple.create"

    with pytest.raises(ToolError, match=r"^Bounded backend failure$") as failure:
        server.call_tool("apple_playlist_create", {"planHandle": handles[0], "approved": True})

    assert backend.instance == ""
    assert server.handles == {}
    assert sum(call[0] == "playlists.apple.create" for call in backend.calls) == 1
    assert not any(handle in str(failure.value) for handle in handles)
    assert not any(token in str(failure.value) for token in tokens)
    with pytest.raises(ToolError, match="invalid or has already been used"):
        server.call_tool("apple_playlist_create", {"planHandle": handles[0], "approved": True})
    assert sum(call[0] == "playlists.apple.create" for call in backend.calls) == 1


def test_adapter_restart_has_no_handle_persistence_or_old_execution(tmp_path, monkeypatch):
    now_ms = 1_700_000_000_000
    backend = RetentionBackend(now_ms + 120_000)
    server = _retention_server(backend)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sonarchy_mcp.server.time.time", lambda: now_ms / 1000)
    monkeypatch.setattr(
        "sonarchy_mcp.server.secrets.token_urlsafe",
        lambda _size: "mcp-restart-handle-0000000000000",
    )
    old_handle = _retention_preflight(server, 0)["planHandle"]

    restarted_backend = RetentionBackend(now_ms + 120_000)
    restarted = _retention_server(restarted_backend)
    with pytest.raises(ToolError, match="invalid or has already been used"):
        restarted.call_tool("apple_playlist_create", {"planHandle": old_handle, "approved": True})

    assert restarted.handles == {}
    assert not any(call[0] == "playlists.apple.create" for call in restarted_backend.calls)
    assert list(tmp_path.iterdir()) == []


def test_handles_and_backend_tokens_do_not_leak_beyond_issuing_preflight(monkeypatch, caplog):
    now_ms = 1_700_000_000_000
    backend = RetentionBackend(now_ms + 120_000)
    server = _retention_server(backend)
    next_handle = iter(f"mcp-leakage-handle-{index:016d}" for index in range(2))
    monkeypatch.setattr("sonarchy_mcp.server.time.time", lambda: now_ms / 1000)
    monkeypatch.setattr(
        "sonarchy_mcp.server.secrets.token_urlsafe", lambda _size: next(next_handle)
    )
    caplog.set_level(logging.DEBUG)

    apple_review = _retention_preflight(server, 0)
    apple_handle = apple_review["planHandle"]
    apple_token = server.handles[apple_handle].token
    assert apple_review["planHandle"] == apple_handle
    assert apple_token not in json.dumps(apple_review)
    execution = server.call_tool(
        "apple_playlist_create", {"planHandle": apple_handle, "approved": True}
    )
    with pytest.raises(ToolError, match="invalid or has already been used") as replay:
        server.call_tool("apple_playlist_create", {"planHandle": apple_handle, "approved": True})

    playback_review = _retention_preflight(server, 1)
    playback_handle = playback_review["planHandle"]
    playback_token = server.handles[playback_handle].token
    with pytest.raises(ToolError, match="bound to another operation") as mismatch:
        server.call_tool("apple_playlist_create", {"planHandle": playback_handle, "approved": True})

    post_preflight_public_values = [execution, replay.value, mismatch.value]
    sensitive_values = [apple_handle, apple_token, playback_handle, playback_token]
    for public_value in post_preflight_public_values:
        rendered = str(public_value)
        assert not any(secret in rendered for secret in sensitive_values)
    assert apple_handle not in json.dumps(playback_review)
    assert playback_token not in json.dumps(playback_review)
    assert not any(secret in caplog.text for secret in sensitive_values)


def test_exact_read_only_inventory_and_write_inventory():
    assert tools(frozenset()) == []
    assert [item["name"] for item in tools({"read"})] == [
        "rooms_list",
        "room_state_get",
        "content_browse",
        "apple_playlist_preflight",
        "sonos_playlist_play_preflight",
    ]
    assert [item["name"] for item in tools({"read", "playlist-create"})][-1] == (
        "apple_playlist_create"
    )
    create_names = [item["name"] for item in tools({"read", "playlist-create"})]
    assert "sonos_playlist_play" not in create_names
    play_inventory = tools({"read", "playlist-play"})
    play_names = [item["name"] for item in play_inventory]
    assert "apple_playlist_create" not in play_names
    assert play_names[-1] == "sonos_playlist_play"
    play_write = play_inventory[-1]
    assert play_write["inputSchema"] == {
        "type": "object",
        "properties": {
            "planHandle": {"type": "string", "minLength": 32, "maxLength": 128},
            "approved": {"const": True},
        },
        "required": ["planHandle", "approved"],
        "additionalProperties": False,
    }
    assert play_write["annotations"] == {
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
    }
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
        {
            "planToken": "backend-secret-ticket",
            "approved": True,
        },
    )
    with pytest.raises(ToolError, match="already been used"):
        server.call_tool(
            "apple_playlist_create", {"planHandle": review["planHandle"], "approved": True}
        )
    assert [call[0] for call in server.backend.calls].count("playlists.apple.create") == 1


@pytest.mark.parametrize(
    "args",
    (
        {"planToken": "backend-secret-ticket"},
        {"planToken": "backend-secret-ticket"},
        {"planToken": "backend-secret-ticket", "approved": False},
        {"planToken": "backend-secret-ticket", "approved": "true"},
        {
            "planToken": "backend-secret-ticket",
            "approved": True,
            "roomUid": "replacement",
        },
    ),
    ids=(
        "missing-approved",
        "token-only-execution",
        "approved-false",
        "approved-string",
        "replacement-field",
    ),
)
def test_strict_fake_backend_rejects_non_authoritative_create_shapes(args):
    backend = FakeBackend()
    with pytest.raises(ValueError, match="exactly planToken and approved: true"):
        backend.call("playlists.apple.create", args)


def test_backend_connection_change_consumes_handle_without_create_or_secret_leak():
    server = _server(write=True)
    review = server.call_tool(
        "apple_playlist_preflight",
        {"roomUid": "R1", "name": "Morning", "allowDuplicates": False, "tracks": [_track()]},
    )
    handle = review["planHandle"]
    server.backend.instance = "backend-b"
    with pytest.raises(
        ToolError,
        match=r"^Sonarchy’s backend connection changed; run a new preflight$",
    ) as changed:
        server.call_tool("apple_playlist_create", {"planHandle": handle, "approved": True})
    assert changed.value.code == "conflict"
    assert not any(call[0] == "playlists.apple.create" for call in server.backend.calls)
    assert handle not in str(changed.value)
    assert server.backend.token not in str(changed.value)

    with pytest.raises(
        ToolError, match=r"^This plan handle is invalid or has already been used$"
    ) as replay:
        server.call_tool("apple_playlist_create", {"planHandle": handle, "approved": True})
    assert replay.value.code == "conflict"
    assert handle not in str(replay.value)
    assert server.backend.token not in str(replay.value)


def test_expired_handle_is_consumed_without_create_or_secret_leak(monkeypatch):
    now = 1_700_000_000.0
    backend = FakeBackend(expires_at_epoch_ms=int((now + 1) * 1000))
    server = _server(write=True, backend=backend)
    review = server.call_tool(
        "apple_playlist_preflight",
        {"roomUid": "R1", "name": "Morning", "allowDuplicates": False, "tracks": [_track()]},
    )
    handle = review["planHandle"]
    monkeypatch.setattr("sonarchy_mcp.server.time.time", lambda: now + 2)

    with pytest.raises(
        ToolError,
        match=r"^The reviewed playlist plan expired; run a new preflight$",
    ) as expired:
        server.call_tool("apple_playlist_create", {"planHandle": handle, "approved": True})
    assert expired.value.code == "conflict"
    assert not any(call[0] == "playlists.apple.create" for call in backend.calls)
    assert handle not in str(expired.value)
    assert backend.token not in str(expired.value)

    with pytest.raises(
        ToolError, match=r"^This plan handle is invalid or has already been used$"
    ) as replay:
        server.call_tool("apple_playlist_create", {"planHandle": handle, "approved": True})
    assert replay.value.code == "conflict"
    assert handle not in str(replay.value)
    assert backend.token not in str(replay.value)


class DeviceFreeController:
    def __init__(self):
        self.calls = []

    def refresh(self, *, rediscover=True):
        self.calls.append(("refresh", rediscover))
        return {
            "type": "snapshot",
            "version": 1,
            "status": {"state": "ready", "message": ""},
            "households": [],
            "target": None,
            "playback": {},
        }

    def event_services(self):
        return {}

    def inspect_apple_playlist_target(self, room_uid, playlist_name):
        self.calls.append(("inspectApplePlaylistTarget", room_uid, playlist_name))
        return {
            "room": {
                "uid": room_uid,
                "coordinatorUid": room_uid,
                "householdFingerprint": "sha256:household",
            },
            "observedState": {
                "playlistCount": 0,
                "playlistInventoryFingerprint": "sha256:playlists",
                "capabilities": [
                    "playlist_plan.apple.validate",
                    "playlists.apple.create",
                    "direct-apple-saved-queue",
                ],
            },
        }

    def create_preflighted_apple_playlist(self, plan):
        self.calls.append(("createPreflightedApplePlaylist", copy.deepcopy(plan)))
        return {"ok": True, "playlist": {"id": "SQ:17", "name": plan["playlistName"]}}


class RecordingProtocolServer(ProtocolServer):
    def __init__(self, controller):
        super().__init__(controller)
        self.requests = []

    def handle(self, request, output):
        self.requests.append(copy.deepcopy(request))
        super().handle(request, output)


def test_device_free_mcp_socket_protocol_create_contract(tmp_path, monkeypatch, caplog):
    backend_token = "backend_contract_ticket_000000000001"  # noqa: S105
    plan_handle = "mcp_contract_handle_00000000000000000001"
    runtime_root = tmp_path / "runtime"
    controller = DeviceFreeController()
    protocol = RecordingProtocolServer(controller)
    ticket_store = next(
        service.contextual_handlers["playlist_plan.apple.validate"].__self__.tickets
        for service in protocol.application.services
        if "playlist_plan.apple.validate" in service.contextual_handlers
    )
    ticket_store._token_factory = lambda: backend_token
    monkeypatch.setattr("sonarchy_mcp.server.secrets.token_urlsafe", lambda _size: plan_handle)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime_root))
    caplog.set_level(logging.DEBUG)

    read_fd, write_fd = os.pipe()
    stdin = os.fdopen(read_fd, "rb", buffering=0)
    stdout = io.BytesIO()
    mcp = None
    with BackendOwnership.acquire(str(runtime_root)) as ownership:
        runtime = MultiClientRuntime(
            protocol,
            ownership.open_listener(),
            frozenset({"read", "playlist-create"}),
        )
        thread = threading.Thread(target=runtime.serve, args=(stdin, stdout), daemon=True)
        thread.start()
        try:
            mcp = SonarchyMcp()
            mcp.permissions = {"read", "playlist-create"}
            review = mcp.call_tool(
                "apple_playlist_preflight",
                {
                    "roomUid": "R1",
                    "name": "AI Friday",
                    "allowDuplicates": False,
                    "tracks": [_track()],
                },
            )
            assert review["planHandle"] == plan_handle
            assert "planToken" not in review
            assert backend_token not in json.dumps(review)

            mcp_create_args = {"planHandle": plan_handle, "approved": True}
            assert set(mcp_create_args) == {"planHandle", "approved"}
            assert mcp_create_args["approved"] is True
            created = mcp.call_tool("apple_playlist_create", mcp_create_args)
            assert created == {
                "ok": True,
                "playlist": {"id": "SQ:17", "name": "AI Friday"},
            }

            create_requests = [
                request
                for request in protocol.requests
                if request.get("op") == "playlists.apple.create"
            ]
            assert [request["args"] for request in create_requests] == [
                {"planToken": backend_token, "approved": True}
            ]
            executions = [
                call for call in controller.calls if call[0] == "createPreflightedApplePlaylist"
            ]
            assert len(executions) == 1
            assert [call[0] for call in controller.calls] == [
                "refresh",
                "inspectApplePlaylistTarget",
                "createPreflightedApplePlaylist",
            ]

            with pytest.raises(
                ToolError, match=r"^This plan handle is invalid or has already been used$"
            ) as replay:
                mcp.call_tool("apple_playlist_create", mcp_create_args)
            assert replay.value.code == "conflict"
            assert (
                len(
                    [
                        request
                        for request in protocol.requests
                        if request.get("op") == "playlists.apple.create"
                    ]
                )
                == 1
            )

            post_review_public_results = json.dumps(
                {
                    "create": created,
                    "replay": {"code": replay.value.code, "message": str(replay.value)},
                }
            )
            assert backend_token not in post_review_public_results
            assert plan_handle not in post_review_public_results
            assert backend_token not in caplog.text
            assert plan_handle not in caplog.text
            assert backend_token.encode() not in stdout.getvalue()
            assert plan_handle.encode() not in stdout.getvalue()
        finally:
            if mcp is not None:
                mcp.backend.close()
            os.close(write_fd)
            thread.join(timeout=3)
            stdin.close()
            assert not thread.is_alive()


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


class PlaybackMcpBackend(FakeBackend):
    def __init__(self):
        super().__init__()
        self.play_tokens = []

    def call(self, operation, args):
        if operation == "playlists.play.validate":
            self.calls.append((operation, copy.deepcopy(args)))
            token = f"backend-play-ticket-{len(self.play_tokens):032d}"
            self.play_tokens.append(token)
            return {
                "ok": True,
                "operation": "playlists.play.execute",
                "planToken": token,
                "planFingerprint": "sha256:" + ("a" * 64),
                "expiresAtEpochMs": int(time.time() * 1000) + 60_000,
                "approvalRequired": True,
                "room": {"uid": args["roomUid"], "coordinatorUid": args["roomUid"]},
                "topology": {"memberUids": [args["roomUid"]], "standalone": True},
                "playlist": {"id": args["playlistId"], "title": "Morning", "itemCount": 1},
                "queue": {"length": 2, "expectedFirstAppendedPosition": 3},
                "expectedSideEffects": ["Append and play once"],
            }
        if operation == "playlists.play.execute":
            self.calls.append((operation, copy.deepcopy(args)))
            if set(args) != {"planToken", "approved"} or args.get("approved") is not True:
                raise ValueError("Backend playback requires exactly planToken and approved: true")
            return {
                "ok": True,
                "playlist": {"id": "SQ:9", "title": "Morning"},
                "mutations": {"appendInvocationCount": 1, "playbackStartInvocationCount": 1},
            }
        return super().call(operation, args)


def playback_mcp_server():
    server = SonarchyMcp()
    server.backend = PlaybackMcpBackend()
    server.permissions = {"read", "playlist-play"}
    return server


def test_playlist_play_preflight_hides_backend_token_and_execute_claims_once():
    server = playback_mcp_server()
    review = server.call_tool(
        "sonos_playlist_play_preflight", {"roomUid": "R1", "playlistId": "SQ:9"}
    )
    handle = review["planHandle"]
    token = server.backend.play_tokens[0]

    assert handle
    assert "planToken" not in review
    assert token not in json.dumps(review)
    result = server.call_tool("sonos_playlist_play", {"planHandle": handle, "approved": True})
    assert result["playlist"] == {"id": "SQ:9", "title": "Morning"}
    assert server.backend.calls[-1] == (
        "playlists.play.execute",
        {"planToken": token, "approved": True},
    )

    with pytest.raises(ToolError, match="already been used"):
        server.call_tool("sonos_playlist_play", {"planHandle": handle, "approved": True})
    assert [call[0] for call in server.backend.calls].count("playlists.play.execute") == 1


def test_playlist_play_rejects_replacements_and_wrong_operation_handles():
    server = playback_mcp_server()
    review = server.call_tool(
        "sonos_playlist_play_preflight", {"roomUid": "R1", "playlistId": "SQ:9"}
    )
    handle = review["planHandle"]
    with pytest.raises(ToolError, match="only planHandle"):
        server.call_tool(
            "sonos_playlist_play",
            {
                "planHandle": handle,
                "approved": True,
                "roomUid": "R2",
                "playlistId": "SQ:10",
                "uri": "private",
                "queue": [],
            },
        )
    assert not any(call[0] == "playlists.play.execute" for call in server.backend.calls)

    server.permissions = {"read", "playlist-create", "playlist-play"}
    with pytest.raises(ToolError, match="another operation"):
        server.call_tool("apple_playlist_create", {"planHandle": handle, "approved": True})
    assert not any(call[0] == "playlists.apple.create" for call in server.backend.calls)


def test_fresh_second_playback_handle_is_used_and_first_review_handle_is_not():
    server = playback_mcp_server()
    first = server.call_tool(
        "sonos_playlist_play_preflight", {"roomUid": "R1", "playlistId": "SQ:9"}
    )
    second = server.call_tool(
        "sonos_playlist_play_preflight", {"roomUid": "R1", "playlistId": "SQ:9"}
    )
    assert first["planFingerprint"] == second["planFingerprint"]
    assert first["planHandle"] != second["planHandle"]

    server.call_tool("sonos_playlist_play", {"planHandle": second["planHandle"], "approved": True})
    execute_call = next(
        call for call in server.backend.calls if call[0] == "playlists.play.execute"
    )
    assert execute_call[1]["planToken"] == server.backend.play_tokens[1]
    assert execute_call[1]["planToken"] != server.backend.play_tokens[0]


def test_mcp_restart_and_backend_connection_change_fail_playback_handles_safely():
    server = playback_mcp_server()
    review = server.call_tool(
        "sonos_playlist_play_preflight", {"roomUid": "R1", "playlistId": "SQ:9"}
    )
    handle = review["planHandle"]

    restarted = playback_mcp_server()
    with pytest.raises(ToolError, match="invalid or has already been used"):
        restarted.call_tool("sonos_playlist_play", {"planHandle": handle, "approved": True})

    server.backend.instance = "backend-b"
    with pytest.raises(ToolError, match="backend connection changed"):
        server.call_tool("sonos_playlist_play", {"planHandle": handle, "approved": True})
    assert not any(call[0] == "playlists.play.execute" for call in server.backend.calls)


def test_expired_playback_handle_is_consumed_without_execution(monkeypatch):
    now = 1_700_000_000.0
    server = playback_mcp_server()
    monkeypatch.setattr("sonarchy_mcp.server.time.time", lambda: now)
    original_call = server.backend.call

    def expiring_call(operation, args):
        value = original_call(operation, args)
        if operation == "playlists.play.validate":
            value["expiresAtEpochMs"] = int((now + 1) * 1000)
        return value

    server.backend.call = expiring_call
    review = server.call_tool(
        "sonos_playlist_play_preflight", {"roomUid": "R1", "playlistId": "SQ:9"}
    )
    handle = review["planHandle"]
    monkeypatch.setattr("sonarchy_mcp.server.time.time", lambda: now + 2)

    with pytest.raises(ToolError, match="playback plan expired"):
        server.call_tool("sonos_playlist_play", {"planHandle": handle, "approved": True})
    with pytest.raises(ToolError, match="invalid or has already been used"):
        server.call_tool("sonos_playlist_play", {"planHandle": handle, "approved": True})
    assert not any(call[0] == "playlists.play.execute" for call in server.backend.calls)
