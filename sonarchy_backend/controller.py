from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .controller_common import NETWORK_SCAN_RETRY_SEC
from .controller_common import ControllerError as ControllerError
from .controller_discovery import DiscoveryMixin
from .controller_facade import DomainFacadeMixin
from .controller_favorites import FavoritesMixin
from .controller_playback import PlaybackMixin
from .controller_snapshot import SnapshotMixin
from .controller_topology import TopologyMixin
from .state import PersistentState


class SonosController(
    DiscoveryMixin,
    FavoritesMixin,
    SnapshotMixin,
    TopologyMixin,
    DomainFacadeMixin,
    PlaybackMixin,
):
    """Authoritative local Sonos state and serialized command execution."""

    def __init__(
        self,
        *,
        discover_fn: Callable[..., Any] | None = None,
        soco_factory: Callable[[str], Any] | None = None,
        network_scan_fn: Callable[..., Any] | None = None,
        persistent_state: PersistentState | None = None,
    ) -> None:
        self._discover_fn = discover_fn
        self._soco_factory = soco_factory
        self._network_scan_fn = network_scan_fn
        self.state = persistent_state or PersistentState.load()
        self._zones: dict[str, Any] = {}
        self._target_group: Any | None = None
        self._target_household_id = ""
        self._last_snapshot: dict[str, Any] = self._empty_snapshot("discovering")
        self._backend_error = ""
        self._last_network_scan_monotonic = -NETWORK_SCAN_RETRY_SEC
        self._discovery_diagnostics: dict[str, Any] = {}
        self._favorite_objects: dict[str, dict[str, Any]] = {}
        self._favorites_model: dict[str, Any] = {
            "state": "not_loaded",
            "items": [],
            "total": 0,
            "unsupported": 0,
            "error": "",
        }
        self._favorites_loaded = False
        self._favorites_household_id = ""
        self._transport_state_cache: dict[str, str] = {}
        self._playback_cache: dict[str, dict[str, Any]] = {}
