pragma Singleton
import QtQuick

QtObject {
  function none() { return {} }
  function controlSpec(_state, _foreground, _accent) { return {} }
  function flat(color, width) {
    return { color: color, width: width }
  }
}
