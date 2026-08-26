from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PROTOCOL_VERSION = 1

CAPABILITY_NAMES = frozenset(
    {
        "artwork.radio.resolve",
        "content.favorite.play",
        "content.favorites.refresh",
        "devices.details.get",
        "mute.group.set",
        "mute.room.set",
        "playback.next",
        "playback.pause",
        "playback.play",
        "playback.previous",
        "playback.room.move",
        "playback.seek",
        "playback.toggle",
        "selection.group.set",
        "selection.room.set",
        "topology.members.set",
        "volume.group.adjust",
        "volume.group.set",
        "volume.room.adjust",
        "volume.room.set",
    }
)

OPERATION_ALIASES = {
    "setPanelOpen": "session.panel_open.set",
    "refresh": "state.refresh",
    "playPause": "playback.toggle",
    "play": "playback.play",
    "pause": "playback.pause",
    "next": "playback.next",
    "previous": "playback.previous",
    "seek": "playback.seek",
    "playFavorite": "content.favorite.play",
    "refreshFavorites": "content.favorites.refresh",
    "movePlaybackToRoom": "playback.room.move",
    "selectGroup": "selection.group.set",
    "selectRoom": "selection.room.set",
    "setGroupVolume": "volume.group.set",
    "adjustGroupVolume": "volume.group.adjust",
    "setGroupMute": "mute.group.set",
    "setRoomVolume": "volume.room.set",
    "adjustRoomVolume": "volume.room.adjust",
    "setRoomMute": "mute.room.set",
    "applyMembers": "topology.members.set",
}


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


def parse_request(payload: dict[str, Any]) -> ProtocolRequest:
    request_id = str(payload.get("id", "") or "")
    raw_operation = payload.get("op", "")
    operation = str(raw_operation or "")

    version = payload.get("version", PROTOCOL_VERSION)
    if type(version) is not int or version != PROTOCOL_VERSION:
        raise ProtocolRequestError(
            "unsupported_version",
            f"Protocol version {version!r} is not supported",
            request_id=request_id,
            operation=operation,
        )
    if not request_id:
        raise ProtocolRequestError(
            "invalid_request", "Request id must be a non-empty string", operation=operation
        )
    if not operation:
        raise ProtocolRequestError(
            "invalid_request", "Operation must be a non-empty string", request_id=request_id
        )

    if "args" in payload:
        raw_args = payload["args"]
        if not isinstance(raw_args, dict):
            raise ProtocolRequestError(
                "invalid_request",
                "Request args must be an object",
                request_id=request_id,
                operation=operation,
            )
        args = dict(raw_args)
    else:
        # Compatibility for the original QML and bridge request shape.
        args = {key: value for key, value in payload.items() if key not in {"version", "id", "op"}}

    return ProtocolRequest(
        request_id=request_id,
        operation=OPERATION_ALIASES.get(operation, operation),
        args=args,
    )


def error_payload(
    code: str,
    message: str,
    *,
    operation: str = "",
    retryable: bool = False,
) -> dict[str, Any]:
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "retryable": retryable,
    }
    if operation:
        error["operation"] = operation
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

    capabilities = {"artwork.radio.resolve", "content.favorites.refresh"}
    if rooms:
        capabilities.update(
            {
                "devices.details.get",
                "mute.room.set",
                "selection.room.set",
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
