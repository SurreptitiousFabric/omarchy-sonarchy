# Contributing

Keep changes local-first, keyboard-accessible, theme-native, and safe on a
household that may be playing audio. Do not add credentials, telemetry, an HTTP
control API, install hooks, or privileged operations.

## Environment

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
bash -n sonarchy-backend.sh
bash tests/qml/run-component-tests.sh
mise exec -- shellcheck sonarchy-backend.sh tests/qml/run-component-tests.sh
/usr/lib/qt6/bin/qmllint BarWidget.qml LiveService.qml Service.qml SonarchyContentState.qml SonarchyNowPage.qml SonarchyBrowsePage.qml SonarchyRoomsPage.qml SonarchySoundPage.qml SonarchySystemPage.qml
```

QML lint may report unresolved `qs.Commons`/`qs.Ui` imports when invoked outside
the running shell's module context; syntax failure or a nonzero exit is not
acceptable. After a shell restart, inspect the user journal for this plugin's
QML/runtime errors.

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

## Sonos testing

Unit tests must fake speaker mutations. Live smoke tests should be read-only:
discovery, details, content listing, alarms listing, and library status. A test
that changes volume, playback, groups, names, queues, playlists, alarms,
sources, or device settings requires the household owner's explicit approval.

## Pull requests

Explain user-visible behavior, security/network changes, test evidence, and
the rollback. Update `CHANGELOG.md`, privacy/capability docs, and the marketplace
declaration whenever the behavior they describe changes.
