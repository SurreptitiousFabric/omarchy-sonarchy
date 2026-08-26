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
  property var contentItems: []
  property var contentMeta: ({})
  property int contentTotal: 0
  property string contentKind: "favorites"
  property string contentTerm: ""
  property var alarms: []
  property bool alarmsLoading: false

  property bool detailsLoading: false
  property bool contentLoading: false
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

  property string requestError: ""
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
  property string contentRequestId: ""
  property string contentRequestRoomUid: ""
  property string contentRequestKind: ""
  property string contentRequestTerm: ""
  property string pendingContentKind: ""
  property string pendingContentTerm: ""
  property string alarmsRequestId: ""
  property string alarmsRequestRoomUid: ""

  property int queuedVolume: -1
  property string queuedVolumeGroupUid: ""

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
    }
  }

  function compactError(text, fallback) {
    var value = String(text || fallback || "Sonos request failed").replace(/\s+/g, " ").trim()
    return value.length > 180 ? value.substring(0, 177) + "…" : value
  }

  function clearError() {
    requestError = ""
    protocolRouter.stopRequestErrorTimer()
    live.clearErrors()
  }

  function setRequestError(text, fallback) {
    requestError = compactError(text, fallback)
    protocolRouter.restartRequestErrorTimer()
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
    if (!deviceForUid(uid)) return
    live.selectRoom(String(uid))
  }

  function selectSession(groupUid) {
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
    requestError = ""
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

  function syncLiveFavorites() {
    if (contentKind !== "favorites") return
    var source = liveFavorites && liveFavorites.items ? liveFavorites.items : []
    var items = []
    for (var i = 0; i < source.length; i++) {
      items.push({
        id: String(source[i].id),
        title: String(source[i].title || "Favorite"),
        subtitle: String(source[i].kind || "favorite"),
        kind: String(source[i].kind || "audio"),
        album_art: safeArtworkUrl(source[i].albumArtUrl),
        playable: true
      })
    }
    contentItems = items
    contentTotal = Number(liveFavorites.total || items.length)
    contentLoading = String(liveFavorites.state || "") === "not_loaded"
    if (String(liveFavorites.state || "") === "error")
      setRequestError(liveFavorites.error, "Could not load Sonos Favorites")
  }

  function loadContent(kind, term) {
    var nextKind = String(kind || "favorites")
    var nextTerm = String(term || "").trim()
    contentKind = nextKind
    contentTerm = nextTerm
    contentMeta = ({})

    if (nextKind === "favorites") {
      syncLiveFavorites()
      if (String(liveFavorites.state || "") === "not_loaded") {
        contentLoading = true
        live.refreshFavorites()
      }
      return
    }
    if (!selectedDevice || !live.hasCapability("content.browse")) {
      contentItems = []
      contentTotal = 0
      return
    }
    if ((nextKind === "apple" || nextKind === "global") && nextTerm === "") {
      contentItems = []
      contentTotal = 0
      contentLoading = false
      return
    }
    if (contentRequestId !== "") {
      pendingContentKind = nextKind
      pendingContentTerm = nextTerm
      return
    }

    contentLoading = true
    contentRequestRoomUid = String(selectedDevice.uid || "")
    contentRequestKind = nextKind
    contentRequestTerm = nextTerm
    var resultLimit = nextKind === "queue" ? 100 : 40
    contentRequestId = live.requestContent(
      contentRequestRoomUid, contentRequestKind, contentRequestTerm, resultLimit)
    if (contentRequestId === "") {
      contentLoading = false
      contentRequestRoomUid = ""
    }
  }

  function reloadContent() {
    if (contentKind === "favorites") {
      contentLoading = true
      live.refreshFavorites()
    } else {
      loadContent(contentKind, contentTerm)
    }
  }

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
    requestError = ""
    actionMessage = ""
    actionFallback = String(fallback || "Sonos control failed")
    protocolActionRequestId = String(requestId)
  }

  function runAction(action) {
    var device = selectedDevice
    if (!device) return

    requestError = ""
    if (action === "play-pause") {
      optimisticDevicePatch(device.ip, {
        is_playing: !device.is_playing,
        state: device.is_playing ? "PAUSED_PLAYBACK" : "PLAYING"
      })
      live.playPause()
    } else if (action === "previous") {
      live.previous()
    } else if (action === "next") {
      live.next()
    } else if (action === "mute-toggle") {
      optimisticDevicePatch(device.ip, { muted: !device.muted })
      live.setGroupMute(!device.muted)
    } else if (action === "stop") {
      if (actionBusy) return
      optimisticDevicePatch(device.ip, { is_playing: false, state: "STOPPED" })
      trackProtocolAction(live.stopRoom(String(device.uid)), "Sonos playback control failed")
      return
    } else {
      return
    }
    showActionMessage("Updated")
  }

  function seek(positionSec) {
    requestError = ""
    live.seek(Math.max(0, Math.round(Number(positionSec || 0))))
  }

  function renameRoom(name) {
    if (!selectedDevice || actionBusy) return
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
    if (!roomUids || roomUids.length === 0) return
    requestError = ""
    live.applyMembers(roomUids)
    showActionMessage("Applying room group…")
  }

  function movePlaybackToRoom(roomUid) {
    requestError = ""
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
    live.setRoomVolume(String(roomUid), Math.max(0, Math.min(100, Math.round(Number(value)))))
  }

  function adjustRoomVolume(roomUid, delta) {
    var room = roomForUid(roomUid)
    if (room) setRoomVolume(roomUid, Number(room.volume || 0) + Number(delta || 0))
  }

  function setRoomMute(roomUid, mute) {
    live.setRoomMute(String(roomUid), Boolean(mute))
  }

  function setPlaybackOption(option, value) {
    if (!selectedDevice || actionBusy) return
    trackProtocolAction(live.setPlaybackOption(
      String(selectedDevice.uid), String(option), String(value)),
      "Could not change playback option")
  }

  function setSound(setting, value) {
    if (!selectedDevice || actionBusy) return
    trackProtocolAction(live.setSound(
      String(selectedDevice.uid), String(setting), String(value)),
      "Could not change sound setting")
  }

  function setDeviceSetting(setting, value) {
    if (!selectedDevice || actionBusy) return
    trackProtocolAction(live.setDeviceSetting(
      String(selectedDevice.uid), String(setting), String(value)),
      "Could not change device setting")
  }

  function switchSource(source, sourceIp) {
    if (!selectedDevice || actionBusy) return
    var sourceRoom = String(sourceIp || "") !== "" ? roomForIp(sourceIp) : null
    if (String(sourceIp || "") !== "" && !sourceRoom) {
      setRequestError("The selected line-in room is no longer available",
                      "Could not switch Sonos source")
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
      live.playFavorite(String(item.id), String(item.title || "Favorite"))
    } else if (contentKind === "queue") {
      trackProtocolAction(live.playQueueItem(
        String(selectedDevice.uid), Number(item.index), String(item.id)),
        "Could not play queue item")
    } else if (contentKind === "apple") {
      trackProtocolAction(live.playApple(
        String(selectedDevice.uid), String(item.url)), "Could not play Apple Music result")
    } else if (contentKind === "global") {
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
    if (!item || !selectedDevice || actionBusy || String(item.album_url || "") === "") return
    trackProtocolAction(live.playAppleAlbum(
      String(selectedDevice.uid), String(item.album_url)), "Could not play Apple Music album")
  }

  function enqueueContent(item, mode) {
    if (!item || !selectedDevice || actionBusy || item.playable === false) return
    if (contentKind !== "library" && contentKind !== "playlist") return
    trackProtocolAction(live.enqueueContent(
      String(selectedDevice.uid), contentKind, contentTerm,
      String(item.id), Number(item.index || 0), String(mode)),
      "Could not add item to the Sonos queue")
  }

  function playlistAction(action, value) {
    if (!selectedDevice || actionBusy) return
    trackProtocolAction(live.mutatePlaylist(
      String(selectedDevice.uid), String(action), String(value || "")),
      "Could not update Sonos playlist")
  }

  function playlistTrackAction(action, item) {
    if (!item || !selectedDevice || actionBusy || contentKind !== "playlist") return
    trackProtocolAction(live.mutatePlaylistTrack(
      String(selectedDevice.uid), String(action), contentTerm,
      Number(item.index || 0), String(item.id)), "Could not update Sonos playlist")
  }

  function startLibraryUpdate() {
    if (selectedDevice && !actionBusy)
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
    if (String(liveFavorites.state || "") === "not_loaded") live.refreshFavorites()
  }

  function saveAlarm(editor) {
    if (!editor || !selectedDevice || actionBusy) return
    trackProtocolAction(live.saveAlarm(String(selectedDevice.uid), {
      alarmId: String(editor.id || "new"),
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
    if (selectedDevice && !actionBusy)
      trackProtocolAction(live.toggleAlarm(
        String(selectedDevice.uid), String(id), Boolean(enabled)),
        "Could not change Sonos alarm")
  }

  function deleteAlarm(id) {
    if (selectedDevice && !actionBusy)
      trackProtocolAction(live.deleteAlarm(String(selectedDevice.uid), String(id)),
                          "Could not delete Sonos alarm")
  }

  function removeQueueItem(index, itemId) {
    if (selectedDevice && !actionBusy)
      trackProtocolAction(live.removeQueueItem(
        String(selectedDevice.uid), Number(index), String(itemId)),
        "Could not remove queue item")
  }

  function clearQueue() {
    if (selectedDevice && !actionBusy)
      trackProtocolAction(live.clearQueue(String(selectedDevice.uid)),
                          "Could not clear Sonos queue")
  }

  function requestVolume(value) {
    var device = selectedDevice
    if (!device || !target) return
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
