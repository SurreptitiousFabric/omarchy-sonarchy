from __future__ import annotations

import re
from typing import Any

PLAYLIST_CONSTRUCTION_STEPS = frozenset(
    {"create", "add_track", "verify_track", "verify_playlist", "cleanup"}
)
CANONICAL_SONG_PATTERN = re.compile(r"song:[1-9]\d{0,19}")
SONOS_PLAYLIST_ID_PATTERN = re.compile(r"SQ:\d+")
SONOS_ERROR_CODE_PATTERN = re.compile(r"(?:\d{1,6}|[A-Z][A-Z0-9_]{0,31})")
PLAYLIST_PLAY_PHASES = frozenset(
    {
        "preflight_revalidation",
        "append_playlist",
        "start_playback",
        "verify_queue",
        "verify_playback",
    }
)
SAFE_FINGERPRINT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")


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


def _bounded_playlist_failure(value: dict[str, Any]) -> dict[str, Any]:
    details: dict[str, Any] = {
        key: value.get(key) is True
        for key in (
            "playlistRemoved",
            "playlistCleanupRequired",
            "preExistingPlaylistsUnchanged",
            "queueUnchanged",
            "playbackUnchanged",
            "succeeded",
        )
    }
    step = value.get("playlistConstructionStep")
    details["playlistConstructionStep"] = step if step in PLAYLIST_CONSTRUCTION_STEPS else "create"
    position = value.get("failedTrackPosition")
    if isinstance(position, int) and not isinstance(position, bool) and 1 <= position <= 25:
        details["failedTrackPosition"] = position
    identity = value.get("failedCanonicalIdentity")
    if isinstance(identity, str) and CANONICAL_SONG_PATTERN.fullmatch(identity):
        details["failedCanonicalIdentity"] = identity
    error_code = value.get("sonosErrorCode")
    if isinstance(error_code, str) and SONOS_ERROR_CODE_PATTERN.fullmatch(error_code):
        details["sonosErrorCode"] = error_code
    playlist_id = value.get("partialPlaylistId")
    if isinstance(playlist_id, str) and SONOS_PLAYLIST_ID_PATTERN.fullmatch(playlist_id):
        details["partialPlaylistId"] = playlist_id
    return details


class PlaylistTransactionError(SafeDomainError):
    def __init__(self, *, phase: str, diagnostics: dict[str, Any]) -> None:
        details = {
            "phase": "playlist_creation" if phase != "playlist_creation" else phase,
            **_bounded_playlist_failure(diagnostics),
        }
        message = (
            "Sonos rejected the playlist operation; the exact partial playlist was removed"
            if details["playlistRemoved"] and not details["playlistCleanupRequired"]
            else "Sonos rejected the playlist operation; exact playlist cleanup may be required"
        )
        super().__init__("speaker_rejected", message, details=details)


def bounded_playlist_play_failure(value: dict[str, Any]) -> dict[str, Any]:
    details: dict[str, Any] = {
        key: value.get(key) is True
        for key in (
            "queueAppended",
            "playbackStarted",
            "queueRollbackAttempted",
            "succeeded",
        )
    }
    for key in ("appendInvocationCount", "playbackStartInvocationCount", "retryCount"):
        count = value.get(key)
        details[key] = count if type(count) is int and 0 <= count <= 1 else 0
    for key in (
        "expectedFirstAppendedPosition",
        "observedQueueLength",
        "observedCurrentPosition",
    ):
        position = value.get(key)
        if type(position) is int and 0 <= position <= 100:
            details[key] = position
    fingerprint = value.get("observedQueueFingerprint")
    if isinstance(fingerprint, str) and SAFE_FINGERPRINT_PATTERN.fullmatch(fingerprint):
        details["observedQueueFingerprint"] = fingerprint
    transport = value.get("observedTransport")
    if transport in {"STOPPED", "PAUSED_PLAYBACK", "PLAYING", "TRANSITIONING", "UNKNOWN"}:
        details["observedTransport"] = transport
    source = value.get("observedSource")
    if source in {"QUEUE", "NONE", "UNSUPPORTED", "UNKNOWN"}:
        details["observedSource"] = source
    return details


class PlaylistPlayTransactionError(SafeDomainError):
    def __init__(self, *, phase: str, diagnostics: dict[str, Any]) -> None:
        bounded_phase = phase if phase in PLAYLIST_PLAY_PHASES else "verify_playback"
        details = {"phase": bounded_phase, **bounded_playlist_play_failure(diagnostics)}
        if bounded_phase == "preflight_revalidation":
            code = "conflict"
            message = "The reviewed room, playlist, or queue state changed before playback"
        else:
            code = "speaker_rejected"
            message = (
                "Sonos could not complete exact playlist playback; appended items may remain"
                if details["queueAppended"]
                else "Sonos rejected exact playlist playback before the queue was appended"
            )
        super().__init__(code, message, details=details)
