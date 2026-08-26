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

  readonly property var sound: service ? service.soundDetails : ({})
  readonly property var playback: service ? service.playbackDetails : ({})
  readonly property bool hasSettings: available(sound.bass)
    || available(sound.treble) || available(sound.balance)
    || available(sound.loudness) || available(sound.night_mode)
    || available(sound.speech_enhancement) || available(sound.sub_enabled)
    || available(sound.sub_gain) || available(sound.sub_crossover)
    || available(sound.surround_enabled) || available(sound.surround_mode)
    || available(sound.surround_tv) || available(sound.surround_music)
    || available(sound.audio_delay) || available(playback.crossfade)

  onVisibleChanged: if (visible && service) service.refreshDetails()

  function available(value) {
    return value !== null && value !== undefined
  }

  function ensureVisible(item) {
    if (!item || !soundFlick.visible) return
    var point = item.mapToItem(soundFlick.contentItem, 0, 0)
    var top = point.y - Style.space(10)
    var bottom = point.y + item.height + Style.space(10)
    if (top < soundFlick.contentY) soundFlick.contentY = Math.max(0, top)
    else if (bottom > soundFlick.contentY + soundFlick.height)
      soundFlick.contentY = Math.min(
        Math.max(0, soundFlick.contentHeight - soundFlick.height),
        bottom - soundFlick.height)
  }

  component NumberSetting: Column {
    id: numberSetting
    required property string title
    required property string setting
    required property real current
    required property real minimum
    required property real maximum
    property real step: 1
    property string suffix: ""

    width: parent ? parent.width : 0
    spacing: Style.space(6)

    Item {
      width: parent.width
      implicitHeight: Math.max(settingHeader.implicitHeight, settingValue.implicitHeight)

      PanelSectionHeader {
        id: settingHeader
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        text: numberSetting.title
        foreground: root.foreground
        fontFamily: root.fontFamily
      }

      Text {
        id: settingValue
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        text: (numberSetting.current > 0 ? "+" : "")
          + String(Math.round(numberSetting.current)) + numberSetting.suffix
        color: Qt.darker(root.foreground, 1.35)
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
        font.bold: true
      }
    }

    Row {
      width: parent.width
      spacing: Style.space(6)

      Button {
        text: "−"
        tooltipText: "Decrease " + numberSetting.title.toLowerCase()
        foreground: root.foreground
        focusable: true
        enabled: root.service && !root.service.actionBusy
          && numberSetting.current > numberSetting.minimum
        onClicked: root.service.setSound(numberSetting.setting,
          Math.max(numberSetting.minimum, numberSetting.current - numberSetting.step))
      }

      PanelSlider {
        width: parent.width - parent.children[0].width - parent.children[2].width
          - parent.spacing * 2
        anchors.verticalCenter: parent.verticalCenter
        bar: root.bar
        minimum: numberSetting.minimum
        maximum: numberSetting.maximum
        step: numberSetting.step
        integer: true
        value: numberSetting.current
        enabled: root.service && !root.service.actionBusy
        onReleased: function(value) {
          root.service.setSound(numberSetting.setting, Math.round(value))
        }
      }

      Button {
        text: "+"
        tooltipText: "Increase " + numberSetting.title.toLowerCase()
        foreground: root.foreground
        focusable: true
        enabled: root.service && !root.service.actionBusy
          && numberSetting.current < numberSetting.maximum
        onClicked: root.service.setSound(numberSetting.setting,
          Math.min(numberSetting.maximum, numberSetting.current + numberSetting.step))
      }
    }
  }

  Flickable {
    id: soundFlick
    anchors.fill: parent
    contentWidth: width
    contentHeight: soundColumn.implicitHeight
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    flickableDirection: Flickable.VerticalFlick

    QQC.ScrollBar.vertical: QQC.ScrollBar {
      policy: QQC.ScrollBar.AsNeeded
    }

    Column {
      id: soundColumn
      width: soundFlick.width - Style.space(6)
      spacing: Style.space(10)

      Text {
        width: parent.width
        visible: root.service && root.service.detailsLoading && !root.hasSettings
        text: "Reading sound settings…"
        color: Qt.darker(root.foreground, 1.45)
        font.family: root.fontFamily
        font.pixelSize: Style.font.bodySmall
        horizontalAlignment: Text.AlignHCenter
        topPadding: Style.space(20)
      }

      Text {
        width: parent.width
        visible: root.service && !root.service.detailsLoading && !root.hasSettings
        text: "No additional sound controls are available for this room."
        color: Qt.darker(root.foreground, 1.45)
        font.family: root.fontFamily
        font.pixelSize: Style.font.bodySmall
        wrapMode: Text.WordWrap
        horizontalAlignment: Text.AlignHCenter
        topPadding: Style.space(20)
      }

      NumberSetting {
        visible: root.available(root.sound.bass)
        title: "BASS"
        setting: "bass"
        current: Number(root.sound.bass || 0)
        minimum: -10
        maximum: 10
      }

      NumberSetting {
        visible: root.available(root.sound.treble)
        title: "TREBLE"
        setting: "treble"
        current: Number(root.sound.treble || 0)
        minimum: -10
        maximum: 10
      }

      NumberSetting {
        visible: root.available(root.sound.balance)
        title: "BALANCE"
        setting: "balance"
        current: Number(root.sound.balance || 0)
        minimum: -100
        maximum: 100
        step: 5
      }

      PanelSeparator { foreground: root.foreground; visible: root.hasSettings }

      SonarchyToggle {
        width: parent.width
        visible: root.available(root.sound.loudness)
        label: "Loudness"
        description: "Boost bass and treble at lower listening volumes"
        checked: root.sound.loudness === true
        foreground: root.foreground
        accent: Color.accent
        fontFamily: root.fontFamily
        enabled: root.service && !root.service.actionBusy
        onClicked: root.service.setSound("loudness", checked ? "off" : "on")
      }

      SonarchyToggle {
        width: parent.width
        visible: root.available(root.playback.crossfade)
        label: "Crossfade"
        description: root.playback.play_mode_supported === true
          ? "Blend the end of one queued track into the next"
          : "Available when the Sonos queue is active"
        checked: root.playback.crossfade === true
        foreground: root.foreground
        accent: Color.accent
        fontFamily: root.fontFamily
        enabled: root.service && !root.service.actionBusy
          && root.playback.play_mode_supported === true
        onClicked: root.service.setPlaybackOption("crossfade", checked ? "off" : "on")
      }

      SonarchyToggle {
        width: parent.width
        visible: root.available(root.sound.night_mode)
        label: "Night mode"
        description: "Reduce loud effects on compatible TV rooms"
        checked: root.sound.night_mode === true
        foreground: root.foreground
        accent: Color.accent
        fontFamily: root.fontFamily
        enabled: root.service && !root.service.actionBusy
        onClicked: root.service.setSound("night-mode", checked ? "off" : "on")
      }

      SonarchyToggle {
        width: parent.width
        visible: root.available(root.sound.speech_enhancement)
        label: "Speech enhancement"
        description: "Make television dialogue clearer"
        checked: root.sound.speech_enhancement === true
        foreground: root.foreground
        accent: Color.accent
        fontFamily: root.fontFamily
        enabled: root.service && !root.service.actionBusy
        onClicked: root.service.setSound(
          "speech-enhancement", checked ? "off" : "on")
      }

      PanelSeparator {
        foreground: root.foreground
        visible: root.available(root.sound.sub_enabled)
          || root.available(root.sound.surround_enabled)
      }

      SonarchyToggle {
        width: parent.width
        visible: root.available(root.sound.sub_enabled)
        label: "Subwoofer"
        description: "Enable the bonded Sonos subwoofer"
        checked: root.sound.sub_enabled === true
        foreground: root.foreground
        accent: Color.accent
        fontFamily: root.fontFamily
        enabled: root.service && !root.service.actionBusy
        onClicked: root.service.setSound("sub-enabled", checked ? "off" : "on")
      }

      NumberSetting {
        visible: root.available(root.sound.sub_gain)
        title: "SUB LEVEL"
        setting: "sub-gain"
        current: Number(root.sound.sub_gain || 0)
        minimum: -15
        maximum: 15
      }

      NumberSetting {
        visible: root.available(root.sound.sub_crossover)
        title: "SUB CROSSOVER"
        setting: "sub-crossover"
        current: Number(root.sound.sub_crossover || 80)
        minimum: 50
        maximum: 110
        step: 10
        suffix: " Hz"
      }

      SonarchyToggle {
        width: parent.width
        visible: root.available(root.sound.surround_enabled)
        label: "Surround speakers"
        description: "Enable bonded surround speakers"
        checked: root.sound.surround_enabled === true
        foreground: root.foreground
        accent: Color.accent
        fontFamily: root.fontFamily
        enabled: root.service && !root.service.actionBusy
        onClicked: root.service.setSound("surround-enabled", checked ? "off" : "on")
      }

      SonarchyToggle {
        width: parent.width
        visible: root.available(root.sound.surround_mode)
        label: "Full music playback"
        description: "Use full-range surrounds for music"
        checked: root.sound.surround_mode === true
        foreground: root.foreground
        accent: Color.accent
        fontFamily: root.fontFamily
        enabled: root.service && !root.service.actionBusy
        onClicked: root.service.setSound("surround-mode", checked ? "off" : "on")
      }

      NumberSetting {
        visible: root.available(root.sound.surround_tv)
        title: "SURROUND TV LEVEL"
        setting: "surround-tv"
        current: Number(root.sound.surround_tv || 0)
        minimum: -15
        maximum: 15
      }

      NumberSetting {
        visible: root.available(root.sound.surround_music)
        title: "SURROUND MUSIC LEVEL"
        setting: "surround-music"
        current: Number(root.sound.surround_music || 0)
        minimum: -15
        maximum: 15
      }

      NumberSetting {
        visible: root.available(root.sound.audio_delay)
        title: "TV DIALOG SYNC"
        setting: "audio-delay"
        current: Number(root.sound.audio_delay || 0)
        minimum: 0
        maximum: 5
      }
    }
  }
}
