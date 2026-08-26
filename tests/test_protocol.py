import io
import json
import tempfile

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


def decoded(output):
    return [json.loads(line) for line in output.getvalue().splitlines()]


def test_mutation_emits_result_then_fresh_snapshot():
    controller = FakeController()
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()
    server.handle({"id": "12", "op": "playPause"}, output)
    messages = decoded(output)
    assert controller.calls == [("playPause",), ("refresh", False)]
    assert messages[0] == {"type": "result", "id": "12", "ok": True}
    assert messages[1]["type"] == "snapshot"


def test_unknown_operation_is_reported_without_crashing():
    controller = FakeController()
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()
    server.handle({"id": "99", "op": "wat"}, output)
    messages = decoded(output)
    assert messages == [
        {"type": "result", "id": "99", "ok": False, "error": "Unknown operation: wat"}
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
    ("playPause", {}, ("play_pause",)),
    ("play", {}, ("play",)),
    ("pause", {}, ("pause",)),
    ("next", {}, ("next",)),
    ("previous", {}, ("previous",)),
    ("seek", {"positionSec": 42}, ("seek", 42)),
    ("playFavorite", {"favoriteId": "fav-1"}, ("play_favorite", "fav-1")),
    ("refreshFavorites", {}, ("refresh_favorites",)),
    (
        "movePlaybackToRoom",
        {"roomUid": "R2"},
        ("move_playback_to_room", "R2"),
    ),
    ("selectGroup", {"groupUid": "G2"}, ("select_group", "G2")),
    ("selectRoom", {"roomUid": "R2"}, ("select_room", "R2")),
    ("setGroupVolume", {"volume": 35}, ("set_group_volume", 35)),
    ("adjustGroupVolume", {"delta": -2}, ("adjust_group_volume", -2)),
    ("setGroupMute", {"mute": True}, ("set_group_mute", True)),
    (
        "setRoomVolume",
        {"roomUid": "R2", "volume": 21},
        ("set_room_volume", "R2", 21),
    ),
    (
        "adjustRoomVolume",
        {"roomUid": "R2", "delta": 2},
        ("adjust_room_volume", "R2", 2),
    ),
    (
        "setRoomMute",
        {"roomUid": "R2", "mute": False},
        ("set_room_mute", "R2", False),
    ),
    (
        "applyMembers",
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
    assert {case[0] for case in PROTOCOL_ACTION_CASES} == PROTOCOL_OPERATIONS


@pytest.mark.parametrize(("operation", "arguments", "expected"), PROTOCOL_ACTION_CASES)
def test_every_protocol_operation_dispatches_and_refreshes(operation, arguments, expected):
    controller = RecordingController()
    server = ProtocolServer(controller)  # type: ignore[arg-type]
    output = io.StringIO()

    server.handle({"id": "matrix", "op": operation, **arguments}, output)

    assert controller.calls == [expected, ("refresh", False)]
    messages = decoded(output)
    assert messages[0] == {"type": "result", "id": "matrix", "ok": True}
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
    assert "network exploded" in message["status"]["message"]


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
    assert any(message.get("error") == "Protocol message is too large" for message in messages)
    assert any(message.get("id") == "2" and message.get("ok") is True for message in messages)
