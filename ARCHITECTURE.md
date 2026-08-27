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
| Alarms | safe alarm projection and mutations | raw credential-bearing program metadata in QML |
| Devices | details, capabilities, sound and supported device settings | topology mutation |
| Sources | validated TV and household line-in switching | arbitrary URI playback |
| Artwork | safe URL policy and optional public-catalog enrichment | transport control |
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
Alarms. `domains/capabilities.py` owns bounded positive/nullable source and
device probes. None registers protocol handlers; an AST gate prevents handler
domains from importing one another.

## State and capabilities

Every authoritative snapshot carries a monotonically increasing `revision` for
the lifetime of the backend process. Every command result carries its request
ID and is followed by, or references, an authoritative revision. QML may show a
bounded optimistic value while a request is pending, but a newer snapshot
always wins.

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
