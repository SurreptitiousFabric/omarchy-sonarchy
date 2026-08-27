pragma Singleton
import QtQuick

QtObject {
  function alpha(color, amount) { return Qt.rgba(color.r, color.g, color.b, amount) }
}
