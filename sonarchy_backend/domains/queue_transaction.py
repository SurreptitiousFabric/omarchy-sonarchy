from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .common import clean, safe_call, safe_index
from .media import item_attr

MAX_RESTORABLE_QUEUE_ITEMS = 100
PINNED_SOCO_PLAYBACK_SOURCES = frozenset(
    {
        "AIRPLAY",
        "LIBRARY",
        "LINE_IN",
        "NONE",
        "RADIO",
        "SPOTIFY_CONNECT",
        "TV",
        "WEB_FILE",
    }
)


class QueueStateError(ValueError):
    """A bounded queue validation error safe to translate at domain boundaries."""


@dataclass(frozen=True)
class QueueBackup:
    """Complete bounded queue and the state required for safe restoration."""

    items: tuple[Any, ...]
    total: int
    update_id: int
    queue_active: bool
    position: int
    transport_state: str
    source: str
    media_fingerprint: str
    freshness_fingerprint: str
    content_fingerprint: str

    @property
    def was_playing(self) -> bool:
        return self.transport_state == "PLAYING"

    @property
    def marker(self) -> str:
        update = str(self.update_id) if self.update_id >= 0 else "unknown"
        return f"update:{update}:sha256:{self.freshness_fingerprint[:16]}"

    @property
    def media_marker(self) -> str:
        return f"sha256:{self.media_fingerprint}"


def _resource_uris(item: Any) -> list[str]:
    resources = item_attr(item, "resources", []) or []
    return [clean(item_attr(resource, "uri")) for resource in resources]


def _item_projection(item: Any, *, include_queue_id: bool) -> dict[str, Any]:
    projection = {
        "title": clean(item_attr(item, "title")),
        "artist": clean(item_attr(item, "creator")),
        "album": clean(item_attr(item, "album")),
        "resources": _resource_uris(item),
    }
    if include_queue_id:
        projection["queueId"] = clean(item_attr(item, "item_id"))
    return projection


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def queue_fingerprint(items: list[Any] | tuple[Any, ...], *, include_queue_ids: bool) -> str:
    return _fingerprint(
        [_item_projection(item, include_queue_id=include_queue_ids) for item in items]
    )


def _playback_source(coordinator: Any, *, queue_active: bool) -> str:
    if queue_active:
        return "QUEUE"
    source = clean(safe_call(lambda: coordinator.music_source, "")).upper()
    return source if source in PINNED_SOCO_PLAYBACK_SOURCES else "UNKNOWN"


def read_complete_queue(
    coordinator: Any,
    *,
    maximum: int = MAX_RESTORABLE_QUEUE_ITEMS,
) -> tuple[list[Any], int, int]:
    result = coordinator.get_queue(max_items=maximum, full_album_art_uri=False)
    items = list(result)
    total = safe_index(item_attr(result, "total_matches", len(items)), len(items))
    update_id = safe_index(item_attr(result, "update_id", -1), -1)
    if total != len(items) or total > maximum:
        raise QueueStateError("The queue is too large to replace safely")
    if any(not item_attr(item, "resources", []) for item in items):
        raise QueueStateError("The current queue cannot be backed up safely")
    return items, total, update_id


def capture_queue_backup(
    coordinator: Any,
    *,
    allow_empty_active: bool = False,
) -> QueueBackup:
    items, total, update_id = read_complete_queue(coordinator)
    media = safe_call(
        lambda: coordinator.avTransport.GetMediaInfo([("InstanceID", 0)]),
        None,
    )
    if not isinstance(media, dict) or "CurrentURI" not in media:
        raise QueueStateError("The current playback source could not be verified")
    current_uri = clean(media.get("CurrentURI"))
    queue_active = current_uri.casefold().startswith("x-rincon-queue:")
    track = safe_call(coordinator.get_current_track_info, {}) or {}
    position = safe_index(track.get("playlist_position"), 0) - 1
    if queue_active and items and not 0 <= position < len(items):
        raise QueueStateError("The current queue position could not be verified")
    if queue_active and not items and not allow_empty_active:
        raise QueueStateError("The active queue is empty and cannot be restored safely")
    transport = safe_call(coordinator.get_current_transport_info, {}) or {}
    transport_state = clean(transport.get("current_transport_state")).upper() or "UNKNOWN"
    source = _playback_source(coordinator, queue_active=queue_active)
    return QueueBackup(
        items=tuple(items),
        total=total,
        update_id=update_id,
        queue_active=queue_active,
        position=position,
        transport_state=transport_state,
        source=source,
        media_fingerprint=_fingerprint(current_uri),
        freshness_fingerprint=queue_fingerprint(items, include_queue_ids=True),
        content_fingerprint=queue_fingerprint(items, include_queue_ids=False),
    )


def restore_queue(coordinator: Any, backup: QueueBackup) -> None:
    coordinator.clear_queue()
    if backup.items:
        coordinator.add_multiple_to_queue(list(backup.items))
    if backup.queue_active and backup.items:
        coordinator.play_from_queue(backup.position, start=backup.was_playing)


def queue_backup_public_state(backup: QueueBackup) -> dict[str, Any]:
    return {
        "length": backup.total,
        "position": backup.position + 1 if backup.position >= 0 else 0,
        "revisionMarker": backup.marker,
        "fingerprint": f"sha256:{backup.freshness_fingerprint}",
        "active": backup.queue_active,
    }


def verify_restored_queue(coordinator: Any, expected: QueueBackup) -> QueueBackup:
    actual = capture_queue_backup(coordinator)
    if actual.total != expected.total or actual.content_fingerprint != expected.content_fingerprint:
        raise QueueStateError("The previous queue contents were not restored exactly")
    if actual.queue_active != expected.queue_active:
        raise QueueStateError("The previous playback source was not restored")
    if expected.queue_active and actual.position != expected.position:
        raise QueueStateError("The previous queue position was not restored")
    if actual.transport_state != expected.transport_state:
        raise QueueStateError("The previous playing state was not restored")
    if actual.source != expected.source:
        raise QueueStateError("The previous playback source was not restored")
    if actual.media_fingerprint != expected.media_fingerprint:
        raise QueueStateError("The previous exact playback source was not preserved")
    return actual
