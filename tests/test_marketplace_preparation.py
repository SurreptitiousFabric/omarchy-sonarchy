"""Device-free checks for the draft package, not marketplace approval."""

import hashlib
import os
import re
import shutil
import struct
import zlib

import pytest

from scripts import render_marketplace_preview as preview
from scripts.validate_platform import ROOT

CHECKLIST = [
    "The repository is public and contains installation and removal instructions.",
    "I have documented the plugin license and any external dependencies.",
    "I confirm that I own or have permission to submit this plugin and its preview assets.",
    "The plugin does not overwrite user configuration without explicit consent.",
    "I understand that approval is for listing and is not a security review.",
]


def test_submission_draft_keeps_exact_format_without_owner_attestation():
    body = (ROOT / "docs/marketplace-submission.md").read_text()
    assert re.findall(r"^### (.+)$", body, re.M) == [
        "Repository URL",
        "Category",
        "Tags",
        "Suggest a missing tag",
        "Maintainer notes",
        "Submission checklist",
    ]
    assert re.findall(r"^- \[ \] (.+)$", body, re.M) == CHECKLIST
    assert not re.search(r"\[[xX]\]", body)
    assert "### Category\n\nHardware\n" in body
    assert "### Tags\n\nmedia, bar, ai\n" in body
    assert "### Repository URL\n\nhttps://github.com/SurreptitiousFabric/omarchy-sonarchy\n" in body
    assert "OWNER-REVIEW DRAFT ONLY" in body and "HOLD" in body
    preparation = (ROOT / "docs/marketplace-preparation.md").read_text()
    assert "[Plugin]: Sonarchy" in preparation
    assert "not an ID reservation" in preparation
    assert "b6a2c19acf1de20261b63d2281d84ca3b6239a91" in preparation


def test_root_preview_matches_reviewed_asset_and_has_no_private_metadata():
    data = (ROOT / "preview.png").read_bytes()
    preview.validate_preview(data)
    preparation = (ROOT / "docs/marketplace-preparation.md").read_text()
    assert hashlib.sha256(data).hexdigest() in preparation
    for name in ("SonarchyQueuePage.qml", "SonarchyNavigation.qml"):
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() in preparation
    assert len(list(ROOT.glob("preview.*"))) == 1


def _chunk(kind, payload):
    content = kind + payload
    return struct.pack(">I", len(payload)) + content + struct.pack(">I", zlib.crc32(content))


@pytest.mark.parametrize(
    "drift", ["signature", "size", "metadata", "checksum", "truncated", "trailing", "dimensions"]
)
def test_preview_guard_rejects_invalid_or_unreviewed_artifacts(drift):
    data = (ROOT / "preview.png").read_bytes()
    cases = {
        "signature": b"not-png" + data[7:],
        "size": data + b"x" * (1024 * 1024),
        "metadata": data[:33] + _chunk(b"tEXt", b"fixture\0unreviewed") + data[33:],
        "checksum": data[:29] + bytes([data[29] ^ 1]) + data[30:],
        "truncated": data[:-1],
        "trailing": data + b"unreviewed",
        "dimensions": data[:8]
        + _chunk(b"IHDR", struct.pack(">II", 1281, 720) + data[24:29])
        + data[33:],
    }
    with pytest.raises(ValueError):
        preview.validate_preview(cases[drift])


def test_renderer_refuses_existing_file_before_any_qt_call(tmp_path, monkeypatch):
    output = tmp_path / "reviewed.png"
    output.write_bytes(b"existing reviewed asset")
    monkeypatch.setattr(preview.gate, "run", lambda *a, **k: pytest.fail("Unexpected Qt call"))
    with pytest.raises(ValueError, match="Output exists"):
        preview.render(output)
    assert output.read_bytes() == b"existing reviewed asset"


def test_renderer_refuses_unavailable_reference_font(tmp_path, monkeypatch):
    output = tmp_path / "new.png"
    monkeypatch.setattr(preview, "FONT", tmp_path / "missing-font")
    monkeypatch.setattr(preview.gate, "run", lambda *a, **k: pytest.fail("Unexpected Qt call"))
    with pytest.raises(ValueError, match="font is unavailable"):
        preview.render(output)
    assert not output.exists()


@pytest.mark.parametrize("drift", ["heading", "attestation"])
def test_draft_contract_rejects_format_or_unapproved_attestation(tmp_path, monkeypatch, drift):
    (tmp_path / "docs").mkdir()
    body = (ROOT / "docs/marketplace-submission.md").read_text()
    original, replacement = ("### Tags", "### Tag") if drift == "heading" else ("- [ ]", "- [x]")
    (tmp_path / "docs/marketplace-submission.md").write_text(body.replace(original, replacement, 1))
    shutil.copyfile(
        ROOT / "docs/marketplace-preparation.md", tmp_path / "docs/marketplace-preparation.md"
    )
    monkeypatch.setitem(globals(), "ROOT", tmp_path)
    with pytest.raises(AssertionError):
        test_submission_draft_keeps_exact_format_without_owner_attestation()


@pytest.mark.skipif(
    os.environ.get("SONARCHY_PLATFORM_TESTS") != "1", reason="Requires recorded Omarchy/Qt host"
)
@pytest.mark.parametrize("drift", ["mutation", "warning"])
def test_real_renderer_rejects_mutation_or_warning_before_output(tmp_path, monkeypatch, drift):
    shadow = tmp_path / "source"
    shutil.copytree(ROOT / "tests/qml/imports", shadow / "tests/qml/imports")
    (shadow / "docs/preview").mkdir(parents=True)
    for name in ("SonarchyQueuePage.qml", "SonarchyNavigation.qml"):
        shutil.copyfile(ROOT / name, shadow / name)
    source = (ROOT / "docs/preview/Preview.qml").read_text()
    marker = "compare(demoService.mutations, 0)"
    assert source.count(marker) == 1
    action = (
        "demoService.clearQueue()"
        if drift == "mutation"
        else 'console.warn("Deliberate preview warning")'
    )
    (shadow / "docs/preview/Preview.qml").write_text(
        source.replace(marker, action + "\n      " + marker)
    )
    monkeypatch.setattr(preview.gate, "ROOT", shadow)
    output = tmp_path / "unaccepted.png"
    with pytest.raises(ValueError, match="Isolated preview failed"):
        preview.render(output)
    assert not output.exists()
