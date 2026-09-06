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
      navigation.cursorIndex = 0
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

    function test_unchanged_selection_reorder_resynchronizes_cursor() {
      navigation.options = [{ value: "rooms", label: "Rooms" }, { value: "now", label: "Now" }]
      wait(0)
      compare(navigation.value, "now")
      compare(navigation.cursorIndex, 1)
      verify(delegates()[1].current)
      compare(host.selections.length, 0)
      keyClick(Qt.Key_Return)
      compare(host.selections.length, 1)
      compare(host.selections[0], "now")
      keyClick(Qt.Key_Space)
      compare(host.selections.length, 2)
      compare(host.selections[1], "now")
    }

    function test_removed_selection_falls_back_without_emitting_or_changing_value() {
      keyClick(Qt.Key_Right)
      keyClick(Qt.Key_Right)
      navigation.options = ["rooms"]
      wait(0)
      compare(navigation.value, "now")
      compare(navigation.cursorIndex, 0)
      compare(host.selections.length, 0)
      keyClick(Qt.Key_Return)
      compare(host.selections.length, 1)
      compare(host.selections[0], "rooms")
    }

    function test_empty_then_repopulated_options_resynchronizes_cursor() {
      keyClick(Qt.Key_Right)
      navigation.options = []
      wait(0)
      compare(navigation.cursorIndex, -1)
      keyClick(Qt.Key_Return)
      compare(host.selections.length, 0)
      navigation.options = ["rooms", "now"]
      wait(0)
      compare(navigation.cursorIndex, 1)
      keyClick(Qt.Key_Space)
      compare(host.selections.length, 1)
      compare(host.selections[0], "now")
    }
  }
}
