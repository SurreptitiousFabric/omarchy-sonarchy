import QtQuick

// Visual-only boundary for browse-row tests; not dropdown acceptance.
Item {
  property string label: ""
  property string value: ""
  property var options: []
  property color foreground: "white"
  property string fontFamily: "monospace"
  property bool hasCursor: false
  property bool popupOpen: false
  signal changed(string value)
  implicitHeight: 40
  function toggle() { popupOpen = !popupOpen }
}
