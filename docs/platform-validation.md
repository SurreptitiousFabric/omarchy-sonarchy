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
  `-W 0` to retain every diagnostic. The owner-approved September 8 baseline
  in `scripts/qml-warning-baseline.json` allows the 117 documented upstream
  type-metadata warnings. Matching requires file, source line, column, category,
  severity, message and occurrence count; line-number shifts alone are harmless.
  Removed warnings are allowed. New/changed/additional warnings, all errors,
  abnormal process exits and unexplained file failures still fail. No category
  suppression or lint stubs are used. Reports retain diagnostics and separately
  count accepted warnings and unexpected diagnostics. Baseline changes require
  explicit review; do not regenerate it automatically to obtain a pass.
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
  The room-volume row regression loads the production row and slider with
  installed controls. It checks narrow/wide content widths, base/font scaling,
  both mute glyphs, control bounds and usable label/slider space using device
  fixtures; no speaker actions are sent.
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

## Owner-approved warning policy — September 8, 2026

Zero warnings is no longer a release requirement. Waiting for upstream type
metadata fixes is not required. This supersedes the previous strict zero-warning
policy and the upstream-dependent release requirement in ADR 0004.

The baseline covers existing anonymous font/popup/spacing role and bar-host
property declarations, plus Quickshell's QProcess::ExitStatus metadata warning.
The warnings remain visible in reports. Manifest, component and required control
stages must still pass, as must QML validation under this explicit baseline.
Final clean exact-candidate acceptance remains required; a local lint-stage pass
alone is not a complete release-host pass or permission to publish.
