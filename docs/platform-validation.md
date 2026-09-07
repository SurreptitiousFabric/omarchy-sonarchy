# Required platform release-host job

Run `mise run validate-platform` from a clean exact candidate checkout on the
Omarchy release host with the repository's Mise Python and locked development
environment already provisioned. The task installs nothing, does not enable
the plugin, does not start its backend and does not restart the shell. It runs
read-only manifest validation, static lint, and isolated offscreen component
tests. Do not run unreviewed pull-request code on a personal release host.

This is an explicit automated release-host job, not a GitHub-hosted Ubuntu
platform check. Do not attach this public repository to an unattended personal
self-hosted runner. The maintainer triggers the task after reviewing the exact
candidate, and again whenever the candidate or platform changes.

## Platform and evidence

The reference host at introduction has omarchy-dev
`4.0.0.r6589.gdec29fa-1`, quickshell-git `0.3.0.r20.g28771c7-1`,
qt6-base `6.11.2-3` and qt6-declarative `6.11.2-1` (aarch64).
This is a recorded validation platform, not a claim that arbitrary older or
future combinations work. Provision/reproduce that package snapshot separately;
the job never installs or upgrades host packages. Platform drift requires a
fresh reviewed report. A different supported release target needs its own run.

The single JSON report records the clean Git candidate SHA, installed package
versions and a digest of the actual installed shell QML/module declarations.
Attach that output to #64 and the release-readiness issue/PR for the candidate.
The process exit is 0 only for `passed`, 1 for `failed`, and 2 for `incomplete`.
Archive failed/incomplete evidence too; neither permits publication. There is
no platform pass implied by skipped host tests in generic Python CI.

## Required stages

- The actual `omarchy plugin validate` command checks the manifest/tree.
- All shipped root QML files are linted with the actual installed `qs` shell
  modules and Qt/Quickshell imports, `--ignore-settings`, `--import error` and
  `-W 0`. Both exit code and per-file success must agree. No visual stubs, warning
  baseline or category suppression are used for lint.
- Existing component tests run offscreen, retaining their narrowly scoped
  visual-only theme stubs and actual installed PanelSlider. These tests do not
  claim full live-shell behavior.
- Real-tool controls require a valid real-import probe to pass and malformed
  manifest/QML, missing import and an intentionally failing component to fail.
  The control subprocess clears inherited `PYTEST_ADDOPTS` so host collection
  or selection preferences cannot skip these required checks.
  The popup layout regression runs the production container in a real Quickshell
  window with installed host controls, content insets and fitting functions.
  Page bodies and device data are fixtures; private HOME/XDG paths isolate theme
  reads, and no backend is created. It checks narrow/wide geometry, visible
  messages, empty state and a smaller available screen height.
  The native-focus regression delivers real Qt Tab/Shift+Tab events in an
  offscreen Quickshell window with installed buttons and key catcher. It uses
  production focus observation, dispatch and Now-page scrolling, with a small
  deterministic page body. It checks clipped control recovery, dropdown child
  and editor ownership, and fixed controls without creating a backend or
  sending speaker actions.
  It also requires the ADR 0004 type-contract probes: actual declaration lint,
  live font-role bindings and readonly behavior, popup text existence/live
  updates/writability with drift negative controls, and the named-role prototype.
  The [spacing-role probes](spacing-role-contract.md) also require real-import
  reproduction, actual live scaling/override/readonly semantics and drift controls.
  A failing contract probe fails the required control stage. These isolated
  probes do not instantiate the live theme singleton or claim theme-reload acceptance.

Missing tools, malformed/incomplete lint output, timeouts or dirty/mismatched
candidates cannot report success. Each child command has a two-minute timeout.
The report excludes raw subprocess output and host configuration; lint evidence
contains only candidate-relative file names, lines, categories and severity.

## Existing blockers

The strict gate exposes pre-existing warnings tracked in #87 (shared UI), #88
(browse/queue) and #89 (remaining pages/service). Their cleanup is separate from
gate infrastructure. Do not weaken the gate to obtain green release evidence.
Until all stages pass on the combined candidate, #64 acceptance remains open.
