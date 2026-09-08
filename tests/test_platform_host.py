"""Real-tool negative controls, required by the explicit release-host gate."""

import json
import os
import re
import shutil
import tempfile

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


def test_navigation_outer_ids_are_bound_without_suppressing_other_diagnostics(tmp_path, imports):
    shutil.copy2(gate.ROOT / "SonarchyNavigation.qml", tmp_path / "SonarchyNavigation.qml")
    result = gate.lint(tmp_path, imports)
    assert not [item for item in result["diagnostics"] if item["category"] == "unqualified"]
    # The complete platform gate still requires all diagnostics to be resolved;
    # shared theme type limitations remain tracked in #91, not suppressed here.


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


def _bar_function(source, name):
    matches = re.findall(rf"^  function {name}\([^\n]*\) \{{\n.*?^  \}}", source, re.M | re.S)
    assert len(matches) == 1, f"Expected one production {name} function"
    return matches[0]


@pytest.fixture
def private_qml_env(tmp_path):
    # Keep Quickshell's IPC socket below the Unix socket path-length limit.
    with tempfile.TemporaryDirectory(prefix="sonarchy-qml-", dir="/tmp") as runtime:
        yield {
            "PATH": os.defpath,
            "HOME": str(tmp_path),
            "XDG_RUNTIME_DIR": runtime,
            "XDG_CONFIG_HOME": str(tmp_path / "config"),
            "XDG_CACHE_HOME": str(tmp_path / "cache"),
            "XDG_DATA_HOME": str(tmp_path / "data"),
            "QT_QPA_PLATFORM": "offscreen",
            "QT_QUICK_BACKEND": "software",
            "QT_STYLE_OVERRIDE": "Fusion",
            "QT_QUICK_CONTROLS_STYLE": "Basic",
        }


def test_bar_widget_local_bindings_and_dispatch_are_statically_resolved(imports):
    result = gate.run(
        [
            gate.LINTER,
            "--ignore-settings",
            "-W",
            "0",
            "--import",
            "error",
            "-I",
            str(imports),
            "--json",
            "-",
            "BarWidget.qml",
        ],
    )
    warnings = json.loads(result.stdout)["files"][0]["warnings"]
    assert not [warning for warning in warnings if warning["id"] == "unqualified"]
    assert not [
        warning
        for warning in warnings
        if any(member in warning["message"] for member in ("activeFocusItem", "ensureVisible"))
    ]
    # This focused assertion does not permit remaining theme/host diagnostics
    # in the complete gate, which still requires every root file to pass.


def test_bar_widget_uses_actual_focus_in_a_real_quickshell_window(tmp_path, private_qml_env):
    source = (gate.ROOT / "BarWidget.qml").read_text()
    functions = "\n".join(
        _bar_function(source, name)
        for name in (
            "activeControl",
            "keyboardFocusable",
            "activateControlOrOwner",
            "activateFocusedControl",
        )
    )
    fixture = (gate.ROOT / "tests/qml/bar-widget/FocusProbe.qml.in").read_text()
    (tmp_path / "shell.qml").write_text(fixture.replace("// PRODUCTION_FUNCTIONS", functions))
    result = gate.run(
        ["/usr/bin/qs", "--no-color", "-p", str(tmp_path / "shell.qml")],
        cwd=tmp_path,
        env=private_qml_env,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0 and "BAR_FOCUS_PASS" in output, output
    assert "BAR_FOCUS_FAIL" not in output
    assert "ERROR" not in output


def test_native_keyboard_focus_scrolls_the_production_page(tmp_path, imports, private_qml_env):
    for module in ("Commons", "Ui"):
        (tmp_path / module).symlink_to(gate.SHELL / module, target_is_directory=True)
    source = (gate.ROOT / "BarWidget.qml").read_text()
    functions = [
        _bar_function(source, name) for name in ("effectivelyUsable", "ensureFocusedVisible")
    ]
    # An absent observer is the original failing-before production state.
    if "function revealActiveFocus(" in source:
        functions.append(_bar_function(source, "revealActiveFocus"))
    connections = re.findall(
        r"^  Connections \{\n    target: keyCatcher.Window.window\n.*?^  \}",
        source,
        re.M | re.S,
    )
    assert len(connections) <= 1
    fixture = (gate.ROOT / "tests/qml/bar-widget/FocusScrollProbe.qml.in").read_text()
    fixture = fixture.replace("// PRODUCTION_FUNCTIONS", "\n".join(functions))
    fixture = fixture.replace("// PRODUCTION_FOCUS_CONNECTION", "\n".join(connections))
    page = (gate.ROOT / "SonarchyNowPage.qml").read_text()
    fixture = fixture.replace("// PRODUCTION_PAGE_SCROLL", _bar_function(page, "ensureVisible"))
    shutil.copy2(gate.ROOT / "SonarchyDropdown.qml", tmp_path / "SonarchyDropdown.qml")
    (tmp_path / "shell.qml").write_text(fixture)
    result = gate.run(
        ["/usr/bin/qs", "--no-color", "-p", str(tmp_path / "shell.qml")],
        cwd=tmp_path,
        env={**private_qml_env, "QML_IMPORT_PATH": str(imports)},
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0 and "BAR_FOCUS_SCROLL_PASS" in output, output
    assert "BAR_FOCUS_SCROLL_FAIL" not in output and "ERROR" not in output, output


def test_alarm_confirmation_keeps_keyboard_focus_visible(tmp_path, imports, private_qml_env):
    for module in ("Commons", "Ui"):
        (tmp_path / module).symlink_to(gate.SHELL / module, target_is_directory=True)
    for source in gate.ROOT.glob("Sonarchy*.qml"):
        shutil.copy2(source, tmp_path / source.name)
    shutil.copy2(
        gate.ROOT / "tests/qml/bar-widget/ConfirmationFocusProbe.qml", tmp_path / "shell.qml"
    )
    result = gate.run(
        ["/usr/bin/qs", "--no-color", "-p", str(tmp_path / "shell.qml")],
        cwd=tmp_path,
        env={**private_qml_env, "QML_IMPORT_PATH": str(imports)},
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0 and "CONFIRM_FOCUS_PASS" in output, output
    assert "CONFIRM_FOCUS_FAIL" not in output and "ERROR" not in output, output
    assert "WARN scene:" not in output and "Binding loop" not in output, output


def test_bar_widget_components_keep_their_owner_in_the_installed_hero_loaders(
    tmp_path, private_qml_env
):
    source = (gate.ROOT / "BarWidget.qml").read_text()
    components = []
    for name in ("heroIconComponent", "refreshControlComponent"):
        matches = re.findall(rf"^  Component \{{\n    id: {name}\n.*?^  \}}", source, re.M | re.S)
        assert len(matches) == 1
        components.append(matches[0])
    pragmas = "\n".join(line for line in source.splitlines() if line.startswith("pragma "))
    template = (gate.ROOT / "tests/qml/bar-widget/Owner.qml.in").read_text()
    (tmp_path / "Owner.qml").write_text(
        pragmas
        + "\n"
        + template.replace("// PRODUCTION_COMPONENTS", "\n".join(components)).replace(
            "// PRODUCTION_REFRESH", _bar_function(source, "refreshPanel")
        )
    )
    shutil.copy2(gate.ROOT / "tests/qml/bar-widget/tst_Hero.qml", tmp_path / "tst_Hero.qml")
    imports = tmp_path / "imports"
    shutil.copytree(gate.ROOT / "tests/qml/imports", imports)
    for name in ("PanelHero", "OpticalGlyph"):
        (imports / f"qs/Ui/{name}.qml").symlink_to(gate.SHELL / f"Ui/{name}.qml")
    qmldir = imports / "qs/Ui/qmldir"
    qmldir.write_text(qmldir.read_text() + "\nPanelHero 1.0 PanelHero.qml\n")
    style = imports / "qs/Commons/Style.qml"
    style.write_text(
        style.read_text().replace(
            'property string family: "monospace"',
            'property string family: "monospace"\n'
            "    property int display: 24\n    property int title: 18",
        )
    )
    result = gate.run(
        [gate.RUNNER, "-input", str(tmp_path / "tst_Hero.qml"), "-import", str(imports)],
        cwd=tmp_path,
        env=private_qml_env,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_bar_widget_scroll_dispatch_reaches_only_the_active_page(tmp_path, private_qml_env):
    source = (gate.ROOT / "BarWidget.qml").read_text()
    fixture = (gate.ROOT / "tests/qml/bar-widget/tst_Dispatch.qml.in").read_text()
    probe = tmp_path / "tst_Dispatch.qml"
    probe.write_text(
        fixture.replace("// PRODUCTION_DISPATCH", _bar_function(source, "ensureFocusedVisible"))
    )
    result = gate.run([gate.RUNNER, "-input", str(probe)], cwd=tmp_path, env=private_qml_env)
    assert result.returncode == 0, result.stdout + result.stderr


def test_bar_widget_layout_fits_the_real_host_content_bounds(tmp_path, imports, private_qml_env):
    for module in ("Commons", "Ui"):
        (tmp_path / module).symlink_to(gate.SHELL / module, target_is_directory=True)
    source = (gate.ROOT / "BarWidget.qml").read_text()
    columns = re.findall(
        r"^      (?:Column|ColumnLayout) \{\n        id: panelColumn\n"
        r".*?^      \}\n(?=    \}\n  \}\n\})",
        source,
        re.M | re.S,
    )
    assert len(columns) == 1, "Review changed production panel boundary"
    heights = re.findall(r"^    contentHeight: (.*?)\n\n    PanelKeyCatcher", source, re.M | re.S)
    assert len(heights) == 1
    host = (gate.SHELL / "Ui/KeyboardPanel.qml").read_text()
    inset = re.findall(r"^  readonly property real verticalContentInset: .*", host, re.M)
    assert len(inset) == 1
    fixture = (gate.ROOT / "tests/qml/bar-widget/tst_Layout.qml.in").read_text()
    fixture = fixture.replace("// PRODUCTION_PANEL_COLUMN", columns[0])
    fixture = fixture.replace(
        "// PRODUCTION_CONTENT_HEIGHT", "property real contentHeight: " + heights[0]
    )
    fixture = fixture.replace("// ACTUAL_HOST_INSET", inset[0].replace("root.", "popup."))
    fitting = "\n".join(
        _bar_function(host, name) for name in ("fittedContentHeight", "cappedContentHeight")
    )
    fixture = fixture.replace("// ACTUAL_HOST_FITTING", fitting.replace("root.", "popup."))
    (tmp_path / "tst_Layout.qml").write_text(fixture)
    for name in ("SonarchyDropdown", "SonarchyNavigation"):
        shutil.copy2(gate.ROOT / f"{name}.qml", tmp_path / f"{name}.qml")
    # Page internals and device data are outside this geometry boundary. Keep
    # the production viewport, all layout containers, navigation, actual host
    # controls, insets and fitting expressions. No backend is instantiated.
    page = """import QtQuick
Item {
  property var bar: null
  property var service: null
  property var device: null
  property color foreground: "white"
  property string fontFamily: "monospace"
  property bool showArtwork: false
  property int volumeStep: 2
}
"""
    for name in ("Now", "Browse", "Queue", "Rooms", "Sound", "System"):
        (tmp_path / f"Sonarchy{name}Page.qml").write_text(page)
    result = gate.run(
        ["/usr/bin/qs", "--no-color", "-p", str(tmp_path / "tst_Layout.qml")],
        cwd=tmp_path,
        env={**private_qml_env, "QML_IMPORT_PATH": str(imports)},
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0 and "POPUP_LAYOUT_PASS" in output, output
    assert "POPUP_LAYOUT_FAIL" not in output and "ERROR" not in output, output
    assert "Binding loop" not in output and "WARN qml:" not in output, output


def test_room_volume_row_fits_actual_host_controls(tmp_path, imports, private_qml_env):
    for module in ("Commons", "Ui"):
        (tmp_path / module).symlink_to(gate.SHELL / module, target_is_directory=True)
    for name in ("SonarchyRoomVolumeRow", "SonarchySlider"):
        shutil.copy2(gate.ROOT / f"{name}.qml", tmp_path / f"{name}.qml")
    shutil.copy2(
        gate.ROOT / "tests/qml/bar-widget/RoomVolumeLayoutProbe.qml.in", tmp_path / "shell.qml"
    )
    result = gate.run(
        ["/usr/bin/qs", "--no-color", "-p", str(tmp_path / "shell.qml")],
        cwd=tmp_path,
        env={**private_qml_env, "QML_IMPORT_PATH": str(imports)},
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0 and "ROOM_VOLUME_LAYOUT_PASS" in output, output
    assert "ROOM_VOLUME_LAYOUT_FAIL" not in output and "ERROR" not in output, output
    assert "Binding loop" not in output and "WARN qml:" not in output, output


@pytest.mark.parametrize("page", ["SonarchyBrowsePage.qml", "SonarchyQueuePage.qml"])
def test_content_page_delegate_bindings_are_statically_resolved(imports, page):
    result = gate.run(
        [
            gate.LINTER,
            "--ignore-settings",
            "-W",
            "0",
            "--import",
            "error",
            "-I",
            str(imports),
            "--json",
            "-",
            page,
        ]
    )
    warnings = json.loads(result.stdout)["files"][0]["warnings"]
    assert not [warning for warning in warnings if warning["id"] == "unqualified"]
    assert not [warning for warning in warnings if 'Member "modelData"' in warning["message"]]
    # Anonymous platform theme properties remain failed in the complete gate.


def test_content_pages_do_not_emit_runtime_binding_warnings():
    result = gate.run(["/bin/bash", str(gate.ROOT / "tests/qml/run-component-tests.sh")])
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert not re.search(r"Sonarchy(?:Browse|Queue)Page\.qml:\d+.*(?:Unable|Error)", output), output


@pytest.mark.parametrize("page", ["Now", "Rooms", "Sound", "System"])
def test_remaining_page_owner_ids_are_statically_bound(imports, page):
    result = gate.run(
        [
            gate.LINTER,
            "--ignore-settings",
            "-W",
            "0",
            "--import",
            "error",
            "-I",
            str(imports),
            "--json",
            "-",
            f"Sonarchy{page}Page.qml",
        ]
    )
    warnings = json.loads(result.stdout)["files"][0]["warnings"]
    assert not [warning for warning in warnings if warning["id"] == "unqualified"]


def test_remaining_page_components_keep_live_owner_and_model_bindings(tmp_path, private_qml_env):
    template = (gate.ROOT / "tests/qml/page-owners/Owner.qml.in").read_text()
    for page in ("Now", "Rooms", "Sound", "System"):
        source = (gate.ROOT / f"Sonarchy{page}Page.qml").read_text()
        pragmas = "\n".join(line for line in source.splitlines() if line.startswith("pragma "))
        definitions = ""
        functions = ""
        if page == "Sound":
            definitions = re.findall(
                r"^  component NumberSetting: Column \{\n.*?^  \}", source, re.M | re.S
            )[0]
            instances = re.findall(r"^      NumberSetting \{\n.*?^      \}", source, re.M | re.S)
            assert len(instances) == 8
            body = "\n".join(instances[:2])
            functions = _bar_function(source, "available")
        else:
            delegates = list(re.finditer(r"^( +)delegate: \w+ \{\n.*?^\1\}", source, re.M | re.S))
            assert len(delegates) == {"Now": 1, "Rooms": 4, "System": 1}[page]
            body = "\n".join(
                f'Repeater {{ objectName: "rows{index}"; model: root.models[{index}] || []\n'
                + match[0]
                + "\n}"
                for index, match in enumerate(delegates)
            )
            if page == "Rooms":
                functions = "\n".join(
                    _bar_function(source, name) for name in ("roomStaged", "toggleStagedRoom")
                )
            if page == "System":
                functions = _bar_function(source, "arm") + "\n" + _bar_function(source, "can")
        (tmp_path / f"{page}Owner.qml").write_text(
            pragmas
            + "\n"
            + template.replace("// DEFINITIONS", definitions)
            .replace("// FUNCTIONS", functions)
            .replace("// INSTANCES", body)
        )
    for name in ("tst_Owners.qml", "PageService.qml"):
        shutil.copy2(gate.ROOT / f"tests/qml/page-owners/{name}", tmp_path / name)
    for name in ("SonarchyRoomVolumeRow.qml", "SonarchySlider.qml"):
        shutil.copy2(gate.ROOT / name, tmp_path / name)
    imports = tmp_path / "imports"
    shutil.copytree(gate.ROOT / "tests/qml/imports", imports)
    for name in ("PanelSlider", "OpticalGlyph"):
        (imports / f"qs/Ui/{name}.qml").symlink_to(gate.SHELL / f"Ui/{name}.qml")
    result = gate.run(
        [gate.RUNNER, "-input", str(tmp_path / "tst_Owners.qml"), "-import", str(imports)],
        cwd=tmp_path,
        env=private_qml_env,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0 and "QWARN" not in output, output
