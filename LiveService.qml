import QtQuick
import Quickshell
import Quickshell.Io

Item {
  id: root

  property var shell: null
  property var manifest: null

  readonly property string moduleName: "io.github.surreptitiousfabric.sonarchy"
  readonly property var backendEnvironment: ({
    HOME: Quickshell.env("HOME"),
    LANG: Quickshell.env("LANG") || "C.UTF-8",
    XDG_CACHE_HOME: Quickshell.env("XDG_CACHE_HOME"),
    XDG_DATA_HOME: Quickshell.env("XDG_DATA_HOME"),
    XDG_STATE_HOME: Quickshell.env("XDG_STATE_HOME")
  })
  property var snapshot: ({
    type: "snapshot",
    version: 1,
    revision: 0,
    status: { state: "starting", message: "Starting Sonos controller…" },
    selectedAnchorRoomUid: "",
    targetGroupUid: "",
    capabilities: [],
    households: [],
    target: null,
    favorites: { state: "not_loaded", items: [], total: 0, unsupported: 0, error: "" },
    playback: {
      state: "STOPPED",
      title: "",
      artist: "",
      album: "",
      artworkUrl: "",
      artworkKind: "",
      source: "UNKNOWN",
      positionSec: null,
      durationSec: null,
      availableActions: [],
      metadataState: "empty",
      stale: false
    }
  })
  property string commandError: ""
  property string processError: ""
  readonly property string lastError: commandError || processError
  property int requestCounter: 0
  property int restartAttempt: 0
  property bool expectedStop: false
  property bool backendReady: false
  property bool receivedSnapshotThisRun: false
  property bool setupFailed: false
  property string backendStderr: ""
  property int openPanelCount: 0
  property string favoriteRequestId: ""
  property string favoriteStartingTitle: ""
  property bool favoriteAwaitingSnapshot: false
  property string favoriteError: ""
  property string moveRequestId: ""
  property string moveError: ""
  property var quietRequestIds: ({})
  signal commandResult(var message)

  readonly property bool ready: backendReady && snapshot && snapshot.status && snapshot.status.state === "ready"
  readonly property var playback: snapshot && snapshot.playback ? snapshot.playback : ({})
  readonly property var target: snapshot ? snapshot.target : null
  readonly property var households: snapshot && snapshot.households ? snapshot.households : []

  function hasCapability(name) {
    var capabilities = snapshot && snapshot.capabilities ? snapshot.capabilities : []
    return capabilities.indexOf(String(name || "")) >= 0
  }

  function setStatus(state, message) {
    var next = {}
    for (var key in snapshot) next[key] = snapshot[key]
    var status = {}
    var currentStatus = snapshot && snapshot.status ? snapshot.status : ({})
    for (var statusKey in currentStatus) status[statusKey] = currentStatus[statusKey]
    status.state = state
    status.message = message
    next.status = status
    snapshot = next
  }

  function localPath(url) {
    var text = String(url || "")
    if (text.indexOf("file://") === 0) text = text.substring(7)
    return decodeURIComponent(text)
  }

  readonly property string backendPath: localPath(Qt.resolvedUrl("sonarchy-backend.sh"))

  function sendCommand(op, args, clearErrors, reportErrors) {
    if (!backend.running) {
      setCommandError("Sonos backend is not running")
      return ""
    }
    requestCounter += 1
    var id = String(requestCounter)
    if (op !== "session.panel_open.set" && clearErrors !== false) clearTransientErrors()
    if (reportErrors === false) {
      var quiet = Object.assign({}, quietRequestIds)
      quiet[id] = true
      quietRequestIds = quiet
    }
    var payload = { version: 1, id: id, op: op, args: args || ({}) }
    backend.write(JSON.stringify(payload) + "\n")
    return id
  }

  function setCommandError(message) {
    commandError = String(message || "Sonos command failed")
    transientErrorTimer.restart()
  }

  function clearTransientErrors() {
    commandError = ""
    favoriteError = ""
    moveError = ""
    transientErrorTimer.stop()
  }

  function clearErrors() {
    clearTransientErrors()
    processError = ""
  }

  function refresh() {
    if (setupFailed) {
      setupFailed = false
      processError = ""
      backendStderr = ""
      restartAttempt = 0
      setStatus("starting", "Starting Sonos controller…")
      if (!backend.running) backend.running = true
      return
    }
    sendCommand("state.refresh")
  }
  function setPanelOpen(open) {
    var wasOpen = openPanelCount > 0
    openPanelCount = Math.max(0, openPanelCount + (open ? 1 : -1))
    var isOpen = openPanelCount > 0
    if (wasOpen !== isOpen && backend.running)
      sendCommand("session.panel_open.set", { open: isOpen }, false, false)
  }
  function playPause() { sendCommand("playback.toggle") }
  function next() { sendCommand("playback.next") }
  function previous() { sendCommand("playback.previous") }
  function seek(positionSec) { sendCommand("playback.seek", { positionSec: positionSec }) }
  function playFavorite(favoriteId, title) {
    if (favoriteRequestId !== "" || favoriteAwaitingSnapshot) return ""
    favoriteStartingTitle = String(title || "Favorite")
    favoriteError = ""
    favoriteRequestId = sendCommand("content.favorite.play", { favoriteId: favoriteId })
    return favoriteRequestId
  }
  function refreshFavorites() { sendCommand("content.favorites.refresh") }
  function movePlaybackToRoom(roomUid) {
    if (moveRequestId !== "") return ""
    moveError = ""
    moveRequestId = sendCommand("playback.room.move", { roomUid: roomUid })
    return moveRequestId
  }
  function selectGroup(groupUid) { sendCommand("selection.group.set", { groupUid: groupUid }) }
  function selectRoom(roomUid) { sendCommand("selection.room.set", { roomUid: roomUid }) }
  function setGroupVolume(volume) { sendCommand("volume.group.set", { volume: volume }) }
  function adjustGroupVolume(delta) { sendCommand("volume.group.adjust", { delta: delta }) }
  function setGroupMute(mute) { sendCommand("mute.group.set", { mute: !!mute }) }
  function setRoomVolume(roomUid, volume) { sendCommand("volume.room.set", { roomUid: roomUid, volume: volume }) }
  function setRoomMute(roomUid, mute) { sendCommand("mute.room.set", { roomUid: roomUid, mute: !!mute }) }
  function applyMembers(roomUids) { sendCommand("topology.members.set", { roomUids: roomUids }) }
  function requestDeviceDetails(roomUid) {
    return sendCommand("devices.details.get", { roomUid: roomUid }, false, false)
  }
  function requestRadioArtwork(title, artist) {
    return sendCommand(
      "artwork.radio.resolve", { title: title, artist: artist }, false, false)
  }
  function requestContent(roomUid, kind, term, limit, context) {
    return sendCommand("content.browse", {
      roomUid: roomUid, kind: kind, term: term, limit: limit,
      context: context || ({})
    }, false, false)
  }
  function requestAlarms(roomUid) {
    return sendCommand("alarms.list", { roomUid: roomUid }, false, false)
  }
  function stopRoom(roomUid) {
    return sendCommand("playback.stop", { roomUid: roomUid })
  }
  function renameRoom(roomUid, name) {
    return sendCommand("devices.rename", { roomUid: roomUid, name: name })
  }
  function setPlaybackOption(roomUid, option, value) {
    return sendCommand("playback.option.set", {
      roomUid: roomUid, option: option, value: value
    })
  }
  function setSound(roomUid, setting, value) {
    return sendCommand("sound.setting.set", {
      roomUid: roomUid, setting: setting, value: value
    })
  }
  function setDeviceSetting(roomUid, setting, value) {
    return sendCommand("devices.setting.set", {
      roomUid: roomUid, setting: setting, value: value
    })
  }
  function switchSource(roomUid, source, sourceRoomUid) {
    var args = { roomUid: roomUid, source: source }
    if (String(sourceRoomUid || "") !== "") args.sourceRoomUid = sourceRoomUid
    return sendCommand("sources.switch", args)
  }
  function playQueueItem(roomUid, index, itemId) {
    return sendCommand("queue.item.play", {
      roomUid: roomUid, index: index, itemId: itemId
    })
  }
  function removeQueueItem(roomUid, index, itemId) {
    return sendCommand("queue.item.remove", {
      roomUid: roomUid, index: index, itemId: itemId
    })
  }
  function clearQueue(roomUid) {
    return sendCommand("queue.clear", { roomUid: roomUid })
  }
  function enqueueContent(roomUid, kind, context, itemId, index, mode, libraryPath) {
    return sendCommand("queue.content.enqueue", {
      roomUid: roomUid, kind: kind, context: context,
      itemId: itemId, index: index, mode: mode,
      libraryPath: libraryPath || []
    })
  }
  function mutatePlaylist(roomUid, action, value) {
    return sendCommand("playlists.mutate", {
      roomUid: roomUid, action: action, value: value
    })
  }
  function mutatePlaylistTrack(roomUid, action, playlistId, index, itemId) {
    return sendCommand("playlists.track.mutate", {
      roomUid: roomUid, action: action, playlistId: playlistId,
      index: index, itemId: itemId
    })
  }
  function playApple(roomUid, url) {
    return sendCommand("content.apple.play", { roomUid: roomUid, url: url })
  }
  function playAppleAlbum(roomUid, url) {
    return sendCommand("content.apple.album.play", { roomUid: roomUid, url: url })
  }
  function playGlobal(roomUid, itemId, term) {
    return sendCommand("content.global.play", {
      roomUid: roomUid, itemId: itemId, term: term
    })
  }
  function startLibraryUpdate(roomUid) {
    return sendCommand("library.update.start", { roomUid: roomUid })
  }
  function saveAlarm(roomUid, alarm) {
    return sendCommand("alarms.save", {
      roomUid: roomUid,
      alarmId: alarm.alarmId,
      alarmRoomUid: alarm.alarmRoomUid,
      time: alarm.time,
      recurrence: alarm.recurrence,
      volume: alarm.volume,
      duration: alarm.duration,
      enabled: alarm.enabled,
      includeGrouped: alarm.includeGrouped,
      program: alarm.program
    })
  }
  function toggleAlarm(roomUid, alarmId, enabled) {
    return sendCommand("alarms.toggle", {
      roomUid: roomUid, alarmId: alarmId, enabled: !!enabled
    })
  }
  function deleteAlarm(roomUid, alarmId) {
    return sendCommand("alarms.delete", { roomUid: roomUid, alarmId: alarmId })
  }

  function errorMessage(error) {
    if (error && typeof error === "object" && error.message)
      return String(error.message)
    return String(error || "Sonos command failed")
  }

  function validRevision(value) {
    var revision = Number(value)
    return isFinite(revision) && revision >= 1 && Math.floor(revision) === revision
  }

  function handleLine(line) {
    var text = String(line || "").trim()
    if (!text) return
    var message
    try {
      message = JSON.parse(text)
    } catch (e) {
      setCommandError("The Sonarchy backend returned an invalid response")
      console.warn("Sonos backend invalid stdout:", text)
      return
    }
    if (message.type === "snapshot") {
      if (Number(message.version || 0) !== 1 || !validRevision(message.revision)
          || !message.status || !Array.isArray(message.households)) {
        setCommandError("The Sonarchy backend returned an invalid snapshot")
        return
      }
      if (receivedSnapshotThisRun
          && Number(message.revision || 0) < Number(snapshot.revision || 0)) return
      var firstSnapshot = !receivedSnapshotThisRun
      snapshot = message
      backendReady = true
      receivedSnapshotThisRun = true
      setupFailed = false
      restartAttempt = 0
      processError = ""
      if (favoriteAwaitingSnapshot) {
        favoriteAwaitingSnapshot = false
        favoriteStartingTitle = ""
      }
      if (firstSnapshot && openPanelCount > 0)
        sendCommand("session.panel_open.set", { open: true }, false, false)
      return
    }
    if (message.type === "result"
        && (Number(message.version || 0) !== 1 || String(message.id || "") === ""
            || !validRevision(message.revision) || typeof message.ok !== "boolean")) {
      setCommandError("The Sonarchy backend returned an invalid result")
      return
    }
    var resultId = String(message.id || "")
    var quietResult = message.type === "result" && quietRequestIds[resultId] === true
    if (quietResult) {
      var remainingQuiet = Object.assign({}, quietRequestIds)
      delete remainingQuiet[resultId]
      quietRequestIds = remainingQuiet
    }
    if (message.type === "result" && message.ok === false) {
      if (!quietResult) setCommandError(errorMessage(message.error))
      if (String(message.id || "") === moveRequestId) {
        moveError = commandError
        moveRequestId = ""
      }
      if (String(message.id || "") === favoriteRequestId) {
        favoriteError = "Could not start " + favoriteStartingTitle + ": "
          + errorMessage(message.error)
        favoriteRequestId = ""
        favoriteAwaitingSnapshot = false
        favoriteStartingTitle = ""
      }
    } else if (message.type === "result" && message.ok === true) {
      if (!quietResult) {
        commandError = ""
        transientErrorTimer.stop()
      }
      if (String(message.id || "") === moveRequestId) {
        moveError = ""
        moveRequestId = ""
      }
      if (String(message.id || "") === favoriteRequestId) {
        favoriteRequestId = ""
        favoriteAwaitingSnapshot = true
      }
    }
    if (message.type === "result") commandResult(message)
  }

  Process {
    id: backend
    command: [root.backendPath]
    clearEnvironment: true
    environment: root.backendEnvironment
    stdinEnabled: true

    stdout: SplitParser {
      onRead: function(line) { root.handleLine(line) }
    }

    stderr: SplitParser {
      onRead: function(line) {
        var text = String(line || "").trim()
        if (!text) return
        var marker = "SONOS_SETUP_ERROR:"
        if (text.indexOf(marker) === 0)
          root.backendStderr = text.substring(marker.length).trim()
        console.warn("Sonos backend:", text)
      }
    }

    onStarted: {
      root.backendReady = false
      root.receivedSnapshotThisRun = false
      root.backendStderr = ""
      root.quietRequestIds = ({})
    }

    onExited: function(exitCode) {
      if (root.expectedStop) return
      root.backendReady = false
      root.processError = root.backendStderr !== ""
        ? root.backendStderr
        : "Sonos backend stopped (" + exitCode + ")"
      if (root.favoriteRequestId !== "" || root.favoriteAwaitingSnapshot) {
        root.favoriteError = "Could not start " + root.favoriteStartingTitle
          + ": the Sonos backend stopped"
      }
      root.favoriteRequestId = ""
      root.favoriteAwaitingSnapshot = false
      root.favoriteStartingTitle = ""
      if (root.moveRequestId !== "") {
        root.moveError = "Could not move playback: the Sonos backend stopped"
      }
      root.moveRequestId = ""
      if (!root.receivedSnapshotThisRun && root.backendStderr !== "") {
        root.setupFailed = true
        root.setStatus("setup_error", root.processError)
        return
      }
      root.setStatus("starting", "Sonos backend stopped and will restart automatically…")
      root.restartAttempt = Math.min(root.restartAttempt + 1, 6)
      restartTimer.interval = Math.min(30000, 1000 * Math.pow(2, root.restartAttempt - 1))
      restartTimer.restart()
    }
  }

  Timer {
    id: transientErrorTimer
    interval: 10000
    repeat: false
    onTriggered: root.clearTransientErrors()
  }

  Timer {
    id: restartTimer
    repeat: false
    onTriggered: if (!root.expectedStop && !backend.running) backend.running = true
  }

  Component.onCompleted: backend.running = true
  Component.onDestruction: {
    expectedStop = true
    backend.running = false
  }
}
