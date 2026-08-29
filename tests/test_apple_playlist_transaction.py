from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest
import soco
from soco.data_structures_entry import from_didl_string
from soco.exceptions import SoCoUPnPException

from sonarchy_backend.contracts import (
    MAX_PROTOCOL_LINE_BYTES,
    MAX_PROTOCOL_REQUEST_ID_BYTES,
    protocol_line,
    result_payload,
)
from sonarchy_backend.domains.apple_playlist_transaction import (
    apple_song_identity_from_item,
    create_preflighted_apple_playlist,
    inspect_apple_playlist_target,
    verify_apple_items,
)
from sonarchy_backend.domains.errors import PlanConflictError, PlaylistTransactionError
from sonarchy_backend.infrastructure.apple_saved_queue import (
    APPEND_INDEX,
    APPLE_SAVED_RESOURCE_PROTOCOL_INFO,
    APPLE_SERVICE_NUMBER,
    APPLE_SONG_CLASS,
    APPLE_SONG_KEY,
    DirectAppleSavedQueueAdapter,
    DirectAppleSavedQueueUnavailableError,
)

TRACK_ONE = {
    "catalogId": "1452806384",
    "url": ("https://music.apple.com/ch/album/kiss-me-kiss-me-kiss-me/1452806377?i=1452806384"),
    "title": "Just Like Heaven",
    "artist": "The Cure",
    "album": "Kiss Me, Kiss Me, Kiss Me",
    "durationMs": 212000,
}
TRACK_TWO = {
    "catalogId": "1443065566",
    "url": ("https://music.apple.com/ch/album/the-colour-of-spring/1443065310?i=1443065566"),
    "title": "Life's What You Make It",
    "artist": "Talk Talk",
    "album": "The Colour of Spring",
    "durationMs": 268000,
}


class Result(list):
    def __init__(self, items=(), *, total_matches=None, update_id=1):
        super().__init__(items)
        self.total_matches = len(self) if total_matches is None else total_matches
        self.update_id = update_id


def apple_item(track, *, item_id=None):
    catalog_id = track["catalogId"]
    return SimpleNamespace(
        item_id=item_id or f"10032020song%3a{catalog_id}",
        title=track["title"],
        creator=track["artist"],
        artist=track["artist"],
        album=track["album"],
        resources=[SimpleNamespace(uri=f"x-sonos-http:song%3a{catalog_id}.mp4")],
    )


def physical_sq49_item():
    """Sanitized SQ:49 read-back shape with synthetic non-secret provider values."""

    return SimpleNamespace(
        item_id=(
            "SQ:49/x-sonosapi-hls-static%3asong%253a1452806384"
            "%3fsid%3d204%26flags%3d1234%26sn%3d42:"
            "AJust%20Like%20Heaven,The%20Cure,"
            "Kiss%20Me%20Kiss%20Me%20Kiss%20Me%20(Deluxe%20Edition)"
        ),
        title="Just Like Heaven",
        creator="The Cure",
        artist="",
        album="Kiss Me Kiss Me Kiss Me (Deluxe Edition)",
        desc="",
        resources=[
            SimpleNamespace(
                uri=("x-sonosapi-hls-static:song%3a1452806384?sid=204&flags=1234&sn=42"),
                protocol_info=APPLE_SAVED_RESOURCE_PROTOCOL_INFO,
            )
        ],
    )


class FakeTransport:
    def __init__(self, owner):
        self.owner = owner

    def AddURIToSavedQueue(self, args):
        self.owner.saved_queue_actions.append(list(args))
        if self.owner.transport_failure is not None:
            raise self.owner.transport_failure
        return {}


class FakeMusicLibrary:
    def __init__(self, owner):
        self.owner = owner

    def browse(self, *, ml_item, start=0, max_items=100, full_album_art_uri=False):
        assert start == 0
        assert full_album_art_uri is False
        self.owner.browse_calls += 1
        playlist_id = ml_item.item_id
        if playlist_id not in self.owner.playlist_tracks:
            raise ValueError("private missing playlist")
        items = copy.deepcopy(self.owner.playlist_tracks[playlist_id])
        if items and self.owner.stale_reads_remaining:
            self.owner.stale_reads_remaining -= 1
            items = items[:-1]
        corruption = self.owner.corruption
        if items and (
            corruption
            and (
                self.owner.corrupt_on_browse is None
                or self.owner.browse_calls >= self.owner.corrupt_on_browse
            )
        ):
            if corruption == "absent":
                items = items[:-1]
            elif corruption == "wrong_count":
                return Result(items[:max_items], total_matches=len(items) + 1)
            elif corruption == "wrong_order":
                items.reverse()
            elif corruption == "wrong_identity":
                items[-1].item_id = "10032020song%3a999999"
                items[-1].resources[0].uri = "x-sonos-http:song%3a999999.mp4"
            elif corruption == "metadata":
                items[-1].title = "Substituted recording"
            elif corruption == "missing_metadata":
                items[-1].album = ""
        return Result(items[:max_items], total_matches=len(items), update_id=self.owner.update_id)


class FakeSpeaker:
    forbidden_method_names = (
        "get_queue",
        "clear_queue",
        "add_to_queue",
        "add_multiple_to_queue",
        "play_from_queue",
        "seek",
        "play",
        "pause",
        "stop",
        "join",
        "unjoin",
    )

    def __init__(self):
        self.uid = "R1"
        self.household_id = "Sonos_HH1"
        self.group = SimpleNamespace(coordinator=self)
        self.playlists = {}
        self.playlist_tracks = {}
        self.next_playlist = 1
        self.update_id = 1
        self.avTransport = FakeTransport(self)
        self.music_library = FakeMusicLibrary(self)
        self.saved_queue_actions = []
        self.transport_failure = None
        self.create_calls = []
        self.add_calls = []
        self.remove_calls = []
        self.browse_calls = 0
        self.fail_create = False
        self.partial_create_failure = False
        self.create_return_id = ""
        self.get_by_attr_failures = 0
        self.fail_add_position = None
        self.add_failure = RuntimeError("private direct-add failure")
        self.drop_add_position = None
        self.stop_after_add = None
        self.fail_remove = False
        self.stale_after_add_position = None
        self.stale_reads_remaining = 0
        self.corruption = ""
        self.corrupt_on_browse = None
        self.unrelated_race_position = None
        self.forbidden_calls = []

        for method_name in self.forbidden_method_names:
            setattr(self, method_name, self._forbidden(method_name))

    @property
    def volume(self):
        raise AssertionError("save-only must not inspect volume")

    @property
    def mute(self):
        raise AssertionError("save-only must not inspect mute")

    def _forbidden(self, name):
        def call(*_args, **_kwargs):
            self.forbidden_calls.append(name)
            raise AssertionError(f"save-only called forbidden method {name}")

        return call

    def get_sonos_playlists(self, *, max_items=100):
        items = list(self.playlists.values())
        return Result(items[:max_items], total_matches=len(items))

    def create_sonos_playlist(self, title):
        self.create_calls.append(title)
        if self.fail_create:
            raise RuntimeError("private create failure at an address")
        playlist_id = self.create_return_id or f"SQ:{self.next_playlist}"
        self.next_playlist += 1
        if playlist_id not in self.playlists:
            playlist = SimpleNamespace(item_id=playlist_id, title=title)
            self.playlists[playlist_id] = playlist
            self.playlist_tracks[playlist_id] = []
        if self.partial_create_failure:
            raise RuntimeError("private create response failure")
        return self.playlists[playlist_id]

    def get_sonos_playlist_by_attr(self, attr_name, value):
        if self.get_by_attr_failures:
            self.get_by_attr_failures -= 1
            raise ValueError("private delayed playlist visibility")
        for playlist in self.playlists.values():
            if getattr(playlist, attr_name) == value:
                return playlist
        raise ValueError("private missing playlist")

    def remove_sonos_playlist(self, playlist):
        self.remove_calls.append(playlist.item_id)
        if self.fail_remove:
            raise RuntimeError("private cleanup failure at an address")
        self.playlists.pop(playlist.item_id, None)
        self.playlist_tracks.pop(playlist.item_id, None)
        return True


class FakeDirectAdapter:
    def __init__(self, speaker):
        self.speaker = speaker

    def add_track(self, playlist, track):
        position = len(self.speaker.add_calls) + 1
        self.speaker.add_calls.append(track["catalogId"])
        if self.speaker.fail_add_position == position:
            raise self.speaker.add_failure
        if self.speaker.drop_add_position != position:
            self.speaker.playlist_tracks[playlist.item_id].append(apple_item(track))
            self.speaker.update_id += 1
        if self.speaker.unrelated_race_position == position:
            unrelated = SimpleNamespace(item_id="SQ:99", title="Concurrent unrelated")
            self.speaker.playlists[unrelated.item_id] = unrelated
            self.speaker.playlist_tracks[unrelated.item_id] = [apple_item(TRACK_ONE)]
        if self.speaker.stale_after_add_position == position:
            self.speaker.stale_reads_remaining = 1


def add_existing_playlist(speaker, playlist_id="SQ:50", title="Existing"):
    playlist = SimpleNamespace(item_id=playlist_id, title=title)
    speaker.playlists[playlist_id] = playlist
    speaker.playlist_tracks[playlist_id] = [apple_item(TRACK_TWO)]
    return playlist


def tracks(count):
    values = []
    for offset in range(count):
        catalog_id = str(3_000_000_000 + offset)
        values.append(
            {
                "catalogId": catalog_id,
                "url": f"https://music.apple.com/ch/album/reviewed/999?i={catalog_id}",
                "title": f"Reviewed song {offset + 1}",
                "artist": f"Reviewed artist {offset + 1}",
                "album": f"Reviewed album {offset + 1}",
                "durationMs": 180000 + offset,
            }
        )
    return values


def plan_for(speaker, *, name="AI Friday", planned_tracks=None):
    return {
        "operation": "playlists.apple.create",
        "roomUid": speaker.uid,
        "playlistName": name,
        "mode": "save-only",
        "allowDuplicates": False,
        "tracks": copy.deepcopy(planned_tracks or [TRACK_ONE, TRACK_TWO]),
        "targetState": inspect_apple_playlist_target(speaker, name),
        "planFingerprint": "test-only",
    }


def execute(speaker, plan, **kwargs):
    return create_preflighted_apple_playlist(
        speaker,
        plan,
        adapter_factory=FakeDirectAdapter,
        sleeper=lambda _delay: None,
        **kwargs,
    )


def test_direct_adapter_matches_pinned_soco_0312_and_escapes_reviewed_xml():
    speaker = FakeSpeaker()
    playlist = add_existing_playlist(speaker, "SQ:7", "Adapter target")
    track = copy.deepcopy(TRACK_ONE)
    track.update(
        {
            "title": "Heaven & <Earth>",
            "artist": 'The "Cure" & Friends',
            "album": "Kiss > Me",
        }
    )

    DirectAppleSavedQueueAdapter(speaker).add_track(playlist, track)

    assert soco.__version__ == "0.31.2"
    assert len(speaker.saved_queue_actions) == 1
    action = dict(speaker.saved_queue_actions[0])
    assert action["ObjectID"] == "SQ:7"
    assert action["EnqueuedURI"] == "song%3a1452806384"
    assert action["AddAtIndex"] == APPEND_INDEX
    parsed = from_didl_string(action["EnqueuedURIMetaData"])
    assert len(parsed) == 1
    item = parsed[0]
    assert item.item_id == f"{APPLE_SONG_KEY}song%3a1452806384"
    assert item.item_class == APPLE_SONG_CLASS
    assert item.title == track["title"]
    assert item.creator == track["artist"]
    assert item.artist == track["artist"]
    assert item.album == track["album"]
    assert item.desc == f"SA_RINCON{APPLE_SERVICE_NUMBER}_X_#Svc{APPLE_SERVICE_NUMBER}-0-Token"
    assert "<Earth>" not in action["EnqueuedURIMetaData"]
    assert "&lt;Earth&gt;" in action["EnqueuedURIMetaData"]
    assert speaker.forbidden_calls == []


def test_direct_adapter_fails_closed_on_soco_or_apple_contract_drift(monkeypatch):
    speaker = FakeSpeaker()
    monkeypatch.setattr(soco, "__version__", "0.32.0")
    with pytest.raises(DirectAppleSavedQueueUnavailableError, match="pinned SoCo"):
        DirectAppleSavedQueueAdapter(speaker)

    monkeypatch.setattr(soco, "__version__", "0.31.2")
    monkeypatch.setattr(
        "sonarchy_backend.infrastructure.apple_saved_queue.AppleMusicShare.service_number",
        lambda _self: 999,
    )
    with pytest.raises(DirectAppleSavedQueueUnavailableError, match="envelope changed"):
        DirectAppleSavedQueueAdapter(speaker)


@pytest.mark.parametrize(
    "change",
    (
        {"catalogId": "999"},
        {"url": "https://example.test/song/1452806384"},
        {"title": "unsafe\nxml"},
        {"durationMs": 0},
        {"provider": "another"},
    ),
)
def test_direct_adapter_rejects_unreviewed_or_generic_inputs(change):
    speaker = FakeSpeaker()
    playlist = add_existing_playlist(speaker, "SQ:7", "Adapter target")
    track = copy.deepcopy(TRACK_ONE)
    track.update(change)
    with pytest.raises(ValueError):
        DirectAppleSavedQueueAdapter(speaker).add_track(playlist, track)
    assert speaker.saved_queue_actions == []


def test_song_identity_requires_anchored_apple_evidence():
    assert apple_song_identity_from_item(apple_item(TRACK_ONE)) == "1452806384"
    assert (
        apple_song_identity_from_item(
            SimpleNamespace(
                item_id="song:1452806384",
                resources=[],
            )
        )
        == "1452806384"
    )
    ambiguous = apple_item(TRACK_ONE, item_id="song:999")
    assert apple_song_identity_from_item(ambiguous) == ""
    substring = SimpleNamespace(
        item_id="prefix10032020song%3a1452806384",
        resources=[SimpleNamespace(uri="https://invalid/song:1452806384")],
    )
    assert apple_song_identity_from_item(substring) == ""


def test_physical_sq49_shape_has_strong_identity_and_verified_metadata():
    item = physical_sq49_item()

    assert apple_song_identity_from_item(item) == "1452806384"
    assert verify_apple_items([item], [TRACK_ONE], container="saved Sonos Playlist") == [
        {
            "position": 1,
            "catalogId": "1452806384",
            "canonicalIdentity": "song:1452806384",
            "title": "Just Like Heaven",
            "artist": "The Cure",
            "album": "Kiss Me, Kiss Me, Kiss Me",
        }
    ]


def test_physical_resource_identity_fails_closed_on_soco_version_drift(monkeypatch):
    item = physical_sq49_item()
    monkeypatch.setattr(soco, "__version__", "0.32.0")

    assert apple_song_identity_from_item(item) == ""


@pytest.mark.parametrize(
    ("uri", "protocol_info"),
    (
        (
            "x-sonosapi-hls-static:song%3a999999?sid=204&flags=1234&sn=42",
            APPLE_SAVED_RESOURCE_PROTOCOL_INFO,
        ),
        (
            "x-sonosapi-hls-static:song%3a999999?sid=204&flags=1234&sn=42&reviewed=1452806384",
            APPLE_SAVED_RESOURCE_PROTOCOL_INFO,
        ),
        (
            "prefix-x-sonosapi-hls-static:song%3a1452806384?sid=204&flags=1234&sn=42",
            APPLE_SAVED_RESOURCE_PROTOCOL_INFO,
        ),
        (
            "x-sonosapi-hls-static:song%3a1452806384?sid=2311&flags=1234&sn=42",
            APPLE_SAVED_RESOURCE_PROTOCOL_INFO,
        ),
        (
            "x-sonosapi-hls-static:song%3a1452806384?sid=204&flags=1234&sn=42",
            "sonos.com-http:*:audio/mpeg:*",
        ),
    ),
)
def test_physical_resource_shape_rejects_wrong_or_untrusted_identity(uri, protocol_info):
    item = physical_sq49_item()
    item.item_id = "SQ:49/sanitized-noncanonical-item"
    item.resources[0].uri = uri
    item.resources[0].protocol_info = protocol_info

    assert apple_song_identity_from_item(item) != "1452806384"
    with pytest.raises(ValueError, match="identity"):
        verify_apple_items([item], [TRACK_ONE], container="saved Sonos Playlist")


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("title", "Just Like Heaven (Live)"),
        ("creator", "Another Artist"),
        ("album", "Disintegration"),
        ("album", "Kiss Me Kiss Me Kiss Me (Live Edition)"),
    ),
)
def test_physical_resource_shape_still_requires_reviewed_metadata(field, value):
    item = physical_sq49_item()
    setattr(item, field, value)

    with pytest.raises(ValueError, match="metadata"):
        verify_apple_items([item], [TRACK_ONE], container="saved Sonos Playlist")


def test_direct_create_retains_verified_physical_shape_without_cleanup_or_queue_calls():
    speaker = FakeSpeaker()

    class PhysicalReadbackAdapter(FakeDirectAdapter):
        def add_track(self, playlist, track):
            self.speaker.add_calls.append(track["catalogId"])
            self.speaker.playlist_tracks[playlist.item_id].append(physical_sq49_item())

    result = create_preflighted_apple_playlist(
        speaker,
        plan_for(speaker, planned_tracks=[TRACK_ONE]),
        adapter_factory=PhysicalReadbackAdapter,
        sleeper=lambda _delay: None,
    )

    assert result["playlist"]["items"][0]["canonicalIdentity"] == "song:1452806384"
    assert result["queueMutation"] is False
    assert result["playbackMutation"] is False
    assert speaker.remove_calls == []
    assert speaker.forbidden_calls == []


def test_verify_items_requires_exact_order_identity_and_complete_metadata():
    items = [apple_item(TRACK_ONE), apple_item(TRACK_TWO)]
    evidence = verify_apple_items(items, [TRACK_ONE, TRACK_TWO], container="playlist")
    assert [item["canonicalIdentity"] for item in evidence] == [
        "song:1452806384",
        "song:1443065566",
    ]
    with pytest.raises(ValueError, match="identity"):
        verify_apple_items(items, [TRACK_TWO, TRACK_ONE], container="playlist")
    items[0].album = ""
    with pytest.raises(ValueError, match="complete reviewed metadata"):
        verify_apple_items(items, [TRACK_ONE, TRACK_TWO], container="playlist")


def test_preflight_reads_only_anchor_inventory_and_direct_capability():
    speaker = FakeSpeaker()
    add_existing_playlist(speaker)
    state = inspect_apple_playlist_target(speaker, "AI Friday")

    assert state["room"]["uid"] == "R1"
    assert state["room"]["coordinatorUid"] == "R1"
    assert state["room"]["householdFingerprint"].startswith("sha256:")
    assert state["observedState"]["playlistCount"] == 1
    assert state["observedState"]["playlistInventoryFingerprint"].startswith("sha256:")
    observed = state["observedState"]
    for absent in ("queue", "transport", "volume", "mute", "mediaFingerprint"):
        assert absent not in observed
    assert speaker.forbidden_calls == []


def test_direct_create_one_song_preserves_all_non_playlist_state():
    speaker = FakeSpeaker()
    existing = add_existing_playlist(speaker)
    existing_tracks = copy.deepcopy(speaker.playlist_tracks[existing.item_id])
    result = execute(speaker, plan_for(speaker, planned_tracks=[TRACK_ONE]))

    assert result["ok"] is True
    assert result["playlist"]["id"] == "SQ:1"
    assert result["playlist"]["name"] == "AI Friday"
    assert result["playlist"]["itemCount"] == 1
    assert result["playlist"]["items"][0]["canonicalIdentity"] == "song:1452806384"
    assert result["queueMutation"] is False
    assert result["playbackMutation"] is False
    assert result["verification"] == {
        "authoritativeReopen": True,
        "preExistingPlaylistsUnchanged": True,
    }
    assert speaker.playlist_tracks[existing.item_id] == existing_tracks
    assert speaker.forbidden_calls == []


def test_direct_create_25_songs_preserves_exact_order_and_fits_protocol():
    speaker = FakeSpeaker()
    planned = tracks(25)
    result = execute(speaker, plan_for(speaker, name="AI 25", planned_tracks=planned))

    assert speaker.add_calls == [track["catalogId"] for track in planned]
    assert [item["canonicalIdentity"] for item in result["playlist"]["items"]] == [
        f"song:{track['catalogId']}" for track in planned
    ]
    envelope = result_payload(
        "x" * MAX_PROTOCOL_REQUEST_ID_BYTES,
        revision=7,
        value=result,
    )
    assert len(protocol_line(envelope).encode("utf-8")) <= MAX_PROTOCOL_LINE_BYTES
    serialized = json.dumps(result)
    for forbidden in (
        "music.apple.com",
        "x-sonos",
        "DIDL",
        "SOAP",
        "CurrentURI",
        "SA_RINCON",
        "Token",
    ):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    ("track_count", "failed_position"),
    ((1, 1), (2, 2), (5, 3), (5, 5)),
)
def test_code_800_track_failure_stops_without_retry_or_substitution_and_cleans_exact_id(
    track_count,
    failed_position,
):
    speaker = FakeSpeaker()
    planned = tracks(track_count)
    plan = plan_for(speaker, planned_tracks=planned)
    speaker.fail_add_position = failed_position
    speaker.add_failure = SoCoUPnPException(
        "private address token and service detail",
        "800",
        b"<private/>",
        "private description",
    )

    with pytest.raises(PlaylistTransactionError) as error:
        execute(speaker, plan)

    details = error.value.details
    assert details["phase"] == "playlist_creation"
    assert details["playlistConstructionStep"] == "add_track"
    assert details["failedTrackPosition"] == failed_position
    assert details["failedCanonicalIdentity"] == (
        f"song:{planned[failed_position - 1]['catalogId']}"
    )
    assert details["sonosErrorCode"] == "800"
    assert details["partialPlaylistId"] == "SQ:1"
    assert details["playlistRemoved"] is True
    assert details["playlistCleanupRequired"] is False
    assert details["queueUnchanged"] is True
    assert details["playbackUnchanged"] is True
    assert speaker.add_calls == [track["catalogId"] for track in planned[:failed_position]]
    assert speaker.remove_calls == ["SQ:1"]
    assert speaker.playlists == {}
    assert speaker.forbidden_calls == []
    serialized = json.dumps(details)
    for forbidden in ("private", "address", "token", "service", "<private"):
        assert forbidden not in serialized


def test_non_upnp_track_failure_does_not_fabricate_a_sonos_code():
    speaker = FakeSpeaker()
    plan = plan_for(speaker, planned_tracks=[TRACK_ONE])
    speaker.fail_add_position = 1
    speaker.add_failure = RuntimeError("UPnP 800 from private address")

    with pytest.raises(PlaylistTransactionError) as error:
        execute(speaker, plan)

    assert "sonosErrorCode" not in error.value.details
    assert error.value.details["playlistRemoved"] is True


def test_untrusted_upnp_error_code_is_not_returned():
    speaker = FakeSpeaker()
    plan = plan_for(speaker, planned_tracks=[TRACK_ONE])
    speaker.fail_add_position = 1
    speaker.add_failure = SoCoUPnPException("private", "800<xml>", b"<private/>")
    with pytest.raises(PlaylistTransactionError) as error:
        execute(speaker, plan)
    assert "sonosErrorCode" not in error.value.details


def test_exact_partial_cleanup_failure_returns_only_attributable_id_and_no_fallback():
    speaker = FakeSpeaker()
    unrelated = add_existing_playlist(speaker, "SQ:50", "Unrelated")
    unrelated_tracks = copy.deepcopy(speaker.playlist_tracks[unrelated.item_id])
    plan = plan_for(speaker, planned_tracks=[TRACK_ONE])
    speaker.fail_add_position = 1
    speaker.fail_remove = True

    with pytest.raises(PlaylistTransactionError) as error:
        execute(speaker, plan)

    details = error.value.details
    assert details["playlistConstructionStep"] == "cleanup"
    assert details["partialPlaylistId"] == "SQ:1"
    assert details["playlistRemoved"] is False
    assert details["playlistCleanupRequired"] is True
    assert details["preExistingPlaylistsUnchanged"] is True
    assert speaker.remove_calls == ["SQ:1"]
    assert set(speaker.playlists) == {"SQ:50", "SQ:1"}
    assert speaker.playlist_tracks[unrelated.item_id] == unrelated_tracks


@pytest.mark.parametrize(
    "corruption",
    ("absent", "wrong_count", "wrong_order", "wrong_identity", "metadata", "missing_metadata"),
)
def test_authoritative_verification_failure_exhausts_bounded_retries_and_cleans(corruption):
    speaker = FakeSpeaker()
    plan = plan_for(speaker)
    speaker.corruption = corruption

    with pytest.raises(PlaylistTransactionError) as error:
        execute(speaker, plan)

    details = error.value.details
    assert details["playlistConstructionStep"] == "verify_track"
    expected_position = 2 if corruption == "wrong_order" else 1
    assert details["failedTrackPosition"] == expected_position
    assert details["failedCanonicalIdentity"] == (
        "song:1443065566" if expected_position == 2 else "song:1452806384"
    )
    assert details["playlistRemoved"] is True
    assert speaker.add_calls == (
        ["1452806384", "1443065566"] if corruption == "wrong_order" else ["1452806384"]
    )
    expected_browse_calls = 5 if corruption == "wrong_order" else 4
    assert speaker.browse_calls == expected_browse_calls
    assert speaker.playlists == {}


def test_delayed_saved_playlist_visibility_uses_small_bounded_retry_and_succeeds():
    speaker = FakeSpeaker()
    speaker.stale_after_add_position = 1
    result = execute(speaker, plan_for(speaker, planned_tracks=[TRACK_ONE]))

    assert result["playlist"]["itemCount"] == 1
    assert speaker.add_calls == ["1452806384"]
    assert speaker.browse_calls == 4  # empty, stale, converged, final


def test_saved_playlist_visibility_retry_exhaustion_fails_safely():
    speaker = FakeSpeaker()
    plan = plan_for(speaker, planned_tracks=[TRACK_ONE])
    speaker.stale_after_add_position = 1
    speaker.stale_reads_remaining = 0

    class NeverVisibleAdapter(FakeDirectAdapter):
        def add_track(self, playlist, track):
            super().add_track(playlist, track)
            self.speaker.stale_reads_remaining = 99

    with pytest.raises(PlaylistTransactionError) as error:
        create_preflighted_apple_playlist(
            speaker,
            plan,
            adapter_factory=NeverVisibleAdapter,
            sleeper=lambda _delay: None,
        )

    assert error.value.details["playlistConstructionStep"] == "verify_track"
    assert error.value.details["playlistRemoved"] is True
    assert speaker.add_calls == ["1452806384"]


def test_final_authoritative_reopen_detects_late_wrong_order_and_cleans():
    speaker = FakeSpeaker()
    plan = plan_for(speaker)
    speaker.corruption = "wrong_order"
    speaker.corrupt_on_browse = 4  # empty + track 1 + track 2 + final

    with pytest.raises(PlaylistTransactionError) as error:
        execute(speaker, plan)

    assert error.value.details["playlistConstructionStep"] == "verify_playlist"
    assert "failedTrackPosition" not in error.value.details
    assert speaker.remove_calls == ["SQ:1"]


def test_create_failure_without_returned_id_never_guesses_cleanup_ownership():
    speaker = FakeSpeaker()
    plan = plan_for(speaker, planned_tracks=[TRACK_ONE])
    speaker.fail_create = True

    with pytest.raises(PlaylistTransactionError) as error:
        execute(speaker, plan)

    details = error.value.details
    assert details["playlistConstructionStep"] == "create"
    assert "partialPlaylistId" not in details
    assert details["playlistRemoved"] is False
    assert details["playlistCleanupRequired"] is True
    assert speaker.remove_calls == []


def test_remote_partial_create_without_returned_id_is_detected_but_never_guessed():
    speaker = FakeSpeaker()
    plan = plan_for(speaker, planned_tracks=[TRACK_ONE])
    speaker.partial_create_failure = True

    with pytest.raises(PlaylistTransactionError) as error:
        execute(speaker, plan)

    details = error.value.details
    assert details["playlistConstructionStep"] == "create"
    assert "partialPlaylistId" not in details
    assert details["playlistRemoved"] is False
    assert details["playlistCleanupRequired"] is True
    assert details["preExistingPlaylistsUnchanged"] is False
    assert speaker.remove_calls == []
    assert set(speaker.playlists) == {"SQ:1"}


def test_create_returning_preexisting_id_is_never_cleanup_owned():
    speaker = FakeSpeaker()
    add_existing_playlist(speaker, "SQ:1", "Existing")
    plan = plan_for(speaker, planned_tracks=[TRACK_ONE])
    speaker.create_return_id = "SQ:1"

    with pytest.raises(PlaylistTransactionError) as error:
        execute(speaker, plan)

    assert "partialPlaylistId" not in error.value.details
    assert error.value.details["playlistRemoved"] is False
    assert speaker.remove_calls == []
    assert set(speaker.playlists) == {"SQ:1"}


def test_create_returned_new_id_is_cleanup_owned_before_first_reopen():
    speaker = FakeSpeaker()
    plan = plan_for(speaker, planned_tracks=[TRACK_ONE])
    speaker.get_by_attr_failures = 3

    with pytest.raises(PlaylistTransactionError) as error:
        execute(speaker, plan)

    details = error.value.details
    assert details["playlistConstructionStep"] == "create"
    assert details["partialPlaylistId"] == "SQ:1"
    assert details["playlistRemoved"] is True
    assert details["playlistCleanupRequired"] is False
    assert speaker.remove_calls == ["SQ:1"]
    assert speaker.playlists == {}


def test_concurrent_unrelated_playlist_is_never_deleted_or_title_matched():
    speaker = FakeSpeaker()
    plan = plan_for(speaker, planned_tracks=[TRACK_ONE])
    speaker.unrelated_race_position = 1

    with pytest.raises(PlaylistTransactionError) as error:
        execute(speaker, plan)

    assert error.value.details["playlistConstructionStep"] == "verify_playlist"
    assert error.value.details["partialPlaylistId"] == "SQ:1"
    assert error.value.details["preExistingPlaylistsUnchanged"] is False
    assert speaker.remove_calls == ["SQ:1"]
    assert set(speaker.playlists) == {"SQ:99"}


@pytest.mark.parametrize("change", ("inventory", "name", "room", "household", "coordinator"))
def test_freshness_change_rejects_before_playlist_mutation(change):
    speaker = FakeSpeaker()
    plan = plan_for(speaker)
    if change == "inventory":
        add_existing_playlist(speaker, "SQ:50", "External")
    elif change == "name":
        add_existing_playlist(speaker, "SQ:50", "AI Friday")
    elif change == "room":
        speaker.uid = "R2"
    elif change == "household":
        speaker.household_id = "Sonos_HH2"
    else:
        other = SimpleNamespace(
            uid="R2",
            household_id="Sonos_HH1",
            get_sonos_playlists=speaker.get_sonos_playlists,
        )
        speaker.group.coordinator = other

    with pytest.raises(PlanConflictError):
        execute(speaker, plan)

    assert speaker.create_calls == []
    assert speaker.remove_calls == []
    assert speaker.forbidden_calls == []


def test_name_collision_and_full_inventory_are_rejected_read_only():
    collision = FakeSpeaker()
    add_existing_playlist(collision, "SQ:50", "AI Friday")
    with pytest.raises(PlanConflictError) as error:
        inspect_apple_playlist_target(collision, "AI Friday")
    assert error.value.details == {"suggestedPlaylistName": "AI Friday (2)"}

    full = FakeSpeaker()
    for index in range(100):
        add_existing_playlist(full, f"SQ:{index + 1}", f"Existing {index + 1}")
    with pytest.raises(PlanConflictError, match="inventory is full"):
        inspect_apple_playlist_target(full, "AI Friday")
    assert full.create_calls == []


def test_invalid_anchor_inventory_and_capability_fail_closed_without_queue_calls():
    missing_household = FakeSpeaker()
    missing_household.household_id = ""
    with pytest.raises(PlanConflictError, match="household"):
        inspect_apple_playlist_target(missing_household, "AI Friday")

    malformed_inventory = FakeSpeaker()
    malformed_inventory.playlists["bad"] = SimpleNamespace(item_id="bad", title="Bad")
    with pytest.raises(PlanConflictError, match="inventory"):
        inspect_apple_playlist_target(malformed_inventory, "AI Friday")

    missing_capability = FakeSpeaker()
    missing_capability.avTransport.AddURIToSavedQueue = None
    with pytest.raises(PlanConflictError, match="direct Apple"):
        inspect_apple_playlist_target(missing_capability, "AI Friday")

    assert missing_household.forbidden_calls == []
    assert malformed_inventory.forbidden_calls == []
    assert missing_capability.forbidden_calls == []


def test_only_create_only_internal_plan_can_execute():
    speaker = FakeSpeaker()
    wrong_mode = plan_for(speaker)
    wrong_mode["mode"] = "save-and-play"
    with pytest.raises(PlanConflictError, match="create-only"):
        execute(speaker, wrong_mode)
    wrong_operation = plan_for(speaker)
    wrong_operation["operation"] = "generic.execute"
    with pytest.raises(PlanConflictError, match="create-only"):
        execute(speaker, wrong_operation)
    assert speaker.create_calls == []


def test_invalid_retry_policy_is_rejected_before_mutation():
    speaker = FakeSpeaker()
    plan = plan_for(speaker)
    with pytest.raises(ValueError, match="retry policy"):
        execute(speaker, plan, verification_attempts=4)
    assert speaker.create_calls == []
