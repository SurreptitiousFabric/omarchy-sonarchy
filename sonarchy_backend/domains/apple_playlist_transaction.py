from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from soco.exceptions import SoCoUPnPException

from ..contracts import (
    MAX_PROTOCOL_LINE_BYTES,
    MAX_PROTOCOL_REQUEST_ID_BYTES,
    protocol_line,
    result_payload,
)
from ..infrastructure.apple_saved_queue import (
    DirectAppleSavedQueueAdapter,
    apple_saved_queue_song_identity,
)
from .apple_playlist_plan import MAX_TRACK_TEXT_LENGTH, validate_apple_song_items
from .common import clean, safe_index
from .errors import PlanConflictError, PlaylistTransactionError
from .media import MAX_PLAYLIST_ID_LENGTH, item_attr, validate_playlist_id
from .playlist_rules import suggested_playlist_title, validate_playlist_title

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

# One sanitized, physically observed display mapping; this is not a provider-wide rule.
APPLE_ALBUM_DISPLAY_EVIDENCE = (
    "1452806384",
    "Just Like Heaven",
    "The Cure",
    "Kiss Me, Kiss Me, Kiss Me",
    "Kiss Me Kiss Me Kiss Me (Deluxe Edition)",
)


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
    total = safe_index(item_attr(result, "total_matches", len(items)), len(items))
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


def _required_capability(coordinator: Any) -> bool:
    methods = (
        "get_sonos_playlists",
        "create_sonos_playlist",
        "get_sonos_playlist_by_attr",
        "remove_sonos_playlist",
    )
    if not all(callable(getattr(coordinator, method, None)) for method in methods):
        return False
    try:
        DirectAppleSavedQueueAdapter(coordinator)
    except Exception:  # noqa: BLE001 - capability failure is deliberately collapsed
        return False
    return True


def _capture_target(speaker: Any, playlist_name: str) -> TargetCapture:
    room, coordinator = _anchor_state(speaker)
    if not _required_capability(coordinator):
        raise PlanConflictError(
            "This Sonos household cannot create direct Apple Sonos Playlists safely"
        )
    playlists = _playlist_inventory(coordinator)
    if len(playlists.items) >= MAX_SONOS_PLAYLISTS:
        raise PlanConflictError(
            "The bounded Sonos Playlist inventory is full; remove one before creating another"
        )
    if playlist_name in playlists.titles:
        suggestion = suggested_playlist_title(playlist_name, set(playlists.titles))
        raise PlanConflictError(
            "A Sonos Playlist with that exact name already exists",
            details={"suggestedPlaylistName": suggestion},
        )
    observed = {
        "playlistCount": len(playlists.items),
        "playlistInventoryFingerprint": f"sha256:{playlists.fingerprint}",
        "capabilities": [
            "playlist_plan.apple.validate",
            "playlists.apple.create",
            "direct-apple-saved-queue",
        ],
    }
    return TargetCapture(
        state={"room": room, "observedState": observed},
        playlists=playlists,
        coordinator=coordinator,
    )


def inspect_apple_playlist_target(speaker: Any, playlist_name: str) -> dict[str, Any]:
    """Capture only household anchor and Sonos Playlist state for create-only."""

    return _capture_target(speaker, playlist_name).state


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
        saved_queue_identity = apple_saved_queue_song_identity(resource)
        if saved_queue_identity:
            identities.add(saved_queue_identity)
    return next(iter(identities)) if len(identities) == 1 else ""


def _metadata_matches(actual: str, expected: str) -> bool:
    def normalize(value: str) -> str:
        return " ".join(value.split()).casefold()

    return normalize(actual) == normalize(expected)


def _observed_album(value: Any, container: str) -> str:
    album = clean(value)
    if not album:
        raise ValueError(f"The {container} did not provide complete reviewed metadata")
    if (
        any(ord(character) < 32 for character in album)
        or len(album.encode("utf-8")) > MAX_TRACK_TEXT_LENGTH
    ):
        raise ValueError(f"The {container} did not provide safe reviewed metadata")
    return album


def _album_verification_kind(
    catalog_id: str,
    title: str,
    artist: str,
    observed_album: str,
    track: dict[str, Any],
) -> str | None:
    if _metadata_matches(observed_album, track["album"]):
        return "exact"
    evidence_id, evidence_title, evidence_artist, reviewed_album, evidence_album = (
        APPLE_ALBUM_DISPLAY_EVIDENCE
    )
    if (
        catalog_id == evidence_id
        and _metadata_matches(title, evidence_title)
        and _metadata_matches(track["title"], evidence_title)
        and _metadata_matches(artist, evidence_artist)
        and _metadata_matches(track["artist"], evidence_artist)
        and _metadata_matches(track["album"], reviewed_album)
        and _metadata_matches(observed_album, evidence_album)
    ):
        return "evidence_bound"
    return None


def _ensure_create_result_fits_protocol(
    tracks: list[dict[str, Any]],
    *,
    playlist_name: str,
    room: dict[str, Any],
) -> None:
    worst_observed_album = "\\" * MAX_TRACK_TEXT_LENGTH
    worst_playlist_id = "SQ:" + ("9" * (MAX_PLAYLIST_ID_LENGTH - len("SQ:")))
    items = [
        {
            "position": position,
            "catalogId": track["catalogId"],
            "canonicalIdentity": f"song:{track['catalogId']}",
            "title": track["title"],
            "artist": track["artist"],
            "album": track["album"],
            "albumVerification": {
                "kind": "evidence_bound",
                "reviewedAlbum": track["album"],
                "observedAlbum": worst_observed_album,
            },
        }
        for position, track in enumerate(tracks, 1)
    ]
    projected = {
        "ok": True,
        "action": "create-apple-sonos-playlist",
        "room": room,
        "playlist": {
            "id": worst_playlist_id,
            "name": playlist_name,
            "itemCount": len(items),
            "items": items,
        },
        "queueMutation": False,
        "playbackMutation": False,
        "verification": {
            "authoritativeReopen": True,
            "preExistingPlaylistsUnchanged": True,
        },
    }
    envelope = result_payload(
        "\\" * MAX_PROTOCOL_REQUEST_ID_BYTES,
        revision=sys.maxsize,
        value=projected,
    )
    if len(protocol_line(envelope).encode("utf-8")) > MAX_PROTOCOL_LINE_BYTES:
        raise PlanConflictError("The playlist result would exceed the protocol limit")


def verify_apple_items(
    items: list[Any] | tuple[Any, ...],
    tracks: list[dict[str, Any]],
    *,
    container: str,
) -> list[dict[str, Any]]:
    if len(items) != len(tracks):
        raise ValueError(f"The {container} expanded to an unexpected item count")
    verified: list[dict[str, Any]] = []
    for position, (item, track) in enumerate(zip(items, tracks, strict=True), 1):
        catalog_id = apple_song_identity_from_item(item)
        if not catalog_id or catalog_id != track["catalogId"]:
            raise ValueError(f"The {container} contains an unexpected Apple song identity")
        title = clean(item_attr(item, "title"))
        artist = clean(item_attr(item, "creator")) or clean(item_attr(item, "artist"))
        album = _observed_album(item_attr(item, "album"), container)
        if not title or not artist:
            raise ValueError(f"The {container} did not provide complete reviewed metadata")
        if not _metadata_matches(title, track["title"]) or not _metadata_matches(
            artist, track["artist"]
        ):
            raise ValueError(f"The {container} metadata does not match the reviewed song")
        album_kind = _album_verification_kind(catalog_id, title, artist, album, track)
        if album_kind is None:
            raise ValueError(f"The {container} metadata does not match the reviewed song")
        verified.append(
            {
                "position": position,
                "catalogId": catalog_id,
                "canonicalIdentity": f"song:{catalog_id}",
                "title": track["title"],
                "artist": track["artist"],
                "album": track["album"],
                "albumVerification": {
                    "kind": album_kind,
                    "reviewedAlbum": track["album"],
                    "observedAlbum": album,
                },
            }
        )
    return verified


def _safe_sonos_error_code(error: Exception) -> str | None:
    if not isinstance(error, SoCoUPnPException):
        return None
    raw = error.error_code
    if isinstance(raw, bool) or not isinstance(raw, (str, int)):
        return None
    value = str(raw).strip()
    return value if SONOS_ERROR_CODE.fullmatch(value) else None


def _inventory_preserves_original(
    current: PlaylistInventory,
    original: PlaylistInventory,
    *,
    owned_playlist_id: str = "",
) -> bool:
    current_entries = tuple(entry for entry in current.entries if entry[0] != owned_playlist_id)
    return current_entries == original.entries


def _browse_exact_playlist(coordinator: Any, playlist: Any) -> tuple[list[Any], int]:
    result = coordinator.music_library.browse(
        ml_item=playlist,
        start=0,
        max_items=MAX_APPLE_PLAYLIST_ITEMS + 1,
        full_album_art_uri=False,
    )
    items = list(result)
    total = safe_index(item_attr(result, "total_matches", len(items)), len(items))
    if total != len(items) or total > MAX_APPLE_PLAYLIST_ITEMS:
        raise ValueError("The saved Sonos Playlist could not be reopened completely")
    return items, total


def _reopen_and_verify(
    coordinator: Any,
    *,
    playlist_id: str,
    playlist_name: str,
    tracks: list[dict[str, Any]],
    attempts: int,
    sleeper: Callable[[float], None],
) -> tuple[Any, list[dict[str, Any]]]:
    failure: Exception | None = None
    for attempt in range(attempts):
        try:
            playlist = coordinator.get_sonos_playlist_by_attr("item_id", playlist_id)
            if clean(item_attr(playlist, "title")) != playlist_name:
                raise ValueError("The saved Sonos Playlist reopened with another name")
            items, total = _browse_exact_playlist(coordinator, playlist)
            if total != len(tracks):
                raise ValueError("The saved Sonos Playlist has an unexpected item count")
            return playlist, verify_apple_items(
                items,
                tracks,
                container="saved Sonos Playlist",
            )
        except Exception as exc:  # noqa: BLE001 - bounded retry hides provider details
            failure = exc
            if attempt + 1 < attempts:
                sleeper(PLAYLIST_VISIBILITY_DELAY_SEC)
    raise ValueError("The saved Sonos Playlist could not be verified authoritatively") from failure


def _verify_created_inventory(
    coordinator: Any,
    *,
    original: PlaylistInventory,
    playlist_id: str,
    playlist_name: str,
) -> bool:
    inventory = _playlist_inventory(coordinator, maximum=MAX_TRANSACTION_PLAYLISTS)
    expected_entry = (playlist_id, playlist_name)
    return (
        playlist_id not in original.ids
        and inventory.entries.count(expected_entry) == 1
        and len(inventory.entries) == len(original.entries) + 1
        and _inventory_preserves_original(
            inventory,
            original,
            owned_playlist_id=playlist_id,
        )
    )


def _cleanup_owned_playlist(
    coordinator: Any,
    *,
    original: PlaylistInventory,
    playlist_id: str,
    supporting_titles: frozenset[str],
) -> tuple[bool, bool]:
    if playlist_id in original.ids:
        return False, False
    inventory = _playlist_inventory(coordinator, maximum=MAX_TRANSACTION_PLAYLISTS)
    candidates = [
        item
        for item in inventory.items
        if clean(item_attr(item, "item_id")) == playlist_id
        and clean(item_attr(item, "title")) in supporting_titles
    ]
    if len(candidates) != 1:
        original_preserved = _inventory_preserves_original(
            inventory,
            original,
            owned_playlist_id=playlist_id,
        )
        return playlist_id not in inventory.ids and original_preserved, original_preserved
    reopened = coordinator.get_sonos_playlist_by_attr("item_id", playlist_id)
    if (
        clean(item_attr(reopened, "item_id")) != playlist_id
        or clean(item_attr(reopened, "title")) not in supporting_titles
    ):
        return False, False
    coordinator.remove_sonos_playlist(reopened)
    after = _playlist_inventory(coordinator, maximum=MAX_TRANSACTION_PLAYLISTS)
    return playlist_id not in after.ids, _inventory_preserves_original(after, original)


def create_preflighted_apple_playlist(
    speaker: Any,
    plan: dict[str, Any],
    *,
    adapter_factory: Callable[[Any], Any] = DirectAppleSavedQueueAdapter,
    verification_attempts: int = PLAYLIST_VISIBILITY_ATTEMPTS,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    room_uid = str(plan["roomUid"])
    try:
        playlist_name = validate_playlist_title(plan["playlistName"])
    except (KeyError, ValueError) as exc:
        raise PlanConflictError("The playlist plan name is no longer valid") from exc
    if plan.get("operation") != "playlists.apple.create" or plan.get("mode") != "save-only":
        raise PlanConflictError("The playlist plan no longer matches create-only execution")
    allow_duplicates = plan.get("allowDuplicates") is True
    validated_tracks = validate_apple_song_items(
        plan.get("tracks"),
        allow_duplicates=allow_duplicates,
    )
    tracks = [track.backend_value() for track in validated_tracks]
    expected_state = dict(plan["targetState"])
    if not 1 <= verification_attempts <= PLAYLIST_VISIBILITY_ATTEMPTS:
        raise ValueError("Invalid saved-playlist verification retry policy")
    if clean(getattr(speaker, "uid", "")) != room_uid:
        raise PlanConflictError("The exact target room no longer matches the playlist plan")
    capture = _capture_target(speaker, playlist_name)
    if capture.state != expected_state:
        raise PlanConflictError(
            "The room, household anchor, playlist inventory, or direct capability changed",
            details={"reason": "preflight_state_changed"},
        )
    _ensure_create_result_fits_protocol(
        tracks,
        playlist_name=playlist_name,
        room=expected_state["room"],
    )

    coordinator = capture.coordinator
    adapter = adapter_factory(coordinator)
    construction_step = "create"
    failed_position: int | None = None
    failed_identity: str | None = None
    creation_attempted = False
    attributable_playlist_id = ""
    cleanup_titles = frozenset({playlist_name})
    playlist_removed = False
    pre_existing_unchanged = True
    try:
        creation_attempted = True
        created = coordinator.create_sonos_playlist(playlist_name)
        created_playlist_id = validate_playlist_id(item_attr(created, "item_id"))
        if created_playlist_id in capture.playlists.ids:
            raise ValueError("Sonos returned a pre-existing Sonos Playlist identity")
        attributable_playlist_id = created_playlist_id
        try:
            returned_title = validate_playlist_title(item_attr(created, "title"))
        except ValueError:
            returned_title = ""
        if returned_title:
            cleanup_titles = frozenset({playlist_name, returned_title})

        created, _empty_evidence = _reopen_and_verify(
            coordinator,
            playlist_id=created_playlist_id,
            playlist_name=playlist_name,
            tracks=[],
            attempts=verification_attempts,
            sleeper=sleeper,
        )
        if not _verify_created_inventory(
            coordinator,
            original=capture.playlists,
            playlist_id=created_playlist_id,
            playlist_name=playlist_name,
        ):
            raise ValueError("The new Sonos Playlist identity was not confirmed authoritatively")
        evidence: list[dict[str, Any]] = []
        for failed_position, track in enumerate(tracks, 1):
            failed_identity = f"song:{track['catalogId']}"
            construction_step = "add_track"
            adapter.add_track(created, track)
            construction_step = "verify_track"
            created, evidence = _reopen_and_verify(
                coordinator,
                playlist_id=created_playlist_id,
                playlist_name=playlist_name,
                tracks=tracks[:failed_position],
                attempts=verification_attempts,
                sleeper=sleeper,
            )

        construction_step = "verify_playlist"
        created, evidence = _reopen_and_verify(
            coordinator,
            playlist_id=created_playlist_id,
            playlist_name=playlist_name,
            tracks=tracks,
            attempts=verification_attempts,
            sleeper=sleeper,
        )
        if not _verify_created_inventory(
            coordinator,
            original=capture.playlists,
            playlist_id=created_playlist_id,
            playlist_name=playlist_name,
        ):
            raise ValueError("The final Sonos Playlist inventory changed unexpectedly")
        return {
            "ok": True,
            "action": "create-apple-sonos-playlist",
            "room": expected_state["room"],
            "playlist": {
                "id": created_playlist_id,
                "name": playlist_name,
                "itemCount": len(evidence),
                "items": evidence,
            },
            "queueMutation": False,
            "playbackMutation": False,
            "verification": {
                "authoritativeReopen": True,
                "preExistingPlaylistsUnchanged": True,
            },
        }
    except Exception as exc:
        original_failure_step = construction_step
        sonos_error_code = _safe_sonos_error_code(exc)
        cleanup_required = creation_attempted
        if attributable_playlist_id:
            try:
                playlist_removed, pre_existing_unchanged = _cleanup_owned_playlist(
                    coordinator,
                    original=capture.playlists,
                    playlist_id=attributable_playlist_id,
                    supporting_titles=cleanup_titles,
                )
                cleanup_required = not playlist_removed
                if cleanup_required:
                    construction_step = "cleanup"
            except Exception:  # noqa: BLE001 - cleanup reports only bounded evidence
                playlist_removed = False
                cleanup_required = True
                construction_step = "cleanup"
                try:
                    current = _playlist_inventory(
                        coordinator,
                        maximum=MAX_TRANSACTION_PLAYLISTS,
                    )
                    pre_existing_unchanged = _inventory_preserves_original(
                        current,
                        capture.playlists,
                        owned_playlist_id=attributable_playlist_id,
                    )
                except Exception:  # noqa: BLE001 - no provider details cross the boundary
                    pre_existing_unchanged = False
        else:
            try:
                current = _playlist_inventory(
                    coordinator,
                    maximum=MAX_TRANSACTION_PLAYLISTS,
                )
                pre_existing_unchanged = current.entries == capture.playlists.entries
            except Exception:  # noqa: BLE001 - no provider details cross the boundary
                pre_existing_unchanged = False
        diagnostics: dict[str, Any] = {
            "playlistConstructionStep": construction_step,
            "playlistRemoved": playlist_removed,
            "playlistCleanupRequired": cleanup_required,
            "preExistingPlaylistsUnchanged": pre_existing_unchanged,
            "queueUnchanged": True,
            "playbackUnchanged": True,
            "succeeded": False,
        }
        if attributable_playlist_id:
            diagnostics["partialPlaylistId"] = attributable_playlist_id
        if original_failure_step in {"add_track", "verify_track"} and failed_position is not None:
            diagnostics["failedTrackPosition"] = failed_position
            diagnostics["failedCanonicalIdentity"] = failed_identity
        if sonos_error_code is not None:
            diagnostics["sonosErrorCode"] = sonos_error_code
        raise PlaylistTransactionError(
            phase="playlist_creation",
            diagnostics=diagnostics,
        ) from exc
