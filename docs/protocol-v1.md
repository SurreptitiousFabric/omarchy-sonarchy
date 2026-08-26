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

The backend temporarily accepts the legacy shape with operation arguments at
the request root. QML migrates first; legacy acceptance is removed with
`sonarchy_bridge.py`.

## Result

```json
{
  "type": "result",
  "version": 1,
  "id": "qml-42",
  "ok": true,
  "revision": 18,
  "capabilities": ["playback.toggle", "volume.group.set"],
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

## Snapshot

```json
{
  "type": "snapshot",
  "version": 1,
  "revision": 18,
  "status": {},
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
it is never inferred from speaker model names. QML uses this list to render or
disable commands as pages migrate to capability-driven behavior.

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
