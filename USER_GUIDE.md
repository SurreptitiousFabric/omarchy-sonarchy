# Sonarchy user guide

Sonarchy is a keyboard-first Sonos controller for the Omarchy bar. It controls
speakers on the same local network and follows the active Omarchy theme. It
does not replace the official Sonos app for speaker setup, account management,
Wi-Fi changes, Trueplay, or adding music services.

## Open and navigate

Open or close Sonarchy from a terminal or an Omarchy keybinding:

```bash
omarchy-shell shell toggle io.github.surreptitiousfabric.sonarchy '{}'
```

Inside the popup:

| Key | Action |
|---|---|
| `Tab` / `Shift+Tab` | Move through every control |
| `Up` / `Down` or `J` / `K` | Move to the previous or next control |
| `Enter` or `Space` | Use the focused control |
| `Left` / `Right` or `H` / `L` | Lower/raise group volume, or move within the focused page dock |
| `N` / `P` | Next or previous track |
| `M` | Mute or unmute the selected group |
| `S` | Stop |
| `R` | Refresh |
| `1`–`6` | Open Now, Browse, Queue, Rooms, Sound, or System |
| `Escape` | Leave a field or dropdown, then close the popup |

Everything has a keyboard path. Sliders also have focusable minus and plus
buttons, so a pointer is never required.

The six-page dock stays below the current page. Focus it with `J`, `K`, or
`Tab`, move across it with `H`/`L` or the arrow keys, and press `Enter` to
switch. The number keys remain the fastest direct route.

## Choose what you are controlling

The room dropdown at the top selects an exact room. If that room belongs to a
group, playback and group-volume controls affect its whole group. Room-specific
volume, mute, naming, and supported speaker settings still target the exact
room shown.

The header shows the selected room, the number of visible rooms, and the
current playback state. The refresh button asks the speakers for fresh state.

## Now page

The Now page shows the current title, artist, album, artwork, progress, and
playback state. It provides:

- previous, play/pause, stop, and next;
- seek back or forward by ten seconds when the source supports seeking;
- whole-group volume/mute plus separate volume and mute controls for every room
  in the current group;
- group volume and mute;
- shuffle, repeat, and crossfade where supported; and
- a sleep timer.

For live radio, Sonarchy first shows safe artwork supplied by the speaker,
usually the station logo. While the popup is open, **Find radio track artwork**
can use the displayed title and artist to request a public Apple catalogue
match. A strong match replaces the logo with album artwork; weak, conflicting,
missing, or failed matches quietly keep the station logo or placeholder. The
bounded cache lasts only for the current shell session.

Live radio, TV, line-in, and some protected services may not support seeking,
previous/next, or play modes. Shuffle, repeat, and crossfade remain disabled
unless the Sonos queue is the active transport, even if the speaker still
reports readable values left over from an earlier queue. Sonarchy leaves other
unsupported actions disabled when Sonos reports that information in advance;
otherwise the speaker may return a short, recoverable error.

## Browse page

Use the Browse selector to choose a source:

- **Sonos Favorites:** saved items reported by the household. Artwork appears
  when the favourite supplies a safe speaker-local or approved media URL.
- **Sonos playlists:** create a playlist, save the current queue, play/delete a
  playlist, and move or remove its tracks.
- **Local music library:** browse the categories and folders actually reported
  by Sonos, including available artist, album-artist, album, genre, composer,
  track, share, and imported-playlist views; search indexed tracks; or request
  a re-index. **Back** returns to the parent folder, and arrow buttons page
  through lists longer than 40 results. Folder and playback actions appear
  only when the backend verifies that the selected item supports them.
- **Apple Music catalog:** search Apple's public catalog across Artists,
  Albums, and Songs. Open an artist to see a balanced list of their albums and
  songs; open an album to see its tracks; use **Back** to return to the prior
  result. Playback uses the Apple Music account already connected to the Sonos
  household. **Play now** starts only the selected song; **Album** queues the
  album container and starts at its first track so playback continues through
  the remaining songs while the Sonos queue remains the active source.
- **Global Player:** search the Global Player service already connected to the
  Sonos household. Search is not case-sensitive; when the provider rejects an
  all-lowercase query, Sonarchy retries a human-friendly capitalization.

Apple catalog search cannot see a private Apple Music library, personal
playlists, listening history, or recommendations. Sonarchy never receives the
user's Apple, Global Player, or Sonos password or service token.

On a home-theater speaker, Sonos can replace music with TV audio whenever TV
Autoplay is enabled and the TV is sending sound. If that combination is active,
Sonarchy warns and stops before adding another copy of the album. Select the
home-theater room, open **System → Device information**, turn off **TV
Autoplay**, then choose **Album** again. This changes a real speaker preference;
Sonarchy never disables it automatically.

Queue clearing, playlist deletion, playlist-track removal, and similar
destructive actions ask for the same focused action twice within five seconds.
The second press is the confirmation; doing nothing lets it expire.

Library navigation is revalidated against the speaker on every request. If the
Sonos index changes while a folder or page is open, Sonarchy asks you to return
to the library root or refresh instead of opening or playing a different item.

## AI-curated Sonos Playlists

Sonarchy's persistent backend can accept a reviewed ordered plan of one to 25
exact Apple catalogue songs and persist it as a new Sonos Playlist. This is a
protocol and local MCP capability for an integrated local AI client; there is
no QML authoring form.

Each reviewed song includes its exact Apple catalogue ID and copied
`https://music.apple.com/...` song link plus bounded title, artist, album, and
duration evidence. Sonarchy validates the link independently through its Apple
URL policy and pinned SoCo integration. It never creates a link from a title or
ID, searches for a substitute, or accepts an album/playlist/artist link as one
song.

The read-only preflight shows the exact room/coordinator anchor, a hashed
household identity, complete Sonos Playlist inventory fingerprint and count,
new playlist name, ordered songs, total known duration, and expected side
effects. It states both `catalogueIdentityValidated: true` and
`sonosAcceptance: unproven_until_create`. It returns a memory-only single-use
token valid for no more than two minutes. The token is a freshness ticket, not
approval; the client must still request explicit approval immediately before
creation. A backend restart or material playlist/anchor change requires a new
preflight.

Creation is save-only. Sonarchy creates a new empty Sonos Playlist, adds the
reviewed Apple songs directly to that saved playlist, and authoritatively
reopens it after every addition and at completion. It does not read or change
the current room queue, source, position, transport, volume, mute, or topology,
and it never starts playback.

Existing exact-name Sonos Playlists are never overwritten. A failed track is
never retried or silently substituted. Failure cleanup targets only the exact
new `SQ:<id>` returned by this invocation after that ID is proven new and
reopens with the invocation-bound title. If exact cleanup cannot be verified,
the result returns that attributable partial ID and requests later reviewed
cleanup; every unrelated playlist is left untouched.

Playback is a separate exact-ID action after creation. With the independent
`playlist-play` MCP permission, Sonarchy can review one existing exact
`SQ:<id>` for one exact room UID, obtain separate approval, repeat an identical
fresh preflight, append that complete playlist to the existing room queue, and
start its first appended item.

This first playback slice accepts only online standalone rooms at volume 20 or
below. Transport must be stopped or paused and source must be confirmed as the
Sonos queue or no active source. The playlist must contain 1–25 completely
readable items and the complete queue plus playlist may contain at most 100.
All existing queue entries remain; playback moves away from the paused/stopped
context. Volume, mute, topology, source settings, and playlist contents remain
unchanged. There is no automatic retry. If append succeeds but playback start
or verification fails, appended entries may remain and Sonarchy will report
the partial state without clearing, rebuilding, removing, or rolling back the
queue. Broader issue #14 actions and issue #19 rollback remain deferred.

A native Apple Music playlist is a separate optional **Export/Copy**, not the
normal persistence target and not a synchronized object. See
[`docs/ai-curated-sonos-playlists.md`](docs/ai-curated-sonos-playlists.md) for
the complete current workflow, MCP status, and Apple export limitations.

## Queue page

The dedicated Queue page shows the current Sonos queue for the selected room.
The active item is highlighted. You can play an exact item, remove it after a
second confirmation, refresh the list, or clear the whole queue after a second
confirmation. Queue actions re-check the item identity so a stale list cannot
silently act on a different track.

## Rooms page

### Rename a room

Focus the room-name field, type the new name, and press `Enter`, or focus
**Rename** and press `Enter`. This changes the real Sonos room name, so it also
changes in the official app. Sonarchy confirms the new name directly with the
speaker and keeps it visible while Sonos's household-topology cache catches up,
which can take several seconds.

### Select or move playback

**Playback sessions** chooses which independent Sonos stream to control without
moving audio. **Move playback** hands the current stream to a safe standalone
room when Sonos can preserve it. Sonarchy blocks moves that would silently tear
apart another group; change the group first when that happens.

### Mix and group rooms

The all-room mixer changes each room's own volume or mute state. Group settings
are staged: select the wanted rooms, review them, then press **Apply** once.
Nothing changes while the selection is only staged.

## Sound page

Controls appear only when the selected product reports support. Depending on
the speaker, Sonarchy can change bass, treble, loudness, balance, night mode,
speech enhancement, Sub enable/gain/crossover, surrounds, surround TV/music
levels, surround mode, and TV audio delay.

These settings affect real speaker configuration. If a bonded component does
not expose a stable local control, Sonarchy does not invent one.

## System page

The System page provides:

- alarm listing, creation, editing, enable/disable, and deletion;
- Chime or a verified Sonos Favorite as an alarm sound;
- line-in and TV source switching when supported;
- model, software, hardware, battery, microphone, voice, and source details;
  and
- TV Autoplay on compatible home-theater speakers, plus status light,
  touch-button, and existing Trueplay-profile toggles when the selected product
  exposes them.

Use the official Sonos app to add products, configure Wi-Fi, transfer
ownership, add/remove services, run Trueplay tuning, bond Subs or surrounds,
configure voice assistants, perform TV setup, or contact Sonos support.

## Errors and how they clear

| What appears | What it means | What to do | How it clears |
|---|---|---|---|
| Red action message | One command was refused or could not reach the speaker | Read the instruction and retry if appropriate | A successful/new action, **Dismiss**, refresh, or ten seconds |
| Sonos error 701 | The requested transition is not valid in the speaker's current playback state | Wait briefly; refresh or choose another track/source, then retry | Same as a red action message |
| Play modes unavailable / Sonos error 712 | Shuffle, repeat, or crossfade was requested while radio, TV, line-in, or another non-queue source was active | Choose and play a queued track first | The controls enable automatically when the Sonos queue becomes active; an old error clears normally |
| Nothing to play / unsupported format / unavailable item | The queue is empty, the source cannot do that operation, or saved content changed | Choose another item or refresh its list | A new successful action, **Dismiss**, or ten seconds |
| TV Autoplay is active | The album link is valid, but the home-theater speaker would immediately replace music with TV audio | Select the home-theater room, open **System → Device information**, turn off **TV Autoplay**, then choose the album again | A successful action, **Dismiss**, refresh, or ten seconds |
| No Sonos rooms found | Discovery has no reachable room | Check that PC and speakers are on the same non-guest LAN; then choose **Search again** | Automatically when a room is discovered |
| Backend stopped | The private controller process exited | Wait for automatic restart; use refresh if it does not recover | Automatically after a healthy snapshot |
| Setup/dependency error | The private Python environment could not be created or verified | Check the shown instruction and network, then press refresh | After a successful retry; it may also be dismissed while troubleshooting |
| Cached/stale playback | A refresh failed after earlier good state was known | Check the network and refresh; displayed playback may be old | Automatically after a healthy speaker response |
| “Press the same focused action again” | Safety confirmation, not a failure | Press the same action again only if the destructive change is intended | Second press, a different choice, or five seconds |

Low-level details remain in the Omarchy Shell logs for maintainers, while the
popup translates common UPnP errors into a short recovery instruction. A
dismissed message does not claim that an underlying network/setup problem has
been fixed; refresh is the recovery test.

## Appearance

Sonarchy uses Omarchy's native hero, controls, focus states, motion, and the
current foreground, accent, surface, border, spacing, font, and urgency tokens.
The artwork-led Now page, restrained list rows, and bottom dock therefore adapt
with the rest of the shell. Configure layout from the command line:

```bash
omarchy bar set io.github.surreptitiousfabric.sonarchy barDisplay "Now playing"
omarchy bar set io.github.surreptitiousfabric.sonarchy maxLabelWidth 260 --json
omarchy bar set io.github.surreptitiousfabric.sonarchy showArtwork false --json
omarchy bar set io.github.surreptitiousfabric.sonarchy enrichRadioArtwork false --json
omarchy bar set io.github.surreptitiousfabric.sonarchy panelWidth 500 --json
omarchy bar set io.github.surreptitiousfabric.sonarchy panelHeight 720 --json
omarchy bar set io.github.surreptitiousfabric.sonarchy volumeStep 3 --json
```

The icon remains the current bar theme colour. Sonarchy does not download a
theme or open a pointer-only settings window.

`enrichRadioArtwork` defaults to `true`. Turn it off to prevent automatic
title-and-artist lookups against Apple's public catalogue. Turning off
`showArtwork` also disables those lookups.

## Privacy and security

Sonarchy is LAN-only. It has no browser UI, cloud account login, or HTTP control
API on port 8000. The persistent backend accepts commands only through its
private stdin pipe. Its Sonos event listener accepts bounded notifications only
from the exact private-LAN speaker attached to a live subscription.

See [SECURITY.md](SECURITY.md), [PRIVACY.md](PRIVACY.md), and
[CAPABILITIES.md](CAPABILITIES.md) for the reviewable details.

## Project and credits

Sonarchy is an independent community project and is not made, sponsored, or
endorsed by Sonos, Inc.

Local speaker communication is powered by
[SoCo](https://github.com/SoCo/SoCo), maintained by the SoCo open-source
contributors. Sonarchy is grateful for their long-running work documenting and
implementing the local Sonos interfaces. SoCo does not sponsor or endorse this
plugin.

The event backend is derived from
[OmaSonos](https://github.com/ctl0v0/omasonos) by ctl0v0 under the MIT License.
Full notices and dependency licences are in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
## Codex and local MCP

See [`docs/mcp.md`](docs/mcp.md) for read-only setup, independent optional
`playlist-create` and `playlist-play` permissions, exact tools, fresh-preflight
consent flows, restart behavior, and safe diagnostics. Playlist creation never
starts playback or alters a room queue. Exact playlist playback is limited to
the standalone-room append-and-play slice above; general transport, queue,
volume, grouping, and source actions are not exposed through MCP.
