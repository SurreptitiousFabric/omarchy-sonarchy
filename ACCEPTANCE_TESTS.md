# Sonarchy release acceptance

**Marketplace status: HOLD**

**Status reporting:** read the [reconciled acceptance matrix](docs/acceptance-status.md)
first (updated 2026-09-08). Unchecked composite criteria below retain historical
requirements; they do not mean every constituent action is untested. Report only
the remaining subcase. Missing evidence is not proof a test was never performed.

Sonarchy must not be published or submitted merely because its automated tests
pass. Marketplace release requires every applicable check below, a reviewed
exact release commit, and explicit owner sign-off. A feature unsupported by the
test household may be marked `not applicable` only with the product limitation
recorded; it must not be called tested.

## Recorded local gates and historical checks

Historical observations below are retained from the
[acceptance record at `e116f898`](https://github.com/SurreptitiousFabric/omarchy-sonarchy/blob/e116f89817d6fc4aa500ceca5a29bb1e0c7e6ee2/ACCEPTANCE_TESTS.md)
unless a later exact case is cited. They are not claims of a new run or of
acceptance on an unspecified release candidate. The required real-device and
final release checklists remain separate and retain their untested criteria.

The later [PR #81 CI run](https://github.com/SurreptitiousFabric/omarchy-sonarchy/actions/runs/34097548397)
passed for head `55bc4870e1a2fd9c9a1d32b7d434f453b31769f6` on both declared
Python targets, including the locked-runtime advisory audit. That immutable
run is automated evidence, not Omarchy release-host or physical acceptance.

- [x] The complete automated Python suite passes under the checked-in branch
  coverage gate, and the complete headless QML component suite passes.
- [x] Repository-wide Ruff, formatting, compilation, JSON, Bash/ShellCheck,
  protocol and security checks pass in the cited automated evidence.
- [ ] Baseline-aware all-shipped-QML validation on the exact clean Omarchy release
  candidate. The [recorded #64 report](https://github.com/SurreptitiousFabric/omarchy-sonarchy/issues/64#issuecomment-5566579718)
  for `cd2518d498ebbc6918c8449781aed8c6ebc23e46` passed manifest/component
  checks but failed the former zero-warning QML lint gate. Owner amendment on
  2026-09-08 removes zero warnings as a requirement: the 117 documented upstream
  metadata warnings are allowed by the reviewed baseline; new warnings and errors
  still fail. Current local lint passes with 117 accepted / zero unexpected
  diagnostics. Final clean exact-candidate validation remains required. Generic Python CI and
  offscreen component tests do not satisfy this gate.
- [x] Headless real-event QML tests load Omarchy's installed `PanelSlider`,
  prove wheel input scrolls without a slider mutation, preserve intentional
  dragging, test request-owned result-driven clearing, and cover content root,
  nested, paging, Back, Favorites, and Apple artist/album history transitions.
  That focused ownership test does not disable or test away the production
  request/transient-error timers: both dismiss messages after ten seconds.
- [x] The marketplace v3 deterministic baseline reports no findings and only
  the disclosed, non-blocking `package-manager` review capability.
- [x] Exact locked runtime versions passed the advisory audit in the cited CI
  run. This means no advisory was returned by OSV for those versions at that
  query time, not a timeless or vulnerability-free claim. Repeat the audit
  for the exact release candidate; do not reuse an old package count/result.
- [x] A disposable first-run bootstrap creates the hash-locked private venv,
  reaches a healthy live snapshot, and exits cleanly without using system
  Python packages.
- [x] Live read-only checks pass for discovery, every visible room's details,
  Favorites, queue, Sonos Playlists and playlist contents, local-library
  access, alarms, Global Player, and Apple catalog search.
- [x] Fake-only automated AI-curated playlist tests cover exact Apple song URL
  and identity validation, 25-track bounds, duplicate review, plan expiry and
  replay, stale inventory/anchor state, direct saved-playlist construction,
  exact per-add/final reopen verification, code-800 failures, bounded visibility
  retry, and exact-ID cleanup/cleanup failure. The redesigned direct operation
  has also passed the bounded physical cases recorded below.
- [x] Fake-only exact-playlist playback tests cover independent permissions,
  exact UID targeting, standalone/online/source/transport/volume/size policy,
  complete fingerprints, fresh-state conflicts, single-use handles/tickets,
  exact append order/start position, authoritative verification, partial
  append/start/verification failure, no retry/rollback, and QML snapshot
  broadcast after a post-append failure.
- [x] Live idempotent writes pass for same-name rename, same-volume write,
  every speaker-reported sound/device setting, and current shuffle, repeat,
  and crossfade values. No effective setting or playback change was requested.
- [x] On a quiet standalone room, volume, mute, bass, treble, balance,
  loudness, status light, touch controls, and sleep timer each changed and
  restored successfully. A temporary rename was authoritatively confirmed and
  restored, and queue-backed shuffle, repeat, and crossfade each changed and
  restored without starting playback.
- [x] On the home-theater room, night mode, speech enhancement, Sub and
  surround enablement, surround mode and levels, Sub gain, audio delay, and TV
  Autoplay each changed and restored without starting playback.
- [x] A disposable disabled alarm was created, enabled, disabled, edited, and
  deleted. A disposable Sonos Playlist was saved from an existing queue,
  reordered, shortened, and deleted. Unrelated alarms and playlists were
  unchanged.
- [x] A stopped standalone room's queue was backed up, cleared, rebuilt with
  Next and End insertion, checked for stale-item rejection, edited, cleared,
  and restored exactly. Playback remained stopped throughout.
- [x] Terminating only the Sonarchy backend process caused its QML supervisor
  to start a new process automatically; the replacement stayed healthy and
  reported no recovery errors.
- [x] A real failed album attempt was diagnosed: the whole album reached the
  queue, then enabled TV Autoplay replaced the queue transport with TV audio.

## Test household products

- Sonos One (S18)
- Sonos Play:1 (S1), two devices
- Sonos Play:5 (S6)
- Sonos Playbar (S9), with Sub and surround devices represented through its
  home-theater controls

These products do not expose Trueplay or Sub crossover through SoCo, so those
two controls are not applicable to this household. They remain covered by
automated capability/visibility tests and must be tested on supporting hardware
before Sonarchy claims real-device coverage for them.

## AI-curated Sonos Playlist physical acceptance — direct ordered persistence passed

The old queue-staging design was rejected after two owner-approved physical
failures:

1. On 2026-08-28, no playlist was created and rollback recreated 36 queue slots
   without complete title, artist, album, or provider identity. Exact queue
   restoration was false and the original contents/order became undetermined.
2. On 2026-08-29, a known stopped one-track **Wish You Were Here — Pink Floyd**
   baseline was established first. Track 1 (`song:1452806384`) staged
   successfully; track 2 (`song:1443065566`) failed with Sonos code 800. No
   playlist was created. Rollback recreated one stopped active queue slot but
   failed resource verification, and the Pink Floyd metadata/stable identity
   were not restored.

The redesign creates an empty Sonos Playlist and adds exact Apple songs directly
to that saved playlist. On 2026-08-29, an owner-approved one-track run created
and retained `SQ:49` (`Sonarchy Direct Test A 2026-08-29`). The owner manually
confirmed **Just Like Heaven — The Cure**, album **Kiss Me, Kiss Me, Kiss Me**.
It was not played, edited, renamed, or deleted, and no queue or playback
operation was issued.

The automated verifier nevertheless returned a false negative because Sonos
browsed the saved item as a queue-local `DidlMusicTrack` with an Apple
HLS-static resource instead of one of the previously accepted forms. Read-only
inspection confirmed one stable catalogue identity backed by the pinned Apple
service and HLS protocol type. A read-only run of the corrected verifier against
the retained item then accepted `song:1452806384` and its reviewed metadata.
`SQ:49` remains retained and untouched.

On 2026-08-30, Test C created and retained `SQ:51` (`Sonarchy Direct Test C
2026-08-30`) with exact canonical identity `song:1551800724`, **Don't Start Now
— Dua Lipa**, album **Future Nostalgia (The Moonlight Edition)**. Direct
creation and authoritative verification succeeded without album normalization.
No queue operation or playback mutation occurred.

Test D then created and retained `SQ:52` (`Sonarchy Direct Test D 2026-08-30`)
with exactly two authoritatively reopened items in approved order:

1. `song:1452806384` — **Just Like Heaven — The Cure**, reviewed album
   **Kiss Me, Kiss Me, Kiss Me**, accepted under the already bounded observed
   Sonos display normalization; and
2. `song:1551800724` — **Don't Start Now — Dua Lipa**, album **Future Nostalgia
   (The Moonlight Edition)**, with no normalization required.

Both canonical identities and supporting metadata were verified. `SQ:49`,
`SQ:51`, and every other pre-existing Sonos Playlist remained unchanged. The
transaction reported `queueMutation: false` and `playbackMutation: false`,
issued no queue operation, did not start playback, executed create exactly
once, and performed no retry or substitution. `SQ:52` remains retained without
playback or editing.

A separate direct attempt for `song:1443065566`, **Life's What You Make It —
Talk Talk**, was rejected during saved-playlist addition with undocumented
Sonos vendor code `814`. Sonarchy stopped without retry or substitution and
removed attributable partial playlist `SQ:50` through exact-ID automatic
cleanup. Pre-existing playlists, queue, and playback remained unchanged. Code
`814` has no assigned semantic meaning here: this evidence establishes only
that this exact item was rejected through this exact route, not a territory,
account, licensing, provider, or universal-availability conclusion.

### Physically passed persistence matrix

The checked rows describe the exact dated cases above, not every playlist or
the current checkout. Tests A/C/D and the rejected-item cleanup remain separate
observations; a successful create is not evidence that its failure path ran.

- [x] Direct one-track Sonos Playlist creation.
- [x] Direct creation with a second independent Apple catalogue item.
- [x] Direct multi-track Sonos Playlist creation.
- [x] Exact two-item count and exact approved order.
- [x] Authoritative reopen and strong canonical identity verification.
- [x] Supporting title, artist, and album verification.
- [x] Unchanged pre-existing Sonos Playlist inventory.
- [x] Zero queue mutation and zero playback mutation.
- [x] Zero retry and zero substitution.
- [x] Exact-ID cleanup after one rejected item.
- [x] Normal restoration of the installed sole backend after each staged test.

### Deferred acceptance

- [ ] Physical playlist-size coverage beyond the exact one-, two- and
  ten-track cases recorded here, including the maximum supported plan size.
- [x] Public-catalog AI-orchestration evaluation and rejection policy under #61
  completed (PR #117). This does not claim every physical rejection scenario.
- [ ] Concurrent physical QML/MCP mutations and event soak remain unverified
  under the applicable #58/#59/#68 scope. Real backend/MCP lifecycle and
  ownership acceptance passed under #60; public-catalog evaluation #61 is
  complete. Do not report those completed portions as pending.
- [ ] Broader MCP transport, queue, grouping, source, and volume actions under
  issue #14.
- [ ] General destructive queue restoration under issue #19.
- [ ] Apple private-library access or Apple/Sonos playlist synchronization.

Issue #19 separately owns general destructive queue rollback; this acceptance
does not claim that issue fixed. Tests A, C, and D do physically demonstrate
ordered direct Sonos Playlist persistence for the exact accepted items above,
not universal acceptance of every Apple catalogue song.

### Ten-track GB case — 2026-09-06

The [accepted architecture/test record in #17](https://github.com/SurreptitiousFabric/omarchy-sonarchy/issues/17)
reports creation of one reviewed ten-track GB catalogue plan, with all ten
identities, metadata and order verified. Separate playback preserved the
existing queue entry and authoritatively started the first appended song.
The owner confirmed audible playback.

This is retained exact-case evidence, not a new physical test by this
documentation PR. The cited record does not identify a tested software SHA or
verification timings, so neither is inferred here. It does not establish
automatic transition, failure cleanup, state restoration or all-device
coverage. In particular, first-track PLAYING and audible confirmation do not
satisfy the original natural-transition requirement:

- [ ] Observe a directly created multi-track Sonos Playlist advance naturally
  from its first track to its second without invoking Next (#17).

The distinct Apple-album transition criterion below also remains unchecked.

### Physical Stage 1: read-only create preflight

1. Resolve one exact room UID as the household anchor and confirm the exact
   coordinator/household binding. Do not inspect queue contents, playback
   source/position, transport, volume, or mute merely for playlist creation.
2. Read the complete bounded Sonos Playlist inventory. Require one free slot
   and an unused exact disposable name.
3. Submit `playlist_plan.apple.validate` with `mode: save-only`, the reviewed
   exact Apple songs, and duplicate policy. Confirm exact ordered canonical
   identities, duration, inventory fingerprint/count, direct capability,
   `catalogueIdentityValidated: true`,
   `sonosAcceptance: unproven_until_create`, `queueMutation: false`,
   `playbackMutation: false`, expiry, and approval requirement.
4. Confirm the review explains that one playlist is created on success, no
   queue changes and no playback start occur, and an exact-ID partial playlist
   may briefly exist with cleanup attempted on failure. Confirm the complete
   result is below 64 KiB and contains no raw infrastructure metadata.
5. Stop and obtain explicit owner approval for exactly one token-only create.

### Physical Stage 2: direct create only

1. Invoke `playlists.apple.create` exactly once with only `planToken` and
   `approved: true`. Never retry a consumed token.
2. Verify the create-returned attributable `SQ:<id>`, exact name, item count,
   exact order/canonical identities, and title/artist/album after authoritative
   reopen.
3. Verify every pre-existing Sonos Playlist is unchanged and the result reports
   `queueMutation: false` and `playbackMutation: false`. Read-only observation
   may confirm no unexpected playback, but no queue backup/restoration action
   belongs to this transaction.
4. On a track failure, require immediate stop with no retry or substitution.
   Accept only bounded `playlistConstructionStep`, reviewed failed
   position/identity, trusted UPnP code, exact attributable partial ID, cleanup
   booleans, and queue/playback unchanged booleans.
5. Cleanup may delete only the exact create-returned new ID after exact-ID and
   invocation-bound-title verification. A cleanup failure must leave every
   unrelated playlist untouched and return that exact ID with
   `playlistCleanupRequired: true`.
6. Retain any successful disposable playlist until separately approved
   exact-ID cleanup. Do not play it during this acceptance.

### Separately reviewed exact-playlist playback

Playback is not a stage of creation. The implemented first issue #14 slice
requires a verified `SQ:<id>`, exact standalone room UID, volume at most 20,
stopped/paused transport, confirmed queue/no source, complete playlist/queue
reads, explicit approval, and a fresh identical preflight. It appends the
playlist and starts its first appended item without retry or queue replacement.
If a later phase fails, appended entries may remain and no issue #19 rollback
is attempted. Never infer playback approval from successful playlist creation.

Automated tests use fake speakers/controllers only. The narrow physical case
below passed under separate owner approval; broader physical acceptance remains
subject to the unchanged checklist and marketplace HOLD.

Physical retest on 2026-09-05, installed commit `b94a1c7`: the owner authorized
one append-and-play of retained commissioning playlist `SQ:53` in the standalone
room. The room was stopped, unmuted, at volume 8, with one existing
`Just Like Heaven` queue item. Fresh preflight matched the reviewed fingerprint.
Exactly one append and one playback-start invocation returned; queue length two
and current position two were confirmed. Playback verification nevertheless
reported `speaker_rejected` in `verify_playback`: both observations reported
`TRANSITIONING`, completing at 157 ms and 1144 ms (second start at 1000 ms).
The only failed predicate was `transportIsPlaying`. A subsequent read reported
`PLAYING` at volume 8; a separate queue read confirmed both items with the second
current. No write retry or cleanup was performed. The running backend started
after the installed verification files were updated. This reproduces a false
negative with those timing fixes installed; exact-playback acceptance remained
open at that revision. These are device-reported observations, not a claim of
audible acceptance or a measurement of the precise time playback began.

Physical acceptance passed on 2026-09-05 with tested software revision
`8d938043caaf625992bdae071a43aab1ab5c4664` (PR #46), distinct from this later
documentation update. Retained evidence confirmed installed/backend/MCP
provenance and a fresh owner-approved plan for one standalone room, initially
stopped, queue source, volume 8, unmuted. Retained playlist `SQ:53` contained one
`Just Like Heaven` by The Cure. One append and one playback-start invocation
both returned, with zero retries. Public MCP returned `ok: true` and
`verification.authoritative: true`: queue length grew from 2 to 3, original
entries were preserved, and position 3 was verified as the first appended item
using positional evidence, not matching titles. Fresh complete verification
confirmed the exact state, including unchanged playlist, volume, mute and
topology.

Six transport observations were made; `PLAYING` returned at 1593 ms. Fresh
complete verification ran from 1594 to 2587 ms with no failed predicates, under
the existing 250 ms / maximum 20 observations / 5000 ms latest-start policy.
These are post-write verification timings, not audible-onset measurements.
The owner separately confirmed audible playback in the intended room. No
cleanup, restoration, replay or second test occurred. This accepts only this
exact case, not every playlist, device or playback scenario. See the
[sanitized physical evidence on #14](https://github.com/SurreptitiousFabric/omarchy-sonarchy/issues/14#issuecomment-5553308423).

## Required real-device acceptance

- [ ] Complete a keyboard-only tour of every page and every visible control,
  including focus-following scroll, confirmation prompts, error dismissal,
  and narrow/wide configured panel sizes.
  Partial passes on 2026-09-07: six-page narrow/wide layout checks, native
  Tab/Shift+Tab focus-scroll checks (PR #129), and grouped-room row bounds
  checks (PR #130). These completed checks must not be listed as wholly
  untested. On 2026-09-08, 54 isolated production-panel keyboard interaction
  cases passed (27 at each size): dropdown open/cancel/selection, six inline
  confirmation types and five-second expiry, error dismissal, editor Escape,
  and group-draft Cancel. Zero device dispatches; real host controls with a
  fake service and in-window Qt keys. See the [exact result and harness limits](docs/keyboard-interaction-acceptance.md).
  Those interactions are no longer pending. A later [headless Wayland visual
  check](docs/keyboard-visual-acceptance.md) found a concrete #65 blocker:
  arming alarm deletion leaves only 5/33 pixels of the focused button visible
  at 360×520 and 22/33 at 620×820. **Fixed, retested and merged in PR #131 on September 8:**
  both sizes now retain focus with 33/33 pixels visible in private Wayland.
  The regression also passes five-second expiry, first/second-press safety and
  outside-page focus checks. Installed plugin unchanged; this source blocker is resolved.
  Enumerated visual passes are retained with their fixture/compositor limits;
  neither this defect nor the open composite row erases earlier passed cases.
- [x] Adjust and restore Group Volume plus individual grouped-room volume/mute
  controls. Owner-confirmed working on installed checkpoint `4626b3f`.
- [ ] Complete remaining transport-control and restoration coverage: pause,
  previous/next and installed control dispatch lack reconciled physical evidence.
  Playback has passed in the exact cases above; standalone mute/volume changed
  and restored. Apple share-link seeking and stop passed on 2026-08-28; see the
  [handoff result](docs/apple-music-handoff-test-result.md). These are not untested.
- [ ] Play one Apple track and one whole Apple album. With TV Autoplay
  explicitly disabled by the owner, observe the album advance automatically
  from the first track to the second; pressing Next alone is not sufficient.
- [ ] Play a Sonos Favorite and a Global Player result. Confirm its safe station
  logo appears first, a confident title/artist match changes to track artwork,
  an ambiguous match keeps the fallback, and live-stream actions remain safe.
- [ ] Exercise queue Play against the disposable queue; Next, End, remove,
  clear, and stale-item protection have passed without starting playback.
- [ ] Play the disposable Sonos Playlist; create/save/reorder/remove/delete and
  unrelated-playlist preservation have passed without starting playback.
  This residual criterion concerns installed QML Play dispatch. Separately
  reviewed MCP saved-playlist playback and audible confirmation already passed
  in the September 5 and 6 cases above; do not report all playlist playback pending.
- [ ] Browse every local-library category reported by the test household,
  traverse at least two nested levels, move forward and backward across a
  multi-page result when available, search and play one track, and confirm a
  deliberately stale path is rejected without playing a different item.
- [x] Create, edit, disable, re-enable, and delete a disposable alarm; verify
  that unrelated alarms are unchanged.
- [x] Owner-confirmed on 2026-09-08: a manually configured alarm works.
  User-reported acceptance; no agent setup or retest was performed for this
  record. The setup interface and tested software revision were not specified.
  #4's room-change/field-preservation and physical rejection-recovery subcases
  have missing evidence; this does not reopen basic alarm setup/function.
- [x] Change and restore every supported sound and device setting exposed by
  the test household, including home-theater, Sub, surround, and TV Autoplay.
  Trueplay and Sub crossover are not applicable on the recorded products.
  Context-inapplicable play modes are disabled with actionable text.
- [ ] Compare renamed/restored room names in the official Sonos app. Temporary
  rename and exact restoration were already authoritatively confirmed at the
  speaker; the cross-app comparison is the remaining evidence gap.
- [x] Group rooms and restore the original topology. Owner-confirmed working on
  the live household with installed checkpoint `7bcb873`.
- [ ] Test ungroup, group-all, staged membership, playback-session selection,
  and safe room handoff; restore the exact original topology afterward.
- [ ] Test line-in and TV source switching only on hardware that reports the
  source, then restore the original source.
- [ ] Compare an active TV audio-format value with the official Sonos app (#5).
  Idle and unsupported-room reporting already passed.
- [x] Verify sleep timer, shuffle, repeat-one, repeat-all, crossfade, and every
  supported home-theater mode, restoring original values.
- [ ] Verify recovery from a temporarily unreachable speaker, stale cached
  state, rejected UPnP actions, and network rediscovery without leaking raw
  private addresses in the popup. Backend-exit recovery has passed.
  Real backend ownership, duplicate-owner rejection and MCP disconnect/reconnect
  also passed under #60; these must not be reported as untested recovery.
- [ ] Leave the event backend running through ordinary playback, grouping, and
  idle periods long enough to detect subscription churn, process leaks,
  repeated errors, or state drift.
- [x] Repeat install, upgrade, disable/enable, and removal instructions from a
  clean test checkout without affecting unrelated Omarchy plugins.
  Passed locally on 2026-09-07 at `bc9fdb8446d7b1914e4325a6756ce0ccb7bcfc03`:
  real copied-shell/widget lifecycle, prior-to-current upgrade, fresh bootstrap
  and removal, backend/MCP reconnect and unrelated-config preservation.
  See [#60 evidence](https://github.com/SurreptitiousFabric/omarchy-sonarchy/issues/60#issuecomment-5573954743).

## Final release gate

- [ ] Review the final source diff and dependency audit.
- [ ] Repeat all automated, security, QML, and exact-commit marketplace checks.
- [ ] Record the tested Sonos products and any `not applicable` rows.
- [ ] Owner release sign-off for the exact commit, repository, permanent plugin
  ID, category, tags, preview, and complete marketplace issue body.

Until every applicable box is complete, the project remains a local beta and
must not be submitted to the marketplace.
## Single-authority MCP acceptance

Automated evidence is the cited PR #81 CI run and production-path tests in
`tests/test_local_mcp.py`, `tests/test_mcp_stdio.py`,
`tests/test_mcp_browse_contract.py` and `tests/test_mcp_playback_contract.py`.
These checks use fake external boundaries and do not establish live household
concurrency or current installed-system acceptance.

- [x] Process ownership and socket/config symlink, owner, and mode boundaries
  are covered with fake-only tests.
- [x] Read-only default and independent optional create/play inventories are
  contract tested; `playlist-create` does not authorize playback.
- [x] Backend token hiding, opaque single-use handles, restart invalidation, no
  replacement fields, fresh second-handle use, and exactly-once create/play
  dispatch are covered.
- [x] MCP import boundaries prohibit SoCo/controller/QML imports.
- [ ] Repeat existing protocol, Apple create, QML, plugin and packaging gates
  on the exact release candidate; historical passing subsets do not waive them.
- [x] No new real-device run was authorized or performed for this implementation.
  The merged PR #18 physical evidence remains create-only. The later separately
  approved exact-playback case on `8d93804` and the later recorded ten-track GB
  case are above. Neither was performed by this documentation update. Issue
  #14 remains open for every broader action.
