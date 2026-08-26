"""Turn low-level SoCo/UPnP failures into short recovery instructions."""

from __future__ import annotations

import re
from typing import Any

_UPNP_CODE = re.compile(r"(?:UPnP Error|error(?:_code)?[=: ]+)\s*['\"]?(\d{3})", re.I)
_TRAILING_HOST = re.compile(r"\s+from\s+(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\s*$", re.I)

_UPNP_HELP = {
    "701": (
        "That action is not available while the speaker is in its current "
        "playback state. Wait a moment, then try again."
    ),
    "702": "There is nothing available to play. Choose a track or favourite first.",
    "704": "The speaker cannot play this audio format. Choose another item.",
    "705": "The Sonos transport is locked. Wait a moment, then try again.",
    "710": "This source does not support seeking.",
    "711": "That seek position is not available for this track or station.",
    "712": "This source does not support that play mode.",
    "714": "The speaker cannot play this item because its media type is unsupported.",
    "715": "The selected content is busy. Wait a moment, then try again.",
    "716": "That item is no longer available. Refresh the list and choose it again.",
    "801": "An alarm already exists for that room and time. Change or remove it first.",
}


def upnp_error_code(error: Any) -> str:
    """Return a three-digit UPnP code without depending on a SoCo class."""

    attribute = str(getattr(error, "error_code", "") or "")
    if re.fullmatch(r"\d{3}", attribute):
        return attribute
    match = _UPNP_CODE.search(str(error or ""))
    return match.group(1) if match else ""


def user_facing_error(error: Any, fallback: str = "Sonos could not complete that action") -> str:
    """Return actionable text while leaving raw details available to logs."""

    code = upnp_error_code(error)
    if code in _UPNP_HELP:
        return f"{_UPNP_HELP[code]} (Sonos error {code})"

    text = str(error or "").replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    text = _TRAILING_HOST.sub("", text)
    if not text:
        text = fallback
    if len(text) > 180:
        text = text[:177].rstrip() + "…"
    return text
