"""Render an explicit demo asset; never load the shell, backend or user data."""

import argparse
import hashlib
import json
import os
import shutil
import struct
import tempfile
import zlib
from pathlib import Path

from scripts import validate_platform as gate

FONT = Path("/usr/share/fonts/TTF/JetBrainsMonoNerdFont-Regular.ttf")


def validate_preview(data):
    """Check our bounded static raster and reject text/EXIF/profile payloads."""
    if len(data) > 1024 * 1024 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Expected a PNG under 1 MiB")
    offset = 8
    kinds = []
    while offset + 12 <= len(data):
        length = struct.unpack_from(">I", data, offset)[0]
        kind = data[offset + 4 : offset + 8]
        end = offset + 12 + length
        if end > len(data) or kind not in {
            b"IHDR",
            b"IDAT",
            b"IEND",
            b"pHYs",
            b"sRGB",
            b"gAMA",
            b"cHRM",
        }:
            raise ValueError("Invalid or unreviewed PNG chunk")
        chunk = data[offset + 4 : end - 4]
        if zlib.crc32(chunk) != struct.unpack_from(">I", data, end - 4)[0]:
            raise ValueError("Invalid PNG checksum")
        kinds.append(kind)
        if kind == b"IHDR" and (
            length != 13 or struct.unpack_from(">II", data, offset + 8) != (1280, 720)
        ):
            raise ValueError("Expected 1280 by 720 preview")
        if kind == b"IEND" and (length or end != len(data)):
            raise ValueError("Unexpected trailing PNG data")
        offset = end
    if (
        offset != len(data)
        or not kinds
        or kinds[0] != b"IHDR"
        or kinds[-1] != b"IEND"
        or kinds.count(b"IHDR") != 1
        or b"IDAT" not in kinds
    ):
        raise ValueError("Incomplete PNG")


def render(output):
    if output.exists():
        raise ValueError("Output exists; render to a new path for explicit review")
    if not FONT.is_file():
        raise ValueError("Recorded demo font is unavailable; review provenance first")
    with tempfile.TemporaryDirectory(prefix="sonarchy-preview-") as directory:
        root = Path(directory)
        imports = root / "imports"
        shutil.copytree(gate.ROOT / "tests/qml/imports", imports)
        shutil.copyfile(gate.SHELL / "Ui/OpticalGlyph.qml", imports / "qs/Ui/OpticalGlyph.qml")
        # Existing test Buttons intentionally paint nothing. Add demo-only visuals
        # to the temporary stub, never to production or the shared test fixture.
        button = imports / "qs/Ui/Button.qml"
        source = button.read_text()
        if source.count("implicitWidth: 34") != 1:
            raise ValueError("Review changed visual-only Button stub")
        source = source.replace(
            "implicitWidth: 34", "implicitWidth: Math.max(34, previewLabel.implicitWidth + 16)"
        )
        button.write_text(
            source.rsplit("}", 1)[0]
            + """
  Rectangle {
    anchors.fill: parent; radius: 4
    color: root.selected ? "#303030" : "#202020"
    border.color: "#444444"
  }
  Text {
    id: previewLabel
    anchors.centerIn: parent
    text: root.text || root.iconText
    color: root.enabled ? root.foreground : "#666666"
    font.family: Style.font.family; font.pixelSize: 16
  }
}
"""
        )
        for name in ("SonarchyQueuePage.qml", "SonarchyNavigation.qml"):
            shutil.copyfile(gate.ROOT / name, root / name)
        shutil.copyfile(gate.ROOT / "docs/preview/Preview.qml", root / "tst_Preview.qml")
        runtime = root / "runtime"
        runtime.mkdir(mode=0o700)
        result = gate.run(
            [gate.RUNNER, "-input", str(root), "-import", str(imports)],
            cwd=root,
            env={
                "PATH": os.defpath,
                "HOME": str(root),
                "XDG_RUNTIME_DIR": str(runtime),
                "QT_QPA_PLATFORM": "offscreen",
                "QT_QUICK_BACKEND": "software",
                "QT_QUICK_CONTROLS_STYLE": "Basic",
                "QT_STYLE_OVERRIDE": "Fusion",
            },
        )
        if result.returncode or result.stderr.strip() or "QWARN" in result.stdout:
            raise ValueError("Isolated preview failed:\n" + result.stdout + result.stderr)
        data = (root / "preview.png").read_bytes()
        validate_preview(data)
        # Exclusive creation: never silently overwrite an existing reviewed image.
        with output.open("xb") as target:
            target.write(data)
        return {
            "width": 1280,
            "height": 720,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New PNG path; existing paths are refused")
    args = parser.parse_args()
    try:
        print(json.dumps(render(args.output), sort_keys=True))
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
