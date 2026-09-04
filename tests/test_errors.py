from __future__ import annotations

import copy

from sonarchy_backend.domains.errors import bounded_post_write_capture_evidence
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


def _valid_post_write_capture_evidence():
    return {
        "attempts": [
            {
                "attempt": 1,
                "startedElapsedMs": 0,
                "completedElapsedMs": 1300,
                "outcome": "completed",
                "queueLength": 2,
                "currentPosition": 2,
                "transport": "TRANSITIONING",
                "source": "QUEUE",
                "failedPredicates": ["transportIsPlaying"],
            }
        ],
        "attemptCount": 1,
        "secondAttemptStarted": False,
        "secondAttemptSkipReason": "latestStartLimitExceeded",
    }


def test_post_write_capture_evidence_retains_only_bounded_safe_fields():
    evidence = _valid_post_write_capture_evidence()
    evidence["privateException"] = "DIDL at 192.0.2.1 token=secret"

    assert bounded_post_write_capture_evidence(evidence) == _valid_post_write_capture_evidence()


def test_post_write_capture_evidence_rejects_adversarial_unbounded_values():
    for path, unsafe in (
        (("attempts", 0, "startedElapsedMs"), 10**1000),
        (("attempts", 0, "failedPredicates"), [{}]),
        (("attempts", 0, "transport"), {}),
        (("secondAttemptStarted",), "false"),
    ):
        evidence = copy.deepcopy(_valid_post_write_capture_evidence())
        target = evidence
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = unsafe

        assert bounded_post_write_capture_evidence(evidence) is None
