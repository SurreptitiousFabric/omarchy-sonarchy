from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .common import DomainService, coordinator_for, number_arg, string_arg
from .media import (
    clean,
    find_playlist_track,
    item_attr,
    safe_index,
    validate_playlist_id,
)
from .playlist_rules import validate_playlist_title
from .ports import PlaylistsPort


class PlaylistPlayStepError(RuntimeError):
    def __init__(
        self,
        phase: str,
        *,
        append_state: str,
        playback_started: bool,
        position: int | None = None,
    ) -> None:
        super().__init__("Exact Sonos Playlist playback failed")
        self.phase = phase
        self.append_state = append_state
        self.playback_started = playback_started
        self.position = position


def append_and_start_playlist(
    coordinator: Any,
    playlist: Any,
    *,
    expected_first_position: int | None = None,
    mutation_started_callback: Callable[[], None] | None = None,
) -> int:
    if mutation_started_callback is not None:
        mutation_started_callback()
    try:
        raw_position = coordinator.add_to_queue(playlist)
    except Exception as exc:
        raise PlaylistPlayStepError(
            "append_playlist", append_state="unknown", playback_started=False
        ) from exc
    position = safe_index(raw_position, -1)
    if position < 1 or (
        expected_first_position is not None and position != expected_first_position
    ):
        raise PlaylistPlayStepError(
            "append_playlist",
            append_state="confirmed",
            playback_started=False,
            position=position if position >= 1 else None,
        )
    try:
        coordinator.play_from_queue(position - 1)
    except Exception as exc:
        raise PlaylistPlayStepError(
            "start_playback",
            append_state="confirmed",
            playback_started=False,
            position=position,
        ) from exc
    return position


def _optional(target: Any, name: str) -> Any:
    try:
        return getattr(target, name)
    except Exception:  # noqa: BLE001 - optional SoCo properties are inconsistent
        return None


def playlist_action(speaker: Any, action: str, value: str) -> dict[str, Any]:
    coordinator = coordinator_for(speaker)
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
        append_and_start_playlist(coordinator, playlist)
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
    coordinator = coordinator_for(speaker)
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
