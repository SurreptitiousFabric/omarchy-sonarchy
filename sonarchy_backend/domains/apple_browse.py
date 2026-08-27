from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ..apple_catalog import (
    apple_artwork_url,
    apple_lookup_results,
    apple_search_results,
    public_apple_album_url,
    public_apple_music_url,
)
from .common import clean


def _duration(milliseconds: Any) -> str:
    try:
        seconds = max(0, int(milliseconds) // 1000)
    except TypeError, ValueError:
        seconds = 0
    return f"{seconds // 60}:{seconds % 60:02d}" if seconds else ""


def _artist(item: dict[str, Any]) -> dict[str, Any] | None:
    identifier = clean(item.get("artistId"))
    title = clean(item.get("artistName"))
    if not identifier or not title:
        return None
    return {
        "id": identifier,
        "title": title,
        "subtitle": "Artist",
        "section": "ARTISTS",
        "media_kind": "artist",
        "browse_kind": "apple-artist",
        "album_art": "",
        "playable": False,
        "browsable": True,
    }


def _album(item: dict[str, Any]) -> dict[str, Any] | None:
    identifier = clean(item.get("collectionId"))
    title = clean(item.get("collectionName"))
    url = public_apple_album_url(item.get("collectionViewUrl"), identifier)
    if not identifier or not title:
        return None
    year = clean(item.get("releaseDate"))[:4]
    artist = clean(item.get("artistName"))
    return {
        "id": identifier,
        "title": title,
        "subtitle": " · ".join(part for part in ("Album", artist, year) if part),
        "section": "ALBUMS",
        "media_kind": "album",
        "browse_kind": "apple-album",
        "album_art": apple_artwork_url(item.get("artworkUrl100")),
        "album_url": url,
        "playable": bool(url),
        "browsable": True,
    }


def _track(item: dict[str, Any]) -> dict[str, Any] | None:
    identifier = clean(item.get("trackId"))
    title = clean(item.get("trackName"))
    url = public_apple_music_url(item.get("trackViewUrl"))
    if not identifier or not title or not url:
        return None
    artist = clean(item.get("artistName"))
    album = clean(item.get("collectionName"))
    return {
        "id": identifier,
        "title": title,
        "subtitle": " · ".join(
            part for part in ("Song", artist, album, _duration(item.get("trackTimeMillis"))) if part
        ),
        "section": "SONGS",
        "media_kind": "song",
        "album_art": apple_artwork_url(item.get("artworkUrl100")),
        "url": url,
        "album_url": public_apple_album_url(
            item.get("collectionViewUrl"), item.get("collectionId")
        ),
        "playable": True,
        "browsable": False,
    }


def _unique(items: list[dict[str, Any] | None]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        if item is None:
            continue
        key = (clean(item.get("media_kind")), clean(item.get("id")))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _parallel(calls: list[Callable[[], list[dict[str, Any]]]]) -> list[list[dict[str, Any]]]:
    with ThreadPoolExecutor(max_workers=len(calls), thread_name_prefix="apple-catalog") as executor:
        futures = [executor.submit(call) for call in calls]
        return [future.result() for future in futures]


def search_apple(
    term: str,
    limit: int,
    *,
    request_get: Callable[..., Any] | None = None,
    country: str | None = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {"country": country}
    if request_get is not None:
        args["request_get"] = request_get
    artist_limit = min(8, max(1, limit // 5)) if limit >= 3 else 0
    album_limit = min(12, max(1, limit // 3)) if limit >= 3 else 0
    song_limit = max(1, limit - artist_limit - album_limit)
    calls: list[Callable[[], list[dict[str, Any]]]] = []
    kinds: list[str] = []
    for entity, entity_limit in (
        ("musicArtist", artist_limit),
        ("album", album_limit),
        ("song", song_limit),
    ):
        if not entity_limit:
            continue
        kinds.append(entity)
        calls.append(
            lambda entity=entity, entity_limit=entity_limit: apple_search_results(
                term, entity_limit, entity=entity, **args
            )
        )
    grouped = dict(zip(kinds, _parallel(calls), strict=True))
    artists = grouped.get("musicArtist", [])
    albums = grouped.get("album", [])
    songs = grouped.get("song", [])
    items = _unique(
        [_artist(item) for item in artists]
        + [_album(item) for item in albums]
        + [_track(item) for item in songs]
    )
    return {
        "ok": True,
        "kind": "apple",
        "items": items,
        "total": len(items),
        "current_title": "Apple Music results",
    }


def browse_apple_artist(
    artist_id: str,
    limit: int,
    *,
    request_get: Callable[..., Any] | None = None,
    country: str | None = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {"country": country}
    if request_get is not None:
        args["request_get"] = request_get
    album_limit = max(1, limit // 2)
    song_limit = max(1, limit - album_limit)
    albums_raw, songs_raw = _parallel(
        [
            lambda: apple_lookup_results(artist_id, album_limit, entity="album", **args),
            lambda: apple_lookup_results(artist_id, song_limit, entity="song", **args),
        ]
    )
    artist_name = next(
        (
            name
            for item in albums_raw + songs_raw
            if item.get("wrapperType") == "artist" and (name := clean(item.get("artistName")))
        ),
        "Artist",
    )
    items = _unique(
        [_album(item) for item in albums_raw if item.get("collectionType") == "Album"]
        + [_track(item) for item in songs_raw if item.get("wrapperType") == "track"]
    )
    return {
        "ok": True,
        "kind": "apple-artist",
        "items": items,
        "total": len(items),
        "current_title": artist_name,
    }


def browse_apple_album(
    album_id: str,
    limit: int,
    *,
    request_get: Callable[..., Any] | None = None,
    country: str | None = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {"country": country}
    if request_get is not None:
        args["request_get"] = request_get
    raw = apple_lookup_results(album_id, limit, entity="song", **args)
    title = next(
        (
            name
            for item in raw
            if item.get("wrapperType") == "collection"
            and (name := clean(item.get("collectionName")))
        ),
        "Album",
    )
    items = _unique([_track(item) for item in raw if item.get("wrapperType") == "track"])
    return {
        "ok": True,
        "kind": "apple-album",
        "items": items,
        "total": len(items),
        "current_title": title,
    }
