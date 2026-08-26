import QtQuick
import qs.Ui

PanelSlider {
  id: root

  // Omarchy's stock PanelSlider maps the wheel to value changes. Inside a
  // scrolling settings page that makes an ordinary vertical scroll mutate the
  // speaker as soon as the pointer crosses a slider. Keep intentional pointer
  // dragging, but route wheel input to the owning Flickable instead.
  property var scrollTarget: null

  // PanelSlider uses a legacy MouseArea for both dragging and wheel changes.
  // A WheelHandler cannot block that MouseArea reliably, so place a wheel-only
  // MouseArea above it. With no accepted buttons, presses still reach the
  // native slider and intentional pointer dragging remains unchanged.
  MouseArea {
    anchors.fill: parent
    acceptedButtons: Qt.NoButton

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
