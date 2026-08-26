import QtQuick

QtObject {
  id: artwork

  required property var store
  required property var live

  property var cache: ({})
  property var cacheOrder: []
  property string requestId: ""
  property string requestKey: ""
  property string requestTitle: ""
  property string requestArtist: ""
  property string diagnosticKey: ""
  readonly property int cacheLimit: 128

  function radioKey(playback) {
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

  function hasCacheEntry(key) {
    return key !== "" && Object.prototype.hasOwnProperty.call(artwork.cache, key)
  }

  function putCache(key, url) {
    if (key === "") return
    var next = Object.assign({}, artwork.cache)
    next[key] = String(url || "")
    var order = []
    for (var i = 0; i < artwork.cacheOrder.length; i++) {
      if (String(artwork.cacheOrder[i]) !== key)
        order.push(String(artwork.cacheOrder[i]))
    }
    order.push(key)
    while (order.length > artwork.cacheLimit) delete next[order.shift()]
    artwork.cache = next
    artwork.cacheOrder = order
  }

  function forPlayback(playback) {
    var supplied = safeUrl(playback ? playback.artworkUrl : "")
    if (!artwork.store.radioArtworkEnrichmentEnabled
        || String(playback ? playback.artworkKind || "" : "") === "track") return supplied
    var key = radioKey(playback)
    if (hasCacheEntry(key)) {
      var enriched = safeUrl(artwork.cache[key])
      if (enriched !== "") return enriched
    }
    return supplied
  }

  function maybeRequest() {
    if (!artwork.store.radioArtworkEnrichmentEnabled || !artwork.store.panelOpen
        || artwork.requestId !== ""
        || !artwork.live.hasCapability("artwork.radio.resolve")) return
    var playback = artwork.store.livePlayback || ({})
    if (String(playback.artworkKind || "") === "track") return
    var key = radioKey(playback)
    if (key === "" || hasCacheEntry(key)) return
    artwork.requestKey = key
    artwork.requestTitle = String(playback.title || "")
    artwork.requestArtist = String(playback.artist || "")
    artwork.requestId = artwork.live.requestRadioArtwork(
      artwork.requestTitle, artwork.requestArtist)
  }

  function safeUrl(url) {
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
    for (var i = 0; i < artwork.store.devices.length; i++) {
      var prefix = "http://" + String(artwork.store.devices[i].ip || "") + ":1400/"
      if (value.indexOf(prefix) === 0) return value
    }
    return artwork.store.devices.length === 0 ? value : ""
  }
}
