"""Device-free evidence for ADR 0004; never instantiate the live theme singleton."""

import json
import os
import re

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
