from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from soco.exceptions import SoCoUPnPException

from ..infrastructure.apple_saved_queue import DirectAppleSavedQueueAdapter
from .apple_retained_plan import RETENTION_MODE, validate_apple_song_items
from .common import clean, safe_index
from .errors import PlanConflictError, RetainedPlaylistTransactionError
from .media import item_attr, validate_playlist_id
from .playlist_rules import validate_playlist_title

MAX_SONOS_PLAYLISTS = 100
MAX_TRANSACTION_PLAYLISTS = MAX_SONOS_PLAYLISTS + 1
MAX_APPLE_PLAYLIST_ITEMS = 25
PLAYLIST_VISIBILITY_ATTEMPTS = 3
PLAYLIST_VISIBILITY_DELAY_SEC = 0.05
APPLE_CANONICAL_SONG_ID = re.compile(r"song(?::|%3a)([1-9]\d{0,19})", re.IGNORECASE)
APPLE_SONOS_ITEM_ID = re.compile(
    r"10032020song(?::|%3a)([1-9]\d{0,19})",
    re.IGNORECASE,
)
APPLE_SONOS_RESOURCE_URI = re.compile(
    r"x-sonos-https?:song(?::|%3a)([1-9]\d{0,19})(?=$|[./?&#])",
    re.IGNORECASE,
)
SONOS_ERROR_CODE = re.compile(r"(?:\d{1,6}|[A-Z][A-Z0-9_]{0,31})")


@dataclass(frozen=True)
class PlaylistInventory:
    items: tuple[Any, ...]
    entries: tuple[tuple[str, str], ...]
    ids: frozenset[str]
    titles: frozenset[str]
    fingerprint: str


@dataclass(frozen=True)
class TargetCapture:
    state: dict[str, Any]
    playlists: PlaylistInventory
    coordinator: Any


@dataclass(frozen=True)
class PlaylistObservation:
    playlist: Any | None
    status: str
    authoritative_reopen: bool
    observed_count: int | None
    verified_items: tuple[dict[str, Any], ...]


def _fingerprint(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _safe_identity(value: Any, label: str) -> str:
    identity = clean(value)
    if not identity or len(identity) > 128 or any(ord(character) < 32 for character in identity):
        raise PlanConflictError(f"The exact Sonos {label} could not be verified")
    return identity


def _anchor_state(speaker: Any) -> tuple[dict[str, str], Any]:
    room_uid = _safe_identity(getattr(speaker, "uid", ""), "room identity")
    try:
        group = speaker.group
        coordinator = (
            getattr(group, "coordinator", None) if group is not None else None
        ) or speaker
    except Exception as exc:
        raise PlanConflictError("The exact Sonos coordinator could not be verified") from exc
    coordinator_uid = _safe_identity(
        getattr(coordinator, "uid", ""),
        "coordinator identity",
    )
    try:
        room_household = _safe_identity(speaker.household_id, "household identity")
        coordinator_household = _safe_identity(
            coordinator.household_id,
            "household identity",
        )
    except PlanConflictError:
        raise
    except Exception as exc:
        raise PlanConflictError("The exact Sonos household identity could not be verified") from exc
    if room_household != coordinator_household:
        raise PlanConflictError("The Sonos room and coordinator household identities differ")
    return (
        {
            "uid": room_uid,
            "coordinatorUid": coordinator_uid,
            "householdFingerprint": f"sha256:{_fingerprint(room_household)}",
        },
        coordinator,
    )


def _playlist_inventory(
    coordinator: Any,
    *,
    maximum: int = MAX_SONOS_PLAYLISTS,
) -> PlaylistInventory:
    try:
        result = coordinator.get_sonos_playlists(max_items=maximum)
        items = list(result)
    except Exception as exc:
        raise PlanConflictError("Current Sonos Playlists could not be listed safely") from exc
    total = safe_index(item_attr(result, "total_matches", len(items)), -1)
    if total != len(items) or total > maximum:
        raise PlanConflictError("There are too many Sonos Playlists to check safely")
    entries: list[tuple[str, str]] = []
    for item in items:
        try:
            playlist_id = validate_playlist_id(item_attr(item, "item_id"))
            title = validate_playlist_title(item_attr(item, "title"))
        except ValueError as exc:
            raise PlanConflictError(
                "The Sonos Playlist inventory is not safely identifiable"
            ) from exc
        entries.append((playlist_id, title))
    if len({playlist_id for playlist_id, _title in entries}) != len(entries):
        raise PlanConflictError("The Sonos Playlist inventory contains duplicate identities")
    ordered = tuple(sorted(entries))
    return PlaylistInventory(
        items=tuple(items),
        entries=ordered,
        ids=frozenset(playlist_id for playlist_id, _title in ordered),
        titles=frozenset(title for _playlist_id, title in ordered),
        fingerprint=_fingerprint(ordered),
    )


def _required_capability(
    coordinator: Any,
    adapter_factory: Callable[[Any], Any],
) -> bool:
    methods = (
        "get_sonos_playlists",
        "create_sonos_playlist",
        "get_sonos_playlist_by_attr",
    )
    if not all(callable(getattr(coordinator, method, None)) for method in methods):
        return False
    try:
        adapter_factory(coordinator)
    except Exception:  # noqa: BLE001 - capability failure is deliberately collapsed
        return False
    return True


def _capture_target(
    speaker: Any,
    playlist_name: str,
    *,
    adapter_factory: Callable[[Any], Any] = DirectAppleSavedQueueAdapter,
) -> TargetCapture:
    room, coordinator = _anchor_state(speaker)
    if not _required_capability(coordinator, adapter_factory):
        raise PlanConflictError(
            "This Sonos household cannot retain direct Apple Sonos Playlists safely"
        )
    playlists = _playlist_inventory(coordinator)
    if len(playlists.items) >= MAX_SONOS_PLAYLISTS:
        raise PlanConflictError(
            "The bounded Sonos Playlist inventory is full; remove one before creating another"
        )
    if playlist_name in playlists.titles:
        raise PlanConflictError("A Sonos Playlist with that exact name already exists")
    observed = {
        "playlistCount": len(playlists.items),
        "playlistInventoryFingerprint": f"sha256:{playlists.fingerprint}",
        "capabilities": [
            "playlist_plan.apple.retained.validate",
            "playlists.apple.retained.create",
            "direct-apple-saved-queue-retained",
        ],
    }
    return TargetCapture(
        state={"room": room, "observedState": observed},
        playlists=playlists,
        coordinator=coordinator,
    )


def inspect_retained_apple_playlist_target(
    speaker: Any,
    playlist_name: str,
    *,
    adapter_factory: Callable[[Any], Any] = DirectAppleSavedQueueAdapter,
) -> dict[str, Any]:
    """Capture only household anchor and saved-playlist state for retained create."""

    return _capture_target(
        speaker,
        playlist_name,
        adapter_factory=adapter_factory,
    ).state


def apple_song_identity_from_item(item: Any) -> str:
    item_id = clean(item_attr(item, "item_id"))
    identities: set[str] = set()
    for pattern in (APPLE_CANONICAL_SONG_ID, APPLE_SONOS_ITEM_ID):
        match = pattern.fullmatch(item_id)
        if match is not None:
            identities.add(match.group(1))
    for resource in item_attr(item, "resources", []) or []:
        uri = clean(item_attr(resource, "uri"))
        match = APPLE_SONOS_RESOURCE_URI.match(uri)
        if match is not None:
            identities.add(match.group(1))
    return next(iter(identities)) if len(identities) == 1 else ""


def _metadata_matches(actual: str, expected: str) -> bool:
    def normalize(value: str) -> str:
        return " ".join(value.split()).casefold()

    return normalize(actual) == normalize(expected)


def _browse_exact_playlist(coordinator: Any, playlist: Any) -> tuple[list[Any], int] | None:
    try:
        result = coordinator.music_library.browse(
            ml_item=playlist,
            start=0,
            max_items=MAX_APPLE_PLAYLIST_ITEMS + 1,
            full_album_art_uri=False,
        )
        items = list(result)
    except Exception:  # noqa: BLE001 - provider details stay below the boundary
        return None
    total = safe_index(item_attr(result, "total_matches", -1), -1)
    if total != len(items) or total > MAX_APPLE_PLAYLIST_ITEMS:
        return None
    return items, total


def _observe_once(
    coordinator: Any,
    *,
    playlist_id: str,
    playlist_name: str,
    tracks: list[dict[str, Any]],
) -> PlaylistObservation:
    try:
        playlist = coordinator.get_sonos_playlist_by_attr("item_id", playlist_id)
    except Exception:  # noqa: BLE001 - provider details stay below the boundary
        return PlaylistObservation(None, "reopen_failed", False, None, ())
    if clean(item_attr(playlist, "item_id")) != playlist_id:
        return PlaylistObservation(None, "reopen_failed", False, None, ())
    if clean(item_attr(playlist, "title")) != playlist_name:
        return PlaylistObservation(playlist, "wrong_name", True, None, ())
    browsed = _browse_exact_playlist(coordinator, playlist)
    if browsed is None:
        return PlaylistObservation(playlist, "incomplete_inventory", True, None, ())
    items, count = browsed
    if count != len(tracks):
        status = "item_absent" if count < len(tracks) else "wrong_count"
        return PlaylistObservation(playlist, status, True, count, ())

    actual_identities = [apple_song_identity_from_item(item) for item in items]
    expected_identities = [str(track["catalogId"]) for track in tracks]
    if actual_identities != expected_identities:
        if all(actual_identities) and sorted(actual_identities) == sorted(expected_identities):
            status = "wrong_order"
        else:
            status = "identity_mismatch"
        return PlaylistObservation(playlist, status, True, count, ())

    verified: list[dict[str, Any]] = []
    for position, (item, track) in enumerate(zip(items, tracks, strict=True), 1):
        title = clean(item_attr(item, "title"))
        artist = clean(item_attr(item, "creator")) or clean(item_attr(item, "artist"))
        album = clean(item_attr(item, "album"))
        if not title or not artist or not album:
            return PlaylistObservation(playlist, "metadata_incomplete", True, count, ())
        if (
            not _metadata_matches(title, str(track["title"]))
            or not _metadata_matches(artist, str(track["artist"]))
            or not _metadata_matches(album, str(track["album"]))
        ):
            return PlaylistObservation(playlist, "metadata_mismatch", True, count, ())
        catalog_id = str(track["catalogId"])
        verified.append(
            {
                "position": position,
                "catalogId": catalog_id,
                "canonicalIdentity": f"song:{catalog_id}",
                "title": track["title"],
                "artist": track["artist"],
                "album": track["album"],
            }
        )
    return PlaylistObservation(playlist, "complete", True, count, tuple(verified))


def _observe_with_retry(
    coordinator: Any,
    *,
    playlist_id: str,
    playlist_name: str,
    tracks: list[dict[str, Any]],
    attempts: int,
    sleeper: Callable[[float], None],
) -> PlaylistObservation:
    observation = PlaylistObservation(None, "reopen_failed", False, None, ())
    for attempt in range(attempts):
        observation = _observe_once(
            coordinator,
            playlist_id=playlist_id,
            playlist_name=playlist_name,
            tracks=tracks,
        )
        if observation.status == "complete":
            return observation
        if attempt + 1 < attempts:
            sleeper(PLAYLIST_VISIBILITY_DELAY_SEC)
    return observation


def _preexisting_playlists_unchanged(
    current: PlaylistInventory,
    original: PlaylistInventory,
) -> bool:
    current_by_id = dict(current.entries)
    return all(current_by_id.get(playlist_id) == title for playlist_id, title in original.entries)


def _created_inventory_exact(
    current: PlaylistInventory,
    original: PlaylistInventory,
    *,
    playlist_id: str,
    playlist_name: str,
) -> bool:
    expected = tuple(sorted((*original.entries, (playlist_id, playlist_name))))
    return playlist_id not in original.ids and current.entries == expected


def _current_inventory_evidence(
    coordinator: Any,
    original: PlaylistInventory,
) -> tuple[PlaylistInventory | None, bool]:
    try:
        current = _playlist_inventory(coordinator, maximum=MAX_TRANSACTION_PLAYLISTS)
    except PlanConflictError:
        return None, False
    return current, _preexisting_playlists_unchanged(current, original)


def _safe_sonos_error_code(error: Exception) -> str | None:
    if not isinstance(error, SoCoUPnPException):
        return None
    raw = error.error_code
    if isinstance(raw, bool) or not isinstance(raw, (str, int)):
        return None
    value = str(raw).strip()
    return value if SONOS_ERROR_CODE.fullmatch(value) else None


def _reviewed_tracks(tracks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "position": position,
            "canonicalIdentity": f"song:{track['catalogId']}",
            "title": track["title"],
            "artist": track["artist"],
            "album": track["album"],
        }
        for position, track in enumerate(tracks, 1)
    ]


def _initial_track_results(tracks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "position": position,
            "canonicalIdentity": f"song:{track['catalogId']}",
            "addCallReturned": False,
            "verificationStatus": "not_started",
        }
        for position, track in enumerate(tracks, 1)
    ]


def create_retained_apple_playlist(
    speaker: Any,
    plan: dict[str, Any],
    *,
    adapter_factory: Callable[[Any], Any] = DirectAppleSavedQueueAdapter,
    verification_attempts: int = PLAYLIST_VISIBILITY_ATTEMPTS,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Create and retain one direct Apple saved playlist, including partial results."""

    room_uid = str(plan.get("roomUid", ""))
    try:
        playlist_name = validate_playlist_title(plan["playlistName"])
    except (KeyError, ValueError) as exc:
        raise PlanConflictError("The retained playlist plan name is no longer valid") from exc
    if (
        plan.get("operation") != "playlists.apple.retained.create"
        or plan.get("retentionMode") != RETENTION_MODE
    ):
        raise PlanConflictError("The plan no longer matches retained direct creation")
    allow_duplicates = plan.get("allowDuplicates") is True
    validated_tracks = validate_apple_song_items(
        plan.get("tracks"),
        allow_duplicates=allow_duplicates,
    )
    tracks = [track.backend_value() for track in validated_tracks]
    expected_state = plan.get("targetState")
    if not isinstance(expected_state, dict):
        raise PlanConflictError("The retained playlist plan state is unavailable")
    if not 1 <= verification_attempts <= PLAYLIST_VISIBILITY_ATTEMPTS:
        raise ValueError("Invalid saved-playlist verification retry policy")
    if clean(getattr(speaker, "uid", "")) != room_uid:
        raise PlanConflictError("The exact target room no longer matches the retained plan")

    capture = _capture_target(
        speaker,
        playlist_name,
        adapter_factory=adapter_factory,
    )
    if capture.state != expected_state:
        raise PlanConflictError(
            "The household anchor, playlist inventory, or retained capability changed",
            details={"reason": "preflight_state_changed"},
        )
    coordinator = capture.coordinator
    adapter = adapter_factory(coordinator)
    reviewed_tracks = _reviewed_tracks(tracks)
    track_results = _initial_track_results(tracks)

    step = "create"
    create_call_returned = False
    add_call_returned = False
    attributable_playlist_id = ""
    observation = PlaylistObservation(None, "not_started", False, None, ())
    failed_position: int | None = None
    failed_identity: str | None = None

    try:
        created = coordinator.create_sonos_playlist(playlist_name)
        create_call_returned = True
        created_playlist_id = validate_playlist_id(item_attr(created, "item_id"))
        if created_playlist_id in capture.playlists.ids:
            raise ValueError("Sonos returned a pre-existing Sonos Playlist identity")
        attributable_playlist_id = created_playlist_id
        if clean(item_attr(created, "title")) != playlist_name:
            observation = PlaylistObservation(created, "wrong_name", False, None, ())
            raise ValueError("Sonos returned a playlist with an unexpected name")

        step = "verify_empty"
        observation = _observe_with_retry(
            coordinator,
            playlist_id=created_playlist_id,
            playlist_name=playlist_name,
            tracks=[],
            attempts=verification_attempts,
            sleeper=sleeper,
        )
        if observation.status != "complete":
            raise ValueError("The empty retained Sonos Playlist could not be verified")
        current_inventory, preexisting_unchanged = _current_inventory_evidence(
            coordinator,
            capture.playlists,
        )
        if (
            current_inventory is None
            or not preexisting_unchanged
            or not _created_inventory_exact(
                current_inventory,
                capture.playlists,
                playlist_id=created_playlist_id,
                playlist_name=playlist_name,
            )
        ):
            observation = PlaylistObservation(
                observation.playlist,
                "inventory_changed",
                observation.authoritative_reopen,
                observation.observed_count,
                observation.verified_items,
            )
            raise ValueError("The retained Sonos Playlist inventory changed unexpectedly")

        active_playlist = observation.playlist
        for failed_position, track in enumerate(tracks, 1):
            failed_identity = f"song:{track['catalogId']}"
            step = "add_track"
            add_call_returned = False
            adapter.add_track(active_playlist, track)
            add_call_returned = True
            track_results[failed_position - 1]["addCallReturned"] = True

            step = "verify_track"
            observation = _observe_with_retry(
                coordinator,
                playlist_id=created_playlist_id,
                playlist_name=playlist_name,
                tracks=tracks[:failed_position],
                attempts=verification_attempts,
                sleeper=sleeper,
            )
            track_results[failed_position - 1]["verificationStatus"] = observation.status
            if observation.status != "complete":
                raise ValueError("The newly added Apple song could not be verified")
            active_playlist = observation.playlist

        step = "verify_playlist"
        observation = _observe_with_retry(
            coordinator,
            playlist_id=created_playlist_id,
            playlist_name=playlist_name,
            tracks=tracks,
            attempts=verification_attempts,
            sleeper=sleeper,
        )
        if observation.status != "complete":
            raise ValueError("The retained Apple Sonos Playlist could not be verified")
        final_inventory, preexisting_unchanged = _current_inventory_evidence(
            coordinator,
            capture.playlists,
        )
        if (
            final_inventory is None
            or not preexisting_unchanged
            or not _created_inventory_exact(
                final_inventory,
                capture.playlists,
                playlist_id=created_playlist_id,
                playlist_name=playlist_name,
            )
        ):
            observation = PlaylistObservation(
                observation.playlist,
                "inventory_changed",
                observation.authoritative_reopen,
                observation.observed_count,
                observation.verified_items,
            )
            raise ValueError("The final Sonos Playlist inventory changed unexpectedly")
        return {
            "ok": True,
            "action": "create-retained-apple-sonos-playlist",
            "retentionMode": RETENTION_MODE,
            "room": expected_state["room"],
            "playlist": {
                "id": created_playlist_id,
                "name": playlist_name,
                "itemCount": len(observation.verified_items),
                "items": list(observation.verified_items),
            },
            "reviewedTracks": reviewed_tracks,
            "trackResults": track_results,
            "createCallReturned": True,
            "authoritativeReopen": True,
            "observedItemCount": observation.observed_count,
            "verificationStatus": "complete",
            "playlistRetained": True,
            "manualInspectionRequired": False,
            "preExistingPlaylistsUnchanged": True,
            "queueMutation": False,
            "playbackMutation": False,
            "succeeded": True,
        }
    except Exception as exc:
        if failed_position is not None and step == "add_track":
            track_results[failed_position - 1]["verificationStatus"] = "add_rejected"
            retained_observation = _observe_with_retry(
                coordinator,
                playlist_id=attributable_playlist_id,
                playlist_name=playlist_name,
                tracks=tracks[: failed_position - 1],
                attempts=verification_attempts,
                sleeper=sleeper,
            )
            observation = PlaylistObservation(
                retained_observation.playlist,
                "add_rejected",
                retained_observation.authoritative_reopen,
                retained_observation.observed_count,
                retained_observation.verified_items,
            )
        current_inventory, preexisting_unchanged = _current_inventory_evidence(
            coordinator,
            capture.playlists,
        )
        playlist_retained = bool(attributable_playlist_id)
        diagnostics: dict[str, Any] = {
            "playlistName": playlist_name,
            "playlistConstructionStep": step,
            "createCallReturned": create_call_returned,
            "addCallReturned": add_call_returned,
            "authoritativeReopen": observation.authoritative_reopen,
            "verificationStatus": observation.status,
            "playlistRetained": playlist_retained,
            "manualInspectionRequired": True,
            "preExistingPlaylistsUnchanged": preexisting_unchanged,
            "queueMutation": False,
            "playbackMutation": False,
            "succeeded": False,
            "reviewedTracks": reviewed_tracks,
            "trackResults": track_results,
        }
        if attributable_playlist_id:
            diagnostics["partialPlaylistId"] = attributable_playlist_id
        if observation.observed_count is not None:
            diagnostics["observedItemCount"] = observation.observed_count
        if failed_position is not None and step in {"add_track", "verify_track"}:
            diagnostics["failedTrackPosition"] = failed_position
            diagnostics["failedCanonicalIdentity"] = failed_identity
        sonos_error_code = _safe_sonos_error_code(exc)
        if sonos_error_code is not None:
            diagnostics["sonosErrorCode"] = sonos_error_code
        raise RetainedPlaylistTransactionError(diagnostics) from exc
