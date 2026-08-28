# Persistent protocol v1

The backend and QML exchange one UTF-8 JSON object per line over private
stdin/stdout pipes. A line is limited to 64 KiB. Unknown object members are
ignored within protocol v1 unless they change the meaning of a required field.

## Request

```json
{
  "version": 1,
  "id": "qml-42",
  "op": "playback.seek",
  "args": { "positionSec": 90 }
}
```

- `version` is required after the compatibility migration and must be `1`.
- `id` is a non-empty QML-generated identifier, unique among pending requests.
- `op` is a namespaced operation from the checked protocol inventory.
- `args` is an object. Operations validate their own allowed and required keys.

The backend accepts only this canonical versioned shape. Missing versions,
camelCase operation aliases, flattened arguments, and non-object `args` are
rejected without executing a command.

`content.browse` accepts an optional `context` object. Local-library requests
use `{ "path": [{ "id": "…", "index": 0 }], "offset": 0 }`: every path
segment carries the absolute index at which its ID was observed, depth is
bounded, and the backend re-reads each segment before returning a page. The
result includes authoritative breadcrumbs, page flags, and `browsable` and
`playable` item capabilities. Existing non-library requests may omit context.

`queue.content.enqueue` accepts an optional `libraryPath` with the same bounded
segments. The backend re-resolves that path and verifies the selected absolute
index and item ID before mutation; QML-supplied metadata is never treated as an
authoritative Sonos object. Its `mode` is `play`, `next`, `end`, or `replace`.
Play and Next insert after the currently reported queue position; Play also
starts the inserted item, while End appends. Replace is destructive and must be
confirmed by the UI. Before clearing, the backend requires a complete backup
of at most 100 restorable items and a verifiable playback source/position; if
adding or starting the replacement fails, it attempts to restore the previous
queue and queue playback position.

### Exact Apple-song Sonos Playlist plans

`playlist_plan.apple.validate` is read-only. It accepts an exact `roomUid`, a
new `playlistName`, `mode` (`save-only` or `save-and-play`), optional Boolean
`allowDuplicates`, and one to 25 reviewed tracks. Each track has exactly these
fields:

```json
{
  "catalogId": "1452806384",
  "url": "https://music.apple.com/ch/album/kiss-me-kiss-me-kiss-me/1452806377?i=1452806384",
  "title": "Just Like Heaven",
  "artist": "The Cure",
  "album": "Kiss Me, Kiss Me, Kiss Me",
  "durationMs": 212000
}
```

The URL must pass Sonarchy's exact public-Apple HTTPS policy and pinned SoCo
0.31.2 must canonicalise it specifically as `song:<catalogId>`. Album,
playlist, artist, radio, arbitrary-host, credential-bearing, non-standard-port,
and unknown links are rejected. Sonarchy never constructs a URL from the ID or
substitutes a catalog result based on display metadata.

Preflight authoritatively checks the exact room and topology, the complete
restorable queue (maximum 100 items), queue position and revision/fingerprint,
transport and source, a SHA-256 media-identity fingerprint, room/group volume
and mute, required capabilities, the Sonos Playlist inventory, name collision,
ordered identities, duplicate policy, and total duration. The raw Sonos media
URI is never returned. An `x-rincon-queue:` current URI authoritatively projects
`QUEUE` even when pinned SoCo's coarse source is `UNKNOWN`; non-queue `UNKNOWN`
remains ineligible. The response includes the exact review, expected side
effects, and a random opaque plan token that expires after at most 120 seconds.
The initial restoration contract accepts an authoritatively `PLAYING` or
`STOPPED` transport; paused, transitioning, unknown, oversized, or otherwise
unrestorable state requires a safe state before preflight can succeed.

The token is memory-only, process-local, single-use, and atomically consumed
before mutation. It binds the operation, backend revision, exact room,
topology, queue identity/order and length, transport/source, exact hashed media
identity, volume/mute, capabilities, playlist inventory and name, mode,
duplicate policy, ordered canonical songs, expiry, and random nonce. It proves
recent validation, not human approval. A backend restart, replay, expiry, newer
backend revision, or changed authoritative target state requires a new
preflight.

`playlists.apple.create` is the corresponding write. Its arguments are exactly:

```json
{ "planToken": "opaque-process-local-token", "approved": true }
```

It rejects replacement tracks, URLs, room IDs, names, or modes. `approved`
must be explicitly `true` immediately before the call. The backend claims the
token even when the subsequent mutation fails, so a failed attempt cannot be
retried without a fresh preflight and approval.

Both modes revalidate state, back up the queue, clear it temporarily, enqueue
each exact song without starting playback, verify the constructed queue, create
the new Sonos Playlist, reopen it by authoritative `SQ:<id>`, and verify exact
count, order, canonical identities, title, and artist. Existing exact-name
collisions are never overwritten or deleted.

- `save-only` restores and verifies the complete previous queue, queue
  position, source, and exact `PLAYING`/`STOPPED` state.
- `save-and-play` starts queue item 1 and leaves the approved queue active.

After a post-mutation failure, the transaction removes a partial playlist only
when the create invocation returned a valid new `SQ:<id>` and that exact ID
still resolves to the invocation's expected playlist. It never infers ownership
from a new name. If creation might have succeeded without returning an
attributable ID, every candidate is left untouched and
`playlistCleanupRequired` is `true`. A safe structured error reports the
controlled failure phase and bounded rollback evidence; it never contains an
exception, address, token, DIDL, URI, or raw service metadata.

`alarms.save` carries both the selected anchor `roomUid` and the requested
`alarmRoomUid`. The backend accepts the target only when it is currently
visible from the anchor room in the same Sonos household. Existing alarms may
change rooms through Sonos's native update operation; if that update is
rejected, every locally cached alarm field is restored before an authoritative
alarm refresh.

Successful `devices.details.get` results include `device.tv_audio_format` only
as a non-null object for speakers that positively report soundbar support. Its
`state` is `active`, `idle`, `unavailable`, or `unknown`, and `label` contains a
bounded normalized display value. Unsupported rooms use `null`; probe errors
become `unavailable` without failing the rest of device details. Sonarchy does
not infer a format that the speaker did not report.

## Result

```json
{
  "type": "result",
  "version": 1,
  "id": "qml-42",
  "ok": true,
  "revision": 18,
  "value": null
}
```

A failed result contains an error object:

```json
{
  "type": "result",
  "version": 1,
  "id": "qml-42",
  "ok": false,
  "revision": 18,
  "error": {
    "code": "invalid_argument",
    "message": "Position must be within the current track",
    "retryable": false,
    "operation": "playback.seek"
  }
}
```

Messages are safe for direct display. They never contain raw exceptions,
private addresses, credentials, or service metadata.
Transactional failures may additionally contain a bounded `details` object,
for example `phase` plus `rollback.attempted`, `playlistRemoved`,
`playlistCleanupRequired`, `queueRestored`, `environmentUnchanged`, and
`succeeded`.

## Snapshot

```json
{
  "type": "snapshot",
  "version": 1,
  "revision": 18,
  "status": {},
  "capabilities": ["playback.toggle", "volume.group.set"],
  "households": [],
  "target": null,
  "playback": {},
  "favorites": {}
}
```

`revision` increases whenever the backend emits a new authoritative snapshot.
It is process-local and resets after backend restart. QML discards a snapshot
older than the newest revision it has applied.

`capabilities` is a sorted list of stable positive action names. It is derived
from discovered topology and actions advertised by the current Sonos source;
it is never inferred from speaker model names. Rooms additionally expose
`lineInAvailable`, populated by a bounded read-only AudioIn action probe. QML
uses these projections to render or disable commands.

## Events

The backend may emit versioned event objects for progress that is not itself an
authoritative snapshot. Events carry a stable `event` name and optional request
ID. QML must not derive speaker state solely from an event.

## Compatibility

- Adding optional fields is backward compatible within v1.
- Removing or changing required fields requires a new protocol version.
- A peer receiving an unsupported version returns `unsupported_version` when
  possible and otherwise terminates before executing the request.
- The protocol inventory is tested for exact agreement with registered
  handlers.
