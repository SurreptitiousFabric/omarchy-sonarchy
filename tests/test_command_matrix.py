from __future__ import annotations

import json

import pytest

import sonarchy_bridge as bridge

IP = "192.168.1.20"
CLI_ROUTE_CASES = (
    ("status", ["status"], "discover_snapshot"),
    ("artwork", ["artwork", "Track title", "Track artist"], "resolve_apple_artwork"),
    ("details", ["details", IP], "details_snapshot"),
    ("content", ["content", IP, "favorites"], "content_snapshot"),
    ("alarms", ["alarms", IP], "alarms_snapshot"),
    ("play", ["play", IP], "run_action"),
    ("pause", ["pause", IP], "run_action"),
    ("play-pause", ["play-pause", IP], "run_action"),
    ("stop", ["stop", IP], "run_action"),
    ("next", ["next", IP], "run_action"),
    ("previous", ["previous", IP], "run_action"),
    ("mute-toggle", ["mute-toggle", IP], "run_action"),
    ("volume", ["volume", IP, "25"], "run_action"),
    ("rename", ["rename", IP, "Dining Room"], "rename_room"),
    ("group", ["group", IP, "192.168.1.21", "on"], "group_room"),
    ("group-all", ["group-all", IP], "group_all"),
    ("separate", ["separate", IP], "separate_room"),
    (
        "playback-option",
        ["playback-option", IP, "shuffle", "on"],
        "playback_option",
    ),
    ("sound", ["sound", IP, "bass", "1"], "set_sound"),
    ("play-favorite", ["play-favorite", IP, "fav-1"], "play_favorite"),
    ("play-queue", ["play-queue", IP, "0", "Q:1"], "queue_action"),
    ("remove-queue", ["remove-queue", IP, "0", "Q:1"], "queue_action"),
    ("clear-queue", ["clear-queue", IP], "queue_action"),
    (
        "queue-content",
        ["queue-content", IP, "library", "blue", "TRACK:1", "0", "next"],
        "enqueue_content_item",
    ),
    ("playlist", ["playlist", IP, "create", "Morning"], "playlist_action"),
    (
        "playlist-track",
        ["playlist-track", IP, "down", "SQ:1", "0", "TRACK:1"],
        "playlist_track_action",
    ),
    ("library-update", ["library-update", IP], "start_library_update"),
    (
        "alarm-save",
        [
            "alarm-save",
            IP,
            "new",
            "07:00",
            "DAILY",
            "25",
            "30",
            "on",
            "off",
            "chime",
        ],
        "save_alarm",
    ),
    ("alarm-toggle", ["alarm-toggle", IP, "1", "off"], "toggle_alarm"),
    ("alarm-delete", ["alarm-delete", IP, "1"], "delete_alarm"),
    ("source", ["source", IP, "tv"], "switch_source"),
    ("device", ["device", IP, "status-light", "off"], "set_device"),
    (
        "play-apple",
        ["play-apple", IP, "https://music.apple.com/ch/album/a/1?i=1"],
        "play_apple",
    ),
    (
        "play-apple-album",
        ["play-apple-album", IP, "https://music.apple.com/ch/album/a/1"],
        "play_apple_album",
    ),
    ("play-global", ["play-global", IP, "station:1", "radio"], "play_global"),
)


def test_cli_route_cases_cover_every_public_subcommand():
    parser = bridge.parser()
    subcommands = next(
        action.choices
        for action in parser._actions
        if isinstance(getattr(action, "choices", None), dict)
    )

    assert set(subcommands) == bridge.CLI_COMMANDS
    assert {case[0] for case in CLI_ROUTE_CASES} == bridge.CLI_COMMANDS


@pytest.mark.parametrize(("command", "arguments", "handler_name"), CLI_ROUTE_CASES)
def test_every_cli_command_parses_and_routes(command, arguments, handler_name, monkeypatch, capsys):
    calls = []

    def handler(*args, **kwargs):
        calls.append((args, kwargs))
        return {"ok": True, "action": command}

    monkeypatch.setattr(bridge, handler_name, handler)

    assert bridge.main(arguments) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"ok": True, "action": command}
    assert len(calls) == 1
