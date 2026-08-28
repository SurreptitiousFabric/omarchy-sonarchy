from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .common import clean, safe_call, safe_index
from .media import item_attr

MAX_RESTORABLE_QUEUE_ITEMS = 100
QUEUE_RESTORE_STEPS = frozenset({"clear", "readd", "position_select"})
QUEUE_VERIFICATION_REASONS = frozenset(
    {
        "queue_read",
        "item_count",
        "resources",
        "metadata",
        "queue_active",
        "position",
        "transport",
        "source",
        "media",
    }
)
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

    def __init__(self, message: str, *, reason: str | None = None) -> None:
        super().__init__(message)
        self.reason = reason


class QueueRestoreError(QueueStateError):
    """A typed failure from one bounded queue-restoration step."""

    def __init__(self, step: str, *, item_position: int | None = None) -> None:
        if step not in QUEUE_RESTORE_STEPS:
            raise ValueError("Unsupported queue restoration step")
        if item_position is not None and not 1 <= item_position <= MAX_RESTORABLE_QUEUE_ITEMS:
            raise ValueError("Invalid queue restoration item position")
        super().__init__("The previous queue could not be restored")
        self.step = step
        self.item_position = item_position


class QueueVerificationError(QueueStateError):
    """A typed exact-restoration verification failure."""

    def __init__(self, reason: str) -> None:
        if reason not in QUEUE_VERIFICATION_REASONS:
            raise ValueError("Unsupported queue verification reason")
        messages = {
            "queue_read": "The previous queue could not be read after restoration",
            "item_count": "The previous queue contents were not restored exactly",
            "resources": "The previous queue contents were not restored exactly",
            "metadata": "The previous queue contents were not restored exactly",
            "queue_active": "The previous playback source was not restored",
            "position": "The previous queue position was not restored",
            "transport": "The previous playing state was not restored",
            "source": "The previous playback source was not restored",
            "media": "The previous exact playback source was not preserved",
        }
        super().__init__(messages[reason], reason=reason)


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
    resource_fingerprint: str = ""
    metadata_fingerprint: str = ""

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


_MISSING = object()
RESOURCE_FIELDS = (
    "uri",
    "protocol_info",
    "import_uri",
    "size",
    "duration",
    "bitrate",
    "sample_frequency",
    "bits_per_sample",
    "nr_audio_channels",
    "resolution",
    "color_depth",
    "protection",
)


def _value(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _attribute(value: Any, name: str, fallback: Any = _MISSING) -> Any:
    try:
        return getattr(value, name)
    except Exception:  # noqa: BLE001 - optional third-party DIDL fields are best effort
        return fallback


def _resources(item: Any) -> list[Any]:
    value = _attribute(item, "resources", [])
    return list(value or [])


def _resource_projection(resource: Any) -> dict[str, Any]:
    return {field: _value(_attribute(resource, field, None)) for field in RESOURCE_FIELDS}


def _provider_projection(item: Any) -> dict[str, Any]:
    """Internal replay identity; values are hashed and never cross the protocol."""

    return {
        "itemClass": _value(_attribute(item, "item_class", "")),
        "tag": _value(_attribute(item, "tag", "")),
        "desc": _value(_attribute(item, "desc", "")),
        "resources": [_resource_projection(resource) for resource in _resources(item)],
    }


def _metadata_projection(item: Any) -> dict[str, Any]:
    translation = _attribute(item, "_translation", {})
    translated_fields = set(translation) if isinstance(translation, dict) else set()
    # Simple fakes and a few provider objects do not publish _translation.
    translated_fields.update({"creator", "artist", "album"})
    fields: dict[str, Any] = {}
    for field in sorted(translated_fields):
        value = _attribute(item, field)
        if value is not _MISSING:
            fields[field] = _value(value)
    return {
        "title": _value(_attribute(item, "title", "")),
        "restricted": _value(_attribute(item, "restricted", None)),
        "fields": fields,
    }


def _stable_item_projection(item: Any) -> dict[str, Any]:
    # item_id and parent_id are deliberately omitted because Sonos regenerates
    # queue-local identities while replaying an otherwise identical item.
    return {
        "provider": _provider_projection(item),
        "metadata": _metadata_projection(item),
    }


def _item_projection(item: Any, *, include_queue_id: bool) -> dict[str, Any]:
    projection = _stable_item_projection(item)
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


def _projection_fingerprint(
    items: list[Any] | tuple[Any, ...],
    projection: Any,
) -> str:
    return _fingerprint([projection(item) for item in items])


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
        raise QueueStateError("The queue is too large to replace safely", reason="item_count")
    if any(not _resources(item) for item in items):
        raise QueueStateError("The current queue cannot be backed up safely", reason="resources")
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
        raise QueueStateError(
            "The current playback source could not be verified",
            reason="queue_read",
        )
    current_uri = clean(media.get("CurrentURI"))
    queue_active = current_uri.casefold().startswith("x-rincon-queue:")
    track = safe_call(coordinator.get_current_track_info, {}) or {}
    position = safe_index(track.get("playlist_position"), 0) - 1
    if queue_active and items and not 0 <= position < len(items):
        raise QueueStateError(
            "The current queue position could not be verified",
            reason="position",
        )
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
        resource_fingerprint=_projection_fingerprint(items, _provider_projection),
        metadata_fingerprint=_projection_fingerprint(items, _metadata_projection),
    )


def restore_queue(coordinator: Any, backup: QueueBackup) -> None:
    try:
        coordinator.clear_queue()
    except Exception as exc:
        raise QueueRestoreError("clear") from exc
    for expected_position, item in enumerate(backup.items, 1):
        try:
            returned_position = coordinator.add_to_queue(item)
        except Exception as exc:
            raise QueueRestoreError("readd", item_position=expected_position) from exc
        if not isinstance(returned_position, int) or isinstance(returned_position, bool):
            raise QueueRestoreError("readd", item_position=expected_position)
        actual_position = returned_position
        if actual_position != expected_position:
            raise QueueRestoreError("readd", item_position=expected_position)
    if backup.queue_active and backup.items:
        try:
            coordinator.play_from_queue(backup.position, start=backup.was_playing)
        except Exception as exc:
            raise QueueRestoreError("position_select") from exc


def queue_backup_public_state(backup: QueueBackup) -> dict[str, Any]:
    return {
        "length": backup.total,
        "position": backup.position + 1 if backup.position >= 0 else 0,
        "revisionMarker": backup.marker,
        "fingerprint": f"sha256:{backup.freshness_fingerprint}",
        "active": backup.queue_active,
    }


def verify_restored_queue(coordinator: Any, expected: QueueBackup) -> QueueBackup:
    try:
        actual = capture_queue_backup(coordinator)
    except QueueStateError as exc:
        reason = exc.reason if exc.reason in QUEUE_VERIFICATION_REASONS else "queue_read"
        raise QueueVerificationError(reason) from exc
    except Exception as exc:
        raise QueueVerificationError("queue_read") from exc
    if actual.total != expected.total:
        raise QueueVerificationError("item_count")
    if actual.resource_fingerprint != expected.resource_fingerprint:
        raise QueueVerificationError("resources")
    if actual.metadata_fingerprint != expected.metadata_fingerprint:
        raise QueueVerificationError("metadata")
    if actual.content_fingerprint != expected.content_fingerprint:
        raise QueueVerificationError("metadata")
    if actual.queue_active != expected.queue_active:
        raise QueueVerificationError("queue_active")
    if expected.queue_active and actual.position != expected.position:
        raise QueueVerificationError("position")
    if actual.transport_state != expected.transport_state:
        raise QueueVerificationError("transport")
    if actual.source != expected.source:
        raise QueueVerificationError("source")
    if actual.media_fingerprint != expected.media_fingerprint:
        raise QueueVerificationError("media")
    return actual
