from __future__ import annotations

import copy
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
PLAYLIST_PLAY_CAPTURE_PREDICATES = frozenset(
    {
        "appendPositionMatches",
        "appendedSegmentMatches",
        "currentItemIdentityMatches",
        "currentMetadataMatches",
        "currentPositionMatches",
        "originalPrefixMatches",
        "playlistMatches",
        "queueLengthMatches",
        "sourceIsQueue",
        "stableRoomMatches",
        "topologyMatches",
        "transportIsPlaying",
    }
)
POST_WRITE_CAPTURE_SKIP_REASONS = frozenset(
    {
        "firstAttemptAuthoritative",
        "latestStartLimitExceeded",
        "maximumAttemptsReached",
        "notApplicable",
        "convergenceDeadlineExceeded",
        "convergenceReadFailure",
        "convergenceTerminalState",
    }
)
PLAYBACK_CONVERGENCE_OUTCOMES = frozenset(
    {"playingObserved", "observationReadFailed", "observationWindowExhausted", "terminalNonPlaying"}
)
PLAYBACK_CONVERGENCE_TRANSPORTS = frozenset(
    {"STOPPED", "PAUSED_PLAYBACK", "PLAYING", "TRANSITIONING", "UNKNOWN"}
)
PLAYBACK_CONVERGENCE_FINAL_REASONS = frozenset(
    {
        "convergenceNotNeeded",
        "playingObserved",
        "observationWindowExhausted",
        "observationReadFailed",
        "completeCaptureFailed",
        "completeCaptureMismatch",
        "terminalNonPlaying",
    }
)
MAX_POST_WRITE_CAPTURE_ELAPSED_MS = 120_000


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


def _bounded_elapsed_ms(value: Any) -> int | None:
    if type(value) is not int or not 0 <= value <= MAX_POST_WRITE_CAPTURE_ELAPSED_MS:
        return None
    return value


def bounded_post_write_capture_evidence(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    raw_attempts = value.get("attempts")
    if not isinstance(raw_attempts, list) or not 1 <= len(raw_attempts) <= 2:
        return None
    attempts: list[dict[str, Any]] = []
    for expected_attempt, raw_attempt in enumerate(raw_attempts, 1):
        if (
            not isinstance(raw_attempt, dict)
            or type(raw_attempt.get("attempt")) is not int
            or raw_attempt["attempt"] != expected_attempt
        ):
            return None
        started = _bounded_elapsed_ms(raw_attempt.get("startedElapsedMs"))
        completed = _bounded_elapsed_ms(raw_attempt.get("completedElapsedMs"))
        if started is None or completed is None or completed < started:
            return None
        outcome = raw_attempt.get("outcome")
        if not isinstance(outcome, str) or outcome not in {"completed", "failed"}:
            return None
        raw_predicates = raw_attempt.get("failedPredicates")
        if (
            not isinstance(raw_predicates, list)
            or len(raw_predicates) > len(PLAYLIST_PLAY_CAPTURE_PREDICATES)
            or any(not isinstance(item, str) for item in raw_predicates)
            or len(set(raw_predicates)) != len(raw_predicates)
            or any(item not in PLAYLIST_PLAY_CAPTURE_PREDICATES for item in raw_predicates)
        ):
            return None
        attempt: dict[str, Any] = {
            "attempt": expected_attempt,
            "startedElapsedMs": started,
            "completedElapsedMs": completed,
            "outcome": outcome,
            "failedPredicates": list(raw_predicates),
        }
        queue_length = raw_attempt.get("queueLength")
        current_position = raw_attempt.get("currentPosition")
        transport = raw_attempt.get("transport")
        source = raw_attempt.get("source")
        if "queueLength" in raw_attempt:
            if type(queue_length) is not int or not 0 <= queue_length <= 100:
                return None
            attempt["queueLength"] = queue_length
        if "currentPosition" in raw_attempt:
            if current_position is not None and (
                type(current_position) is not int or not 1 <= current_position <= 100
            ):
                return None
            attempt["currentPosition"] = current_position
        if "transport" in raw_attempt:
            if not isinstance(transport, str) or transport not in {
                "STOPPED",
                "PAUSED_PLAYBACK",
                "PLAYING",
                "TRANSITIONING",
                "UNKNOWN",
            }:
                return None
            attempt["transport"] = transport
        if "source" in raw_attempt:
            if not isinstance(source, str) or source not in {
                "QUEUE",
                "NONE",
                "UNSUPPORTED",
                "UNKNOWN",
            }:
                return None
            attempt["source"] = source
        if (
            outcome == "completed"
            and not {
                "queueLength",
                "currentPosition",
                "transport",
                "source",
            }
            <= raw_attempt.keys()
        ):
            return None
        if outcome == "failed" and raw_predicates:
            return None
        attempts.append(attempt)

    attempt_count = value.get("attemptCount")
    if type(attempt_count) is not int or attempt_count != len(attempts):
        return None
    if type(value.get("secondAttemptStarted")) is not bool:
        return None
    second_started = value["secondAttemptStarted"]
    evidence: dict[str, Any] = {
        "attempts": attempts,
        "attemptCount": attempt_count,
        "secondAttemptStarted": second_started,
    }
    skip_reason = value.get("secondAttemptSkipReason")
    if not isinstance(skip_reason, str) or skip_reason not in POST_WRITE_CAPTURE_SKIP_REASONS:
        return None
    evidence["secondAttemptSkipReason"] = skip_reason
    if second_started:
        if len(attempts) != 2 or skip_reason != "notApplicable":
            return None
    elif len(attempts) != 1 or skip_reason not in {
        "firstAttemptAuthoritative",
        "latestStartLimitExceeded",
        "convergenceDeadlineExceeded",
        "convergenceReadFailure",
        "convergenceTerminalState",
    }:
        return None
    raw_convergence = value.get("convergence")
    if raw_convergence is None:
        return evidence
    if not isinstance(raw_convergence, dict):
        return None
    observations = raw_convergence.get("observations")
    if not isinstance(observations, list) or len(observations) > 20:
        return None
    bounded_observations: list[dict[str, Any]] = []
    for expected_observation, raw_observation in enumerate(observations, 1):
        if not isinstance(raw_observation, dict) or set(raw_observation) != {
            "observation",
            "startedElapsedMs",
            "completedElapsedMs",
            "outcome",
            "transport",
        }:
            return None
        if raw_observation.get("observation") != expected_observation:
            return None
        started = _bounded_elapsed_ms(raw_observation.get("startedElapsedMs"))
        completed = _bounded_elapsed_ms(raw_observation.get("completedElapsedMs"))
        if started is None or completed is None or completed < started or started > 5_000:
            return None
        outcome = raw_observation.get("outcome")
        transport = raw_observation.get("transport")
        if (
            outcome not in {"completed", "failed"}
            or transport not in PLAYBACK_CONVERGENCE_TRANSPORTS
        ):
            return None
        bounded_observations.append(
            {
                "observation": expected_observation,
                "startedElapsedMs": started,
                "completedElapsedMs": completed,
                "outcome": outcome,
                "transport": transport,
            }
        )
    observation_count = raw_convergence.get("observationCount")
    maximum = raw_convergence.get("maximumObservationCount")
    interval = raw_convergence.get("intervalMs")
    latest_start = _bounded_elapsed_ms(raw_convergence.get("latestObservationStartMs"))
    if (
        set(raw_convergence)
        != {
            "observations",
            "observationCount",
            "maximumObservationCount",
            "intervalMs",
            "latestObservationStartMs",
            "playingObserved",
            "completeCaptureAttempted",
            "completeCaptureAuthoritative",
            "finalReason",
        }
        or type(observation_count) is not int
        or observation_count != len(bounded_observations)
        or type(maximum) is not int
        or maximum != 20
        or type(interval) is not int
        or interval != 250
        or latest_start is None
        or raw_convergence.get("playingObserved") not in {True, False}
        or raw_convergence.get("completeCaptureAttempted") not in {True, False}
        or raw_convergence.get("completeCaptureAuthoritative") not in {True, False}
        or raw_convergence.get("finalReason") not in PLAYBACK_CONVERGENCE_FINAL_REASONS
    ):
        return None
    evidence["convergence"] = {
        "observations": bounded_observations,
        "observationCount": observation_count,
        "maximumObservationCount": maximum,
        "intervalMs": interval,
        "latestObservationStartMs": latest_start,
        "playingObserved": raw_convergence["playingObserved"],
        "completeCaptureAttempted": raw_convergence["completeCaptureAttempted"],
        "completeCaptureAuthoritative": raw_convergence["completeCaptureAuthoritative"],
        "finalReason": raw_convergence["finalReason"],
    }
    return evidence


def bounded_playlist_play_failure(value: dict[str, Any]) -> dict[str, Any]:
    append_state = value.get("appendState")
    if append_state not in {"confirmed", "absent", "unknown"}:
        append_state = "unknown"
    playback_state = value.get("playbackState")
    if playback_state not in {"confirmed", "absent", "unknown"}:
        playback_state = (
            "confirmed"
            if value.get("playbackStarted") is True
            else "absent"
            if "playbackStarted" in value
            else "unknown"
        )
    details: dict[str, Any] = {
        "appendState": append_state,
        "playbackState": playback_state,
        "appendInvocationReturned": value.get("appendInvocationReturned") is True,
        "playbackStartInvocationReturned": value.get("playbackStartInvocationReturned") is True,
        "queueRollbackAttempted": value.get("queueRollbackAttempted") is True,
        "succeeded": value.get("succeeded") is True,
    }
    verification_outcome = value.get("verificationOutcome")
    if verification_outcome in {"inconclusive"}:
        details["verificationOutcome"] = verification_outcome
    if playback_state != "unknown":
        details["playbackStarted"] = playback_state == "confirmed"
    if append_state != "unknown":
        details["queueAppended"] = append_state == "confirmed"
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
    capture_evidence = bounded_post_write_capture_evidence(value.get("postWriteCaptureEvidence"))
    if capture_evidence is not None:
        details["postWriteCaptureEvidence"] = capture_evidence
    return details


def authoritative_playlist_play_result(
    *,
    room: dict[str, Any],
    topology: dict[str, Any],
    playlist: dict[str, Any],
    before_length: int,
    after_length: int,
    expected_position: int,
    current_position: int | None,
    appended_item_count: int,
    appended_segment_fingerprint: str,
    current_item: dict[str, Any],
    append_invocation_returned: bool,
    playback_start_invocation_returned: bool,
    post_write_capture_evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "ok": True,
        "action": "play-exact-sonos-playlist",
        "room": copy.deepcopy(room),
        "topology": copy.deepcopy(topology),
        "playlist": copy.deepcopy(playlist),
        "queue": {
            "beforeLength": before_length,
            "afterLength": after_length,
            "expectedFirstAppendedPosition": expected_position,
            "currentPosition": current_position,
            "appendedItemCount": appended_item_count,
            "appendedSegmentFingerprint": appended_segment_fingerprint,
            "existingEntriesPreserved": True,
        },
        "playback": {
            "transport": "PLAYING",
            "source": "QUEUE",
            "currentItem": copy.deepcopy(current_item),
        },
        "verification": {
            "authoritative": True,
            "playlistContentUnchanged": True,
            "queueLengthIncreasedByPlaylistCount": True,
            "appendedSegmentMatchesPlaylist": True,
            "currentPositionIsFirstAppended": True,
            "currentItemMatchesPlaylistFirstItem": True,
            "volumeUnchanged": True,
            "muteUnchanged": True,
            "topologyUnchanged": True,
        },
        "mutations": {
            "appendInvocationCount": 1,
            "playbackStartInvocationCount": 1,
            "appendInvocationReturned": append_invocation_returned,
            "playbackStartInvocationReturned": playback_start_invocation_returned,
            "queueClearCount": 0,
            "queueReplaceCount": 0,
            "queueRemoveCount": 0,
            "queueMoveCount": 0,
            "queueRollbackAttempted": False,
            "volumeMutation": False,
            "muteMutation": False,
            "topologyMutation": False,
            "sourceSwitchMutation": False,
            "playlistMutation": False,
        },
        "appendState": "confirmed",
        "playbackState": "confirmed",
        "playbackStarted": True,
        "postWriteCaptureEvidence": copy.deepcopy(post_write_capture_evidence),
        "retryCount": 0,
        "substitutionCount": 0,
    }


class PlaylistPlayTransactionError(SafeDomainError):
    def __init__(self, *, phase: str, diagnostics: dict[str, Any]) -> None:
        bounded_phase = phase if phase in PLAYLIST_PLAY_PHASES else "verify_playback"
        details = {"phase": bounded_phase, **bounded_playlist_play_failure(diagnostics)}
        if bounded_phase == "preflight_revalidation":
            code = "conflict"
            message = "The reviewed room, playlist, or queue state changed before playback"
        elif details.get("verificationOutcome") == "inconclusive":
            code = "verification_inconclusive"
            message = (
                "Playback start was accepted, but bounded post-write verification did not "
                "establish authoritative playback; playback may still be starting. "
                "Do not repeat the mutation."
            )
        else:
            code = "speaker_rejected"
            message = (
                "Sonos could not complete exact playlist playback; appended items may remain"
                if details["appendState"] != "absent"
                else "Sonos rejected exact playlist playback before the queue was appended"
            )
        super().__init__(code, message, details=details)
