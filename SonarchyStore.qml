import QtQuick

Item {
  id: root

  property var shell: null

  readonly property var liveSnapshot: live.snapshot
  readonly property var connectionStatus: liveSnapshot && liveSnapshot.status
    ? liveSnapshot.status : ({ state: "starting", message: "Starting Sonos controller…" })
  readonly property var target: liveSnapshot ? liveSnapshot.target : null
  readonly property var livePlayback: liveSnapshot && liveSnapshot.playback
    ? liveSnapshot.playback : ({})
  readonly property var liveFavorites: liveSnapshot && liveSnapshot.favorites
    ? liveSnapshot.favorites : ({ state: "not_loaded", items: [], total: 0, unsupported: 0, error: "" })
  readonly property var households: liveSnapshot && liveSnapshot.households
    ? liveSnapshot.households : []
  readonly property bool ready: live.ready
  readonly property bool loading: {
    var state = String(connectionStatus.state || "")
    return !live.backendReady || state === "starting" || state === "discovering"
  }

  property var devices: []
  property var details: ({})
  property alias contentItems: contentState.items
  property alias contentMeta: contentState.meta
  property alias contentTotal: contentState.total
  property alias contentKind: contentState.kind
  property alias contentTerm: contentState.term
  property alias contentPath: contentState.path
  property alias contentOffset: contentState.offset
  property var alarms: []
  property bool alarmsLoading: false

  property bool detailsLoading: false
  property alias contentLoading: contentState.loading
  property bool panelOpen: false
  property bool radioArtworkEnrichmentEnabled: false
  property alias artworkCache: artwork.cache
  property alias artworkCacheOrder: artwork.cacheOrder
  property alias artworkRequestId: artwork.requestId
  property alias artworkRequestKey: artwork.requestKey
  property alias artworkRequestTitle: artwork.requestTitle
  property alias artworkRequestArtist: artwork.requestArtist
  readonly property alias artworkCacheLimit: artwork.cacheLimit
  readonly property bool actionBusy: protocolActionRequestId !== ""
    || live.favoriteRequestId !== "" || live.favoriteAwaitingSnapshot
    || live.moveRequestId !== ""

  readonly property alias requestError: requestErrorState.message
  readonly property alias requestErrorRequestId: requestErrorState.ownerId
  readonly property string lastError: requestError !== "" ? requestError
    : (String(live.moveError || "") !== "" ? String(live.moveError)
       : (String(live.favoriteError || "") !== "" ? String(live.favoriteError)
          : String(live.lastError || "")))
  property string actionMessage: ""
  property string actionFallback: "Sonos control failed"
  property string protocolActionRequestId: ""
  property bool detailsQueued: false

  property string detailsRequestId: ""
  property string detailsRequestRoomUid: ""
  property alias contentRequestId: contentState.requestId
  property alias contentRequestRoomUid: contentState.requestRoomUid
  property alias contentRequestKind: contentState.requestKind
  property alias contentRequestTerm: contentState.requestTerm
  property alias contentRequestContextKey: contentState.requestContextKey
  property alias pendingContentKind: contentState.pendingKind
  property alias pendingContentTerm: contentState.pendingTerm
  property alias pendingContentPath: contentState.pendingPath
  property alias pendingContentOffset: contentState.pendingOffset
  property string alarmsRequestId: ""
  property string alarmsRequestRoomUid: ""

  property int queuedVolume: -1
  property string queuedVolumeGroupUid: ""

  SonarchyErrorState {
    id: requestErrorState
  }

  SonarchyContentState {
    id: contentState
    store: root
    live: live
  }

  readonly property var selectedDevice: {
    var selectedUid = String(liveSnapshot ? liveSnapshot.selectedAnchorRoomUid || "" : "")
    for (var i = 0; i < devices.length; i++) {
      if (String(devices[i].uid) === selectedUid) return devices[i]
    }
    return devices.length > 0 ? devices[0] : null
  }
  readonly property string selectedIp: selectedDevice ? String(selectedDevice.ip) : ""
  readonly property var playbackDetails: details && details.playback ? details.playback : ({})
  readonly property var soundDetails: details && details.sound ? details.sound : ({})
  readonly property var deviceDetails: details && details.device ? details.device : ({})
  readonly property bool hasDevices: devices.length > 0
  readonly property bool anyPlaying: {
    for (var i = 0; i < devices.length; i++) {
      if (devices[i].is_playing === true) return true
    }
    return false
  }
  readonly property var activeHousehold: {
    if (!target) return null
    for (var i = 0; i < households.length; i++) {
      if (String(households[i].id) === String(target.householdId)) return households[i]
    }
    return null
  }
  readonly property var rooms: activeHousehold && activeHousehold.rooms
    ? activeHousehold.rooms : []
  readonly property var groups: activeHousehold && activeHousehold.groups
    ? activeHousehold.groups : []
  readonly property var sessions: {
    var result = []
    for (var h = 0; h < households.length; h++) {
      var household = households[h]
      var householdGroups = household.groups || []
      for (var g = 0; g < householdGroups.length; g++) {
        var group = householdGroups[g]
        result.push({
          uid: String(group.uid),
          label: String(group.label || "Sonos"),
          householdId: String(household.id || ""),
          playbackState: String(group.playbackState || "STOPPED"),
          volume: Number(group.volume || 0),
          mute: group.mute === true,
          memberUids: group.memberUids || []
        })
      }
    }
    return result
  }

  onSelectedIpChanged: {
    details = ({})
    if (contentKind === "library") {
      contentItems = []
      contentTotal = 0
      contentMeta = ({})
      contentTerm = ""
      contentPath = []
      contentOffset = 0
    }
    if (selectedIp === "" || contentKind === "queue") {
      if (contentKind !== "favorites") {
        contentItems = []
        contentTotal = 0
      }
    }
    if (selectedIp !== "" && panelOpen) {
      Qt.callLater(root.refreshDetails)
      if (contentKind === "queue")
        Qt.callLater(function() { root.loadContent("queue", "") })
      else if (contentKind === "library")
        Qt.callLater(function() { root.loadContent("library", "", [], 0) })
    }
  }

  function clearError() {
    clearRequestError()
    protocolRouter.stopRequestErrorTimer()
    live.clearErrors()
  }

  function hasCapability(name) {
    return live.hasCapability(String(name || ""))
  }

  function requireCapability(name) {
    if (hasCapability(name)) return true
    setRequestError("This Sonos action is not available right now",
                    "Sonos action unavailable", "local", true)
    return false
  }

  function setRequestError(text, fallback, requestId, replaceExisting) {
    if (!requestErrorState.setError(text, fallback, requestId, replaceExisting)) return false
    protocolRouter.restartRequestErrorTimer()
    return true
  }

  function clearRequestError(requestId) {
    if (!requestErrorState.clearError(requestId)) return false
    protocolRouter.stopRequestErrorTimer()
    return true
  }

  function formatTime(value) {
    if (value === null || value === undefined || value === "") return ""
    var total = Math.max(0, Math.floor(Number(value)))
    if (!isFinite(total)) return ""
    var hours = Math.floor(total / 3600)
    var minutes = Math.floor((total % 3600) / 60)
    var seconds = total % 60
    var mm = (hours > 0 && minutes < 10 ? "0" : "") + minutes
    var ss = (seconds < 10 ? "0" : "") + seconds
    return hours > 0 ? hours + ":" + mm + ":" + ss : minutes + ":" + ss
  }

  function groupForRoom(uid, household) {
    var source = household && household.groups ? household.groups : []
    for (var i = 0; i < source.length; i++) {
      var members = source[i].memberUids || []
      if (members.indexOf(String(uid)) !== -1) return source[i]
    }
    return null
  }

  function roomForUid(uid) {
    for (var h = 0; h < households.length; h++) {
      var householdRooms = households[h].rooms || []
      for (var r = 0; r < householdRooms.length; r++) {
        if (String(householdRooms[r].uid) === String(uid || "")) return householdRooms[r]
      }
    }
    return null
  }

  function roomForIp(ip) {
    for (var i = 0; i < devices.length; i++) {
      if (String(devices[i].ip) === String(ip || "")) return devices[i]
    }
    return null
  }

  function radioArtworkKey(playback) {
    return artwork.radioKey(playback)
  }

  function hasArtworkCacheEntry(key) {
    return artwork.hasCacheEntry(key)
  }

  function cacheArtwork(key, url) {
    artwork.putCache(key, url)
  }

  function artworkForPlayback(playback) {
    return artwork.forPlayback(playback)
  }

  function maybeRequestRadioArtwork() {
    artwork.maybeRequest()
  }

  function applyLiveSnapshot() {
    var next = []
    var selectedGroupUid = target ? String(target.groupUid || "") : ""
    var playback = livePlayback || ({})
    var targetArtwork = artworkForPlayback(playback)

    for (var h = 0; h < households.length; h++) {
      var household = households[h]
      var householdRooms = household.rooms || []
      for (var r = 0; r < householdRooms.length; r++) {
        var room = householdRooms[r]
        var group = groupForRoom(room.uid, household)
        var memberUids = group && group.memberUids ? group.memberUids : [room.uid]
        var members = []
        var coordinatorIp = ""
        for (var m = 0; m < memberUids.length; m++) {
          var member = null
          for (var x = 0; x < householdRooms.length; x++) {
            if (String(householdRooms[x].uid) === String(memberUids[m])) {
              member = householdRooms[x]
              break
            }
          }
          if (!member) continue
          if (group && String(member.uid) === String(group.coordinatorUid))
            coordinatorIp = String(member.ip || "")
          members.push({
            uid: String(member.uid),
            name: String(member.name || member.ip || "Sonos"),
            ip: String(member.ip || ""),
            is_coordinator: group && String(member.uid) === String(group.coordinatorUid)
          })
        }

        var isTarget = group && String(group.uid) === selectedGroupUid
        var state = String(group ? group.playbackState : room.playbackState || "STOPPED")
        next.push({
          uid: String(room.uid),
          name: String(room.name || room.ip || "Sonos"),
          ip: String(room.ip || ""),
          model: "",
          volume: isTarget ? Number(group.volume || 0) : Number(room.volume || 0),
          room_volume: Number(room.volume || 0),
          muted: isTarget ? group.mute === true : room.mute === true,
          room_muted: room.mute === true,
          line_in_available: room.lineInAvailable === true,
          state: state,
          is_playing: state === "PLAYING" || state === "TRANSITIONING",
          group_uid: group ? String(group.uid) : "",
          coordinator_uid: group ? String(group.coordinatorUid) : String(room.uid),
          coordinator_ip: coordinatorIp || String(room.ip || ""),
          group_label: group ? String(group.label || room.name || "Sonos") : String(room.name || "Sonos"),
          group_members: members,
          title: isTarget ? String(playback.title || "") : "",
          artist: isTarget ? String(playback.artist || "") : "",
          album: isTarget ? String(playback.album || "") : "",
          album_art: isTarget ? targetArtwork : "",
          position: isTarget ? formatTime(playback.positionSec) : "",
          duration: isTarget ? formatTime(playback.durationSec) : ""
        })
      }
    }
    devices = next
    if (contentKind === "favorites") syncLiveFavorites()
    maybeRequestRadioArtwork()
  }

  function safeArtworkUrl(url) {
    return artwork.safeUrl(url)
  }

  function deviceForUid(uid) {
    for (var i = 0; i < devices.length; i++) {
      if (String(devices[i].uid) === String(uid || "")) return devices[i]
    }
    return null
  }

  function roomOptions() {
    var options = []
    for (var i = 0; i < devices.length; i++) {
      var device = devices[i]
      var suffix = device.group_members && device.group_members.length > 1
        ? "  ·  " + device.group_members.length + " rooms" : ""
      options.push({
        value: String(device.uid),
        label: String(device.name || device.ip) + suffix
      })
    }
    return options
  }

  function selectDevice(uid) {
    if (!deviceForUid(uid) || !requireCapability("selection.room.set")) return
    live.selectRoom(String(uid))
  }

  function selectSession(groupUid) {
    if (!requireCapability("selection.group.set")) return
    live.selectGroup(String(groupUid))
  }

  function setPanelOpen(open) {
    panelOpen = Boolean(open)
    live.setPanelOpen(panelOpen)
    if (panelOpen) {
      refreshDetails()
      if (contentKind === "favorites" || contentKind === "queue")
        loadContent(contentKind, "")
      Qt.callLater(maybeRequestRadioArtwork)
    }
  }

  onRadioArtworkEnrichmentEnabledChanged: {
    applyLiveSnapshot()
    if (radioArtworkEnrichmentEnabled) Qt.callLater(maybeRequestRadioArtwork)
  }

  function refresh() {
    clearRequestError()
    live.refresh()
  }

  function refreshDetails() {
    if (!selectedDevice || !live.hasCapability("devices.details.get")) return
    if (detailsRequestId !== "") {
      detailsQueued = true
      return
    }
    detailsLoading = true
    detailsRequestRoomUid = String(selectedDevice.uid || "")
    detailsRequestId = live.requestDeviceDetails(detailsRequestRoomUid)
    if (detailsRequestId === "") {
      detailsLoading = false
      detailsRequestRoomUid = ""
    }
  }

  function syncLiveFavorites() { contentState.syncFavorites() }
  function loadContent(kind, term, path, offset) {
    contentState.load(kind, term, path, offset)
  }
  function prepareContentSearch(kind) { contentState.prepareSearch(kind) }
  function reloadContent() { contentState.reload() }
  function openLibraryItem(item) { contentState.openLibraryItem(item) }
  function libraryBack() { contentState.libraryBack() }
  function libraryPage(offset) { contentState.libraryPage(offset) }
  function contentContextKey() { return contentState.currentContextKey() }

  function optimisticDevicePatch(ip, patch) {
    var next = []
    for (var i = 0; i < devices.length; i++) {
      var device = devices[i]
      if (String(device.ip) === String(ip)) next.push(Object.assign({}, device, patch))
      else next.push(device)
    }
    devices = next
  }

  function showActionMessage(message) {
    actionMessage = String(message || "Updated")
    protocolRouter.restartActionMessageTimer()
  }

  function trackProtocolAction(requestId, fallback) {
    if (String(requestId || "") === "") return
    clearRequestError()
    actionMessage = ""
    actionFallback = String(fallback || "Sonos control failed")
    protocolActionRequestId = String(requestId)
  }

  function runAction(action) {
    var device = selectedDevice
    if (!device) return

    clearRequestError()
    if (action === "play-pause") {
      if (!requireCapability("playback.toggle")) return
      optimisticDevicePatch(device.ip, {
        is_playing: !device.is_playing,
        state: device.is_playing ? "PAUSED_PLAYBACK" : "PLAYING"
      })
      live.playPause()
    } else if (action === "previous") {
      if (!requireCapability("playback.previous")) return
      live.previous()
    } else if (action === "next") {
      if (!requireCapability("playback.next")) return
      live.next()
    } else if (action === "mute-toggle") {
      if (!requireCapability("mute.group.set")) return
      optimisticDevicePatch(device.ip, { muted: !device.muted })
      live.setGroupMute(!device.muted)
    } else if (action === "stop") {
      if (actionBusy || !requireCapability("playback.stop")) return
      optimisticDevicePatch(device.ip, { is_playing: false, state: "STOPPED" })
      trackProtocolAction(live.stopRoom(String(device.uid)), "Sonos playback control failed")
      return
    } else {
      return
    }
    showActionMessage("Updated")
  }

  function seek(positionSec) {
    if (!requireCapability("playback.seek")) return
    clearRequestError()
    live.seek(Math.max(0, Math.round(Number(positionSec || 0))))
  }

  function renameRoom(name) {
    if (!selectedDevice || actionBusy || !requireCapability("devices.rename")) return
    trackProtocolAction(live.renameRoom(String(selectedDevice.uid), String(name || "")),
                        "Could not rename Sonos room")
  }

  function setGrouped(memberIp, grouped) {
    var member = roomForIp(memberIp)
    if (!member || !target) return
    var desired = target.memberUids ? target.memberUids.slice() : []
    var index = desired.indexOf(String(member.uid))
    if (grouped && index === -1) desired.push(String(member.uid))
    if (!grouped && index !== -1 && desired.length > 1) desired.splice(index, 1)
    applyMembers(desired)
  }

  function groupAll() {
    var desired = []
    for (var i = 0; i < rooms.length; i++) desired.push(String(rooms[i].uid))
    applyMembers(desired)
  }

  function separateRoom() {
    if (selectedDevice) applyMembers([String(selectedDevice.uid)])
  }

  function applyMembers(roomUids) {
    if (!roomUids || roomUids.length === 0
        || !requireCapability("topology.members.set")) return
    clearRequestError()
    live.applyMembers(roomUids)
    showActionMessage("Applying room group…")
  }

  function movePlaybackToRoom(roomUid) {
    if (!requireCapability("playback.room.move")) return
    clearRequestError()
    live.movePlaybackToRoom(String(roomUid))
  }

  function roomMoveBlocked(roomUid) {
    if (!target) return true
    var state = String(livePlayback.state || "").toUpperCase()
    if (state !== "PLAYING" && state !== "TRANSITIONING") return false
    if (target.memberUids && target.memberUids.length > 1)
      return target.memberUids.indexOf(String(roomUid)) === -1
    for (var i = 0; i < groups.length; i++) {
      var members = groups[i].memberUids || []
      if (members.indexOf(String(roomUid)) !== -1 && members.length > 1) return true
    }
    return false
  }

  function setRoomVolume(roomUid, value) {
    if (!requireCapability("volume.room.set")) return
    live.setRoomVolume(String(roomUid), Math.max(0, Math.min(100, Math.round(Number(value)))))
  }

  function adjustRoomVolume(roomUid, delta) {
    var room = roomForUid(roomUid)
    if (room) setRoomVolume(roomUid, Number(room.volume || 0) + Number(delta || 0))
  }

  function setRoomMute(roomUid, mute) {
    if (!requireCapability("mute.room.set")) return
    live.setRoomMute(String(roomUid), Boolean(mute))
  }

  function setPlaybackOption(option, value) {
    if (!selectedDevice || actionBusy
        || !requireCapability("playback.option.set")) return
    trackProtocolAction(live.setPlaybackOption(
      String(selectedDevice.uid), String(option), String(value)),
      "Could not change playback option")
  }

  function setSound(setting, value) {
    if (!selectedDevice || actionBusy || !requireCapability("sound.setting.set")) return
    trackProtocolAction(live.setSound(
      String(selectedDevice.uid), String(setting), String(value)),
      "Could not change sound setting")
  }

  function setDeviceSetting(setting, value) {
    if (!selectedDevice || actionBusy
        || !requireCapability("devices.setting.set")) return
    trackProtocolAction(live.setDeviceSetting(
      String(selectedDevice.uid), String(setting), String(value)),
      "Could not change device setting")
  }

  function switchSource(source, sourceRoomUid) {
    if (!selectedDevice || actionBusy || !requireCapability("sources.switch")) return
    var sourceRoom = String(sourceRoomUid || "") !== "" ? deviceForUid(sourceRoomUid) : null
    if (String(sourceRoomUid || "") !== "" && (!sourceRoom || sourceRoom.line_in_available !== true)) {
      setRequestError("The selected line-in room is no longer available",
                      "Could not switch Sonos source", "local", true)
      return
    }
    trackProtocolAction(live.switchSource(
      String(selectedDevice.uid), String(source), sourceRoom ? String(sourceRoom.uid) : ""),
      "Could not switch Sonos source")
  }

  function playContent(item) {
    if (!item || !selectedDevice || item.playable === false) return
    if (contentKind !== "favorites" && actionBusy) return
    if (contentKind === "favorites") {
      if (!requireCapability("content.favorite.play")) return
      live.playFavorite(String(item.id), String(item.title || "Favorite"))
    } else if (contentKind === "queue") {
      if (!requireCapability("queue.item.play")) return
      trackProtocolAction(live.playQueueItem(
        String(selectedDevice.uid), Number(item.index), String(item.id)),
        "Could not play queue item")
    } else if (contentKind === "apple") {
      if (!requireCapability("content.apple.play")) return
      trackProtocolAction(live.playApple(
        String(selectedDevice.uid), String(item.url)), "Could not play Apple Music result")
    } else if (contentKind === "global") {
      if (!requireCapability("content.global.play")) return
      trackProtocolAction(live.playGlobal(
        String(selectedDevice.uid), String(item.id), contentTerm),
        "Could not play Global Player result")
    } else if (contentKind === "library" || contentKind === "playlist") {
      enqueueContent(item, "play")
    } else if (contentKind === "playlists") {
      loadContent("playlist", String(item.id))
    }
  }

  function playAppleAlbum(item) {
    if (!item || !selectedDevice || actionBusy || String(item.album_url || "") === ""
        || !requireCapability("content.apple.album.play")) return
    trackProtocolAction(live.playAppleAlbum(
      String(selectedDevice.uid), String(item.album_url)), "Could not play Apple Music album")
  }

  function enqueueContent(item, mode) {
    if (!item || !selectedDevice || actionBusy || item.playable === false) return
    if (contentKind !== "library" && contentKind !== "playlist") return
    if (!requireCapability("queue.content.enqueue")) return
    trackProtocolAction(live.enqueueContent(
      String(selectedDevice.uid), contentKind, contentTerm,
      String(item.id), Number(item.index || 0), String(mode), contentPath),
      "Could not add item to the Sonos queue")
  }

  function playlistAction(action, value) {
    if (!selectedDevice || actionBusy || !requireCapability("playlists.mutate")) return
    trackProtocolAction(live.mutatePlaylist(
      String(selectedDevice.uid), String(action), String(value || "")),
      "Could not update Sonos playlist")
  }

  function playlistTrackAction(action, item) {
    if (!item || !selectedDevice || actionBusy || contentKind !== "playlist") return
    if (!requireCapability("playlists.track.mutate")) return
    trackProtocolAction(live.mutatePlaylistTrack(
      String(selectedDevice.uid), String(action), contentTerm,
      Number(item.index || 0), String(item.id)), "Could not update Sonos playlist")
  }

  function startLibraryUpdate() {
    if (selectedDevice && !actionBusy && requireCapability("library.update.start"))
      trackProtocolAction(live.startLibraryUpdate(String(selectedDevice.uid)),
                          "Could not update the music library")
  }

  function loadAlarms() {
    if (!selectedDevice || alarmsRequestId !== ""
        || !live.hasCapability("alarms.list")) return
    alarmsLoading = true
    alarmsRequestRoomUid = String(selectedDevice.uid || "")
    alarmsRequestId = live.requestAlarms(alarmsRequestRoomUid)
    if (alarmsRequestId === "") {
      alarmsLoading = false
      alarmsRequestRoomUid = ""
    }
  }

  function ensureFavorites() {
    if (String(liveFavorites.state || "") === "not_loaded"
        && hasCapability("content.favorites.refresh")) live.refreshFavorites()
  }

  function saveAlarm(editor) {
    if (!editor || !selectedDevice || actionBusy || !requireCapability("alarms.save")) return
    trackProtocolAction(live.saveAlarm(String(selectedDevice.uid), {
      alarmId: String(editor.id || "new"),
      alarmRoomUid: String(editor.roomUid || ""),
      time: String(editor.time || "07:00"),
      recurrence: String(editor.recurrence || "DAILY"),
      volume: Math.round(Number(editor.volume || 0)),
      duration: Math.round(Number(editor.duration || 0)),
      enabled: editor.enabled !== false,
      includeGrouped: editor.includeGrouped === true,
      program: String(editor.program || "chime")
    }), "Could not save Sonos alarm")
  }

  function toggleAlarm(id, enabled) {
    if (selectedDevice && !actionBusy && requireCapability("alarms.toggle"))
      trackProtocolAction(live.toggleAlarm(
        String(selectedDevice.uid), String(id), Boolean(enabled)),
        "Could not change Sonos alarm")
  }

  function deleteAlarm(id) {
    if (selectedDevice && !actionBusy && requireCapability("alarms.delete"))
      trackProtocolAction(live.deleteAlarm(String(selectedDevice.uid), String(id)),
                          "Could not delete Sonos alarm")
  }

  function removeQueueItem(index, itemId) {
    if (selectedDevice && !actionBusy && requireCapability("queue.item.remove"))
      trackProtocolAction(live.removeQueueItem(
        String(selectedDevice.uid), Number(index), String(itemId)),
        "Could not remove queue item")
  }

  function clearQueue() {
    if (selectedDevice && !actionBusy && requireCapability("queue.clear"))
      trackProtocolAction(live.clearQueue(String(selectedDevice.uid)),
                          "Could not clear Sonos queue")
  }

  function requestVolume(value) {
    var device = selectedDevice
    if (!device || !target || !requireCapability("volume.group.set")) return
    var volume = Math.max(0, Math.min(100, Math.round(Number(value))))
    queuedVolume = volume
    queuedVolumeGroupUid = String(target.groupUid || "")
    optimisticDevicePatch(device.ip, { volume: volume })
    protocolRouter.restartVolumeDebounce()
  }

  function adjustVolume(delta) {
    var base = target ? Number(target.volume || 0)
      : (selectedDevice ? Number(selectedDevice.volume || 0) : 0)
    requestVolume(base + Number(delta || 0))
  }

  function flushVolume() {
    if (queuedVolume < 0 || !target
        || queuedVolumeGroupUid !== String(target.groupUid || "")) {
      queuedVolume = -1
      queuedVolumeGroupUid = ""
      return
    }
    var value = queuedVolume
    queuedVolume = -1
    queuedVolumeGroupUid = ""
    live.setGroupVolume(value)
  }

  SonarchyArtwork {
    id: artwork
    store: root
    live: live
  }

  LiveService {
    id: live
    shell: root.shell
  }

  SonarchyProtocolRouter {
    id: protocolRouter
    store: root
    live: live
  }

  Component.onCompleted: applyLiveSnapshot()
}
