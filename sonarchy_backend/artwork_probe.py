from __future__ import annotations

import requests


def speaker_artwork_available(url: str) -> bool:
    """Check a pre-authorized speaker-local artwork URL without retaining its body."""
    try:
        with requests.get(
            url,
            headers={"Accept": "image/*"},
            stream=True,
            allow_redirects=False,
            timeout=(0.5, 1.0),
        ) as response:
            if response.status_code != 200:
                return False
            content_type = str(response.headers.get("Content-Type", "")).partition(";")[0]
            return content_type.strip().casefold().startswith("image/")
    except requests.RequestException:
        return False
