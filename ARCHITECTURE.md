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
| Retained Apple inspection | approved exact-song plans and direct saved-playlist verification | room queues, playback, automatic cleanup, or generic provider commands |
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

`domains/apple_retained_plan.py` owns the short-lived, process-local approval
ticket and binds an exact household anchor, complete Sonos Playlist inventory,
unused name, and ordered reviewed Apple songs. After atomic ticket claim,
`domains/apple_retained_transaction.py` creates one empty saved playlist,
retains its exact create-returned `SQ:<id>`, and verifies each direct addition.
Failures never delete the attributable playlist or successful prefix. The only
provider-specific construction lives in
`infrastructure/apple_saved_queue.py`; it reproduces the pinned SoCo 0.31.2
Apple-song envelope and fails closed on dependency drift. No URI, DIDL, service,
account, or saved-queue field crosses the domain or protocol boundary.

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

The 630-line `domains/apple_retained_transaction.py` also crosses the Python
review trigger. Its single responsibility is the create/add/reopen state
machine and its bounded retained-failure evidence. Token ownership is in
`apple_retained_plan.py`, generic playlist rules and media identity are neutral
helpers, and provider construction is isolated below it in
`infrastructure/apple_saved_queue.py`; splitting the state machine itself would
obscure the no-cleanup and stop-after-first-failure invariants.

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
