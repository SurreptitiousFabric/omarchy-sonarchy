import json
from types import SimpleNamespace

import pytest

from scripts import validate_platform as gate


@pytest.mark.parametrize("stage", ["manifest", "qml", "components", "negativeControls", "none"])
def test_all_stages_required(monkeypatch, capsys, stage):
    candidate = "a" * 40
    monkeypatch.setattr(gate.sys, "argv", ["gate", candidate])

    def run(command, **kwargs):
        if "rev-parse" in command:
            return SimpleNamespace(returncode=0, stdout=candidate)
        if "status" in command:
            return SimpleNamespace(returncode=0, stdout="")
        assert kwargs["env"]["SONARCHY_PLATFORM_TESTS"] == "1"
        return SimpleNamespace(returncode=int(stage == "negativeControls"))

    monkeypatch.setattr(gate, "run", run)
    monkeypatch.setattr(gate, "platform", lambda: {"packages": ["fixture"]})
    for function, name in [("manifest", "manifest"), ("lint", "qml"), ("components", "components")]:
        monkeypatch.setattr(
            gate,
            function,
            lambda *_, name=name: {"status": "failed" if stage == name else "passed"},
        )
    assert gate.main() == (0 if stage == "none" else 1)
    report = json.loads(capsys.readouterr().out)
    assert report["candidate"] == candidate
    assert len(report["stages"]) == 4


def test_unavailable_tooling_is_incomplete_not_success(monkeypatch, capsys):
    candidate = "a" * 40
    monkeypatch.setattr(gate.sys, "argv", ["gate", candidate])
    monkeypatch.setattr(
        gate,
        "run",
        lambda cmd: SimpleNamespace(returncode=0, stdout=candidate if "rev-parse" in cmd else ""),
    )

    def unavailable():
        raise FileNotFoundError("private-host-marker")

    monkeypatch.setattr(gate, "platform", unavailable)
    assert gate.main() == 2
    output = capsys.readouterr().out
    assert json.loads(output)["status"] == "incomplete"
    assert "private-host-marker" not in output


def test_dirty_candidate_is_incomplete(monkeypatch, capsys):
    monkeypatch.setattr(gate, "run", lambda *_: SimpleNamespace(returncode=0, stdout="dirty"))
    monkeypatch.setattr(gate, "platform", lambda: pytest.fail("must stop first"))
    assert gate.main() == 2
    assert json.loads(capsys.readouterr().out)["status"] == "incomplete"


def test_lint_default_zero_exit_cannot_mask_failed_report(tmp_path, monkeypatch):
    (tmp_path / "Probe.qml").write_text("import QtQuick\nItem {}")
    monkeypatch.setattr(
        gate,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {"files": [{"filename": "Probe.qml", "success": False, "warnings": []}]}
            ),
        ),
    )
    assert gate.lint(tmp_path, tmp_path)["status"] == "failed"


@pytest.mark.parametrize("addopts", ["--collect-only", "-k test_positive_probe"])
@pytest.mark.parametrize("failing_control", [None, "platform", "contract"])
def test_inherited_options_cannot_skip_controls(
    tmp_path, monkeypatch, capsys, addopts, failing_control
):
    """Exercise the gate's real subprocess/env path with portable pytest controls."""
    candidate = "a" * 40
    monkeypatch.setattr(gate.sys, "argv", ["gate", candidate])
    monkeypatch.setenv("PYTEST_ADDOPTS", addopts)
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "test_platform_host.py").write_text(
        "from pathlib import Path\n"
        "def test_positive_probe():\n"
        "    Path('positive-ran').touch()\n"
        "def test_negative_control():\n"
        "    Path('negative-ran').touch()\n"
        f"    assert {failing_control != 'platform'!r}\n"
    )
    (test_dir / "test_qml_type_contract.py").write_text(
        "from pathlib import Path\n"
        "def test_type_contract():\n"
        "    Path('contract-ran').touch()\n"
        f"    assert {failing_control != 'contract'!r}\n"
    )
    real_run = gate.run

    def run(command, **kwargs):
        if "rev-parse" in command:
            return SimpleNamespace(returncode=0, stdout=candidate)
        if "status" in command:
            return SimpleNamespace(returncode=0, stdout="")
        return real_run(command, cwd=tmp_path, **kwargs)

    monkeypatch.setattr(gate, "run", run)
    monkeypatch.setattr(gate, "platform", lambda: {"packages": ["fixture"]})
    for name in ["manifest", "lint", "components"]:
        monkeypatch.setattr(gate, name, lambda *_: {"status": "passed"})
    result = gate.main()
    report = json.loads(capsys.readouterr().out)
    assert (tmp_path / "positive-ran").is_file()
    assert (tmp_path / "negative-ran").is_file()
    assert (tmp_path / "contract-ran").is_file()
    assert result == int(failing_control is not None)
    assert report["stages"]["negativeControls"]["status"] == (
        "failed" if failing_control else "passed"
    )


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ("known", "passed"),
        ("removed", "passed"),
        ("new", "failed"),
        ("duplicate", "failed"),
        ("error", "failed"),
        ("crash", "failed"),
        ("source", "failed"),
    ],
)
def test_warning_baseline_is_specific(tmp_path, monkeypatch, change, expected):
    source = "Item { property var value: upstream.caption }"
    (tmp_path / "Probe.qml").write_text(source if change != "source" else source + " // changed")
    entry = dict(
        file="Probe.qml",
        category="missing-property",
        severity="warning",
        message="Known upstream member",
        source=source,
        column=28,
        count=1,
    )
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/qml-warning-baseline.json").write_text(json.dumps({"entries": [entry]}))
    warning = dict(
        id=entry["category"], type="warning", message=entry["message"], line=1, column=28
    )
    if change == "new":
        warning["message"] = "Different member"
    if change == "error":
        warning["type"] = "error"
    warnings = [] if change == "removed" else [warning] * (2 if change == "duplicate" else 1)
    monkeypatch.setattr(
        gate,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=-11 if change == "crash" else (255 if warnings else 0),
            stdout=json.dumps(
                {
                    "files": [
                        {"filename": "Probe.qml", "success": not warnings, "warnings": warnings}
                    ]
                }
            ),
        ),
    )
    result = gate.lint(tmp_path, tmp_path)
    assert result["status"] == expected
    assert result["acceptedWarnings"] == (1 if change in ("known", "duplicate", "crash") else 0)


def test_informational_lint_note_is_not_a_warning(tmp_path, monkeypatch):
    (tmp_path / "Probe.qml").write_text("import QtQuick\nItem {}")
    monkeypatch.setattr(
        gate,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "files": [
                        {
                            "filename": "Probe.qml",
                            "success": True,
                            "warnings": [{"type": "info", "id": "unused-imports", "line": 1}],
                        }
                    ]
                }
            ),
        ),
    )
    result = gate.lint(tmp_path, tmp_path)
    assert result["status"] == "passed"
    assert result["informationalDiagnostics"] == 1
    assert result["unexpectedDiagnostics"] == 0


@pytest.mark.parametrize("missing", ["success", "warnings"])
def test_missing_lint_file_fields_are_incomplete(tmp_path, monkeypatch, missing):
    (tmp_path / "Probe.qml").write_text("Item {}")
    item = {"filename": "Probe.qml", "success": True, "warnings": []}
    del item[missing]
    monkeypatch.setattr(
        gate,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0, stdout=json.dumps({"files": [item]})
        ),
    )
    with pytest.raises(ValueError, match="Incomplete lint file result"):
        gate.lint(tmp_path, tmp_path)
