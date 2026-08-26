from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .content import content_service
from .mixer import mixer_service
from .playback import playback_service
from .ports import SonarchyBackendPort
from .topology import topology_service


class SonarchyApplication:
    """Compose domain services while the protocol owns only wire concerns."""

    def __init__(self, backend: SonarchyBackendPort) -> None:
        self.backend = backend
        self.services = (
            playback_service(backend),
            content_service(backend),
            topology_service(backend),
            mixer_service(backend),
        )
        operations = [operation for service in self.services for operation in service.operations]
        if len(operations) != len(set(operations)):
            raise RuntimeError("A protocol operation has more than one domain owner")
        self.operations = frozenset(operations)

    def execute(self, operation: str, args: dict[str, Any]) -> bool:
        return any(service.execute(operation, args) for service in self.services)

    def refresh(self, *, rediscover: bool = True) -> dict[str, Any]:
        return self.backend.refresh(rediscover=rediscover)

    def event_services(self) -> dict[str, Any]:
        return self.backend.event_services()

    def refresh_event_topologies(self, household_ids: Iterable[str]) -> None:
        self.backend.refresh_event_topologies(household_ids)
