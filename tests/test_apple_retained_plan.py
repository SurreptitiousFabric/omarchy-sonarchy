from __future__ import annotations

import copy
import itertools
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from sonarchy_backend.apple_catalog import canonical_apple_song
from sonarchy_backend.contracts import (
    MAX_PROTOCOL_LINE_BYTES,
    MAX_PROTOCOL_REQUEST_ID_BYTES,
    protocol_line,
    result_payload,
)
from sonarchy_backend.domains.apple_retained_plan import (
    AppleSongPlanItem,
    PlanTicketStore,
    RetainedApplePlaylistPlan,
    RetainedApplePlaylistPlanService,
    validate_apple_song_items,
)
from sonarchy_backend.domains.errors import PlanConflictError

TRACK_ONE = {
    "catalogId": "1452806384",
    "url": (
        "https://music.apple.com/ch/album/kiss-me-kiss-me-kiss-me/1452806377?i=1452806384&l=en-GB"
    ),
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


def target_state(room_uid="R1", fingerprint="sha256:playlists"):
    return {
        "room": {
            "uid": room_uid,
            "coordinatorUid": room_uid,
            "householdFingerprint": f"sha256:{'1' * 64}",
        },
        "observedState": {
            "playlistCount": 1,
            "playlistInventoryFingerprint": fingerprint,
            "capabilities": [
                "playlist_plan.apple.retained.validate",
                "playlists.apple.retained.create",
                "direct-apple-saved-queue-retained",
            ],
        },
    }


class FakeBackend:
    def __init__(self):
        self.states = {"R1": target_state(), "R2": target_state("R2")}
        self.inspections = []
        self.executions = []
        self.failure = None

    def inspect_retained_apple_playlist_target(self, room_uid, playlist_name):
        self.inspections.append((room_uid, playlist_name))
        return copy.deepcopy(self.states[room_uid])

    def create_retained_apple_playlist(self, plan):
        self.executions.append(copy.deepcopy(plan))
        if self.failure is not None:
            raise self.failure
        return {"ok": True, "playlist": {"id": "SQ:17"}}


class MutableClock:
    def __init__(self, value=100.0):
        self.value = value

    def __call__(self):
        return self.value


def token_factory():
    counter = itertools.count(1)
    return lambda: f"retained_ticket_{next(counter):024d}"


def plan_args(**changes):
    value = {
        "roomUid": "R1",
        "playlistName": "Inspection Friday",
        "retentionMode": "manual-inspection",
        "tracks": [copy.deepcopy(TRACK_ONE), copy.deepcopy(TRACK_TWO)],
    }
    value.update(changes)
    return value


def services(backend=None, *, clock=None):
    backend = backend or FakeBackend()
    clock = clock or MutableClock()
    tickets = PlanTicketStore(
        clock=clock,
        wall_clock=lambda: 1_700_000_000.0,
        token_factory=token_factory(),
    )
    validation, creation = RetainedApplePlaylistPlanService(
        backend,
        tickets=tickets,
    ).services()
    return backend, validation, creation


def stored_plan(operation="playlists.apple.retained.create"):
    track = AppleSongPlanItem(
        catalog_id=TRACK_ONE["catalogId"],
        url=TRACK_ONE["url"],
        title=TRACK_ONE["title"],
        artist=TRACK_ONE["artist"],
        album=TRACK_ONE["album"],
        duration_ms=TRACK_ONE["durationMs"],
    )
    return RetainedApplePlaylistPlan(
        operation=operation,
        room_uid="R1",
        playlist_name="Inspection Friday",
        retention_mode="manual-inspection",
        allow_duplicates=False,
        tracks=(track,),
        target_state=target_state(),
        plan_fingerprint="test-fingerprint",
    )


def validate(validation, args=None):
    return validation.execute(
        "playlist_plan.apple.retained.validate",
        args or plan_args(),
    )


def test_exact_apple_song_is_canonicalised_without_substitution():
    url, catalog_id = canonical_apple_song(TRACK_ONE["url"], TRACK_ONE["catalogId"])
    assert url == TRACK_ONE["url"]
    assert catalog_id == "1452806384"


@pytest.mark.parametrize(
    ("url", "catalog_id"),
    (
        ("https://example.test/ch/album/a/1?i=2", "2"),
        ("http://music.apple.com/ch/album/a/1?i=2", "2"),
        ("https://user@music.apple.com/ch/album/a/1?i=2", "2"),
        ("https://music.apple.com:444/ch/album/a/1?i=2", "2"),
        ("https://music.apple.com/ch/album/a/1", "1"),
        ("https://music.apple.com/ch/playlist/a/pl.u-abc", "123"),
        ("https://music.apple.com/ch/album/a/1?i=2#fragment", "2"),
        ("https://music.apple.com/ch/album/a/1?i=2", "3"),
    ),
)
def test_untrusted_or_non_exact_apple_links_are_rejected(url, catalog_id):
    with pytest.raises(ValueError):
        canonical_apple_song(url, catalog_id)


def test_track_schema_bounds_and_duplicate_policy_fail_closed():
    duplicate = [copy.deepcopy(TRACK_ONE), copy.deepcopy(TRACK_ONE)]
    with pytest.raises(ValueError, match="Duplicate"):
        validate_apple_song_items(duplicate, allow_duplicates=False)
    assert len(validate_apple_song_items(duplicate, allow_duplicates=True)) == 2
    with pytest.raises(ValueError, match="at most 25"):
        validate_apple_song_items([copy.deepcopy(TRACK_ONE)] * 26, allow_duplicates=True)
    for change in (
        {"title": "x" * 241},
        {"artist": "unsafe\ntext"},
        {"durationMs": 0},
        {"durationMs": True},
        {"provider": "generic"},
    ):
        track = copy.deepcopy(TRACK_ONE)
        track.update(change)
        with pytest.raises(ValueError):
            validate_apple_song_items([track], allow_duplicates=False)


def test_preflight_is_explicit_bounded_and_honest_about_sonos_acceptance():
    backend, validation, _creation = services()
    review = validate(validation)

    assert backend.inspections == [("R1", "Inspection Friday")]
    assert review["operation"] == "playlists.apple.retained.create"
    assert review["approvalRequired"] is True
    assert review["retentionMode"] == "manual-inspection"
    assert review["playlist"] == {"name": "Inspection Friday", "collision": False}
    assert review["catalogueIdentityValidated"] is True
    assert review["sonosAcceptance"] == "unproven_until_create"
    assert review["playlistRetainedOnFailure"] is True
    assert review["queueMutation"] is False
    assert review["playbackMutation"] is False
    assert review["expiresInSec"] == 120
    assert review["trackCount"] == 2
    assert review["totalDurationMs"] == 480000
    assert [track["canonicalIdentity"] for track in review["tracks"]] == [
        "song:1452806384",
        "song:1443065566",
    ]
    side_effects = " ".join(review["expectedSideEffects"]).casefold()
    assert "retain" in side_effects
    assert "separate exact-id approval" in side_effects
    assert "do not inspect or change a room queue" in side_effects
    serialized = json.dumps(review)
    assert "music.apple.com" not in serialized
    for irrelevant in ("mediaFingerprint", "transportState", '"queue"', '"volume"', '"mute"'):
        assert irrelevant not in serialized


def test_maximal_25_track_review_remains_below_protocol_limit():
    planned = []
    metadata = "界" * 80
    for offset in range(25):
        identifier = str(3_000_000_000 + offset)
        planned.append(
            {
                "catalogId": identifier,
                "url": f"https://music.apple.com/ch/album/reviewed/999?i={identifier}",
                "title": metadata,
                "artist": metadata,
                "album": metadata,
                "durationMs": 180000 + offset,
            }
        )
    _backend, validation, _creation = services()
    review = validate(validation, plan_args(playlistName="\\" * 80, tracks=planned))
    envelope = result_payload(
        "\\" * MAX_PROTOCOL_REQUEST_ID_BYTES,
        revision=999,
        value=review,
    )
    assert len(protocol_line(envelope).encode("utf-8")) <= MAX_PROTOCOL_LINE_BYTES


@pytest.mark.parametrize(
    "changes",
    (
        {"retentionMode": "automatic-cleanup"},
        {"playlistName": ""},
        {"playlistName": "x" * 81},
        {"allowDuplicates": "yes"},
        {"unknown": True},
    ),
)
def test_preflight_rejects_non_retained_or_unbounded_arguments(changes):
    _backend, validation, _creation = services()
    with pytest.raises(ValueError):
        validate(validation, plan_args(**changes))


def test_approved_ticket_executes_once_with_only_the_bound_plan():
    backend, validation, creation = services()
    review = validate(validation)
    result = creation.execute(
        "playlists.apple.retained.create",
        {"planToken": review["planToken"], "approved": True},
    )
    assert result["playlist"]["id"] == "SQ:17"
    executed = backend.executions[0]
    assert executed["roomUid"] == "R1"
    assert executed["playlistName"] == "Inspection Friday"
    assert executed["retentionMode"] == "manual-inspection"
    assert [track["catalogId"] for track in executed["tracks"]] == [
        "1452806384",
        "1443065566",
    ]
    with pytest.raises(PlanConflictError, match="already used"):
        creation.execute(
            "playlists.apple.retained.create",
            {"planToken": review["planToken"], "approved": True},
        )


def test_preclaim_rejection_leaves_ticket_usable_and_replacements_are_denied():
    backend, validation, creation = services()
    token = validate(validation)["planToken"]
    with pytest.raises(ValueError, match="Explicit approval"):
        creation.execute(
            "playlists.apple.retained.create",
            {"planToken": token, "approved": False},
        )
    with pytest.raises(ValueError, match="only planToken and approved"):
        creation.execute(
            "playlists.apple.retained.create",
            {"planToken": token, "approved": True, "playlistName": "replacement"},
        )
    creation.execute(
        "playlists.apple.retained.create",
        {"planToken": token, "approved": True},
    )
    assert len(backend.executions) == 1


def test_ticket_expiry_restart_and_claimed_failure_all_fail_closed():
    clock = MutableClock()
    _backend, validation, creation = services(clock=clock)
    expired = validate(validation)["planToken"]
    clock.value += 121
    with pytest.raises(PlanConflictError, match="expired"):
        creation.execute(
            "playlists.apple.retained.create",
            {"planToken": expired, "approved": True},
        )

    _backend, validation, _creation = services()
    restarted_token = validate(validation)["planToken"]
    _new_backend, _new_validation, new_creation = services()
    with pytest.raises(PlanConflictError, match="invalid or unavailable"):
        new_creation.execute(
            "playlists.apple.retained.create",
            {"planToken": restarted_token, "approved": True},
        )

    backend, validation, creation = services()
    backend.failure = RuntimeError("private provider address and token")
    failed_token = validate(validation)["planToken"]
    with pytest.raises(RuntimeError):
        creation.execute(
            "playlists.apple.retained.create",
            {"planToken": failed_token, "approved": True},
        )
    with pytest.raises(PlanConflictError, match="already used"):
        creation.execute(
            "playlists.apple.retained.create",
            {"planToken": failed_token, "approved": True},
        )


def test_atomic_claim_permits_only_one_concurrent_execution():
    backend, validation, creation = services()
    token = validate(validation)["planToken"]

    def execute_once(_index):
        try:
            creation.execute(
                "playlists.apple.retained.create",
                {"planToken": token, "approved": True},
            )
            return "success"
        except PlanConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(execute_once, range(2)))
    assert sorted(outcomes) == ["conflict", "success"]
    assert len(backend.executions) == 1


def test_ticket_store_bounds_ttl_capacity_and_operation_identity(monkeypatch):
    for ttl in (0, 121):
        with pytest.raises(ValueError, match="lifetime"):
            PlanTicketStore(ttl_sec=ttl)
    invalid = PlanTicketStore(token_factory=lambda: "short")
    with pytest.raises(RuntimeError, match="unique retained playlist"):
        invalid.issue(stored_plan())
    monkeypatch.setattr(
        "sonarchy_backend.domains.apple_retained_plan.MAX_PENDING_PLAN_TICKETS",
        1,
    )
    bounded = PlanTicketStore(token_factory=token_factory())
    bounded.issue(stored_plan())
    with pytest.raises(PlanConflictError, match="Too many retained"):
        bounded.issue(stored_plan())

    backend = FakeBackend()
    tickets = PlanTicketStore(token_factory=token_factory())
    _validation, creation = RetainedApplePlaylistPlanService(
        backend,
        tickets=tickets,
    ).services()
    wrong = tickets.issue(stored_plan(operation="another.operation"))
    with pytest.raises(PlanConflictError, match="another operation"):
        creation.execute(
            "playlists.apple.retained.create",
            {"planToken": wrong.token, "approved": True},
        )
