# Sonarchy release acceptance

**Marketplace status: HOLD**

Sonarchy must not be published or submitted merely because its automated tests
pass. Marketplace release requires every applicable check below, a reviewed
exact release commit, and explicit owner sign-off. A feature unsupported by the
test household may be marked `not applicable` only with the product limitation
recorded; it must not be called tested.

## Completed local gates

- [x] The complete automated Python suite passes under the checked-in branch
  coverage gate, and the complete headless QML component suite passes.
- [x] Repository-wide Ruff, formatting, compilation, JSON, Bash syntax,
  protocol, security, Omarchy plugin, and standalone QML lint gates pass.
- [x] Headless real-event QML tests load Omarchy's installed `PanelSlider`,
  prove wheel input scrolls without a slider mutation, preserve intentional
  dragging, enforce request-owned error clearing, and cover content root,
  nested, paging, Back, Favorites, and Apple artist/album history transitions.
- [x] The marketplace v3 deterministic baseline reports no findings and only
  the disclosed, non-blocking `package-manager` review capability.
- [x] The exact 12-package runtime environment is internally consistent and a
  current OSV batch query reports no known advisories for the installed
  versions.
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

- [ ] Physical playlists larger than the tested two-item case.
- [ ] AI-orchestration policy for individually rejected catalogue items.
- [ ] MCP process ownership and concurrency under issue #11.
- [ ] Broader MCP transport, queue, grouping, source, and volume actions under
  issue #14.
- [ ] General destructive queue restoration under issue #19.
- [ ] Apple private-library access or Apple/Sonos playlist synchronization.

Issue #19 separately owns general destructive queue rollback; this acceptance
does not claim that issue fixed. Tests A, C, and D do physically demonstrate
ordered direct Sonos Playlist persistence for the exact accepted items above,
not universal acceptance of every Apple catalogue song.

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

Automated tests use fake speakers/controllers only. Physical acceptance remains
pending and must use one retained commissioning playlist in one quiet
standalone room under a separate owner-approved prompt.

Physical retest on 2026-09-05, installed commit `b94a1c7`: the owner authorized
one append-and-play of retained commissioning playlist `SQ:53` in the standalone
Master Bedroom. The room was stopped, unmuted, at volume 8, with one existing
`Just Like Heaven` queue item. Fresh preflight matched the reviewed fingerprint.
Exactly one append and one playback-start invocation returned; queue length two
and current position two were confirmed. Playback verification nevertheless
reported `speaker_rejected` in `verify_playback`: both observations reported
`TRANSITIONING`, completing at 157 ms and 1144 ms (second start at 1000 ms).
The only failed predicate was `transportIsPlaying`. A subsequent read reported
`PLAYING` at volume 8; a separate queue read confirmed both items with the second
current. No write retry or cleanup was performed. The running backend started
after the installed verification files were updated. This reproduces a false
negative with the timing fixes installed; exact-playback acceptance remains
open. These are device-reported observations, not a claim of audible acceptance
or a measurement of the precise time playback began.

## Required real-device acceptance

- [ ] Complete a keyboard-only tour of every page and every visible control,
  including focus-following scroll, confirmation prompts, error dismissal,
  and narrow/wide configured panel sizes.
- [x] Adjust and restore Group Volume plus individual grouped-room volume/mute
  controls. Owner-confirmed working on installed checkpoint `4626b3f`.
- [ ] Test play, pause, stop, previous, next, standalone mute/volume, and
  supported seeking, restoring the starting state afterward.
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
- [ ] Browse every local-library category reported by the test household,
  traverse at least two nested levels, move forward and backward across a
  multi-page result when available, search and play one track, and confirm a
  deliberately stale path is rejected without playing a different item.
- [x] Create, edit, disable, re-enable, and delete a disposable alarm; verify
  that unrelated alarms are unchanged.
- [x] Change and restore every supported sound and device setting exposed by
  the test household, including home-theater, Sub, surround, and TV Autoplay.
  Trueplay and Sub crossover are not applicable on the recorded products.
  Context-inapplicable play modes are disabled with actionable text.
- [ ] Rename one room and restore its exact original name in both Sonarchy and
  the official Sonos app.
- [x] Group rooms and restore the original topology. Owner-confirmed working on
  the live household with installed checkpoint `7bcb873`.
- [ ] Test ungroup, group-all, staged membership, playback-session selection,
  and safe room handoff; restore the exact original topology afterward.
- [ ] Test line-in and TV source switching only on hardware that reports the
  source, then restore the original source.
- [x] Verify sleep timer, shuffle, repeat-one, repeat-all, crossfade, and every
  supported home-theater mode, restoring original values.
- [ ] Verify recovery from a temporarily unreachable speaker, stale cached
  state, rejected UPnP actions, and network rediscovery without leaking raw
  private addresses in the popup. Backend-exit recovery has passed.
- [ ] Leave the event backend running through ordinary playback, grouping, and
  idle periods long enough to detect subscription churn, process leaks,
  repeated errors, or state drift.
- [ ] Repeat install, upgrade, disable/enable, and removal instructions from a
  clean test checkout without affecting unrelated Omarchy plugins.

## Final release gate

- [ ] Review the final source diff and dependency audit.
- [ ] Repeat all automated, security, QML, and exact-commit marketplace checks.
- [ ] Record the tested Sonos products and any `not applicable` rows.
- [ ] Owner release sign-off for the exact commit, repository, permanent plugin
  ID, category, tags, preview, and complete marketplace issue body.

Until every applicable box is complete, the project remains a local beta and
must not be submitted to the marketplace.
## Single-authority MCP acceptance

- [x] Process ownership and socket/config symlink, owner, and mode boundaries
  are covered with fake-only tests.
- [x] Read-only default and independent optional create/play inventories are
  contract tested; `playlist-create` does not authorize playback.
- [x] Backend token hiding, opaque single-use handles, restart invalidation, no
  replacement fields, fresh second-handle use, and exactly-once create/play
  dispatch are covered.
- [x] MCP import boundaries prohibit SoCo/controller/QML imports.
- [x] Existing protocol, Apple create, QML, plugin, and packaging gates remain
  required.
- [x] No new real-device run was authorized or performed for this implementation.
  The merged PR #18 physical evidence remains create-only; exact-playback
  physical acceptance is a separate owner-approved phase. Issue #14 remains
  open for every broader action.
