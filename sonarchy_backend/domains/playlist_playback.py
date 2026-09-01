from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .common import clean, safe_index
from .errors import PlanConflictError, PlaylistPlayTransactionError
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


def _content_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        item["identity"],
        item["title"],
        item["artist"],
        item["album"],
        item["duration"],
    )


def _content_fingerprint(items: tuple[dict[str, Any], ...]) -> str:
    return _fingerprint([_content_key(item) for item in items])


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
    source = _source(coordinator)
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
    return PlaylistPlayCapture(
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
    playback_started: bool,
    append_count: int,
    playback_start_count: int,
    post: PlaylistPlayCapture | None,
) -> PlaylistPlayTransactionError:
    diagnostics: dict[str, Any] = {
        "appendState": append_state,
        "playbackStarted": playback_started,
        "queueRollbackAttempted": False,
        "appendInvocationCount": append_count,
        "playbackStartInvocationCount": playback_start_count,
        "retryCount": 0,
        "expectedFirstAppendedPosition": expected_position,
        "succeeded": False,
    }
    if post is not None:
        diagnostics.update(
            observedQueueLength=post.state["queue"]["length"],
            observedQueueFingerprint=post.state["queue"]["contentFingerprint"],
            observedCurrentPosition=post.state["queue"]["currentPosition"],
            observedTransport=post.state["room"]["transport"],
            observedSource=post.state["room"]["source"],
        )
        if playback_start_count == 1:
            playback_started = (
                post.state["room"]["transport"] == "PLAYING"
                and post.state["room"]["source"] == "QUEUE"
                and post.state["queue"]["currentPosition"] == expected_position
            )
            diagnostics["playbackStarted"] = playback_started
    return PlaylistPlayTransactionError(phase=phase, diagnostics=diagnostics)


def _append_state_from_queue_evidence(
    before: PlaylistPlayCapture,
    post: PlaylistPlayCapture | None,
) -> str:
    if post is None:
        return "unknown"
    before_items = tuple(map(_content_key, before.queue_items))
    post_items = tuple(map(_content_key, post.queue_items))
    if post_items == before_items:
        return "absent"
    playlist_items = tuple(map(_content_key, before.playlist_items))
    if post_items == before_items + playlist_items:
        return "confirmed"
    return "unknown"


def _post_capture(speaker: Any, playlist_id: str) -> PlaylistPlayCapture | None:
    try:
        return capture_playlist_play_target(
            speaker,
            playlist_id,
            enforce_preflight_policy=False,
        )
    except Exception:  # noqa: BLE001 - partial-state reporting must stay bounded
        return None


def _stable_room(room: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in room.items() if key not in {"transport", "source"}}


def execute_preflighted_playlist_play(
    speaker: Any,
    plan: dict[str, Any],
    *,
    mutation_started_callback: Callable[[], None] | None = None,
) -> dict[str, Any]:
    if plan.get("operation") != "playlists.play.execute":
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
            playback_started=False,
            append_count=0,
            playback_start_count=0,
            post=None,
        ) from exc
    if before.state != expected_state or expected_position < 1:
        raise _failure_diagnostics(
            phase="preflight_revalidation",
            expected_position=max(0, expected_position),
            append_state="absent",
            playback_started=False,
            append_count=0,
            playback_start_count=0,
            post=before,
        )

    append_count = 1
    playback_start_count = 0
    try:
        position = append_and_start_playlist(
            before.coordinator,
            before.playlist,
            expected_first_position=expected_position,
            mutation_started_callback=mutation_started_callback,
        )
        playback_start_count = 1
    except PlaylistPlayStepError as exc:
        post = _post_capture(speaker, playlist_id)
        append_state = exc.append_state
        if exc.phase == "append_playlist" and append_state == "unknown":
            append_state = _append_state_from_queue_evidence(before, post)
        if append_state == "confirmed":
            playback_start_count = 1 if exc.phase == "start_playback" else 0
        raise _failure_diagnostics(
            phase=exc.phase,
            expected_position=expected_position,
            append_state=append_state,
            playback_started=exc.playback_started,
            append_count=append_count,
            playback_start_count=playback_start_count,
            post=post,
        ) from exc

    post = _post_capture(speaker, playlist_id)
    if post is None:
        raise _failure_diagnostics(
            phase="verify_queue",
            expected_position=expected_position,
            append_state="confirmed",
            playback_started=True,
            append_count=append_count,
            playback_start_count=playback_start_count,
            post=None,
        )
    approved_playlist = expected_state["playlist"]
    approved_queue = expected_state["queue"]
    stable_state_matches = (
        _stable_room(post.state["room"]) == _stable_room(expected_state["room"])
        and post.state["topology"] == expected_state["topology"]
        and post.state["playlist"] == approved_playlist
    )
    expected_after_length = approved_queue["length"] + approved_playlist["itemCount"]
    prefix_matches = tuple(
        map(_content_key, post.queue_items[: approved_queue["length"]])
    ) == tuple(map(_content_key, before.queue_items))
    appended_items = post.queue_items[approved_queue["length"] :]
    appended_matches = tuple(map(_content_key, appended_items)) == tuple(
        map(_content_key, before.playlist_items)
    )
    queue_matches = (
        stable_state_matches
        and post.state["queue"]["length"] == expected_after_length
        and prefix_matches
        and appended_matches
        and position == expected_position
    )
    if not queue_matches:
        raise _failure_diagnostics(
            phase="verify_queue",
            expected_position=expected_position,
            append_state="confirmed",
            playback_started=True,
            append_count=append_count,
            playback_start_count=playback_start_count,
            post=post,
        )

    first_item = before.playlist_items[0]
    current_queue_item = post.queue_items[expected_position - 1]
    current_metadata_matches = post.current_track == {
        "title": first_item["title"],
        "artist": first_item["artist"],
        "album": first_item["album"],
    }
    playback_matches = (
        post.state["room"]["transport"] == "PLAYING"
        and post.state["room"]["source"] == "QUEUE"
        and post.state["queue"]["currentPosition"] == expected_position
        and _content_key(current_queue_item) == _content_key(first_item)
        and current_metadata_matches
    )
    if not playback_matches:
        raise _failure_diagnostics(
            phase="verify_playback",
            expected_position=expected_position,
            append_state="confirmed",
            playback_started=True,
            append_count=append_count,
            playback_start_count=playback_start_count,
            post=post,
        )

    return {
        "ok": True,
        "action": "play-exact-sonos-playlist",
        "room": copy.deepcopy(post.state["room"]),
        "topology": copy.deepcopy(post.state["topology"]),
        "playlist": copy.deepcopy(post.state["playlist"]),
        "queue": {
            "beforeLength": approved_queue["length"],
            "afterLength": post.state["queue"]["length"],
            "expectedFirstAppendedPosition": expected_position,
            "currentPosition": post.state["queue"]["currentPosition"],
            "appendedItemCount": approved_playlist["itemCount"],
            "appendedSegmentFingerprint": _content_fingerprint(appended_items),
            "existingEntriesPreserved": True,
        },
        "playback": {
            "transport": "PLAYING",
            "source": "QUEUE",
            "currentItem": copy.deepcopy(first_item),
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
        "retryCount": 0,
        "substitutionCount": 0,
    }
