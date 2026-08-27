from __future__ import annotations

from typing import Any

from .common import DomainService, coordinator_for, number_arg, string_arg
from .media import (
    clean,
    find_playlist_track,
    item_attr,
    safe_call,
    safe_index,
    validate_identifier,
)
from .ports import QueuePort


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


def find_library_item(coordinator: Any, item_id: str, term: str) -> Any:
    expected_id = validate_identifier(item_id, "library item identifier")
    result = coordinator.music_library.get_music_library_information(
        "tracks", max_items=100, search_term=_validate_search_term(term)
    )
    for item in result:
        if clean(item_attr(item, "item_id")) == expected_id:
            return item
    raise ValueError("The library item is no longer available")


def enqueue_content_item(
    speaker: Any,
    kind: str,
    context: str,
    item_id: str,
    index: int,
    mode: str,
) -> dict[str, Any]:
    coordinator = coordinator_for(speaker)
    if kind == "library":
        item = find_library_item(coordinator, item_id, context)
    elif kind == "playlist":
        _, item, _ = find_playlist_track(coordinator, context, index, item_id)
    else:
        raise ValueError("Only library and playlist items can be queued here")
    if not item_attr(item, "resources", []):
        raise ValueError("This item does not contain a playable resource")
    if mode not in {"play", "next", "end"}:
        raise ValueError("Unsupported queue position")
    if mode == "next":
        current = safe_call(coordinator.get_current_track_info, {}) or {}
        current_position = max(0, safe_index(current.get("playlist_position"), 0))
        coordinator.add_to_queue(item, position=current_position + 1 if current_position else 1)
        message = "Added next"
    else:
        queue_position = coordinator.add_to_queue(item)
        if mode == "play":
            coordinator.play_from_queue(max(0, int(queue_position) - 1))
            message = "Playing from the queue"
        else:
            message = "Added to the queue"
    return {"ok": True, "action": f"queue-{mode}", "message": message}


def queue_service(backend: QueuePort) -> DomainService:
    def index_arg(args: dict[str, Any]) -> int:
        value = number_arg(args, "index")
        if int(value) != value:
            raise ValueError("index must be an integer")
        return int(value)

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
                string_arg(args, "context"),
                string_arg(args, "itemId"),
                index_arg(args),
                string_arg(args, "mode"),
            ),
        }
    )
