# Marketplace release checklist

The source tree is being prepared for the community Omarchy plugin marketplace,
but its current status is **HOLD**. Publishing and submitting are external
actions that require every applicable gate in
[`ACCEPTANCE_TESTS.md`](ACCEPTANCE_TESTS.md) plus the maintainer's explicit
approval.

The [owner-reviewable preparation package](docs/marketplace-preparation.md)
contains the proposed title, exact-format draft body, demo preview and dated
rules/ID checks. Every submission attestation remains unchecked pending owner
confirmation. Preparation is not publication or a release-gate waiver.

## Repository contract

- Public GitHub repository with this directory at its root
- Exactly one root `manifest.json`
- Root README with install, keyboard use, configuration, and removal steps
- Root MIT `LICENSE`, security policy, privacy policy, third-party notices, and
  changelog
- Globally unique, lowercase plugin ID `io.github.surreptitiousfabric.sonarchy`
- No symlinks, bundled binaries, submodules, install hooks, or privileged files
- Optional root `preview.png`: isolated demo data and test visuals; provenance
  and owner-review limits are recorded in the preparation package

The public source repository is
<https://github.com/SurreptitiousFabric/omarchy-sonarchy>. Re-check the live
registry for an ID collision immediately before publishing because marketplace
acceptance makes the ID effectively permanent.

## Declared review outcome

The declared `package-manager` capability is the non-interactive, hash-locked
pip download from PyPI and requires review under the recorded baseline policy.
Run a fresh exact-commit baseline before submission; a historical local scan is
not current verification. Reviewers should also inspect the installer-like
first-run private venv creation independently of which capabilities that scan
emits for the root launcher.

There should be no blocking finding for curl-pipe-shell, remote git execution,
unhashed runtime packages, shared `/tmp` privilege state, sudoers changes,
bundled executables, privilege escalation, or system-service management. See
`CAPABILITIES.md`; do not describe a review-required result as “certified” or
“sandboxed.”

## Release commands

Run from the repository root:

```bash
mise run validate-platform
bash -n sonarchy-backend.sh sonarchy-mcp.sh tests/qml/run-component-tests.sh
bash tests/qml/run-component-tests.sh
mise exec -- shellcheck sonarchy-backend.sh sonarchy-mcp.sh tests/qml/run-component-tests.sh
mise exec -- python -m pytest -q
mise exec -- python -m ruff check .
mise exec -- python -m ruff format --check .
mise exec -- python -m coverage run -m pytest -q
mise exec -- python -m coverage report
```

Also run the marketplace's deterministic baseline against the exact release
commit, audit Python dependencies, check file modes/symlinks, and perform only
read-only Sonos smoke checks unless the test household owner explicitly
authorizes mutations.

The [platform validation job](docs/platform-validation.md) must report `passed`
for the exact clean candidate. Attach its JSON output to the release-readiness
issue/PR before owner approval. A failed or incomplete report keeps release on
HOLD, even when GitHub's generic Python CI is green.

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
