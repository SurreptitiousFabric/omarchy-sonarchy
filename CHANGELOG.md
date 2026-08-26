# Changelog

## Unreleased

- Replaced every one-shot QML command with one canonical versioned persistent
  backend protocol and removed the 1,000-line compatibility bridge.
- Split backend behavior into device, settings, queue, playlist, content,
  alarm, artwork, playback, topology, and mixer domains with narrow ports.
- Split the QML service into a 76-line public facade, cohesive store, protocol
  router, artwork owner, and the single process-owning live protocol client.
- Added exact operation inventory tests, correlated result handling, stable
  capabilities/errors, destructive identity checks, and an 80% coverage gate.
- Gated controls at both page and Store boundaries, projected line-in support
  through bounded, quiet AudioIn probes, and removed model-name-based TV
  visibility.
- Kept background request results from clearing unrelated errors or pending
  mutations, and atomically clears pending UI requests after backend loss.
- Prevented vertical page scrolling over a slider from changing playback,
  room, sound, or alarm values; intentional pointer dragging remains available.

## 4.1.0 — 2026-08-26

- Rebuilt the popup around Omarchy's native hero and themed control states,
  with a larger artwork-led Now view, clearer transport hierarchy, restrained
  list rows, softer surfaces, and short theme-native transitions.
- Replaced the five boxed page buttons with a fixed compact dock below the
  content and made its active page and keyboard cursor visually distinct.
- Extended the custom focus route to Omarchy dropdowns and toggles, including
  room, source, alarm, device, and sleep-timer controls, so the redesign remains
  fully usable without a pointer.
- Changed page and artwork loading to gentle crossfades and made page scrollbars
  appear only when their content needs them.
- Added optional radio-track artwork enrichment through the existing public
  Apple catalogue: strong title-and-artist matches replace the station logo,
  while ambiguous, failed, or missing matches retain the safe fallback.
- Added an exact Classic FM/MyTuner station-art host exception, high-resolution
  Apple covers, a 128-entry memory-only result cache, and explicit privacy and
  security disclosures for automatic lookup while the popup is open.

## 4.0.0 — 2026-08-26

- Renamed the project to Sonarchy with the permanent plugin ID
  `io.github.surreptitiousfabric.sonarchy` and SurreptitiousFabric ownership.
- Added whole-album Apple Music playback so the queue continues beyond the
  selected song, while retaining an explicit single-track action.
- Canonicalized Apple's track-qualified collection links before album
  playback, preventing the Album action from silently queueing one song.
- Detects when active TV Autoplay would immediately take control back from an
  album, gives a precise recovery instruction, and exposes an explicit
  keyboard-controlled TV Autoplay toggle for compatible home-theater rooms.
- Uses authoritative room-name confirmation plus a topology-aware delayed
  refresh, and disables shuffle, repeat, and crossfade when a non-queue source
  would reject them instead of surfacing a predictable UPnP error 712.
- Added safe artwork to Favorites and clearer, dismissible, automatically
  expiring action errors with recovery guidance.
- Moved the keyboard-reachable page navigation below the content viewport, so
  artwork, transport, and volume form one uninterrupted primary-control flow,
  and separated elapsed/total time labels so they cannot run together.
- Added the keyboard-first user guide and prominent SoCo contributor credit.
- Hardened speaker XML parsing with `defusedxml` and regenerated both exact,
  hash-locked dependency sets.
- Expanded the suite to cover every command route and supported mutation, and
  added a regression for post-command TV source takeover plus strict Ruff,
  formatting, branch-coverage, ShellCheck, and CI gates.
- Added an explicit marketplace HOLD checklist separating automated,
  read-only, reversible, audible, recovery, and owner-acceptance evidence.
- Added generated-artifact exclusions so Python, coverage, and test caches do
  not enter a source checkout or marketplace bundle.

## 3.1.0 — 2026-08-26

- Added keyboard-first Sonos Playlist, local-library, alarm, source, device,
  battery, Sub, surround, balance, and TV-sync controls.
- Added safe Play/Next/End queueing, playlist track reorder/removal, queue item
  identity checks, and timed confirmation for destructive UI actions.
- Added a fifth System page and focus-following scroll behavior; every action
  now has a focus/Enter path and numeric sliders have explicit minus/plus paths.
- Restricted public artwork hosts/ports, Apple response size and redirects,
  search lengths, line-in household targets, and persistent protocol size.
- Hardened the Sonos event callback with exact subscription/source checks,
  bounded headers, bodies, pending events, connection concurrency, and socket
  timeouts.
- Hardened the private environment launcher and atomic state/cache writes.
- Added marketplace capability declarations, official-app gap analysis,
  contribution/release guidance, removal instructions, and expanded tests.

## 3.0.0 — 2026-08-25

- Added a persistent event-driven backend with polling fallback.
- Added playback-session switching, safe room handoff, seeking, true group
  volume/mute, an all-room mixer, and staged grouping.
- Expanded Favorites playback for streams, queueable containers, and supported
  TuneIn podcasts.
- Added cached discovery, remembered exact-room selection, automatic reconnect,
  and keyboard controls.
- Added configurable bar text, label width, artwork, popup dimensions, and
  volume step through the Omarchy widget schema.
- Switched to a plugin-managed, hash-locked virtual environment.
- Restricted cached control targets, artwork URLs, and TuneIn fetches; added
  owner-only state.
- Fixed room rename input focus and hidden bonded components appearing as rooms.
- Retained queue, Apple catalog, Global Player, room rename, play modes, sleep,
  EQ, and compatible home-theater controls from version 2.
