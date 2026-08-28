# AI-curated Sonos Playlists

## Current implementation

Sonarchy can now persist an AI-curated, human-reviewed sequence of exact Apple
catalogue songs as a new **Sonos Playlist**. The deterministic capability lives
inside Sonarchy's existing persistent backend/application path and has two
protocol operations:

1. `playlist_plan.apple.validate` performs a read-only preflight and returns a
   short-lived opaque plan token.
2. `playlists.apple.create` consumes that token once after an explicit
   `approved: true` write decision.

The AI client still owns curation: interpreting the request, choosing exact
catalogue versions, and presenting the ordered review. Sonarchy owns exact
room identity, Apple song/link validation, duplicates, bounds, freshness,
queue safety, Sonos Playlist persistence, playback, verification, and rollback.
Preflight binds a safe SHA-256 fingerprint of the exact current media URI, not
the URI itself. A current `x-rincon-queue:` URI is authoritative `QUEUE` even
when the pinned SoCo coarse classifier says `UNKNOWN`; other unknown sources
remain ineligible.

The initial modes are:

- `save-only`: create and reopen the exact Sonos Playlist, then restore and
  verify the prior queue, position, source, and playing/stopped state.
- `save-and-play`: create and reopen the exact Sonos Playlist, start track 1,
  and leave the approved queue active.

Temporary play without saving is intentionally deferred. Sonos Playlist
creation is create-only: an exact existing name is rejected with a
deterministic suggestion and is never overwritten or deleted.
Rollback removes a partial playlist only through the exact new `SQ:<id>`
returned by this transaction's create call and confirmed in the authoritative
inventory. A matching new title is never treated as ownership. If the create
call might have succeeded without returning an attributable ID, Sonarchy
restores what it can, leaves every playlist untouched, and reports that cleanup
is still required.
Preflight also reserves one slot below the bounded 100-playlist inventory. A
review is published only when its complete UTF-8 protocol result fits within
64 KiB; otherwise its unpublished execution ticket is discarded.
`save-and-play` requires CurrentURI to prove that the active source is the Sonos
queue, so a failure can restore it exactly. A verified radio, TV, or other
non-queue source may be used with `save-only`, which does not switch playback
sources, but is rejected for `save-and-play` before any mutation.

Every track must contain a bounded decimal Apple catalogue song ID, the exact
public Apple Music share URL, title, artist, album, and duration. Sonarchy
applies its strict public URL policy and asks pinned SoCo 0.31.2 to canonicalise
the same URL. Only canonical `song:<id>` results whose ID exactly matches the
reviewed `catalogId` are accepted. Metadata supports review and verification;
it cannot redirect identity. Plain titles are never a write input.
Constructed queue and reopened-playlist items must expose the identity as a
complete canonical or pinned Sonos item ID, or as the leading song token of an
expected `x-sonos-http:` or `x-sonos-https:` resource. A matching substring
elsewhere in item metadata or a resource query is not identity evidence.

Execution rejections that occur before atomic ticket claim—such as missing
approval, replacement fields, or an unavailable token—do not refresh state or
advance the backend revision. They therefore cannot stale a different valid
pending plan. Once a valid ticket is claimed and its revision matches, every
execution attempt is followed by authoritative refresh.

Queue restoration replays each original queueable DIDL object individually
through pinned SoCo's `add_to_queue`. That method serializes one complete item
into one metadata document and returns the new one-based position; Sonarchy
checks every returned position before continuing. Restoration deliberately no
longer uses `add_multiple_to_queue`, whose batched metadata path recreated 36
physical queue slots without preserving their complete metadata during the
first approved `save-only` test. Verification still rejects missing metadata:
it separately compares stable resource/provider fields and complete DIDL
metadata while ignoring regenerated queue-local IDs.

Controlled construction failures identify only a bounded step
(`share_link_initialization`, `enqueue`, `position_decode`, or
`position_verify`). Track position and canonical `song:<id>` are included only
for a track-owned step. An enqueue may include the pinned exception's explicit,
strictly validated `error_code`; exception messages, XML, descriptions, URIs,
addresses, and provider data are never inspected for diagnostics. Rollback can
similarly identify its queue step, failed backup position, or exact typed
verification reason without parsing an exception message.

The complete wire contract and transaction rules are in
[`protocol-v1.md`](protocol-v1.md).

## Physical acceptance status

The first owner-approved physical `save-only` attempt on 2026-08-28 failed in
`queue_construction`; no Sonos Playlist was created. Its rollback could not
verify queue restoration. A subsequent read-only assessment found 36 active
queue entries at the prior position with stopped transport, but all projected
title/artist/album/provider evidence was absent. Exact original content and
order remain undetermined. The run did not retain enough bounded evidence to
identify the failed Apple track, returned position, or Sonos error code, so the
repair does not claim to explain that initial enqueue failure.

The per-item restoration and typed diagnostics described above have only
device-free automated coverage. Physical acceptance has not passed, and no
further speaker write is authorized by this implementation work. A fresh
review, green CI, exact owner-approved preflight, and separately approved write
are required before another attempt.

## Current client boundary

This implementation does **not** add an MCP server. Issue #11 still has no
accepted process-ownership and concurrency design. Starting a second MCP-owned
SoCo controller would create competing subscriptions, revisions, selections,
and writes, so Sonarchy does not do that.

The capability is ready below that future adapter. Once issue #11 selects one
authoritative process, a thin MCP adapter can expose preflight and token-only
execution through it. Read-only configuration must omit or decisively deny the
write operation. No future adapter should expose generic protocol, command,
SoCo, UPnP, URL, or URI execution.

Until then, the private JSON-line protocol remains owned by the running
Omarchy/QML backend and there is no supported independent Codex connection to
it. This is the deliberately deferred integration slice, not a missing Sonos
playlist transaction.

## Export/Copy to Apple Music

Native Apple Music playlist creation is a secondary, one-way export. It must be
labelled **Export/Copy to Apple Music**, never **Move**, unless a separately
approved action explicitly deletes the Sonos Playlist.

If an AI client provides Apple's user-reviewed playlist-creation widget, it can
reuse the same reviewed exact-song list to create a separate native Apple Music
playlist. That export is not implemented by Sonarchy and does not block Sonos
Playlist persistence. Sonarchy does not add Apple credentials or direct
private-library integration for this feature.

Current limitations are important:

- the current Apple plugin cannot inspect existing personal playlists;
- it cannot read private-library membership or listening history;
- it cannot mutate, clear, reorder, clone, or synchronize an existing Apple
  playlist through the exposed AI tools;
- the Apple copy and Sonos Playlist do not synchronize;
- changing one does not change the other;
- Sonarchy cannot adjust the Apple playlist after export;
- to play the Apple copy through Sonarchy, the user must currently copy its
  Apple Music share URL and provide it to Codex/Sonarchy;
- Sonarchy can validate and play that share URL but cannot modify its contents;
  and
- stronger Apple MCP capabilities may change this later.

No Apple export failure can roll back or invalidate a successfully verified
Sonos Playlist.
