import QtQuick
import QtTest
import "."

Item {
  width: 600
  height: 500

  property var moves: []

  QtObject {
    id: fakeService
    property bool actionBusy: false
    property bool contentLoading: false
    property string contentKind: "queue"
    property int contentTotal: 3
    property var contentItems: [
      { index: 0, id: "Q:0", title: "First", playable: true },
      { index: 1, id: "Q:1", title: "Second", playable: true },
      { index: 2, id: "Q:2", title: "Third", playable: true }
    ]
    function hasCapability(name) { return name === "queue.item.move" }
    function loadContent(_kind, _term) {}
    function moveQueueItem(index, itemId, targetIndex, targetItemId) {
      moves = moves.concat([{
        index: index, itemId: itemId,
        targetIndex: targetIndex, targetItemId: targetItemId
      }])
    }
  }

  SonarchyQueuePage {
    id: page
    anchors.fill: parent
    service: fakeService
    device: ({ uid: "R1" })
    showArtwork: false
  }

  TestCase {
    name: "SonarchyQueueReorder"
    when: windowShown

    function init() {
      moves = []
      wait(0)
    }

    function test_move_by_uses_authoritative_adjacent_identity() {
      page.moveBy(fakeService.contentItems[1], -1)
      compare(moves.length, 1)
      compare(moves[0].index, 1)
      compare(moves[0].itemId, "Q:1")
      compare(moves[0].targetIndex, 0)
      compare(moves[0].targetItemId, "Q:0")
    }

    function test_keyboard_shortcut_moves_the_focused_row() {
      var down = findChild(page, "queueMoveDown:1")
      verify(down !== null)
      down.forceActiveFocus()
      verify(down.activeFocus)
      keyClick(Qt.Key_Down, Qt.AltModifier)
      compare(moves.length, 1)
      compare(moves[0].itemId, "Q:1")
      compare(moves[0].targetItemId, "Q:2")
    }

    function test_drag_handle_drops_on_another_row() {
      var handle = findChild(page, "queueDragHandle:0")
      var target = findChild(page, "queueCard:2")
      verify(handle !== null)
      verify(target !== null)
      verify(handle.enabled)
      mousePress(handle, handle.width / 2, handle.height / 2, Qt.LeftButton)
      verify(handle.pressed)
      mouseMove(target, target.width / 2, target.height / 2, 30)
      verify(handle.dragging)
      mouseRelease(target, target.width / 2, target.height / 2, Qt.LeftButton)
      verify(!handle.pressed)
      tryCompare(moves, "length", 1)
      compare(moves[0].itemId, "Q:0")
      compare(moves[0].targetItemId, "Q:2")
    }
  }
}
