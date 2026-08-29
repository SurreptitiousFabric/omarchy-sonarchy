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
new `playlistName`, `mode: "save-only"`, optional Boolean `allowDuplicates`,
and one to 25 reviewed tracks. `save-and-play` is not accepted. Each track has
exactly these fields:

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
substitutes a catalogue result based on display metadata.

Preflight authoritatively checks the exact room UID used as household anchor,
coordinator and hashed household identity, required direct saved-playlist
capability, complete Sonos Playlist inventory fingerprint/count, name
collision, ordered identities, duplicate policy, and total duration. It does
not read or bind queue contents, source/position, media identity, transport,
volume, mute, or room topology. The response includes the exact bounded review,
expected side effects, and a random opaque plan token that expires after at
most 120 seconds. Reviewed URLs remain backend-only and are not echoed.
The bounded inventory admits at most 100 Sonos Playlists and preflight requires
one free verification slot. Post-create verification and owned cleanup may
read exactly one bounded transaction extra so a concurrent create cannot make
the transaction's attributable ID unreachable.

The token is memory-only, process-local, single-use, and atomically consumed
before the first playlist mutation. It binds the operation, exact
room/household anchor, capabilities, playlist inventory and name, create-only
mode, duplicate policy, ordered reviewed songs, expiry, and random nonce. It
proves recent validation, not human approval. A backend restart, replay,
expiry, or changed authoritative target state requires a new preflight. The
general snapshot revision is deliberately not bound because unchanged
background polls advance it; execution re-captures every material target fact.
Requests rejected before a ticket is claimed, including missing approval,
replacement arguments, and unavailable tokens, do not emit a mutation refresh
or advance the backend revision. A still-valid ticket therefore remains usable
after an unrelated pre-claim rejection. Once a valid ticket is atomically
claimed, every accepted execution attempt consumes it. Create-only
intentionally does not request the general playback
snapshot after execution because that would perform irrelevant queue,
transport, volume, and mute reads.
The complete result envelope is serialized as unescaped UTF-8 JSON and measured
against the 64 KiB protocol-line limit before the review is returned. Request
IDs and operation names are byte-bounded. If a review does not fit, its
unpublished ticket is discarded and validation fails safely.
Every authoritative snapshot is measured against the same complete UTF-8 line
limit. A snapshot that does not fit is neither cached nor partially emitted;
the server emits a fixed bounded degraded snapshot without target-derived write
capabilities, preserves the monotonic revision, and continues serving startup,
polling, and mutation-refresh traffic.
The successful create result is bounded too. `playlist.items` contains the one
full sequence of reviewed metadata after authoritative reopen comparison.
Provider-returned text, URLs, and optional Sonos item IDs are not echoed. A
maximal 25-track result, including the worst bounded request ID, must fit the
same 64 KiB line.

`playlists.apple.create` is the corresponding write. Its arguments are exactly:

```json
{ "planToken": "opaque-process-local-token", "approved": true }
```

It rejects replacement tracks, URLs, room IDs, names, or modes. `approved`
must be explicitly `true` immediately before the call. The backend claims the
token even when the subsequent mutation fails, so a failed attempt cannot be
retried without a fresh preflight and approval.

Execution revalidates the exact anchor, inventory, unused name, capacity,
ordered tracks, and direct capability. It creates one empty Sonos Playlist
through SoCo's normal API, validates the create-returned new `SQ:<id>`, and
reopens that exact ID. One private Apple-only adapter then appends each exact
song directly to the saved playlist. The adapter fixes every provider-specific
field internally and uses SoCo data structures for escaped XML; none of its
URI, DIDL, service, account, flag, or SOAP fields can be supplied through the
protocol.

After every add, bounded authoritative reopen verifies expected count, exact
new position, canonical identity, and reviewed title/artist/album. Final reopen
verifies the complete sequence, exact name, and unchanged pre-existing
playlist inventory. Identity evidence is accepted only as a complete canonical
`song:<id>`, complete pinned Apple Sonos item ID, or leading song token of the
expected Sonos Apple resource form. A saved-playlist browse may instead return
the pinned Apple HLS-static form observed during the one-track physical test;
that form is accepted only as one complete resource with the Apple service
identity derived from the pinned service type, bounded saved-resource fields,
and the exact HLS protocol type. Arbitrary substrings, another provider, and
catalogue IDs present only in query parameters cannot satisfy verification.
Sonos's physically observed comma removal plus literal `(Deluxe Edition)`
album-display qualifier is accepted only after exact catalogue identity, title,
and artist comparison; unrelated album or edition text is rejected. Success
returns `queueMutation: false` and `playbackMutation: false`; no queue or
playback method is invoked.

Catalogue validation reports `catalogueIdentityValidated: true` and
`sonosAcceptance: "unproven_until_create"`. A direct add may still be rejected
by Sonos. Execution stops at the first failure, never retries the track, and
never substitutes another catalogue ID or recording.

Cleanup targets a partial playlist only when the exact create-returned ID is a
validated new `SQ:<id>` and that exact ID authoritatively resolves to the
invocation-bound title. Title alone never establishes ownership. One deletion
is attempted and verified; no title fallback or second-ID guess is allowed. If
exact deletion fails, the attributable ID is returned with
`playlistCleanupRequired: true` and every unrelated playlist remains untouched.

Playback of the new exact `SQ:<id>` is a separate existing action. This token
does not approve it, and the create transaction never starts playback.

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
with `phase: "playlist_creation"` plus:

- `playlistConstructionStep`: `create`, `add_track`, `verify_track`,
  `verify_playlist`, or `cleanup`;
- `failedTrackPosition`: integer 1–25 for a track-owned step;
- `failedCanonicalIdentity`: exact bounded `song:<catalogId>` for that track;
- `sonosErrorCode`: a strictly bounded numeric or symbolic value read only
  from pinned `SoCoUPnPException.error_code`;
- `partialPlaylistId`: only a validated, invocation-attributable `SQ:<id>`;
- `playlistRemoved`, `playlistCleanupRequired`,
  `preExistingPlaylistsUnchanged`, `queueUnchanged`, `playbackUnchanged`, and
  `succeeded`: bounded Booleans.

Optional fields are omitted when unavailable. They are typed at the failure
site and never inferred by parsing exception text. Exception messages,
descriptions, XML, arguments, URIs, DIDL, addresses, credentials, and raw
service metadata are not included.

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
