import io
import json
import tempfile
from unittest.mock import patch

import pytest

from sonarchy_backend.protocol import (
    MAX_PROTOCOL_LINE_BYTES,
    PROTOCOL_OPERATIONS,
    ProtocolServer,
)


class FakeController:
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

    def play_pause(self):
        self.calls.append(("playPause",))

    def set_group_volume(self, volume):
        self.calls.append(("setGroupVolume", volume))

    def play_favorite(self, favorite_id):
        self.calls.append(("playFavorite", favorite_id))

    def move_playback_to_room(self, room_uid):
        self.calls.append(("movePlaybackToRoom", room_uid))

    def select_room(self, room_uid):
        self.calls.append(("selectRoom", room_uid))

    def device_details(self, room_uid):
        self.calls.append(("deviceDetails", room_uid))
        return {"ok": True, "ip": "device-address", "device": {"name": "Office"}}

    def browse_content(self, room_uid, kind, term, limit):
        self.calls.append(("browseContent", room_uid, kind, term, limit))
        return {"ok": True, "kind": kind, "items": [], "total": 0}


def decoded(output):
    return [json.loads(line) for line in output.getvalue().splitlines()]


def test_mutation_emits_result_then_fresh_snapshot():
    controller = FakeController()
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()
    server.handle({"version": 1, "id": "12", "op": "playback.toggle", "args": {}}, output)
    messages = decoded(output)
    assert controller.calls == [("playPause",), ("refresh", False)]
    assert messages[0] == {
        "type": "result",
        "version": 1,
        "id": "12",
        "ok": True,
        "revision": 0,
        "value": None,
    }
    assert messages[1]["type"] == "snapshot"
    assert messages[1]["revision"] == 1


def test_unknown_operation_is_reported_without_crashing():
    controller = FakeController()
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()
    server.handle({"id": "99", "op": "wat"}, output)
    messages = decoded(output)
    assert messages == [
        {
            "type": "result",
            "version": 1,
            "id": "99",
            "ok": False,
            "revision": 0,
            "error": {
                "code": "unsupported_operation",
                "message": "Unknown operation: wat",
                "retryable": False,
                "operation": "wat",
            },
        }
    ]


def test_set_panel_open_is_local_protocol_state():
    controller = FakeController()
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()
    server.handle({"id": "2", "op": "setPanelOpen", "open": True}, output)
    assert server.panel_open is True
    assert decoded(output)[0]["ok"] is True


def test_plan_style_top_level_arguments_are_used():
    controller = FakeController()
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()
    server.handle({"id": "3", "op": "setGroupVolume", "volume": 35}, output)
    assert controller.calls == [("setGroupVolume", 35), ("refresh", False)]
    assert decoded(output)[0]["ok"] is True


def test_versioned_nested_arguments_are_used():
    controller = FakeController()
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()
    server.handle(
        {
            "version": 1,
            "id": "3",
            "op": "volume.group.set",
            "args": {"volume": 35},
        },
        output,
    )
    assert controller.calls == [("setGroupVolume", 35), ("refresh", False)]


@pytest.mark.parametrize(
    ("request_payload", "code"),
    (
        ({"version": 2, "id": "3", "op": "state.refresh", "args": {}}, "unsupported_version"),
        ({"version": 1, "id": "", "op": "state.refresh", "args": {}}, "invalid_request"),
        ({"version": 1, "id": "3", "op": "", "args": {}}, "invalid_request"),
        ({"version": 1, "id": "3", "op": "state.refresh", "args": []}, "invalid_request"),
    ),
)
def test_invalid_request_contract_is_rejected_without_execution(request_payload, code):
    controller = FakeController()
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()

    server.handle(request_payload, output)

    message = decoded(output)[0]
    assert message["version"] == 1
    assert message["ok"] is False
    assert message["error"]["code"] == code
    assert controller.calls == []


def test_play_favorite_dispatches_opaque_id():
    controller = FakeController()
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()
    server.handle({"id": "4", "op": "playFavorite", "favoriteId": "fav-1"}, output)
    assert controller.calls == [("playFavorite", "fav-1"), ("refresh", False)]
    assert decoded(output)[0]["ok"] is True


def test_move_playback_dispatches_dedicated_room_operation():
    controller = FakeController()
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()
    server.handle({"id": "5", "op": "movePlaybackToRoom", "roomUid": "R2"}, output)
    assert controller.calls == [("movePlaybackToRoom", "R2"), ("refresh", False)]
    assert decoded(output)[0]["ok"] is True


def test_select_room_dispatches_without_changing_topology():
    controller = FakeController()
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()
    server.handle({"id": "6", "op": "selectRoom", "roomUid": "R2"}, output)
    assert controller.calls == [("selectRoom", "R2"), ("refresh", False)]
    assert decoded(output)[0]["ok"] is True


PROTOCOL_ACTION_CASES = (
    ("playback.toggle", {}, ("play_pause",)),
    ("playback.play", {}, ("play",)),
    ("playback.pause", {}, ("pause",)),
    ("playback.next", {}, ("next",)),
    ("playback.previous", {}, ("previous",)),
    ("playback.seek", {"positionSec": 42}, ("seek", 42)),
    ("content.favorite.play", {"favoriteId": "fav-1"}, ("play_favorite", "fav-1")),
    ("content.favorites.refresh", {}, ("refresh_favorites",)),
    (
        "playback.room.move",
        {"roomUid": "R2"},
        ("move_playback_to_room", "R2"),
    ),
    ("selection.group.set", {"groupUid": "G2"}, ("select_group", "G2")),
    ("selection.room.set", {"roomUid": "R2"}, ("select_room", "R2")),
    ("volume.group.set", {"volume": 35}, ("set_group_volume", 35)),
    ("volume.group.adjust", {"delta": -2}, ("adjust_group_volume", -2)),
    ("mute.group.set", {"mute": True}, ("set_group_mute", True)),
    (
        "volume.room.set",
        {"roomUid": "R2", "volume": 21},
        ("set_room_volume", "R2", 21),
    ),
    (
        "volume.room.adjust",
        {"roomUid": "R2", "delta": 2},
        ("adjust_room_volume", "R2", 2),
    ),
    (
        "mute.room.set",
        {"roomUid": "R2", "mute": False},
        ("set_room_mute", "R2", False),
    ),
    (
        "topology.members.set",
        {"roomUids": ["R1", "R2"]},
        ("apply_members", ["R1", "R2"]),
    ),
)


class RecordingController:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def record(*args):
            self.calls.append((name, *args))

        return record

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


def test_protocol_action_cases_cover_every_operation():
    assert {case[0] for case in PROTOCOL_ACTION_CASES} == PROTOCOL_OPERATIONS - {
        "artwork.radio.resolve",
        "content.browse",
        "devices.details.get",
    }


def test_device_details_query_returns_value_without_snapshot_refresh():
    controller = FakeController()
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()

    server.handle(
        {
            "version": 1,
            "id": "details",
            "op": "devices.details.get",
            "args": {"roomUid": "R1"},
        },
        output,
    )

    assert controller.calls == [("deviceDetails", "R1")]
    assert decoded(output) == [
        {
            "type": "result",
            "version": 1,
            "id": "details",
            "ok": True,
            "revision": 0,
            "value": {"ok": True, "ip": "device-address", "device": {"name": "Office"}},
        }
    ]


def test_artwork_query_returns_value_without_speaker_refresh():
    controller = FakeController()
    output = io.StringIO()
    result = {
        "ok": True,
        "match": True,
        "artwork_url": "https://example.test/art.jpg",
        "confidence": 0.9,
    }
    with patch(
        "sonarchy_backend.domains.artwork.resolve_apple_artwork", return_value=result
    ) as resolve:
        server = ProtocolServer(controller)  # type: ignore[arg-type]
        server.handle(
            {
                "version": 1,
                "id": "artwork",
                "op": "artwork.radio.resolve",
                "args": {"title": "Track", "artist": "Artist"},
            },
            output,
        )

    resolve.assert_called_once_with("Track", "Artist")
    assert controller.calls == []
    message = decoded(output)[0]
    assert message["ok"] is True
    assert message["value"] == result


def test_content_query_returns_value_without_snapshot_refresh():
    controller = FakeController()
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()

    server.handle(
        {
            "version": 1,
            "id": "content",
            "op": "content.browse",
            "args": {"roomUid": "R1", "kind": "queue", "term": "", "limit": 100},
        },
        output,
    )

    assert controller.calls == [("browseContent", "R1", "queue", "", 100)]
    messages = decoded(output)
    assert len(messages) == 1
    assert messages[0]["value"] == {"ok": True, "kind": "queue", "items": [], "total": 0}


@pytest.mark.parametrize(("operation", "arguments", "expected"), PROTOCOL_ACTION_CASES)
def test_every_protocol_operation_dispatches_and_refreshes(operation, arguments, expected):
    controller = RecordingController()
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()

    server.handle({"version": 1, "id": "matrix", "op": operation, "args": arguments}, output)

    assert controller.calls == [expected, ("refresh", False)]
    messages = decoded(output)
    assert messages[0] == {
        "type": "result",
        "version": 1,
        "id": "matrix",
        "ok": True,
        "revision": 0,
        "value": None,
    }
    assert messages[1]["type"] == "snapshot"
    assert messages[1]["revision"] == 1


@pytest.mark.parametrize(
    ("operation", "arguments", "expected_message"),
    (
        ("playback.seek", {}, "positionSec must be a finite number"),
        ("content.favorite.play", {"favoriteId": ""}, "favoriteId must be a non-empty string"),
        (
            "topology.members.set",
            {"roomUids": ["R1", "R1"]},
            "roomUids must not contain duplicates",
        ),
        ("mute.room.set", {"roomUid": "R1", "mute": "yes"}, "mute must be true or false"),
    ),
)
def test_each_domain_rejects_invalid_arguments_before_command(
    operation, arguments, expected_message
):
    controller = RecordingController()
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()

    server.handle({"version": 1, "id": "invalid", "op": operation, "args": arguments}, output)

    messages = decoded(output)
    assert messages[0]["error"] == {
        "code": "invalid_argument",
        "message": expected_message,
        "retryable": False,
        "operation": operation,
    }
    assert controller.calls == [("refresh", False)]
    assert messages[1]["type"] == "snapshot"


def test_refresh_exception_becomes_error_snapshot():
    class BrokenController(FakeController):
        def refresh(self, *, rediscover=True):
            raise RuntimeError("network exploded")

    server = ProtocolServer(BrokenController())  # type: ignore[arg-type]
    output = io.StringIO()
    server.emit_snapshot(output)
    message = decoded(output)[0]
    assert message["type"] == "snapshot"
    assert message["status"]["state"] == "error"
    assert message["favorites"]["state"] == "not_loaded"
    assert message["status"]["error"]["code"] == "internal_error"
    assert message["status"]["error"]["retryable"] is True
    assert "network exploded" not in message["status"]["message"]


def test_refresh_network_error_is_classified_and_redacted():
    class BrokenController(FakeController):
        def refresh(self, *, rediscover=True):
            raise OSError("failed at http://203.0.113.20/device")

    server = ProtocolServer(BrokenController())  # type: ignore[arg-type]
    output = io.StringIO()
    server.emit_snapshot(output)

    status = decoded(output)[0]["status"]
    assert status["error"]["code"] == "network_error"
    assert "203.0.113.20" not in json.dumps(status)


def test_refresh_exception_retains_last_good_playback_snapshot():
    class FlakyController(FakeController):
        def __init__(self):
            super().__init__()
            self.fail = False

        def refresh(self, *, rediscover=True):
            if self.fail:
                raise OSError("speaker temporarily unavailable")
            return {
                "type": "snapshot",
                "version": 1,
                "status": {"state": "ready", "message": ""},
                "households": [],
                "target": {"roomLabel": "Office"},
                "playback": {
                    "state": "PLAYING",
                    "title": "The Last Good Track",
                    "artworkUrl": "https://example.test/art.png",
                },
            }

    controller = FlakyController()
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()
    server.emit_snapshot(output)
    controller.fail = True
    server.emit_snapshot(output)

    message = decoded(output)[-1]
    assert message["status"]["state"] == "ready"
    assert message["status"]["degraded"] is True
    assert message["playback"]["state"] == "PLAYING"
    assert message["playback"]["title"] == "The Last Good Track"
    assert message["playback"]["artworkUrl"] == "https://example.test/art.png"
    assert message["playback"]["stale"] is True


def test_snapshot_revisions_are_monotonic():
    server = ProtocolServer(FakeController())  # type: ignore[arg-type]
    output = io.StringIO()

    server.emit_snapshot(output)
    server.emit_snapshot(output, rediscover=False)

    assert [message["revision"] for message in decoded(output)] == [1, 2]


def test_snapshot_capabilities_come_from_topology_and_advertised_actions():
    class CapableController(FakeController):
        def refresh(self, *, rediscover=True):
            return {
                "type": "snapshot",
                "version": 1,
                "status": {"state": "ready", "message": ""},
                "households": [
                    {
                        "id": "HH1",
                        "rooms": [{"uid": "R1"}, {"uid": "R2"}],
                        "groups": [{"uid": "G1"}],
                    }
                ],
                "target": {"groupUid": "G1"},
                "playback": {"availableActions": ["Next", "SeekTime"]},
            }

    server = ProtocolServer(CapableController())  # type: ignore[arg-type]
    output = io.StringIO()
    server.emit_snapshot(output)

    capabilities = decoded(output)[0]["capabilities"]
    assert capabilities == sorted(capabilities)
    assert "playback.next" in capabilities
    assert "playback.seek" in capabilities
    assert "playback.previous" not in capabilities
    assert "topology.members.set" in capabilities


@pytest.mark.parametrize(
    ("error", "code", "message"),
    (
        (
            OSError("connection failed at http://203.0.113.20/device"),
            "network_error",
            "A Sonos speaker could not be reached. Check the network and try again.",
        ),
        (
            RuntimeError("raw backend detail"),
            "internal_error",
            "Sonos could not complete that action",
        ),
    ),
)
def test_command_errors_are_classified_without_leaking_raw_details(error, code, message):
    class BrokenController(FakeController):
        def play_pause(self):
            raise error

    server = ProtocolServer(BrokenController())  # type: ignore[arg-type]
    output = io.StringIO()
    server.handle({"version": 1, "id": "broken", "op": "playback.toggle", "args": {}}, output)

    result = decoded(output)[0]
    assert result["error"]["code"] == code
    assert result["error"]["message"] == message
    assert result["error"]["retryable"] is isinstance(error, OSError)


def test_oversized_protocol_line_is_rejected_and_service_stays_alive():
    controller = FakeController()
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()
    with tempfile.TemporaryFile(mode="w+") as input_stream:
        input_stream.write("x" * (MAX_PROTOCOL_LINE_BYTES + 10) + "\n")
        input_stream.write('{"id":"2","op":"setPanelOpen","open":true}\n')
        input_stream.seek(0)
        server.serve(input_stream, output)

    messages = decoded(output)
    assert any(
        message.get("error", {}).get("message") == "Protocol message is too large"
        for message in messages
    )
    assert any(message.get("id") == "2" and message.get("ok") is True for message in messages)
