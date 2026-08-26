from __future__ import annotations

from .common import DomainService, number_arg, string_arg
from .ports import PlaybackPort


def playback_service(backend: PlaybackPort) -> DomainService:
    return DomainService(
        {
            "playback.toggle": lambda _args: backend.play_pause(),
            "playback.play": lambda _args: backend.play(),
            "playback.pause": lambda _args: backend.pause(),
            "playback.next": lambda _args: backend.next(),
            "playback.previous": lambda _args: backend.previous(),
            "playback.seek": lambda args: backend.seek(number_arg(args, "positionSec")),
            "playback.room.move": lambda args: backend.move_playback_to_room(
                string_arg(args, "roomUid")
            ),
        }
    )
