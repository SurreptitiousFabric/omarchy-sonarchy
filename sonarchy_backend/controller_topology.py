from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable
from typing import Any

from .controller_common import (
    TOPOLOGY_QUERY_TIMEOUT_SEC,
    TOPOLOGY_SETTLE_ATTEMPTS,
    TOPOLOGY_SETTLE_INTERVAL_SEC,
    ControllerError,
)

LOG = logging.getLogger(__name__)


class TopologyMixin:
    def _coordinator(self) -> Any:
        if self._target_group is None:
            self.refresh()
        if self._target_group is None:
            raise ControllerError("No target Sonos group is available")
        return self._target_group.coordinator

    def _zone(self, uid: str) -> Any:
        if uid not in self._zones:
            self.refresh()
        zone = self._zones.get(uid)
        if zone is None:
            raise ControllerError(f"Unknown or offline room: {uid}")
        return zone

    def _clear_topology_caches(self) -> None:
        """Force subsequent SoCo group reads to query authoritative topology."""
        for zone in self._zones.values():
            topology = getattr(zone, "zone_group_state", None)
            clear_cache = getattr(topology, "clear_cache", None)
            if callable(clear_cache):
                self._safe(clear_cache)

    def _household_representative(self, household_id: str = "") -> Any | None:
        for zone in self._zones.values():
            if not household_id:
                return zone
            zone_household = str(self._safe(lambda z=zone: z.household_id, "unknown") or "unknown")
            if zone_household == household_id:
                return zone
        return None

    def _refresh_topology_authoritatively(self, household_id: str = "") -> bool:
        """Bypass SoCo's subscription-backed topology cache.

        SoCo 0.31.2 declines to poll ZoneGroupState while any subscription is
        active. The threaded events implementation does not apply the topology
        payload to ZoneGroupState, so group mutations otherwise remain stale.
        """
        representative = self._household_representative(household_id)
        if representative is None:
            return False
        service = getattr(representative, "zoneGroupTopology", None)
        topology = getattr(representative, "zone_group_state", None)
        get_state = getattr(service, "GetZoneGroupState", None)
        process_payload = getattr(topology, "process_payload", None)
        if not callable(get_state) or not callable(process_payload):
            return False
        try:
            response = get_state(timeout=TOPOLOGY_QUERY_TIMEOUT_SEC)
            payload = response.get("ZoneGroupState", "") if response else ""
            if not payload:
                return False
            process_payload(
                payload=payload,
                source="sonarchy-authoritative-poll",
                source_ip=str(getattr(representative, "ip_address", "") or ""),
            )
            return True
        except Exception as exc:  # noqa: BLE001 - retry/fallback owns failures
            LOG.debug("Authoritative Sonos topology query failed: %s", exc)
            return False

    def refresh_event_topologies(self, household_ids: Iterable[str]) -> None:
        """Apply authoritative topology after SoCo's threaded event callback."""
        for household_id in sorted(set(household_ids)):
            self._refresh_topology_authoritatively(household_id)

    @staticmethod
    def _snapshot_group_for_room(
        snapshot: dict[str, Any], household_id: str, room_uid: str
    ) -> dict[str, Any] | None:
        for household in snapshot.get("households", []):
            if household.get("id") != household_id:
                continue
            for group in household.get("groups", []):
                if room_uid in group.get("memberUids", []):
                    return group
        return None

    def _wait_for_topology(
        self,
        predicate: Callable[[dict[str, Any]], bool],
        *,
        household_id: str = "",
        phase: str = "topology mutation",
    ) -> dict[str, Any]:
        """Poll briefly while Sonos and SoCo converge after a group mutation."""
        latest: dict[str, Any] = {}
        started = time.monotonic()
        for attempt in range(TOPOLOGY_SETTLE_ATTEMPTS):
            # SoCo's join/unjoin methods clear only the mutated speaker's
            # cache. Refresh may use another household member as its topology
            # representative, so invalidate all known views before checking.
            self._clear_topology_caches()
            authoritative = self._refresh_topology_authoritatively(household_id)
            latest = self.refresh(rediscover=False)
            if predicate(latest):
                LOG.info(
                    "Sonos %s confirmed after %.2fs (%s checks, authoritative=%s)",
                    phase,
                    time.monotonic() - started,
                    attempt + 1,
                    authoritative,
                )
                return latest
            if attempt + 1 < TOPOLOGY_SETTLE_ATTEMPTS:
                time.sleep(TOPOLOGY_SETTLE_INTERVAL_SEC)
        LOG.warning(
            "Sonos %s did not converge after %.2fs (%s checks)",
            phase,
            time.monotonic() - started,
            TOPOLOGY_SETTLE_ATTEMPTS,
        )
        return latest

    def _wait_for_room_memberships(
        self,
        household_id: str,
        expected: dict[str, set[str]],
        *,
        phase: str,
    ) -> dict[str, Any]:
        """Wait on the small topology model, avoiding full household refreshes."""
        representative = self._household_representative(household_id)
        topology = getattr(representative, "zone_group_state", None)
        if topology is None or not callable(getattr(topology, "process_payload", None)):
            return self._wait_for_topology(
                lambda current: all(
                    set(
                        (self._snapshot_group_for_room(current, household_id, room_uid) or {}).get(
                            "memberUids", []
                        )
                    )
                    == members
                    for room_uid, members in expected.items()
                ),
                household_id=household_id,
                phase=phase,
            )

        started = time.monotonic()
        logical_uids = set(self._zones)
        observed: dict[str, set[str]] = {}
        for attempt in range(TOPOLOGY_SETTLE_ATTEMPTS):
            self._refresh_topology_authoritatively(household_id)
            observed = {}
            for group in getattr(topology, "groups", set()) or set():
                members = {
                    self._zone_uid(member)
                    for member in getattr(group, "members", set())
                    if self._zone_uid(member) in logical_uids
                }
                for uid in members:
                    observed[uid] = members
            if all(observed.get(uid, set()) == members for uid, members in expected.items()):
                LOG.info(
                    "Sonos %s confirmed after %.2fs (%s topology checks)",
                    phase,
                    time.monotonic() - started,
                    attempt + 1,
                )
                return self.refresh(rediscover=False)
            if attempt + 1 < TOPOLOGY_SETTLE_ATTEMPTS:
                time.sleep(TOPOLOGY_SETTLE_INTERVAL_SEC)
        LOG.warning(
            "Sonos %s did not converge after %.2fs; observed memberships: %s",
            phase,
            time.monotonic() - started,
            {uid: sorted(members) for uid, members in observed.items()},
        )
        return self.refresh(rediscover=False)

    def _refresh_after_topology_mutation(self, household_id: str) -> dict[str, Any]:
        self._clear_topology_caches()
        self._refresh_topology_authoritatively(household_id)
        return self.refresh(rediscover=False)

    @staticmethod
    def _play_confirmed_coordinator(zone: Any) -> None:
        """Play after snapshot verification without consulting SoCo's stale role cache."""
        try:
            zone.play()
            return
        except Exception as exc:
            if type(exc).__name__ != "SoCoSlaveException":
                raise
            LOG.info(
                "Bypassing stale SoCo coordinator role for confirmed room %s",
                str(getattr(zone, "uid", "") or ""),
            )
        zone.avTransport.Play([("InstanceID", 0), ("Speed", 1)])

    def select_group(self, group_uid: str) -> None:
        snapshot = self.refresh(rediscover=False)
        for household in snapshot["households"]:
            for group in household["groups"]:
                if group["uid"] == group_uid and group["memberUids"]:
                    self.state.selected_room_uid = group["memberUids"][0]
                    self._save_state_quietly()
                    return
        raise ControllerError(f"Unknown Sonos group: {group_uid}")

    def apply_members(self, room_uids: list[str]) -> None:
        """Reconcile selected logical rooms around the current coordinator.

        The old coordinator is removed last if it is not retained. We refresh
        after each topology mutation so the next decision is based on Sonos's
        authoritative state rather than a hoped-for transaction.
        """
        requested = list(dict.fromkeys(str(uid) for uid in room_uids if uid))
        if not requested:
            raise ControllerError("A Sonos group must contain at least one room")

        snapshot = self.refresh(rediscover=False)
        target = snapshot.get("target")
        if not target:
            raise ControllerError("No target Sonos group is available")
        old_coordinator_uid = str(target["coordinatorUid"])
        requested_set = set(requested)
        source_was_playing = str(snapshot.get("playback", {}).get("state", "")).upper() == "PLAYING"

        # Sonos households are a hard boundary. Never join across them.
        allowed_uids: set[str] = set()
        for household in snapshot["households"]:
            if household["id"] == target["householdId"]:
                allowed_uids = {room["uid"] for room in household["rooms"]}
                break
        invalid = requested_set - allowed_uids
        if invalid:
            raise ControllerError(
                "Cannot group rooms outside the active Sonos household: "
                + ", ".join(sorted(invalid))
            )

        retained_uid = requested[0]
        if old_coordinator_uid in requested_set:
            retained_uid = old_coordinator_uid
        master = self._zone(old_coordinator_uid)

        # Add requested outsiders one by one to the current coordinator.
        current_members = set(target["memberUids"])
        for uid in requested:
            if uid in current_members:
                continue
            self._zone(uid).join(master)
            refreshed = self._refresh_after_topology_mutation(target["householdId"])
            current = refreshed.get("target") or {}
            current_members = set(current.get("memberUids", []))
            if uid not in current_members:
                raise ControllerError(f"Sonos did not add room {uid} to the group")

        # Remove unwanted followers first.
        refreshed = self.refresh(rediscover=False)
        current = refreshed.get("target") or {}
        current_members = list(current.get("memberUids", []))
        for uid in current_members:
            if uid == old_coordinator_uid or uid in requested_set:
                continue
            self._zone(uid).unjoin()
            self._refresh_after_topology_mutation(target["householdId"])

        # Coordinator removal is deliberately last because Sonos elects the
        # replacement. Anchor to a retained room before the topology shifts.
        if old_coordinator_uid not in requested_set:
            self.state.selected_room_uid = retained_uid
            self._save_state_quietly()
            detached = self._zone(old_coordinator_uid)
            detached.unjoin()
            final = self._refresh_after_topology_mutation(target["householdId"])

            # Sonos may leave the old coordinator playing by itself after it
            # becomes a standalone group. Stop it only after topology confirms
            # that detachment.
            detached_is_standalone = False
            for household in final.get("households", []):
                if household.get("id") != target["householdId"]:
                    continue
                for group in household.get("groups", []):
                    if group.get("coordinatorUid") == old_coordinator_uid and group.get(
                        "memberUids"
                    ) == [old_coordinator_uid]:
                        detached_is_standalone = True
                        break
            if detached_is_standalone:
                detached.stop()
                final = self.refresh(rediscover=False)
        else:
            final = self.refresh(rediscover=False)

        actual = set((final.get("target") or {}).get("memberUids", []))
        if actual != requested_set:
            raise ControllerError(
                "Sonos partially applied the grouping request; actual members: "
                + ", ".join(sorted(actual))
            )

        # Coordinator handoff can leave the retained room paused even though
        # the source was playing. Restore only an observed PLAYING state; do
        # not start audio that the user had paused before moving it.
        if (
            source_was_playing
            and str(final.get("playback", {}).get("state", "")).upper() != "PLAYING"
        ):
            self._coordinator().play()
            final = self.refresh(rediscover=False)

        self.state.selected_room_uid = retained_uid
        self._save_state_quietly()
