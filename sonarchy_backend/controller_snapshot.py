from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring as safe_xml_fromstring

from .controller_common import (
    ARTWORK_AVAILABILITY_CACHE_LIMIT,
    ARTWORK_AVAILABILITY_TTL_SEC,
    ControllerError,
)
from .model import choose_target_group, clamp_volume, group_label, parse_sonos_time

LOG = logging.getLogger(__name__)


class SnapshotMixin:
    def _available_artwork_url(self, url: str) -> str:
        if not url.startswith("http://"):
            return url
        now = time.monotonic()
        cached = self._artwork_availability_cache.get(url)
        if cached and now - cached[1] < ARTWORK_AVAILABILITY_TTL_SEC:
            return url if cached[0] else ""
        available = bool(self._artwork_probe_fn(url))
        self._artwork_availability_cache.pop(url, None)
        self._artwork_availability_cache[url] = (available, now)
        while len(self._artwork_availability_cache) > ARTWORK_AVAILABILITY_CACHE_LIMIT:
            self._artwork_availability_cache.pop(next(iter(self._artwork_availability_cache)))
        return url if available else ""

    def refresh(self, *, rediscover: bool = True) -> dict[str, Any]:
        if not rediscover and self._zones:
            zones = list(self._zones.values())
        else:
            try:
                zones = self._discover_zones()
            except ControllerError as exc:
                self._last_snapshot = self._empty_snapshot("setup_error", str(exc))
                self._last_snapshot["status"]["discovery"] = dict(self._discovery_diagnostics)
                self._last_snapshot["selectedAnchorRoomUid"] = self.state.selected_room_uid
                return self._last_snapshot

        if not zones:
            self._zones = {}
            self._target_group = None
            self._last_snapshot = self._empty_snapshot(
                "offline",
                "Not connected to your Sonos network",
            )
            self._last_snapshot["status"]["discovery"] = dict(self._discovery_diagnostics)
            self._last_snapshot["selectedAnchorRoomUid"] = self.state.selected_room_uid
            return self._last_snapshot

        # A discovered bonded component can expose hidden zones. visible_zones on
        # a household member gives us logical user-facing rooms only.
        logical: dict[str, Any] = {}
        for zone in zones:
            visible = self._safe(lambda z=zone: z.visible_zones, None)
            candidates: Iterable[Any] = visible if visible is not None else [zone]
            for candidate in candidates:
                uid = self._zone_uid(candidate)
                if uid:
                    logical[uid] = candidate
        self._zones = logical
        self._refresh_source_capabilities(logical)

        by_household: dict[str, list[Any]] = defaultdict(list)
        for zone in logical.values():
            household_id = str(self._safe(lambda z=zone: z.household_id, "unknown") or "unknown")
            by_household[household_id].append(zone)

        household_models: list[dict[str, Any]] = []
        all_group_models: list[dict[str, Any]] = []
        group_objects: dict[str, tuple[str, Any]] = {}

        for household_id, household_zones in sorted(by_household.items()):
            representative = household_zones[0]
            groups = self._safe(lambda z=representative: list(z.all_groups), []) or []
            room_models = [self._room_model(zone) for zone in household_zones]
            logical_uids = {room["uid"] for room in room_models}
            room_models.sort(key=lambda room: room["name"].lower())
            group_models: list[dict[str, Any]] = []
            for group in groups:
                model = self._group_model(group, logical_uids)
                if not model["memberUids"]:
                    continue
                group_models.append(model)
                all_group_models.append({**model, "householdId": household_id})
                group_objects[model["uid"]] = (household_id, group)
            group_models.sort(key=lambda group: group["label"].lower())
            for room in room_models:
                room["playbackState"] = "STOPPED"
                for group in group_models:
                    if room["uid"] in group["memberUids"]:
                        room["playbackState"] = group["playbackState"]
                        break
            household_models.append(
                {
                    "id": household_id,
                    "rooms": room_models,
                    "groups": group_models,
                }
            )

        target_model = choose_target_group(all_group_models, self.state.selected_room_uid)
        target: dict[str, Any] | None = None
        playback = self._empty_snapshot()["playback"]
        self._target_group = None
        self._target_household_id = ""

        if target_model is not None:
            target_uid = target_model["uid"]
            household_id, target_group_obj = group_objects[target_uid]
            self._target_group = target_group_obj
            self._target_household_id = household_id
            coordinator = target_group_obj.coordinator
            playback = self._playback_model(
                coordinator,
                state_hint=target_model["playbackState"],
            )
            target = {
                "householdId": household_id,
                "groupUid": target_uid,
                "coordinatorUid": target_model["coordinatorUid"],
                "roomLabel": target_model["label"],
                "memberUids": target_model["memberUids"],
                "volume": target_model["volume"],
                "mute": target_model["mute"],
            }

            # Persist a stable room identity, not a transient group/coordinator id.
            member_uids = target_model["memberUids"]
            if self.state.selected_room_uid not in member_uids and member_uids:
                self.state.selected_room_uid = member_uids[0]
                self._save_state_quietly()

            if self._favorites_household_id != household_id:
                self._favorites_loaded = False
            if not self._favorites_loaded:
                self.refresh_favorites()

        self._last_snapshot = {
            "type": "snapshot",
            "version": 1,
            "status": {
                "state": "ready",
                "message": "",
                "lastRefreshEpochMs": int(time.time() * 1000),
                "discovery": dict(self._discovery_diagnostics),
                "playbackDegraded": bool(playback.get("stale", False)),
            },
            "selectedAnchorRoomUid": self.state.selected_room_uid,
            "targetGroupUid": target["groupUid"] if target else "",
            "households": household_models,
            "target": target,
            "favorites": dict(self._favorites_model),
            "playback": playback,
        }
        return self._last_snapshot

    def _room_model(self, zone: Any) -> dict[str, Any]:
        return {
            "uid": self._zone_uid(zone),
            "name": self._zone_name(zone),
            "ip": str(getattr(zone, "ip_address", "") or ""),
            "online": True,
            "lineInAvailable": self._line_in_available.get(self._zone_uid(zone), False),
            "volume": clamp_volume(self._safe(lambda z=zone: z.volume, 0)),
            "mute": bool(self._safe(lambda z=zone: z.mute, False)),
        }

    def _transport_state(self, coordinator: Any) -> tuple[str, bool]:
        uid = self._zone_uid(coordinator)
        ok, transport = self._query_with_retry(
            f"transport for {uid or 'unknown coordinator'}",
            lambda: coordinator.get_current_transport_info(),
            {},
        )
        if ok and isinstance(transport, dict):
            state = str(transport.get("current_transport_state", "") or "").upper()
            if state:
                self._transport_state_cache[uid] = state
                return state, True
        cached = self._transport_state_cache.get(uid, "UNKNOWN")
        return cached, False

    def _group_model(
        self,
        group: Any,
        logical_uids: set[str] | None = None,
    ) -> dict[str, Any]:
        coordinator = group.coordinator
        members = sorted(
            [
                member
                for member in group.members
                if logical_uids is None or self._zone_uid(member) in logical_uids
            ],
            key=lambda member: (self._zone_name(member).lower(), self._zone_uid(member)),
        )
        member_uids = [self._zone_uid(member) for member in members]
        names = [self._zone_name(member) for member in members]
        state, _ = self._transport_state(coordinator)
        group_uid = self._zone_uid(coordinator)
        return {
            "uid": group_uid,
            "coordinatorUid": group_uid,
            "memberUids": member_uids,
            "label": group_label(names),
            "volume": clamp_volume(self._safe(lambda g=group: g.volume, 0)),
            "mute": bool(self._safe(lambda g=group: g.mute, False)),
            "playbackState": state,
        }

    @staticmethod
    def _media_metadata(response: Any) -> dict[str, str]:
        """Extract station/container metadata omitted by track-position info."""
        if not isinstance(response, dict):
            return {"title": "", "artworkUrl": "", "uri": ""}
        result = {
            "title": "",
            "artworkUrl": "",
            "uri": str(response.get("CurrentURI", "") or ""),
        }
        raw = str(response.get("CurrentURIMetaData", "") or "")
        if not raw or raw == "NOT_IMPLEMENTED":
            return result
        try:
            metadata = safe_xml_fromstring(raw)
        except (ET.ParseError, DefusedXmlException) as exc:
            LOG.debug("Could not parse Sonos media metadata: %s", exc)
            return result
        result["title"] = str(metadata.findtext(".//{http://purl.org/dc/elements/1.1/}title") or "")
        result["artworkUrl"] = str(
            metadata.findtext(".//{urn:schemas-upnp-org:metadata-1-0/upnp/}albumArtURI") or ""
        )
        return result

    def _playback_model(
        self,
        coordinator: Any,
        *,
        state_hint: str = "UNKNOWN",
    ) -> dict[str, Any]:
        uid = self._zone_uid(coordinator)
        cached = self._playback_cache.get(uid, {})
        track_ok, track = self._query_with_retry(
            f"track metadata for {uid or 'unknown coordinator'}",
            lambda: coordinator.get_current_track_info(),
            {},
        )
        if not isinstance(track, dict):
            track_ok = False
            track = {}

        state, transport_ok = self._transport_state(coordinator)
        if state == "UNKNOWN" and state_hint:
            state = str(state_hint).upper()

        media_ok, media_response = self._query_with_retry(
            f"media metadata for {uid or 'unknown coordinator'}",
            lambda: coordinator.avTransport.GetMediaInfo([("InstanceID", 0)]),
            {},
        )
        media = (
            self._media_metadata(media_response)
            if media_ok
            else {
                "title": "",
                "artworkUrl": "",
                "uri": "",
            }
        )

        actions = self._safe(lambda: coordinator.available_actions, []) or []
        source = str(
            self._safe(lambda: coordinator.music_source, cached.get("source", "UNKNOWN"))
            or cached.get("source", "UNKNOWN")
            or "UNKNOWN"
        )
        coordinator_ip = getattr(coordinator, "ip_address", "")
        track_artwork = self._available_artwork_url(
            self._safe_artwork_url(
                track.get("album_art", ""),
                coordinator_ip,
            )
        )
        station_artwork = self._available_artwork_url(
            self._safe_artwork_url(
                media["artworkUrl"],
                coordinator_ip,
            )
        )
        artwork = track_artwork or station_artwork
        artwork_kind = "track" if track_artwork else ("station" if station_artwork else "")

        track_title = str(track.get("title", "") or "")
        media_title = str(media["title"] or "")
        # Direct podcast streams can expose a shortened title through
        # GetPositionInfo while retaining the complete title in media metadata.
        title = track_title or media_title
        if media_title and track_title and media_title.startswith(track_title):
            title = media_title
        if source.upper() == "TV" and title == uid:
            title = "TV"

        model: dict[str, Any] = {
            "state": state,
            "title": title,
            "artist": str(track.get("artist", "") or ""),
            "album": str(track.get("album", "") or ""),
            "artworkUrl": artwork,
            "artworkKind": artwork_kind,
            "source": source,
            "positionSec": parse_sonos_time(track.get("position")),
            "durationSec": parse_sonos_time(track.get("duration")),
            "availableActions": sorted({str(action) for action in actions}),
            "metadataState": "fresh",
            "stale": not transport_ok or not track_ok,
        }

        active = state in {"PLAYING", "PAUSED_PLAYBACK", "TRANSITIONING"}
        used_cached_metadata = False
        if active and cached and (not track_ok or not media_ok):
            for key in ("title", "artist", "album", "artworkUrl", "artworkKind"):
                if not model[key] and cached.get(key):
                    model[key] = cached[key]
                    used_cached_metadata = True
            if model["positionSec"] is None and not track_ok:
                model["positionSec"] = cached.get("positionSec")
            if model["durationSec"] is None and not track_ok:
                model["durationSec"] = cached.get("durationSec")
            if not model["availableActions"]:
                model["availableActions"] = list(cached.get("availableActions", []))

        if active:
            if used_cached_metadata:
                model["metadataState"] = "cached"
            elif not model["title"] and not model["artist"] and not model["artworkUrl"]:
                model["metadataState"] = "unavailable"
            self._playback_cache[uid] = dict(model)
        elif state == "STOPPED" and transport_ok:
            # A confirmed stop must not display a previous session's track.
            self._playback_cache.pop(uid, None)
            model.update(
                {
                    "title": "",
                    "artist": "",
                    "album": "",
                    "artworkUrl": "",
                    "artworkKind": "",
                    "positionSec": None,
                    "durationSec": None,
                    "metadataState": "empty",
                    "stale": False,
                }
            )
        elif cached:
            # If transport itself is unreachable, retain the last confirmed
            # session instead of manufacturing a STOPPED/blank snapshot.
            preserved = dict(cached)
            preserved["stale"] = True
            preserved["metadataState"] = "cached"
            return preserved

        return model
