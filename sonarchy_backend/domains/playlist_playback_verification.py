from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from .errors import PlanConflictError

MAX_POST_CAPTURE_ATTEMPTS = 2
MAX_POST_CAPTURE_ELAPSED_MS = 120_000
POST_CAPTURE_RETRY_START_WINDOW_SECONDS = 0.25
POST_PLAYBACK_SECOND_CAPTURE_TARGET_SECONDS, POST_PLAYBACK_SECOND_CAPTURE_LATEST_START_SECONDS = (
    1.0,
    1.25,
)
PLAYBACK_CONVERGENCE_DEADLINE_SECONDS = 5.0
PLAYBACK_CONVERGENCE_POLL_SECONDS = 0.25
MAX_PLAYBACK_CONVERGENCE_POLLS = 20
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


class PostWritePlaybackObservationError(Exception):
    def __init__(self, partial_capture: Any) -> None:
        super().__init__("Post-write playback observation failed")
        self.partial_capture = partial_capture


def content_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        item["identity"],
        item["title"],
        item["artist"],
        item["album"],
        item["duration"],
    )


def append_state_from_queue_evidence(
    before: Any,
    post: Any | None,
    capture_status: dict[str, Any],
) -> str:
    if post is None:
        return "unknown"
    before_items = tuple(map(content_key, before.queue_items))
    post_items = tuple(map(content_key, post.queue_items))
    playlist_items = tuple(map(content_key, before.playlist_items))
    if post_items == before_items + playlist_items:
        return "confirmed"
    if (
        post_items == before_items
        and capture_status["attemptCount"] == MAX_POST_CAPTURE_ATTEMPTS
        and capture_status["completedCount"] == MAX_POST_CAPTURE_ATTEMPTS
    ):
        return "absent"
    return "unknown"


def append_verification_failures(before: Any, post: Any) -> tuple[str, ...]:
    before_items = tuple(map(content_key, before.queue_items))
    post_items = tuple(map(content_key, post.queue_items))
    playlist_items = tuple(map(content_key, before.playlist_items))
    checks = (
        ("queueLengthMatches", len(post_items) == len(before_items) + len(playlist_items)),
        ("originalPrefixMatches", post_items[: len(before_items)] == before_items),
        ("appendedSegmentMatches", post_items[len(before_items) :] == playlist_items),
    )
    return tuple(name for name, passed in checks if not passed)


def _elapsed_ms(started: float, observed: float) -> int:
    elapsed = round((observed - started) * 1000)
    return min(MAX_POST_CAPTURE_ELAPSED_MS, max(0, elapsed))


def _convergence_evidence() -> dict[str, Any]:
    return {
        "observations": [],
        "observationCount": 0,
        "maximumObservationCount": MAX_PLAYBACK_CONVERGENCE_POLLS,
        "intervalMs": round(PLAYBACK_CONVERGENCE_POLL_SECONDS * 1000),
        "latestObservationStartMs": 0,
        "playingObserved": False,
        "completeCaptureAttempted": False,
        "completeCaptureAuthoritative": False,
        "finalReason": "convergenceNotNeeded",
    }


def observe_transport_convergence(
    read_transport: Callable[[], str],
    *,
    started: float,
    capture_status: dict[str, Any],
    clock: Any = time,
) -> str:
    evidence = _convergence_evidence()
    deadline = started + PLAYBACK_CONVERGENCE_DEADLINE_SECONDS
    poll_count = 0
    outcome = "observationWindowExhausted"
    for slot in range(1, MAX_PLAYBACK_CONVERGENCE_POLLS + 1):
        now = clock.monotonic()
        if now > deadline:
            break
        target = started + slot * PLAYBACK_CONVERGENCE_POLL_SECONDS
        # Skip slots missed during a slow read instead of issuing catch-up reads.
        if target < now:
            continue
        if target > now:
            clock.sleep(target - now)
        observation_started = clock.monotonic()
        # A scheduler wakeup can be late even when the requested sleep was bounded.
        if observation_started > deadline:
            break
        observation = {
            "observation": poll_count + 1,
            "startedElapsedMs": _elapsed_ms(started, observation_started),
            "outcome": "failed",
            "transport": "UNKNOWN",
        }
        try:
            transport = read_transport()
        except PlanConflictError:
            observation["completedElapsedMs"] = _elapsed_ms(started, clock.monotonic())
            evidence["observations"].append(observation)
            poll_count += 1
            outcome = "observationReadFailed"
            break
        observation.update(
            {
                "completedElapsedMs": _elapsed_ms(started, clock.monotonic()),
                "outcome": "completed",
                "transport": transport,
            }
        )
        evidence["observations"].append(observation)
        poll_count += 1
        if transport == "PLAYING":
            evidence["playingObserved"] = True
            outcome = "playingObserved"
            break
        if transport in {"STOPPED", "PAUSED_PLAYBACK", "UNKNOWN"}:
            outcome = "terminalNonPlaying"
            break
    evidence.update(
        observationCount=poll_count,
        latestObservationStartMs=(
            evidence["observations"][-1]["startedElapsedMs"] if evidence["observations"] else 0
        ),
        finalReason=outcome,
    )
    capture_status["postWriteCaptureEvidence"]["convergence"] = evidence
    if outcome == "playingObserved":
        evidence["completeCaptureAttempted"] = True
        return "ready"
    if outcome != "terminalNonPlaying":
        capture_status["verificationOutcome"] = "inconclusive"
    return {
        "observationReadFailed": "convergenceReadFailure",
        "terminalNonPlaying": "convergenceTerminalState",
        "observationWindowExhausted": "convergenceDeadlineExceeded",
    }.get(outcome, "convergenceDeadlineExceeded")


def capture_playlist_play_post_write(
    capture: Callable[[], Any],
    *,
    acceptable: Callable[[Any], bool] | None = None,
    failed_predicates: Callable[[Any], tuple[str, ...]] | None = None,
    prepare_retry: Callable[[Any, float, Any], str | None] | None = None,
    capture_status: dict[str, Any] | None = None,
    playback_verification: bool = False,
    clock: Any = time,
) -> Any | None:
    started = clock.monotonic()
    deadline = (
        float("inf") if playback_verification else started + POST_CAPTURE_RETRY_START_WINDOW_SECONDS
    )
    latest: Any | None = None
    retry_ready = False
    status = capture_status if capture_status is not None else {}
    evidence: dict[str, Any] = {
        "attempts": [],
        "attemptCount": 0,
        "secondAttemptStarted": False,
        "secondAttemptSkipReason": "notApplicable",
    }
    if playback_verification:
        evidence["convergence"] = _convergence_evidence()
    status.update(
        attemptCount=0,
        completedCount=0,
        failedCount=0,
        postWriteCaptureEvidence=evidence,
    )

    def skip_second_attempt(reason: str) -> None:
        evidence["secondAttemptSkipReason"] = reason

    for attempt in range(MAX_POST_CAPTURE_ATTEMPTS):
        if attempt > 0 and not playback_verification and clock.monotonic() >= deadline:
            skip_second_attempt("latestStartLimitExceeded")
            break
        if attempt > 0 and playback_verification and not retry_ready:
            elapsed = clock.monotonic() - started
            if elapsed < POST_PLAYBACK_SECOND_CAPTURE_TARGET_SECONDS:
                clock.sleep(POST_PLAYBACK_SECOND_CAPTURE_TARGET_SECONDS - elapsed)
                elapsed = clock.monotonic() - started
            if elapsed > POST_PLAYBACK_SECOND_CAPTURE_LATEST_START_SECONDS:
                skip_second_attempt("latestStartLimitExceeded")
                break
        attempt_started = started if attempt == 0 else clock.monotonic()
        if attempt == 1:
            evidence["secondAttemptStarted"] = True
        status["attemptCount"] += 1
        evidence["attemptCount"] = status["attemptCount"]
        attempt_evidence: dict[str, Any] = {
            "attempt": attempt + 1,
            "startedElapsedMs": _elapsed_ms(started, attempt_started),
            "outcome": "failed",
            "failedPredicates": [],
        }
        try:
            candidate = capture()
        except PostWritePlaybackObservationError as exc:
            attempt_evidence.update(
                completedElapsedMs=_elapsed_ms(started, clock.monotonic()),
                queueLength=exc.partial_capture.state["queue"]["length"],
                currentPosition=exc.partial_capture.state["queue"]["currentPosition"],
            )
            evidence["attempts"].append(attempt_evidence)
            status["failedCount"] += 1
        except Exception:  # noqa: BLE001 - partial or incomplete reads are bounded
            attempt_evidence["completedElapsedMs"] = _elapsed_ms(started, clock.monotonic())
            evidence["attempts"].append(attempt_evidence)
            status["failedCount"] += 1
        else:
            attempt_evidence.update(
                completedElapsedMs=_elapsed_ms(started, clock.monotonic()),
                outcome="completed",
                queueLength=candidate.state["queue"]["length"],
                currentPosition=candidate.state["queue"]["currentPosition"],
                transport=candidate.state["room"]["transport"],
                source=candidate.state["room"]["source"],
                failedPredicates=list(failed_predicates(candidate))
                if failed_predicates is not None
                else [],
            )
            status["completedCount"] += 1
            latest = candidate
            evidence["attempts"].append(attempt_evidence)
            if acceptable is None or acceptable(candidate):
                if playback_verification:
                    evidence["convergence"]["completeCaptureAuthoritative"] = True
                if attempt == 0:
                    skip_second_attempt("firstAttemptAuthoritative")
                return candidate
            if attempt == 0 and prepare_retry is not None:
                retry_decision = prepare_retry(candidate, started, clock)
                if retry_decision is not None and retry_decision != "ready":
                    skip_second_attempt(retry_decision)
                    break
                retry_ready = retry_decision == "ready"
        if clock.monotonic() >= deadline:
            if attempt == 0:
                skip_second_attempt("latestStartLimitExceeded")
            break
    return latest


def _stable_room(room: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in room.items() if key not in {"transport", "source"}}


def queue_verification_failures(
    before: Any,
    post: Any,
    expected_state: dict[str, Any],
    expected_position: int,
    position: int,
) -> tuple[str, ...]:
    approved_playlist = expected_state["playlist"]
    approved_queue = expected_state["queue"]
    expected_after_length = approved_queue["length"] + approved_playlist["itemCount"]
    prefix_matches = tuple(map(content_key, post.queue_items[: approved_queue["length"]])) == tuple(
        map(content_key, before.queue_items)
    )
    appended_items = post.queue_items[approved_queue["length"] :]
    appended_matches = tuple(map(content_key, appended_items)) == tuple(
        map(content_key, before.playlist_items)
    )
    checks = (
        (
            "stableRoomMatches",
            _stable_room(post.state["room"]) == _stable_room(expected_state["room"]),
        ),
        ("topologyMatches", post.state["topology"] == expected_state["topology"]),
        ("playlistMatches", post.state["playlist"] == approved_playlist),
        ("queueLengthMatches", post.state["queue"]["length"] == expected_after_length),
        ("originalPrefixMatches", prefix_matches),
        ("appendedSegmentMatches", appended_matches),
        ("appendPositionMatches", position == expected_position),
    )
    return tuple(name for name, passed in checks if not passed)


def playback_verification_failures(
    before: Any,
    post: Any,
    expected_position: int,
) -> tuple[str, ...]:
    first_item = before.playlist_items[0]
    position_available = 1 <= expected_position <= len(post.queue_items)
    current_queue_item_matches = position_available and (
        content_key(post.queue_items[expected_position - 1]) == content_key(first_item)
    )
    checks = (
        ("transportIsPlaying", post.state["room"]["transport"] == "PLAYING"),
        ("sourceIsQueue", post.state["room"]["source"] == "QUEUE"),
        (
            "currentPositionMatches",
            post.state["queue"]["currentPosition"] == expected_position,
        ),
        ("currentItemIdentityMatches", current_queue_item_matches),
        (
            "currentMetadataMatches",
            post.current_track
            == {
                "title": first_item["title"],
                "artist": first_item["artist"],
                "album": first_item["album"],
            },
        ),
    )
    return tuple(name for name, passed in checks if not passed)


def approved_verification_failures(
    before: Any,
    post: Any,
    expected_state: dict[str, Any],
    expected_position: int,
    position: int,
) -> tuple[str, ...]:
    return queue_verification_failures(
        before,
        post,
        expected_state,
        expected_position,
        position,
    ) + playback_verification_failures(before, post, expected_position)
