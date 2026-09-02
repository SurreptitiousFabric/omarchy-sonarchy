# Changelog

## Unreleased

- Added a single-authority, Quickshell-owned local MCP bridge over an owner-only
  Unix socket, with read-only room/content tools and independently permissioned
  exact Apple-track playlist creation and exact native Sonos Playlist playback.
- Added the narrow first issue #14 slice: read-only exact room/playlist/queue
  preflight plus explicit `playlist-play` permission for append-and-play in one
  online standalone room at volume 20 or below. It accepts only stopped/paused
  queue or no-source state, preserves the existing queue, starts the first
  appended item once, revalidates and verifies authoritative state, never
  retries or rolls back a partial append, and leaves broader issue #14 actions
  open.
- Added read-only exact Apple-song playlist preflight and an explicitly
  approved, single-use-token create-only Sonos Playlist operation. It creates
  an empty saved playlist, adds exact songs directly without reading or
  changing the room queue/playback state, and authoritatively verifies every
  addition and the final order.
- Added one Apple-only saved-queue adapter pinned to SoCo 0.31.2. It reuses
  Apple canonicalisation, constructs escaped DIDL with fixed internal service
  assumptions, exposes no generic execution path, and fails closed on version
  or contract drift.
- Recognize the complete Apple HLS-static resource returned by an authoritative
  saved-playlist browse after direct one-track physical creation. The matcher
  requires the pinned Apple service and protocol shape, rejects query-only or
  other-provider identities, and handles the one observed bounded Sonos album
  display normalization without weakening catalogue identity.
- Record physical acceptance of a second independent one-track Apple item and
  an exact two-item direct Sonos Playlist with preserved order, authoritative
  reopen, unchanged pre-existing playlists, and no queue or playback mutation.
  Also record safe exact-ID cleanup after one different exact item was rejected;
  the undocumented vendor code is not assigned a semantic cause.
- Removed the provisional `save-and-play` mode and all AI playlist dependencies
  on queue backup/restoration. Playback is a separate exact-ID action; issue
  #19 continues to track destructive queue replacement rollback.
- Reserve bounded Sonos Playlist inventory capacity for create verification and
  enforce the 64 KiB UTF-8 protocol limit before publishing a plan ticket.
- Keep the persistent backend alive when authoritative state exceeds that
  protocol limit by emitting a fixed bounded, write-disabled degraded snapshot.
- Bound maximal successful playlist responses by returning full verified
  metadata once with explicit false queue/playback mutation flags.
- Require a create-returned new `SQ:<id>` plus authoritative exact-ID/title
  resolution before partial cleanup; cleanup never guesses from title.
- Keep pre-claim playlist execution rejections from advancing backend revision,
  and require Apple identity evidence to use complete canonical or expected
  Sonos item/resource tokens rather than arbitrary metadata substrings.
- Replaced every one-shot QML command with one canonical versioned persistent
  backend protocol and removed the 1,000-line compatibility bridge.
- Split backend behavior into device, settings, queue, playlist, content,
  alarm, artwork, playback, topology, and mixer domains with narrow ports.
- Moved cross-domain metadata, identity, lookup, and device-capability helpers
  into neutral support modules and enforce that handler domains never import
  one another's private implementation.
- Split the QML service into a 76-line public facade, cohesive store, protocol
  router, artwork owner, and the single process-owning live protocol client.
- Added exact operation inventory tests, correlated result handling, stable
  capabilities/errors, destructive identity checks, and an overall 80%
  branch-coverage target alongside the checked-in automated gate.
- Gated controls at both page and Store boundaries, projected line-in support
  through bounded, quiet AudioIn probes, and removed model-name-based TV
  visibility.
- Kept background request results from clearing unrelated errors or pending
  mutations, and atomically clears pending UI requests after backend loss.
- Correlated Store request errors with their owning request so successful
  details, content, or alarm reads cannot erase or overwrite an unrelated
  action failure.
- Pinned ShellCheck through Mise and aligned CI with the documented syntax and
  lint gates for both the backend launcher and QML component-test runner.
- Corrected an invalid YAML command scalar that caused GitHub Actions to reject
  the workflow before creating any jobs.
- Updated the immutable Mise action pin to v4.3.0 so CI runs natively on the
  current GitHub Actions Node.js 24 runtime.
- Preflighted allowlisted speaker-local artwork through a bounded in-memory
  availability cache so stale 404 URLs fall back before Qt can log a private
  speaker address.
- Prevented vertical page scrolling over a slider from changing playback,
  room, sound, or alarm values; a headless real-event test now proves the page
  scrolls without a slider mutation and intentional pointer dragging remains
  available.
- Added hierarchical, paged local-library browsing from speaker-discovered
  root categories, with authoritative breadcrumbs, keyboard-reachable folder
  and paging controls, and stale path/index/identity checks before nested
  playback.
- Extracted content request, navigation, and paging state into a focused QML
  component so the public facade and main Store stay below their architecture
  guardrails while late results remain correlated to room, source, search,
  path, and page.
- Made Play now insert directly after the current track, retained explicit Next
  and End actions, and added a two-step Replace queue control with bounded
  preflight backup and best-effort restoration after speaker rejection.
- Added active-household room selection to alarm creation and editing, with
  backend household validation and full cached-field restoration when Sonos
  rejects an existing-alarm update.
- Added quiet read-only TV audio format reporting for compatible soundbars,
  preserving active, idle, unavailable, unknown, and unsupported states, and
  extracted a shared Omarchy-themed information row to keep the System page
  within its 800-line health guard.
- Extracted the alarm draft, validation, room/program options, and exact save
  projection into a directly runtime-tested model beneath the Omarchy-themed
  form, leaving the System page as a 518-line composition layer and enforcing
  each component's size and ownership gates.
- Promoted the current Sonos queue from a buried Browse source to a dedicated
  keyboard-accessible Queue tab with refresh, play, identity-checked removal,
  confirmed clear, active-item highlighting, and no duplicated backend state.
- Expanded public Apple Music search into bounded Artists, Albums, and Songs
  sections. Artist results open balanced album/song views, albums open their
  tracks, Back preserves catalogue history, and album/track playback retain
  their existing capability-gated paths.
- Added a Global Player compatibility retry that preserves the original query
  first and retries provider-friendly capitalization only after an empty
  result, so searches such as `classic fm` do not depend on title case.
- Fixed Apple artist/album arrows falling through to single-track playback by
  explicitly qualifying the delegate row, centralizing browse-before-play
  activation in the Store, and rejecting browsable rows at the playback gate.
- Added per-room volume and mute controls directly beneath Group Volume on the
  Now page. Now and the all-room mixer share one Omarchy-themed row that reads
  authoritative room volume/mute values instead of the active group aggregate.
- Allowed slow speaker-local artwork responses up to five seconds while
  retaining the short connection timeout and existing image validation.
- Added current-queue reordering through a dedicated drag handle, focusable
  move buttons, and row-scoped Alt+Up/Alt+Down shortcuts. Moves revalidate both
  source and destination identities before the queue domain calls Sonos.

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
