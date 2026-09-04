from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

MAX_POST_CAPTURE_ATTEMPTS = 2
MAX_POST_CAPTURE_ELAPSED_MS = 120_000
POST_CAPTURE_RETRY_START_WINDOW_SECONDS = 0.25
POST_PLAYBACK_SECOND_CAPTURE_TARGET_SECONDS, POST_PLAYBACK_SECOND_CAPTURE_LATEST_START_SECONDS = (
    1.0,
    1.25,
)


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


def capture_playlist_play_post_write(
    capture: Callable[[], Any],
    *,
    acceptable: Callable[[Any], bool] | None = None,
    failed_predicates: Callable[[Any], tuple[str, ...]] | None = None,
    capture_status: dict[str, Any] | None = None,
    playback_verification: bool = False,
    clock: Any = time,
) -> Any | None:
    started = clock.monotonic()
    deadline = (
        float("inf") if playback_verification else started + POST_CAPTURE_RETRY_START_WINDOW_SECONDS
    )
    latest: Any | None = None
    status = capture_status if capture_status is not None else {}
    evidence: dict[str, Any] = {
        "attempts": [],
        "attemptCount": 0,
        "secondAttemptStarted": False,
        "secondAttemptSkipReason": "notApplicable",
    }
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
        if attempt > 0 and playback_verification:
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
                if attempt == 0:
                    skip_second_attempt("firstAttemptAuthoritative")
                return candidate
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
