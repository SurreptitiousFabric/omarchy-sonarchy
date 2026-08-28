import io
import json
import tempfile
from unittest.mock import patch

import pytest

from sonarchy_backend.contracts import (
    CAPABILITY_NAMES,
    MAX_PROTOCOL_OPERATION_BYTES,
    MAX_PROTOCOL_REQUEST_ID_BYTES,
)
from sonarchy_backend.domains.errors import PlaylistTransactionError
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

    def browse_content(self, room_uid, kind, term, limit, context=None):
        self.calls.append(("browseContent", room_uid, kind, term, limit, context))
        return {"ok": True, "kind": kind, "items": [], "total": 0}

    def list_alarms(self, room_uid):
        self.calls.append(("listAlarms", room_uid))
        return {"ok": True, "kind": "alarms", "items": [], "total": 0}


class OversizedSnapshotController(FakeController):
    def refresh(self, *, rediscover=True):
        snapshot = super().refresh(rediscover=rediscover)
        snapshot["favorites"] = {
            "state": "ready",
            "items": [
                {
                    "id": f"favorite-{index}",
                    "title": f"oversized-favorite-{index}-" + ("界" * 300),
                    "kind": "radio",
                    "albumArtUrl": "",
                }
                for index in range(100)
            ],
            "total": 100,
            "unsupported": 0,
            "error": "",
        }
        return snapshot


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
    server.handle({"version": 1, "id": "99", "op": "wat", "args": {}}, output)
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
    server.handle(
        {
            "version": 1,
            "id": "2",
            "op": "session.panel_open.set",
            "args": {"open": True},
        },
        output,
    )
    assert server.panel_open is True
    assert decoded(output)[0]["ok"] is True


@pytest.mark.parametrize(
    "request_payload",
    (
        {"id": "3", "op": "volume.group.set", "args": {"volume": 35}},
        {"version": 1, "id": "3", "op": "setGroupVolume", "args": {"volume": 35}},
        {"version": 1, "id": "3", "op": "volume.group.set", "volume": 35},
    ),
)
def test_legacy_request_shapes_are_rejected_without_execution(request_payload):
    controller = FakeController()
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()
    server.handle(request_payload, output)
    assert controller.calls == []
    assert decoded(output)[0]["ok"] is False


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
        (
            {
                "version": 1,
                "id": "x" * (MAX_PROTOCOL_REQUEST_ID_BYTES + 1),
                "op": "state.refresh",
                "args": {},
            },
            "invalid_request",
        ),
        (
            {
                "version": 1,
                "id": "3",
                "op": "x" * (MAX_PROTOCOL_OPERATION_BYTES + 1),
                "args": {},
            },
            "invalid_request",
        ),
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


def test_protocol_emits_utf8_without_ascii_escape_expansion():
    server = ProtocolServer(FakeController())  # type: ignore[arg-type]
    output = io.StringIO()

    server._emit({"type": "result", "value": "界"}, output)

    assert "界" in output.getvalue()
    assert "\\u754c" not in output.getvalue()


def test_protocol_refuses_to_emit_an_oversized_response_line():
    server = ProtocolServer(FakeController())  # type: ignore[arg-type]
    output = io.StringIO()

    with pytest.raises(RuntimeError, match="bounded line size"):
        server._emit({"value": "x" * MAX_PROTOCOL_LINE_BYTES}, output)

    assert output.getvalue() == ""


def test_oversized_authoritative_poll_snapshot_is_replaced_by_bounded_degraded_state():
    server = ProtocolServer(OversizedSnapshotController())  # type: ignore[arg-type]
    output = io.StringIO()

    server.emit_snapshot(output)
    server.emit_snapshot(output, rediscover=False)

    messages = decoded(output)
    assert [message["revision"] for message in messages] == [1, 2]
    assert all(
        len((line + "\n").encode("utf-8")) <= MAX_PROTOCOL_LINE_BYTES
        for line in output.getvalue().splitlines()
    )
    assert all(message["status"]["state"] == "error" for message in messages)
    assert all(message["status"]["degraded"] is True for message in messages)
    assert all(message["status"]["error"]["code"] == "internal_error" for message in messages)
    assert all(message["favorites"]["items"] == [] for message in messages)
    assert all("playlists.apple.create" not in message["capabilities"] for message in messages)
    assert "oversized-favorite" not in output.getvalue()
    assert server.last_snapshot is None


def test_oversized_mutation_snapshot_does_not_hide_result_or_terminate_handling():
    controller = OversizedSnapshotController()
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()

    server.handle({"version": 1, "id": "mutate", "op": "playback.toggle", "args": {}}, output)
    server.handle(
        {
            "version": 1,
            "id": "still-alive",
            "op": "session.panel_open.set",
            "args": {"open": True},
        },
        output,
    )

    messages = decoded(output)
    assert messages[0]["id"] == "mutate"
    assert messages[0]["ok"] is True
    assert messages[1]["type"] == "snapshot"
    assert messages[1]["status"]["degraded"] is True
    assert messages[2]["id"] == "still-alive"
    assert messages[2]["ok"] is True
    assert server.panel_open is True


def test_oversized_startup_snapshot_does_not_stop_the_protocol_loop():
    server = ProtocolServer(OversizedSnapshotController())  # type: ignore[arg-type]
    output = io.StringIO()
    with tempfile.TemporaryFile(mode="w+") as input_stream:
        input_stream.write(
            '{"version":1,"id":"after-startup","op":"session.panel_open.set",'
            '"args":{"open":true}}\n'
        )
        input_stream.seek(0)

        server.serve(input_stream, output)

    messages = decoded(output)
    assert messages[0]["type"] == "snapshot"
    assert messages[0]["status"]["degraded"] is True
    assert messages[1]["id"] == "after-startup"
    assert messages[1]["ok"] is True


def test_play_favorite_dispatches_opaque_id():
    controller = FakeController()
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()
    server.handle(
        {
            "version": 1,
            "id": "4",
            "op": "content.favorite.play",
            "args": {"favoriteId": "fav-1"},
        },
        output,
    )
    assert controller.calls == [("playFavorite", "fav-1"), ("refresh", False)]
    assert decoded(output)[0]["ok"] is True


def test_move_playback_dispatches_dedicated_room_operation():
    controller = FakeController()
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()
    server.handle(
        {
            "version": 1,
            "id": "5",
            "op": "playback.room.move",
            "args": {"roomUid": "R2"},
        },
        output,
    )
    assert controller.calls == [("movePlaybackToRoom", "R2"), ("refresh", False)]
    assert decoded(output)[0]["ok"] is True


def test_select_room_dispatches_without_changing_topology():
    controller = FakeController()
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()
    server.handle(
        {
            "version": 1,
            "id": "6",
            "op": "selection.room.set",
            "args": {"roomUid": "R2"},
        },
        output,
    )
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
    ("playback.stop", {"roomUid": "R1"}, ("stop_room", "R1")),
    (
        "devices.rename",
        {"roomUid": "R1", "name": "Dining Room"},
        ("rename_room", "R1", "Dining Room"),
    ),
    (
        "playback.option.set",
        {"roomUid": "R1", "option": "repeat", "value": "one"},
        ("set_playback_option", "R1", "repeat", "one"),
    ),
    (
        "sound.setting.set",
        {"roomUid": "R1", "setting": "bass", "value": "4"},
        ("set_sound", "R1", "bass", "4"),
    ),
    (
        "devices.setting.set",
        {"roomUid": "R1", "setting": "status-light", "value": "off"},
        ("set_device", "R1", "status-light", "off"),
    ),
    (
        "sources.switch",
        {"roomUid": "R1", "source": "line-in", "sourceRoomUid": "R2"},
        ("switch_source", "R1", "line-in", "R2"),
    ),
    (
        "queue.item.play",
        {"roomUid": "R1", "index": 2, "itemId": "Q:2"},
        ("queue_action", "R1", "play-queue", 2, "Q:2"),
    ),
    (
        "queue.item.remove",
        {"roomUid": "R1", "index": 2, "itemId": "Q:2"},
        ("queue_action", "R1", "remove-queue", 2, "Q:2"),
    ),
    (
        "queue.item.move",
        {
            "roomUid": "R1",
            "index": 2,
            "itemId": "Q:2",
            "targetIndex": 0,
            "targetItemId": "Q:0",
        },
        ("move_queue_item", "R1", 2, "Q:2", 0, "Q:0"),
    ),
    ("queue.clear", {"roomUid": "R1"}, ("queue_action", "R1", "clear-queue")),
    (
        "queue.content.enqueue",
        {
            "roomUid": "R1",
            "kind": "library",
            "context": "song",
            "itemId": "L:1",
            "index": 0,
            "mode": "play",
            "libraryPath": [],
        },
        ("enqueue_content_item", "R1", "library", "song", "L:1", 0, "play", []),
    ),
    (
        "playlists.mutate",
        {"roomUid": "R1", "action": "create", "value": "Road Trip"},
        ("playlist_action", "R1", "create", "Road Trip"),
    ),
    (
        "playlists.track.mutate",
        {
            "roomUid": "R1",
            "action": "down",
            "playlistId": "SQ:1",
            "index": 0,
            "itemId": "T:1",
        },
        ("playlist_track_action", "R1", "down", "SQ:1", 0, "T:1"),
    ),
    (
        "content.apple.play",
        {"roomUid": "R1", "url": "https://music.apple.com/ch/song/example/1"},
        ("play_apple", "R1", "https://music.apple.com/ch/song/example/1"),
    ),
    (
        "content.apple.album.play",
        {"roomUid": "R1", "url": "https://music.apple.com/ch/album/example/1"},
        ("play_apple_album", "R1", "https://music.apple.com/ch/album/example/1"),
    ),
    (
        "content.global.play",
        {"roomUid": "R1", "itemId": "G:1", "term": "news"},
        ("play_global", "R1", "G:1", "news"),
    ),
    ("library.update.start", {"roomUid": "R1"}, ("start_library_update", "R1")),
    (
        "alarms.save",
        {
            "roomUid": "R1",
            "alarmId": "new",
            "alarmRoomUid": "R2",
            "time": "07:00",
            "recurrence": "DAILY",
            "volume": 25,
            "duration": 30,
            "enabled": True,
            "includeGrouped": False,
            "program": "chime",
        },
        (
            "save_alarm",
            "R1",
            "new",
            "R2",
            "07:00",
            "DAILY",
            25,
            30,
            True,
            False,
            "chime",
        ),
    ),
    (
        "alarms.toggle",
        {"roomUid": "R1", "alarmId": "7", "enabled": False},
        ("toggle_alarm", "R1", "7", False),
    ),
    (
        "alarms.delete",
        {"roomUid": "R1", "alarmId": "7"},
        ("delete_alarm", "R1", "7"),
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
        "alarms.list",
        "artwork.radio.resolve",
        "content.browse",
        "devices.details.get",
        "playlist_plan.apple.validate",
        "playlists.apple.create",
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

    assert controller.calls == [("browseContent", "R1", "queue", "", 100, None)]
    messages = decoded(output)
    assert len(messages) == 1
    assert messages[0]["value"] == {"ok": True, "kind": "queue", "items": [], "total": 0}


def test_library_content_query_forwards_hierarchy_and_page_context():
    controller = FakeController()
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()
    context = {"path": [{"id": "A:ARTIST", "index": 3}], "offset": 40}

    server.handle(
        {
            "version": 1,
            "id": "library-page",
            "op": "content.browse",
            "args": {
                "roomUid": "R1",
                "kind": "library",
                "term": "",
                "limit": 40,
                "context": context,
            },
        },
        output,
    )

    assert controller.calls == [("browseContent", "R1", "library", "", 40, context)]
    assert decoded(output)[0]["ok"] is True


def test_alarm_query_returns_value_without_snapshot_refresh():
    controller = FakeController()
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()

    server.handle(
        {
            "version": 1,
            "id": "alarms",
            "op": "alarms.list",
            "args": {"roomUid": "R1"},
        },
        output,
    )

    assert controller.calls == [("listAlarms", "R1")]
    messages = decoded(output)
    assert len(messages) == 1
    assert messages[0]["value"] == {
        "ok": True,
        "kind": "alarms",
        "items": [],
        "total": 0,
    }


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


def test_source_switch_rejects_non_string_optional_room_uid():
    controller = RecordingController()
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()

    server.handle(
        {
            "version": 1,
            "id": "source",
            "op": "sources.switch",
            "args": {"roomUid": "R1", "source": "line-in", "sourceRoomUid": 2},
        },
        output,
    )

    messages = decoded(output)
    message = messages[0]
    assert message["ok"] is False
    assert message["error"]["code"] == "invalid_argument"
    assert controller.calls == [("refresh", False)]
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
    assert set(capabilities) <= CAPABILITY_NAMES
    assert "playback.next" in capabilities
    assert "playback.seek" in capabilities
    assert "playback.previous" not in capabilities
    assert "topology.members.set" in capabilities
    assert "playlist_plan.apple.validate" in capabilities
    assert "playlists.apple.create" in capabilities


def _apple_plan_track():
    return {
        "catalogId": "1452806384",
        "url": ("https://music.apple.com/ch/album/kiss-me-kiss-me-kiss-me/1452806377?i=1452806384"),
        "title": "Just Like Heaven",
        "artist": "The Cure",
        "album": "Kiss Me, Kiss Me, Kiss Me",
        "durationMs": 212000,
    }


def _apple_target_state():
    return {
        "room": {
            "uid": "R1",
            "standalone": True,
            "memberUids": ["R1"],
            "coordinatorUid": "R1",
        },
        "observedState": {
            "topologyFingerprint": "sha256:topology",
            "queue": {
                "length": 0,
                "position": 0,
                "revisionMarker": "update:1:sha256:queue",
                "fingerprint": "sha256:queue",
                "active": False,
            },
            "transportState": "STOPPED",
            "playbackSource": "RADIO",
            "mediaFingerprint": f"sha256:{'0' * 64}",
            "volume": {"room": 20, "group": 20},
            "mute": {"room": False, "group": False},
            "capabilities": ["playlist_plan.apple.validate", "playlists.apple.create"],
            "playlistCount": 0,
            "playlistInventoryFingerprint": "sha256:playlists",
        },
    }


class ApplePlanController(FakeController):
    def __init__(self):
        super().__init__()
        self.failure = None

    def inspect_apple_playlist_target(self, room_uid, playlist_name):
        self.calls.append(("inspectApplePlaylistTarget", room_uid, playlist_name))
        return _apple_target_state()

    def create_preflighted_apple_playlist(self, plan):
        self.calls.append(("createPreflightedApplePlaylist", plan))
        if self.failure:
            raise self.failure
        return {"ok": True, "playlist": {"id": "SQ:17", "name": plan["playlistName"]}}


def _protocol_preflight(server, output):
    server.handle(
        {
            "version": 1,
            "id": "plan",
            "op": "playlist_plan.apple.validate",
            "args": {
                "roomUid": "R1",
                "playlistName": "AI Friday",
                "mode": "save-only",
                "tracks": [_apple_plan_track()],
            },
        },
        output,
    )
    return decoded(output)[-1]


def test_apple_playlist_preflight_is_read_only_and_execution_is_token_only():
    controller = ApplePlanController()
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()

    preflight = _protocol_preflight(server, output)
    assert preflight["ok"] is True
    assert preflight["revision"] == 0
    assert preflight["value"]["approvalRequired"] is True
    assert preflight["value"]["observedState"]["mediaFingerprint"].startswith("sha256:")
    assert "CurrentURI" not in json.dumps(preflight)
    assert controller.calls == [("inspectApplePlaylistTarget", "R1", "AI Friday")]

    server.handle(
        {
            "version": 1,
            "id": "create",
            "op": "playlists.apple.create",
            "args": {"planToken": preflight["value"]["planToken"], "approved": True},
        },
        output,
    )
    messages = decoded(output)
    result = next(message for message in messages if message.get("id") == "create")
    assert result["ok"] is True
    assert result["value"]["playlist"] == {"id": "SQ:17", "name": "AI Friday"}
    execution = next(
        call for call in controller.calls if call[0] == "createPreflightedApplePlaylist"
    )
    assert execution[1]["roomUid"] == "R1"
    assert execution[1]["playlistName"] == "AI Friday"
    assert execution[1]["tracks"][0]["catalogId"] == "1452806384"
    assert controller.calls[-1] == ("refresh", False)


def test_apple_playlist_execution_rejects_replacement_fields_without_consuming_ticket():
    controller = ApplePlanController()
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()
    token = _protocol_preflight(server, output)["value"]["planToken"]

    server.handle(
        {
            "version": 1,
            "id": "bad-create",
            "op": "playlists.apple.create",
            "args": {
                "planToken": token,
                "approved": True,
                "roomUid": "R2",
                "url": "https://attacker.invalid/replace",
            },
        },
        output,
    )
    error = next(message for message in decoded(output) if message.get("id") == "bad-create")
    assert error["ok"] is False
    assert error["error"]["code"] == "invalid_argument"
    assert "attacker.invalid" not in json.dumps(error)
    assert not any(call[0] == "createPreflightedApplePlaylist" for call in controller.calls)


def test_apple_playlist_failure_returns_bounded_rollback_evidence_without_raw_details():
    controller = ApplePlanController()
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()
    token = _protocol_preflight(server, output)["value"]["planToken"]
    controller.failure = PlaylistTransactionError(
        phase="playlist_verification",
        rollback={
            "attempted": True,
            "playlistRemoved": True,
            "playlistCleanupRequired": False,
            "queueRestored": False,
            "environmentUnchanged": True,
            "succeeded": False,
        },
    )

    server.handle(
        {
            "version": 1,
            "id": "failed-create",
            "op": "playlists.apple.create",
            "args": {"planToken": token, "approved": True},
        },
        output,
    )
    result = next(message for message in decoded(output) if message.get("id") == "failed-create")
    assert result["ok"] is False
    assert result["error"]["code"] == "speaker_rejected"
    assert result["error"]["details"]["phase"] == "playlist_verification"
    assert result["error"]["details"]["rollback"]["succeeded"] is False
    serialized = json.dumps(result)
    for forbidden in ("192.168", "token=", "DIDL", "CurrentURI", "service metadata"):
        assert forbidden not in serialized


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
        input_stream.write(
            '{"version":1,"id":"2","op":"session.panel_open.set","args":{"open":true}}\n'
        )
        input_stream.seek(0)
        server.serve(input_stream, output)

    messages = decoded(output)
    assert any(
        message.get("error", {}).get("message") == "Protocol message is too large"
        for message in messages
    )
    assert any(message.get("id") == "2" and message.get("ok") is True for message in messages)
