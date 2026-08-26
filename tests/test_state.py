import json
import stat

import pytest

from sonarchy_backend.state import PersistentState, default_state_path


def test_state_round_trip(tmp_path):
    path = tmp_path / "state.json"
    state = PersistentState("RINCON_A", ["10.0.0.3", "10.0.0.2", "10.0.0.2"])
    state.save(path)
    loaded = PersistentState.load(path)
    assert loaded.selected_room_uid == "RINCON_A"
    assert loaded.cached_hosts == ["10.0.0.2", "10.0.0.3"]
    raw = json.loads(path.read_text())
    assert raw["selectedRoomUid"] == "RINCON_A"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_non_object_state_is_ignored(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("[]")

    assert PersistentState.load(path) == PersistentState()


def test_state_save_refuses_symbolic_link_target(tmp_path):
    victim = tmp_path / "victim.json"
    victim.write_text("do not replace")
    path = tmp_path / "state.json"
    path.symlink_to(victim)

    with pytest.raises(OSError, match="symbolic-link"):
        PersistentState("RINCON_A", []).save(path)

    assert victim.read_text() == "do not replace"


def test_empty_xdg_state_home_uses_the_home_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_STATE_HOME", "")

    assert default_state_path() == (
        tmp_path / ".local" / "state" / "io.github.surreptitiousfabric.sonarchy" / "state.json"
    )
