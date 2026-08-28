from __future__ import annotations

import copy
import json
import re
from types import SimpleNamespace

import pytest

from sonarchy_backend.contracts import (
    MAX_PROTOCOL_LINE_BYTES,
    MAX_PROTOCOL_REQUEST_ID_BYTES,
    protocol_line,
    result_payload,
)
from sonarchy_backend.domains.apple_playlist_plan import ApplePlaylistPlanService, PlanTicketStore
from sonarchy_backend.domains.apple_playlist_transaction import (
    apple_song_identity_from_item,
    create_preflighted_apple_playlist,
    inspect_apple_playlist_target,
    verify_apple_items,
)
from sonarchy_backend.domains.common import RequestContext
from sonarchy_backend.domains.errors import PlanConflictError, PlaylistTransactionError
from sonarchy_backend.domains.queue_transaction import (
    QueueStateError,
    capture_queue_backup,
    verify_restored_queue,
)

TRACK_ONE = {
    "catalogId": "1452806384",
    "url": ("https://music.apple.com/ch/album/kiss-me-kiss-me-kiss-me/1452806377?i=1452806384"),
    "title": "Just Like Heaven",
    "artist": "The Cure",
    "album": "Kiss Me, Kiss Me, Kiss Me",
    "durationMs": 212000,
}
TRACK_TWO = {
    "catalogId": "1443065566",
    "url": ("https://music.apple.com/ch/album/the-colour-of-spring/1443065310?i=1443065566"),
    "title": "Life's What You Make It",
    "artist": "Talk Talk",
    "album": "The Colour of Spring",
    "durationMs": 268000,
}


class Result(list):
    def __init__(self, items=(), *, total_matches=None, update_id=1):
        super().__init__(items)
        self.total_matches = len(self) if total_matches is None else total_matches
        self.update_id = update_id


def queue_item(
    item_id,
    title,
    artist="Existing Artist",
    album="Existing Album",
    uri="x-test:existing",
):
    resources = [] if uri is None else [SimpleNamespace(uri=uri)]
    return SimpleNamespace(
        item_id=item_id,
        title=title,
        creator=artist,
        album=album,
        resources=resources,
    )


def apple_item(track, item_id):
    return queue_item(
        item_id,
        track["title"],
        track["artist"],
        track["album"],
        f"x-sonos-http:song%3a{track['catalogId']}.mp4?service=apple",
    )


class FakeTransport:
    def __init__(self, owner):
        self.owner = owner

    def GetMediaInfo(self, _args):
        return {"CurrentURI": self.owner.current_uri}


class FakeMusicLibrary:
    def __init__(self, owner):
        self.owner = owner

    def browse(self, *, ml_item, max_items, **_kwargs):
        tracks = [copy.deepcopy(item) for item in self.owner.playlist_tracks[ml_item.item_id]]
        if self.owner.saved_verification == "reverse":
            tracks.reverse()
        elif self.owner.saved_verification == "wrong-title" and tracks:
            tracks[0].title = "Substituted title"
        elif self.owner.saved_verification == "wrong-identity" and tracks:
            tracks[0].resources[0].uri = "x-sonos-http:song%3a999999.mp4"
        total = (
            self.owner.saved_browse_total
            if self.owner.saved_browse_total is not None
            else len(tracks)
        )
        return Result(tracks[:max_items], total_matches=total)


class FakeShareLinks:
    def __init__(self, owner):
        self.owner = owner

    def add_share_link_to_queue(self, url, *, dc_title):
        track = self.owner.catalog[url]
        item_id = self.owner.apple_item_id or f"Q:{len(self.owner.queue) + 1}"
        self.owner.queue.append(apple_item(track, item_id))
        self.owner.queue_update += 1
        if self.owner.concurrent_playlist_during_queue:
            self.owner.concurrent_playlist_during_queue = False
            raced = SimpleNamespace(item_id="SQ:99", title="AI Friday")
            self.owner.playlists[raced.item_id] = raced
            self.owner.playlist_tracks[raced.item_id] = copy.deepcopy(self.owner.queue)
        first_position = len(self.owner.queue)
        if self.owner.expand_share:
            self.owner.queue.append(apple_item(track, f"Q:{len(self.owner.queue) + 1}"))
            self.owner.queue_update += 1
            self.owner.expand_share = False
        if self.owner.unexpected_queue_extra and url == TRACK_TWO["url"]:
            self.owner.queue.append(apple_item(track, f"Q:{len(self.owner.queue) + 1}"))
            self.owner.queue_update += 1
        if self.owner.wrong_insert_position:
            return first_position + 1
        return first_position


class FakeGroup:
    def __init__(self, coordinator):
        self.coordinator = coordinator
        self.members = [coordinator]
        self.volume = coordinator.volume
        self.mute = coordinator.mute


class FakeSpeaker:
    def __init__(
        self,
        *,
        queue=None,
        position=0,
        transport_state="STOPPED",
        queue_active=True,
    ):
        self.uid = "R1"
        self.volume = 20
        self.mute = False
        self.group = FakeGroup(self)
        self.queue = list(queue or [])
        self.current_position = position if self.queue else -1
        self.transport_state = transport_state
        self.current_uri = "x-rincon-queue:R1#0" if queue_active else "x-sonosapi-stream:radio"
        self.music_source = "QUEUE" if queue_active else "RADIO"
        self.avTransport = FakeTransport(self)
        self.music_library = FakeMusicLibrary(self)
        self.catalog = {TRACK_ONE["url"]: TRACK_ONE, TRACK_TWO["url"]: TRACK_TWO}
        self.playlists = {}
        self.playlist_tracks = {}
        self.queue_update = 1
        self.next_playlist = 1
        self.clear_calls = 0
        self.play_calls = []
        self.expand_share = False
        self.wrong_insert_position = False
        self.fail_create = False
        self.partial_create_failure = False
        self.fail_reopen = False
        self.fail_play_once = False
        self.fail_restore = False
        self.fail_playlist_remove = False
        self.saved_verification = ""
        self.saved_browse_total = None
        self.create_name_race = False
        self.concurrent_playlist_during_queue = False
        self.topology_change_on_create = False
        self.volume_change_on_create = False
        self.unexpected_queue_extra = False
        self.created_title_override = ""
        self.reopened_title_override = ""
        self.drop_queue_after_save = False
        self.play_stays_stopped = False
        self.current_metadata_override = None
        self.apple_item_id = ""

    def get_queue(self, *, max_items, full_album_art_uri):
        assert full_album_art_uri is False
        return Result(
            [copy.deepcopy(item) for item in self.queue[:max_items]],
            total_matches=len(self.queue),
            update_id=self.queue_update,
        )

    def clear_queue(self):
        self.clear_calls += 1
        self.queue = []
        self.current_position = -1
        self.queue_update += 1

    def add_multiple_to_queue(self, items):
        if self.fail_restore:
            raise RuntimeError("private restore failure at 192.168.1.20")
        self.queue = []
        for index, item in enumerate(items, 1):
            restored = copy.deepcopy(item)
            restored.item_id = f"Q:restored:{index}"
            self.queue.append(restored)
        self.queue_update += 1

    def play_from_queue(self, position, start=True):
        self.play_calls.append((position, start))
        self.current_position = position
        self.current_uri = "x-rincon-queue:R1#0"
        self.music_source = "QUEUE"
        self.transport_state = (
            "STOPPED" if self.play_stays_stopped else ("PLAYING" if start else "STOPPED")
        )
        if self.fail_play_once:
            self.fail_play_once = False
            raise RuntimeError("private playback failure token=secret")

    def get_current_track_info(self):
        result = {
            "playlist_position": (
                str(self.current_position + 1) if self.current_position >= 0 else "0"
            )
        }
        if 0 <= self.current_position < len(self.queue):
            current = self.queue[self.current_position]
            result.update({"title": current.title, "artist": current.creator})
        if self.current_metadata_override is not None:
            result.update(self.current_metadata_override)
        return result

    def get_current_transport_info(self):
        return {"current_transport_state": self.transport_state}

    def get_sonos_playlists(self, *, max_items=100):
        items = list(self.playlists.values())
        return Result(items[:max_items], total_matches=len(items))

    def create_sonos_playlist_from_queue(self, title):
        playlist_id = f"SQ:{self.next_playlist}"
        self.next_playlist += 1
        playlist = SimpleNamespace(
            item_id=playlist_id,
            title=self.created_title_override or title,
        )
        if self.partial_create_failure:
            self.playlists[playlist_id] = playlist
            self.playlist_tracks[playlist_id] = copy.deepcopy(self.queue)
            raise RuntimeError("private partial create failure")
        if self.fail_create:
            raise RuntimeError("private create failure")
        self.playlists[playlist_id] = playlist
        self.playlist_tracks[playlist_id] = copy.deepcopy(self.queue)
        if self.create_name_race:
            raced = SimpleNamespace(item_id="SQ:99", title=title)
            self.playlists[raced.item_id] = raced
            self.playlist_tracks[raced.item_id] = copy.deepcopy(self.queue)
        if self.topology_change_on_create:
            self.group.members.append(SimpleNamespace(uid="R2"))
        if self.volume_change_on_create:
            self.volume += 1
        if self.drop_queue_after_save:
            self.queue.pop()
            self.queue_update += 1
        return playlist

    def get_sonos_playlist_by_attr(self, attr_name, value):
        if self.fail_reopen:
            raise RuntimeError("private reopen failure")
        for playlist in self.playlists.values():
            if getattr(playlist, attr_name) == value:
                if self.reopened_title_override:
                    return SimpleNamespace(
                        item_id=playlist.item_id,
                        title=self.reopened_title_override,
                    )
                return playlist
        raise ValueError("missing playlist")

    def remove_sonos_playlist(self, playlist):
        if self.fail_playlist_remove:
            raise RuntimeError("private playlist removal failure")
        self.playlists.pop(playlist.item_id, None)
        self.playlist_tracks.pop(playlist.item_id, None)
        return True


def share_link_factory(coordinator):
    return FakeShareLinks(coordinator)


def original_queue(size=2):
    return [
        queue_item(f"Q:old:{index}", f"Original {index}", uri=f"x-test:existing:{index}")
        for index in range(1, size + 1)
    ]


def add_existing_playlists(speaker, count):
    for index in range(count):
        playlist_id = f"SQ:{1000 + index}"
        speaker.playlists[playlist_id] = SimpleNamespace(
            item_id=playlist_id,
            title=f"Existing playlist {index + 1}",
        )
        speaker.playlist_tracks[playlist_id] = []


def plan_for(speaker, *, mode="save-only", name="AI Friday", tracks=None):
    state = inspect_apple_playlist_target(speaker, name)
    return {
        "operation": "playlists.apple.create",
        "roomUid": speaker.uid,
        "playlistName": name,
        "mode": mode,
        "allowDuplicates": False,
        "tracks": copy.deepcopy(tracks or [TRACK_ONE, TRACK_TWO]),
        "targetState": state,
        "backendRevision": 7,
        "planFingerprint": "test-only",
    }


def execute(speaker, plan):
    return create_preflighted_apple_playlist(
        speaker,
        plan,
        share_link_factory=share_link_factory,
    )


def test_song_identity_is_read_only_from_exact_apple_resource():
    assert apple_song_identity_from_item(apple_item(TRACK_ONE, "Q:1")) == "1452806384"
    ambiguous = apple_item(TRACK_ONE, "song:999")
    assert apple_song_identity_from_item(ambiguous) == ""


def test_verify_items_requires_exact_order_identity_title_and_artist():
    items = [apple_item(TRACK_ONE, "Q:1"), apple_item(TRACK_TWO, "Q:2")]
    evidence = verify_apple_items(items, [TRACK_ONE, TRACK_TWO], container="queue")
    assert [item["position"] for item in evidence] == [1, 2]
    assert [item["canonicalIdentity"] for item in evidence] == [
        "song:1452806384",
        "song:1443065566",
    ]

    with pytest.raises(ValueError, match="identity"):
        verify_apple_items(items, [TRACK_TWO, TRACK_ONE], container="queue")
    items[0].creator = "Another Artist"
    with pytest.raises(ValueError, match="metadata"):
        verify_apple_items(items, [TRACK_ONE, TRACK_TWO], container="queue")


def test_verify_items_rejects_count_missing_metadata_and_wrong_album():
    item = apple_item(TRACK_ONE, "Q:1")
    with pytest.raises(ValueError, match="item count"):
        verify_apple_items([], [TRACK_ONE], container="queue")
    item.creator = ""
    with pytest.raises(ValueError, match="title and artist"):
        verify_apple_items([item], [TRACK_ONE], container="queue")
    item.creator = TRACK_ONE["artist"]
    item.album = "Wrong album"
    with pytest.raises(ValueError, match="album metadata"):
        verify_apple_items([item], [TRACK_ONE], container="queue")


def test_verify_items_projects_bounded_reviewed_metadata_without_sonos_item_identifiers():
    item = apple_item(TRACK_ONE, "Q:" + ("\\" * 510))
    item.title = "Just" + (" " * MAX_PROTOCOL_LINE_BYTES) + "Like Heaven"
    evidence = verify_apple_items([item], [TRACK_ONE], container="queue")

    assert evidence[0]["title"] == TRACK_ONE["title"]
    assert len(evidence[0]["title"]) < len(item.title)
    assert "sonosItemId" not in evidence[0]


def test_save_only_constructs_saves_reopens_and_restores_stopped_queue():
    speaker = FakeSpeaker(queue=original_queue(), position=1, transport_state="STOPPED")
    plan = plan_for(speaker)
    result = execute(speaker, plan)

    assert result["ok"] is True
    assert result["mode"] == "save-only"
    assert result["room"] == {
        "uid": "R1",
        "standalone": True,
        "memberUids": ["R1"],
        "coordinatorUid": "R1",
    }
    assert result["playlist"]["id"] == "SQ:1"
    assert [item["title"] for item in result["playlist"]["items"]] == [
        "Just Like Heaven",
        "Life's What You Make It",
    ]
    assert [item["position"] for item in result["queue"]["approvedItems"]] == [1, 2]
    assert result["queue"]["disposition"] == "restored"
    assert [item.title for item in speaker.queue] == ["Original 1", "Original 2"]
    assert speaker.current_position == 1
    assert speaker.transport_state == "STOPPED"
    assert result["rollback"] == {"attempted": False, "succeeded": None}


def test_maximal_success_result_fits_protocol_without_duplicate_metadata_or_sonos_ids():
    metadata = "\\" * 240
    tracks = []
    for offset in range(25):
        catalog_id = str(3_000_000_000 + offset)
        tracks.append(
            {
                "catalogId": catalog_id,
                "url": f"https://music.apple.com/ch/album/reviewed/999?i={catalog_id}",
                "title": metadata,
                "artist": metadata,
                "album": metadata,
                "durationMs": 212000,
            }
        )
    speaker = FakeSpeaker(queue=original_queue())
    speaker.catalog = {track["url"]: track for track in tracks}
    speaker.apple_item_id = "Q:" + ("\\" * 510)

    result = execute(
        speaker,
        plan_for(
            speaker,
            mode="save-and-play",
            name="\\" * 80,
            tracks=tracks,
        ),
    )
    request_id = "\\" * MAX_PROTOCOL_REQUEST_ID_BYTES
    encoded = protocol_line(result_payload(request_id, revision=7, value=result)).encode("utf-8")

    assert len(encoded) <= MAX_PROTOCOL_LINE_BYTES
    assert all(
        set(item) == {"position", "catalogId", "canonicalIdentity"}
        for item in result["queue"]["approvedItems"]
    )
    assert "sonosItemId" not in json.dumps(result)

    legacy = copy.deepcopy(result)
    duplicated = [
        item | {"sonosItemId": speaker.apple_item_id} for item in result["playlist"]["items"]
    ]
    legacy["playlist"]["items"] = duplicated
    legacy["queue"]["approvedItems"] = copy.deepcopy(duplicated)
    legacy_line = protocol_line(result_payload(request_id, revision=7, value=legacy))
    assert len(legacy_line.encode("utf-8")) > MAX_PROTOCOL_LINE_BYTES


def test_save_only_restores_playing_queue_and_position():
    speaker = FakeSpeaker(queue=original_queue(3), position=2, transport_state="PLAYING")
    result = execute(speaker, plan_for(speaker))

    assert speaker.current_position == 2
    assert speaker.transport_state == "PLAYING"
    assert result["playback"]["state"] == "PLAYING"
    assert (2, True) in speaker.play_calls


def test_save_only_handles_empty_stopped_non_queue_source():
    speaker = FakeSpeaker(queue=[], transport_state="STOPPED", queue_active=False)
    plan = plan_for(speaker)
    observed = plan["targetState"]["observedState"]
    assert observed["playbackSource"] == "RADIO"
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", observed["mediaFingerprint"])
    assert speaker.current_uri not in json.dumps(plan["targetState"])
    result = execute(speaker, plan)

    assert speaker.queue == []
    assert speaker.current_uri == "x-sonosapi-stream:radio"
    assert speaker.music_source == "RADIO"
    assert result["queue"]["length"] == 0
    assert result["playback"]["state"] == "STOPPED"


def test_changed_non_queue_media_identity_conflicts_before_mutation_without_uri_leak():
    speaker = FakeSpeaker(queue=[], transport_state="STOPPED", queue_active=False)
    plan = plan_for(speaker)
    changed_uri = "x-sonosapi-stream:private-station?token=secret"
    speaker.current_uri = changed_uri

    with pytest.raises(PlanConflictError) as error:
        execute(speaker, plan)

    assert error.value.details == {"reason": "preflight_state_changed"}
    assert changed_uri not in str(error.value)
    assert changed_uri not in json.dumps(error.value.details)
    assert speaker.clear_calls == 0


def test_changed_non_queue_media_conflict_consumes_single_use_ticket():
    speaker = FakeSpeaker(queue=[], transport_state="STOPPED", queue_active=False)

    class Backend:
        def inspect_apple_playlist_target(self, room_uid, playlist_name):
            assert room_uid == speaker.uid
            return inspect_apple_playlist_target(speaker, playlist_name)

        def create_preflighted_apple_playlist(self, plan):
            return execute(speaker, plan)

    tickets = PlanTicketStore(token_factory=lambda: "media_change_ticket_12345678901234567890")
    validation, creation = ApplePlaylistPlanService(Backend(), tickets=tickets).services()
    preflight = validation.execute(
        "playlist_plan.apple.validate",
        {
            "roomUid": "R1",
            "playlistName": "AI Friday",
            "mode": "save-only",
            "tracks": [copy.deepcopy(TRACK_ONE), copy.deepcopy(TRACK_TWO)],
        },
        RequestContext(backend_revision=7),
    )
    speaker.current_uri = "x-sonosapi-stream:changed-after-approval"

    with pytest.raises(PlanConflictError, match="state changed"):
        creation.execute(
            "playlists.apple.create",
            {"planToken": preflight["planToken"], "approved": True},
            RequestContext(backend_revision=7),
        )
    assert speaker.clear_calls == 0
    with pytest.raises(PlanConflictError, match="already used"):
        creation.execute(
            "playlists.apple.create",
            {"planToken": preflight["planToken"], "approved": True},
            RequestContext(backend_revision=7),
        )


@pytest.mark.parametrize("transport_state", ("STOPPED", "PLAYING"))
def test_queue_uri_makes_unknown_coarse_source_eligible_and_restorable(transport_state):
    speaker = FakeSpeaker(
        queue=original_queue(),
        position=1,
        transport_state=transport_state,
        queue_active=True,
    )
    speaker.music_source = "UNKNOWN"
    plan = plan_for(speaker)

    observed = plan["targetState"]["observedState"]
    assert observed["playbackSource"] == "QUEUE"
    assert speaker.current_uri not in json.dumps(observed)
    result = execute(speaker, plan)

    assert result["playback"]["source"] == "QUEUE"
    assert speaker.current_position == 1
    assert speaker.transport_state == transport_state


def test_non_queue_unknown_or_unbounded_source_remains_ineligible_without_leak():
    for source in ("UNKNOWN", "x-sonosapi-stream:private?token=secret"):
        speaker = FakeSpeaker(queue=[], transport_state="STOPPED", queue_active=False)
        speaker.music_source = source
        with pytest.raises(PlanConflictError, match="source must be known") as error:
            inspect_apple_playlist_target(speaker, "AI Friday")
        assert source not in str(error.value)
        assert speaker.clear_calls == 0


def test_queue_at_supported_backup_limit_is_accepted():
    speaker = FakeSpeaker(queue=original_queue(100), position=99, transport_state="STOPPED")
    result = execute(speaker, plan_for(speaker))
    assert result["queue"]["length"] == 100
    assert len(speaker.queue) == 100


def test_last_bounded_playlist_inventory_slot_can_be_created_and_verified():
    speaker = FakeSpeaker(queue=original_queue())
    add_existing_playlists(speaker, 99)

    result = execute(speaker, plan_for(speaker))

    assert result["playlist"]["id"] == "SQ:1"
    assert len(speaker.playlists) == 100


def test_bounded_extra_inventory_item_allows_owned_race_cleanup():
    speaker = FakeSpeaker(queue=original_queue())
    add_existing_playlists(speaker, 99)
    plan = plan_for(speaker)
    speaker.create_name_race = True

    with pytest.raises(PlaylistTransactionError) as error:
        execute(speaker, plan)

    rollback = error.value.details["rollback"]
    assert rollback["playlistRemoved"] is True
    assert rollback["playlistCleanupRequired"] is False
    assert rollback["succeeded"] is True
    assert "SQ:1" not in speaker.playlists
    assert "SQ:99" in speaker.playlists
    assert len(speaker.playlists) == 100


def test_oversized_and_unrestorable_queues_are_rejected_before_mutation():
    oversized = FakeSpeaker(queue=original_queue(101), position=0)
    with pytest.raises(PlanConflictError, match="too large"):
        inspect_apple_playlist_target(oversized, "AI Friday")
    assert oversized.clear_calls == 0

    broken = FakeSpeaker(queue=[queue_item("Q:1", "Broken", uri=None)], position=0)
    with pytest.raises(PlanConflictError, match="cannot be backed up"):
        inspect_apple_playlist_target(broken, "AI Friday")
    assert broken.clear_calls == 0

    active_empty = FakeSpeaker(queue=[], queue_active=True)
    with pytest.raises(PlanConflictError, match="active queue is empty"):
        inspect_apple_playlist_target(active_empty, "AI Friday")


def test_preflight_rejects_malformed_topology_mixer_and_playlist_inventory():
    invalid_uid = FakeSpeaker(queue=original_queue())
    invalid_uid.uid = ""
    with pytest.raises(PlanConflictError, match="room identity"):
        inspect_apple_playlist_target(invalid_uid, "AI Friday")

    inconsistent = FakeSpeaker(queue=original_queue())
    inconsistent.group.members = [SimpleNamespace(uid="R2")]
    with pytest.raises(PlanConflictError, match="internally inconsistent"):
        inspect_apple_playlist_target(inconsistent, "AI Friday")

    invalid_volume = FakeSpeaker(queue=original_queue())
    invalid_volume.volume = 101
    with pytest.raises(PlanConflictError, match="room volume"):
        inspect_apple_playlist_target(invalid_volume, "AI Friday")

    invalid_mute = FakeSpeaker(queue=original_queue())
    invalid_mute.mute = 0
    with pytest.raises(PlanConflictError, match="room mute"):
        inspect_apple_playlist_target(invalid_mute, "AI Friday")

    full_playlists = FakeSpeaker(queue=original_queue())
    add_existing_playlists(full_playlists, 100)
    with pytest.raises(PlanConflictError, match="inventory is full"):
        inspect_apple_playlist_target(full_playlists, "AI Friday")
    assert full_playlists.clear_calls == 0

    too_many_playlists = FakeSpeaker(queue=original_queue())
    add_existing_playlists(too_many_playlists, 101)
    with pytest.raises(PlanConflictError, match="too many Sonos Playlists"):
        inspect_apple_playlist_target(too_many_playlists, "AI Friday")


def test_preflight_converts_untrusted_topology_queue_and_playlist_failures():
    class BrokenTopology:
        uid = "R1"

        @property
        def group(self):
            raise RuntimeError("private topology at 192.168.1.20")

    with pytest.raises(PlanConflictError, match="topology could not be verified") as topology:
        inspect_apple_playlist_target(BrokenTopology(), "AI Friday")
    assert "192.168" not in str(topology.value)

    queue_failure = FakeSpeaker(queue=original_queue())
    queue_failure.get_queue = lambda **_kwargs: (_ for _ in ()).throw(
        RuntimeError("private queue token=secret")
    )
    with pytest.raises(PlanConflictError, match="queue state could not be read") as queue_error:
        inspect_apple_playlist_target(queue_failure, "AI Friday")
    assert "token=" not in str(queue_error.value)

    playlist_failure = FakeSpeaker(queue=original_queue())
    playlist_failure.get_sonos_playlists = lambda **_kwargs: (_ for _ in ()).throw(
        RuntimeError("private playlist DIDL")
    )
    with pytest.raises(PlanConflictError, match="could not be listed safely") as playlist_error:
        inspect_apple_playlist_target(playlist_failure, "AI Friday")
    assert "DIDL" not in str(playlist_error.value)


def test_save_and_play_leaves_exact_approved_queue_and_starts_track_one():
    speaker = FakeSpeaker(queue=original_queue(), position=1, transport_state="STOPPED")
    result = execute(speaker, plan_for(speaker, mode="save-and-play"))

    assert result["queue"]["disposition"] == "approved-plan-active"
    assert [item.title for item in speaker.queue] == [
        "Just Like Heaven",
        "Life's What You Make It",
    ]
    assert speaker.current_position == 0
    assert speaker.transport_state == "PLAYING"
    assert result["playback"]["current"]["catalogId"] == "1452806384"
    assert result["playback"]["current"]["title"] == "Just Like Heaven"
    assert result["playback"]["current"]["artist"] == "The Cure"
    assert [item.title for item in speaker.playlist_tracks["SQ:1"]] == [
        "Just Like Heaven",
        "Life's What You Make It",
    ]


def test_grouped_target_preserves_exact_members_and_coordinator():
    speaker = FakeSpeaker(queue=original_queue())
    member = SimpleNamespace(uid="R2")
    speaker.group.members.append(member)
    plan = plan_for(speaker, mode="save-and-play")
    result = execute(speaker, plan)
    assert result["room"] == {
        "uid": "R1",
        "standalone": False,
        "memberUids": ["R1", "R2"],
        "coordinatorUid": "R1",
    }


def test_exact_playlist_name_collision_is_create_only_and_suggested():
    speaker = FakeSpeaker(queue=original_queue())
    speaker.playlists["SQ:8"] = SimpleNamespace(item_id="SQ:8", title="AI Friday")
    speaker.playlist_tracks["SQ:8"] = []
    with pytest.raises(PlanConflictError) as error:
        inspect_apple_playlist_target(speaker, "AI Friday")
    assert error.value.details == {"suggestedPlaylistName": "AI Friday (2)"}
    assert speaker.clear_calls == 0


@pytest.mark.parametrize("change", ("queue", "topology", "volume", "mute", "capability"))
def test_changed_preflight_state_requires_a_fresh_plan_without_mutation(change):
    speaker = FakeSpeaker(queue=original_queue())
    plan = plan_for(speaker)
    if change == "queue":
        speaker.queue.append(queue_item("Q:new", "External change"))
        speaker.queue_update += 1
    elif change == "topology":
        speaker.group.members.append(SimpleNamespace(uid="R2"))
    elif change == "volume":
        speaker.volume = 21
    elif change == "mute":
        speaker.mute = True
    else:
        speaker.create_sonos_playlist_from_queue = None

    with pytest.raises(PlanConflictError):
        execute(speaker, plan)
    assert speaker.clear_calls == 0


def test_playlist_create_failure_restores_queue_but_reports_unattributable_cleanup():
    speaker = FakeSpeaker(queue=original_queue(), position=1, transport_state="PLAYING")
    plan = plan_for(speaker)
    speaker.fail_create = True

    with pytest.raises(PlaylistTransactionError) as error:
        execute(speaker, plan)
    assert error.value.details == {
        "phase": "playlist_creation",
        "rollback": {
            "attempted": True,
            "playlistRemoved": False,
            "playlistCleanupRequired": True,
            "queueRestored": True,
            "environmentUnchanged": True,
            "succeeded": False,
        },
    }
    assert [item.title for item in speaker.queue] == ["Original 1", "Original 2"]
    assert speaker.current_position == 1
    assert speaker.transport_state == "PLAYING"
    assert speaker.playlists == {}


@pytest.mark.parametrize("failure", ("reverse", "wrong-title", "wrong-identity"))
def test_saved_playlist_verification_failure_removes_partial_and_restores(failure):
    speaker = FakeSpeaker(queue=original_queue(), position=0, transport_state="STOPPED")
    plan = plan_for(speaker)
    speaker.saved_verification = failure

    with pytest.raises(PlaylistTransactionError) as error:
        execute(speaker, plan)
    assert error.value.details["phase"] == "playlist_verification"
    assert error.value.details["rollback"]["succeeded"] is True
    assert error.value.details["rollback"]["playlistCleanupRequired"] is False
    assert speaker.playlists == {}
    assert [item.title for item in speaker.queue] == ["Original 1", "Original 2"]


def test_saved_playlist_incomplete_reopen_is_a_verification_failure():
    speaker = FakeSpeaker(queue=original_queue())
    plan = plan_for(speaker)
    speaker.saved_browse_total = 3
    with pytest.raises(PlaylistTransactionError) as error:
        execute(speaker, plan)
    assert error.value.details["phase"] == "playlist_verification"
    assert error.value.details["rollback"]["succeeded"] is True


@pytest.mark.parametrize(
    ("attribute", "value", "phase"),
    (
        ("created_title_override", "Unexpected", "playlist_creation"),
        ("reopened_title_override", "Unexpected", "playlist_verification"),
        ("drop_queue_after_save", True, "playlist_verification"),
        ("unexpected_queue_extra", True, "queue_verification"),
    ),
)
def test_authoritative_name_and_queue_verification_failures_rollback(attribute, value, phase):
    speaker = FakeSpeaker(queue=original_queue())
    plan = plan_for(speaker)
    setattr(speaker, attribute, value)
    with pytest.raises(PlaylistTransactionError) as error:
        execute(speaker, plan)
    assert error.value.details["phase"] == phase
    assert error.value.details["rollback"]["succeeded"] is True
    assert "SQ:1" not in speaker.playlists


def test_reopen_failure_removes_exact_new_playlist_and_restores():
    speaker = FakeSpeaker(queue=original_queue())
    plan = plan_for(speaker)
    speaker.fail_reopen = True
    with pytest.raises(PlaylistTransactionError) as error:
        execute(speaker, plan)
    assert error.value.details["rollback"]["succeeded"] is True
    assert speaker.playlists == {}


def test_create_succeeding_remotely_without_returned_id_never_guesses_cleanup_ownership():
    speaker = FakeSpeaker(queue=original_queue())
    plan = plan_for(speaker)
    speaker.partial_create_failure = True
    with pytest.raises(PlaylistTransactionError) as error:
        execute(speaker, plan)
    rollback = error.value.details["rollback"]
    assert rollback["playlistRemoved"] is False
    assert rollback["playlistCleanupRequired"] is True
    assert rollback["queueRestored"] is True
    assert rollback["succeeded"] is False
    assert set(speaker.playlists) == {"SQ:1"}


def test_concurrent_same_name_during_queue_construction_is_never_deleted():
    speaker = FakeSpeaker(queue=original_queue())
    plan = plan_for(speaker)
    speaker.concurrent_playlist_during_queue = True
    speaker.wrong_insert_position = True

    with pytest.raises(PlaylistTransactionError) as error:
        execute(speaker, plan)

    rollback = error.value.details["rollback"]
    assert error.value.details["phase"] == "queue_construction"
    assert rollback["playlistRemoved"] is False
    assert rollback["playlistCleanupRequired"] is False
    assert rollback["succeeded"] is True
    assert set(speaker.playlists) == {"SQ:99"}


def test_same_name_created_after_preflight_conflicts_without_mutation_or_deletion():
    speaker = FakeSpeaker(queue=original_queue())
    plan = plan_for(speaker)
    unrelated = SimpleNamespace(item_id="SQ:99", title="AI Friday")
    speaker.playlists[unrelated.item_id] = unrelated
    speaker.playlist_tracks[unrelated.item_id] = []

    with pytest.raises(PlanConflictError, match="exact name"):
        execute(speaker, plan)

    assert speaker.clear_calls == 0
    assert set(speaker.playlists) == {"SQ:99"}


def test_unattributable_cleanup_leaves_every_ambiguous_playlist_untouched():
    speaker = FakeSpeaker(queue=original_queue())
    plan = plan_for(speaker)
    speaker.concurrent_playlist_during_queue = True
    speaker.partial_create_failure = True

    with pytest.raises(PlaylistTransactionError) as error:
        execute(speaker, plan)

    rollback = error.value.details["rollback"]
    assert rollback["playlistRemoved"] is False
    assert rollback["playlistCleanupRequired"] is True
    assert rollback["succeeded"] is False
    assert set(speaker.playlists) == {"SQ:1", "SQ:99"}


def test_exact_name_race_aborts_without_deleting_the_unrelated_playlist():
    speaker = FakeSpeaker(queue=original_queue())
    plan = plan_for(speaker)
    speaker.create_name_race = True
    with pytest.raises(PlaylistTransactionError) as error:
        execute(speaker, plan)
    assert error.value.details["phase"] == "playlist_verification"
    assert error.value.details["rollback"]["succeeded"] is True
    assert error.value.details["rollback"]["playlistRemoved"] is True
    assert error.value.details["rollback"]["playlistCleanupRequired"] is False
    assert set(speaker.playlists) == {"SQ:99"}


def test_create_returning_an_original_playlist_id_is_never_cleanup_owned():
    speaker = FakeSpeaker(queue=original_queue())
    original = SimpleNamespace(item_id="SQ:1", title="Existing playlist")
    speaker.playlists[original.item_id] = original
    speaker.playlist_tracks[original.item_id] = [queue_item("P:old", "Old playlist item")]
    plan = plan_for(speaker)

    with pytest.raises(PlaylistTransactionError) as error:
        execute(speaker, plan)

    rollback = error.value.details["rollback"]
    assert rollback["playlistRemoved"] is False
    assert rollback["playlistCleanupRequired"] is True
    assert rollback["succeeded"] is False
    assert set(speaker.playlists) == {"SQ:1"}


def test_topology_change_during_mutation_aborts_and_is_not_claimed_restored():
    speaker = FakeSpeaker(queue=original_queue())
    plan = plan_for(speaker)
    speaker.topology_change_on_create = True
    with pytest.raises(PlaylistTransactionError) as error:
        execute(speaker, plan)
    rollback = error.value.details["rollback"]
    assert rollback["queueRestored"] is True
    assert rollback["environmentUnchanged"] is False
    assert rollback["succeeded"] is False


def test_volume_change_during_mutation_aborts_and_is_not_claimed_restored():
    speaker = FakeSpeaker(queue=original_queue())
    plan = plan_for(speaker)
    speaker.volume_change_on_create = True
    with pytest.raises(PlaylistTransactionError) as error:
        execute(speaker, plan)
    rollback = error.value.details["rollback"]
    assert rollback["queueRestored"] is True
    assert rollback["environmentUnchanged"] is False
    assert rollback["succeeded"] is False


def test_save_and_play_failure_uses_prior_queue_only_for_rollback():
    speaker = FakeSpeaker(queue=original_queue(), position=1, transport_state="PLAYING")
    plan = plan_for(speaker, mode="save-and-play")
    speaker.fail_play_once = True

    with pytest.raises(PlaylistTransactionError) as error:
        execute(speaker, plan)
    assert error.value.details["phase"] == "playback_start"
    assert error.value.details["rollback"]["succeeded"] is True
    assert [item.title for item in speaker.queue] == ["Original 1", "Original 2"]
    assert speaker.current_position == 1
    assert speaker.transport_state == "PLAYING"
    assert speaker.playlists == {}


def test_save_and_play_rejects_unconfirmed_playing_state_and_current_metadata():
    stopped = FakeSpeaker(queue=original_queue(), transport_state="STOPPED")
    stopped_plan = plan_for(stopped, mode="save-and-play")
    stopped.play_stays_stopped = True
    with pytest.raises(PlaylistTransactionError) as state_error:
        execute(stopped, stopped_plan)
    assert state_error.value.details["phase"] == "playback_verification"
    assert state_error.value.details["rollback"]["succeeded"] is True

    mismatched = FakeSpeaker(queue=original_queue(), transport_state="STOPPED")
    mismatched_plan = plan_for(mismatched, mode="save-and-play")
    mismatched.current_metadata_override = {"title": "Wrong", "artist": "Wrong"}
    with pytest.raises(PlaylistTransactionError) as metadata_error:
        execute(mismatched, mismatched_plan)
    assert metadata_error.value.details["phase"] == "playback_verification"
    assert metadata_error.value.details["rollback"]["succeeded"] is True


def test_unexpected_share_expansion_aborts_and_restores_without_playlist():
    speaker = FakeSpeaker(queue=original_queue())
    plan = plan_for(speaker)
    speaker.expand_share = True
    with pytest.raises(PlaylistTransactionError) as error:
        execute(speaker, plan)
    assert error.value.details["phase"] == "queue_construction"
    assert error.value.details["rollback"]["succeeded"] is True
    assert speaker.playlists == {}


def test_rollback_failure_is_reported_without_claiming_restoration():
    speaker = FakeSpeaker(queue=original_queue())
    plan = plan_for(speaker)
    speaker.fail_create = True
    speaker.fail_restore = True
    with pytest.raises(PlaylistTransactionError) as error:
        execute(speaker, plan)
    rollback = error.value.details["rollback"]
    assert rollback["queueRestored"] is False
    assert rollback["succeeded"] is False
    assert "192.168" not in str(error.value)


def test_playlist_cleanup_failure_is_reported_as_incomplete_rollback():
    speaker = FakeSpeaker(queue=original_queue())
    plan = plan_for(speaker)
    speaker.saved_verification = "reverse"
    speaker.fail_playlist_remove = True
    with pytest.raises(PlaylistTransactionError) as error:
        execute(speaker, plan)
    rollback = error.value.details["rollback"]
    assert rollback["playlistRemoved"] is False
    assert rollback["playlistCleanupRequired"] is True
    assert rollback["queueRestored"] is True
    assert rollback["succeeded"] is False


def test_preflight_rejects_unknown_transport_and_non_restorable_paused_state():
    for state in ("UNKNOWN", "PAUSED_PLAYBACK", "TRANSITIONING"):
        speaker = FakeSpeaker(queue=original_queue(), transport_state=state)
        with pytest.raises(PlanConflictError, match="playing or stopped"):
            inspect_apple_playlist_target(speaker, "AI Friday")


def test_internal_room_or_mode_mismatch_still_cannot_start_mutation():
    speaker = FakeSpeaker(queue=original_queue())
    wrong_room = plan_for(speaker)
    wrong_room["roomUid"] = "R2"
    with pytest.raises(PlanConflictError, match="exact target room"):
        execute(speaker, wrong_room)
    assert speaker.clear_calls == 0

    wrong_mode = plan_for(speaker)
    wrong_mode["mode"] = "temporary"
    with pytest.raises(PlanConflictError, match="mode"):
        execute(speaker, wrong_mode)
    assert speaker.clear_calls == 0


@pytest.mark.parametrize(
    ("change", "message"),
    (
        ("contents", "contents"),
        ("source-kind", "playback source"),
        ("position", "queue position"),
        ("transport", "playing state"),
    ),
)
def test_restoration_verification_rejects_each_changed_authoritative_fact(change, message):
    speaker = FakeSpeaker(queue=original_queue(), position=1, transport_state="STOPPED")
    expected = capture_queue_backup(speaker)
    if change == "contents":
        speaker.queue[0].resources[0].uri = "x-test:changed"
    elif change == "source-kind":
        speaker.current_uri = "x-sonosapi-stream:radio"
        speaker.music_source = "RADIO"
    elif change == "position":
        speaker.current_position = 0
    elif change == "transport":
        speaker.transport_state = "PLAYING"
    with pytest.raises(QueueStateError, match=message):
        verify_restored_queue(speaker, expected)


def test_non_queue_restoration_verifies_exact_media_identity():
    speaker = FakeSpeaker(queue=[], transport_state="STOPPED", queue_active=False)
    expected = capture_queue_backup(speaker)
    speaker.current_uri = "x-sonosapi-stream:another-radio"
    with pytest.raises(QueueStateError, match="exact playback source"):
        verify_restored_queue(speaker, expected)


def test_queue_restoration_verifies_exact_queue_uri_not_coarse_source():
    speaker = FakeSpeaker(queue=original_queue(), position=0, queue_active=True)
    speaker.music_source = "UNKNOWN"
    expected = capture_queue_backup(speaker)
    assert expected.source == "QUEUE"
    speaker.current_uri = "x-rincon-queue:ANOTHER_ROOM#0"
    with pytest.raises(QueueStateError, match="exact playback source"):
        verify_restored_queue(speaker, expected)


def test_non_queue_restoration_verifies_bounded_coarse_source_fact():
    speaker = FakeSpeaker(queue=[], transport_state="STOPPED", queue_active=False)
    expected = capture_queue_backup(speaker)
    speaker.music_source = "WEB_FILE"
    with pytest.raises(QueueStateError, match="playback source"):
        verify_restored_queue(speaker, expected)
