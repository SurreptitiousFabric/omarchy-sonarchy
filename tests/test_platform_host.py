"""Real-tool negative controls, required by the explicit release-host gate."""

import os
import shutil

import pytest

from scripts import validate_platform as gate

pytestmark = pytest.mark.skipif(
    os.environ.get("SONARCHY_PLATFORM_TESTS") != "1",
    reason="Use the release-host platform gate; generic Python CI is not platform evidence",
)


@pytest.fixture
def imports(tmp_path):
    path = tmp_path / "imports"
    path.mkdir()
    (path / "qs").symlink_to(gate.SHELL, target_is_directory=True)
    return path


def test_real_imports_resolve(tmp_path, imports):
    (tmp_path / "Probe.qml").write_text(
        "import QtQuick\nimport qs.Commons\nimport qs.Ui\nPanelSlider {}\n"
    )
    assert gate.lint(tmp_path, imports)["status"] == "passed"


@pytest.mark.parametrize(
    "source", ["import QtQuick\nItem {", "import MissingSonarchyModule\nItem {}"]
)
def test_malformed_qml_or_missing_import_fails(tmp_path, imports, source):
    (tmp_path / "Probe.qml").write_text(source)
    assert gate.lint(tmp_path, imports)["status"] == "failed"


def test_malformed_manifest_fails(tmp_path):
    (tmp_path / "manifest.json").write_text('{"schemaVersion":1}')
    assert gate.manifest(tmp_path)["status"] == "failed"


def test_failing_component_is_not_success(tmp_path):
    shutil.copytree(gate.ROOT / "tests/qml", tmp_path / "tests/qml")
    for path in gate.ROOT.glob("*.qml"):
        shutil.copy2(path, tmp_path / path.name)
    (tmp_path / "tests/qml/tst_GateFailure.qml").write_text(
        'import QtQuick\nimport QtTest\nTestCase { name: "GateFailure"; '
        "function test_failure() { verify(false) } }\n"
    )
    assert gate.components(tmp_path)["status"] == "failed"
