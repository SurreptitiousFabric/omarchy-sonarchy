from __future__ import annotations

from typing import Any

from .capabilities import line_in_available, queue_transport_active, tv_autoplay_enabled
from .common import DomainService, clean, coordinator_for, safe_call, string_arg
from .ports import SettingsPort

NUMBER_SETTINGS = {
    "bass": (-10, 10),
    "treble": (-10, 10),
    "sub-gain": (-15, 15),
    "sub-crossover": (50, 110),
    "surround-tv": (-15, 15),
    "surround-music": (-15, 15),
    "audio-delay": (0, 5),
    "balance": (-100, 100),
}
BOOLEAN_SETTINGS = {
    "loudness": "loudness",
    "night-mode": "night_mode",
    "sub-enabled": "sub_enabled",
    "surround-enabled": "surround_enabled",
    "surround-mode": "surround_mode",
}
NUMBER_ATTRIBUTES = {
    "sub-gain": "sub_gain",
    "sub-crossover": "sub_crossover",
    "surround-tv": "surround_volume_tv",
    "surround-music": "surround_volume_music",
    "audio-delay": "audio_delay",
}
DEVICE_BOOLEAN_SETTINGS = {
    "status-light": "status_light",
    "buttons-enabled": "buttons_enabled",
    "trueplay": "trueplay",
}
TV_AUTOPLAY_SETTING = "tv-autoplay"
DEVICE_SETTINGS = frozenset({*DEVICE_BOOLEAN_SETTINGS, TV_AUTOPLAY_SETTING})


def _parse_bool(raw: str | bool) -> bool:
    if isinstance(raw, bool):
        return raw
    value = clean(raw).casefold()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError("Expected on or off")


def stop_playback(speaker: Any) -> dict[str, Any]:
    coordinator = coordinator_for(speaker)
    coordinator.stop()
    return {
        "ok": True,
        "action": "stop",
        "coordinator_ip": clean(getattr(coordinator, "ip_address", "")),
        "message": "Stopped",
    }


def rename_room(speaker: Any, name: str) -> dict[str, Any]:
    room_name = clean(name)
    if not room_name:
        raise ValueError("Room name cannot be empty")
    if len(room_name) > 64 or any(ord(character) < 32 for character in room_name):
        raise ValueError("Room name is too long or contains control characters")
    speaker.player_name = room_name
    response = safe_call(lambda: speaker.deviceProperties.GetZoneAttributes([]), None)
    if isinstance(response, dict) and clean(response.get("CurrentZoneName")) != room_name:
        raise ValueError("Sonos did not confirm the room name change")
    return {"ok": True, "action": "rename", "name": room_name, "message": f"Renamed to {room_name}"}


def set_playback_option(speaker: Any, option: str, value: str) -> dict[str, Any]:
    coordinator = coordinator_for(speaker)
    if (
        option in {"shuffle", "repeat", "crossfade"}
        and queue_transport_active(coordinator) is False
    ):
        raise ValueError(
            "Play modes are available only while the Sonos queue is the active source. "
            "Choose a queued track first."
        )
    if option == "shuffle":
        enabled = _parse_bool(value)
        coordinator.shuffle = enabled
        message = "Shuffle on" if enabled else "Shuffle off"
    elif option == "repeat":
        mode = clean(value).casefold()
        if mode not in {"off", "all", "one"}:
            raise ValueError("Repeat must be off, all, or one")
        coordinator.repeat = {"off": False, "all": True, "one": "ONE"}[mode]
        message = {"off": "Repeat off", "all": "Repeat all", "one": "Repeat one"}[mode]
    elif option == "crossfade":
        enabled = _parse_bool(value)
        coordinator.cross_fade = enabled
        message = "Crossfade on" if enabled else "Crossfade off"
    elif option == "sleep":
        if clean(value).casefold() == "off":
            seconds = None
            message = "Sleep timer cancelled"
        else:
            seconds = int(value)
            if seconds < 60 or seconds > 86399:
                raise ValueError("Sleep timer must be between 1 minute and 23 hours")
            message = f"Sleep timer {max(1, round(seconds / 60))} min"
        coordinator.set_sleep_timer(seconds)
    else:
        raise ValueError(f"Unsupported playback option: {option}")
    return {"ok": True, "action": option, "message": message}


def set_sound(speaker: Any, setting: str, value: str) -> dict[str, Any]:
    if setting in NUMBER_SETTINGS:
        lower, upper = NUMBER_SETTINGS[setting]
        number = max(lower, min(upper, int(value)))
        if setting == "balance":
            speaker.balance = (100, 100 + number) if number < 0 else (100 - number, 100)
        elif setting in {"bass", "treble"}:
            setattr(speaker, setting, number)
        else:
            setattr(speaker, NUMBER_ATTRIBUTES[setting], number)
        message = f"{setting.replace('-', ' ').title()} {number:+d}"
    elif setting == "speech-enhancement":
        enabled = _parse_bool(value)
        try:
            speaker.speech_enhance_enabled = enabled
        except Exception:  # noqa: BLE001 - older soundbars use the fallback property
            speaker.dialog_mode = enabled
        message = "Speech enhancement on" if enabled else "Speech enhancement off"
    elif setting in BOOLEAN_SETTINGS:
        enabled = _parse_bool(value)
        setattr(speaker, BOOLEAN_SETTINGS[setting], enabled)
        message = f"{setting.replace('-', ' ').title()} {'on' if enabled else 'off'}"
    else:
        raise ValueError(f"Unsupported sound setting: {setting}")
    return {"ok": True, "action": setting, "message": message}


def set_device(speaker: Any, setting: str, value: str) -> dict[str, Any]:
    if setting not in DEVICE_SETTINGS:
        raise ValueError("Unsupported device setting")
    enabled = _parse_bool(value)
    if setting == TV_AUTOPLAY_SETTING:
        if tv_autoplay_enabled(speaker) is None:
            raise ValueError("TV Autoplay is not available on this speaker")
        room_uuid = clean(safe_call(lambda: speaker.uid, ""))
        if enabled and not room_uuid:
            raise ValueError("Sonos did not provide the room identity needed for TV Autoplay")
        speaker.deviceProperties.SetAutoplayRoomUUID(
            [("RoomUUID", room_uuid if enabled else ""), ("Source", "")]
        )
        if tv_autoplay_enabled(speaker) is not enabled:
            raise ValueError("Sonos did not confirm the TV Autoplay change")
    else:
        setattr(speaker, DEVICE_BOOLEAN_SETTINGS[setting], enabled)
    label = "TV Autoplay" if setting == TV_AUTOPLAY_SETTING else setting.replace("-", " ").title()
    return {"ok": True, "action": setting, "message": f"{label} {'on' if enabled else 'off'}"}


def switch_source(speaker: Any, source: str, source_speaker: Any | None = None) -> dict[str, Any]:
    coordinator = coordinator_for(speaker)
    if source == "line-in":
        line_in = source_speaker or speaker
        visible = list(safe_call(lambda: speaker.visible_zones, set()) or set())
        if all(
            clean(getattr(zone, "ip_address", "")) != clean(speaker.ip_address) for zone in visible
        ):
            visible.append(speaker)
        expected_ip = clean(getattr(line_in, "ip_address", ""))
        if all(clean(getattr(zone, "ip_address", "")) != expected_ip for zone in visible):
            raise ValueError("Line-in source is not part of this Sonos household")
        if not line_in_available(line_in):
            raise ValueError("Line-in is not available on the selected Sonos room")
        coordinator.switch_to_line_in(line_in)
        message = "Playing line-in"
    elif source == "tv":
        coordinator.switch_to_tv()
        message = "Playing TV audio"
    else:
        raise ValueError("Unsupported Sonos source")
    return {"ok": True, "action": f"source-{source}", "message": message}


def settings_service(backend: SettingsPort) -> DomainService:
    def source_room_uid(args: dict[str, Any]) -> str:
        value = args.get("sourceRoomUid", "")
        if not isinstance(value, str):
            raise ValueError("sourceRoomUid must be a string")
        return value.strip()

    return DomainService(
        {
            "playback.stop": lambda args: backend.stop_room(string_arg(args, "roomUid")),
            "devices.rename": lambda args: backend.rename_room(
                string_arg(args, "roomUid"), string_arg(args, "name")
            ),
            "playback.option.set": lambda args: backend.set_playback_option(
                string_arg(args, "roomUid"), string_arg(args, "option"), string_arg(args, "value")
            ),
            "sound.setting.set": lambda args: backend.set_sound(
                string_arg(args, "roomUid"), string_arg(args, "setting"), string_arg(args, "value")
            ),
            "devices.setting.set": lambda args: backend.set_device(
                string_arg(args, "roomUid"), string_arg(args, "setting"), string_arg(args, "value")
            ),
            "sources.switch": lambda args: backend.switch_source(
                string_arg(args, "roomUid"),
                string_arg(args, "source"),
                source_room_uid(args),
            ),
        }
    )
