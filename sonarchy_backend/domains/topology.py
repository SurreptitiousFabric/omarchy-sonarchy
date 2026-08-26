from __future__ import annotations

from .common import DomainService, string_arg, string_list_arg
from .ports import TopologyPort


def topology_service(backend: TopologyPort) -> DomainService:
    return DomainService(
        {
            "selection.group.set": lambda args: backend.select_group(string_arg(args, "groupUid")),
            "selection.room.set": lambda args: backend.select_room(string_arg(args, "roomUid")),
            "topology.members.set": lambda args: backend.apply_members(
                string_list_arg(args, "roomUids")
            ),
        }
    )
