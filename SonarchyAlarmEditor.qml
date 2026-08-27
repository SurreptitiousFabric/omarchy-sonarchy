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

  readonly property bool editing: alarmTimeField.activeFocus || recurrencePicker.popupOpen
    || durationPicker.popupOpen || programPicker.popupOpen || alarmRoomPicker.popupOpen

  spacing: Style.space(9)

  SonarchyAlarmDraft {
    id: draft
    service: editor.service
    device: editor.device
  }

  function resetAlarm() {
    draft.resetAlarm()
    alarmTimeField.text = draft.alarmTime
  }

  function editAlarm(item) {
    draft.editAlarm(item)
    alarmTimeField.text = draft.alarmTime
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
      text: draft.alarmId === "new" ? "NEW ALARM" : "EDIT ALARM"
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
    value: draft.alarmRoomUid
    options: draft.alarmRooms
    foreground: editor.foreground
    fontFamily: editor.fontFamily
    onChanged: function(value) { draft.alarmRoomUid = String(value) }
  }

  Row {
    width: parent.width
    spacing: Style.space(7)

    TextField {
      id: alarmTimeField
      width: Style.space(95)
      placeholderText: "HH:MM"
      text: draft.alarmTime
      foreground: editor.foreground
      accent: Color.accent
      font.family: editor.fontFamily
      font.pixelSize: Style.font.body
      onTextChanged: draft.alarmTime = text.trim()
      Keys.onEscapePressed: focus = false
    }

    SonarchyDropdown {
      id: recurrencePicker
      width: parent.width - alarmTimeField.width - parent.spacing
      label: "REPEATS"
      value: draft.alarmRecurrence
      options: [
        { value: "ONCE", label: "Once" },
        { value: "DAILY", label: "Daily" },
        { value: "WEEKDAYS", label: "Weekdays" },
        { value: "WEEKENDS", label: "Weekends" }
      ]
      foreground: editor.foreground
      fontFamily: editor.fontFamily
      onChanged: function(value) { draft.alarmRecurrence = String(value) }
    }
  }

  SonarchyDropdown {
    id: durationPicker
    width: parent.width
    label: "DURATION"
    value: String(draft.alarmDuration)
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
    onChanged: function(value) { draft.alarmDuration = Number(value) }
  }

  SonarchyDropdown {
    id: programPicker
    width: parent.width
    label: "SOUND"
    value: draft.alarmProgram
    options: draft.alarmPrograms
    foreground: editor.foreground
    fontFamily: editor.fontFamily
    onChanged: function(value) { draft.alarmProgram = String(value) }
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
      text: draft.alarmVolume + "%"
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
      enabled: draft.alarmVolume > 0
      onClicked: draft.alarmVolume = Math.max(0, draft.alarmVolume - 1)
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
      value: draft.alarmVolume
      onMoved: function(value) { draft.alarmVolume = Math.round(value) }
      onReleased: function(value) { draft.alarmVolume = Math.round(value) }
    }

    Button {
      text: "+"
      tooltipText: "Raise alarm volume"
      foreground: editor.foreground
      focusable: true
      enabled: draft.alarmVolume < 100
      onClicked: draft.alarmVolume = Math.min(100, draft.alarmVolume + 1)
    }
  }

  SonarchyToggle {
    width: parent.width
    label: "Enabled"
    description: "Allow this alarm to run"
    checked: draft.alarmEnabled
    foreground: editor.foreground
    accent: Color.accent
    fontFamily: editor.fontFamily
    onClicked: draft.alarmEnabled = !draft.alarmEnabled
  }

  SonarchyToggle {
    width: parent.width
    label: "Include grouped rooms"
    description: "Play on rooms grouped with the alarm room"
    checked: draft.alarmGrouped
    foreground: editor.foreground
    accent: Color.accent
    fontFamily: editor.fontFamily
    onClicked: draft.alarmGrouped = !draft.alarmGrouped
  }

  Button {
    width: parent.width
    text: draft.alarmId === "new" ? "Create alarm" : "Save alarm"
    iconText: "󰆓"
    foreground: editor.foreground
    bordered: true
    focusable: true
    enabled: editor.service && !editor.service.actionBusy
      && editor.can("alarms.save") && draft.valid
    onClicked: editor.service.saveAlarm(draft.savePayload())
  }
}
