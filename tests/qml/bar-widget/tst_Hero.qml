import QtQuick
import QtTest
import qs.Ui
import "."

Item {
  id: host
  width: 600
  height: 200

  QtObject {
    id: firstBar
    property string fontFamily: "monospace"
  }
  QtObject {
    id: secondBar
    property string fontFamily: "sans-serif"
  }
  component TestService: QtObject {
    property bool loading: false
    property bool detailsLoading: false
    property bool contentLoading: false
    property var calls: []
    function refresh() { calls = calls.concat(["refresh"]) }
    function refreshDetails() { calls = calls.concat(["details"]) }
    function reloadContent() { calls = calls.concat(["browse"]) }
    function loadContent(kind, term) { calls = calls.concat([kind]) }
  }
  TestService { id: firstService }
  TestService { id: secondService }

  Owner {
    id: owner
    bar: firstBar
    service: firstService
  }

  PanelHero {
    id: hero
    width: 480
    iconComponent: owner.hero
    trailingControl: owner.refresh
    fontFamily: "monospace"
  }

  TestCase {
    name: "BarWidgetOwnerBindings"
    when: windowShown

    function loaded(component) {
      for (var i = 0; i < hero.children.length; i++) {
        var child = hero.children[i]
        if (child instanceof Loader && child.sourceComponent === component) return child.item
      }
      fail("Missing installed PanelHero loader")
      return null
    }

    function test_owner_bindings_and_replacement() {
      var icon = loaded(owner.hero).children[0]
      var refresh = loaded(owner.refresh)
      compare(icon.fontFamily, "monospace")
      compare(icon.color, owner.panelForeground)
      verify(refresh.enabled)
      verify(!refresh.iconSpinning)
      refresh.clicked()
      compare(firstService.calls.join(","), "refresh,details,browse")

      firstService.loading = true
      verify(!refresh.enabled)
      verify(refresh.iconSpinning)
      firstService.loading = false
      firstService.detailsLoading = true
      verify(refresh.enabled)
      verify(refresh.iconSpinning)
      firstService.detailsLoading = false
      firstService.contentLoading = true
      verify(refresh.iconSpinning)

      owner.bar = secondBar
      owner.service = secondService
      owner.panelForeground = "#112233"
      owner.activePage = "queue"
      compare(icon.fontFamily, "sans-serif")
      compare(icon.color, owner.panelForeground)
      compare(refresh.foreground, owner.panelForeground)
      verify(refresh.enabled)
      verify(!refresh.iconSpinning)
      refresh.clicked()
      compare(secondService.calls.join(","), "refresh,details,queue")
      compare(firstService.calls.join(","), "refresh,details,browse")

      owner.service = null
      verify(!refresh.enabled)
      verify(!refresh.iconSpinning)
      refresh.clicked()
      compare(secondService.calls.join(","), "refresh,details,queue")
    }
  }
}
