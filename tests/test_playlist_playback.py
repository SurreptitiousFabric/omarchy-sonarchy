from __future__ import annotations

import copy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from sonarchy_backend.controller_common import ControllerError
from sonarchy_backend.controller_facade import DomainFacadeMixin
from sonarchy_backend.domains.apple_playlist_plan import PlanTicketStore
from sonarchy_backend.domains.application import SonarchyApplication
from sonarchy_backend.domains.common import RequestContext
from sonarchy_backend.domains.errors import PlanConflictError, PlaylistPlayTransactionError
from sonarchy_backend.domains.playlist_play_plan import PlaylistPlayPlanService
from sonarchy_backend.domains.playlist_playback import (
    PLAYLIST_PLAY_SIDE_EFFECTS,
    execute_preflighted_playlist_play,
    inspect_playlist_play_target,
)


class Result(list):
    def __init__(self, items=(), *, total_matches=None):
        super().__init__(items)
        self.total_matches = len(self) if total_matches is None else total_matches


def resource(identity: str):
    return SimpleNamespace(
        uri=f"x-private-provider:{identity}",
        protocol_info="x-private-protocol",
        duration="0:03:32",
    )


def item(identity: str, title: str | None = None):
    return SimpleNamespace(
        item_id=f"private:{identity}",
        title=title or f"Track {identity}",
        creator=f"Artist {identity}",
        album=f"Album {identity}",
        resources=[resource(identity)],
    )


class Transport:
    def __init__(self, owner):
        self.owner = owner

    def GetMediaInfo(self, _args):
        return {"CurrentURI": self.owner.source_uri}


class MusicLibrary:
    def __init__(self, owner):
        self.owner = owner

    def browse(self, *, ml_item, start, max_items, full_album_art_uri):
        assert ml_item.item_id == self.owner.playlist.item_id
        assert (start, full_album_art_uri) == (0, False)
        values = copy.deepcopy(self.owner.playlist_items)
        if self.owner.playlist_total_override is not None:
            total = self.owner.playlist_total_override
        else:
            total = len(values)
        return Result(values[:max_items], total_matches=total)


class FakeSpeaker:
    def __init__(self):
        self.uid = "R1"
        self.player_name = "Office"
        self.household_id = "Sonos_HH1"
        self.is_visible = True
        self.volume = 20
        self.mute = False
        self.transport = "STOPPED"
        self.music_source = "APPLE_MUSIC"
        self.source_uri = "x-rincon-queue:R1#0"
        self.group = SimpleNamespace(coordinator=self, members=[self])
        self.playlist = SimpleNamespace(item_id="SQ:9", title="Morning")
        self.playlist_items = [item("one"), item("two")]
        self.queue_items = [item("existing")]
        self.current_position = 1
        self.playlist_total_override = None
        self.queue_total_override = None
        self.append_failure = False
        self.play_failure = False
        self.bad_append_position = False
        self.queue_verification_failure = False
        self.playback_verification_failure = False
        self.append_calls = []
        self.play_calls = []
        self.get_playlist_calls = []
        self.avTransport = Transport(self)
        self.music_library = MusicLibrary(self)

    def get_current_transport_info(self):
        return {"current_transport_state": self.transport}

    def get_current_track_info(self):
        position = self.current_position
        selected = (
            self.queue_items[position - 1] if 1 <= position <= len(self.queue_items) else None
        )
        return {
            "playlist_position": str(position) if position else "0",
            "title": selected.title if selected else "",
            "artist": selected.creator if selected else "",
            "album": selected.album if selected else "",
        }

    def get_sonos_playlists(self, *, max_items):
        values = [self.playlist] if self.playlist is not None else []
        return Result(values[:max_items], total_matches=len(values))

    def get_sonos_playlist_by_attr(self, attribute, value):
        self.get_playlist_calls.append((attribute, value))
        if self.playlist is None or getattr(self.playlist, attribute) != value:
            raise ValueError("private missing playlist")
        return self.playlist

    def get_queue(self, *, max_items, full_album_art_uri):
        assert full_album_art_uri is False
        values = copy.deepcopy(self.queue_items)
        if self.queue_verification_failure and self.play_calls:
            values[-1].title = "Changed after append"
        total = self.queue_total_override
        return Result(
            values[:max_items],
            total_matches=len(values) if total is None else total,
        )

    def add_to_queue(self, playlist):
        self.append_calls.append(playlist.item_id)
        if self.append_failure:
            raise RuntimeError("private append failure at 192.0.2.1")
        position = len(self.queue_items) + 1
        self.queue_items.extend(copy.deepcopy(self.playlist_items))
        return position + 1 if self.bad_append_position else position

    def play_from_queue(self, index):
        self.play_calls.append(index)
        if self.play_failure:
            raise RuntimeError("private playback failure with DIDL")
        self.current_position = index + 1
        self.transport = "PAUSED_PLAYBACK" if self.playback_verification_failure else "PLAYING"
        self.source_uri = "x-rincon-queue:R1#0"


class PlaybackBackend:
    def __init__(self, speaker):
        self.speaker = speaker

    def inspect_playlist_play_target(self, room_uid, playlist_id):
        if room_uid != self.speaker.uid:
            raise PlanConflictError("The exact Sonos room is unavailable")
        return inspect_playlist_play_target(self.speaker, playlist_id)

    def execute_preflighted_playlist_play(self, plan, mutation_started_callback=None):
        return execute_preflighted_playlist_play(
            self.speaker,
            plan,
            mutation_started_callback=mutation_started_callback,
        )


class FacadeHarness(DomainFacadeMixin):
    def __init__(self, speakers):
        self.speakers = {speaker.uid: speaker for speaker in speakers}

    def _zone(self, room_uid):
        try:
            return self.speakers[room_uid]
        except KeyError as exc:
            raise ControllerError("private missing room") from exc


def preflight(application, *, room_uid="R1", playlist_id="SQ:9"):
    return application.execute(
        "playlists.play.validate",
        {"roomUid": room_uid, "playlistId": playlist_id},
    )


def execute(application, review, callback=None):
    return application.execute(
        "playlists.play.execute",
        {"planToken": review["planToken"], "approved": True},
        mutation_started_callback=callback,
    )


def test_preflight_binds_complete_safe_room_playlist_and_queue_review():
    speaker = FakeSpeaker()
    state = inspect_playlist_play_target(speaker, "SQ:9")

    assert state["room"] == {
        "uid": "R1",
        "name": "Office",
        "householdFingerprint": state["room"]["householdFingerprint"],
        "coordinatorUid": "R1",
        "online": True,
        "volume": 20,
        "mute": False,
        "transport": "STOPPED",
        "source": "QUEUE",
        "capabilities": [
            "append-sonos-playlist",
            "play-from-queue",
            "read-complete-playlist",
            "read-complete-queue",
            "resolve-exact-playlist",
        ],
    }
    assert state["topology"] == {
        "groupUid": "R1",
        "coordinatorUid": "R1",
        "memberUids": ["R1"],
        "standalone": True,
    }
    assert state["playlist"]["id"] == "SQ:9"
    assert state["playlist"]["title"] == "Morning"
    assert state["playlist"]["itemCount"] == 2
    assert len(state["playlist"]["itemPreview"]) == 2
    assert state["playlist"]["firstItem"]["title"] == "Track one"
    assert state["queue"]["length"] == 1
    assert state["queue"]["currentPosition"] == 1
    assert state["queue"]["expectedFirstAppendedPosition"] == 2
    rendered = json.dumps(state)
    assert "x-private-provider" not in rendered
    assert "private:one" not in rendered


def test_exact_room_uid_wins_over_duplicate_supporting_names_and_missing_uid_fails():
    first = FakeSpeaker()
    second = FakeSpeaker()
    second.uid = "R2"
    second.group = SimpleNamespace(coordinator=second, members=[second])
    first.player_name = second.player_name = "Office"
    facade = FacadeHarness([first, second])

    state = facade.inspect_playlist_play_target("R2", "SQ:9")
    assert state["room"]["uid"] == "R2"
    assert state["room"]["name"] == "Office"
    with pytest.raises(PlanConflictError, match="exact Sonos room"):
        facade.inspect_playlist_play_target("missing", "SQ:9")


def test_plan_review_states_every_append_and_play_effect():
    application = SonarchyApplication(PlaybackBackend(FakeSpeaker()))  # type: ignore[arg-type]
    review = preflight(application)

    assert review["operation"] == "playlists.play.execute"
    assert review["approvalRequired"] is True
    assert review["planFingerprint"].startswith("sha256:")
    assert review["expectedSideEffects"] == list(PLAYLIST_PLAY_SIDE_EFFECTS)
    combined = " ".join(review["expectedSideEffects"]).lower()
    for phrase in (
        "every existing",
        "append the complete",
        "first newly appended",
        "interrupt",
        "sonos queue",
        "do not change volume",
        "do not retry",
        "appended items may remain",
        "do not clear",
    ):
        assert phrase in combined


@pytest.mark.parametrize(
    ("change", "message"),
    (
        (
            lambda speaker: setattr(
                speaker,
                "group",
                SimpleNamespace(coordinator=speaker, members=[speaker, SimpleNamespace(uid="R2")]),
            ),
            "standalone",
        ),
        (lambda speaker: setattr(speaker, "is_visible", False), "offline"),
        (lambda speaker: setattr(speaker, "transport", "PLAYING"), "stopped or paused"),
        (lambda speaker: setattr(speaker, "volume", 21), "at most 20"),
    ),
)
def test_preflight_rejects_unsafe_room_state(change, message):
    speaker = FakeSpeaker()
    change(speaker)
    with pytest.raises(PlanConflictError, match=message):
        inspect_playlist_play_target(speaker, "SQ:9")


@pytest.mark.parametrize(
    "source_uri",
    (
        "x-sonos-htastream:R1:spdif",
        "x-rincon-stream:R2",
        "x-sonos-vli:R1:airplay",
        "x-sonosapi-stream:station",
        "https://unknown.invalid/stream",
    ),
)
def test_preflight_rejects_tv_line_in_airplay_radio_and_unknown_sources(source_uri):
    speaker = FakeSpeaker()
    speaker.source_uri = source_uri
    with pytest.raises(PlanConflictError, match="source"):
        inspect_playlist_play_target(speaker, "SQ:9")


@pytest.mark.parametrize("source_hint", ("TV", "LINE_IN", "AIRPLAY", "RADIO", "UNKNOWN"))
def test_preflight_rejects_explicit_unsafe_source_even_with_contradictory_queue_uri(
    source_hint,
):
    speaker = FakeSpeaker()
    speaker.music_source = source_hint
    with pytest.raises(PlanConflictError, match="source"):
        inspect_playlist_play_target(speaker, "SQ:9")


def test_preflight_accepts_volume_twenty_and_established_no_source():
    speaker = FakeSpeaker()
    speaker.source_uri = ""
    speaker.music_source = "NONE"
    state = inspect_playlist_play_target(speaker, "SQ:9")
    assert state["room"]["volume"] == 20
    assert state["room"]["source"] == "NONE"


@pytest.mark.parametrize("playlist_id", ("", "9", "SQ:x", "SQ:9/track"))
def test_preflight_rejects_malformed_playlist_id(playlist_id):
    with pytest.raises(PlanConflictError, match="SQ:<id>"):
        inspect_playlist_play_target(FakeSpeaker(), playlist_id)


def test_preflight_rejects_missing_empty_overlarge_or_incomplete_playlist():
    missing = FakeSpeaker()
    missing.playlist = None
    with pytest.raises(PlanConflictError, match="unavailable or ambiguous"):
        inspect_playlist_play_target(missing, "SQ:9")

    empty = FakeSpeaker()
    empty.playlist_items = []
    with pytest.raises(PlanConflictError, match="empty"):
        inspect_playlist_play_target(empty, "SQ:9")

    large = FakeSpeaker()
    large.playlist_items = [item(str(index)) for index in range(26)]
    with pytest.raises(PlanConflictError, match="contents could not be read safely"):
        inspect_playlist_play_target(large, "SQ:9")

    incomplete = FakeSpeaker()
    incomplete.playlist_total_override = 3
    with pytest.raises(PlanConflictError, match="contents could not be read safely"):
        inspect_playlist_play_target(incomplete, "SQ:9")

    ambiguous = FakeSpeaker()
    duplicate = SimpleNamespace(item_id="SQ:9", title="Duplicate")
    ambiguous.get_sonos_playlists = Mock(return_value=Result([ambiguous.playlist, duplicate]))
    with pytest.raises(PlanConflictError, match="unavailable or ambiguous"):
        inspect_playlist_play_target(ambiguous, "SQ:9")


def test_preflight_preview_is_bounded_while_fingerprint_covers_all_items():
    speaker = FakeSpeaker()
    speaker.playlist_items = [item(f"track-{index}") for index in range(25)]
    state = inspect_playlist_play_target(speaker, "SQ:9")
    assert state["playlist"]["itemCount"] == 25
    assert len(state["playlist"]["itemPreview"]) == 5
    assert state["playlist"]["contentFingerprint"].startswith("sha256:")


def test_preflight_rejects_incomplete_or_overcombined_queue():
    incomplete = FakeSpeaker()
    incomplete.queue_total_override = 2
    with pytest.raises(PlanConflictError, match="queue could not be read safely"):
        inspect_playlist_play_target(incomplete, "SQ:9")

    full = FakeSpeaker()
    full.queue_items = [item(f"queue-{index}") for index in range(99)]
    with pytest.raises(PlanConflictError, match="exceed 100"):
        inspect_playlist_play_target(full, "SQ:9")


def test_success_preserves_queue_appends_exact_order_and_verifies_playback():
    speaker = FakeSpeaker()
    application = SonarchyApplication(PlaybackBackend(speaker))  # type: ignore[arg-type]
    review = preflight(application)
    mutation_started = Mock()

    result = execute(application, review, mutation_started)

    assert result["ok"] is True
    assert result["room"]["uid"] == "R1"
    assert result["playlist"]["id"] == "SQ:9"
    assert result["playlist"]["contentFingerprint"] == review["playlist"]["contentFingerprint"]
    assert result["queue"] == {
        "beforeLength": 1,
        "afterLength": 3,
        "expectedFirstAppendedPosition": 2,
        "currentPosition": 2,
        "appendedItemCount": 2,
        "appendedSegmentFingerprint": review["playlist"]["contentFingerprint"],
        "existingEntriesPreserved": True,
    }
    assert [queued.title for queued in speaker.queue_items] == [
        "Track existing",
        "Track one",
        "Track two",
    ]
    assert speaker.append_calls == ["SQ:9"]
    assert speaker.play_calls == [1]
    assert result["playback"]["transport"] == "PLAYING"
    assert result["playback"]["source"] == "QUEUE"
    assert result["mutations"]["appendInvocationCount"] == 1
    assert result["mutations"]["playbackStartInvocationCount"] == 1
    assert result["mutations"]["queueRollbackAttempted"] is False
    assert result["retryCount"] == 0
    assert result["substitutionCount"] == 0
    mutation_started.assert_called_once_with()


@pytest.mark.parametrize(
    "change",
    (
        lambda speaker: setattr(speaker, "uid", "R2"),
        lambda speaker: setattr(speaker, "player_name", "Renamed"),
        lambda speaker: setattr(speaker, "household_id", "Sonos_HH2"),
        lambda speaker: setattr(speaker, "is_visible", False),
        lambda speaker: setattr(
            speaker,
            "group",
            SimpleNamespace(coordinator=speaker, members=[speaker, SimpleNamespace(uid="R2")]),
        ),
        lambda speaker: setattr(speaker, "volume", 19),
        lambda speaker: setattr(speaker, "mute", True),
        lambda speaker: setattr(speaker, "source_uri", ""),
        lambda speaker: setattr(speaker, "transport", "PAUSED_PLAYBACK"),
        lambda speaker: speaker.queue_items.append(item("changed-queue")),
        lambda speaker: setattr(speaker, "current_position", 0),
        lambda speaker: setattr(speaker.playlist, "title", "Changed title"),
        lambda speaker: setattr(speaker.playlist, "item_id", "SQ:10"),
        lambda speaker: speaker.playlist_items.append(item("changed-playlist")),
        lambda speaker: setattr(speaker, "add_to_queue", None),
    ),
)
def test_every_bound_state_change_conflicts_before_mutation(change):
    speaker = FakeSpeaker()
    application = SonarchyApplication(PlaybackBackend(speaker))  # type: ignore[arg-type]
    review = preflight(application)
    change(speaker)

    with pytest.raises(PlaylistPlayTransactionError) as rejected:
        execute(application, review)

    assert rejected.value.code == "conflict"
    assert rejected.value.details["phase"] == "preflight_revalidation"
    assert rejected.value.details["queueAppended"] is False
    assert rejected.value.details["playbackStarted"] is False
    assert speaker.append_calls == []
    assert speaker.play_calls == []


def test_append_rejection_is_bounded_and_never_retried():
    speaker = FakeSpeaker()
    application = SonarchyApplication(PlaybackBackend(speaker))  # type: ignore[arg-type]
    review = preflight(application)
    speaker.append_failure = True

    with pytest.raises(PlaylistPlayTransactionError) as rejected:
        execute(application, review)

    details = rejected.value.details
    assert details["phase"] == "append_playlist"
    assert details["queueAppended"] is False
    assert details["playbackStarted"] is False
    assert details["appendInvocationCount"] == 1
    assert details["playbackStartInvocationCount"] == 0
    assert details["retryCount"] == 0
    assert speaker.append_calls == ["SQ:9"]
    assert speaker.play_calls == []
    assert "192.0.2.1" not in str(rejected.value)


def test_playback_rejection_leaves_append_and_attempts_no_rollback():
    speaker = FakeSpeaker()
    application = SonarchyApplication(PlaybackBackend(speaker))  # type: ignore[arg-type]
    review = preflight(application)
    speaker.play_failure = True

    with pytest.raises(PlaylistPlayTransactionError) as rejected:
        execute(application, review)

    details = rejected.value.details
    assert details["phase"] == "start_playback"
    assert details["queueAppended"] is True
    assert details["playbackStarted"] is False
    assert details["observedQueueLength"] == 3
    assert details["expectedFirstAppendedPosition"] == 2
    assert details["appendInvocationCount"] == 1
    assert details["playbackStartInvocationCount"] == 1
    assert details["queueRollbackAttempted"] is False
    assert len(speaker.queue_items) == 3
    assert speaker.append_calls == ["SQ:9"]
    assert speaker.play_calls == [1]


def test_unexpected_append_position_reports_partial_append_without_starting_playback():
    speaker = FakeSpeaker()
    application = SonarchyApplication(PlaybackBackend(speaker))  # type: ignore[arg-type]
    review = preflight(application)
    speaker.bad_append_position = True

    with pytest.raises(PlaylistPlayTransactionError) as rejected:
        execute(application, review)

    assert rejected.value.details["phase"] == "append_playlist"
    assert rejected.value.details["queueAppended"] is True
    assert rejected.value.details["playbackStarted"] is False
    assert rejected.value.details["queueRollbackAttempted"] is False
    assert speaker.append_calls == ["SQ:9"]
    assert speaker.play_calls == []


@pytest.mark.parametrize(
    ("attribute", "phase", "playback_started"),
    (
        ("queue_verification_failure", "verify_queue", True),
        ("playback_verification_failure", "verify_playback", False),
    ),
)
def test_post_write_verification_failures_report_partial_state_without_rollback(
    attribute, phase, playback_started
):
    speaker = FakeSpeaker()
    application = SonarchyApplication(PlaybackBackend(speaker))  # type: ignore[arg-type]
    review = preflight(application)
    setattr(speaker, attribute, True)

    with pytest.raises(PlaylistPlayTransactionError) as rejected:
        execute(application, review)

    assert rejected.value.details["phase"] == phase
    assert rejected.value.details["queueAppended"] is True
    assert rejected.value.details["playbackStarted"] is playback_started
    assert rejected.value.details["queueRollbackAttempted"] is False
    assert speaker.append_calls == ["SQ:9"]
    assert speaker.play_calls == [1]


def test_token_replay_and_replacement_fields_fail_without_second_execution():
    speaker = FakeSpeaker()
    application = SonarchyApplication(PlaybackBackend(speaker))  # type: ignore[arg-type]
    review = preflight(application)
    token = review["planToken"]

    with pytest.raises(ValueError, match="only planToken"):
        application.execute(
            "playlists.play.execute",
            {
                "planToken": token,
                "approved": True,
                "roomUid": "R2",
                "playlistId": "SQ:10",
            },
        )
    assert speaker.append_calls == []

    execute(application, review)
    with pytest.raises(PlanConflictError, match="already used"):
        execute(application, review)
    assert speaker.append_calls == ["SQ:9"]
    assert speaker.play_calls == [1]


def test_playback_backend_token_expiry_and_restart_fail_without_mutation():
    now = [100.0]
    speaker = FakeSpeaker()
    backend = PlaybackBackend(speaker)
    tickets = PlanTicketStore(
        clock=lambda: now[0],
        wall_clock=lambda: now[0],
        token_factory=lambda: "playback_ticket_000000000000000000000001",
        ttl_sec=1,
    )
    service = PlaylistPlayPlanService(backend, tickets=tickets)
    review = service.validate(
        {"roomUid": "R1", "playlistId": "SQ:9"},
        RequestContext(),
    )
    now[0] += 2

    with pytest.raises(PlanConflictError, match="expired"):
        service.execute(
            {"planToken": review["planToken"], "approved": True},
            RequestContext(),
        )
    assert speaker.append_calls == []

    first_backend = SonarchyApplication(backend)  # type: ignore[arg-type]
    restart_review = preflight(first_backend)
    restarted_backend = SonarchyApplication(backend)  # type: ignore[arg-type]
    with pytest.raises(PlanConflictError, match="invalid or unavailable"):
        execute(restarted_backend, restart_review)
    assert speaker.append_calls == []
