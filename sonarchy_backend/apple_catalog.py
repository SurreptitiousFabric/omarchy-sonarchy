from __future__ import annotations

import ipaddress
import json
import os
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests
from soco.plugins.sharelink import AppleMusicShare

from .artwork import select_artwork_match

APPLE_SEARCH_URL = "https://itunes.apple.com/search"
APPLE_LOOKUP_URL = "https://itunes.apple.com/lookup"
APPLE_RESPONSE_LIMIT = 1024 * 1024
APPLE_ALBUM_PATH_PATTERN = re.compile(r"/[A-Za-z]{2}/album/[^/]+/(\d+)/?")
APPLE_CATALOG_ID_PATTERN = re.compile(r"[1-9]\d{0,19}")
APPLE_SONG_PATH_PATTERN = re.compile(r"/[A-Za-z]{2}/album/[^/]+/[1-9]\d{0,19}/?")
MAX_APPLE_URL_LENGTH = 1024


def default_country() -> str:
    country = os.environ.get(
        "SONARCHY_APPLE_COUNTRY", os.environ.get("OMARCHY_SONOS_APPLE_COUNTRY", "CH")
    ).upper()
    return country if re.fullmatch(r"[A-Z]{2}", country) else "CH"


def clean(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text == "NOT_IMPLEMENTED" else text


def validate_search_term(raw: Any, *, allow_empty: bool = True) -> str:
    value = clean(raw)
    if not value and not allow_empty:
        raise ValueError("Search text is required")
    if len(value) > 120 or any(ord(character) < 32 for character in value):
        raise ValueError("Search text is too long or contains control characters")
    return value


def public_apple_music_url(value: Any) -> str:
    url = clean(value)
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "music.apple.com"
        or parsed.username
        or parsed.password
    ):
        return ""
    try:
        port = parsed.port
    except ValueError:
        return ""
    return url if port in (None, 443) else ""


def canonical_apple_song(
    value: Any,
    catalog_id: Any,
    *,
    canonicalizer: Callable[[str], str | None] | None = None,
) -> tuple[str, str]:
    """Validate one exact Apple song share URL through Sonarchy and SoCo.

    The original public URL is retained. It is never synthesized from an ID.
    """

    url = public_apple_music_url(value)
    identifier = clean(catalog_id)
    if not url or len(url.encode("utf-8")) > MAX_APPLE_URL_LENGTH:
        raise ValueError("Expected a bounded Apple Music song link")
    if not APPLE_CATALOG_ID_PATTERN.fullmatch(identifier):
        raise ValueError("Invalid Apple catalogue song identifier")
    parsed = urlparse(url)
    if not APPLE_SONG_PATH_PATTERN.fullmatch(parsed.path) or parsed.fragment:
        raise ValueError("Expected an Apple Music song link")
    try:
        song_ids = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True).get("i", [])
    except ValueError as exc:
        raise ValueError("The Apple Music song link has a malformed query") from exc
    if len(song_ids) != 1 or not APPLE_CATALOG_ID_PATTERN.fullmatch(song_ids[0]):
        raise ValueError("The Apple Music link has a missing or malformed song identifier")
    if song_ids[0] != identifier:
        raise ValueError("The Apple song link does not match its catalogue identifier")
    canonical_uri = (canonicalizer or AppleMusicShare().canonical_uri)(url)
    if not canonical_uri:
        raise ValueError("SoCo does not recognise this Apple Music link")
    content_type, separator, canonical_id = canonical_uri.partition(":")
    if separator != ":" or content_type != "song":
        raise ValueError("The Apple Music link must identify one song")
    if not APPLE_CATALOG_ID_PATTERN.fullmatch(canonical_id):
        raise ValueError("SoCo returned an invalid Apple song identity")
    if canonical_id != identifier:
        raise ValueError("The Apple song link does not match its catalogue identifier")
    return url, canonical_id


def public_apple_album_url(value: Any, collection_id: Any = "") -> str:
    url = public_apple_music_url(value)
    if not url:
        return ""
    parsed = urlparse(url)
    match = APPLE_ALBUM_PATH_PATTERN.fullmatch(parsed.path)
    expected_id = clean(collection_id)
    if not match or (expected_id and match.group(1) != expected_id):
        return ""
    return parsed._replace(params="", query="", fragment="").geturl()


def apple_artwork_url(value: Any, size: int = 600) -> str:
    url = clean(value)
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.username or parsed.password or not parsed.hostname:
        return ""
    try:
        if parsed.port not in (None, 443):
            return ""
        ipaddress.ip_address(parsed.hostname)
        return ""
    except ValueError:
        pass
    hostname = parsed.hostname.casefold().rstrip(".")
    if hostname != "mzstatic.com" and not hostname.endswith(".mzstatic.com"):
        return ""
    bounded_size = max(100, min(int(size), 1200))
    path = re.sub(
        r"/\d+x\d+bb(?=\.[A-Za-z0-9]+$)",
        f"/{bounded_size}x{bounded_size}bb",
        parsed.path,
        count=1,
    )
    return parsed._replace(path=path, params="", fragment="").geturl()


def _apple_results(
    url: str,
    params: dict[str, Any],
    *,
    request_get: Callable[..., Any],
) -> list[dict[str, Any]]:
    response = request_get(
        url,
        params=params,
        headers={"Accept": "application/json", "User-Agent": "sonarchy/4"},
        timeout=6,
        allow_redirects=False,
        stream=True,
    )
    try:
        if 300 <= int(response.status_code) < 400:
            raise ValueError("Apple catalog returned an unexpected redirect")
        response.raise_for_status()
        try:
            content_length = int(response.headers.get("content-length", 0))
        except TypeError, ValueError:
            content_length = 0
        if content_length > APPLE_RESPONSE_LIMIT:
            raise ValueError("Apple catalog returned an oversized response")
        chunks = []
        total = 0
        for chunk in response.iter_content(chunk_size=16384):
            total += len(chunk)
            if total > APPLE_RESPONSE_LIMIT:
                raise ValueError("Apple catalog returned an oversized response")
            chunks.append(chunk)
        payload = json.loads(b"".join(chunks).decode("utf-8"))
    finally:
        response.close()
    results = payload.get("results", []) if isinstance(payload, dict) else []
    return [item for item in results if isinstance(item, dict)]


def apple_search_results(
    term: str,
    limit: int,
    *,
    entity: str = "song",
    request_get: Callable[..., Any] = requests.get,
    country: str | None = None,
) -> list[dict[str, Any]]:
    query = validate_search_term(term)
    if not query:
        return []
    bounded_limit = max(1, min(int(limit), 100))
    selected_country = (country or default_country()).upper()
    if not re.fullmatch(r"[A-Z]{2}", selected_country):
        selected_country = "CH"
    if entity not in {"musicArtist", "album", "song"}:
        raise ValueError("Unsupported Apple catalog entity")
    return _apple_results(
        APPLE_SEARCH_URL,
        params={
            "term": query,
            "country": selected_country,
            "media": "music",
            "entity": entity,
            "limit": bounded_limit,
        },
        request_get=request_get,
    )


def apple_lookup_results(
    item_id: str,
    limit: int,
    *,
    entity: str,
    request_get: Callable[..., Any] = requests.get,
    country: str | None = None,
) -> list[dict[str, Any]]:
    identifier = clean(item_id)
    if not identifier.isdecimal() or len(identifier) > 20:
        raise ValueError("Invalid Apple catalog identifier")
    if entity not in {"album", "song"}:
        raise ValueError("Unsupported Apple catalog entity")
    selected_country = (country or default_country()).upper()
    if not re.fullmatch(r"[A-Z]{2}", selected_country):
        selected_country = "CH"
    return _apple_results(
        APPLE_LOOKUP_URL,
        params={
            "id": identifier,
            "country": selected_country,
            "entity": entity,
            "limit": max(1, min(int(limit), 100)),
        },
        request_get=request_get,
    )


def resolve_apple_artwork(
    title: str,
    artist: str,
    *,
    request_get: Callable[..., Any] = requests.get,
    country: str | None = None,
) -> dict[str, Any]:
    safe_title = validate_search_term(title, allow_empty=False)
    safe_artist = validate_search_term(artist, allow_empty=False)
    query = f"{safe_title} {safe_artist}"[:120].strip()
    candidates = []
    for item in apple_search_results(query, 12, request_get=request_get, country=country):
        artwork_url = apple_artwork_url(item.get("artworkUrl100"))
        if not artwork_url:
            continue
        candidates.append(
            {
                "title": clean(item.get("trackName")),
                "artist": clean(item.get("artistName")),
                "album": clean(item.get("collectionName")),
                "artwork_url": artwork_url,
            }
        )
    match = select_artwork_match(safe_title, safe_artist, candidates)
    if match is None:
        return {"ok": True, "match": False, "artwork_url": "", "confidence": 0}
    return {"ok": True, "match": True, **match}
