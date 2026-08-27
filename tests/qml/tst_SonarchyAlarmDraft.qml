import QtQuick
import QtTest

TestCase {
  id: testCase
  name: "SonarchyAlarmDraftBehavior"

  property var subject: null

  QtObject {
    id: fakeService
    property var rooms: []
    property var liveFavorites: ({ items: [] })
  }

  QtObject {
    id: fakeDevice
    property string uid: "R1"
    property int volume: 37
  }

  Component {
    id: subjectComponent
    SonarchyAlarmDraft {
      service: fakeService
      device: fakeDevice
    }
  }

  function init() {
    fakeService.rooms = [
      { uid: "R1", name: "Kitchen", online: true },
      { uid: "R2", name: "Offline", online: false },
      { uid: "R3", name: "Study", online: true }
    ]
    fakeService.liveFavorites = ({ items: [
      { id: "F1", title: "Morning Radio" }
    ] })
    fakeDevice.uid = "R1"
    fakeDevice.volume = 37
    subject = createTemporaryObject(subjectComponent, testCase)
    verify(subject !== null)
  }

  function test_room_options_are_online_authoritative_and_select_the_device() {
    compare(subject.alarmRooms.length, 2)
    compare(subject.alarmRooms[0].value, "R1")
    compare(subject.alarmRooms[1].value, "R3")
    compare(subject.alarmRoomUid, "R1")
    verify(subject.alarmRoomAvailable)

    fakeService.rooms = [{ uid: "R3", name: "Study", online: true }]
    tryCompare(subject, "alarmRoomUid", "R3")
    verify(subject.alarmRoomAvailable)
  }

  function test_edit_projects_every_field_and_exact_save_payload() {
    subject.editAlarm({
      id: "8",
      room_uid: "R3",
      time: "06:45",
      recurrence: "WEEKDAYS",
      duration: 30,
      volume: 28,
      enabled: false,
      include_grouped: true
    })

    compare(subject.alarmProgram, "keep")
    compare(subject.alarmPrograms.length, 3)
    compare(subject.alarmPrograms[0].value, "keep")
    compare(subject.alarmPrograms[2].value, "favorite:F1")
    verify(subject.valid)

    var payload = subject.savePayload()
    compare(payload.id, "8")
    compare(payload.roomUid, "R3")
    compare(payload.time, "06:45")
    compare(payload.recurrence, "WEEKDAYS")
    compare(payload.duration, 30)
    compare(payload.volume, 28)
    compare(payload.enabled, false)
    compare(payload.includeGrouped, true)
    compare(payload.program, "keep")
  }

  function test_reset_restores_device_defaults() {
    subject.editAlarm({ id: "8", room_uid: "R3", time: "06:45", volume: 12 })
    subject.resetAlarm()

    compare(subject.alarmId, "new")
    compare(subject.alarmRoomUid, "R1")
    compare(subject.alarmTime, "07:00")
    compare(subject.alarmRecurrence, "DAILY")
    compare(subject.alarmDuration, 0)
    compare(subject.alarmVolume, 37)
    compare(subject.alarmEnabled, true)
    compare(subject.alarmGrouped, false)
    compare(subject.alarmProgram, "chime")
    compare(subject.alarmPrograms.length, 2)
  }

  function test_validation_rejects_bad_time_and_missing_room() {
    verify(subject.valid)
    subject.alarmTime = "25:99"
    verify(!subject.valid)
    subject.alarmTime = "07:00"
    subject.alarmRoomUid = "missing"
    verify(!subject.valid)
  }
}
