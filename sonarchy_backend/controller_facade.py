from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .controller_common import ControllerError
from .domains.alarms import delete_alarm, project_alarms, save_alarm, toggle_alarm
from .domains.apple_playlist_transaction import (
    create_preflighted_apple_playlist,
    inspect_apple_playlist_target,
)
from .domains.browse import browse_content
from .domains.content import play_apple, play_apple_album, play_global, start_library_update
from .domains.devices import project_device_details
from .domains.errors import PlanConflictError, PlaylistPlayTransactionError
from .domains.playlist_playback import (
    execute_preflighted_playlist_play,
    inspect_playlist_play_target,
)
from .domains.playlists import playlist_action, playlist_track_action
from .domains.queue import enqueue_content_item, move_queue_item, queue_action
from .domains.settings import rename_room as rename_sonos_room
from .domains.settings import set_device as set_sonos_device
from .domains.settings import set_playback_option as set_sonos_playback_option
from .domains.settings import set_sound as set_sonos_sound
from .domains.settings import stop_playback
from .domains.settings import switch_source as switch_sonos_source


class DomainFacadeMixin:
    def device_details(self, room_uid: str) -> dict[str, Any]:
        return project_device_details(self._zone(room_uid))

    def browse_content(
        self,
        room_uid: str,
        kind: str,
        term: str,
        limit: int,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        speaker = self._zone(room_uid)
        coordinator = self._safe(
            lambda: speaker.group.coordinator if speaker.group else speaker, speaker
        )
        return browse_content(coordinator, kind, term, limit, context)

    def list_alarms(self, room_uid: str) -> dict[str, Any]:
        return project_alarms(self._zone(room_uid))

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
    ) -> dict[str, Any]:
        return save_alarm(
            self._zone(room_uid),
            alarm_id,
            alarm_room_uid,
            start,
            recurrence,
            volume,
            duration,
            enabled,
            include_grouped,
            program,
        )

    def toggle_alarm(self, room_uid: str, alarm_id: str, enabled: bool) -> dict[str, Any]:
        return toggle_alarm(self._zone(room_uid), alarm_id, enabled)

    def delete_alarm(self, room_uid: str, alarm_id: str) -> dict[str, Any]:
        return delete_alarm(self._zone(room_uid), alarm_id)

    def queue_action(
        self, room_uid: str, action: str, index: int | None = None, item_id: str = ""
    ) -> dict[str, Any]:
        return queue_action(self._zone(room_uid), action, index, item_id)

    def move_queue_item(
        self,
        room_uid: str,
        index: int,
        item_id: str,
        target_index: int,
        target_item_id: str,
    ) -> dict[str, Any]:
        return move_queue_item(self._zone(room_uid), index, item_id, target_index, target_item_id)

    def enqueue_content_item(
        self,
        room_uid: str,
        kind: str,
        context: str,
        item_id: str,
        index: int,
        mode: str,
        library_path: Any = None,
    ) -> dict[str, Any]:
        return enqueue_content_item(
            self._zone(room_uid), kind, context, item_id, index, mode, library_path
        )

    def playlist_action(self, room_uid: str, action: str, value: str) -> dict[str, Any]:
        return playlist_action(self._zone(room_uid), action, value)

    def playlist_track_action(
        self, room_uid: str, action: str, playlist_id: str, index: int, item_id: str
    ) -> dict[str, Any]:
        return playlist_track_action(self._zone(room_uid), action, playlist_id, index, item_id)

    def inspect_apple_playlist_target(self, room_uid: str, playlist_name: str) -> dict[str, Any]:
        try:
            speaker = self._zone(room_uid)
        except ControllerError as exc:
            raise PlanConflictError("The exact Sonos room is unavailable") from exc
        return inspect_apple_playlist_target(speaker, playlist_name)

    def create_preflighted_apple_playlist(self, plan: dict[str, Any]) -> dict[str, Any]:
        room_uid = str(plan.get("roomUid", ""))
        try:
            speaker = self._zone(room_uid)
        except ControllerError as exc:
            raise PlanConflictError("The exact Sonos room is unavailable") from exc
        return create_preflighted_apple_playlist(speaker, plan)

    def inspect_playlist_play_target(self, room_uid: str, playlist_id: str) -> dict[str, Any]:
        try:
            speaker = self._zone(room_uid)
        except ControllerError as exc:
            raise PlanConflictError("The exact Sonos room is unavailable") from exc
        return inspect_playlist_play_target(speaker, playlist_id)

    def execute_preflighted_playlist_play(
        self,
        plan: dict[str, Any],
        mutation_started_callback: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        room_uid = str(plan.get("roomUid", ""))
        try:
            speaker = self._zone(room_uid)
        except ControllerError as exc:
            raise PlaylistPlayTransactionError(
                phase="preflight_revalidation",
                diagnostics={
                    "appendState": "absent",
                    "playbackStarted": False,
                    "queueRollbackAttempted": False,
                    "appendInvocationCount": 0,
                    "playbackStartInvocationCount": 0,
                    "retryCount": 0,
                    "succeeded": False,
                },
            ) from exc
        return execute_preflighted_playlist_play(
            speaker,
            plan,
            mutation_started_callback=mutation_started_callback,
        )

    def play_apple(self, room_uid: str, url: str) -> dict[str, Any]:
        return play_apple(self._zone(room_uid), url)

    def play_apple_album(self, room_uid: str, url: str) -> dict[str, Any]:
        return play_apple_album(self._zone(room_uid), url)

    def play_global(self, room_uid: str, item_id: str, term: str) -> dict[str, Any]:
        return play_global(self._zone(room_uid), item_id, term)

    def start_library_update(self, room_uid: str) -> dict[str, Any]:
        return start_library_update(self._zone(room_uid))

    def stop_room(self, room_uid: str) -> dict[str, Any]:
        return stop_playback(self._zone(room_uid))

    def rename_room(self, room_uid: str, name: str) -> dict[str, Any]:
        return rename_sonos_room(self._zone(room_uid), name)

    def set_playback_option(self, room_uid: str, option: str, value: str) -> dict[str, Any]:
        return set_sonos_playback_option(self._zone(room_uid), option, value)

    def set_sound(self, room_uid: str, setting: str, value: str) -> dict[str, Any]:
        return set_sonos_sound(self._zone(room_uid), setting, value)

    def set_device(self, room_uid: str, setting: str, value: str) -> dict[str, Any]:
        return set_sonos_device(self._zone(room_uid), setting, value)

    def switch_source(
        self, room_uid: str, source: str, source_room_uid: str = ""
    ) -> dict[str, Any]:
        speaker = self._zone(room_uid)
        source_speaker = self._zone(source_room_uid) if source_room_uid else None
        return switch_sonos_source(speaker, source, source_speaker)

    def select_room(self, room_uid: str) -> None:
        """Remember one exact room without changing its group or playback."""
        snapshot = self.refresh(rediscover=False)
        for household in snapshot["households"]:
            if any(room["uid"] == room_uid for room in household["rooms"]):
                self.state.selected_room_uid = room_uid
                self._save_state_quietly()
                return
        raise ControllerError(f"Unknown Sonos room: {room_uid}")
