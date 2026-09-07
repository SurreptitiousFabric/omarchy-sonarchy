# Checked browse boundary

The Mypy pin in `requirements-dev.in` and the generated development lock support
the repository's Python 3.14 targets. This is a narrow maintainability pilot
(#77), not whole-repository type safety or physical-device acceptance. No runtime
typing framework is required; the declarations use the standard library.

Run `mise exec -- python -m mypy --config-file pyproject.toml`. Both exact-target
Python CI jobs must pass this gate and the runtime suite. Install the locked
development dependencies as described in [CONTRIBUTING.md](../CONTRIBUTING.md).

## What is checked

- `sonarchy_mcp_contract.py` owns the shared declarations alongside the existing
  required/optional field contracts. `BrowseWireArguments` describes routing
  after MCP validation: `roomUid` is a string (empty for room-free Apple browse),
  while `storefront` may be absent but must not be `None` when present. The raw
  term, limit and context remain `object`, not falsely validated values.
- `sonarchy_mcp/browse.py` runs the existing MCP routing checks before the
  server hands an ordinary dictionary to its generic socket transport. Invalid
  kinds, room values and explicit storefronts still fail at runtime. The server
  retains its independent tool/permission/field checks.
- `domains/browse.py` constructs `BrowseRequest` only after the existing backend
  field, room, non-empty kind, finite-number limit and explicit storefront checks.
  Term conversion and integer limit normalization are unchanged. `BrowsePort`
  checks the actual dispatch arguments. A missing storefront is `None` inside
  the request; it is not a new wire field or an empty-string country code.
- `domains/apple_browse.py` constructs required, checked song fields. Artist,
  album and duration may be unknown (`None`); explicitness is one of `cleaned`,
  `explicit`, `notExplicit` or `unknown`. Discriminated artist/album/song items
  keep the song type through the Apple result collection, so a checked consumer
  can narrow on `media_kind == "song"` and retain the structured field types.

The backend paths above are under `sonarchy_backend/`. The complete selected
module list and strictness settings live in `pyproject.toml`. Imported project
signatures are retained with Mypy's `follow_imports = "silent"`; diagnostics in
other modules are outside this pilot. Imports are not globally skipped or
replaced with `Any`, and no new blanket casts or ignores suppress browse errors.

## Runtime ownership and limits

Types are not validators. Both MCP and backend runtime checks remain necessary,
including the independently enforced field sets and exact room/storefront
rules. A `BrowseRequest` annotation does not make directly constructed instances
trusted; production dispatch uses `parse_browse_request`.

Context remains opaque (`object`) until the existing source-specific library
validator handles it. Other sources' existing treatment of context is unchanged.
The controller facade's matching context annotation reflects that fact without
changing selection, discovery or provider calls. Unsupported browse kinds still
fail at the existing source-dispatch boundary.

Provider transport and SoCo-shaped objects remain dynamic internally. The song
producer receives `Mapping[str, object]` and explicitly normalizes untrusted
metadata before constructing a typed result: malformed duration is unknown, not
coerced; unknown explicitness is not silently labeled clean. These types do not
prove catalog availability, recording identity or the truth of provider metadata.

Generic protocol/result dictionaries, result-size bounding and JSON serialization
remain outside the static guarantee. Do not cast data read from a socket to a song
type just because the producing function is annotated. Existing real
MCP → Unix socket → protocol → controller → domain tests verify room/storefront
behavior and song fields across that dynamic path, faking only external provider
and device access. This pilot adds malformed-provider and invalid-limit checks
on the same path; it does not perform live catalog or household requests.

## Keeping the gate meaningful

`tests/test_browse_types.py` runs the locked checker against the selected slice,
checks inferred consumer types, and requires invalid room/storefront optionality,
explicitness and song-kind examples to fail. Temporary Mypy shadow files also
remove a required field or replace duration with text in the actual song producer,
and pass a string limit at the actual port call. Each must fail for a relevant
type diagnostic, without changing production files or executing the examples.

Keep those controls and the runtime cross-layer tests when evolving this boundary.
A checker outage, missing dependency, syntax/configuration failure or skipped
gate is not a successful type check. Broader typing, protocol schemas, new runtime
validation policy and dependency upgrades require their own bounded scope.
