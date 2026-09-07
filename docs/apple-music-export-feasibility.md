# Apple Music export: current feasibility limit

Status: #72's documented-feasibility outcome, checked 2026-09-07. **No Sonarchy
Apple-account export tool is implemented.** A title-matched draft is not proof
that an already approved exact Sonos track plan was copied and verified.

## Observed integration boundary

The Apple Music app exposed these two tools in the assessment session:

| Tool | Declared inputs and purpose | Limit relevant to export |
| --- | --- | --- |
| `search` | `term`, `storefront`, optional `l`; public catalog discovery | Not a private playlist/library reader or writer |
| `get_track_details_batch` | `trackTitles`, `title`, `storefront`, optional `description`/`l`; enrich up to 25 title/artist candidates and present a draft | No exact catalog-ID input; native creation requires the user's Apple Music button action |

The batch helper's instructions explicitly distinguish preparing a draft from
creating a playlist. It may return the same recordings as a previous plan, but
title/artist rematching cannot by itself enforce that identity. Current evidence
does not establish exact-ID binding between a pre-approved plan, its displayed
widget and the eventual Apple playlist. No authoritative created personal-
playlist ID/read-back/edit/delete operation appears in this exposed app inventory.

This is a dated assessment of the selected interface, not a claim that every
Apple integration lacks stronger capabilities. No connector build/version or
OAuth-grant evidence was available from those declarations. A separate read-only
app-permission check concerns approval policy, not OAuth scopes, account contents
or absent API methods. No permission setting or credential was changed, and no
Apple catalog/account action was invoked for this assessment.

Sonarchy's `apple_playlist_create` instead targets a **native Sonos Playlist**.
Its local `playlist-create`/`playlist-play` grants and preflight handles are not
Apple-account authorization. The [MCP allowlist](mcp.md) contains no Apple export,
private-library read or arbitrary Apple playlist-share playback operation.

## Decision and proposed contract

Do not introduce an export command on the strength of title-based drafting or
the historical handoff alone. Current supported behavior remains direct Sonos
persistence and separately approved bounded Sonos playback. Generic external
Apple drafting remains distinct from verified reuse of an existing exact plan.

Any future export must bind the reviewed name and complete ordered 1–25-song
plan: exact catalog IDs/validated song links, artist, album/version, duration,
explicitness and explicit storefront. Do not substitute the configured storefront,
silently rematch editions, drop items or deduplicate without renewed review.
Require separate informed Apple creation approval; preparing a draft or approving
a Sonos operation is not that approval. Missing, malformed, changed or ambiguous
identity evidence must stop the proposed exact-copy workflow before creation.

Create one new Apple playlist as a one-way snapshot, never overwrite/delete an
existing playlist or move/remove the Sonos original. A current integration must
establish how the reviewed identities bind to the creation action and what
authoritative identity/order read-back it can provide. Otherwise report the
limit, not verified success. Uncertain creation must not trigger an automatic
retry, cleanup or title-based search/deletion. Neither copy is synchronized.

This is a prospective contract, not a new permission, adapter or acceptance
waiver. Revisit through a separately bounded issue if the selected integration
offers stronger evidence; do not add Apple authentication to Sonarchy as a
fallback under #72.

## Evidence and acceptance limits

| Case | Evidence in this assessment | What is not claimed |
| --- | --- | --- |
| Positive | The [2026-08-28 experiment](apple-music-handoff-test-result.md) records owner-created native Apple playlist and two-track Sonos share-link handoff | Not a current exact Sonos-plan → Apple export, widget binding or automated Apple read-back pass |
| Denied approval | Current tool declarations separate a draft from the user creation action; no export operation/account call was added or made here | No newly implemented authorization path or live denied-write test |
| Malformed or wrong recording | Exact-ID input is absent from the batch helper; rematching can produce a different edition and cannot be treated as validation of the old plan | No claim of current exact-export input validation or tested rejection by Apple |
| Stale plan/result | No exposed authoritative personal-playlist read-back or documented binding to the original approved plan establishes freshness | No stale-state account test or guarantee that a displayed draft remains unchanged |
| Partial/uncertain creation | The exposed inventory supplies no authoritative create-completion/read-back contract for a native account playlist | No partial-write test, automatic retry, rollback, deletion or fabricated success |

There is no export implementation to exercise in the latter cases. The rows
record capability/permission constraints and required future acceptance, not
fake passing tests. No disposable account mutation was authorized or attempted.
If a future owner-approved widget action occurs without authoritative read-back,
report only the observed draft/user action and verification limits; do not infer
that the requested exact playlist exists. Independent user confirmation is a
separate observation, not a machine-readable completion contract.

## Mapping the parent export requirements

The relevant #17 requirements remain intact:

- Reuse the same exact ordered plan: prospective contract above; current
  title-based input and undocumented widget binding are insufficient evidence.
- Present a user-reviewed Apple draft: documented helper capability, but not
  proof that it is a verified copy of an earlier Sonos plan.
- Create a new native Apple snapshot: historically observed after user action;
  no current export/completion/read-back guarantee or account test here.
- Keep the Sonos original and avoid synchronization: mandatory boundary;
  this documentation-only outcome performs no mutation on either side.
- No private-library membership, existing-playlist edits or credential ownership:
  no such feature is added or inferred from public catalog access.
- Manual share-link handoff is a separate historical workflow: the current MCP
  allowlist does not acquire arbitrary share-link playback through this issue.
- User documentation distinguishes persistence and optional export: see
  [direct Sonos Playlists](ai-curated-sonos-playlists.md) and the
  [AI/MCP roadmap](ai-mcp-roadmap.md). Broader Sonos playback/restoration and
  physical criteria in #17/#19 remain separate and unresolved where recorded.

Evidence sources: the runtime-exposed Apple Music tool declarations inspected
on 2026-09-07; the separate read-only approval-policy check; the public dated
handoff record; and Sonarchy's
[permission/operation contract at the reviewed base](https://github.com/SurreptitiousFabric/omarchy-sonarchy/blob/38d821e6463feea128b5adf207fb95d60749a1fb/sonarchy_mcp_contract.py).
The historical [experiment plan](apple-music-plugin-test.md) is not current
capability evidence or authorization. Alternative integrations were not
evaluated. Recheck current schemas, supported identity binding and permissions
before proposing any future implementation.
