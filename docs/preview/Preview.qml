import QtQuick
import QtTest
import qs.Commons

Rectangle {
  id: board
  width: 1280
  height: 720
  color: "#101010"

  FontLoader {
    id: demoFont
    source: "file:///usr/share/fonts/TTF/JetBrainsMonoNerdFont-Regular.ttf"
  }

  QtObject {
    id: demoService
    property int mutations: 0
    property bool actionBusy: false
    property bool contentLoading: false
    property string contentKind: "queue"
    property int contentTotal: 3
    property var contentItems: [
      { index: 0, id: "DEMO:0", title: "Demo track 01", subtitle: "Example artist / Demo album", album_art: "", current: true },
      { index: 1, id: "DEMO:1", title: "Demo track 02", subtitle: "Example artist / Demo album", album_art: "" },
      { index: 2, id: "DEMO:2", title: "Demo track 03", subtitle: "Example artist / Demo album", album_art: "" }
    ]
    function hasCapability(_name) { return true }
    function loadContent(_kind, _term) {}
    function rejectMutation() { mutations += 1; throw new Error("Preview must not mutate") }
    function clearQueue() { rejectMutation() }
    function moveQueueItem() { rejectMutation() }
    function removeQueueItem() { rejectMutation() }
    function playContent() { rejectMutation() }
  }

  Column {
    x: 64
    y: 118
    width: 430
    spacing: 26

    Text {
      text: "SONARCHY"
      color: "#e0ba8c"
      font.family: demoFont.name
      font.pixelSize: 46
    }
    Text {
      width: parent.width
      text: "Keyboard-first\nSonos control."
      color: "#eeeeee"
      font.family: demoFont.name
      font.pixelSize: 28
      lineHeight: 1.3
    }
    Rectangle { width: 80; height: 2; color: "#e0ba8c" }
    Text {
      width: parent.width
      text: "Local playback & rooms\nQueue & library navigation\nOptional AI / MCP workflows"
      color: "#aaaaaa"
      font.family: demoFont.name
      font.pixelSize: 18
      lineHeight: 1.65
    }
    Text {
      width: parent.width
      text: "Community plugin for Omarchy\nNot affiliated with Sonos"
      color: "#888888"
      font.family: demoFont.name
      font.pixelSize: 14
      lineHeight: 1.5
    }
  }

  Rectangle {
    x: 570
    y: 56
    width: 646
    height: 590
    radius: 12
    color: "#161616"
    border.color: "#444444"

    Text {
      x: 24
      y: 22
      text: "Demo room / queue"
      color: "#e0ba8c"
      font.family: demoFont.name
      font.pixelSize: 18
    }
    SonarchyQueuePage {
      id: queue
      x: 24
      y: 66
      width: parent.width - 48
      height: 408
      service: demoService
      device: ({ uid: "DEMO-ROOM" })
      showArtwork: false
      fontFamily: demoFont.name
    }
    SonarchyNavigation {
      x: 24
      y: 512
      width: parent.width - 48
      fontFamily: demoFont.name
      options: ["Now", "Browse", "Queue", "Rooms", "Sound", "System"]
      value: "Queue"
      focusable: false
    }
  }

  Text {
    x: 64
    y: 675
    text: "ISOLATED UI PREVIEW / DEMO DATA / TEST THEME / NOT RELEASE ACCEPTANCE"
    color: "#999999"
    font.family: demoFont.name
    font.pixelSize: 14
  }

  TestCase {
    name: "MarketplacePreview"
    when: windowShown
    property bool saved: false

    function test_render_demo_without_mutation() {
      tryCompare(demoFont, "status", FontLoader.Ready)
      Style.font.family = demoFont.name
      verify(findChild(queue, "queueCard:2") !== null)
      verify(waitForRendering(board))
      verify(board.grabToImage(function(result) { saved = result.saveToFile("preview.png") }))
      tryCompare(this, "saved", true)
      compare(demoService.mutations, 0)
    }
  }
}
