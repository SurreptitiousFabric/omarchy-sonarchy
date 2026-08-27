import QtQuick

QtObject {
  id: draft

  property var service: null
  property var device: null

  property string alarmId: "new"
  property string alarmRoomUid: ""
  property string alarmTime: "07:00"
  property string alarmRecurrence: "DAILY"
  property int alarmDuration: 0
  property int alarmVolume: 25
  property bool alarmEnabled: true
  property bool alarmGrouped: false
  property string alarmProgram: "chime"

  readonly property var alarmRooms: alarmRoomOptions()
  readonly property var alarmPrograms: alarmProgramOptions()
  readonly property bool alarmRoomAvailable: optionContains(alarmRooms, alarmRoomUid)
  readonly property bool valid: alarmRoomAvailable
    && /^([01]\d|2[0-3]):[0-5]\d$/.test(alarmTime)

  onDeviceChanged: selectAvailableAlarmRoom()
  onAlarmRoomsChanged: selectAvailableAlarmRoom()
  Component.onCompleted: selectAvailableAlarmRoom()

  function resetAlarm() {
    alarmId = "new"
    alarmRoomUid = device ? String(device.uid || "") : ""
    alarmTime = "07:00"
    alarmRecurrence = "DAILY"
    alarmDuration = 0
    alarmVolume = device ? Number(device.volume || 25) : 25
    alarmEnabled = true
    alarmGrouped = false
    alarmProgram = "chime"
  }

  function editAlarm(item) {
    alarmId = String(item.id)
    alarmRoomUid = String(item.room_uid || "")
    alarmTime = String(item.time || "07:00")
    alarmRecurrence = String(item.recurrence || "DAILY")
    alarmDuration = Number(item.duration || 0)
    alarmVolume = Number(item.volume || 25)
    alarmEnabled = item.enabled === true
    alarmGrouped = item.include_grouped === true
    alarmProgram = "keep"
  }

  function alarmRoomOptions() {
    var options = []
    var rooms = service ? service.rooms : []
    for (var i = 0; i < rooms.length; i++) {
      if (rooms[i].online === false) continue
      options.push({ value: String(rooms[i].uid), label: String(rooms[i].name) })
    }
    return options
  }

  function optionContains(options, value) {
    for (var i = 0; i < options.length; i++) {
      if (String(options[i].value) === String(value || "")) return true
    }
    return false
  }

  function selectAvailableAlarmRoom() {
    var options = alarmRoomOptions()
    if (optionContains(options, alarmRoomUid)) return
    var selectedUid = device ? String(device.uid || "") : ""
    alarmRoomUid = optionContains(options, selectedUid)
      ? selectedUid : (options.length > 0 ? String(options[0].value) : "")
  }

  function alarmProgramOptions() {
    var options = []
    if (alarmId !== "new") options.push({ value: "keep", label: "Keep current sound" })
    options.push({ value: "chime", label: "Sonos Chime" })
    var favorites = service && service.liveFavorites && service.liveFavorites.items
      ? service.liveFavorites.items : []
    for (var i = 0; i < favorites.length; i++) {
      options.push({
        value: "favorite:" + String(favorites[i].id),
        label: String(favorites[i].title || "Sonos Favorite")
      })
    }
    return options
  }

  function savePayload() {
    return {
      id: alarmId,
      time: alarmTime,
      recurrence: alarmRecurrence,
      duration: alarmDuration,
      volume: alarmVolume,
      enabled: alarmEnabled,
      includeGrouped: alarmGrouped,
      program: alarmProgram,
      roomUid: alarmRoomUid
    }
  }
}
