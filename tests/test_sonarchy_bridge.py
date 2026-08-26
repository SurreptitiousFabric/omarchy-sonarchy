from __future__ import annotations

import importlib.util
import json
import unittest
from datetime import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "sonarchy_bridge.py"
SPEC = importlib.util.spec_from_file_location("sonarchy_bridge", MODULE_PATH)
assert SPEC and SPEC.loader
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


class FakeGroup:
    def __init__(self, coordinator, members):
        self.coordinator = coordinator
        self.members = members


class SecurityTests(unittest.TestCase):
    def test_empty_xdg_cache_home_uses_the_home_fallback(self):
        with (
            patch.dict(bridge.os.environ, {"XDG_CACHE_HOME": ""}),
            patch.object(bridge.Path, "home", return_value=Path("/safe-home")),
        ):
            self.assertEqual(
                bridge.default_cache_path(),
                Path("/safe-home/.cache/sonarchy/rooms.json"),
            )

    def test_public_control_targets_are_rejected(self):
        with self.assertRaises(ValueError):
            bridge.validate_ip("8.8.8.8")
        with self.assertRaises(ValueError):
            bridge.validate_ip("169.254.169.254")
        self.assertEqual(bridge.validate_ip("192.168.1.20"), "192.168.1.20")

    def test_artwork_only_allows_speaker_http_or_public_https(self):
        self.assertEqual(
            bridge.album_art_url("/getaa?id=1", "192.168.1.20"),
            "http://192.168.1.20:1400/getaa?id=1",
        )
        self.assertEqual(
            bridge.album_art_url("http://169.254.169.254/latest/meta-data", "192.168.1.20"),
            "",
        )
        self.assertEqual(
            bridge.album_art_url("https://images.example.test/cover.jpg", "192.168.1.20"),
            "",
        )
        self.assertEqual(
            bridge.album_art_url("https://is4-ssl.mzstatic.com/cover.jpg", "192.168.1.20"),
            "https://is4-ssl.mzstatic.com/cover.jpg",
        )
        self.assertEqual(
            bridge.album_art_url("https://is4-ssl.mzstatic.com:8443/cover.jpg", "192.168.1.20"),
            "",
        )
        self.assertEqual(
            bridge.album_art_url("https://8.8.8.8/cover.jpg", "192.168.1.20"),
            "",
        )
        station_art = "https://static.mytuner-radio.net/media/tvos_radios/example.png"
        self.assertEqual(bridge.public_artwork_url(station_art), station_art)
        self.assertEqual(
            bridge.public_artwork_url(
                "https://evil.static.mytuner-radio.net/media/tvos_radios/example.png"
            ),
            "",
        )

    def test_search_text_is_bounded(self):
        with self.assertRaisesRegex(ValueError, "too long"):
            bridge.validate_search_term("x" * 121)
        with self.assertRaisesRegex(ValueError, "control"):
            bridge.validate_search_term("hello\nworld")


class FakeResource:
    def __init__(self, uri="x-test:stream"):
        self.uri = uri


class FakeReference:
    def __init__(self, uri="x-test:stream"):
        self.resources = [FakeResource(uri)]

    def to_element(self, include_namespaces=False):
        del include_namespaces
        return bridge.XML.Element("item") if hasattr(bridge, "XML") else None


class FakeFavorite:
    def __init__(self, item_id="FV:1", title="Favorite", playable=True):
        self.item_id = item_id
        self.title = title
        self.description = "A saved favorite"
        self.album_art_uri = "/art"
        self._reference = FakeReference() if playable else None

    @property
    def reference(self):
        if self._reference is None:
            raise ValueError("not playable")
        return self._reference


class FakeResult(list):
    @property
    def total_matches(self):
        return len(self)


class FakeLibrary:
    def __init__(self, favorites=None, tracks=None, shares=None):
        self.favorites = FakeResult(favorites or [])
        self.tracks = FakeResult(tracks or [])
        self.shares = list(shares or [])
        self.library_updating = False

    def get_sonos_favorites(self, max_items=100):
        return FakeResult(self.favorites[:max_items])

    def get_music_library_information(self, search_type, start=0, max_items=100, search_term=""):
        del start
        assert search_type == "tracks"
        term = search_term.casefold()
        matches = [item for item in self.tracks if term in item.title.casefold()]
        return FakeResult(matches[:max_items])

    def list_library_shares(self):
        return list(self.shares)

    def browse(self, ml_item=None, start=0, max_items=100):
        return FakeResult(list(ml_item.tracks)[start : start + max_items])

    def start_library_update(self):
        self.library_updating = True


class FakeMusicItem:
    def __init__(self, item_id="station:1", title="Station", uri="x-sonosapi-stream:test"):
        self.item_id = item_id
        self.title = title
        self.creator = "Artist"
        self.album = "Album"
        self.album_art_uri = "https://is4-ssl.mzstatic.com/art"
        self.can_play = True
        self.resources = [FakeResource(uri)]


class FakePlaylist:
    def __init__(self, item_id="SQ:1", title="Playlist", tracks=None):
        self.item_id = item_id
        self.title = title
        self.resources = [FakeResource(f"file:///jffs/settings/savedqueues.rsq#{item_id}")]
        self.tracks = FakeResult(tracks or [])


class FakeAlarm:
    def __init__(self, speaker, alarm_id="1"):
        self.zone = speaker
        self.alarm_id = alarm_id
        self.start_time = time(7, 0)
        self.duration = None
        self.recurrence = "DAILY"
        self.enabled = True
        self.volume = 25
        self.include_linked_zones = False
        self.room_uuid = speaker.uid
        self.program_uri = "x-rincon-buzzer:0"
        self.program_metadata = ""
        self.saved = 0
        self.removed = False

    def save(self):
        self.saved += 1
        return self.alarm_id

    def remove(self):
        self.removed = True


class FakeDeviceProperties:
    def __init__(self, speaker):
        self.speaker = speaker
        self.autoplay_room_uuid = ""
        self.set_autoplay_calls = []
        self.zone_name_override = None

    def GetAutoplayRoomUUID(self, arguments):
        assert dict(arguments) == {"Source": ""}
        return {"RoomUUID": self.autoplay_room_uuid}

    def SetAutoplayRoomUUID(self, arguments):
        values = dict(arguments)
        assert values.get("Source") == ""
        self.autoplay_room_uuid = values["RoomUUID"]
        self.set_autoplay_calls.append(arguments)

    def GetZoneAttributes(self, arguments):
        assert arguments == []
        name = self.speaker.player_name
        if self.zone_name_override is not None:
            name = self.zone_name_override
        return {"CurrentZoneName": name}


class FakeAVTransport:
    def __init__(self):
        self.current_uri = "x-rincon-queue:RINCON_TEST#0"

    def GetMediaInfo(self, arguments):
        assert arguments == [("InstanceID", 0)]
        return {"CurrentURI": self.current_uri}


class FakeSpeaker:
    def __init__(
        self,
        ip: str,
        name: str,
        uid: str,
        *,
        volume: int = 25,
        muted: bool = False,
        state: str = "STOPPED",
    ):
        self.ip_address = ip
        self.player_name = name
        self.uid = uid
        self.volume = volume
        self.mute = muted
        self.state = state
        self.group = FakeGroup(self, [self])
        self.calls = []
        self.is_visible = True
        self.play_mode = "NORMAL"
        self.shuffle = False
        self.repeat = False
        self.cross_fade = False
        self.bass = 0
        self.treble = 0
        self.loudness = True
        self.night_mode = False
        self.speech_enhance_enabled = False
        self.sub_enabled = True
        self.sub_gain = 0
        self.sub_crossover = 80
        self.surround_enabled = True
        self.surround_mode = False
        self.surround_volume_tv = 0
        self.surround_volume_music = 0
        self.audio_delay = 0
        self.balance = (100, 100)
        self.status_light = True
        self.buttons_enabled = True
        self.trueplay = False
        self.mic_enabled = False
        self.voice_service_configured = False
        self.channel = "LF,RF"
        self.music_source = "UNKNOWN"
        self.is_soundbar = False
        self.deviceProperties = FakeDeviceProperties(self)
        self.avTransport = FakeAVTransport()
        self.sleep_timer = None
        self.music_library = FakeLibrary()
        self.queue = FakeResult()
        self.playlists = FakeResult()
        self.visible_zones = {self}

    def get_speaker_info(self):
        return {
            "model_name": "Sonos One",
            "model_number": "S18",
            "serial_number": "00-11-22-33-44-55:A",
            "software_version": "99.1",
            "hardware_version": "1.0",
        }

    def get_battery_info(self, timeout=3):
        del timeout
        return {}

    def get_current_transport_info(self):
        return {"current_transport_state": self.state}

    def get_current_track_info(self):
        return {
            "title": "A Track",
            "artist": "An Artist",
            "album": "An Album",
            "album_art": "/getaa?u=track",
            "position": "0:00:12",
            "duration": "0:03:40",
            "playlist_position": "1",
        }

    def play(self):
        self.calls.append("play")

    def pause(self):
        self.calls.append("pause")

    def stop(self):
        self.calls.append("stop")

    def next(self):
        self.calls.append("next")

    def previous(self):
        self.calls.append("previous")

    def get_sleep_timer(self):
        return self.sleep_timer

    def set_sleep_timer(self, value):
        self.sleep_timer = value
        self.calls.append(("sleep", value))

    def join(self, coordinator):
        self.calls.append(("join", coordinator.ip_address))

    def unjoin(self):
        self.calls.append("unjoin")

    def partymode(self):
        self.calls.append("partymode")

    def play_from_queue(self, index):
        self.calls.append(("play_from_queue", index))

    def remove_from_queue(self, index):
        self.calls.append(("remove_from_queue", index))

    def clear_queue(self):
        self.calls.append("clear_queue")

    def play_uri(self, uri, **kwargs):
        self.calls.append(("play_uri", uri, kwargs))

    @property
    def queue_size(self):
        return len(self.queue)

    def get_queue(self, start=0, max_items=100, full_album_art_uri=False):
        del full_album_art_uri
        return FakeResult(self.queue[start : start + max_items])

    def add_to_queue(self, item, position=0, as_next=False):
        del as_next
        if position:
            self.queue.insert(max(0, position - 1), item)
            result = position
        else:
            self.queue.append(item)
            result = len(self.queue)
        self.calls.append(("add_to_queue", item.item_id, position))
        return result

    def get_sonos_playlists(self, max_items=100):
        return FakeResult(self.playlists[:max_items])

    def get_sonos_playlist_by_attr(self, attr_name, match):
        for playlist in self.playlists:
            if getattr(playlist, attr_name) == match:
                return playlist
        raise ValueError("playlist not found")

    def create_sonos_playlist(self, title):
        playlist = FakePlaylist(f"SQ:{len(self.playlists) + 1}", title)
        self.playlists.append(playlist)
        return playlist

    def create_sonos_playlist_from_queue(self, title):
        playlist = FakePlaylist(f"SQ:{len(self.playlists) + 1}", title, list(self.queue))
        self.playlists.append(playlist)
        return playlist

    def remove_sonos_playlist(self, playlist):
        self.playlists.remove(playlist)

    def remove_from_sonos_playlist(self, playlist, index):
        playlist.tracks.pop(index)

    def move_in_sonos_playlist(self, playlist, index, new_index):
        playlist.tracks.insert(new_index, playlist.tracks.pop(index))

    def switch_to_line_in(self, source):
        self.calls.append(("line-in", source.ip_address))

    def switch_to_tv(self):
        self.calls.append("tv")


class SnapshotTests(unittest.TestCase):
    def test_upnp_not_implemented_metadata_is_hidden(self):
        self.assertEqual(bridge.clean("NOT_IMPLEMENTED"), "")

    def test_empty_discovery_is_a_successful_snapshot(self):
        with (
            patch.object(bridge, "cached_visible_zones", return_value=set()),
            patch.object(bridge.soco, "discover", return_value=None) as discover,
        ):
            self.assertEqual(
                bridge.discover_snapshot(1),
                {"ok": True, "devices": []},
            )
        discover.assert_called_once_with(
            timeout=1,
            allow_network_scan=True,
            max_threads=128,
            scan_timeout=0.8,
            min_netmask=24,
        )

    def test_cached_topology_skips_network_discovery(self):
        speaker = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
        with (
            patch.object(bridge, "cached_visible_zones", return_value={speaker}),
            patch.object(bridge, "save_cached_zones") as save_cache,
            patch.object(bridge.soco, "discover") as discover,
        ):
            payload = bridge.discover_snapshot(1)

        self.assertEqual([device["name"] for device in payload["devices"]], ["Kitchen"])
        discover.assert_not_called()
        save_cache.assert_called_once()

    def test_group_transport_is_read_from_coordinator_once(self):
        kitchen = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
        lounge = FakeSpeaker("192.168.1.11", "Lounge", "RINCON_L", state="PLAYING")
        group = FakeGroup(lounge, [kitchen, lounge])
        kitchen.group = group
        lounge.group = group

        devices = bridge.snapshot_from_speakers([kitchen, lounge])

        self.assertEqual([device["name"] for device in devices], ["Kitchen", "Lounge"])
        self.assertTrue(all(device["is_playing"] for device in devices))
        self.assertEqual(devices[0]["coordinator_ip"], "192.168.1.11")
        self.assertEqual(devices[0]["group_members"], ["Kitchen", "Lounge"])
        self.assertEqual(
            devices[0]["album_art"],
            "http://192.168.1.11:1400/getaa?u=track",
        )


class ActionTests(unittest.TestCase):
    def test_playback_action_routes_to_group_coordinator(self):
        kitchen = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
        lounge = FakeSpeaker("192.168.1.11", "Lounge", "RINCON_L")
        kitchen.group = FakeGroup(lounge, [kitchen, lounge])

        with patch.object(bridge, "SoCo", return_value=kitchen):
            result = bridge.run_action("next", kitchen.ip_address)

        self.assertEqual(lounge.calls, ["next"])
        self.assertEqual(result["coordinator_ip"], lounge.ip_address)

    def test_play_pause_pauses_a_playing_group(self):
        speaker = FakeSpeaker(
            "192.168.1.10",
            "Kitchen",
            "RINCON_K",
            state="PLAYING",
        )
        with patch.object(bridge, "SoCo", return_value=speaker):
            result = bridge.run_action("play-pause", speaker.ip_address)

        self.assertEqual(speaker.calls, ["pause"])
        self.assertEqual(result["action"], "pause")

    def test_volume_is_clamped_and_room_specific(self):
        speaker = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
        with patch.object(bridge, "SoCo", return_value=speaker):
            result = bridge.run_action("volume", speaker.ip_address, 140)

        self.assertEqual(speaker.volume, 100)
        self.assertEqual(result["volume"], 100)

    def test_grouping_joins_room_to_selected_coordinator(self):
        kitchen = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
        lounge = FakeSpeaker("192.168.1.11", "Lounge", "RINCON_L")

        def speaker_for(ip):
            return kitchen if ip == kitchen.ip_address else lounge

        with patch.object(bridge, "SoCo", side_effect=speaker_for):
            result = bridge.group_room(kitchen.ip_address, lounge.ip_address, True)

        self.assertEqual(lounge.calls, [("join", kitchen.ip_address)])
        self.assertTrue(result["grouped"])

    def test_separating_coordinator_ungroups_other_members(self):
        kitchen = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
        lounge = FakeSpeaker("192.168.1.11", "Lounge", "RINCON_L")
        kitchen.group = lounge.group = FakeGroup(kitchen, [kitchen, lounge])

        with patch.object(bridge, "SoCo", return_value=kitchen):
            bridge.separate_room(kitchen.ip_address)

        self.assertEqual(lounge.calls, ["unjoin"])

    def test_playback_options_update_coordinator(self):
        speaker = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
        with patch.object(bridge, "SoCo", return_value=speaker):
            bridge.playback_option(speaker.ip_address, "shuffle", "on")
            bridge.playback_option(speaker.ip_address, "repeat", "one")
            bridge.playback_option(speaker.ip_address, "sleep", "1800")

        self.assertTrue(speaker.shuffle)
        self.assertEqual(speaker.repeat, "ONE")
        self.assertEqual(speaker.sleep_timer, 1800)

    def test_play_modes_are_rejected_before_sonos_when_queue_is_not_active(self):
        speaker = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
        speaker.avTransport.current_uri = "x-sonosapi-stream:station"

        with (
            patch.object(bridge, "SoCo", return_value=speaker),
            self.assertRaisesRegex(ValueError, "queue is the active source"),
        ):
            bridge.playback_option(speaker.ip_address, "shuffle", "on")

        self.assertFalse(speaker.shuffle)

    def test_sound_value_is_clamped(self):
        speaker = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
        with patch.object(bridge, "SoCo", return_value=speaker):
            result = bridge.set_sound(speaker.ip_address, "bass", "99")

        self.assertEqual(speaker.bass, 10)
        self.assertEqual(result["message"], "Bass +10")

    def test_rename_rejects_empty_name(self):
        speaker = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
        with (
            patch.object(bridge, "SoCo", return_value=speaker),
            self.assertRaisesRegex(ValueError, "cannot be empty"),
        ):
            bridge.rename_room(speaker.ip_address, "   ")

    def test_rename_updates_the_real_player_name(self):
        speaker = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
        with patch.object(bridge, "SoCo", return_value=speaker):
            result = bridge.rename_room(speaker.ip_address, "Dining Room")

        self.assertEqual(speaker.player_name, "Dining Room")
        self.assertEqual(result["message"], "Renamed to Dining Room")

    def test_rename_requires_authoritative_speaker_confirmation(self):
        speaker = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
        speaker.deviceProperties.zone_name_override = "Kitchen"

        with (
            patch.object(bridge, "SoCo", return_value=speaker),
            self.assertRaisesRegex(ValueError, "did not confirm"),
        ):
            bridge.rename_room(speaker.ip_address, "Dining Room")


class BrowseTests(unittest.TestCase):
    def test_details_report_playback_and_sound(self):
        speaker = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
        speaker.sleep_timer = 900
        with patch.object(bridge, "SoCo", return_value=speaker):
            payload = bridge.details_snapshot(speaker.ip_address)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["playback"]["sleep_timer"], 900)
        self.assertEqual(payload["playback"]["repeat"], "off")
        self.assertEqual(payload["sound"]["bass"], 0)
        self.assertEqual(payload["sound"]["balance"], 0)
        self.assertEqual(payload["device"]["model_number"], "S18")
        self.assertTrue(payload["device"]["status_light"])
        self.assertIsNone(payload["device"]["tv_autoplay"])
        self.assertTrue(payload["playback"]["play_mode_supported"])
        self.assertFalse(payload["playback"]["tv_autoplay_risk"])

    def test_details_disable_play_modes_when_current_transport_is_not_the_queue(self):
        speaker = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
        speaker.avTransport.current_uri = "x-sonosapi-stream:station"

        with patch.object(bridge, "SoCo", return_value=speaker):
            payload = bridge.details_snapshot(speaker.ip_address)

        self.assertFalse(payload["playback"]["play_mode_supported"])

    def test_details_report_tv_autoplay_risk_without_exposing_its_room_uuid(self):
        speaker = FakeSpeaker("192.168.1.10", "Living Room", "RINCON_HT")
        speaker.is_soundbar = True
        speaker.music_source = "TV"
        speaker.deviceProperties.autoplay_room_uuid = speaker.uid

        with patch.object(bridge, "SoCo", return_value=speaker):
            payload = bridge.details_snapshot(speaker.ip_address)

        self.assertTrue(payload["device"]["tv_autoplay"])
        self.assertTrue(payload["playback"]["tv_autoplay_risk"])
        self.assertNotIn("tv_autoplay_room_uuid", payload["device"])

    def test_favorites_mark_unplayable_entries(self):
        speaker = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
        speaker.music_library = FakeLibrary(
            [FakeFavorite("FV:1", playable=True), FakeFavorite("FV:2", playable=False)]
        )

        payload = bridge.favorites_content(speaker, 10)

        self.assertEqual(payload["total"], 2)
        self.assertEqual([item["playable"] for item in payload["items"]], [True, False])

    def test_apple_search_only_returns_music_apple_links(self):
        response = Mock()
        response.status_code = 200
        response.headers = {}
        response.raise_for_status.return_value = None
        result_payload = {
            "results": [
                {
                    "trackId": 1,
                    "trackName": "Track",
                    "artistName": "Artist",
                    "collectionName": "Album",
                    "trackTimeMillis": 61000,
                    "artworkUrl100": "https://is4-ssl.mzstatic.com/art",
                    "trackViewUrl": "https://music.apple.com/ch/album/a/1?i=1",
                    "collectionId": 1,
                    "collectionViewUrl": ("https://music.apple.com/ch/album/a/1?i=1&uo=4"),
                },
                {
                    "trackId": 2,
                    "trackName": "Wrong host",
                    "trackViewUrl": "https://example.test/not-apple",
                },
            ]
        }
        response.iter_content.return_value = [json.dumps(result_payload).encode("utf-8")]

        with patch.object(bridge.requests, "get", return_value=response):
            payload = bridge.apple_content("track", 10)

        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["items"][0]["subtitle"], "Artist · Album · 1:01")
        self.assertEqual(
            payload["items"][0]["album_art"],
            "https://is4-ssl.mzstatic.com/art",
        )
        self.assertEqual(
            payload["items"][0]["album_url"],
            "https://music.apple.com/ch/album/a/1",
        )
        apple_service = next(
            service
            for service in bridge.ShareLinkPlugin(Mock()).services
            if service.__class__.__name__ == "AppleMusicShare"
        )
        self.assertEqual(
            apple_service.canonical_uri(payload["items"][0]["album_url"]),
            "album:1",
        )
        response.close.assert_called_once()

    def test_radio_artwork_resolver_returns_only_a_confident_apple_match(self):
        response = Mock(status_code=200, headers={})
        response.raise_for_status.return_value = None
        response.iter_content.return_value = [
            json.dumps(
                {
                    "results": [
                        {
                            "trackName": "Pie Jesu - Album Version",
                            "artistName": "The Choirboys",
                            "collectionName": "The Choir Boys (EU Version)",
                            "artworkUrl100": (
                                "https://is4-ssl.mzstatic.com/image/thumb/Music/cover/100x100bb.jpg"
                            ),
                        },
                        {
                            "trackName": "Requiem: Pie Jesu",
                            "artistName": "Duncan Watts",
                            "collectionName": "Choirboy of the Year",
                            "artworkUrl100": (
                                "https://is4-ssl.mzstatic.com/image/thumb/Music/wrong/100x100bb.jpg"
                            ),
                        },
                    ]
                }
            ).encode("utf-8")
        ]

        with patch.object(bridge.requests, "get", return_value=response) as get:
            payload = bridge.resolve_apple_artwork(
                "Requiem - Pie Jesu.",
                "Andrew Lloyd Webber, The Choirboys",
            )

        self.assertTrue(payload["match"])
        self.assertEqual(payload["artist"], "The Choirboys")
        self.assertIn("/600x600bb.jpg", payload["artwork_url"])
        self.assertGreaterEqual(payload["confidence"], 0.8)
        self.assertEqual(get.call_args.kwargs["params"]["entity"], "song")
        response.close.assert_called_once()

    def test_radio_artwork_resolver_returns_a_quiet_miss(self):
        response = Mock(status_code=200, headers={})
        response.raise_for_status.return_value = None
        response.iter_content.return_value = [
            json.dumps(
                {
                    "results": [
                        {
                            "trackName": "Pie Jesu",
                            "artistName": "Different Artist",
                            "artworkUrl100": "https://is4-ssl.mzstatic.com/100x100bb.jpg",
                        }
                    ]
                }
            ).encode("utf-8")
        ]

        with patch.object(bridge.requests, "get", return_value=response):
            payload = bridge.resolve_apple_artwork("Pie Jesu", "The Choirboys")

        self.assertEqual(
            payload,
            {"ok": True, "match": False, "artwork_url": "", "confidence": 0},
        )

    def test_apple_album_url_rejects_a_mismatched_collection(self):
        self.assertEqual(
            bridge.public_apple_album_url(
                "https://music.apple.com/ch/album/a/1?i=9",
                "2",
            ),
            "",
        )
        self.assertEqual(
            bridge.public_apple_album_url("https://example.test/ch/album/a/1", "1"),
            "",
        )

    def test_apple_search_rejects_redirects_and_oversized_responses(self):
        redirect = Mock(status_code=302, headers={})
        redirect.close = Mock()
        with (
            patch.object(bridge.requests, "get", return_value=redirect),
            self.assertRaisesRegex(ValueError, "redirect"),
        ):
            bridge.apple_content("track", 10)
        redirect.close.assert_called_once()

        oversized = Mock(
            status_code=200,
            headers={"content-length": str(bridge.APPLE_RESPONSE_LIMIT + 1)},
        )
        oversized.raise_for_status.return_value = None
        oversized.close = Mock()
        with (
            patch.object(bridge.requests, "get", return_value=oversized),
            self.assertRaisesRegex(ValueError, "oversized"),
        ):
            bridge.apple_content("track", 10)
        oversized.close.assert_called_once()

    def test_apple_play_converts_one_based_queue_position(self):
        speaker = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
        plugin = Mock()
        plugin.add_share_link_to_queue.return_value = 4
        url = "https://music.apple.com/ch/album/a/1?i=1"

        with (
            patch.object(bridge, "SoCo", return_value=speaker),
            patch.object(bridge, "ShareLinkPlugin", return_value=plugin),
        ):
            bridge.play_apple(speaker.ip_address, url)

        plugin.add_share_link_to_queue.assert_called_once_with(url)
        self.assertEqual(speaker.calls, [("play_from_queue", 3)])

    def test_apple_album_link_is_canonicalized_queued_and_started(self):
        speaker = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
        plugin = Mock()
        plugin.add_share_link_to_queue.return_value = 7
        album_url = "https://music.apple.com/ch/album/every-open-eye/1031545506?i=1031545514&uo=4"
        canonical_url = "https://music.apple.com/ch/album/every-open-eye/1031545506"

        with (
            patch.object(bridge, "SoCo", return_value=speaker),
            patch.object(bridge, "ShareLinkPlugin", return_value=plugin),
        ):
            payload = bridge.play_apple_album(speaker.ip_address, album_url)

        plugin.add_share_link_to_queue.assert_called_once_with(canonical_url)
        self.assertEqual(speaker.calls, [("play_from_queue", 6)])
        self.assertEqual(payload["action"], "play-apple-album")

    def test_apple_album_action_rejects_track_only_links_before_queueing(self):
        speaker = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
        plugin = Mock()

        with (
            patch.object(bridge, "SoCo", return_value=speaker) as speaker_factory,
            patch.object(bridge, "ShareLinkPlugin", return_value=plugin),
            self.assertRaisesRegex(ValueError, "album link"),
        ):
            bridge.play_apple_album(
                speaker.ip_address,
                "https://music.apple.com/ch/song/not-an-album/1031545514",
            )

        plugin.add_share_link_to_queue.assert_not_called()
        speaker_factory.assert_not_called()
        self.assertEqual(speaker.calls, [])

    def test_apple_album_is_blocked_when_active_tv_autoplay_would_take_over(self):
        speaker = FakeSpeaker("192.168.1.10", "Living Room", "RINCON_HT")
        speaker.is_soundbar = True
        speaker.music_source = "TV"
        speaker.deviceProperties.autoplay_room_uuid = speaker.uid
        plugin = Mock()

        with (
            patch.object(bridge, "SoCo", return_value=speaker),
            patch.object(bridge, "ShareLinkPlugin", return_value=plugin),
            self.assertRaisesRegex(ValueError, "turn off TV Autoplay"),
        ):
            bridge.play_apple_album(
                speaker.ip_address,
                "https://music.apple.com/ch/album/every-open-eye/1031545506",
            )

        plugin.add_share_link_to_queue.assert_not_called()
        self.assertEqual(speaker.calls, [])

    def test_details_detect_tv_autoplay_takeover_after_an_album_started(self):
        speaker = FakeSpeaker("192.168.1.10", "Living Room", "RINCON_HT")
        speaker.is_soundbar = True
        speaker.music_source = "QUEUE"
        speaker.deviceProperties.autoplay_room_uuid = speaker.uid
        plugin = Mock()
        plugin.add_share_link_to_queue.return_value = 1

        with (
            patch.object(bridge, "SoCo", return_value=speaker),
            patch.object(bridge, "ShareLinkPlugin", return_value=plugin),
        ):
            bridge.play_apple_album(
                speaker.ip_address,
                "https://music.apple.com/ch/album/every-open-eye/1031545506",
            )
            speaker.music_source = "TV"
            details = bridge.details_snapshot(speaker.ip_address)

        self.assertEqual(speaker.calls, [("play_from_queue", 0)])
        self.assertTrue(details["playback"]["tv_autoplay_risk"])

    def test_global_result_plays_with_service_metadata(self):
        speaker = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
        item = FakeMusicItem()
        with (
            patch.object(bridge, "SoCo", return_value=speaker),
            patch.object(bridge, "global_results", return_value=[item]),
            patch.object(bridge, "to_didl_string", return_value="<meta/>") as metadata,
        ):
            bridge.play_global(speaker.ip_address, item.item_id, "station")

        metadata.assert_called_once_with(item)
        self.assertEqual(
            speaker.calls,
            [("play_uri", "x-sonosapi-stream:test", {"meta": "<meta/>"})],
        )

    def test_parser_builds_every_subcommand(self):
        command_parser = bridge.parser()
        args = command_parser.parse_args(["sound", "192.168.1.10", "speech-enhancement", "on"])
        self.assertEqual(args.setting, "speech-enhancement")

        queue_args = command_parser.parse_args(["remove-queue", "192.168.1.10", "2", "Q:3"])
        self.assertEqual(queue_args.item_id, "Q:3")


class LibraryAndPlaylistTests(unittest.TestCase):
    def test_library_reports_shares_and_searches_tracks(self):
        speaker = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
        track = FakeMusicItem("A:TRACKS/TRACK:1", "Blue Train", "x-file-cifs:test")
        speaker.music_library = FakeLibrary(tracks=[track], shares=["//server/music"])

        empty = bridge.library_content(speaker, "", 40)
        result = bridge.library_content(speaker, "blue", 40)

        self.assertEqual(empty["shares"], ["//server/music"])
        self.assertFalse(empty["updating"])
        self.assertEqual(result["items"][0]["id"], track.item_id)
        self.assertEqual(result["items"][0]["index"], 0)

    def test_library_item_is_re_resolved_before_queueing_next(self):
        speaker = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
        track = FakeMusicItem("A:TRACKS/TRACK:1", "Blue Train", "x-file-cifs:test")
        speaker.music_library = FakeLibrary(tracks=[track])
        speaker.queue = FakeResult([FakeMusicItem("Q:1", "Current")])

        with patch.object(bridge, "SoCo", return_value=speaker):
            payload = bridge.enqueue_content_item(
                speaker.ip_address,
                "library",
                "blue",
                track.item_id,
                0,
                "next",
            )

        self.assertEqual(payload["message"], "Added next")
        self.assertEqual(speaker.queue[1].item_id, track.item_id)

    def test_stale_queue_index_cannot_play_or_remove_a_different_item(self):
        speaker = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
        speaker.queue = FakeResult([FakeMusicItem("Q:changed", "Different")])

        with (
            patch.object(bridge, "SoCo", return_value=speaker),
            self.assertRaisesRegex(ValueError, "queue changed"),
        ):
            bridge.queue_action(speaker.ip_address, "remove-queue", 0, "Q:original")

        self.assertEqual(len(speaker.queue), 1)

    def test_playlist_browse_create_save_play_and_delete(self):
        speaker = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
        track = FakeMusicItem("A:TRACKS/TRACK:1", "Track", "x-file-cifs:test")
        playlist = FakePlaylist("SQ:1", "Morning", [track])
        speaker.playlists = FakeResult([playlist])
        speaker.queue = FakeResult([track])

        listing = bridge.playlists_content(speaker, 40)
        contents = bridge.playlist_content(speaker, "SQ:1", 40)
        self.assertTrue(listing["items"][0]["playable"])
        self.assertEqual(contents["playlist_title"], "Morning")

        with patch.object(bridge, "SoCo", return_value=speaker):
            bridge.playlist_action(speaker.ip_address, "create", title="Empty")
            bridge.playlist_action(speaker.ip_address, "save-queue", title="Saved")
            bridge.playlist_action(speaker.ip_address, "play", playlist_id="SQ:1")
            bridge.playlist_action(speaker.ip_address, "delete", playlist_id="SQ:1")

        self.assertEqual([item.title for item in speaker.playlists], ["Empty", "Saved"])
        self.assertIn(("play_from_queue", 1), speaker.calls)

    def test_playlist_track_mutation_checks_the_expected_item(self):
        speaker = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
        first = FakeMusicItem("TRACK:1", "First")
        second = FakeMusicItem("TRACK:2", "Second")
        playlist = FakePlaylist("SQ:1", "Morning", [first, second])
        speaker.playlists = FakeResult([playlist])

        with patch.object(bridge, "SoCo", return_value=speaker):
            with self.assertRaisesRegex(ValueError, "playlist changed"):
                bridge.playlist_track_action(speaker.ip_address, "remove", "SQ:1", 0, "TRACK:old")
            bridge.playlist_track_action(speaker.ip_address, "down", "SQ:1", 0, "TRACK:1")

        self.assertEqual([item.item_id for item in playlist.tracks], ["TRACK:2", "TRACK:1"])


class AlarmSourceAndDeviceTests(unittest.TestCase):
    def test_alarm_snapshot_does_not_expose_program_uri(self):
        speaker = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
        alarm = FakeAlarm(speaker)
        alarm.program_uri = "x-sonos-http:private-service-token"

        with (
            patch.object(bridge, "SoCo", return_value=speaker),
            patch.object(bridge, "get_alarms", return_value={alarm}),
        ):
            payload = bridge.alarms_snapshot(speaker.ip_address)

        self.assertEqual(payload["items"][0]["program"], "Saved Sonos content")
        self.assertNotIn("program_uri", payload["items"][0])
        self.assertNotIn("private-service-token", json.dumps(payload))

    def test_new_alarm_is_validated_and_saved_for_selected_room(self):
        speaker = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
        alarm = FakeAlarm(speaker, "7")

        with (
            patch.object(bridge, "SoCo", return_value=speaker),
            patch.object(bridge, "Alarm", return_value=alarm),
        ):
            payload = bridge.save_alarm(
                speaker.ip_address,
                "new",
                "06:45",
                "WEEKDAYS",
                35,
                30,
                True,
                True,
                "chime",
            )

        self.assertEqual(payload["id"], "7")
        self.assertEqual(alarm.start_time, time(6, 45))
        self.assertEqual(alarm.duration, time(0, 30))
        self.assertEqual(alarm.program_uri, None)
        self.assertEqual(alarm.saved, 1)

    def test_alarm_time_rejects_invalid_values(self):
        with self.assertRaisesRegex(ValueError, "HH:MM"):
            bridge.parse_alarm_time("25:00")

    def test_line_in_source_must_be_in_visible_household(self):
        selected = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
        source = FakeSpeaker("192.168.1.11", "Turntable", "RINCON_T")
        selected.visible_zones = {selected, source}

        with patch.object(bridge, "SoCo", return_value=selected):
            bridge.switch_source(selected.ip_address, "line-in", source.ip_address)
            with self.assertRaisesRegex(ValueError, "household"):
                bridge.switch_source(selected.ip_address, "line-in", "192.168.1.99")

        self.assertEqual(selected.calls, [("line-in", source.ip_address)])

    def test_device_setting_uses_an_allowlisted_boolean_property(self):
        speaker = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
        with patch.object(bridge, "SoCo", return_value=speaker):
            bridge.set_device(speaker.ip_address, "status-light", "off")
            with self.assertRaisesRegex(ValueError, "Unsupported"):
                bridge.set_device(speaker.ip_address, "made-up", "on")

        self.assertFalse(speaker.status_light)

    def test_tv_autoplay_can_be_explicitly_disabled_and_enabled(self):
        speaker = FakeSpeaker("192.168.1.10", "Living Room", "RINCON_HT")
        speaker.is_soundbar = True
        speaker.deviceProperties.autoplay_room_uuid = speaker.uid

        with patch.object(bridge, "SoCo", return_value=speaker):
            disabled = bridge.set_device(speaker.ip_address, "tv-autoplay", "off")
            enabled = bridge.set_device(speaker.ip_address, "tv-autoplay", "on")

        self.assertEqual(disabled["message"], "TV Autoplay off")
        self.assertEqual(enabled["message"], "TV Autoplay on")
        self.assertEqual(
            speaker.deviceProperties.set_autoplay_calls,
            [
                [("RoomUUID", ""), ("Source", "")],
                [("RoomUUID", speaker.uid), ("Source", "")],
            ],
        )

    def test_tv_autoplay_is_rejected_for_a_non_home_theater_speaker(self):
        speaker = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")

        with (
            patch.object(bridge, "SoCo", return_value=speaker),
            self.assertRaisesRegex(ValueError, "not available"),
        ):
            bridge.set_device(speaker.ip_address, "tv-autoplay", "off")

        self.assertEqual(speaker.deviceProperties.set_autoplay_calls, [])


@pytest.mark.parametrize(
    "action",
    sorted(bridge.PLAYBACK_ACTIONS - {"play-pause"}),
)
def test_every_direct_playback_action_changes_the_coordinator(action):
    speaker = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
    with patch.object(bridge, "SoCo", return_value=speaker):
        payload = bridge.run_action(action, speaker.ip_address)

    assert speaker.calls == [action]
    assert payload["action"] == action


def test_mute_toggle_changes_only_the_selected_room():
    speaker = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K", muted=False)
    with patch.object(bridge, "SoCo", return_value=speaker):
        payload = bridge.run_action("mute-toggle", speaker.ip_address)

    assert speaker.mute is True
    assert payload["muted"] is True


@pytest.mark.parametrize(
    ("option", "value", "attribute", "expected"),
    (
        ("shuffle", "on", "shuffle", True),
        ("repeat", "all", "repeat", True),
        ("repeat", "one", "repeat", "ONE"),
        ("crossfade", "on", "cross_fade", True),
        ("sleep", "1800", "sleep_timer", 1800),
        ("sleep", "off", "sleep_timer", None),
    ),
)
def test_every_playback_option_is_applied(option, value, attribute, expected):
    speaker = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
    with patch.object(bridge, "SoCo", return_value=speaker):
        payload = bridge.playback_option(speaker.ip_address, option, value)

    assert getattr(speaker, attribute) == expected
    assert payload["action"] == option


@pytest.mark.parametrize("setting", sorted(bridge.NUMBER_SETTINGS))
def test_every_numeric_sound_setting_is_supported_and_bounded(setting):
    speaker = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
    with patch.object(bridge, "SoCo", return_value=speaker):
        payload = bridge.set_sound(speaker.ip_address, setting, "999")

    assert payload["action"] == setting


@pytest.mark.parametrize(
    "setting",
    sorted(set(bridge.BOOLEAN_SETTINGS) | {"speech-enhancement"}),
)
def test_every_boolean_sound_setting_can_be_enabled(setting):
    speaker = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
    with patch.object(bridge, "SoCo", return_value=speaker):
        payload = bridge.set_sound(speaker.ip_address, setting, "on")

    assert payload["action"] == setting


@pytest.mark.parametrize("setting", sorted(bridge.DEVICE_BOOLEAN_SETTINGS))
def test_every_device_toggle_can_be_changed(setting):
    speaker = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
    with patch.object(bridge, "SoCo", return_value=speaker):
        payload = bridge.set_device(speaker.ip_address, setting, "off")

    assert payload["action"] == setting
    assert getattr(speaker, bridge.DEVICE_BOOLEAN_SETTINGS[setting]) is False


@pytest.mark.parametrize("action", ("play-queue", "remove-queue", "clear-queue"))
def test_every_queue_mutation_has_a_success_path(action):
    speaker = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
    track = FakeMusicItem("Q:1", "Queued")
    speaker.queue = FakeResult([track])
    with patch.object(bridge, "SoCo", return_value=speaker):
        if action == "clear-queue":
            payload = bridge.queue_action(speaker.ip_address, action)
        else:
            payload = bridge.queue_action(speaker.ip_address, action, 0, track.item_id)

    assert payload["action"] == action
    expected_call = {
        "play-queue": ("play_from_queue", 0),
        "remove-queue": ("remove_from_queue", 0),
        "clear-queue": "clear_queue",
    }[action]
    assert expected_call in speaker.calls


@pytest.mark.parametrize("mode", ("play", "next", "end"))
def test_every_queue_placement_mode_is_supported(mode):
    speaker = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
    track = FakeMusicItem("A:TRACKS/TRACK:1", "Blue Train", "x-file-cifs:test")
    speaker.music_library = FakeLibrary(tracks=[track])
    speaker.queue = FakeResult([FakeMusicItem("Q:1", "Current")])
    with patch.object(bridge, "SoCo", return_value=speaker):
        payload = bridge.enqueue_content_item(
            speaker.ip_address,
            "library",
            "blue",
            track.item_id,
            0,
            mode,
        )

    assert payload["action"] == f"queue-{mode}"


@pytest.mark.parametrize("action", ("up", "down", "remove"))
def test_every_playlist_track_mutation_has_a_success_path(action):
    speaker = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
    tracks = [
        FakeMusicItem("TRACK:1", "First"),
        FakeMusicItem("TRACK:2", "Second"),
        FakeMusicItem("TRACK:3", "Third"),
    ]
    playlist = FakePlaylist("SQ:1", "Morning", tracks)
    speaker.playlists = FakeResult([playlist])
    with patch.object(bridge, "SoCo", return_value=speaker):
        payload = bridge.playlist_track_action(
            speaker.ip_address,
            action,
            playlist.item_id,
            1,
            "TRACK:2",
        )

    assert payload["action"] == f"playlist-track-{action}"


def test_group_everywhere_calls_partymode():
    speaker = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
    with patch.object(bridge, "SoCo", return_value=speaker):
        payload = bridge.group_all(speaker.ip_address)

    assert speaker.calls == ["partymode"]
    assert payload["action"] == "group-all"


def test_tv_source_switches_the_group_coordinator():
    speaker = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
    with patch.object(bridge, "SoCo", return_value=speaker):
        payload = bridge.switch_source(speaker.ip_address, "tv")

    assert speaker.calls == ["tv"]
    assert payload["action"] == "source-tv"


@pytest.mark.parametrize("operation", ("toggle", "delete"))
def test_alarm_toggle_and_delete_mutate_the_exact_alarm(operation):
    speaker = FakeSpeaker("192.168.1.10", "Kitchen", "RINCON_K")
    alarm = FakeAlarm(speaker)
    with (
        patch.object(bridge, "SoCo", return_value=speaker),
        patch.object(bridge, "get_alarms", return_value={alarm}),
    ):
        if operation == "toggle":
            payload = bridge.toggle_alarm(speaker.ip_address, alarm.alarm_id, False)
            assert alarm.enabled is False
            assert alarm.saved == 1
        else:
            payload = bridge.delete_alarm(speaker.ip_address, alarm.alarm_id)
            assert alarm.removed is True

    assert payload["action"] == f"alarm-{operation}"


if __name__ == "__main__":
    unittest.main()
