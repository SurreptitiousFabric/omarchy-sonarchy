import QtQuick

QtObject {
  id: root

  property string message: ""
  property string ownerId: ""

  function compact(text, fallback) {
    var value = String(text || fallback || "Sonos request failed").replace(/\s+/g, " ").trim()
    return value.length > 180 ? value.substring(0, 177) + "…" : value
  }

  function setError(text, fallback, requestId, replaceExisting) {
    var nextOwner = String(requestId || "")
    if (!Boolean(replaceExisting) && message !== "" && ownerId !== nextOwner)
      return false
    message = compact(text, fallback)
    ownerId = nextOwner
    return true
  }

  function clearError(requestId) {
    var expectedOwner = String(requestId || "")
    if (expectedOwner !== "" && ownerId !== expectedOwner) return false
    message = ""
    ownerId = ""
    return true
  }
}
