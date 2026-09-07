# State and capability models

This page answers **what can happen from the system's current state**. Journey
models describe a goal over time; state models describe legal transitions and
why an action may be enabled now, disabled now, or rejected after the world
changes.

## 1. Backend lifecycle

```mermaid
stateDiagram-v2
    [*] --> Stopped
    Stopped --> Starting: QML starts launcher
    Starting --> Setup: environment health or lock/runtime identity requires rebuild
    Starting --> SetupError: unsupported system interpreter
    Starting --> Discovering: runtime ready
    Setup --> Discovering: dependencies verified
    Setup --> SetupError: bootstrap or verification fails
    SetupError --> Starting: user refreshes or supervisor retries
    Discovering --> Healthy: authoritative snapshot emitted
    Discovering --> NoRooms: bounded discovery finds no room
    NoRooms --> Discovering: Search again or cached host changes
    Healthy --> Degraded: refresh or subscription temporarily fails
    Degraded --> Healthy: fresh authoritative snapshot
    Healthy --> Restarting: process exits
    Degraded --> Restarting: process exits
    Restarting --> Starting: supervised restart
    Healthy --> Stopped: shell/plugin lifecycle ends
```

A process restart resets process-local snapshot revisions. QML treats a healthy
snapshot from the replacement process as recovery; merely starting a new PID is
not sufficient.
The launcher supports stable CPython 3.14.x only; setup/restart does not make
an unsupported interpreter compatible. See [ADR 0003](../adr/0003-python-runtime-policy.md).

## 2. Authoritative versus optimistic state

```mermaid
stateDiagram-v2
    [*] --> Authoritative
    Authoritative --> OptimisticPending: user changes bounded control
    OptimisticPending --> Authoritative: newer snapshot confirms or corrects value
    OptimisticPending --> ActionError: matching request fails
    ActionError --> Authoritative: allowed retry or refresh succeeds
    ActionError --> Dismissed: user dismisses message
    ActionError --> Dismissed: ten-second request or transient-error timer expires
    Dismissed --> Authoritative: later healthy snapshot
```

Rules:

- every request has an ID and an error owner;
- a newer authoritative snapshot wins over an older optimistic value;
- an unrelated background success cannot clear a foreground action error;
- an unrelated background failure cannot replace an error already being shown;
- timers can clear errors even without a successful owning request;
- dismissal or expiry removes the message, not the underlying problem.

## 3. Playback transport and source capability

Transport state and media source are orthogonal. A room can be `PLAYING`, for
example, while the source is Queue, Radio, TV, Line-In, or another provider.
The source determines which transitions are legal.

```mermaid
stateDiagram-v2
    [*] --> NoTarget
    NoTarget --> Stopped: selected target reports STOPPED
    NoTarget --> Playing: selected target reports PLAYING
    NoTarget --> Paused: selected target reports PAUSED_PLAYBACK
    NoTarget --> OtherObserved: target projection is transitional or unknown
    OtherObserved --> Stopped: later projection reports STOPPED
    OtherObserved --> Playing: later projection reports PLAYING
    OtherObserved --> Paused: later projection reports PAUSED_PLAYBACK
    OtherObserved --> NoTarget: selected room disappears
    Stopped --> Playing: play exact supported item
    Playing --> Paused: pause supported
    Paused --> Playing: play
    Playing --> Stopped: stop
    Paused --> Stopped: stop
    Playing --> Playing: next / previous / seek / play-mode change when supported
    Paused --> Paused: seek when supported
    Stopped --> NoTarget: selected room disappears
    Playing --> NoTarget: selected room disappears
    Paused --> NoTarget: selected room disappears
```

Target acquisition is observation, not a stop/play/pause command. Selecting a
different room likewise projects that coordinator's existing state without
changing its group or transport. The command-labelled arrows above require
separate user actions and the corresponding capability.

This is a simplified projection model, not an exhaustive device transport
enum. `TRANSITIONING`, `UNKNOWN` and other nonsettled observations are not
coerced to Stopped. The backend can retain last-known playback with a stale
marker when fresh evidence is unavailable or uncertain; freshness is separate
from the displayed transport state. Later snapshots or another controller's
actions can update the projection without a local transport command.

### Typical source capability matrix

This table is explanatory. The backend's positive capability projection is
authoritative for the current source.

| Action | Sonos queue | Live radio | TV | Line-In | Provider item/container |
|---|---:|---:|---:|---:|---:|
| Play/pause | Usually | Provider-dependent | Source-dependent | Source-dependent | After valid dispatch |
| Stop | Usually | Usually | Source-dependent | Source-dependent | After valid dispatch |
| Previous/next | When advertised | Usually unavailable | Unavailable | Unavailable | Depends on resulting queue/source |
| Seek | When advertised | Usually unavailable | Unavailable | Unavailable | Depends on resulting queue/source |
| Shuffle/repeat/crossfade | Queue only, when supported | Disabled | Disabled | Disabled | Enabled only after queue becomes active |
| Queue edit | Yes | Edits queue but does not necessarily replace active radio until played | Edits queue but TV Autoplay can reclaim source | Edits queue but line-in remains source until changed | Depends on exact insertion path |

No UI or MCP client should infer these rows from a speaker model name or
from stale values left over from an earlier source.

## 4. Selected room, playback group, and exact-room controls

```mermaid
stateDiagram-v2
    [*] --> NoSelection
    NoSelection --> StandaloneSelected: select standalone room UID
    NoSelection --> GroupMemberSelected: select grouped room UID
    StandaloneSelected --> GroupMemberSelected: topology groups selected room
    GroupMemberSelected --> StandaloneSelected: topology ungroups selected room
    StandaloneSelected --> NoSelection: room no longer visible
    GroupMemberSelected --> NoSelection: room no longer visible
    StandaloneSelected --> StandaloneSelected: rename confirmed
    GroupMemberSelected --> GroupMemberSelected: rename confirmed
```

Target rules:

- transport and group-volume actions target the selected room's current playback
  coordinator/group;
- room volume, mute, rename, and product settings target the exact room UID;
- selecting another playback session changes what is controlled but does not
  itself move audio;
- handoff is a separate validated mutation;
- room-targeted MCP calls require an explicit room UID rather than mutable QML
  selection; public Apple browsing alone can omit the room. Supplying an
  invalid room is still an error, not permission to fall back silently.

## 5. Content navigation

```mermaid
stateDiagram-v2
    [*] --> SourceRoot
    SourceRoot --> Loading: search or open container
    Nested --> Loading: open child or request another page
    Loading --> SourceRoot: root result
    Loading --> Nested: authoritative breadcrumbs and items returned
    Nested --> Nested: Back to authoritative parent
    Nested --> SourceRoot: Back from first level
    Loading --> Stale: path segment, absolute index, or item identity changed
    Loading --> Error: provider, network, or validation failure
    Stale --> SourceRoot: return to root or refresh
    Error --> Loading: retry
    Error --> SourceRoot: choose another source
```

A displayed list is not an authority grant. Hierarchical library mutations
re-read bounded path segments, the claimed absolute index and the exact item
identifier so an updated Sonos index cannot redirect an old click to a new item.
Other sources follow their own lookup/validation contracts. In particular,
Favorite activation uses a cached ID and does not re-read the Favorites
inventory; the library guarantee must not be applied to that cached path.

## 6. Destructive-action confirmation

```mermaid
stateDiagram-v2
    [*] --> Idle
    Idle --> Armed: first press on one exact focused action
    Armed --> Idle: five seconds expire
    Armed --> Idle: focus/action changes
    Armed --> Submitted: matching second press
    Submitted --> Refreshing: backend accepts request
    Submitted --> ActionError: validation or mutation rejected
    Refreshing --> Idle: authoritative result applied
    ActionError --> Idle: dismiss, retry, refresh, or another action
```

The confirmation identity includes the action and target. A first press on one
queue item cannot confirm deletion of another item, and a drag/drop or keyboard
move cannot inherit an unrelated pending destructive action.

## 7. Guarded empty-queue playback

```mermaid
stateDiagram-v2
    [*] --> Unchecked
    Unchecked --> Revalidated: room, path, index, item, and mode match current state
    Unchecked --> Refused: stale or invalid identity
    Revalidated --> EmptyConfirmed: authoritative queue response proves empty and source is verifiable
    Revalidated --> Refused: queue nonempty or cannot be verified empty
    EmptyConfirmed --> Appending: add exact item without clearing
    Appending --> Starting: append returned a position
    Starting --> Completed: play call succeeds
    Appending --> PartialFailure: add raises or result invalid
    Starting --> PartialFailure: start raises
    Completed --> [*]
    Refused --> [*]
    PartialFailure --> [*]
```

This is the confirmed **Play if queue empty** action, not general replacement.
Refusal happens before writes. Partial failure is reported without clearing,
removing, reconstructing or replaying queue entries. Issue #19 remains open;
no arbitrary-provider restoration guarantee is made.

## 8. Alarm draft

```mermaid
stateDiagram-v2
    [*] --> Editing
    Editing --> Editing: edit a field or load an existing alarm
    Editing --> Editing: New immediately resets fields
    Editing --> InvalidDraft: local validation fails
    InvalidDraft --> Editing: correct fields or New resets them
    Editing --> Submitted: valid exact projection sent
    Submitted --> Editing: result and authoritative alarm list refresh
    Submitted --> SaveError: target/program changed or speaker rejects update
    SaveError --> Editing: correct and retry or New resets fields
```

The draft owns presentation edits. The backend owns household membership,
program identity, and the mutation. A rejected update restores locally cached
alarm fields before authoritative refresh. These labels describe the flow,
not a dirty-state flag in QML: there is no dirty-draft tracking or confirmed
cancel. The editor's New action calls `resetAlarm()` immediately, discarding
unsaved edits without a dialog; saving refreshes the list, not an implicit
reset of all editor fields.

## 9. Current MCP permissions

Permissions are independent configuration grants, not a hierarchy of transport,
queue and playlist authority. Changes take effect when the backend restarts.

| Configuration | Authority |
|---|---|
| `enabled = false` | MCP disabled |
| `permissions = ["read"]` | Default bounded reads and read-only preflights |
| `read` plus `playlist-create` | Reads and exact reviewed Apple Sonos Playlist creation; no playback |
| `read` plus `playlist-play` | Reads and exact reviewed native Sonos Playlist playback; no creation |
| `read` plus both optional grants | Both narrow writes, each with its own approval and preflight |

Speaker settings, topology, alarms, source switching, room rename, general
transport/volume/queue editing and generic protocol passthrough are absent.
Neither a QML capability nor one playlist grant authorizes another MCP action.
See [MCP setup](../mcp.md) for private configuration validation and exact bounds.

## 10. Current exact-plan lifecycle

```mermaid
stateDiagram-v2
    [*] --> Requested
    Requested --> Drafted: client resolves exact items and target
    Drafted --> Validating: read-only preflight
    Validating --> NeedsReview: invalid or unresolved plan
    NeedsReview --> Drafted: person reviews a revised proposal
    Validating --> ReviewReady: deterministic validation succeeds
    ReviewReady --> Cancelled: user declines
    ReviewReady --> Approved: user approves exact plan and action
    Approved --> Revalidating: repeat read-only preflight
    Revalidating --> NeedsReview: material facts changed
    Revalidating --> Executing: identical plan and independent permission; use fresh handle once
    ReviewReady --> Invalidated: expiry or backend restart
    Approved --> Invalidated: expiry or backend restart
    Executing --> Completed: complete authoritative verification succeeds
    Executing --> Failed: conflict, write failure or inconclusive verification
    Cancelled --> [*]
    Completed --> [*]
    Failed --> [*]
    Invalidated --> [*]
```

This lifecycle applies separately to creation and playback. The AI client owns
interpretation, proposal and human consent; Sonarchy validates the exact plan,
enforces permissions and single-use tickets, executes, and reports verified or
partial results. `approved: true` cannot establish that the client actually
obtained consent. Failure never implies an automatic execution retry. Creating
a playlist ends that plan; playing it needs a new, separately approved plan.
