from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from soco.music_services import MusicService

from .common import clean
from .common import safe_call as safe_call
from .common import safe_index as safe_index

PLAYLIST_ID_PATTERN = re.compile(r"SQ:\d+")
MAX_PLAYLIST_ID_LENGTH = 32


def item_attr(item: Any, name: str, fallback: Any = "") -> Any:
    try:
        return getattr(item, name)
    except Exception:  # noqa: BLE001 - third-party metadata properties are optional
        return fallback


def favorite_reference(item: Any) -> Any:
    reference = item.reference
    if not getattr(reference, "resources", None):
        raise ValueError("This Sonos Favorite is not directly playable")
    return reference


def validate_identifier(raw: Any, label: str, maximum: int = 512) -> str:
    value = clean(raw)
    if not value or len(value) > maximum or any(ord(character) < 32 for character in value):
        raise ValueError(f"Invalid {label}")
    return value


def validate_playlist_id(raw: Any) -> str:
    value = validate_identifier(raw, "Sonos playlist identifier", MAX_PLAYLIST_ID_LENGTH)
    if not PLAYLIST_ID_PATTERN.fullmatch(value):
        raise ValueError("Invalid Sonos playlist identifier")
    return value


def global_results(
    coordinator: Any,
    term: str,
    limit: int,
    *,
    music_service_factory: Callable[..., Any] = MusicService,
) -> Any:
    query = validate_identifier(term, "search text", 120) if clean(term) else ""
    if not query:
        return []
    service = music_service_factory("Global Player", device=coordinator)
    result = service.search("stations", query, count=limit)
    if result:
        return result
    words = query.split()
    fallback = " ".join(word.upper() if len(word) <= 3 else word.capitalize() for word in words)
    return result if fallback == query else service.search("stations", fallback, count=limit)


def find_playlist_track(
    coordinator: Any, playlist_id: str, index: int, item_id: str
) -> tuple[Any, Any, int]:
    playlist = coordinator.get_sonos_playlist_by_attr("item_id", validate_playlist_id(playlist_id))
    result = coordinator.music_library.browse(ml_item=playlist, max_items=100)
    position = int(index)
    if position < 0 or position >= len(result):
        raise ValueError("The playlist changed; refresh it and try again")
    track = result[position]
    expected_id = validate_identifier(item_id, "playlist item identifier")
    if clean(item_attr(track, "item_id")) != expected_id:
        raise ValueError("The playlist changed; refresh it and try again")
    return playlist, track, len(result)
