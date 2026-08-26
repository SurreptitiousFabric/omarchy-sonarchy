from __future__ import annotations

import contextlib
import ipaddress
import logging
import os
import queue
import socket
import threading
from typing import Any

LOG = logging.getLogger(__name__)
SUBSCRIPTION_LEASE_SEC = 300
MAX_EVENT_BODY_BYTES = 512 * 1024
MAX_EVENT_CONNECTIONS = 16
EVENT_SOCKET_TIMEOUT_SEC = 3.0
MAX_EVENT_SID_CHARS = 160
MAX_EVENT_SEQUENCE_CHARS = 20
MAX_PENDING_EVENTS = 1024


def harden_soco_event_listener() -> None:
    """Bound and authenticate SoCo's LAN callback listener.

    Upstream SoCo intentionally exposes a general UPnP NOTIFY endpoint. This
    desktop integration can be stricter: every accepted event must come from
    the exact private IPv4 speaker associated with an active subscription.
    """

    import soco.events as events

    if getattr(events, "_omarchy_sonos_hardened", False):
        return

    original_server = events.EventServer
    original_handler = events.EventNotifyHandler

    class BoundedEventServer(original_server):
        daemon_threads = True
        request_queue_size = MAX_EVENT_CONNECTIONS

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._event_slots = threading.BoundedSemaphore(MAX_EVENT_CONNECTIONS)
            super().__init__(*args, **kwargs)

        def process_request(self, request: socket.socket, client_address: Any) -> None:
            if not self._event_slots.acquire(blocking=False):
                self.shutdown_request(request)
                return
            worker = threading.Thread(
                target=self._bounded_request,
                args=(request, client_address),
                daemon=True,
                name="sonos-event",
            )
            worker.start()

        def _bounded_request(self, request: socket.socket, client_address: Any) -> None:
            try:
                self.process_request_thread(request, client_address)
            finally:
                self._event_slots.release()

    class HardenedEventNotifyHandler(original_handler):
        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(EVENT_SOCKET_TIMEOUT_SEC)

        def _reject(self, status: int, message: str) -> None:
            self.close_connection = True
            self.send_error(status, message)

        def do_NOTIFY(self) -> None:  # noqa: N802 - HTTP verb hook
            try:
                source = ipaddress.ip_address(self.client_address[0])
            except ValueError:
                self._reject(403, "Invalid event source")
                return
            if (
                source.version != 4
                or not source.is_private
                or source.is_loopback
                or source.is_link_local
                or source.is_multicast
            ):
                self._reject(403, "Invalid event source")
                return

            sid = str(self.headers.get("sid", ""))
            sequence = str(self.headers.get("seq", ""))
            if (
                not sid
                or len(sid) > MAX_EVENT_SID_CHARS
                or any(ord(character) < 0x20 or ord(character) == 0x7F for character in sid)
                or not sequence.isascii()
                or not sequence.isdecimal()
                or len(sequence) > MAX_EVENT_SEQUENCE_CHARS
            ):
                self._reject(412, "Invalid Sonos subscription headers")
                return
            subscription = events.subscriptions_map.get_subscription(sid)
            subscription_service = getattr(subscription, "service", None)
            subscription_soco = getattr(subscription_service, "soco", None)
            expected_source = str(getattr(subscription_soco, "ip_address", ""))
            if subscription is None:
                self._reject(412, "Unknown Sonos subscription")
                return
            if str(source) != expected_source:
                self._reject(403, "Event source does not match subscription")
                return

            try:
                content_length = int(self.headers.get("content-length", ""))
            except ValueError:
                self._reject(411, "Valid Content-Length required")
                return
            if content_length < 0 or content_length > MAX_EVENT_BODY_BYTES:
                self._reject(413, "Sonos event is too large")
                return

            try:
                content = self.rfile.read(content_length)
                if len(content) != content_length:
                    self._reject(400, "Incomplete Sonos event")
                    return
                self.handle_notification(self.headers, content)
            except Exception:  # noqa: BLE001 - malformed LAN input is rejected
                self._reject(400, "Invalid Sonos event")
                return
            self.send_response(200)
            self.end_headers()

    events.EventServer = BoundedEventServer
    events.EventNotifyHandler = HardenedEventNotifyHandler
    events._omarchy_sonos_hardened = True


harden_soco_event_listener()


class WakeQueue(queue.Queue[Any]):
    """Thread-safe event queue which also wakes a select-based protocol loop."""

    def __init__(self) -> None:
        super().__init__(maxsize=MAX_PENDING_EVENTS)
        self.read_fd, self.write_fd = os.pipe()
        os.set_blocking(self.read_fd, False)
        os.set_blocking(self.write_fd, False)

    def put(self, item: Any, block: bool = True, timeout: float | None = None) -> None:
        try:
            # A refresh reads authoritative state, so dropping only the newest
            # redundant wake-up is safer than allowing hostile LAN traffic to
            # grow the desktop process without a bound.
            super().put(item, block=False)
        except queue.Full:
            return
        with contextlib.suppress(BlockingIOError, OSError):
            os.write(self.write_fd, b"\0")

    def drain_items(self) -> list[Any]:
        while True:
            try:
                os.read(self.read_fd, 4096)
            except BlockingIOError:
                break
        items: list[Any] = []
        while True:
            try:
                items.append(self.get_nowait())
            except queue.Empty:
                return items

    def drain(self) -> int:
        return len(self.drain_items())

    def close(self) -> None:
        os.close(self.read_fd)
        os.close(self.write_fd)


class TaggedEventQueue:
    """Attach the subscription identity without touching SoCo callback threads."""

    def __init__(self, target: WakeQueue, subscription_key: str) -> None:
        self.target = target
        self.subscription_key = subscription_key

    def put(self, item: Any, block: bool = True, timeout: float | None = None) -> None:
        self.target.put(
            {"subscriptionKey": self.subscription_key, "event": item},
            block=block,
            timeout=timeout,
        )


class EventSubscriptionManager:
    def __init__(self, event_queue: WakeQueue) -> None:
        self.event_queue = event_queue
        self.subscriptions: dict[str, Any] = {}
        self.errors: list[str] = []
        self.complete = False
        self._invalid: set[str] = set()
        self._lock = threading.RLock()

    def reconcile(self, services: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            desired = set(services)
            for key, subscription in list(self.subscriptions.items()):
                healthy = bool(getattr(subscription, "is_subscribed", True))
                time_left = getattr(subscription, "time_left", None)
                if time_left is not None and time_left <= 0:
                    healthy = False
                if key not in desired or key in self._invalid or not healthy:
                    self._unsubscribe(key)
            self._invalid.clear()

            self.errors = []
            for key, service in services.items():
                if key in self.subscriptions:
                    continue
                try:
                    subscription = service.subscribe(
                        requested_timeout=SUBSCRIPTION_LEASE_SEC,
                        auto_renew=True,
                        event_queue=TaggedEventQueue(self.event_queue, key),
                        strict=True,
                    )
                    subscription.auto_renew_fail = lambda exc, subscription_key=key: (
                        self._auto_renew_failed(subscription_key, exc)
                    )
                    self.subscriptions[key] = subscription
                except Exception as exc:  # noqa: BLE001 - network fallback is intentional
                    message = f"{key}: {type(exc).__name__}: {exc}"
                    self.errors.append(message)
                    LOG.warning("Sonos event subscription failed: %s", message)

        listener = ""
        try:
            from soco.events import event_listener

            if event_listener.is_running:
                host, port = event_listener.address
                listener = f"{host}:{port}"
        except Exception as exc:  # noqa: BLE001
            self.errors.append(f"listener: {type(exc).__name__}: {exc}")

        with self._lock:
            self.complete = (
                bool(services) and not self._invalid and len(self.subscriptions) == len(services)
            )
            subscribed = len(self.subscriptions)
        return {
            "mode": "events" if self.complete else "polling",
            "listener": listener,
            "subscribed": subscribed,
            "requested": len(services),
            "errors": list(self.errors),
        }

    def _auto_renew_failed(self, key: str, exc: Exception) -> None:
        message = f"{key} auto-renew: {type(exc).__name__}: {exc}"
        with self._lock:
            self.errors.append(message)
            self._invalid.add(key)
            self.complete = False
        LOG.warning("Sonos event subscription renewal failed: %s", message)
        # Wake the protocol loop immediately so reconcile can replace the dead
        # subscription instead of waiting for the next background poll.
        self.event_queue.put({"type": "subscription-renewal-failed", "key": key})

    def _unsubscribe(self, key: str) -> None:
        with self._lock:
            subscription = self.subscriptions.pop(key, None)
        if subscription is None:
            return
        try:
            # A synchronous UNSUBSCRIBE can block once per Sonos service and
            # make shell reloads take minutes. Cancel locally; the short lease
            # expires on the speaker even if the process disappears.
            cancel = getattr(subscription, "_cancel_subscription", None)
            if callable(cancel):
                cancel("Sonos local subscription shutdown")
            else:
                subscription.unsubscribe(strict=False)
        except Exception as exc:  # noqa: BLE001
            LOG.debug("Could not unsubscribe %s: %s", key, exc)

    def close(self) -> None:
        with self._lock:
            for key in list(self.subscriptions):
                self._unsubscribe(key)
        self.event_queue.close()
        self.complete = False
