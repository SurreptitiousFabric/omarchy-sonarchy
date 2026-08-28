from __future__ import annotations

from typing import Any


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


class PlaylistTransactionError(SafeDomainError):
    def __init__(self, *, phase: str, rollback: dict[str, Any]) -> None:
        restored = rollback.get("succeeded") is True
        message = (
            "Sonos could not complete the playlist operation; the previous state was restored"
            if restored
            else "Sonos could not complete the playlist operation and restoration was not verified"
        )
        super().__init__(
            "speaker_rejected",
            message,
            details={"phase": phase, "rollback": rollback},
        )
