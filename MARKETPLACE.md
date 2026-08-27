# Marketplace release checklist

The source tree is being prepared for the community Omarchy plugin marketplace,
but its current status is **HOLD**. Publishing and submitting are external
actions that require every applicable gate in
[`ACCEPTANCE_TESTS.md`](ACCEPTANCE_TESTS.md) plus the maintainer's explicit
approval.

## Repository contract

- Public GitHub repository with this directory at its root
- Exactly one root `manifest.json`
- Root README with install, keyboard use, configuration, and removal steps
- Root MIT `LICENSE`, security policy, privacy policy, third-party notices, and
  changelog
- Globally unique, lowercase plugin ID `io.github.surreptitiousfabric.sonarchy`
- No symlinks, bundled binaries, submodules, install hooks, or privileged files
- Optional root preview image only if one is later created and reviewed

The public source repository is
<https://github.com/SurreptitiousFabric/omarchy-sonarchy>. Re-check the live
registry for an ID collision immediately before publishing because marketplace
acceptance makes the ID effectively permanent.

## Declared review outcome

The current v3 deterministic security baseline requires human review for
`package-manager`: the non-interactive, hash-locked pip download from PyPI. A
local scan reports no findings and no other automated capabilities. Reviewers
should additionally inspect the declared installer-like first-run private venv
creation even though the scanner does not currently emit `installer` for the
root launcher.

There should be no blocking finding for curl-pipe-shell, remote git execution,
unhashed runtime packages, shared `/tmp` privilege state, sudoers changes,
bundled executables, privilege escalation, or system-service management. See
`CAPABILITIES.md`; do not describe a review-required result as “certified” or
“sandboxed.”

## Release commands

Run from the repository root:

```bash
omarchy plugin validate .
bash -n sonarchy-backend.sh
bash tests/qml/run-component-tests.sh
mise exec -- shellcheck sonarchy-backend.sh tests/qml/run-component-tests.sh
mise exec -- python -m pytest -q
mise exec -- python -m ruff check .
mise exec -- python -m ruff format --check .
mise exec -- python -m coverage run -m pytest -q
mise exec -- python -m coverage report
/usr/lib/qt6/bin/qmllint BarWidget.qml LiveService.qml Service.qml SonarchyAlarmEditor.qml SonarchyNowPage.qml SonarchyBrowsePage.qml SonarchyRoomsPage.qml SonarchySoundPage.qml SonarchySystemPage.qml
```

Also run the marketplace's deterministic baseline against the exact release
commit, audit Python dependencies, check file modes/symlinks, and perform only
read-only Sonos smoke checks unless the test household owner explicitly
authorizes mutations.

## Submission guardrail

Before opening the marketplace issue, the maintainer must review and explicitly
approve:

1. every applicable real-device and final gate in `ACCEPTANCE_TESTS.md`;
2. the public repository owner and URL;
3. the exact release commit SHA;
4. the permanent plugin ID, category, tags, and optional preview;
5. the scanner result and declared review capabilities;
6. the complete issue title and body.

Automation or an AI assistant must not create the repository, publish a
release, or submit the marketplace issue without that approval.
