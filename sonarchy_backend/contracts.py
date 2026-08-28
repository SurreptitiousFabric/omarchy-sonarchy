from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

PROTOCOL_VERSION = 1
MAX_PROTOCOL_LINE_BYTES = 64 * 1024
MAX_PROTOCOL_REQUEST_ID_BYTES = 256
MAX_PROTOCOL_OPERATION_BYTES = 128

CAPABILITY_NAMES = frozenset(
    {
        "alarms.list",
        "alarms.delete",
        "alarms.save",
        "alarms.toggle",
        "artwork.radio.resolve",
        "content.apple.album.play",
        "content.apple.play",
        "content.browse",
        "content.favorite.play",
        "content.favorites.refresh",
        "content.global.play",
        "devices.details.get",
        "devices.rename",
        "devices.setting.set",
        "library.update.start",
        "mute.group.set",
        "mute.room.set",
        "playback.next",
        "playback.option.set",
        "playback.pause",
        "playback.play",
        "playback.previous",
        "playback.room.move",
        "playback.seek",
        "playback.stop",
        "playback.toggle",
        "playlists.mutate",
        "playlist_plan.apple.validate",
        "playlists.apple.create",
        "playlists.track.mutate",
        "queue.clear",
        "queue.content.enqueue",
        "queue.item.play",
        "queue.item.move",
        "queue.item.remove",
        "selection.group.set",
        "selection.room.set",
        "sound.setting.set",
        "sources.switch",
        "topology.members.set",
        "volume.group.adjust",
        "volume.group.set",
        "volume.room.adjust",
        "volume.room.set",
    }
)


@dataclass(frozen=True)
class ProtocolRequest:
    request_id: str
    operation: str
    args: dict[str, Any]


class ProtocolRequestError(ValueError):
    def __init__(self, code: str, message: str, *, request_id: str = "", operation: str = ""):
        super().__init__(message)
        self.code = code
        self.request_id = request_id
        self.operation = operation


def protocol_line(payload: dict[str, Any]) -> str:
    """Serialize one bounded UTF-8 JSON-line protocol message."""

    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"


def _bounded_protocol_label(raw: Any, maximum: int) -> str:
    value = str(raw or "")
    if (
        not value
        or len(value.encode("utf-8")) > maximum
        or any(ord(character) < 32 for character in value)
    ):
        return ""
    return value


def parse_request(payload: dict[str, Any]) -> ProtocolRequest:
    request_id = _bounded_protocol_label(
        payload.get("id", ""),
        MAX_PROTOCOL_REQUEST_ID_BYTES,
    )
    raw_operation = payload.get("op", "")
    operation = _bounded_protocol_label(raw_operation, MAX_PROTOCOL_OPERATION_BYTES)

    version = payload.get("version")
    if type(version) is not int or version != PROTOCOL_VERSION:
        raise ProtocolRequestError(
            "unsupported_version",
            f"Protocol version {version!r} is not supported",
            request_id=request_id,
            operation=operation,
        )
    if not request_id:
        raise ProtocolRequestError(
            "invalid_request",
            "Request id must be a non-empty bounded string",
            operation=operation,
        )
    if not operation:
        raise ProtocolRequestError(
            "invalid_request",
            "Operation must be a non-empty bounded string",
            request_id=request_id,
        )

    raw_args = payload.get("args")
    if not isinstance(raw_args, dict):
        raise ProtocolRequestError(
            "invalid_request",
            "Request args must be an object",
            request_id=request_id,
            operation=operation,
        )

    return ProtocolRequest(
        request_id=request_id,
        operation=operation,
        args=dict(raw_args),
    )


def error_payload(
    code: str,
    message: str,
    *,
    operation: str = "",
    retryable: bool = False,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "retryable": retryable,
    }
    if operation:
        error["operation"] = operation
    if details:
        error["details"] = details
    return error


def result_payload(
    request_id: str,
    *,
    revision: int,
    error: dict[str, Any] | None = None,
    value: Any = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": "result",
        "version": PROTOCOL_VERSION,
        "id": request_id,
        "ok": error is None,
        "revision": revision,
    }
    if error is None:
        payload["value"] = value
    else:
        payload["error"] = error
    return payload


def snapshot_capabilities(snapshot: dict[str, Any]) -> list[str]:
    households = snapshot.get("households") or []
    rooms = [room for household in households for room in household.get("rooms", [])]
    groups = [group for household in households for group in household.get("groups", [])]
    target = snapshot.get("target")
    playback = snapshot.get("playback") or {}
    advertised = {str(action).lower() for action in playback.get("availableActions", [])}

    capabilities = {
        "artwork.radio.resolve",
        "content.browse",
        "content.favorites.refresh",
    }
    if rooms:
        capabilities.update(
            {
                "alarms.list",
                "alarms.save",
                "alarms.toggle",
                "alarms.delete",
                "devices.details.get",
                "devices.rename",
                "devices.setting.set",
                "mute.room.set",
                "playback.option.set",
                "playback.stop",
                "selection.room.set",
                "sound.setting.set",
                "sources.switch",
                "queue.item.play",
                "queue.item.move",
                "queue.item.remove",
                "queue.clear",
                "queue.content.enqueue",
                "playlists.mutate",
                "playlist_plan.apple.validate",
                "playlists.apple.create",
                "playlists.track.mutate",
                "content.apple.play",
                "content.apple.album.play",
                "content.global.play",
                "library.update.start",
                "volume.room.adjust",
                "volume.room.set",
            }
        )
    if len(rooms) > 1:
        capabilities.update({"playback.room.move", "topology.members.set"})
    if groups:
        capabilities.add("selection.group.set")
    if target:
        capabilities.update(
            {
                "content.favorite.play",
                "mute.group.set",
                "playback.pause",
                "playback.play",
                "playback.toggle",
                "volume.group.adjust",
                "volume.group.set",
            }
        )
    if "next" in advertised:
        capabilities.add("playback.next")
    if "previous" in advertised:
        capabilities.add("playback.previous")
    if advertised.intersection({"seek", "seektime"}):
        capabilities.add("playback.seek")

    return sorted(capabilities)
