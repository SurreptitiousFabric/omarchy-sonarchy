"""Explicit release-host gate; never install or start the plugin/backend."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL = Path("/usr/share/omarchy/shell")
LINTER = "/usr/lib/qt6/bin/qmllint"
RUNNER = "/usr/lib/qt6/bin/qmltestrunner"
OMARCHY = "/usr/share/omarchy/bin/omarchy"


def run(command, cwd=ROOT, env=None):
    return subprocess.run(  # noqa: S603 - fixed tool argv, trusted candidate files
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def lint(root, imports):
    files = sorted(path.name for path in root.glob("*.qml"))
    if not files:
        raise ValueError("No QML files")
    result = run(
        [
            LINTER,
            "--ignore-settings",
            "-W",
            "0",
            "--import",
            "error",
            "-I",
            str(imports),
            "--json",
            "-",
            *files,
        ],
        cwd=root,
    )
    report = json.loads(result.stdout)
    checked = report.get("files", [])
    if sorted(item["filename"] for item in checked) != files:
        raise ValueError("Incomplete lint report")
    diagnostics = [
        {
            "file": item["filename"],
            "line": warning.get("line"),
            "category": warning.get("id"),
            "severity": warning.get("type"),
        }
        for item in checked
        for warning in item.get("warnings", [])
    ]
    passed = result.returncode == 0 and all(item.get("success") is True for item in checked)
    return {"status": "passed" if passed else "failed", "files": files, "diagnostics": diagnostics}


def manifest(root):
    result = run([OMARCHY, "plugin", "validate", str(root)])
    return {"status": "passed" if result.returncode == 0 else "failed"}


def components(root):
    result = run(["/bin/bash", str(root / "tests/qml/run-component-tests.sh")], cwd=root)
    return {"status": "passed" if result.returncode == 0 else "failed"}


def platform():
    for path in [
        Path(LINTER),
        Path(RUNNER),
        Path(OMARCHY),
        SHELL / "Commons/qmldir",
        SHELL / "Ui/qmldir",
    ]:
        if not path.is_file():
            raise ValueError("Required platform tooling unavailable")
    versions = run(
        ["/usr/bin/pacman", "-Q", "omarchy", "quickshell", "qt6-base", "qt6-declarative"]
    )
    if versions.returncode:
        raise ValueError("Platform package versions unavailable")
    digest = hashlib.sha256()
    for path in sorted(SHELL.rglob("*")):
        if path.is_file() and (path.suffix == ".qml" or path.name == "qmldir"):
            digest.update(str(path.relative_to(SHELL)).encode() + b"\0" + path.read_bytes())
    return {
        "packages": versions.stdout.splitlines(),
        "architecture": os.uname().machine,
        "shellQmlSha256": digest.hexdigest(),
    }


def main():
    report = {"status": "incomplete", "stages": {}}
    try:
        candidate = run(["/usr/bin/git", "rev-parse", "HEAD"])
        dirty = run(["/usr/bin/git", "status", "--porcelain", "--untracked-files=all"])
        if (
            candidate.returncode
            or dirty.returncode
            or dirty.stdout
            or sys.argv[1:] != [candidate.stdout.strip()]
        ):
            raise ValueError("Clean exact candidate required")
        report["candidate"] = candidate.stdout.strip()
        report["platform"] = platform()
        # Real modules are read-only symlinked under their actual qs namespace.
        with tempfile.TemporaryDirectory(prefix="sonarchy-platform-") as directory:
            imports = Path(directory)
            (imports / "qs").symlink_to(SHELL, target_is_directory=True)
            report["stages"]["manifest"] = manifest(ROOT)
            report["stages"]["qml"] = lint(ROOT, imports)
            report["stages"]["components"] = components(ROOT)
            controls = run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    "tests/test_platform_host.py",
                    "tests/test_qml_type_contract.py",
                ],
                # Host selection/collection options must not bypass required controls.
                env={**os.environ, "PYTEST_ADDOPTS": "", "SONARCHY_PLATFORM_TESTS": "1"},
            )
            report["stages"]["negativeControls"] = {
                "status": "passed" if controls.returncode == 0 else "failed"
            }
        report["status"] = (
            "passed"
            if all(stage["status"] == "passed" for stage in report["stages"].values())
            else "failed"
        )
    except Exception:  # noqa: BLE001 - bounded diagnostics, no raw host paths/config/output
        report["message"] = "Platform gate incomplete; check tooling and clean candidate."
    print(json.dumps(report, sort_keys=True))
    return {"passed": 0, "failed": 1, "incomplete": 2}[report["status"]]


if __name__ == "__main__":
    sys.exit(main())
