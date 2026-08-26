from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from sonarchy_backend.domains.content import (
    play_apple,
    play_apple_album,
    play_global,
    start_library_update,
)
from sonarchy_backend.domains.playlists import (
    playlist_action,
    playlist_track_action,
    playlists_service,
    validate_playlist_title,
)
from sonarchy_backend.domains.queue import (
    enqueue_content_item,
    find_library_item,
    find_playlist_track,
    queue_action,
    queue_service,
)


def speaker(**values):
    return SimpleNamespace(group=None, **values)


def item(item_id="I:1", *, resources=None, title="Item", can_play=True):
    return SimpleNamespace(
        item_id=item_id,
        resources=[SimpleNamespace(uri="x-test:item")] if resources is None else resources,
        title=title,
        can_play=can_play,
    )


@pytest.mark.parametrize(
    ("index", "expected_id"),
    ((None, "Q:1"), (-1, "Q:1"), (2, "Q:1"), (0, "Q:stale")),
)
def test_queue_identity_failures_do_not_mutate(index, expected_id):
    room = speaker(
        get_queue=Mock(return_value=[item("Q:1")]),
        remove_from_queue=Mock(),
    )

    with pytest.raises(ValueError):
        queue_action(room, "remove-queue", index, expected_id)

    room.remove_from_queue.assert_not_called()


def test_queue_rejects_unknown_action():
    with pytest.raises(ValueError, match="Unsupported queue action"):
        queue_action(speaker(), "replace-queue")


@pytest.mark.parametrize("term", ("", "bad\nterm", "x" * 121))
def test_library_search_rejects_unsafe_terms(term):
    library = Mock()
    with pytest.raises(ValueError, match="Search text"):
        find_library_item(SimpleNamespace(music_library=library), "L:1", term)
    library.get_music_library_information.assert_not_called()


def test_library_and_playlist_staleness_are_rejected():
    library = Mock()
    library.get_music_library_information.return_value = [item("L:other")]
    coordinator = SimpleNamespace(
        music_library=library,
        get_sonos_playlist_by_attr=Mock(return_value=object()),
    )
    with pytest.raises(ValueError, match="no longer available"):
        find_library_item(coordinator, "L:1", "song")

    library.browse.return_value = [item("T:1")]
    with pytest.raises(ValueError, match="playlist changed"):
        find_playlist_track(coordinator, "SQ:1", 2, "T:1")
    with pytest.raises(ValueError, match="playlist changed"):
        find_playlist_track(coordinator, "SQ:1", 0, "T:stale")


def test_enqueue_rejects_wrong_kind_empty_resource_and_mode():
    room = speaker()
    with pytest.raises(ValueError, match="Only library and playlist"):
        enqueue_content_item(room, "radio", "context", "I:1", 0, "play")

    with (
        patch(
            "sonarchy_backend.domains.queue.find_library_item",
            return_value=item(resources=[]),
        ),
        pytest.raises(ValueError, match="playable resource"),
    ):
        enqueue_content_item(room, "library", "song", "I:1", 0, "play")
    with (
        patch("sonarchy_backend.domains.queue.find_library_item", return_value=item()),
        pytest.raises(ValueError, match="queue position"),
    ):
        enqueue_content_item(room, "library", "song", "I:1", 0, "middle")


def test_queue_and_playlist_services_reject_fractional_indices():
    backend = Mock()
    with pytest.raises(ValueError, match="integer"):
        queue_service(backend).execute(
            "queue.item.play", {"roomUid": "R1", "index": 1.5, "itemId": "Q:1"}
        )
    with pytest.raises(ValueError, match="integer"):
        playlists_service(backend).execute(
            "playlists.track.mutate",
            {
                "roomUid": "R1",
                "action": "down",
                "playlistId": "SQ:1",
                "index": 1.5,
                "itemId": "T:1",
            },
        )


def test_playlist_validation_and_empty_queue_fail_before_mutation():
    with pytest.raises(ValueError, match="cannot be empty"):
        validate_playlist_title("  ")
    with pytest.raises(ValueError, match="too long"):
        validate_playlist_title("x" * 81)

    room = speaker(queue_size=0, create_sonos_playlist_from_queue=Mock())
    with pytest.raises(ValueError, match="queue is empty"):
        playlist_action(room, "save-queue", "Saved")
    room.create_sonos_playlist_from_queue.assert_not_called()
    with pytest.raises(ValueError, match="Unsupported playlist action"):
        playlist_action(room, "rename", "Saved")


@pytest.mark.parametrize(
    ("action", "index", "count", "message"),
    (
        ("up", 0, 2, "already first"),
        ("down", 1, 2, "already last"),
        ("sideways", 0, 2, "Unsupported"),
    ),
)
def test_playlist_track_boundaries_do_not_mutate(action, index, count, message):
    room = speaker(
        move_in_sonos_playlist=Mock(),
        remove_from_sonos_playlist=Mock(),
    )
    with (
        patch(
            "sonarchy_backend.domains.playlists.find_playlist_track",
            return_value=(object(), item(), count),
        ),
        pytest.raises(ValueError, match=message),
    ):
        playlist_track_action(room, action, "SQ:1", index, "T:1")
    room.move_in_sonos_playlist.assert_not_called()
    room.remove_from_sonos_playlist.assert_not_called()


def test_content_provider_rejections_and_library_states():
    room = speaker()
    with pytest.raises(ValueError, match="Apple Music link"):
        play_apple(room, "https://example.test/song")
    with pytest.raises(ValueError, match="album link"):
        play_apple_album(room, "https://music.apple.com/ch/song/example/1")

    unplayable = item("G:1", resources=[], can_play=False)
    with pytest.raises(ValueError, match="not directly playable"):
        play_global(room, "G:1", "news", results_fn=lambda *_args: [unplayable])
    with pytest.raises(ValueError, match="no longer exists"):
        play_global(room, "G:1", "news", results_fn=lambda *_args: [])

    updating = speaker(music_library=SimpleNamespace(library_updating=True))
    assert start_library_update(updating)["message"] == "Library update is already running"
    library = SimpleNamespace(library_updating=False, start_library_update=Mock())
    assert (
        start_library_update(speaker(music_library=library))["message"] == "Library update started"
    )
    library.start_library_update.assert_called_once_with()
