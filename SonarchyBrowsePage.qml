import QtQuick
import QtQuick.Controls as QQC
import qs.Commons
import qs.Ui

Item {
  id: root

  property var service: null
  property var device: null
  property color foreground: Color.popups.text
  property string fontFamily: Style.font.family
  property string sourceKind: "favorites"
  property bool showArtwork: true
  property string confirmation: ""

  readonly property bool searchable: sourceKind === "apple"
    || sourceKind === "global" || sourceKind === "library"
  readonly property bool editing: queryField.activeFocus || playlistNameField.activeFocus
    || sourcePicker.popupOpen

  onVisibleChanged: {
    if (!visible || !service) return
    service.refreshDetails()
    if (searchable && sourceKind !== "library") return
    if (sourceKind === "library" && service.contentKind === "library")
      service.reloadContent()
    else service.loadContent(sourceKind, "")
  }

  onDeviceChanged: if (sourceKind === "library") queryField.text = ""

  function ensureVisible(item) {
    if (!item || !browseFlick.visible) return
    var point = item.mapToItem(browseFlick.contentItem, 0, 0)
    var top = point.y - Style.space(10)
    var bottom = point.y + item.height + Style.space(10)
    if (top < browseFlick.contentY) browseFlick.contentY = Math.max(0, top)
    else if (bottom > browseFlick.contentY + browseFlick.height)
      browseFlick.contentY = Math.min(
        Math.max(0, browseFlick.contentHeight - browseFlick.height),
        bottom - browseFlick.height)
  }

  function arm(key) {
    if (confirmation === key) {
      confirmation = ""
      confirmTimer.stop()
      return true
    }
    confirmation = key
    confirmTimer.restart()
    return false
  }

  function runSearch() {
    if (!service || !searchable) return
    service.loadContent(sourceKind, queryField.text, [], 0)
  }

  function changeSource(value) {
    sourceKind = String(value)
    confirmation = ""
    queryField.text = ""
    playlistNameField.text = ""
    if (!service) return
    if (searchable && sourceKind !== "library") {
      service.prepareContentSearch(sourceKind)
    } else {
      service.loadContent(sourceKind, "", [], 0)
    }
  }

  function emptyMessage() {
    if (!service) return "Sonos is starting"
    if (service.contentLoading) return "Loading…"
    if (sourceKind === "library" && service.contentTerm === "") {
      if (service.contentMeta.shares && service.contentMeta.shares.length === 0
          && (!service.contentMeta.breadcrumbs
              || service.contentMeta.breadcrumbs.length === 0))
        return "No local music library is configured in Sonos"
      if (service.contentMeta.breadcrumbs && service.contentMeta.breadcrumbs.length > 0)
        return "This library folder is empty"
      return "No local library categories found"
    }
    if (searchable && service.contentTerm === "") {
      return "Type something to search"
    }
    if (service.contentKind === "queue") return "The queue is empty"
    if (service.contentKind === "favorites") return "No Sonos Favorites found"
    if (service.contentKind === "playlists") return "No Sonos playlists found"
    if (service.contentKind === "playlist") return "This playlist is empty"
    return "No matching results"
  }

  function resultHeading() {
    if (!service) return "RESULTS"
    if (service.contentKind === "queue") return "QUEUE"
    if (service.contentKind === "favorites") return "FAVORITES"
    if (service.contentKind === "library")
      return String(service.contentMeta.currentTitle || "LOCAL LIBRARY").toUpperCase()
    if (service.contentKind === "playlists") return "SONOS PLAYLISTS"
    if (service.contentKind === "playlist")
      return String(service.contentMeta.playlistTitle || "PLAYLIST").toUpperCase()
    return "RESULTS"
  }

  function can(operation) {
    return service && service.hasCapability(operation)
  }

  function canPlayCurrentKind() {
    if (!service) return false
    var kind = String(service.contentKind || "")
    if (kind === "favorites") return can("content.favorite.play")
    if (kind === "queue") return can("queue.item.play")
    if (kind === "apple") return can("content.apple.play")
    if (kind === "global") return can("content.global.play")
    if (kind === "library" || kind === "playlist")
      return can("queue.content.enqueue")
    return kind === "playlists" && can("content.browse")
  }

  Timer {
    id: confirmTimer
    interval: 5000
    repeat: false
    onTriggered: root.confirmation = ""
  }

  Flickable {
    id: browseFlick
    anchors.fill: parent
    contentWidth: width
    contentHeight: browseColumn.implicitHeight
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    flickableDirection: Flickable.VerticalFlick

    QQC.ScrollBar.vertical: QQC.ScrollBar {
      policy: QQC.ScrollBar.AsNeeded
    }

    Column {
      id: browseColumn
      width: browseFlick.width - Style.space(6)
      spacing: Style.space(10)

      SonarchyDropdown {
        id: sourcePicker
        width: parent.width
        label: "BROWSE"
        value: root.sourceKind
        options: [
          { value: "favorites", label: "Sonos Favorites" },
          { value: "queue", label: "Current queue" },
          { value: "playlists", label: "Sonos playlists" },
          { value: "library", label: "Local music library" },
          { value: "apple", label: "Apple Music catalog" },
          { value: "global", label: "Global Player stations" }
        ]
        foreground: root.foreground
        fontFamily: root.fontFamily
        onChanged: function(value) { root.changeSource(value) }
      }

      Row {
        width: parent.width
        spacing: Style.space(7)
        visible: root.searchable

        TextField {
          id: queryField
          width: parent.width - searchButton.width - parent.spacing
          placeholderText: root.sourceKind === "apple" ? "Search songs and artists"
            : (root.sourceKind === "global" ? "Search radio stations"
               : "Search indexed tracks")
          foreground: root.foreground
          accent: Color.accent
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
          onAccepted: root.runSearch()
          Keys.onEscapePressed: focus = false
        }

        Button {
          id: searchButton
          anchors.verticalCenter: parent.verticalCenter
          iconText: "󰍉"
          text: "Search"
          foreground: root.foreground
          bordered: true
          focusable: true
          enabled: root.service && !root.service.contentLoading
            && root.can("content.browse")
            && queryField.text.trim() !== ""
          onClicked: root.runSearch()
        }
      }

      Text {
        width: parent.width
        visible: root.searchable
        text: root.sourceKind === "apple"
          ? "Public Apple catalog; the speaker uses the Apple Music account already connected in Sonos."
          : (root.sourceKind === "global"
             ? "Search runs through Global Player as connected to Sonos."
             : "Searches the music library indexed by Sonos, not your private Apple Music cloud library.")
        color: Qt.darker(root.foreground, 1.5)
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
        wrapMode: Text.WordWrap
      }

      Text {
        width: parent.width
        visible: root.sourceKind === "library" && root.service
          && root.service.contentMeta.breadcrumbs
          && root.service.contentMeta.breadcrumbs.length > 0
        text: {
          var crumbs = root.service && root.service.contentMeta
            ? (root.service.contentMeta.breadcrumbs || []) : []
          var labels = ["Local library"]
          for (var i = 0; i < crumbs.length; i++)
            labels.push(String(crumbs[i].title || "Folder"))
          return labels.join("  ›  ")
        }
        color: Qt.darker(root.foreground, 1.35)
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
        elide: Text.ElideLeft
      }

      Text {
        width: parent.width
        visible: root.sourceKind === "apple" && root.service
          && root.service.playbackDetails.tv_autoplay_risk === true
        text: "TV Autoplay is on while TV audio is active, so Sonos will interrupt music. "
          + "Select the home-theater room, open System, and turn off TV Autoplay first."
        color: Color.urgent
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
        font.bold: true
        wrapMode: Text.WordWrap
      }

      Row {
        width: parent.width
        spacing: Style.space(7)
        visible: root.sourceKind === "playlists"
          && root.service && root.service.contentKind !== "playlist"

        TextField {
          id: playlistNameField
          width: parent.width - createPlaylistButton.width
            - saveQueueButton.width - parent.spacing * 2
          placeholderText: "New playlist name"
          foreground: root.foreground
          accent: Color.accent
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
          onAccepted: if (root.service && text.trim() !== "")
            root.service.playlistAction("create", text)
          Keys.onEscapePressed: focus = false
        }

        Button {
          id: createPlaylistButton
          text: "Create"
          foreground: root.foreground
          bordered: true
          focusable: true
          enabled: root.service && !root.service.actionBusy
            && root.can("playlists.mutate")
            && playlistNameField.text.trim() !== ""
          onClicked: root.service.playlistAction("create", playlistNameField.text)
        }

        Button {
          id: saveQueueButton
          text: "Save queue"
          foreground: root.foreground
          bordered: true
          focusable: true
          enabled: root.service && !root.service.actionBusy
            && root.can("playlists.mutate")
            && playlistNameField.text.trim() !== ""
          onClicked: root.service.playlistAction("save-queue", playlistNameField.text)
        }
      }

      Text {
        width: parent.width
        visible: root.sourceKind === "library" && root.service
          && root.service.contentMeta.shares && root.service.contentMeta.shares.length > 0
        text: {
          var shares = root.service && root.service.contentMeta
            ? (root.service.contentMeta.shares || []) : []
          return "Sonos has " + shares.length + " local library share"
            + (shares.length === 1 ? "" : "s") + " configured."
        }
        color: Qt.darker(root.foreground, 1.45)
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
        wrapMode: Text.WordWrap
      }

      Text {
        width: parent.width
        visible: root.confirmation !== ""
        text: "Press the same focused action again to confirm. This expires in 5 seconds."
        color: Color.urgent
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
        font.bold: true
        wrapMode: Text.WordWrap
      }

      Item {
        width: parent.width
        implicitHeight: Math.max(resultsHeader.implicitHeight, headerActions.implicitHeight)

        PanelSectionHeader {
          id: resultsHeader
          anchors.left: parent.left
          anchors.verticalCenter: parent.verticalCenter
          text: root.resultHeading()
          foreground: root.foreground
          fontFamily: root.fontFamily
        }

        Row {
          id: headerActions
          anchors.right: parent.right
          anchors.verticalCenter: parent.verticalCenter
          spacing: Style.space(5)

          Text {
            anchors.verticalCenter: parent.verticalCenter
            text: root.service ? String(root.service.contentTotal || 0) : "0"
            color: Qt.darker(root.foreground, 1.4)
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            font.bold: true
          }

          Button {
            visible: root.service && (root.service.contentKind === "playlist"
              || (root.service.contentKind === "library"
                  && (root.service.contentTerm !== ""
                      || (root.service.contentMeta.breadcrumbs
                          && root.service.contentMeta.breadcrumbs.length > 0))))
            text: root.service && root.service.contentKind === "library"
              && root.service.contentTerm !== "" ? "Browse" : "Back"
            iconText: "󰁍"
            foreground: root.foreground
            focusable: true
            onClicked: {
              browseFlick.contentY = 0
              if (root.service.contentKind === "library") {
                if (root.service.contentTerm !== "") {
                  queryField.text = ""
                  root.service.loadContent("library", "", [], 0)
                } else root.service.libraryBack()
              } else root.service.loadContent("playlists", "")
            }
          }

          Button {
            visible: root.service && root.service.contentKind === "library"
              && root.service.contentMeta.hasPrevious === true
            iconText: "󰁍"
            tooltipText: "Previous page"
            foreground: root.foreground
            focusable: true
            enabled: root.service && !root.service.contentLoading
            onClicked: {
              browseFlick.contentY = 0
              root.service.libraryPage(Math.max(0,
                Number(root.service.contentMeta.offset || 0)
                - Number(root.service.contentMeta.pageSize || 40)))
            }
          }

          Button {
            visible: root.service && root.service.contentKind === "library"
              && root.service.contentMeta.hasNext === true
            iconText: "󰁔"
            tooltipText: "Next page"
            foreground: root.foreground
            focusable: true
            enabled: root.service && !root.service.contentLoading
            onClicked: {
              browseFlick.contentY = 0
              root.service.libraryPage(Number(root.service.contentMeta.offset || 0)
                + Number(root.service.contentMeta.pageSize || 40))
            }
          }

          Button {
            visible: root.sourceKind === "library"
            text: root.service && root.service.contentMeta.updating ? "Indexing…" : "Re-index"
            foreground: root.foreground
            focusable: true
            enabled: root.service && !root.service.actionBusy
              && !root.service.contentMeta.updating
              && root.can("library.update.start")
            onClicked: root.service.startLibraryUpdate()
          }

          Button {
            iconText: "󰑐"
            tooltipText: "Refresh"
            foreground: root.foreground
            focusable: true
            iconSpinning: root.service ? root.service.contentLoading : false
            enabled: root.service && !root.service.contentLoading
              && (root.sourceKind === "favorites"
                  ? root.can("content.favorites.refresh") : root.can("content.browse"))
            onClicked: root.service.reloadContent()
          }

          Button {
            visible: root.service && root.service.contentKind === "queue"
              && root.service.contentItems.length > 0
            iconText: "󰅖"
            text: root.confirmation === "queue-clear" ? "Confirm clear" : "Clear"
            foreground: root.confirmation === "queue-clear" ? Color.urgent : root.foreground
            bordered: true
            focusable: true
            enabled: root.service && !root.service.actionBusy && root.can("queue.clear")
            onClicked: if (root.arm("queue-clear")) root.service.clearQueue()
          }

          Button {
            visible: root.service && root.service.contentKind === "playlist"
            text: "Play all"
            iconText: "󰐊"
            foreground: root.foreground
            bordered: true
            focusable: true
            enabled: root.service && !root.service.actionBusy
              && root.can("playlists.mutate")
            onClicked: root.service.playlistAction("play", root.service.contentTerm)
          }

          Button {
            visible: root.service && root.service.contentKind === "playlist"
            text: root.confirmation === "playlist-delete" ? "Confirm delete" : "Delete"
            iconText: "󰅖"
            foreground: root.confirmation === "playlist-delete" ? Color.urgent : root.foreground
            bordered: true
            focusable: true
            enabled: root.service && !root.service.actionBusy
              && root.can("playlists.mutate")
            onClicked: if (root.arm("playlist-delete"))
              root.service.playlistAction("delete", root.service.contentTerm)
          }
        }
      }

      Column {
        width: parent.width
        spacing: Style.space(4)

        Repeater {
          model: root.service ? root.service.contentItems : []

          delegate: BorderSurface {
            id: resultCard
            required property var modelData
            readonly property string rowKey: String(root.service ? root.service.contentKind : "")
              + ":" + String(modelData.index) + ":" + String(modelData.id)
            width: parent.width
            implicitHeight: root.showArtwork ? Style.space(64) : Style.space(52)
            radius: Style.cornerRadius
            color: modelData.current === true
              ? Style.selectedFillFor(root.foreground, Color.accent)
              : "transparent"
            borderSpec: Border.none()

            Rectangle {
              anchors.left: parent.left
              anchors.top: parent.top
              anchors.bottom: parent.bottom
              width: Style.space(3)
              color: modelData.current === true ? Color.accent : "transparent"

              Behavior on color { ColorAnimation { duration: 140 } }
            }

            Rectangle {
              anchors.left: root.showArtwork ? resultArtworkSurface.right : parent.left
              anchors.leftMargin: root.showArtwork ? Style.space(9) : Style.space(10)
              anchors.right: parent.right
              anchors.rightMargin: Style.space(8)
              anchors.bottom: parent.bottom
              height: Style.spacing.hairline
              color: Util.alpha(root.foreground, 0.08)
            }

            BorderSurface {
              id: resultArtworkSurface
              anchors.left: parent.left
              anchors.leftMargin: Style.space(8)
              anchors.verticalCenter: parent.verticalCenter
              width: Style.space(46)
              height: Style.space(46)
              radius: Style.spacing.labelGap
              color: Style.selectedFillFor(root.foreground, Color.accent)
              borderSpec: Border.flat(Util.alpha(root.foreground, 0.1),
                Math.max(1, Style.normalBorderWidth))
              clip: true
              visible: root.showArtwork

              Image {
                id: resultArtwork
                anchors.fill: parent
                source: String(modelData.album_art || "")
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                cache: true
                opacity: status === Image.Ready ? 1.0 : 0.0

                Behavior on opacity {
                  NumberAnimation { duration: 160; easing.type: Easing.OutCubic }
                }
              }

              Text {
                anchors.centerIn: parent
                visible: resultArtwork.status !== Image.Ready
                text: modelData.browsable === true ? "󰉋"
                  : (root.service && root.service.contentKind === "playlists" ? "󰒛"
                     : (root.service && root.service.contentKind === "queue" ? "󰎇" : "󰐊"))
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.iconLarge
                opacity: 0.55
              }
            }

            Row {
              id: resultActions
              anchors.right: parent.right
              anchors.rightMargin: resultCard.borderRight + Style.space(6)
              anchors.verticalCenter: parent.verticalCenter
              spacing: Style.space(4)

              Button {
                iconText: modelData.browsable === true ? "󰅂"
                  : (root.service && root.service.contentKind === "playlists" ? "󰅂" : "󰐊")
                tooltipText: modelData.browsable === true ? "Open folder"
                  : (root.service && root.service.contentKind === "playlists"
                     ? "Open playlist" : "Play now")
                foreground: root.foreground
                focusable: true
                selected: modelData.current === true
                enabled: root.service && !root.service.actionBusy
                  && ((root.service.contentKind === "library"
                       && modelData.browsable === true && root.can("content.browse"))
                      || (root.canPlayCurrentKind() && modelData.playable !== false))
                opacity: enabled ? 1.0 : 0.35
                onClicked: {
                  if (root.service.contentKind === "library" && modelData.browsable === true) {
                    browseFlick.contentY = 0
                    root.service.openLibraryItem(modelData)
                  } else {
                    root.service.playContent(modelData)
                  }
                }
              }

              Button {
                visible: root.service && root.service.contentKind === "library"
                  && modelData.browsable === true && modelData.playable === true
                text: "Play"
                foreground: root.foreground
                bordered: true
                focusable: true
                enabled: root.service && !root.service.actionBusy
                  && root.can("queue.content.enqueue")
                onClicked: root.service.enqueueContent(modelData, "play")
              }

              Button {
                visible: root.service && root.service.contentKind === "apple"
                  && String(modelData.album_url || "") !== ""
                text: "Album"
                tooltipText: "Play the whole album"
                foreground: root.foreground
                bordered: true
                focusable: true
                enabled: root.service && !root.service.actionBusy
                  && root.can("content.apple.album.play")
                onClicked: root.service.playAppleAlbum(modelData)
              }

              Button {
                visible: root.service && (root.service.contentKind === "library"
                  || root.service.contentKind === "playlist")
                  && modelData.playable === true
                text: "Next"
                foreground: root.foreground
                bordered: true
                focusable: true
                enabled: root.service && !root.service.actionBusy
                  && root.can("queue.content.enqueue") && modelData.playable !== false
                onClicked: root.service.enqueueContent(modelData, "next")
              }

              Button {
                visible: root.service && (root.service.contentKind === "library"
                  || root.service.contentKind === "playlist")
                  && modelData.playable === true
                text: "End"
                foreground: root.foreground
                bordered: true
                focusable: true
                enabled: root.service && !root.service.actionBusy
                  && root.can("queue.content.enqueue") && modelData.playable !== false
                onClicked: root.service.enqueueContent(modelData, "end")
              }

              Button {
                visible: root.service && root.service.contentKind === "playlist"
                iconText: "󰁝"
                tooltipText: "Move up"
                foreground: root.foreground
                focusable: true
                enabled: root.service && !root.service.actionBusy
                  && root.can("playlists.track.mutate") && Number(modelData.index) > 0
                onClicked: root.service.playlistTrackAction("up", modelData)
              }

              Button {
                visible: root.service && root.service.contentKind === "playlist"
                iconText: "󰁅"
                tooltipText: "Move down"
                foreground: root.foreground
                focusable: true
                enabled: root.service && !root.service.actionBusy
                  && root.can("playlists.track.mutate")
                  && Number(modelData.index) < root.service.contentItems.length - 1
                onClicked: root.service.playlistTrackAction("down", modelData)
              }

              Button {
                visible: root.service && (root.service.contentKind === "queue"
                  || root.service.contentKind === "playlist")
                iconText: "󰅖"
                tooltipText: root.confirmation === resultCard.rowKey
                  ? "Press again to confirm" : "Remove"
                foreground: root.confirmation === resultCard.rowKey ? Color.urgent : root.foreground
                focusable: true
                enabled: root.service && !root.service.actionBusy
                  && (root.service.contentKind === "queue"
                      ? root.can("queue.item.remove")
                      : root.can("playlists.track.mutate"))
                onClicked: {
                  if (!root.arm(resultCard.rowKey)) return
                  if (root.service.contentKind === "queue")
                    root.service.removeQueueItem(Number(modelData.index), String(modelData.id))
                  else root.service.playlistTrackAction("remove", modelData)
                }
              }
            }

            Column {
              anchors.left: root.showArtwork ? resultArtworkSurface.right : parent.left
              anchors.leftMargin: root.showArtwork ? Style.space(9)
                : Style.space(10)
              anchors.right: resultActions.left
              anchors.rightMargin: Style.space(7)
              anchors.verticalCenter: parent.verticalCenter
              spacing: Style.space(2)

              Text {
                width: parent.width
                text: String(modelData.title || "Untitled")
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                font.bold: modelData.current === true
                elide: Text.ElideRight
              }

              Text {
                width: parent.width
                visible: text !== ""
                text: String(modelData.subtitle || "")
                color: Qt.darker(root.foreground, 1.45)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                elide: Text.ElideRight
              }
            }
          }
        }

        Text {
          width: parent.width
          visible: !root.service || root.service.contentItems.length === 0
          text: root.emptyMessage()
          color: Qt.darker(root.foreground, 1.45)
          font.family: root.fontFamily
          font.pixelSize: Style.font.bodySmall
          horizontalAlignment: Text.AlignHCenter
          wrapMode: Text.WordWrap
          topPadding: Style.space(20)
          bottomPadding: Style.space(20)
        }
      }
    }
  }
}
