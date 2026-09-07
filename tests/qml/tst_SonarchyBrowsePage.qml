import QtQuick
import QtTest
import "."

Item {
  id: host
  width: 620
  height: 700
  property var calls: []

  QtObject {
    id: fakeService
    property bool actionBusy: false
    property bool contentLoading: false
    property bool capabilities: true
    property string contentKind: "library"
    property string contentTerm: ""
    property int contentTotal: contentItems.length
    property var contentMeta: ({})
    property var playbackDetails: ({})
    property bool appleCanGoBack: false
    property bool libraryCanGoBack: false
    property var contentItems: []
    function hasCapability(name) { return capabilities }
    function refreshDetails() {}
    function loadContent(kind, term) {}
    function reloadContent() {}
    function activateContent(item) { host.calls = host.calls.concat([{ action: "activate", item: item }]) }
    function enqueueContent(item, mode) { host.calls = host.calls.concat([{ action: mode, item: item }]) }
    function playAppleAlbum(item) { host.calls = host.calls.concat([{ action: "album", item: item }]) }
    function playlistTrackAction(action, item) { host.calls = host.calls.concat([{ action: action, item: item }]) }
  }

  SonarchyBrowsePage {
    id: page
    anchors.fill: parent
    service: fakeService
    device: ({ uid: "fixture-room" })
    sourceKind: "library"
    showArtwork: false
  }

  TestCase {
    name: "SonarchyBrowseDelegateBindings"
    when: windowShown

    function item(index, id, section) {
      return { index: index, id: id, section: section, title: "Title " + id,
        subtitle: "Subtitle " + id, browsable: true, playable: true,
        current: index === 1, album_url: "fixture-album", media_kind: "album" }
    }

    function descendants(owner, predicate) {
      var result = []
      for (var i = 0; i < owner.children.length; i++) {
        var child = owner.children[i]
        if (predicate(child)) result.push(child)
        result = result.concat(descendants(child, predicate))
      }
      return result
    }

    function rows() {
      return descendants(page, function(child) { return child.rowKey !== undefined })
    }

    function action(row, tooltip, text) {
      var matches = descendants(row, function(child) {
        return child.tooltipText === tooltip && (text === undefined || child.text === text)
      })
      compare(matches.length, 1)
      return matches[0]
    }

    function init() {
      host.calls = []
      page.confirmation = ""
      page.sourceKind = "library"
      host.width = 620
      page.foreground = "#abcdef"
      page.fontFamily = "monospace"
      fakeService.contentKind = "library"
      fakeService.contentMeta = ({})
      fakeService.capabilities = true
      fakeService.actionBusy = false
      fakeService.contentItems = [item(0, "first", "Albums"), item(1, "second", "Albums")]
      wait(0)
      compare(rows().length, 2)
    }

    function test_optional_library_metadata_visibility() {
      fakeService.contentMeta = ({ breadcrumbs: [{ title: "Albums" }], shares: ["fixture-share"] })
      var crumbs = descendants(page, function(child) { return child.text === "Local library  ›  Albums" })[0]
      var shares = descendants(page, function(child) { return child.text === "Sonos has 1 local library share configured." })[0]
      var back = descendants(page, function(child) { return child.text === "Back" && child.iconText !== undefined })[0]
      verify(crumbs !== undefined && shares !== undefined && back !== undefined)
      verify(crumbs.visible && shares.visible && back.visible)
      fakeService.contentMeta = ({})
      verify(!crumbs.visible && !shares.visible && !back.visible)
      fakeService.contentMeta = ({ breadcrumbs: [], shares: [] })
      verify(!crumbs.visible && !shares.visible && !back.visible)
    }

    function test_model_roles_display_and_live_replacement() {
      var cards = rows()
      verify(cards[0].showSection)
      verify(!cards[1].showSection)
      compare(cards[1].rowKey, "library:1:second")
      var title = descendants(cards[1], function(child) { return child.text === "Title second" })[0]
      verify(title !== undefined)
      verify(title.font.bold)
      page.foreground = "#123456"
      page.fontFamily = "sans-serif"
      compare(title.color, page.foreground)
      compare(title.font.family, "sans-serif")
      host.width = 380
      wait(0)
      verify(cards[1].width <= 380)
      host.width = 620
      fakeService.contentItems = [item(0, "replacement", "Tracks")]
      wait(0)
      compare(rows().length, 1)
      compare(rows()[0].modelData.id, "replacement")
      compare(rows()[0].section, "Tracks")
      verify(rows()[0].showSection)
      fakeService.contentItems = []
      wait(0)
      compare(rows().length, 0)
      compare(host.calls.length, 0)
    }

    function test_focused_activation_and_queue_modes_use_exact_row() {
      var row = rows()[1]
      var open = action(row, "View album tracks")
      open.forceActiveFocus()
      verify(open.activeFocus)
      keyClick(Qt.Key_Return)
      compare(host.calls.length, 1)
      compare(host.calls[0].item, fakeService.contentItems[1])
      compare(host.calls[0].action, "activate")
      for (var pair of [["Play", "play"], ["Next", "next"], ["End", "end"]]) {
        var button = action(row, "", pair[0])
        verify(button.visible && button.enabled)
        button.clicked()
        compare(host.calls[host.calls.length - 1].action, pair[1])
        compare(host.calls[host.calls.length - 1].item, fakeService.contentItems[1])
      }
      var replace = action(row, "Play if queue empty")
      var before = host.calls.length
      replace.clicked()
      compare(host.calls.length, before)
      compare(page.confirmation, row.replaceKey)
      replace.clicked()
      compare(host.calls.length, before + 1)
      compare(host.calls[before].action, "replace")
      compare(host.calls[before].item, fakeService.contentItems[1])
    }

    function test_playlist_album_and_capability_bindings() {
      fakeService.contentKind = "playlist"
      var row = rows()[1]
      var up = action(row, "Move up")
      var down = action(row, "Move down")
      verify(up.enabled)
      verify(!down.enabled)
      up.clicked()
      compare(host.calls[0].action, "up")
      compare(host.calls[0].item, fakeService.contentItems[1])
      action(rows()[0], "Move down").clicked()
      compare(host.calls[1].action, "down")
      compare(host.calls[1].item, fakeService.contentItems[0])
      var remove = action(row, "Remove")
      remove.clicked()
      compare(host.calls.length, 2)
      remove.clicked()
      compare(host.calls[2].action, "remove")
      compare(host.calls[2].item, fakeService.contentItems[1])
      fakeService.contentKind = "apple-songs"
      var album = action(row, "Play the whole album")
      verify(album.visible && album.enabled)
      album.clicked()
      compare(host.calls[3].action, "album")
      compare(host.calls[3].item, fakeService.contentItems[1])
      fakeService.actionBusy = true
      verify(!album.enabled)
      fakeService.actionBusy = false
      fakeService.capabilities = false
      verify(!album.enabled)
      var before = host.calls.length
      album.forceActiveFocus()
      keyClick(Qt.Key_Return)
      compare(host.calls.length, before)
    }
  }
}
