"""Device-free evidence for ADR 0004; never instantiate the live theme singleton."""

import json
import os
import re
import shutil

import pytest

from scripts import validate_platform as gate

pytestmark = pytest.mark.skipif(
    os.environ.get("SONARCHY_PLATFORM_TESTS") != "1", reason="Requires recorded Omarchy/Qt host"
)

SPACING_DEFAULTS = {
    "hairline": 1,
    "xxs": 2,
    "xs": 3,
    "sm": 4,
    "md": 6,
    "lg": 8,
    "xl": 10,
    "xxl": 12,
    "xxxl": 14,
    "huge": 18,
    "controlGap": 8,
    "controlPaddingX": 10,
    "controlPaddingY": 6,
    "inputPaddingY": 7,
    "controlHeight": 28,
    "popupRowHeight": 28,
    "dropdownWidth": 240,
    "searchableDropdownWidth": 260,
    "numberFieldWidth": 120,
    "searchablePopupMinHeight": 220,
    "rowGap": 8,
    "rowPaddingX": 12,
    "labelGap": 4,
    "panelGap": 14,
    "panelPadding": 18,
    "popupPadding": 14,
}


def _spacing_fixture(directory, source, named):
    directory.mkdir()
    match = re.search(
        r"  readonly property QtObject spacing: QtObject \{\n(.*?)\n  \}", source, re.S
    )
    assert match is not None, "Review changed spacing declaration"
    body = match[1]
    roles = re.findall(r"property (\w+) (\w+):", body)
    assert len(roles) == len(SPACING_DEFAULTS) + 1, "Review changed spacing role inventory"
    assert dict((name, kind) for kind, name in roles) == {
        "scale": "real",
        **dict.fromkeys(SPACING_DEFAULTS, "int"),
    }, "Review changed spacing role inventory/types"
    helpers = []
    for name in ("spaceReal", "space", "spacingToken"):
        found = re.findall(rf"^  function {name}\([^\n]*\) \{{\n.*?^  \}}", source, re.M | re.S)
        assert len(found) == 1
        helpers.append(found[0])
    declaration = match[0]
    scale = re.findall(r"^  readonly property real effectiveSpacingScale: .+$", source, re.M)
    assert len(scale) == 1, "Review changed spacing scale declaration"
    if named:
        (directory / "SpacingRoles.qml").write_text(
            "import QtQuick\nQtObject {\n"
            + "\n".join(
                f"required property {kind} input_{name}\n"
                f"readonly property {kind} {name}: input_{name}"
                for kind, name in roles
            )
            + "\n}\n"
        )
        declaration = (
            "readonly property SpacingRoles spacing: SpacingRoles {\n"
            + re.sub(r"readonly property \w+ (\w+):", r"input_\1:", body)
            + "\n}\n"
        )
    # Copy actual pure expressions/helpers; never instantiate live Style.
    (directory / "Provider.qml").write_text(
        "import QtQuick\nQtObject { id: root\n"
        "property real spacingScale: 1\nproperty real fontScale: 1\n"
        "property bool spacingScaleWithFont: true\nproperty var spacingOverrides: ({})\n"
        + scale[0]
        + "\n"
        + "\n".join(helpers)
        + "\n"
        + declaration
        + "\n}\n"
    )
    (directory / "Consumer.qml").write_text(
        "import QtQuick\nQtObject {\nproperty Provider provider: Provider {}\n"
        + "\n".join(f"property {kind} {name}: provider.spacing.{name}" for kind, name in roles)
        + "\nreadonly property var defaults: ("
        + json.dumps(SPACING_DEFAULTS)
        + ")\n}\n"
    )
    shutil.copy2(gate.ROOT / "tests/qml/spacing/tst_Spacing.qml", directory / "tst_Spacing.qml")
    return directory


def _check_spacing_runtime(directory):
    result = gate.run(
        [gate.RUNNER, "-input", str(directory / "tst_Spacing.qml")],
        cwd=directory,
        env={
            "PATH": os.defpath,
            "HOME": str(directory),
            "QT_QPA_PLATFORM": "offscreen",
            "QT_QUICK_CONTROLS_STYLE": "Basic",
            "QT_STYLE_OVERRIDE": "Fusion",
        },
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0 and "QWARN" not in output, (
        "Spacing runtime contract failed:\n" + output
    )


@pytest.mark.parametrize("named", [False, True], ids=["actual-anonymous", "named-proposal"])
def test_spacing_roles_preserve_actual_live_readonly_contract(tmp_path, named):
    source = (gate.SHELL / "Commons/Style.qml").read_text()
    directory = _spacing_fixture(tmp_path / "spacing", source, named)
    result = gate.run(
        [gate.LINTER, "--ignore-settings", "-W", "0", "--json", "-", "Consumer.qml"], cwd=directory
    )
    warnings = json.loads(result.stdout)["files"][0]["warnings"]
    if named:
        assert result.returncode == 0 and not warnings, warnings
    else:
        assert result.returncode != 0
        assert len(warnings) == len(SPACING_DEFAULTS) + 1
        assert all(warning["id"] == "missing-property" for warning in warnings)
    _check_spacing_runtime(directory)


def test_installed_spacing_declaration_loses_static_member_information(tmp_path):
    (tmp_path / "qs").symlink_to(gate.SHELL, target_is_directory=True)
    (tmp_path / "Probe.qml").write_text(
        "import QtQuick\nimport qs.Commons\nQtObject {\n"
        " property int hairline: Style.spacing.hairline\n"
        " property int labelGap: Style.spacing.labelGap\n}\n"
    )
    result = gate.lint(tmp_path, tmp_path)
    assert result["status"] == "failed"
    assert [item["category"] for item in result["diagnostics"]] == [
        "missing-property",
        "missing-property",
    ]


@pytest.mark.parametrize("drift", ["removed", "wrong-type", "writable", "frozen"])
def test_spacing_contract_rejects_role_drift(tmp_path, drift):
    source = (gate.SHELL / "Commons/Style.qml").read_text()
    original = '    readonly property int labelGap: root.spacingToken("label-gap", 4)'
    assert source.count(original) == 1
    replacements = {
        "removed": "",
        "wrong-type": original.replace("property int", "property string"),
        "writable": original.replace("readonly property", "property"),
        "frozen": "    readonly property int labelGap: 4",
    }
    with pytest.raises(
        AssertionError, match=r"spacing role inventory|Spacing runtime contract failed"
    ):
        directory = _spacing_fixture(
            tmp_path / "drift", source.replace(original, replacements[drift]), False
        )
        _check_spacing_runtime(directory)


def test_named_spacing_contract_rejects_a_genuine_consumer_typo(tmp_path):
    source = (gate.SHELL / "Commons/Style.qml").read_text()
    directory = _spacing_fixture(tmp_path / "typo", source, True)
    consumer = directory / "Consumer.qml"
    consumer.write_text(
        consumer.read_text().replace("provider.spacing.labelGap", "provider.spacing.labelGpa")
    )
    result = gate.run(
        [gate.LINTER, "--ignore-settings", "-W", "0", "--json", "-", "Consumer.qml"], cwd=directory
    )
    warnings = json.loads(result.stdout)["files"][0]["warnings"]
    assert result.returncode != 0 and len(warnings) == 1
    assert warnings[0]["id"] == "missing-property" and "labelGpa" in warnings[0]["message"]


def test_installed_declarations_lose_static_member_information(tmp_path):
    (tmp_path / "qs").symlink_to(gate.SHELL, target_is_directory=True)
    probe = tmp_path / "Probe.qml"
    probe.write_text(
        "import QtQuick\nimport qs.Commons\nQtObject {\n"
        " property string family: Style.font.family\n"
        " property color text: Color.popups.text\n}\n"
    )
    result = gate.lint(tmp_path, tmp_path)
    assert result["status"] == "failed"
    assert [item["category"] for item in result["diagnostics"]] == [
        "missing-property",
        "missing-property",
    ]
    _verify_popup_runtime_contract(tmp_path / "popup-runtime")


def _verify_popup_runtime_contract(directory):
    source = (gate.SHELL / "Commons/Color.qml").read_text()
    declaration = re.search(
        r"  readonly property QtObject popups: QtObject \{\n.*?\n  \}", source, re.S
    )
    pick = re.search(r"  function pick\(key, fallback\) \{\n.*?\n  \}", source, re.S)
    assert declaration is not None and pick is not None, "Review changed popup declaration"
    directory.mkdir()
    # Copy the actual declaration and pure lookup helper, not the live singleton.
    # Unrelated composed background/border colors use deterministic fixture inputs.
    (directory / "PopupProvider.qml").write_text(
        "import QtQuick\nQtObject { id: root\n"
        'property color foreground: "#123456"\n'
        'property color background: "#101112"\n'
        'property color accent: "#abcdef"\n'
        "property var shellValues: ({})\n"
        "function composed(_key, _alphaKey, fallback, _alpha) { return fallback }\n"
        + pick[0]
        + "\n"
        + declaration[0]
        + "\n}\n"
    )
    (directory / "tst_PopupContract.qml").write_text(
        "import QtQuick\nimport QtTest\nItem {\n"
        "PopupProvider { id: provider }\n"
        'TestCase { name: "PopupContract"\n'
        "function test_text_exists_updates_and_is_writable() {\n"
        'verify(provider.popups.text !== undefined, "text must exist");\n'
        'verify(Qt.colorEqual(provider.popups.text, "#123456"), "initial fallback");\n'
        'provider.foreground = "#654321";\n'
        'verify(Qt.colorEqual(provider.popups.text, "#654321"), "live fallback");\n'
        'provider.shellValues = ({"popups.text": "#123abc"});\n'
        'verify(Qt.colorEqual(provider.popups.text, "#123abc"), "theme override");\n'
        'provider.shellValues = ({"popups.text": "#654cba"});\n'
        'verify(Qt.colorEqual(provider.popups.text, "#654cba"), "live theme value");\n'
        "provider.shellValues = ({});\n"
        'verify(Qt.colorEqual(provider.popups.text, "#654321"), "restore fallback");\n'
        "verify(provider.popups.genuinelyMissing === undefined);\n"
        'var writable = false; try { provider.popups.text = "#abcdef"; writable = true } '
        'catch (error) {} verify(writable, "text must remain writable");\n'
        'verify(Qt.colorEqual(provider.popups.text, "#abcdef"), "explicit assignment");\n'
        "}\n}\n}\n"
    )
    result = gate.run(
        [gate.RUNNER, "-input", str(directory)],
        cwd=directory,
        env={
            "PATH": os.defpath,
            "HOME": str(directory),
            "QT_QPA_PLATFORM": "offscreen",
            "QT_QUICK_CONTROLS_STYLE": "Basic",
            "QT_STYLE_OVERRIDE": "Fusion",
        },
    )
    assert result.returncode == 0, (
        "Popup runtime contract failed:\n" + result.stdout + result.stderr
    )


@pytest.mark.parametrize("drift", ["removed", "renamed", "readonly", "frozen"])
def test_popup_drift_cannot_pass_static_category_probe(tmp_path, monkeypatch, drift):
    """Mutate only the external declaration; exercise the actual contract probe."""
    shell = tmp_path / "shell"
    shutil.copytree(gate.SHELL / "Commons", shell / "Commons")
    color = shell / "Commons/Color.qml"
    source = color.read_text()
    match = re.search(
        r"  readonly property QtObject popups: QtObject \{\n(.*?)\n  \}", source, re.S
    )
    assert match is not None
    text_role = re.search(r"^    property color text: .*\n", match[0], re.M)
    assert text_role is not None
    replacements = {
        "removed": "",
        "renamed": text_role[0].replace("color text:", "color renamedText:", 1),
        "readonly": text_role[0].replace("property color", "readonly property color", 1),
        "frozen": '    property color text: "#123456"\n',
    }
    declaration = match[0].replace(text_role[0], replacements[drift], 1)
    color.write_text(source[: match.start()] + declaration + source[match.end() :])
    monkeypatch.setattr(gate, "SHELL", shell)
    probe = tmp_path / "probe"
    probe.mkdir()
    with pytest.raises(AssertionError, match="Popup runtime contract failed"):
        test_installed_declarations_lose_static_member_information(probe)


@pytest.mark.parametrize(
    "named", [False, True], ids=["actual-anonymous-declaration", "named-proposal"]
)
def test_real_font_declaration_runtime_binding_and_named_proposal(tmp_path, named):
    source = (gate.SHELL / "Commons/Style.qml").read_text()
    match = re.search(r"  readonly property QtObject font: QtObject \{\n(.*?)\n  \}", source, re.S)
    assert match is not None, "Review the probe when upstream declaration changes"
    body = match[1]
    roles = re.findall(r"readonly property (\w+) (\w+):", body)
    assert ("string", "family") in roles and ("int", "body") in roles
    declaration = match[0]
    if named:
        (tmp_path / "FontRoles.qml").write_text(
            "import QtQuick\nQtObject {\n"
            + "\n".join(
                f"required property {kind} input_{name}\n"
                f"readonly property {kind} {name}: input_{name}"
                for kind, name in roles
            )
            + "\n}\n"
        )
        declaration = (
            "readonly property FontRoles font: FontRoles {\n"
            + re.sub(r"readonly property \w+ (\w+):", r"input_\1:", body)
            + "\n}"
        )
    # Only underlying theme inputs are supplied by the fixture. Font declaration
    # expressions are copied verbatim from the installed source; no singleton IO.
    (tmp_path / "Provider.qml").write_text(
        "import QtQuick\nQtObject { id: root\n"
        'property string fontFamily: "fixture-a"\n'
        "property string resolvedFontFamily: fontFamily\n"
        "property string menuFontFamily: fontFamily\n"
        "property int fontBaseSize: 12\n"
        "function fontToken(name, fallback) { return fallback }\n"
        "function fontPx(scale) { return Math.round(fontBaseSize * scale) }\n"
        + declaration
        + "\n}\n"
    )
    (tmp_path / "Consumer.qml").write_text(
        "import QtQuick\nQtObject {\n"
        "property Provider provider: Provider {}\n"
        "property string family: provider.font.family\n"
        "property int bodySize: provider.font.body\n}\n"
    )
    lint = gate.run(
        [gate.LINTER, "--ignore-settings", "-W", "0", "--json", "-", "Consumer.qml"], cwd=tmp_path
    )
    diagnostics = json.loads(lint.stdout)["files"][0]["warnings"]
    if named:
        assert lint.returncode == 0, diagnostics
        assert not diagnostics
    else:
        assert lint.returncode != 0
        assert all(item["id"] == "missing-property" for item in diagnostics)
    (tmp_path / "tst_FontContract.qml").write_text(
        "import QtQuick\nimport QtTest\nItem {\n"
        "Consumer { id: consumer }\n"
        'TestCase { name: "FontContract"\n'
        "function test_live_bindings() {\n"
        'compare(consumer.family, "fixture-a"); compare(consumer.bodySize, 12);\n'
        'consumer.provider.fontFamily = "fixture-b"; consumer.provider.fontBaseSize = 20;\n'
        'compare(consumer.family, "fixture-b"); compare(consumer.bodySize, 20);\n'
        "verify(consumer.provider.font.genuinelyMissing === undefined);\n"
        'var rejected = false; try { consumer.provider.font.family = "override" } '
        "catch (error) { rejected = true } verify(rejected);\n"
        "}\n}\n}\n"
    )
    result = gate.run(
        [gate.RUNNER, "-input", str(tmp_path)],
        cwd=tmp_path,
        env={
            "PATH": os.defpath,
            "HOME": str(tmp_path),
            "QT_QPA_PLATFORM": "offscreen",
            "QT_QUICK_CONTROLS_STYLE": "Basic",
            "QT_STYLE_OVERRIDE": "Fusion",
        },
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_current_host_read_inventory():
    """Fail closed when this prototype's observed production surface changes."""
    widget = (gate.ROOT / "BarWidget.qml").read_text()
    assert set(re.findall(r"\bbar\.(\w+)", widget)) == {
        "shell",
        "fontFamily",
        "foreground",
        "barForeground",
    }
    assert 'bar.shell.serviceFor("io.github.surreptitiousfabric.sonarchy")' in widget
    base = (gate.SHELL / "Ui/BarWidget.qml").read_text()
    assert "property QtObject bar: null" in base
    assert "readonly property bool vertical: bar ? bar.vertical : false" in base
    assert "readonly property int barSize: bar ? bar.barSize : Style.bar.sizeHorizontal" in base
    host = (gate.SHELL / "plugins/bar/Bar.qml").read_text()
    declarations = set(re.findall(r"\bproperty (\w+) (\w+):", host))
    assert {
        ("var", "shell"),
        ("string", "fontFamily"),
        ("color", "foreground"),
        ("color", "barForeground"),
        ("bool", "vertical"),
        ("int", "barSize"),
    } <= declarations


def _host_fixture(directory):
    source = (gate.SHELL / "shell.qml").read_text()
    lookup = re.search(r"  function serviceFor\(pluginId\) \{\n.*?\n  \}", source, re.S)
    assert lookup is not None, "Review changed installed service lookup"
    assert lookup[0].strip() == (
        "function serviceFor(pluginId) {\n    return _services[String(pluginId)] || null\n  }"
    ), "Review service lookup purity before extracting changed source"
    shutil.copytree(gate.ROOT / "tests/qml/host-context", directory)
    # Reuse only the actual pure lookup, never the live shell/registry or ensureService.
    (directory / "Registry.qml").write_text(
        "import QtQuick\nQtObject {\nproperty var _services: ({})\n" + lookup[0] + "\n}\n"
    )
    return directory


@pytest.mark.parametrize("typo", [False, True], ids=["named-contract", "genuine-typo"])
def test_named_host_context_strict_lint(tmp_path, typo):
    directory = _host_fixture(tmp_path / "host")
    if typo:
        consumer = directory / "HostConsumer.qml"
        source = consumer.read_text()
        assert source.count("root.activeContext.fontFamily") == 1
        consumer.write_text(
            source.replace("root.activeContext.fontFamily", "root.activeContext.fontFamliy")
        )
    result = gate.run(
        [
            gate.LINTER,
            "--ignore-settings",
            "-W",
            "0",
            "--json",
            "-",
            "BarHostContext.qml",
            "HostConsumer.qml",
        ],
        cwd=directory,
    )
    diagnostics = [
        warning for file in json.loads(result.stdout)["files"] for warning in file["warnings"]
    ]
    if typo:
        assert result.returncode != 0
        assert any(
            item["id"] == "missing-property" and "fontFamliy" in item["message"]
            for item in diagnostics
        )
    else:
        assert result.returncode == 0, diagnostics
        assert not diagnostics


def _run_host_fixture(directory):
    return gate.run(
        [gate.RUNNER, "-input", str(directory)],
        cwd=directory,
        env={
            "PATH": os.defpath,
            "HOME": str(directory),
            "QT_QPA_PLATFORM": "offscreen",
            "QT_QUICK_CONTROLS_STYLE": "Basic",
            "QT_STYLE_OVERRIDE": "Fusion",
        },
    )


def test_named_host_context_runtime(tmp_path):
    result = _run_host_fixture(_host_fixture(tmp_path / "host"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "HostContext::test_live_bindings()" in result.stdout
    assert "QWARN" not in result.stdout + result.stderr


@pytest.mark.parametrize("drift", ["fontFamily", "foreground", "barForeground", "ownership"])
def test_host_context_runtime_rejects_binding_and_ownership_drift(tmp_path, drift):
    directory = _host_fixture(tmp_path / "host")
    if drift == "ownership":
        path = directory / "HostConsumer.qml"
        original = "&& root.hostContext.host === root.bar "
        replacement = ""
        failed_test = "test_bar_replaced_first"
    else:
        path = directory / "BarHostContext.qml"
        original = f"{drift}: root.input{drift[0].upper()}{drift[1:]}"
        # Preserve the initial value: only an actual live-update check detects this.
        value = {"fontFamily": "host-a", "foreground": "#123456", "barForeground": "#234567"}[drift]
        replacement = f'{drift}: "{value}"'
        failed_test = "test_live_bindings"
    source = path.read_text()
    assert source.count(original) == 1
    path.write_text(source.replace(original, replacement))
    result = _run_host_fixture(directory)
    assert result.returncode != 0, "Broken host contract unexpectedly passed"
    assert re.search(rf"FAIL!\s+:.*HostContext::{failed_test}\(\)", result.stdout), (
        result.stdout + result.stderr
    )
