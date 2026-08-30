# Declared capabilities

Omarchy loads shell plugins without a sandbox. This file states every material
capability used by `io.github.surreptitiousfabric.sonarchy` so marketplace
reviewers and users do not need to infer them from the code.

| Capability | Used | Reason and boundary |
|---|---:|---|
| `installer` | Yes, first run only | `sonarchy-backend.sh` creates one private virtual environment below the user's XDG data directory. No install hook runs during `omarchy plugin add`. |
| `package-manager` | Yes, first run and lock changes | The venv invokes pip in an allowlisted environment, without a download cache, non-interactively against PyPI with `--require-hashes`, `--no-deps`, wheel-only installs, and exact versions from `requirements.lock`. |
| Local-network access | Yes | SSDP/UPnP control of private IPv4 Sonos speakers, normally TCP 1400. |
| Inbound LAN listener | Yes, notifications only | SoCo subscriptions bind the attached interface on TCP 1400–1499. Requests are limited to 16 concurrent handlers, 512 KiB bodies, three-second socket timeouts, bounded 1,024-event buffering, valid sequence headers, active subscription IDs, and the exact subscribed speaker IP. No controls are accepted. |
| Public HTTPS | Yes | Explicit Apple catalog searches, optional popup-scoped matching of Sonos-supplied radio title/artist metadata, and allowlisted artwork/service hosts. Redirects and oversized Apple responses are rejected. |
| Persistent files | Yes | Selected room UID and private speaker IP cache; private venv and dependency hash. Directories are 0700 and state/cache files are 0600. |
| Subprocesses | Yes | Quickshell starts one persistent Python backend through the checked-in shell launcher. It receives a small allowlisted environment rather than the full desktop environment; QML has no one-shot command bridge. |
| Privilege escalation | No | No `sudo`, `pkexec`, setuid, capabilities, polkit rules, or sudoers changes. |
| System package manager | No | No pacman, AUR helper, apt, dnf, or system Python installation. |
| Service management | No | No systemd unit or long-lived process outside the Omarchy shell lifecycle. |
| Remote build or bundled binary | No | Source-only QML, Python, shell, Markdown, and JSON. |
| HTTP control API | No | No web UI, REST control service, or listener on port 8000. Commands use a private stdin/stdout pipe. |
| Credentials or secret storage | No | No Sonos, Apple, Global Player, SMB, or other account password/token is requested or persisted. |
| Telemetry | No | No analytics, crash upload, advertising, or maintainer-operated service. |

## Application action capabilities

When at least one room is authoritatively available, snapshots now advertise:

- `playlist_plan.apple.validate`: read-only exact room/household anchor,
  playlist-inventory/name, direct saved-playlist capability, and exact Apple
  song preflight; and
- `playlists.apple.create`: the explicitly approved, token-only create and
  authoritative verification transaction.

These names describe positive operations in the private application protocol;
they do not create a public API or MCP server. The create operation has no
plain-title, arbitrary URL/URI, generic protocol, raw SoCo, or overwrite form.
No Apple credential, private-library permission, or native Apple Music
playlist-write capability is added.
The create-only operation does not inspect or mutate a room queue, playback,
transport, position, volume, mute, or topology. Playback of the returned exact
`SQ:<id>` remains a separate existing action and is not approved by creation.

A local run of the marketplace's current v3 deterministic scanner marks this
release **review-required** for `package-manager`, with no findings. The project
also declares the first-run venv bootstrap above as installer-like behavior for
human review even though that scanner does not currently emit an `installer`
capability for the root launcher. This is an intentional disclosure, not a
claim that the plugin can bypass review.
