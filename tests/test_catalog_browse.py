import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from sonarchy_backend.apple_catalog import (
    APPLE_RESPONSE_LIMIT,
    apple_artwork_url,
    apple_search_results,
    public_apple_album_url,
    public_apple_music_url,
    resolve_apple_artwork,
    validate_search_term,
)
from sonarchy_backend.domains.browse import (
    album_art_url,
    apple_content,
    browse_content,
    didl_item_payload,
    favorites_content,
    format_duration,
    global_content,
    global_results,
    library_content,
    playlist_content,
    playlists_content,
    public_artwork_url,
    queue_content,
    validate_playlist_id,
)


class Result(list):
    @property
    def total_matches(self):
        return len(self)


class Response:
    def __init__(self, payload=None, *, status=200, headers=None, chunks=None):
        self.status_code = status
        self.headers = headers or {}
        self.payload = payload if payload is not None else {"results": []}
        self.chunks = chunks
        self.closed = False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("HTTP failure")

    def iter_content(self, chunk_size):
        assert chunk_size == 16384
        if self.chunks is not None:
            yield from self.chunks
        else:
            yield json.dumps(self.payload).encode()

    def close(self):
        self.closed = True


def music_item(item_id="T:1", title="Track", *, playable=True):
    return SimpleNamespace(
        item_id=item_id,
        title=title,
        creator="Artist",
        album="Album",
        album_art_uri="/getaa?s=1",
        resources=[SimpleNamespace(uri="x-test:item")] if playable else [],
        can_play=playable,
    )


@pytest.mark.parametrize(
    "url",
    (
        "http://music.apple.com/ch/song/x/1",
        "https://user@music.apple.com/ch/song/x/1",
        "https://music.apple.com:444/ch/song/x/1",
        "https://example.test/ch/song/x/1",
    ),
)
def test_apple_music_url_rejects_untrusted_variants(url):
    assert public_apple_music_url(url) == ""


def test_apple_album_and_artwork_urls_are_canonical_and_bounded():
    album = "https://music.apple.com/ch/album/example/123?i=456#track"
    assert public_apple_album_url(album, "123") == "https://music.apple.com/ch/album/example/123"
    assert public_apple_album_url(album, "999") == ""
    assert public_apple_album_url("https://music.apple.com/ch/song/example/123") == ""

    artwork = "https://is1-ssl.mzstatic.com/image/100x100bb.jpg?x=1#fragment"
    assert "/1200x1200bb.jpg" in apple_artwork_url(artwork, 5000)
    assert apple_artwork_url("https://example.test/image.jpg") == ""
    assert apple_artwork_url("https://127.0.0.1/image.jpg") == ""


def test_apple_search_streams_bounded_json_and_closes_response():
    response = Response(
        {
            "results": [
                {"trackName": "Song"},
                "not-an-object",
            ]
        }
    )
    request = Mock(return_value=response)
    assert apple_search_results("song", 500, request_get=request, country="bad") == [
        {"trackName": "Song"}
    ]
    assert request.call_args.kwargs["params"]["limit"] == 100
    assert request.call_args.kwargs["params"]["country"] == "CH"
    assert response.closed is True
    assert apple_search_results("", 5, request_get=request) == []


@pytest.mark.parametrize(
    "response",
    (
        Response(status=302),
        Response(headers={"content-length": str(APPLE_RESPONSE_LIMIT + 1)}),
        Response(chunks=[b"x" * (APPLE_RESPONSE_LIMIT + 1)]),
    ),
)
def test_apple_search_rejects_redirects_and_oversized_responses(response):
    with pytest.raises(ValueError):
        apple_search_results("song", 5, request_get=lambda *_args, **_kwargs: response)
    assert response.closed is True


def test_apple_search_term_and_artwork_resolution():
    with pytest.raises(ValueError, match="required"):
        validate_search_term("", allow_empty=False)
    with pytest.raises(ValueError, match="too long"):
        validate_search_term("x" * 121)

    payload = {
        "results": [
            {
                "trackName": "Song",
                "artistName": "Artist",
                "collectionName": "Album",
                "artworkUrl100": "https://is1-ssl.mzstatic.com/image/100x100bb.jpg",
            }
        ]
    }
    result = resolve_apple_artwork(
        "Song", "Artist", request_get=lambda *_args, **_kwargs: Response(payload)
    )
    assert result["match"] is True
    miss = resolve_apple_artwork(
        "Different", "Artist", request_get=lambda *_args, **_kwargs: Response(payload)
    )
    assert miss["match"] is False


def test_artwork_policy_allows_only_speaker_http_or_reviewed_public_https():
    assert album_art_url("/getaa?s=1", "192.168.1.2").startswith("http://192.168.1.2:1400/")
    assert album_art_url("http://192.168.1.3:1400/getaa", "192.168.1.2") == ""
    assert public_artwork_url("https://is1-ssl.mzstatic.com/image.jpg")
    assert public_artwork_url("https://localhost/image.jpg") == ""
    assert public_artwork_url("https://example.test/image.jpg") == ""


def test_queue_favorites_library_and_playlist_projections():
    track = music_item()
    favorite = SimpleNamespace(
        item_id="F:1",
        title="Favorite",
        description="Radio",
        album_art_uri="/fav.jpg",
        reference=SimpleNamespace(resources=[SimpleNamespace(uri="x-test:fav")]),
    )
    unplayable = SimpleNamespace(
        item_id="F:2",
        title="Broken",
        description="",
        album_art_uri="",
        reference=SimpleNamespace(resources=[]),
    )
    playlist = SimpleNamespace(item_id="SQ:1", title="Morning")
    invalid_playlist = SimpleNamespace(item_id="bad", title="Ignored")
    library = SimpleNamespace(
        library_updating=True,
        list_library_shares=Mock(return_value=["//server/music"]),
        get_sonos_favorites=Mock(return_value=Result([favorite, unplayable])),
        get_music_library_information=Mock(return_value=Result([track])),
        browse=Mock(return_value=Result([track])),
    )
    coordinator = SimpleNamespace(
        ip_address="192.168.1.2",
        music_library=library,
        get_queue=Mock(return_value=Result([track])),
        get_current_track_info=Mock(return_value={"playlist_position": "1"}),
        get_sonos_playlists=Mock(return_value=Result([playlist, invalid_playlist])),
        get_sonos_playlist_by_attr=Mock(return_value=playlist),
    )

    assert queue_content(coordinator, 10)["items"][0]["current"] is True
    assert [entry["playable"] for entry in favorites_content(coordinator, 10)["items"]] == [
        True,
        False,
    ]
    assert library_content(coordinator, "", 10)["shares"] == ["//server/music"]
    assert library_content(coordinator, "track", 10)["items"][0]["id"] == "T:1"
    assert playlists_content(coordinator, 10)["total"] == 2
    assert playlist_content(coordinator, "SQ:1", 10)["playlist_title"] == "Morning"
    assert didl_item_payload(track, 0, coordinator.ip_address)["playable"] is True
    with pytest.raises(ValueError, match="playlist identifier"):
        validate_playlist_id("bad")


def test_apple_and_global_content_normalize_provider_results():
    apple_result = {
        "trackId": 1,
        "trackName": "Song",
        "artistName": "Artist",
        "collectionName": "Album",
        "trackTimeMillis": 61000,
        "trackViewUrl": "https://music.apple.com/ch/song/example/1",
        "collectionViewUrl": "https://music.apple.com/ch/album/example/2",
        "collectionId": 2,
        "artworkUrl100": "https://is1-ssl.mzstatic.com/image/100x100bb.jpg",
    }
    payload = apple_content(
        "song", 5, request_get=lambda *_args, **_kwargs: Response({"results": [apple_result]})
    )
    assert payload["items"][0]["subtitle"] == "Artist · Album · 1:01"
    assert format_duration("bad") == ""

    station = music_item("G:1", "Station")
    coordinator = SimpleNamespace(ip_address="192.168.1.2")
    service = Mock()
    service.search.return_value = Result([station])
    assert global_results(
        coordinator, "news", 5, music_service_factory=Mock(return_value=service)
    ) == [station]
    with patch("sonarchy_backend.domains.browse.global_results", return_value=Result([station])):
        assert global_content(coordinator, "news", 5)["items"][0]["playable"] is True


def test_browse_dispatch_rejects_unknown_and_missing_room():
    with pytest.raises(ValueError, match="Unsupported content kind"):
        browse_content(None, "bluetooth", "", 10)
    with pytest.raises(ValueError, match="room is required"):
        browse_content(None, "queue", "", 10)
