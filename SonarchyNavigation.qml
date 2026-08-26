import QtQuick
import qs.Commons
import qs.Ui

BorderSurface {
  id: root

  property var options: []
  property string value: ""
  property color foreground: Color.popups.text
  property color accent: Color.accent
  property string fontFamily: Style.font.family
  property bool focusable: true
  property int cursorIndex: indexOfValue(value)

  signal changed(string value)
  signal clicked()

  function optionValue(option) {
    return option && typeof option === "object" ? String(option.value) : String(option)
  }

  function optionLabel(option) {
    return option && typeof option === "object" ? String(option.label) : String(option)
  }

  function optionIcon(option) {
    return option && typeof option === "object" ? String(option.icon || "") : ""
  }

  function indexOfValue(candidate) {
    for (var i = 0; i < options.length; i++) {
      if (optionValue(options[i]) === candidate) return i
    }
    return options.length > 0 ? 0 : -1
  }

  function moveCursor(delta) {
    if (options.length === 0) return
    var start = cursorIndex >= 0 ? cursorIndex : indexOfValue(value)
    cursorIndex = Math.max(0, Math.min(options.length - 1, start + delta))
  }

  function activateCursor() {
    if (cursorIndex < 0 || cursorIndex >= options.length) return
    var nextValue = optionValue(options[cursorIndex])
    changed(nextValue)
  }

  onClicked: activateCursor()
  onValueChanged: cursorIndex = indexOfValue(value)
  onActiveFocusChanged: {
    if (activeFocus) cursorIndex = indexOfValue(value)
  }

  activeFocusOnTab: focusable
  implicitHeight: Style.space(52)
  radius: Style.cornerRadius
  color: Style.normalFillFor(foreground, accent)
  borderSpec: Border.none()

  Keys.onLeftPressed: moveCursor(-1)
  Keys.onRightPressed: moveCursor(1)
  Keys.onReturnPressed: activateCursor()
  Keys.onEnterPressed: activateCursor()
  Keys.onSpacePressed: activateCursor()

  Row {
    id: navigationRow
    anchors.fill: parent
    anchors.margins: Style.space(3)
    spacing: Style.space(2)

    Repeater {
      model: root.options

      delegate: BorderSurface {
        id: navigationItem

        required property var modelData
        required property int index
        readonly property bool current: root.optionValue(modelData) === root.value
        readonly property bool cursor: root.activeFocus && root.cursorIndex === index

        width: Math.max(1, (navigationRow.width
          - navigationRow.spacing * Math.max(0, root.options.length - 1))
          / Math.max(1, root.options.length))
        height: navigationRow.height
        radius: Math.max(2, Style.cornerRadius - Style.space(2))
        color: cursor ? Style.focusFillFor(root.foreground, root.accent)
          : (current ? Style.selectedFillFor(root.foreground, root.accent) : "transparent")
        borderSpec: cursor
          ? Border.controlSpec("focus", root.foreground, root.accent)
          : Border.none()

        Behavior on color { ColorAnimation { duration: 120 } }

        Column {
          anchors.centerIn: parent
          spacing: Style.space(1)

          OpticalGlyph {
            anchors.horizontalCenter: parent.horizontalCenter
            width: Style.space(20)
            height: Style.space(20)
            text: root.optionIcon(navigationItem.modelData)
            color: navigationItem.current
              ? Style.selectedStateColor(root.foreground, root.accent)
              : root.foreground
            fontFamily: root.fontFamily
            fontSize: Style.font.icon
          }

          Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: root.optionLabel(navigationItem.modelData)
            color: navigationItem.current
              ? Style.selectedStateColor(root.foreground, root.accent)
              : Qt.darker(root.foreground, 1.28)
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            font.bold: navigationItem.current
          }
        }

        Rectangle {
          anchors.bottom: parent.bottom
          anchors.horizontalCenter: parent.horizontalCenter
          width: navigationItem.current ? Style.space(18) : 0
          height: Style.space(2)
          radius: height / 2
          color: Style.selectedStateColor(root.foreground, root.accent)

          Behavior on width {
            NumberAnimation { duration: 140; easing.type: Easing.OutCubic }
          }
        }

        MouseArea {
          anchors.fill: parent
          cursorShape: Qt.PointingHandCursor
          onClicked: {
            root.cursorIndex = navigationItem.index
            root.activateCursor()
            root.forceActiveFocus()
          }
        }
      }
    }
  }
}
