from __future__ import annotations

from collections.abc import Callable
from typing import Any

from soco.data_structures import to_didl_string
from soco.music_services import MusicService
from soco.plugins.sharelink import ShareLinkPlugin

from ..apple_catalog import public_apple_album_url, public_apple_music_url
from .browse import clean, global_results, item_attr, safe_call, validate_identifier
from .common import DomainService, string_arg
from .ports import ContentPort
from .settings import tv_autoplay_enabled


def _coordinator(speaker: Any) -> Any:
    return (
        safe_call(lambda: speaker.group.coordinator if speaker.group else speaker, speaker)
        or speaker
    )


def play_apple(
    speaker: Any, url: str, *, share_link_factory: Callable[..., Any] = ShareLinkPlugin
) -> dict[str, Any]:
    validated = public_apple_music_url(url)
    if not validated:
        raise ValueError("Expected an Apple Music link")
    coordinator = _coordinator(speaker)
    position = share_link_factory(coordinator).add_share_link_to_queue(validated)
    coordinator.play_from_queue(max(0, int(position) - 1))
    return {"ok": True, "action": "play-apple", "message": "Playing from Apple Music"}


def play_apple_album(
    speaker: Any, url: str, *, share_link_factory: Callable[..., Any] = ShareLinkPlugin
) -> dict[str, Any]:
    validated = public_apple_album_url(url)
    if not validated:
        raise ValueError("Expected an Apple Music album link")
    coordinator = _coordinator(speaker)
    try:
        source = coordinator.music_source
    except Exception:  # noqa: BLE001 - optional SoCo source is inconsistent
        source = None
    if clean(source).upper() == "TV" and tv_autoplay_enabled(coordinator) is True:
        raise ValueError(
            "TV Autoplay is on while TV audio is active. Select the home-theater room, "
            "turn off TV Autoplay in System, then play the album again."
        )
    position = share_link_factory(coordinator).add_share_link_to_queue(validated)
    coordinator.play_from_queue(max(0, int(position) - 1))
    return {"ok": True, "action": "play-apple-album", "message": "Playing Apple Music album"}


def play_global(
    speaker: Any,
    item_id: str,
    term: str,
    *,
    music_service_factory: Callable[..., Any] = MusicService,
    results_fn: Callable[[Any, str, int], Any] | None = None,
    metadata_fn: Callable[[Any], str] = to_didl_string,
) -> dict[str, Any]:
    coordinator = _coordinator(speaker)
    expected = validate_identifier(item_id, "Global Player item identifier")
    results = (
        results_fn(coordinator, term, 50)
        if results_fn is not None
        else global_results(coordinator, term, 50, music_service_factory=music_service_factory)
    )
    for item in results:
        if clean(item_attr(item, "item_id")) != expected:
            continue
        resources = item_attr(item, "resources", [])
        if not item_attr(item, "can_play", False) or not resources:
            raise ValueError("This Global Player result is not directly playable")
        coordinator.play_uri(resources[0].uri, meta=metadata_fn(item))
        return {
            "ok": True,
            "action": "play-global",
            "message": f"Playing {clean(item_attr(item, 'title'))}",
        }
    raise ValueError("Global Player result no longer exists")


def start_library_update(speaker: Any) -> dict[str, Any]:
    coordinator = _coordinator(speaker)
    if bool(safe_call(lambda: coordinator.music_library.library_updating, False)):
        return {
            "ok": True,
            "action": "library-update",
            "message": "Library update is already running",
        }
    coordinator.music_library.start_library_update()
    return {"ok": True, "action": "library-update", "message": "Library update started"}


def content_service(backend: ContentPort) -> DomainService:
    return DomainService(
        {
            "content.favorite.play": lambda args: backend.play_favorite(
                string_arg(args, "favoriteId")
            ),
            "content.favorites.refresh": lambda _args: backend.refresh_favorites(),
            "content.apple.play": lambda args: backend.play_apple(
                string_arg(args, "roomUid"), string_arg(args, "url")
            ),
            "content.apple.album.play": lambda args: backend.play_apple_album(
                string_arg(args, "roomUid"), string_arg(args, "url")
            ),
            "content.global.play": lambda args: backend.play_global(
                string_arg(args, "roomUid"),
                string_arg(args, "itemId"),
                string_arg(args, "term"),
            ),
            "library.update.start": lambda args: backend.start_library_update(
                string_arg(args, "roomUid")
            ),
        }
    )
