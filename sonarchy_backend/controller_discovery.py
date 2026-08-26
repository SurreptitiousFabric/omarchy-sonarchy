from __future__ import annotations

import ipaddress
import logging
import time
import unicodedata
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from .controller_common import (
    NETWORK_SCAN_MAX_THREADS,
    NETWORK_SCAN_MIN_NETMASK,
    NETWORK_SCAN_RETRY_SEC,
    NETWORK_SCAN_TIMEOUT_SEC,
    PLAYBACK_QUERY_ATTEMPTS,
    PLAYBACK_QUERY_RETRY_SEC,
    SSDP_DISCOVERY_TIMEOUT_SEC,
    ControllerError,
)

LOG = logging.getLogger(__name__)


class DiscoveryMixin:
    @staticmethod
    def _empty_snapshot(status: str = "offline", message: str = "") -> dict[str, Any]:
        return {
            "type": "snapshot",
            "version": 1,
            "status": {
                "state": status,
                "message": message,
                "lastRefreshEpochMs": int(time.time() * 1000),
            },
            "selectedAnchorRoomUid": "",
            "targetGroupUid": "",
            "households": [],
            "target": None,
            "favorites": {
                "state": "not_loaded",
                "items": [],
                "total": 0,
                "unsupported": 0,
                "error": "",
            },
            "playback": {
                "state": "STOPPED",
                "title": "",
                "artist": "",
                "album": "",
                "artworkUrl": "",
                "artworkKind": "",
                "source": "UNKNOWN",
                "positionSec": None,
                "durationSec": None,
                "availableActions": [],
                "metadataState": "empty",
                "stale": False,
            },
        }

    def _ensure_soco(
        self,
    ) -> tuple[Callable[..., Any], Callable[[str], Any], Callable[..., Any]]:
        if (
            self._discover_fn is not None
            and self._soco_factory is not None
            and self._network_scan_fn is not None
        ):
            return self._discover_fn, self._soco_factory, self._network_scan_fn
        try:
            import soco
            from soco.discovery import scan_network
        except ImportError as exc:  # pragma: no cover - bootstrap owns this in prod
            raise ControllerError("SoCo is not installed") from exc
        self._discover_fn = self._discover_fn or soco.discover
        self._soco_factory = self._soco_factory or soco.SoCo
        self._network_scan_fn = self._network_scan_fn or scan_network
        return self._discover_fn, self._soco_factory, self._network_scan_fn

    @staticmethod
    def _safe(call: Callable[[], Any], default: Any = None) -> Any:
        try:
            return call()
        except Exception as exc:  # noqa: BLE001 - network devices fail in many ways
            LOG.debug("Sonos query failed: %s", exc)
            return default

    @staticmethod
    def _query_with_retry(
        label: str,
        call: Callable[[], Any],
        default: Any,
    ) -> tuple[bool, Any]:
        """Distinguish a real empty Sonos response from a network failure."""
        for attempt in range(PLAYBACK_QUERY_ATTEMPTS):
            try:
                return True, call()
            except Exception as exc:  # noqa: BLE001 - LAN devices fail transiently
                LOG.debug(
                    "Sonos %s query failed (%s/%s): %s",
                    label,
                    attempt + 1,
                    PLAYBACK_QUERY_ATTEMPTS,
                    exc,
                )
                if attempt + 1 < PLAYBACK_QUERY_ATTEMPTS:
                    time.sleep(PLAYBACK_QUERY_RETRY_SEC)
        return False, default

    @staticmethod
    def _zone_uid(zone: Any) -> str:
        return str(getattr(zone, "uid", "") or "")

    @staticmethod
    def _clean_name(value: Any, fallback: str) -> str:
        name = str(value or fallback)
        # Some Sonos room names arrive with a leading variation selector or
        # zero-width formatting mark. It renders as indentation in QML even
        # though there is no visible glyph.
        while name and (name[0].isspace() or unicodedata.category(name[0]) in {"Cf", "Mn", "Me"}):
            name = name[1:]
        return name or fallback

    @classmethod
    def _zone_name(cls, zone: Any) -> str:
        return cls._clean_name(getattr(zone, "player_name", ""), "Sonos")

    @staticmethod
    def _local_ipv4(value: Any) -> str:
        """Return a safe LAN IPv4 address or an empty string.

        Cached state is writable by the desktop user, so it must never turn
        into a way to make the backend connect to arbitrary internet hosts.
        Discovery results are checked too as a defense-in-depth measure.
        """
        try:
            address = ipaddress.ip_address(str(value or ""))
        except ValueError:
            return ""
        if (
            address.version != 4
            or not address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_unspecified
            or address.is_reserved
        ):
            return ""
        return str(address)

    @classmethod
    def _safe_artwork_url(cls, value: Any, coordinator_ip: Any) -> str:
        """Allow speaker-local artwork and HTTPS from reviewed media hosts."""
        raw = str(value or "").strip()
        local_ip = cls._local_ipv4(coordinator_ip)
        if not raw:
            return ""
        if raw.startswith("/") and local_ip:
            return f"http://{local_ip}:1400{raw}"

        parsed = urlsplit(raw)
        if parsed.username or parsed.password or not parsed.hostname:
            return ""
        try:
            port = parsed.port
        except ValueError:
            return ""
        if parsed.scheme == "http":
            return raw if local_ip and parsed.hostname == local_ip and port in (None, 1400) else ""
        if parsed.scheme != "https" or port not in (None, 443):
            return ""
        try:
            ipaddress.ip_address(parsed.hostname)
        except ValueError:
            hostname = parsed.hostname.casefold().rstrip(".")
            if hostname == "localhost" or hostname.endswith((".local", ".internal")):
                return ""
            trusted_suffixes = (
                ".mzstatic.com",
                ".scdn.co",
                ".tunein.com",
                ".radiotime.com",
                ".globalplayer.com",
                ".thisisglobal.com",
                ".radioplayer.cloud",
            )
            trusted_hosts = ("static.mytuner-radio.net",)
            return (
                raw
                if hostname in trusted_hosts
                or any(
                    hostname == suffix.removeprefix(".") or hostname.endswith(suffix)
                    for suffix in trusted_suffixes
                )
                else ""
            )
        # Literal remote addresses are never required for the reviewed media
        # providers and would bypass the hostname allowlist.
        return ""

    def _discover_zones(self) -> list[Any]:
        discover, factory, scan_network = self._ensure_soco()
        found: dict[str, Any] = {}
        errors: list[str] = []
        cached_hosts = [host for host in self.state.cached_hosts if self._local_ipv4(host)]
        if cached_hosts != self.state.cached_hosts:
            self.state.cached_hosts = cached_hosts
            self._save_state_quietly()
        cached_hosts_tried = len(cached_hosts)
        cached_found = 0
        ssdp_found = 0
        scan_found = 0
        scan_attempted = False
        attempts: list[dict[str, Any]] = []

        # Cached addresses make cold starts useful even when SSDP is flaky.
        for host in cached_hosts:
            try:
                zone = factory(host)
                uid = self._safe(lambda z=zone: z.uid, "")
                if uid:
                    found[str(uid)] = zone
                    cached_found += 1
                    attempts.append({"method": "cache", "target": host, "result": "found"})
                else:
                    attempts.append({"method": "cache", "target": host, "result": "no-response"})
            except Exception as exc:  # noqa: BLE001
                LOG.debug("Cached Sonos host %s unavailable: %s", host, exc)
                errors.append(f"cached {host}: {type(exc).__name__}")
                attempts.append(
                    {
                        "method": "cache",
                        "target": host,
                        "result": "error",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

        # A successful cached speaker exposes the household's current
        # ``visible_zones``, including topology changes and newly added rooms.
        # Do not stack a five-second SSDP wait onto every poll and command when
        # that direct path is healthy. SSDP remains the recovery path when all
        # cached addresses miss (including a first run with an empty cache).
        if found:
            discovered = set()
            attempts.append(
                {
                    "method": "ssdp",
                    "result": "skipped",
                    "reason": "cache-found",
                }
            )
        else:
            # SoCo's own default is five seconds. Keep that full window for
            # recovery on real Wi-Fi and multi-interface machines.
            try:
                discovered = discover(timeout=SSDP_DISCOVERY_TIMEOUT_SEC) or set()
            except Exception as exc:  # noqa: BLE001
                LOG.warning("Sonos discovery failed: %s", exc)
                errors.append(f"ssdp: {type(exc).__name__}: {exc}")
                discovered = set()
                attempts.append(
                    {
                        "method": "ssdp",
                        "result": "error",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
            else:
                attempts.append(
                    {
                        "method": "ssdp",
                        "result": "complete",
                        "found": len(discovered),
                    }
                )

        for zone in discovered:
            uid = self._zone_uid(zone)
            if uid and self._local_ipv4(getattr(zone, "ip_address", "")):
                found[uid] = zone
                ssdp_found += 1

        # SSDP is UDP multicast and can be filtered by AP isolation, VLANs,
        # firewalls, or a quirky interface route. SoCo ships an explicit
        # attached-network scanner for this situation. Run it only when cache
        # and SSDP both miss, and rate-limit retries so an offline household
        # does not cause a /24 scan every polling tick.
        now = time.monotonic()
        scan_due = now - self._last_network_scan_monotonic >= NETWORK_SCAN_RETRY_SEC
        if not found and scan_due:
            scan_attempted = True
            self._last_network_scan_monotonic = now
            try:
                scanned = (
                    scan_network(
                        multi_household=True,
                        scan_timeout=NETWORK_SCAN_TIMEOUT_SEC,
                        min_netmask=NETWORK_SCAN_MIN_NETMASK,
                        max_threads=NETWORK_SCAN_MAX_THREADS,
                    )
                    or set()
                )
            except Exception as exc:  # noqa: BLE001
                LOG.warning("Sonos network-scan fallback failed: %s", exc)
                errors.append(f"network_scan: {type(exc).__name__}: {exc}")
                scanned = set()
                attempts.append(
                    {
                        "method": "network-scan",
                        "result": "error",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
            else:
                attempts.append(
                    {
                        "method": "network-scan",
                        "result": "complete",
                        "found": len(scanned),
                    }
                )

            for zone in scanned:
                uid = self._zone_uid(zone)
                if uid and self._local_ipv4(getattr(zone, "ip_address", "")):
                    found[uid] = zone
                    scan_found += 1
        elif found:
            attempts.append(
                {"method": "network-scan", "result": "skipped", "reason": "already-found"}
            )
        else:
            attempts.append(
                {"method": "network-scan", "result": "skipped", "reason": "rate-limited"}
            )

        zones = list(found.values())
        hosts = sorted(
            set(self.state.cached_hosts)
            | {
                self._local_ipv4(getattr(zone, "ip_address", ""))
                for zone in zones
                if self._local_ipv4(getattr(zone, "ip_address", ""))
            }
        )
        if hosts != self.state.cached_hosts:
            self.state.cached_hosts = hosts
            self._save_state_quietly()

        self._discovery_diagnostics = {
            "cachedHostsTried": cached_hosts_tried,
            "cachedHostsFound": cached_found,
            "ssdpTimeoutSec": SSDP_DISCOVERY_TIMEOUT_SEC,
            "ssdpFound": ssdp_found,
            "networkScanAttempted": scan_attempted,
            "networkScanFound": scan_found,
            "networkScanRetrySec": NETWORK_SCAN_RETRY_SEC,
            "attempts": attempts,
            "errors": errors,
        }
        return zones

    def _save_state_quietly(self) -> None:
        try:
            self.state.save()
        except OSError as exc:
            LOG.warning("Could not persist Sonos state: %s", exc)

    def event_services(self) -> dict[str, Any]:
        """Return stable event-service identities for the current topology."""
        if not self._zones:
            return {}
        services: dict[str, Any] = {}
        household_representatives: dict[str, Any] = {}
        for zone in self._zones.values():
            household_id = str(self._safe(lambda z=zone: z.household_id, "unknown") or "unknown")
            household_representatives.setdefault(household_id, zone)
        for household_id, representative in household_representatives.items():
            topology = getattr(representative, "zoneGroupTopology", None)
            if topology is not None:
                services[f"topology:{household_id}"] = topology
        if self._target_group is not None:
            coordinator = self._target_group.coordinator
            group_rendering = getattr(coordinator, "groupRenderingControl", None)
            if group_rendering is not None:
                services[f"group-volume:{self._zone_uid(coordinator)}"] = group_rendering

        # Playback indicators cover every room, including independent sessions
        # outside the selected group. Subscribe once per group coordinator so
        # those indicators update immediately on play/pause transitions.
        transport_coordinators: set[str] = set()
        for zone in self._zones.values():
            group = self._safe(lambda z=zone: z.group, None)
            coordinator = getattr(group, "coordinator", None)
            uid = self._zone_uid(coordinator)
            if not uid or uid in transport_coordinators:
                continue
            transport_coordinators.add(uid)
            transport = getattr(coordinator, "avTransport", None)
            if transport is not None:
                services[f"transport:{uid}"] = transport
        for uid, zone in self._zones.items():
            rendering = getattr(zone, "renderingControl", None)
            if rendering is not None:
                services[f"room-volume:{uid}"] = rendering
        return services
