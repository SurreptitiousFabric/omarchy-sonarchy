pragma Singleton
import QtQuick

QtObject {
  function none() { return {} }
  function flat(color, width) {
    return { color: color, width: width }
  }
}
