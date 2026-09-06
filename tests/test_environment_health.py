import json
import subprocess
import sys
from pathlib import Path

import pytest

import sonarchy_environment as health

ROOT = Path(__file__).resolve().parents[1]


def test_identity_ignores_patch_but_tracks_minor_and_abi(monkeypatch):
    monkeypatch.setattr(sys, "version_info", (3, 14, 0, "final", 0))
    initial = health.interpreter_identity()
    monkeypatch.setattr(sys, "version_info", (3, 14, 7, "final", 0))
    assert health.interpreter_identity() == initial
    monkeypatch.setattr(sys, "version_info", (3, 15, 0, "final", 0))
    assert health.interpreter_identity() != initial
    monkeypatch.setattr(sys, "version_info", (3, 14, 7, "final", 0))
    monkeypatch.setattr(health.sysconfig, "get_config_var", lambda _key: "other-abi")
    assert health.interpreter_identity() != initial


@pytest.mark.parametrize(
    "failure", ("identity", "version", "import", "unknown", "empty", "malformed")
)
def test_health_rejects_drift_and_unreviewed_lock_entries(tmp_path, monkeypatch, failure):
    lock = tmp_path / "requirements.lock"
    lock.write_text("soco==0.31.2\n")
    monkeypatch.setattr(
        health.importlib.metadata,
        "version",
        lambda _name: "bad" if failure == "version" else "0.31.2",
    )

    def import_module(_name):
        if failure == "import":
            raise ImportError("missing module")

    monkeypatch.setattr(health.importlib, "import_module", import_module)
    if failure in {"unknown", "empty", "malformed"}:
        lock.write_text(
            {"unknown": "unreviewed==1\n", "empty": "# empty\n", "malformed": "soco>=1\n"}[failure]
        )
    with pytest.raises((ValueError, ImportError)):
        health.check_environment(
            lock, "old" if failure == "identity" else health.interpreter_identity()
        )


def test_real_locked_imports_complete_without_network():
    code = """import runpy, socket, sys
def forbidden(*args, **kwargs):
    raise AssertionError('network access in health check')
socket.socket.connect = forbidden
socket.socket.connect_ex = forbidden
socket.socket.sendto = forbidden
socket.create_connection = forbidden
sys.argv = sys.argv[1:]
runpy.run_path(sys.argv[0], run_name='__main__')
"""
    result = subprocess.run(  # noqa: S603 - selected runtime, fixed code and repository-owned inputs
        [
            sys.executable,
            "-I",
            "-B",
            "-c",
            code,
            str(ROOT / "sonarchy_environment.py"),
            "check",
            str(ROOT / "requirements.lock"),
            health.interpreter_identity(),
        ],
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == result.stderr == b""
    assert json.loads(health.interpreter_identity())["version"] == [3, 14]
