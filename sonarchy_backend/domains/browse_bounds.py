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
TRUNCATION_MARKER = "…"
MAX_ENVELOPE_REVISION = (1 << 63) - 1

DISPLAY_TITLE_FIELDS = frozenset({"title", "playlist_title", "current_title"})
DISPLAY_TEXT_FIELDS = frozenset({"subtitle", "section", "media_kind", "browse_kind"})
IDENTITY_FIELDS = frozenset({"id", "url", "album_url"})


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


def _complete_identity(raw: Any) -> str | None:
    if (
        not isinstance(raw, str)
        or not raw
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
    identity = _complete_identity(item.get("id"))
    if identity is None:
        return None
    item["id"] = identity
    for field in IDENTITY_FIELDS - {"id"}:
        if field not in item or item[field] in (None, ""):
            continue
        complete = _complete_identity(item[field])
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

    items: list[dict[str, Any]] = []
    identity_failure_index: int | None = None
    for source_index, raw_item in enumerate(source_items):
        item = _bounded_item(raw_item)
        if item is None:
            identity_failure_index = source_index
            break
        items.append(item)
    value["items"] = items

    for field in DISPLAY_TITLE_FIELDS:
        if field in value:
            value[field] = bounded_display_text(value[field], DISPLAY_TITLE_BYTES)
    if isinstance(value.get("shares"), list):
        value["shares"] = [bounded_display_text(share) for share in value["shares"][:32]]
    if isinstance(value.get("breadcrumbs"), list):
        breadcrumbs = []
        for raw_crumb in value["breadcrumbs"]:
            if not isinstance(raw_crumb, dict) or _complete_identity(raw_crumb.get("id")) is None:
                break
            crumb = copy.deepcopy(raw_crumb)
            crumb["title"] = bounded_display_text(crumb.get("title"), DISPLAY_TITLE_BYTES)
            breadcrumbs.append(crumb)
        value["breadcrumbs"] = breadcrumbs

    value["returned_count"] = len(items)
    value["requested_limit"] = max(1, min(int(requested_limit), 100))
    value["result_truncated"] = identity_failure_index is not None
    if identity_failure_index is not None:
        value["omitted_count"] = 1

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
