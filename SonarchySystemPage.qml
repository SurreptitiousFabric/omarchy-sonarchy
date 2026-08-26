import QtQuick
import QtQuick.Controls as QQC
import qs.Commons
import qs.Ui

Item {
  id: root

  property var bar: null
  property var service: null
  property var device: null
  property color foreground: Color.popups.text
  property string fontFamily: Style.font.family
  property string section: "alarms"
  property string confirmation: ""

  property string alarmId: "new"
  property string alarmTime: "07:00"
  property string alarmRecurrence: "DAILY"
  property int alarmDuration: 0
  property int alarmVolume: 25
  property bool alarmEnabled: true
  property bool alarmGrouped: false
  property string alarmProgram: "chime"
  property string lineInIp: ""

  readonly property var deviceInfo: service ? service.deviceDetails : ({})
  readonly property bool editing: alarmTimeField.activeFocus
    || sectionPicker.popupOpen || recurrencePicker.popupOpen
    || durationPicker.popupOpen || programPicker.popupOpen || lineInPicker.popupOpen

  onVisibleChanged: {
    if (!visible || !service) return
    service.refreshDetails()
    service.loadAlarms()
    service.ensureFavorites()
    if (lineInIp === "" && device) lineInIp = String(device.ip || "")
  }

  onDeviceChanged: {
    if (device) lineInIp = String(device.ip || "")
    if (visible && service) service.refreshDetails()
  }

  function ensureVisible(item) {
    if (!item || !systemFlick.visible) return
    var point = item.mapToItem(systemFlick.contentItem, 0, 0)
    var top = point.y - Style.space(10)
    var bottom = point.y + item.height + Style.space(10)
    if (top < systemFlick.contentY) systemFlick.contentY = Math.max(0, top)
    else if (bottom > systemFlick.contentY + systemFlick.height)
      systemFlick.contentY = Math.min(
        Math.max(0, systemFlick.contentHeight - systemFlick.height),
        bottom - systemFlick.height)
  }

  function arm(key) {
    if (confirmation === key) {
      confirmation = ""
      confirmTimer.stop()
      return true
    }
    confirmation = key
    confirmTimer.restart()
    return false
  }

  function resetAlarm() {
    alarmId = "new"
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
    alarmTime = String(item.time || "07:00")
    alarmRecurrence = String(item.recurrence || "DAILY")
    alarmDuration = Number(item.duration || 0)
    alarmVolume = Number(item.volume || 25)
    alarmEnabled = item.enabled === true
    alarmGrouped = item.include_grouped === true
    alarmProgram = "keep"
    alarmTimeField.text = alarmTime
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

  function lineInOptions() {
    var options = []
    var rooms = service ? service.devices : []
    for (var i = 0; i < rooms.length; i++)
      options.push({ value: String(rooms[i].ip), label: String(rooms[i].name) })
    return options
  }

  function valueText(value, fallback) {
    var text = String(value === null || value === undefined ? "" : value)
    return text === "" ? String(fallback || "Not reported") : text
  }

  function can(operation) {
    return service && service.hasCapability(operation)
  }

  Timer {
    id: confirmTimer
    interval: 5000
    repeat: false
    onTriggered: root.confirmation = ""
  }

  Flickable {
    id: systemFlick
    anchors.fill: parent
    contentWidth: width
    contentHeight: systemColumn.implicitHeight
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    flickableDirection: Flickable.VerticalFlick

    QQC.ScrollBar.vertical: QQC.ScrollBar {
      policy: QQC.ScrollBar.AsNeeded
    }

    Column {
      id: systemColumn
      width: systemFlick.width - Style.space(6)
      spacing: Style.space(10)

      SonarchyDropdown {
        id: sectionPicker
        width: parent.width
        label: "SYSTEM"
        value: root.section
        options: [
          { value: "alarms", label: "Alarms" },
          { value: "sources", label: "TV and line-in" },
          { value: "device", label: "Device information" }
        ]
        foreground: root.foreground
        fontFamily: root.fontFamily
        onChanged: function(value) { root.section = String(value) }
      }

      Text {
        width: parent.width
        visible: root.confirmation !== ""
        text: "Press the same focused delete action again to confirm. This expires in 5 seconds."
        color: Color.urgent
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
        font.bold: true
        wrapMode: Text.WordWrap
      }

      Column {
        width: parent.width
        spacing: Style.space(9)
        visible: root.section === "alarms"

        Item {
          width: parent.width
          implicitHeight: Math.max(alarmHeader.implicitHeight, newAlarmButton.implicitHeight)

          PanelSectionHeader {
            id: alarmHeader
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            text: root.alarmId === "new" ? "NEW ALARM" : "EDIT ALARM"
            foreground: root.foreground
            fontFamily: root.fontFamily
          }

          Button {
            id: newAlarmButton
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            text: "New"
            iconText: "󰐕"
            foreground: root.foreground
            bordered: true
            focusable: true
            onClicked: root.resetAlarm()
          }
        }

        Text {
          width: parent.width
          text: root.alarmId === "new"
            ? "The new alarm will belong to " + String(root.device ? root.device.name : "the selected room") + "."
            : "Editing the existing alarm for its original room."
          color: Qt.darker(root.foreground, 1.45)
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          wrapMode: Text.WordWrap
        }

        Row {
          width: parent.width
          spacing: Style.space(7)

          TextField {
            id: alarmTimeField
            width: Style.space(95)
            placeholderText: "HH:MM"
            text: root.alarmTime
            foreground: root.foreground
            accent: Color.accent
            font.family: root.fontFamily
            font.pixelSize: Style.font.body
            onTextChanged: root.alarmTime = text.trim()
            Keys.onEscapePressed: focus = false
          }

          SonarchyDropdown {
            id: recurrencePicker
            width: parent.width - alarmTimeField.width - parent.spacing
            label: "REPEATS"
            value: root.alarmRecurrence
            options: [
              { value: "ONCE", label: "Once" },
              { value: "DAILY", label: "Daily" },
              { value: "WEEKDAYS", label: "Weekdays" },
              { value: "WEEKENDS", label: "Weekends" }
            ]
            foreground: root.foreground
            fontFamily: root.fontFamily
            onChanged: function(value) { root.alarmRecurrence = String(value) }
          }
        }

        SonarchyDropdown {
          id: durationPicker
          width: parent.width
          label: "DURATION"
          value: String(root.alarmDuration)
          options: [
            { value: "0", label: "No limit" },
            { value: "15", label: "15 minutes" },
            { value: "30", label: "30 minutes" },
            { value: "45", label: "45 minutes" },
            { value: "60", label: "1 hour" },
            { value: "90", label: "1½ hours" },
            { value: "120", label: "2 hours" }
          ]
          foreground: root.foreground
          fontFamily: root.fontFamily
          onChanged: function(value) { root.alarmDuration = Number(value) }
        }

        SonarchyDropdown {
          id: programPicker
          width: parent.width
          label: "SOUND"
          value: root.alarmProgram
          options: root.alarmProgramOptions()
          foreground: root.foreground
          fontFamily: root.fontFamily
          onChanged: function(value) { root.alarmProgram = String(value) }
        }

        Item {
          width: parent.width
          implicitHeight: Math.max(alarmVolumeHeader.implicitHeight, alarmVolumeValue.implicitHeight)

          PanelSectionHeader {
            id: alarmVolumeHeader
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            text: "ALARM VOLUME"
            foreground: root.foreground
            fontFamily: root.fontFamily
          }

          Text {
            id: alarmVolumeValue
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            text: root.alarmVolume + "%"
            color: Qt.darker(root.foreground, 1.35)
            font.family: root.fontFamily
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
            foreground: root.foreground
            focusable: true
            enabled: root.alarmVolume > 0
            onClicked: root.alarmVolume = Math.max(0, root.alarmVolume - 1)
          }

          SonarchySlider {
            scrollTarget: systemFlick
            width: parent.width - parent.children[0].width - parent.children[2].width
              - parent.spacing * 2
            anchors.verticalCenter: parent.verticalCenter
            bar: root.bar
            minimum: 0
            maximum: 100
            step: 1
            integer: true
            value: root.alarmVolume
            onMoved: function(value) { root.alarmVolume = Math.round(value) }
            onReleased: function(value) { root.alarmVolume = Math.round(value) }
          }

          Button {
            text: "+"
            tooltipText: "Raise alarm volume"
            foreground: root.foreground
            focusable: true
            enabled: root.alarmVolume < 100
            onClicked: root.alarmVolume = Math.min(100, root.alarmVolume + 1)
          }
        }

        SonarchyToggle {
          width: parent.width
          label: "Enabled"
          description: "Allow this alarm to run"
          checked: root.alarmEnabled
          foreground: root.foreground
          accent: Color.accent
          fontFamily: root.fontFamily
          onClicked: root.alarmEnabled = !root.alarmEnabled
        }

        SonarchyToggle {
          width: parent.width
          label: "Include grouped rooms"
          description: "Play on rooms grouped with the alarm room"
          checked: root.alarmGrouped
          foreground: root.foreground
          accent: Color.accent
          fontFamily: root.fontFamily
          onClicked: root.alarmGrouped = !root.alarmGrouped
        }

        Button {
          width: parent.width
          text: root.alarmId === "new" ? "Create alarm" : "Save alarm"
          iconText: "󰆓"
          foreground: root.foreground
          bordered: true
          focusable: true
          enabled: root.service && !root.service.actionBusy
            && root.can("alarms.save")
            && /^([01]\d|2[0-3]):[0-5]\d$/.test(root.alarmTime)
          onClicked: root.service.saveAlarm({
            id: root.alarmId,
            time: root.alarmTime,
            recurrence: root.alarmRecurrence,
            duration: root.alarmDuration,
            volume: root.alarmVolume,
            enabled: root.alarmEnabled,
            includeGrouped: root.alarmGrouped,
            program: root.alarmProgram
          })
        }

        PanelSeparator { foreground: root.foreground }

        Item {
          width: parent.width
          implicitHeight: Math.max(savedAlarmsHeader.implicitHeight, refreshAlarmsButton.implicitHeight)

          PanelSectionHeader {
            id: savedAlarmsHeader
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            text: "SAVED ALARMS"
            foreground: root.foreground
            fontFamily: root.fontFamily
          }

          Button {
            id: refreshAlarmsButton
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            iconText: "󰑐"
            iconSpinning: root.service ? root.service.alarmsLoading : false
            tooltipText: "Refresh alarms"
            foreground: root.foreground
            focusable: true
            enabled: root.service && !root.service.alarmsLoading
              && root.can("alarms.list")
            onClicked: root.service.loadAlarms()
          }
        }

        Repeater {
          model: root.service ? root.service.alarms : []

          delegate: BorderSurface {
            id: alarmCard
            required property var modelData
            readonly property string deleteKey: "alarm-delete:" + String(modelData.id)
            width: parent.width
            implicitHeight: Style.space(58)
            radius: Style.cornerRadius
            color: Style.normalFillFor(root.foreground, Color.accent)
            borderSpec: Border.none()

            Row {
              id: alarmActions
              anchors.right: parent.right
              anchors.rightMargin: alarmCard.borderRight + Style.space(6)
              anchors.verticalCenter: parent.verticalCenter
              spacing: Style.space(4)

              Button {
                text: alarmCard.modelData.enabled === true ? "Disable" : "Enable"
                foreground: root.foreground
                bordered: true
                focusable: true
                enabled: root.service && !root.service.actionBusy
                  && root.can("alarms.toggle")
                onClicked: root.service.toggleAlarm(String(alarmCard.modelData.id),
                  alarmCard.modelData.enabled !== true)
              }

              Button {
                text: "Edit"
                iconText: "󰏫"
                foreground: root.foreground
                bordered: true
                focusable: true
                onClicked: root.editAlarm(alarmCard.modelData)
              }

              Button {
                iconText: "󰅖"
                tooltipText: root.confirmation === alarmCard.deleteKey
                  ? "Press again to confirm" : "Delete alarm"
                foreground: root.confirmation === alarmCard.deleteKey ? Color.urgent : root.foreground
                focusable: true
                enabled: root.service && !root.service.actionBusy
                  && root.can("alarms.delete")
                onClicked: if (root.arm(alarmCard.deleteKey))
                  root.service.deleteAlarm(String(alarmCard.modelData.id))
              }
            }

            Column {
              anchors.left: parent.left
              anchors.leftMargin: Style.space(10)
              anchors.right: alarmActions.left
              anchors.rightMargin: Style.space(8)
              anchors.verticalCenter: parent.verticalCenter
              spacing: Style.space(2)

              Text {
                width: parent.width
                text: String(alarmCard.modelData.time) + "  ·  "
                  + String(alarmCard.modelData.room)
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                font.bold: true
                elide: Text.ElideRight
              }

              Text {
                width: parent.width
                text: String(alarmCard.modelData.recurrence).toLowerCase()
                  + "  ·  " + String(alarmCard.modelData.volume) + "%  ·  "
                  + String(alarmCard.modelData.program)
                color: Qt.darker(root.foreground, 1.45)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                elide: Text.ElideRight
              }
            }
          }
        }

        Text {
          width: parent.width
          visible: root.service && !root.service.alarmsLoading
            && root.service.alarms.length === 0
          text: "No Sonos alarms found."
          color: Qt.darker(root.foreground, 1.45)
          font.family: root.fontFamily
          font.pixelSize: Style.font.bodySmall
          horizontalAlignment: Text.AlignHCenter
          topPadding: Style.space(12)
        }
      }

      Column {
        width: parent.width
        spacing: Style.space(9)
        visible: root.section === "sources"

        PanelSectionHeader {
          text: "LINE-IN"
          foreground: root.foreground
          fontFamily: root.fontFamily
        }

        Text {
          width: parent.width
          text: "Choose the Sonos room where the cable is connected, then send that audio to the selected playback group."
          color: Qt.darker(root.foreground, 1.45)
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          wrapMode: Text.WordWrap
        }

        SonarchyDropdown {
          id: lineInPicker
          width: parent.width
          label: "SOURCE ROOM"
          value: root.lineInIp
          options: root.lineInOptions()
          foreground: root.foreground
          fontFamily: root.fontFamily
          onChanged: function(value) { root.lineInIp = String(value) }
        }

        Button {
          width: parent.width
          text: "Play line-in"
          iconText: "󰕾"
          foreground: root.foreground
          bordered: true
          focusable: true
          enabled: root.service && !root.service.actionBusy && root.lineInIp !== ""
            && root.can("sources.switch")
          onClicked: root.service.switchSource("line-in", root.lineInIp)
        }

        PanelSeparator {
          foreground: root.foreground
          visible: root.deviceInfo.is_soundbar === true
        }

        PanelSectionHeader {
          visible: root.deviceInfo.is_soundbar === true
          text: "TV AUDIO"
          foreground: root.foreground
          fontFamily: root.fontFamily
        }

        Button {
          width: parent.width
          visible: root.deviceInfo.is_soundbar === true
          text: "Switch to TV"
          iconText: "󰔂"
          foreground: root.foreground
          bordered: true
          focusable: true
          enabled: root.service && !root.service.actionBusy
            && root.can("sources.switch")
          onClicked: root.service.switchSource("tv", "")
        }

        Text {
          width: parent.width
          text: "Current source: " + root.valueText(root.deviceInfo.source, "Unknown")
          color: Qt.darker(root.foreground, 1.35)
          font.family: root.fontFamily
          font.pixelSize: Style.font.bodySmall
          wrapMode: Text.WordWrap
        }
      }

      Column {
        width: parent.width
        spacing: Style.space(8)
        visible: root.section === "device"

        PanelSectionHeader {
          text: "DEVICE"
          foreground: root.foreground
          fontFamily: root.fontFamily
        }

        Text {
          width: parent.width
          text: root.valueText(root.deviceInfo.model, "Sonos speaker")
            + (String(root.deviceInfo.model_number || "") !== ""
               ? "  ·  " + String(root.deviceInfo.model_number) : "")
          color: root.foreground
          font.family: root.fontFamily
          font.pixelSize: Style.font.subtitle
          font.bold: true
          wrapMode: Text.WordWrap
        }

        Text {
          width: parent.width
          text: "Software " + root.valueText(root.deviceInfo.software_version, "unknown")
            + "  ·  Hardware " + root.valueText(root.deviceInfo.hardware_version, "unknown")
          color: Qt.darker(root.foreground, 1.4)
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          wrapMode: Text.WordWrap
        }

        Text {
          width: parent.width
          visible: String(root.deviceInfo.serial_number || "") !== ""
          text: "Serial: " + String(root.deviceInfo.serial_number)
          color: Qt.darker(root.foreground, 1.4)
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          wrapMode: Text.WordWrap
        }

        Text {
          width: parent.width
          visible: root.deviceInfo.battery !== null
            && root.deviceInfo.battery !== undefined
          text: "Battery: " + root.valueText(
            root.deviceInfo.battery ? root.deviceInfo.battery.level : "", "unknown")
            + (root.deviceInfo.battery && root.deviceInfo.battery.level !== null ? "%" : "")
            + (root.deviceInfo.battery && String(root.deviceInfo.battery.power_source || "") !== ""
               ? "  ·  " + String(root.deviceInfo.battery.power_source) : "")
          color: root.foreground
          font.family: root.fontFamily
          font.pixelSize: Style.font.bodySmall
          wrapMode: Text.WordWrap
        }

        PanelSeparator { foreground: root.foreground }

        SonarchyToggle {
          width: parent.width
          visible: root.deviceInfo.is_soundbar === true
            && root.deviceInfo.tv_autoplay !== null
            && root.deviceInfo.tv_autoplay !== undefined
          label: "TV Autoplay"
          description: "Switch from music whenever the TV sends audio"
          checked: root.deviceInfo.tv_autoplay === true
          foreground: root.foreground
          accent: Color.accent
          fontFamily: root.fontFamily
          enabled: root.service && !root.service.actionBusy
            && root.can("devices.setting.set")
          onClicked: root.service.setDeviceSetting(
            "tv-autoplay", root.deviceInfo.tv_autoplay === true ? "off" : "on")
        }

        SonarchyToggle {
          width: parent.width
          visible: root.deviceInfo.status_light !== null
            && root.deviceInfo.status_light !== undefined
          label: "Status light"
          description: "Speaker status LED"
          checked: root.deviceInfo.status_light === true
          foreground: root.foreground
          accent: Color.accent
          fontFamily: root.fontFamily
          enabled: root.service && !root.service.actionBusy
            && root.can("devices.setting.set")
          onClicked: root.service.setDeviceSetting(
            "status-light", root.deviceInfo.status_light === true ? "off" : "on")
        }

        SonarchyToggle {
          width: parent.width
          visible: root.deviceInfo.buttons_enabled !== null
            && root.deviceInfo.buttons_enabled !== undefined
          label: "Touch controls"
          description: "Buttons on the speaker itself"
          checked: root.deviceInfo.buttons_enabled === true
          foreground: root.foreground
          accent: Color.accent
          fontFamily: root.fontFamily
          enabled: root.service && !root.service.actionBusy
            && root.can("devices.setting.set")
          onClicked: root.service.setDeviceSetting(
            "buttons-enabled", root.deviceInfo.buttons_enabled === true ? "off" : "on")
        }

        SonarchyToggle {
          width: parent.width
          visible: root.deviceInfo.trueplay !== null
            && root.deviceInfo.trueplay !== undefined
          label: "Trueplay"
          description: "Use the room tuning already stored on this speaker"
          checked: root.deviceInfo.trueplay === true
          foreground: root.foreground
          accent: Color.accent
          fontFamily: root.fontFamily
          enabled: root.service && !root.service.actionBusy
            && root.can("devices.setting.set")
          onClicked: root.service.setDeviceSetting(
            "trueplay", root.deviceInfo.trueplay === true ? "off" : "on")
        }

        Text {
          width: parent.width
          visible: root.deviceInfo.mic_enabled !== null
            && root.deviceInfo.mic_enabled !== undefined
          text: "Microphone: " + (root.deviceInfo.mic_enabled === true ? "on" : "off")
            + "  ·  Voice service: "
            + (root.deviceInfo.voice_service_configured === true ? "configured" : "not configured")
          color: Qt.darker(root.foreground, 1.4)
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          wrapMode: Text.WordWrap
        }
      }
    }
  }
}
