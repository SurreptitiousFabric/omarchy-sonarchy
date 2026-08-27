import QtQuick
import qs.Commons

FocusScope {
  id: root
  property string text: ""
  property string iconText: ""
  property string tooltipText: ""
  property color foreground: Color.foreground
  property bool focusable: false
  property bool selected: false
  property bool bordered: false
  property bool iconSpinning: false
  signal clicked()
  activeFocusOnTab: focusable
  implicitWidth: 34
  implicitHeight: 32
  Keys.onReturnPressed: if (focusable && enabled) clicked()
  Keys.onEnterPressed: if (focusable && enabled) clicked()
  Keys.onSpacePressed: if (focusable && enabled) clicked()
  MouseArea {
    anchors.fill: parent
    enabled: root.enabled
    onClicked: root.clicked()
  }
}
