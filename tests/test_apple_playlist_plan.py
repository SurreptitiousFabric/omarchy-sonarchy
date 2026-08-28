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
from sonarchy_backend.domains.apple_playlist_plan import (
    ApplePlaylistPlan,
    ApplePlaylistPlanService,
    AppleSongPlanItem,
    PlanTicketStore,
    validate_apple_song_items,
)
from sonarchy_backend.domains.common import RequestContext
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
    "url": ("https://music.apple.com/ch/album/the-colour-of-spring/1443065310?i=1443065566"),
    "title": "Life's What You Make It",
    "artist": "Talk Talk",
    "album": "The Colour of Spring",
    "durationMs": 268000,
}


def target_state(room_uid: str = "R1", *, queue_fingerprint: str = "sha256:queue"):
    return {
        "room": {
            "uid": room_uid,
            "standalone": True,
            "memberUids": [room_uid],
            "coordinatorUid": room_uid,
        },
        "observedState": {
            "topologyFingerprint": "sha256:topology",
            "queue": {
                "length": 2,
                "position": 1,
                "revisionMarker": "update:4:sha256:queue",
                "fingerprint": queue_fingerprint,
                "active": True,
            },
            "transportState": "STOPPED",
            "playbackSource": "QUEUE",
            "mediaFingerprint": f"sha256:{'a' * 64}",
            "volume": {"room": 20, "group": 20},
            "mute": {"room": False, "group": False},
            "capabilities": ["playlist_plan.apple.validate", "playlists.apple.create"],
            "playlistCount": 1,
            "playlistInventoryFingerprint": "sha256:playlists",
        },
    }


class FakePlanBackend:
    def __init__(self):
        self.states = {"R1": target_state("R1"), "R2": target_state("R2")}
        self.inspections = []
        self.executions = []
        self.failure = None

    def inspect_apple_playlist_target(self, room_uid, playlist_name):
        self.inspections.append((room_uid, playlist_name))
        return copy.deepcopy(self.states[room_uid])

    def create_preflighted_apple_playlist(self, plan):
        self.executions.append(copy.deepcopy(plan))
        if self.failure:
            raise self.failure
        return {"ok": True, "playlist": {"id": "SQ:17"}}


class MutableClock:
    def __init__(self, value=100.0):
        self.value = value

    def __call__(self):
        return self.value


def token_factory():
    counter = itertools.count(1)
    return lambda: f"ticket_{next(counter):024d}"


def plan_args(**changes):
    value = {
        "roomUid": "R1",
        "playlistName": "AI Friday",
        "mode": "save-only",
        "tracks": [copy.deepcopy(TRACK_ONE), copy.deepcopy(TRACK_TWO)],
    }
    value.update(changes)
    return value


def services(backend=None, *, clock=None):
    backend = backend or FakePlanBackend()
    clock = clock or MutableClock()
    tickets = PlanTicketStore(
        clock=clock,
        wall_clock=lambda: 1_700_000_000.0,
        token_factory=token_factory(),
    )
    validation, creation = ApplePlaylistPlanService(backend, tickets=tickets).services()
    return backend, validation, creation


def stored_plan(*, operation="playlists.apple.create"):
    item = AppleSongPlanItem(
        catalog_id=TRACK_ONE["catalogId"],
        url=TRACK_ONE["url"],
        title=TRACK_ONE["title"],
        artist=TRACK_ONE["artist"],
        album=TRACK_ONE["album"],
        duration_ms=TRACK_ONE["durationMs"],
    )
    return ApplePlaylistPlan(
        operation=operation,
        room_uid="R1",
        playlist_name="AI Friday",
        mode="save-only",
        allow_duplicates=False,
        tracks=(item,),
        target_state=target_state(),
        backend_revision=7,
        plan_fingerprint="test-fingerprint",
    )


def validate_plan(validation, args=None, *, revision=7):
    return validation.execute(
        "playlist_plan.apple.validate",
        args or plan_args(),
        RequestContext(backend_revision=revision),
    )


def test_valid_apple_song_url_is_canonicalised_as_exact_song():
    url, catalog_id = canonical_apple_song(TRACK_ONE["url"], TRACK_ONE["catalogId"])
    assert url == TRACK_ONE["url"]
    assert catalog_id == "1452806384"


@pytest.mark.parametrize(
    ("url", "catalog_id", "message"),
    (
        ("https://example.com/ch/album/a/1?i=2", "2", "Apple Music"),
        ("http://music.apple.com/ch/album/a/1?i=2", "2", "Apple Music"),
        ("https://user@music.apple.com/ch/album/a/1?i=2", "2", "Apple Music"),
        ("https://music.apple.com:444/ch/album/a/1?i=2", "2", "Apple Music"),
        ("https://[", "2", "Invalid IPv6 URL"),
        ("https://music.apple.com/ch/album/a/1", "1", "missing or malformed"),
        (
            "https://music.apple.com/ch/playlist/a/pl.u-abc",
            "123",
            "song link",
        ),
        ("https://music.apple.com/ch/artist/a/123", "123", "song link"),
        ("https://music.apple.com/ch/album/a/1?i=abc", "1", "malformed song"),
        ("https://music.apple.com/ch/album/a/1?i=2evil", "2", "malformed song"),
        ("https://music.apple.com/ch/album/a/1?i=2&i=2", "2", "malformed song"),
        ("https://music.apple.com/ch/album/a/1?i=2#other", "2", "song link"),
        ("https://music.apple.com/ch/album/a/1?i=2", "abc", "catalogue"),
        ("https://music.apple.com/ch/album/a/1?i=2", "3", "does not match"),
    ),
)
def test_invalid_apple_song_links_are_rejected(url, catalog_id, message):
    with pytest.raises(ValueError, match=message):
        canonical_apple_song(url, catalog_id)


def test_track_validation_rejects_duplicates_unless_explicitly_reviewed():
    duplicates = [copy.deepcopy(TRACK_ONE), copy.deepcopy(TRACK_ONE)]
    with pytest.raises(ValueError, match="Duplicate"):
        validate_apple_song_items(duplicates, allow_duplicates=False)

    accepted = validate_apple_song_items(duplicates, allow_duplicates=True)
    assert [track.canonical_identity for track in accepted] == [
        "song:1452806384",
        "song:1452806384",
    ]


def test_track_validation_rejects_plan_limit_and_oversized_metadata():
    with pytest.raises(ValueError, match="at most 25"):
        validate_apple_song_items([copy.deepcopy(TRACK_ONE)] * 26, allow_duplicates=True)

    oversized = copy.deepcopy(TRACK_ONE)
    oversized["title"] = "x" * 241
    with pytest.raises(ValueError, match="title"):
        validate_apple_song_items([oversized], allow_duplicates=False)

    oversized["title"] = "é" * 121
    with pytest.raises(ValueError, match="title"):
        validate_apple_song_items([oversized], allow_duplicates=False)


def test_exact_25_track_plan_fits_the_bounded_protocol_request():
    tracks = []
    for offset in range(25):
        identifier = str(1_000_000_000 + offset)
        track = copy.deepcopy(TRACK_ONE)
        track.update(
            {
                "catalogId": identifier,
                "url": f"https://music.apple.com/ch/album/reviewed/999?i={identifier}",
                "title": f"Reviewed song {offset + 1}",
            }
        )
        tracks.append(track)
    accepted = validate_apple_song_items(tracks, allow_duplicates=False)
    request = {
        "version": 1,
        "id": "max-plan",
        "op": "playlist_plan.apple.validate",
        "args": plan_args(tracks=tracks),
    }
    assert len(accepted) == 25
    assert len(json.dumps(request, ensure_ascii=False).encode("utf-8")) < 64 * 1024


def test_maximal_unicode_plan_review_fits_the_exact_protocol_line_encoding():
    tracks = []
    metadata = "界" * 80
    for offset in range(25):
        identifier = str(2_000_000_000 + offset)
        prefix = "https://music.apple.com/ch/album/"
        suffix = f"/9999999999?i={identifier}"
        slug = "x" * (1024 - len(prefix.encode()) - len(suffix.encode()))
        tracks.append(
            {
                "catalogId": identifier,
                "url": f"{prefix}{slug}{suffix}",
                "title": metadata,
                "artist": metadata,
                "album": metadata,
                "durationMs": 212000,
            }
        )

    _backend, validation, _creation = services()
    review = validate_plan(
        validation,
        plan_args(playlistName="\\" * 80, tracks=tracks),
    )
    envelope = result_payload(
        "\\" * MAX_PROTOCOL_REQUEST_ID_BYTES,
        revision=7,
        value=review,
    )
    encoded = protocol_line(envelope).encode("utf-8")
    ascii_escaped = (json.dumps(envelope, separators=(",", ":")) + "\n").encode("utf-8")

    assert len(encoded) <= MAX_PROTOCOL_LINE_BYTES
    assert len(ascii_escaped) > MAX_PROTOCOL_LINE_BYTES
    assert b"\\u754c" not in encoded


def test_oversized_plan_review_is_rejected_and_its_ticket_is_discarded():
    backend = FakePlanBackend()
    backend.states["R1"]["observedState"]["padding"] = "x" * MAX_PROTOCOL_LINE_BYTES
    opaque_value = "discarded_ticket_12345678901234567890"
    tickets = PlanTicketStore(token_factory=lambda: opaque_value)
    validation, _creation = ApplePlaylistPlanService(backend, tickets=tickets).services()

    with pytest.raises(ValueError, match="review is too large"):
        validate_plan(validation)

    backend.states["R1"]["observedState"].pop("padding")
    review = validate_plan(validation)
    assert review["planToken"] == opaque_value


def test_song_validation_rejects_an_oversized_public_url():
    url = f"https://music.apple.com/ch/album/{'x' * 1000}/1?i=2"
    with pytest.raises(ValueError, match="bounded"):
        canonical_apple_song(url, "2")


@pytest.mark.parametrize("duration", (True, 0, -1, 86_400_001, 1.5, "212000"))
def test_track_validation_rejects_invalid_duration(duration):
    track = copy.deepcopy(TRACK_ONE)
    track["durationMs"] = duration
    with pytest.raises(ValueError, match="durationMs"):
        validate_apple_song_items([track], allow_duplicates=False)


def test_track_validation_rejects_missing_extra_and_non_object_fields():
    missing = copy.deepcopy(TRACK_ONE)
    missing.pop("artist")
    extra = copy.deepcopy(TRACK_ONE) | {"uri": "not-authorized"}
    for value in (missing, extra, "song"):
        with pytest.raises(ValueError, match="reviewed Apple song fields"):
            validate_apple_song_items([value], allow_duplicates=False)

    non_string = copy.deepcopy(TRACK_ONE)
    non_string["title"] = 123
    with pytest.raises(ValueError, match="must be a string"):
        validate_apple_song_items([non_string], allow_duplicates=False)
    control = copy.deepcopy(TRACK_ONE)
    control["artist"] = "Artist\nInjected"
    with pytest.raises(ValueError, match="control characters"):
        validate_apple_song_items([control], allow_duplicates=False)
    with pytest.raises(ValueError, match="non-empty list"):
        validate_apple_song_items([], allow_duplicates=False)


def test_preflight_returns_review_and_short_lived_opaque_ticket():
    backend, validation, _creation = services()
    result = validate_plan(validation)

    assert backend.inspections == [("R1", "AI Friday")]
    assert result["ok"] is True
    assert result["operation"] == "playlists.apple.create"
    assert result["approvalRequired"] is True
    assert result["expiresInSec"] == 120
    assert result["trackCount"] == 2
    assert result["totalDurationMs"] == 480000
    assert [item["canonicalIdentity"] for item in result["tracks"]] == [
        "song:1452806384",
        "song:1443065566",
    ]
    assert result["room"]["uid"] == "R1"
    assert result["observedState"]["queue"]["length"] == 2
    assert result["observedState"]["mediaFingerprint"] == f"sha256:{'a' * 64}"
    assert result["expectedSideEffects"][-1].startswith("Restore and verify")


@pytest.mark.parametrize(
    "changes",
    (
        {"mode": "temporary"},
        {"playlistName": ""},
        {"playlistName": "x" * 81},
        {"allowDuplicates": "yes"},
        {"unknown": True},
    ),
)
def test_preflight_rejects_invalid_plan_arguments(changes):
    _backend, validation, _creation = services()
    with pytest.raises(ValueError):
        validate_plan(validation, plan_args(**changes))


def test_preflight_rejects_exact_existing_name_with_deterministic_suggestion():
    class CollisionBackend(FakePlanBackend):
        def inspect_apple_playlist_target(self, room_uid, playlist_name):
            raise PlanConflictError(
                "A Sonos Playlist with that exact name already exists",
                details={"suggestedPlaylistName": "AI Friday (2)"},
            )

    _backend, validation, _creation = services(CollisionBackend())
    with pytest.raises(PlanConflictError) as error:
        validate_plan(validation)
    assert error.value.details == {"suggestedPlaylistName": "AI Friday (2)"}


def test_approved_ticket_executes_once_and_carries_only_bound_plan():
    backend, validation, creation = services()
    preflight = validate_plan(validation)
    result = creation.execute(
        "playlists.apple.create",
        {"planToken": preflight["planToken"], "approved": True},
        RequestContext(backend_revision=7),
    )

    assert result == {"ok": True, "playlist": {"id": "SQ:17"}}
    assert len(backend.executions) == 1
    executed = backend.executions[0]
    assert executed["roomUid"] == "R1"
    assert executed["playlistName"] == "AI Friday"
    assert executed["mode"] == "save-only"
    assert [item["catalogId"] for item in executed["tracks"]] == [
        "1452806384",
        "1443065566",
    ]

    with pytest.raises(PlanConflictError, match="already used"):
        creation.execute(
            "playlists.apple.create",
            {"planToken": preflight["planToken"], "approved": True},
            RequestContext(backend_revision=7),
        )


def test_ticket_expires_and_requires_new_validation():
    clock = MutableClock()
    _backend, validation, creation = services(clock=clock)
    token = validate_plan(validation)["planToken"]
    clock.value += 121
    with pytest.raises(PlanConflictError, match="expired"):
        creation.execute(
            "playlists.apple.create",
            {"planToken": token, "approved": True},
            RequestContext(backend_revision=7),
        )


def test_backend_restart_invalidates_process_local_ticket():
    _backend, validation, _creation = services()
    token = validate_plan(validation)["planToken"]
    _new_backend, _new_validation, new_creation = services()
    with pytest.raises(PlanConflictError, match="invalid or unavailable"):
        new_creation.execute(
            "playlists.apple.create",
            {"planToken": token, "approved": True},
            RequestContext(backend_revision=7),
        )


def test_ticket_store_enforces_ttl_capacity_and_safe_token_generation(monkeypatch):
    for ttl in (0, 121):
        with pytest.raises(ValueError, match="lifetime"):
            PlanTicketStore(ttl_sec=ttl)

    invalid_tokens = PlanTicketStore(token_factory=lambda: "short")
    with pytest.raises(RuntimeError, match="unique playlist plan token"):
        invalid_tokens.issue(stored_plan())

    monkeypatch.setattr(
        "sonarchy_backend.domains.apple_playlist_plan.MAX_PENDING_PLAN_TICKETS",
        1,
    )
    bounded = PlanTicketStore(token_factory=token_factory())
    bounded.issue(stored_plan())
    with pytest.raises(PlanConflictError, match="Too many playlist plans"):
        bounded.issue(stored_plan())


def test_ticket_cannot_cross_operation_boundary_or_accept_malformed_value():
    backend = FakePlanBackend()
    tickets = PlanTicketStore(token_factory=token_factory())
    _validation, creation = ApplePlaylistPlanService(backend, tickets=tickets).services()
    ticket = tickets.issue(stored_plan(operation="another.operation"))
    with pytest.raises(PlanConflictError, match="another operation"):
        creation.execute(
            "playlists.apple.create",
            {"planToken": ticket.token, "approved": True},
            RequestContext(backend_revision=7),
        )
    with pytest.raises(PlanConflictError, match="invalid or unavailable"):
        tickets.claim("bad")


def test_revision_conflict_consumes_ticket_before_any_mutation():
    backend, validation, creation = services()
    token = validate_plan(validation)["planToken"]
    with pytest.raises(PlanConflictError, match="state changed"):
        creation.execute(
            "playlists.apple.create",
            {"planToken": token, "approved": True},
            RequestContext(backend_revision=8),
        )
    assert backend.executions == []
    with pytest.raises(PlanConflictError, match="already used"):
        creation.execute(
            "playlists.apple.create",
            {"planToken": token, "approved": True},
            RequestContext(backend_revision=7),
        )


def test_ticket_is_consumed_even_when_mutation_attempt_fails():
    backend, validation, creation = services()
    backend.failure = RuntimeError("private speaker detail at 192.168.1.2")
    token = validate_plan(validation)["planToken"]
    with pytest.raises(RuntimeError):
        creation.execute(
            "playlists.apple.create",
            {"planToken": token, "approved": True},
            RequestContext(backend_revision=7),
        )
    with pytest.raises(PlanConflictError, match="already used"):
        creation.execute(
            "playlists.apple.create",
            {"planToken": token, "approved": True},
            RequestContext(backend_revision=7),
        )


@pytest.mark.parametrize(
    "replacement",
    (
        {"roomUid": "R2"},
        {"playlistName": "Replacement"},
        {"mode": "save-and-play"},
        {"tracks": [TRACK_TWO, TRACK_ONE]},
    ),
)
def test_execution_rejects_room_name_mode_or_track_replacements(replacement):
    backend, validation, creation = services()
    token = validate_plan(validation)["planToken"]
    with pytest.raises(ValueError, match="only planToken and approved"):
        creation.execute(
            "playlists.apple.create",
            {"planToken": token, "approved": True, **replacement},
            RequestContext(backend_revision=7),
        )
    assert backend.executions == []


def test_distinct_room_order_mode_and_name_have_distinct_plan_bindings():
    _backend, validation, _creation = services()
    values = [
        validate_plan(validation, plan_args()),
        validate_plan(validation, plan_args(roomUid="R2")),
        validate_plan(validation, plan_args(tracks=[TRACK_TWO, TRACK_ONE])),
        validate_plan(validation, plan_args(mode="save-and-play")),
        validate_plan(validation, plan_args(playlistName="Another name")),
    ]
    assert len({value["planFingerprint"] for value in values}) == len(values)


def test_safe_media_fingerprint_is_bound_into_the_plan_fingerprint():
    backend, validation, _creation = services()
    first = validate_plan(validation)
    backend.states["R1"]["observedState"]["mediaFingerprint"] = f"sha256:{'b' * 64}"
    second = validate_plan(validation)

    assert first["planFingerprint"] != second["planFingerprint"]


def test_explicit_approval_is_checked_before_ticket_is_claimed():
    backend, validation, creation = services()
    token = validate_plan(validation)["planToken"]
    with pytest.raises(ValueError, match="Explicit approval"):
        creation.execute(
            "playlists.apple.create",
            {"planToken": token, "approved": False},
            RequestContext(backend_revision=7),
        )
    creation.execute(
        "playlists.apple.create",
        {"planToken": token, "approved": True},
        RequestContext(backend_revision=7),
    )
    assert len(backend.executions) == 1


def test_atomic_claim_allows_only_one_concurrent_execution():
    backend, validation, creation = services()
    token = validate_plan(validation)["planToken"]

    def execute():
        try:
            creation.execute(
                "playlists.apple.create",
                {"planToken": token, "approved": True},
                RequestContext(backend_revision=7),
            )
            return "success"
        except PlanConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _index: execute(), range(2)))
    assert sorted(outcomes) == ["conflict", "success"]
    assert len(backend.executions) == 1
