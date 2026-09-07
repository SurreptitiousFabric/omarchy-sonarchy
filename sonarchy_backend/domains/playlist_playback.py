from __future__ import annotations

import copy
import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sonarchy_mcp_contract import MCP_OPERATION_PLAY_EXECUTE

from . import playlist_playback_verification as verification
from .common import clean, safe_index
from .errors import (
    PlanConflictError,
    PlaylistPlayTransactionError,
    authoritative_playlist_play_result,
)
from .media import item_attr, validate_playlist_id
from .playlist_rules import validate_playlist_title
from .playlists import PlaylistPlayStepError, append_and_start_playlist

MAX_PLAYLIST_PLAY_ITEMS = 25
MAX_PLAYLIST_PLAY_QUEUE_ITEMS = 100
MAX_PLAYLIST_INVENTORY_ITEMS = 100
MAX_PLAYLIST_ITEM_PREVIEW = 5
MAX_ITEM_RESOURCES = 8
MAX_ITEM_TEXT_BYTES = 512
MAX_RESOURCE_TEXT_BYTES = 2048
PLAYLIST_PLAY_SIDE_EFFECTS = (
    "Keep every existing room queue entry",
    "Append the complete reviewed Sonos Playlist to the end of the room queue",
    "Move playback to the first newly appended item",
    "Interrupt the current paused or stopped queue context",
    "Use the Sonos queue as the playback source",
    "Do not change volume, mute, topology, or Sonos Playlist contents",
    "Do not retry automatically",
    "If append succeeds but playback start or verification fails, appended items may remain",
    "Do not clear, reconstruct, or roll back the queue because issue #19 remains unresolved",
)


@dataclass(frozen=True)
class PlaylistPlayCapture:
    state: dict[str, Any]
    coordinator: Any
    playlist: Any
    playlist_items: tuple[dict[str, Any], ...]
    queue_items: tuple[dict[str, Any], ...]
    current_track: dict[str, str]


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return f"sha256:{hashlib.sha256(encoded.encode('utf-8')).hexdigest()}"


def _bounded_text(
    raw: Any,
    label: str,
    *,
    required: bool = False,
    maximum: int = MAX_ITEM_TEXT_BYTES,
) -> str:
    value = clean(raw)
    if required and not value:
        raise PlanConflictError(f"The Sonos {label} is unavailable")
    if len(value.encode("utf-8")) > maximum or any(ord(character) < 32 for character in value):
        raise PlanConflictError(f"The Sonos {label} is not safely bounded")
    return value


def _resource_values(item: Any) -> list[dict[str, str]]:
    resources = item_attr(item, "resources", []) or []
    try:
        values = list(resources)
    except TypeError as exc:
        raise PlanConflictError("Sonos item resources could not be inspected safely") from exc
    if len(values) > MAX_ITEM_RESOURCES:
        raise PlanConflictError("A Sonos item has too many resources to inspect safely")
    projected = []
    for resource in values:
        projected.append(
            {
                "uri": _bounded_text(
                    item_attr(resource, "uri"),
                    "resource identity",
                    maximum=MAX_RESOURCE_TEXT_BYTES,
                ),
                "protocol": _bounded_text(
                    item_attr(resource, "protocol_info"),
                    "resource protocol",
                ),
                "duration": _bounded_text(
                    item_attr(resource, "duration"),
                    "resource duration",
                    maximum=64,
                ),
            }
        )
    return projected


def _item_value(item: Any, position: int) -> dict[str, Any]:
    item_id = _bounded_text(item_attr(item, "item_id"), "item identity")
    resources = _resource_values(item)
    if not item_id and not any(resource["uri"] for resource in resources):
        raise PlanConflictError("A Sonos item has no stable content identity")
    title = _bounded_text(item_attr(item, "title"), "item title", required=True)
    artist = _bounded_text(
        item_attr(item, "creator", item_attr(item, "artist")),
        "item artist",
    )
    album = _bounded_text(item_attr(item, "album"), "item album")
    duration = _bounded_text(
        item_attr(item, "duration", resources[0]["duration"] if resources else ""),
        "item duration",
        maximum=64,
    )
    identity_material: dict[str, Any] = {
        "title": title,
        "artist": artist,
        "album": album,
        "duration": duration,
    }
    if any(resource["uri"] for resource in resources):
        identity_material["resources"] = resources
    else:
        identity_material["itemId"] = item_id
    return {
        "position": position,
        "identity": _fingerprint(identity_material),
        "title": title,
        "artist": artist,
        "album": album,
        "duration": duration,
    }


def _ordered_items(items: list[Any]) -> tuple[dict[str, Any], ...]:
    return tuple(_item_value(item, index) for index, item in enumerate(items, 1))


def _content_fingerprint(items: tuple[dict[str, Any], ...]) -> str:
    return _fingerprint([verification.content_key(item) for item in items])


def _complete_result(result: Any, maximum: int, label: str) -> list[Any]:
    try:
        items = list(result)
    except TypeError as exc:
        raise PlanConflictError(f"The complete Sonos {label} could not be read") from exc
    total = safe_index(item_attr(result, "total_matches", len(items)), -1)
    if total != len(items) or total > maximum:
        raise PlanConflictError(f"The complete Sonos {label} could not be read safely")
    return items


def _exact_playlist(coordinator: Any, playlist_id: str) -> tuple[Any, str]:
    try:
        inventory_result = coordinator.get_sonos_playlists(
            max_items=MAX_PLAYLIST_INVENTORY_ITEMS + 1
        )
        inventory = _complete_result(
            inventory_result,
            MAX_PLAYLIST_INVENTORY_ITEMS,
            "Playlist inventory",
        )
    except PlanConflictError:
        raise
    except Exception as exc:
        raise PlanConflictError("Sonos Playlists could not be listed safely") from exc
    matches = [item for item in inventory if clean(item_attr(item, "item_id")) == playlist_id]
    if len(matches) != 1:
        raise PlanConflictError("The exact Sonos Playlist is unavailable or ambiguous")
    try:
        playlist = coordinator.get_sonos_playlist_by_attr("item_id", playlist_id)
        exact_id = validate_playlist_id(item_attr(playlist, "item_id"))
        title = validate_playlist_title(item_attr(playlist, "title"))
    except Exception as exc:
        raise PlanConflictError("The exact Sonos Playlist could not be reopened") from exc
    listed_title = _bounded_text(item_attr(matches[0], "title"), "Playlist title", required=True)
    if exact_id != playlist_id or title != listed_title:
        raise PlanConflictError("The exact Sonos Playlist identity changed while resolving it")
    return playlist, title


def _playlist_state(
    coordinator: Any, playlist_id: str
) -> tuple[dict[str, Any], Any, tuple[dict[str, Any], ...]]:
    playlist, title = _exact_playlist(coordinator, playlist_id)
    try:
        result = coordinator.music_library.browse(
            ml_item=playlist,
            start=0,
            max_items=MAX_PLAYLIST_PLAY_ITEMS + 1,
            full_album_art_uri=False,
        )
        raw_items = _complete_result(result, MAX_PLAYLIST_PLAY_ITEMS, "Playlist contents")
    except PlanConflictError:
        raise
    except Exception as exc:
        raise PlanConflictError("The complete Sonos Playlist could not be read") from exc
    if not raw_items:
        raise PlanConflictError("The exact Sonos Playlist is empty")
    items = _ordered_items(raw_items)
    preview = [copy.deepcopy(item) for item in items[:MAX_PLAYLIST_ITEM_PREVIEW]]
    return (
        {
            "id": playlist_id,
            "title": title,
            "itemCount": len(items),
            "contentFingerprint": _content_fingerprint(items),
            "itemPreview": preview,
            "firstItem": copy.deepcopy(items[0]),
        },
        playlist,
        items,
    )


def _current_position(raw: Any, queue_length: int) -> int | None:
    position = safe_index(raw, 0)
    if position == 0:
        return None
    return position if 1 <= position <= queue_length else None


def _queue_state(
    coordinator: Any,
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...], dict[str, str]]:
    try:
        result = coordinator.get_queue(
            max_items=MAX_PLAYLIST_PLAY_QUEUE_ITEMS + 1,
            full_album_art_uri=False,
        )
        raw_items = _complete_result(result, MAX_PLAYLIST_PLAY_QUEUE_ITEMS, "room queue")
        track = coordinator.get_current_track_info()
    except PlanConflictError:
        raise
    except Exception as exc:
        raise PlanConflictError("The complete room queue could not be read") from exc
    if not isinstance(track, dict):
        raise PlanConflictError("The current queue position could not be read safely")
    items = _ordered_items(raw_items)
    position = _current_position(track.get("playlist_position"), len(items))
    current_track = {
        "title": _bounded_text(track.get("title"), "current item title"),
        "artist": _bounded_text(track.get("artist"), "current item artist"),
        "album": _bounded_text(track.get("album"), "current item album"),
    }
    return (
        {
            "length": len(items),
            "contentFingerprint": _content_fingerprint(items),
            "currentPosition": position,
            "expectedFirstAppendedPosition": len(items) + 1,
        },
        items,
        current_track,
    )


def _source(coordinator: Any) -> str:
    try:
        media = coordinator.avTransport.GetMediaInfo([("InstanceID", 0)])
        hint = clean(getattr(coordinator, "music_source", "")).upper().replace("-", "_")
    except Exception as exc:
        raise PlanConflictError("The current Sonos source could not be established safely") from exc
    if not isinstance(media, dict) or "CurrentURI" not in media:
        raise PlanConflictError("The current Sonos source could not be established safely")
    current_uri = clean(media.get("CurrentURI"))
    if hint in {"TV", "LINE_IN", "AIRPLAY", "RADIO"}:
        return "UNSUPPORTED"
    if current_uri.casefold().startswith("x-rincon-queue:"):
        return "QUEUE"
    if not current_uri and hint in {"", "NONE", "NO_SOURCE"}:
        return "NONE"
    return "UNSUPPORTED"


def _transport_state(coordinator: Any) -> str:
    try:
        transport_info = coordinator.get_current_transport_info()
    except Exception as exc:
        raise PlanConflictError("The current Sonos transport could not be read safely") from exc
    if not isinstance(transport_info, dict):
        raise PlanConflictError("The current Sonos transport could not be read safely")
    transport = clean(transport_info.get("current_transport_state")).upper() or "UNKNOWN"
    if transport not in {
        "STOPPED",
        "PAUSED_PLAYBACK",
        "PLAYING",
        "TRANSITIONING",
    }:
        transport = "UNKNOWN"
    return transport


def _dynamic_playback_state(coordinator: Any) -> tuple[str, str]:
    return _transport_state(coordinator), _source(coordinator)


def _room_state(
    speaker: Any,
) -> tuple[dict[str, Any], dict[str, Any], Any]:
    room_uid = _bounded_text(getattr(speaker, "uid", ""), "room UID", required=True)
    room_name = _bounded_text(getattr(speaker, "player_name", ""), "room name", required=True)
    household_id = _bounded_text(
        getattr(speaker, "household_id", ""), "household identity", required=True
    )
    try:
        group = speaker.group
        if group is None:
            coordinator = speaker
            members = [speaker]
        else:
            coordinator = group.coordinator
            members = list(group.members)
    except Exception as exc:
        raise PlanConflictError("The complete room topology could not be established") from exc
    coordinator_uid = _bounded_text(
        getattr(coordinator, "uid", ""), "coordinator UID", required=True
    )
    member_uids = sorted(
        _bounded_text(getattr(member, "uid", ""), "room UID", required=True) for member in members
    )
    if member_uids != [room_uid] or coordinator_uid != room_uid:
        raise PlanConflictError("Exact Sonos Playlist playback requires a standalone room")
    coordinator_household = _bounded_text(
        getattr(coordinator, "household_id", ""),
        "household identity",
        required=True,
    )
    if coordinator_household != household_id:
        raise PlanConflictError("The room and coordinator household identities differ")
    online_value = getattr(speaker, "is_visible", True)
    if online_value is not True:
        raise PlanConflictError("The exact Sonos room is offline")
    volume = getattr(speaker, "volume", None)
    if type(volume) is not int or not 0 <= volume <= 100:
        raise PlanConflictError("The exact room volume could not be read safely")
    if volume > 20:
        raise PlanConflictError("Exact Sonos Playlist playback requires room volume at most 20")
    mute = getattr(speaker, "mute", None)
    if type(mute) is not bool:
        raise PlanConflictError("The exact room mute state could not be read safely")
    transport, source = _dynamic_playback_state(coordinator)
    capabilities = {
        "append-sonos-playlist": callable(getattr(coordinator, "add_to_queue", None)),
        "play-from-queue": callable(getattr(coordinator, "play_from_queue", None)),
        "read-complete-queue": callable(getattr(coordinator, "get_queue", None)),
        "read-complete-playlist": callable(
            getattr(getattr(coordinator, "music_library", None), "browse", None)
        ),
        "resolve-exact-playlist": callable(getattr(coordinator, "get_sonos_playlist_by_attr", None))
        and callable(getattr(coordinator, "get_sonos_playlists", None)),
    }
    if not all(capabilities.values()):
        raise PlanConflictError("This room lacks exact Sonos Playlist playback capabilities")
    topology = {
        "groupUid": coordinator_uid,
        "coordinatorUid": coordinator_uid,
        "memberUids": member_uids,
        "standalone": True,
    }
    room = {
        "uid": room_uid,
        "name": room_name,
        "householdFingerprint": _fingerprint(household_id),
        "coordinatorUid": coordinator_uid,
        "online": True,
        "volume": volume,
        "mute": mute,
        "transport": transport,
        "source": source,
        "capabilities": sorted(
            capability for capability, present in capabilities.items() if present
        ),
    }
    return room, topology, coordinator


def capture_playlist_play_target(
    speaker: Any,
    playlist_id: str,
    *,
    enforce_preflight_policy: bool,
) -> PlaylistPlayCapture:
    try:
        exact_playlist_id = validate_playlist_id(playlist_id)
    except ValueError as exc:
        raise PlanConflictError("The Sonos Playlist ID must be an exact SQ:<id>") from exc
    room, topology, coordinator = _room_state(speaker)
    if enforce_preflight_policy:
        if room["transport"] not in {"STOPPED", "PAUSED_PLAYBACK"}:
            raise PlanConflictError("The room must be stopped or paused before playlist playback")
        if room["source"] not in {"QUEUE", "NONE"}:
            raise PlanConflictError(
                "The room source is not a safely established queue or no source"
            )
    playlist, playlist_object, playlist_items = _playlist_state(coordinator, exact_playlist_id)
    queue, queue_items, current_track = _queue_state(coordinator)
    if enforce_preflight_policy and queue["length"] + playlist["itemCount"] > 100:
        raise PlanConflictError("The room queue and Sonos Playlist would exceed 100 items")
    capture = PlaylistPlayCapture(
        state={
            "room": room,
            "topology": topology,
            "playlist": playlist,
            "queue": queue,
        },
        coordinator=coordinator,
        playlist=playlist_object,
        playlist_items=playlist_items,
        queue_items=queue_items,
        current_track=current_track,
    )
    if not enforce_preflight_policy:
        try:
            transport, source = _dynamic_playback_state(coordinator)
        except PlanConflictError as exc:
            raise verification.PostWritePlaybackObservationError(capture) from exc
        capture.state["room"]["transport"] = transport
        capture.state["room"]["source"] = source
    return capture


def _prepare_playback_retry(
    candidate: PlaylistPlayCapture,
    started: float,
    clock: Any,
    *,
    before: PlaylistPlayCapture,
    expected_state: dict[str, Any],
    expected_position: int,
    position: int,
    capture_status: dict[str, Any],
) -> str | None:
    failures = verification.approved_verification_failures(
        before,
        candidate,
        expected_state,
        expected_position,
        position,
    )
    if (
        failures != ("transportIsPlaying",)
        or candidate.state["room"]["transport"] != "TRANSITIONING"
    ):
        return None
    return verification.observe_transport_convergence(
        lambda: _transport_state(candidate.coordinator),
        started=started,
        capture_status=capture_status,
        clock=clock,
    )


def inspect_playlist_play_target(speaker: Any, playlist_id: str) -> dict[str, Any]:
    return copy.deepcopy(
        capture_playlist_play_target(
            speaker,
            playlist_id,
            enforce_preflight_policy=True,
        ).state
    )


def _failure_diagnostics(
    *,
    phase: str,
    expected_position: int,
    append_state: str,
    playback_state: str,
    append_invocation_returned: bool,
    playback_start_invocation_returned: bool,
    append_count: int,
    playback_start_count: int,
    post: PlaylistPlayCapture | None,
    post_write_capture_evidence: dict[str, Any] | None = None,
    verification_outcome: str | None = None,
) -> PlaylistPlayTransactionError:
    diagnostics: dict[str, Any] = {
        "appendState": append_state,
        "playbackState": playback_state,
        "appendInvocationReturned": append_invocation_returned,
        "playbackStartInvocationReturned": playback_start_invocation_returned,
        "queueRollbackAttempted": False,
        "appendInvocationCount": append_count,
        "playbackStartInvocationCount": playback_start_count,
        "retryCount": 0,
        "expectedFirstAppendedPosition": expected_position,
        "succeeded": False,
    }
    if post_write_capture_evidence is not None:
        diagnostics["postWriteCaptureEvidence"] = copy.deepcopy(post_write_capture_evidence)
    if verification_outcome is not None:
        diagnostics["verificationOutcome"] = verification_outcome
    if playback_state != "unknown":
        diagnostics["playbackStarted"] = playback_state == "confirmed"
    if post is not None:
        diagnostics.update(
            observedQueueLength=post.state["queue"]["length"],
            observedQueueFingerprint=post.state["queue"]["contentFingerprint"],
            observedCurrentPosition=post.state["queue"]["currentPosition"],
            observedTransport=post.state["room"]["transport"],
            observedSource=post.state["room"]["source"],
        )
    return PlaylistPlayTransactionError(phase=phase, diagnostics=diagnostics)


def _post_capture(
    speaker: Any,
    playlist_id: str,
    *,
    acceptable: Callable[[PlaylistPlayCapture], bool] | None = None,
    failed_predicates: Callable[[PlaylistPlayCapture], tuple[str, ...]] | None = None,
    prepare_retry: Callable[[PlaylistPlayCapture, float, Any], str | None] | None = None,
    capture_status: dict[str, Any] | None = None,
    playback_verification: bool = False,
) -> PlaylistPlayCapture | None:
    return verification.capture_playlist_play_post_write(
        lambda: capture_playlist_play_target(
            speaker,
            playlist_id,
            enforce_preflight_policy=False,
        ),
        acceptable=acceptable,
        failed_predicates=failed_predicates,
        prepare_retry=prepare_retry,
        capture_status=capture_status,
        playback_verification=playback_verification,
        clock=time,
    )


def execute_preflighted_playlist_play(
    speaker: Any,
    plan: dict[str, Any],
    *,
    mutation_started_callback: Callable[[], None] | None = None,
) -> dict[str, Any]:
    if plan.get("operation") != MCP_OPERATION_PLAY_EXECUTE:
        raise PlanConflictError("The playlist plan is not bound to exact playback")
    room_uid = str(plan.get("roomUid", ""))
    try:
        playlist_id = validate_playlist_id(plan.get("playlistId"))
        expected_state = copy.deepcopy(plan["targetState"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PlanConflictError("The exact playlist playback plan is invalid") from exc
    if clean(getattr(speaker, "uid", "")) != room_uid:
        raise PlaylistPlayTransactionError(
            phase="preflight_revalidation",
            diagnostics={
                "appendState": "absent",
                "playbackState": "absent",
                "appendInvocationReturned": False,
                "playbackStartInvocationReturned": False,
                "playbackStarted": False,
                "queueRollbackAttempted": False,
                "appendInvocationCount": 0,
                "playbackStartInvocationCount": 0,
                "retryCount": 0,
                "succeeded": False,
            },
        )
    expected_position = safe_index(
        expected_state.get("queue", {}).get("expectedFirstAppendedPosition"),
        -1,
    )
    try:
        before = capture_playlist_play_target(
            speaker,
            playlist_id,
            enforce_preflight_policy=True,
        )
    except PlanConflictError as exc:
        raise _failure_diagnostics(
            phase="preflight_revalidation",
            expected_position=max(0, expected_position),
            append_state="absent",
            playback_state="absent",
            append_invocation_returned=False,
            playback_start_invocation_returned=False,
            append_count=0,
            playback_start_count=0,
            post=None,
        ) from exc
    if before.state != expected_state or expected_position < 1:
        raise _failure_diagnostics(
            phase="preflight_revalidation",
            expected_position=max(0, expected_position),
            append_state="absent",
            playback_state="absent",
            append_invocation_returned=False,
            playback_start_invocation_returned=False,
            append_count=0,
            playback_start_count=0,
            post=before,
        )

    append_count = 1
    playback_start_count = 0
    append_invocation_returned = True
    playback_start_invocation_returned = True
    lost_playback_error: PlaylistPlayStepError | None = None

    def reject(
        *,
        phase: str,
        post: PlaylistPlayCapture | None,
        append_state: str = "confirmed",
        playback_state: str = "unknown",
        playback_start_returned: bool | None = None,
        evidence: dict[str, Any] | None = None,
        verification_outcome: str | None = None,
        cause: BaseException | None = None,
    ) -> None:
        error = _failure_diagnostics(
            phase=phase,
            expected_position=expected_position,
            append_state=append_state,
            playback_state=playback_state,
            append_invocation_returned=append_invocation_returned,
            playback_start_invocation_returned=(
                playback_start_invocation_returned
                if playback_start_returned is None
                else playback_start_returned
            ),
            append_count=append_count,
            playback_start_count=playback_start_count,
            post=post,
            post_write_capture_evidence=evidence,
            verification_outcome=verification_outcome,
        )
        if cause is None:
            raise error
        raise error from cause

    try:
        position = append_and_start_playlist(
            before.coordinator,
            before.playlist,
            expected_first_position=expected_position,
            mutation_started_callback=mutation_started_callback,
        )
        playback_start_count = 1
    except PlaylistPlayStepError as exc:
        if exc.phase == "append_playlist":
            append_invocation_returned = exc.invocation_returned
            capture_status: dict[str, Any] = {}
            post = _post_capture(
                speaker,
                playlist_id,
                acceptable=lambda candidate: (
                    verification.append_state_from_queue_evidence(before, candidate, capture_status)
                    == "confirmed"
                ),
                failed_predicates=lambda candidate: verification.append_verification_failures(
                    before, candidate
                ),
                capture_status=capture_status,
            )
            append_state = exc.append_state
            if append_state == "unknown":
                append_state = verification.append_state_from_queue_evidence(
                    before,
                    post,
                    capture_status,
                )
            reject(
                phase=exc.phase,
                append_state=append_state,
                playback_state="absent",
                post=post,
                playback_start_returned=False,
                evidence=capture_status["postWriteCaptureEvidence"],
                cause=exc,
            )

        playback_start_count = 1
        playback_start_invocation_returned = False
        lost_playback_error = exc
        position = exc.position or expected_position

    capture_status = {}
    post = _post_capture(
        speaker,
        playlist_id,
        acceptable=lambda candidate: (
            not verification.approved_verification_failures(
                before, candidate, expected_state, expected_position, position
            )
        ),
        failed_predicates=lambda candidate: verification.approved_verification_failures(
            before,
            candidate,
            expected_state,
            expected_position,
            position,
        ),
        prepare_retry=lambda candidate, started, clock: _prepare_playback_retry(
            candidate,
            started,
            clock,
            before=before,
            expected_state=expected_state,
            expected_position=expected_position,
            position=position,
            capture_status=capture_status,
        ),
        capture_status=capture_status,
        playback_verification=True,
    )

    def mark_complete_capture_failure(reason: str) -> str | None:
        convergence = capture_status.get("postWriteCaptureEvidence", {}).get("convergence", {})
        if convergence.get("playingObserved") is not True:
            return None
        convergence["completeCaptureAuthoritative"] = False
        convergence["finalReason"] = reason
        capture_status["verificationOutcome"] = "inconclusive"
        return "inconclusive"

    if post is None:
        reject(
            phase=lost_playback_error.phase if lost_playback_error else "verify_queue",
            post=None,
            evidence=capture_status["postWriteCaptureEvidence"],
            verification_outcome=mark_complete_capture_failure("completeCaptureFailed")
            or capture_status.get("verificationOutcome"),
        )
    queue_matches = not verification.queue_verification_failures(
        before, post, expected_state, expected_position, position
    )
    if not queue_matches:
        reject(
            phase=lost_playback_error.phase if lost_playback_error else "verify_queue",
            post=post,
            evidence=capture_status["postWriteCaptureEvidence"],
            verification_outcome=mark_complete_capture_failure("completeCaptureMismatch")
            or capture_status.get("verificationOutcome"),
        )

    playback_matches = not verification.playback_verification_failures(
        before, post, expected_position
    )
    if not playback_matches:
        reject(
            phase=lost_playback_error.phase if lost_playback_error else "verify_playback",
            post=post,
            evidence=capture_status["postWriteCaptureEvidence"],
            verification_outcome=mark_complete_capture_failure("completeCaptureMismatch")
            or capture_status.get("verificationOutcome"),
        )

    approved_playlist = expected_state["playlist"]
    approved_queue = expected_state["queue"]
    appended_items = post.queue_items[approved_queue["length"] :]
    return authoritative_playlist_play_result(
        room=post.state["room"],
        topology=post.state["topology"],
        playlist=post.state["playlist"],
        before_length=approved_queue["length"],
        after_length=post.state["queue"]["length"],
        expected_position=expected_position,
        current_position=post.state["queue"]["currentPosition"],
        appended_item_count=approved_playlist["itemCount"],
        appended_segment_fingerprint=_content_fingerprint(appended_items),
        current_item=before.playlist_items[0],
        append_invocation_returned=append_invocation_returned,
        playback_start_invocation_returned=playback_start_invocation_returned,
        post_write_capture_evidence=capture_status["postWriteCaptureEvidence"],
    )
