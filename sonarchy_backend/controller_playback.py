from __future__ import annotations

import logging
from typing import Any

from .controller_common import ControllerError
from .model import clamp_volume, format_sonos_time

LOG = logging.getLogger(__name__)


class PlaybackMixin:
    def play_pause(self) -> None:
        coordinator = self._coordinator()
        transport = coordinator.get_current_transport_info()
        if str(transport.get("current_transport_state", "")).upper() == "PLAYING":
            coordinator.pause()
        else:
            coordinator.play()

    def play(self) -> None:
        self._coordinator().play()

    def pause(self) -> None:
        self._coordinator().pause()

    def next(self) -> None:
        self._coordinator().next()

    def previous(self) -> None:
        self._coordinator().previous()

    def seek(self, position_sec: Any) -> None:
        self._coordinator().seek(format_sonos_time(max(0, int(position_sec))))

    def set_group_volume(self, volume: Any) -> None:
        if self._target_group is None:
            self.refresh()
        if self._target_group is None:
            raise ControllerError("No target Sonos group is available")
        self._target_group.volume = clamp_volume(volume)

    def adjust_group_volume(self, delta: Any) -> None:
        if self._target_group is None:
            self.refresh()
        if self._target_group is None:
            raise ControllerError("No target Sonos group is available")
        self._target_group.set_relative_volume(int(delta))

    def set_group_mute(self, mute: Any) -> None:
        if self._target_group is None:
            self.refresh()
        if self._target_group is None:
            raise ControllerError("No target Sonos group is available")
        self._target_group.mute = bool(mute)

    def set_room_volume(self, room_uid: str, volume: Any) -> None:
        self._zone(room_uid).volume = clamp_volume(volume)

    def adjust_room_volume(self, room_uid: str, delta: Any) -> None:
        self._zone(room_uid).set_relative_volume(int(delta))

    def set_room_mute(self, room_uid: str, mute: Any) -> None:
        self._zone(room_uid).mute = bool(mute)

    def _rollback_audio_handoff(
        self,
        source: Any,
        destination: Any,
        source_uid: str,
        destination_uid: str,
        household_id: str,
        source_was_playing: bool,
    ) -> None:
        """Best-effort restoration of the pre-handoff standalone rooms."""
        LOG.warning(
            "Rolling back Sonos audio handoff %s -> %s",
            source_uid,
            destination_uid,
        )
        try:
            destination.unjoin()
            self._wait_for_room_memberships(
                household_id,
                {
                    source_uid: {source_uid},
                    destination_uid: {destination_uid},
                },
                phase="handoff rollback",
            )
        except Exception as exc:  # noqa: BLE001 - preserve the original error
            LOG.warning("Could not fully restore Sonos topology: %s", exc)
        self.state.selected_room_uid = source_uid
        self._save_state_quietly()
        if source_was_playing:
            try:
                self._play_confirmed_coordinator(source)
            except Exception as exc:  # noqa: BLE001 - preserve the original error
                LOG.warning("Could not resume source after handoff rollback: %s", exc)

    def _move_direct_stream(
        self,
        source: Any,
        destination: Any,
        snapshot: dict[str, Any],
    ) -> bool:
        """Move addressable streams without slow, failure-prone regrouping."""
        ok, media = self._query_with_retry(
            "media for direct room handoff",
            lambda: source.avTransport.GetMediaInfo([("InstanceID", 0)]),
            {},
        )
        if not ok or not isinstance(media, dict):
            return False
        uri = str(media.get("CurrentURI", "") or "")
        if not self._favorite_is_directly_playable(uri):
            return False
        metadata = str(media.get("CurrentURIMetaData", "") or "")
        position = snapshot.get("playback", {}).get("positionSec")
        actions = {
            str(action) for action in snapshot.get("playback", {}).get("availableActions", [])
        }

        source.pause()
        try:
            destination.avTransport.SetAVTransportURI(
                [
                    ("InstanceID", 0),
                    ("CurrentURI", uri),
                    ("CurrentURIMetaData", metadata),
                ]
            )
            if position is not None and "SeekTime" in actions:
                destination.avTransport.Seek(
                    [
                        ("InstanceID", 0),
                        ("Unit", "REL_TIME"),
                        ("Target", format_sonos_time(max(0, int(position)))),
                    ]
                )
            self._play_confirmed_coordinator(destination)
        except Exception:
            self._play_confirmed_coordinator(source)
            raise
        LOG.info(
            "Moved direct Sonos stream %s -> %s without regrouping",
            self._zone_uid(source),
            self._zone_uid(destination),
        )
        return True

    def move_playback_to_room(self, room_uid: str) -> None:
        """Select a room, moving the current session only while it is playing.

        When the selected session is paused or stopped, this is only a control
        target change and never mutates topology. For playing audio, rooms in a
        different multi-room group remain protected because joining one would
        dismantle that group as a side effect; those changes belong to the
        explicit group-settings operation.
        """
        snapshot = self.refresh(rediscover=False)
        target = snapshot.get("target")
        if not target:
            raise ControllerError("No target Sonos group is available")

        household = next(
            (
                item
                for item in snapshot.get("households", [])
                if item.get("id") == target.get("householdId")
            ),
            None,
        )
        if household is None or room_uid not in {
            room.get("uid") for room in household.get("rooms", [])
        }:
            raise ControllerError("The selected room is unavailable")

        source_was_playing = str(snapshot.get("playback", {}).get("state", "")).upper() in {
            "PLAYING",
            "TRANSITIONING",
        }
        if not source_was_playing:
            self.state.selected_room_uid = room_uid
            self._save_state_quietly()
            return

        current_members = set(target.get("memberUids", []))
        if len(current_members) > 1:
            raise ControllerError(
                "Current audio is playing on a group. Change that group "
                "deliberately in Group settings before moving to one room."
            )
        for group in household.get("groups", []):
            members = set(group.get("memberUids", []))
            if room_uid in members and len(members) > 1:
                raise ControllerError(
                    "That room belongs to another group. Change groups deliberately "
                    "in Group settings first."
                )

        source_uid = str(target.get("coordinatorUid", ""))
        if room_uid == source_uid:
            return

        source = self._zone(source_uid)
        destination = self._zone(room_uid)

        if self._move_direct_stream(source, destination, snapshot):
            self.state.selected_room_uid = room_uid
            self._save_state_quietly()
            return

        # Silence the source before the session handoff so joining the
        # destination never makes both rooms audible, even briefly.
        if source_was_playing:
            source.pause()

        try:
            destination.join(source)
        except Exception:
            # A failed join has not moved the session. Restore what the user
            # was listening to rather than leaving the source paused.
            if source_was_playing:
                source.play()
            raise

        household_id = str(target.get("householdId", ""))
        joined = self._wait_for_room_memberships(
            household_id,
            {
                source_uid: {source_uid, room_uid},
                room_uid: {source_uid, room_uid},
            },
            phase="handoff join",
        )
        joined_group = self._snapshot_group_for_room(joined, household_id, source_uid) or {}
        joined_members = set(joined_group.get("memberUids", []))
        if joined_members != {source_uid, room_uid}:
            self._rollback_audio_handoff(
                source,
                destination,
                source_uid,
                room_uid,
                household_id,
                source_was_playing,
            )
            raise ControllerError("Sonos did not prepare the selected room for the audio handoff")

        # Anchor selection to the destination before detaching the old
        # coordinator. Sonos will elect the remaining room as coordinator.
        self.state.selected_room_uid = room_uid
        self._save_state_quietly()
        source.unjoin()
        final = self._wait_for_room_memberships(
            household_id,
            {source_uid: {source_uid}, room_uid: {room_uid}},
            phase="handoff detach",
        )

        source_group = self._snapshot_group_for_room(final, household_id, source_uid) or {}
        destination_group = self._snapshot_group_for_room(final, household_id, room_uid) or {}
        source_members = set(source_group.get("memberUids", []))
        destination_members = set(destination_group.get("memberUids", []))
        source_state = str(source_group.get("playbackState", "")).upper()

        if source_members != {source_uid} or destination_members != {room_uid}:
            self._rollback_audio_handoff(
                source,
                destination,
                source_uid,
                room_uid,
                household_id,
                source_was_playing,
            )
            raise ControllerError("Sonos partially moved the audio; the rooms are not standalone")

        # Coordinator changes can restart the detached source. If that
        # happened, pause it again after topology confirms it is independent,
        # then resume only the new destination.
        if source_was_playing:
            if source_state == "PLAYING":
                source.pause()
            self._play_confirmed_coordinator(destination)

        self.state.selected_room_uid = room_uid
        self._save_state_quietly()
