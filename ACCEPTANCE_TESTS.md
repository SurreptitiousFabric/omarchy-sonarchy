# Sonarchy release acceptance

**Marketplace status: HOLD**

Sonarchy must not be published or submitted merely because its automated tests
pass. Marketplace release requires every applicable check below, a reviewed
exact release commit, and explicit owner sign-off. A feature unsupported by the
test household may be marked `not applicable` only with the product limitation
recorded; it must not be called tested.

## Completed local gates

- [x] All 301 automated Python tests pass with 84% branch coverage, alongside
  27 headless QML runtime checks.
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

## Required real-device acceptance

- [ ] Complete a keyboard-only tour of every page and every visible control,
  including focus-following scroll, confirmation prompts, error dismissal,
  and narrow/wide configured panel sizes.
- [ ] Test play, pause, stop, previous, next, mute, group volume, room volume,
  and supported seeking, restoring the starting state afterward.
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
