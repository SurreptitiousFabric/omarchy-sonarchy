import QtQuick
import QtTest
import "."

Item {
  width: 400
  height: 300

  property int movedCount: 0
  property int releasedCount: 0
  property real lastReleasedValue: -1

  Flickable {
    id: page
    anchors.fill: parent
    contentWidth: width
    contentHeight: 900
    contentY: 300

    SonarchySlider {
      id: slider
      x: 20
      y: 100
      width: 300
      height: 50
      minimum: 0
      maximum: 100
      value: 50
      scrollTarget: page
      onMoved: movedCount++
      onReleased: function(nextValue) {
        releasedCount++
        lastReleasedValue = nextValue
      }
    }
  }

  TestCase {
    name: "SonarchySliderWheel"
    when: windowShown

    function init() {
      slider.value = 50
      page.contentY = 300
      movedCount = 0
      releasedCount = 0
      lastReleasedValue = -1
    }

    function test_wheel_scrolls_page_without_mutating_slider() {
      mouseWheel(slider, slider.width / 2, slider.height / 2, 0, -120)
      compare(slider.value, 50)
      compare(slider.liveValue, 50)
      compare(movedCount, 0)
      compare(releasedCount, 0)
      compare(page.contentY, 360)
    }

    function test_pointer_drag_still_uses_native_slider() {
      mousePress(slider, 10, slider.height / 2, Qt.LeftButton)
      mouseMove(slider, slider.width - 10, slider.height / 2, 20)
      mouseRelease(slider, slider.width - 10, slider.height / 2, Qt.LeftButton)
      verify(movedCount > 0)
      compare(releasedCount, 1)
      verify(lastReleasedValue > 90)
    }
  }
}
