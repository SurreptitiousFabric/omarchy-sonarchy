from types import SimpleNamespace

import pytest

from sonarchy_backend.domains.playlist_playback_verification import observe_transport_convergence


@pytest.mark.parametrize(
    ("read_duration", "expected_starts"),
    [(0.1, [0.25, 0.5, 0.75, 1.0]), (0.4, [0.25, 0.75, 1.25, 1.75])],
)
def test_transport_observations_use_absolute_cadence_without_catchup_bursts(
    read_duration, expected_starts
):
    now = [0.0]
    starts = []
    status = {"postWriteCaptureEvidence": {}}
    clock = SimpleNamespace(
        monotonic=lambda: now[0],
        sleep=lambda duration: now.__setitem__(0, now[0] + duration),
    )

    def read_transport():
        starts.append(now[0])
        now[0] += read_duration
        return "PLAYING" if len(starts) == 4 else "TRANSITIONING"

    assert (
        observe_transport_convergence(
            read_transport, started=0.0, capture_status=status, clock=clock
        )
        == "ready"
    )
    assert starts == pytest.approx(expected_starts)
    assert status["postWriteCaptureEvidence"]["convergence"]["observationCount"] == 4


def test_transport_observation_does_not_start_after_sleep_overshoots_deadline():
    now = [4.9]
    starts = []
    status = {"postWriteCaptureEvidence": {}}
    clock = SimpleNamespace(
        monotonic=lambda: now[0],
        sleep=lambda duration: now.__setitem__(0, now[0] + duration + 0.01),
    )
    result = observe_transport_convergence(
        lambda: starts.append(now[0]) or "PLAYING",
        started=0.0,
        capture_status=status,
        clock=clock,
    )
    assert result == "convergenceDeadlineExceeded"
    assert starts == []
    assert status["verificationOutcome"] == "inconclusive"
    assert status["postWriteCaptureEvidence"]["convergence"]["observations"] == []


def test_transport_read_started_at_deadline_may_complete_after_it():
    now = [4.9]
    starts = []
    status = {"postWriteCaptureEvidence": {}}
    clock = SimpleNamespace(
        monotonic=lambda: now[0],
        sleep=lambda duration: now.__setitem__(0, now[0] + duration),
    )

    def read_transport():
        starts.append(now[0])
        now[0] += 0.4
        return "PLAYING"

    assert (
        observe_transport_convergence(
            read_transport, started=0.0, capture_status=status, clock=clock
        )
        == "ready"
    )
    assert starts == [5.0]
    observation = status["postWriteCaptureEvidence"]["convergence"]["observations"][0]
    assert observation["startedElapsedMs"] == 5000
    assert observation["completedElapsedMs"] == 5400


def test_transport_observations_stop_at_twenty_when_clock_advances():
    now = [0.0]
    starts = []
    status = {"postWriteCaptureEvidence": {}}
    clock = SimpleNamespace(
        monotonic=lambda: now[0],
        sleep=lambda duration: now.__setitem__(0, now[0] + duration),
    )
    assert (
        observe_transport_convergence(
            lambda: starts.append(now[0]) or "TRANSITIONING",
            started=0.0,
            capture_status=status,
            clock=clock,
        )
        == "convergenceDeadlineExceeded"
    )
    assert starts == [index / 4 for index in range(1, 21)]
    assert status["verificationOutcome"] == "inconclusive"
