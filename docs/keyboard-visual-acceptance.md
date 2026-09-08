# Headless Wayland visual acceptance — 2026-09-08

**Result: alarm confirmation-focus defect fixed, retested and merged in PR #131.**
Candidate: `c4949affc42d3a0bba38cc740b1fdbab0eb6527c`.
The original visual test changed no production code. The repair below merged as
`b0ef30328e8bb7eac5f329031cd1255f0ff3e559`; the installed plugin is unchanged.

## Confirmed defect

In System → Alarms, focus the saved alarm's Delete action and reveal it fully.
Press the action once to arm its confirmation, without deleting the alarm.
The confirmation notice increases the page's content height. The focused action
moves below the clipped viewport and is not fully revealed again.

| Configured popup | Before arming | After arming | Focus |
| --- | --- | --- | --- |
| 360×520 | 33 of 33 logical pixels visible | 5 of 33 visible | Retained by Delete |
| 620×820 | 33 of 33 logical pixels visible | 22 of 33 visible | Retained by Delete |

Screenshots independently confirm the clipped action. This is a presentation
failure, not a failed alarm operation: only the first confirmation press ran,
and the recording service received zero mutations. The owner's successful
manual alarm test remains passed.

The relevant production paths are `SonarchySystemPage.qml`'s `arm`, confirmation
notice and `ensureVisible`, and `BarWidget.qml`'s focus-change observer. Existing
focus scrolling handles a newly focused control; this observation concerns
layout growth while the same control retains focus. A repair should keep that
control fully visible after layout settles, without changing focus or dispatching
an action. Verify both sizes, original five-second expiry, and zero mutation on
the first press. Inspect the equivalent Browse/Queue confirmation paths within
that focused repair; their shared mechanism alone is not evidence they failed.

## Repair and regression result

The original failure above is superseded by the September 8 repair in PR #131.
`SonarchySystemPage.qml` now observes confirmation-time content-height changes
and reveals the same focused descendant after the Column settles. Focus outside
the scrollable page is ignored. The confirmation/action logic is unchanged.

The new `ConfirmationFocusProbe.qml` regression failed on the original code at
5/33 and 22/33 pixels and passes with the repair. It exercises actual keyboard
Return presses and checks full visibility, retained focus, five-second expiry,
zero deletion on first press/expiry, exactly one fake deletion on a deliberate
second press, and unchanged fixed-header focus/scroll during page growth.

The complete production panel was then rebuilt in the private Wayland sandbox:

| Configured popup | Before arming | After arming | Focus / device writes |
| --- | --- | --- | --- |
| 360×520 | 33/33 pixels | 33/33 pixels | Retained / zero |
| 620×820 | 33/33 pixels | 33/33 pixels | Retained / zero |

Both repaired screenshots were visually inspected. Evidence is retained as
`{narrow,wide}-alarm-fixed-{before,after}-arm.{png,json}` and `fix-results.json`
in the same private evidence directory. Historical failure evidence is preserved.
Browse and Queue confirmation placement was inspected; those pages also insert
notices into their columns, but this alarm regression does not establish a new
pass or failure for their other content variants. Their earlier credited checks
remain valid. This repair resolves the recorded alarm blocker; it does not close
the entire composite #65 acceptance scope or claim an installed-build test.

## Visual coverage credited

Thirty-six page/expanded-state screenshots were captured across both configured
sizes, with separate before/after confirmation probes. Visually inspected cases
include page navigation, queue and saved-playlist rows, room/session labels,
room/browse/recurrence/duration menus, alarm-editor bottom controls, queue-clear
confirmation, source controls, device information, empty library/sound states,
and error presentation. No other defect was established in these inspected cases.
The entire capture inventory is retained; capture alone does not prove that each
image or every possible live-data variant was accepted.

The narrow duration menu extends beyond the card but remains fully visible on
the virtual display. A card-only screenshot cropped the menu; a full-display
capture disproved menu clipping. Do not file that crop artifact as a defect.

The prior 54 isolated keyboard interaction passes remain credited. They checked
arming/expiry and input behavior, but did not assert the focused control's
post-arming visible rectangle; this visual finding does not erase those passes.

## Method and limits

The complete production `BarWidget.qml` was copied under a non-conflicting type
name and loaded unchanged with the installed Omarchy `KeyboardPanel`, controls,
page components and theme. A minimal private bar host supplied the host contract.
Read-only MCP snapshots supplied room/group, queue and playlist content. Alarm,
error and optional-detail states were fixtures; this does not verify real alarm
rejection, active TV format, sound capability discovery, media artwork or current
track metadata. External artwork requests were blocked by network isolation.

A private labwc/wlroots headless compositor rendered a 1600×1000 software display.
Its packages were extracted into the evidence directory and verified against
local package-database SHA-256 values; nothing was installed system-wide.
Bubblewrap removed host `/run` and `/tmp`, used private HOME/XDG paths, isolated
PID/IPC/network namespaces and supplied no input/GPU devices, host display socket,
Hyprland instance signature or session bus. Screenshots and UI operations used
only this private display. This is actual Wayland/layer-shell rendering, with a
labwc compositor rather than a new acceptance claim about Hyprland-specific
focus priming, multi-monitor dismissal or the owner's installed `8d93804` build.

Evidence, package provenance, runners, read-only input data, screenshots and
geometry are private under
`~/.local/share/sonarchy-private-evidence/issue65/2026-09-08-headless/`.
No remote issue/comment was published by this local acceptance record.
