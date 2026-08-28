from __future__ import annotations

import copy
import hashlib
import json
import re
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..apple_catalog import canonical_apple_song
from ..contracts import (
    MAX_PROTOCOL_LINE_BYTES,
    MAX_PROTOCOL_REQUEST_ID_BYTES,
    protocol_line,
    result_payload,
)
from .common import DomainService, RequestContext, bool_arg, string_arg
from .errors import PlanConflictError
from .playlist_rules import validate_playlist_title
from .ports import ApplePlaylistPlansPort

MAX_APPLE_PLAN_TRACKS = 25
MAX_TRACK_TEXT_LENGTH = 240
MAX_TRACK_DURATION_MS = 24 * 60 * 60 * 1000
PLAN_TICKET_TTL_SEC = 120
MAX_PENDING_PLAN_TICKETS = 256
MAX_CONSUMED_PLAN_TICKETS = 1024
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{16,256}")
PLAN_MODES = frozenset({"save-only", "save-and-play"})
TRACK_FIELDS = frozenset({"catalogId", "url", "title", "artist", "album", "durationMs"})


@dataclass(frozen=True)
class AppleSongPlanItem:
    catalog_id: str
    url: str
    title: str
    artist: str
    album: str
    duration_ms: int

    @property
    def canonical_identity(self) -> str:
        return f"song:{self.catalog_id}"

    def public_value(self, position: int) -> dict[str, Any]:
        return {
            "position": position,
            "catalogId": self.catalog_id,
            "canonicalContentType": "song",
            "canonicalIdentity": self.canonical_identity,
            "url": self.url,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "durationMs": self.duration_ms,
        }

    def backend_value(self) -> dict[str, Any]:
        return {
            "catalogId": self.catalog_id,
            "url": self.url,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "durationMs": self.duration_ms,
        }


@dataclass(frozen=True)
class ApplePlaylistPlan:
    operation: str
    room_uid: str
    playlist_name: str
    mode: str
    allow_duplicates: bool
    tracks: tuple[AppleSongPlanItem, ...]
    target_state: dict[str, Any]
    backend_revision: int
    plan_fingerprint: str

    def backend_value(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "roomUid": self.room_uid,
            "playlistName": self.playlist_name,
            "mode": self.mode,
            "allowDuplicates": self.allow_duplicates,
            "tracks": [track.backend_value() for track in self.tracks],
            "targetState": copy.deepcopy(self.target_state),
            "backendRevision": self.backend_revision,
            "planFingerprint": self.plan_fingerprint,
        }


@dataclass(frozen=True)
class PlanTicket:
    token: str
    plan: ApplePlaylistPlan
    expires_monotonic: float
    expires_epoch_ms: int


class PlanTicketStore:
    """Bounded process-local, atomically claimed execution tickets."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
        token_factory: Callable[[], str] | None = None,
        ttl_sec: int = PLAN_TICKET_TTL_SEC,
    ) -> None:
        if not 1 <= ttl_sec <= PLAN_TICKET_TTL_SEC:
            raise ValueError("Plan ticket lifetime must be between 1 and 120 seconds")
        self._clock = clock
        self._wall_clock = wall_clock
        self._token_factory = token_factory or (lambda: secrets.token_urlsafe(32))
        self._ttl_sec = ttl_sec
        self._pending: dict[str, PlanTicket] = {}
        self._consumed: dict[str, float] = {}
        self._lock = threading.Lock()

    def _prune(self, now: float) -> None:
        self._consumed = {token: expiry for token, expiry in self._consumed.items() if expiry > now}
        expired = [
            token for token, ticket in self._pending.items() if ticket.expires_monotonic <= now
        ]
        for token in expired:
            self._pending.pop(token, None)

    def issue(self, plan: ApplePlaylistPlan) -> PlanTicket:
        now = self._clock()
        with self._lock:
            self._prune(now)
            if len(self._pending) >= MAX_PENDING_PLAN_TICKETS:
                raise PlanConflictError("Too many playlist plans are awaiting execution")
            token = ""
            for _attempt in range(3):
                candidate = self._token_factory()
                if (
                    TOKEN_PATTERN.fullmatch(candidate)
                    and candidate not in self._pending
                    and candidate not in self._consumed
                ):
                    token = candidate
                    break
            if not token:
                raise RuntimeError("A unique playlist plan token could not be issued")
            ticket = PlanTicket(
                token=token,
                plan=copy.deepcopy(plan),
                expires_monotonic=now + self._ttl_sec,
                expires_epoch_ms=int((self._wall_clock() + self._ttl_sec) * 1000),
            )
            self._pending[token] = ticket
            return ticket

    def claim(self, raw_token: Any) -> ApplePlaylistPlan:
        token = str(raw_token or "")
        if not TOKEN_PATTERN.fullmatch(token):
            raise PlanConflictError("The playlist plan token is invalid or unavailable")
        now = self._clock()
        with self._lock:
            if token in self._consumed:
                raise PlanConflictError("The playlist plan token was already used")
            ticket = self._pending.pop(token, None)
            if ticket is None:
                self._prune(now)
                raise PlanConflictError("The playlist plan token is invalid or unavailable")
            self._consumed[token] = now + self._ttl_sec
            while len(self._consumed) > MAX_CONSUMED_PLAN_TICKETS:
                self._consumed.pop(next(iter(self._consumed)))
            if ticket.expires_monotonic <= now:
                raise PlanConflictError("The playlist plan token expired; validate a new plan")
            return copy.deepcopy(ticket.plan)

    def cancel_unpublished(self, token: str) -> None:
        """Discard a ticket whose bounded review could not be returned to its caller."""

        with self._lock:
            self._pending.pop(token, None)


def _bounded_track_text(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Track {label} must be a string")
    text = value.strip()
    if (
        not text
        or len(text.encode("utf-8")) > MAX_TRACK_TEXT_LENGTH
        or any(ord(character) < 32 for character in text)
    ):
        raise ValueError(f"Track {label} is empty, too long, or contains control characters")
    return text


def validate_apple_song_items(
    raw_tracks: Any,
    *,
    allow_duplicates: bool,
) -> tuple[AppleSongPlanItem, ...]:
    if not isinstance(raw_tracks, list) or not raw_tracks:
        raise ValueError("tracks must be a non-empty list")
    if len(raw_tracks) > MAX_APPLE_PLAN_TRACKS:
        raise ValueError("An Apple playlist plan can contain at most 25 tracks")
    tracks: list[AppleSongPlanItem] = []
    identities: set[str] = set()
    for raw_track in raw_tracks:
        if not isinstance(raw_track, dict) or set(raw_track) != TRACK_FIELDS:
            raise ValueError("Each track must contain only the reviewed Apple song fields")
        url, canonical_id = canonical_apple_song(raw_track.get("url"), raw_track.get("catalogId"))
        identity = f"song:{canonical_id}"
        if identity in identities and not allow_duplicates:
            raise ValueError("Duplicate Apple song identities require allowDuplicates: true")
        identities.add(identity)
        duration_ms = raw_track.get("durationMs")
        if (
            isinstance(duration_ms, bool)
            or not isinstance(duration_ms, int)
            or not 1 <= duration_ms <= MAX_TRACK_DURATION_MS
        ):
            raise ValueError("Track durationMs must be a bounded positive integer")
        tracks.append(
            AppleSongPlanItem(
                catalog_id=canonical_id,
                url=url,
                title=_bounded_track_text(raw_track.get("title"), "title"),
                artist=_bounded_track_text(raw_track.get("artist"), "artist"),
                album=_bounded_track_text(raw_track.get("album"), "album"),
                duration_ms=duration_ms,
            )
        )
    return tuple(tracks)


def _plan_fingerprint(
    *,
    room_uid: str,
    playlist_name: str,
    mode: str,
    allow_duplicates: bool,
    tracks: tuple[AppleSongPlanItem, ...],
    target_state: dict[str, Any],
    backend_revision: int,
) -> str:
    binding = {
        "operation": "playlists.apple.create",
        "roomUid": room_uid,
        "playlistName": playlist_name,
        "mode": mode,
        "allowDuplicates": allow_duplicates,
        "tracks": [track.backend_value() for track in tracks],
        "targetState": target_state,
        "backendRevision": backend_revision,
    }
    encoded = json.dumps(binding, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class ApplePlaylistPlanService:
    def __init__(
        self,
        backend: ApplePlaylistPlansPort,
        *,
        tickets: PlanTicketStore | None = None,
    ) -> None:
        self.backend = backend
        self.tickets = tickets or PlanTicketStore()

    def services(self) -> tuple[DomainService, DomainService]:
        validate = DomainService(
            {},
            mutates=False,
            contextual_handlers={"playlist_plan.apple.validate": self.validate},
        )
        create = DomainService(
            {},
            contextual_handlers={"playlists.apple.create": self.create},
        )
        return validate, create

    def validate(self, args: dict[str, Any], context: RequestContext) -> dict[str, Any]:
        allowed = {"roomUid", "playlistName", "mode", "tracks", "allowDuplicates"}
        if set(args) - allowed:
            raise ValueError("Playlist plan contains unsupported arguments")
        room_uid = string_arg(args, "roomUid").strip()
        playlist_name = validate_playlist_title(args.get("playlistName"))
        mode = string_arg(args, "mode")
        if mode not in PLAN_MODES:
            raise ValueError("Unsupported Apple playlist plan mode")
        allow_duplicates = bool_arg(args, "allowDuplicates") if "allowDuplicates" in args else False
        tracks = validate_apple_song_items(args.get("tracks"), allow_duplicates=allow_duplicates)
        target_state = self.backend.inspect_apple_playlist_target(room_uid, playlist_name)
        fingerprint = _plan_fingerprint(
            room_uid=room_uid,
            playlist_name=playlist_name,
            mode=mode,
            allow_duplicates=allow_duplicates,
            tracks=tracks,
            target_state=target_state,
            backend_revision=context.backend_revision,
        )
        plan = ApplePlaylistPlan(
            operation="playlists.apple.create",
            room_uid=room_uid,
            playlist_name=playlist_name,
            mode=mode,
            allow_duplicates=allow_duplicates,
            tracks=tracks,
            target_state=copy.deepcopy(target_state),
            backend_revision=context.backend_revision,
            plan_fingerprint=fingerprint,
        )
        ticket = self.tickets.issue(plan)
        side_effects = [
            "Temporarily replace the target queue",
            "Create one new Sonos Playlist",
        ]
        if mode == "save-only":
            side_effects.append("Restore and verify the previous queue and playing state")
        else:
            side_effects.append("Leave the approved queue active and start track 1")
        review = {
            "ok": True,
            "operation": plan.operation,
            "planToken": ticket.token,
            "planFingerprint": f"sha256:{fingerprint}",
            "expiresAtEpochMs": ticket.expires_epoch_ms,
            "expiresInSec": PLAN_TICKET_TTL_SEC,
            "approvalRequired": True,
            "room": copy.deepcopy(target_state["room"]),
            "observedState": copy.deepcopy(target_state["observedState"]),
            "playlist": {"name": playlist_name, "collision": False},
            "mode": mode,
            "allowDuplicates": allow_duplicates,
            "trackCount": len(tracks),
            "totalDurationMs": sum(track.duration_ms for track in tracks),
            "tracks": [track.public_value(index) for index, track in enumerate(tracks, 1)],
            "expectedSideEffects": side_effects,
        }
        worst_case_request_id = "\\" * MAX_PROTOCOL_REQUEST_ID_BYTES
        envelope = result_payload(
            worst_case_request_id,
            revision=context.backend_revision,
            value=review,
        )
        if len(protocol_line(envelope).encode("utf-8")) > MAX_PROTOCOL_LINE_BYTES:
            self.tickets.cancel_unpublished(ticket.token)
            raise ValueError("The playlist plan review is too large for the protocol")
        return review

    def create(self, args: dict[str, Any], context: RequestContext) -> dict[str, Any]:
        if set(args) != {"planToken", "approved"}:
            raise ValueError("Execution accepts only planToken and approved")
        if args.get("approved") is not True:
            raise ValueError("Explicit approval is required immediately before execution")
        plan = self.tickets.claim(args.get("planToken"))
        if plan.operation != "playlists.apple.create":
            raise PlanConflictError("The plan token is bound to another operation")
        if context.backend_revision != plan.backend_revision:
            raise PlanConflictError(
                "Backend state changed after validation; validate a new playlist plan",
                details={"reason": "backend_revision_changed"},
            )
        return self.backend.create_preflighted_apple_playlist(plan.backend_value())
