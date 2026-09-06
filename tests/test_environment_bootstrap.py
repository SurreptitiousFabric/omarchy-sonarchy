import hashlib
import json
import shlex
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

FAKE_PYTHON = """#!{python}
import json, pathlib, sys
config = json.loads(pathlib.Path({config!r}).read_text())
args = sys.argv[1:]
def record(value):
    with open({log!r}, "a") as stream:
        stream.write(json.dumps(value) + "\\n")
if any(arg.endswith("sonarchy_runtime.py") for arg in args):
    sys.exit(0)
if any(arg.endswith("sonarchy_environment.py") for arg in args):
    if "identity" in args:
        print("test-abi")
        sys.exit(0)
    record("health")
    if config.get("fail") == "timeout":
        import time
        time.sleep(5)
    sys.exit(0 if (pathlib.Path(sys.argv[0]).parent.parent / ".healthy").exists() else 1)
if args[:2] == ["-m", "venv"]:
    record("build")
    if config.get("fail") == "create": sys.exit(1)
    target = pathlib.Path(args[2]) / "bin" / "python"
    target.parent.mkdir(parents=True)
    target.write_text(pathlib.Path(sys.argv[0]).read_text())
    target.chmod(0o700)
elif "pip" in args:
    record(args)
    if config.get("fail") == "install": sys.exit(1)
    if config.get("fail") != "validate":
        (pathlib.Path(sys.argv[0]).parent.parent / ".healthy").touch()
elif any(arg.endswith("sonarchy_service.py") for arg in args):
    record("start")
else:
    raise RuntimeError("unexpected fake interpreter call")
"""


@pytest.fixture
def bootstrap(tmp_path):
    config = tmp_path / "config.json"
    config.write_text("{}")
    log = tmp_path / "calls.jsonl"
    python = tmp_path / "python-test"
    python.write_text(FAKE_PYTHON.format(python=sys.executable, config=str(config), log=str(log)))
    python.chmod(0o700)
    script = tmp_path / "sonarchy-backend.sh"
    script.write_text((ROOT / script.name).read_text().replace("/usr/bin/python3", str(python)))
    lock = tmp_path / "requirements.lock"
    lock.write_text("soco==0.31.2\n")
    data = tmp_path / "data"
    venv = data / "sonarchy" / "venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "python").write_text(python.read_text())
    (venv / "bin" / "python").chmod(0o700)
    (venv / ".requirements.sha256").write_text(hashlib.sha256(lock.read_bytes()).hexdigest())
    (venv / ".python-identity").write_text("test-abi")
    (venv / "old-marker").touch()
    return (
        script,
        venv,
        config,
        log,
        {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "XDG_DATA_HOME": str(data)},
    )


def run_bootstrap(case):
    script, _, _, _, env = case
    return subprocess.run(  # noqa: S603 - copied launcher with test-owned fake external interpreter
        ["/bin/bash", str(script)], env=env, capture_output=True, timeout=10, check=False
    )


def calls(case):
    log = case[3]
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def test_executable_but_missing_imports_rebuilds_before_start(bootstrap):
    result = run_bootstrap(bootstrap)
    assert result.returncode == 0, result.stderr
    assert "build" in calls(bootstrap)
    assert calls(bootstrap)[-1] == "start"


def test_healthy_compatible_environment_reuses_without_install(bootstrap):
    (bootstrap[1] / ".healthy").touch()
    result = run_bootstrap(bootstrap)
    assert result.returncode == 0, result.stderr
    assert calls(bootstrap) == ["health", "start"]
    assert (bootstrap[1] / "old-marker").exists()


@pytest.mark.parametrize("partial_identity", ("", "test-abi"))
@pytest.mark.parametrize("install_failure", (False, True))
def test_failed_identity_read_rebuilds_or_reports_setup_error(
    bootstrap, tmp_path, partial_identity, install_failure
):
    script, venv, config, _, _ = bootstrap
    (venv / ".healthy").touch()
    if install_failure:
        config.write_text(json.dumps({"fail": "install"}))
    reader = tmp_path / "failed-identity-read"
    reader.write_text("#!/bin/bash\nprintf %s " + shlex.quote(partial_identity) + "\nexit 1\n")
    reader.chmod(0o700)
    source = script.read_text()
    assert source.count('cat "$IDENTITY_FILE"') == 1
    # Inject only the OS-level read failure; keep assignment, set -e and recovery real.
    script.write_text(source.replace('cat "$IDENTITY_FILE"', f'"{reader}" "$IDENTITY_FILE"'))
    result = run_bootstrap(bootstrap)
    assert result.stdout == b""
    assert calls(bootstrap).count("build") == 1
    if install_failure:
        assert result.returncode != 0
        assert b"SONOS_SETUP_ERROR" in result.stderr
        assert (venv / "old-marker").exists()
        assert "start" not in calls(bootstrap)
        assert not list(venv.parent.glob("venv.build.*"))
    else:
        assert result.returncode == 0, result.stderr
        assert calls(bootstrap)[-2:] == ["health", "start"]
        assert not (venv / "old-marker").exists()
        assert (venv / ".python-identity").read_text().strip() == "test-abi"


@pytest.mark.parametrize("changed", ("minor", "abi", "lock", "executable", "legacy"))
def test_changed_compatibility_or_lock_or_missing_python_rebuilds(bootstrap, changed):
    venv = bootstrap[1]
    (venv / ".healthy").touch()
    if changed in {"minor", "abi"}:
        (venv / ".python-identity").write_text("old-" + changed)
    elif changed == "lock":
        (venv / ".requirements.sha256").write_text("old-lock")
    elif changed == "legacy":
        (venv / ".python-identity").unlink()
    else:
        (venv / "bin" / "python").unlink()
    result = run_bootstrap(bootstrap)
    assert result.returncode == 0, result.stderr
    assert calls(bootstrap).count("build") == 1
    assert (venv / ".python-identity").read_text().strip() == "test-abi"
    pip_call = next(call for call in calls(bootstrap) if isinstance(call, list))
    assert {"--require-hashes", "--only-binary=:all:", "--no-deps", "--no-input"} <= set(pip_call)


@pytest.mark.parametrize("failure", ("create", "install", "validate"))
def test_failed_replacement_preserves_old_environment(bootstrap, failure):
    bootstrap[2].write_text(json.dumps({"fail": failure}))
    result = run_bootstrap(bootstrap)
    assert result.returncode != 0
    assert b"SONOS_SETUP_ERROR" in result.stderr
    assert (bootstrap[1] / "old-marker").exists()
    assert (bootstrap[1] / "bin" / "python").is_file()
    assert "start" not in calls(bootstrap)
    assert not list(bootstrap[1].parent.glob("venv.build.*"))


def test_concurrent_startups_install_once(bootstrap):
    script, _, _, _, env = bootstrap
    processes = [
        subprocess.Popen(  # noqa: S603 - test-owned launcher and interpreter
            ["/bin/bash", str(script)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        for _ in range(2)
    ]
    for process in processes:
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 0, stderr
        assert stdout == b""
    assert calls(bootstrap).count("build") == 1
    assert calls(bootstrap).count("start") == 2


def test_symlink_metadata_is_rejected_without_build_or_start(bootstrap, tmp_path):
    stamp = bootstrap[1] / ".python-identity"
    stamp.unlink()
    stamp.symlink_to(tmp_path / "unrelated")
    result = run_bootstrap(bootstrap)
    assert result.returncode != 0
    assert "build" not in calls(bootstrap)
    assert "start" not in calls(bootstrap)


def test_failed_promotion_restores_prior_environment(bootstrap, tmp_path):
    script = bootstrap[0]
    mover = tmp_path / "mv-test"
    mover.write_text(
        '#!/bin/bash\nif [[ "$2" == */venv.build.* ]]; then exit 1; fi\nexec /usr/bin/mv "$@"\n'
    )
    mover.chmod(0o700)
    script.write_text(script.read_text().replace("mv -T", '"' + str(mover) + '" -T'))
    result = run_bootstrap(bootstrap)
    assert result.returncode != 0
    assert b"promote" in result.stderr
    assert (bootstrap[1] / "old-marker").exists()
    assert "start" not in calls(bootstrap)
    assert not list(bootstrap[1].parent.glob("venv.previous.*"))


def test_hung_health_check_is_bounded_and_preserves_old_environment(bootstrap):
    script = bootstrap[0]
    source = script.read_text()
    assert "timeout --kill-after=1 10" in source
    # Shorten only the test's deadline; no production environment override.
    script.write_text(source.replace("timeout --kill-after=1 10", "timeout --kill-after=1 0.2"))
    bootstrap[2].write_text(json.dumps({"fail": "timeout"}))
    result = run_bootstrap(bootstrap)
    assert result.returncode != 0
    assert (bootstrap[1] / "old-marker").exists()
    assert "start" not in calls(bootstrap)


def test_fresh_environment_is_validated_and_owner_only(bootstrap):
    venv = bootstrap[1]
    shutil.rmtree(venv)
    result = run_bootstrap(bootstrap)
    assert result.returncode == 0, result.stderr
    assert calls(bootstrap).count("build") == 1
    assert calls(bootstrap)[-2:] == ["health", "start"]
    assert stat.S_IMODE(venv.stat().st_mode) == 0o700
    for path in (
        venv / ".python-identity",
        venv / ".requirements.sha256",
        venv.parent / "setup.lock",
    ):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
