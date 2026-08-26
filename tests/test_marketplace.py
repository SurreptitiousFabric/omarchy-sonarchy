import json
import re
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_manifest_identity_and_entrypoints_are_safe():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    assert manifest["schemaVersion"] == 1
    assert re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)+", manifest["id"])
    assert manifest["id"] == "io.github.surreptitiousfabric.sonarchy"
    assert manifest["name"] == "Sonarchy"
    assert manifest["version"] == "4.1.0"
    assert manifest["author"] == "SurreptitiousFabric"
    assert manifest["license"] == "MIT"
    assert set(manifest["kinds"]) == {"service", "bar-widget"}
    for relative in manifest["entryPoints"].values():
        path = Path(relative)
        assert not path.is_absolute()
        assert ".." not in path.parts
        assert (ROOT / path).is_file()


def test_marketplace_root_has_one_manifest_and_required_docs():
    assert list(ROOT.rglob("manifest.json")) == [ROOT / "manifest.json"]
    required = {
        "README.md",
        "LICENSE",
        "SECURITY.md",
        "PRIVACY.md",
        "CAPABILITIES.md",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "THIRD_PARTY_NOTICES.md",
        "USER_GUIDE.md",
        "ACCEPTANCE_TESTS.md",
    }
    assert all((ROOT / name).is_file() for name in required)
    readme = (ROOT / "README.md").read_text()
    assert "omarchy plugin add https://github.com/SurreptitiousFabric/omarchy-sonarchy" in readme
    assert "omarchy plugin remove io.github.surreptitiousfabric.sonarchy" in readme
    assert "<public-repository-url>" not in readme
    assert "USER_GUIDE.md" in readme
    assert "github.com/SoCo/SoCo" in readme


def test_generated_python_artifacts_are_ignored():
    ignored = (ROOT / ".gitignore").read_text().splitlines()
    assert {
        "__pycache__/",
        "*.py[cod]",
        ".coverage",
        ".pytest_cache/",
        ".ruff_cache/",
        ".venv/",
    } <= set(ignored)


def test_marketplace_release_is_held_until_live_acceptance_and_owner_signoff():
    acceptance = (ROOT / "ACCEPTANCE_TESTS.md").read_text()
    marketplace = (ROOT / "MARKETPLACE.md").read_text()

    assert "**Marketplace status: HOLD**" in acceptance
    assert "- [ ] Owner release sign-off" in acceptance
    assert "remains a local beta" in acceptance
    assert "current status is **HOLD**" in marketplace
    assert "The planned public repository URL" in marketplace
    assert "it does not exist" in marketplace


def test_tree_has_no_symlinks_or_unexpected_executables():
    for path in ROOT.rglob("*"):
        assert not path.is_symlink(), path
        if not path.is_file() or ".git" in path.parts:
            continue
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode & 0o022 == 0, path
        executable = bool(mode & 0o111)
        assert executable is (path.name == "sonarchy-backend.sh"), path


def test_runtime_lock_is_versioned_and_hashed():
    text = (ROOT / "requirements.lock").read_text()
    requirements = [
        line
        for line in text.splitlines()
        if line and not line.startswith(("#", " ")) and "==" in line
    ]
    assert requirements
    assert text.count("--hash=sha256:") >= len(requirements)
    for line in requirements:
        requirement = line.removesuffix("\\").strip()
        name, version = requirement.split("==", 1)
        assert re.fullmatch(r"[a-z0-9_.-]+", name)
        assert version and not any(character.isspace() for character in version)


def test_apple_results_offer_a_keyboard_reachable_whole_album_action():
    service = (ROOT / "Service.qml").read_text()
    browse_page = (ROOT / "SonarchyBrowsePage.qml").read_text()

    assert "function playAppleAlbum(item)" in service
    assert 'startAction(["play-apple-album"' in service
    assert "root.service.playAppleAlbum(modelData)" in browse_page
    assert 'text: "Album"' in browse_page
    assert "focusable: true" in browse_page


def test_tv_autoplay_takeover_has_a_keyboard_reachable_recovery():
    browse_page = (ROOT / "SonarchyBrowsePage.qml").read_text()
    system_page = (ROOT / "SonarchySystemPage.qml").read_text()

    assert "playbackDetails.tv_autoplay_risk" in browse_page
    assert "Sonos will interrupt music" in browse_page
    assert 'label: "TV Autoplay"' in system_page
    assert 'root.service.setDeviceSetting(\n            "tv-autoplay"' in system_page


def test_contextual_play_modes_are_disabled_and_rename_waits_for_topology():
    now_page = (ROOT / "SonarchyNowPage.qml").read_text()
    sound_page = (ROOT / "SonarchySoundPage.qml").read_text()
    service = (ROOT / "Service.qml").read_text()

    assert "playbackDetails.play_mode_supported" in now_page
    assert "root.playModeSupported" in now_page
    assert "root.playback.play_mode_supported === true" in sound_page
    assert "id: renameRefresh" in service
    assert "interval: 5500" in service
    assert "root.optimisticDevicePatch(root.selectedIp" in service


def test_errors_are_keyboard_dismissible_and_expire():
    widget = (ROOT / "BarWidget.qml").read_text()
    service = (ROOT / "Service.qml").read_text()
    live_service = (ROOT / "LiveService.qml").read_text()

    assert 'tooltipText: "Dismiss error"' in widget
    assert "root.service.clearError()" in widget
    assert "id: requestErrorTimer" in service
    assert "interval: 10000" in service
    assert "id: transientErrorTimer" in live_service
    assert "interval: 10000" in live_service


def test_device_details_use_the_persistent_backend_not_a_one_shot_process():
    service = (ROOT / "Service.qml").read_text()
    live_service = (ROOT / "LiveService.qml").read_text()

    assert "detailsProcess" not in service
    assert "live.requestDeviceDetails(detailsRequestRoomUid)" in service
    assert 'sendCommand("devices.details.get", { roomUid: roomUid }, false)' in live_service
    assert len(re.findall(r"\bProcess\s*\{", service)) == 3


def test_page_navigation_follows_the_now_playing_content():
    widget = (ROOT / "BarWidget.qml").read_text()
    navigation = (ROOT / "SonarchyNavigation.qml").read_text()
    now_page = (ROOT / "SonarchyNowPage.qml").read_text()

    assert widget.index("id: roomPicker") < widget.index("id: pageViewport")
    assert widget.index("id: pageViewport") < widget.index("id: pageTabs")
    assert "SonarchyNavigation {" in widget
    assert "ButtonGroup {" not in widget
    assert "activeFocusOnTab: focusable" in navigation
    assert "function moveCursor(delta)" in navigation
    assert "changed(nextValue)" in navigation
    assert 'else if (key === "1") root.activePage = "now"' in widget
    assert 'else if (key === "5") root.activePage = "system"' in widget
    assert "id: positionLabel" in now_page
    assert "id: durationLabel" in now_page
    assert "anchors.left: parent.left" in now_page
    assert "anchors.right: parent.right" in now_page


def test_shared_omarchy_dropdowns_and_toggles_are_in_the_keyboard_focus_route():
    widget = (ROOT / "BarWidget.qml").read_text()
    now_page = (ROOT / "SonarchyNowPage.qml").read_text()
    dropdown = (ROOT / "SonarchyDropdown.qml").read_text()
    toggle = (ROOT / "SonarchyToggle.qml").read_text()

    assert "function focusCandidates()" in widget
    assert "if (item.focusable === true) return true" in widget
    assert "visit(item.children[i])" in widget
    assert "owner.keyboardOwnsFocus === true" in widget
    assert 'typeof current.toggle === "function"' in widget
    assert '"popupOpen" in current' in widget
    assert "blocked: nowPage.editing" in widget
    assert "readonly property bool editing: sleepPicker.popupOpen" in now_page
    assert "property bool keyboardOwnsFocus: true" in dropdown
    assert "activeFocusOnTab: focusable" in dropdown
    assert "onClicked: toggle()" in dropdown
    assert "property bool focusable: true" in toggle

    for page_name in (
        "BarWidget.qml",
        "SonarchyNowPage.qml",
        "SonarchyBrowsePage.qml",
        "SonarchySoundPage.qml",
        "SonarchySystemPage.qml",
    ):
        page = (ROOT / page_name).read_text()
        assert re.search(r"\bDropdown \{", page) is None
        assert re.search(r"\bToggle \{", page) is None


def test_favorite_artwork_is_forwarded_to_the_browse_model():
    service = (ROOT / "Service.qml").read_text()
    browse_page = (ROOT / "SonarchyBrowsePage.qml").read_text()

    assert "safeArtworkUrl(source[i].albumArtUrl)" in service
    assert "modelData.album_art" in browse_page


def test_radio_artwork_enrichment_is_bounded_async_optional_and_safe():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    widget = (ROOT / "BarWidget.qml").read_text()
    service = (ROOT / "Service.qml").read_text()
    controller = (ROOT / "sonarchy_backend" / "controller.py").read_text()

    assert manifest["barWidget"]["defaults"]["enrichRadioArtwork"] is True
    assert 'setting("enrichRadioArtwork", true)' in widget
    assert "service.radioArtworkEnrichmentEnabled = showArtwork && enrichRadioArtwork" in widget
    assert "property bool radioArtworkEnrichmentEnabled: false" in service
    assert "readonly property int artworkCacheLimit: 128" in service
    assert "artworkProcess" not in service
    assert 'live.hasCapability("artwork.radio.resolve")' in service
    assert "live.requestRadioArtwork(artworkRequestTitle, artworkRequestArtist)" in service
    assert "payload && payload.ok === true && payload.match === true" in service
    assert "root.cacheArtwork(completedKey, artworkUrl)" in service
    assert 'playback.artworkKind || "") === "track"' in service
    assert 'trusted_hosts = ("static.mytuner-radio.net",)' in controller


def test_every_manifest_setting_is_documented_and_read_by_qml():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    readme = (ROOT / "README.md").read_text()
    widget = (ROOT / "BarWidget.qml").read_text()

    setting_keys = {entry["key"] for entry in manifest["barWidget"]["schema"]}
    assert setting_keys == {
        "barDisplay",
        "maxLabelWidth",
        "showArtwork",
        "enrichRadioArtwork",
        "panelWidth",
        "panelHeight",
        "volumeStep",
    }
    for key in setting_keys:
        assert key in readme
        assert f'setting("{key}"' in widget
