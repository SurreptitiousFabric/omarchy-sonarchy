from __future__ import annotations

from typing import Any

from .capabilities import queue_transport_active, tv_autoplay_enabled
from .common import DomainService, clean, coordinator_for, safe_call, string_arg
from .ports import DevicesPort


def _optional(speaker: Any, name: str) -> Any:
    try:
        return getattr(speaker, name)
    except Exception:  # noqa: BLE001 - unsupported SoCo properties are optional
        return None


def _optional_bool(speaker: Any, name: str) -> bool | None:
    value = _optional(speaker, name)
    return None if value is None else bool(value)


def _optional_int(speaker: Any, name: str) -> int | None:
    value = _optional(speaker, name)
    try:
        return None if value is None else int(value)
    except TypeError, ValueError:
        return None


def _balance(speaker: Any) -> int | None:
    value = _optional(speaker, "balance")
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        left = max(0, min(100, int(value[0])))
        right = max(0, min(100, int(value[1])))
    except TypeError, ValueError:
        return None
    if left == right:
        return 0
    return -(100 - right) if left > right else 100 - left


def _members(speaker: Any) -> list[Any]:
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


def _repeat_label(raw: Any) -> str | None:
    if raw is None:
        return None
    if clean(raw).upper() == "ONE":
        return "one"
    return "all" if bool(raw) else "off"


def _battery(speaker: Any) -> dict[str, Any] | None:
    raw = safe_call(lambda: speaker.get_battery_info(timeout=1.5), None)
    if not isinstance(raw, dict) or not raw:
        return None
    try:
        level = int(raw.get("Level", -1))
    except TypeError, ValueError:
        level = -1
    return {
        "level": level if 0 <= level <= 100 else None,
        "health": clean(raw.get("Health"))[:40],
        "temperature": clean(raw.get("Temperature"))[:40],
        "power_source": clean(raw.get("PowerSource"))[:80],
    }


def project_device_details(speaker: Any) -> dict[str, Any]:
    coordinator = coordinator_for(speaker)
    speaker_ip = clean(getattr(speaker, "ip_address", ""))
    coordinator_ip = clean(getattr(coordinator, "ip_address", speaker_ip))
    speaker_info = safe_call(speaker.get_speaker_info, {}) or {}
    repeat_value = safe_call(lambda: coordinator.repeat, None)
    sleep_timer = safe_call(coordinator.get_sleep_timer, None)
    source = clean(_optional(coordinator, "music_source")) or "UNKNOWN"
    selected_tv_autoplay = tv_autoplay_enabled(speaker)
    coordinator_tv_autoplay = (
        selected_tv_autoplay if coordinator is speaker else tv_autoplay_enabled(coordinator)
    )
    speech = _optional_bool(speaker, "speech_enhance_enabled")
    if speech is None:
        speech = _optional_bool(speaker, "dialog_mode")

    members = []
    for member in _members(speaker):
        member_ip = clean(getattr(member, "ip_address", ""))
        members.append(
            {
                "uid": clean(safe_call(lambda member=member: member.uid, "")) or member_ip,
                "name": clean(safe_call(lambda member=member: member.player_name, "")) or member_ip,
                "ip": member_ip,
                "is_coordinator": member_ip == coordinator_ip,
            }
        )

    return {
        "ok": True,
        "ip": speaker_ip,
        "playback": {
            "play_mode": clean(safe_call(lambda: coordinator.play_mode, "")),
            "shuffle": safe_call(lambda: bool(coordinator.shuffle), None),
            "repeat": _repeat_label(repeat_value),
            "crossfade": safe_call(lambda: bool(coordinator.cross_fade), None),
            "sleep_timer": None if sleep_timer is None else int(sleep_timer),
            "play_mode_supported": queue_transport_active(coordinator) is True,
            "tv_autoplay_risk": source.upper() == "TV" and coordinator_tv_autoplay is True,
        },
        "sound": {
            "bass": _optional_int(speaker, "bass"),
            "treble": _optional_int(speaker, "treble"),
            "balance": _balance(speaker),
            "loudness": _optional_bool(speaker, "loudness"),
            "night_mode": _optional_bool(speaker, "night_mode"),
            "speech_enhancement": speech,
            "sub_enabled": _optional_bool(speaker, "sub_enabled"),
            "sub_gain": _optional_int(speaker, "sub_gain"),
            "sub_crossover": _optional_int(speaker, "sub_crossover"),
            "surround_enabled": _optional_bool(speaker, "surround_enabled"),
            "surround_mode": _optional_bool(speaker, "surround_mode"),
            "surround_tv": _optional_int(speaker, "surround_volume_tv"),
            "surround_music": _optional_int(speaker, "surround_volume_music"),
            "audio_delay": _optional_int(speaker, "audio_delay"),
        },
        "device": {
            "name": clean(safe_call(lambda: speaker.player_name, "")),
            "model": clean(speaker_info.get("model_name")),
            "model_number": clean(speaker_info.get("model_number")),
            "serial_number": clean(speaker_info.get("serial_number")),
            "software_version": clean(speaker_info.get("software_version")),
            "hardware_version": clean(speaker_info.get("hardware_version")),
            "channel": clean(_optional(speaker, "channel")),
            "source": source,
            "tv_autoplay": selected_tv_autoplay,
            "status_light": _optional_bool(speaker, "status_light"),
            "buttons_enabled": _optional_bool(speaker, "buttons_enabled"),
            "trueplay": _optional_bool(speaker, "trueplay"),
            "mic_enabled": _optional_bool(speaker, "mic_enabled"),
            "voice_service_configured": _optional_bool(speaker, "voice_service_configured"),
            "battery": _battery(speaker),
        },
        "group": {"coordinator_ip": coordinator_ip, "members": members},
    }


def devices_service(backend: DevicesPort) -> DomainService:
    return DomainService(
        {"devices.details.get": lambda args: backend.device_details(string_arg(args, "roomUid"))},
        mutates=False,
    )
