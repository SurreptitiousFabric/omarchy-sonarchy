# AI and MCP: implemented boundary and remaining roadmap

Sonarchy provides deterministic local Sonos operations, not an AI model. A
client can research music, propose exact recordings, collect human approval
and call the narrow MCP tools. The backend validates and executes only its
declared contract. Public catalogue data, model confidence and an account
connected in Sonos do not grant access to a private Apple Music library.

Use [MCP setup and contract](mcp.md) for current tools, schemas, configuration,
permissions and limits; [AI-curated Sonos Playlists](ai-curated-sonos-playlists.md)
for direct persistence; and [release acceptance](../ACCEPTANCE_TESTS.md) for
observed evidence. This roadmap does not introduce additional operations.

## Implemented foundation

| Boundary | Current behavior | Authority |
|---|---|---|
| Process ownership | Quickshell owns one backend. The thin stdio MCP adapter connects to its owner-only Unix socket; no second controller, fallback backend or MCP HTTP listener. | [ADR 0002](adr/0002-single-authority-local-mcp.md) |
| Read context | Bounded rooms, exact-room state and content browsing. Public Apple browsing can omit the room and choose an explicit per-request storefront; supplied invalid rooms fail. | [MCP contract](mcp.md) |
| Recording metadata | Structured artist/album, duration and explicitness accompany Apple songs. Missing values remain unknown/null, not invented recording evidence. | [MCP contract](mcp.md) |
| Persistence | One reviewed 1–25-song Apple plan creates and verifies one new Sonos Playlist directly. No queue staging, playback-state reads or playback start. | [Direct persistence](ai-curated-sonos-playlists.md) |
| Playback | A separate reviewed exact native Sonos Playlist and room plan preserves the existing queue, appends once, starts its first appended item once and verifies exact state. | [MCP contract](mcp.md) |
| Permissions | `read` is the default; `playlist-create` and `playlist-play` are independent opt-ins, not generic transport, volume, grouping or queue authority. | [MCP setup](mcp.md) |
| Dependency boundary | Pinned SoCo assumptions fail closed in the narrow saved-queue adapter; other domains retain documented coupling and tracked test gaps. | [ADR 0005](adr/0005-soco-contract-and-upgrades.md) |

Creation approval never means playback approval. For either mutation the
client must show the read-only preflight, obtain explicit human consent,
repeat preflight, compare every material fact and execute once using only the
fresh handle. A handle is short-lived and single-use; client-supplied
`approved: true` is not proof that a person consented. Changed or rejected
plans require renewed review, never a silent recording substitution.

Playback is deliberately narrower than QML control: an online standalone room,
volume at most 20, stopped/paused transport, queue or no active source, complete
bounded queue/playlist evidence, and at most 100 combined items. Partial failure
can leave appended entries. It never retries the write, clears/removes/rebuilds
queue items, or claims generic rollback. Creation has a different failure policy:
one exact attributable partial playlist may be removed after its ownership checks.

## What the AI client must establish

1. **Source and scope:** distinguish a chart's country and period from the
   Apple storefront and the Sonos account's territory. For a UK request, source
   the requested UK chart and explicitly resolve the intended catalogue; never
   silently substitute the configured `CH` default for `GB`.
2. **Exact recording:** compare artist, title, album/version, duration,
   explicitness and stable catalogue identity. Flag ambiguous, missing or
   unavailable candidates. Metadata helps review but does not guarantee
   household playback acceptance or substitute for external chart evidence.
3. **Destination and effects:** distinguish a saved Sonos Playlist from a room
   queue and a native Apple playlist. Explain the exact name, ordered songs,
   room when required, write type and possible partial state.
4. **Consent and freshness:** follow the two-preflight contract independently
   for create and play. “Prepare for approval” is not permission to create or
   play; a failed write is not permission to retry.
5. **Evidence:** report the original authoritative outcome and any partial
   result. Later PLAYING cannot retrospectively turn failed verification into
   success. Audible confirmation and natural transition are separate observations.

The [bounded catalogue evaluation](public-catalog-evaluation.md) records fixed
client scenarios, actual deterministic boundary tests, the historical ten-track
GB case and their limits. A self-reviewed client walkthrough and green fixture
tests are not an independent LLM benchmark or current physical acceptance.

## Remaining bounded work

These are tracked requirements, not current tools or permission grants. Follow
each issue's individual scope and acceptance contract.

| Work | Tracking | Boundary |
|---|---|---|
| Public-catalog curation, ambiguity, prompt-injection and rejected-recording evaluation | [#15](https://github.com/SurreptitiousFabric/omarchy-sonarchy/issues/15), [#61](https://github.com/SurreptitiousFabric/omarchy-sonarchy/issues/61) | Evaluate implemented tools without broad control or automatic substitutions. |
| Broader room-targeted transport, volume and queue actions | [#14](https://github.com/SurreptitiousFabric/omarchy-sonarchy/issues/14), [#69](https://github.com/SurreptitiousFabric/omarchy-sonarchy/issues/69), [#70](https://github.com/SurreptitiousFabric/omarchy-sonarchy/issues/70), [#71](https://github.com/SurreptitiousFabric/omarchy-sonarchy/issues/71) | Separate designs, grants, review and physical approval, not implied by playlist playback. |
| General destructive queue restoration | [#19](https://github.com/SurreptitiousFabric/omarchy-sonarchy/issues/19) | Play if queue empty refuses nonempty/unverifiable queues; direct persistence does not solve restoration. |
| Private Apple-library feasibility | [#12](https://github.com/SurreptitiousFabric/omarchy-sonarchy/issues/12) | Investigate supported authentication, consent, privacy and provider capabilities first; no extraction of Sonos-held credentials. |
| Optional one-way Apple Music export | [#72](https://github.com/SurreptitiousFabric/omarchy-sonarchy/issues/72), [feasibility result](apple-music-export-feasibility.md) | Documented current identity/read-back limits; no exact-plan export tool implemented. |
| AI/MCP privacy disclosure | [#53](https://github.com/SurreptitiousFabric/omarchy-sonarchy/issues/53) | Local transport does not imply a local model; clients may send tool context to their model provider. |
| Release-host, installation and physical acceptance | [#48](https://github.com/SurreptitiousFabric/omarchy-sonarchy/issues/48) and children | Exact-candidate evidence and owner sign-off remain required; marketplace HOLD is unchanged. |

Optional export must remain **Export/Copy**, never Move: it would create a
separate native Apple playlist and leave the Sonos Playlist intact. Neither copy
should be described as synchronized. Any external client's actual Apple
permissions and supported workflow must be verified before a future
implementation. The #72 feasibility result distinguishes title-matched drafts
from exact-plan reuse and authoritative account verification; this roadmap
promises no ability to inspect or edit an existing private playlist.

## Evidence limits

The [2026-09-06 record in #17](https://github.com/SurreptitiousFabric/omarchy-sonarchy/issues/17)
reports direct creation of an exact ten-track GB plan, verified identities,
metadata and order, then separately approved playback preserving the existing
queue entry and starting the first appended song. The owner confirmed audible
playback. That case did **not** test natural transition, failure cleanup, state
restoration, every recording, every room or every playlist size.

Earlier queue-staging failures and narrower one-/two-track direct cases remain
in [acceptance evidence](../ACCEPTANCE_TESTS.md). Do not close the broader
playlist roadmap because one sequence persists and initially plays. Historical
cases and green Python CI are not candidate-wide acceptance; strict Omarchy
QML validation and remaining physical gates stand separately.
