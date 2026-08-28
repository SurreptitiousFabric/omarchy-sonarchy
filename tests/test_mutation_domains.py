from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from sonarchy_backend.domains.alarms import (
    alarm_by_id,
    alarm_mutations_service,
    alarm_program,
    delete_alarm,
    project_alarms,
    save_alarm,
    toggle_alarm,
)
from sonarchy_backend.domains.capabilities import (
    line_in_available,
    queue_transport_active,
    tv_autoplay_enabled,
)
from sonarchy_backend.domains.common import coordinator_for
from sonarchy_backend.domains.content import (
    play_apple,
    play_apple_album,
    play_global,
    start_library_update,
)
from sonarchy_backend.domains.devices import project_device_details
from sonarchy_backend.domains.playlists import (
    playlist_action,
    playlist_track_action,
    playlists_service,
    validate_playlist_title,
)
from sonarchy_backend.domains.queue import (
    MAX_REPLACE_BACKUP_ITEMS,
    _replace_queue,
    enqueue_content_item,
    find_library_item,
    find_playlist_track,
    move_queue_item,
    queue_action,
    queue_service,
)
from sonarchy_backend.domains.settings import (
    BOOLEAN_SETTINGS,
    DEVICE_BOOLEAN_SETTINGS,
    NUMBER_SETTINGS,
    rename_room,
    set_device,
    set_playback_option,
    set_sound,
    stop_playback,
    switch_source,
)


def speaker(**values):
    return SimpleNamespace(group=None, **values)


def item(item_id="I:1", *, resources=None, title="Item", can_play=True):
    return SimpleNamespace(
        item_id=item_id,
        resources=[SimpleNamespace(uri="x-test:item")] if resources is None else resources,
        title=title,
        can_play=can_play,
    )


class QueueResult(list):
    def __init__(self, items=(), *, total_matches=None):
        super().__init__(items)
        self.total_matches = len(self) if total_matches is None else total_matches


class DeviceProperties:
    def __init__(self, owner):
        self.owner = owner
        self.autoplay_room_uuid = owner.uid
        self.zone_name_override = None

    def GetZoneAttributes(self, _args):
        return {"CurrentZoneName": self.zone_name_override or self.owner.player_name}

    def GetAutoplayRoomUUID(self, _args):
        return {"RoomUUID": self.autoplay_room_uuid}

    def SetAutoplayRoomUUID(self, args):
        self.autoplay_room_uuid = dict(args)["RoomUUID"]


class Transport:
    def __init__(self, uri="x-rincon-queue:RINCON_TEST#0"):
        self.uri = uri

    def GetMediaInfo(self, _args):
        return {"CurrentURI": self.uri}


def test_shared_coordinator_projection_handles_groups_and_stale_state():
    coordinator = object()

    class GroupedSpeaker:
        group_reads = 0

        @property
        def group(self):
            self.group_reads += 1
            if self.group_reads > 1:
                raise RuntimeError("group state changed during projection")
            return SimpleNamespace(coordinator=coordinator)

    grouped = GroupedSpeaker()
    assert coordinator_for(grouped) is coordinator
    assert grouped.group_reads == 1

    class StaleSpeaker:
        @property
        def group(self):
            raise RuntimeError("stale topology")

    stale = StaleSpeaker()
    assert coordinator_for(stale) is stale


def test_shared_capability_projections_preserve_authoritative_tristate():
    autoplay = SimpleNamespace(
        deviceProperties=SimpleNamespace(GetAutoplayRoomUUID=Mock(return_value={"RoomUUID": "R1"}))
    )
    assert tv_autoplay_enabled(autoplay) is True
    autoplay.deviceProperties.GetAutoplayRoomUUID.return_value = {"RoomUUID": ""}
    assert tv_autoplay_enabled(autoplay) is False
    autoplay.deviceProperties.GetAutoplayRoomUUID.return_value = {}
    assert tv_autoplay_enabled(autoplay) is None

    transport = SimpleNamespace(avTransport=Transport())
    assert queue_transport_active(transport) is True
    transport.avTransport.uri = "x-sonosapi-stream:station"
    assert queue_transport_active(transport) is False
    transport.avTransport.GetMediaInfo = Mock(return_value={})
    assert queue_transport_active(transport) is None


class AudioIn:
    def __init__(self, supported=True):
        self.supported = supported

    def send_command(self, action, args, *, timeout):
        assert (action, args, timeout) == ("GetAudioInputAttributes", [], 1.5)
        if not self.supported:
            raise RuntimeError("unsupported")
        return {"CurrentName": "Line-In"}


class DirectAudioIn:
    base_url = "http://speaker.test:1400"
    control_url = "/MediaServer/AudioIn/Control"

    def build_command(self, action, args):
        assert (action, args) == ("GetAudioInputAttributes", [])
        return {"SOAPACTION": "AudioIn#GetAudioInputAttributes"}, "<Envelope />"

    def send_command(self, *_args, **_kwargs):
        raise AssertionError("direct probe must bypass SoCo's response parser")


class SettingsSpeaker:
    def __init__(self, uid="R1", ip="192.168.1.2"):
        self.uid = uid
        self.ip_address = ip
        self.player_name = "Office"
        self.group = None
        self.visible_zones = {self}
        self.avTransport = Transport()
        self.audioIn = AudioIn()
        self.deviceProperties = DeviceProperties(self)
        self.music_source = "TV"
        self.is_soundbar = True
        self.shuffle = False
        self.repeat = False
        self.cross_fade = False
        self.play_mode = "NORMAL"
        self.sleep_timer = 900
        self.bass = 0
        self.treble = 0
        self.balance = (100, 100)
        self.loudness = True
        self.night_mode = False
        self.speech_enhance_enabled = True
        self.sub_enabled = True
        self.sub_gain = 0
        self.sub_crossover = 80
        self.surround_enabled = True
        self.surround_mode = True
        self.surround_volume_tv = 1
        self.surround_volume_music = 2
        self.audio_delay = 0
        self.status_light = True
        self.buttons_enabled = True
        self.trueplay = True
        self.mic_enabled = True
        self.voice_service_configured = False
        self.channel = "LF"
        self.calls = []

    def stop(self):
        self.calls.append("stop")

    def set_sleep_timer(self, seconds):
        self.sleep_timer = seconds

    def switch_to_line_in(self, source):
        self.calls.append(("line-in", source.uid))

    def switch_to_tv(self):
        self.calls.append("tv")

    def get_sleep_timer(self):
        return self.sleep_timer

    def get_speaker_info(self):
        return {
            "model_name": "Era",
            "model_number": "E100",
            "serial_number": "redacted-test",
            "software_version": "1",
            "hardware_version": "2",
        }

    def get_battery_info(self, timeout):
        assert timeout == 1.5
        return {"Level": "80", "Health": "GOOD", "PowerSource": "BATTERY"}


@pytest.mark.parametrize(("status_code", "expected"), ((200, True), (500, False)))
def test_line_in_capability_uses_quiet_bounded_direct_request(status_code, expected):
    speaker = SimpleNamespace(audioIn=DirectAudioIn())
    response = Mock(status_code=status_code)

    request_path = "sonarchy_backend.domains.capabilities.requests.post"
    with patch(request_path, return_value=response) as post:
        assert line_in_available(speaker) is expected

    post.assert_called_once_with(
        "http://speaker.test:1400/MediaServer/AudioIn/Control",
        headers={"SOAPACTION": "AudioIn#GetAudioInputAttributes"},
        data=b"<Envelope />",
        timeout=1.5,
        allow_redirects=False,
    )
    response.close.assert_called_once_with()


@pytest.mark.parametrize(
    ("index", "expected_id"),
    ((None, "Q:1"), (-1, "Q:1"), (2, "Q:1"), (0, "Q:stale")),
)
def test_queue_identity_failures_do_not_mutate(index, expected_id):
    room = speaker(
        get_queue=Mock(return_value=[item("Q:1")]),
        remove_from_queue=Mock(),
    )

    with pytest.raises(ValueError):
        queue_action(room, "remove-queue", index, expected_id)

    room.remove_from_queue.assert_not_called()


def test_queue_rejects_unknown_action():
    with pytest.raises(ValueError, match="Unsupported queue action"):
        queue_action(speaker(), "replace-queue")


@pytest.mark.parametrize(
    ("source", "target", "insert_before"),
    ((2, 0, 1), (0, 2, 4), (1, 2, 4)),
)
def test_queue_move_translates_zero_based_positions_for_sonos(source, target, insert_before):
    queued = [item(f"Q:{index}") for index in range(3)]
    reorder = Mock()
    room = speaker(
        get_queue=Mock(return_value=queued),
        avTransport=SimpleNamespace(ReorderTracksInQueue=reorder),
    )

    payload = move_queue_item(
        room,
        source,
        f"Q:{source}",
        target,
        f"Q:{target}",
    )

    assert payload["action"] == "queue-move"
    reorder.assert_called_once_with(
        [
            ("InstanceID", 0),
            ("StartingIndex", source + 1),
            ("NumberOfTracks", 1),
            ("InsertBefore", insert_before),
            ("UpdateID", 0),
        ]
    )


def test_queue_move_rejects_stale_destination_and_ignores_same_row_drop():
    queued = [item("Q:0"), item("Q:1")]
    reorder = Mock()
    room = speaker(
        get_queue=Mock(return_value=queued),
        avTransport=SimpleNamespace(ReorderTracksInQueue=reorder),
    )

    with pytest.raises(ValueError, match="queue changed"):
        move_queue_item(room, 0, "Q:0", 1, "Q:stale")
    reorder.assert_not_called()

    move_queue_item(room, 0, "Q:0", 0, "Q:0")
    reorder.assert_not_called()


@pytest.mark.parametrize("action", ("play-queue", "remove-queue", "clear-queue"))
def test_every_queue_action_succeeds(action):
    queued = item("Q:1")
    room = speaker(
        get_queue=Mock(return_value=[queued]),
        play_from_queue=Mock(),
        remove_from_queue=Mock(),
        clear_queue=Mock(),
    )
    payload = (
        queue_action(room, action)
        if action == "clear-queue"
        else queue_action(room, action, 0, "Q:1")
    )
    assert payload["action"] == action


@pytest.mark.parametrize("term", ("bad\nterm", "x" * 121))
def test_library_search_rejects_unsafe_terms(term):
    library = Mock()
    with pytest.raises(ValueError, match="Search text"):
        find_library_item(SimpleNamespace(music_library=library), "L:1", term)
    library.get_music_library_information.assert_not_called()


def test_nested_library_item_is_re_resolved_by_path_index_and_identity():
    category = item("A:ARTIST", resources=[])
    category.browsable = True
    track = item("T:42")
    library = Mock()
    library.browse.side_effect = [[category], [track]]
    coordinator = SimpleNamespace(music_library=library)

    result = find_library_item(
        coordinator,
        "T:42",
        "",
        42,
        [{"id": "A:ARTIST", "index": 3}],
    )

    assert result is track
    assert library.browse.call_args_list[0].kwargs["start"] == 3
    assert library.browse.call_args_list[1].kwargs["start"] == 42


def test_nested_library_item_rejects_stale_identity():
    category = item("A:ARTIST", resources=[])
    category.browsable = True
    library = Mock()
    library.browse.side_effect = [[category], [item("T:stale")]]
    with pytest.raises(ValueError, match="no longer available"):
        find_library_item(
            SimpleNamespace(music_library=library),
            "T:42",
            "",
            0,
            [{"id": "A:ARTIST", "index": 0}],
        )


@pytest.mark.parametrize("path", ("", False, {}))
def test_library_item_rejects_malformed_paths(path):
    with pytest.raises(ValueError, match="library path"):
        find_library_item(SimpleNamespace(music_library=Mock()), "T:1", "", 0, path)


def test_library_item_rejects_combined_search_and_hierarchy_context():
    with pytest.raises(ValueError, match="search must start"):
        find_library_item(
            SimpleNamespace(music_library=Mock()),
            "T:1",
            "track",
            0,
            [{"id": "A:ARTIST", "index": 0}],
        )


def test_library_and_playlist_staleness_are_rejected():
    library = Mock()
    library.get_music_library_information.return_value = [item("L:other")]
    coordinator = SimpleNamespace(
        music_library=library,
        get_sonos_playlist_by_attr=Mock(return_value=object()),
    )
    with pytest.raises(ValueError, match="no longer available"):
        find_library_item(coordinator, "L:1", "song")

    library.browse.return_value = [item("T:1")]
    with pytest.raises(ValueError, match="playlist changed"):
        find_playlist_track(coordinator, "SQ:1", 2, "T:1")
    with pytest.raises(ValueError, match="playlist changed"):
        find_playlist_track(coordinator, "SQ:1", 0, "T:stale")


def test_enqueue_rejects_wrong_kind_empty_resource_and_mode():
    room = speaker()
    with pytest.raises(ValueError, match="Only library and playlist"):
        enqueue_content_item(room, "radio", "context", "I:1", 0, "play")

    with (
        patch(
            "sonarchy_backend.domains.queue.find_library_item",
            return_value=item(resources=[]),
        ),
        pytest.raises(ValueError, match="playable resource"),
    ):
        enqueue_content_item(room, "library", "song", "I:1", 0, "play")
    with (
        patch("sonarchy_backend.domains.queue.find_library_item", return_value=item()),
        pytest.raises(ValueError, match="queue position"),
    ):
        enqueue_content_item(room, "library", "song", "I:1", 0, "middle")


@pytest.mark.parametrize("mode", ("play", "next", "end"))
def test_every_enqueue_mode_succeeds(mode):
    room = speaker(
        add_to_queue=Mock(return_value=2),
        play_from_queue=Mock(),
        get_current_track_info=Mock(return_value={"playlist_position": "2"}),
    )
    with patch("sonarchy_backend.domains.queue.find_library_item", return_value=item()):
        payload = enqueue_content_item(room, "library", "song", "I:1", 0, mode)
    assert payload["action"] == f"queue-{mode}"


def test_play_now_inserts_after_current_and_starts_returned_position():
    selected = item()
    room = speaker(
        add_to_queue=Mock(return_value=3),
        play_from_queue=Mock(),
        get_current_track_info=Mock(return_value={"playlist_position": "2"}),
    )
    with patch("sonarchy_backend.domains.queue.find_library_item", return_value=selected):
        payload = enqueue_content_item(room, "library", "song", "I:1", 0, "play")

    room.add_to_queue.assert_called_once_with(selected, position=3)
    room.play_from_queue.assert_called_once_with(2)
    assert payload["message"] == "Playing now"


def test_replace_queue_preflights_then_clears_adds_and_plays():
    old = item("Q:old")
    selected = item("Q:new")
    room = speaker(
        get_queue=Mock(return_value=QueueResult([old])),
        avTransport=Transport(),
        get_current_track_info=Mock(return_value={"playlist_position": "1"}),
        get_current_transport_info=Mock(return_value={"current_transport_state": "PLAYING"}),
        clear_queue=Mock(),
        add_to_queue=Mock(return_value=1),
        add_multiple_to_queue=Mock(),
        play_from_queue=Mock(),
    )

    assert _replace_queue(room, selected) == 1

    room.get_queue.assert_called_once_with(
        max_items=MAX_REPLACE_BACKUP_ITEMS,
        full_album_art_uri=False,
    )
    room.clear_queue.assert_called_once_with()
    room.add_to_queue.assert_called_once_with(selected)
    room.play_from_queue.assert_called_once_with(0)
    room.add_multiple_to_queue.assert_not_called()


def test_replace_queue_refuses_incomplete_backup_before_mutating():
    room = speaker(
        get_queue=Mock(
            return_value=QueueResult(
                [item(f"Q:{index}") for index in range(MAX_REPLACE_BACKUP_ITEMS)],
                total_matches=MAX_REPLACE_BACKUP_ITEMS + 1,
            )
        ),
        clear_queue=Mock(),
    )

    with pytest.raises(ValueError, match="too large"):
        _replace_queue(room, item("Q:new"))

    room.clear_queue.assert_not_called()


def test_replace_queue_refuses_unrestorable_backup_before_mutating():
    room = speaker(
        get_queue=Mock(return_value=QueueResult([item("Q:old", resources=[])])),
        clear_queue=Mock(),
    )

    with pytest.raises(ValueError, match="cannot be backed up"):
        _replace_queue(room, item("Q:new"))

    room.clear_queue.assert_not_called()


@pytest.mark.parametrize(
    ("uri", "playlist_position", "message"),
    (
        (None, "1", "source could not be verified"),
        ("x-rincon-queue:RINCON_TEST#0", "0", "position could not be verified"),
    ),
)
def test_replace_queue_refuses_unverifiable_playback_before_mutating(
    uri, playlist_position, message
):
    transport = SimpleNamespace() if uri is None else Transport(uri)
    room = speaker(
        get_queue=Mock(return_value=QueueResult([item("Q:old")])),
        avTransport=transport,
        get_current_track_info=Mock(return_value={"playlist_position": playlist_position}),
        get_current_transport_info=Mock(return_value={}),
        clear_queue=Mock(),
    )

    with pytest.raises(ValueError, match=message):
        _replace_queue(room, item("Q:new"))

    room.clear_queue.assert_not_called()


@pytest.mark.parametrize(("active", "was_playing"), ((True, False), (False, True)))
def test_replace_queue_restores_backup_when_replacement_fails(active, was_playing):
    old = item("Q:old")
    uri = "x-rincon-queue:RINCON_TEST#0" if active else "x-sonosapi-stream:station"
    room = speaker(
        get_queue=Mock(return_value=QueueResult([old])),
        avTransport=Transport(uri),
        get_current_track_info=Mock(return_value={"playlist_position": "1"}),
        get_current_transport_info=Mock(
            return_value={
                "current_transport_state": "PLAYING" if was_playing else "PAUSED_PLAYBACK"
            }
        ),
        clear_queue=Mock(),
        add_to_queue=Mock(side_effect=[RuntimeError("speaker rejected item"), 1]),
        add_multiple_to_queue=Mock(),
        play_from_queue=Mock(),
    )

    with pytest.raises(RuntimeError, match="speaker rejected item"):
        _replace_queue(room, item("Q:new"))

    assert room.clear_queue.call_count == 2
    assert room.add_to_queue.call_count == 2
    assert room.add_to_queue.call_args_list[1].args == (old,)
    room.add_multiple_to_queue.assert_not_called()
    if active:
        room.play_from_queue.assert_called_once_with(0, start=was_playing)
    else:
        room.play_from_queue.assert_not_called()


def test_replace_queue_reports_when_backup_recovery_also_fails():
    room = speaker(
        get_queue=Mock(return_value=QueueResult([item("Q:old")])),
        avTransport=Transport(),
        get_current_track_info=Mock(return_value={"playlist_position": "1"}),
        get_current_transport_info=Mock(return_value={}),
        clear_queue=Mock(),
        add_to_queue=Mock(
            side_effect=[
                RuntimeError("replacement failed"),
                RuntimeError("recovery failed"),
            ]
        ),
        add_multiple_to_queue=Mock(side_effect=RuntimeError("recovery failed")),
        play_from_queue=Mock(),
    )

    with pytest.raises(RuntimeError, match="previous queue could not be restored"):
        _replace_queue(room, item("Q:new"))

    assert room.clear_queue.call_count == 2


def test_replace_queue_can_restore_an_empty_backup_without_queueing_items():
    room = speaker(
        get_queue=Mock(return_value=QueueResult()),
        avTransport=Transport("x-sonosapi-stream:station"),
        get_current_track_info=Mock(return_value={}),
        get_current_transport_info=Mock(return_value={}),
        clear_queue=Mock(),
        add_to_queue=Mock(side_effect=RuntimeError("replacement failed")),
        add_multiple_to_queue=Mock(),
        play_from_queue=Mock(),
    )

    with pytest.raises(RuntimeError, match="replacement failed"):
        _replace_queue(room, item("Q:new"))

    assert room.clear_queue.call_count == 2
    room.add_multiple_to_queue.assert_not_called()
    room.play_from_queue.assert_not_called()


def test_replace_queue_preserves_legacy_support_for_an_empty_active_queue():
    room = speaker(
        get_queue=Mock(return_value=QueueResult()),
        avTransport=Transport(),
        get_current_track_info=Mock(return_value={"playlist_position": "0"}),
        get_current_transport_info=Mock(return_value={"current_transport_state": "STOPPED"}),
        clear_queue=Mock(),
        add_to_queue=Mock(return_value=1),
        add_multiple_to_queue=Mock(),
        play_from_queue=Mock(),
    )

    assert _replace_queue(room, item("Q:new")) == 1
    room.play_from_queue.assert_called_once_with(0)


def test_replace_enqueue_mode_uses_safe_replacement_path():
    selected = item("Q:new")
    room = speaker()
    with (
        patch("sonarchy_backend.domains.queue.find_library_item", return_value=selected),
        patch("sonarchy_backend.domains.queue._replace_queue", return_value=1) as replace,
    ):
        payload = enqueue_content_item(room, "library", "song", "Q:new", 0, "replace")

    replace.assert_called_once_with(room, selected)
    assert payload == {
        "ok": True,
        "action": "queue-replace",
        "message": "Replaced the queue and started playback",
    }


def test_queue_and_playlist_services_reject_fractional_indices():
    backend = Mock()
    with pytest.raises(ValueError, match="integer"):
        queue_service(backend).execute(
            "queue.item.play", {"roomUid": "R1", "index": 1.5, "itemId": "Q:1"}
        )
    with pytest.raises(ValueError, match="integer"):
        playlists_service(backend).execute(
            "playlists.track.mutate",
            {
                "roomUid": "R1",
                "action": "down",
                "playlistId": "SQ:1",
                "index": 1.5,
                "itemId": "T:1",
            },
        )


def test_queue_service_accepts_empty_context_for_hierarchical_library_items():
    backend = Mock()
    path = [{"id": "A:ARTIST", "index": 0}]
    queue_service(backend).execute(
        "queue.content.enqueue",
        {
            "roomUid": "R1",
            "kind": "library",
            "context": "",
            "itemId": "T:1",
            "index": 4,
            "mode": "play",
            "libraryPath": path,
        },
    )
    backend.enqueue_content_item.assert_called_once_with(
        "R1", "library", "", "T:1", 4, "play", path
    )


def test_playlist_validation_and_empty_queue_fail_before_mutation():
    with pytest.raises(ValueError, match="cannot be empty"):
        validate_playlist_title("  ")
    with pytest.raises(ValueError, match="too long"):
        validate_playlist_title("x" * 81)

    room = speaker(queue_size=0, create_sonos_playlist_from_queue=Mock())
    with pytest.raises(ValueError, match="queue is empty"):
        playlist_action(room, "save-queue", "Saved")
    room.create_sonos_playlist_from_queue.assert_not_called()
    with pytest.raises(ValueError, match="Unsupported playlist action"):
        playlist_action(room, "rename", "Saved")


@pytest.mark.parametrize("action", ("create", "save-queue", "play", "delete"))
def test_every_playlist_action_succeeds(action):
    playlist = SimpleNamespace(item_id="SQ:1", title="Morning")
    room = speaker(
        queue_size=1,
        create_sonos_playlist=Mock(return_value=playlist),
        create_sonos_playlist_from_queue=Mock(return_value=playlist),
        get_sonos_playlist_by_attr=Mock(return_value=playlist),
        add_to_queue=Mock(return_value=1),
        play_from_queue=Mock(),
        remove_sonos_playlist=Mock(),
    )
    value = "Morning" if action in {"create", "save-queue"} else "SQ:1"
    assert playlist_action(room, action, value)["action"] == f"playlist-{action}"


@pytest.mark.parametrize(
    ("action", "index", "count", "message"),
    (
        ("up", 0, 2, "already first"),
        ("down", 1, 2, "already last"),
        ("sideways", 0, 2, "Unsupported"),
    ),
)
def test_playlist_track_boundaries_do_not_mutate(action, index, count, message):
    room = speaker(
        move_in_sonos_playlist=Mock(),
        remove_from_sonos_playlist=Mock(),
    )
    with (
        patch(
            "sonarchy_backend.domains.playlists.find_playlist_track",
            return_value=(object(), item(), count),
        ),
        pytest.raises(ValueError, match=message),
    ):
        playlist_track_action(room, action, "SQ:1", index, "T:1")
    room.move_in_sonos_playlist.assert_not_called()
    room.remove_from_sonos_playlist.assert_not_called()


@pytest.mark.parametrize("action", ("up", "down", "remove"))
def test_every_playlist_track_action_succeeds(action):
    room = speaker(
        move_in_sonos_playlist=Mock(),
        remove_from_sonos_playlist=Mock(),
    )
    with patch(
        "sonarchy_backend.domains.playlists.find_playlist_track",
        return_value=(object(), item(), 3),
    ):
        payload = playlist_track_action(room, action, "SQ:1", 1, "T:1")
    assert payload["action"] == f"playlist-track-{action}"


def test_content_provider_rejections_and_library_states():
    room = speaker()
    with pytest.raises(ValueError, match="Apple Music link"):
        play_apple(room, "https://example.test/song")
    with pytest.raises(ValueError, match="album link"):
        play_apple_album(room, "https://music.apple.com/ch/song/example/1")

    unplayable = item("G:1", resources=[], can_play=False)
    with pytest.raises(ValueError, match="not directly playable"):
        play_global(room, "G:1", "news", results_fn=lambda *_args: [unplayable])
    with pytest.raises(ValueError, match="no longer exists"):
        play_global(room, "G:1", "news", results_fn=lambda *_args: [])

    updating = speaker(music_library=SimpleNamespace(library_updating=True))
    assert start_library_update(updating)["message"] == "Library update is already running"
    library = SimpleNamespace(library_updating=False, start_library_update=Mock())
    assert (
        start_library_update(speaker(music_library=library))["message"] == "Library update started"
    )
    library.start_library_update.assert_called_once_with()


def test_content_provider_success_paths_play_the_queued_result():
    room = speaker(play_from_queue=Mock(), play_uri=Mock())
    plugin = Mock()
    plugin.add_share_link_to_queue.return_value = 2
    factory = Mock(return_value=plugin)
    assert (
        play_apple(
            room,
            "https://music.apple.com/ch/song/example/1",
            share_link_factory=factory,
        )["action"]
        == "play-apple"
    )
    assert (
        play_apple_album(
            room,
            "https://music.apple.com/ch/album/example/2",
            share_link_factory=factory,
        )["action"]
        == "play-apple-album"
    )

    station = item("G:1", title="News")
    assert (
        play_global(
            room,
            "G:1",
            "news",
            results_fn=lambda *_args: [station],
            metadata_fn=lambda _item: "<meta/>",
        )["action"]
        == "play-global"
    )
    room.play_uri.assert_called_once_with("x-test:item", meta="<meta/>")


def test_alarm_identity_and_program_validation():
    room = speaker(music_library=SimpleNamespace(get_sonos_favorites=Mock(return_value=[])))
    with pytest.raises(ValueError, match="Invalid alarm identifier"):
        alarm_by_id(room, "not-an-id", alarm_loader=lambda _room: [])
    with pytest.raises(ValueError, match="no longer exists"):
        alarm_by_id(room, "7", alarm_loader=lambda _room: [])
    with pytest.raises(ValueError, match="Unsupported alarm sound"):
        alarm_program(room, "radio")
    with pytest.raises(ValueError, match="Favorite no longer exists"):
        alarm_program(room, "favorite:missing")

    reference = SimpleNamespace(resources=[SimpleNamespace(uri="x-test:favorite")])
    favorite = SimpleNamespace(item_id="F:1", reference=reference)
    room.music_library.get_sonos_favorites.return_value = [favorite]
    assert alarm_program(room, "favorite:F:1", metadata_fn=lambda _item: "<meta/>") == (
        "x-test:favorite",
        "<meta/>",
    )


@pytest.mark.parametrize(
    ("recurrence", "duration", "message"),
    (("YEARLY", 30, "recurrence"), ("DAILY", 10, "duration")),
)
def test_alarm_save_rejects_unsupported_schedule(recurrence, duration, message):
    factory = Mock()
    room = speaker(uid="R1")
    with pytest.raises(ValueError, match=message):
        save_alarm(
            room,
            "new",
            "R1",
            "07:00",
            recurrence,
            25,
            duration,
            True,
            False,
            "chime",
            alarm_factory=factory,
        )
    factory.assert_not_called()


def test_new_alarm_save_and_existing_alarm_mutations():
    alarm = SimpleNamespace(save=Mock(return_value="9"), remove=Mock())
    room = speaker(uid="R1")
    payload = save_alarm(
        room,
        "new",
        "R1",
        "06:45",
        "weekdays",
        125,
        0,
        True,
        True,
        "chime",
        alarm_factory=lambda _room: alarm,
    )
    assert payload["id"] == "9"
    assert alarm.volume == 100
    assert alarm.duration is None
    assert alarm.program_uri is None

    alarm.alarm_id = "9"
    toggle_alarm(room, "9", False, alarm_loader=lambda _room: [alarm])
    assert alarm.enabled is False
    delete_alarm(room, "9", alarm_loader=lambda _room: [alarm])
    alarm.remove.assert_called_once_with()


def test_new_alarm_targets_an_authoritative_visible_room():
    anchor = speaker(uid="R1")
    target = speaker(uid="R2")
    anchor.visible_zones = [anchor, target]
    alarm = SimpleNamespace(save=Mock(return_value="10"))
    factory = Mock(return_value=alarm)

    payload = save_alarm(
        anchor,
        "new",
        "R2",
        "07:15",
        "DAILY",
        20,
        30,
        True,
        False,
        "chime",
        alarm_factory=factory,
    )

    factory.assert_called_once_with(target)
    assert payload["id"] == "10"


def test_existing_alarm_can_change_room_without_losing_other_fields():
    anchor = speaker(uid="R1")
    target = speaker(uid="R2")
    anchor.visible_zones = [anchor, target]
    alarm = SimpleNamespace(
        alarm_id="10",
        zone=anchor,
        room_uuid="R1",
        program_uri="x-test:existing",
        program_metadata="<existing/>",
        start_time=__import__("datetime").time(6, 0),
        recurrence="DAILY",
        volume=15,
        duration=None,
        enabled=True,
        include_linked_zones=False,
        save=Mock(return_value="10"),
    )

    save_alarm(
        anchor,
        "10",
        "R2",
        "08:30",
        "WEEKDAYS",
        35,
        45,
        False,
        True,
        "keep",
        alarm_loader=lambda _room: [alarm],
    )

    assert alarm.zone is target
    assert alarm.room_uuid == "R2"
    assert alarm.start_time == __import__("datetime").time(8, 30)
    assert alarm.recurrence == "WEEKDAYS"
    assert alarm.volume == 35
    assert alarm.duration == __import__("datetime").time(0, 45)
    assert alarm.enabled is False
    assert alarm.include_linked_zones is True
    assert alarm.program_uri == "x-test:existing"
    assert alarm.program_metadata == "<existing/>"
    alarm.save.assert_called_once_with()


def test_alarm_save_rejects_an_unavailable_room_before_mutating():
    anchor = speaker(uid="R1", visible_zones=[])
    factory = Mock()

    with pytest.raises(ValueError, match="unavailable"):
        save_alarm(
            anchor,
            "new",
            "R9",
            "07:00",
            "DAILY",
            20,
            30,
            True,
            False,
            "chime",
            alarm_factory=factory,
        )

    factory.assert_not_called()


def test_rejected_alarm_edit_restores_the_cached_authoritative_fields():
    anchor = speaker(uid="R1")
    target = speaker(uid="R2")
    anchor.visible_zones = [anchor, target]
    original_values = {
        "zone": anchor,
        "room_uuid": "R1",
        "program_uri": "x-test:existing",
        "program_metadata": "<existing/>",
        "start_time": __import__("datetime").time(6, 0),
        "recurrence": "DAILY",
        "volume": 15,
        "duration": None,
        "enabled": True,
        "include_linked_zones": False,
    }
    alarm = SimpleNamespace(
        alarm_id="10",
        **original_values,
        save=Mock(side_effect=RuntimeError("speaker rejected update")),
    )

    with pytest.raises(RuntimeError, match="speaker rejected update"):
        save_alarm(
            anchor,
            "10",
            "R2",
            "08:30",
            "WEEKDAYS",
            35,
            45,
            False,
            True,
            "chime",
            alarm_loader=lambda _room: [alarm],
        )

    for field, value in original_values.items():
        if field == "zone":
            assert getattr(alarm, field) is value
        else:
            assert getattr(alarm, field) == value


def test_alarm_projection_redacts_program_details_and_handles_missing_room_name():
    class MissingZone:
        @property
        def player_name(self):
            raise RuntimeError("offline")

    alarm = SimpleNamespace(
        alarm_id="7",
        start_time=__import__("datetime").time(7, 30),
        duration=__import__("datetime").time(0, 30),
        recurrence="DAILY",
        enabled=True,
        volume=20,
        include_linked_zones=False,
        room_uuid="R1",
        zone=MissingZone(),
        program_uri="x-private:secret",
    )
    payload = project_alarms(speaker(), alarm_loader=lambda _room: [alarm])
    assert payload["items"][0]["room"] == "Unknown room"
    assert payload["items"][0]["program"] == "Saved Sonos content"
    assert "x-private" not in str(payload)


def test_alarm_service_rejects_fractional_numbers():
    with pytest.raises(ValueError, match="volume must be an integer"):
        alarm_mutations_service(Mock()).execute(
            "alarms.save",
            {
                "roomUid": "R1",
                "alarmId": "new",
                "alarmRoomUid": "R1",
                "time": "07:00",
                "recurrence": "DAILY",
                "volume": 2.5,
                "duration": 30,
                "enabled": True,
                "includeGrouped": False,
                "program": "chime",
            },
        )


def test_stop_rename_and_source_switches_use_the_expected_speaker():
    room = SettingsSpeaker()
    assert stop_playback(room)["action"] == "stop"
    assert room.calls == ["stop"]
    assert rename_room(room, "  Studio  ")["name"] == "Studio"
    with pytest.raises(ValueError, match="cannot be empty"):
        rename_room(room, "  ")
    room.deviceProperties.zone_name_override = "Office"
    with pytest.raises(ValueError, match="did not confirm"):
        rename_room(room, "Dining")

    source = SettingsSpeaker("R2", "192.168.1.3")
    room.visible_zones.add(source)
    assert switch_source(room, "line-in", source)["action"] == "source-line-in"
    assert switch_source(room, "tv")["action"] == "source-tv"
    with pytest.raises(ValueError, match="household"):
        switch_source(room, "line-in", SettingsSpeaker("R3", "192.168.1.4"))
    with pytest.raises(ValueError, match="Unsupported Sonos source"):
        switch_source(room, "bluetooth")
    source.audioIn.supported = False
    with pytest.raises(ValueError, match="Line-in is not available"):
        switch_source(room, "line-in", source)


@pytest.mark.parametrize(
    ("option", "value", "attribute", "expected"),
    (
        ("shuffle", "on", "shuffle", True),
        ("repeat", "one", "repeat", "ONE"),
        ("crossfade", "on", "cross_fade", True),
        ("sleep", "off", "sleep_timer", None),
        ("sleep", "1800", "sleep_timer", 1800),
    ),
)
def test_every_playback_setting_updates_the_coordinator(option, value, attribute, expected):
    room = SettingsSpeaker()
    payload = set_playback_option(room, option, value)
    assert payload["action"] == option
    assert getattr(room, attribute) == expected


def test_playback_setting_validation_precedes_mutation():
    room = SettingsSpeaker()
    room.avTransport.uri = "x-sonosapi-stream:station"
    with pytest.raises(ValueError, match="queue is the active source"):
        set_playback_option(room, "shuffle", "on")
    with pytest.raises(ValueError, match="Repeat must"):
        set_playback_option(SettingsSpeaker(), "repeat", "track")
    with pytest.raises(ValueError, match="between 1 minute"):
        set_playback_option(SettingsSpeaker(), "sleep", "20")
    with pytest.raises(ValueError, match="Unsupported playback option"):
        set_playback_option(SettingsSpeaker(), "gapless", "on")


@pytest.mark.parametrize("setting", sorted(NUMBER_SETTINGS))
def test_every_numeric_sound_setting_is_bounded(setting):
    room = SettingsSpeaker()
    payload = set_sound(room, setting, "999")
    assert payload["action"] == setting


@pytest.mark.parametrize("setting", sorted(BOOLEAN_SETTINGS))
def test_every_boolean_sound_setting_can_be_disabled(setting):
    room = SettingsSpeaker()
    set_sound(room, setting, "off")
    assert getattr(room, BOOLEAN_SETTINGS[setting]) is False


def test_speech_enhancement_and_invalid_sound_setting():
    room = SettingsSpeaker()
    assert set_sound(room, "speech-enhancement", "off")["message"].endswith("off")
    assert room.speech_enhance_enabled is False
    with pytest.raises(ValueError, match="Unsupported sound setting"):
        set_sound(room, "made-up", "on")


@pytest.mark.parametrize("setting", sorted(DEVICE_BOOLEAN_SETTINGS))
def test_every_device_boolean_setting_can_be_disabled(setting):
    room = SettingsSpeaker()
    set_device(room, setting, "off")
    assert getattr(room, DEVICE_BOOLEAN_SETTINGS[setting]) is False


def test_tv_autoplay_is_confirmed_and_rejects_unsupported_rooms():
    room = SettingsSpeaker()
    set_device(room, "tv-autoplay", "off")
    assert room.deviceProperties.autoplay_room_uuid == ""
    set_device(room, "tv-autoplay", "on")
    assert room.deviceProperties.autoplay_room_uuid == room.uid

    ordinary = SettingsSpeaker()
    ordinary.deviceProperties.GetAutoplayRoomUUID = Mock(side_effect=RuntimeError("unsupported"))
    with pytest.raises(ValueError, match="not available"):
        set_device(ordinary, "tv-autoplay", "on")
    with pytest.raises(ValueError, match="Unsupported device setting"):
        set_device(room, "bluetooth", "on")


def test_device_details_project_supported_state_without_private_autoplay_identity():
    room = SettingsSpeaker()
    room.balance = (80, 100)
    details = project_device_details(room)

    assert details["ok"] is True
    assert details["playback"] == {
        "play_mode": "NORMAL",
        "shuffle": False,
        "repeat": "off",
        "crossfade": False,
        "sleep_timer": 900,
        "play_mode_supported": True,
        "tv_autoplay_risk": True,
    }
    assert details["sound"]["balance"] == 20
    assert details["device"]["name"] == "Office"
    assert details["device"]["tv_autoplay"] is True
    assert details["device"]["battery"]["level"] == 80
    assert details["group"]["members"][0]["uid"] == "R1"
    assert "RoomUUID" not in str(details)


@pytest.mark.parametrize(
    ("reported", "state"),
    (
        ("Stereo", "active"),
        ("Dolby 5.1", "active"),
        ("No input connected", "idle"),
        ("No audio", "idle"),
        ("Unknown audio input format: 123", "unknown"),
    ),
)
def test_tv_audio_format_normalizes_supported_soundbar_values(reported, state):
    room = SettingsSpeaker()
    room.soundbar_audio_input_format = reported

    details = project_device_details(room)

    expected_label = "Unknown format" if state == "unknown" else reported
    assert details["device"]["tv_audio_format"] == {
        "state": state,
        "label": expected_label,
    }


def test_tv_audio_format_is_absent_for_unsupported_rooms():
    room = SettingsSpeaker()
    room.is_soundbar = False

    assert project_device_details(room)["device"]["tv_audio_format"] is None


def test_tv_audio_format_reports_unavailable_without_raising_on_malformed_response():
    class MalformedFormatSpeaker(SettingsSpeaker):
        @property
        def soundbar_audio_input_format(self):
            raise ValueError("malformed HTAudioIn")

    assert project_device_details(MalformedFormatSpeaker())["device"]["tv_audio_format"] == {
        "state": "unavailable",
        "label": "Temporarily unavailable",
    }
