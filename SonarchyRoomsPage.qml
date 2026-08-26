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
  property int volumeStep: 2
  property string loadedUid: ""
  property var stagedRoomUids: []
  property bool groupingDirty: false
  property bool groupingApplying: false
  readonly property bool editing: renameField.activeFocus

  onDeviceChanged: {
    syncRoomName()
    if (!groupingDirty) resetStagedRooms()
  }
  onVisibleChanged: {
    if (!visible) return
    syncRoomName()
    resetStagedRooms()
  }

  function syncRoomName() {
    var uid = device ? String(device.uid || "") : ""
    if (uid === loadedUid) return
    loadedUid = uid
    renameField.text = device ? String(device.name || "") : ""
  }

  function focusRename() {
    if (!visible || !device) return
    renameField.forceActiveFocus()
    renameField.selectAll()
  }

  function ensureVisible(item) {
    if (!item || !roomsFlick.visible) return
    var point = item.mapToItem(roomsFlick.contentItem, 0, 0)
    var top = point.y - Style.space(10)
    var bottom = point.y + item.height + Style.space(10)
    if (top < roomsFlick.contentY) roomsFlick.contentY = Math.max(0, top)
    else if (bottom > roomsFlick.contentY + roomsFlick.height)
      roomsFlick.contentY = Math.min(
        Math.max(0, roomsFlick.contentHeight - roomsFlick.height),
        bottom - roomsFlick.height)
  }

  function resetStagedRooms() {
    stagedRoomUids = service && service.target && service.target.memberUids
      ? service.target.memberUids.slice() : []
    groupingDirty = false
    groupingApplying = false
  }

  function roomStaged(uid) {
    return stagedRoomUids.indexOf(String(uid)) !== -1
  }

  function toggleStagedRoom(uid) {
    var value = String(uid)
    var next = stagedRoomUids.slice()
    var index = next.indexOf(value)
    if (index === -1) next.push(value)
    else if (next.length > 1) next.splice(index, 1)
    stagedRoomUids = next
    groupingDirty = true
  }

  function stageEverywhere() {
    var next = []
    var rooms = service ? service.rooms : []
    for (var i = 0; i < rooms.length; i++) next.push(String(rooms[i].uid))
    stagedRoomUids = next
    groupingDirty = true
  }

  function applyStagedRooms() {
    if (!service || stagedRoomUids.length === 0) return
    groupingApplying = true
    service.applyMembers(stagedRoomUids.slice())
    groupingSettle.restart()
  }

  Timer {
    id: groupingSettle
    interval: 20000
    repeat: false
    onTriggered: root.resetStagedRooms()
  }

  Connections {
    target: root.service
    function onTargetChanged() {
      if (root.groupingApplying || !root.groupingDirty)
        root.resetStagedRooms()
    }
  }

  Flickable {
    id: roomsFlick
    anchors.fill: parent
    contentWidth: width
    contentHeight: roomsColumn.implicitHeight
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    flickableDirection: Flickable.VerticalFlick

    QQC.ScrollBar.vertical: QQC.ScrollBar {
      policy: QQC.ScrollBar.AsNeeded
    }

    Column {
      id: roomsColumn
      width: roomsFlick.width - Style.space(6)
      spacing: Style.space(10)

      PanelSectionHeader {
        text: "ROOM NAME"
        foreground: root.foreground
        fontFamily: root.fontFamily
      }

      Row {
        width: parent.width
        spacing: Style.space(7)

        TextField {
          id: renameField
          width: parent.width - renameButton.width - parent.spacing
          placeholderText: "Room name"
          selectByMouse: true
          foreground: root.foreground
          accent: Color.accent
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
          onAccepted: {
            if (root.service && text.trim() !== "") root.service.renameRoom(text)
          }
          Keys.onEscapePressed: {
            root.loadedUid = ""
            root.syncRoomName()
            focus = false
          }
        }

        Button {
          id: renameButton
          anchors.verticalCenter: parent.verticalCenter
          iconText: "󰏫"
          text: "Rename"
          foreground: root.foreground
          bordered: true
          focusable: true
          enabled: root.service && !root.service.actionBusy
            && renameField.text.trim() !== ""
            && root.device
            && renameField.text.trim() !== String(root.device.name || "")
          onClicked: root.service.renameRoom(renameField.text)
        }
      }

      Text {
        width: parent.width
        text: "Changes the real room name everywhere, including the official Sonos app."
        color: Qt.darker(root.foreground, 1.5)
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
        wrapMode: Text.WordWrap
      }

      PanelSeparator {
        visible: root.service && root.service.sessions.length > 1
        foreground: root.foreground
      }

      Column {
        width: parent.width
        spacing: Style.space(6)
        visible: root.service && root.service.sessions.length > 1

        PanelSectionHeader {
          text: "PLAYBACK SESSIONS"
          foreground: root.foreground
          fontFamily: root.fontFamily
        }

        Text {
          width: parent.width
          text: "Choose a separate stream to control. This does not move its audio."
          color: Qt.darker(root.foreground, 1.5)
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          wrapMode: Text.WordWrap
        }

        Repeater {
          model: root.service ? root.service.sessions : []

          delegate: Button {
            required property var modelData
            width: parent.width
            text: String(modelData.label)
              + (String(modelData.playbackState) === "PLAYING" ? "  ·  Playing" : "")
            iconText: String(modelData.playbackState) === "PLAYING" ? "󰐊" : "󰓃"
            foreground: root.foreground
            focusable: true
            leftAlign: true
            selected: root.service && root.service.target
              && String(root.service.target.groupUid) === String(modelData.uid)
            enabled: !selected
            onClicked: root.service.selectSession(String(modelData.uid))
          }
        }
      }

      PanelSeparator { foreground: root.foreground }

      Column {
        width: parent.width
        spacing: Style.space(6)

        PanelSectionHeader {
          text: root.service
            && ["PLAYING", "TRANSITIONING"].indexOf(
              String(root.service.livePlayback.state || "").toUpperCase()) !== -1
            ? "MOVE PLAYBACK" : "CONTROL ROOM"
          foreground: root.foreground
          fontFamily: root.fontFamily
        }

        Text {
          width: parent.width
          text: root.service
            && ["PLAYING", "TRANSITIONING"].indexOf(
              String(root.service.livePlayback.state || "").toUpperCase()) !== -1
            ? "Hand off the current stream without accidentally dismantling another group."
            : "Choose the exact room for its name, sound settings, and controls."
          color: Qt.darker(root.foreground, 1.5)
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          wrapMode: Text.WordWrap
        }

        Flow {
          width: parent.width
          spacing: Style.space(5)

          Repeater {
            model: root.service ? root.service.rooms : []

            delegate: Button {
              required property var modelData
              readonly property bool exactRoom: root.device
                && String(root.device.uid) === String(modelData.uid)
              readonly property bool blockedMove: root.service
                ? root.service.roomMoveBlocked(String(modelData.uid)) : true
              text: String(modelData.name || "Sonos")
              foreground: root.foreground
              focusable: true
              selected: exactRoom
              enabled: !exactRoom && !blockedMove && root.service && !root.service.actionBusy
              tooltipText: blockedMove
                ? "Change group membership below before moving audio here"
                : (exactRoom ? "Current room" : "Use this room")
              onClicked: root.service.movePlaybackToRoom(String(modelData.uid))
            }
          }
        }

        Text {
          width: parent.width
          visible: root.service && root.service.target
            && root.service.target.memberUids
            && root.service.target.memberUids.length > 1
            && ["PLAYING", "TRANSITIONING"].indexOf(
              String(root.service.livePlayback.state || "").toUpperCase()) !== -1
          text: "The current audio is grouped. Adjust Group settings first if you want it on one room."
          color: Qt.darker(root.foreground, 1.35)
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          wrapMode: Text.WordWrap
        }
      }

      PanelSeparator { foreground: root.foreground }

      Column {
        id: roomMixer
        width: parent.width
        spacing: Style.space(7)

        PanelSectionHeader {
          text: "ALL-ROOM MIXER"
          foreground: root.foreground
          fontFamily: root.fontFamily
        }

        Repeater {
          model: root.service ? root.service.rooms : []

          delegate: Row {
            id: roomRow
            required property var modelData
            width: roomMixer.width
            spacing: Style.space(6)

            Text {
              width: Style.space(100)
              anchors.verticalCenter: parent.verticalCenter
              text: String(roomRow.modelData.name || "Sonos")
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
                && Number(roomRow.modelData.volume || 0) > 0
              onClicked: root.service.adjustRoomVolume(
                String(roomRow.modelData.uid), -Math.max(1, root.volumeStep))
            }

            PanelSlider {
              bar: root.bar
              anchors.verticalCenter: parent.verticalCenter
              width: Math.max(Style.space(70), roomMixer.width - Style.space(228))
              minimum: 0
              maximum: 100
              step: Math.max(1, root.volumeStep)
              integer: true
              value: Number(roomRow.modelData.volume || 0)
              enabled: root.service && !root.service.actionBusy
              onReleased: function(value) {
                root.service.setRoomVolume(String(roomRow.modelData.uid), value)
              }
            }

            Button {
              anchors.verticalCenter: parent.verticalCenter
              text: "+"
              foreground: root.foreground
              focusable: true
              enabled: root.service && !root.service.actionBusy
                && Number(roomRow.modelData.volume || 0) < 100
              onClicked: root.service.adjustRoomVolume(
                String(roomRow.modelData.uid), Math.max(1, root.volumeStep))
            }

            Button {
              anchors.verticalCenter: parent.verticalCenter
              iconText: roomRow.modelData.mute ? "󰝟" : "󰓄"
              tooltipText: roomRow.modelData.mute ? "Unmute room" : "Mute room"
              foreground: root.foreground
              focusable: true
              onClicked: root.service.setRoomMute(
                String(roomRow.modelData.uid), !roomRow.modelData.mute)
            }
          }
        }
      }

      PanelSeparator { foreground: root.foreground }

      Column {
        width: parent.width
        spacing: Style.space(7)

        Item {
          width: parent.width
          implicitHeight: Math.max(groupHeader.implicitHeight, everywhereButton.implicitHeight)

          PanelSectionHeader {
            id: groupHeader
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            text: "GROUP SETTINGS"
            foreground: root.foreground
            fontFamily: root.fontFamily
          }

          Button {
            id: everywhereButton
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            text: "Everywhere"
            iconText: "󰓅"
            foreground: root.foreground
            bordered: true
            enabled: !root.groupingApplying
            focusable: true
            onClicked: root.stageEverywhere()
          }
        }

        Text {
          width: parent.width
          text: "Stage the rooms first, then Apply once. Nothing changes while you are choosing."
          color: Qt.darker(root.foreground, 1.5)
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          wrapMode: Text.WordWrap
        }

        Flow {
          width: parent.width
          spacing: Style.space(5)

          Repeater {
            model: root.service ? root.service.rooms : []

            delegate: Button {
              required property var modelData
              text: String(modelData.name || "Sonos")
              foreground: root.foreground
              selected: root.roomStaged(String(modelData.uid))
              focusable: true
              enabled: !root.groupingApplying
              onClicked: root.toggleStagedRoom(String(modelData.uid))
            }
          }
        }

        Row {
          width: parent.width
          spacing: Style.space(6)

          Button {
            text: "Cancel"
            foreground: root.foreground
            bordered: true
            focusable: true
            enabled: root.groupingDirty && !root.groupingApplying
            onClicked: root.resetStagedRooms()
          }

          Button {
            text: root.groupingApplying ? "Applying…" : "Apply"
            iconText: "󰄬"
            foreground: root.foreground
            bordered: true
            focusable: true
            active: root.groupingDirty
            enabled: root.groupingDirty && root.stagedRoomUids.length > 0
              && !root.groupingApplying
            onClicked: root.applyStagedRooms()
          }
        }
      }
    }
  }
}
