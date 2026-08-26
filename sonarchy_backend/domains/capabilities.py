from __future__ import annotations

from typing import Any

LINE_IN_QUERY_TIMEOUT_SEC = 1.5


def line_in_available(speaker: Any) -> bool:
    """Return only positively confirmed AudioIn support.

    Calling ``send_command`` directly avoids SoCo's dynamic action lookup,
    whose service-description fetch has a separate, longer timeout.
    """
    try:
        response = speaker.audioIn.send_command(
            "GetAudioInputAttributes", [], timeout=LINE_IN_QUERY_TIMEOUT_SEC
        )
    except Exception:  # noqa: BLE001 - unsupported and unreachable both fail closed
        return False
    return isinstance(response, dict)
