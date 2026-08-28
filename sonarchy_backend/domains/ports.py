from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol


class StatePort(Protocol):
    def refresh(self, *, rediscover: bool = True) -> dict[str, Any]: ...

    def event_services(self) -> dict[str, Any]: ...

    def refresh_event_topologies(self, household_ids: Iterable[str]) -> None: ...


class PlaybackPort(Protocol):
    def play_pause(self) -> None: ...

    def play(self) -> None: ...

    def pause(self) -> None: ...

    def next(self) -> None: ...

    def previous(self) -> None: ...

    def seek(self, position_sec: Any) -> None: ...

    def move_playback_to_room(self, room_uid: str) -> None: ...


class ContentPort(Protocol):
    def play_favorite(self, favorite_id: str) -> None: ...

    def refresh_favorites(self) -> None: ...

    def play_apple(self, room_uid: str, url: str) -> dict[str, Any]: ...

    def play_apple_album(self, room_uid: str, url: str) -> dict[str, Any]: ...

    def play_global(self, room_uid: str, item_id: str, term: str) -> dict[str, Any]: ...

    def start_library_update(self, room_uid: str) -> dict[str, Any]: ...


class TopologyPort(Protocol):
    def select_group(self, group_uid: str) -> None: ...

    def select_room(self, room_uid: str) -> None: ...

    def apply_members(self, room_uids: list[str]) -> None: ...


class MixerPort(Protocol):
    def set_group_volume(self, volume: Any) -> None: ...

    def adjust_group_volume(self, delta: Any) -> None: ...

    def set_group_mute(self, mute: Any) -> None: ...

    def set_room_volume(self, room_uid: str, volume: Any) -> None: ...

    def adjust_room_volume(self, room_uid: str, delta: Any) -> None: ...

    def set_room_mute(self, room_uid: str, mute: Any) -> None: ...


class DevicesPort(Protocol):
    def device_details(self, room_uid: str) -> dict[str, Any]: ...


class BrowsePort(Protocol):
    def browse_content(
        self,
        room_uid: str,
        kind: str,
        term: str,
        limit: int,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


class AlarmsPort(Protocol):
    def list_alarms(self, room_uid: str) -> dict[str, Any]: ...

    def save_alarm(
        self,
        room_uid: str,
        alarm_id: str,
        alarm_room_uid: str,
        start: str,
        recurrence: str,
        volume: int,
        duration: int,
        enabled: bool,
        include_grouped: bool,
        program: str,
    ) -> dict[str, Any]: ...

    def toggle_alarm(self, room_uid: str, alarm_id: str, enabled: bool) -> dict[str, Any]: ...

    def delete_alarm(self, room_uid: str, alarm_id: str) -> dict[str, Any]: ...


class SettingsPort(Protocol):
    def stop_room(self, room_uid: str) -> dict[str, Any]: ...

    def rename_room(self, room_uid: str, name: str) -> dict[str, Any]: ...

    def set_playback_option(self, room_uid: str, option: str, value: str) -> dict[str, Any]: ...

    def set_sound(self, room_uid: str, setting: str, value: str) -> dict[str, Any]: ...

    def set_device(self, room_uid: str, setting: str, value: str) -> dict[str, Any]: ...

    def switch_source(
        self, room_uid: str, source: str, source_room_uid: str = ""
    ) -> dict[str, Any]: ...


class QueuePort(Protocol):
    def queue_action(
        self, room_uid: str, action: str, index: int | None = None, item_id: str = ""
    ) -> dict[str, Any]: ...

    def move_queue_item(
        self,
        room_uid: str,
        index: int,
        item_id: str,
        target_index: int,
        target_item_id: str,
    ) -> dict[str, Any]: ...

    def enqueue_content_item(
        self,
        room_uid: str,
        kind: str,
        context: str,
        item_id: str,
        index: int,
        mode: str,
        library_path: Any = None,
    ) -> dict[str, Any]: ...


class PlaylistsPort(Protocol):
    def playlist_action(self, room_uid: str, action: str, value: str) -> dict[str, Any]: ...

    def playlist_track_action(
        self, room_uid: str, action: str, playlist_id: str, index: int, item_id: str
    ) -> dict[str, Any]: ...


class ApplePlaylistPlansPort(Protocol):
    def inspect_apple_playlist_target(
        self, room_uid: str, playlist_name: str
    ) -> dict[str, Any]: ...

    def create_preflighted_apple_playlist(self, plan: dict[str, Any]) -> dict[str, Any]: ...


class SonarchyBackendPort(
    StatePort,
    PlaybackPort,
    ContentPort,
    TopologyPort,
    MixerPort,
    DevicesPort,
    BrowsePort,
    AlarmsPort,
    SettingsPort,
    QueuePort,
    PlaylistsPort,
    ApplePlaylistPlansPort,
    Protocol,
):
    """Temporary adapter port implemented by the legacy controller."""
