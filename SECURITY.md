# Security

## Trust model

Like every Omarchy shell plugin, this code runs unsandboxed as the desktop user.
The plugin directory, current user account, Omarchy shell, Python interpreter,
and installed dependency environment are trusted. The local network, speaker
metadata, service responses, artwork URLs, search text, and stale UI state are
treated as untrusted.

Anyone able to run code as the same desktop user can already send equivalent
Sonos UPnP commands. This plugin is not an authorization boundary between local
processes.

The local MCP bridge still applies least privilege against accidental or
malicious same-user clients. A non-blocking owner lock is acquired before Sonos
contact. Its Unix socket requires safe owner/mode/type checks and verified Linux
same-UID peer credentials. The backend enforces a fixed operation allowlist;
model-visible tool annotations are not authorization.

## Network surface

Expected traffic is limited to:

- SSDP discovery and a rate-limited attached-network fallback scan;
- UPnP/HTTP requests to private, unicast IPv4 Sonos speakers, normally TCP 1400;
- a Sonos event callback listener on the attached interface, TCP 1400–1499;
- explicit HTTPS Apple catalog searches and optional, popup-scoped radio-track
  artwork matching against the same public endpoint;
- one local Unix-domain control socket below `XDG_RUNTIME_DIR`, never TCP/HTTP;
- Global Player and compatible Favorite/TuneIn traffic requested by the user;
- allowlisted public HTTPS artwork and exact speaker-local HTTP artwork on 1400;
  bounded, no-redirect availability probes prevent missing local art from
  reaching Qt's raw image-transfer logger.

The event callback is not a control server. It accepts only `NOTIFY` requests
whose subscription ID exists and whose source address exactly matches that
subscription's private IPv4 speaker. Sequence and subscription headers are
bounded and validated. Bodies are capped at 512 KiB, sockets time out after
three seconds, at most 16 handlers run concurrently, and pending events are
capped at 1,024. A valid event only wakes an authoritative speaker refresh. Do
not port-forward these ports or expose the computer to an untrusted LAN.

There is no REST API, browser UI, or listener on port 8000.

## Defensive measures

- Runtime packages have exact versions and hashes. Pip runs with an allowlisted
  environment and no download cache; configuration, extra indexes, link
  sources, Python startup hooks, and interactive prompts are excluded. The
  explicit index is HTTPS PyPI, dependency discovery is disabled, and only
  wheels (not remote source builds) are used.
- The managed venv, lock, state, and cache paths reject relevant symbolic-link
  targets. State and caches use unique, exclusive temporary files, `fsync`, and
  atomic replacement with owner-only modes.
- Cached and explicit speaker targets must be private, unicast IPv4 addresses;
  loopback, link-local, multicast, public, reserved, and unspecified targets
  are rejected.
- A line-in source must be visible in the selected speaker's Sonos household.
- External artwork requires HTTPS on port 443 and a small hostname allowlist.
  The MyTuner station fallback permits only `static.mytuner-radio.net`, not its
  parent domain or arbitrary subdomains. Speaker artwork must use the exact
  speaker address and port 1400.
- Apple catalog responses do not follow redirects and are capped at 1 MiB.
  Automatic radio matching requires both title and artist, rejects weak or
  conflicting catalog candidates, runs outside the persistent control process,
  and keeps at most 128 positive or negative results in memory.
  TuneIn playlist reads use trusted hostnames and a 256 KiB cap.
- Speaker-supplied XML metadata is parsed with `defusedxml`; entity expansion
  and external entity access are forbidden.
- Persistent-backend protocol lines are capped at 64 KiB. Browse responses
  pre-bound display fields and, when necessary, return a deterministic exact
  item prefix measured against the complete worst-case result envelope. They
  never partially truncate identities or artwork URLs, and explicitly report
  byte-budget reduction while preserving the provider total.
- QML process calls use argument arrays and small allowlisted environments;
  user text is never interpolated into a shell command. Search terms,
  room/playlist names, IDs, alarm fields, Boolean settings, and numeric ranges
  are validated again in Python.
- Queue and playlist item mutations re-read the authoritative item and compare
  its opaque ID before changing it. The UI requires a timed second activation
  for item removal, queue clearing, and playlist/alarm deletion.
- AI-curated playlist writes accept only one to 25 exact Apple song records.
  Each HTTPS URL must use the exact `music.apple.com` host without credentials
  or a non-standard port, and pinned SoCo must independently canonicalise it as
  the same bounded decimal `song` identity. No generic URL, URI, UPnP, SoCo,
  shell, or protocol-execution operation is exposed.
- Apple-create plan tokens are random, opaque, memory-only, process-local,
  single-use, and valid for no more than two minutes. They bind authoritative
  room UID, coordinator and hashed household identity, complete playlist
  inventory fingerprint/count, new name, direct capability, duplicate policy,
  ordered reviewed songs, expiry, and nonce. Queue contents,
  source, position, media, transport, volume, and mute are deliberately absent.
  The general snapshot revision is also absent because unchanged background
  polls increment it; execution instead re-captures every material bound fact.
  Tickets are claimed before the first playlist mutation and are not a
  replacement for explicit client/user approval. Rejections before ticket
  claim do not stale a valid token; every accepted execution attempt consumes
  it whether the operation succeeds or fails.
- Exact-playback plan tokens use the same single process-local ticket store but
  bind a separate operation: exact room/coordinator/household, complete
  standalone topology, online state, volume/mute, transport/source,
  capabilities, exact `SQ:<id>`/title, complete playlist content fingerprint,
  bounded preview/first item, and complete queue fingerprint/length/position.
  Preflight accepts only volume at most 20, stopped or paused transport, a
  confirmed queue or no active source, 1–25 playlist items, and at most 100
  combined items. Execution re-reads all facts before the first mutation.
- Exact-playlist playback reuses the existing playlist domain helper. It
  appends once, starts once at the returned first appended position, never
  clears or replaces the queue, and never changes volume, mute, topology,
  source settings, or playlist contents. Post-write reads verify the preserved
  queue prefix, appended order, current item/position, playing queue transport,
  and unchanged bound state.
- Playback partial failures expose only a controlled phase and bounded hashes,
  positions, counts, and booleans. If append succeeded, entries may remain.
  There is no automatic retry, removal, reconstruction, or issue #19 rollback.
  Raw exceptions, addresses, item/resource URIs, DIDL, SOAP, service metadata,
  backend tokens, and MCP handles are never returned.
- Exact-song persistence creates an empty Sonos Playlist through the normal
  SoCo API and appends directly to that exact saved queue. It never calls queue
  or playback methods and does not trigger a general playback snapshot refresh.
  The Apple-only adapter revalidates an exact song link, fixes every provider
  and saved-queue field internally, and uses SoCo DIDL objects for XML escaping.
  It fails closed on any SoCo version or pinned Apple-envelope drift. No generic
  URI, DIDL, SOAP, service, or command path is exposed.
- Failure cleanup deletes a partial playlist only by a validated new `SQ:<id>`
  returned by that invocation and authoritatively reopened with the expected
  title. Title-only ownership is forbidden. Missing or ambiguous identity
  leaves every candidate untouched and reports required cleanup. Failure
  results contain controlled phases and bounded cleanup status, never raw
  exceptions, addresses, DIDL, provider URIs, credentials, or tokens.
  Apple identity evidence must occupy a complete canonical or pinned Sonos item
  ID, the leading song token of an expected `x-sonos-http:` or
  `x-sonos-https:` resource, or the complete pinned Apple HLS-static
  saved-playlist resource form. The latter requires the Apple service identity
  derived from the pinned service type, bounded saved-resource fields, and the
  exact HLS protocol type. Other providers, unanchored metadata, extra query
  fields, and query-string-only catalogue IDs are never authoritative.
  Catalogue identity validation is not evidence that the household Sonos Apple
  service will accept the item. A direct add rejection stops immediately;
  Sonarchy never retries or substitutes another recording, edition, remaster,
  live version, or catalogue ID.
- Playlist creation requires a free slot below the 100-item bounded inventory;
  post-create verification and exact-ID cleanup can inspect one bounded extra.
  Preflight reviews use unescaped UTF-8 and must fit the complete 64 KiB
  protocol result envelope. An oversized review discards its unpublished ticket.
- Authoritative snapshots are subject to the same complete-line limit. An
  oversized snapshot is not cached or partially emitted; it is replaced by a
  fixed degraded snapshot with no target-derived write capabilities, and the
  backend remains available for later bounded refreshes.
- Successful playlist results return the bounded reviewed title, artist, and
  album only after authoritative metadata comparison. Raw provider metadata and
  optional Sonos item IDs are not echoed. Success explicitly reports no queue or
  playback mutation. A physically observed Sonos album display rewrite may omit
  commas and append the literal `(Deluxe Edition)` qualifier; that single
  normalization is accepted only after exact Apple catalogue identity, title,
  and artist verification. Other album names and edition labels fail closed.
- Alarms returned to QML contain a human label, not their potentially
  credential-bearing program URI or service metadata.
- No service or account credentials are requested, logged, or stored.

There is no TCP/HTTP MCP listener or second AI-owned Sonos controller. The
stdio MCP adapter is a same-user client of the Quickshell-owned Unix socket and
never constructs a controller or fallback backend.

## Dependency and release policy

`requirements.lock` is generated for Python 3.14 with hashes and reviewed as a
source change. Release validation includes the Omarchy manifest validator,
Python/QML static checks, unit tests, dependency auditing, a symlink/file-mode
check, and the marketplace deterministic baseline when available.

SoCo uses Sonos's local UPnP interfaces and is not the official Sonos app.
Local Sonos control is generally unauthenticated and unencrypted by the
speakers themselves; use this plugin only on a trusted home network.

## Reporting

Use the public repository's **Security → Report a vulnerability** form so the
report remains private. If private vulnerability reporting is unavailable,
contact the marketplace maintainer privately before sharing details. Never put
tokens, passwords, pairing codes, private room metadata, or raw diagnostics in
a public issue.
## Local MCP threat model

- A second backend fails its non-blocking process lock before controller
  construction or discovery and cannot remove the active owner's socket.
- Runtime, lock, socket, and configuration symlinks fail closed. Wrong socket
  type, owner, mode, or unverifiable peer credentials are rejected.
- Same-user clients remain confined to the backend read allowlist plus
  independently permissioned exact playlist-create and exact playlist-play
  writes. `playlist-create` never authorizes playback. Raw operation names,
  URI/DIDL/SoCo objects, addresses, service metadata, credentials, and backend
  tickets never enter the MCP contract or logs.
- Per-client routing prevents identical request IDs from crossing clients.
  Controller/application execution is serial, including simultaneous QML and
  MCP requests; authoritative snapshots are broadcast after accepted writes.
- Client count, line/incomplete-buffer size, and pending output are bounded.
  Malformed, oversized, stalled, or disconnected clients are contained and do
  not terminate or block QML. A disconnect after an accepted mutation neither
  cancels nor repeats it; the backend finishes once and broadcasts state.
- Backend restart closes clients, invalidates every ticket, and changes the MCP
  connection instance. MCP restart loses all memory-only handles. Reads may
  reconnect; writes are never replayed and require a new preflight.
- Random plan handles are process-local, short-lived, single-use, claimed before
  mutation, and removed after every attempt. Execution accepts no replacement
  fields. Permission upgrades/downgrades require backend and adapter restart.
- Duplicate room names are returned visibly. Exact stale/missing room UIDs fail
  instead of selecting another room or mutating QML selection.
- Safe structured errors omit raw exceptions and private traffic. The adapter
  does not log handles, tickets, provider metadata, addresses, or socket lines.
- The consent boundary combines default-absent write tooling, independent owner
  opt-in, exact review, a fresh identical post-approval preflight, backend state
  revalidation, single-use execution, and no retry. Playlist create additionally
  has exact-ID cleanup; playlist playback deliberately has no destructive queue
  rollback. The MCP client must obtain current user approval; `approved: true`
  is not independent evidence of human consent.
