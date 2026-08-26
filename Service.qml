import QtQuick
import Quickshell
import Quickshell.Io

Item {
  id: root

  property var shell: null

  readonly property string dataHome: Quickshell.env("XDG_DATA_HOME") !== ""
    ? Quickshell.env("XDG_DATA_HOME") : Quickshell.env("HOME") + "/.local/share"
  readonly property string pythonPath: dataHome + "/sonarchy/venv/bin/python"
  readonly property string helperPath: localPath(Qt.resolvedUrl("sonarchy_bridge.py"))
  readonly property var helperEnvironment: ({
    HOME: Quickshell.env("HOME"),
    LANG: Quickshell.env("LANG") || "C.UTF-8",
    SONARCHY_APPLE_COUNTRY: Quickshell.env("SONARCHY_APPLE_COUNTRY"),
    OMARCHY_SONOS_APPLE_COUNTRY: Quickshell.env("OMARCHY_SONOS_APPLE_COUNTRY"),
    XDG_CACHE_HOME: Quickshell.env("XDG_CACHE_HOME"),
    XDG_DATA_HOME: Quickshell.env("XDG_DATA_HOME"),
    XDG_STATE_HOME: Quickshell.env("XDG_STATE_HOME")
  })

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
  property var artworkCache: ({})
  property var artworkCacheOrder: []
  property string artworkRequestId: ""
  property string artworkRequestKey: ""
  property string artworkRequestTitle: ""
  property string artworkRequestArtist: ""
  property string artworkDiagnosticKey: ""
  readonly property int artworkCacheLimit: 128
  readonly property bool actionBusy: actionProcess.running || protocolActionRequestId !== ""
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

  function localPath(url) {
    var text = String(url || "")
    if (text.indexOf("file://") === 0) text = text.substring(7)
    return decodeURIComponent(text)
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
    requestErrorTimer.stop()
    live.clearErrors()
  }

  function setRequestError(text, fallback) {
    requestError = compactError(text, fallback)
    requestErrorTimer.restart()
  }

  function parsePayload(raw) {
    try {
      var value = String(raw || "").trim()
      return value === "" ? null : JSON.parse(value)
    } catch (error) {
      return null
    }
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
    if (!playback) return ""
    var state = String(playback.state || "").toUpperCase()
    var source = String(playback.source || "").toUpperCase()
    var title = String(playback.title || "").trim()
    var artist = String(playback.artist || "").trim()
    if (source !== "RADIO" || title === "" || artist === ""
        || (state !== "PLAYING" && state !== "PAUSED_PLAYBACK"
            && state !== "TRANSITIONING")) return ""
    return source + "\u001f" + title.toLocaleLowerCase()
      + "\u001f" + artist.toLocaleLowerCase()
  }

  function hasArtworkCacheEntry(key) {
    return key !== "" && Object.prototype.hasOwnProperty.call(artworkCache, key)
  }

  function cacheArtwork(key, url) {
    if (key === "") return
    var next = Object.assign({}, artworkCache)
    next[key] = String(url || "")
    var order = []
    for (var i = 0; i < artworkCacheOrder.length; i++) {
      if (String(artworkCacheOrder[i]) !== key) order.push(String(artworkCacheOrder[i]))
    }
    order.push(key)
    while (order.length > artworkCacheLimit) {
      var oldest = order.shift()
      delete next[oldest]
    }
    artworkCache = next
    artworkCacheOrder = order
  }

  function artworkForPlayback(playback) {
    var supplied = safeArtworkUrl(playback ? playback.artworkUrl : "")
    if (!radioArtworkEnrichmentEnabled
        || String(playback ? playback.artworkKind || "" : "") === "track") return supplied
    var key = radioArtworkKey(playback)
    if (hasArtworkCacheEntry(key)) {
      var enriched = safeArtworkUrl(artworkCache[key])
      if (enriched !== "") return enriched
    }
    return supplied
  }

  function maybeRequestRadioArtwork() {
    if (!radioArtworkEnrichmentEnabled || !panelOpen || artworkRequestId !== ""
        || !live.hasCapability("artwork.radio.resolve")) return
    var playback = livePlayback || ({})
    if (String(playback.artworkKind || "") === "track") return
    var key = radioArtworkKey(playback)
    if (key === "" || hasArtworkCacheEntry(key)) return
    artworkRequestKey = key
    artworkRequestTitle = String(playback.title || "")
    artworkRequestArtist = String(playback.artist || "")
    artworkRequestId = live.requestRadioArtwork(artworkRequestTitle, artworkRequestArtist)
  }

  function applyLiveSnapshot() {
    var next = []
    var selectedGroupUid = target ? String(target.groupUid || "") : ""
    var playback = livePlayback || ({})
    var targetArtwork = artworkForPlayback(playback)
    var diagnosticKey = [
      String(playback.state || ""), String(playback.source || ""),
      String(playback.artworkKind || ""), targetArtwork !== "",
      radioArtworkEnrichmentEnabled, panelOpen
    ].join("|")
    if (diagnosticKey !== artworkDiagnosticKey) {
      console.warn("SONARCHY_ARTWORK_STATE", diagnosticKey)
      artworkDiagnosticKey = diagnosticKey
    }

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
    var value = String(url || "").trim()
    if (value.indexOf("https://") === 0) {
      var match = value.match(/^https:\/\/([^\/?#]+)(?:[\/?#]|$)/i)
      if (!match || match[1].indexOf("@") !== -1) return ""
      var authorityParts = String(match[1]).split(":")
      if (authorityParts.length > 2
          || (authorityParts.length === 2 && authorityParts[1] !== "443")) return ""
      var host = authorityParts[0].toLowerCase().replace(/\.$/, "")
      var suffixes = [
        "mzstatic.com", "scdn.co", "tunein.com", "radiotime.com",
        "globalplayer.com", "thisisglobal.com", "radioplayer.cloud"
      ]
      var exactHosts = ["static.mytuner-radio.net"]
      for (var e = 0; e < exactHosts.length; e++) {
        if (host === exactHosts[e]) return value
      }
      for (var h = 0; h < suffixes.length; h++) {
        if (host === suffixes[h] || host.endsWith("." + suffixes[h])) return value
      }
      return ""
    }
    if (value.indexOf("http://") !== 0) return ""
    for (var i = 0; i < devices.length; i++) {
      var prefix = "http://" + String(devices[i].ip || "") + ":1400/"
      if (value.indexOf(prefix) === 0) return value
    }
    // The first snapshot is already sanitized by the backend, before devices
    // have been projected into the compatibility model.
    return devices.length === 0 ? value : ""
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
    actionMessageTimer.restart()
  }

  function startAction(args, fallback) {
    if (!selectedDevice || actionBusy) return
    requestError = ""
    actionMessage = ""
    actionFallback = String(fallback || "Sonos control failed")
    actionProcess.command = [pythonPath, "-B", helperPath].concat(args)
    actionProcess.running = true
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
    if (!item || selectedIp === "" || item.playable === false) return
    if (contentKind === "favorites") {
      live.playFavorite(String(item.id), String(item.title || "Favorite"))
    } else if (contentKind === "queue") {
      startAction(["play-queue", selectedIp, String(item.index), String(item.id)],
                  "Could not play queue item")
    } else if (contentKind === "apple") {
      startAction(["play-apple", selectedIp, String(item.url)], "Could not play Apple Music result")
    } else if (contentKind === "global") {
      startAction(["play-global", selectedIp, String(item.id), contentTerm],
                  "Could not play Global Player result")
    } else if (contentKind === "library" || contentKind === "playlist") {
      enqueueContent(item, "play")
    } else if (contentKind === "playlists") {
      loadContent("playlist", String(item.id))
    }
  }

  function playAppleAlbum(item) {
    if (!item || selectedIp === "" || String(item.album_url || "") === "") return
    startAction(["play-apple-album", selectedIp, String(item.album_url)],
                "Could not play Apple Music album")
  }

  function enqueueContent(item, mode) {
    if (!item || selectedIp === "" || item.playable === false) return
    if (contentKind !== "library" && contentKind !== "playlist") return
    startAction([
      "queue-content", selectedIp, contentKind, contentTerm,
      String(item.id), String(Number(item.index || 0)), String(mode)
    ], "Could not add item to the Sonos queue")
  }

  function playlistAction(action, value) {
    if (selectedIp === "") return
    startAction(["playlist", selectedIp, String(action), String(value || "")],
                "Could not update Sonos playlist")
  }

  function playlistTrackAction(action, item) {
    if (!item || selectedIp === "" || contentKind !== "playlist") return
    startAction([
      "playlist-track", selectedIp, String(action), contentTerm,
      String(Number(item.index || 0)), String(item.id)
    ], "Could not update Sonos playlist")
  }

  function startLibraryUpdate() {
    if (selectedIp !== "")
      startAction(["library-update", selectedIp], "Could not update the music library")
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
    if (!editor || selectedIp === "") return
    startAction([
      "alarm-save", selectedIp, String(editor.id || "new"),
      String(editor.time || "07:00"), String(editor.recurrence || "DAILY"),
      String(Math.round(Number(editor.volume || 0))),
      String(Math.round(Number(editor.duration || 0))),
      editor.enabled === false ? "off" : "on",
      editor.includeGrouped === true ? "on" : "off",
      String(editor.program || "chime")
    ], "Could not save Sonos alarm")
  }

  function toggleAlarm(id, enabled) {
    if (selectedIp !== "")
      startAction(["alarm-toggle", selectedIp, String(id), enabled ? "on" : "off"],
                  "Could not change Sonos alarm")
  }

  function deleteAlarm(id) {
    if (selectedIp !== "")
      startAction(["alarm-delete", selectedIp, String(id)], "Could not delete Sonos alarm")
  }

  function removeQueueItem(index, itemId) {
    if (selectedIp !== "")
      startAction(["remove-queue", selectedIp, String(index), String(itemId)],
                  "Could not remove queue item")
  }

  function clearQueue() {
    if (selectedIp !== "")
      startAction(["clear-queue", selectedIp], "Could not clear Sonos queue")
  }

  function requestVolume(value) {
    var device = selectedDevice
    if (!device || !target) return
    var volume = Math.max(0, Math.min(100, Math.round(Number(value))))
    queuedVolume = volume
    queuedVolumeGroupUid = String(target.groupUid || "")
    optimisticDevicePatch(device.ip, { volume: volume })
    volumeDebounce.restart()
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

  function processFailure(stdout, stderr, fallback) {
    var payload = parsePayload(stdout)
    setRequestError(payload && payload.error ? payload.error : stderr || stdout, fallback)
  }

  LiveService {
    id: live
    shell: root.shell
  }

  Connections {
    target: live
    function onSnapshotChanged() { root.applyLiveSnapshot() }
    function onCommandResult(message) {
      if (String(message.id || "") === root.protocolActionRequestId) {
        var actionPayload = message.ok === true ? message.value : null
        var completedAction = String(actionPayload && actionPayload.action || "")
        root.protocolActionRequestId = ""
        if (!actionPayload || actionPayload.ok !== true) {
          root.setRequestError(live.errorMessage(message.error), root.actionFallback)
        } else {
          root.requestError = ""
          root.showActionMessage(String(actionPayload.message || "Updated"))
          if (completedAction === "rename") {
            root.optimisticDevicePatch(
              root.selectedIp, { name: String(actionPayload.name || "") })
            renameRefresh.restart()
          }
        }
        if (completedAction !== "rename" || !actionPayload || actionPayload.ok !== true)
          delayedRefresh.restart()
        return
      }
      if (String(message.id || "") === root.artworkRequestId) {
        var completedKey = root.artworkRequestKey
        var payload = message.ok === true ? message.value : null
        var artworkUrl = ""
        if (payload && payload.ok === true && payload.match === true)
          artworkUrl = root.safeArtworkUrl(payload.artwork_url)
        root.cacheArtwork(completedKey, artworkUrl)
        root.artworkRequestId = ""
        root.artworkRequestKey = ""
        root.artworkRequestTitle = ""
        root.artworkRequestArtist = ""
        if (root.protocolActionRequestId !== "")
          root.setRequestError("The Sonos backend stopped", root.actionFallback)
        root.protocolActionRequestId = ""
        root.applyLiveSnapshot()
        Qt.callLater(root.maybeRequestRadioArtwork)
        return
      }
      if (String(message.id || "") === root.contentRequestId) {
        root.contentLoading = false
        var payload = message.ok === true ? message.value : null
        var stillCurrentContent = root.selectedDevice
          && root.contentRequestRoomUid === String(root.selectedDevice.uid || "")
          && root.contentRequestKind === root.contentKind
          && root.contentRequestTerm === root.contentTerm
        root.contentRequestId = ""
        root.contentRequestRoomUid = ""
        if (payload && payload.ok === true && Array.isArray(payload.items)
            && stillCurrentContent) {
          var safeItems = []
          for (var i = 0; i < payload.items.length; i++) {
            var item = Object.assign({}, payload.items[i])
            item.album_art = root.safeArtworkUrl(item.album_art)
            safeItems.push(item)
          }
          root.contentItems = safeItems
          root.contentTotal = Number(payload.total || safeItems.length)
          root.contentMeta = {
            shares: Array.isArray(payload.shares) ? payload.shares : [],
            updating: payload.updating === true,
            playlistId: String(payload.playlist_id || ""),
            playlistTitle: String(payload.playlist_title || "")
          }
          root.requestError = ""
        } else if (stillCurrentContent) {
          root.setRequestError(live.errorMessage(message.error), "Could not browse Sonos content")
        }
        if (root.pendingContentKind !== "") {
          var nextKind = root.pendingContentKind
          var nextTerm = root.pendingContentTerm
          root.pendingContentKind = ""
          root.pendingContentTerm = ""
          Qt.callLater(function() { root.loadContent(nextKind, nextTerm) })
        }
        return
      }
      if (String(message.id || "") === root.alarmsRequestId) {
        root.alarmsLoading = false
        var alarmsPayload = message.ok === true ? message.value : null
        var stillCurrentAlarms = root.selectedDevice
          && root.alarmsRequestRoomUid === String(root.selectedDevice.uid || "")
        root.alarmsRequestId = ""
        root.alarmsRequestRoomUid = ""
        if (alarmsPayload && alarmsPayload.ok === true
            && Array.isArray(alarmsPayload.items) && stillCurrentAlarms) {
          root.alarms = alarmsPayload.items
          root.requestError = ""
        } else if (stillCurrentAlarms) {
          root.setRequestError(live.errorMessage(message.error), "Could not read Sonos alarms")
        }
        return
      }
      if (String(message.id || "") !== root.detailsRequestId) return
      var requestedRoomUid = root.detailsRequestRoomUid
      root.detailsLoading = false
      root.detailsRequestId = ""
      root.detailsRequestRoomUid = ""
      var stillCurrent = root.selectedDevice
        && requestedRoomUid === String(root.selectedDevice.uid || "")
      if (message.ok === true && message.value && message.value.ok === true && stillCurrent) {
        root.details = message.value
        root.requestError = ""
      } else if (stillCurrent) {
        root.setRequestError(live.errorMessage(message.error), "Could not read Sonos settings")
      }
      if (root.detailsQueued) {
        root.detailsQueued = false
        root.contentLoading = false
        root.contentRequestId = ""
        root.contentRequestRoomUid = ""
        root.alarmsLoading = false
        root.alarmsRequestId = ""
        root.alarmsRequestRoomUid = ""
        Qt.callLater(root.refreshDetails)
      }
    }
    function onBackendReadyChanged() {
      if (!live.backendReady) {
        root.detailsLoading = false
        root.detailsRequestId = ""
        root.detailsRequestRoomUid = ""
        root.detailsQueued = false
        root.artworkRequestId = ""
        root.artworkRequestKey = ""
        root.artworkRequestTitle = ""
        root.artworkRequestArtist = ""
      } else if (root.panelOpen) {
        Qt.callLater(root.refreshDetails)
        if (root.contentKind !== "favorites") Qt.callLater(root.reloadContent)
      }
    }
  }

  Timer {
    interval: 15000
    running: root.panelOpen && root.selectedIp !== ""
    repeat: true
    onTriggered: root.refreshDetails()
  }

  Timer {
    id: delayedRefresh
    interval: 500
    repeat: false
    onTriggered: {
      live.refresh()
      root.refreshDetails()
      if (root.contentKind === "queue") root.reloadContent()
      else if (root.contentKind === "favorites") root.syncLiveFavorites()
    }
  }

  Timer {
    id: renameRefresh
    interval: 5500
    repeat: false
    onTriggered: {
      live.refresh()
      root.refreshDetails()
    }
  }

  Timer {
    id: requestErrorTimer
    interval: 10000
    repeat: false
    onTriggered: root.requestError = ""
  }

  Timer {
    id: actionMessageTimer
    interval: 2600
    repeat: false
    onTriggered: root.actionMessage = ""
  }

  Timer {
    id: volumeDebounce
    interval: 140
    repeat: false
    onTriggered: root.flushVolume()
  }

  Process {
    id: actionProcess
    command: []
    clearEnvironment: true
    environment: root.helperEnvironment
    stdout: StdioCollector { id: actionStdout; waitForEnd: true }
    stderr: StdioCollector { id: actionStderr; waitForEnd: true }
    onExited: function(exitCode) {
      var payload = root.parsePayload(actionStdout.text)
      var completedAction = String(payload && payload.action || "")
      if (exitCode !== 0 || !payload || payload.ok !== true) {
        root.processFailure(actionStdout.text, actionStderr.text, root.actionFallback)
      } else {
        root.requestError = ""
        root.showActionMessage(String(payload.message || "Updated"))
        if (completedAction === "rename") {
          root.optimisticDevicePatch(root.selectedIp, { name: String(payload.name || "") })
          renameRefresh.restart()
        }
      }
      if (completedAction !== "rename" || exitCode !== 0 || !payload || payload.ok !== true)
        delayedRefresh.restart()
      if (String(payload && payload.action || "").indexOf("alarm-") === 0)
        Qt.callLater(root.loadAlarms)
      if (completedAction === "playlist-delete")
        Qt.callLater(function() { root.loadContent("playlists", "") })
      else if (completedAction.indexOf("playlist-") === 0
               || completedAction.indexOf("queue-") === 0
               || completedAction === "library-update")
        Qt.callLater(root.reloadContent)
    }
  }

  Component.onCompleted: applyLiveSnapshot()
}
