import QtQuick
import QtTest

TestCase {
  id: testCase
  name: "SonarchyContentStateNavigation"

  property var subject: null

  QtObject {
    id: fakeStore
    property var selectedDevice: ({ uid: "R1" })
    property var liveFavorites: ({ state: "ready", total: 1, items: [
      { id: "F:1", title: "Station", kind: "radio", albumArtUrl: "safe-art" }
    ] })
    property string lastErrorOwner: ""
    function safeArtworkUrl(value) { return String(value || "") }
    function setRequestError(_text, _fallback, owner) { lastErrorOwner = String(owner) }
    function clearRequestError(owner) {
      if (lastErrorOwner === String(owner)) lastErrorOwner = ""
    }
  }

  QtObject {
    id: fakeLive
    property var calls: []
    function hasCapability(name) { return name === "content.browse" }
    function refreshFavorites() { calls = calls.concat([{ operation: "favorites" }]) }
    function requestContent(roomUid, kind, term, limit, context) {
      calls = calls.concat([{
        operation: "browse",
        roomUid: roomUid,
        kind: kind,
        term: term,
        limit: limit,
        context: context
      }])
      return "content-1"
    }
  }

  Component {
    id: subjectComponent
    SonarchyContentState {
      store: fakeStore
      live: fakeLive
    }
  }

  function init() {
    fakeLive.calls = []
    fakeStore.lastErrorOwner = ""
    subject = createTemporaryObject(subjectComponent, testCase)
    verify(subject !== null)
  }

  function test_library_root_request_has_explicit_bounded_context() {
    subject.load("library", "", [], 0)

    compare(fakeLive.calls.length, 1)
    compare(fakeLive.calls[0].roomUid, "R1")
    compare(fakeLive.calls[0].kind, "library")
    compare(fakeLive.calls[0].limit, 40)
    compare(fakeLive.calls[0].context.offset, 0)
    compare(fakeLive.calls[0].context.path.length, 0)
    compare(subject.requestContextKey, "[]:0")
  }

  function test_nested_navigation_is_queued_while_request_is_pending() {
    subject.load("library", "", [], 0)
    subject.openLibraryItem({ id: "A:ARTIST", index: 7, browsable: true })

    compare(fakeLive.calls.length, 1)
    compare(subject.path.length, 1)
    compare(subject.path[0].id, "A:ARTIST")
    compare(subject.path[0].index, 7)
    compare(subject.pendingKind, "library")
    compare(subject.pendingPath.length, 1)
    compare(subject.currentContextKey(), '[{"id":"A:ARTIST","index":7}]:0')
  }

  function test_library_back_and_page_preserve_navigation_context() {
    subject.path = [{ id: "A:ARTIST", index: 2 }]
    subject.kind = "library"
    subject.offset = 40

    subject.libraryPage(80)
    compare(fakeLive.calls[0].context.offset, 80)
    compare(fakeLive.calls[0].context.path[0].id, "A:ARTIST")

    subject.cancelRequests()
    subject.libraryBack()
    compare(fakeLive.calls[1].context.offset, 0)
    compare(fakeLive.calls[1].context.path.length, 0)
  }

  function test_favorites_are_projected_without_a_browse_request() {
    subject.load("favorites", "", [], 0)

    compare(fakeLive.calls.length, 0)
    compare(subject.items.length, 1)
    compare(subject.items[0].album_art, "safe-art")
    compare(subject.items[0].browsable, false)
  }
}
