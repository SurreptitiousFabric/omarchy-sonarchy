import QtQuick
import qs.Ui

PanelSlider {
  id: root

  // Omarchy's stock PanelSlider maps the wheel to value changes. Inside a
  // scrolling settings page that makes an ordinary vertical scroll mutate the
  // speaker as soon as the pointer crosses a slider. Keep intentional pointer
  // dragging, but route wheel input to the owning Flickable instead.
  property var scrollTarget: null

  WheelHandler {
    target: null
    blocking: true

    onWheel: function(event) {
      event.accepted = true
      var view = root.scrollTarget
      if (!view) return

      var pixelDelta = Number(event.pixelDelta.y || 0)
      var angleDelta = Number(event.angleDelta.y || 0)
      var delta = pixelDelta !== 0 ? pixelDelta : angleDelta / 2
      var maximumY = Math.max(0, Number(view.contentHeight) - Number(view.height))
      view.contentY = Math.max(0, Math.min(maximumY, Number(view.contentY) - delta))
    }
  }
}
