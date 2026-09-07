import QtQuick

// Proposal only: actual named QML type, not a claim about the installed API.
QtObject {
  id: root

  required property QtObject inputHost
  required property string inputFontFamily
  required property color inputForeground
  required property color inputBarForeground
  required property bool inputVertical
  required property int inputBarSize

  // Only this capability is deliberately dynamic. The owner supplies a pure
  // lookup, never service creation or an arbitrary host-operation dispatcher.
  property var serviceLookup: null

  readonly property QtObject host: root.inputHost
  readonly property string fontFamily: root.inputFontFamily
  readonly property color foreground: root.inputForeground
  readonly property color barForeground: root.inputBarForeground
  readonly property bool vertical: root.inputVertical
  readonly property int barSize: root.inputBarSize

  function serviceFor(pluginId: string): QtObject {
    if (!root.host || typeof root.serviceLookup !== "function") return null
    try {
      const value = root.serviceLookup(pluginId)
      return value instanceof QtObject ? value : null
    } catch (error) {
      return null
    }
  }
}
