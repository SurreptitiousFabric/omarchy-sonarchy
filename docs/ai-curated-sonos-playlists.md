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
The intended future flow for issue #17 is:

1. create the exact Sonos Playlist;
2. report its exact `SQ:<id>` and verified contents;
3. separately preflight and approve playback in an exact room.

Playback remains the existing exact-ID Sonos Playlist action. Safe AI/MCP
orchestration of that separate mutation belongs to issues #14 and #11; playlist
creation does not grant playback approval.

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

The redesigned implementation has fake-only automated coverage. **No physical
test has occurred for direct saved-playlist construction, and it must not be
described as physically accepted.** Issue #19 separately tracks the general
destructive queue replacement and exact rollback defect; PR #18 neither fixes
nor closes it.

## AI, MCP, and Apple export boundaries

The AI client owns curation and review. Sonarchy owns deterministic validation,
single-use approval binding, direct Sonos Playlist persistence, exact reopen
verification, and exact-ID cleanup. This PR does **not** add an MCP server or a
second Sonos controller; issue #11 still owns that process/concurrency design.

Without an explicitly supplied Apple API source, the AI cannot inspect existing
personal playlists and cannot read private-library membership or listening
history. A native Apple Music playlist is a separate optional **Export/Copy to Apple Music**,
not the normal persistence target. The Apple copy and Sonos
Playlist do not synchronize; changing one does not change the other. Sonarchy
cannot adjust the Apple playlist after export. To play that copy through
Sonarchy, the user must copy its Apple Music share URL and provide it for a
separately reviewed action. Sonarchy can validate and play that share URL but
cannot modify its contents.
