import QtQuick

Item {
  id: root

  required property var store
  required property var live

  property var items: []
  property var meta: ({})
  property int total: 0
  property string kind: "favorites"
  property string term: ""
  property var path: []
  property int offset: 0
  property bool loading: false
  property var appleHistory: []
  property var libraryOffsetHistory: []
  readonly property bool appleCanGoBack: appleHistory.length > 0
  readonly property bool libraryCanGoBack: libraryOffsetHistory.length > 0

  property string requestId: ""
  property string requestRoomUid: ""
  property string requestKind: ""
  property string requestTerm: ""
  property string requestContextKey: ""
  property string pendingKind: ""
  property string pendingTerm: ""
  property var pendingPath: []
  property int pendingOffset: 0

  function normalizedPath(value) {
    if (!Array.isArray(value)) return []
    var result = []
    for (var i = 0; i < value.length; i++) {
      var segment = value[i] || ({})
      result.push({ id: String(segment.id || ""), index: Number(segment.index || 0) })
    }
    return result
  }

  function contextKey(value, pageOffset) {
    return JSON.stringify(normalizedPath(value)) + ":" + String(Math.max(0, pageOffset || 0))
  }

  function currentContextKey() { return contextKey(path, offset) }

  function resetLibraryHistory() { libraryOffsetHistory = [] }

  function syncFavorites() {
    if (kind !== "favorites") return
    var source = store.liveFavorites && store.liveFavorites.items
      ? store.liveFavorites.items : []
    var nextItems = []
    for (var i = 0; i < source.length; i++) {
      nextItems.push({
        id: String(source[i].id),
        title: String(source[i].title || "Favorite"),
        subtitle: String(source[i].kind || "favorite"),
        kind: String(source[i].kind || "audio"),
        album_art: store.safeArtworkUrl(source[i].albumArtUrl),
        playable: true,
        browsable: false
      })
    }
    items = nextItems
    total = Number(store.liveFavorites.total || nextItems.length)
    loading = String(store.liveFavorites.state || "") === "not_loaded"
    if (String(store.liveFavorites.state || "") === "error") {
      store.setRequestError(store.liveFavorites.error, "Could not load Sonos Favorites",
                            "favorites-snapshot")
    } else if (String(store.liveFavorites.state || "") !== "not_loaded") {
      store.clearRequestError("favorites-snapshot")
    }
  }

  function load(nextKindValue, nextTermValue, nextPathValue, nextOffsetValue) {
    var nextKind = String(nextKindValue || "favorites")
    var nextTerm = String(nextTermValue || "").trim()
    var nextPath = nextKind === "library" ? normalizedPath(nextPathValue) : []
    var nextOffset = nextKind === "library" ? Math.max(0, Number(nextOffsetValue || 0)) : 0
    if (nextKind !== kind || nextTerm !== term
        || JSON.stringify(nextPath) !== JSON.stringify(normalizedPath(path)))
      resetLibraryHistory()
    var contextChanged = nextKind !== kind || nextTerm !== term
      || contextKey(nextPath, nextOffset) !== currentContextKey()
    if (contextChanged) {
      items = []
      total = 0
    }
    kind = nextKind
    term = nextTerm
    path = nextPath
    offset = nextOffset
    meta = ({})

    if (nextKind === "favorites") {
      syncFavorites()
      if (String(store.liveFavorites.state || "") === "not_loaded") {
        loading = true
        live.refreshFavorites()
      }
      return
    }
    if (!store.selectedDevice || !live.hasCapability("content.browse")) {
      items = []
      total = 0
      loading = false
      return
    }
    if ((nextKind === "apple" || nextKind === "global") && nextTerm === "") {
      items = []
      total = 0
      loading = false
      return
    }
    if (requestId !== "") {
      pendingKind = nextKind
      pendingTerm = nextTerm
      pendingPath = nextPath
      pendingOffset = nextOffset
      return
    }

    loading = true
    requestRoomUid = String(store.selectedDevice.uid || "")
    requestKind = nextKind
    requestTerm = nextTerm
    requestContextKey = contextKey(nextPath, nextOffset)
    var resultLimit = nextKind === "queue" ? 100 : 40
    requestId = live.requestContent(
      requestRoomUid, requestKind, requestTerm, resultLimit,
      { path: nextPath, offset: nextOffset })
    if (requestId === "") {
      loading = false
      requestRoomUid = ""
      requestContextKey = ""
    }
  }

  function prepareSearch(nextKind) {
    kind = String(nextKind || "")
    term = ""
    path = []
    offset = 0
    items = []
    total = 0
    meta = ({})
    loading = false
    appleHistory = []
    resetLibraryHistory()
  }

  function search(nextKind, nextTerm) {
    appleHistory = []
    load(nextKind, nextTerm, [], 0)
  }

  function reload() {
    if (kind === "favorites") {
      loading = true
      live.refreshFavorites()
    } else {
      load(kind, term, path, offset)
    }
  }

  function openLibraryItem(item) {
    if (kind !== "library" || !item || item.browsable !== true) return
    var nextPath = normalizedPath(path)
    nextPath.push({ id: String(item.id || ""), index: Number(item.index || 0) })
    load("library", "", nextPath, 0)
  }

  function libraryBack() {
    if (kind !== "library" || path.length === 0) return
    load("library", "", path.slice(0, path.length - 1), 0)
  }

  function libraryPage(pageOffset) {
    if (kind !== "library") return
    load("library", term, path, Math.max(0, Number(pageOffset || 0)))
  }

  function libraryNext(nextOffsetValue) {
    if (kind !== "library") return
    var continuation = Math.max(0, Number(nextOffsetValue || 0))
    if (continuation <= offset) return
    var nextHistory = libraryOffsetHistory.slice(-99)
    nextHistory.push(offset)
    libraryOffsetHistory = nextHistory
    libraryPage(continuation)
  }

  function libraryPrevious() {
    if (kind !== "library" || libraryOffsetHistory.length === 0) return
    var nextHistory = libraryOffsetHistory.slice()
    var previousOffset = Number(nextHistory.pop() || 0)
    libraryOffsetHistory = nextHistory
    libraryPage(previousOffset)
  }

  function openAppleItem(item) {
    if (kind.indexOf("apple") !== 0 || !item || item.browsable !== true) return false
    var nextKind = String(item.browse_kind || "")
    if (nextKind !== "apple-artist" && nextKind !== "apple-album") return false
    var nextHistory = appleHistory.slice()
    nextHistory.push({ kind: kind, term: term })
    appleHistory = nextHistory
    load(nextKind, String(item.id || ""), [], 0)
    return true
  }

  function openItem(item) {
    if (!item || item.browsable !== true) return false
    if (kind === "library") {
      openLibraryItem(item)
      return true
    }
    return openAppleItem(item)
  }

  function appleBack() {
    if (kind.indexOf("apple") !== 0 || appleHistory.length === 0) return
    var nextHistory = appleHistory.slice()
    var previous = nextHistory.pop()
    appleHistory = nextHistory
    load(String(previous.kind || "apple"), String(previous.term || ""), [], 0)
  }

  function cancelRequests() {
    loading = false
    requestId = ""
    requestRoomUid = ""
    requestKind = ""
    requestTerm = ""
    requestContextKey = ""
    pendingKind = ""
    pendingTerm = ""
    pendingPath = []
    pendingOffset = 0
    appleHistory = []
    resetLibraryHistory()
  }
}
