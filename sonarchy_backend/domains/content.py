from __future__ import annotations

from .common import DomainService, string_arg
from .ports import ContentPort


def content_service(backend: ContentPort) -> DomainService:
    return DomainService(
        {
            "content.favorite.play": lambda args: backend.play_favorite(
                string_arg(args, "favoriteId")
            ),
            "content.favorites.refresh": lambda _args: backend.refresh_favorites(),
        }
    )
