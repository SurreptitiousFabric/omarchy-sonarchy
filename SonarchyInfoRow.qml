import QtQuick
import qs.Commons

Text {
  required property string label
  required property string value
  property color foreground: Color.popups.text
  property string fontFamily: Style.font.family

  width: parent ? parent.width : implicitWidth
  text: label + ": " + value
  color: Qt.darker(foreground, 1.35)
  font.family: fontFamily
  font.pixelSize: Style.font.bodySmall
  wrapMode: Text.WordWrap
}
