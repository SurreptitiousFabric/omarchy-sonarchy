from __future__ import annotations

import copy
from typing import Any

from ..contracts import (
    MAX_PROTOCOL_LINE_BYTES,
    MAX_PROTOCOL_REQUEST_ID_BYTES,
    protocol_line,
    result_payload,
)
from .library import MAX_LIBRARY_INDEX

DISPLAY_TEXT_BYTES = 512
DISPLAY_TITLE_BYTES = 256
ARTWORK_URL_BYTES = 2048
BROWSE_IDENTITY_BYTES = 512
BROWSE_ACTION_URL_BYTES = 1024
BROWSE_PLAYLIST_ID_BYTES = 32
TRUNCATION_MARKER = "…"
MAX_ENVELOPE_REVISION = (1 << 63) - 1

DISPLAY_TITLE_FIELDS = frozenset({"title", "playlist_title", "current_title"})
DISPLAY_TEXT_FIELDS = frozenset({"subtitle", "section", "media_kind", "browse_kind"})
ACTION_IDENTITY_FIELDS = frozenset({"url", "album_url"})


def bounded_display_text(raw: Any, maximum_bytes: int = DISPLAY_TEXT_BYTES) -> str:
    """Return deterministic, control-free display text within a UTF-8 byte bound."""

    value = "".join(
        character
        for character in str(raw or "").strip()
        if ord(character) >= 32 and ord(character) != 127
    )
    encoded = value.encode("utf-8")
    if len(encoded) <= maximum_bytes:
        return value
    marker = TRUNCATION_MARKER.encode("utf-8")
    prefix = encoded[: maximum_bytes - len(marker)].decode("utf-8", errors="ignore")
    return prefix + TRUNCATION_MARKER


def _complete_identity(raw: Any, maximum_bytes: int) -> str | None:
    if (
        not isinstance(raw, str)
        or not raw
        or len(raw.encode("utf-8")) > maximum_bytes
        or any(ord(character) < 32 or ord(character) == 127 for character in raw)
    ):
        return None
    return raw


def _bounded_artwork(raw: Any) -> str:
    value = str(raw or "")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        return ""
    return value if len(value.encode("utf-8")) <= ARTWORK_URL_BYTES else ""


def _bounded_item(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    item = copy.deepcopy(raw)
    identity = _complete_identity(item.get("id"), BROWSE_IDENTITY_BYTES)
    if identity is None:
        return None
    item["id"] = identity
    for field in ACTION_IDENTITY_FIELDS:
        if field not in item or item[field] in (None, ""):
            continue
        complete = _complete_identity(item[field], BROWSE_ACTION_URL_BYTES)
        if complete is None:
            return None
        item[field] = complete
    for field in DISPLAY_TITLE_FIELDS:
        if field in item:
            item[field] = bounded_display_text(item[field], DISPLAY_TITLE_BYTES)
    for field in DISPLAY_TEXT_FIELDS:
        if field in item:
            item[field] = bounded_display_text(item[field])
    if "album_art" in item:
        item["album_art"] = _bounded_artwork(item["album_art"])
    return item


def _bound_navigation_identities(value: dict[str, Any]) -> None:
    raw_breadcrumbs = value.get("breadcrumbs")
    raw_path = value.get("path")
    if not isinstance(raw_breadcrumbs, list) or not isinstance(raw_path, list):
        return
    breadcrumbs: list[dict[str, Any]] = []
    path: list[dict[str, Any]] = []
    for raw_crumb, raw_segment in zip(raw_breadcrumbs, raw_path, strict=False):
        if not isinstance(raw_crumb, dict) or not isinstance(raw_segment, dict):
            break
        crumb_id = _complete_identity(raw_crumb.get("id"), BROWSE_IDENTITY_BYTES)
        segment_id = _complete_identity(raw_segment.get("id"), BROWSE_IDENTITY_BYTES)
        if (
            crumb_id is None
            or segment_id != crumb_id
            or raw_crumb.get("index") != raw_segment.get("index")
        ):
            break
        crumb = copy.deepcopy(raw_crumb)
        crumb["id"] = crumb_id
        crumb["title"] = bounded_display_text(crumb.get("title"), DISPLAY_TITLE_BYTES)
        segment = copy.deepcopy(raw_segment)
        segment["id"] = segment_id
        breadcrumbs.append(crumb)
        path.append(segment)
    value["breadcrumbs"] = breadcrumbs
    value["path"] = path


def _fits_complete_envelope(value: dict[str, Any], revision: int) -> bool:
    envelope = result_payload(
        "\\" * MAX_PROTOCOL_REQUEST_ID_BYTES,
        revision=max(revision, MAX_ENVELOPE_REVISION),
        value=value,
    )
    return len(protocol_line(envelope).encode("utf-8")) <= MAX_PROTOCOL_LINE_BYTES


def bound_browse_result(
    raw: Any,
    *,
    revision: int,
    requested_limit: int,
) -> dict[str, Any]:
    """Project a useful exact-prefix browse result inside the protocol budget."""

    if not isinstance(raw, dict):
        return raw
    value = copy.deepcopy(raw)
    source_items = value.get("items")
    if not isinstance(source_items, list):
        return value
    if "playlist_id" in value:
        playlist_id = _complete_identity(value["playlist_id"], BROWSE_PLAYLIST_ID_BYTES)
        if playlist_id is None:
            raise ValueError("Browse playlist identity is not representable")
        value["playlist_id"] = playlist_id

    items: list[dict[str, Any]] = []
    identity_failure_index: int | None = None
    omitted_count = 0
    is_library = value.get("kind") == "library"
    for source_index, raw_item in enumerate(source_items):
        item = _bounded_item(raw_item)
        if item is None:
            omitted_count += 1
            if is_library:
                identity_failure_index = source_index
                break
            continue
        items.append(item)
    value["items"] = items

    for field in DISPLAY_TITLE_FIELDS:
        if field in value:
            value[field] = bounded_display_text(value[field], DISPLAY_TITLE_BYTES)
    if isinstance(value.get("shares"), list):
        value["shares"] = [bounded_display_text(share) for share in value["shares"][:32]]
    _bound_navigation_identities(value)

    value["returned_count"] = len(items)
    value["requested_limit"] = max(1, min(int(requested_limit), 100))
    value["result_truncated"] = omitted_count > 0
    if omitted_count:
        value["omitted_count"] = omitted_count

    def update_library_continuation() -> None:
        if value.get("kind") != "library":
            return
        offset = max(0, int(value.get("offset", 0)))
        total = max(offset, int(value.get("total", offset + len(source_items))))
        valid_prefix_count = (
            identity_failure_index if identity_failure_index is not None else len(source_items)
        )
        if len(items) < valid_prefix_count:
            consumed = len(items)
        elif identity_failure_index is not None:
            consumed = identity_failure_index + 1
        else:
            consumed = len(source_items)
        next_offset = min(total, MAX_LIBRARY_INDEX, offset + consumed)
        value["next_offset"] = next_offset
        value["has_next"] = next_offset > offset and next_offset < total

    update_library_continuation()

    while items and not _fits_complete_envelope(value, revision):
        items.pop()
        value["returned_count"] = len(items)
        value["result_truncated"] = True
        update_library_continuation()

    if not _fits_complete_envelope(value, revision):
        raise RuntimeError("Bounded browse metadata exceeds the protocol line size")
    return value
