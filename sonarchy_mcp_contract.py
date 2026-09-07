"""Stable declarations shared by the two independent local MCP boundaries."""

from __future__ import annotations

import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, NotRequired, TypedDict

MCP_PERMISSION_READ = "read"
MCP_PERMISSION_PLAYLIST_CREATE = "playlist-create"
MCP_PERMISSION_PLAYLIST_PLAY = "playlist-play"
MCP_PERMISSIONS = frozenset(
    {MCP_PERMISSION_READ, MCP_PERMISSION_PLAYLIST_CREATE, MCP_PERMISSION_PLAYLIST_PLAY}
)
MCP_DEFAULT_PERMISSIONS = frozenset({MCP_PERMISSION_READ})
MCP_DISABLED_PERMISSIONS: frozenset[str] = frozenset()


class BrowseWireArguments(TypedDict):
    """MCP-validated routing; the backend still validates the opaque arguments."""

    roomUid: str
    kind: str
    term: object
    limit: object
    context: object
    storefront: NotRequired[str]


@dataclass(frozen=True)
class BrowseRequest:
    """Backend-normalized scalars; context still needs source-specific validation."""

    room_uid: str
    kind: str
    term: str
    limit: int
    context: object = None
    storefront: str | None = None


type SongExplicitness = Literal["cleaned", "explicit", "notExplicit", "unknown"]


class AppleSongResult(TypedDict):
    id: str
    title: str
    subtitle: str
    artist: str | None
    album: str | None
    durationMs: int | None
    explicitness: SongExplicitness
    section: Literal["SONGS"]
    media_kind: Literal["song"]
    album_art: str
    url: str
    album_url: str
    playable: Literal[True]
    browsable: Literal[False]


class AppleArtistResult(TypedDict):
    id: str
    title: str
    subtitle: str
    section: Literal["ARTISTS"]
    media_kind: Literal["artist"]
    browse_kind: Literal["apple-artist"]
    album_art: str
    playable: Literal[False]
    browsable: Literal[True]


class AppleAlbumResult(TypedDict):
    id: str
    title: str
    subtitle: str
    section: Literal["ALBUMS"]
    media_kind: Literal["album"]
    browse_kind: Literal["apple-album"]
    album_art: str
    album_url: str
    playable: bool
    browsable: Literal[True]


type AppleBrowseItem = AppleSongResult | AppleArtistResult | AppleAlbumResult


class AppleBrowseResult(TypedDict):
    ok: Literal[True]
    kind: Literal["apple", "apple-artist", "apple-album"]
    items: list[AppleBrowseItem]
    total: int
    current_title: str


def normalize_browse_storefront(kind: str, value: object) -> str:
    if kind not in {"apple", "apple-artist", "apple-album"}:
        raise ValueError("storefront is only supported for Apple content")
    if not isinstance(value, str) or len(value) != 2 or not value.isascii() or not value.isalpha():
        raise ValueError("storefront must be a two-letter country code, such as GB")
    return value.upper()


MCP_CONFIG_DIRECTORY = "sonarchy"
MCP_CONFIG_FILENAME = "mcp.toml"
MAX_MCP_CONFIG_BYTES = 8 * 1024
MAX_SONOS_PLAYLIST_ID_LENGTH = 32

MCP_OPERATION_STATE_REFRESH = "state.refresh"
MCP_OPERATION_CONTENT_BROWSE = "content.browse"
MCP_OPERATION_APPLE_VALIDATE = "playlist_plan.apple.validate"
MCP_OPERATION_APPLE_CREATE = "playlists.apple.create"
MCP_OPERATION_PLAY_VALIDATE = "playlists.play.validate"
MCP_OPERATION_PLAY_EXECUTE = "playlists.play.execute"

MCP_SOCKET_OPERATIONS = frozenset(
    {
        MCP_OPERATION_STATE_REFRESH,
        MCP_OPERATION_CONTENT_BROWSE,
        MCP_OPERATION_APPLE_VALIDATE,
        MCP_OPERATION_APPLE_CREATE,
        MCP_OPERATION_PLAY_VALIDATE,
        MCP_OPERATION_PLAY_EXECUTE,
    }
)
MCP_DOMAIN_OPERATIONS = MCP_SOCKET_OPERATIONS - {MCP_OPERATION_STATE_REFRESH}

MCP_OPERATION_PERMISSIONS = MappingProxyType(
    {
        MCP_OPERATION_STATE_REFRESH: MCP_PERMISSION_READ,
        MCP_OPERATION_CONTENT_BROWSE: MCP_PERMISSION_READ,
        MCP_OPERATION_APPLE_VALIDATE: MCP_PERMISSION_READ,
        MCP_OPERATION_PLAY_VALIDATE: MCP_PERMISSION_READ,
        MCP_OPERATION_APPLE_CREATE: MCP_PERMISSION_PLAYLIST_CREATE,
        MCP_OPERATION_PLAY_EXECUTE: MCP_PERMISSION_PLAYLIST_PLAY,
    }
)

MCP_TOOL_ROOMS_LIST = "rooms_list"
MCP_TOOL_ROOM_STATE_GET = "room_state_get"
MCP_TOOL_CONTENT_BROWSE = "content_browse"
MCP_TOOL_APPLE_PREFLIGHT = "apple_playlist_preflight"
MCP_TOOL_PLAY_PREFLIGHT = "sonos_playlist_play_preflight"
MCP_TOOL_APPLE_CREATE = "apple_playlist_create"
MCP_TOOL_PLAY = "sonos_playlist_play"
MCP_TOOL_ORDER = (
    MCP_TOOL_ROOMS_LIST,
    MCP_TOOL_ROOM_STATE_GET,
    MCP_TOOL_CONTENT_BROWSE,
    MCP_TOOL_APPLE_PREFLIGHT,
    MCP_TOOL_PLAY_PREFLIGHT,
    MCP_TOOL_APPLE_CREATE,
    MCP_TOOL_PLAY,
)
MCP_TOOL_OPERATIONS = MappingProxyType(
    {
        MCP_TOOL_ROOMS_LIST: MCP_OPERATION_STATE_REFRESH,
        MCP_TOOL_ROOM_STATE_GET: MCP_OPERATION_STATE_REFRESH,
        MCP_TOOL_CONTENT_BROWSE: MCP_OPERATION_CONTENT_BROWSE,
        MCP_TOOL_APPLE_PREFLIGHT: MCP_OPERATION_APPLE_VALIDATE,
        MCP_TOOL_PLAY_PREFLIGHT: MCP_OPERATION_PLAY_VALIDATE,
        MCP_TOOL_APPLE_CREATE: MCP_OPERATION_APPLE_CREATE,
        MCP_TOOL_PLAY: MCP_OPERATION_PLAY_EXECUTE,
    }
)


@dataclass(frozen=True)
class ArgumentFields:
    required: frozenset[str]
    optional: frozenset[str] = frozenset()

    @property
    def allowed(self) -> frozenset[str]:
        return self.required | self.optional

    def accepts(self, keys: Iterable[str]) -> bool:
        received = frozenset(keys)
        return self.required <= received <= self.allowed


MCP_PUBLIC_FIELDS = MappingProxyType(
    {
        MCP_TOOL_ROOMS_LIST: ArgumentFields(frozenset()),
        MCP_TOOL_ROOM_STATE_GET: ArgumentFields(frozenset({"roomUid"})),
        MCP_TOOL_CONTENT_BROWSE: ArgumentFields(
            frozenset({"kind", "term", "limit", "context"}), frozenset({"roomUid", "storefront"})
        ),
        MCP_TOOL_APPLE_PREFLIGHT: ArgumentFields(
            frozenset({"roomUid", "name", "allowDuplicates", "tracks"})
        ),
        MCP_TOOL_PLAY_PREFLIGHT: ArgumentFields(frozenset({"roomUid", "playlistId"})),
        MCP_TOOL_APPLE_CREATE: ArgumentFields(frozenset({"planHandle", "approved"})),
        MCP_TOOL_PLAY: ArgumentFields(frozenset({"planHandle", "approved"})),
    }
)
MCP_BACKEND_FIELDS = MappingProxyType(
    {
        MCP_OPERATION_STATE_REFRESH: ArgumentFields(frozenset()),
        MCP_OPERATION_CONTENT_BROWSE: ArgumentFields(
            frozenset({"roomUid", "kind", "limit"}), frozenset({"term", "context", "storefront"})
        ),
        MCP_OPERATION_APPLE_VALIDATE: ArgumentFields(
            frozenset({"roomUid", "playlistName", "mode", "tracks"}),
            frozenset({"allowDuplicates"}),
        ),
        MCP_OPERATION_PLAY_VALIDATE: ArgumentFields(frozenset({"roomUid", "playlistId"})),
        MCP_OPERATION_APPLE_CREATE: ArgumentFields(frozenset({"planToken", "approved"})),
        MCP_OPERATION_PLAY_EXECUTE: ArgumentFields(frozenset({"planToken", "approved"})),
    }
)


def parse_mcp_permissions(raw: bytes) -> frozenset[str]:
    """Parse bounded configuration bytes without performing filesystem policy."""
    try:
        value = tomllib.loads(raw.decode("utf-8"))
    except UnicodeDecodeError, ValueError:
        return MCP_DEFAULT_PERMISSIONS
    if value.get("enabled") is not True:
        return MCP_DISABLED_PERMISSIONS
    permissions = value.get("permissions")
    if not isinstance(permissions, list) or not all(isinstance(item, str) for item in permissions):
        return MCP_DEFAULT_PERMISSIONS
    selected = frozenset(permissions)
    if MCP_PERMISSION_READ not in selected or not selected <= MCP_PERMISSIONS:
        return MCP_DEFAULT_PERMISSIONS
    return selected
