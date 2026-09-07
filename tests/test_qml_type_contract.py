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
