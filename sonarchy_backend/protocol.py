from __future__ import annotations

import copy
import json
import logging
import select
import sys
import time
from typing import Any, TextIO

from sonarchy_errors import user_facing_error

from .contracts import (
    PROTOCOL_VERSION,
    ProtocolRequestError,
    error_payload,
    parse_request,
    result_payload,
    snapshot_capabilities,
)
from .controller import ControllerError, SonosController
from .domains import SonarchyApplication
from .domains.errors import SafeDomainError
from .live_updates import EventSubscriptionManager, WakeQueue

LOG = logging.getLogger(__name__)
EVENT_BURST_SEC = 0.075
EVENT_PANEL_POLL_SEC = 5.0
EVENT_BACKGROUND_POLL_SEC = 15.0
FALLBACK_PANEL_POLL_SEC = 2.0
FALLBACK_BACKGROUND_POLL_SEC = 5.0
MAX_PROTOCOL_LINE_BYTES = 64 * 1024
PROTOCOL_OPERATIONS = frozenset(
    {
        "alarms.list",
        "artwork.radio.resolve",
        "playback.toggle",
        "playback.play",
        "playback.pause",
        "playback.next",
        "playback.previous",
        "playback.seek",
        "content.favorite.play",
        "content.favorites.refresh",
        "content.browse",
        "playback.room.move",
        "selection.group.set",
        "selection.room.set",
        "volume.group.set",
        "volume.group.adjust",
        "mute.group.set",
        "volume.room.set",
        "volume.room.adjust",
        "mute.room.set",
        "topology.members.set",
        "devices.details.get",
        "playback.stop",
        "devices.rename",
        "playback.option.set",
        "sound.setting.set",
        "devices.setting.set",
        "sources.switch",
        "queue.item.play",
        "queue.item.move",
        "queue.item.remove",
        "queue.clear",
        "queue.content.enqueue",
        "playlists.mutate",
        "playlist_plan.apple.validate",
        "playlists.apple.create",
        "playlists.track.mutate",
        "content.apple.play",
        "content.apple.album.play",
        "content.global.play",
        "library.update.start",
        "alarms.save",
        "alarms.toggle",
        "alarms.delete",
    }
)


class ProtocolServer:
    def __init__(self, controller: SonosController) -> None:
        self.application = SonarchyApplication(controller)
        self.panel_open = False
        self.last_refresh = 0.0
        self.revision = 0
        self.last_snapshot: dict[str, Any] | None = None
        self.event_queue = WakeQueue()
        self.event_subscriptions = EventSubscriptionManager(self.event_queue)

    def _emit(self, payload: dict[str, Any], output: TextIO) -> None:
        output.write(json.dumps(payload, separators=(",", ":")) + "\n")
        output.flush()

    def emit_snapshot(self, output: TextIO, *, rediscover: bool = True) -> None:
        try:
            snapshot = self.application.refresh(rediscover=rediscover)
            diagnostics = self.event_subscriptions.reconcile(self.application.event_services())
            snapshot.setdefault("status", {})["liveUpdates"] = diagnostics
            self.last_snapshot = copy.deepcopy(snapshot)
        except Exception as exc:
            LOG.exception("Sonos refresh failed")
            refresh_error = error_payload(
                "network_error" if isinstance(exc, OSError) else "internal_error",
                "Sonos state is temporarily unavailable. Try refreshing in a moment.",
                operation="state.refresh",
                retryable=True,
            )
            if self.last_snapshot is not None:
                snapshot = copy.deepcopy(self.last_snapshot)
                status = snapshot.setdefault("status", {})
                status["state"] = "ready" if status.get("state") == "ready" else "error"
                status["message"] = refresh_error["message"]
                status["error"] = refresh_error
                status["degraded"] = True
                status["lastRefreshEpochMs"] = int(time.time() * 1000)
                snapshot.setdefault("playback", {})["stale"] = True
                snapshot["playback"]["metadataState"] = "cached"
            else:
                snapshot = {
                    "type": "snapshot",
                    "version": 1,
                    "status": {
                        "state": "error",
                        "message": refresh_error["message"],
                        "error": refresh_error,
                        "lastRefreshEpochMs": int(time.time() * 1000),
                    },
                    "selectedAnchorRoomUid": "",
                    "targetGroupUid": "",
                    "households": [],
                    "target": None,
                    "favorites": {
                        "state": "not_loaded",
                        "items": [],
                        "total": 0,
                        "unsupported": 0,
                        "error": "",
                    },
                    "playback": {
                        "state": "STOPPED",
                        "title": "",
                        "artist": "",
                        "album": "",
                        "artworkUrl": "",
                        "artworkKind": "",
                        "source": "UNKNOWN",
                        "positionSec": None,
                        "durationSec": None,
                        "availableActions": [],
                        "metadataState": "empty",
                        "stale": False,
                    },
                }
        self.revision += 1
        snapshot["type"] = "snapshot"
        snapshot["version"] = PROTOCOL_VERSION
        snapshot["revision"] = self.revision
        snapshot["capabilities"] = snapshot_capabilities(snapshot)
        self.last_refresh = time.monotonic()
        self._emit(snapshot, output)

    def handle(self, request: dict[str, Any], output: TextIO) -> None:
        try:
            parsed = parse_request(request)
        except ProtocolRequestError as exc:
            self._emit_error(
                output,
                request_id=exc.request_id,
                code=exc.code,
                message=str(exc),
                operation=exc.operation,
            )
            return
        request_id = parsed.request_id
        op = parsed.operation
        args = parsed.args

        if op == "session.panel_open.set":
            self.panel_open = bool(args.get("open", False))
            self._emit(result_payload(request_id, revision=self.revision), output)
            return

        if op == "state.refresh":
            self._emit(result_payload(request_id, revision=self.revision), output)
            self.emit_snapshot(output)
            return

        if self.application.operations != PROTOCOL_OPERATIONS:
            raise RuntimeError("Protocol operation inventory is out of sync")
        if op not in self.application.operations:
            self._emit_error(
                output,
                request_id=request_id,
                code="unsupported_operation",
                message=f"Unknown operation: {op}",
                operation=op,
            )
            return

        refresh_after = self.application.mutates(op)
        try:
            value = self.application.execute(op, args, backend_revision=self.revision)
            self._emit(result_payload(request_id, revision=self.revision, value=value), output)
        except SafeDomainError as exc:
            LOG.warning("Sonarchy operation %s was safely rejected: %s", op, exc.code)
            self._emit_error(
                output,
                request_id=request_id,
                code=exc.code,
                message=str(exc),
                operation=op,
                retryable=exc.retryable,
                details=exc.details,
            )
        except (ControllerError, ValueError, TypeError, OSError) as exc:
            LOG.warning("Sonos command %s failed: %s", op, exc)
            if isinstance(exc, (ValueError, TypeError)):
                code = "invalid_argument"
            elif isinstance(exc, OSError):
                code = "network_error"
            else:
                code = "speaker_rejected"
            self._emit_error(
                output,
                request_id=request_id,
                code=code,
                message=(
                    "A Sonos speaker could not be reached. Check the network and try again."
                    if isinstance(exc, OSError)
                    else user_facing_error(exc)
                ),
                operation=op,
                retryable=isinstance(exc, OSError),
            )
        except Exception:
            LOG.exception("Unhandled Sonos command error")
            self._emit_error(
                output,
                request_id=request_id,
                code="internal_error",
                message="Sonos could not complete that action",
                operation=op,
            )
        finally:
            # Mutations are followed by authoritative state, including partial
            # failures, so the QML never has to pretend its optimistic view won.
            if refresh_after:
                self.emit_snapshot(output, rediscover=False)

    def _emit_error(
        self,
        output: TextIO,
        *,
        request_id: str,
        code: str,
        message: str,
        operation: str = "",
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        error = error_payload(
            code,
            message,
            operation=operation,
            retryable=retryable,
            details=details,
        )
        self._emit(result_payload(request_id, revision=self.revision, error=error), output)

    def serve(self, input_stream: TextIO = sys.stdin, output: TextIO = sys.stdout) -> None:
        pending_event_at: float | None = None
        pending_topology_households: set[str] = set()
        try:
            self.emit_snapshot(output)
            while True:
                live = self.event_subscriptions.complete
                interval = (
                    (EVENT_PANEL_POLL_SEC if self.panel_open else EVENT_BACKGROUND_POLL_SEC)
                    if live
                    else (
                        FALLBACK_PANEL_POLL_SEC if self.panel_open else FALLBACK_BACKGROUND_POLL_SEC
                    )
                )
                now = time.monotonic()
                poll_timeout = max(0.0, interval - (now - self.last_refresh))
                if pending_event_at is not None:
                    poll_timeout = min(poll_timeout, max(0.0, pending_event_at - now))
                readable, _, _ = select.select(
                    [input_stream, self.event_queue.read_fd], [], [], poll_timeout
                )
                now = time.monotonic()
                if self.event_queue.read_fd in readable:
                    for event in self.event_queue.drain_items():
                        if not isinstance(event, dict):
                            continue
                        key = str(event.get("subscriptionKey", ""))
                        if key.startswith("topology:"):
                            pending_topology_households.add(key.removeprefix("topology:"))
                    pending_event_at = now + EVENT_BURST_SEC
                if pending_event_at is not None and now >= pending_event_at:
                    pending_event_at = None
                    if pending_topology_households:
                        self.application.refresh_event_topologies(pending_topology_households)
                        pending_topology_households.clear()
                    self.emit_snapshot(output, rediscover=False)
                    continue
                if not readable:
                    self.emit_snapshot(output)
                    continue
                if input_stream not in readable:
                    continue
                line = input_stream.readline(MAX_PROTOCOL_LINE_BYTES + 1)
                if line == "":
                    return
                if len(line.encode("utf-8")) > MAX_PROTOCOL_LINE_BYTES:
                    while line and not line.endswith("\n"):
                        line = input_stream.readline(MAX_PROTOCOL_LINE_BYTES + 1)
                    self._emit_error(
                        output,
                        request_id="",
                        code="invalid_request",
                        message="Protocol message is too large",
                    )
                    continue
                if not line.strip():
                    continue
                try:
                    request = json.loads(line)
                except json.JSONDecodeError as exc:
                    self._emit_error(
                        output,
                        request_id="",
                        code="invalid_request",
                        message=f"Invalid JSON: {exc.msg}",
                    )
                    continue
                if not isinstance(request, dict):
                    self._emit_error(
                        output,
                        request_id="",
                        code="invalid_request",
                        message="Protocol message must be a JSON object",
                    )
                    continue
                self.handle(request, output)
        finally:
            self.event_subscriptions.close()
