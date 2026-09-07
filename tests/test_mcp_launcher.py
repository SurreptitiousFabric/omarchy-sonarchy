"""Run the shipped shell entry point; substitute only its system interpreter path."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def _frame(value):
    return (json.dumps(value) + "\n").encode()


def _run_launcher(tmp_path, runtime, mutation=""):
    plugin = tmp_path / "checkout with spaces"
    plugin.mkdir()
    for name in ("sonarchy_runtime.py", "sonarchy_mcp_contract.py"):
        shutil.copy2(ROOT / name, plugin / name)
    shutil.copytree(
        ROOT / "sonarchy_mcp", plugin / "sonarchy_mcp", ignore=shutil.ignore_patterns("__pycache__")
    )
    launcher = (ROOT / "sonarchy-mcp.sh").read_text()
    assert launcher.count("/usr/bin/python3") == 2
    launcher = launcher.replace("/usr/bin/python3", shlex.quote(sys.executable))
    script = plugin / "sonarchy-mcp.sh"
    script.write_text(launcher)
    if mutation == "stdout":
        script.write_text(launcher.replace("set -euo pipefail", "set -euo pipefail\necho noise"))
    elif mutation == "broken-module":
        script.write_text(launcher.replace("sonarchy_mcp.server", "missing_adapter"))
    home = tmp_path / "home"
    config = tmp_path / "config"
    home.mkdir()
    config.mkdir()
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "ping"},
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "rooms_list", "arguments": {}},
        },
    ]
    completed = subprocess.run(  # noqa: S603 - trusted checkout copy in private test directory
        ["/bin/bash", str(script)],
        cwd=home,
        env={
            "PATH": os.defpath,
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(config),
            "XDG_RUNTIME_DIR": str(runtime),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        input=b"".join(map(_frame, requests)),
        capture_output=True,
        timeout=5,
    )
    assert list(home.iterdir()) == []
    assert list(config.iterdir()) == []
    assert not list(plugin.rglob("__pycache__"))
    return completed


def _assert_startup(completed):
    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == b""
    messages = [json.loads(line) for line in completed.stdout.splitlines()]
    assert [message["id"] for message in messages] == [1, 2, 3, 4]
    assert all(message["jsonrpc"] == "2.0" for message in messages)
    assert messages[0]["result"]["protocolVersion"] == "2025-06-18"
    assert "rooms_list" in [tool["name"] for tool in messages[1]["result"]["tools"]]
    assert messages[2]["result"] == {}
    return messages[3]["result"]


def test_launcher_startup_with_unavailable_backend(tmp_path):
    result = _assert_startup(_run_launcher(tmp_path, tmp_path / "absent"))
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "unavailable"


def test_launcher_real_stdio_and_socket_with_fake_backend(tmp_path):
    # Short private path avoids AF_UNIX's pathname limit on long CI checkout paths.
    with tempfile.TemporaryDirectory(prefix="sonarchy-launcher-") as directory:
        runtime = Path(directory)
        private = runtime / "sonarchy"
        private.mkdir(mode=0o700)
        address = private / "control.sock"
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.bind(str(address))
            address.chmod(0o600)
            listener.listen(1)
            listener.settimeout(5)

            def serve():
                connection, _ = listener.accept()
                with connection:
                    connection.settimeout(5)
                    with connection.makefile("rb") as reader:
                        request = json.loads(reader.readline())
                        connection.sendall(
                            _frame(
                                {
                                    "type": "result",
                                    "id": request["id"],
                                    "ok": True,
                                    "revision": 1,
                                    "value": {},
                                }
                            )
                            + _frame({"type": "snapshot", "revision": 2, "households": []})
                        )
                        assert reader.readline() == b""
                        return request

            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(serve)
                result = _assert_startup(_run_launcher(tmp_path, runtime))
                request = future.result(timeout=5)
    assert request == {"version": 1, "id": "mcp-1", "op": "state.refresh", "args": {}}
    assert result["isError"] is False
    assert result["structuredContent"]["households"] == []


@pytest.mark.parametrize("mutation", ["stdout", "broken-module"])
def test_startup_gate_rejects_noisy_or_broken_launcher(tmp_path, mutation):
    completed = _run_launcher(tmp_path, tmp_path / "absent", mutation)
    with pytest.raises((AssertionError, json.JSONDecodeError)):
        _assert_startup(completed)
