# Sonarchy release acceptance

**Marketplace status: HOLD**

Sonarchy must not be published or submitted merely because its automated tests
pass. Marketplace release requires every applicable check below, a reviewed
exact release commit, and explicit owner sign-off. A feature unsupported by the
test household may be marked `not applicable` only with the product limitation
recorded; it must not be called tested.

## Completed local gates

- [x] All 433 automated Python tests pass with 86% branch coverage, alongside
  32 headless QML runtime checks.
- [x] Repository-wide Ruff, formatting, compilation, JSON, Bash syntax,
  Omarchy manifest, and standalone QML lint gates pass.
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
  replay, stale state, exact save/reopen verification, both persistence modes,
  and rollback success/failure. No feature-specific speaker write was run.
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

## AI-curated Sonos Playlist physical acceptance — not run

This feature's automated suite uses fakes and must not mutate real speakers
without explicit owner approval for the exact run. Use two exact Apple songs
whose catalogue IDs, URLs, title, artist, album, duration, and order have been
reviewed. Use unique disposable Sonos Playlist names; never reuse or overwrite
an existing name.

### Stage 1: read-only preflight

1. Resolve one exact standalone room UID; record its name only as supporting
   evidence. Confirm its sole member and coordinator are that UID.
2. Record authoritative room/group volume and mute, transport and bounded
   source, the safe current-media fingerprint, current item when present,
   complete queue identities/order/length/update marker, active position, and
   every existing Sonos Playlist ID/name. Do not record the raw media URI.
3. Confirm the queue contains no more than 100 items and every item is
   restorable. A stopped transport is not required to retain a current-item
   marker.
   Confirm the bounded Sonos Playlist inventory contains at most 99 entries so
   one authoritative create/verification slot remains.
4. Submit `playlist_plan.apple.validate` in `save-only` mode. Confirm the
   returned room/topology, queue, transport/source and media fingerprint,
   volume/mute, positive capabilities, exact ordered canonical `song:<id>`
   values, total duration, unique name, side effects, expiry, and approval
   requirement. A queue-active URI may safely project `QUEUE` even if the coarse
   source probe reports `UNKNOWN`; an unverified non-queue `UNKNOWN` must fail.
   Confirm the complete UTF-8 result line remains within 64 KiB.
   Confirm an oversized authoritative snapshot is replaced by a bounded,
   write-disabled degraded snapshot without stopping the backend process.
   Confirm the maximal successful 25-track result also fits within 64 KiB and
   returns full verified metadata only once.
   Confirm an invalid or unreadable create-returned title retains exact-ID
   cleanup ownership without permitting name-only deletion.
5. Stop. Obtain explicit owner approval for the one token-only write.

### Stage 2: save only

1. Invoke `playlists.apple.create` exactly once with only the preflight token
   and `approved: true`. Do not use an ad-hoc SoCo process.
2. Verify the new authoritative `SQ:<id>`, exact name, exact item count, exact
   order and Apple song identities, and supporting title/artist evidence after
   reopening the saved playlist.
3. Verify the original queue contents/order, active position, source, and exact
   playing/stopped state were restored. Verify topology, volume, and mute never
   changed and no playback started prematurely.
4. Verify every unrelated Sonos Playlist ID/name/content remains unchanged.
5. Retain the disposable playlist until cleanup receives separate approval.
   Any failure without an exact create-returned playlist ID must leave all
   candidates untouched and report `playlistCleanupRequired: true`.

### Stage 3: save and play plus natural progression

1. Repeat Stage 1 with a second unique disposable name and
   `save-and-play`; obtain fresh explicit approval.
2. Execute once. Verify the reopened playlist and active queue contain the
   exact reviewed order and track 1 is authoritatively `PLAYING` in the exact
   standalone room.
3. Let track 1 finish naturally. If time-bounded acceptance requires seeking,
   obtain approval and use the narrow seek operation near the end; never invoke
   Next to prove sequencing.
4. Capture authoritative evidence while track 2 is positively playing: exact
   title, artist, queue position, room UID, and unchanged topology/volume/mute.
5. Invoke and verify Stop as a separate approved action. Do not infer Stop from
   a missing current-item marker.

### Stage 4: separately approved cleanup

1. Re-read playlist inventory and match each disposable playlist by both exact
   `SQ:<id>` and name before deletion. Abort on ambiguity.
2. Delete only those approved disposable identities. Restore any queue/playback
   state retained after successful `save-and-play` using a separately reviewed
   operation.
3. Verify original topology, volume/mute, unrelated playlists, and other rooms
   are unchanged. Record any rollback or cleanup uncertainty as a failure, not
   a pass.

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
