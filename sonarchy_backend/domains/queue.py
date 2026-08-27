from __future__ import annotations

from typing import Any

from .capabilities import queue_transport_active
from .common import DomainService, coordinator_for, number_arg, string_arg
from .library import library_item_at, validate_library_context
from .media import (
    clean,
    find_playlist_track,
    item_attr,
    safe_call,
    safe_index,
    validate_identifier,
)
from .ports import QueuePort

MAX_REPLACE_BACKUP_ITEMS = 100


def queue_action(
    speaker: Any,
    action: str,
    index: int | None = None,
    expected_item_id: str = "",
) -> dict[str, Any]:
    coordinator = coordinator_for(speaker)
    if action in {"play-queue", "remove-queue"}:
        if index is None or index < 0:
            raise ValueError("Queue index is required")
        expected = validate_identifier(expected_item_id, "queue item identifier")
        result = coordinator.get_queue(max_items=100, full_album_art_uri=False)
        if index >= len(result):
            raise ValueError("The queue changed; refresh it and try again")
        actual = clean(item_attr(result[index], "item_id")) or str(index)
        if actual != expected:
            raise ValueError("The queue changed; refresh it and try again")

    if action == "play-queue":
        coordinator.play_from_queue(index)
        message = "Playing queue item"
    elif action == "remove-queue":
        coordinator.remove_from_queue(index)
        message = "Removed from queue"
    elif action == "clear-queue":
        coordinator.clear_queue()
        message = "Queue cleared"
    else:
        raise ValueError(f"Unsupported queue action: {action}")
    return {"ok": True, "action": action, "message": message}


def _validate_search_term(raw: Any) -> str:
    value = clean(raw)
    if not value:
        raise ValueError("Search text is required")
    if len(value) > 120 or any(ord(character) < 32 for character in value):
        raise ValueError("Search text is too long or contains control characters")
    return value


def find_library_item(
    coordinator: Any,
    item_id: str,
    term: str,
    index: int = 0,
    library_path: Any = None,
) -> Any:
    path_value = [] if library_path is None else library_path
    path, _ = validate_library_context({"path": path_value, "offset": 0})
    query = _validate_search_term(term) if clean(term) else ""
    if query and path:
        raise ValueError("Library search must start from the library root")
    return library_item_at(
        coordinator.music_library,
        path=path,
        index=index,
        item_id=item_id,
        search_term=query,
    )


def _replace_backup(coordinator: Any) -> tuple[list[Any], bool, int, bool]:
    result = coordinator.get_queue(
        max_items=MAX_REPLACE_BACKUP_ITEMS,
        full_album_art_uri=False,
    )
    items = list(result)
    total = safe_index(item_attr(result, "total_matches", len(items)), len(items))
    if total != len(items) or total > MAX_REPLACE_BACKUP_ITEMS:
        raise ValueError("The queue is too large to replace safely")
    if any(not item_attr(item, "resources", []) for item in items):
        raise ValueError("The current queue cannot be backed up safely")

    active = queue_transport_active(coordinator)
    if active is None:
        raise ValueError("The current playback source could not be verified")
    track = safe_call(coordinator.get_current_track_info, {}) or {}
    position = safe_index(track.get("playlist_position"), 0) - 1
    if active and items and not 0 <= position < len(items):
        raise ValueError("The current queue position could not be verified")
    transport = safe_call(coordinator.get_current_transport_info, {}) or {}
    was_playing = clean(transport.get("current_transport_state")).upper() == "PLAYING"
    return items, active, position, was_playing


def _restore_replaced_queue(
    coordinator: Any,
    items: list[Any],
    active: bool,
    position: int,
    was_playing: bool,
) -> None:
    coordinator.clear_queue()
    if not items:
        return
    coordinator.add_multiple_to_queue(items)
    if active:
        coordinator.play_from_queue(position, start=was_playing)


def _replace_queue(coordinator: Any, item: Any) -> int:
    backup, active, position, was_playing = _replace_backup(coordinator)
    try:
        coordinator.clear_queue()
        queue_position = int(coordinator.add_to_queue(item))
        coordinator.play_from_queue(max(0, queue_position - 1))
        return queue_position
    except Exception:
        try:
            _restore_replaced_queue(coordinator, backup, active, position, was_playing)
        except Exception as recovery_error:
            raise RuntimeError(
                "Queue replacement failed and the previous queue could not be restored"
            ) from recovery_error
        raise


def enqueue_content_item(
    speaker: Any,
    kind: str,
    context: str,
    item_id: str,
    index: int,
    mode: str,
    library_path: Any = None,
) -> dict[str, Any]:
    coordinator = coordinator_for(speaker)
    if kind == "library":
        item = find_library_item(coordinator, item_id, context, index, library_path)
    elif kind == "playlist":
        _, item, _ = find_playlist_track(coordinator, context, index, item_id)
    else:
        raise ValueError("Only library and playlist items can be queued here")
    if not item_attr(item, "resources", []):
        raise ValueError("This item does not contain a playable resource")
    if mode not in {"play", "next", "end", "replace"}:
        raise ValueError("Unsupported queue position")
    if mode == "replace":
        _replace_queue(coordinator, item)
        message = "Replaced the queue and started playback"
    elif mode in {"play", "next"}:
        current = safe_call(coordinator.get_current_track_info, {}) or {}
        current_position = max(0, safe_index(current.get("playlist_position"), 0))
        queue_position = coordinator.add_to_queue(
            item, position=current_position + 1 if current_position else 1
        )
        if mode == "play":
            coordinator.play_from_queue(max(0, int(queue_position) - 1))
            message = "Playing now"
        else:
            message = "Added next"
    else:
        coordinator.add_to_queue(item)
        message = "Added to the queue"
    return {"ok": True, "action": f"queue-{mode}", "message": message}


def queue_service(backend: QueuePort) -> DomainService:
    def index_arg(args: dict[str, Any]) -> int:
        value = number_arg(args, "index")
        if int(value) != value:
            raise ValueError("index must be an integer")
        return int(value)

    def context_arg(args: dict[str, Any]) -> str:
        value = args.get("context", "")
        if not isinstance(value, str):
            raise ValueError("context must be a string")
        return value

    return DomainService(
        {
            "queue.item.play": lambda args: backend.queue_action(
                string_arg(args, "roomUid"),
                "play-queue",
                index_arg(args),
                string_arg(args, "itemId"),
            ),
            "queue.item.remove": lambda args: backend.queue_action(
                string_arg(args, "roomUid"),
                "remove-queue",
                index_arg(args),
                string_arg(args, "itemId"),
            ),
            "queue.clear": lambda args: backend.queue_action(
                string_arg(args, "roomUid"), "clear-queue"
            ),
            "queue.content.enqueue": lambda args: backend.enqueue_content_item(
                string_arg(args, "roomUid"),
                string_arg(args, "kind"),
                context_arg(args),
                string_arg(args, "itemId"),
                index_arg(args),
                string_arg(args, "mode"),
                args.get("libraryPath", []),
            ),
        }
    )
