import QtQuick
import QtTest
import "."

Item {
  id: host
  width: 600
  height: 500

  property var moves: []
  property var actions: []

  QtObject {
    id: fakeService
    property bool actionBusy: false
    property bool contentLoading: false
    property bool capabilities: true
    property string contentKind: "queue"
    property int contentTotal: 3
    property var contentItems: [
      { index: 0, id: "Q:0", title: "First", playable: true },
      { index: 1, id: "Q:1", title: "Second", playable: true },
      { index: 2, id: "Q:2", title: "Third", playable: true }
    ]
    function hasCapability(name) { return capabilities }
    function loadContent(_kind, _term) {}
    function playContent(item) { host.actions = host.actions.concat([{ action: "play", item: item }]) }
    function removeQueueItem(index, itemId) {
      host.actions = host.actions.concat([{ action: "remove", index: index, itemId: itemId }])
    }
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
      actions = []
      page.confirmation = ""
      fakeService.actionBusy = false
      fakeService.capabilities = true
      fakeService.contentItems = [
        { index: 0, id: "Q:0", title: "First", playable: true },
        { index: 1, id: "Q:1", title: "Second", playable: true },
        { index: 2, id: "Q:2", title: "Third", playable: true }
      ]
      wait(0)
    }

    function actionButton(owner, tooltip) {
      for (var i = 0; i < owner.children.length; i++) {
        var child = owner.children[i]
        if (child.tooltipText === tooltip) return child
        var nested = actionButton(child, tooltip)
        if (nested) return nested
      }
      return null
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

    function test_replaced_model_uses_new_identities_for_shortcut_and_actions() {
      fakeService.contentItems = [
        { index: 0, id: "NEW:0", title: "New first", playable: true },
        { index: 1, id: "NEW:1", title: "New second", playable: true }
      ]
      wait(0)
      var up = findChild(page, "queueMoveUp:1")
      verify(up !== null)
      up.forceActiveFocus()
      verify(up.activeFocus)
      keyClick(Qt.Key_Up, Qt.AltModifier)
      compare(moves.length, 1)
      compare(moves[0].itemId, "NEW:1")
      compare(moves[0].targetItemId, "NEW:0")
      var row = findChild(page, "queueCard:1")
      compare(row.modelData.id, "NEW:1")
      var play = actionButton(row, "Play now")
      verify(play !== null)
      play.clicked()
      compare(actions[0].item, fakeService.contentItems[1])
      var remove = actionButton(row, "Remove")
      verify(remove !== null)
      remove.clicked()
      compare(actions.length, 1)
      compare(page.confirmation, row.rowKey)
      remove.clicked()
      compare(actions[1].action, "remove")
      compare(actions[1].index, 1)
      compare(actions[1].itemId, "NEW:1")
      fakeService.contentItems = []
      wait(0)
      compare(findChild(page, "queueCard:1"), null)
    }

    function test_outside_or_same_row_drop_and_boundary_moves_do_nothing() {
      page.moveBy(fakeService.contentItems[0], -1)
      page.moveBy(fakeService.contentItems[2], 1)
      page.dropItemAt(fakeService.contentItems[0], -1000)
      var row = findChild(page, "queueCard:0")
      var top = row.mapToItem(row.parent.parent, 0, 0).y
      page.dropItemAt(fakeService.contentItems[0], top + row.height / 2)
      compare(moves.length, 0)
    }

    function test_busy_and_missing_capability_disable_reorder_controls() {
      var down = findChild(page, "queueMoveDown:1")
      var handle = findChild(page, "queueDragHandle:1")
      verify(down.enabled && handle.enabled)
      fakeService.actionBusy = true
      verify(!down.enabled && !handle.enabled)
      mouseClick(down)
      compare(moves.length, 0)
      fakeService.actionBusy = false
      fakeService.capabilities = false
      verify(!down.enabled && !handle.enabled)
      mouseClick(down)
      compare(moves.length, 0)
    }
  }
}
