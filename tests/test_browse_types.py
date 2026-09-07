"""Run the locked checker, including real production-source negative controls."""

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from sonarchy_backend.domains.browse import parse_browse_request
from sonarchy_mcp.browse import browse_arguments

ROOT = Path(__file__).resolve().parents[1]


def run_checker(tmp_path, *arguments):
    return subprocess.run(  # noqa: S603 - selected interpreter and test-owned checker inputs
        [
            sys.executable,
            "-m",
            "mypy",
            "--config-file",
            str(ROOT / "pyproject.toml"),
            "--no-incremental",
            "--cache-dir",
            str(tmp_path / "mypy-cache"),
            *arguments,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_typed_slice_passes_and_gate_is_not_optional(tmp_path):
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["mypy"]
    assert set(config["files"]) == {
        "sonarchy_mcp_contract.py",
        "sonarchy_mcp/browse.py",
        "sonarchy_backend/domains/browse.py",
        "sonarchy_backend/domains/apple_browse.py",
        "sonarchy_backend/domains/ports.py",
    }
    assert config["follow_imports"] == "silent"
    assert not config.get("ignore_errors")
    assert not config.get("ignore_missing_imports")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    assert '"$SONARCHY_CI_PYTHON" -m mypy --config-file pyproject.toml' in workflow
    assert "continue-on-error" not in workflow
    result = run_checker(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Success:" in result.stdout


def test_types_reject_incorrect_optionality_and_literal_fields(tmp_path):
    probe = tmp_path / "invalid_browse_types.py"
    probe.write_text(
        """from sonarchy_mcp_contract import AppleSongResult, BrowseRequest, BrowseWireArguments

def bad_room() -> BrowseRequest:
    return BrowseRequest(room_uid=None, kind="apple", term="song", limit=1)

def bad_storefront(request: BrowseRequest) -> str:
    return request.storefront.lower()

def bad_wire(arguments: BrowseWireArguments) -> None:
    arguments["storefront"] = None

def bad_explicitness(song: AppleSongResult) -> None:
    song["explicitness"] = "clean"

def bad_kind(song: AppleSongResult) -> None:
    song["media_kind"] = "album"
""",
    )
    result = run_checker(tmp_path, str(probe))
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.count("error:") == 5, result.stdout
    assert "[arg-type]" in result.stdout
    assert "[union-attr]" in result.stdout
    assert result.stdout.count("[typeddict-item]") == 3


@pytest.mark.parametrize(
    "original,replacement",
    [
        ('        "artist": artist,\n', ""),
        (
            '        "durationMs": duration_ms,',
            '        "durationMs": "not a duration",',
        ),
    ],
)
def test_checker_rejects_real_song_producer_regressions(tmp_path, original, replacement):
    source_path = ROOT / "sonarchy_backend/domains/apple_browse.py"
    source = source_path.read_text()
    assert source.count(original) == 1
    shadow = tmp_path / "apple_browse.py"
    shadow.write_text(source.replace(original, replacement))
    result = run_checker(tmp_path, "--shadow-file", str(source_path), str(shadow))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "sonarchy_backend/domains/apple_browse.py:" in result.stdout
    assert 'expected "AppleSongResult | None"' in result.stdout
    assert "[return-value]" in result.stdout
    assert source_path.read_text() == source


def test_checked_producer_and_request_signatures_reach_consumers(tmp_path):
    probe = tmp_path / "valid_browse_types.py"
    probe.write_text(
        """from typing import assert_type
from sonarchy_mcp_contract import AppleSongResult, BrowseRequest, BrowseWireArguments
from sonarchy_backend.domains.apple_browse import _track, browse_apple_album
from sonarchy_backend.domains.browse import parse_browse_request
from sonarchy_mcp.browse import browse_arguments

def consume(raw: dict[str, object]) -> None:
    wire = browse_arguments(raw)
    assert_type(wire, BrowseWireArguments)
    request = parse_browse_request(dict(wire))
    assert_type(request, BrowseRequest)
    assert_type(request.room_uid, str)
    assert_type(request.storefront, str | None)
    assert_type(_track(raw), AppleSongResult | None)
    for item in browse_apple_album("123", 1)["items"]:
        if item["media_kind"] == "song":
            assert_type(item, AppleSongResult)
            assert_type(item["durationMs"], int | None)
            assert_type(item["artist"], str | None)
"""
    )
    result = run_checker(tmp_path, str(probe))
    assert result.returncode == 0, result.stdout + result.stderr


def test_checker_rejects_wrong_request_type_at_actual_port_call(tmp_path):
    source_path = ROOT / "sonarchy_backend/domains/browse.py"
    source = source_path.read_text()
    original = "            request.limit,"
    assert source.count(original) == 1
    shadow = tmp_path / "browse.py"
    shadow.write_text(source.replace(original, "            str(request.limit),"))
    result = run_checker(tmp_path, "--shadow-file", str(source_path), str(shadow))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "sonarchy_backend/domains/browse.py:" in result.stdout
    assert 'Argument 4 to "browse_content"' in result.stdout
    assert "[arg-type]" in result.stdout
    assert source_path.read_text() == source


@pytest.mark.parametrize("storefront", [None, "gb"])
def test_routing_and_backend_normalization_preserve_absent_optionals(storefront):
    raw = {"kind": "apple", "term": 123, "limit": 2.9, "context": ["opaque"]}
    if storefront is not None:
        raw["storefront"] = storefront
    wire = browse_arguments(raw)
    assert wire["roomUid"] == ""
    assert wire["context"] is raw["context"]
    assert ("storefront" in wire) == (storefront is not None)
    request = parse_browse_request(dict(wire))
    assert request.room_uid == ""
    assert request.storefront == ("GB" if storefront is not None else None)
    assert request.term == "123"
    assert request.limit == 2
    assert request.context is raw["context"]
    assert "roomUid" not in raw


@pytest.mark.parametrize("value", [None, " ", False, 123, []])
def test_room_runtime_validation_is_not_replaced_by_annotations(value):
    raw = {"roomUid": value, "kind": "apple", "term": "song", "limit": 1, "context": {}}
    with pytest.raises(ValueError, match="roomUid"):
        browse_arguments(raw)
    with pytest.raises(ValueError, match="roomUid"):
        parse_browse_request(raw)
