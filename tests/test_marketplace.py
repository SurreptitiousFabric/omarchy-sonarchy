import ast
import json
import re
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def service_implementation():
    return "\n".join(
        (ROOT / name).read_text()
        for name in (
            "Service.qml",
            "SonarchyStore.qml",
            "SonarchyContentState.qml",
            "SonarchyProtocolRouter.qml",
            "SonarchyArtwork.qml",
        )
    )


def controller_implementation():
    return "\n".join(
        path.read_text() for path in sorted((ROOT / "sonarchy_backend").glob("controller*.py"))
    )


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
    marketplace = (ROOT / "MARKETPLACE.md").read_text()
    assert "The public source repository is" in marketplace
    assert "it does not exist" not in marketplace


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


def test_ci_uses_yaml_safe_mise_managed_tool_gates():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()

    assert "jdx/mise-action@c2a87611a18de5b3828c5652fe268e992400cb5c # v4.3.0" in workflow
    assert "run: >-\n          mise exec -- python -m pip install" in workflow
    assert "--only-binary=:all: --require-hashes" in workflow
    assert "bash -n sonarchy-backend.sh tests/qml/run-component-tests.sh" in workflow
    assert (
        "mise exec -- shellcheck sonarchy-backend.sh tests/qml/run-component-tests.sh" in workflow
    )


def test_marketplace_release_is_held_until_live_acceptance_and_owner_signoff():
    acceptance = (ROOT / "ACCEPTANCE_TESTS.md").read_text()
    marketplace = (ROOT / "MARKETPLACE.md").read_text()

    assert "**Marketplace status: HOLD**" in acceptance
    assert "- [ ] Owner release sign-off" in acceptance
    assert "remains a local beta" in acceptance
    assert "current status is **HOLD**" in marketplace
    assert "The public source repository is" in marketplace


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
    service = service_implementation()
    browse_page = (ROOT / "SonarchyBrowsePage.qml").read_text()

    assert "function playAppleAlbum(item)" in service
    assert "live.playAppleAlbum(" in service
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
    service = service_implementation()

    assert "playbackDetails.play_mode_supported" in now_page
    assert "root.playModeSupported" in now_page
    assert "root.playback.play_mode_supported === true" in sound_page
    assert "id: renameRefresh" in service
    assert "interval: 5500" in service
    assert "router.store.optimisticDevicePatch(" in service
    assert "router.store.selectedIp, { name:" in service


def test_errors_are_keyboard_dismissible_and_expire():
    widget = (ROOT / "BarWidget.qml").read_text()
    service = service_implementation()
    live_service = (ROOT / "LiveService.qml").read_text()

    assert 'tooltipText: "Dismiss error"' in widget
    assert "root.service.clearError()" in widget
    assert "id: requestErrorTimer" in service
    assert "interval: 10000" in service
    assert "id: transientErrorTimer" in live_service
    assert "interval: 10000" in live_service


def test_device_details_use_the_persistent_backend_not_a_one_shot_process():
    service = service_implementation()
    live_service = (ROOT / "LiveService.qml").read_text()

    assert "detailsProcess" not in service
    assert "live.requestDeviceDetails(detailsRequestRoomUid)" in service
    assert 'sendCommand("devices.details.get", { roomUid: roomUid }, false, false)' in live_service
    assert len(re.findall(r"\bProcess\s*\{", service)) == 0


def test_content_reads_use_the_persistent_backend_not_a_one_shot_process():
    service = service_implementation()
    live_service = (ROOT / "LiveService.qml").read_text()

    assert "contentProcess" not in service
    assert "live.requestContent(" in service
    assert 'sendCommand("content.browse"' in live_service


def test_browsable_content_uses_one_activation_route_and_cannot_fall_through_to_playback():
    service = service_implementation()
    browse_page = (ROOT / "SonarchyBrowsePage.qml").read_text()

    assert "root.service.activateContent(resultCard.modelData)" in browse_page
    assert "if (contentState.openItem(item)) return" in service
    assert "item.browsable === true" in service


def test_library_browse_has_keyboard_routes_for_hierarchy_search_and_pages():
    service = service_implementation()
    browse_page = (ROOT / "SonarchyBrowsePage.qml").read_text()

    assert "function openLibraryItem(item)" in service
    assert "function libraryBack()" in service
    assert "function libraryPage(offset)" in service
    assert 'text: root.service && root.service.contentKind === "library"' in browse_page
    assert '? "Browse" : "Back"' in browse_page
    assert 'tooltipText: "Previous page"' in browse_page
    assert 'tooltipText: "Next page"' in browse_page
    assert "focusable: true" in browse_page


def test_queue_insertion_controls_include_confirmed_replace():
    browse_page = (ROOT / "SonarchyBrowsePage.qml").read_text()
    service = service_implementation()

    for mode in ("play", "next", "end", "replace"):
        assert f'root.service.enqueueContent(modelData, "{mode}")' in browse_page
    assert 'readonly property string replaceKey: "replace:" + rowKey' in browse_page
    assert '"Press again to replace the queue"' in browse_page
    assert "root.arm(resultCard.replaceKey)" in browse_page
    assert 'enqueueContent(item, "play")' in service


def test_alarm_reads_use_the_persistent_backend_not_a_one_shot_process():
    service = service_implementation()
    live_service = (ROOT / "LiveService.qml").read_text()

    assert "alarmsProcess" not in service
    assert "live.requestAlarms(alarmsRequestRoomUid)" in service
    assert 'sendCommand("alarms.list"' in live_service


def test_device_and_playback_settings_use_the_persistent_backend():
    service = service_implementation()
    live_service = (ROOT / "LiveService.qml").read_text()

    for legacy_command in ("stop", "rename", "playback-option", "sound", "device", "source"):
        assert f'startAction(["{legacy_command}"' not in service
    for operation in (
        "playback.stop",
        "devices.rename",
        "playback.option.set",
        "sound.setting.set",
        "devices.setting.set",
        "sources.switch",
    ):
        assert f'sendCommand("{operation}"' in live_service
    assert len(re.findall(r"\bProcess\s*\{", service)) == 0


def test_content_mutations_use_the_persistent_backend():
    service = service_implementation()
    live_service = (ROOT / "LiveService.qml").read_text()

    for legacy_command in (
        "play-queue",
        "remove-queue",
        "clear-queue",
        "queue-content",
        "playlist",
        "playlist-track",
        "play-apple",
        "play-apple-album",
        "play-global",
        "library-update",
    ):
        assert f'startAction(["{legacy_command}"' not in service
    for operation in (
        "queue.item.play",
        "queue.item.remove",
        "queue.clear",
        "queue.content.enqueue",
        "playlists.mutate",
        "playlists.track.mutate",
        "content.apple.play",
        "content.apple.album.play",
        "content.global.play",
        "library.update.start",
    ):
        assert f'sendCommand("{operation}"' in live_service
    assert len(re.findall(r"\bProcess\s*\{", service)) == 0


def test_alarm_mutations_use_the_persistent_backend_and_no_process_remains():
    service = service_implementation()
    live_service = (ROOT / "LiveService.qml").read_text()

    for legacy_command in ("alarm-save", "alarm-toggle", "alarm-delete"):
        assert f'startAction(["{legacy_command}"' not in service
    for operation in ("alarms.save", "alarms.toggle", "alarms.delete"):
        assert f'sendCommand("{operation}"' in live_service
    for legacy_plumbing in (
        "Process {",
        "StdioCollector",
        "pythonPath",
        "helperPath",
        "helperEnvironment",
        "parsePayload",
        "processFailure",
        "function startAction(",
    ):
        assert legacy_plumbing not in service


def test_alarm_editor_uses_authoritative_keyboard_reachable_room_options():
    system_page = (ROOT / "SonarchySystemPage.qml").read_text()
    alarm_editor = (ROOT / "SonarchyAlarmEditor.qml").read_text()
    alarm_draft = (ROOT / "SonarchyAlarmDraft.qml").read_text()
    alarm_runtime_test = (ROOT / "tests/qml/tst_SonarchyAlarmDraft.qml").read_text()
    store = (ROOT / "SonarchyStore.qml").read_text()
    live = (ROOT / "LiveService.qml").read_text()
    router = (ROOT / "SonarchyProtocolRouter.qml").read_text()

    assert "SonarchyAlarmEditor {" in system_page
    assert "alarmEditor.editing" in system_page
    assert "alarmEditor.editAlarm(alarmCard.modelData)" in system_page
    assert "scrollTarget: systemFlick" in system_page
    assert "property string alarmRoomUid" not in system_page
    assert "SonarchyAlarmDraft {" in alarm_editor
    assert "id: alarmRoomPicker" in alarm_editor
    assert 'label: "ROOM"' in alarm_editor
    assert "alarmRoomPicker.popupOpen" in alarm_editor
    assert "&& draft.valid" in alarm_editor
    assert "saveAlarm(draft.savePayload())" in alarm_editor
    assert "function alarmRoomOptions()" in alarm_draft
    assert "var rooms = service ? service.rooms : []" in alarm_draft
    assert "if (rooms[i].online === false) continue" in alarm_draft
    assert 'alarmRoomUid = String(item.room_uid || "")' in alarm_draft
    assert "readonly property bool valid" in alarm_draft
    assert "function savePayload()" in alarm_draft
    assert "test_edit_projects_every_field_and_exact_save_payload" in alarm_runtime_test
    assert "test_validation_rejects_bad_time_and_missing_room" in alarm_runtime_test
    assert 'alarmRoomUid: String(editor.roomUid || "")' in store
    assert "alarmRoomUid: alarm.alarmRoomUid" in live
    assert 'failedOperation.indexOf("alarms.") === 0' in router


def test_tv_audio_format_uses_the_shared_read_only_information_row():
    system_page = (ROOT / "SonarchySystemPage.qml").read_text()
    info_row = (ROOT / "SonarchyInfoRow.qml").read_text()
    devices = (ROOT / "sonarchy_backend/domains/devices.py").read_text()

    assert '"tv_audio_format": _tv_audio_format(speaker)' in devices
    assert system_page.count("SonarchyInfoRow {") >= 2
    assert 'label: "TV format"' in system_page
    assert "root.deviceInfo.tv_audio_format !== null" in system_page
    assert "required property string label" in info_row
    assert "required property string value" in info_row
    assert "font.pixelSize: Style.font.bodySmall" in info_row


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
    assert 'else if (key === "3") root.activePage = "queue"' in widget
    assert 'else if (key === "6") root.activePage = "system"' in widget
    assert "id: positionLabel" in now_page
    assert "id: durationLabel" in now_page
    assert "anchors.left: parent.left" in now_page
    assert "anchors.right: parent.right" in now_page


def test_queue_is_a_dedicated_capability_driven_keyboard_page():
    widget = (ROOT / "BarWidget.qml").read_text()
    browse_page = (ROOT / "SonarchyBrowsePage.qml").read_text()
    queue_page = (ROOT / "SonarchyQueuePage.qml").read_text()

    assert "SonarchyQueuePage {" in widget
    assert 'readonly property bool currentPage: root.activePage === "queue"' in widget
    assert '{ value: "queue", label: "Queue"' in widget
    assert 'else if (key === "3") root.activePage = "queue"' in widget
    assert 'activePage === "queue" ? queuePage' in widget
    assert 'else if (activePage === "queue") service.loadContent("queue", "")' in widget
    assert 'else if (key === "r") root.refreshPanel()' in widget
    assert '{ value: "queue", label: "Current queue" }' not in browse_page
    assert 'service.loadContent("queue", "")' in queue_page
    assert 'root.can("queue.item.play")' in queue_page
    assert 'root.can("queue.item.remove")' in queue_page
    assert 'root.can("queue.clear")' in queue_page
    assert "root.service.removeQueueItem(" in queue_page
    assert 'root.arm("queue-clear")' in queue_page
    assert "function ensureVisible(item)" in queue_page


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
        "SonarchyQueuePage.qml",
        "SonarchySoundPage.qml",
        "SonarchySystemPage.qml",
    ):
        page = (ROOT / page_name).read_text()
        assert re.search(r"\bDropdown \{", page) is None
        assert re.search(r"\bToggle \{", page) is None


def test_favorite_artwork_is_forwarded_to_the_browse_model():
    service = service_implementation()
    browse_page = (ROOT / "SonarchyBrowsePage.qml").read_text()

    assert "safeArtworkUrl(source[i].albumArtUrl)" in service
    assert "modelData.album_art" in browse_page


def test_radio_artwork_enrichment_is_bounded_async_optional_and_safe():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    widget = (ROOT / "BarWidget.qml").read_text()
    service = service_implementation()
    controller = controller_implementation()

    assert manifest["barWidget"]["defaults"]["enrichRadioArtwork"] is True
    assert 'setting("enrichRadioArtwork", true)' in widget
    assert "service.radioArtworkEnrichmentEnabled = showArtwork && enrichRadioArtwork" in widget
    assert "property bool radioArtworkEnrichmentEnabled: false" in service
    assert "readonly property int cacheLimit: 128" in service
    assert "artworkProcess" not in service
    assert 'artwork.live.hasCapability("artwork.radio.resolve")' in service
    assert "artwork.live.requestRadioArtwork(" in service
    assert "payload && payload.ok === true && payload.match === true" in service
    assert "router.store.cacheArtwork(completedKey, artworkUrl)" in service
    assert 'playback.artworkKind || "") === "track"' in service
    assert 'trusted_hosts = ("static.mytuner-radio.net",)' in controller


def test_production_components_stay_within_size_guardrails():
    facade = (ROOT / "Service.qml").read_text()
    components = (
        "SonarchyStore.qml",
        "SonarchyContentState.qml",
        "SonarchyProtocolRouter.qml",
        "SonarchyArtwork.qml",
        "LiveService.qml",
        "SonarchySystemPage.qml",
        "SonarchyAlarmEditor.qml",
        "SonarchyAlarmDraft.qml",
        "SonarchyQueuePage.qml",
        "SonarchyInfoRow.qml",
    )

    assert len(facade.splitlines()) <= 350
    assert "SonarchyStore {" in facade
    for name in components:
        assert len((ROOT / name).read_text().splitlines()) <= 800, name
    for path in (ROOT / "sonarchy_backend").rglob("*.py"):
        assert len(path.read_text().splitlines()) <= 800, path.relative_to(ROOT)
    assert re.search(r"\bProcess\s*\{", service_implementation()) is None


def test_handler_domains_do_not_import_each_others_private_implementations():
    handler_domains = {
        "alarms",
        "artwork",
        "browse",
        "content",
        "devices",
        "mixer",
        "playback",
        "playlists",
        "queue",
        "settings",
        "topology",
    }
    domain_root = ROOT / "sonarchy_backend/domains"

    for domain in sorted(handler_domains):
        tree = ast.parse((domain_root / f"{domain}.py").read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            if node.level == 1:
                imported_domain = node.module.split(".", 1)[0]
            elif node.module.startswith("sonarchy_backend.domains."):
                imported_domain = node.module.split(".")[2]
            else:
                continue
            assert imported_domain not in handler_domains - {domain}, (
                f"{domain} imports private handler domain {imported_domain}"
            )


def test_pages_use_omarchy_tokens_without_debug_chrome():
    pages = "\n".join(path.read_text() for path in sorted(ROOT.glob("Sonarchy*Page.qml")))

    assert 'color: "#' not in pages
    assert not re.search(r"font\.pixelSize:\s*\d", pages)
    assert "SONARCHY_IMAGE_STATE" not in pages
    assert "SONARCHY_ARTWORK_STATE" not in service_implementation()
    assert "Style.spacing.hairline" in pages


def test_pages_are_capability_driven_and_do_not_mutate_store_state():
    pages = "\n".join(path.read_text() for path in sorted(ROOT.glob("Sonarchy*Page.qml")))
    store = (ROOT / "SonarchyStore.qml").read_text()

    assert "hasCapability(" in pages
    assert "requireCapability(" in store
    assert "is_soundbar" not in pages
    for property_name in ("contentItems", "contentTotal", "contentMeta", "contentTerm"):
        assert re.search(rf"service\.{property_name}\s*=(?!=)", pages) is None


def test_protocol_requests_keep_background_and_action_state_correlated():
    live = (ROOT / "LiveService.qml").read_text()
    router = (ROOT / "SonarchyProtocolRouter.qml").read_text()

    assert 'sendCommand("session.panel_open.set", { open: isOpen }, false, false)' in live
    assert 'sendCommand("session.panel_open.set", { open: true }, false, false)' in live
    assert 'sendCommand("devices.details.get", { roomUid: roomUid }, false, false)' in live
    assert 'sendCommand("alarms.list", { roomUid: roomUid }, false, false)' in live
    assert "if (!quietResult)" in live
    assert "validRevision(message.revision)" in live
    artwork_branch = router.split("=== router.store.artworkRequestId) {", 1)[1].split(
        "=== router.store.contentRequestId) {", 1
    )[0]
    assert "protocolActionRequestId" not in artwork_branch
    backend_loss = router.split("function onBackendReadyChanged()", 1)[1]
    for pending_state in (
        "protocolActionRequestId",
        "detailsRequestId",
        "contentRequestId",
        "alarmsRequestId",
        "queuedVolume",
    ):
        assert pending_state in backend_loss


def test_page_sliders_scroll_the_page_without_wheel_mutations():
    controls = "\n".join(
        path.read_text()
        for path in (*sorted(ROOT.glob("Sonarchy*Page.qml")), ROOT / "SonarchyAlarmEditor.qml")
    )
    slider = (ROOT / "SonarchySlider.qml").read_text()
    runtime_test = (ROOT / "tests/qml/tst_SonarchySlider.qml").read_text()
    runtime_runner = (ROOT / "tests/qml/run-component-tests.sh").read_text()

    assert "PanelSlider {" not in controls
    assert controls.count("SonarchySlider {") == 5
    assert controls.count("scrollTarget:") >= controls.count("SonarchySlider {")
    assert "MouseArea {" in slider
    assert "acceptedButtons: Qt.NoButton" in slider
    assert "event.accepted = true" in slider
    assert "view.contentY =" in slider
    assert "root.value" not in slider
    assert "mouseWheel(slider" in runtime_test
    assert "compare(movedCount, 0)" in runtime_test
    assert "test_pointer_drag_still_uses_native_slider" in runtime_test
    assert "/usr/share/omarchy/shell/Ui/PanelSlider.qml" in runtime_runner
    assert "QT_QPA_PLATFORM=offscreen" in runtime_runner


def test_background_results_cannot_clear_unrelated_request_errors():
    store = (ROOT / "SonarchyStore.qml").read_text()
    content_state = (ROOT / "SonarchyContentState.qml").read_text()
    router = (ROOT / "SonarchyProtocolRouter.qml").read_text()
    error_state = (ROOT / "SonarchyErrorState.qml").read_text()
    runtime_test = (ROOT / "tests/qml/tst_SonarchyErrorState.qml").read_text()

    assert "property string ownerId" in error_state
    assert "ownerId !== expectedOwner" in error_state
    assert "ownerId !== nextOwner" in error_state
    assert "readonly property alias requestErrorRequestId" in store
    assert '"favorites-snapshot"' in content_state
    assert '"local", true' in store
    assert "router.store.requestError =" not in router
    for owner in (
        "actionRequestId",
        "completedContentRequestId",
        "completedAlarmsRequestId",
        "completedDetailsRequestId",
    ):
        assert owner in router
    assert "test_unrelated_success_cannot_clear_foreground_error" in runtime_test
    assert "test_unrelated_background_error_cannot_replace_foreground_error" in runtime_test
    assert "test_foreground_error_can_replace_background_error" in runtime_test


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
