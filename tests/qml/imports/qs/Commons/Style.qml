pragma Singleton
import QtQuick

QtObject {
  property QtObject spacing: QtObject {
    property real controlHeight: 40
    property real md: 8
  }

  function space(value) {
    return value
  }
}
