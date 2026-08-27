from unittest.mock import MagicMock, patch

import requests

from sonarchy_backend.artwork_probe import (
    SPEAKER_ARTWORK_TIMEOUT,
    speaker_artwork_available,
)


@patch("sonarchy_backend.artwork_probe.requests.get")
def test_probe_accepts_only_successful_images_without_redirects(get):
    response = MagicMock(status_code=200, headers={"Content-Type": "image/jpeg; charset=binary"})
    response.__enter__.return_value = response
    get.return_value = response

    assert speaker_artwork_available("http://10.0.0.2:1400/getaa") is True
    get.assert_called_once_with(
        "http://10.0.0.2:1400/getaa",
        headers={"Accept": "image/*"},
        stream=True,
        allow_redirects=False,
        timeout=SPEAKER_ARTWORK_TIMEOUT,
    )


def test_probe_allows_slow_speaker_responses_without_relaxing_connect_timeout():
    assert SPEAKER_ARTWORK_TIMEOUT == (0.5, 5.0)


@patch("sonarchy_backend.artwork_probe.requests.get")
def test_probe_rejects_missing_images_and_network_failures(get):
    response = MagicMock(status_code=404, headers={"Content-Type": "text/html"})
    response.__enter__.return_value = response
    get.return_value = response
    assert speaker_artwork_available("http://10.0.0.2:1400/missing") is False

    response.status_code = 200
    assert speaker_artwork_available("http://10.0.0.2:1400/not-an-image") is False

    get.side_effect = requests.Timeout("speaker unavailable")
    assert speaker_artwork_available("http://10.0.0.2:1400/slow") is False
