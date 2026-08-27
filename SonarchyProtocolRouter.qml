import QtQuick

Item {
  id: router
  required property var store
  required property var live

  function stopRequestErrorTimer() { requestErrorTimer.stop() }
  function restartRequestErrorTimer() { requestErrorTimer.restart() }
  function restartActionMessageTimer() { actionMessageTimer.restart() }
  function restartVolumeDebounce() { volumeDebounce.restart() }

  Connections {
    target: router.live
    function onSnapshotChanged() { router.store.applyLiveSnapshot() }
    function onCommandResult(message) {
      if (String(message.id || "") === router.store.protocolActionRequestId) {
        var actionRequestId = String(message.id || "")
        var actionPayload = message.ok === true ? message.value : null
        var completedAction = String(actionPayload && actionPayload.action || "")
        var failedOperation = String(message.error && message.error.operation || "")
        router.store.protocolActionRequestId = ""
        if (!actionPayload || actionPayload.ok !== true) {
          router.store.setRequestError(
            router.live.errorMessage(message.error), router.store.actionFallback,
            actionRequestId, true)
        } else {
          router.store.clearRequestError(actionRequestId)
          router.store.showActionMessage(String(actionPayload.message || "Updated"))
          if (completedAction === "rename") {
            router.store.optimisticDevicePatch(
              router.store.selectedIp, { name: String(actionPayload.name || "") })
            renameRefresh.restart()
          }
        }
        if (completedAction !== "rename" || !actionPayload || actionPayload.ok !== true)
          delayedRefresh.restart()
        if (completedAction === "playlist-delete")
          Qt.callLater(function() { router.store.loadContent("playlists", "") })
        else if (completedAction.indexOf("playlist-") === 0
                 || completedAction.indexOf("queue-") === 0
                 || completedAction === "library-update")
          Qt.callLater(router.store.reloadContent)
        if (completedAction.indexOf("alarm-") === 0)
          Qt.callLater(router.store.loadAlarms)
        else if (failedOperation.indexOf("alarms.") === 0)
          Qt.callLater(router.store.loadAlarms)
        return
      }
      if (String(message.id || "") === router.store.artworkRequestId) {
        var completedKey = router.store.artworkRequestKey
        var payload = message.ok === true ? message.value : null
        var artworkUrl = ""
        if (payload && payload.ok === true && payload.match === true)
          artworkUrl = router.store.safeArtworkUrl(payload.artwork_url)
        router.store.cacheArtwork(completedKey, artworkUrl)
        router.store.artworkRequestId = ""
        router.store.artworkRequestKey = ""
        router.store.artworkRequestTitle = ""
        router.store.artworkRequestArtist = ""
        router.store.applyLiveSnapshot()
        Qt.callLater(router.store.maybeRequestRadioArtwork)
        return
      }
      if (String(message.id || "") === router.store.contentRequestId) {
        var completedContentRequestId = String(message.id || "")
        router.store.contentLoading = false
        var payload = message.ok === true ? message.value : null
        var stillCurrentContent = router.store.selectedDevice
          && router.store.contentRequestRoomUid === String(router.store.selectedDevice.uid || "")
          && router.store.contentRequestKind === router.store.contentKind
          && router.store.contentRequestTerm === router.store.contentTerm
          && router.store.contentRequestContextKey === router.store.contentContextKey()
        router.store.contentRequestId = ""
        router.store.contentRequestRoomUid = ""
        router.store.contentRequestContextKey = ""
        if (payload && payload.ok === true && Array.isArray(payload.items)
            && stillCurrentContent) {
          var safeItems = []
          for (var i = 0; i < payload.items.length; i++) {
            var item = Object.assign({}, payload.items[i])
            item.album_art = router.store.safeArtworkUrl(item.album_art)
            safeItems.push(item)
          }
          router.store.contentItems = safeItems
          router.store.contentTotal = Number(payload.total || safeItems.length)
          router.store.contentMeta = {
            shares: Array.isArray(payload.shares) ? payload.shares : [],
            updating: payload.updating === true,
            playlistId: String(payload.playlist_id || ""),
            playlistTitle: String(payload.playlist_title || ""),
            breadcrumbs: Array.isArray(payload.breadcrumbs) ? payload.breadcrumbs : [],
            currentTitle: String(payload.current_title || ""),
            offset: Number(payload.offset || 0),
            pageSize: Number(payload.page_size || 40),
            hasPrevious: payload.has_previous === true,
            hasNext: payload.has_next === true
          }
          router.store.clearRequestError(completedContentRequestId)
        } else if (stillCurrentContent) {
          router.store.setRequestError(
            router.live.errorMessage(message.error), "Could not browse Sonos content",
            completedContentRequestId)
        }
        if (router.store.pendingContentKind !== "") {
          var nextKind = router.store.pendingContentKind
          var nextTerm = router.store.pendingContentTerm
          var nextPath = router.store.pendingContentPath
          var nextOffset = router.store.pendingContentOffset
          router.store.pendingContentKind = ""
          router.store.pendingContentTerm = ""
          router.store.pendingContentPath = []
          router.store.pendingContentOffset = 0
          Qt.callLater(function() {
            router.store.loadContent(nextKind, nextTerm, nextPath, nextOffset)
          })
        }
        return
      }
      if (String(message.id || "") === router.store.alarmsRequestId) {
        var completedAlarmsRequestId = String(message.id || "")
        router.store.alarmsLoading = false
        var alarmsPayload = message.ok === true ? message.value : null
        var stillCurrentAlarms = router.store.selectedDevice
          && router.store.alarmsRequestRoomUid === String(router.store.selectedDevice.uid || "")
        router.store.alarmsRequestId = ""
        router.store.alarmsRequestRoomUid = ""
        if (alarmsPayload && alarmsPayload.ok === true
            && Array.isArray(alarmsPayload.items) && stillCurrentAlarms) {
          router.store.alarms = alarmsPayload.items
          router.store.clearRequestError(completedAlarmsRequestId)
        } else if (stillCurrentAlarms) {
          router.store.setRequestError(
            router.live.errorMessage(message.error), "Could not read Sonos alarms",
            completedAlarmsRequestId)
        }
        return
      }
      if (String(message.id || "") !== router.store.detailsRequestId) return
      var completedDetailsRequestId = String(message.id || "")
      var requestedRoomUid = router.store.detailsRequestRoomUid
      router.store.detailsLoading = false
      router.store.detailsRequestId = ""
      router.store.detailsRequestRoomUid = ""
      var stillCurrent = router.store.selectedDevice
        && requestedRoomUid === String(router.store.selectedDevice.uid || "")
      if (message.ok === true && message.value && message.value.ok === true && stillCurrent) {
        router.store.details = message.value
        router.store.clearRequestError(completedDetailsRequestId)
      } else if (stillCurrent) {
        router.store.setRequestError(
          router.live.errorMessage(message.error), "Could not read Sonos settings",
          completedDetailsRequestId)
      }
      if (router.store.detailsQueued) {
        router.store.detailsQueued = false
        router.store.contentLoading = false
        router.store.contentRequestId = ""
        router.store.contentRequestRoomUid = ""
        router.store.alarmsLoading = false
        router.store.alarmsRequestId = ""
        router.store.alarmsRequestRoomUid = ""
        Qt.callLater(router.store.refreshDetails)
      }
    }
    function onBackendReadyChanged() {
      if (!router.live.backendReady) {
        if (router.store.protocolActionRequestId !== "")
          router.store.setRequestError(
            "The Sonos backend stopped", router.store.actionFallback,
            router.store.protocolActionRequestId, true)
        router.store.protocolActionRequestId = ""
        router.store.detailsLoading = false
        router.store.detailsRequestId = ""
        router.store.detailsRequestRoomUid = ""
        router.store.detailsQueued = false
        router.store.contentLoading = false
        router.store.contentRequestId = ""
        router.store.contentRequestRoomUid = ""
        router.store.contentRequestKind = ""
        router.store.contentRequestTerm = ""
        router.store.contentRequestContextKey = ""
        router.store.pendingContentKind = ""
        router.store.pendingContentTerm = ""
        router.store.pendingContentPath = []
        router.store.pendingContentOffset = 0
        router.store.alarmsLoading = false
        router.store.alarmsRequestId = ""
        router.store.alarmsRequestRoomUid = ""
        router.store.artworkRequestId = ""
        router.store.artworkRequestKey = ""
        router.store.artworkRequestTitle = ""
        router.store.artworkRequestArtist = ""
        router.store.queuedVolume = -1
        router.store.queuedVolumeGroupUid = ""
        volumeDebounce.stop()
      } else if (router.store.panelOpen) {
        Qt.callLater(router.store.refreshDetails)
        if (router.store.contentKind !== "favorites") Qt.callLater(router.store.reloadContent)
      }
    }
  }

  Timer {
    interval: 15000
    running: router.store.panelOpen && router.store.selectedIp !== ""
    repeat: true
    onTriggered: router.store.refreshDetails()
  }

  Timer {
    id: delayedRefresh
    interval: 500
    repeat: false
    onTriggered: {
      router.live.refresh()
      router.store.refreshDetails()
      if (router.store.contentKind === "queue") router.store.reloadContent()
      else if (router.store.contentKind === "favorites") router.store.syncLiveFavorites()
    }
  }

  Timer {
    id: renameRefresh
    interval: 5500
    repeat: false
    onTriggered: {
      router.live.refresh()
      router.store.refreshDetails()
    }
  }

  Timer {
    id: requestErrorTimer
    interval: 10000
    repeat: false
    onTriggered: router.store.clearRequestError()
  }

  Timer {
    id: actionMessageTimer
    interval: 2600
    repeat: false
    onTriggered: router.store.actionMessage = ""
  }

  Timer {
    id: volumeDebounce
    interval: 140
    repeat: false
    onTriggered: router.store.flushVolume()
  }
}
