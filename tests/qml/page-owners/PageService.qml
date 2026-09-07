import QtQuick

QtObject {
  id: root
  property var calls: []
  property bool actionBusy: false
  property bool capabilities: true
  property var target: ({ groupUid: "group-a" })
  property string blockedUid: "room-c"
  property var soundDetails: ({ bass: 2, treble: -2 })
  function record(action, args) { calls = calls.concat([{ action: action, args: args }]) }
  function hasCapability(name) { return capabilities }
  function roomMoveBlocked(uid) { return uid === blockedUid }
  function selectSession(uid) { record("session", [uid]) }
  function movePlaybackToRoom(uid) { record("move", [uid]) }
  function adjustRoomVolume(uid, amount) { record("adjust", [uid, amount]) }
  function setRoomVolume(uid, value) { record("volume", [uid, value]) }
  function setRoomMute(uid, value) { record("mute", [uid, value]) }
  function setSound(setting, value) { record("sound", [setting, value]) }
  function toggleAlarm(id, value) { record("alarm-toggle", [id, value]) }
  function deleteAlarm(id) { record("alarm-delete", [id]) }
}
