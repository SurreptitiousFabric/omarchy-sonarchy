from __future__ import annotations

from typing import Any

from soco.data_structures import DidlContainer

from .media import clean, item_attr, validate_identifier

MAX_LIBRARY_DEPTH = 8
MAX_LIBRARY_INDEX = 1_000_000


def _index(raw: Any, label: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int) or not 0 <= raw <= MAX_LIBRARY_INDEX:
        raise ValueError(f"Invalid {label}")
    return raw


def validate_library_context(raw: Any) -> tuple[list[dict[str, Any]], int]:
    if raw is None:
        return [], 0
    if not isinstance(raw, dict):
        raise ValueError("Library context must be an object")
    unknown = set(raw) - {"path", "offset"}
    if unknown:
        raise ValueError("Library context contains unsupported fields")
    raw_path = raw.get("path", [])
    if not isinstance(raw_path, list) or len(raw_path) > MAX_LIBRARY_DEPTH:
        raise ValueError("Invalid library path")
    path: list[dict[str, Any]] = []
    for segment in raw_path:
        if not isinstance(segment, dict) or set(segment) != {"id", "index"}:
            raise ValueError("Invalid library path segment")
        raw_id = segment["id"]
        if not isinstance(raw_id, str) or any(ord(character) < 32 for character in raw_id):
            raise ValueError("Invalid library container identifier")
        path.append(
            {
                "id": validate_identifier(raw_id, "library container identifier"),
                "index": _index(segment["index"], "library container index"),
            }
        )
    return path, _index(raw.get("offset", 0), "library page offset")


def is_library_container(item: Any) -> bool:
    if isinstance(item, DidlContainer):
        return True
    item_class = clean(item_attr(item, "item_class"))
    return item_class.startswith("object.container") or bool(item_attr(item, "browsable", False))


def resolve_library_path(
    library: Any, path: list[dict[str, Any]]
) -> tuple[Any | None, list[dict[str, Any]]]:
    current = None
    breadcrumbs: list[dict[str, Any]] = []
    for segment in path:
        result = library.browse(
            ml_item=current,
            start=segment["index"],
            max_items=1,
            full_album_art_uri=False,
        )
        if len(result) != 1:
            raise ValueError("The music library changed; return to the library root")
        candidate = result[0]
        if clean(item_attr(candidate, "item_id")) != segment["id"]:
            raise ValueError("The music library changed; return to the library root")
        if not is_library_container(candidate):
            raise ValueError("The selected music-library item cannot be browsed")
        current = candidate
        breadcrumbs.append(
            {
                "id": segment["id"],
                "index": segment["index"],
                "title": clean(item_attr(candidate, "title"))[:512] or "Untitled folder",
            }
        )
    return current, breadcrumbs


def library_item_at(
    library: Any,
    *,
    path: list[dict[str, Any]],
    index: int,
    item_id: str,
    search_term: str = "",
) -> Any:
    expected_id = validate_identifier(item_id, "library item identifier")
    absolute_index = _index(index, "library item index")
    if search_term:
        result = library.get_music_library_information(
            "tracks",
            start=absolute_index,
            max_items=1,
            search_term=search_term,
            full_album_art_uri=False,
        )
    else:
        parent, _ = resolve_library_path(library, path)
        result = library.browse(
            ml_item=parent,
            start=absolute_index,
            max_items=1,
            full_album_art_uri=False,
        )
    if len(result) != 1 or clean(item_attr(result[0], "item_id")) != expected_id:
        raise ValueError("The library item is no longer available; refresh and try again")
    return result[0]
