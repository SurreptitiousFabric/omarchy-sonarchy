import QtQuick

QtObject {
  id: root

  // The legacy host remains generic. This does not cast it to the built-in Bar.
  property QtObject bar: null
  property BarHostContext hostContext: null
  property string moduleName: "io.github.surreptitiousfabric.sonarchy"
  required property string fallbackFontFamily
  required property color fallbackForeground
  required property color fallbackBarForeground
  required property int fallbackBarSize

  // During replacement, never use a context belonging to the previous host.
  readonly property BarHostContext activeContext: root.bar && root.hostContext
    && root.hostContext.host === root.bar ? root.hostContext : null

  readonly property string fontFamily: root.activeContext
    ? root.activeContext.fontFamily : root.fallbackFontFamily
  readonly property color foreground: root.activeContext
    ? root.activeContext.foreground : root.fallbackForeground
  readonly property color barForeground: root.activeContext
    ? root.activeContext.barForeground : root.fallbackBarForeground
  readonly property bool vertical: root.activeContext ? root.activeContext.vertical : false
  readonly property int barSize: root.activeContext
    ? root.activeContext.barSize : root.fallbackBarSize
  readonly property QtObject service: root.activeContext
    ? root.activeContext.serviceFor(root.moduleName) : null
}
