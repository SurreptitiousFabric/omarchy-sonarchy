from __future__ import annotations

from typing import Any

import requests

from .common import clean, safe_call

LINE_IN_QUERY_TIMEOUT_SEC = 1.5


def tv_autoplay_enabled(speaker: Any) -> bool | None:
    """Project TV Autoplay support and state without guessing from a model name."""
    response = safe_call(
        lambda: speaker.deviceProperties.GetAutoplayRoomUUID([("Source", "")]), None
    )
    if not isinstance(response, dict) or "RoomUUID" not in response:
        return None
    return bool(clean(response.get("RoomUUID")))


def queue_transport_active(speaker: Any) -> bool | None:
    """Return whether the authoritative transport URI is the Sonos queue."""
    response = safe_call(lambda: speaker.avTransport.GetMediaInfo([("InstanceID", 0)]), None)
    if not isinstance(response, dict) or "CurrentURI" not in response:
        return None
    return clean(response.get("CurrentURI")).casefold().startswith("x-rincon-queue:")


def line_in_available(speaker: Any) -> bool:
    """Return only positively confirmed AudioIn support.

    Building the SOAP request directly avoids SoCo's dynamic action lookup,
    whose service-description fetch has a separate, longer timeout. It also
    avoids logging expected unsupported-device responses as backend errors.
    """
    try:
        service = speaker.audioIn
        headers, body = service.build_command("GetAudioInputAttributes", [])
        response = requests.post(
            service.base_url + service.control_url,
            headers=headers,
            data=body.encode("utf-8"),
            timeout=LINE_IN_QUERY_TIMEOUT_SEC,
            allow_redirects=False,
        )
        try:
            return response.status_code == 200
        finally:
            response.close()
    except AttributeError:
        # Narrow test/adaptor ports may expose only the action method.
        try:
            response = speaker.audioIn.send_command(
                "GetAudioInputAttributes", [], timeout=LINE_IN_QUERY_TIMEOUT_SEC
            )
        except Exception:  # noqa: BLE001 - unsupported and unreachable both fail closed
            return False
        return isinstance(response, dict)
    except Exception:  # noqa: BLE001 - unsupported and unreachable both fail closed
        return False
