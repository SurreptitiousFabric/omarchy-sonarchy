# ADR 0002: Single-authority local MCP bridge

Status: Accepted for the MVP

## Decision

Quickshell continues to own one persistent Sonarchy backend. That backend keeps
its private JSON-lines stdin/stdout connection to `LiveService.qml` and also
listens on `${XDG_RUNTIME_DIR}/sonarchy/control.sock`. Codex launches
`sonarchy-mcp.sh` as a stdio MCP adapter; the adapter is only a client of this
socket and never starts a backend.

```text
Quickshell LiveService -- private stdin/stdout --+
                                                v
                                      authoritative backend
Codex -- MCP stdio adapter -- 0600 Unix socket --+
```

The process acquires a non-blocking `backend.lock` before constructing
`SonosController`, so there is one controller, `SonarchyApplication`, Apple
ticket store, `EventSubscriptionManager`, snapshot cache, revision stream, and
mutation dispatcher. QML and socket requests run serially on the same event
loop. Results are routed by client plus request ID; snapshots are broadcast.
Socket clients are bounded and slow, oversized, malformed, unverifiable, or
excess clients are disconnected without stopping the backend. Only QML may set
`session.panel_open.set`.

## Security and permission model

The runtime directory is owned by the desktop UID, mode `0700`, and must not be
a symlink. The lock and socket are `0600`. Linux peer credentials must prove the
connecting UID; otherwise the connection is rejected. There is no TCP, HTTP,
LAN, QML, or presentation-state transport. Stale sockets are removed only by
the lock owner after type and ownership checks; shutdown removes only the
socket inode created by that process.

The owner-only `${XDG_CONFIG_HOME:-$HOME/.config}/sonarchy/mcp.toml` is read at
backend startup. Missing configuration defaults to `read`; an explicit
`playlist-create` permission adds only `playlists.apple.create`. Socket
snapshots are an authoritative address-free projection; QML retains its private
full snapshot. The socket
allowlist, not MCP annotations, enforces authorization. Unsafe or invalid
configuration fails closed to read-only; `enabled = false` disables socket
operations. Changes require restart.

## Consent boundary

The write tool is absent by default. A write-enabled client must first obtain a
complete exact-track preflight. The adapter hides the backend ticket behind a
short-lived, random, process-local, memory-only, single-use handle. Execution
accepts only that handle and `approved: true`, revalidates state, never retries
or substitutes, and uses exact-ID cleanup after partial failure. The MCP client
must obtain explicit current user approval immediately before execution. The
boolean is a request assertion, not independent proof of human consent.

Backend restart invalidates backend tickets and connections. MCP restart loses
all handles. Reconnection may retry reads, but never replays writes; a new
preflight is required.

## Alternatives

- Rejected: a Codex-launched backend/controller. It duplicates discovery,
  subscriptions and writes and splits the ticket store.
- Rejected: QML as an MCP proxy. Presentation state is not the authoritative
  domain boundary and would create selected-room ambiguity.
- Deferred: a systemd user service owning the backend for shell-independent
  availability. Socket activation, install/removal, migration, upgrade and
  restart ordering add operational scope inappropriate for this MVP.

## Deferred scope

Playback, queue replacement or mutation, volume/mute, grouping/topology,
selection, source switching, alarms, settings, rename, playlist replacement or
deletion, private Apple-library access, arbitrary URI/protocol access, and a
desktop confirmation popup are not exposed. Room-targeted playback remains
issue #14 and requires a separate design and PR.
