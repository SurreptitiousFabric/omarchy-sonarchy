from __future__ import annotations

from sonarchy_errors import upnp_error_code, user_facing_error


class FakeUPnPError(Exception):
    error_code = "701"

    def __str__(self) -> str:
        return "UPnP Error 701 received: Transition not available from 192.168.1.103"


def test_upnp_error_701_has_a_recovery_instruction_without_an_ip_address():
    message = user_facing_error(FakeUPnPError())

    assert upnp_error_code(FakeUPnPError()) == "701"
    assert "Wait a moment" in message
    assert "Sonos error 701" in message
    assert "192.168" not in message


def test_known_content_errors_explain_what_the_user_should_do():
    assert "Choose another item" in user_facing_error("UPnP Error 704 received")
    assert "Refresh the list" in user_facing_error("UPnP Error 716 received")


def test_unknown_errors_are_compacted_and_strip_the_speaker_address():
    message = user_facing_error("A strange network error from 192.168.1.103")
    assert message == "A strange network error"


def test_empty_error_uses_plain_fallback():
    assert user_facing_error("", "Could not rename the room") == "Could not rename the room"
