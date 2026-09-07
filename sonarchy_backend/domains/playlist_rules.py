from __future__ import annotations

from typing import Any

from .common import clean

MAX_PLAYLIST_TITLE_LENGTH = 80


def validate_playlist_title(raw: Any) -> str:
    title = clean(raw)
    if not title:
        raise ValueError("Playlist name cannot be empty")
    if len(title) > MAX_PLAYLIST_TITLE_LENGTH or any(ord(character) < 32 for character in title):
        raise ValueError("Playlist name is too long or contains control characters")
    return title


def suggested_playlist_title(title: str, existing_titles: set[str]) -> str:
    """Return the first deterministic, bounded create-only alternative."""

    if title not in existing_titles:
        return title
    for suffix_number in range(2, 1000):
        suffix = f" ({suffix_number})"
        candidate = title[: MAX_PLAYLIST_TITLE_LENGTH - len(suffix)].rstrip() + suffix
        if candidate not in existing_titles:
            return candidate
    raise ValueError("A unique Sonos Playlist name could not be suggested safely")
