from __future__ import annotations

from collections.abc import Callable
from typing import Any

from soco.alarms import get_alarms

from .common import DomainService, string_arg
from .ports import AlarmsPort


def _clean(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text == "NOT_IMPLEMENTED" else text


def _safe(call: Callable[[], Any], fallback: Any) -> Any:
    try:
        return call()
    except Exception:  # noqa: BLE001 - stale optional alarm metadata is non-fatal
        return fallback


def project_alarms(
    speaker: Any, *, alarm_loader: Callable[[Any], Any] = get_alarms
) -> dict[str, Any]:
    alarms = list(alarm_loader(speaker))
    items = []
    for alarm in sorted(alarms, key=lambda value: (value.start_time, _clean(value.alarm_id))):
        program_uri = _clean(alarm.program_uri)
        items.append(
            {
                "id": _clean(alarm.alarm_id),
                "time": alarm.start_time.strftime("%H:%M"),
                "duration": 0
                if alarm.duration is None
                else alarm.duration.hour * 60 + alarm.duration.minute,
                "recurrence": _clean(alarm.recurrence),
                "enabled": bool(alarm.enabled),
                "volume": int(alarm.volume),
                "include_grouped": bool(alarm.include_linked_zones),
                "room_uid": _clean(alarm.room_uuid),
                "room": _clean(_safe(lambda alarm=alarm: alarm.zone.player_name, "Unknown room")),
                "program": "Chime"
                if program_uri in {"", "x-rincon-buzzer:0"}
                else "Saved Sonos content",
            }
        )
    return {"ok": True, "kind": "alarms", "items": items, "total": len(items)}


def alarms_service(backend: AlarmsPort) -> DomainService:
    return DomainService(
        {"alarms.list": lambda args: backend.list_alarms(string_arg(args, "roomUid"))},
        mutates=False,
    )
