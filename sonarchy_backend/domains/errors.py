from __future__ import annotations

import re
from typing import Any

PLAYLIST_CONSTRUCTION_STEPS = frozenset(
    {"create", "verify_empty", "add_track", "verify_track", "verify_playlist"}
)
VERIFICATION_STATUSES = frozenset(
    {
        "not_started",
        "complete",
        "reopen_failed",
        "wrong_name",
        "incomplete_inventory",
        "wrong_count",
        "item_absent",
        "wrong_order",
        "identity_mismatch",
        "metadata_incomplete",
        "metadata_mismatch",
        "inventory_changed",
        "attribution_unproven",
        "add_rejected",
    }
)
CANONICAL_SONG_PATTERN = re.compile(r"song:[1-9]\d{0,19}")
SONOS_PLAYLIST_ID_PATTERN = re.compile(r"SQ:\d+")
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


def _bounded_retained_failure(value: dict[str, Any]) -> dict[str, Any]:
    details: dict[str, Any] = {
        key: value.get(key) is True
        for key in (
            "createCallReturned",
            "addCallReturned",
            "authoritativeReopen",
            "playlistRetained",
            "manualInspectionRequired",
            "preExistingPlaylistsUnchanged",
            "queueMutation",
            "playbackMutation",
            "succeeded",
        )
    }
    step = value.get("playlistConstructionStep")
    details["playlistConstructionStep"] = step if step in PLAYLIST_CONSTRUCTION_STEPS else "create"
    status = value.get("verificationStatus")
    details["verificationStatus"] = status if status in VERIFICATION_STATUSES else "reopen_failed"
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
    playlist_name = value.get("playlistName")
    if (
        isinstance(playlist_name, str)
        and playlist_name
        and len(playlist_name) <= 80
        and not any(ord(character) < 32 for character in playlist_name)
    ):
        details["playlistName"] = playlist_name
    observed_count = value.get("observedItemCount")
    if (
        isinstance(observed_count, int)
        and not isinstance(observed_count, bool)
        and 0 <= observed_count <= 25
    ):
        details["observedItemCount"] = observed_count
    reviewed_tracks = value.get("reviewedTracks")
    if isinstance(reviewed_tracks, list):
        bounded_tracks: list[dict[str, Any]] = []
        for track in reviewed_tracks[:25]:
            if not isinstance(track, dict):
                continue
            identity = track.get("canonicalIdentity")
            position = track.get("position")
            if (
                not isinstance(position, int)
                or isinstance(position, bool)
                or not 1 <= position <= 25
                or not isinstance(identity, str)
                or not CANONICAL_SONG_PATTERN.fullmatch(identity)
            ):
                continue
            safe_track: dict[str, Any] = {
                "position": position,
                "canonicalIdentity": identity,
            }
            for key in ("title", "artist", "album"):
                text = track.get(key)
                if (
                    isinstance(text, str)
                    and text
                    and len(text.encode("utf-8")) <= 240
                    and not any(ord(character) < 32 for character in text)
                ):
                    safe_track[key] = text
            bounded_tracks.append(safe_track)
        details["reviewedTracks"] = bounded_tracks
    track_results = value.get("trackResults")
    if isinstance(track_results, list):
        bounded_results: list[dict[str, Any]] = []
        for result in track_results[:25]:
            if not isinstance(result, dict):
                continue
            identity = result.get("canonicalIdentity")
            position = result.get("position")
            status = result.get("verificationStatus")
            if (
                not isinstance(position, int)
                or isinstance(position, bool)
                or not 1 <= position <= 25
                or not isinstance(identity, str)
                or not CANONICAL_SONG_PATTERN.fullmatch(identity)
                or status not in VERIFICATION_STATUSES
            ):
                continue
            bounded_results.append(
                {
                    "position": position,
                    "canonicalIdentity": identity,
                    "addCallReturned": result.get("addCallReturned") is True,
                    "verificationStatus": status,
                }
            )
        details["trackResults"] = bounded_results
    return details


class RetainedPlaylistTransactionError(SafeDomainError):
    def __init__(self, diagnostics: dict[str, Any]) -> None:
        details = {
            "phase": "retained_playlist_creation",
            **_bounded_retained_failure(diagnostics),
        }
        if details["playlistRetained"]:
            message = (
                "The direct Apple playlist could not be verified completely; "
                "the exact playlist was retained for manual inspection"
            )
        else:
            message = "The direct Apple playlist could not be created safely"
        super().__init__("speaker_rejected", message, details=details)
