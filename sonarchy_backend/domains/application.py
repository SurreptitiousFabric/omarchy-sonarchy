from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from .alarms import alarm_mutations_service, alarms_service
from .apple_playlist_plan import ApplePlaylistPlanService
from .artwork import artwork_service
from .browse import browse_service
from .common import RequestContext
from .content import content_service
from .devices import devices_service
from .mixer import mixer_service
from .playback import playback_service
from .playlists import playlists_service
from .ports import SonarchyBackendPort
from .queue import queue_service
from .settings import settings_service
from .topology import topology_service


class SonarchyApplication:
    """Compose domain services while the protocol owns only wire concerns."""

    def __init__(self, backend: SonarchyBackendPort) -> None:
        self.backend = backend
        apple_playlist_services = ApplePlaylistPlanService(backend).services()
        self.services = (
            playback_service(backend),
            content_service(backend),
            topology_service(backend),
            mixer_service(backend),
            devices_service(backend),
            artwork_service(),
            browse_service(backend),
            alarms_service(backend),
            alarm_mutations_service(backend),
            settings_service(backend),
            queue_service(backend),
            playlists_service(backend),
            *apple_playlist_services,
        )
        operations = [operation for service in self.services for operation in service.operations]
        if len(operations) != len(set(operations)):
            raise RuntimeError("A protocol operation has more than one domain owner")
        self.operations = frozenset(operations)
        self.mutating_operations = frozenset(
            operation
            for service in self.services
            if service.mutates
            for operation in service.operations
        )
        self.conditional_mutating_operations = frozenset(
            operation
            for service in self.services
            if service.mutates and service.conditional_mutation
            for operation in service.operations
        )

    def execute(
        self,
        operation: str,
        args: dict[str, Any],
        *,
        backend_revision: int = 0,
        mutation_started_callback: Callable[[], None] | None = None,
    ) -> Any:
        context = RequestContext(
            backend_revision=backend_revision,
            mutation_started_callback=mutation_started_callback,
        )
        for service in self.services:
            if operation in service.operations:
                return service.execute(operation, args, context)
        raise KeyError(operation)

    def mutates(self, operation: str) -> bool:
        return operation in self.mutating_operations

    def mutation_is_conditional(self, operation: str) -> bool:
        return operation in self.conditional_mutating_operations

    def refresh(self, *, rediscover: bool = True) -> dict[str, Any]:
        return self.backend.refresh(rediscover=rediscover)

    def event_services(self) -> dict[str, Any]:
        return self.backend.event_services()

    def refresh_event_topologies(self, household_ids: Iterable[str]) -> None:
        self.backend.refresh_event_topologies(household_ids)
