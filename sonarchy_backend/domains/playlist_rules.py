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
