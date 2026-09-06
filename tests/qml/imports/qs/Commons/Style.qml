pragma Singleton
import QtQuick

QtObject {
  property real cornerRadius: 4
  property real normalBorderWidth: 1
  property QtObject font: QtObject {
    property string family: "monospace"
    property real caption: 11
    property real bodySmall: 12
    property real body: 14
    property real iconSmall: 14
    property real icon: 18
    property real iconLarge: 20
  }
  property QtObject spacing: QtObject {
    property real controlHeight: 40
    property real md: 8
    property real hairline: 1
    property real labelGap: 4
  }

  function space(value) {
    return value
  }

  function selectedFillFor(_foreground, _accent) {
    return "#202020"
  }

  function normalFillFor(_foreground, _accent) { return "#101010" }
  function focusFillFor(_foreground, _accent) { return "#303030" }
  function selectedStateColor(foreground, _accent) { return foreground }
}
