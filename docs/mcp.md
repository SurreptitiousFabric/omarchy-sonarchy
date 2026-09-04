# Local MCP integration

Sonarchy exposes local AI access without creating another Sonos controller.
Quickshell owns the backend; `sonarchy-mcp.sh` is a thin stdio adapter to the
owner-only `${XDG_RUNTIME_DIR}/sonarchy/control.sock`. There is no LAN, TCP, or
HTTP listener, and the adapter never starts a fallback backend.

## Permissions

No configuration means read-only. To state that explicitly, create
`${XDG_CONFIG_HOME:-$HOME/.config}/sonarchy/mcp.toml` as the current user with
mode `0600`:

```toml
enabled = true
permissions = ["read"]
```

To expose exact reviewed playlist creation:

```toml
enabled = true
permissions = ["read", "playlist-create"]
```

To expose exact reviewed native Sonos Playlist playback instead:

```toml
enabled = true
permissions = ["read", "playlist-play"]
```

`playlist-play` is independent from `read` and `playlist-create`. Read remains
required. A configuration containing only `read` and `playlist-create` does not
expose playback; both writes require listing both optional permissions.

Set `enabled = false` to disable socket operations, or remove the file to return
to the read-only default. Reject symlinks and do not make the file group/world
accessible. Permission changes take effect only after the Quickshell-owned
backend restarts.

## Codex configuration

Codex CLI 0.151.0 reports the supported stdio form as `codex mcp add NAME --
COMMAND...`. From an installed plugin directory:

```sh
codex mcp add sonarchy -- /absolute/path/to/sonarchy-mcp.sh
```

The equivalent checked TOML shape is:

```toml
[mcp_servers.sonarchy]
command = "/absolute/path/to/sonarchy-mcp.sh"
```

The Codex entry is identical for every permission set; the owner-only
Sonarchy configuration above controls both tool inventory and backend access.
Do not edit global Codex configuration during plugin installation.

## Stdio protocol boundary

The adapter accepts one individual UTF-8 JSON-RPC 2.0 object per newline-
delimited physical frame. Embedded physical newlines and top-level arrays or
JSON-RPC batches are not supported. Input and output frames include their
terminating newline in the 64 KiB limit.

Input is read and oversized-frame remainders are drained in bounded chunks.
An oversized input receives one bounded Invalid Request response, and malformed
JSON or UTF-8 does not terminate the adapter. Valid JSON-RPC notifications
receive no response; a later valid request is processed normally. Every stdout
line is one complete bounded JSON-RPC message. Diagnostics, when present, go
only to stderr and never include the raw input.

## Tools

- `rooms_list`: exact room UIDs plus bounded household/group facts.
- `room_state_get`: current bounded state for one exact UID.
- `content_browse`: explicitly mapped Sonarchy browse kinds and normalized
  provider-neutral results.
- `apple_playlist_preflight`: exact 1–25 track review and opaque `planHandle`.
- `sonos_playlist_play_preflight`: read-only review of one exact existing
  `SQ:<id>`, exact room UID, complete bounded playlist and queue state, and
  append-and-play effects.
- `apple_playlist_create`: present only with `playlist-create`; creates one new
  native Sonos Playlist and does not play or alter a queue.
- `sonos_playlist_play`: present only with `playlist-play`; accepts exactly a
  fresh `planHandle` and `approved: true`, appends the reviewed playlist to the
  unchanged queue, and starts its first newly appended item.

There is no generic operation, command, URI, UPnP, SoCo, arbitrary playback,
queue clear/replace/edit, volume, grouping, settings, alarm, source, rename,
playlist edit/replacement, or deletion tool.
Public Apple catalogue search is supported; private Apple-library access is not.

## Consent example

1. Run `apple_playlist_preflight` and show the exact reviewed plan, including
   its room UID, playlist name, ordered tracks, collision status, duration,
   Sonos-acceptance status, mutation flags, expected side effects, and expiry.
2. Obtain explicit user approval for that exact plan.
3. Immediately perform a fresh, identical preflight after approval.
4. Compare the fresh plan's exact fingerprint, room UID, playlist name,
   ordered tracks, collision status, and side effects with the approved review.
5. If anything changed, stop and ask for approval again.
6. If everything is identical, immediately call `apple_playlist_create` with
   only the fresh `planHandle` and `approved: true`.

The MCP client owns the confirmation interaction. `approved: true` alone is not
proof that a human approved it. Revalidating immediately after approval avoids
depending on a human response within the backend ticket's 120-second lifetime
while preserving approval of the exact content and side effects. Handles and
tickets are short-lived and single-use; after any backend or adapter restart,
repeat preflight. Writes are never retried.

An MCP plan handle may be visible in a client's tool invocation display. It is
not the backend token, is short-lived and single-use, and must not be copied
into logs or documentation.

### Exact Sonos Playlist playback consent

1. Call `sonos_playlist_play_preflight` with only an exact `roomUid` and exact
   `playlistId`.
2. Show the complete room, topology, volume/mute, transport/source, playlist,
   queue, item-preview, fingerprints, append position, and side-effect review.
3. Obtain explicit user approval for that exact review.
4. Immediately call the same preflight again. Compare every reviewed fact
   except handle and expiry. If anything changed, do not play and request new
   approval.
5. If identical, call `sonos_playlist_play` exactly once with only the fresh
   handle and `approved: true`. Never use the first review handle.

Playback is limited to an online standalone room at volume 20 or below. The
room must be stopped or paused and its source must be authoritatively the Sonos
queue or no active source. The playlist must contain 1–25 completely readable
items, and the complete queue plus playlist may contain at most 100 items.

All existing queue entries remain. Sonarchy appends the complete playlist and
moves playback to the first appended item, interrupting a paused or stopped
queue context. It does not change volume, mute, topology, source settings, or
playlist contents, and never retries. If append succeeds but playback start or
verification fails, the appended items may remain. Sonarchy reports that
partial state and does not clear, reconstruct, remove, or roll back queue items;
general rollback remains deferred to issue #19.

After the single playback mutation, post-write verification keeps `PLAYING` as
mandatory proof of success. If transport is initially `TRANSITIONING`, it may
observe transport only on a fixed 250 ms cadence, for at most 20 observations;
the latest new observation may start at 5,000 ms. That boundary is not a hard
end-to-end timeout: an already-started synchronous SoCo read may finish later.
Observing `PLAYING` only triggers one fresh complete capture of the exact room,
playlist, queue, position, item, source, volume, mute, and topology. A bounded
verification failure is reported as non-retryable `verification_inconclusive`
because mutation may already have occurred. Actual speaker rejection and plan
expiry retain their separate classifications. No mutation retry or rollback
occurs.

## Diagnostics and removal

Inspect metadata without connecting or reading private traffic:

```sh
stat -Lc '%F %U %a %n' "$XDG_RUNTIME_DIR/sonarchy" \
  "$XDG_RUNTIME_DIR/sonarchy/backend.lock" \
  "$XDG_RUNTIME_DIR/sonarchy/control.sock"
codex mcp get sonarchy
```

“Sonarchy is unavailable” means the fixed socket could not be safely reached.
Confirm the plugin is enabled, Quickshell is running, `XDG_RUNTIME_DIR` is
present, and the socket is owned by the current user with mode `0600`. The
adapter will reconnect on a later read; it never launches a backend.

Remove the Codex entry with `codex mcp remove sonarchy`. Remove the optional
`mcp.toml` separately if desired. Neither operation deletes playlists or changes
speakers.
