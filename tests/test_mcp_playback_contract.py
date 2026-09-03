from __future__ import annotations

import copy
import io
import json
import os
import select
import stat
import subprocess
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from sonarchy_backend.controller_common import ControllerError
from sonarchy_backend.controller_facade import DomainFacadeMixin
from sonarchy_backend.local_mcp import BackendOwnership, MultiClientRuntime
from sonarchy_backend.protocol import ProtocolServer

ROOT = Path(__file__).parents[1]
BACKEND_TOKEN = "backend_contract_ticket_000000000001"  # noqa: S105


class Result(list):
    def __init__(self, items=()):
        super().__init__(items)
        self.total_matches = len(self)


def _item(identity: str):
    return SimpleNamespace(
        item_id=f"private:{identity}",
        title=f"Track {identity}",
        creator=f"Artist {identity}",
        album=f"Album {identity}",
        resources=[
            SimpleNamespace(
                uri=f"x-private-provider:{identity}",
                protocol_info="x-private-protocol",
                duration="0:03:32",
            )
        ],
    )


class _Transport:
    def __init__(self, speaker):
        self.speaker = speaker

    def GetMediaInfo(self, _args):
        return {"CurrentURI": self.speaker.source_uri}


class _MusicLibrary:
    def __init__(self, speaker):
        self.speaker = speaker

    def browse(self, *, ml_item, start, max_items, full_album_art_uri):
        assert ml_item is self.speaker.playlist
        assert (start, full_album_art_uri) == (0, False)
        return Result(copy.deepcopy(self.speaker.playlist_items[:max_items]))


class FakeSonosSpeaker:
    """Only the final device API used by production playlist playback."""

    def __init__(self):
        self.uid = "R1"
        self.player_name = "Office"
        self.household_id = "Sonos_HH1"
        self.is_visible = True
        self.volume = 20
        self.mute = False
        self.transport = "STOPPED"
        self.music_source = "APPLE_MUSIC"
        self.source_uri = "x-rincon-queue:R1#0"
        self.group = SimpleNamespace(coordinator=self, members=[self])
        self.playlist = SimpleNamespace(item_id="SQ:9", title="Morning")
        self.playlist_items = [_item("one"), _item("two")]
        self.queue_items = [_item("existing")]
        self.current_position = 1
        self.playlist_lookups = []
        self.append_calls = []
        self.play_calls = []
        self.append_failure_after_mutation = False
        self.append_failure_without_mutation = False
        self.append_failure_ambiguous = False
        self.post_capture_stale_queue_remaining = 0
        self.queue_before_append = None
        self.post_capture_failures_remaining = 0
        self.post_capture_stale_remaining = 0
        self.play_failure_after_mutation = False
        self.playback_verification_failure = False
        self.avTransport = _Transport(self)
        self.music_library = _MusicLibrary(self)

    def get_current_transport_info(self):
        if self.play_calls and self.post_capture_stale_remaining:
            self.post_capture_stale_remaining -= 1
            return {"current_transport_state": "STOPPED"}
        return {"current_transport_state": self.transport}

    def get_current_track_info(self):
        selected = self.queue_items[self.current_position - 1]
        return {
            "playlist_position": str(self.current_position),
            "title": selected.title,
            "artist": selected.creator,
            "album": selected.album,
        }

    def get_sonos_playlists(self, *, max_items):
        self.playlist_lookups.append(("inventory", max_items))
        return Result([self.playlist])

    def get_sonos_playlist_by_attr(self, attribute, value):
        self.playlist_lookups.append((attribute, value))
        assert (attribute, value) == ("item_id", "SQ:9")
        return self.playlist

    def get_queue(self, *, max_items, full_album_art_uri):
        assert full_album_art_uri is False
        if self.play_calls and self.post_capture_failures_remaining:
            self.post_capture_failures_remaining -= 1
            raise RuntimeError("transient post-write queue read failure")
        values = self.queue_items
        if self.append_calls and self.post_capture_stale_queue_remaining:
            self.post_capture_stale_queue_remaining -= 1
            values = self.queue_before_append
        return Result(copy.deepcopy(values[:max_items]))

    def add_to_queue(self, playlist):
        self.append_calls.append(playlist.item_id)
        position = len(self.queue_items) + 1
        self.queue_before_append = copy.deepcopy(self.queue_items)
        if self.append_failure_without_mutation:
            raise RuntimeError("lost append response before mutation")
        self.queue_items.extend(copy.deepcopy(self.playlist_items))
        if self.append_failure_ambiguous:
            self.queue_items = self.queue_items[:-1]
            raise RuntimeError("ambiguous append response")
        if self.append_failure_after_mutation:
            raise RuntimeError("lost append response after mutation")
        return position

    def play_from_queue(self, index):
        self.play_calls.append(index)
        self.current_position = index + 1
        self.transport = "PAUSED_PLAYBACK" if self.playback_verification_failure else "PLAYING"
        if self.play_failure_after_mutation:
            raise RuntimeError("lost playback response after mutation")


class DeviceBoundaryController(DomainFacadeMixin):
    def __init__(self, speaker):
        self.speaker = speaker

    def _zone(self, room_uid):
        if room_uid != self.speaker.uid:
            raise ControllerError("missing room")
        return self.speaker

    def refresh(self, *, rediscover=True):
        return {
            "type": "snapshot",
            "version": 1,
            "revision": 1,
            "status": {"state": "ready", "message": ""},
            "households": [],
            "target": None,
            "playback": {},
        }

    def event_services(self):
        return {}


class RecordingProtocolServer(ProtocolServer):
    def __init__(self, controller):
        super().__init__(controller)
        self.requests = []

    def handle(self, request, output):
        self.requests.append(copy.deepcopy(request))
        super().handle(request, output)


class JsonRpcClient:
    def __init__(self, process):
        self.process = process
        self.public_results = []

    def send(self, payload):
        self.process.stdin.write((json.dumps(payload) + "\n").encode())
        self.process.stdin.flush()

    def request(self, request_id, method, params=None):
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            payload["params"] = params
        self.send(payload)
        ready, _, _ = select.select([self.process.stdout], [], [], 5)
        assert ready, f"timed out waiting for JSON-RPC response {request_id}"
        response = json.loads(self.process.stdout.readline())
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == request_id
        self.public_results.append(response)
        return response

    def assert_no_response(self):
        ready, _, _ = select.select([self.process.stdout], [], [], 0.2)
        assert not ready


@contextmanager
def playback_contract(tmp_path, backend_permissions):
    runtime_root = tmp_path / "runtime"
    config_home = tmp_path / "config"
    home = tmp_path / "home"
    config_dir = config_home / "sonarchy"
    for directory in (runtime_root, config_home, config_dir, home):
        directory.mkdir(mode=0o700)
        directory.chmod(0o700)
    config = config_dir / "mcp.toml"
    config.write_text('enabled = true\npermissions = ["read", "playlist-play"]\n')
    config.chmod(0o600)

    speaker = FakeSonosSpeaker()
    protocol = RecordingProtocolServer(DeviceBoundaryController(speaker))
    ticket_store = next(
        service.contextual_handlers["playlists.play.validate"].__self__.tickets
        for service in protocol.application.services
        if "playlists.play.validate" in service.contextual_handlers
    )
    ticket_store._token_factory = lambda: BACKEND_TOKEN
    qml_read_fd, qml_write_fd = os.pipe()
    qml_stdin = os.fdopen(qml_read_fd, "rb", buffering=0)
    runtime_output = io.BytesIO()
    process = None
    thread = None
    with BackendOwnership.acquire(str(runtime_root)) as ownership:
        listener = ownership.open_listener()
        assert stat.S_IMODE(ownership.runtime_dir.stat().st_mode) == 0o700
        assert stat.S_IMODE(ownership.socket_path.stat().st_mode) == 0o600
        runtime = MultiClientRuntime(protocol, listener, frozenset(backend_permissions))
        thread = threading.Thread(
            target=runtime.serve, args=(qml_stdin, runtime_output), daemon=True
        )
        thread.start()
        env = {
            **os.environ,
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(config_home),
            "XDG_RUNTIME_DIR": str(runtime_root),
            "PYTHONUNBUFFERED": "1",
        }
        process = subprocess.Popen(
            [sys.executable, "-B", "-u", "-m", "sonarchy_mcp.server"],
            cwd=ROOT,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        client = JsonRpcClient(process)
        try:
            yield client, protocol, speaker, runtime_output
        finally:
            process.stdin.close()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=3)
            os.close(qml_write_fd)
            thread.join(timeout=3)
            qml_stdin.close()
            assert not thread.is_alive()
            client.stderr = process.stderr.read().decode()
            process.stdout.close()
            process.stderr.close()


def _initialize(client):
    initialized = client.request(1, "initialize", {})
    assert initialized["result"]["protocolVersion"] == "2025-06-18"
    client.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    client.assert_no_response()
    inventory = client.request(2, "tools/list", {})["result"]["tools"]
    names = {tool["name"] for tool in inventory}
    assert {"sonos_playlist_play_preflight", "sonos_playlist_play"} <= names
    assert "apple_playlist_create" not in names


def _preflight(client):
    response = client.request(
        3,
        "tools/call",
        {
            "name": "sonos_playlist_play_preflight",
            "arguments": {"roomUid": "R1", "playlistId": "SQ:9"},
        },
    )
    result = response["result"]
    review = result["structuredContent"]
    assert result["isError"] is False
    assert review["room"]["uid"] == "R1"
    assert review["room"]["name"] == "Office"
    assert review["topology"] == {
        "groupUid": "R1",
        "coordinatorUid": "R1",
        "memberUids": ["R1"],
        "standalone": True,
    }
    assert (review["playlist"]["id"], review["playlist"]["title"]) == ("SQ:9", "Morning")
    assert review["playlist"]["itemCount"] == 2
    assert review["queue"]["expectedFirstAppendedPosition"] == 2
    assert "planToken" not in review
    assert BACKEND_TOKEN not in json.dumps(response)
    return review["planHandle"]


def test_mcp_stdio_socket_protocol_playback_contract(tmp_path):
    with playback_contract(tmp_path, {"read", "playlist-play"}) as harness:
        client, protocol, speaker, runtime_output = harness
        _initialize(client)
        handle = _preflight(client)
        public_args = {"planHandle": handle, "approved": True}
        response = client.request(
            4,
            "tools/call",
            {"name": "sonos_playlist_play", "arguments": public_args},
        )
        result = response["result"]
        value = result["structuredContent"]
        assert result["isError"] is False
        execute_requests = [
            request
            for request in protocol.requests
            if request.get("op") == "playlists.play.execute"
        ]
        assert [request["args"] for request in execute_requests] == [
            {"planToken": BACKEND_TOKEN, "approved": True}
        ]
        assert speaker.append_calls == ["SQ:9"]
        assert speaker.play_calls == [1]
        assert value["mutations"]["appendInvocationCount"] == 1
        assert value["mutations"]["playbackStartInvocationCount"] == 1
        assert value["mutations"]["appendInvocationReturned"] is True
        assert value["mutations"]["playbackStartInvocationReturned"] is True
        assert value["appendState"] == "confirmed"
        assert value["playbackState"] == "confirmed"
        assert value["queue"]["currentPosition"] == 2
        assert value["retryCount"] == 0
        assert value["substitutionCount"] == 0

        replay = client.request(
            5,
            "tools/call",
            {"name": "sonos_playlist_play", "arguments": public_args},
        )
        assert replay["result"]["isError"] is True
        assert replay["result"]["structuredContent"]["code"] == "conflict"
        assert (
            len(
                [
                    request
                    for request in protocol.requests
                    if request.get("op") == "playlists.play.execute"
                ]
            )
            == 1
        )
        assert speaker.append_calls == ["SQ:9"]
        assert speaker.play_calls == [1]
        assert client.request(6, "ping", {})["result"] == {}

    public = json.dumps(client.public_results)
    assert BACKEND_TOKEN not in public
    assert BACKEND_TOKEN not in client.stderr
    assert BACKEND_TOKEN.encode() not in runtime_output.getvalue()
    assert handle not in json.dumps(response)
    assert handle not in json.dumps(replay)
    for private_value in ("x-private-provider:", "x-private-protocol", "192.0.2.1"):
        assert private_value not in public
        assert private_value not in client.stderr


def test_mcp_full_path_recaptures_after_transient_post_write_read_failure(tmp_path):
    with playback_contract(tmp_path, {"read", "playlist-play"}) as harness:
        client, _protocol, speaker, runtime_output = harness
        _initialize(client)
        handle = _preflight(client)
        speaker.post_capture_failures_remaining = 1

        response = client.request(
            4,
            "tools/call",
            {
                "name": "sonos_playlist_play",
                "arguments": {"planHandle": handle, "approved": True},
            },
        )

        result = response["result"]
        value = result["structuredContent"]
        assert result["isError"] is False
        assert value["verification"]["authoritative"] is True
        assert value["queue"]["afterLength"] == 3
        assert value["queue"]["currentPosition"] == 2
        assert speaker.append_calls == ["SQ:9"]
        assert speaker.play_calls == [1]
        assert client.request(5, "ping", {})["result"] == {}

    public = json.dumps(client.public_results)
    assert BACKEND_TOKEN not in public
    assert BACKEND_TOKEN.encode() not in runtime_output.getvalue()
    assert "transient post-write queue read failure" not in public


def test_mcp_full_path_recaptures_stale_state_within_bound(tmp_path):
    with playback_contract(tmp_path, {"read", "playlist-play"}) as harness:
        client, _protocol, speaker, _runtime_output = harness
        _initialize(client)
        handle = _preflight(client)
        speaker.post_capture_stale_remaining = 1

        response = client.request(
            4,
            "tools/call",
            {
                "name": "sonos_playlist_play",
                "arguments": {"planHandle": handle, "approved": True},
            },
        )

        assert response["result"]["isError"] is False
        assert response["result"]["structuredContent"]["verification"]["authoritative"] is True
        assert speaker.append_calls == ["SQ:9"]
        assert speaker.play_calls == [1]


def test_mcp_full_path_verifies_lost_playback_response(tmp_path):
    with playback_contract(tmp_path, {"read", "playlist-play"}) as harness:
        client, _protocol, speaker, runtime_output = harness
        _initialize(client)
        handle = _preflight(client)
        speaker.play_failure_after_mutation = True

        response = client.request(
            4,
            "tools/call",
            {
                "name": "sonos_playlist_play",
                "arguments": {"planHandle": handle, "approved": True},
            },
        )

        result = response["result"]
        value = result["structuredContent"]
        assert result["isError"] is False
        assert value["verification"]["authoritative"] is True
        assert value["appendState"] == "confirmed"
        assert value["playbackState"] == "confirmed"
        assert value["mutations"]["appendInvocationReturned"] is True
        assert value["mutations"]["playbackStartInvocationReturned"] is False
        assert speaker.append_calls == ["SQ:9"]
        assert speaker.play_calls == [1]
        assert client.request(5, "ping", {})["result"] == {}

    public = json.dumps(client.public_results)
    assert BACKEND_TOKEN not in public
    assert "lost playback response after mutation" not in public
    assert BACKEND_TOKEN.encode() not in runtime_output.getvalue()


def test_mcp_full_path_reports_unknown_lost_playback_response(tmp_path):
    with playback_contract(tmp_path, {"read", "playlist-play"}) as harness:
        client, _protocol, speaker, _runtime_output = harness
        _initialize(client)
        handle = _preflight(client)
        speaker.play_failure_after_mutation = True
        speaker.playback_verification_failure = True

        response = client.request(
            4,
            "tools/call",
            {
                "name": "sonos_playlist_play",
                "arguments": {"planHandle": handle, "approved": True},
            },
        )

        result = response["result"]
        value = result["structuredContent"]
        assert result["isError"] is True
        assert value["details"]["playbackState"] == "unknown"
        assert "playbackStarted" not in value["details"]
        assert value["details"]["appendInvocationReturned"] is True
        assert value["details"]["playbackStartInvocationReturned"] is False
        assert speaker.append_calls == ["SQ:9"]
        assert speaker.play_calls == [1]
        assert client.request(5, "ping", {})["result"] == {}


def test_mcp_append_response_loss_uses_second_capture_for_confirmation(tmp_path):
    with playback_contract(tmp_path, {"read", "playlist-play"}) as harness:
        client, _protocol, speaker, _runtime_output = harness
        _initialize(client)
        handle = _preflight(client)
        speaker.append_failure_after_mutation = True
        speaker.post_capture_stale_queue_remaining = 1

        response = client.request(
            4,
            "tools/call",
            {
                "name": "sonos_playlist_play",
                "arguments": {"planHandle": handle, "approved": True},
            },
        )

        details = response["result"]["structuredContent"]["details"]
        assert response["result"]["isError"] is True
        assert details["appendState"] == "confirmed"
        assert details["playbackState"] == "absent"
        assert details["playbackStarted"] is False
        assert details["appendInvocationReturned"] is False
        assert details["playbackStartInvocationReturned"] is False
        assert details["appendInvocationCount"] == 1
        assert details["playbackStartInvocationCount"] == 0
        assert speaker.append_calls == ["SQ:9"]
        assert speaker.play_calls == []
        assert client.request(5, "ping", {})["result"] == {}


def test_mcp_append_without_mutation_is_absent_only_after_two_old_captures(tmp_path):
    with playback_contract(tmp_path, {"read", "playlist-play"}) as harness:
        client, _protocol, speaker, _runtime_output = harness
        _initialize(client)
        handle = _preflight(client)
        speaker.append_failure_without_mutation = True

        response = client.request(
            4,
            "tools/call",
            {
                "name": "sonos_playlist_play",
                "arguments": {"planHandle": handle, "approved": True},
            },
        )

        details = response["result"]["structuredContent"]["details"]
        assert details["appendState"] == "absent"
        assert details["playbackState"] == "absent"
        assert details["queueAppended"] is False
        assert details["appendInvocationReturned"] is False
        assert details["playbackStartInvocationReturned"] is False
        assert speaker.append_calls == ["SQ:9"]
        assert speaker.play_calls == []
        assert client.request(5, "ping", {})["result"] == {}


def test_mcp_ambiguous_append_response_remains_unknown(tmp_path):
    with playback_contract(tmp_path, {"read", "playlist-play"}) as harness:
        client, _protocol, speaker, _runtime_output = harness
        _initialize(client)
        handle = _preflight(client)
        speaker.append_failure_ambiguous = True

        response = client.request(
            4,
            "tools/call",
            {
                "name": "sonos_playlist_play",
                "arguments": {"planHandle": handle, "approved": True},
            },
        )

        details = response["result"]["structuredContent"]["details"]
        assert details["appendState"] == "unknown"
        assert "queueAppended" not in details
        assert details["playbackState"] == "absent"
        assert details["appendInvocationReturned"] is False
        assert details["playbackStartInvocationReturned"] is False
        assert speaker.append_calls == ["SQ:9"]
        assert speaker.play_calls == []
        assert client.request(5, "ping", {})["result"] == {}


def test_mcp_socket_playlist_play_permission_is_independently_enforced(tmp_path):
    with playback_contract(tmp_path, {"read", "playlist-create"}) as harness:
        client, protocol, speaker, _runtime_output = harness
        _initialize(client)
        handle = _preflight(client)
        denied = client.request(
            4,
            "tools/call",
            {
                "name": "sonos_playlist_play",
                "arguments": {"planHandle": handle, "approved": True},
            },
        )
        assert denied["result"]["isError"] is True
        assert denied["result"]["structuredContent"]["code"] == "permission_denied"
        assert [r for r in protocol.requests if r.get("op") == "playlists.play.execute"] == []
        assert speaker.append_calls == []
        assert speaker.play_calls == []
        assert client.request(5, "ping", {})["result"] == {}
