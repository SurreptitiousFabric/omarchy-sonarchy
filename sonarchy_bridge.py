#!/usr/bin/env python3
"""JSON bridge between Quickshell and Sonos speakers on the local network.

The bridge deliberately has no server. Quickshell starts it for one snapshot,
browse request, or control action, reads a single JSON object from stdout, and
the process exits. Transport and queue commands are routed to a room's group
coordinator; room volume, grouping, names, and sound settings remain explicit.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import tempfile
from collections.abc import Iterable
from datetime import time
from pathlib import Path
from typing import Any

import requests
import soco
from soco import SoCo, config
from soco.alarms import Alarm, get_alarms
from soco.data_structures import to_didl_string
from soco.music_services import MusicService
from soco.plugins.sharelink import ShareLinkPlugin

from sonarchy_backend.apple_catalog import APPLE_RESPONSE_LIMIT as CATALOG_RESPONSE_LIMIT
from sonarchy_backend.apple_catalog import apple_search_results as catalog_search_results
from sonarchy_backend.apple_catalog import (
    public_apple_album_url,
    public_apple_music_url,
)
from sonarchy_backend.apple_catalog import resolve_apple_artwork as catalog_resolve_artwork
from sonarchy_backend.domains.alarms import project_alarms
from sonarchy_backend.domains.browse import (
    album_art_url,
    browse_content,
)
from sonarchy_backend.domains.browse import apple_content as browse_apple_content
from sonarchy_backend.domains.browse import didl_item_payload as browse_didl_item_payload
from sonarchy_backend.domains.browse import favorite_reference as browse_favorite_reference
from sonarchy_backend.domains.browse import favorites_content as browse_favorites_content
from sonarchy_backend.domains.browse import global_content as browse_global_content
from sonarchy_backend.domains.browse import global_results as browse_global_results
from sonarchy_backend.domains.browse import item_attr as browse_item_attr
from sonarchy_backend.domains.browse import library_content as browse_library_content
from sonarchy_backend.domains.browse import playlist_content as browse_playlist_content
from sonarchy_backend.domains.browse import playlists_content as browse_playlists_content
from sonarchy_backend.domains.browse import public_artwork_url as browse_public_artwork_url
from sonarchy_backend.domains.browse import queue_content as browse_queue_content
from sonarchy_backend.domains.browse import validate_identifier as browse_validate_identifier
from sonarchy_backend.domains.browse import validate_playlist_id as browse_validate_playlist_id
from sonarchy_backend.domains.devices import project_device_details
from sonarchy_backend.domains.settings import (
    BOOLEAN_SETTINGS,
    DEVICE_BOOLEAN_SETTINGS,  # noqa: F401 - compatibility export for callers/tests
    DEVICE_SETTINGS,
    NUMBER_SETTINGS,
    TV_AUTOPLAY_SETTING,  # noqa: F401 - compatibility export for callers/tests
)
from sonarchy_backend.domains.settings import rename_room as rename_sonos_room
from sonarchy_backend.domains.settings import set_device as set_sonos_device
from sonarchy_backend.domains.settings import set_playback_option as set_sonos_playback_option
from sonarchy_backend.domains.settings import set_sound as set_sonos_sound
from sonarchy_backend.domains.settings import switch_source as switch_sonos_source
from sonarchy_errors import user_facing_error

config.REQUEST_TIMEOUT = 3.0
APPLE_RESPONSE_LIMIT = CATALOG_RESPONSE_LIMIT
public_artwork_url = browse_public_artwork_url


def default_cache_path() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "sonarchy" / "rooms.json"


CACHE_PATH = default_cache_path()

APPLE_COUNTRY = os.environ.get(
    "SONARCHY_APPLE_COUNTRY",
    os.environ.get("OMARCHY_SONOS_APPLE_COUNTRY", "CH"),
).upper()
if not re.fullmatch(r"[A-Z]{2}", APPLE_COUNTRY):
    APPLE_COUNTRY = "CH"

PLAYBACK_ACTIONS = {
    "play",
    "pause",
    "play-pause",
    "stop",
    "next",
    "previous",
}
CONTENT_KINDS = {
    "favorites",
    "queue",
    "apple",
    "global",
    "library",
    "playlists",
    "playlist",
}
ALARM_RECURRENCES = {"ONCE", "DAILY", "WEEKDAYS", "WEEKENDS"}
ALARM_DURATIONS = {0, 15, 30, 45, 60, 90, 120}
ALARM_ID_PATTERN = re.compile(r"\d+")
CLI_COMMANDS = frozenset(
    {
        "artwork",
        "status",
        "details",
        "content",
        "alarms",
        *PLAYBACK_ACTIONS,
        "mute-toggle",
        "volume",
        "rename",
        "group",
        "group-all",
        "separate",
        "playback-option",
        "sound",
        "play-favorite",
        "play-queue",
        "remove-queue",
        "clear-queue",
        "queue-content",
        "playlist",
        "playlist-track",
        "library-update",
        "alarm-save",
        "alarm-toggle",
        "alarm-delete",
        "source",
        "device",
        "play-apple",
        "play-apple-album",
        "play-global",
    }
)


def emit(payload: dict[str, Any]) -> None:
    """Write exactly one machine-readable response."""

    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), flush=True)


def clean(value: Any) -> str:
    """Normalize optional Sonos metadata for JSON and QML."""

    text = str(value or "").strip()
    # Some radio/stream sources return this UPnP sentinel instead of metadata.
    # It is an implementation detail, not a track title or artist name.
    return "" if text == "NOT_IMPLEMENTED" else text


def validate_search_term(raw: Any, *, allow_empty: bool = True) -> str:
    value = clean(raw)
    if not value and not allow_empty:
        raise ValueError("Search text is required")
    if len(value) > 120 or any(ord(character) < 32 for character in value):
        raise ValueError("Search text is too long or contains control characters")
    return value


def validate_ip(raw: str) -> str:
    """Accept an ordinary unicast IPv4 address and reject special targets."""

    address = ipaddress.ip_address(raw)
    if (
        address.version != 4
        or not address.is_private
        or address.is_multicast
        or address.is_unspecified
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
    ):
        raise ValueError("Expected a unicast IPv4 address")
    return str(address)


def parse_bool(raw: str | bool) -> bool:
    if isinstance(raw, bool):
        return raw
    value = clean(raw).casefold()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError("Expected on or off")


def safe_call(callable_value: Any, fallback: Any) -> Any:
    try:
        return callable_value()
    except Exception:  # noqa: BLE001 - optional SoCo properties fail inconsistently
        return fallback


def optional_property(target: Any, name: str) -> Any:
    try:
        return getattr(target, name)
    except Exception:  # noqa: BLE001 - unsupported SoCo properties are optional
        return None


def cached_visible_zones(cache_path: Path = CACHE_PATH) -> set[Any]:
    """Use one known room to ask Sonos for the current household topology."""

    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        addresses = payload.get("addresses", []) if isinstance(payload, dict) else []
    except OSError, ValueError, TypeError:
        return set()

    for raw_address in addresses:
        try:
            speaker = SoCo(validate_ip(str(raw_address)))
            zones = set(speaker.visible_zones or set())
            if zones:
                return zones
        except Exception:  # noqa: BLE001, S112 - try the next cached speaker
            continue
    return set()


def save_cached_zones(
    speakers: Iterable[Any],
    cache_path: Path = CACHE_PATH,
) -> None:
    """Persist only discovered room addresses for fast future topology reads."""

    addresses = sorted(
        {
            clean(getattr(speaker, "ip_address", ""))
            for speaker in speakers
            if clean(getattr(speaker, "ip_address", ""))
        }
    )
    if not addresses:
        return

    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        cache_path.parent.chmod(0o700)
        if cache_path.is_symlink():
            return
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{cache_path.name}.",
            suffix=".tmp",
            dir=cache_path.parent,
            text=True,
        )
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(json.dumps({"addresses": addresses}, separators=(",", ":")))
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(cache_path)
        finally:
            temporary.unlink(missing_ok=True)
    except OSError:
        pass


def coordinator_for(speaker: Any) -> Any:
    """Return the transport coordinator, falling back to the speaker itself."""

    try:
        group = speaker.group
        coordinator = group.coordinator if group else None
        return coordinator or speaker
    except Exception:  # noqa: BLE001 - stale group state falls back safely
        return speaker


def group_members_for(speaker: Any) -> list[Any]:
    try:
        group = speaker.group
        members = list(group.members) if group and group.members else [speaker]
        return [
            member
            for member in members
            if bool(safe_call(lambda member=member: member.is_visible, True))
        ]
    except Exception:  # noqa: BLE001 - stale group state falls back safely
        return [speaker]


def safe_index(raw: Any, fallback: int = -1) -> int:
    try:
        return int(raw)
    except TypeError, ValueError:
        return fallback


def transport_snapshot(coordinator: Any) -> dict[str, Any]:
    """Read group-wide playback state and track metadata once."""

    transport = safe_call(coordinator.get_current_transport_info, {}) or {}
    track = safe_call(coordinator.get_current_track_info, {}) or {}
    state = clean(transport.get("current_transport_state")) or "UNKNOWN"
    coordinator_ip = clean(getattr(coordinator, "ip_address", ""))

    return {
        "state": state,
        "is_playing": state == "PLAYING",
        "title": clean(track.get("title")),
        "artist": clean(track.get("artist")),
        "album": clean(track.get("album")),
        "album_art": album_art_url(track.get("album_art"), coordinator_ip),
        "position": clean(track.get("position")),
        "duration": clean(track.get("duration")),
        "queue_position": max(-1, safe_index(track.get("playlist_position"), 0) - 1),
    }


def speaker_snapshot(
    speaker: Any,
    transport_cache: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    speaker_ip = clean(getattr(speaker, "ip_address", ""))
    name = clean(safe_call(lambda: speaker.player_name, ""))
    if not name:
        raise ConnectionError(f"Sonos room at {speaker_ip} is not responding")

    coordinator = coordinator_for(speaker)
    coordinator_ip = clean(getattr(coordinator, "ip_address", ""))
    cache_key = coordinator_ip or speaker_ip

    if cache_key not in transport_cache:
        transport_cache[cache_key] = transport_snapshot(coordinator)

    members = group_members_for(speaker)
    member_names = sorted(
        {clean(safe_call(lambda member=member: member.player_name, "")) for member in members}
        - {""}
    )
    if name and name not in member_names:
        member_names.append(name)
        member_names.sort()

    speaker_info = safe_call(speaker.get_speaker_info, {}) or {}
    uid = clean(safe_call(lambda: speaker.uid, "")) or speaker_ip

    snapshot = {
        "uid": uid,
        "name": name,
        "ip": speaker_ip,
        "model": clean(speaker_info.get("model_name")),
        "volume": int(safe_call(lambda: speaker.volume, 0)),
        "muted": bool(safe_call(lambda: speaker.mute, False)),
        "coordinator_ip": coordinator_ip,
        "is_coordinator": coordinator_ip == speaker_ip,
        "group_members": member_names,
        "group_label": " + ".join(member_names),
    }
    snapshot.update(transport_cache[cache_key])
    return snapshot


def snapshot_from_speakers(speakers: Iterable[Any]) -> list[dict[str, Any]]:
    transport_cache: dict[str, dict[str, Any]] = {}
    devices: list[dict[str, Any]] = []

    for speaker in sorted(
        speakers,
        key=lambda item: clean(
            safe_call(lambda item=item: item.player_name, item.ip_address)
        ).casefold(),
    ):
        try:
            devices.append(speaker_snapshot(speaker, transport_cache))
        except Exception:  # noqa: BLE001, S112 - skip one malformed room snapshot
            continue

    return devices


def discover_snapshot(timeout: float) -> dict[str, Any]:
    speakers = cached_visible_zones()
    if not speakers:
        speakers = (
            soco.discover(
                timeout=max(0.5, min(timeout, 8.0)),
                allow_network_scan=True,
                max_threads=128,
                scan_timeout=0.8,
                min_netmask=24,
            )
            or set()
        )
    save_cached_zones(speakers)
    return {"ok": True, "devices": snapshot_from_speakers(speakers)}


def tv_autoplay_enabled(speaker: Any) -> bool | None:
    """Return the home-theater autoplay state without exposing its room UUID."""

    if not bool(safe_call(lambda: speaker.is_soundbar, False)):
        return None
    response = safe_call(
        lambda: speaker.deviceProperties.GetAutoplayRoomUUID([("Source", "")]),
        None,
    )
    if not isinstance(response, dict) or "RoomUUID" not in response:
        return None
    return bool(clean(response.get("RoomUUID")))


def queue_transport_active(coordinator: Any) -> bool | None:
    """Return whether AVTransport is currently backed by the Sonos queue."""

    response = safe_call(
        lambda: coordinator.avTransport.GetMediaInfo([("InstanceID", 0)]),
        None,
    )
    if not isinstance(response, dict) or "CurrentURI" not in response:
        return None
    return clean(response.get("CurrentURI")).casefold().startswith("x-rincon-queue:")


def details_snapshot(ip: str) -> dict[str, Any]:
    return project_device_details(SoCo(validate_ip(ip)))


def item_attr(item: Any, name: str, fallback: Any = "") -> Any:
    return browse_item_attr(item, name, fallback)


def queue_content(coordinator: Any, limit: int) -> dict[str, Any]:
    return browse_queue_content(coordinator, limit)


def favorite_reference(item: Any) -> Any:
    return browse_favorite_reference(item)


def favorites_content(coordinator: Any, limit: int) -> dict[str, Any]:
    return browse_favorites_content(coordinator, limit)


def validate_identifier(raw: Any, label: str, maximum: int = 512) -> str:
    return browse_validate_identifier(raw, label, maximum)


def validate_playlist_id(raw: Any) -> str:
    return browse_validate_playlist_id(raw)


def didl_item_payload(
    item: Any,
    index: int,
    coordinator_ip: str,
) -> dict[str, Any]:
    return browse_didl_item_payload(item, index, coordinator_ip)


def library_content(coordinator: Any, term: str, limit: int) -> dict[str, Any]:
    return browse_library_content(coordinator, term, limit)


def playlists_content(coordinator: Any, limit: int) -> dict[str, Any]:
    return browse_playlists_content(coordinator, limit)


def playlist_content(coordinator: Any, playlist_id: str, limit: int) -> dict[str, Any]:
    return browse_playlist_content(coordinator, playlist_id, limit)


def apple_search_results(term: str, limit: int) -> list[dict[str, Any]]:
    return catalog_search_results(term, limit, request_get=requests.get, country=APPLE_COUNTRY)


def apple_content(term: str, limit: int) -> dict[str, Any]:
    return browse_apple_content(term, limit, request_get=requests.get, country=APPLE_COUNTRY)


def resolve_apple_artwork(title: str, artist: str) -> dict[str, Any]:
    return catalog_resolve_artwork(title, artist, request_get=requests.get, country=APPLE_COUNTRY)


def global_results(coordinator: Any, term: str, limit: int) -> Any:
    return browse_global_results(coordinator, term, limit, music_service_factory=MusicService)


def global_content(coordinator: Any, term: str, limit: int) -> dict[str, Any]:
    return browse_global_content(coordinator, term, limit)


def content_snapshot(ip: str, kind: str, term: str = "", limit: int = 30) -> dict[str, Any]:
    if kind not in CONTENT_KINDS:
        raise ValueError(f"Unsupported content kind: {kind}")
    limit = max(1, min(int(limit), 100))

    if kind == "apple":
        return browse_apple_content(term, limit, request_get=requests.get, country=APPLE_COUNTRY)

    speaker = SoCo(validate_ip(ip))
    coordinator = coordinator_for(speaker)
    if kind == "favorites":
        return favorites_content(coordinator, limit)
    return browse_content(coordinator, kind, term, limit)


def run_action(action: str, ip: str, value: int | None = None) -> dict[str, Any]:
    ip = validate_ip(ip)
    speaker = SoCo(ip)

    if action == "volume":
        if value is None:
            raise ValueError("Volume requires a value")
        volume = max(0, min(100, int(value)))
        speaker.volume = volume
        return {"ok": True, "action": action, "volume": volume, "message": f"Volume {volume}%"}

    if action == "mute-toggle":
        muted = not bool(speaker.mute)
        speaker.mute = muted
        return {
            "ok": True,
            "action": action,
            "muted": muted,
            "message": "Muted" if muted else "Unmuted",
        }

    if action not in PLAYBACK_ACTIONS:
        raise ValueError(f"Unsupported action: {action}")

    coordinator = coordinator_for(speaker)
    if action == "play-pause":
        transport = coordinator.get_current_transport_info() or {}
        state = clean(transport.get("current_transport_state"))
        action = "pause" if state == "PLAYING" else "play"

    getattr(coordinator, action.replace("-", "_"))()
    labels = {
        "play": "Playing",
        "pause": "Paused",
        "stop": "Stopped",
        "next": "Skipped forward",
        "previous": "Skipped back",
    }
    return {
        "ok": True,
        "action": action,
        "coordinator_ip": clean(getattr(coordinator, "ip_address", ip)),
        "message": labels.get(action, "Updated"),
    }


def rename_room(ip: str, name: str) -> dict[str, Any]:
    return rename_sonos_room(SoCo(validate_ip(ip)), name)


def group_room(ip: str, member_ip: str, grouped: bool) -> dict[str, Any]:
    speaker = SoCo(validate_ip(ip))
    member = SoCo(validate_ip(member_ip))
    if clean(speaker.ip_address) == clean(member.ip_address):
        raise ValueError("A room cannot be grouped with itself")

    coordinator = coordinator_for(speaker)
    same_group = clean(coordinator_for(member).ip_address) == clean(coordinator.ip_address)
    if grouped and not same_group:
        member.join(coordinator)
    elif not grouped and same_group:
        if clean(member.ip_address) == clean(coordinator.ip_address):
            speaker.unjoin()
        else:
            member.unjoin()

    return {
        "ok": True,
        "action": "group",
        "grouped": grouped,
        "message": "Room grouped" if grouped else "Room separated",
    }


def group_all(ip: str) -> dict[str, Any]:
    speaker = SoCo(validate_ip(ip))
    speaker.partymode()
    return {"ok": True, "action": "group-all", "message": "Playing everywhere"}


def separate_room(ip: str) -> dict[str, Any]:
    speaker = SoCo(validate_ip(ip))
    coordinator = coordinator_for(speaker)
    members = group_members_for(speaker)
    if len(members) > 1:
        if clean(speaker.ip_address) == clean(coordinator.ip_address):
            for member in members:
                if clean(member.ip_address) != clean(speaker.ip_address):
                    member.unjoin()
        else:
            speaker.unjoin()
    return {"ok": True, "action": "separate", "message": "Room separated"}


def playback_option(ip: str, option: str, value: str) -> dict[str, Any]:
    return set_sonos_playback_option(SoCo(validate_ip(ip)), option, value)


def set_sound(ip: str, setting: str, value: str) -> dict[str, Any]:
    return set_sonos_sound(SoCo(validate_ip(ip)), setting, value)


def find_favorite(coordinator: Any, item_id: str) -> Any:
    for item in coordinator.music_library.get_sonos_favorites(max_items=200):
        if clean(item_attr(item, "item_id")) == clean(item_id):
            return item
    raise ValueError("Sonos Favorite no longer exists")


def play_favorite(ip: str, item_id: str) -> dict[str, Any]:
    coordinator = coordinator_for(SoCo(validate_ip(ip)))
    favorite = find_favorite(coordinator, item_id)
    reference = favorite_reference(favorite)
    coordinator.play_uri(
        reference.resources[0].uri,
        meta=to_didl_string(reference),
    )
    return {"ok": True, "action": "play-favorite", "message": f"Playing {clean(favorite.title)}"}


def queue_action(
    ip: str,
    action: str,
    index: int | None = None,
    expected_item_id: str = "",
) -> dict[str, Any]:
    coordinator = coordinator_for(SoCo(validate_ip(ip)))
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


def find_library_item(coordinator: Any, item_id: str, term: str) -> Any:
    expected_id = validate_identifier(item_id, "library item identifier")
    query = validate_search_term(term, allow_empty=False)
    result = coordinator.music_library.get_music_library_information(
        "tracks",
        max_items=100,
        search_term=query,
    )
    for item in result:
        if clean(item_attr(item, "item_id")) == expected_id:
            return item
    raise ValueError("The library item is no longer available")


def find_playlist_track(
    coordinator: Any,
    playlist_id: str,
    index: int,
    item_id: str,
) -> tuple[Any, Any, int]:
    sonos_playlist = coordinator.get_sonos_playlist_by_attr(
        "item_id", validate_playlist_id(playlist_id)
    )
    result = coordinator.music_library.browse(ml_item=sonos_playlist, max_items=100)
    position = int(index)
    if position < 0 or position >= len(result):
        raise ValueError("The playlist changed; refresh it and try again")
    track = result[position]
    expected_id = validate_identifier(item_id, "playlist item identifier")
    if clean(item_attr(track, "item_id")) != expected_id:
        raise ValueError("The playlist changed; refresh it and try again")
    return sonos_playlist, track, len(result)


def enqueue_content_item(
    ip: str,
    kind: str,
    context: str,
    item_id: str,
    index: int,
    mode: str,
) -> dict[str, Any]:
    coordinator = coordinator_for(SoCo(validate_ip(ip)))
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
        queue_position = coordinator.add_to_queue(
            item,
            position=current_position + 1 if current_position else 1,
        )
        message = "Added next"
    else:
        queue_position = coordinator.add_to_queue(item)
        if mode == "play":
            coordinator.play_from_queue(max(0, int(queue_position) - 1))
            message = "Playing from the queue"
        else:
            message = "Added to the queue"
    return {"ok": True, "action": f"queue-{mode}", "message": message}


def validate_playlist_title(raw: Any) -> str:
    title = clean(raw)
    if not title:
        raise ValueError("Playlist name cannot be empty")
    if len(title) > 80 or any(ord(character) < 32 for character in title):
        raise ValueError("Playlist name is too long or contains control characters")
    return title


def playlist_action(
    ip: str,
    action: str,
    playlist_id: str = "",
    title: str = "",
) -> dict[str, Any]:
    coordinator = coordinator_for(SoCo(validate_ip(ip)))
    if action == "create":
        playlist = coordinator.create_sonos_playlist(validate_playlist_title(title))
        message = f"Created {clean(item_attr(playlist, 'title'))}"
    elif action == "save-queue":
        if not safe_index(optional_property(coordinator, "queue_size"), 0):
            raise ValueError("The current queue is empty")
        playlist = coordinator.create_sonos_playlist_from_queue(validate_playlist_title(title))
        message = f"Saved queue as {clean(item_attr(playlist, 'title'))}"
    elif action == "play":
        playlist = coordinator.get_sonos_playlist_by_attr(
            "item_id", validate_playlist_id(playlist_id)
        )
        position = coordinator.add_to_queue(playlist)
        coordinator.play_from_queue(max(0, int(position) - 1))
        message = f"Playing {clean(item_attr(playlist, 'title'))}"
    elif action == "delete":
        playlist = coordinator.get_sonos_playlist_by_attr(
            "item_id", validate_playlist_id(playlist_id)
        )
        playlist_title = clean(item_attr(playlist, "title")) or "Sonos playlist"
        coordinator.remove_sonos_playlist(playlist)
        message = f"Deleted {playlist_title}"
    else:
        raise ValueError("Unsupported playlist action")
    return {"ok": True, "action": f"playlist-{action}", "message": message}


def playlist_track_action(
    ip: str,
    action: str,
    playlist_id: str,
    index: int,
    item_id: str,
) -> dict[str, Any]:
    coordinator = coordinator_for(SoCo(validate_ip(ip)))
    playlist, _, count = find_playlist_track(coordinator, playlist_id, int(index), item_id)
    position = int(index)
    if action == "remove":
        coordinator.remove_from_sonos_playlist(playlist, position)
        message = "Removed from playlist"
    elif action == "up":
        if position <= 0:
            raise ValueError("This item is already first")
        coordinator.move_in_sonos_playlist(playlist, position, position - 1)
        message = "Moved up"
    elif action == "down":
        if position >= count - 1:
            raise ValueError("This item is already last")
        coordinator.move_in_sonos_playlist(playlist, position, position + 1)
        message = "Moved down"
    else:
        raise ValueError("Unsupported playlist track action")
    return {"ok": True, "action": f"playlist-track-{action}", "message": message}


def start_library_update(ip: str) -> dict[str, Any]:
    coordinator = coordinator_for(SoCo(validate_ip(ip)))
    if bool(safe_call(lambda: coordinator.music_library.library_updating, False)):
        return {
            "ok": True,
            "action": "library-update",
            "message": "Library update is already running",
        }
    coordinator.music_library.start_library_update()
    return {"ok": True, "action": "library-update", "message": "Library update started"}


def alarms_snapshot(ip: str) -> dict[str, Any]:
    return project_alarms(SoCo(validate_ip(ip)), alarm_loader=get_alarms)


def parse_alarm_time(raw: str) -> time:
    match = re.fullmatch(r"([01]\d|2[0-3]):([0-5]\d)", clean(raw))
    if not match:
        raise ValueError("Alarm time must be HH:MM")
    return time(hour=int(match.group(1)), minute=int(match.group(2)))


def alarm_by_id(speaker: Any, alarm_id: str) -> Any:
    expected = clean(alarm_id)
    if not ALARM_ID_PATTERN.fullmatch(expected):
        raise ValueError("Invalid alarm identifier")
    for alarm in get_alarms(speaker):
        if clean(alarm.alarm_id) == expected:
            return alarm
    raise ValueError("The alarm no longer exists")


def alarm_program(coordinator: Any, raw: str) -> tuple[str | None, str]:
    value = clean(raw)
    if value == "chime":
        return None, ""
    if not value.startswith("favorite:"):
        raise ValueError("Unsupported alarm sound")
    favorite = find_favorite(coordinator, value.removeprefix("favorite:"))
    reference = favorite_reference(favorite)
    return reference.resources[0].uri, to_didl_string(reference)


def save_alarm(
    ip: str,
    alarm_id: str,
    start: str,
    recurrence: str,
    volume: int,
    duration_minutes: int,
    enabled: bool,
    include_grouped: bool,
    program: str,
) -> dict[str, Any]:
    speaker = SoCo(validate_ip(ip))
    recurrence_value = clean(recurrence).upper()
    if recurrence_value not in ALARM_RECURRENCES:
        raise ValueError("Unsupported alarm recurrence")
    duration_value = int(duration_minutes)
    if duration_value not in ALARM_DURATIONS:
        raise ValueError("Unsupported alarm duration")
    if clean(alarm_id) == "new":
        alarm = Alarm(speaker)
        alarm.program_uri, alarm.program_metadata = alarm_program(coordinator_for(speaker), program)
    else:
        alarm = alarm_by_id(speaker, alarm_id)
        if clean(program) != "keep":
            alarm.program_uri, alarm.program_metadata = alarm_program(
                coordinator_for(speaker), program
            )
    alarm.start_time = parse_alarm_time(start)
    alarm.recurrence = recurrence_value
    alarm.volume = max(0, min(100, int(volume)))
    alarm.duration = (
        None
        if duration_value == 0
        else time(
            hour=duration_value // 60,
            minute=duration_value % 60,
        )
    )
    alarm.enabled = bool(enabled)
    alarm.include_linked_zones = bool(include_grouped)
    saved_id = alarm.save()
    return {
        "ok": True,
        "action": "alarm-save",
        "id": clean(saved_id),
        "message": "Alarm saved",
    }


def toggle_alarm(ip: str, alarm_id: str, enabled: bool) -> dict[str, Any]:
    speaker = SoCo(validate_ip(ip))
    alarm = alarm_by_id(speaker, alarm_id)
    alarm.enabled = bool(enabled)
    alarm.save()
    return {
        "ok": True,
        "action": "alarm-toggle",
        "message": "Alarm enabled" if enabled else "Alarm disabled",
    }


def delete_alarm(ip: str, alarm_id: str) -> dict[str, Any]:
    speaker = SoCo(validate_ip(ip))
    alarm = alarm_by_id(speaker, alarm_id)
    alarm.remove()
    return {"ok": True, "action": "alarm-delete", "message": "Alarm deleted"}


def switch_source(ip: str, source: str, source_ip: str = "") -> dict[str, Any]:
    speaker = SoCo(validate_ip(ip))
    source_speaker = None
    if source_ip:
        expected_ip = validate_ip(source_ip)
        visible = list(safe_call(lambda: speaker.visible_zones, set()) or set())
        if all(
            clean(getattr(zone, "ip_address", "")) != clean(speaker.ip_address) for zone in visible
        ):
            visible.append(speaker)
        source_speaker = next(
            (zone for zone in visible if clean(getattr(zone, "ip_address", "")) == expected_ip),
            None,
        )
        if source_speaker is None:
            raise ValueError("Line-in source is not part of this Sonos household")
    return switch_sonos_source(speaker, source, source_speaker)


def set_device(ip: str, setting: str, value: str) -> dict[str, Any]:
    return set_sonos_device(SoCo(validate_ip(ip)), setting, value)


def validate_apple_url(url: str) -> str:
    validated = public_apple_music_url(url)
    if not validated:
        raise ValueError("Expected an Apple Music link")
    return validated


def validate_apple_album_url(url: str) -> str:
    validated = public_apple_album_url(url)
    if not validated:
        raise ValueError("Expected an Apple Music album link")
    return validated


def play_apple(ip: str, url: str) -> dict[str, Any]:
    coordinator = coordinator_for(SoCo(validate_ip(ip)))
    plugin = ShareLinkPlugin(coordinator)
    queue_position = plugin.add_share_link_to_queue(validate_apple_url(url))
    coordinator.play_from_queue(max(0, int(queue_position) - 1))
    return {"ok": True, "action": "play-apple", "message": "Playing from Apple Music"}


def play_apple_album(ip: str, url: str) -> dict[str, Any]:
    album_url = validate_apple_album_url(url)
    coordinator = coordinator_for(SoCo(validate_ip(ip)))
    if (
        clean(optional_property(coordinator, "music_source")).upper() == "TV"
        and tv_autoplay_enabled(coordinator) is True
    ):
        raise ValueError(
            "TV Autoplay is on while TV audio is active. Select the home-theater room, "
            "turn off TV Autoplay in System, then play the album again."
        )
    plugin = ShareLinkPlugin(coordinator)
    queue_position = plugin.add_share_link_to_queue(album_url)
    coordinator.play_from_queue(max(0, int(queue_position) - 1))
    return {
        "ok": True,
        "action": "play-apple-album",
        "message": "Playing Apple Music album",
    }


def play_global(ip: str, item_id: str, term: str) -> dict[str, Any]:
    coordinator = coordinator_for(SoCo(validate_ip(ip)))
    expected_item_id = validate_identifier(item_id, "Global Player item identifier")
    for item in global_results(coordinator, term, 50):
        if clean(item_attr(item, "item_id")) != expected_item_id:
            continue
        resources = item_attr(item, "resources", [])
        if not item_attr(item, "can_play", False) or not resources:
            raise ValueError("This Global Player result is not directly playable")
        coordinator.play_uri(resources[0].uri, meta=to_didl_string(item))
        return {"ok": True, "action": "play-global", "message": f"Playing {clean(item.title)}"}
    raise ValueError("Global Player result no longer exists")


def parser() -> argparse.ArgumentParser:
    command_parser = argparse.ArgumentParser(description="Quickshell Sonos JSON bridge")
    subparsers = command_parser.add_subparsers(dest="command", required=True)

    status = subparsers.add_parser("status", help="Discover rooms and return their state")
    status.add_argument("--timeout", type=float, default=2.0)

    artwork = subparsers.add_parser("artwork")
    artwork.add_argument("title")
    artwork.add_argument("artist")

    details = subparsers.add_parser("details")
    details.add_argument("ip")

    content = subparsers.add_parser("content")
    content.add_argument("ip")
    content.add_argument("kind", choices=sorted(CONTENT_KINDS))
    content.add_argument("term", nargs="?", default="")
    content.add_argument("--limit", type=int, default=30)

    alarms = subparsers.add_parser("alarms")
    alarms.add_argument("ip")

    for action in sorted(PLAYBACK_ACTIONS | {"mute-toggle"}):
        action_parser = subparsers.add_parser(action)
        action_parser.add_argument("ip")

    volume = subparsers.add_parser("volume")
    volume.add_argument("ip")
    volume.add_argument("value", type=int)

    rename = subparsers.add_parser("rename")
    rename.add_argument("ip")
    rename.add_argument("name")

    group = subparsers.add_parser("group")
    group.add_argument("ip")
    group.add_argument("member_ip")
    group.add_argument("state", choices=("on", "off"))

    for command in ("group-all", "separate"):
        action_parser = subparsers.add_parser(command)
        action_parser.add_argument("ip")

    playback = subparsers.add_parser("playback-option")
    playback.add_argument("ip")
    playback.add_argument("option", choices=("shuffle", "repeat", "crossfade", "sleep"))
    playback.add_argument("value")

    sound = subparsers.add_parser("sound")
    sound.add_argument("ip")
    sound.add_argument(
        "setting",
        choices=sorted(set(NUMBER_SETTINGS) | set(BOOLEAN_SETTINGS) | {"speech-enhancement"}),
    )
    sound.add_argument("value")

    favorite = subparsers.add_parser("play-favorite")
    favorite.add_argument("ip")
    favorite.add_argument("item_id")

    for command in ("play-queue", "remove-queue"):
        queue = subparsers.add_parser(command)
        queue.add_argument("ip")
        queue.add_argument("index", type=int)
        queue.add_argument("item_id")

    clear_queue = subparsers.add_parser("clear-queue")
    clear_queue.add_argument("ip")

    queue_content = subparsers.add_parser("queue-content")
    queue_content.add_argument("ip")
    queue_content.add_argument("kind", choices=("library", "playlist"))
    queue_content.add_argument("context")
    queue_content.add_argument("item_id")
    queue_content.add_argument("index", type=int)
    queue_content.add_argument("mode", choices=("play", "next", "end"))

    playlist = subparsers.add_parser("playlist")
    playlist.add_argument("ip")
    playlist.add_argument("action", choices=("create", "save-queue", "play", "delete"))
    playlist.add_argument("value", nargs="?", default="")

    playlist_track = subparsers.add_parser("playlist-track")
    playlist_track.add_argument("ip")
    playlist_track.add_argument("action", choices=("up", "down", "remove"))
    playlist_track.add_argument("playlist_id")
    playlist_track.add_argument("index", type=int)
    playlist_track.add_argument("item_id")

    library_update = subparsers.add_parser("library-update")
    library_update.add_argument("ip")

    alarm_save = subparsers.add_parser("alarm-save")
    alarm_save.add_argument("ip")
    alarm_save.add_argument("alarm_id")
    alarm_save.add_argument("time")
    alarm_save.add_argument("recurrence", choices=sorted(ALARM_RECURRENCES))
    alarm_save.add_argument("volume", type=int)
    alarm_save.add_argument("duration", type=int, choices=sorted(ALARM_DURATIONS))
    alarm_save.add_argument("enabled", choices=("on", "off"))
    alarm_save.add_argument("include_grouped", choices=("on", "off"))
    alarm_save.add_argument("program")

    alarm_toggle = subparsers.add_parser("alarm-toggle")
    alarm_toggle.add_argument("ip")
    alarm_toggle.add_argument("alarm_id")
    alarm_toggle.add_argument("enabled", choices=("on", "off"))

    alarm_delete = subparsers.add_parser("alarm-delete")
    alarm_delete.add_argument("ip")
    alarm_delete.add_argument("alarm_id")

    source = subparsers.add_parser("source")
    source.add_argument("ip")
    source.add_argument("source", choices=("line-in", "tv"))
    source.add_argument("source_ip", nargs="?", default="")

    device = subparsers.add_parser("device")
    device.add_argument("ip")
    device.add_argument("setting", choices=sorted(DEVICE_SETTINGS))
    device.add_argument("value", choices=("on", "off"))

    apple = subparsers.add_parser("play-apple")
    apple.add_argument("ip")
    apple.add_argument("url")

    apple_album = subparsers.add_parser("play-apple-album")
    apple_album.add_argument("ip")
    apple_album.add_argument("url")

    global_player = subparsers.add_parser("play-global")
    global_player.add_argument("ip")
    global_player.add_argument("item_id")
    global_player.add_argument("term")

    if subparsers.choices.keys() != CLI_COMMANDS:
        raise RuntimeError("CLI command inventory is out of sync")
    return command_parser


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "status":
            payload = discover_snapshot(args.timeout)
        elif args.command == "artwork":
            payload = resolve_apple_artwork(args.title, args.artist)
        elif args.command == "details":
            payload = details_snapshot(args.ip)
        elif args.command == "content":
            payload = content_snapshot(args.ip, args.kind, args.term, args.limit)
        elif args.command == "alarms":
            payload = alarms_snapshot(args.ip)
        elif args.command == "volume":
            payload = run_action(args.command, args.ip, args.value)
        elif args.command in PLAYBACK_ACTIONS | {"mute-toggle"}:
            payload = run_action(args.command, args.ip)
        elif args.command == "rename":
            payload = rename_room(args.ip, args.name)
        elif args.command == "group":
            payload = group_room(args.ip, args.member_ip, args.state == "on")
        elif args.command == "group-all":
            payload = group_all(args.ip)
        elif args.command == "separate":
            payload = separate_room(args.ip)
        elif args.command == "playback-option":
            payload = playback_option(args.ip, args.option, args.value)
        elif args.command == "sound":
            payload = set_sound(args.ip, args.setting, args.value)
        elif args.command == "play-favorite":
            payload = play_favorite(args.ip, args.item_id)
        elif args.command in {"play-queue", "remove-queue"}:
            payload = queue_action(args.ip, args.command, args.index, args.item_id)
        elif args.command == "clear-queue":
            payload = queue_action(args.ip, args.command)
        elif args.command == "queue-content":
            payload = enqueue_content_item(
                args.ip,
                args.kind,
                args.context,
                args.item_id,
                args.index,
                args.mode,
            )
        elif args.command == "playlist":
            payload = playlist_action(
                args.ip,
                args.action,
                playlist_id=args.value if args.action in {"play", "delete"} else "",
                title=args.value if args.action in {"create", "save-queue"} else "",
            )
        elif args.command == "playlist-track":
            payload = playlist_track_action(
                args.ip,
                args.action,
                args.playlist_id,
                args.index,
                args.item_id,
            )
        elif args.command == "library-update":
            payload = start_library_update(args.ip)
        elif args.command == "alarm-save":
            payload = save_alarm(
                args.ip,
                args.alarm_id,
                args.time,
                args.recurrence,
                args.volume,
                args.duration,
                args.enabled == "on",
                args.include_grouped == "on",
                args.program,
            )
        elif args.command == "alarm-toggle":
            payload = toggle_alarm(args.ip, args.alarm_id, args.enabled == "on")
        elif args.command == "alarm-delete":
            payload = delete_alarm(args.ip, args.alarm_id)
        elif args.command == "source":
            payload = switch_source(args.ip, args.source, args.source_ip)
        elif args.command == "device":
            payload = set_device(args.ip, args.setting, args.value)
        elif args.command == "play-apple":
            payload = play_apple(args.ip, args.url)
        elif args.command == "play-apple-album":
            payload = play_apple_album(args.ip, args.url)
        elif args.command == "play-global":
            payload = play_global(args.ip, args.item_id, args.term)
        else:
            raise ValueError(f"Unsupported command: {args.command}")
        emit(payload)
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI returns one bounded JSON error
        emit({"ok": False, "error": user_facing_error(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
