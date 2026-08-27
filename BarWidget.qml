import QtQuick
import QtQuick.Controls
import Quickshell
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "io.github.surreptitiousfabric.sonarchy"

  readonly property var service: bar && bar.shell ? bar.shell.serviceFor("io.github.surreptitiousfabric.sonarchy") : null
  readonly property var device: service ? service.selectedDevice : null
  readonly property color panelForeground: bar ? bar.foreground : Color.popups.text
  readonly property string barDisplay: String(setting("barDisplay", "Icon only"))
  readonly property real maxLabelWidth: Math.max(80, Number(setting("maxLabelWidth", 220)))
  readonly property bool showArtwork: Boolean(setting("showArtwork", true))
  readonly property bool enrichRadioArtwork: Boolean(setting("enrichRadioArtwork", true))
  readonly property real configuredPanelWidth: Math.max(360, Math.min(620,
    Number(setting("panelWidth", 440))))
  readonly property real configuredPanelHeight: Math.max(520, Math.min(820,
    Number(setting("panelHeight", 660))))
  readonly property int volumeStep: Math.max(1, Math.min(10,
    Number(setting("volumeStep", 2))))
  readonly property bool showBarLabel: !vertical && barDisplay !== "Icon only"
  readonly property string barLabel: {
    if (!device) return "Sonos offline"
    if (barDisplay === "Room") return String(device.name || "Sonos")
    var title = String(device.title || "")
    var artist = String(device.artist || "")
    if (title !== "") return title + (artist !== "" ? " — " + artist : "")
    return String(device.name || "Sonos") + " · " + playbackLabel.toLowerCase()
  }
  readonly property string playbackLabel: {
    if (!device) return "OFFLINE"
    if (device.state === "PLAYING") return "PLAYING"
    if (device.state === "PAUSED_PLAYBACK") return "PAUSED"
    if (device.state === "TRANSITIONING") return "BUFFERING"
    if (device.state === "UNAVAILABLE") return "UNAVAILABLE"
    return "STOPPED"
  }

  property bool popupOpen: false
  property real wheelAccumulator: 0
  property string activePage: "now"
  property var focusedControl: null

  Component {
    id: heroIconComponent

    BorderSurface {
      implicitWidth: Style.space(36)
      implicitHeight: Style.space(36)
      radius: Style.cornerRadius
      color: Style.selectedFillFor(root.panelForeground, Color.accent)
      borderSpec: Border.none()

      OpticalGlyph {
        anchors.centerIn: parent
        width: Style.space(24)
        height: Style.space(24)
        text: "󰓃"
        color: Style.selectedStateColor(root.panelForeground, Color.accent)
        fontFamily: root.bar.fontFamily
        fontSize: Style.font.display
      }
    }
  }

  Component {
    id: refreshControlComponent

    Button {
      iconText: "󰑐"
      iconSpinning: root.service
        ? root.service.loading || root.service.detailsLoading || root.service.contentLoading : false
      tooltipText: "Refresh Sonos"
      foreground: root.panelForeground
      focusable: true
      enabled: root.service && !root.service.loading
      onClicked: root.refreshPanel()
    }
  }

  function close() { popupOpen = false }
  function closeForPopoutSwitch() { close() }
  readonly property bool opened: popupOpen
  function open() { popupOpen = true }
  function toggle() { popupOpen = !popupOpen }

  function syncArtworkPreference() {
    if (service)
      service.radioArtworkEnrichmentEnabled = showArtwork && enrichRadioArtwork
  }

  function refreshPanel() {
    if (!service) return
    service.refresh()
    service.refreshDetails()
    if (activePage === "browse") service.reloadContent()
    else if (activePage === "queue") service.loadContent("queue", "")
  }

  onServiceChanged: syncArtworkPreference()
  onShowArtworkChanged: syncArtworkPreference()
  onEnrichRadioArtworkChanged: syncArtworkPreference()

  onPopupOpenChanged: {
    if (service) service.setPanelOpen(popupOpen)
    focusedControl = null
  }
  onActivePageChanged: {
    if (!service || !popupOpen) return
    if (activePage === "sound" || activePage === "rooms" || activePage === "system")
      service.refreshDetails()
    if (activePage === "system") service.loadAlarms()
  }
  Component.onCompleted: syncArtworkPreference()
  Component.onDestruction: {
    if (service) {
      service.radioArtworkEnrichmentEnabled = false
      service.setPanelOpen(false)
    }
  }

  function activeControl() {
    var window = keyCatcher.QsWindow.window
    var item = window ? window.activeFocusItem : null
    return item && keyboardFocusable(item) ? item : focusedControl
  }

  function keyboardFocusable(item) {
    if (!item) return false
    if (item.focusable === true) return true
    if (item.activeFocusOnTab !== true) return false
    var owner = item.parent
    for (var i = 0; owner && i < 8; i++) {
      if (owner.keyboardOwnsFocus === true) return false
      owner = owner.parent
    }
    return true
  }

  function effectivelyUsable(item) {
    var current = item
    for (var i = 0; current && i < 40; i++) {
      if (!current.visible || !current.enabled || Number(current.opacity) <= 0.01)
        return false
      if (current === keyCatcher) return true
      current = current.parent
    }
    return false
  }

  function focusCandidates() {
    var candidates = []

    function visit(item) {
      if (!item || !item.children) return
      if (keyboardFocusable(item) && effectivelyUsable(item)) candidates.push(item)
      for (var i = 0; i < item.children.length; i++) visit(item.children[i])
    }

    visit(keyCatcher)
    candidates.sort(function(left, right) {
      var leftPoint = left.mapToItem(keyCatcher, 0, 0)
      var rightPoint = right.mapToItem(keyCatcher, 0, 0)
      var rowDelta = leftPoint.y - rightPoint.y
      if (Math.abs(rowDelta) > Style.space(4)) return rowDelta
      return leftPoint.x - rightPoint.x
    })
    return candidates
  }

  function activateControlOrOwner(item) {
    var current = item
    for (var i = 0; current && i < 8; i++) {
      if ("clicked" in current) {
        current.clicked()
        return true
      }
      if (typeof current.toggle === "function" && "popupOpen" in current) {
        current.toggle()
        return true
      }
      current = current.parent
    }
    return false
  }

  function moveControlFocus(forward) {
    var candidates = focusCandidates()
    if (candidates.length === 0) return
    var current = activeControl()
    var currentIndex = candidates.indexOf(current)
    var owner = current
    while (currentIndex < 0 && owner && owner !== keyCatcher) {
      owner = owner.parent
      currentIndex = candidates.indexOf(owner)
    }
    var nextIndex = currentIndex < 0
      ? (forward ? 0 : candidates.length - 1)
      : Math.max(0, Math.min(candidates.length - 1,
          currentIndex + (forward ? 1 : -1)))
    var next = candidates[nextIndex]
    focusedControl = next
    next.forceActiveFocus()
    Qt.callLater(function() { root.ensureFocusedVisible(next) })
  }

  function ensureFocusedVisible(item) {
    var page = activePage === "browse" ? browsePage
      : (activePage === "queue" ? queuePage
         : (activePage === "rooms" ? roomsPage
            : (activePage === "sound" ? soundPage
               : (activePage === "system" ? systemPage : nowPage))))
    if (page && typeof page.ensureVisible === "function") page.ensureVisible(item)
  }

  function activateFocusedControl() {
    var current = activeControl()
    if (current && current.enabled && current.visible && activateControlOrOwner(current)) return
    if (service && device) service.runAction("play-pause")
  }

  implicitWidth: barRow.implicitWidth + Style.space(14)
  implicitHeight: barSize

  opacity: !service || (!service.hasDevices && !service.loading) ? 0.55 : 1.0

  Row {
    id: barRow
    anchors.centerIn: parent
    spacing: Style.space(6)

    Text {
      id: barGlyph
      anchors.verticalCenter: parent.verticalCenter
      text: "󰓃"
      // Always use the bar's theme foreground, exactly like system icons.
      color: root.bar ? root.bar.barForeground : Color.foreground
      font.family: root.bar ? root.bar.fontFamily : Style.font.family
      font.pixelSize: Style.font.body
    }

    Item {
      id: labelClip
      width: root.showBarLabel ? Math.min(root.maxLabelWidth, labelText.implicitWidth) : 0
      height: barGlyph.height
      clip: true
      visible: root.showBarLabel
      anchors.verticalCenter: parent.verticalCenter

      Row {
        id: marqueeRow
        anchors.verticalCenter: parent.verticalCenter
        spacing: Style.space(18)

        Text {
          id: labelText
          text: root.barLabel
          color: root.bar ? root.bar.barForeground : Color.foreground
          font.family: root.bar ? root.bar.fontFamily : Style.font.family
          font.pixelSize: Style.font.body
        }

        Text {
          text: root.barLabel
          visible: labelText.implicitWidth > labelClip.width
          color: root.bar ? root.bar.barForeground : Color.foreground
          font.family: root.bar ? root.bar.fontFamily : Style.font.family
          font.pixelSize: Style.font.body
        }

        NumberAnimation on x {
          running: labelText.implicitWidth > labelClip.width
            && !root.popupOpen && root.showBarLabel
          loops: Animation.Infinite
          from: 0
          to: -(labelText.implicitWidth + marqueeRow.spacing)
          duration: Math.max(4000, (labelText.implicitWidth + marqueeRow.spacing) * 32)
          easing.type: Easing.Linear
          onRunningChanged: if (!running) marqueeRow.x = 0
        }
      }
    }
  }

  WidgetButton {
    id: barButton
    anchors.fill: parent
    bar: root.bar
    text: " "
    labelVisible: false
    tooltipText: {
      if (!root.service) return "Sonos controller is starting"
      if (root.service.loading && !root.service.hasDevices) return "Searching for Sonos rooms…"
      if (!root.device) return "No Sonos rooms found"
      var track = root.device.title ? " · " + root.device.title : ""
      return root.device.name + " · " + root.playbackLabel.toLowerCase() + track
    }

    onPressed: function(mouseButton) {
      if (!root.service) return
      if (mouseButton === Qt.MiddleButton) root.service.refresh()
      else if (mouseButton === Qt.RightButton) root.service.runAction("play-pause")
      else root.toggle()
    }

    onWheelMoved: function(delta) {
      if (!root.service || !root.device) return
      var wheel = Util.wheelSteps(root.wheelAccumulator, delta)
      root.wheelAccumulator = wheel.remainder
      if (wheel.steps !== 0) root.service.adjustVolume(wheel.steps * root.volumeStep)
    }
  }

  KeyboardPanel {
    id: popup
    anchorItem: barButton
    bar: root.bar
    owner: root
    open: root.popupOpen
    focusTarget: keyCatcher
    contentWidth: popup.fittedContentWidth(root.configuredPanelWidth)
    contentHeight: popup.fittedContentHeight(panelColumn.implicitHeight, root.configuredPanelHeight)

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      blocked: nowPage.editing || browsePage.editing || queuePage.editing
        || roomsPage.editing || systemPage.editing || roomPicker.popupOpen
      onMoveRequested: function(dx, dy) {
        if (dy !== 0) root.moveControlFocus(dy > 0)
        else if (dx !== 0 && root.activeControl() === pageTabs)
          pageTabs.moveCursor(dx)
        else if (dx !== 0 && root.service && root.device)
          root.service.adjustVolume(dx * root.volumeStep)
      }
      onActivateRequested: root.activateFocusedControl()
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.moveControlFocus(direction > 0) }
      onTextKey: function(text) {
        if (!root.service || !root.device) return
        var key = String(text).toLowerCase()
        if (key === "n") root.service.runAction("next")
        else if (key === "p") root.service.runAction("previous")
        else if (key === "m") root.service.runAction("mute-toggle")
        else if (key === "s") root.service.runAction("stop")
        else if (key === "r") root.refreshPanel()
        else if (key === "1") root.activePage = "now"
        else if (key === "2") root.activePage = "browse"
        else if (key === "3") root.activePage = "queue"
        else if (key === "4") root.activePage = "rooms"
        else if (key === "5") root.activePage = "sound"
        else if (key === "6") root.activePage = "system"
      }

      Column {
        id: panelColumn
        anchors.fill: parent
        spacing: Style.space(10)

        PanelHero {
          width: parent.width
          iconComponent: heroIconComponent
          title: root.device ? String(root.device.name || "Sonos") : "Sonarchy"
          meta: {
            if (!root.service) return "Starting"
            if (root.service.loading && !root.service.hasDevices) return "Searching your network"
            var count = root.service.devices.length
            return count === 1 ? "1 room" : count + " rooms"
          }
          detail: root.playbackLabel
          foreground: root.panelForeground
          fontFamily: root.bar.fontFamily
          iconOpacity: root.device ? 1.0 : 0.45
          trailingControl: refreshControlComponent
        }

      PanelSeparator { foreground: root.panelForeground }

      Column {
        width: parent.width
        spacing: Style.space(9)
        visible: root.device !== null

        SonarchyDropdown {
          id: roomPicker
          width: parent.width
          label: "ROOM"
          value: root.device ? String(root.device.uid) : ""
          options: root.service ? root.service.roomOptions() : []
          foreground: root.panelForeground
          fontFamily: root.bar.fontFamily
          onChanged: function(value) { if (root.service) root.service.selectDevice(value) }
        }

        Item {
          id: pageViewport
          width: parent.width
          implicitHeight: Math.max(300, root.configuredPanelHeight - Style.space(258))
          clip: true

          SonarchyNowPage {
            id: nowPage
            anchors.fill: parent
            readonly property bool currentPage: root.activePage === "now"
            visible: currentPage || opacity > 0.01
            enabled: currentPage
            opacity: currentPage ? 1.0 : 0.0
            z: currentPage ? 1 : 0
            bar: root.bar
            service: root.service
            device: root.device
            foreground: root.panelForeground
            fontFamily: root.bar.fontFamily
            showArtwork: root.showArtwork
            volumeStep: root.volumeStep

            Behavior on opacity {
              NumberAnimation { duration: 140; easing.type: Easing.OutCubic }
            }
          }

          SonarchyBrowsePage {
            id: browsePage
            anchors.fill: parent
            readonly property bool currentPage: root.activePage === "browse"
            visible: currentPage || opacity > 0.01
            enabled: currentPage
            opacity: currentPage ? 1.0 : 0.0
            z: currentPage ? 1 : 0
            service: root.service
            device: root.device
            foreground: root.panelForeground
            fontFamily: root.bar.fontFamily
            showArtwork: root.showArtwork

            Behavior on opacity {
              NumberAnimation { duration: 140; easing.type: Easing.OutCubic }
            }
          }

          SonarchyQueuePage {
            id: queuePage
            anchors.fill: parent
            readonly property bool currentPage: root.activePage === "queue"
            visible: currentPage || opacity > 0.01
            enabled: currentPage
            opacity: currentPage ? 1.0 : 0.0
            z: currentPage ? 1 : 0
            service: root.service
            device: root.device
            foreground: root.panelForeground
            fontFamily: root.bar.fontFamily
            showArtwork: root.showArtwork

            Behavior on opacity {
              NumberAnimation { duration: 140; easing.type: Easing.OutCubic }
            }
          }

          SonarchyRoomsPage {
            id: roomsPage
            anchors.fill: parent
            readonly property bool currentPage: root.activePage === "rooms"
            visible: currentPage || opacity > 0.01
            enabled: currentPage
            opacity: currentPage ? 1.0 : 0.0
            z: currentPage ? 1 : 0
            bar: root.bar
            service: root.service
            device: root.device
            foreground: root.panelForeground
            fontFamily: root.bar.fontFamily
            volumeStep: root.volumeStep

            Behavior on opacity {
              NumberAnimation { duration: 140; easing.type: Easing.OutCubic }
            }
          }

          SonarchySoundPage {
            id: soundPage
            anchors.fill: parent
            readonly property bool currentPage: root.activePage === "sound"
            visible: currentPage || opacity > 0.01
            enabled: currentPage
            opacity: currentPage ? 1.0 : 0.0
            z: currentPage ? 1 : 0
            bar: root.bar
            service: root.service
            device: root.device
            foreground: root.panelForeground
            fontFamily: root.bar.fontFamily

            Behavior on opacity {
              NumberAnimation { duration: 140; easing.type: Easing.OutCubic }
            }
          }

          SonarchySystemPage {
            id: systemPage
            anchors.fill: parent
            readonly property bool currentPage: root.activePage === "system"
            visible: currentPage || opacity > 0.01
            enabled: currentPage
            opacity: currentPage ? 1.0 : 0.0
            z: currentPage ? 1 : 0
            bar: root.bar
            service: root.service
            device: root.device
            foreground: root.panelForeground
            fontFamily: root.bar.fontFamily

            Behavior on opacity {
              NumberAnimation { duration: 140; easing.type: Easing.OutCubic }
            }
          }
        }

        PanelSeparator { foreground: root.panelForeground; strength: 0.1 }

        SonarchyNavigation {
          id: pageTabs
          width: parent.width
          options: [
            { value: "now", label: "Now", icon: "󰐊" },
            { value: "browse", label: "Browse", icon: "󰍉" },
            { value: "queue", label: "Queue", icon: "󰎇" },
            { value: "rooms", label: "Rooms", icon: "󰓅" },
            { value: "sound", label: "Sound", icon: "󰕾" },
            { value: "system", label: "System", icon: "󰒓" }
          ]
          value: root.activePage
          foreground: root.panelForeground
          accent: Color.accent
          fontFamily: root.bar.fontFamily
          onChanged: function(value) { root.activePage = value }
        }

        Text {
          width: parent.width
          visible: root.service && root.service.actionMessage !== ""
          text: root.service ? root.service.actionMessage : ""
          color: Qt.darker(root.panelForeground, 1.25)
          font.family: root.bar.fontFamily
          font.pixelSize: Style.font.caption
          font.bold: true
          horizontalAlignment: Text.AlignHCenter
        }
      }

      Column {
        width: parent.width
        spacing: Style.space(10)
        visible: !root.device

        Text {
          anchors.horizontalCenter: parent.horizontalCenter
          text: root.service && root.service.loading ? "󰑐" : "󰒍"
          color: root.panelForeground
          font.family: root.bar.fontFamily
          font.pixelSize: Style.font.displayLarge
          opacity: 0.5

          RotationAnimation on rotation {
            from: 0
            to: 360
            duration: 900
            loops: Animation.Infinite
            running: root.service && root.service.loading
          }
        }

        Text {
          width: parent.width
          text: root.service && root.service.loading ? "Looking for your speakers…" : "No Sonos rooms found"
          color: root.panelForeground
          font.family: root.bar.fontFamily
          font.pixelSize: Style.font.subtitle
          font.bold: true
          horizontalAlignment: Text.AlignHCenter
        }

        Text {
          width: parent.width
          text: "Make sure this computer and your Sonos system are on the same network."
          color: Qt.darker(root.panelForeground, 1.45)
          font.family: root.bar.fontFamily
          font.pixelSize: Style.font.bodySmall
          wrapMode: Text.WordWrap
          horizontalAlignment: Text.AlignHCenter
        }

        Button {
          anchors.horizontalCenter: parent.horizontalCenter
          text: "Search again"
          iconText: "󰑐"
          foreground: root.panelForeground
          bordered: true
          focusable: true
          enabled: root.service && !root.service.loading
          onClicked: root.service.refresh()
        }
      }

      BorderSurface {
        width: parent.width
        visible: root.service && root.service.lastError !== ""
        implicitHeight: errorRow.implicitHeight + Style.space(12)
        radius: Style.cornerRadius
        color: Util.alpha(Color.urgent, 0.12)
        borderSpec: Border.flat(Util.alpha(Color.urgent, 0.65), Math.max(1, Style.normalBorderWidth))

        Row {
          id: errorRow
          anchors.left: parent.left
          anchors.right: parent.right
          anchors.verticalCenter: parent.verticalCenter
          anchors.leftMargin: Style.space(8)
          anchors.rightMargin: Style.space(8)
          spacing: Style.space(7)

          Text {
            text: "󰅚"
            color: Color.urgent
            font.family: root.bar.fontFamily
            font.pixelSize: Style.font.body
          }

          Text {
            width: parent.width - Style.space(25) - errorDismissButton.width
              - errorRow.spacing
            text: root.service ? root.service.lastError : ""
            color: root.panelForeground
            font.family: root.bar.fontFamily
            font.pixelSize: Style.font.caption
            wrapMode: Text.WordWrap
          }

          Button {
            id: errorDismissButton
            anchors.verticalCenter: parent.verticalCenter
            iconText: "󰅖"
            tooltipText: "Dismiss error"
            foreground: root.panelForeground
            focusable: true
            onClicked: if (root.service) root.service.clearError()
          }
        }
      }
      }
    }
  }
}
