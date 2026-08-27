from __future__ import annotations

import re
from collections.abc import Callable
from datetime import time
from typing import Any

from soco.alarms import Alarm, get_alarms
from soco.data_structures import to_didl_string

from .common import (
    DomainService,
    bool_arg,
    clean,
    coordinator_for,
    number_arg,
    safe_call,
    string_arg,
)
from .media import favorite_reference, item_attr
from .ports import AlarmsPort


def project_alarms(
    speaker: Any, *, alarm_loader: Callable[[Any], Any] = get_alarms
) -> dict[str, Any]:
    alarms = list(alarm_loader(speaker))
    items = []
    for alarm in sorted(alarms, key=lambda value: (value.start_time, clean(value.alarm_id))):
        program_uri = clean(alarm.program_uri)
        items.append(
            {
                "id": clean(alarm.alarm_id),
                "time": alarm.start_time.strftime("%H:%M"),
                "duration": 0
                if alarm.duration is None
                else alarm.duration.hour * 60 + alarm.duration.minute,
                "recurrence": clean(alarm.recurrence),
                "enabled": bool(alarm.enabled),
                "volume": int(alarm.volume),
                "include_grouped": bool(alarm.include_linked_zones),
                "room_uid": clean(alarm.room_uuid),
                "room": clean(
                    safe_call(lambda alarm=alarm: alarm.zone.player_name, "Unknown room")
                ),
                "program": "Chime"
                if program_uri in {"", "x-rincon-buzzer:0"}
                else "Saved Sonos content",
            }
        )
    return {"ok": True, "kind": "alarms", "items": items, "total": len(items)}


def parse_alarm_time(raw: str) -> time:
    match = re.fullmatch(r"([01]\d|2[0-3]):([0-5]\d)", clean(raw))
    if not match:
        raise ValueError("Alarm time must be HH:MM")
    return time(hour=int(match.group(1)), minute=int(match.group(2)))


def alarm_by_id(
    speaker: Any, alarm_id: str, *, alarm_loader: Callable[[Any], Any] = get_alarms
) -> Any:
    expected = clean(alarm_id)
    if not re.fullmatch(r"\d+", expected):
        raise ValueError("Invalid alarm identifier")
    for alarm in alarm_loader(speaker):
        if clean(alarm.alarm_id) == expected:
            return alarm
    raise ValueError("The alarm no longer exists")


def alarm_program(
    coordinator: Any,
    raw: str,
    *,
    metadata_fn: Callable[[Any], str] = to_didl_string,
) -> tuple[str | None, str]:
    value = clean(raw)
    if value == "chime":
        return None, ""
    if not value.startswith("favorite:"):
        raise ValueError("Unsupported alarm sound")
    expected = value.removeprefix("favorite:")
    favorite = next(
        (
            item
            for item in coordinator.music_library.get_sonos_favorites(max_items=200)
            if clean(item_attr(item, "item_id")) == expected
        ),
        None,
    )
    if favorite is None:
        raise ValueError("Sonos Favorite no longer exists")
    reference = favorite_reference(favorite)
    return reference.resources[0].uri, metadata_fn(reference)


def save_alarm(
    speaker: Any,
    alarm_id: str,
    start: str,
    recurrence: str,
    volume: int,
    duration_minutes: int,
    enabled: bool,
    include_grouped: bool,
    program: str,
    *,
    alarm_factory: Callable[[Any], Any] = Alarm,
    alarm_loader: Callable[[Any], Any] = get_alarms,
    metadata_fn: Callable[[Any], str] = to_didl_string,
) -> dict[str, Any]:
    recurrence_value = clean(recurrence).upper()
    if recurrence_value not in {"ONCE", "DAILY", "WEEKDAYS", "WEEKENDS"}:
        raise ValueError("Unsupported alarm recurrence")
    duration_value = int(duration_minutes)
    if duration_value not in {0, 15, 30, 45, 60, 90, 120}:
        raise ValueError("Unsupported alarm duration")
    if clean(alarm_id) == "new":
        alarm = alarm_factory(speaker)
        alarm.program_uri, alarm.program_metadata = alarm_program(
            coordinator_for(speaker), program, metadata_fn=metadata_fn
        )
    else:
        alarm = alarm_by_id(speaker, alarm_id, alarm_loader=alarm_loader)
        if clean(program) != "keep":
            alarm.program_uri, alarm.program_metadata = alarm_program(
                coordinator_for(speaker), program, metadata_fn=metadata_fn
            )
    alarm.start_time = parse_alarm_time(start)
    alarm.recurrence = recurrence_value
    alarm.volume = max(0, min(100, int(volume)))
    alarm.duration = (
        None if duration_value == 0 else time(hour=duration_value // 60, minute=duration_value % 60)
    )
    alarm.enabled = bool(enabled)
    alarm.include_linked_zones = bool(include_grouped)
    saved_id = alarm.save()
    return {"ok": True, "action": "alarm-save", "id": clean(saved_id), "message": "Alarm saved"}


def toggle_alarm(
    speaker: Any,
    alarm_id: str,
    enabled: bool,
    *,
    alarm_loader: Callable[[Any], Any] = get_alarms,
) -> dict[str, Any]:
    alarm = alarm_by_id(speaker, alarm_id, alarm_loader=alarm_loader)
    alarm.enabled = bool(enabled)
    alarm.save()
    return {
        "ok": True,
        "action": "alarm-toggle",
        "message": "Alarm enabled" if enabled else "Alarm disabled",
    }


def delete_alarm(
    speaker: Any, alarm_id: str, *, alarm_loader: Callable[[Any], Any] = get_alarms
) -> dict[str, Any]:
    alarm = alarm_by_id(speaker, alarm_id, alarm_loader=alarm_loader)
    alarm.remove()
    return {"ok": True, "action": "alarm-delete", "message": "Alarm deleted"}


def alarms_service(backend: AlarmsPort) -> DomainService:
    return DomainService(
        {"alarms.list": lambda args: backend.list_alarms(string_arg(args, "roomUid"))},
        mutates=False,
    )


def alarm_mutations_service(backend: AlarmsPort) -> DomainService:
    def integer_arg(args: dict[str, Any], name: str) -> int:
        value = number_arg(args, name)
        if int(value) != value:
            raise ValueError(f"{name} must be an integer")
        return int(value)

    return DomainService(
        {
            "alarms.save": lambda args: backend.save_alarm(
                string_arg(args, "roomUid"),
                string_arg(args, "alarmId"),
                string_arg(args, "time"),
                string_arg(args, "recurrence"),
                integer_arg(args, "volume"),
                integer_arg(args, "duration"),
                bool_arg(args, "enabled"),
                bool_arg(args, "includeGrouped"),
                string_arg(args, "program"),
            ),
            "alarms.toggle": lambda args: backend.toggle_alarm(
                string_arg(args, "roomUid"),
                string_arg(args, "alarmId"),
                bool_arg(args, "enabled"),
            ),
            "alarms.delete": lambda args: backend.delete_alarm(
                string_arg(args, "roomUid"), string_arg(args, "alarmId")
            ),
        }
    )
