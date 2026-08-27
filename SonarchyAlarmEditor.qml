import QtQuick
import qs.Commons
import qs.Ui

Column {
  id: editor

  property var bar: null
  property var service: null
  property var device: null
  property var scrollTarget: null
  property color foreground: Color.popups.text
  property string fontFamily: Style.font.family

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
  readonly property bool alarmRoomAvailable: optionContains(alarmRooms, alarmRoomUid)
  readonly property bool editing: alarmTimeField.activeFocus || recurrencePicker.popupOpen
    || durationPicker.popupOpen || programPicker.popupOpen || alarmRoomPicker.popupOpen

  spacing: Style.space(9)

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
    alarmTimeField.text = alarmTime
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
    alarmTimeField.text = alarmTime
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

  function can(operation) {
    return service && service.hasCapability(operation)
  }

  Item {
    width: parent.width
    implicitHeight: Math.max(alarmHeader.implicitHeight, newAlarmButton.implicitHeight)

    PanelSectionHeader {
      id: alarmHeader
      anchors.left: parent.left
      anchors.verticalCenter: parent.verticalCenter
      text: editor.alarmId === "new" ? "NEW ALARM" : "EDIT ALARM"
      foreground: editor.foreground
      fontFamily: editor.fontFamily
    }

    Button {
      id: newAlarmButton
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      text: "New"
      iconText: "󰐕"
      foreground: editor.foreground
      bordered: true
      focusable: true
      onClicked: editor.resetAlarm()
    }
  }

  SonarchyDropdown {
    id: alarmRoomPicker
    width: parent.width
    label: "ROOM"
    value: editor.alarmRoomUid
    options: editor.alarmRooms
    foreground: editor.foreground
    fontFamily: editor.fontFamily
    onChanged: function(value) { editor.alarmRoomUid = String(value) }
  }

  Row {
    width: parent.width
    spacing: Style.space(7)

    TextField {
      id: alarmTimeField
      width: Style.space(95)
      placeholderText: "HH:MM"
      text: editor.alarmTime
      foreground: editor.foreground
      accent: Color.accent
      font.family: editor.fontFamily
      font.pixelSize: Style.font.body
      onTextChanged: editor.alarmTime = text.trim()
      Keys.onEscapePressed: focus = false
    }

    SonarchyDropdown {
      id: recurrencePicker
      width: parent.width - alarmTimeField.width - parent.spacing
      label: "REPEATS"
      value: editor.alarmRecurrence
      options: [
        { value: "ONCE", label: "Once" },
        { value: "DAILY", label: "Daily" },
        { value: "WEEKDAYS", label: "Weekdays" },
        { value: "WEEKENDS", label: "Weekends" }
      ]
      foreground: editor.foreground
      fontFamily: editor.fontFamily
      onChanged: function(value) { editor.alarmRecurrence = String(value) }
    }
  }

  SonarchyDropdown {
    id: durationPicker
    width: parent.width
    label: "DURATION"
    value: String(editor.alarmDuration)
    options: [
      { value: "0", label: "No limit" },
      { value: "15", label: "15 minutes" },
      { value: "30", label: "30 minutes" },
      { value: "45", label: "45 minutes" },
      { value: "60", label: "1 hour" },
      { value: "90", label: "1½ hours" },
      { value: "120", label: "2 hours" }
    ]
    foreground: editor.foreground
    fontFamily: editor.fontFamily
    onChanged: function(value) { editor.alarmDuration = Number(value) }
  }

  SonarchyDropdown {
    id: programPicker
    width: parent.width
    label: "SOUND"
    value: editor.alarmProgram
    options: editor.alarmProgramOptions()
    foreground: editor.foreground
    fontFamily: editor.fontFamily
    onChanged: function(value) { editor.alarmProgram = String(value) }
  }

  Item {
    width: parent.width
    implicitHeight: Math.max(alarmVolumeHeader.implicitHeight, alarmVolumeValue.implicitHeight)

    PanelSectionHeader {
      id: alarmVolumeHeader
      anchors.left: parent.left
      anchors.verticalCenter: parent.verticalCenter
      text: "ALARM VOLUME"
      foreground: editor.foreground
      fontFamily: editor.fontFamily
    }

    Text {
      id: alarmVolumeValue
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      text: editor.alarmVolume + "%"
      color: Qt.darker(editor.foreground, 1.35)
      font.family: editor.fontFamily
      font.pixelSize: Style.font.caption
      font.bold: true
    }
  }

  Row {
    width: parent.width
    spacing: Style.space(6)

    Button {
      text: "−"
      tooltipText: "Lower alarm volume"
      foreground: editor.foreground
      focusable: true
      enabled: editor.alarmVolume > 0
      onClicked: editor.alarmVolume = Math.max(0, editor.alarmVolume - 1)
    }

    SonarchySlider {
      scrollTarget: editor.scrollTarget
      width: parent.width - parent.children[0].width - parent.children[2].width
        - parent.spacing * 2
      anchors.verticalCenter: parent.verticalCenter
      bar: editor.bar
      minimum: 0
      maximum: 100
      step: 1
      integer: true
      value: editor.alarmVolume
      onMoved: function(value) { editor.alarmVolume = Math.round(value) }
      onReleased: function(value) { editor.alarmVolume = Math.round(value) }
    }

    Button {
      text: "+"
      tooltipText: "Raise alarm volume"
      foreground: editor.foreground
      focusable: true
      enabled: editor.alarmVolume < 100
      onClicked: editor.alarmVolume = Math.min(100, editor.alarmVolume + 1)
    }
  }

  SonarchyToggle {
    width: parent.width
    label: "Enabled"
    description: "Allow this alarm to run"
    checked: editor.alarmEnabled
    foreground: editor.foreground
    accent: Color.accent
    fontFamily: editor.fontFamily
    onClicked: editor.alarmEnabled = !editor.alarmEnabled
  }

  SonarchyToggle {
    width: parent.width
    label: "Include grouped rooms"
    description: "Play on rooms grouped with the alarm room"
    checked: editor.alarmGrouped
    foreground: editor.foreground
    accent: Color.accent
    fontFamily: editor.fontFamily
    onClicked: editor.alarmGrouped = !editor.alarmGrouped
  }

  Button {
    width: parent.width
    text: editor.alarmId === "new" ? "Create alarm" : "Save alarm"
    iconText: "󰆓"
    foreground: editor.foreground
    bordered: true
    focusable: true
    enabled: editor.service && !editor.service.actionBusy
      && editor.can("alarms.save") && editor.alarmRoomAvailable
      && /^([01]\d|2[0-3]):[0-5]\d$/.test(editor.alarmTime)
    onClicked: editor.service.saveAlarm({
      id: editor.alarmId,
      time: editor.alarmTime,
      recurrence: editor.alarmRecurrence,
      duration: editor.alarmDuration,
      volume: editor.alarmVolume,
      enabled: editor.alarmEnabled,
      includeGrouped: editor.alarmGrouped,
      program: editor.alarmProgram,
      roomUid: editor.alarmRoomUid
    })
  }
}
