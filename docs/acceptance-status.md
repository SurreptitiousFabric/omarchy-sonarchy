# Reconciled acceptance status

Last reconciled: **2026-09-08**. This is the starting point for “what remains to
test”; the detailed historical record is [ACCEPTANCE_TESTS.md](../ACCEPTANCE_TESTS.md).
Reconciled against that record, the Apple handoff result, live issue bodies and
comments (#2–5, #17, #48, #58–59, #65–68), and the private machine log and retained
#60/#65/#127/#128 evidence. No device test was run during reconciliation. A later isolated keyboard
interaction run on the same date is recorded below; it used a fake service.

**An evidence gap means no matching result was found in those records, not that
the owner has never performed the test. Do not turn this table into a blanket
retest list.** Historical passes remain passes for their observed scope; the
separate exact-release gates do not erase them.

## Completed evidence and exact residual scope

The agreed bounded work is the **whole pre-publication plan #48**, not the alarm
fix or keyboard subtask alone. Current #48 was read again on September 8: completed
children are #49–#53, #55–#57, #60 and #61. Remaining composite work is #54 candidate
validation, #58 keyboard/content/device acceptance, #59 room/source/recovery
acceptance, and final exact-candidate checks/evidence review/owner sign-off.
The detailed passes below narrow those composites; they do not reset them.
The September 7 owner amendment cancelled upstream submission/adoption work.
The full pre-publication plan is **not complete**. Publication is not authorized.
The September 8 warning-policy amendment below is also recorded in GitHub
#48/#54/#64. The initial HTTP 403 was resolved by using the already signed-in
repository owner account for repository requests.

| Area | Completed evidence | Residual scope / status |
| --- | --- | --- |
| Alarm | Disposable create/edit/enable/disable/delete and unrelated-alarm preservation passed historically. Owner manually configured an alarm and confirmed it works on September 8. | Basic alarm setup/function is **passed**. #4's room-change with field preservation and physical rejection recovery have **missing evidence**; do not schedule another basic alarm setup. Owner confirmation did not specify interface or revision. |
| Installation lifecycle | #60 completed September 7 at `bc9fdb8`: real add/enable/disable/update/remove in a copied shell, fresh bootstrap, prior-to-current upgrade, backend/MCP reconnect, data retention and unrelated-config preservation. Interpreter replacement separately passed on `d68326d`. | **Passed**; no outstanding generic install/removal test. |
| Keyboard/layout | Six pages at 360×520 and 620×820 passed geometry after #125. Native focus scroll and grouped-row bounds passed after #127/#128. Retained `c4949af` tour reports all observed controls reached on each page/size, zero clipped focus and zero unreached controls. | **Interaction passes added September 8**: [54 fixture-backed checks](keyboard-interaction-acceptance.md), 27 per size, cover dropdown cancellation/selection, six confirmation types and expiry, error dismissal, editor Escape and group-draft Cancel, with zero device dispatches. These are no longer untested. A later [headless Wayland visual check](keyboard-visual-acceptance.md) found alarm-delete confirmation clipping (5px narrow / 22px wide). **Fixed, retested and merged in PR #131 September 8:** the focused button remains fully visible at 33/33px in both sizes; regression covers expiry, first/second-press safety and outside-page focus. The installed plugin is unchanged. This alarm blocker is resolved in source; do not repeat all 54 passed interactions. Wayland screenshots credit the enumerated presentation cases, with compositor/live-data limits recorded. |
| Playlist creation/playback | Direct one-, two-, ten-track persistence with exact order/identity passed. Separate exact saved-playlist append/play and audible confirmation passed September 5 (`8d93804`) and September 6 (ten-track case, revision unspecified). Historical saved-playlist save/reorder/remove/delete passed. | **Passed for these cases**. QML disposable-playlist Play dispatch is a separate **evidence gap**, not a reason to call playlist playback untested. Maximum plan size and direct-created playlist natural transition remain unverified. |
| Apple share-link playback/seek/stop | August 28 two-track Apple playlist handoff appended without replacing existing entries, played, sought near track end, naturally advanced without Next, then stopped. | **Passed for this path**. Do not call seeking, stopping or all natural transitions untested. Apple-album and direct-created Sonos Playlist natural transitions are distinct **evidence gaps**. |
| Other transport | Standalone volume/mute changes/restoration passed; playback/seek/stop evidence above. | #66: pause, previous/next, installed control dispatch and agreed end-state restoration as a complete scenario have **missing evidence**. Future MCP transport implementation (#69/#113–115) is separate. |
| Grouping/mixer | Owner confirmed grouping at `7bcb873`; group volume and individual grouped-room volume/mute at `4626b3f`. | **Passed for these actions**. Ungroup/group-all, staged membership, session selection and handoff are **evidence gaps** (#66). |
| Sound/device/play modes | Standalone and home-theater settings changed/restored; sleep timer, shuffle, repeat-one/all and crossfade passed. | **Passed**. Trueplay/Sub crossover are **not applicable** to recorded household hardware. |
| Queue | Historical stopped-queue Next/End, edit/remove/clear, stale-item rejection and exact restoration passed for that case. Exact MCP playlist append preserves existing queue entries. | **Partial**: installed queue Play and source-specific insertion/order/position/failed-operation refresh are **evidence gaps** (#3). Later queue replay resource-loss failures under #19 prevent general restoration claims. #55 containment is completed; #19 is unresolved engineering, not an instruction to repeat destructive testing. |
| Local library | Live read-only access passed; hierarchy, paging, dispatch/error handling and stale-path checks have automated coverage. | Indexed-library categories, two nested levels, available multipage results, search/play and stale-path rejection together on real indexed content have **missing physical evidence** (#2). |
| Favorites/Global Player | Live read-only Favorites and Global Player search passed. | Playback, station-logo/track-artwork transitions and ambiguous-match fallback have **missing physical evidence**. Search/browse is not untested. |
| Room rename | Temporary rename authoritatively confirmed and restored historically. | **Passed at speaker**; matching original/restored names in the official app is the **evidence gap**. Do not repeat rename wholesale without checking that comparison. |
| Sources/TV format | TV Autoplay setting changed/restored; observed TV Autoplay interrupting album playback. TV-format idle/unsupported readout passed (#5). | Deliberate supported TV/Line-In switching with return-state verification (#67), and active TV-format comparison against official app (#5), have **missing evidence**. Autoplay observation does not prove the switching test. |
| Recovery/concurrency | Backend-exit auto-restart passed; #60 real backend ownership, duplicate-owner rejection, MCP unavailable/reconnect and widget lifecycle passed. | Temporary speaker unreachability, stale discovery/network recovery and a timed ordinary-playback/grouping/idle soak have **missing evidence** (#68). Concurrent physical QML/MCP mutations are separate unverified coverage; do not call all backend recovery/concurrency untested. |

## Release engineering, separate from owner manual tests

- **Owner amendment September 8:** zero QML warnings is no longer required,
  and upstream fixes are not release dependencies. The 117 documented platform
  metadata warnings are explicitly baselined; errors and new warnings still fail.
  The current local QML scan passes with 117 accepted warnings and zero unexpected
  diagnostics. This supersedes the previous zero-warning blocker, preserving its
  historical failed reports. Final clean exact-candidate validation remains required.
- Automated CI/security/advisory checks have passing dated evidence. Final
  exact-release validation and source/dependency review remain release gates;
  these are not blanket requests to repeat household testing.
- Public-catalog orchestration evaluation #61 is completed. Additional playlist
  size/device combinations are unverified coverage, not evidence that creation
  fails or has never been tested.
- Broader MCP transport/queue/volume, destructive queue restoration, private
  Apple-library work and optional Apple export/synchronization are separate
  implementation/research scope, not current manual acceptance tasks.
- Marketplace HOLD and final owner sign-off remain. No release was authorized
  or performed by this reconciliation.

## Evidence pointers

- [Detailed historical and physical cases](../ACCEPTANCE_TESTS.md)
- [Apple share-link playback, seek, natural transition and stop](apple-music-handoff-test-result.md)
- [Completed real lifecycle #60](https://github.com/SurreptitiousFabric/omarchy-sonarchy/issues/60#issuecomment-5573954743)
- [Keyboard/layout passes and remaining interaction scope #65](https://github.com/SurreptitiousFabric/omarchy-sonarchy/issues/65#issuecomment-5574275677)
- [Local-library scope #2](https://github.com/SurreptitiousFabric/omarchy-sonarchy/issues/2)
- [Source-specific queue scope #3](https://github.com/SurreptitiousFabric/omarchy-sonarchy/issues/3)
- [Alarm room/rejection scope #4](https://github.com/SurreptitiousFabric/omarchy-sonarchy/issues/4)
- [Active TV-format comparison #5](https://github.com/SurreptitiousFabric/omarchy-sonarchy/issues/5)

## Update rule

After each owner confirmation or observed test, update this table and the exact
criterion in ACCEPTANCE_TESTS.md before reporting remaining work. Preserve date,
source, scope and known revision; label unknowns. If an issue retains a broad
unchecked row, report its residual subcase, not the whole row. Investigate newer
conflicting evidence before asking for a repeat. No new physical test is implied
by a request to reconcile or update these records.
