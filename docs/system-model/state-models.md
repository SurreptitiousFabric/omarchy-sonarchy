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
    Starting --> Setup: private environment missing or hash changed
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

## 2. Authoritative versus optimistic state

```mermaid
stateDiagram-v2
    [*] --> Authoritative
    Authoritative --> OptimisticPending: user changes bounded control
    OptimisticPending --> Authoritative: newer snapshot confirms or corrects value
    OptimisticPending --> ActionError: matching request fails
    ActionError --> Authoritative: allowed retry or refresh succeeds
    ActionError --> Dismissed: user dismisses message
    Dismissed --> Authoritative: later healthy snapshot
```

Rules:

- every request has an ID and an error owner;
- a newer authoritative snapshot wins over an older optimistic value;
- an unrelated background success cannot clear a foreground action error;
- an unrelated background failure cannot replace an error already being shown;
- dismissal removes the message, not the underlying network or setup problem.

## 3. Playback transport and source capability

Transport state and media source are orthogonal. A room can be `PLAYING`, for
example, while the source is Queue, Radio, TV, Line-In, or another provider.
The source determines which transitions are legal.

```mermaid
stateDiagram-v2
    [*] --> NoTarget
    NoTarget --> Stopped: select reachable room
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

No UI or future MCP client should infer these rows from a speaker model name or
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
- a future AI call must carry an explicit room identity rather than relying only
  on mutable QML selection.

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

A displayed list is not an authority grant. Before a mutation, the backend
re-reads bounded path segments, the claimed absolute index, and the exact item
identifier so an updated Sonos index cannot redirect an old click to a new item.

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

## 7. Queue replacement transaction

```mermaid
stateDiagram-v2
    [*] --> Unchecked
    Unchecked --> Revalidated: room, path, index, item, and mode match current state
    Unchecked --> Refused: stale or invalid identity
    Revalidated --> BackedUp: complete queue and source position are restorable
    Revalidated --> Refused: queue exceeds bounded backup or source cannot be restored
    BackedUp --> Replacing: clear and add exact replacement
    Replacing --> Completed: add and start succeed
    Replacing --> Restoring: required step fails
    Restoring --> Restored: old queue and position confirmed
    Restoring --> RecoveryFailed: restoration cannot be proven
    Completed --> [*]
    Restored --> [*]
    Refused --> [*]
    RecoveryFailed --> [*]
```

`RecoveryFailed` must be visible and actionable. It must never be collapsed into
a generic success message.

## 8. Alarm draft

```mermaid
stateDiagram-v2
    [*] --> CleanDraft
    CleanDraft --> DirtyDraft: user edits a field
    DirtyDraft --> InvalidDraft: local validation fails
    InvalidDraft --> DirtyDraft: user corrects field
    DirtyDraft --> Saving: exact projection submitted
    Saving --> CleanDraft: authoritative alarm refresh confirms result
    Saving --> SaveError: target/program changed or speaker rejects update
    SaveError --> DirtyDraft: correct and retry
    CleanDraft --> [*]: cancel/close
    DirtyDraft --> [*]: confirmed cancel
```

The draft owns presentation edits. The backend owns household membership,
program identity, and the mutation. A rejected update restores locally cached
alarm fields before authoritative refresh.

## 9. Planned MCP permission states

This model is a design constraint for issues #11–#15, not current behavior.

```mermaid
stateDiagram-v2
    [*] --> Disabled
    Disabled --> ReadOnly: owner enables bounded inspection
    ReadOnly --> PlaybackAllowed: owner grants transport permission
    PlaybackAllowed --> QueueAllowed: owner grants queue mutation permission
    QueueAllowed --> PlaylistAllowed: owner grants playlist-write permission
    PlaylistAllowed --> ReadOnly: owner revokes write permissions
    QueueAllowed --> ReadOnly: owner revokes write permissions
    PlaybackAllowed --> ReadOnly: owner revokes write permissions
    ReadOnly --> Disabled: owner disables MCP
```

Speaker settings, topology, alarms, source switching, room rename, arbitrary
volume, and generic protocol passthrough remain outside these initial states.
They require separate design and grants rather than being implicitly included in
“control Sonos.”

## 10. Planned bespoke-playlist plan

```mermaid
stateDiagram-v2
    [*] --> Requested
    Requested --> ResolvingRoom
    ResolvingRoom --> NeedsClarification: room ambiguous or unavailable
    NeedsClarification --> ResolvingRoom: exact room chosen
    ResolvingRoom --> GatheringCandidates
    GatheringCandidates --> Drafted: bounded authorized candidates returned
    Drafted --> Validating: AI submits exact ordered identities
    Validating --> Drafted: unresolved, stale, duplicate, wrong-version, or unplayable item
    Validating --> ReviewReady: deterministic validation succeeds
    ReviewReady --> Cancelled: user declines
    ReviewReady --> Approved: user approves exact plan and action
    Approved --> Executing: permitted tool called
    Executing --> Completed: authoritative queue/playlist/playback confirms result
    Executing --> Failed: provider or Sonos rejects and recovery is reported
    Cancelled --> [*]
    Completed --> [*]
    Failed --> [*]
```

The AI client owns interpretation and proposal. Sonarchy owns exact resolution,
validation, permission, confirmation, mutation, and authoritative reporting.
