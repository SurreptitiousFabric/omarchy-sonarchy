import QtQuick
import QtTest
import "."

Item {
  id: host
  width: 600
  height: 200
  property var selections: []

  SonarchyNavigation {
    id: navigation
    width: 480
    onChanged: function(value) { host.selections = host.selections.concat([value]) }
  }

  TestCase {
    name: "SonarchyNavigationBindings"
    when: windowShown

    function delegates() {
      var items = []
      var children = navigation.children[0].children
      for (var i = 0; i < children.length; i++) {
        if (children[i].modelData !== undefined) items.push(children[i])
      }
      return items
    }

    function init() {
      host.selections = []
      navigation.width = 480
      navigation.options = [
        { value: "now", label: "Now", icon: "A" },
        { value: "browse", label: "Browse", icon: "B" },
        { value: "queue", label: "Queue", icon: "C" }
      ]
      navigation.value = "now"
      navigation.forceActiveFocus()
      wait(0)
    }

    function test_keyboard_cursor_and_activation_use_required_model_roles() {
      compare(delegates().length, 3)
      compare(delegates()[1].modelData.value, "browse")
      compare(delegates()[1].index, 1)
      keyClick(Qt.Key_Right)
      compare(navigation.cursorIndex, 1)
      compare(host.selections.length, 0)
      keyClick(Qt.Key_Return)
      compare(host.selections.length, 1)
      compare(host.selections[0], "browse")
      keyClick(Qt.Key_Left)
      keyClick(Qt.Key_Left)
      compare(navigation.cursorIndex, 0)
    }

    function test_pointer_selection_keeps_owner_and_index() {
      var target = delegates()[2]
      mouseClick(target, target.width / 2, target.height / 2)
      compare(navigation.cursorIndex, 2)
      compare(host.selections.length, 1)
      compare(host.selections[0], "queue")
      verify(navigation.activeFocus)
    }

    function test_model_replacement_with_new_selection_and_resize() {
      navigation.options = [{ value: "rooms", label: "Rooms" }, { value: "now", label: "Now" }]
      navigation.value = "rooms"
      wait(0)
      compare(delegates().length, 2)
      compare(navigation.cursorIndex, 0)
      verify(delegates()[0].current)
      var originalWidth = delegates()[0].width
      navigation.width = 600
      wait(0)
      verify(delegates()[0].width > originalWidth)
      keyClick(Qt.Key_Space)
      compare(host.selections[0], "rooms")
    }

    function test_empty_model_does_not_emit_selection() {
      navigation.options = []
      navigation.value = "missing"
      wait(0)
      compare(delegates().length, 0)
      keyClick(Qt.Key_Right)
      keyClick(Qt.Key_Return)
      compare(host.selections.length, 0)
    }
  }
}
