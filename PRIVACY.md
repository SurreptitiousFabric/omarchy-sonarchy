# Privacy

The plugin has no telemetry, analytics, advertising, or remote account of its
own.

Its local state cache stores the selected room UID and cached private speaker IP
addresses so startup is fast. Now-playing metadata, room/device details, local music
share paths, alarms, volumes, grouping, Favorites, playlists, and queues are
held in memory while the plugin runs. Alarm service URIs and metadata are not
sent to QML.

External requests occur only for requested or explicitly enabled functionality:

- an Apple catalog search sends the typed query and storefront to Apple's
  public iTunes Search API;
- when **Find radio track artwork** is enabled and the popup is open, the title
  and artist currently supplied by Sonos may be sent to that same public Apple
  API. Only confident artwork matches are used, and positive and negative
  results stay in a bounded memory-only cache for the shell session;
- allowlisted public HTTPS artwork may be loaded from a sanitized URL supplied
  by Sonos or an Apple search result;
- Global Player and TuneIn actions contact those connected services as needed.

The plugin does not receive or store the user's Apple Music, Global Player, or
Sonos account password/token. Private Apple Music library search is therefore
not available.

Automatic radio-art matching can be disabled with the `enrichRadioArtwork`
bar setting. Disabling popup artwork also disables matching.
Speaker-local artwork URLs are checked through a bounded, no-redirect streamed
request before QML receives them. Missing images therefore fall back without
placing a private speaker address in Qt's image-transfer warning output.

The private Python environment contains executable dependencies and runtime/
lock health metadata. There are no analytics identifiers, account
records, browsing-history databases, or cloud backups created by the plugin.

## AI clients and MCP data

Connecting an MCP client gives that client access to Sonarchy's permitted tools.
The stdio adapter and owner-only Unix socket are local transport, not a promise
that the AI model runs locally. A client may send prompts, tool arguments and
results to a remote model/service, or retain them in conversations, tool traces
and diagnostic logs. Sonarchy does not control those destinations, retention,
deletion or training policies. Check the chosen client/provider's settings and
privacy terms before connecting; Sonarchy provides no downstream retention
guarantee.

Depending on the requested tool, arguments and results can include:

| Tool family | Data exposed |
| --- | --- |
| Room listing and exact-room state | Household identifiers; room/group identifiers and names; coordinator/member relationships; online, transport, volume/mute and Line-In availability facts. Identifiers are not anonymous. |
| Content browsing | Requested search text, storefront and navigation context; bounded content identifiers, titles/subtitles, playlist names, counts and artwork URLs. Apple song results also include artist/album, duration and explicitness when available. Local-library results can include share paths and browse breadcrumbs. |
| Playlist preflight and approved results | Exact room/playlist identities, reviewed ordered tracks and metadata, fingerprints, expiry, side effects and bounded verification/failure facts. Playback preflight also exposes queue/item previews, position/source and topology/volume/mute facts. The client sees an opaque plan handle, not the backend ticket. |

The room-snapshot projection omits speaker IP fields. Content browsing uses the
shared browse result, however: artwork locations may contain a private speaker
address, and library shares/content identifiers can reveal local locations.
Bounds and normalized fields are not anonymization or general-purpose redaction.
User/provider-supplied names and metadata can themselves contain sensitive text.
There is no credential-retrieval tool or generic raw SOAP/DIDL/SoCo-object tool;
do not interpret that as a guarantee that every displayed string is non-sensitive.
Private Apple Music library access is not provided; Sonos local-library browsing
is a different, supported source.

Sonarchy's memory-only metadata/plan handling does not prevent an MCP client
from storing its own copies. Short-lived plan handles can appear in a client's
tool display; do not copy handles, backend tickets or raw traffic into reports.

## Read access, consent and disabling MCP

No Sonarchy MCP configuration means read-only access, not disabled access.
Read-only tools can disclose the data above without changing speakers; Sonarchy
does not add a per-read human confirmation dialog. Connect only clients you
trust to use that access and review their own tool-confirmation settings.

The independent `playlist-create` and `playlist-play` opt-ins expose only their
respective writes. They are not standing approval for an individual action.
The client must show the exact plan/side effects, obtain current human approval
and perform the fresh matching preflight described in [MCP setup](docs/mcp.md).
Sonarchy enforces permissions, revalidation and single-use tickets, but
`approved: true` is a client assertion, not independent or cryptographic proof
that a human consented. Creation does not authorize playback.

To disable Sonarchy MCP access, set `enabled = false` in the valid owner-only
`sonarchy/mcp.toml` file under the configuration directory described in
[MCP setup](docs/mcp.md#permissions), then restart both the Quickshell-owned
backend and the MCP adapter. Removing that file restores the read-only default;
it does not disable access. Unreadable/unsafe files or invalid TOML can also fall
back to read-only. To disconnect one client, also remove/disable its
Sonarchy MCP connection. These steps do not erase copies already held by a
client/provider, undo accepted Sonos actions, or remove existing playlists.
