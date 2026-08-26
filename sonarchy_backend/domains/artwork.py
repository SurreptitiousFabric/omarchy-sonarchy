from __future__ import annotations

from ..apple_catalog import resolve_apple_artwork
from .common import DomainService, string_arg


def artwork_service() -> DomainService:
    return DomainService(
        {
            "artwork.radio.resolve": lambda args: resolve_apple_artwork(
                string_arg(args, "title"), string_arg(args, "artist")
            )
        },
        mutates=False,
    )
