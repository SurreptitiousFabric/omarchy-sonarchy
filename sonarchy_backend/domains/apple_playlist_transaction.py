from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from soco.plugins.sharelink import ShareLinkPlugin

from .common import clean, coordinator_for, safe_call, safe_index
from .errors import PlanConflictError, PlaylistTransactionError
from .media import item_attr, validate_playlist_id
from .playlist_rules import suggested_playlist_title, validate_playlist_title
from .queue_transaction import (
    MAX_RESTORABLE_QUEUE_ITEMS,
    QueueBackup,
    QueueStateError,
    capture_queue_backup,
    queue_backup_public_state,
    read_complete_queue,
    restore_queue,
    verify_restored_queue,
)

MAX_SONOS_PLAYLISTS = 100
MAX_TRANSACTION_PLAYLISTS = MAX_SONOS_PLAYLISTS + 1
APPLE_SONG_REFERENCE = re.compile(r"song(?::|%3a)([1-9]\d{0,19})(?!\d)", re.IGNORECASE)


@dataclass(frozen=True)
class PlaylistInventory:
    items: tuple[Any, ...]
    ids: frozenset[str]
    titles: frozenset[str]
    fingerprint: str


@dataclass(frozen=True)
class TargetCapture:
    state: dict[str, Any]
    backup: QueueBackup
    playlists: PlaylistInventory


def _fingerprint(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _safe_uid(value: Any) -> str:
    uid = clean(value)
    if not uid or len(uid) > 128 or any(ord(character) < 32 for character in uid):
        raise PlanConflictError("The exact Sonos room identity could not be verified")
    return uid


def _target_topology(speaker: Any) -> dict[str, Any]:
    room_uid = _safe_uid(getattr(speaker, "uid", ""))
    try:
        group = speaker.group
    except Exception as exc:
        raise PlanConflictError("The Sonos room topology could not be verified") from exc
    try:
        coordinator = getattr(group, "coordinator", None) if group is not None else speaker
        coordinator = coordinator or speaker
        coordinator_uid = _safe_uid(getattr(coordinator, "uid", ""))
        raw_members = getattr(group, "members", None) if group is not None else None
        members = list(raw_members or [speaker])
    except Exception as exc:
        raise PlanConflictError("The Sonos room topology could not be verified") from exc
    member_uids = sorted({_safe_uid(getattr(member, "uid", "")) for member in members})
    if room_uid not in member_uids or coordinator_uid not in member_uids:
        raise PlanConflictError("The Sonos room topology is internally inconsistent")
    binding = {
        "roomUid": room_uid,
        "coordinatorUid": coordinator_uid,
        "memberUids": member_uids,
    }
    return {
        **binding,
        "standalone": len(member_uids) == 1,
        "topologyFingerprint": f"sha256:{_fingerprint(binding)}",
    }


def _bounded_volume(target: Any, label: str) -> int:
    volume = safe_index(safe_call(lambda: target.volume, -1), -1)
    if not 0 <= volume <= 100:
        raise PlanConflictError(f"The {label} volume could not be verified")
    return volume


def _bounded_mute(target: Any, label: str) -> bool:
    try:
        mute = target.mute
    except Exception as exc:
        raise PlanConflictError(f"The {label} mute state could not be verified") from exc
    if not isinstance(mute, bool):
        raise PlanConflictError(f"The {label} mute state could not be verified")
    return mute


def _mixer_state(speaker: Any, coordinator: Any) -> dict[str, Any]:
    group = safe_call(lambda: speaker.group, None)
    group_target = group or coordinator
    return {
        "roomVolume": _bounded_volume(speaker, "room"),
        "roomMuted": _bounded_mute(speaker, "room"),
        "groupVolume": _bounded_volume(group_target, "group"),
        "groupMuted": _bounded_mute(group_target, "group"),
    }


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
    projection: list[dict[str, str]] = []
    ids: set[str] = set()
    titles: set[str] = set()
    for item in items:
        item_id = clean(item_attr(item, "item_id"))
        title = clean(item_attr(item, "title"))
        if item_id:
            ids.add(item_id)
        if title:
            titles.add(title)
        projection.append({"id": item_id, "title": title})
    return PlaylistInventory(
        items=tuple(items),
        ids=frozenset(ids),
        titles=frozenset(titles),
        fingerprint=_fingerprint(projection),
    )


def _required_capability(coordinator: Any) -> bool:
    methods = (
        "get_queue",
        "clear_queue",
        "add_multiple_to_queue",
        "play_from_queue",
        "get_sonos_playlists",
        "create_sonos_playlist_from_queue",
        "get_sonos_playlist_by_attr",
        "remove_sonos_playlist",
    )
    library = getattr(coordinator, "music_library", None)
    return all(callable(getattr(coordinator, method, None)) for method in methods) and callable(
        getattr(library, "browse", None)
    )


def _capture_target(speaker: Any, playlist_name: str) -> TargetCapture:
    topology = _target_topology(speaker)
    coordinator = coordinator_for(speaker)
    if _safe_uid(getattr(coordinator, "uid", "")) != topology["coordinatorUid"]:
        raise PlanConflictError("The Sonos coordinator changed during validation")
    if not _required_capability(coordinator):
        raise PlanConflictError("This Sonos target cannot safely create an Apple playlist")
    try:
        backup = capture_queue_backup(coordinator)
    except QueueStateError as exc:
        raise PlanConflictError(str(exc)) from exc
    except Exception as exc:
        raise PlanConflictError("The current queue state could not be read safely") from exc
    if backup.transport_state not in {"PLAYING", "STOPPED"} or backup.source == "UNKNOWN":
        raise PlanConflictError(
            "The current source must be known and transport must be playing or stopped"
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
    mixer = _mixer_state(speaker, coordinator)
    queue_state = queue_backup_public_state(backup)
    observed = {
        "topologyFingerprint": topology["topologyFingerprint"],
        "queue": queue_state,
        "transportState": backup.transport_state,
        "playbackSource": backup.source,
        "mediaFingerprint": backup.media_marker,
        "volume": {
            "room": mixer["roomVolume"],
            "group": mixer["groupVolume"],
        },
        "mute": {
            "room": mixer["roomMuted"],
            "group": mixer["groupMuted"],
        },
        "capabilities": ["playlist_plan.apple.validate", "playlists.apple.create"],
        "playlistCount": len(playlists.items),
        "playlistInventoryFingerprint": f"sha256:{playlists.fingerprint}",
    }
    room = {
        "uid": topology["roomUid"],
        "standalone": topology["standalone"],
        "memberUids": topology["memberUids"],
        "coordinatorUid": topology["coordinatorUid"],
    }
    return TargetCapture(
        state={"room": room, "observedState": observed},
        backup=backup,
        playlists=playlists,
    )


def inspect_apple_playlist_target(speaker: Any, playlist_name: str) -> dict[str, Any]:
    return _capture_target(speaker, playlist_name).state


def apple_song_identity_from_item(item: Any) -> str:
    candidates = [clean(item_attr(item, "item_id"))]
    for resource in item_attr(item, "resources", []) or []:
        candidates.append(clean(item_attr(resource, "uri")))
    identities = {
        match.group(1)
        for candidate in candidates
        for match in APPLE_SONG_REFERENCE.finditer(candidate)
    }
    return next(iter(identities)) if len(identities) == 1 else ""


def _metadata_matches(actual: str, expected: str) -> bool:
    def normalize(value: str) -> str:
        return " ".join(value.split()).casefold()

    return normalize(actual) == normalize(expected)


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
        artist = clean(item_attr(item, "creator"))
        album = clean(item_attr(item, "album"))
        if not title or not artist:
            raise ValueError(f"The {container} did not provide title and artist evidence")
        if not _metadata_matches(title, track["title"]) or not _metadata_matches(
            artist, track["artist"]
        ):
            raise ValueError(f"The {container} metadata does not match the reviewed song")
        if album and not _metadata_matches(album, track["album"]):
            raise ValueError(f"The {container} album metadata does not match the reviewed song")
        sonos_item_id = clean(item_attr(item, "item_id"))
        evidence = {
            "position": position,
            "catalogId": catalog_id,
            "canonicalIdentity": f"song:{catalog_id}",
            "title": title,
            "artist": artist,
            "album": album,
        }
        if (
            sonos_item_id
            and len(sonos_item_id) <= 512
            and not any(ord(character) < 32 for character in sonos_item_id)
        ):
            evidence["sonosItemId"] = sonos_item_id
        verified.append(evidence)
    return verified


def _playlist_tracks(coordinator: Any, playlist: Any) -> list[Any]:
    result = coordinator.music_library.browse(
        ml_item=playlist,
        max_items=MAX_RESTORABLE_QUEUE_ITEMS,
    )
    items = list(result)
    total = safe_index(item_attr(result, "total_matches", len(items)), len(items))
    if total != len(items) or total > MAX_RESTORABLE_QUEUE_ITEMS:
        raise ValueError("The saved Sonos Playlist could not be reopened completely")
    return items


def _verify_environment(speaker: Any, expected_state: dict[str, Any]) -> None:
    topology = _target_topology(speaker)
    room = expected_state["room"]
    if (
        topology["roomUid"] != room["uid"]
        or topology["coordinatorUid"] != room["coordinatorUid"]
        or topology["memberUids"] != room["memberUids"]
    ):
        raise ValueError("The target room topology changed during the operation")
    coordinator = coordinator_for(speaker)
    mixer = _mixer_state(speaker, coordinator)
    expected = expected_state["observedState"]
    if (
        mixer["roomVolume"] != expected["volume"]["room"]
        or mixer["groupVolume"] != expected["volume"]["group"]
        or mixer["roomMuted"] != expected["mute"]["room"]
        or mixer["groupMuted"] != expected["mute"]["group"]
    ):
        raise ValueError("Volume or mute changed during the playlist operation")
    if not _required_capability(coordinator):
        raise ValueError("The target playlist capability changed during the operation")


def _remove_partial_playlist(
    coordinator: Any,
    *,
    original_ids: frozenset[str],
    created_playlist_id: str,
    created_playlist_title: str,
) -> bool:
    playlist_id = validate_playlist_id(created_playlist_id)
    if playlist_id in original_ids:
        return False
    inventory = _playlist_inventory(coordinator, maximum=MAX_TRANSACTION_PLAYLISTS)
    candidates = [
        item
        for item in inventory.items
        if clean(item_attr(item, "item_id")) == playlist_id
        and clean(item_attr(item, "title")) == created_playlist_title
    ]
    if len(candidates) != 1:
        return False
    coordinator.remove_sonos_playlist(candidates[0])
    after = _playlist_inventory(coordinator, maximum=MAX_TRANSACTION_PLAYLISTS)
    return playlist_id not in after.ids


def _rollback(
    speaker: Any,
    capture: TargetCapture,
    *,
    playlist_creation_attempted: bool,
    created_playlist_id: str | None,
    created_playlist_title: str | None,
) -> dict[str, Any]:
    coordinator = coordinator_for(speaker)
    playlist_removed = False
    playlist_cleanup_required = playlist_creation_attempted
    queue_restored = False
    environment_unchanged = False
    if created_playlist_id is not None and created_playlist_title is not None:
        try:
            playlist_removed = _remove_partial_playlist(
                coordinator,
                original_ids=capture.playlists.ids,
                created_playlist_id=created_playlist_id,
                created_playlist_title=created_playlist_title,
            )
            playlist_cleanup_required = not playlist_removed
        except Exception:  # noqa: BLE001 - rollback reports only bounded booleans
            playlist_removed = False
            playlist_cleanup_required = True
    try:
        restore_queue(coordinator, capture.backup)
        verify_restored_queue(coordinator, capture.backup)
        queue_restored = True
    except Exception:  # noqa: BLE001 - rollback reports only bounded booleans
        queue_restored = False
    try:
        _verify_environment(speaker, capture.state)
        environment_unchanged = True
    except Exception:  # noqa: BLE001 - rollback reports only bounded booleans
        environment_unchanged = False
    succeeded = not playlist_cleanup_required and queue_restored and environment_unchanged
    return {
        "attempted": True,
        "playlistRemoved": playlist_removed,
        "playlistCleanupRequired": playlist_cleanup_required,
        "queueRestored": queue_restored,
        "environmentUnchanged": environment_unchanged,
        "succeeded": succeeded,
    }


def _verify_new_playlist_inventory(
    coordinator: Any,
    *,
    original: PlaylistInventory,
    playlist_id: str,
    playlist_name: str,
) -> None:
    inventory = _playlist_inventory(coordinator, maximum=MAX_TRANSACTION_PLAYLISTS)
    matching_title = [
        item for item in inventory.items if clean(item_attr(item, "title")) == playlist_name
    ]
    if (
        len(matching_title) != 1
        or clean(item_attr(matching_title[0], "item_id")) != playlist_id
        or playlist_id in original.ids
    ):
        raise ValueError("The new Sonos Playlist identity was not confirmed authoritatively")


def create_preflighted_apple_playlist(
    speaker: Any,
    plan: dict[str, Any],
    *,
    share_link_factory: Callable[..., Any] = ShareLinkPlugin,
) -> dict[str, Any]:
    room_uid = str(plan["roomUid"])
    playlist_name = str(plan["playlistName"])
    mode = str(plan["mode"])
    tracks = list(plan["tracks"])
    expected_state = dict(plan["targetState"])
    if _safe_uid(getattr(speaker, "uid", "")) != room_uid:
        raise PlanConflictError("The exact target room no longer matches the playlist plan")
    if mode not in {"save-only", "save-and-play"}:
        raise PlanConflictError("The playlist plan mode no longer matches a supported operation")
    capture = _capture_target(speaker, playlist_name)
    if capture.state != expected_state:
        raise PlanConflictError(
            "Room, topology, media, queue, transport, volume, mute, playlist, "
            "or capability state changed",
            details={"reason": "preflight_state_changed"},
        )

    coordinator = coordinator_for(speaker)
    phase = "queue_clear"
    playlist_creation_attempted = False
    created_playlist_id: str | None = None
    created_playlist_title: str | None = None
    try:
        coordinator.clear_queue()
        phase = "queue_construction"
        share_links = share_link_factory(coordinator)
        for expected_position, track in enumerate(tracks, 1):
            actual_position = int(
                share_links.add_share_link_to_queue(
                    track["url"],
                    dc_title=track["title"],
                )
            )
            if actual_position != expected_position:
                raise ValueError("An Apple song expanded to an unexpected queue position")

        phase = "queue_verification"
        queue_items, queue_total, _queue_update = read_complete_queue(coordinator)
        if queue_total != len(tracks):
            raise ValueError("The approved Apple plan expanded to unexpected queue content")
        queue_evidence = verify_apple_items(queue_items, tracks, container="constructed queue")

        phase = "playlist_creation"
        playlist_creation_attempted = True
        created_playlist = coordinator.create_sonos_playlist_from_queue(playlist_name)
        playlist_id = validate_playlist_id(item_attr(created_playlist, "item_id"))
        created_playlist_id = playlist_id
        created_playlist_title = validate_playlist_title(item_attr(created_playlist, "title"))
        if created_playlist_title != playlist_name:
            raise ValueError("Sonos returned an unexpected playlist name")

        phase = "playlist_verification"
        reopened = coordinator.get_sonos_playlist_by_attr("item_id", playlist_id)
        if clean(item_attr(reopened, "title")) != playlist_name:
            raise ValueError("The saved Sonos Playlist reopened with another name")
        playlist_evidence = verify_apple_items(
            _playlist_tracks(coordinator, reopened),
            tracks,
            container="saved Sonos Playlist",
        )
        _verify_new_playlist_inventory(
            coordinator,
            original=capture.playlists,
            playlist_id=playlist_id,
            playlist_name=playlist_name,
        )
        post_save_items, post_save_total, _post_save_update = read_complete_queue(coordinator)
        if post_save_total != len(tracks):
            raise ValueError("The queue changed while the Sonos Playlist was being saved")
        queue_evidence = verify_apple_items(
            post_save_items,
            tracks,
            container="post-save queue",
        )

        if mode == "save-only":
            phase = "queue_restoration"
            restore_queue(coordinator, capture.backup)
            restored = verify_restored_queue(coordinator, capture.backup)
            _verify_environment(speaker, capture.state)
            final_queue = queue_backup_public_state(restored)
            playback = {
                "state": restored.transport_state,
                "source": restored.source,
                "queuePosition": restored.position + 1 if restored.position >= 0 else 0,
            }
            queue_disposition = "restored"
        else:
            phase = "playback_start"
            coordinator.play_from_queue(0)
            phase = "playback_verification"
            active = capture_queue_backup(coordinator)
            if not active.queue_active or not active.was_playing or active.position != 0:
                raise ValueError("The first approved track did not start playing")
            active_items = list(active.items)
            verify_apple_items(active_items, tracks, container="active queue")
            current = safe_call(coordinator.get_current_track_info, {}) or {}
            if not _metadata_matches(clean(current.get("title")), tracks[0]["title"]) or not (
                _metadata_matches(clean(current.get("artist")), tracks[0]["artist"])
            ):
                raise ValueError("Authoritative playback does not match the first approved track")
            _verify_environment(speaker, capture.state)
            final_queue = queue_backup_public_state(active)
            playback = {
                "state": active.transport_state,
                "source": active.source,
                "queuePosition": 1,
                "current": queue_evidence[0],
            }
            queue_disposition = "approved-plan-active"
        return {
            "ok": True,
            "action": "create-apple-sonos-playlist",
            "mode": mode,
            "room": expected_state["room"],
            "playlist": {
                "id": playlist_id,
                "name": playlist_name,
                "itemCount": len(playlist_evidence),
                "items": playlist_evidence,
            },
            "queue": {
                **final_queue,
                "disposition": queue_disposition,
                "approvedItems": queue_evidence,
            },
            "playback": playback,
            "rollback": {"attempted": False, "succeeded": None},
        }
    except Exception as exc:
        rollback = _rollback(
            speaker,
            capture,
            playlist_creation_attempted=playlist_creation_attempted,
            created_playlist_id=created_playlist_id,
            created_playlist_title=created_playlist_title,
        )
        raise PlaylistTransactionError(phase=phase, rollback=rollback) from exc
