# Keyboard interaction acceptance — 2026-09-08

Candidate: `c4949affc42d3a0bba38cc740b1fdbab0eb6527c`.
Production source was unchanged. Narrow 360×520: **27 checks passed**.
Wide 620×820: **27 checks passed in a fresh window**. Total: **54 passed cases**.

The production panel content, page components, focus functions and keyboard
routing were loaded with the installed Omarchy controls in an isolated Qt
window. A recording fake service replaced device access. QtTest delivered
keyboard events directly inside that window; no global keystrokes or desktop
shell were used. Network access was isolated, with private HOME/runtime and a
read-only filesystem outside the evidence directory.

| Interaction | Checked behavior |
| --- | --- |
| Dropdowns | Enter opens; Down navigates; Escape closes without selecting or closing the panel. Room, sleep, browse, system, alarm room/recurrence/duration/sound and source-room selectors covered. |
| Local selection | Duration selection updates only the alarm draft; keyboard system-section selection displays source controls. No alarm save. |
| Confirmations | First Enter arms without dispatch; the production five-second timer expires without dispatch. Queue clear/remove, playlist delete/item-remove, Play if queue empty, and alarm delete covered. No second destructive press. |
| Error | Enter on Dismiss clears the fixture error without dispatching a device action. |
| Editors | Escape releases alarm-time, library/Apple/Global search and playlist-name editor focus without submission. Rename typing then Escape restores the original name. |
| Group draft | Keyboard staging changes the local draft; Cancel restores original staged membership without applying it. |

Both accepted size runs recorded zero action dispatches. Retained private evidence is in
`~/.local/share/sonarchy-private-evidence/issue65/2026-09-08-interactions/`, including
runner, fixture, source/control hashes and logs.

Initial harness iterations had incomplete fixture data, an overly long private
IPC path, an outdated label and an ambiguous room-button selector. Those were
corrected in the harness and are not reported as product defects or acceptance
passes. The combined-size run completed all 27 narrow cases and 26 wide cases, then
failed its final wide section-selection assertion after the fixture reset page
state while the host dropdown retained its previous selection. A fresh-window
focused check passed, followed by a complete fresh wide run with 27 passes and
zero dispatches. The failed combined-run assertion is retained, not counted as
a pass. The reusable runner now starts each size independently. This does not
claim host dropdown synchronization after arbitrary external state resets.

The accepted fixtures load without QML binding errors. The offscreen
platform's unsupported-window-mask warning limits visible rendering claims.

This accepts the enumerated keyboard interactions against fixture data. It does
not claim new physical-device behavior, real rejection recovery, second-press
mutation execution, or a new installed Wayland visual tour. Prior real-popup
layout/focus passes remain valid. There are no separate modal Dialog components
in the inspected Sonarchy sources; confirmations are inline and dropdowns use
the host popup component.
