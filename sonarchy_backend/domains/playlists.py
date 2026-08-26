from __future__ import annotations

from typing import Any

from .browse import clean, item_attr, safe_call, safe_index, validate_playlist_id
from .common import DomainService, number_arg, string_arg
from .ports import PlaylistsPort
from .queue import find_playlist_track


def _coordinator(speaker: Any) -> Any:
    return (
        safe_call(lambda: speaker.group.coordinator if speaker.group else speaker, speaker)
        or speaker
    )


def _optional(target: Any, name: str) -> Any:
    try:
        return getattr(target, name)
    except Exception:  # noqa: BLE001 - optional SoCo properties are inconsistent
        return None


def validate_playlist_title(raw: Any) -> str:
    title = clean(raw)
    if not title:
        raise ValueError("Playlist name cannot be empty")
    if len(title) > 80 or any(ord(character) < 32 for character in title):
        raise ValueError("Playlist name is too long or contains control characters")
    return title


def playlist_action(speaker: Any, action: str, value: str) -> dict[str, Any]:
    coordinator = _coordinator(speaker)
    if action == "create":
        playlist = coordinator.create_sonos_playlist(validate_playlist_title(value))
        message = f"Created {clean(item_attr(playlist, 'title'))}"
    elif action == "save-queue":
        if not safe_index(_optional(coordinator, "queue_size"), 0):
            raise ValueError("The current queue is empty")
        playlist = coordinator.create_sonos_playlist_from_queue(validate_playlist_title(value))
        message = f"Saved queue as {clean(item_attr(playlist, 'title'))}"
    elif action == "play":
        playlist = coordinator.get_sonos_playlist_by_attr("item_id", validate_playlist_id(value))
        position = coordinator.add_to_queue(playlist)
        coordinator.play_from_queue(max(0, int(position) - 1))
        message = f"Playing {clean(item_attr(playlist, 'title'))}"
    elif action == "delete":
        playlist = coordinator.get_sonos_playlist_by_attr("item_id", validate_playlist_id(value))
        title = clean(item_attr(playlist, "title")) or "Sonos playlist"
        coordinator.remove_sonos_playlist(playlist)
        message = f"Deleted {title}"
    else:
        raise ValueError("Unsupported playlist action")
    return {"ok": True, "action": f"playlist-{action}", "message": message}


def playlist_track_action(
    speaker: Any, action: str, playlist_id: str, index: int, item_id: str
) -> dict[str, Any]:
    coordinator = _coordinator(speaker)
    playlist, _, count = find_playlist_track(coordinator, playlist_id, index, item_id)
    if action == "remove":
        coordinator.remove_from_sonos_playlist(playlist, index)
        message = "Removed from playlist"
    elif action == "up":
        if index <= 0:
            raise ValueError("This item is already first")
        coordinator.move_in_sonos_playlist(playlist, index, index - 1)
        message = "Moved up"
    elif action == "down":
        if index >= count - 1:
            raise ValueError("This item is already last")
        coordinator.move_in_sonos_playlist(playlist, index, index + 1)
        message = "Moved down"
    else:
        raise ValueError("Unsupported playlist track action")
    return {"ok": True, "action": f"playlist-track-{action}", "message": message}


def playlists_service(backend: PlaylistsPort) -> DomainService:
    def index_arg(args: dict[str, Any]) -> int:
        value = number_arg(args, "index")
        if int(value) != value:
            raise ValueError("index must be an integer")
        return int(value)

    return DomainService(
        {
            "playlists.mutate": lambda args: backend.playlist_action(
                string_arg(args, "roomUid"), string_arg(args, "action"), string_arg(args, "value")
            ),
            "playlists.track.mutate": lambda args: backend.playlist_track_action(
                string_arg(args, "roomUid"),
                string_arg(args, "action"),
                string_arg(args, "playlistId"),
                index_arg(args),
                string_arg(args, "itemId"),
            ),
        }
    )
