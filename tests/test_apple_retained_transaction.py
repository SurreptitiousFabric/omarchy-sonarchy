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
    error_payload,
    protocol_line,
    result_payload,
)
from sonarchy_backend.domains.apple_retained_transaction import (
    apple_song_identity_from_item,
    create_retained_apple_playlist,
    inspect_retained_apple_playlist_target,
)
from sonarchy_backend.domains.errors import PlanConflictError, RetainedPlaylistTransactionError
from sonarchy_backend.infrastructure.apple_saved_queue import (
    APPEND_INDEX,
    APPLE_SERVICE_NUMBER,
    APPLE_SONG_CLASS,
    APPLE_SONG_KEY,
    DirectAppleSavedQueueAdapter,
    DirectAppleSavedQueueUnavailableError,
)

TRACK_ONE = {
    "catalogId": "1452806384",
    "url": "https://music.apple.com/ch/album/kiss-me-kiss-me-kiss-me/1452806377?i=1452806384",
    "title": "Just Like Heaven",
    "artist": "The Cure",
    "album": "Kiss Me, Kiss Me, Kiss Me",
    "durationMs": 212000,
}
TRACK_TWO = {
    "catalogId": "1443065566",
    "url": "https://music.apple.com/ch/album/the-colour-of-spring/1443065310?i=1443065566",
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
            raise ValueError("private missing playlist address")
        items = copy.deepcopy(self.owner.playlist_tracks[playlist_id])
        if items and self.owner.stale_reads_remaining:
            self.owner.stale_reads_remaining -= 1
            items = items[:-1]
        should_corrupt = (
            items
            and self.owner.corruption
            and len(self.owner.add_calls) >= self.owner.corrupt_after_add
        )
        if should_corrupt:
            if self.owner.corruption == "wrong_count":
                items.append(copy.deepcopy(items[-1]))
            elif self.owner.corruption == "wrong_order":
                items.reverse()
            elif self.owner.corruption == "wrong_identity":
                items[-1].item_id = "10032020song%3a999999"
                items[-1].resources[0].uri = "x-sonos-http:song%3a999999.mp4"
            elif self.owner.corruption == "metadata":
                items[-1].title = "Substituted recording"
            elif self.owner.corruption == "missing_metadata":
                items[-1].album = ""
        return Result(
            items[:max_items],
            total_matches=len(items),
            update_id=self.owner.update_id,
        )


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
        "next",
        "previous",
        "join",
        "unjoin",
        "remove_sonos_playlist",
        "remove_from_sonos_playlist",
        "move_in_sonos_playlist",
        "create_sonos_playlist_from_queue",
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
        self.browse_calls = 0
        self.fail_create = False
        self.partial_create_failure = False
        self.create_return_id = ""
        self.get_by_attr_failures = 0
        self.fail_add_position = None
        self.add_failure = RuntimeError("private direct-add failure at speaker address")
        self.drop_add_position = None
        self.stale_after_add_position = None
        self.stale_reads_remaining = 0
        self.corruption = ""
        self.corrupt_after_add = 1
        self.unrelated_race_position = None
        self.forbidden_calls = []
        for method_name in self.forbidden_method_names:
            setattr(self, method_name, self._forbidden(method_name))

    @property
    def volume(self):
        raise AssertionError("retained create must not inspect volume")

    @property
    def mute(self):
        raise AssertionError("retained create must not inspect mute")

    def _forbidden(self, name):
        def call(*_args, **_kwargs):
            self.forbidden_calls.append(name)
            raise AssertionError(f"retained create called forbidden method {name}")

        return call

    def get_sonos_playlists(self, *, max_items=100):
        items = list(self.playlists.values())
        return Result(items[:max_items], total_matches=len(items))

    def create_sonos_playlist(self, title):
        self.create_calls.append(title)
        if self.fail_create:
            raise RuntimeError("private create failure at speaker address")
        playlist_id = self.create_return_id or f"SQ:{self.next_playlist}"
        self.next_playlist += 1
        if playlist_id not in self.playlists:
            playlist = SimpleNamespace(item_id=playlist_id, title=title)
            self.playlists[playlist_id] = playlist
            self.playlist_tracks[playlist_id] = []
        if self.partial_create_failure:
            raise RuntimeError("private create response failure with token")
        return self.playlists[playlist_id]

    def get_sonos_playlist_by_attr(self, attr_name, value):
        if self.get_by_attr_failures:
            self.get_by_attr_failures -= 1
            raise ValueError("private delayed playlist visibility")
        for playlist in self.playlists.values():
            if getattr(playlist, attr_name) == value:
                return playlist
        raise ValueError("private missing playlist")


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


def generated_tracks(count):
    tracks = []
    for offset in range(count):
        catalog_id = str(3_000_000_000 + offset)
        tracks.append(
            {
                "catalogId": catalog_id,
                "url": f"https://music.apple.com/ch/album/reviewed/999?i={catalog_id}",
                "title": f"Reviewed song {offset + 1}",
                "artist": f"Reviewed artist {offset + 1}",
                "album": f"Reviewed album {offset + 1}",
                "durationMs": 180000 + offset,
            }
        )
    return tracks


def plan_for(speaker, *, name="Inspection Friday", planned_tracks=None):
    return {
        "operation": "playlists.apple.retained.create",
        "roomUid": speaker.uid,
        "playlistName": name,
        "retentionMode": "manual-inspection",
        "allowDuplicates": False,
        "tracks": copy.deepcopy(planned_tracks or [TRACK_ONE, TRACK_TWO]),
        "targetState": inspect_retained_apple_playlist_target(
            speaker,
            name,
            adapter_factory=FakeDirectAdapter,
        ),
        "planFingerprint": "test-only",
    }


def execute(speaker, plan, **kwargs):
    return create_retained_apple_playlist(
        speaker,
        plan,
        adapter_factory=FakeDirectAdapter,
        sleeper=lambda _delay: None,
        **kwargs,
    )


def test_direct_adapter_matches_pinned_soco_and_escapes_reviewed_xml():
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
    assert item.album == track["album"]
    assert item.desc == f"SA_RINCON{APPLE_SERVICE_NUMBER}_X_#Svc{APPLE_SERVICE_NUMBER}-0-Token"
    assert "&lt;Earth&gt;" in action["EnqueuedURIMetaData"]
    assert speaker.forbidden_calls == []


def test_direct_adapter_fails_closed_on_version_drift_and_generic_input(monkeypatch):
    speaker = FakeSpeaker()
    monkeypatch.setattr(soco, "__version__", "0.32.0")
    with pytest.raises(DirectAppleSavedQueueUnavailableError, match="pinned SoCo"):
        DirectAppleSavedQueueAdapter(speaker)
    monkeypatch.setattr(soco, "__version__", "0.31.2")
    playlist = add_existing_playlist(speaker, "SQ:7", "Adapter target")
    unreviewed = copy.deepcopy(TRACK_ONE) | {"provider": "generic"}
    with pytest.raises(ValueError, match="reviewed track shape"):
        DirectAppleSavedQueueAdapter(speaker).add_track(playlist, unreviewed)
    assert speaker.saved_queue_actions == []


def test_identity_requires_anchored_apple_evidence():
    assert apple_song_identity_from_item(apple_item(TRACK_ONE)) == "1452806384"
    ambiguous = apple_item(TRACK_ONE, item_id="song:999")
    assert apple_song_identity_from_item(ambiguous) == ""
    substring = SimpleNamespace(
        item_id="prefix10032020song%3a1452806384",
        resources=[SimpleNamespace(uri="https://invalid/song:1452806384")],
    )
    assert apple_song_identity_from_item(substring) == ""


def test_preflight_reads_only_anchor_inventory_and_retained_capability():
    speaker = FakeSpeaker()
    add_existing_playlist(speaker)
    state = inspect_retained_apple_playlist_target(
        speaker,
        "Inspection Friday",
        adapter_factory=FakeDirectAdapter,
    )
    assert state["room"]["uid"] == "R1"
    assert state["room"]["coordinatorUid"] == "R1"
    assert state["room"]["householdFingerprint"].startswith("sha256:")
    assert state["observedState"]["playlistCount"] == 1
    assert "direct-apple-saved-queue-retained" in state["observedState"]["capabilities"]
    for absent in ("queue", "transport", "volume", "mute", "mediaFingerprint"):
        assert absent not in state["observedState"]
    assert speaker.forbidden_calls == []


def test_retained_create_one_song_preserves_existing_state_and_reports_evidence():
    speaker = FakeSpeaker()
    existing = add_existing_playlist(speaker)
    original_tracks = copy.deepcopy(speaker.playlist_tracks[existing.item_id])
    result = execute(speaker, plan_for(speaker, planned_tracks=[TRACK_ONE]))

    assert result["playlist"]["id"] == "SQ:1"
    assert result["playlist"]["itemCount"] == 1
    assert result["playlist"]["items"][0]["canonicalIdentity"] == "song:1452806384"
    assert result["trackResults"] == [
        {
            "position": 1,
            "canonicalIdentity": "song:1452806384",
            "addCallReturned": True,
            "verificationStatus": "complete",
        }
    ]
    assert result["playlistRetained"] is True
    assert result["manualInspectionRequired"] is False
    assert result["queueMutation"] is False
    assert result["playbackMutation"] is False
    assert speaker.playlist_tracks[existing.item_id] == original_tracks
    assert speaker.forbidden_calls == []


def test_retained_create_25_songs_preserves_order_and_protocol_bound():
    speaker = FakeSpeaker()
    planned = generated_tracks(25)
    result = execute(
        speaker,
        plan_for(speaker, name="Inspection 25", planned_tracks=planned),
    )
    assert speaker.add_calls == [track["catalogId"] for track in planned]
    assert [item["canonicalIdentity"] for item in result["playlist"]["items"]] == [
        f"song:{track['catalogId']}" for track in planned
    ]
    envelope = result_payload(
        "x" * MAX_PROTOCOL_REQUEST_ID_BYTES,
        revision=999,
        value=result,
    )
    assert len(protocol_line(envelope).encode("utf-8")) <= MAX_PROTOCOL_LINE_BYTES
    serialized = json.dumps(result)
    for forbidden in ("music.apple.com", "x-sonos", "DIDL", "SOAP", "SA_RINCON", "Token"):
        assert forbidden not in serialized
    assert speaker.forbidden_calls == []


@pytest.mark.parametrize(
    ("track_count", "failed_position"),
    ((1, 1), (3, 2), (5, 3), (5, 5)),
)
def test_code_800_failure_retains_exact_partial_and_successful_prefix(
    track_count,
    failed_position,
):
    speaker = FakeSpeaker()
    planned = generated_tracks(track_count)
    plan = plan_for(speaker, planned_tracks=planned)
    speaker.fail_add_position = failed_position
    speaker.add_failure = SoCoUPnPException(
        "private address token and service detail",
        "800",
        b"<private/>",
        "private description",
    )

    with pytest.raises(RetainedPlaylistTransactionError) as error:
        execute(speaker, plan)

    details = error.value.details
    assert details["phase"] == "retained_playlist_creation"
    assert details["playlistConstructionStep"] == "add_track"
    assert details["failedTrackPosition"] == failed_position
    assert details["failedCanonicalIdentity"] == (
        f"song:{planned[failed_position - 1]['catalogId']}"
    )
    assert details["sonosErrorCode"] == "800"
    assert details["partialPlaylistId"] == "SQ:1"
    assert details["playlistRetained"] is True
    assert details["manualInspectionRequired"] is True
    assert details["observedItemCount"] == failed_position - 1
    assert details["trackResults"][failed_position - 1]["addCallReturned"] is False
    assert details["trackResults"][failed_position - 1]["verificationStatus"] == "add_rejected"
    assert speaker.add_calls == [track["catalogId"] for track in planned[:failed_position]]
    assert len(speaker.playlist_tracks["SQ:1"]) == failed_position - 1
    assert speaker.forbidden_calls == []
    serialized = json.dumps(details)
    for forbidden in ("private", "address", "token", "service", "<private"):
        assert forbidden not in serialized


def test_non_upnp_failure_fabricates_no_error_code_and_still_retains_playlist():
    speaker = FakeSpeaker()
    plan = plan_for(speaker, planned_tracks=[TRACK_ONE])
    speaker.fail_add_position = 1
    speaker.add_failure = RuntimeError("UPnP 800 at private speaker address")
    with pytest.raises(RetainedPlaylistTransactionError) as error:
        execute(speaker, plan)
    assert "sonosErrorCode" not in error.value.details
    assert error.value.details["partialPlaylistId"] == "SQ:1"
    assert set(speaker.playlists) == {"SQ:1"}
    assert speaker.forbidden_calls == []


@pytest.mark.parametrize(
    ("corruption", "expected_status", "tracks", "configure"),
    (
        ("absent", "item_absent", [TRACK_ONE], "drop"),
        ("wrong_count", "wrong_count", [TRACK_ONE], "corrupt"),
        ("wrong_identity", "identity_mismatch", [TRACK_ONE], "corrupt"),
        ("metadata", "metadata_mismatch", [TRACK_ONE], "corrupt"),
        ("missing_metadata", "metadata_incomplete", [TRACK_ONE], "corrupt"),
        ("wrong_order", "wrong_order", [TRACK_ONE, TRACK_TWO], "after_two"),
    ),
)
def test_verification_failure_retains_add_result_for_manual_inspection(
    corruption,
    expected_status,
    tracks,
    configure,
):
    speaker = FakeSpeaker()
    plan = plan_for(speaker, planned_tracks=tracks)
    if configure == "drop":
        speaker.drop_add_position = 1
    else:
        speaker.corruption = corruption
        speaker.corrupt_after_add = 2 if configure == "after_two" else 1

    with pytest.raises(RetainedPlaylistTransactionError) as error:
        execute(speaker, plan)

    details = error.value.details
    failed_position = 2 if configure == "after_two" else 1
    assert details["playlistConstructionStep"] == "verify_track"
    assert details["verificationStatus"] == expected_status
    assert details["failedTrackPosition"] == failed_position
    assert details["addCallReturned"] is True
    assert details["playlistRetained"] is True
    assert details["partialPlaylistId"] == "SQ:1"
    assert set(speaker.playlists) == {"SQ:1"}
    assert speaker.forbidden_calls == []


def test_delayed_visibility_uses_bounded_read_retry_without_readding():
    speaker = FakeSpeaker()
    speaker.stale_after_add_position = 1
    result = execute(speaker, plan_for(speaker, planned_tracks=[TRACK_ONE]))
    assert result["verificationStatus"] == "complete"
    assert speaker.add_calls == ["1452806384"]
    assert speaker.browse_calls == 4
    assert speaker.forbidden_calls == []


def test_visibility_retry_exhaustion_retains_exact_playlist():
    speaker = FakeSpeaker()
    plan = plan_for(speaker, planned_tracks=[TRACK_ONE])

    class NeverVisibleAdapter(FakeDirectAdapter):
        def add_track(self, playlist, track):
            super().add_track(playlist, track)
            self.speaker.stale_reads_remaining = 99

    with pytest.raises(RetainedPlaylistTransactionError) as error:
        create_retained_apple_playlist(
            speaker,
            plan,
            adapter_factory=NeverVisibleAdapter,
            sleeper=lambda _delay: None,
        )
    assert error.value.details["verificationStatus"] == "item_absent"
    assert error.value.details["partialPlaylistId"] == "SQ:1"
    assert speaker.add_calls == ["1452806384"]
    assert set(speaker.playlists) == {"SQ:1"}


def test_create_ambiguity_never_guesses_an_id_or_deletes_any_playlist():
    speaker = FakeSpeaker()
    plan = plan_for(speaker, planned_tracks=[TRACK_ONE])
    speaker.partial_create_failure = True
    with pytest.raises(RetainedPlaylistTransactionError) as error:
        execute(speaker, plan)
    details = error.value.details
    assert details["createCallReturned"] is False
    assert "partialPlaylistId" not in details
    assert details["manualInspectionRequired"] is True
    assert set(speaker.playlists) == {"SQ:1"}
    assert speaker.forbidden_calls == []


def test_create_returned_exact_id_is_retained_even_when_reopen_is_inconclusive():
    speaker = FakeSpeaker()
    plan = plan_for(speaker, planned_tracks=[TRACK_ONE])
    speaker.get_by_attr_failures = 3
    with pytest.raises(RetainedPlaylistTransactionError) as error:
        execute(speaker, plan)
    details = error.value.details
    assert details["playlistConstructionStep"] == "verify_empty"
    assert details["partialPlaylistId"] == "SQ:1"
    assert details["playlistRetained"] is True
    assert details["verificationStatus"] == "reopen_failed"
    assert set(speaker.playlists) == {"SQ:1"}
    assert speaker.forbidden_calls == []


@pytest.mark.parametrize("change", ("inventory", "name", "room", "household", "coordinator"))
def test_freshness_change_rejects_before_any_playlist_mutation(change):
    speaker = FakeSpeaker()
    plan = plan_for(speaker)
    if change == "inventory":
        add_existing_playlist(speaker, "SQ:50", "External")
    elif change == "name":
        add_existing_playlist(speaker, "SQ:50", "Inspection Friday")
    elif change == "room":
        speaker.uid = "R2"
    elif change == "household":
        speaker.household_id = "Sonos_HH2"
    else:
        other = SimpleNamespace(uid="R2", household_id="Sonos_HH1")
        speaker.group.coordinator = other
    with pytest.raises(PlanConflictError):
        execute(speaker, plan)
    assert speaker.create_calls == []
    assert speaker.forbidden_calls == []


def test_collision_full_inventory_and_missing_capability_are_read_only_rejections():
    collision = FakeSpeaker()
    add_existing_playlist(collision, "SQ:50", "Inspection Friday")
    with pytest.raises(PlanConflictError, match="exact name"):
        inspect_retained_apple_playlist_target(
            collision,
            "Inspection Friday",
            adapter_factory=FakeDirectAdapter,
        )

    full = FakeSpeaker()
    for index in range(100):
        add_existing_playlist(full, f"SQ:{index + 1}", f"Existing {index + 1}")
    with pytest.raises(PlanConflictError, match="inventory is full"):
        inspect_retained_apple_playlist_target(
            full,
            "Inspection Friday",
            adapter_factory=FakeDirectAdapter,
        )

    class MissingAdapter:
        def __init__(self, _speaker):
            raise ValueError("private unavailable capability")

    missing = FakeSpeaker()
    with pytest.raises(PlanConflictError, match="direct Apple"):
        inspect_retained_apple_playlist_target(
            missing,
            "Inspection Friday",
            adapter_factory=MissingAdapter,
        )
    assert collision.forbidden_calls == full.forbidden_calls == missing.forbidden_calls == []


def test_concurrent_unrelated_playlist_causes_retained_bounded_failure_without_deletion():
    speaker = FakeSpeaker()
    plan = plan_for(speaker, planned_tracks=[TRACK_ONE])
    speaker.unrelated_race_position = 1
    with pytest.raises(RetainedPlaylistTransactionError) as error:
        execute(speaker, plan)
    details = error.value.details
    assert details["verificationStatus"] == "inventory_changed"
    assert details["partialPlaylistId"] == "SQ:1"
    assert details["preExistingPlaylistsUnchanged"] is True
    assert set(speaker.playlists) == {"SQ:1", "SQ:99"}
    assert speaker.forbidden_calls == []


def test_safe_failure_envelope_is_bounded_and_leaks_no_infrastructure_detail():
    speaker = FakeSpeaker()
    planned = generated_tracks(25)
    plan = plan_for(speaker, planned_tracks=planned)
    speaker.fail_add_position = 25
    speaker.add_failure = SoCoUPnPException(
        "secret credential at 192.0.2.1 with URI and SOAP",
        "800",
        b"<private/>",
    )
    with pytest.raises(RetainedPlaylistTransactionError) as error:
        execute(speaker, plan)
    envelope = result_payload(
        "x" * MAX_PROTOCOL_REQUEST_ID_BYTES,
        revision=999,
        error=error_payload(
            error.value.code,
            str(error.value),
            operation="playlists.apple.retained.create",
            details=error.value.details,
        ),
    )
    line = protocol_line(envelope)
    assert len(line.encode("utf-8")) <= MAX_PROTOCOL_LINE_BYTES
    for forbidden in (
        "192.0.2.1",
        "credential",
        "music.apple.com",
        "x-sonos",
        "DIDL",
        "SOAP",
        "SA_RINCON",
        "<private",
    ):
        assert forbidden not in line
