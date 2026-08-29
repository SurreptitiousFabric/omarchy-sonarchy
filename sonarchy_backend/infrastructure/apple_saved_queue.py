from __future__ import annotations

import re
from typing import Any

import soco
from soco.data_structures import DidlMusicTrack, to_didl_string
from soco.plugins.sharelink import AppleMusicShare

from ..apple_catalog import canonical_apple_song

PINNED_SOCO_VERSION = "0.31.2"
APPLE_SERVICE_NUMBER = 52231
APPLE_SONG_KEY = "10032020"
APPLE_SONG_CLASS = "object.item.audioItem.musicTrack"
APPLE_SONG_PREFIX = ""
APPLE_CATALOG_ID = re.compile(r"[1-9]\d{0,19}")
APPLE_TRACK_FIELDS = frozenset({"catalogId", "url", "title", "artist", "album", "durationMs"})
MAX_TRACK_TEXT_BYTES = 240
MAX_TRACK_DURATION_MS = 24 * 60 * 60 * 1000
APPEND_INDEX = 2**32 - 1


class DirectAppleSavedQueueUnavailableError(ValueError):
    """The pinned direct Apple saved-queue contract is unavailable."""


def _clean(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text == "NOT_IMPLEMENTED" else text


def _item_attr(item: Any, name: str, fallback: Any = "") -> Any:
    try:
        return getattr(item, name)
    except Exception:  # noqa: BLE001 - third-party metadata fields are optional
        return fallback


def _safe_index(value: Any, fallback: int = -1) -> int:
    try:
        return int(value)
    except TypeError, ValueError:
        return fallback


def _bounded_text(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("Direct Apple playlist items require reviewed text")
    text = value.strip()
    if (
        not text
        or len(text.encode("utf-8")) > MAX_TRACK_TEXT_BYTES
        or any(ord(character) < 32 for character in text)
    ):
        raise ValueError("Direct Apple playlist items require reviewed bounded text")
    return text


class DirectAppleSavedQueueAdapter:
    """Add one validated Apple song directly to one Sonos saved queue.

    This deliberately reproduces only the Apple ``song`` envelope used by
    SoCo 0.31.2's ShareLink plugin. It is not a generic URI, DIDL, music
    service, saved-queue, or UPnP facility. A SoCo upgrade or drift in the
    pinned Apple constants disables the adapter until its contract tests and
    assumptions are reviewed again.
    """

    def __init__(self, coordinator: Any) -> None:
        self._coordinator = coordinator
        self._apple = AppleMusicShare()
        self.assert_available()

    def assert_available(self) -> None:
        if soco.__version__ != PINNED_SOCO_VERSION:
            raise DirectAppleSavedQueueUnavailableError(
                "Direct Apple Sonos Playlist creation requires the pinned SoCo version"
            )
        song_magic = self._apple.magic().get("song")
        if (
            song_magic
            != {
                "prefix": APPLE_SONG_PREFIX,
                "key": APPLE_SONG_KEY,
                "class": APPLE_SONG_CLASS,
            }
            or self._apple.service_number() != APPLE_SERVICE_NUMBER
        ):
            raise DirectAppleSavedQueueUnavailableError(
                "The pinned SoCo Apple song envelope changed"
            )
        transport = getattr(self._coordinator, "avTransport", None)
        library = getattr(self._coordinator, "music_library", None)
        if not callable(getattr(transport, "AddURIToSavedQueue", None)) or not callable(
            getattr(library, "browse", None)
        ):
            raise DirectAppleSavedQueueUnavailableError(
                "This Sonos coordinator cannot add direct Apple saved-queue items"
            )

    def add_track(self, playlist: Any, track: dict[str, Any]) -> None:
        """Append one already reviewed Apple song to ``playlist``."""

        if not isinstance(track, dict) or set(track) != APPLE_TRACK_FIELDS:
            raise ValueError("Direct Apple playlist items require the reviewed track shape")
        url, catalog_id = canonical_apple_song(track.get("url"), track.get("catalogId"))
        if not APPLE_CATALOG_ID.fullmatch(catalog_id):
            raise ValueError("Direct Apple playlist items require one exact song identity")
        title = _bounded_text(track.get("title"))
        artist = _bounded_text(track.get("artist"))
        album = _bounded_text(track.get("album"))
        duration_ms = track.get("durationMs")
        if (
            isinstance(duration_ms, bool)
            or not isinstance(duration_ms, int)
            or not 1 <= duration_ms <= MAX_TRACK_DURATION_MS
        ):
            raise ValueError("Direct Apple playlist items require a reviewed duration")

        extracted = self._apple.extract(url)
        encoded_uri = f"song%3a{catalog_id}"
        if extracted != ("song", encoded_uri):
            raise DirectAppleSavedQueueUnavailableError(
                "The pinned SoCo Apple canonicalisation changed"
            )

        playlist_id = _clean(_item_attr(playlist, "item_id"))
        if not re.fullmatch(r"SQ:\d+", playlist_id):
            raise ValueError("Direct Apple playlist items require an exact Sonos Playlist ID")
        browse = self._coordinator.music_library.browse(
            ml_item=playlist,
            start=0,
            max_items=1,
            full_album_art_uri=False,
        )
        update_id = _safe_index(_item_attr(browse, "update_id", -1), -1)
        if update_id < 0:
            raise DirectAppleSavedQueueUnavailableError(
                "The Sonos Playlist update identity could not be verified"
            )

        item = DidlMusicTrack(
            title=title,
            parent_id="-1",
            item_id=f"{APPLE_SONG_KEY}{encoded_uri}",
            restricted=True,
            resources=[],
            desc=(f"SA_RINCON{APPLE_SERVICE_NUMBER}_X_#Svc{APPLE_SERVICE_NUMBER}-0-Token"),
            creator=artist,
            artist=artist,
            album=album,
        )
        metadata = to_didl_string(item)
        self._coordinator.avTransport.AddURIToSavedQueue(
            [
                ("InstanceID", 0),
                ("UpdateID", update_id),
                ("ObjectID", playlist_id),
                ("EnqueuedURI", encoded_uri),
                ("EnqueuedURIMetaData", metadata),
                ("AddAtIndex", APPEND_INDEX),
            ]
        )
