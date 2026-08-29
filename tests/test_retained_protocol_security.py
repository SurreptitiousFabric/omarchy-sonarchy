from __future__ import annotations

from pathlib import Path

import pytest

from sonarchy_backend.domains.apple_retained_plan import RetainedApplePlaylistPlanService

ROOT = Path(__file__).resolve().parents[1]
VALID_TRACK = {
    "catalogId": "1452806384",
    "url": "https://music.apple.com/ch/album/example/1?i=1452806384",
    "title": "Just Like Heaven",
    "artist": "The Cure",
    "album": "Kiss Me, Kiss Me, Kiss Me",
    "durationMs": 212000,
}


class Backend:
    def inspect_retained_apple_playlist_target(self, room_uid, _playlist_name):
        return {
            "room": {
                "uid": room_uid,
                "coordinatorUid": room_uid,
                "householdFingerprint": f"sha256:{'1' * 64}",
            },
            "observedState": {
                "playlistCount": 0,
                "playlistInventoryFingerprint": f"sha256:{'2' * 64}",
                "capabilities": [
                    "playlist_plan.apple.retained.validate",
                    "playlists.apple.retained.create",
                    "direct-apple-saved-queue-retained",
                ],
            },
        }

    def create_retained_apple_playlist(self, _plan):
        return {"ok": True}


def test_protocol_rejects_provider_and_saved_queue_fields_at_public_boundary():
    validation, _creation = RetainedApplePlaylistPlanService(Backend()).services()
    base = {
        "roomUid": "R1",
        "playlistName": "Inspection",
        "retentionMode": "manual-inspection",
        "allowDuplicates": False,
        "tracks": [VALID_TRACK],
    }
    for field in (
        "EnqueuedURI",
        "EnqueuedURIMetaData",
        "serviceId",
        "accountSequence",
        "flags",
        "didl",
        "soap",
        "command",
    ):
        with pytest.raises(ValueError, match="unsupported arguments"):
            validation.execute(
                "playlist_plan.apple.retained.validate",
                {**base, field: "not-authorized"},
            )


def test_provider_construction_is_confined_to_one_infrastructure_adapter():
    production_files = list((ROOT / "sonarchy_backend").rglob("*.py"))
    owners = []
    for path in production_files:
        text = path.read_text()
        if "AddURIToSavedQueue" in text or "EnqueuedURIMetaData" in text:
            owners.append(path.relative_to(ROOT).as_posix())
    assert owners == ["sonarchy_backend/infrastructure/apple_saved_queue.py"]


def test_qml_has_no_retained_diagnostic_or_infrastructure_execution_path():
    qml = "\n".join(path.read_text() for path in ROOT.glob("*.qml"))
    for forbidden in (
        "playlist_plan.apple.retained.validate",
        "playlists.apple.retained.create",
        "AddURIToSavedQueue",
        "EnqueuedURIMetaData",
        "soco",
        "DIDL",
        "SOAP",
    ):
        assert forbidden not in qml


def test_retained_transaction_source_has_no_queue_playback_or_cleanup_call():
    source = (ROOT / "sonarchy_backend/domains/apple_retained_transaction.py").read_text()
    for forbidden in (
        ".get_queue(",
        ".clear_queue(",
        ".add_to_queue(",
        ".add_multiple_to_queue(",
        ".play_from_queue(",
        ".play(",
        ".pause(",
        ".stop(",
        ".remove_sonos_playlist(",
    ):
        assert forbidden not in source
