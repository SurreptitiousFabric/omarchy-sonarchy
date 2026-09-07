"""Event-slot ownership through real socketserver dispatch, without LAN I/O."""

import socket
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import soco.events as events

from sonarchy_backend.live_updates import MAX_EVENT_CONNECTIONS


@pytest.fixture(autouse=True)
def forbid_network_and_subscriptions(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("worker tests must not bind, connect or subscribe")

    for operation in ("bind", "listen", "connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, operation, forbidden)
    monkeypatch.setattr(events.Subscription, "subscribe", forbidden)


@pytest.fixture
def accepted_request():
    handler = Mock(name="request_handler", return_value=None)
    server = events.EventServer(("127.0.0.1", 0), handler, bind_and_activate=False)
    try:
        request, client = socket.socketpair()
        with request, client:
            address = ("127.0.0.1", 0)
            server.get_request = Mock(return_value=(request, address))
            server.handle_error = Mock()
            server.shutdown_request = Mock(wraps=server.shutdown_request)
            server.close_request = Mock(wraps=server.close_request)
            yield SimpleNamespace(
                server=server, request=request, client=client, address=address, handler=handler
            )
    finally:
        server.server_close()


def assert_request_closed_once(case):
    case.server.shutdown_request.assert_called_once_with(case.request)
    case.server.close_request.assert_called_once_with(case.request)
    assert case.request.fileno() == -1
    case.client.settimeout(1)
    assert case.client.recv(1) == b""


def assert_full_capacity(server):
    acquired = 0
    try:
        for _ in range(MAX_EVENT_CONNECTIONS):
            assert server._event_slots.acquire(blocking=False), "event-handler capacity was lost"
            acquired += 1
        assert not server._event_slots.acquire(blocking=False), "extra event-handler capacity"
    finally:
        for _ in range(acquired):
            server._event_slots.release()


@pytest.mark.parametrize("failure_point", ["constructor", "start"])
def test_worker_startup_failure_returns_slot_to_dispatcher(
    monkeypatch, accepted_request, failure_point
):
    failure = RuntimeError("fixture worker startup failure")
    if failure_point == "constructor":
        monkeypatch.setattr(threading, "Thread", Mock(side_effect=failure))
    else:
        monkeypatch.setattr(threading.Thread, "start", Mock(side_effect=failure))

    case = accepted_request
    # The stdlib dispatcher must still observe the exception and own socket cleanup.
    case.server._handle_request_noblock()

    case.handler.assert_not_called()
    case.server.handle_error.assert_called_once_with(case.request, case.address)
    assert_request_closed_once(case)
    assert_full_capacity(case.server)


@pytest.mark.parametrize("handler_fails", [False, True])
def test_started_worker_releases_once_after_handler_outcome(
    monkeypatch, accepted_request, handler_fails
):
    case = accepted_request
    if handler_fails:
        case.handler.side_effect = RuntimeError("fixture request handler failure")

    thread_class = threading.Thread
    workers = []

    def record_worker(*args, **kwargs):
        worker = thread_class(*args, **kwargs)
        workers.append(worker)
        return worker

    monkeypatch.setattr(threading, "Thread", record_worker)
    case.server._handle_request_noblock()
    assert len(workers) == 1
    workers[0].join(timeout=2)
    assert not workers[0].is_alive(), "bounded fixture worker did not finish"

    case.handler.assert_called_once_with(case.request, case.address, case.server)
    if handler_fails:
        case.server.handle_error.assert_called_once_with(case.request, case.address)
    else:
        case.server.handle_error.assert_not_called()
    assert_request_closed_once(case)
    assert_full_capacity(case.server)
