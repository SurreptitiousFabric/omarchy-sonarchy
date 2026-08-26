from __future__ import annotations

from .common import DomainService, bool_arg, number_arg, string_arg
from .ports import MixerPort


def mixer_service(backend: MixerPort) -> DomainService:
    return DomainService(
        {
            "volume.group.set": lambda args: backend.set_group_volume(number_arg(args, "volume")),
            "volume.group.adjust": lambda args: backend.adjust_group_volume(
                number_arg(args, "delta")
            ),
            "mute.group.set": lambda args: backend.set_group_mute(bool_arg(args, "mute")),
            "volume.room.set": lambda args: backend.set_room_volume(
                string_arg(args, "roomUid"), number_arg(args, "volume")
            ),
            "volume.room.adjust": lambda args: backend.adjust_room_volume(
                string_arg(args, "roomUid"), number_arg(args, "delta")
            ),
            "mute.room.set": lambda args: backend.set_room_mute(
                string_arg(args, "roomUid"), bool_arg(args, "mute")
            ),
        }
    )
