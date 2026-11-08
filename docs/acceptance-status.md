# Reconciled acceptance status

Last owner-evidence update: **2026-09-09**; full record reconciliation: **2026-09-08**.
This is the starting point for “what remains to
test”; the detailed historical record is [ACCEPTANCE_TESTS.md](../ACCEPTANCE_TESTS.md).
Reconciled against that record, the Apple handoff result, live issue bodies and
comments (#2–5, #17, #48, #58–59, #65–68), and the private machine log and retained
#60/#65/#127/#128 evidence. No device test was run during reconciliation. A later isolated keyboard
interaction run on the same date is recorded below; it used a fake service.

On September 9 the owner confirmed that they **do not have a local music
library**. At that point the real indexed-content scenario lacked its test-data
prerequisite in this household. This narrowed the earlier generic evidence-gap
status; it does not invalidate automated/read-only passes, establish a physical
pass, or waive #2's release criterion.

Later on September 9 the owner accepted the proposed temporary test library.
**Setup is prepared:** 45 locally generated, numbered spoken MP3 clips, three
artists/albums, genre/composer tags and one three-track M3U file. All 45 clips
passed metadata and decoding checks. A dedicated authenticated, read-only
SMB2/3 share is running in an isolated Docker container; all 46 shared files
were downloaded with matching bytes/hashes, and anonymous access and writes
were rejected. Evidence and the private setup guide are retained under
`~/.local/share/sonarchy-test-library/`. No host packages or desktop settings
were changed. This supersedes the absence of prepared test files; **adding the
share in Sonos and indexing are still pending**, as are real indexed browsing,
playback and stale-selection acceptance. No speaker mutation or active-desktop
interaction was performed, and no release criterion was waived.

**September 9 setup diagnostic after the owner's screenshot:** local-library
root/category presentation is observed in the installed popup. A read-only
same-backend browse for the selected room returned seven root categories, zero
artists and zero tracks; the populated test library is not yet evidenced there.
The installed checkout is clean at `8d93804`, distinct from the reviewed current
source candidate. Existing journal entries at 13:39:07 and 13:39:19 CEST record
Sonos code 804 from `add_to_queue`; the screenshot shows the generic rejection
message and truncated category labels crowded by playback actions. The exact
clicked item/button and the vendor code's meaning are not established. Record
the attempted enqueue as **failed**, not successful file playback or a proof
that the MP3s are invalid. The returned empty share list/indexing flag use
fallback handling and do not prove that the raw share query succeeded. Setup
verification in the official Sonos app remains the next step. The supplied
image, journal and read-only results are retained in
`~/.local/share/sonarchy-test-library/evidence/2026-09-09-empty-library/`.
No failure was replayed, no speaker/desktop action was issued, and no general
keyboard pass or Apple Music confirmation is reset by this source-specific case.

The owner subsequently confirmed on September 9 that **adding the temporary
folder in the official Sonos app fails with “no longer available.”** This
supersedes the uncertain setup status with an owner-observed **share-add
failure**. The container, unchanged host address and authenticated local share
read still pass; access from Sonos is not established. Connectivity/protocol/
authentication diagnosis is in progress, with no new playback attempt.

On the next owner attempt September 9, the official app displayed **“scanning
for new content.”** Record that as owner-observed progress, not a completed
scan or physical pass. Connection summaries now show bidirectional traffic
between a LAN client and the temporary SMB share. A concurrent same-backend
read still returned zero artists/tracks in the selected room; indexing success
and populated-library availability are not yet confirmed. Earlier setup failure
remains historical evidence; the new scanning state does not prove its cause
was fixed. No playback was started by the agent.

The owner then confirmed that the scanning attempt **did not add the folder**.
The intermediate scanning state is superseded by a second **failed setup
outcome**; indexing and physical library acceptance remain unresolved. TCP
reachability was observed, so the next diagnosis concerns the SMB exchange and
authentication rather than treating the folder as successfully added.

**September 9 scoped compatibility change:** a local SMB2 client forced to use
NTLMv1 reproduced login rejection with the correct dedicated test password;
the Samba log explicitly reported that NTLMv1 was not permitted. Setting
`ntlm auth = ntlmv1-permitted` only in the temporary test-share container made
the same client authenticate and list the test folders. Normal authentication
also passes; anonymous access and writes remain denied. SMB2/3 transport,
the read-only generated-data mount and the dedicated test credential are retained;
no host firewall, desktop or speaker setting changed. This is a **locally verified
compatibility repair**, informed by primary Sonos/Samba guidance, not a proven
diagnosis or physical pass for the owner's last attempt. A Sonos retry is now
needed specifically because the server authentication policy changed. The
earlier scanning failure is retained; indexing and subsequent physical acceptance
remain unresolved. Evidence: `~/.local/share/sonarchy-test-library/diagnostics/ntlm-compatibility-result.json`.
The temporary packet-summary monitor was stopped and removed after retaining its
logs; authentication logging remains on the test share for the next attempt.

The owner also confirmed on September 9 that they had done the same described
library workflow using **Apple Music**. Credit the user-reported category and
nested browsing, Back, paging where available, search and selected-song playback
workflow for that Apple Music route. The exact interface, Apple source subtype
and software revision were not stated; those unknowns do not invalidate the
confirmation or justify repeating the working flow. This does not establish
local shared-folder/indexed-file coverage, stale-selection rejection, album
natural transition or artwork behavior, none of which was part of the confirmed
six-step flow. No agent-operated device test ran.

**An evidence gap means no matching result was found in those records, not that
the owner has never performed the test. Do not turn this table into a blanket
retest list.** Historical passes remain passes for their observed scope; the
separate exact-release gates do not erase them.

## Completed evidence and exact residual scope

The agreed bounded work is the **whole pre-publication plan #48**, not the alarm
fix or keyboard subtask alone. Current #48 was read again on September 8: completed
children are #49–#57, #60 and #61. #54/#64 were completed by reviewed PR #132.
Remaining composite work is #58 content/device acceptance and #59 room/source/recovery
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
| Playlist creation/playback | Direct one-, two-, ten-track persistence with exact order/identity passed. Separate exact saved-playlist append/play and audible confirmation passed September 5 (`8d93804`) and September 6 (ten-track case, revision unspecified). Historical saved-playlist save/reorder/remove/delete passed. | **Passed for these cases**. QML disposable-playlist Play dispatch is a separate **evidence gap**, not a reason to call playlist playback untested. Maximum plan size and direct-created playlist natural transition are additional unverified coverage, not newly added #48 blockers. |
| Apple share-link playback/seek/stop | August 28 two-track Apple playlist handoff appended without replacing existing entries, played, sought near track end, naturally advanced without Next, then stopped. | **Passed for this path**. Do not call seeking, stopping or all natural transitions untested. Apple-album and direct-created Sonos Playlist natural transitions are distinct **evidence gaps**. |
| Apple Music library workflow | Owner confirmed September 9 that they completed the described category/nested browsing, Back, paging where available, search and selected-song playback workflow using Apple Music. | **Passed by owner report for the stated Apple Music flow**. Exact interface/source subtype/revision unspecified. This is separate from #2's local indexed-file route; stale-selection rejection and whole-album natural transition are not established by this confirmation. |
| Other transport | Standalone volume/mute changes/restoration passed; playback/seek/stop evidence above. | #66: pause, previous/next, installed control dispatch and agreed end-state restoration as a complete scenario have **missing evidence**. Future MCP transport implementation (#69/#113–115) is separate. |
| Grouping/mixer | Owner confirmed grouping at `7bcb873`; group volume and individual grouped-room volume/mute at `4626b3f`. | **Passed for these actions**. Ungroup/group-all, staged membership, session selection and handoff are **evidence gaps** (#66). |
| Sound/device/play modes | Standalone and home-theater settings changed/restored; sleep timer, shuffle, repeat-one/all and crossfade passed. | **Passed**. Trueplay/Sub crossover are **not applicable** to recorded household hardware. |
| Queue | Historical stopped-queue Next/End, edit/remove/clear, stale-item rejection and exact restoration passed for that case. Exact MCP playlist append preserves existing queue entries. | **Partial**: installed queue Play and source-specific insertion/order/position/failed-operation refresh are **evidence gaps** (#3). Later queue replay resource-loss failures under #19 prevent general restoration claims. #55 containment is completed; #19 is unresolved engineering, not an instruction to repeat destructive testing. |
| Local library | Live read-only access and automated hierarchy/paging/dispatch/error/stale-path checks passed. September 9 temporary 45-clip share passed media/SMB checks; root categories are accessible. Local forced-NTLMv1 login failed before the scoped compatibility change and passed afterward. | **Official-app setup has failed; retry after the authentication change is pending.** Successful Sonos indexing remains unverified. Earlier installed `8d93804` enqueue failures (804) and crowded category presentation are retained separately. Populated navigation, paging, search/play and stale-path acceptance (#2) remain unverified; no blanket keyboard retest follows. |
| Favorites/Global Player | Live read-only Favorites and Global Player search passed. | Playback, station-logo/track-artwork transitions and ambiguous-match fallback have **missing physical evidence**. Search/browse is not untested. |
| Room rename | Temporary rename authoritatively confirmed and restored historically. | **Passed at speaker**; matching original/restored names in the official app is the **evidence gap**. Do not repeat rename wholesale without checking that comparison. |
| Sources/TV format | TV Autoplay setting changed/restored; observed TV Autoplay interrupting album playback. TV-format idle/unsupported readout passed (#5). | Deliberate supported TV/Line-In switching with return-state verification (#67), and active TV-format comparison against official app (#5), have **missing evidence**. Autoplay observation does not prove the switching test. |
| Recovery/concurrency | Backend-exit auto-restart passed; #60 real backend ownership, duplicate-owner rejection, MCP unavailable/reconnect and widget lifecycle passed. | Temporary speaker unreachability, stale discovery/network recovery and a timed ordinary-playback/grouping/idle soak have **missing evidence** (#68). Concurrent physical QML/MCP mutations are separate unverified coverage, not a newly added #48 blocker; do not call all backend recovery/concurrency untested. |

## Release engineering, separate from owner manual tests

- **Owner amendment September 8:** zero QML warnings is no longer required,
  and upstream fixes are not release dependencies. The 117 documented platform
  metadata warnings are explicitly baselined; errors and new warnings still fail.
  The entire clean-candidate platform gate passed on reviewed `ac7f132`: manifest,
  QML (117 accepted / zero unexpected), components and real-tool/type-contract
  controls. PR #132 merged with the same source tree as `8dbf652`. #54/#64 are
  closed. This supersedes the zero-warning blocker; historical failed reports remain.
  A later release candidate still needs its own final applicable evidence.
- PRs #131/#132 have passing exact-head CI/security/advisory checks, substantive
  source reviews and completed clean automatic reviews. These reviews are done.
  Final marketplace baseline/ID availability and owner approval remain; refresh
  code/dependency checks only as required for the final selected release candidate.
- Public-catalog orchestration evaluation #61 is completed. Additional playlist
  size/device combinations are unverified coverage, not evidence that creation
  fails or has never been tested.
- Broader MCP transport/queue/volume, destructive queue restoration, private
  Apple-library work and optional Apple export/synchronization are separate
  implementation/research scope, not current manual acceptance tasks.
- Marketplace HOLD and final owner sign-off remain. No release was authorized
  or performed by this reconciliation.

## Reconciliation outcome after PRs #131/#132

Record-checking is complete for the sources listed below. No new speaker or UI
test ran. No additional physical pass was found for the following exact gaps.
“Missing result” is an evidence status, not a claim about every action the owner
has performed. These are the existing applicable criteria needing evidence or an
explicit owner scope decision; they are not automatically scheduled retests.

| Existing criterion | Exact result not found | Evidence checked / completed scope retained |
| --- | --- | --- |
| #2 local library | **Prepared share still needs Sonos indexing**; real indexed categories, nested/paged navigation, playback and stale-path rejection remain physically unverified | September 9: owner had no library, then approved temporary generated data. 45-clip media validation and authenticated read-only share verification passed. #2 comment 5435799997 and automated/read-only passes retained; no physical pass or release waiver. |
| #3 queue/content | Supported source insertion order/current position and failed-operation refresh; installed queue/playlist Play dispatch | #3 comment 5435977444; stopped-queue operations and exact MCP append/play passes retained; unsafe replacement remains contained |
| #4 alarm edge cases | Room change preserving fields; real rejection recovery | #4 comment 5436075393; disposable lifecycle and owner's working alarm retained |
| #5 TV format | Active reported audio format compared with official app | #5 comment 5436148170; idle/unsupported pass retained |
| #66 transport | Pause, previous/next, installed dispatch and agreed restoration | #66 body, August/September logs, Apple handoff report; working playback/seek/stop and mixer retained |
| #66 group/session | Ungroup/group-all, applied staged membership, session selection/handoff and restoration | #66 body and owner-confirmed grouping/mixer; local draft Cancel passed |
| #67 source switching | Deliberate supported TV/Line-In selection and verified return state | #67 body and TV Autoplay observations; settings pass retained |
| #68 recovery/soak | Temporary speaker loss, stale discovery/recovery and a timed playback/grouping/idle observation | #68 body and lifecycle evidence; backend restart/ownership/MCP reconnect retained |
| Apple album | Whole-album automatic first-to-second transition | Historical interrupted album and successful two-track share-link handoff are distinct cases |
| Favorites/Global Player | Playback, station-to-track artwork and ambiguous-match fallback | Read-only browsing/search passed; no matching physical result found |
| Rename comparison | Original/restored name comparison in official app | Speaker rename and restoration passed; do not repeat that operation wholesale |

Keyboard evidence is credited for six pages at both sizes: observed/reached
controls per size were Now 17/17, Browse 30/30, Queue 4/4, Rooms 28/28, Sound
11/11 and System 16/16; all recorded unreached/clipped-focus lists were empty.
The later 54 interaction cases cover expanded dropdowns, confirmations, errors,
editors and group drafts; the visual alarm defect is fixed and merged. Those
checks are complete. The retained evidence does not certify every possible
source/data-dependent control state; #65's universal composite is not silently
closed, but no specific new general keyboard test was established by this audit.
Source-specific physical gaps belong to the rows above, not a repeated full tour.

The tested Sonos product inventory and Trueplay/Sub crossover limitations are
already recorded. No hardware-inventory task remains for those products.
The listing draft/preview is prepared; final commit-specific marketplace checks
and owner sign-off are outstanding. Upstream work, broader MCP features,
destructive queue restoration and optional extra playlist combinations stay out
of this bounded reconciliation.

Read-back sources: complete current bodies and paginated comments for #2–5,
#17, #48, #58–59 and #65–68; August/September machine-log acceptance sections;
ACCEPTANCE_TESTS, Apple handoff report; retained `c4949af` keyboard-tour JSON and
September 8 interaction/visual reports; #131/#132 reviews, CI and platform report.
Private source snapshots are retained at `release48/2026-09-08-reconciliation`.

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
