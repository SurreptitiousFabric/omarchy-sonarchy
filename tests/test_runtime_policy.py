import ast
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from sonarchy_runtime import RUNTIME_REQUIREMENT, main, supported_runtime

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "version,implementation,expected",
    [
        ((3, 13, 9, "final", 0), "cpython", False),
        ((3, 14, 0, "final", 0), "cpython", True),
        ((3, 14, 7, "final", 0), "cpython", True),
        ((3, 14, 99, "final", 0), "cpython", True),
        ((3, 14, 0, "candidate", 1), "cpython", False),
        ((3, 14, 0, "beta", 1), "cpython", False),
        ((3, 15, 0, "final", 0), "cpython", False),
        ((4, 0, 0, "final", 0), "cpython", False),
        ((3, 14, 0, "final", 0), "pypy", False),
    ],
)
def test_runtime_policy_boundaries(version, implementation, expected):
    assert supported_runtime(version, implementation) is expected


def test_unsupported_runtime_reports_only_to_stderr(monkeypatch, capsys):
    monkeypatch.setattr(sys, "version_info", (3, 15, 0, "final", 0))
    assert main() == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err.strip() == RUNTIME_REQUIREMENT


def test_real_selected_runtime_guard_is_silent():
    result = subprocess.run(  # noqa: S603 - selected runtime and repository-owned guard
        [sys.executable, "-I", "-S", "-B", str(ROOT / "sonarchy_runtime.py")],
        capture_output=True,
        check=False,
        timeout=5,
    )
    assert result.returncode == 0
    assert result.stdout == result.stderr == b""


def test_guard_is_parseable_before_application_syntax_and_used_by_both_launchers():
    ast.parse((ROOT / "sonarchy_runtime.py").read_text(), feature_version=(3, 9))
    for filename in ("sonarchy-backend.sh", "sonarchy-mcp.sh"):
        source = (ROOT / filename).read_text()
        assert '-I -S -B "$PLUGIN_DIR/sonarchy_runtime.py"' in source
        assert source.index("sonarchy_runtime.py") < source.index(
            "exec ", source.index("sonarchy_runtime.py")
        )


@pytest.mark.parametrize("launcher", ("sonarchy-backend.sh", "sonarchy-mcp.sh"))
@pytest.mark.parametrize(
    "version", ((3, 13, 9, "final", 0), (3, 15, 0, "final", 0), (3, 14, 0, "candidate", 1))
)
def test_launcher_stops_before_setup_or_application_on_unsupported_runtime(
    tmp_path, launcher, version
):
    wrapper = tmp_path / "python-test"
    code = (
        f"import runpy, sys; sys.version_info = {version!r}; "
        "runpy.run_path(sys.argv[1], run_name='__main__')"
    )
    wrapper.write_text(
        "#!/bin/bash\nexec "
        + shlex.quote(sys.executable)
        + " -I -S -B -c "
        + shlex.quote(code)
        + ' "${@: -1}"\n'
    )
    wrapper.chmod(0o700)
    source = (ROOT / launcher).read_text().replace("/usr/bin/python3", str(wrapper))
    script = tmp_path / launcher
    script.write_text(source)
    (tmp_path / "sonarchy_runtime.py").write_text((ROOT / "sonarchy_runtime.py").read_text())
    data = tmp_path / "data"
    result = subprocess.run(  # noqa: S603 - test-owned launcher and synthetic interpreter
        ["/bin/bash", str(script)],
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "XDG_DATA_HOME": str(data)},
        capture_output=True,
        check=False,
        timeout=5,
    )
    assert result.returncode != 0
    assert result.stdout == b""
    assert b"CPython 3.14.x" in result.stderr
    assert not data.exists()
