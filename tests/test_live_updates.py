import io
from types import SimpleNamespace
from unittest.mock import Mock, patch

import soco.events as events

from sonarchy_backend.live_updates import (
    MAX_EVENT_BODY_BYTES,
    MAX_EVENT_CONNECTIONS,
    MAX_PENDING_EVENTS,
    EventSubscriptionManager,
    WakeQueue,
)


class FakeSubscription:
    def __init__(self):
        self.auto_renew_fail = None
        self.unsubscribed = False
        self.is_subscribed = True
        self.time_left = 300

    def unsubscribe(self, strict=True):
        self.unsubscribed = True
        self.is_subscribed = False


class FakeService:
    def __init__(self, fail=False):
        self.fail = fail
        self.subscription = None
        self.subscribe_calls = 0

    def subscribe(self, **kwargs):
        self.subscribe_calls += 1
        if self.fail:
            raise OSError("callback blocked")
        self.subscription = FakeSubscription()
        self.kwargs = kwargs
        return self.subscription


def test_event_subscriptions_reconcile_and_clean_up():
    event_queue = WakeQueue()
    manager = EventSubscriptionManager(event_queue)
    topology = FakeService()
    transport = FakeService()
    try:
        diagnostics = manager.reconcile({"topology": topology, "transport:R1": transport})
        assert diagnostics["mode"] == "events"
        assert diagnostics["subscribed"] == 2
        topology.kwargs["event_queue"].put(object())
        tagged_event = event_queue.drain_items()[0]
        assert tagged_event["subscriptionKey"] == "topology"
        assert topology.kwargs["auto_renew"] is True
        assert topology.kwargs["requested_timeout"] == 300

        manager.reconcile({"topology": topology})
        assert transport.subscription.unsubscribed is True
    finally:
        manager.close()


def test_subscription_failure_keeps_polling_fallback():
    event_queue = WakeQueue()
    manager = EventSubscriptionManager(event_queue)
    try:
        diagnostics = manager.reconcile(
            {"topology": FakeService(), "transport:R1": FakeService(fail=True)}
        )
        assert diagnostics["mode"] == "polling"
        assert diagnostics["subscribed"] == 1
        assert diagnostics["requested"] == 2
        assert "callback blocked" in diagnostics["errors"][0]
    finally:
        manager.close()


def test_auto_renew_failure_replaces_dead_subscription_immediately():
    event_queue = WakeQueue()
    manager = EventSubscriptionManager(event_queue)
    transport = FakeService()
    try:
        manager.reconcile({"transport:R1": transport})
        failed = transport.subscription
        failed.auto_renew_fail(OSError("renewal timed out"))

        assert manager.complete is False
        assert event_queue.drain() == 1

        diagnostics = manager.reconcile({"transport:R1": transport})
        assert failed.unsubscribed is True
        assert transport.subscribe_calls == 2
        assert transport.subscription is not failed
        assert diagnostics["mode"] == "events"
    finally:
        manager.close()


def test_wake_queue_notifies_and_drains_event_bursts():
    event_queue = WakeQueue()
    try:
        event_queue.put(object())
        event_queue.put(object())
        assert event_queue.drain() == 2
    finally:
        event_queue.close()


def test_wake_queue_has_a_hard_memory_bound():
    event_queue = WakeQueue()
    try:
        for value in range(MAX_PENDING_EVENTS + 20):
            event_queue.put(value)
        assert event_queue.qsize() == MAX_PENDING_EVENTS
        assert event_queue.drain() == MAX_PENDING_EVENTS
    finally:
        event_queue.close()


def event_handler(content_length, body=b"<event/>", source="192.168.1.20"):
    handler = events.EventNotifyHandler.__new__(events.EventNotifyHandler)
    handler.client_address = (source, 12345)
    handler.headers = {
        "sid": "uuid:subscription",
        "seq": "1",
        "content-length": str(content_length),
    }
    handler.rfile = io.BytesIO(body)
    handler.send_error = Mock()
    handler.send_response = Mock()
    handler.end_headers = Mock()
    handler.handle_notification = Mock()
    return handler


def test_hardened_event_listener_bounds_connections_and_body_size():
    assert events.EventServer.request_queue_size == MAX_EVENT_CONNECTIONS
    handler = event_handler(MAX_EVENT_BODY_BYTES + 1)
    subscription = SimpleNamespace(
        service=SimpleNamespace(soco=SimpleNamespace(ip_address="192.168.1.20"))
    )
    with patch.object(events.subscriptions_map, "get_subscription", return_value=subscription):
        handler.do_NOTIFY()

    handler.send_error.assert_called_once_with(413, "Sonos event is too large")
    handler.handle_notification.assert_not_called()


def test_hardened_event_listener_rejects_malformed_subscription_headers():
    handler = event_handler(0, b"")
    handler.headers["seq"] = "not-a-sequence"
    with patch.object(events.subscriptions_map, "get_subscription") as lookup:
        handler.do_NOTIFY()

    handler.send_error.assert_called_once_with(412, "Invalid Sonos subscription headers")
    lookup.assert_not_called()
    handler.handle_notification.assert_not_called()


def test_hardened_event_listener_accepts_only_matching_subscribed_speaker():
    body = b"<event/>"
    handler = event_handler(len(body), body)
    subscription = SimpleNamespace(
        service=SimpleNamespace(soco=SimpleNamespace(ip_address="192.168.1.20"))
    )
    with patch.object(events.subscriptions_map, "get_subscription", return_value=subscription):
        handler.do_NOTIFY()

    handler.handle_notification.assert_called_once_with(handler.headers, body)
    handler.send_response.assert_called_once_with(200)
    handler.send_error.assert_not_called()

    spoofed = event_handler(len(body), body, source="192.168.1.99")
    with patch.object(events.subscriptions_map, "get_subscription", return_value=subscription):
        spoofed.do_NOTIFY()
    spoofed.send_error.assert_called_once_with(403, "Event source does not match subscription")
    spoofed.handle_notification.assert_not_called()
