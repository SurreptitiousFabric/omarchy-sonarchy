# Contributing

Keep changes local-first, keyboard-accessible, theme-native, and safe on a
household that may be playing audio. Do not add credentials, telemetry, an HTTP
control API, install hooks, or privileged operations.

## Environment

- Stable CPython 3.14.x only, with a declared 3.14.0 floor. Use the exact
  project Mise pin for development. CI runs separate exact-floor/current jobs
  with isolated environments, version assertions, locked imports and the suite.
  Both jobs must pass; unavailable runtime/wheels or incompatible locks are
  failures, not skips. Future minors and prereleases
  require an explicit support decision, not an automatic pin bump. See
  [ADR 0003](docs/adr/0003-python-runtime-policy.md).
- [Mise](https://mise.jdx.dev/) with the repository's trusted `.mise.toml`
- Current Omarchy/Quickshell for QML integration checks
- The external Mise-managed `../.venvs/omarchy-sonarchy`; never install test
  packages into system Python or the plugin's runtime venv. Keeping the venv
  outside the repository also keeps its internal symlinks out of the plugin
  bundle and marketplace validation.

Trust the repository configuration, install its pinned Python, and populate the
project environment from the checked-in hash lock:

```bash
mise trust
mise install
mise exec -- python -m pip install --require-hashes -r requirements-dev.lock
```

Run verification:

```bash
mise exec -- python -m pytest -q
mise exec -- python -m ruff check .
mise exec -- python -m ruff format --check .
mise exec -- python -m coverage run -m pytest -q
mise exec -- python -m coverage report
omarchy plugin validate .
bash -n sonarchy-backend.sh sonarchy-mcp.sh tests/qml/run-component-tests.sh
bash tests/qml/run-component-tests.sh
mise exec -- shellcheck sonarchy-backend.sh sonarchy-mcp.sh tests/qml/run-component-tests.sh
/usr/lib/qt6/bin/qmllint BarWidget.qml LiveService.qml Service.qml SonarchyContentState.qml SonarchyNowPage.qml SonarchyBrowsePage.qml SonarchyRoomsPage.qml SonarchySoundPage.qml SonarchySystemPage.qml
```

QML lint may report unresolved `qs.Commons`/`qs.Ui` imports when invoked outside
the running shell's module context; syntax failure or a nonzero exit is not
acceptable. After a shell restart, inspect the user journal for this plugin's
QML/runtime errors.

CI checks every shipped shell launcher with Bash and ShellCheck. The Python
suite also runs a temporary copy of the MCP launcher from an unrelated working
directory, substituting only `/usr/bin/python3` with the exact test interpreter.
It exercises real stdio and Unix-socket I/O against a fake backend, with private
HOME/XDG directories and no runtime installation or speakers. Negative controls
prove stdout noise and a broken adapter entry point fail the startup assertion.
This is not evidence for the installed system-Python path or live Omarchy startup.

The component interaction tests run offscreen. The slider test uses the
installed Omarchy `PanelSlider.qml` with minimal visual-only theme stubs and
proves wheel/drag routing. The error-state test proves that only an owning
request or explicit user dismissal can clear a correlated request error.

## Dependency updates

Direct runtime requirements belong in `requirements.in`; direct development
requirements belong in `requirements-dev.in`. Regenerate both lock files with
a reviewed version of `pip-compile` under Python 3.14 using
`--generate-hashes --strip-extras`, review the complete diff, run the full test
and audit suite, and never hand-edit generated hashes.

When adding a runtime distribution, review its device-free import target in
`sonarchy_environment.py`. The bootstrap health check validates exact installed
versions from the lock and imports every listed runtime dependency; unknown
distributions or unsupported lock syntax fail closed until reviewed. Its
identity intentionally excludes patch versions but includes implementation,
major/minor, ABI and architecture. Keep the real-import no-network check and
synthetic bootstrap failure/concurrency tests passing.

## Sonos testing

Unit tests must fake speaker mutations. Live smoke tests should be read-only:
discovery, details, content listing, alarms listing, and library status. A test
that changes volume, playback, groups, names, queues, playlists, alarms,
sources, or device settings requires the household owner's explicit approval.

## Pull requests

Every PR must complete `.github/pull_request_template.md`. Do not delete
applicable sections; write `Not applicable` and give a reason where appropriate.

Give the PR one primary user-visible or maintainability objective. List its
intended files or domains and explicit non-goals. List and justify every
cross-cutting change. Unrelated browse, pagination, QML, protocol,
security-boundary, dependency, or infrastructure work requires a separate issue
and PR; do not hide an unrelated repair inside another feature's acceptance
story. Deferred work and newly exposed unrelated defects also require linked
issues rather than being silently absorbed into the active PR.

Settle the issue acceptance criteria and Definition of Done before
implementation. Do not weaken, delete, or reinterpret them merely because the
implementation cannot satisfy them. If the acceptance contract is wrong, stop
and record an explicit owner-approved amendment before continuing.

Map completion evidence to every acceptance criterion. A real defect should
have failing-before and passing-after evidence. Green CI is necessary but not
sufficient. Durable documentation must state required gates, not current suite
totals; exact totals belong only in commit-specific PR evidence or evidence tied
to an immutable release. A large test count is not a substitute for meaningful
boundary coverage.

When a defect can occur between adapter, socket, protocol, application, and
domain layers, a self-authored fake at an upper layer is not sufficient as the
only evidence. Exercise the production path and fake only the lowest practical
external boundary. If cross-layer evidence is genuinely not applicable, say
why.

After exact-head CI, conduct one substantive review round and at most one
in-scope P1/P2 repair round. File out-of-scope findings as separate issues. If
the repair exposes another substantive finding, stop and reassess instead of
entering another review/fix loop.

Preserve the Sonos approval rules above. Fake or device-free evidence must not
be described as physical acceptance; PR evidence must state exactly what was
and was not run. Also explain security/network changes, side effects, partial
failure or rollback, and update `CHANGELOG.md`, privacy/capability docs, and the
marketplace declaration whenever the behavior they describe changes.
