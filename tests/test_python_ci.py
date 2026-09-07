import ast
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_matrix_matches_declared_floor_and_exact_project_pin():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    pin = tomllib.loads((ROOT / ".mise.toml").read_text())["tools"]["python"]
    matrix = ast.literal_eval(re.search(r"python: (\[.*\])", workflow)[1])
    assert matrix == ["3.14.0", pin]
    assert "fail-fast: false" in workflow
    assert "continue-on-error" not in workflow
    assert "needs: [python_compatibility]" in workflow
    assert 'run: test "${{ needs.python_compatibility.result }}" = success' in workflow
    assert 'target_root="$(mise where "python@$SONARCHY_TEST_VERSION")"' in workflow
    assert '"$target_root/bin/python" -m venv "$target_venv"' in workflow
    assert 'assert sys.version.split()[0] == os.environ["SONARCHY_TEST_VERSION"]' in workflow
    assert '"$SONARCHY_CI_PYTHON" -m compileall' in workflow
    assert '"$SONARCHY_CI_PYTHON" -I -B sonarchy_environment.py check' in workflow
    assert '"$SONARCHY_CI_PYTHON" -m coverage run -m pytest' in workflow


def test_compilation_gate_rejects_invalid_source_under_each_ci_interpreter(tmp_path):
    broken = tmp_path / "future_incompatible.py"
    broken.write_text("def incompatible(:\n    pass\n")
    result = subprocess.run(  # noqa: S603 - selected CI interpreter and test-owned syntax fixture
        [sys.executable, "-m", "compileall", "-q", str(broken)],
        capture_output=True,
        timeout=5,
        check=False,
    )
    assert result.returncode != 0
    assert b"SyntaxError" in result.stdout + result.stderr


def test_application_exception_syntax_establishes_minor_floor():
    source = "try:\n    pass\nexcept ValueError, TypeError:\n    pass\n"
    ast.parse(source)
    try:
        ast.parse(source, feature_version=(3, 13))
    except SyntaxError:
        return
    raise AssertionError("3.14 exception syntax unexpectedly accepted by 3.13 grammar")
