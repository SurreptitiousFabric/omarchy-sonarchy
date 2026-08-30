import io
import json
import tempfile
from unittest.mock import patch

import pytest

from sonarchy_backend.contracts import (
    CAPABILITY_NAMES,
    MAX_PROTOCOL_OPERATION_BYTES,
    MAX_PROTOCOL_REQUEST_ID_BYTES,
    protocol_line,
    result_payload,
)
from sonarchy_backend.domains.browse_bounds import (
    BROWSE_ACTION_URL_BYTES,
    BROWSE_IDENTITY_BYTES,
    BROWSE_PLAYLIST_ID_BYTES,
    bound_browse_result,
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


class BrowseResultController(FakeController):
    def __init__(self, result):
        super().__init__()
        self.result = result

    def browse_content(self, room_uid, kind, term, limit, context=None):
        self.calls.append(("browseContent", room_uid, kind, term, limit, context))
        return self.result


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


@pytest.mark.parametrize("version", (2, True, None, [2, "private"], {"private": 2}))
def test_unsupported_versions_use_one_fixed_bounded_correlated_error(version):
    controller = FakeController()
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()

    server.handle(
        {
            "version": version,
            "id": "unsupported-correlated",
            "op": "state.refresh",
            "args": {},
        },
        output,
    )

    line = output.getvalue()
    result = json.loads(line)
    assert result["id"] == "unsupported-correlated"
    assert result["error"] == {
        "code": "unsupported_version",
        "message": "Unsupported protocol version",
        "retryable": False,
        "operation": "state.refresh",
    }
    assert len(line.encode("utf-8")) < MAX_PROTOCOL_LINE_BYTES
    assert "private" not in line


def test_large_unsupported_version_is_bounded_redacted_and_server_survives():
    private_version = "private-version-fragment-" + ("x" * 65_300)
    invalid_request = {
        "version": private_version,
        "id": "large-version",
        "op": "session.panel_open.set",
        "args": {},
    }
    invalid_line = protocol_line(invalid_request)
    assert len(invalid_line.encode("utf-8")) < MAX_PROTOCOL_LINE_BYTES

    controller = FakeController()
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()
    with tempfile.TemporaryFile(mode="w+") as input_stream:
        input_stream.write(invalid_line)
        input_stream.write(
            '{"version":1,"id":"after-invalid-version",'
            '"op":"session.panel_open.set","args":{"open":true}}\n'
        )
        input_stream.seek(0)
        server.serve(input_stream, output)

    messages = decoded(output)
    invalid_result = next(message for message in messages if message.get("id") == "large-version")
    later_result = next(
        message for message in messages if message.get("id") == "after-invalid-version"
    )
    assert invalid_result["error"]["code"] == "unsupported_version"
    assert invalid_result["error"]["message"] == "Unsupported protocol version"
    assert invalid_result["error"]["operation"] == "session.panel_open.set"
    invalid_result_line = protocol_line(invalid_result)
    assert len(invalid_result_line.encode("utf-8")) < MAX_PROTOCOL_LINE_BYTES
    assert private_version not in output.getvalue()
    assert "private-version-fragment" not in output.getvalue()
    assert later_result["ok"] is True
    assert server.panel_open is True


def test_unsupported_version_does_not_echo_an_oversized_request_id():
    server = ProtocolServer(FakeController())  # type: ignore[arg-type]
    output = io.StringIO()

    server.handle(
        {
            "version": 2,
            "id": "private-id-" + ("x" * MAX_PROTOCOL_REQUEST_ID_BYTES),
            "op": "state.refresh",
            "args": {},
        },
        output,
    )

    result = decoded(output)[0]
    assert result["id"] == ""
    assert result["error"]["message"] == "Unsupported protocol version"
    assert "private-id" not in output.getvalue()


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
    assert messages[0]["value"] == {
        "ok": True,
        "kind": "queue",
        "items": [],
        "total": 0,
        "returned_count": 0,
        "requested_limit": 100,
        "result_truncated": False,
    }


def _oversized_browse_value(kind):
    long_text = "Title\n" + ("界" * 1000)
    long_artwork = "https://is1-ssl.mzstatic.com/" + ("a" * 3000) + ".jpg"
    items = [
        {
            "id": (
                f"SQ:{index}"
                if kind == "playlists"
                else str(9_000_000_000 + index)
                if kind.startswith("apple")
                else f"{kind}-identity-{index}-" + ("i" * 480)
            ),
            "index": index,
            "title": long_text,
            "subtitle": "Subtitle\t" + ("λ" * 1000),
            "album_art": long_artwork,
            "playable": True,
        }
        for index in range(100)
    ]
    value = {"ok": True, "kind": kind, "items": items, "total": 237}
    if kind == "playlist":
        value.update(playlist_id="SQ:999", playlist_title=long_text)
    elif kind == "library":
        value.update(
            shares=[long_text] * 32,
            breadcrumbs=[
                {"id": "A:ARTIST", "index": 0, "title": long_text},
                {"id": "A:ALBUM", "index": 4, "title": long_text},
            ],
            path=[{"id": "A:ARTIST", "index": 0}, {"id": "A:ALBUM", "index": 4}],
            current_title=long_text,
            offset=40,
            page_size=100,
            has_previous=True,
            has_next=False,
        )
    elif kind.startswith("apple"):
        value["current_title"] = long_text
        for index, item in enumerate(items):
            item["url"] = f"https://music.apple.com/ch/song/example/{index}?i={index}"
            item["album_url"] = f"https://music.apple.com/ch/album/example/{index}"
    return value


@pytest.mark.parametrize(
    "kind",
    (
        "queue",
        "favorites",
        "playlists",
        "playlist",
        "library",
        "global",
        "apple",
        "apple-artist",
        "apple-album",
    ),
)
def test_large_browse_pages_return_successful_exact_prefixes_with_bounded_envelopes(kind):
    source = _oversized_browse_value(kind)
    controller = BrowseResultController(source)
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    server.revision = (1 << 63) - 1
    output = io.StringIO()
    request_id = "\\" * MAX_PROTOCOL_REQUEST_ID_BYTES

    server.handle(
        {
            "version": 1,
            "id": request_id,
            "op": "content.browse",
            "args": {"roomUid": "R1", "kind": kind, "term": "", "limit": 100},
        },
        output,
    )

    line = output.getvalue()
    message = json.loads(line)
    value = message["value"]
    assert message["ok"] is True
    assert len(line.encode("utf-8")) <= MAX_PROTOCOL_LINE_BYTES
    assert 0 < value["returned_count"] == len(value["items"]) < 100
    assert value["requested_limit"] == 100
    assert value["result_truncated"] is True
    assert value["total"] == 237
    assert [item["id"] for item in value["items"]] == [
        item["id"] for item in source["items"][: value["returned_count"]]
    ]
    assert all(not item["id"].endswith("…") for item in value["items"])
    assert all(
        "\n" not in item["title"] and "\t" not in item["subtitle"] for item in value["items"]
    )
    assert all(item["title"].endswith("…") for item in value["items"])
    assert all(item["album_art"] == "" for item in value["items"])
    if kind == "library":
        assert value["offset"] == 40
        assert value["has_next"] is True
        assert value["next_offset"] == 40 + value["returned_count"]
        assert value["path"] == source["path"]


def test_browse_bounding_preserves_complete_action_identities_and_unicode_boundaries():
    source = _oversized_browse_value("apple")
    controller = BrowseResultController(source)
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()

    server.handle(
        {
            "version": 1,
            "id": "identity",
            "op": "content.browse",
            "args": {"roomUid": "R1", "kind": "apple", "term": "x", "limit": 100},
        },
        output,
    )

    value = decoded(output)[0]["value"]
    for index, item in enumerate(value["items"]):
        assert item["id"] == source["items"][index]["id"]
        assert item["url"] == source["items"][index]["url"]
        assert item["album_url"] == source["items"][index]["album_url"]
        item["title"].encode("utf-8").decode("utf-8")


def test_invalid_non_library_identity_omits_only_that_item_without_partial_identity():
    source = _oversized_browse_value("queue")
    source["items"][3]["id"] = "invalid\nidentity"
    controller = BrowseResultController(source)
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()

    server.handle(
        {
            "version": 1,
            "id": "identity-stop",
            "op": "content.browse",
            "args": {"roomUid": "R1", "kind": "queue", "term": "", "limit": 100},
        },
        output,
    )

    value = decoded(output)[0]["value"]
    expected = [item["id"] for index, item in enumerate(source["items"]) if index != 3]
    assert [item["id"] for item in value["items"]] == expected[: value["returned_count"]]
    assert value["omitted_count"] == 1
    assert value["result_truncated"] is True


NON_LIBRARY_BROWSE_KINDS = (
    "queue",
    "favorites",
    "playlists",
    "playlist",
    "global",
    "apple",
    "apple-artist",
    "apple-album",
)


def _identity_test_item(index):
    return {
        "id": f"item-{index}",
        "url": f"https://music.apple.com/ch/song/example/{index}",
        "album_url": f"https://music.apple.com/ch/album/example/{index}",
        "title": f"Item {index}",
        "subtitle": "Artist",
        "album_art": "",
        "playable": True,
    }


@pytest.mark.parametrize("kind", NON_LIBRARY_BROWSE_KINDS)
@pytest.mark.parametrize("invalid_positions", ((0,), (2,), (0, 2, 4)))
def test_non_library_kinds_skip_invalid_identities_and_preserve_later_order(
    kind, invalid_positions
):
    items = [_identity_test_item(index) for index in range(6)]
    for index in invalid_positions:
        items[index]["id"] = "invalid\nidentity"
    source = {"ok": True, "kind": kind, "items": items, "total": 19}

    value = bound_browse_result(source, revision=0, requested_limit=100)

    assert [item["id"] for item in value["items"]] == [
        f"item-{index}" for index in range(6) if index not in invalid_positions
    ]
    assert value["returned_count"] == len(value["items"])
    assert value["omitted_count"] == len(invalid_positions)
    assert value["result_truncated"] is True
    assert value["total"] == 19
    assert "next_offset" not in value


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    (
        ("id", "x" * (BROWSE_IDENTITY_BYTES + 1)),
        ("url", "x" * (BROWSE_ACTION_URL_BYTES + 1)),
        ("album_url", "x" * (BROWSE_ACTION_URL_BYTES + 1)),
        ("id", "controlled\tidentity"),
        ("id", ""),
    ),
)
@pytest.mark.parametrize("kind", NON_LIBRARY_BROWSE_KINDS)
def test_non_library_identity_failures_are_whole_item_omissions(kind, field, invalid_value):
    items = [_identity_test_item(index) for index in range(3)]
    items[1][field] = invalid_value

    value = bound_browse_result(
        {"ok": True, "kind": kind, "items": items, "total": 3},
        revision=0,
        requested_limit=100,
    )

    assert [item["id"] for item in value["items"]] == ["item-0", "item-2"]
    assert value["omitted_count"] == 1
    assert value["returned_count"] == 2
    assert all(item["title"] != "Item 1" for item in value["items"])
    if invalid_value:
        assert invalid_value not in json.dumps(value)


@pytest.mark.parametrize("kind", NON_LIBRARY_BROWSE_KINDS)
def test_non_library_exact_limit_identity_is_retained_and_one_over_is_omitted(kind):
    items = [_identity_test_item(index) for index in range(3)]
    items[0]["id"] = "i" * BROWSE_IDENTITY_BYTES
    items[1]["url"] = "u" * BROWSE_ACTION_URL_BYTES
    items[2]["album_url"] = "a" * (BROWSE_ACTION_URL_BYTES + 1)

    value = bound_browse_result(
        {"ok": True, "kind": kind, "items": items, "total": 3},
        revision=0,
        requested_limit=100,
    )

    assert value["items"][0]["id"] == "i" * BROWSE_IDENTITY_BYTES
    assert value["items"][1]["url"] == "u" * BROWSE_ACTION_URL_BYTES
    assert [item["title"] for item in value["items"]] == ["Item 0", "Item 1"]
    assert value["omitted_count"] == 1


@pytest.mark.parametrize("kind", NON_LIBRARY_BROWSE_KINDS)
def test_non_library_aggregate_reduction_runs_after_invalid_filtering(kind):
    items = [_identity_test_item(index) for index in range(8)]
    items[1]["id"] = "invalid\nidentity"
    items[5]["url"] = "x" * (BROWSE_ACTION_URL_BYTES + 1)

    with patch(
        "sonarchy_backend.domains.browse_bounds._fits_complete_envelope",
        side_effect=lambda value, _revision: len(value["items"]) <= 3,
    ):
        value = bound_browse_result(
            {"ok": True, "kind": kind, "items": items, "total": 20},
            revision=0,
            requested_limit=100,
        )

    assert [item["id"] for item in value["items"]] == ["item-0", "item-2", "item-3"]
    assert value["omitted_count"] == 2
    assert value["returned_count"] == 3
    assert value["result_truncated"] is True
    assert value["total"] == 20


def test_invalid_non_library_page_keeps_protocol_server_alive_for_later_request():
    items = [_identity_test_item(index) for index in range(3)]
    items[0]["url"] = "x" * (BROWSE_ACTION_URL_BYTES + 1)
    controller = BrowseResultController({"ok": True, "kind": "apple", "items": items, "total": 3})
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()

    server.handle(
        {
            "version": 1,
            "id": "invalid-page",
            "op": "content.browse",
            "args": {"roomUid": "R1", "kind": "apple", "term": "x", "limit": 100},
        },
        output,
    )
    server.handle(
        {"version": 1, "id": "later", "op": "alarms.list", "args": {"roomUid": "R1"}},
        output,
    )

    messages = decoded(output)
    assert [message["id"] for message in messages] == ["invalid-page", "later"]
    assert all(message["ok"] is True for message in messages)
    assert [item["id"] for item in messages[0]["value"]["items"]] == ["item-1", "item-2"]


def _library_page(offset, count, total=100):
    return {
        "ok": True,
        "kind": "library",
        "items": [
            {
                "id": f"library-item-{offset + index}",
                "index": offset + index,
                "title": f"Item {offset + index}",
                "subtitle": "Artist",
                "album_art": "",
                "playable": True,
            }
            for index in range(count)
        ],
        "total": total,
        "offset": offset,
        "page_size": 100,
        "next_offset": min(total, offset + count),
        "has_previous": offset > 0,
        "has_next": offset + count < total,
    }


def test_library_byte_reduction_returns_exact_continuation_without_gaps():
    first_source = _library_page(0, 100)
    second_source = _library_page(20, 80)

    with patch(
        "sonarchy_backend.domains.browse_bounds._fits_complete_envelope",
        side_effect=lambda value, _revision: len(value["items"]) <= 20,
    ):
        first = bound_browse_result(first_source, revision=0, requested_limit=100)
    with patch(
        "sonarchy_backend.domains.browse_bounds._fits_complete_envelope",
        side_effect=lambda value, _revision: len(value["items"]) <= 17,
    ):
        second = bound_browse_result(second_source, revision=0, requested_limit=100)

    assert first["returned_count"] == 20
    assert first["next_offset"] == 20
    assert first["has_next"] is True
    assert second["returned_count"] == 17
    assert second["next_offset"] == 37
    assert [item["id"] for item in first["items"] + second["items"]] == [
        f"library-item-{index}" for index in range(37)
    ]


def test_library_final_page_and_invalid_identity_have_bounded_progress_semantics():
    final = bound_browse_result(_library_page(90, 10), revision=0, requested_limit=100)
    invalid = _library_page(0, 100)
    invalid["items"][0]["id"] = "invalid\nidentity"
    omitted = bound_browse_result(invalid, revision=0, requested_limit=100)
    empty = bound_browse_result(_library_page(0, 0), revision=0, requested_limit=100)
    bounded_terminal = bound_browse_result(
        _library_page(1_000_000, 1, total=2_000_000), revision=0, requested_limit=100
    )

    assert final["next_offset"] == 100
    assert final["has_next"] is False
    assert omitted["items"] == []
    assert omitted["returned_count"] == 0
    assert omitted["omitted_count"] == 1
    assert omitted["next_offset"] == 1
    assert omitted["has_next"] is True
    assert empty["next_offset"] == 0
    assert empty["has_next"] is False
    assert bounded_terminal["next_offset"] == 1_000_000
    assert bounded_terminal["has_next"] is False


def test_oversized_first_library_identity_is_omitted_and_later_item_is_reachable():
    source = _library_page(0, 3, total=3)
    source["items"][0]["id"] = "x" * (BROWSE_IDENTITY_BYTES + 1)

    first = bound_browse_result(source, revision=0, requested_limit=100)
    second = bound_browse_result(
        {
            **_library_page(1, 2, total=3),
            "items": source["items"][1:],
        },
        revision=0,
        requested_limit=100,
    )

    assert first["items"] == []
    assert first["returned_count"] == 0
    assert first["omitted_count"] == 1
    assert first["result_truncated"] is True
    assert first["next_offset"] == 1
    assert first["has_next"] is True
    assert [item["id"] for item in second["items"]] == ["library-item-1", "library-item-2"]


def test_oversized_middle_identity_consumes_only_that_provider_position():
    source = _library_page(0, 8, total=8)
    source["items"][5]["id"] = "x" * (BROWSE_IDENTITY_BYTES + 1)

    first = bound_browse_result(source, revision=0, requested_limit=100)
    second = bound_browse_result(
        {**_library_page(6, 2, total=8), "items": source["items"][6:]},
        revision=0,
        requested_limit=100,
    )

    assert [item["id"] for item in first["items"]] == [
        f"library-item-{index}" for index in range(5)
    ]
    assert first["omitted_count"] == 1
    assert first["next_offset"] == 6
    assert [item["id"] for item in second["items"]] == ["library-item-6", "library-item-7"]


def test_aggregate_reduction_does_not_consume_a_later_invalid_identity():
    source = _library_page(0, 10, total=10)
    source["items"][5]["id"] = "x" * (BROWSE_IDENTITY_BYTES + 1)

    with patch(
        "sonarchy_backend.domains.browse_bounds._fits_complete_envelope",
        side_effect=lambda value, _revision: len(value["items"]) <= 3,
    ):
        value = bound_browse_result(source, revision=0, requested_limit=100)

    assert [item["id"] for item in value["items"]] == [
        "library-item-0",
        "library-item-1",
        "library-item-2",
    ]
    assert value["next_offset"] == 3
    assert value["has_next"] is True


@pytest.mark.parametrize("field", ("id", "url", "album_url"))
def test_browse_item_identity_fields_are_complete_at_limit_and_omitted_over_limit(field):
    maximum = BROWSE_IDENTITY_BYTES if field == "id" else BROWSE_ACTION_URL_BYTES
    item = {
        "id": "i" * BROWSE_IDENTITY_BYTES,
        "title": "Item",
        "subtitle": "",
        "album_art": "",
        "playable": True,
    }
    item[field] = "x" * maximum
    retained = bound_browse_result(
        {"ok": True, "kind": "apple", "items": [item], "total": 1},
        revision=(1 << 63) - 1,
        requested_limit=100,
    )
    item[field] += "x"
    omitted = bound_browse_result(
        {"ok": True, "kind": "apple", "items": [item], "total": 1},
        revision=(1 << 63) - 1,
        requested_limit=100,
    )

    assert retained["items"][0][field] == "x" * maximum
    assert omitted["items"] == []
    assert omitted["omitted_count"] == 1


def test_browse_navigation_identities_keep_only_one_matching_exact_safe_prefix():
    exact = "n" * BROWSE_IDENTITY_BYTES
    oversized = "n" * (BROWSE_IDENTITY_BYTES + 1)
    value = _library_page(0, 1)
    value["breadcrumbs"] = [
        {"id": exact, "index": 0, "title": "Safe"},
        {"id": oversized, "index": 1, "title": "Unsafe"},
    ]
    value["path"] = [
        {"id": exact, "index": 0},
        {"id": oversized, "index": 1},
    ]

    bounded = bound_browse_result(value, revision=0, requested_limit=100)

    assert bounded["breadcrumbs"] == [{"id": exact, "index": 0, "title": "Safe"}]
    assert bounded["path"] == [{"id": exact, "index": 0}]

    mismatched = _library_page(0, 1)
    mismatched["breadcrumbs"] = [{"id": "A", "index": 0, "title": "A"}]
    mismatched["path"] = [{"id": "B", "index": 0}]
    bounded_mismatch = bound_browse_result(mismatched, revision=0, requested_limit=100)
    assert bounded_mismatch["breadcrumbs"] == []
    assert bounded_mismatch["path"] == []


def test_maximum_identity_item_fits_worst_case_complete_envelope_and_playlist_id_is_bounded():
    item = {
        "id": "\\" * BROWSE_IDENTITY_BYTES,
        "url": "\\" * BROWSE_ACTION_URL_BYTES,
        "album_url": "\\" * BROWSE_ACTION_URL_BYTES,
        "title": "界" * 200,
        "subtitle": "λ" * 400,
        "album_art": "https://is1-ssl.mzstatic.com/" + ("a" * 1900),
        "playable": True,
    }
    value = bound_browse_result(
        {"ok": True, "kind": "apple", "items": [item], "total": 1},
        revision=(1 << 63) - 1,
        requested_limit=100,
    )
    envelope = result_payload(
        "\\" * MAX_PROTOCOL_REQUEST_ID_BYTES,
        revision=(1 << 63) - 1,
        value=value,
    )

    assert value["items"][0]["id"] == item["id"]
    assert value["items"][0]["url"] == item["url"]
    assert value["items"][0]["album_url"] == item["album_url"]
    assert len(protocol_line(envelope).encode("utf-8")) < MAX_PROTOCOL_LINE_BYTES

    playlist = {"ok": True, "kind": "playlist", "playlist_id": "S" * 32, "items": [], "total": 0}
    assert bound_browse_result(playlist, revision=0, requested_limit=100)["playlist_id"] == "S" * 32
    playlist["playlist_id"] = "S" * (BROWSE_PLAYLIST_ID_BYTES + 1)
    with pytest.raises(ValueError, match="playlist identity"):
        bound_browse_result(playlist, revision=0, requested_limit=100)


def test_display_and_artwork_bounding_is_deterministic_and_leaves_small_values_unchanged():
    short_artwork = "https://is1-ssl.mzstatic.com/image/cover.jpg"
    result = {
        "ok": True,
        "kind": "queue",
        "items": [
            {
                "id": "Q:1",
                "title": "Short title",
                "subtitle": "Artist",
                "album_art": short_artwork,
                "playable": True,
            },
            {
                "id": "Q:2",
                "title": "Long\n" + ("界" * 1000),
                "subtitle": "Artist\t" + ("λ" * 1000),
                "album_art": "https://is1-ssl.mzstatic.com/" + ("a" * 3000),
                "playable": True,
            },
        ],
        "total": 2,
    }

    outputs = []
    for request_id in ("first", "second"):
        server = ProtocolServer(BrowseResultController(result))  # type: ignore[arg-type]
        output = io.StringIO()
        server.handle(
            {
                "version": 1,
                "id": request_id,
                "op": "content.browse",
                "args": {"roomUid": "R1", "kind": "queue", "term": "", "limit": 100},
            },
            output,
        )
        outputs.append(decoded(output)[0]["value"])

    assert outputs[0] == outputs[1]
    assert outputs[0]["items"][0] == result["items"][0]
    assert outputs[0]["items"][1]["title"].endswith("…")
    assert "\n" not in outputs[0]["items"][1]["title"]
    assert outputs[0]["items"][1]["album_art"] == ""


def test_oversized_browse_result_does_not_prevent_a_later_request():
    controller = BrowseResultController(_oversized_browse_value("queue"))
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()

    server.handle(
        {
            "version": 1,
            "id": "large",
            "op": "content.browse",
            "args": {"roomUid": "R1", "kind": "queue", "term": "", "limit": 100},
        },
        output,
    )
    server.handle(
        {"version": 1, "id": "later", "op": "alarms.list", "args": {"roomUid": "R1"}},
        output,
    )

    messages = decoded(output)
    assert [message["id"] for message in messages] == ["large", "later"]
    assert all(message["ok"] is True for message in messages)


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
            "coordinatorUid": "R1",
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
    assert preflight["value"]["catalogueIdentityValidated"] is True
    assert preflight["value"]["sonosAcceptance"] == "unproven_until_create"
    assert preflight["value"]["queueMutation"] is False
    assert preflight["value"]["playbackMutation"] is False
    assert "CurrentURI" not in json.dumps(preflight)
    assert "music.apple.com" not in json.dumps(preflight)
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
    assert "backendRevision" not in execution[1]
    assert controller.calls[-1][0] == "createPreflightedApplePlaylist"
    assert not any(call[0] == "refresh" for call in controller.calls)


def test_apple_playlist_plan_survives_an_unchanged_snapshot_poll():
    controller = ApplePlanController()
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()
    token = _protocol_preflight(server, output)["value"]["planToken"]

    server.emit_snapshot(output, rediscover=False)
    assert server.revision == 1

    server.handle(
        {
            "version": 1,
            "id": "create-after-poll",
            "op": "playlists.apple.create",
            "args": {"planToken": token, "approved": True},
        },
        output,
    )

    result = next(
        message for message in decoded(output) if message.get("id") == "create-after-poll"
    )
    assert result["ok"] is True
    assert result["revision"] == 1
    executions = [call for call in controller.calls if call[0] == "createPreflightedApplePlaylist"]
    assert len(executions) == 1


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


def test_apple_playlist_preclaim_rejections_do_not_refresh_or_stale_valid_ticket():
    controller = ApplePlanController()
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()
    token = _protocol_preflight(server, output)["value"]["planToken"]
    preflight_calls = list(controller.calls)

    rejected_args = (
        {"planToken": token, "approved": False},
        {"planToken": token, "approved": True, "roomUid": "R2"},
        {"planToken": "invalid-plan-token", "approved": True},
    )
    for index, args in enumerate(rejected_args, 1):
        server.handle(
            {
                "version": 1,
                "id": f"rejected-{index}",
                "op": "playlists.apple.create",
                "args": args,
            },
            output,
        )

    assert server.revision == 0
    assert controller.calls == preflight_calls
    rejected = [
        message for message in decoded(output) if str(message.get("id", "")).startswith("rejected-")
    ]
    assert [message["revision"] for message in rejected] == [0, 0, 0]
    assert [message["error"]["code"] for message in rejected] == [
        "invalid_argument",
        "invalid_argument",
        "conflict",
    ]

    server.handle(
        {
            "version": 1,
            "id": "valid-create",
            "op": "playlists.apple.create",
            "args": {"planToken": token, "approved": True},
        },
        output,
    )

    result = next(message for message in decoded(output) if message.get("id") == "valid-create")
    assert result["ok"] is True
    assert result["revision"] == 0
    assert server.revision == 0
    assert controller.calls[-1][0] == "createPreflightedApplePlaylist"
    assert not any(call[0] == "refresh" for call in controller.calls)
    assert (
        len([call for call in controller.calls if call[0] == "createPreflightedApplePlaylist"]) == 1
    )


def test_apple_playlist_failure_returns_bounded_cleanup_evidence_without_raw_details():
    controller = ApplePlanController()
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()
    token = _protocol_preflight(server, output)["value"]["planToken"]
    controller.failure = PlaylistTransactionError(
        phase="playlist_creation",
        diagnostics={
            "playlistConstructionStep": "add_track",
            "failedTrackPosition": 2,
            "failedCanonicalIdentity": "song:1452806384",
            "sonosErrorCode": "701",
            "partialPlaylistId": "SQ:17",
            "playlistRemoved": True,
            "playlistCleanupRequired": False,
            "preExistingPlaylistsUnchanged": True,
            "queueUnchanged": True,
            "playbackUnchanged": True,
            "succeeded": False,
            "rawException": "private DIDL at 192.168.1.20 token=secret",
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
    details = result["error"]["details"]
    assert details["phase"] == "playlist_creation"
    assert details["playlistConstructionStep"] == "add_track"
    assert details["failedTrackPosition"] == 2
    assert details["failedCanonicalIdentity"] == "song:1452806384"
    assert details["sonosErrorCode"] == "701"
    assert details["partialPlaylistId"] == "SQ:17"
    assert details["playlistRemoved"] is True
    assert details["playlistCleanupRequired"] is False
    assert details["preExistingPlaylistsUnchanged"] is True
    assert details["queueUnchanged"] is True
    assert details["playbackUnchanged"] is True
    assert details["succeeded"] is False
    assert len(protocol_line(result).encode("utf-8")) <= MAX_PROTOCOL_LINE_BYTES
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
