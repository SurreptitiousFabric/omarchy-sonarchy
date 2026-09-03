from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from sonarchy_mcp import server as mcp_server
from sonarchy_mcp.server import MAX_LINE, MAX_REQUEST_ID_BYTES, _emit_response, _read_frame

ROOT = Path(__file__).parents[1]


def _run_stdio(tmp_path: Path, frames: bytes) -> subprocess.CompletedProcess[bytes]:
    home = tmp_path / "home"
    config = tmp_path / "config"
    runtime = tmp_path / "runtime"
    home.mkdir()
    config.mkdir()
    runtime.mkdir()
    env = {
        **os.environ,
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(config),
        "XDG_RUNTIME_DIR": str(runtime),
        "PYTHONUNBUFFERED": "1",
    }
    return subprocess.run(
        [sys.executable, "-B", "-u", "-m", "sonarchy_mcp.server"],
        cwd=ROOT,
        env=env,
        input=frames,
        capture_output=True,
        timeout=5,
        check=False,
    )


def _frame(value: object) -> bytes:
    return (json.dumps(value, separators=(",", ":")) + "\n").encode()


def _messages(completed: subprocess.CompletedProcess[bytes]) -> list[dict[str, object]]:
    return [json.loads(line) for line in completed.stdout.splitlines()]


def _ping(request_id: object = "after") -> bytes:
    return _frame({"jsonrpc": "2.0", "id": request_id, "method": "ping"})


def test_non_object_is_invalid_request_and_later_ping_survives(tmp_path: Path):
    completed = _run_stdio(tmp_path, b"[]\n" + _ping())

    assert completed.returncode == 0
    assert _messages(completed) == [
        {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32600, "message": "Invalid Request"},
        },
        {"jsonrpc": "2.0", "id": "after", "result": {}},
    ]


def test_oversized_frame_gets_one_error_then_later_ping_survives(tmp_path: Path):
    oversized = b'{"padding":"' + (b"x" * MAX_LINE) + b'"}\n'
    completed = _run_stdio(tmp_path, oversized + _ping())

    assert completed.returncode == 0
    assert _messages(completed) == [
        {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32600, "message": "Invalid Request"},
        },
        {"jsonrpc": "2.0", "id": "after", "result": {}},
    ]
    assert b"padding" not in completed.stdout + completed.stderr


@pytest.mark.parametrize("version", [pytest.param(None, id="missing"), "1.0"])
def test_wrong_jsonrpc_version_is_invalid_request(tmp_path: Path, version: str | None):
    request = {"id": "bad-version", "method": "ping"}
    if version is not None:
        request["jsonrpc"] = version

    completed = _run_stdio(tmp_path, _frame(request))

    assert completed.returncode == 0
    assert _messages(completed) == [
        {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32600, "message": "Invalid Request"},
        }
    ]


def test_notification_is_silent_and_later_ping_gets_only_response(tmp_path: Path):
    notification = _frame({"jsonrpc": "2.0", "method": "ping"})
    completed = _run_stdio(tmp_path, notification + _ping())

    assert completed.returncode == 0
    assert _messages(completed) == [{"jsonrpc": "2.0", "id": "after", "result": {}}]


@pytest.mark.parametrize(
    "malformed",
    [b'{"private-marker":\n', b"\xff\xfe\n"],
    ids=["malformed-json", "invalid-utf8"],
)
def test_parse_error_is_bounded_and_later_ping_survives(tmp_path: Path, malformed: bytes):
    completed = _run_stdio(tmp_path, malformed + _ping())

    assert completed.returncode == 0
    messages = _messages(completed)
    assert messages[0] == {
        "jsonrpc": "2.0",
        "id": None,
        "error": {"code": -32700, "message": "Parse error"},
    }
    assert messages[1] == {"jsonrpc": "2.0", "id": "after", "result": {}}
    assert malformed.rstrip(b"\n") not in completed.stdout + completed.stderr


@pytest.mark.parametrize("value", [[], [1], "text", 7, True, None])
def test_every_non_object_top_level_value_is_invalid_request(tmp_path: Path, value: object):
    completed = _run_stdio(tmp_path, _frame(value))

    assert completed.returncode == 0
    assert _messages(completed) == [
        {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32600, "message": "Invalid Request"},
        }
    ]


@pytest.mark.parametrize("version", [None, "1.0", 2, False])
def test_every_invalid_jsonrpc_version_is_rejected(tmp_path: Path, version: object):
    request = {"jsonrpc": version, "id": "version", "method": "ping"}
    if version is None:
        request.pop("jsonrpc")
    completed = _run_stdio(tmp_path, _frame(request))

    assert _messages(completed)[0]["error"] == {
        "code": -32600,
        "message": "Invalid Request",
    }
    assert _messages(completed)[0]["id"] is None


@pytest.mark.parametrize("method", [None, 1, False])
def test_missing_or_non_string_method_is_invalid_request(tmp_path: Path, method: object):
    request = {"jsonrpc": "2.0", "id": "method"}
    if method is not None:
        request["method"] = method
    completed = _run_stdio(tmp_path, _frame(request))

    assert _messages(completed) == [
        {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32600, "message": "Invalid Request"},
        }
    ]


def test_unknown_request_method_uses_validated_id(tmp_path: Path):
    completed = _run_stdio(
        tmp_path,
        _frame({"jsonrpc": "2.0", "id": "unknown", "method": "not-supported"}),
    )

    assert _messages(completed) == [
        {
            "jsonrpc": "2.0",
            "id": "unknown",
            "error": {"code": -32601, "message": "Method not found"},
        }
    ]


@pytest.mark.parametrize("params", [None, [], "bad", 1, False])
def test_structurally_invalid_params_are_rejected(tmp_path: Path, params: object):
    completed = _run_stdio(
        tmp_path,
        _frame({"jsonrpc": "2.0", "id": "params", "method": "ping", "params": params}),
    )

    assert _messages(completed) == [
        {
            "jsonrpc": "2.0",
            "id": "params",
            "error": {"code": -32602, "message": "Invalid params"},
        }
    ]


@pytest.mark.parametrize(
    "params",
    [{}, {"name": 7}, {"name": "rooms_list", "arguments": []}],
)
def test_malformed_tools_call_params_are_protocol_errors(tmp_path: Path, params: object):
    completed = _run_stdio(
        tmp_path,
        _frame({"jsonrpc": "2.0", "id": "tool", "method": "tools/call", "params": params}),
    )

    assert _messages(completed)[0] == {
        "jsonrpc": "2.0",
        "id": "tool",
        "error": {"code": -32602, "message": "Invalid params"},
    }


def test_tool_application_failure_remains_an_mcp_tool_result(tmp_path: Path):
    completed = _run_stdio(
        tmp_path,
        _frame(
            {
                "jsonrpc": "2.0",
                "id": "rooms",
                "method": "tools/call",
                "params": {"name": "rooms_list", "arguments": {}},
            }
        ),
    )

    response = _messages(completed)[0]
    assert response["id"] == "rooms"
    assert "error" not in response
    assert response["result"]["isError"] is True
    assert response["result"]["structuredContent"]["code"] == "unavailable"


def test_notifications_are_silent_and_cannot_execute_tools(tmp_path: Path):
    notifications = [
        {"jsonrpc": "2.0", "method": "ping"},
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        {"jsonrpc": "2.0", "method": "ping", "params": []},
        {"jsonrpc": "2.0", "method": "not-supported"},
        {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "rooms_list", "arguments": {}},
        },
    ]
    completed = _run_stdio(tmp_path, b"".join(map(_frame, notifications)) + _ping())

    assert _messages(completed) == [{"jsonrpc": "2.0", "id": "after", "result": {}}]
    assert list((tmp_path / "runtime").iterdir()) == []


def test_exact_input_boundary_is_accepted_and_one_byte_over_is_drained(tmp_path: Path):
    prefix = b'{"jsonrpc":"2.0","id":"boundary","method":"ping","padding":"'
    suffix = b'"}\n'
    exact = prefix + (b"x" * (MAX_LINE - len(prefix) - len(suffix))) + suffix
    assert len(exact) == MAX_LINE
    oversized = exact[:-1] + b"x\n"
    assert len(oversized) == MAX_LINE + 1

    completed = _run_stdio(tmp_path, exact + oversized + _ping())

    assert _messages(completed) == [
        {"jsonrpc": "2.0", "id": "boundary", "result": {}},
        {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32600, "message": "Invalid Request"},
        },
        {"jsonrpc": "2.0", "id": "after", "result": {}},
    ]


def test_ten_megabyte_frame_is_drained_once_without_echo(tmp_path: Path):
    hostile = b'{"private":"' + (b"z" * (10 * 1024 * 1024)) + b'"}\n'
    completed = _run_stdio(tmp_path, hostile + _ping())

    assert completed.returncode == 0
    assert _messages(completed) == [
        {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32600, "message": "Invalid Request"},
        },
        {"jsonrpc": "2.0", "id": "after", "result": {}},
    ]
    assert b"private" not in completed.stdout + completed.stderr


class GuardedLargeFrame:
    def __init__(self, size: int):
        self.remaining = size
        self.requested_sizes: list[int] = []
        self.largest_returned = 0

    def readline(self, size: int = -1) -> bytes:
        assert size == MAX_LINE + 1
        self.requested_sizes.append(size)
        if self.remaining == 0:
            return b""
        count = min(size, self.remaining)
        self.remaining -= count
        chunk = b"x" * count
        self.largest_returned = max(self.largest_returned, len(chunk))
        return chunk


def test_frame_reader_never_requests_or_retains_an_unbounded_remainder():
    reader = GuardedLargeFrame(10 * 1024 * 1024)

    raw, oversized = _read_frame(reader)

    assert raw == b""
    assert oversized is True
    assert reader.remaining == 0
    assert set(reader.requested_sizes) == {MAX_LINE + 1}
    assert reader.largest_returned == MAX_LINE + 1


@pytest.mark.parametrize("request_id", ["exact-id", 17])
def test_valid_request_ids_are_echoed_exactly(tmp_path: Path, request_id: str | int):
    completed = _run_stdio(tmp_path, _ping(request_id))

    assert _messages(completed) == [{"jsonrpc": "2.0", "id": request_id, "result": {}}]


@pytest.mark.parametrize("request_id", [True, None, "\\" * MAX_REQUEST_ID_BYTES, "\ud800"])
def test_invalid_or_oversized_request_ids_are_not_reflected(tmp_path: Path, request_id: object):
    completed = _run_stdio(tmp_path, _ping(request_id))

    response = _messages(completed)[0]
    assert response == {
        "jsonrpc": "2.0",
        "id": None,
        "error": {"code": -32600, "message": "Invalid Request"},
    }
    assert len(completed.stdout.splitlines()[0]) + 1 <= MAX_LINE
    if isinstance(request_id, str):
        assert request_id.encode("utf-8", "backslashreplace") not in (
            completed.stdout + completed.stderr
        )


def test_initialize_inventory_and_stdout_are_jsonrpc_only(tmp_path: Path):
    frames = b"".join(
        [
            _frame(
                {
                    "jsonrpc": "2.0",
                    "id": "initialize",
                    "method": "initialize",
                    "params": {},
                }
            ),
            _frame({"jsonrpc": "2.0", "id": "tools", "method": "tools/list"}),
        ]
    )
    completed = _run_stdio(tmp_path, frames)

    messages = _messages(completed)
    assert messages[0]["result"]["protocolVersion"] == "2025-06-18"
    assert [tool["name"] for tool in messages[1]["result"]["tools"]] == [
        "rooms_list",
        "room_state_get",
        "content_browse",
        "apple_playlist_preflight",
        "sonos_playlist_play_preflight",
    ]
    assert all(message["jsonrpc"] == "2.0" for message in messages)
    assert all(len(line) + 1 <= MAX_LINE for line in completed.stdout.splitlines())
    assert completed.stderr == b""
    assert list((tmp_path / "runtime").iterdir()) == []


def test_exact_codex_startup_accepts_request_metadata(tmp_path: Path):
    frames = b"".join(
        map(
            _frame,
            [
                {
                    "jsonrpc": "2.0",
                    "id": 0,
                    "method": "initialize",
                    "params": {
                        "capabilities": {"elicitation": {"form": {}, "url": {}}},
                        "clientInfo": {
                            "name": "codex-mcp-client",
                            "title": "Codex",
                            "version": "0.151.0",
                        },
                        "protocolVersion": "2025-06-18",
                    },
                },
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/list",
                    "params": {"_meta": {"progressToken": 0}},
                },
                {"jsonrpc": "2.0", "id": 2, "method": "ping"},
            ],
        )
    )

    completed = _run_stdio(tmp_path, frames)

    assert completed.returncode == 0
    messages = _messages(completed)
    assert messages[0]["id"] == 0
    assert messages[0]["result"]["protocolVersion"] == "2025-06-18"
    assert "result" in messages[1], messages[1]
    assert [tool["name"] for tool in messages[1]["result"]["tools"]] == [
        "rooms_list",
        "room_state_get",
        "content_browse",
        "apple_playlist_preflight",
        "sonos_playlist_play_preflight",
    ]
    assert messages[2] == {"jsonrpc": "2.0", "id": 2, "result": {}}
    assert all(message["jsonrpc"] == "2.0" for message in messages)
    assert b"progressToken" not in completed.stdout + completed.stderr
    assert b'"_meta"' not in completed.stdout + completed.stderr
    assert completed.stderr == b""
    assert list((tmp_path / "runtime").iterdir()) == []


def test_tools_list_ignores_unknown_request_metadata(tmp_path: Path):
    metadata = {
        "progressToken": 0,
        "vendor.example/trace": "opaque",
        "unknown": {"nested": True},
    }
    completed = _run_stdio(
        tmp_path,
        _frame(
            {
                "jsonrpc": "2.0",
                "id": "tools",
                "method": "tools/list",
                "params": {"_meta": metadata},
            }
        ),
    )

    response = _messages(completed)[0]
    assert [tool["name"] for tool in response["result"]["tools"]] == [
        "rooms_list",
        "room_state_get",
        "content_browse",
        "apple_playlist_preflight",
        "sonos_playlist_play_preflight",
    ]
    assert b"progressToken" not in completed.stdout + completed.stderr
    assert b"vendor.example/trace" not in completed.stdout + completed.stderr
    assert b'"_meta"' not in completed.stdout + completed.stderr


def test_ping_accepts_request_metadata(tmp_path: Path):
    completed = _run_stdio(
        tmp_path,
        _frame(
            {
                "jsonrpc": "2.0",
                "id": "ping",
                "method": "ping",
                "params": {"_meta": {"unknown": True}},
            }
        ),
    )

    assert _messages(completed) == [{"jsonrpc": "2.0", "id": "ping", "result": {}}]
    assert b'"_meta"' not in completed.stdout + completed.stderr


@pytest.mark.parametrize("metadata", [None, "bad", 7, False, []])
def test_invalid_request_metadata_is_bounded_and_later_ping_survives(
    tmp_path: Path, metadata: object
):
    malformed = _frame(
        {
            "jsonrpc": "2.0",
            "id": "bad-meta",
            "method": "tools/list",
            "params": {"_meta": metadata},
        }
    )
    completed = _run_stdio(tmp_path, malformed + _ping())

    assert completed.returncode == 0
    assert _messages(completed) == [
        {
            "jsonrpc": "2.0",
            "id": "bad-meta",
            "error": {"code": -32602, "message": "Invalid params"},
        },
        {"jsonrpc": "2.0", "id": "after", "result": {}},
    ]
    assert b'"_meta"' not in completed.stdout + completed.stderr
    assert completed.stderr == b""


@pytest.mark.parametrize("method", ["tools/list", "ping"])
def test_metadata_does_not_hide_unexpected_functional_params(tmp_path: Path, method: str):
    completed = _run_stdio(
        tmp_path,
        _frame(
            {
                "jsonrpc": "2.0",
                "id": "strict",
                "method": method,
                "params": {"_meta": {}, "unexpected": True},
            }
        ),
    )

    assert _messages(completed) == [
        {
            "jsonrpc": "2.0",
            "id": "strict",
            "error": {"code": -32602, "message": "Invalid params"},
        }
    ]
    assert b"unexpected" not in completed.stdout + completed.stderr
    assert b'"_meta"' not in completed.stdout + completed.stderr


def test_tool_call_request_metadata_is_not_forwarded(monkeypatch):
    frames = _frame(
        {
            "jsonrpc": "2.0",
            "id": "tool",
            "method": "tools/call",
            "params": {
                "_meta": {"progressToken": 0, "private": "marker"},
                "name": "rooms_list",
                "arguments": {"functional": "value"},
            },
        }
    )
    output = io.BytesIO()
    received: list[tuple[str, dict[str, object]]] = []
    server = mcp_server.SonarchyMcp()
    monkeypatch.setattr(mcp_server.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(frames)))
    monkeypatch.setattr(mcp_server.sys, "stdout", SimpleNamespace(buffer=output))
    monkeypatch.setattr(
        server,
        "call_tool",
        lambda name, arguments: received.append((name, arguments)) or {"ok": True},
    )

    server.run()

    assert received == [("rooms_list", {"functional": "value"})]
    assert json.loads(output.getvalue())["result"]["structuredContent"] == {"ok": True}
    assert b"progressToken" not in output.getvalue()
    assert b'"_meta"' not in output.getvalue()
    assert b"private" not in output.getvalue()


def test_oversized_output_is_replaced_before_any_bytes_are_written(monkeypatch):
    output = io.BytesIO()
    monkeypatch.setattr(mcp_server.sys, "stdout", SimpleNamespace(buffer=output))

    _emit_response(
        {"jsonrpc": "2.0", "id": "bounded", "result": {"value": "x" * MAX_LINE}},
        "bounded",
    )

    encoded = output.getvalue()
    assert len(encoded) <= MAX_LINE
    assert json.loads(encoded) == {
        "jsonrpc": "2.0",
        "id": "bounded",
        "error": {"code": -32603, "message": "Internal error"},
    }


def test_large_valid_tool_result_drops_only_duplicate_text_before_emission(monkeypatch):
    output = io.BytesIO()
    monkeypatch.setattr(mcp_server.sys, "stdout", SimpleNamespace(buffer=output))
    value = {"items": ["x" * 40_000]}

    _emit_response(
        {
            "jsonrpc": "2.0",
            "id": "large-result",
            "result": {
                "content": [{"type": "text", "text": json.dumps(value)}],
                "structuredContent": value,
                "isError": False,
            },
        },
        "large-result",
    )

    encoded = output.getvalue()
    response = json.loads(encoded)
    assert len(encoded) <= MAX_LINE
    assert response["result"] == {
        "content": [],
        "structuredContent": value,
        "isError": False,
    }


def test_unserializable_output_is_replaced_before_any_bytes_are_written(monkeypatch):
    output = io.BytesIO()
    monkeypatch.setattr(mcp_server.sys, "stdout", SimpleNamespace(buffer=output))

    _emit_response({"jsonrpc": "2.0", "id": 19, "result": {"value": object()}}, 19)

    assert json.loads(output.getvalue()) == {
        "jsonrpc": "2.0",
        "id": 19,
        "error": {"code": -32603, "message": "Internal error"},
    }
