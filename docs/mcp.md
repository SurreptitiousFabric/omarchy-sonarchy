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

The Codex entry is identical for read-only and playlist-create; the owner-only
Sonarchy configuration above controls both tool inventory and backend access.
Do not edit global Codex configuration during plugin installation.

## Tools

- `rooms_list`: exact room UIDs plus bounded household/group facts.
- `room_state_get`: current bounded state for one exact UID.
- `content_browse`: explicitly mapped Sonarchy browse kinds and normalized
  provider-neutral results.
- `apple_playlist_preflight`: exact 1–25 track review and opaque `planHandle`.
- `apple_playlist_create`: present only with `playlist-create`; creates one new
  native Sonos Playlist and does not play or alter a queue.

There is no generic operation, command, URI, UPnP, SoCo, playback, volume,
grouping, settings, alarm, source, rename, replacement, or deletion tool.
Public Apple catalogue search is supported; private Apple-library access is not.

## Consent example

1. Call `apple_playlist_preflight` with the exact room UID, new name,
   duplicate policy, and exact reviewed Apple songs.
2. Display every ordered track, collision state, duration, Sonos-acceptance
   status, `queueMutation: false`, `playbackMutation: false`, expected side
   effects, and expiry.
3. Stop and ask the user to approve creating exactly that playlist.
4. Only after an explicit current confirmation, call
   `apple_playlist_create` with only `planHandle` and `approved: true`.

The MCP client owns the confirmation interaction. `approved: true` alone is not
proof that a human approved it. Handles and tickets are single-use; after any
backend or adapter restart, repeat preflight. Writes are never retried.

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
