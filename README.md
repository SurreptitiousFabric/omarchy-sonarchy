# Sonarchy

A keyboard-first Quickshell controller for Sonos systems on the local network.
Sonarchy follows the active Omarchy theme and does not require a Sonos cloud
login or expose a local web-control API.

This is an independent community project. It is not made, sponsored, or
endorsed by Sonos, Inc.; product and service names belong to their respective
owners.

## Features

- Event-driven now-playing state with bounded polling fallback
- Previous, play/pause, stop, next, seek, group volume, and group mute
- Playback-session selection, safe handoff, per-room mixer, and staged grouping
- Real room rename
- Sonos Favorites and current-queue playback, removal, clearing, and safe replacement
- Sonos Playlist create, save-queue, browse, play, reorder, and delete actions
- Hierarchical, paged local Sonos music-library browsing, track search, and index refresh
- Public Apple Music catalog and Global Player station search
- Confidence-checked album artwork for radio tracks, with a station-logo fallback
- Alarm create, room-aware edit, enable/disable, and delete, including Favorite sounds
- Line-in and TV source switching
- EQ, home-theater, Sub, surround, and supported device controls
- Speaker model, versions, battery, microphone, voice, source, and reported TV audio format
- Owner-only state, cached discovery, automatic reconnect, and keyboard controls

Destructive queue, playlist, and alarm actions require the same focused action
twice within five seconds. Queue and playlist item mutations also re-check the
item identifier so a stale screen cannot silently change a different track.
Library and playlist rows offer **Play now**, **Next**, **End**, and a confirmed
**Replace queue** action. Replace first verifies a bounded backup and restores
the previous queue if the new item cannot be added; queues over 100 items are
left untouched because Sonarchy cannot back them up completely.

## Install

Install the public repository with:

```bash
omarchy plugin add https://github.com/SurreptitiousFabric/omarchy-sonarchy --enable
omarchy bar move io.github.surreptitiousfabric.sonarchy --before omarchy.audio
```

The repository URL must point to the repository root containing
`manifest.json`.

On first start, the plugin creates a private virtual environment at
`${XDG_DATA_HOME:-$HOME/.local/share}/sonarchy/venv`. It downloads only the
versions and file hashes recorded in `requirements.lock`, directly from PyPI.
It does not install into system Python or the user's global Python environment,
never requests administrator privileges, and does not run an installer hook
during `plugin add`.
Python 3.14 or newer is required and is included with current Omarchy.

## Keyboard use

Open or close the popup without a mouse:

```bash
omarchy-shell shell toggle io.github.surreptitiousfabric.sonarchy '{}'
```

That command can be placed in a normal Omarchy/Hyprland user keybinding. The
plugin does not silently claim a global shortcut during installation.

While the popup is focused:

- `Tab` / `Shift+Tab`, `Up` / `Down`, or `J` / `K`: move focus
- `Enter` or `Space`: activate the focused control
- `Left` / `Right` or `H` / `L`: selected playback-group volume; when the
  bottom page dock is focused, move within the dock
- `N` / `P`: next / previous
- `M`: mute
- `S`: stop
- `R`: refresh
- `1` / `2` / `3` / `4` / `5` / `6`: Now / Browse / Queue / Rooms / Sound / System
- `Escape`: leave a text field, close a dropdown, or close the popup

Every action has a keyboard path. Number controls include focusable minus and
plus buttons because Omarchy's shared visual slider is pointer-oriented.
The fixed bottom dock keeps the six pages available without interrupting the
artwork, transport, and volume flow above it.

The six pages are:

- **Now:** metadata, seeking, transport, volume, play mode, and sleep timer.
- **Browse:** Favorites, Sonos Playlists, paged local-library folders and
  search, Apple catalog, and Global Player.
- **Queue:** the current Sonos queue, with play, remove, refresh, and confirmed
  clear controls.
- **Rooms:** rename, playback sessions, room handoff, all-room mixer, and staged
  grouping.
- **Sound:** EQ and supported speaker, Sub, surround, and home-theater settings.
- **System:** alarms, line-in/TV sources, hardware details, TV Autoplay, and
  device toggles.

## Appearance and behavior

The popup uses Omarchy's native hero, controls, focus states, motion, spacing,
and theme tokens. Its artwork-led Now page, quiet list rows, and fixed bottom
dock automatically follow the current theme. Users can configure layout and
visibility from the command line:

```bash
omarchy bar set io.github.surreptitiousfabric.sonarchy barDisplay "Now playing"
omarchy bar set io.github.surreptitiousfabric.sonarchy maxLabelWidth 260 --json
omarchy bar set io.github.surreptitiousfabric.sonarchy showArtwork false --json
omarchy bar set io.github.surreptitiousfabric.sonarchy enrichRadioArtwork false --json
omarchy bar set io.github.surreptitiousfabric.sonarchy panelWidth 500 --json
omarchy bar set io.github.surreptitiousfabric.sonarchy panelHeight 720 --json
omarchy bar set io.github.surreptitiousfabric.sonarchy volumeStep 3 --json
```

| Setting | Values | Default |
|---|---|---|
| Bar appearance | `Icon only`, `Room`, `Now playing` | `Icon only` |
| Maximum label width | 80–500 px | 220 px |
| Show artwork | true/false | true |
| Find radio track artwork | true/false | true |
| Popup width | 360–620 px | 440 px |
| Popup height | 520–820 px | 660 px |
| Volume step | 1–10 percentage points | 2 |

No downloaded QML, custom theme, or mouse-only settings window is used.

## Apple Music and connected services

Apple search uses Apple's public catalog endpoint. It cannot see a user's
private Apple Music library, recommendations, or personal playlists because
the plugin does not possess the user's private Apple/Sonos authenticated
session. Playing a public result hands its Apple share link to the speaker,
which then uses the Apple Music account already connected in Sonos.

`Play now` starts the selected song. `Album` queues the result's whole album so
Sonos continues to the following tracks. If active TV Autoplay on a
home-theater speaker would immediately replace that queue with TV audio,
Sonarchy explains the conflict and asks the user to turn off **TV Autoplay** in
the System page first; it never changes that preference silently. The default
Apple storefront is Switzerland (`CH`). Set `SONARCHY_APPLE_COUNTRY` to another
two-letter country code before the shell starts to use a different storefront.
The legacy `OMARCHY_SONOS_APPLE_COUNTRY` name remains accepted for local
development upgrades.

When **Find radio track artwork** is enabled and the popup is open, a live
radio track that has no proper album art is looked up using the title and
artist already shown by Sonos. Sonarchy accepts only a strong title-and-artist
match, keeps results only in a bounded in-memory cache, and otherwise retains
the station logo or placeholder. Disable it with the `enrichRadioArtwork`
setting above to prevent these automatic public-catalog lookups. This uses the
same public catalog and never accesses a private Apple library or account.

Global Player and compatible Favorites use services already connected to the
Sonos household. The plugin never receives their passwords or access tokens.

## Security and privacy

There is no HTTP control API and nothing listens on port 8000. The persistent
backend accepts commands only over its private stdin pipe. Sonos event updates
use a callback listener bound to the attached LAN interface on TCP 1400–1499;
it accepts only bounded notifications from the exact private-IP speaker tied
to a live subscription and never accepts playback commands.

See [SECURITY.md](SECURITY.md), [PRIVACY.md](PRIVACY.md), and
[CAPABILITIES.md](CAPABILITIES.md) for the reviewable threat model and declared
marketplace capabilities. See [OFFICIAL_APP_GAPS.md](OFFICIAL_APP_GAPS.md) for
what remains exclusive to, or safer in, the official Sonos app. The complete
keyboard-first walkthrough is in the [user guide](USER_GUIDE.md).

The runtime boundaries and refactoring target are documented in
[ARCHITECTURE.md](ARCHITECTURE.md), with decisions and the persistent protocol
under [`docs/`](docs/).

## Remove

Remove the installed plugin with:

```bash
omarchy plugin remove io.github.surreptitiousfabric.sonarchy
```

Omarchy removes the plugin code and bar entry. It intentionally leaves the
private dependency environment and tiny discovery/state caches so reinstalling
does not redownload packages. A user who also wants those local files removed
can send these exact directories to the desktop trash:

```bash
gio trash "${XDG_DATA_HOME:-$HOME/.local/share}/sonarchy"
gio trash "${XDG_CACHE_HOME:-$HOME/.cache}/sonarchy"
gio trash "${XDG_STATE_HOME:-$HOME/.local/state}/io.github.surreptitiousfabric.sonarchy"
```

Those directories contain no credentials. Empty or missing paths may simply be
skipped by `gio`.

## Development and verification

Runtime dependencies are direct in `requirements.in` and fully pinned with
hashes in `requirements.lock`. Development dependencies use the same policy.
See [CONTRIBUTING.md](CONTRIBUTING.md) for reproducible update and test steps.

The Omarchy validation command is:

```bash
omarchy plugin validate .
```

## Credits and license

The plugin is MIT licensed. Local speaker communication is powered by
[SoCo](https://github.com/SoCo/SoCo), maintained by the SoCo open-source
contributors. Its persistent event backend is derived from OmaSonos 0.2.1 by
ctl0v0 and retains that project's MIT notice. SoCo and OmaSonos do not sponsor
or endorse Sonarchy. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and
[LICENSES/OMASONOS-MIT.txt](LICENSES/OMASONOS-MIT.txt).
