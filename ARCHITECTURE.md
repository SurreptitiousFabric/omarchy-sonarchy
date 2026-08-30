# Architecture

Sonarchy is a local Sonos controller for the Omarchy shell. It is not a generic
audio router, Bluetooth manager, AirPlay sender, Sonos account client, or
firmware/setup tool. The product boundary is recorded in
[`docs/adr/0001-sonos-only-single-backend.md`](docs/adr/0001-sonos-only-single-backend.md).

## Target runtime

The target runtime has one supervised Python process and one versioned JSON-line
protocol over its private stdin/stdout pipes:

```text
QML pages -> QML store -> protocol -> application services -> SoCo adapter
                              |                  |
                              |                  +-> state/cache
                              +-> snapshots/events
```

QML owns presentation state: focus, open pages, editor drafts, pending request
labels, and bounded optimistic display values. Python owns discovery, speaker
state, validation, authorization-by-capability, command execution, caches,
retries, and error classification. A QML page never launches Python, constructs
a CLI argument list, parses backend stderr, or infers device support from model
names.

The former one-shot compatibility bridge has been removed. New behavior must
be implemented in a domain service and exposed through the persistent protocol;
QML must not add subprocess-based command paths.

`Service.qml` is the stable page-facing facade. `SonarchyStore.qml` owns the
compatibility view model and user actions, `SonarchyProtocolRouter.qml` owns
correlated results and timers, `SonarchyArtwork.qml` owns bounded artwork state
and URL policy, and `LiveService.qml` alone owns the backend process/protocol.
`SonarchyAlarmDraft.qml` owns the alarm draft, authoritative room and program
options, input validation, and exact save projection. `SonarchyAlarmEditor.qml`
is the visual form over that model; `SonarchySystemPage.qml` composes it with
the saved-alarm list and read-only device/source sections.
`SonarchyQueuePage.qml` is the dedicated current-queue presentation; it consumes
the Store's authoritative content projection and capability-gated actions and
does not own a second queue model or protocol path.
`SonarchyRoomVolumeRow.qml` is the shared authoritative per-room volume/mute
control used by the current-group Now view and the all-room mixer; pages do not
reimplement its room-field selection or action routing.

## Omarchy visual language

The bar and popup use Omarchy's public `qs.Ui` and `qs.Commons` primitives:
`WidgetButton`, `KeyboardPanel`, `PanelHero`, `PanelSeparator`,
`PanelSectionHeader`, `PanelSlider`, `Button`, `Dropdown`, `Toggle`,
`BorderSurface`, `OpticalGlyph`, `Style`, `Color`, and `Border`. Geometry and
typography come from `Style`; surfaces and state colors come from the active
theme. Product-specific components may compose these primitives, but must not
introduce fixed fonts, hard-coded colors, platform-native control chrome, or
debug overlays.

## Domain ownership

| Domain | Owns | Must not own |
|---|---|---|
| Discovery | cached-host probes, SSDP, bounded attached-network fallback | playback or UI selection |
| Topology | households, visible rooms, groups, coordinators, membership changes | content browsing |
| Playback | transport, seek, play modes, sleep, handoff | discovery or alarms |
| Content | normalized browse/search results and provider routing | QML formatting or device settings |
| Queue | queue reads and identity-checked mutations | playlists |
| Playlists | Sonos Playlist reads and identity-checked mutations | current queue |
| Apple playlist plans | exact reviewed song validation, short-lived tickets, and create-only Sonos Playlist orchestration | AI song selection, private Apple libraries, or generic URI execution |
| Alarms | safe alarm projection and mutations | raw credential-bearing program metadata in QML |
| Devices | details, capabilities, sound and supported device settings | topology mutation |
| Sources | validated TV and household line-in switching | arbitrary URI playback |
| Artwork | safe URL policy, bounded speaker-image availability probes, and optional public-catalog enrichment | transport control |
| State | selected room, cached hosts, state revision and atomic persistence | network calls |

External catalogs are adapters beneath Content. SoCo is an infrastructure
adapter beneath the domains. Neither may leak library-specific objects into the
protocol model.

`SonosController` is the stable composition root for those services. Its
implementation is separated by infrastructure responsibility: discovery,
snapshot projection, favorites, topology convergence, playback/handoff, and
thin domain delegation. The mixins are internal and do not widen the protocol
or expose SoCo objects.

## Dependency direction

Dependencies point inward:

1. QML pages depend on the QML store and reusable controls.
2. The QML store depends only on the protocol schema.
3. Protocol handlers depend on application/domain services.
4. Domain services depend on narrow ports for SoCo, HTTP, time and persistence.
5. Infrastructure adapters implement those ports.

Domain modules may share immutable protocol models and validation helpers. They
must not import QML concepts, subprocess launchers, or another domain's private
implementation.

`domains/common.py` owns neutral value normalization, safe optional reads, and
single-read coordinator selection. `domains/media.py` owns stable item identity
checks and provider-item lookup shared by Browse, Content, Queue, Playlists, and
Alarms. `domains/library.py` owns bounded library path/page validation,
authoritative container resolution, and nested item identity checks shared by
Browse and Queue. `domains/capabilities.py` owns bounded positive/nullable
source and device probes. None registers protocol handlers; an AST gate
prevents handler domains from importing one another.

`domains/apple_browse.py` owns the public Apple catalogue's normalized artist,
album, and song views plus bounded concurrent provider reads. The HTTP adapter
in `apple_catalog.py` owns request limits, response bounds, identifier and URL
validation. QML receives only provider-neutral browse items and keeps a small
presentation-only Back history.

`domains/browse_bounds.py` is the browse wire-budget boundary. It removes
control characters and byte-bounds display-only text at Unicode boundaries,
keeps artwork whole or empty, and never shortens an actionable identity. It
then measures the complete worst-case result envelope and removes only a
deterministic item suffix until the line fits. The provider total remains
authoritative while explicit returned-count and truncation fields tell QML
whether the page is an exact prefix. The protocol emitter remains the final
fail-closed boundary for unexpected oversized responses.

Library results also expose an authoritative `next_offset` based on provider
positions consumed by the emitted prefix, without redefining the requested
page size. QML keeps a bounded history of exact prior offsets for Previous and
uses only `next_offset` for Next. That history survives a same-page refresh but
resets when the room, content kind, search, or library path changes.

Opaque browse and navigation IDs have a separate 512-byte UTF-8 bound, Apple
action URLs retain their existing 1,024-byte contract, and `SQ:<id>` values
have a 32-byte bound. An over-limit identity is never truncated: its item is
omitted as one consumed provider position, while aggregate-only suffix removal
does not consume the removed positions. Breadcrumb and path identities are
projected together as the same exact safe prefix.

`domains/apple_playlist_plan.py` owns bounded reviewed values and the
process-local ticket lifecycle. Its read-only validation and write execution
are separate services sharing one in-memory store. `apple_catalog.py` owns the
narrow pinned-SoCo song canonicalisation adapter.
The create service declares a conditional mutation boundary: protocol errors
before atomic ticket claim do not cause a state refresh or revision increment.
The token does not bind the general snapshot revision because unchanged polls
advance it; the transaction instead re-captures and compares every material
room/household, capability, name, and playlist-inventory fact. Create-only does
not refresh the general playback
snapshot after execution because the verified result is complete and a refresh
would perform irrelevant queue, transport, volume, and mute reads.
`domains/apple_playlist_transaction.py` owns the room/household anchor,
playlist-inventory freshness, exact-ID creation ownership, ordered addition,
and authoritative reopen verification. It has no dependency on queue backup or
restoration. Ordinary destructive queue replacement remains unchanged and its
broader replay defect is tracked separately by issue #19.

The transaction creates a Sonos Playlist directly; it never constructs tracks
in a room's playback queue. SoCo's normal `create_sonos_playlist()` creates the
empty saved queue and immediately returns its candidate `SQ:<id>`. The private
`infrastructure/apple_saved_queue.py` adapter then appends one already validated
Apple song at a time with `AddURIToSavedQueue`. That adapter accepts no generic
URI or DIDL input. It re-runs `AppleMusicShare` canonicalisation, fixes the
Apple song key, class, service descriptor, append index, and account sequence,
and serializes reviewed title/artist/album text with SoCo DIDL data structures
and ElementTree escaping. It fails closed unless SoCo is exactly 0.31.2 and the
pinned Apple service assumptions still match.

After creation and every add, the transaction reopens the exact `SQ:<id>` with
a three-attempt bounded visibility policy. It verifies expected count, exact
new position, canonical Apple identity, and reviewed title, artist, and album.
Final verification repeats the complete ordered comparison and confirms the
pre-existing playlist inventory is unchanged. Catalogue canonicalisation is
reported honestly as identity validation only; household Sonos acceptance
remains `unproven_until_create`.

A one-track physical create showed that saved-playlist browse can rewrite the
ShareLink input into a queue-local `DidlMusicTrack` with one Apple HLS-static
resource. The private adapter now owns recognition of that exact pinned
representation: complete song token, Apple service identity derived from the
pinned service type, bounded saved-resource fields, and exact HLS protocol
type. The domain still rejects conflicting identities, other providers,
unanchored substrings, and IDs found only in query text. Sonos also returned a
punctuation-normalized album plus its literal `(Deluxe Edition)` display
qualifier. That one bounded display normalization is accepted only after exact
catalogue identity, title, and artist verification; other album names or
edition labels remain failures.

Subsequent physical acceptance created a second independent one-track playlist
and one exact two-track playlist. The two-track result preserved approved
canonical order and supporting metadata through final authoritative reopen,
while every pre-existing playlist remained unchanged and queue/playback
mutation flags remained false. A different exact Apple item was rejected with
an undocumented vendor code and its attributable partial playlist was removed
through the same exact-ID cleanup boundary. These results validate the
architecture for the tested one- and two-item cases, not universal catalogue
acceptance or general queue restoration; issue #19 remains separate.

Failure diagnostics identify `create`, `add_track`, `verify_track`,
`verify_playlist`, or `cleanup`. Track failures may include only the reviewed
position/identity and a validated `SoCoUPnPException.error_code`; exception
text is never parsed. Cleanup is attempted once only after the create-returned
ID is validated as new and that exact ID authoritatively resolves to the
invocation-bound title. Title alone never establishes ownership and no second
deletion candidate is guessed. A cleanup failure returns the exact attributable
partial ID and leaves every unrelated playlist untouched.

Preflight reserves one slot below the 100-item bounded playlist inventory;
post-create verification and cleanup allow one transaction-scoped extra. The
shared protocol serializer emits UTF-8 JSON and the plan service measures the
complete worst-request-ID result envelope before publishing its ticket.
Authoritative snapshots are measured as complete protocol lines too. An
oversized snapshot is never cached or emitted; the persistent process emits a
fixed bounded degraded snapshot with no target-derived write capabilities and
continues serving startup, polling, and post-mutation traffic.
Successful playlist results project bounded reviewed metadata once under the
authoritatively reopened playlist plus explicit `queueMutation: false` and
`playbackMutation: false`. Raw provider metadata and optional Sonos item IDs
are not exposed.
Apple identity extraction accepts only complete canonical or pinned Sonos item
identifiers, the leading token of an expected `x-sonos-http:` or
`x-sonos-https:` resource, or the complete pinned Apple HLS-static saved-item
resource form. It never searches arbitrary metadata substrings or query
parameters.

## AI and MCP boundary

The deterministic protocol operations are implemented inside the existing
persistent application path. Issue #11 has not yet accepted a process-owner,
transport, or concurrency design for MCP, so this repository does not start a
second controller and does not currently expose an external MCP server. A
future adapter must remain thin, consume these operations through the accepted
single owner, require exact room UIDs and explicit write approval, and remove
write tools entirely in read-only configuration. It must not add generic
protocol, SoCo, UPnP, command, URL, or URI passthrough.

## State and capabilities

Every authoritative snapshot carries a monotonically increasing `revision` for
the lifetime of the backend process. Every command result carries its request
ID and is followed by, or references, an authoritative revision. QML may show a
bounded optimistic value while a request is pending, but a newer snapshot
always wins.

Request errors carry the ID of the request that produced them. A successful
background read may clear only its own error; it cannot erase a foreground
action failure or local validation error. An unrelated background failure also
cannot replace an error already being shown. Explicit user dismissal and
foreground failures may replace or clear the current error regardless of owner.
Local validation and Favorites snapshot state use stable owner keys so their
retries can update only their own prior errors without colliding with each other.

Every snapshot exposes a canonical set of positive action capabilities such as
`playback.seek`, `queue.item.remove`, `topology.members.set`, and
`sound.setting.set`. Device-specific settings use nullable backend projections,
content items expose `playable`, and rooms expose a bounded, positively probed
`lineInAvailable` flag. Pages render or disable controls from those projections
instead of relying on speaker model names or predictable command failures.

## Error model

Backend failures have a stable machine code, a safe user message, retryability,
and optional operation context. Raw exceptions, private addresses, service
metadata, and credentials never cross the protocol. The initial codes are:

- `invalid_request`
- `unsupported_operation`
- `invalid_argument`
- `not_connected`
- `not_found`
- `conflict`
- `speaker_rejected`
- `network_error`
- `internal_error`

## File-size guardrails

Line count is a diagnostic, not an objective. A production module over roughly
600 lines receives a responsibility review; a file over 800 lines requires an
architecture note explaining why further separation would worsen cohesion.
`Service.qml` remains a thin public facade below 350 lines. Each internal QML
service component remains below 800 lines and has one named responsibility.

Current reviewed QML modules above the 600-line trigger are:

| Module | Reviewed responsibility | Existing separation boundary |
|---|---|---|
| `SonarchyStore.qml` | Page-facing state projection and capability-gated user actions | Content navigation, artwork, protocol routing, and process ownership are separate components |
| `SonarchyBrowsePage.qml` | Browse/search presentation and keyboard interaction | Requests, authoritative results, validation, and mutations remain in the Store/backend |
| `BarWidget.qml` | Root bar/popup composition and shared spatial focus routing | Pages, navigation, reusable controls, state, and backend protocol ownership remain separate |

## Verification gates

- One persistent backend process and no one-shot `Process` in `Service.qml`.
- Every operation is present in the protocol inventory and contract tests.
- No QML Python command arrays or backend stderr parsing.
- Domain tests cover success, invalid input, expected failure and recovery.
- Destructive and topology-sensitive paths reach at least 90% branch coverage;
  overall branch coverage remains at least 80%.
- Omarchy validation, Python/QML static checks, installation, hot reload,
  real-event shared-control tests, degraded network behavior, and the
  documented Sonos acceptance suite pass.
