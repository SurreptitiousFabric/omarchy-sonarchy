pragma Singleton
import QtQuick

QtObject {
  property color accent: "#ffffff"
  property color foreground: "#ffffff"
  property color background: "#000000"
  property color urgent: "#ff5555"
  property QtObject popups: QtObject { property color text: "#ffffff" }
}
