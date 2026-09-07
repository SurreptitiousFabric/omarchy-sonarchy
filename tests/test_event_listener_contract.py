"""Pinned SoCo contracts; no bound listener, live subscription or speaker I/O.

Binding and listener-thread startup are disabled. Accepted-peer metadata, speaker
cache updates and worker scheduling are synthetic; HTTP parsing, hardening, the
SoCo registry and event delivery are real.
"""

import inspect
import socket
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import soco
import soco.events as events

from sonarchy_backend.live_updates import (
    EVENT_SOCKET_TIMEOUT_SEC,
    MAX_EVENT_BODY_BYTES,
    MAX_EVENT_CONNECTIONS,
    harden_soco_event_listener,
)


@pytest.fixture(autouse=True)
def forbid_network_and_live_subscriptions(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("contract tests must not bind, connect or subscribe")

    for operation in ("bind", "listen", "connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, operation, forbidden)
    monkeypatch.setattr(events.Subscription, "subscribe", forbidden)


def assert_contract():
    assert soco.__version__ == "0.31.2", "review contracts before changing the pinned SoCo version"
    for hook in (events.EventServer, events.EventNotifyHandler):
        assert hook.__module__ == "sonarchy_backend.live_updates", "hardening hook was bypassed"
    assert list(inspect.signature(events.EventNotifyHandler.handle_notification).parameters) == [
        "self",
        "headers",
        "content",
    ], "SoCo notification signature drifted"
    assert list(inspect.signature(events.SubscriptionsMap.get_subscription).parameters) == [
        "self",
        "sid",
    ], "SoCo subscription lookup signature drifted"


def test_pinned_hooks_are_installed_and_idempotent():
    assert_contract()
    server, handler = events.EventServer, events.EventNotifyHandler
    harden_soco_event_listener()
    assert (events.EventServer, events.EventNotifyHandler) == (server, handler)


def test_signature_drift_fails_contract(monkeypatch):
    monkeypatch.setattr(
        events.EventNotifyHandler, "handle_notification", lambda self, payload: None
    )
    with pytest.raises(AssertionError, match="notification signature drifted"):
        assert_contract()


@pytest.mark.parametrize("hook", ["EventServer", "EventNotifyHandler"])
def test_unhardened_hook_drift_fails_contract(monkeypatch, hook):
    monkeypatch.setattr(events, hook, getattr(events, hook).__bases__[0])
    with pytest.raises(AssertionError, match="hardening hook was bypassed"):
        assert_contract()


def test_subscription_lookup_signature_drift_fails_contract(monkeypatch):
    monkeypatch.setattr(events.SubscriptionsMap, "get_subscription", lambda self, token: None)
    with pytest.raises(AssertionError, match="subscription lookup signature drifted"):
        assert_contract()


def test_version_drift_requires_contract_review(monkeypatch):
    monkeypatch.setattr(soco, "__version__", "fixture-unreviewed-version")
    with pytest.raises(AssertionError, match="changing the pinned SoCo version"):
        assert_contract()


def test_actual_listener_constructs_hardened_server_without_binding(monkeypatch):
    server_class = events.EventServer
    constructed = []

    def unbound_server(address, handler):
        assert handler is events.EventNotifyHandler
        result = server_class(address, handler, bind_and_activate=False)
        constructed.append(result)
        return result

    monkeypatch.setattr(events, "EventServer", unbound_server)
    monkeypatch.setattr(events.EventServerThread, "start", lambda self: None)
    listener = events.EventListener()
    listener.requested_port_number = 0
    try:
        assert listener.listen("127.0.0.1") == 0
        assert len(constructed) == 1
        assert listener._listener_thread.server is constructed[0]
        assert constructed[0].socket.getsockname()[1] == 0
        assert constructed[0].RequestHandlerClass is events.EventNotifyHandler
    finally:
        for server in constructed:
            server.server_close()


def test_connection_cap_and_release_after_handler_failure(monkeypatch):
    server = events.EventServer(
        ("127.0.0.1", 0), events.EventNotifyHandler, bind_and_activate=False
    )
    workers = []

    class Worker:
        def __init__(self, *, target, args, **kwargs):
            self.target, self.args = target, args
            workers.append(self)

        def start(self):
            pass

    monkeypatch.setattr("sonarchy_backend.live_updates.threading.Thread", Worker)
    server.shutdown_request = Mock()
    server.process_request_thread = Mock(side_effect=RuntimeError("fixture failure"))
    try:
        for _ in range(MAX_EVENT_CONNECTIONS):
            server.process_request(object(), ("127.0.0.1", 0))
        overflow = object()
        server.process_request(overflow, ("127.0.0.1", 0))
        assert len(workers) == MAX_EVENT_CONNECTIONS
        server.shutdown_request.assert_called_once_with(overflow)
        with pytest.raises(RuntimeError, match="fixture failure"):
            workers[0].target(*workers[0].args)
        server.process_request(object(), ("127.0.0.1", 0))
        assert len(workers) == MAX_EVENT_CONNECTIONS + 1
        server.process_request_thread.side_effect = None
        for worker in workers[1:]:
            worker.target(*worker.args)
        for _ in range(MAX_EVENT_CONNECTIONS):
            assert server._event_slots.acquire(blocking=False)
        assert not server._event_slots.acquire(blocking=False)
    finally:
        server.server_close()


@pytest.fixture
def subscription(monkeypatch):
    registry = events.SubscriptionsMap()
    monkeypatch.setattr(events, "subscriptions_map", registry)
    service = SimpleNamespace(
        soco=SimpleNamespace(ip_address="192.168.1.20"),
        service_id="urn:upnp-org:serviceId:RenderingControl",
        _update_cache_on_event=Mock(),
    )
    result = events.Subscription(service)
    result.sid = "uuid:fixture-subscription"
    # Populate real weak registry without registering an atexit unsubscribe.
    with registry.subscriptions_lock:
        registry.subscriptions[result.sid] = result
    return result


def notify(body, length, sid="uuid:fixture-subscription", source="192.168.1.20"):
    headers = ["NOTIFY / HTTP/1.0", f"SID: {sid}", "SEQ: 1"]
    if length is not None:
        headers.append(f"Content-Length: {length}")
    pair = socket.socketpair()
    with pair[0] as server_socket, pair[1] as client_socket:
        client_socket.settimeout(2)
        client_socket.sendall(("\r\n".join(headers) + "\r\n\r\n").encode() + body)
        client_socket.shutdown(socket.SHUT_WR)
        # Synthetic accepted peer metadata is the only source-address fixture;
        # the transport is AF_UNIX and never exposes a LAN port.
        events.EventNotifyHandler(server_socket, (source, 12345), SimpleNamespace())
        assert server_socket.gettimeout() == EVENT_SOCKET_TIMEOUT_SEC
        return client_socket.recv(8192).split(b"\r\n", 1)[0]


def test_real_http_notify_parses_event_and_delivers_to_subscription(subscription):
    body = (
        b'<e:propertyset xmlns:e="urn:schemas-upnp-org:event-1-0">'
        b"<e:property><Volume>17</Volume></e:property></e:propertyset>"
    )
    assert b" 200 " in notify(body, len(body))
    event = subscription.events.get_nowait()
    assert event.sid == subscription.sid
    assert event.variables == {"volume": "17"}
    subscription.service._update_cache_on_event.assert_called_once_with(event)
    assert subscription.events.empty()


@pytest.mark.parametrize(
    "body,length,sid,status",
    [
        (b"", None, "uuid:fixture-subscription", 411),
        (b"", "bad", "uuid:fixture-subscription", 411),
        (b"", -1, "uuid:fixture-subscription", 413),
        (b"", MAX_EVENT_BODY_BYTES + 1, "uuid:fixture-subscription", 413),
        (b"short", 10, "uuid:fixture-subscription", 400),
        (b"not xml", 7, "uuid:fixture-subscription", 400),
        (b"", 0, "uuid:unknown", 412),
    ],
)
def test_real_http_rejects_invalid_notifications(subscription, body, length, sid, status):
    assert f" {status} ".encode() in notify(body, length, sid)
    assert subscription.events.empty()
    subscription.service._update_cache_on_event.assert_not_called()


@pytest.mark.parametrize(
    "source",
    ["192.168.1.99", "127.0.0.1", "169.254.1.1", "224.0.0.1", "8.8.8.8", "::1", "invalid"],
)
def test_real_http_rejects_nonmatching_or_loopback_source(subscription, source):
    assert b" 403 " in notify(b"", 0, source=source)
    assert subscription.events.empty()
    subscription.service._update_cache_on_event.assert_not_called()
