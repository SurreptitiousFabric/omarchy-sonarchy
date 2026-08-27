import QtQuick

Item {
  id: root

  property alias shell: store.shell
  property alias radioArtworkEnrichmentEnabled: store.radioArtworkEnrichmentEnabled
  property alias contentKind: store.contentKind
  property alias contentTerm: store.contentTerm

  readonly property alias actionBusy: store.actionBusy
  readonly property alias actionMessage: store.actionMessage
  readonly property alias alarms: store.alarms
  readonly property alias alarmsLoading: store.alarmsLoading
  readonly property alias contentItems: store.contentItems
  readonly property alias contentLoading: store.contentLoading
  readonly property alias contentMeta: store.contentMeta
  readonly property alias contentTotal: store.contentTotal
  readonly property alias detailsLoading: store.detailsLoading
  readonly property alias deviceDetails: store.deviceDetails
  readonly property alias devices: store.devices
  readonly property alias hasDevices: store.hasDevices
  readonly property alias lastError: store.lastError
  readonly property alias liveFavorites: store.liveFavorites
  readonly property alias livePlayback: store.livePlayback
  readonly property alias loading: store.loading
  readonly property alias playbackDetails: store.playbackDetails
  readonly property alias rooms: store.rooms
  readonly property alias selectedDevice: store.selectedDevice
  readonly property alias sessions: store.sessions
  readonly property alias soundDetails: store.soundDetails
  readonly property alias target: store.target

  function adjustRoomVolume(roomUid, delta) { store.adjustRoomVolume(roomUid, delta) }
  function adjustVolume(delta) { store.adjustVolume(delta) }
  function applyMembers(roomUids) { store.applyMembers(roomUids) }
  function clearError() { store.clearError() }
  function clearQueue() { store.clearQueue() }
  function deleteAlarm(id) { store.deleteAlarm(id) }
  function enqueueContent(item, mode) { store.enqueueContent(item, mode) }
  function ensureFavorites() { store.ensureFavorites() }
  function formatTime(value) { return store.formatTime(value) }
  function hasCapability(name) { return store.hasCapability(name) }
  function loadAlarms() { store.loadAlarms() }
  function libraryBack() { store.libraryBack() }
  function libraryPage(offset) { store.libraryPage(offset) }
  function loadContent(kind, term, path, offset) { store.loadContent(kind, term, path, offset) }
  function openLibraryItem(item) { store.openLibraryItem(item) }
  function prepareContentSearch(kind) { store.prepareContentSearch(kind) }
  function movePlaybackToRoom(roomUid) { store.movePlaybackToRoom(roomUid) }
  function playAppleAlbum(item) { store.playAppleAlbum(item) }
  function playContent(item) { store.playContent(item) }
  function playlistAction(action, value) { store.playlistAction(action, value) }
  function playlistTrackAction(action, item) { store.playlistTrackAction(action, item) }
  function refresh() { store.refresh() }
  function refreshDetails() { store.refreshDetails() }
  function reloadContent() { store.reloadContent() }
  function removeQueueItem(index, itemId) { store.removeQueueItem(index, itemId) }
  function renameRoom(name) { store.renameRoom(name) }
  function requestVolume(value) { store.requestVolume(value) }
  function roomMoveBlocked(roomUid) { return store.roomMoveBlocked(roomUid) }
  function roomOptions() { return store.roomOptions() }
  function runAction(action) { store.runAction(action) }
  function saveAlarm(editor) { store.saveAlarm(editor) }
  function seek(positionSec) { store.seek(positionSec) }
  function selectDevice(uid) { store.selectDevice(uid) }
  function selectSession(groupUid) { store.selectSession(groupUid) }
  function setDeviceSetting(setting, value) { store.setDeviceSetting(setting, value) }
  function setPanelOpen(open) { store.setPanelOpen(open) }
  function setPlaybackOption(option, value) { store.setPlaybackOption(option, value) }
  function setRoomMute(roomUid, mute) { store.setRoomMute(roomUid, mute) }
  function setRoomVolume(roomUid, value) { store.setRoomVolume(roomUid, value) }
  function setSound(setting, value) { store.setSound(setting, value) }
  function startLibraryUpdate() { store.startLibraryUpdate() }
  function switchSource(source, sourceIp) { store.switchSource(source, sourceIp) }
  function toggleAlarm(id, enabled) { store.toggleAlarm(id, enabled) }

  SonarchyStore {
    id: store
  }
}
