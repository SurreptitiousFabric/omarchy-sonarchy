import QtQuick
import QtQuick.Controls as QQC
import qs.Commons
import qs.Ui

Item {
  id: root

  property var service: null
  property var device: null
  property color foreground: Color.popups.text
  property string fontFamily: Style.font.family
  property bool showArtwork: true
  property string confirmation: ""

  readonly property bool editing: false

  onVisibleChanged: if (visible) refresh()
  onDeviceChanged: if (visible) refresh()

  function refresh() {
    if (!service || !device) return
    service.loadContent("queue", "")
  }

  function ensureVisible(item) {
    if (!item || !queueFlick.visible) return
    var point = item.mapToItem(queueFlick.contentItem, 0, 0)
    var top = point.y - Style.space(10)
    var bottom = point.y + item.height + Style.space(10)
    if (top < queueFlick.contentY) queueFlick.contentY = Math.max(0, top)
    else if (bottom > queueFlick.contentY + queueFlick.height)
      queueFlick.contentY = Math.min(
        Math.max(0, queueFlick.contentHeight - queueFlick.height),
        bottom - queueFlick.height)
  }

  function arm(key) {
    if (confirmation === key) {
      confirmation = ""
      confirmTimer.stop()
      return true
    }
    confirmation = key
    confirmTimer.restart()
    return false
  }

  function can(operation) {
    return service && service.hasCapability(operation)
  }

  function moveItem(item, target) {
    if (!item || !target || Number(item.index) === Number(target.index)) return
    service.moveQueueItem(
      Number(item.index), String(item.id),
      Number(target.index), String(target.id))
  }

  function moveBy(item, delta) {
    if (!service || !item) return
    var targetIndex = Number(item.index) + Number(delta)
    if (targetIndex < 0 || targetIndex >= service.contentItems.length) return
    moveItem(item, service.contentItems[targetIndex])
  }

  function dropItemAt(item, contentY) {
    for (var index = 0; index < queueRepeater.count; index++) {
      var target = queueRepeater.itemAt(index)
      if (!target || String(target.modelData.id) === String(item.id)) continue
      var targetTop = target.mapToItem(queueColumn, 0, 0).y
      if (contentY >= targetTop && contentY <= targetTop + target.height) {
        moveItem(item, target.modelData)
        return
      }
    }
  }

  Timer {
    id: confirmTimer
    interval: 5000
    repeat: false
    onTriggered: root.confirmation = ""
  }

  Flickable {
    id: queueFlick
    anchors.fill: parent
    contentWidth: width
    contentHeight: queueColumn.implicitHeight
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    flickableDirection: Flickable.VerticalFlick

    QQC.ScrollBar.vertical: QQC.ScrollBar {
      policy: QQC.ScrollBar.AsNeeded
    }

    Column {
      id: queueColumn
      width: queueFlick.width - Style.space(6)
      spacing: Style.space(10)

      Text {
        width: parent.width
        visible: root.confirmation !== ""
        text: "Press the same focused action again to confirm. This expires in 5 seconds."
        color: Color.urgent
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
        font.bold: true
        wrapMode: Text.WordWrap
      }

      Item {
        width: parent.width
        implicitHeight: Math.max(queueHeader.implicitHeight, queueActions.implicitHeight)

        PanelSectionHeader {
          id: queueHeader
          anchors.left: parent.left
          anchors.verticalCenter: parent.verticalCenter
          text: "CURRENT QUEUE"
          foreground: root.foreground
          fontFamily: root.fontFamily
        }

        Row {
          id: queueActions
          anchors.right: parent.right
          anchors.verticalCenter: parent.verticalCenter
          spacing: Style.space(5)

          Text {
            anchors.verticalCenter: parent.verticalCenter
            text: root.service && root.service.contentKind === "queue"
              ? String(root.service.contentTotal || 0) : "…"
            color: Qt.darker(root.foreground, 1.4)
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            font.bold: true
          }

          Button {
            iconText: "󰑐"
            iconSpinning: root.service ? root.service.contentLoading : false
            tooltipText: "Refresh queue"
            foreground: root.foreground
            focusable: true
            enabled: root.service && !root.service.contentLoading
              && root.can("content.browse")
            onClicked: root.refresh()
          }

          Button {
            visible: root.service && root.service.contentKind === "queue"
              && root.service.contentItems.length > 0
            iconText: "󰅖"
            text: root.confirmation === "queue-clear" ? "Confirm clear" : "Clear"
            foreground: root.confirmation === "queue-clear" ? Color.urgent : root.foreground
            bordered: true
            focusable: true
            enabled: root.service && !root.service.actionBusy && root.can("queue.clear")
            onClicked: if (root.arm("queue-clear")) root.service.clearQueue()
          }
        }
      }

      Column {
        width: parent.width
        spacing: Style.space(4)

        Repeater {
          id: queueRepeater
          model: root.service && root.service.contentKind === "queue"
            ? root.service.contentItems : []

          delegate: BorderSurface {
            id: queueCard
            required property var modelData
            objectName: "queueCard:" + String(modelData.index)
            readonly property string rowKey: "queue:" + String(modelData.index)
              + ":" + String(modelData.id)
            readonly property bool rowFocused: moveUpButton.activeFocus
              || moveDownButton.activeFocus || playButton.activeFocus
              || removeButton.activeFocus
            property real restingY: 0
            width: parent.width
            implicitHeight: root.showArtwork ? Style.space(64) : Style.space(52)
            radius: Style.cornerRadius
            color: modelData.current === true
              ? Style.selectedFillFor(root.foreground, Color.accent) : "transparent"
            borderSpec: Border.none()
            z: dragArea.dragging ? 100 : 0

            Shortcut {
              sequence: "Alt+Up"
              enabled: queueCard.rowFocused && moveUpButton.enabled
              onActivated: root.moveBy(modelData, -1)
            }

            Shortcut {
              sequence: "Alt+Down"
              enabled: queueCard.rowFocused && moveDownButton.enabled
              onActivated: root.moveBy(modelData, 1)
            }

            Rectangle {
              anchors.left: parent.left
              anchors.top: parent.top
              anchors.bottom: parent.bottom
              width: Style.space(3)
              color: modelData.current === true ? Color.accent : "transparent"

              Behavior on color { ColorAnimation { duration: 140 } }
            }

            Rectangle {
              anchors.left: root.showArtwork ? queueArtworkSurface.right : parent.left
              anchors.leftMargin: root.showArtwork ? Style.space(9) : Style.space(10)
              anchors.right: parent.right
              anchors.rightMargin: Style.space(8)
              anchors.bottom: parent.bottom
              height: Style.spacing.hairline
              color: Util.alpha(root.foreground, 0.08)
            }

            BorderSurface {
              id: queueArtworkSurface
              anchors.left: parent.left
              anchors.leftMargin: Style.space(8)
              anchors.verticalCenter: parent.verticalCenter
              width: Style.space(46)
              height: Style.space(46)
              radius: Style.spacing.labelGap
              color: Style.selectedFillFor(root.foreground, Color.accent)
              borderSpec: Border.flat(Util.alpha(root.foreground, 0.1),
                Math.max(1, Style.normalBorderWidth))
              clip: true
              visible: root.showArtwork

              Image {
                id: queueArtwork
                anchors.fill: parent
                source: String(modelData.album_art || "")
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                cache: true
                opacity: status === Image.Ready ? 1.0 : 0.0

                Behavior on opacity {
                  NumberAnimation { duration: 160; easing.type: Easing.OutCubic }
                }
              }

              Text {
                anchors.centerIn: parent
                visible: queueArtwork.status !== Image.Ready
                text: "󰎇"
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.iconLarge
                opacity: 0.55
              }
            }

            Row {
              id: queueRowActions
              anchors.right: parent.right
              anchors.rightMargin: queueCard.borderRight + Style.space(6)
              anchors.verticalCenter: parent.verticalCenter
              spacing: Style.space(4)

              Item {
                width: Style.space(24)
                height: Style.space(32)

                Text {
                  anchors.centerIn: parent
                  text: "󰆾"
                  color: root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.iconSmall
                  opacity: dragArea.enabled ? 0.65 : 0.3
                }

                MouseArea {
                  id: dragArea
                  objectName: "queueDragHandle:" + String(modelData.index)
                  property bool dragging: false
                  property real pressContentY: 0
                  property real currentContentY: 0
                  anchors.fill: parent
                  preventStealing: true
                  enabled: root.service && !root.service.actionBusy
                    && root.can("queue.item.move")
                  cursorShape: dragging ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                  onPressed: function(mouse) {
                    queueCard.restingY = queueCard.y
                    pressContentY = mapToItem(queueColumn, mouse.x, mouse.y).y
                    currentContentY = pressContentY
                    root.confirmation = ""
                  }
                  onPositionChanged: function(mouse) {
                    if (!pressed) return
                    var contentY = mapToItem(queueColumn, mouse.x, mouse.y).y
                    currentContentY = contentY
                    var delta = contentY - pressContentY
                    if (!dragging && Math.abs(delta) >= Style.space(4)) dragging = true
                    if (dragging) queueCard.y = queueCard.restingY + delta
                  }
                  onReleased: {
                    if (dragging)
                      root.dropItemAt(queueCard.modelData, currentContentY)
                    dragging = false
                    queueCard.y = queueCard.restingY
                  }
                  onCanceled: {
                    dragging = false
                    queueCard.y = queueCard.restingY
                  }
                }
              }

              Button {
                id: moveUpButton
                objectName: "queueMoveUp:" + String(modelData.index)
                iconText: "󰁝"
                tooltipText: "Move up (Alt+Up)"
                foreground: root.foreground
                focusable: true
                enabled: root.service && !root.service.actionBusy
                  && root.can("queue.item.move") && Number(modelData.index) > 0
                opacity: enabled ? 1.0 : 0.3
                onClicked: root.moveBy(modelData, -1)
              }

              Button {
                id: moveDownButton
                objectName: "queueMoveDown:" + String(modelData.index)
                iconText: "󰁅"
                tooltipText: "Move down (Alt+Down)"
                foreground: root.foreground
                focusable: true
                enabled: root.service && !root.service.actionBusy
                  && root.can("queue.item.move") && Number(modelData.index) + 1
                    < root.service.contentItems.length
                opacity: enabled ? 1.0 : 0.3
                onClicked: root.moveBy(modelData, 1)
              }

              Button {
                id: playButton
                iconText: "󰐊"
                tooltipText: "Play now"
                foreground: root.foreground
                focusable: true
                selected: modelData.current === true
                enabled: root.service && !root.service.actionBusy
                  && root.can("queue.item.play") && modelData.playable !== false
                opacity: enabled ? 1.0 : 0.35
                onClicked: root.service.playContent(modelData)
              }

              Button {
                id: removeButton
                iconText: "󰅖"
                tooltipText: root.confirmation === queueCard.rowKey
                  ? "Press again to confirm" : "Remove"
                foreground: root.confirmation === queueCard.rowKey
                  ? Color.urgent : root.foreground
                focusable: true
                enabled: root.service && !root.service.actionBusy
                  && root.can("queue.item.remove")
                onClicked: if (root.arm(queueCard.rowKey))
                  root.service.removeQueueItem(
                    Number(modelData.index), String(modelData.id))
              }
            }

            Column {
              anchors.left: root.showArtwork ? queueArtworkSurface.right : parent.left
              anchors.leftMargin: root.showArtwork ? Style.space(9) : Style.space(10)
              anchors.right: queueRowActions.left
              anchors.rightMargin: Style.space(7)
              anchors.verticalCenter: parent.verticalCenter
              spacing: Style.space(2)

              Text {
                width: parent.width
                text: String(modelData.title || "Untitled")
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                font.bold: modelData.current === true
                elide: Text.ElideRight
              }

              Text {
                width: parent.width
                visible: text !== ""
                text: String(modelData.subtitle || "")
                color: Qt.darker(root.foreground, 1.45)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                elide: Text.ElideRight
              }
            }
          }
        }

        Text {
          width: parent.width
          visible: !root.service || (!root.service.contentLoading
            && (root.service.contentKind !== "queue"
                || root.service.contentItems.length === 0))
          text: !root.service ? "Sonos is starting" : "The queue is empty"
          color: Qt.darker(root.foreground, 1.45)
          font.family: root.fontFamily
          font.pixelSize: Style.font.bodySmall
          horizontalAlignment: Text.AlignHCenter
          wrapMode: Text.WordWrap
          topPadding: Style.space(20)
          bottomPadding: Style.space(20)
        }
      }
    }
  }
}
