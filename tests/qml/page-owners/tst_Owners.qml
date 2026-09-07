import QtQuick
import QtTest
import "."

Item {
  id: host
  width: 600
  height: 650
  PageService { id: firstService }
  PageService { id: secondService }

  TestCase {
    name: "RemainingPageOwnerBindings"
    when: windowShown

    function init() {
      firstService.calls = []
      secondService.calls = []
      secondService.capabilities = true
      secondService.actionBusy = false
      firstService.capabilities = true
      firstService.actionBusy = false
      firstService.soundDetails = ({ bass: 2, treble: -2 })
      secondService.soundDetails = ({ bass: 10, treble: -10 })
    }

    function make(name, models) {
      var component = Qt.createComponent(name + "Owner.qml")
      compare(component.status, Component.Ready, component.errorString())
      var owner = createTemporaryObject(component, host, { service: firstService, models: models || [] })
      verify(owner !== null)
      return owner
    }

    function room(uid) { return { uid: uid, name: uid, room_volume: 20, room_muted: false } }
    function row(owner, repeater, index) { return findChild(owner, "rows" + repeater).itemAt(index) }
    function find(owner, predicate) {
      for (var i = 0; i < owner.children.length; i++) {
        var child = owner.children[i]
        if (predicate(child)) return child
        var nested = find(child, predicate)
        if (nested) return nested
      }
      return null
    }
    function button(owner, text) {
      var control = find(owner, function(child) { return child.text === text && child.clicked !== undefined })
      verify(control !== null)
      return control
    }
    function call(service, index, action, args) {
      compare(service.calls[index].action, action)
      compare(JSON.stringify(service.calls[index].args), JSON.stringify(args))
    }

    function test_now_room_volume_owner_and_model_replacement() {
      var owner = make("Now", [[room("room-a"), room("room-b")]])
      var target = row(owner, 0, 1)
      compare(target.room.uid, "room-b")
      button(target, "+").forceActiveFocus()
      keyClick(Qt.Key_Return)
      call(firstService, 0, "adjust", ["room-b", 2])
      owner.foreground = "#123456"
      owner.fontFamily = "sans-serif"
      owner.volumeStep = 5
      compare(target.foreground, owner.foreground)
      compare(target.fontFamily, "sans-serif")
      owner.service = secondService
      owner.models = [[room("room-new")]]
      target = row(owner, 0, 0)
      compare(target.service, secondService)
      button(target, "−").clicked()
      call(secondService, 0, "adjust", ["room-new", -5])
      compare(firstService.calls.length, 1)
      owner.models = [[]]
      compare(findChild(owner, "rows0").count, 0)
    }

    function test_rooms_sessions_move_mixer_and_staging_keep_roles() {
      var rooms = [room("room-a"), room("room-b"), room("room-c")]
      var owner = make("Rooms", [[{ uid: "group-a", label: "A", playbackState: "STOPPED" },
        { uid: "group-b", label: "B", playbackState: "PLAYING" }], rooms, rooms, rooms])
      verify(row(owner, 0, 0).selected)
      verify(!row(owner, 0, 0).enabled)
      var session = row(owner, 0, 1)
      compare(session.text, "B  ·  Playing")
      session.forceActiveFocus()
      keyClick(Qt.Key_Return)
      call(firstService, 0, "session", ["group-b"])
      verify(!row(owner, 1, 0).enabled)
      verify(!row(owner, 1, 2).enabled)
      row(owner, 1, 1).clicked()
      call(firstService, 1, "move", ["room-b"])
      compare(row(owner, 2, 1).room.uid, "room-b")
      row(owner, 3, 1).clicked()
      compare(JSON.stringify(owner.stagedRoomUids), '["room-a","room-b"]')
      verify(owner.groupingDirty)
      compare(firstService.calls.length, 2)
      owner.groupingApplying = true
      verify(!row(owner, 3, 1).enabled)
      owner.service = secondService
      row(owner, 1, 1).clicked()
      call(secondService, 0, "move", ["room-b"])
      owner.foreground = "#654321"
      compare(session.foreground, owner.foreground)
    }

    function test_system_alarm_identity_edit_and_confirmation() {
      var alarms = [{ id: "a", enabled: true, time: "08:00", room: "A", recurrence: "DAILY", volume: 10, program: "Chime" },
        { id: "b", enabled: false, time: "09:00", room: "B", recurrence: "ONCE", volume: 20, program: "Chime" }]
      var owner = make("System", [alarms])
      var first = row(owner, 0, 0)
      button(first, "Disable").clicked()
      call(firstService, 0, "alarm-toggle", ["a", false])
      button(row(owner, 0, 1), "Edit").clicked()
      compare(owner.edited, alarms[1])
      var remove = find(first, function(child) { return child.tooltipText === "Delete alarm" })
      verify(remove !== null)
      remove.clicked()
      compare(firstService.calls.length, 1)
      compare(owner.confirmation, "alarm-delete:a")
      remove.clicked()
      call(firstService, 1, "alarm-delete", ["a"])
      owner.service = secondService
      owner.models = [[alarms[1]]]
      button(row(owner, 0, 0), "Enable").clicked()
      call(secondService, 0, "alarm-toggle", ["b", true])
    }

    function test_sound_inline_instances_bounds_and_live_owner() {
      var owner = make("Sound")
      var bass = find(owner, function(child) { return child.title === "BASS" })
      var treble = find(owner, function(child) { return child.title === "TREBLE" })
      verify(bass !== null && treble !== null)
      button(bass, "+").forceActiveFocus()
      keyClick(Qt.Key_Return)
      call(firstService, 0, "sound", ["bass", 3])
      button(treble, "−").clicked()
      call(firstService, 1, "sound", ["treble", -3])
      owner.service = secondService
      verify(!button(bass, "+").enabled)
      verify(!button(treble, "−").enabled)
      button(bass, "−").clicked()
      call(secondService, 0, "sound", ["bass", 9])
      var slider = find(bass, function(child) { return child.scrollTarget !== undefined })
      verify(slider !== null)
      slider.released(4.6)
      call(secondService, 1, "sound", ["bass", 5])
      secondService.actionBusy = true
      verify(!button(bass, "−").enabled && !slider.enabled)
      secondService.actionBusy = false
      secondService.capabilities = false
      verify(!button(bass, "−").enabled && !slider.enabled)
      compare(firstService.calls.length, 2)
    }
  }
}
