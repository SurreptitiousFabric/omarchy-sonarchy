# ADR 0003: bounded Python runtime support

Status: proposed for acceptance with issue #73.

## Decision

Support stable CPython 3.14.x, with a declared floor of 3.14.0. The exact
development/CI target is the project `.mise.toml` pin (3.14.7 at this decision).
Do not interpret a declared floor as tested evidence: only 3.14.7 has current
suite evidence; issue #75 must add the floor/current compatibility gate.

Accept stable patch releases within 3.14 without requiring a new product
support decision. Reject older minors, prereleases, alternative implementations
and future minors before bootstrap/application imports. Future support requires
reviewed dependency locks, source/import checks and passing applicable tests.
No unsupported-interpreter override or bundled runtime is introduced.

The guard is dependency-free and uses old syntax so unsupported interpreters
can print a useful stderr diagnostic rather than an application syntax error.
Both shell launchers invoke the same guard in isolated, no-site mode. The MCP
guard writes nothing to stdout, preserving protocol framing.

## Evidence and rationale

- Current backend and MCP sources use unparenthesized multiple-exception
  handlers, a Python 3.14 syntax choice. Examples include `apple_catalog.py`,
  `domains/apple_browse.py`, `local_mcp.py` and `sonarchy_mcp/server.py`.
- `tomllib` in the shared MCP contract imposes a Python 3.11 stdlib floor
  without a backport. The application uses conventional synchronous networking,
  threads, dataclasses, pathlib and typing; no essential 3.14-only runtime
  feature was identified in this review.
- Installed locked runtime distribution metadata reports: SoCo >=3.6;
  Requests and urllib3 >=3.10; charset-normalizer and certifi >=3.7;
  idna and xmltodict >=3.9; lxml >=3.8; defusedxml >=2.7 with early Python 3
  exclusions; appdirs and ifaddr have no declared Requires-Python. These
  declarations are not proof of runtime compatibility and do not establish an
  application floor.
- Locked development metadata reports coverage/pytest/iniconfig >=3.10,
  packaging/pluggy/Pygments >=3.9 and Ruff >=3.7. These likewise do not force
  3.14; the project pin and application syntax determine this development target.
- The current syntax, Ruff target, generated locks and development toolchain
  already agree on 3.14. Keeping that minor avoids coupling release readiness
  to an unrequested older-Python backport. It does not establish that Python
  3.14 is fundamental to Sonos control or justify a Go/Rust rewrite.

No dependency version, interpreter installation or Mise pin changes in this
decision. Older-Python support would require a separately justified task and
its own lock/import/behavior evidence.

## Upgrade and verification consequences

- #75: test 3.14.0 and the exact current target; keep missing wheels/lock failures
  visible. Do not claim future-minor support before actual validation.
- #74: bind environment reuse to interpreter compatibility and dependency
  health. Compatible patch releases do not inherently require rebuilding;
  changed minor/ABI or missing imports must not reuse a broken environment.
- #60: a real system-Python/Omarchy upgrade remains separately approved lifecycle
  acceptance. Synthetic guards do not prove that upgrade path.
- Policy tests cover lower/current/future minors, final versus prerelease,
  implementation identity, stderr-only diagnostics and both launchers stopping
  before setup. Running those tests under 3.14.7 does not test the 3.14.0 floor.

Rolling-distribution availability is not guaranteed. If Omarchy advances beyond
the accepted minor, the launcher fails clearly until compatibility is reviewed;
it must not silently run unvalidated code or downgrade the user's system Python.
