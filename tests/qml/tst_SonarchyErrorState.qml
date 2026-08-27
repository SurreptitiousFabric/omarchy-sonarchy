import QtQuick
import QtTest
import "."

Item {
  SonarchyErrorState {
    id: errorState
  }

  TestCase {
    name: "SonarchyErrorStateOwnership"

    function init() {
      errorState.clearError()
    }

    function test_unrelated_success_cannot_clear_foreground_error() {
      errorState.setError("Playback failed", "Fallback", "action-7")
      compare(errorState.message, "Playback failed")
      compare(errorState.ownerId, "action-7")
      verify(!errorState.clearError("details-8"))
      compare(errorState.message, "Playback failed")
      verify(errorState.clearError("action-7"))
      compare(errorState.message, "")
    }

    function test_explicit_clear_removes_any_error() {
      errorState.setError("Local validation failed", "Fallback", "")
      verify(!errorState.clearError("content-9"))
      compare(errorState.message, "Local validation failed")
      verify(errorState.clearError())
      compare(errorState.message, "")
      compare(errorState.ownerId, "")
    }

    function test_unrelated_background_error_cannot_replace_foreground_error() {
      verify(errorState.setError("Playback failed", "Fallback", "action-7", true))
      verify(!errorState.setError("Details failed", "Fallback", "details-8", false))
      compare(errorState.message, "Playback failed")
      compare(errorState.ownerId, "action-7")
    }

    function test_foreground_error_can_replace_background_error() {
      verify(errorState.setError("Details failed", "Fallback", "details-8", false))
      verify(errorState.setError("Playback failed", "Fallback", "action-7", true))
      compare(errorState.message, "Playback failed")
      compare(errorState.ownerId, "action-7")
    }

    function test_messages_are_compacted_and_bounded() {
      errorState.setError("  too   much\nspace  ", "Fallback", "request-1")
      compare(errorState.message, "too much space")
      errorState.setError("x".repeat(200), "Fallback", "request-1")
      compare(errorState.message.length, 178)
      verify(errorState.message.endsWith("…"))
    }
  }
}
