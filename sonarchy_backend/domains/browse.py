from __future__ import annotations

import ipaddress
from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin, urlparse

from ..apple_catalog import (
    apple_artwork_url,
    apple_search_results,
    public_apple_album_url,
    public_apple_music_url,
)
from .common import DomainService, number_arg, string_arg
from .media import (
    PLAYLIST_ID_PATTERN,
    clean,
    favorite_reference,
    global_results,
    item_attr,
    safe_call,
    safe_index,
    validate_identifier,
    validate_playlist_id,
)
from .ports import BrowsePort

CONTENT_KINDS = frozenset({"queue", "apple", "global", "library", "playlists", "playlist"})
PUBLIC_ARTWORK_SUFFIXES = (
    ".mzstatic.com",
    ".scdn.co",
    ".tunein.com",
    ".radiotime.com",
    ".globalplayer.com",
    ".thisisglobal.com",
    ".radioplayer.cloud",
)
PUBLIC_ARTWORK_HOSTS = ("static.mytuner-radio.net",)


def validate_private_ip(raw: str) -> str:
    address = ipaddress.ip_address(raw)
    if (
        address.version != 4
        or not address.is_private
        or address.is_multicast
        or address.is_unspecified
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
    ):
        raise ValueError("Expected a unicast IPv4 address")
    return str(address)


def public_artwork_url(raw: Any) -> str:
    resolved = clean(raw)
    parsed = urlparse(resolved)
    if parsed.username or parsed.password or not parsed.hostname or parsed.scheme != "https":
        return ""
    try:
        if parsed.port not in (None, 443):
            return ""
        ipaddress.ip_address(parsed.hostname)
        return ""
    except ValueError:
        pass
    hostname = parsed.hostname.casefold().rstrip(".")
    if hostname == "localhost" or hostname.endswith((".local", ".internal")):
        return ""
    if hostname not in PUBLIC_ARTWORK_HOSTS and not any(
        hostname == suffix.removeprefix(".") or hostname.endswith(suffix)
        for suffix in PUBLIC_ARTWORK_SUFFIXES
    ):
        return ""
    return resolved


def album_art_url(raw: Any, coordinator_ip: str) -> str:
    art = clean(raw)
    if not art:
        return ""
    local_ip = validate_private_ip(coordinator_ip)
    resolved = urljoin(f"http://{local_ip}:1400/", art)
    parsed = urlparse(resolved)
    if parsed.username or parsed.password or not parsed.hostname:
        return ""
    if parsed.scheme == "http":
        return resolved if parsed.hostname == local_ip and parsed.port in (None, 1400) else ""
    return public_artwork_url(resolved)


def result_total(result: Any) -> int:
    return safe_index(safe_call(lambda: result.total_matches, len(result)), len(result))


def queue_content(coordinator: Any, limit: int) -> dict[str, Any]:
    result = coordinator.get_queue(max_items=limit, full_album_art_uri=False)
    coordinator_ip = clean(getattr(coordinator, "ip_address", ""))
    current = safe_call(coordinator.get_current_track_info, {}) or {}
    current_index = max(-1, safe_index(current.get("playlist_position"), 0) - 1)
    items = []
    for index, item in enumerate(result):
        artist = clean(item_attr(item, "creator"))
        album = clean(item_attr(item, "album"))
        items.append(
            {
                "id": clean(item_attr(item, "item_id")) or str(index),
                "index": index,
                "title": clean(item_attr(item, "title")) or f"Queue item {index + 1}",
                "subtitle": " · ".join(part for part in (artist, album) if part),
                "album_art": album_art_url(item_attr(item, "album_art_uri"), coordinator_ip),
                "playable": True,
                "current": index == current_index,
            }
        )
    return {"ok": True, "kind": "queue", "items": items, "total": result_total(result)}


def favorites_content(coordinator: Any, limit: int) -> dict[str, Any]:
    result = coordinator.music_library.get_sonos_favorites(max_items=limit)
    coordinator_ip = clean(getattr(coordinator, "ip_address", ""))
    items = []
    for item in result:
        playable = bool(safe_call(lambda item=item: favorite_reference(item), None))
        items.append(
            {
                "id": clean(item_attr(item, "item_id")),
                "title": clean(item_attr(item, "title")) or "Untitled favorite",
                "subtitle": clean(item_attr(item, "description")),
                "album_art": album_art_url(item_attr(item, "album_art_uri"), coordinator_ip),
                "playable": playable,
            }
        )
    return {"ok": True, "kind": "favorites", "items": items, "total": result_total(result)}


def didl_item_payload(item: Any, index: int, coordinator_ip: str) -> dict[str, Any]:
    creator = clean(item_attr(item, "creator"))
    album = clean(item_attr(item, "album"))
    resources = item_attr(item, "resources", []) or []
    return {
        "id": clean(item_attr(item, "item_id")) or str(index),
        "index": index,
        "title": clean(item_attr(item, "title")) or f"Item {index + 1}",
        "subtitle": " · ".join(part for part in (creator, album) if part),
        "album_art": album_art_url(item_attr(item, "album_art_uri"), coordinator_ip),
        "playable": bool(resources),
    }


def library_content(coordinator: Any, term: str, limit: int) -> dict[str, Any]:
    query = validate_identifier(term, "search text", 120) if clean(term) else ""
    library = coordinator.music_library
    shares = safe_call(library.list_library_shares, []) or []
    updating = bool(safe_call(lambda: library.library_updating, False))
    if not query:
        return {
            "ok": True,
            "kind": "library",
            "items": [],
            "total": 0,
            "shares": [clean(share)[:512] for share in shares[:32]],
            "updating": updating,
        }
    result = library.get_music_library_information("tracks", max_items=limit, search_term=query)
    coordinator_ip = clean(getattr(coordinator, "ip_address", ""))
    items = [didl_item_payload(item, index, coordinator_ip) for index, item in enumerate(result)]
    return {
        "ok": True,
        "kind": "library",
        "items": items,
        "total": result_total(result),
        "shares": [clean(share)[:512] for share in shares[:32]],
        "updating": updating,
    }


def playlists_content(coordinator: Any, limit: int) -> dict[str, Any]:
    result = coordinator.get_sonos_playlists(max_items=limit)
    items = []
    for index, item in enumerate(result):
        item_id = clean(item_attr(item, "item_id"))
        if not PLAYLIST_ID_PATTERN.fullmatch(item_id):
            continue
        items.append(
            {
                "id": item_id,
                "index": index,
                "title": clean(item_attr(item, "title")) or f"Playlist {index + 1}",
                "subtitle": "Sonos playlist",
                "album_art": "",
                "playable": True,
            }
        )
    return {"ok": True, "kind": "playlists", "items": items, "total": result_total(result)}


def playlist_content(coordinator: Any, playlist_id: str, limit: int) -> dict[str, Any]:
    item_id = validate_playlist_id(playlist_id)
    playlist = coordinator.get_sonos_playlist_by_attr("item_id", item_id)
    result = coordinator.music_library.browse(ml_item=playlist, max_items=limit)
    coordinator_ip = clean(getattr(coordinator, "ip_address", ""))
    items = [didl_item_payload(item, index, coordinator_ip) for index, item in enumerate(result)]
    return {
        "ok": True,
        "kind": "playlist",
        "playlist_id": item_id,
        "playlist_title": clean(item_attr(playlist, "title")) or "Sonos playlist",
        "items": items,
        "total": result_total(result),
    }


def format_duration(milliseconds: Any) -> str:
    seconds = max(0, safe_index(milliseconds, 0) // 1000)
    return f"{seconds // 60}:{seconds % 60:02d}" if seconds else ""


def apple_content(
    term: str,
    limit: int,
    *,
    request_get: Callable[..., Any] | None = None,
    country: str | None = None,
) -> dict[str, Any]:
    items = []
    search_args = {"country": country}
    if request_get is not None:
        search_args["request_get"] = request_get
    for item in apple_search_results(term, limit, **search_args):
        url = public_apple_music_url(item.get("trackViewUrl"))
        if not url:
            continue
        artist = clean(item.get("artistName"))
        album = clean(item.get("collectionName"))
        duration = format_duration(item.get("trackTimeMillis"))
        items.append(
            {
                "id": clean(item.get("trackId")),
                "title": clean(item.get("trackName")) or "Untitled track",
                "subtitle": " · ".join(part for part in (artist, album, duration) if part),
                "album_art": apple_artwork_url(item.get("artworkUrl100")),
                "url": url,
                "album_url": public_apple_album_url(
                    item.get("collectionViewUrl"), item.get("collectionId")
                ),
                "playable": True,
            }
        )
    return {"ok": True, "kind": "apple", "items": items, "total": len(items)}


def global_content(coordinator: Any, term: str, limit: int) -> dict[str, Any]:
    result = global_results(coordinator, term, limit)
    items = []
    for item in result:
        items.append(
            {
                "id": clean(item_attr(item, "item_id")),
                "title": clean(item_attr(item, "title")) or "Untitled station",
                "subtitle": "Global Player",
                "album_art": album_art_url(
                    item_attr(item, "album_art_uri"), clean(getattr(coordinator, "ip_address", ""))
                ),
                "playable": bool(item_attr(item, "can_play", False))
                and bool(item_attr(item, "resources", [])),
            }
        )
    return {
        "ok": True,
        "kind": "global",
        "items": items,
        "total": result_total(result) if result else 0,
    }


def browse_content(coordinator: Any, kind: str, term: str, limit: int) -> dict[str, Any]:
    if kind not in CONTENT_KINDS:
        raise ValueError(f"Unsupported content kind: {kind}")
    bounded_limit = max(1, min(int(limit), 100))
    if kind == "apple":
        return apple_content(term, bounded_limit)
    if coordinator is None:
        raise ValueError("A Sonos room is required for this content source")
    if kind == "queue":
        return queue_content(coordinator, bounded_limit)
    if kind == "library":
        return library_content(coordinator, term, bounded_limit)
    if kind == "playlists":
        return playlists_content(coordinator, bounded_limit)
    if kind == "playlist":
        return playlist_content(coordinator, term, bounded_limit)
    return global_content(coordinator, term, bounded_limit)


def browse_service(backend: BrowsePort) -> DomainService:
    return DomainService(
        {
            "content.browse": lambda args: backend.browse_content(
                string_arg(args, "roomUid"),
                string_arg(args, "kind"),
                str(args.get("term", "")),
                int(number_arg(args, "limit")),
            )
        },
        mutates=False,
    )
