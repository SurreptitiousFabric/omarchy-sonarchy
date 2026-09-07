"""The checked browse-routing slice of the otherwise generic MCP transport."""

from __future__ import annotations

from collections.abc import Mapping

from sonarchy_mcp_contract import (
    MCP_PUBLIC_FIELDS,
    MCP_TOOL_CONTENT_BROWSE,
    BrowseWireArguments,
    normalize_browse_storefront,
)

READ_KINDS = frozenset(
    {"queue", "playlists", "playlist", "library", "global", "apple", "apple-album", "apple-artist"}
)


def browse_arguments(arguments: Mapping[str, object]) -> BrowseWireArguments:
    """Validate routing only; preserve backend ownership of term/limit/context."""
    if not MCP_PUBLIC_FIELDS[MCP_TOOL_CONTENT_BROWSE].accepts(arguments):
        raise ValueError("Invalid content_browse inputs")
    kind = str(arguments["kind"])
    if kind not in READ_KINDS:
        raise ValueError("Unsupported content kind")
    storefront = (
        normalize_browse_storefront(kind, arguments["storefront"])
        if "storefront" in arguments
        else None
    )
    room_uid = arguments.get("roomUid", "")
    if not isinstance(room_uid, str) or (room_uid and not room_uid.strip()):
        raise ValueError("roomUid must be an exact room UID or empty")
    if not room_uid and kind not in {"apple", "apple-artist", "apple-album"}:
        raise ValueError("roomUid is required for Sonos-backed content")
    result: BrowseWireArguments = {
        "roomUid": room_uid,
        "kind": kind,
        "term": arguments["term"],
        "limit": arguments["limit"],
        "context": arguments["context"],
    }
    if storefront is not None:
        result["storefront"] = storefront
    return result
