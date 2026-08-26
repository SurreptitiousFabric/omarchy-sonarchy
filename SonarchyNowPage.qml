import QtQuick
import QtQuick.Controls as QQC
import qs.Commons
import qs.Ui

Item {
  id: root

  property var bar: null
  property var service: null
  property var device: null
  property color foreground: Color.popups.text
  property string fontFamily: Style.font.family
  property bool showArtwork: true
  property int volumeStep: 2
  readonly property var live: service ? service.livePlayback : ({})

  readonly property string playbackLabel: {
    if (!device) return "OFFLINE"
    if (device.state === "PLAYING") return "PLAYING"
    if (device.state === "PAUSED_PLAYBACK") return "PAUSED"
    if (device.state === "TRANSITIONING") return "BUFFERING"
    if (device.state === "UNAVAILABLE") return "UNAVAILABLE"
    return "STOPPED"
  }
  readonly property string repeatMode: service && service.playbackDetails.repeat
    ? String(service.playbackDetails.repeat) : "off"
  readonly property bool playModeSupported: service
    && service.playbackDetails.play_mode_supported === true
  readonly property bool canSeek: service && service.hasCapability("playback.seek")
  readonly property bool canSetGroupVolume: service
    && service.hasCapability("volume.group.set")
  readonly property bool editing: sleepPicker.popupOpen

  function nextRepeatMode() {
    return repeatMode === "off" ? "all" : (repeatMode === "all" ? "one" : "off")
  }

  function sleepOptions() {
    var options = [
      { value: "off", label: "Off" },
      { value: "900", label: "15 minutes" },
      { value: "1800", label: "30 minutes" },
      { value: "2700", label: "45 minutes" },
      { value: "3600", label: "1 hour" },
      { value: "5400", label: "90 minutes" },
      { value: "7200", label: "2 hours" }
    ]
    var remaining = service && service.playbackDetails
      ? Number(service.playbackDetails.sleep_timer) : 0
    if (remaining > 0)
      options.unshift({ value: String(remaining), label: Math.max(1, Math.ceil(remaining / 60)) + " min left" })
    return options
  }

  function sleepValue() {
    var remaining = service && service.playbackDetails
      ? Number(service.playbackDetails.sleep_timer) : 0
    return remaining > 0 ? String(remaining) : "off"
  }

  function ensureVisible(item) {
    if (!item || !nowFlick.visible) return
    var point = item.mapToItem(nowFlick.contentItem, 0, 0)
    var top = point.y - Style.space(10)
    var bottom = point.y + item.height + Style.space(10)
    if (top < nowFlick.contentY) nowFlick.contentY = Math.max(0, top)
    else if (bottom > nowFlick.contentY + nowFlick.height)
      nowFlick.contentY = Math.min(
        Math.max(0, nowFlick.contentHeight - nowFlick.height),
        bottom - nowFlick.height)
  }

  Flickable {
    id: nowFlick
    anchors.fill: parent
    contentWidth: width
    contentHeight: contentColumn.implicitHeight
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    flickableDirection: Flickable.VerticalFlick

    QQC.ScrollBar.vertical: QQC.ScrollBar {
      policy: QQC.ScrollBar.AsNeeded
    }

    Column {
      id: contentColumn
      width: nowFlick.width - Style.space(6)
      spacing: Style.space(10)

      BorderSurface {
        id: nowPlayingCard
        width: parent.width
        implicitHeight: root.showArtwork ? Style.space(126) : Style.space(94)
        radius: Style.cornerRadius
        color: Style.normalFillFor(root.foreground, Color.accent)
        borderSpec: Border.none()
        clip: true

        Rectangle {
          anchors.left: parent.left
          anchors.top: parent.top
          anchors.bottom: parent.bottom
          width: Style.space(3)
          color: root.device && (root.device.is_playing
            || root.device.state === "TRANSITIONING") ? Color.accent : "transparent"

          Behavior on color { ColorAnimation { duration: 160 } }
        }

        BorderSurface {
          id: artworkSurface
          anchors.left: parent.left
          anchors.leftMargin: Style.space(12)
          anchors.verticalCenter: parent.verticalCenter
          width: Style.space(102)
          height: Style.space(102)
          radius: Math.max(2, Style.cornerRadius - Style.space(1))
          color: Style.selectedFillFor(root.foreground, Color.accent)
          borderSpec: Border.flat(Util.alpha(root.foreground, 0.12),
            Math.max(1, Style.normalBorderWidth))
          clip: true
          visible: root.showArtwork

          Image {
            id: artwork
            anchors.fill: parent
            source: root.device ? String(root.device.album_art || "") : ""
            fillMode: Image.PreserveAspectCrop
            asynchronous: true
            cache: true
            opacity: status === Image.Ready ? 1.0 : 0.0

            Behavior on opacity {
              NumberAnimation { duration: 180; easing.type: Easing.OutCubic }
            }
          }

          OpticalGlyph {
            anchors.centerIn: parent
            width: Style.space(42)
            height: Style.space(42)
            visible: artwork.status !== Image.Ready
            text: "󰎆"
            color: root.foreground
            fontFamily: root.fontFamily
            fontSize: Style.font.displayLarge
            opacity: 0.5
          }

        }

        Column {
          anchors.left: root.showArtwork ? artworkSurface.right : parent.left
          anchors.leftMargin: Style.space(14)
          anchors.right: parent.right
          anchors.rightMargin: Style.space(14)
          anchors.verticalCenter: parent.verticalCenter
          spacing: Style.space(4)

          Text {
            width: parent.width
            text: root.device && root.device.title ? root.device.title
              : (root.device && root.device.is_playing ? "Live audio" : "Nothing playing")
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.heading
            font.bold: true
            elide: Text.ElideRight
          }

          Text {
            width: parent.width
            visible: text !== ""
            text: root.device ? String(root.device.artist || "") : ""
            color: Qt.darker(root.foreground, 1.2)
            font.family: root.fontFamily
            font.pixelSize: Style.font.subtitle
            elide: Text.ElideRight
          }

          Text {
            width: parent.width
            visible: text !== ""
            text: root.device ? String(root.device.album || "") : ""
            color: Qt.darker(root.foreground, 1.48)
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            elide: Text.ElideRight
          }

          Row {
            spacing: Style.space(6)

            Rectangle {
              anchors.verticalCenter: parent.verticalCenter
              width: Style.space(6)
              height: width
              radius: width / 2
              color: root.device && root.device.is_playing
                ? Color.accent : Qt.darker(root.foreground, 1.55)
            }

            Text {
              text: root.playbackLabel
              color: root.device && root.device.is_playing
                ? Color.accent : Qt.darker(root.foreground, 1.42)
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              font.bold: true
              font.letterSpacing: 0.8
            }
          }
        }
      }

      Column {
        width: parent.width
        spacing: Style.space(2)
        visible: root.service && Number(root.live.durationSec || 0) > 0

        Row {
          width: parent.width
          spacing: Style.space(6)

          Button {
            id: seekBackButton
            text: "−10"
            tooltipText: "Back 10 seconds"
            foreground: root.foreground
            focusable: true
            enabled: root.service && !root.service.actionBusy
              && root.canSeek
              && Number(root.live.positionSec || 0) > 0
            opacity: enabled ? 0.82 : 0.35
            onClicked: root.service.seek(
              Math.max(0, Number(root.live.positionSec || 0) - 10))
          }

          SonarchySlider {
            scrollTarget: nowFlick
            width: parent.width - seekBackButton.width - seekForwardButton.width
              - parent.spacing * 2
            anchors.verticalCenter: parent.verticalCenter
            bar: root.bar
            minimum: 0
            maximum: Math.max(1, Number(root.live.durationSec || 1))
            step: 1
            integer: true
            value: Number(root.live.positionSec || 0)
            enabled: root.service && !root.service.actionBusy && root.canSeek
            onReleased: function(value) { root.service.seek(value) }
          }

          Button {
            id: seekForwardButton
            text: "+10"
            tooltipText: "Forward 10 seconds"
            foreground: root.foreground
            focusable: true
            enabled: root.service && !root.service.actionBusy
              && root.canSeek
              && Number(root.live.positionSec || 0) < Number(root.live.durationSec || 0)
            opacity: enabled ? 0.82 : 0.35
            onClicked: root.service.seek(Math.min(
              Number(root.live.durationSec || 0),
              Number(root.live.positionSec || 0) + 10))
          }
        }

        Item {
          width: parent.width
          implicitHeight: Math.max(positionLabel.implicitHeight, durationLabel.implicitHeight)

          Text {
            id: positionLabel
            anchors.left: parent.left
            text: root.service ? root.service.formatTime(root.live.positionSec) : ""
            color: Qt.darker(root.foreground, 1.45)
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }

          Text {
            id: durationLabel
            anchors.right: parent.right
            text: root.service ? root.service.formatTime(root.live.durationSec) : ""
            color: Qt.darker(root.foreground, 1.45)
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }
        }
      }

      Item {
        width: parent.width
        implicitHeight: Math.max(primaryTransport.implicitHeight, stopButton.implicitHeight)

        Row {
          id: primaryTransport
          anchors.horizontalCenter: parent.horizontalCenter
          spacing: Style.space(8)

          Button {
            iconText: "󰒮"
            tooltipText: "Previous track"
            foreground: root.foreground
            focusable: true
            enabled: root.service && !root.service.actionBusy
              && root.service.hasCapability("playback.previous")
            opacity: enabled ? 1.0 : 0.35
            onClicked: root.service.runAction("previous")
          }

          Button {
            iconText: root.device && root.device.is_playing ? "󰏤" : "󰐊"
            tooltipText: root.device && root.device.is_playing ? "Pause" : "Play"
            foreground: root.foreground
            focusable: true
            selected: true
            iconSize: Style.font.iconLarge
            horizontalPadding: Style.space(14)
            verticalPadding: Style.space(9)
            enabled: root.service && !root.service.actionBusy
              && root.service.hasCapability("playback.toggle")
            opacity: enabled ? 1.0 : 0.4
            onClicked: root.service.runAction("play-pause")
          }

          Button {
            iconText: "󰒭"
            tooltipText: "Next track"
            foreground: root.foreground
            focusable: true
            enabled: root.service && !root.service.actionBusy
              && root.service.hasCapability("playback.next")
            opacity: enabled ? 1.0 : 0.35
            onClicked: root.service.runAction("next")
          }
        }

        Button {
          id: stopButton
          anchors.right: parent.right
          anchors.verticalCenter: primaryTransport.verticalCenter
          iconText: "󰓛"
          tooltipText: "Stop"
          foreground: root.foreground
          focusable: true
          enabled: root.service && !root.service.actionBusy
            && root.service.hasCapability("playback.stop")
          opacity: enabled ? 0.62 : 0.28
          onClicked: root.service.runAction("stop")
        }
      }

      PanelSeparator { foreground: root.foreground; strength: 0.1 }

      Column {
        width: parent.width
        spacing: Style.space(5)

        Item {
          width: parent.width
          implicitHeight: Math.max(volumeHeader.implicitHeight, volumeValue.implicitHeight)

          PanelSectionHeader {
            id: volumeHeader
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            text: root.device && root.device.group_members
              && root.device.group_members.length > 1 ? "GROUP VOLUME" : "ROOM VOLUME"
            foreground: root.foreground
            fontFamily: root.fontFamily
          }

          Text {
            id: volumeValue
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            text: root.device ? Math.round(Number(root.device.volume || 0)) + "%" : "—"
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            font.bold: true
          }
        }

        Row {
          width: parent.width
          spacing: Style.space(9)

          Button {
            width: Style.space(34)
            anchors.verticalCenter: parent.verticalCenter
            iconText: root.device && root.device.muted ? "󰝟" : "󰕾"
            tooltipText: root.device && root.device.muted ? "Unmute playback group" : "Mute playback group"
            foreground: root.foreground
            focusable: true
            selected: root.device && root.device.muted
            enabled: root.service && !root.service.actionBusy
              && root.service.hasCapability("mute.group.set")
            onClicked: root.service.runAction("mute-toggle")
          }

          SonarchySlider {
            scrollTarget: nowFlick
            width: parent.width - Style.space(43)
            anchors.verticalCenter: parent.verticalCenter
            bar: root.bar
            minimum: 0
            maximum: 100
            step: Math.max(1, root.volumeStep)
            integer: true
            value: root.device ? Number(root.device.volume || 0) : 0
            enabled: root.service && !root.service.actionBusy && root.canSetGroupVolume
            opacity: root.device && root.device.muted ? 0.48 : 1.0
            onMoved: function(value) { if (root.service) root.service.requestVolume(value) }
            onReleased: function(value) { if (root.service) root.service.requestVolume(value) }
            onRightClicked: if (root.service) root.service.runAction("mute-toggle")
          }
        }
      }

      PanelSeparator { foreground: root.foreground; strength: 0.1 }

      Item {
        width: parent.width
        implicitHeight: Math.max(modeHeader.implicitHeight, modeButtons.implicitHeight)

        PanelSectionHeader {
          id: modeHeader
          anchors.left: parent.left
          anchors.verticalCenter: parent.verticalCenter
          text: "PLAY MODE"
          foreground: root.foreground
          fontFamily: root.fontFamily
        }

        Row {
          id: modeButtons
          anchors.right: parent.right
          anchors.verticalCenter: parent.verticalCenter
          spacing: Style.space(5)

          Button {
            iconText: "󰒟"
            tooltipText: !root.playModeSupported ? "Available when the Sonos queue is active"
              : (root.service && root.service.playbackDetails.shuffle
                 ? "Turn shuffle off" : "Turn shuffle on")
            foreground: root.foreground
            focusable: true
            selected: root.service && root.service.playbackDetails.shuffle === true
            enabled: root.service && !root.service.actionBusy && root.playModeSupported
              && root.service.hasCapability("playback.option.set")
            opacity: enabled ? 1.0 : 0.35
            onClicked: root.service.setPlaybackOption(
              "shuffle", root.service.playbackDetails.shuffle === true ? "off" : "on")
          }

          Button {
            iconText: root.repeatMode === "one" ? "󰑘" : "󰑖"
            tooltipText: !root.playModeSupported ? "Available when the Sonos queue is active"
              : (root.repeatMode === "off" ? "Repeat off"
                 : (root.repeatMode === "all" ? "Repeat all" : "Repeat one"))
            foreground: root.foreground
            focusable: true
            selected: root.repeatMode !== "off"
            enabled: root.service && !root.service.actionBusy && root.playModeSupported
              && root.service.hasCapability("playback.option.set")
            opacity: enabled ? 1.0 : 0.35
            onClicked: root.service.setPlaybackOption("repeat", root.nextRepeatMode())
          }
        }
      }

      Item {
        width: parent.width
        implicitHeight: Math.max(sleepHeader.implicitHeight, sleepPicker.implicitHeight)

        PanelSectionHeader {
          id: sleepHeader
          anchors.left: parent.left
          anchors.verticalCenter: parent.verticalCenter
          text: "SLEEP TIMER"
          foreground: root.foreground
          fontFamily: root.fontFamily
          enabled: root.service && !root.service.actionBusy
            && root.service.hasCapability("playback.option.set")
        }

        SonarchyDropdown {
          id: sleepPicker
          anchors.right: parent.right
          anchors.verticalCenter: parent.verticalCenter
          width: Math.min(Style.space(180), parent.width * 0.54)
          showLabel: false
          value: root.sleepValue()
          options: root.sleepOptions()
          foreground: root.foreground
          fontFamily: root.fontFamily
          onChanged: function(value) {
            if (root.service) root.service.setPlaybackOption("sleep", value)
          }
        }
      }
    }
  }
}
