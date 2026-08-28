from __future__ import annotations

import re
from typing import Any

PLAYLIST_TRANSACTION_PHASES = frozenset(
    {
        "queue_clear",
        "queue_construction",
        "queue_verification",
        "playlist_creation",
        "playlist_verification",
        "queue_restoration",
        "playback_start",
        "playback_verification",
    }
)
QUEUE_CONSTRUCTION_STEPS = frozenset(
    {"share_link_initialization", "enqueue", "position_decode", "position_verify"}
)
ROLLBACK_QUEUE_STEPS = frozenset({"clear", "readd", "position_select", "verification"})
ROLLBACK_VERIFICATION_REASONS = frozenset(
    {
        "queue_read",
        "item_count",
        "resources",
        "metadata",
        "queue_active",
        "position",
        "transport",
        "source",
        "media",
    }
)
CANONICAL_SONG_PATTERN = re.compile(r"song:[1-9]\d{0,19}")
SONOS_ERROR_CODE_PATTERN = re.compile(r"(?:\d{1,6}|[A-Z][A-Z0-9_]{0,31})")


class SafeDomainError(Exception):
    """A request-owned error whose public fields are deliberately bounded."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})
        self.retryable = retryable


class PlanConflictError(SafeDomainError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__("conflict", message, details=details)


def _bounded_playlist_diagnostics(value: dict[str, Any] | None) -> dict[str, Any]:
    diagnostics = dict(value or {})
    result: dict[str, Any] = {}
    step = diagnostics.get("queueConstructionStep")
    if step in QUEUE_CONSTRUCTION_STEPS:
        result["queueConstructionStep"] = step
    position = diagnostics.get("failedTrackPosition")
    if isinstance(position, int) and not isinstance(position, bool) and 1 <= position <= 25:
        result["failedTrackPosition"] = position
    identity = diagnostics.get("failedCanonicalIdentity")
    if isinstance(identity, str) and CANONICAL_SONG_PATTERN.fullmatch(identity):
        result["failedCanonicalIdentity"] = identity
    error_code = diagnostics.get("sonosErrorCode")
    if isinstance(error_code, str) and SONOS_ERROR_CODE_PATTERN.fullmatch(error_code):
        result["sonosErrorCode"] = error_code
    return result


def _bounded_rollback(value: dict[str, Any]) -> dict[str, Any]:
    rollback = {
        key: value.get(key) is True
        for key in (
            "attempted",
            "playlistRemoved",
            "playlistCleanupRequired",
            "queueRestored",
            "environmentUnchanged",
            "succeeded",
        )
    }
    step = value.get("rollbackQueueStep")
    if step in ROLLBACK_QUEUE_STEPS:
        rollback["rollbackQueueStep"] = step
    position = value.get("rollbackFailedItemPosition")
    if isinstance(position, int) and not isinstance(position, bool) and 1 <= position <= 100:
        rollback["rollbackFailedItemPosition"] = position
    reason = value.get("rollbackVerificationReason")
    if reason in ROLLBACK_VERIFICATION_REASONS:
        rollback["rollbackVerificationReason"] = reason
    return rollback


class PlaylistTransactionError(SafeDomainError):
    def __init__(
        self,
        *,
        phase: str,
        rollback: dict[str, Any],
        diagnostics: dict[str, Any] | None = None,
    ) -> None:
        safe_rollback = _bounded_rollback(rollback)
        restored = safe_rollback["succeeded"]
        message = (
            "Sonos could not complete the playlist operation; the previous state was restored"
            if restored
            else "Sonos could not complete the playlist operation and restoration was not verified"
        )
        details: dict[str, Any] = {
            "phase": phase if phase in PLAYLIST_TRANSACTION_PHASES else "queue_construction",
            "rollback": safe_rollback,
        }
        details.update(_bounded_playlist_diagnostics(diagnostics))
        super().__init__(
            "speaker_rejected",
            message,
            details=details,
        )
