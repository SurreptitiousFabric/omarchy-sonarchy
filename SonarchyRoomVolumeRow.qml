import QtQuick
import qs.Commons
import qs.Ui

Row {
  id: root

  required property var service
  required property var room
  property var bar: null
  property var scrollTarget: null
  property color foreground: Color.popups.text
  property string fontFamily: Style.font.family
  property int volumeStep: 2

  readonly property real roomVolume: room && room.room_volume !== undefined
    ? Number(room.room_volume || 0) : Number(room && room.volume || 0)
  readonly property bool roomMuted: room && room.room_muted !== undefined
    ? room.room_muted === true : room && room.muted === true

  spacing: Style.space(6)

  Text {
    width: Style.space(100)
    anchors.verticalCenter: parent.verticalCenter
    text: String(root.room && root.room.name || "Sonos")
    color: root.foreground
    font.family: root.fontFamily
    font.pixelSize: Style.font.bodySmall
    elide: Text.ElideRight
  }

  Button {
    anchors.verticalCenter: parent.verticalCenter
    text: "−"
    foreground: root.foreground
    focusable: true
    enabled: root.service && !root.service.actionBusy
      && root.service.hasCapability("volume.room.set") && root.roomVolume > 0
    onClicked: root.service.adjustRoomVolume(
      String(root.room.uid), -Math.max(1, root.volumeStep))
  }

  SonarchySlider {
    scrollTarget: root.scrollTarget
    bar: root.bar
    anchors.verticalCenter: parent.verticalCenter
    width: Math.max(Style.space(70), root.width - Style.space(228))
    minimum: 0
    maximum: 100
    step: Math.max(1, root.volumeStep)
    integer: true
    value: root.roomVolume
    enabled: root.service && !root.service.actionBusy
      && root.service.hasCapability("volume.room.set")
    opacity: root.roomMuted ? 0.48 : 1.0
    onReleased: function(value) {
      root.service.setRoomVolume(String(root.room.uid), value)
    }
  }

  Button {
    anchors.verticalCenter: parent.verticalCenter
    text: "+"
    foreground: root.foreground
    focusable: true
    enabled: root.service && !root.service.actionBusy
      && root.service.hasCapability("volume.room.set") && root.roomVolume < 100
    onClicked: root.service.adjustRoomVolume(
      String(root.room.uid), Math.max(1, root.volumeStep))
  }

  Button {
    anchors.verticalCenter: parent.verticalCenter
    iconText: root.roomMuted ? "󰝟" : "󰓄"
    tooltipText: root.roomMuted ? "Unmute room" : "Mute room"
    foreground: root.foreground
    focusable: true
    enabled: root.service && !root.service.actionBusy
      && root.service.hasCapability("mute.room.set")
    onClicked: root.service.setRoomMute(String(root.room.uid), !root.roomMuted)
  }
}
