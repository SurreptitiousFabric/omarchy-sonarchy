# AI-curated Sonos Playlists

## Current create-only contract

Sonarchy can persist a human-reviewed sequence of exact Apple catalogue songs
as one new **Sonos Playlist**. Two protocol-v1 operations own the workflow:

1. `playlist_plan.apple.validate` performs a read-only preflight and returns a
   short-lived opaque plan token.
2. `playlists.apple.create` atomically claims that token after explicit
   `approved: true`, creates the saved playlist, and verifies it.

This is creation only. It does not play the new playlist and does not inspect,
clear, stage in, back up, restore, or otherwise change a room queue. It does not
read or mutate queue source/position, transport, volume, mute, or topology.
Success has exactly three effects: create one new Sonos Playlist, add the
reviewed songs in order, and authoritatively reopen and verify that exact
playlist.

The prior compound `save-and-play` mode was provisional and has been removed.
The implemented flow supporting issue #17 is:

1. create the exact Sonos Playlist;
2. report its exact `SQ:<id>` and verified contents;
3. separately preflight and approve playback in an exact room.

The current MCP surface exposes separate exact-ID playback preflight and
execution under an independent `playlist-play` grant. Creation does not grant
playback permission or approval. See [MCP setup](mcp.md) for the fresh-preflight
contract, standalone-room safety policy and honest partial-failure reporting.
Broader playback/orchestration work remains in issues #14/#15/#61; the
single-authority process decision is accepted in [ADR 0002](adr/0002-single-authority-local-mcp.md).

## Reviewed Apple song input

Every track must contain exactly a decimal Apple catalogue song ID, its copied
public `https://music.apple.com/...` song link, bounded title, artist, album,
and positive duration. The URL must use the exact host, no credentials,
non-standard port, or fragment, and one `i=<catalogId>` query value. Pinned SoCo
must independently canonicalise it to the same `song:<catalogId>` identity.
Album, artist, playlist, radio, unknown, and other-provider links are rejected.

Canonicalisation proves catalogue identity only. The plan therefore reports:

```text
catalogueIdentityValidated: true
sonosAcceptance: unproven_until_create
```

It does not promise that the household's Sonos Apple service will accept an
individual song route. A rejected song is reported by exact reviewed position
and identity. Sonarchy never retries it automatically or substitutes another
recording, edition, remaster, live version, or catalogue ID. The AI must show
the failed exact track and ask the user to review an alternative.

## Direct saved-playlist construction

SoCo's normal `create_sonos_playlist()` creates one empty Sonos Playlist. The
create-returned `SQ:<id>` is validated immediately, proved absent from the
preflight inventory, and reopened by that exact ID and requested title.

One private Apple-only infrastructure adapter then appends each reviewed song
directly to that saved playlist. The adapter:

- is disabled unless SoCo is exactly 0.31.2;
- reuses `AppleMusicShare` canonicalisation and checks the pinned Apple song
  envelope before every use;
- fixes every provider, item-class, append, and account field internally;
- builds escaped metadata with SoCo DIDL data structures rather than string
  interpolation; and
- accepts no generic URI, DIDL, service, SOAP, UPnP, provider, or command input.

These infrastructure values never cross the domain/protocol boundary. QML,
MCP documentation, and callers cannot supply or replace them.

After the empty create and after every addition, Sonarchy reopens the exact
`SQ:<id>` with a small three-attempt visibility policy. It verifies the expected
count, exact new position, Apple canonical identity, and reviewed title,
artist, and album. Final verification repeats the complete ordered comparison,
checks the requested playlist name, and confirms every pre-existing playlist
inventory entry is unchanged. Success returns `queueMutation: false` and
`playbackMutation: false`.

Saved-playlist browse may not return the original ShareLink item form. The
one-track physical result returned a queue-local `DidlMusicTrack` with one
HLS-static resource. Sonarchy recognises it only when the complete resource has
the reviewed `song:<catalogId>`, the Apple service identity derived from the
pinned SoCo service type, bounded saved-resource fields, and the exact HLS
protocol type. Another provider, a different catalogue ID, arbitrary prefix or
suffix text, and an ID appearing only in query text all fail. Sonos also
returned the complete album display `Kiss Me Kiss Me Kiss Me (Deluxe Edition)`.
That sanitized physical observation is accepted only through one explicit
tuple containing the exact catalogue identity, title, artist, reviewed album,
and observed album. It is not a general Deluxe, punctuation, provider, or
edition equivalence. Verified items retain the reviewed `album` and report
`albumVerification.kind` as `exact` or `evidence_bound`, alongside complete
bounded `reviewedAlbum` and `observedAlbum` values. Evidence-bound acceptance
does not prove byte identity or universal interchangeability between editions.

## Tokens and freshness

Plan tokens are opaque, random, process-local, memory-only, single-use, and
valid for at most 120 seconds. They bind the operation, exact room UID used as
the household anchor, coordinator and hashed household identity, complete
playlist inventory fingerprint/count, exact new name, duplicate policy,
ordered tracks and canonical identities, required direct capability, expiry,
and nonce. The general snapshot revision is not bound because unchanged
background polls advance it. Execution instead re-captures and compares every
material create-only target fact immediately before mutation.

Queue contents, queue position/source, media identity, transport, volume, and
mute are deliberately not read or bound. The token is atomically claimed before
the first playlist mutation and is consumed after every accepted execution
attempt, successful or failed. A backend restart invalidates it. Invalid args,
missing approval, and an invalid token are rejected before claim and do not
consume another valid token.

The review states plainly that no queue will change, no playback will start,
one Sonos Playlist is created on success, and an exact-ID partial playlist may
briefly exist while exact cleanup is attempted on failure. Complete protocol
results remain below the 64 KiB JSON-line limit.

## Partial failure and cleanup

Construction stops at the first add or verification failure. No failed song is
retried. Cleanup is attempted only for the exact create-returned ID after all of
these remain true:

- the ID is a validated `SQ:<id>`;
- it did not exist before this invocation;
- it still resolves authoritatively; and
- that exact ID has the invocation-bound requested title.

Title alone never establishes ownership. Cleanup performs one exact deletion
attempt, verifies disappearance authoritatively, and never makes a title-based
or second-ID guess. If deletion fails, the exact attributable partial ID is
returned with `playlistCleanupRequired: true`; every unrelated playlist is left
untouched.

Bounded failures may report only `phase`, `playlistConstructionStep`, reviewed
track position/identity, validated `SoCoUPnPException.error_code`, attributable
partial ID, cleanup booleans, pre-existing-playlist status, and explicit queue
and playback unchanged booleans. Raw exceptions, descriptions, addresses,
credentials, URLs, URIs, DIDL, XML, SOAP, and service/account metadata are never
returned.

## Why queue staging was rejected

Two owner-approved physical attempts disproved the old queue-backed design.

On 2026-08-28, the first attempt failed during queue construction. No Sonos
Playlist was created. Bulk replay recreated 36 queue slots but lost complete
title, artist, album, and provider identity, so exact restoration was false and
the original contents/order became undetermined.

On 2026-08-29, a known one-track baseline was first established as **Wish You
Were Here — Pink Floyd**, active at queue position 1 and stopped. A fresh plan
then added `song:1452806384` successfully, but `song:1443065566` failed at track
2 with Sonos code 800. No Sonos Playlist was created. Rollback recreated one
stopped active queue slot, but exact resource verification failed and the Pink
Floyd title, artist, metadata, and stable resource identity were not restored.

The code-800 evidence is a regression case, not a global unavailability claim:
the same recording had played when Sonos expanded a native Apple playlist. It
proves only that catalogue validation does not guarantee acceptance of this
exact individual-item route. Direct saved-playlist construction must fail
safely if Sonos rejects it.

### Direct physical acceptance results

On 2026-08-29, the direct route created and retained `SQ:49`, named `Sonarchy
Direct Test A 2026-08-29`. The owner manually confirmed **Just Like Heaven —
The Cure**, album **Kiss Me, Kiss Me, Kiss Me**, in the Sonos app. The playlist
was not played, edited, renamed, or deleted; no queue or playback operation was
issued.

The earlier automated verdict was a false negative. Sonos accepted and retained
the song, while the verifier rejected the queue-local/HLS-static read-back
representation. A read-only inspection of `SQ:49` established the narrow
machine-readable Apple identity form used by the fix. The corrected verifier
was then run read-only against the same retained item and accepted
`song:1452806384` with exact title and artist plus the explicit evidence-bound
reviewed/observed album mapping. The retained playlist remains untouched.

On 2026-08-30, direct Test C created and retained `SQ:51`, named `Sonarchy
Direct Test C 2026-08-30`, containing `song:1551800724`, **Don't Start Now — Dua
Lipa**, album **Future Nostalgia (The Moonlight Edition)**. Exact canonical
identity and reviewed metadata passed authoritative reopen without album
normalization. No queue operation or playback mutation occurred.

Direct Test D then created and retained `SQ:52`, named `Sonarchy Direct Test D
2026-08-30`, with two authoritatively verified items in exact approved order:
`song:1452806384` (**Just Like Heaven — The Cure**) followed by
`song:1551800724` (**Don't Start Now — Dua Lipa**). The first item used only the
explicit evidence-bound album observation; the second was an exact album match.
Both identities and all supporting title, artist, and album evidence passed.
Every pre-existing playlist, including `SQ:49` and `SQ:51`, remained unchanged.
The single create execution reported `queueMutation: false` and
`playbackMutation: false`; no queue operation, playback, retry, or substitution
occurred.

A separate direct attempt to add `song:1443065566`, **Life's What You Make It
— Talk Talk**, stopped at the rejected item with undocumented Sonos vendor code
`814`. Exact-ID automatic cleanup removed attributable partial playlist
`SQ:50`; pre-existing playlists, queue, and playback remained unchanged. No
semantic cause is assigned to `814`, and the result is not evidence of global
unavailability. It proves only rejection of this exact item through this exact
route.

These cases physically demonstrate one- and two-item direct persistence,
approved ordering, authoritative verification, unchanged existing playlists,
queue/playback isolation, no retry/substitution, and exact-ID partial cleanup.
The [2026-09-06 record in #17](https://github.com/SurreptitiousFabric/omarchy-sonarchy/issues/17)
adds an exact ten-track GB catalogue plan: all identities, metadata and order
were verified, followed by separate playback that preserved the existing queue
entry and authoritatively started the first appended song. The owner confirmed
audible playback. That run did not test natural transition, failure cleanup or
state restoration; no revision or timing is inferred beyond the cited record.

These exact cases do not demonstrate universal Apple-song acceptance or every
playlist size. Issue #19 separately tracks general destructive queue
restoration; direct persistence neither fixes nor closes it. The ordinary
Play if queue empty action now refuses nonempty/unverifiable queues instead
of attempting unsafe replacement.

## AI, MCP, and Apple export boundaries

The AI client owns curation, review and the human consent interaction. Sonarchy
owns deterministic validation, permission and single-use ticket enforcement,
direct Sonos Playlist persistence, exact reopen verification and exact-ID
cleanup. The current MCP bridge exposes the same preflight/create services
and separate exact-playlist playback through the Quickshell-owned backend; it
does **not** add a second Sonos controller. A supplied `approved: true` flag
cannot prove that the client obtained consent. Playback failure has no queue
cleanup, reconstruction or retry; appended entries may remain.

Without an explicitly supplied Apple API source, the AI cannot inspect existing
personal playlists and cannot read private-library membership or listening
history through Sonarchy. A native Apple Music playlist would be a separate
optional **Export/Copy to Apple Music**, not the normal persistence target.
That user-assisted/external workflow is future work in #72, not an implemented
Sonarchy export tool. It must not imply synchronization, private-library
access, or permission to mutate an existing Apple playlist. Any supported
external Apple tool and its consent requirements must be verified separately.

The constraints on that future copy remain explicit: the Apple copy and Sonos
Playlist do not synchronize. Sonarchy cannot adjust the Apple playlist after
export and cannot modify its contents. To request a separately reviewed
share-link handoff, the user would need to copy its Apple Music share URL;
that is not an automatic transfer, and the current MCP allowlist does not
expose arbitrary Apple playlist-share playback. The historical external
handoff experiment does not grant that missing tool or waive its review.
