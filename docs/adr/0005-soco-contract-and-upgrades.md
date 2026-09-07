# ADR 0005: intentional SoCo coupling and bounded upgrade review

Status: proposed for acceptance with #76. SoCo remains pinned to 0.31.2.

## Decision

Retain intentional Sonos-specific coupling where it is straightforward and
already localized. Do not add interfaces around every DIDL class, alarm or
speaker property merely to claim dependency inversion. Additional isolation is
justified for fragile/private protocol envelopes and security hooks, but the
next missing step is stronger event/topology and capability contract evidence
(#98/#99/#103), not
an all-domain refactor. Keep the existing direct Apple adapter boundary.

The package pin fixes library code, not speaker firmware, subscription behavior,
music-service registration, account state or provider resource representations.
A passing package test or dependency audit cannot certify those external states.

## Current direct imports

All paths below are under `sonarchy_backend/`; this inventory includes local
imports, not only module-level imports. Other controller/domain helpers also
receive SoCo-shaped objects through factories and ports without importing SoCo.

| Owner | Direct dependency and purpose | Classification |
| --- | --- | --- |
| `controller_discovery.py` | `soco.discover`, `SoCo`, `discovery.scan_network` | Deliberate injectable discovery/creation coupling |
| `controller_favorites.py` | `MusicService` for TuneIn | Deliberate provider-specific resolution |
| `apple_catalog.py` | `AppleMusicShare` canonical URI | Tested identity contract outside infrastructure package |
| `domains/content.py` | `ShareLinkPlugin`, `MusicService`, `to_didl_string` | Deliberate content execution/service coupling, injectable factories |
| `domains/media.py` | `MusicService` | Deliberate service search coupling |
| `domains/library.py` | `DidlContainer` | Deliberate container classification, with metadata fallback |
| `domains/alarms.py` | `Alarm`, `get_alarms`, `to_didl_string` | Deliberate alarm/DIDL construction and projection |
| `domains/apple_playlist_transaction.py` | `SoCoUPnPException` | Tested typed error-code allowlist, not exception-text parsing |
| `infrastructure/apple_saved_queue.py` | version, `AppleMusicShare`, `DidlMusicTrack`, serializer | Explicitly version/envelope-gated infrastructure contract |
| `live_updates.py` | `soco.events`, `event_listener` | Private global listener hardening and subscription integration |

## Fragile assumptions, evidence and failure behavior

Test paths below are under `tests/`. “Tested” does not imply physical acceptance.

| Contract / owner | Guard or failure behavior | Existing evidence / gap |
| --- | --- | --- |
| Song URL identity: `apple_catalog.canonical_apple_song` expects `AppleMusicShare.canonical_uri` to return `song:<exact ID>` | Validates original HTTPS URL shape, unique numeric `i`, exact reviewed ID and returned kind/ID. Mismatch raises ValueError before saved-playlist work. This helper has no independent version check. | `test_apple_playlist_plan.py::test_valid_apple_song_url_is_canonicalised_as_exact_song` uses the real pinned canonicalizer; malformed/mismatch input cases reject. `test_canonicalizer_return_drift_rejects_before_saved_queue_access` in the transaction suite covers returned-value drift (#100). |
| Apple envelope: `DirectAppleSavedQueueAdapter` expects version 0.31.2, service number 52231, song key 10032020, empty prefix and musicTrack class | Constructor rejects version/magic/service drift. Exact extract result `("song", "song%3a<ID>")` required. | `test_direct_adapter_matches_pinned_soco_0312_and_escapes_reviewed_xml` verifies the real library's valid DIDL round trip with fake speaker transport. `test_direct_adapter_fails_closed_on_soco_or_apple_contract_drift` tests only version/service-number drift. `test_each_apple_magic_field_drift_disables_adapter` independently covers prefix/key/class; `test_extract_drift_rejects_before_saved_queue_access` covers instance-only extract-output drift without masking the earlier canonicalizer. All are in `test_apple_playlist_transaction.py` (#100). |
| Direct adapter capabilities: callable AddURIToSavedQueue and browse methods | Constructor rejects absent/non-callable methods before creating or adding saved content. | `test_apple_playlist_transaction.py::test_invalid_anchor_inventory_and_capability_fail_closed_without_queue_calls` covers AddURIToSavedQueue=None through preflight. Missing/non-callable browse and remaining absent-method variants are separate coverage gaps: #103. |
| Saved-queue append: adapter uses SQ numeric ID, browse update_id and AddAtIndex 2**32-1; reviewed metadata uses SA_RINCON descriptor and ElementTree-backed DIDL serialization | Invalid fields/identity/update ID reject; one direct saved-queue call, no temporary playback queue. Remote exceptions propagate to transaction logic; package pin does not validate firmware SOAP semantics. | Same adapter tests, unreviewed-input cases, transaction success/partial-cleanup tests. Approved physical content validation remains required separately. |
| Read-back identity: `apple_saved_queue_song_identity` accepts only pinned version and full HLS-static song resource/protocol/sid shape | Unknown/mismatched representation returns empty identity. Transaction combines independent item/resource evidence and accepts exactly one non-conflicting ID; complete ordered metadata verification can fail. | `test_song_identity_requires_anchored_apple_evidence`, `test_physical_sq49_shape_has_strong_identity_and_verified_metadata`, version/resource-shape rejection tests. “Physical” names are stored observed fixtures, not newly executed live tests. |
| Error classification: transaction `_safe_sonos_error_code` reads real SoCoUPnPException.error_code | Only a bounded code is exposed: 1–6 digits or up to 32 uppercase letters/digits/underscores starting with a letter (for example TIMEOUT_1). Non-UPnP, bool and malformed values are omitted. Partial failure/cleanup remains transaction-owned; never infer code from raw exception text. | `test_non_upnp_track_failure_does_not_fabricate_a_sonos_code`, `test_untrusted_upnp_error_code_is_not_returned`, partial-cleanup tests. |
| Event hooks: `live_updates.harden_soco_event_listener` subclasses/patches EventServer and EventNotifyHandler; depends on subscriptions_map and handle_notification signature | Import-time patch is idempotent; source/SID/sequence/body bounds reject callbacks. No explicit SoCo version/shape preflight here. Missing classes can fail import; changed upstream wiring could bypass hooks without an equivalent guard. Subscription failures use polling fallback, not proof of hardened callback wiring. | `test_live_updates.py` covers fake subscriptions, bounded queue, direct handler validation. It substitutes parser handoff and does not exercise real listener creation/concurrency. Gap #98. |
| Topology: `controller_topology.py` uses clear_cache, GetZoneGroupState and ZoneGroupState.process_payload; confirmed-coordinator Play fallback matches exception class name | Missing methods/query/parse failure return false for authoritative refresh; optional cache clear is skipped safely. Retry/convergence callers own final outcome. Not every topology read fails closed on contract drift; do not claim it does. Unrelated play exceptions propagate. | `test_controller.py` authoritative refresh and partial-convergence cases use fake topology state. Real pinned parser/cache and exception contract gap #99. |
| Ordinary domain service APIs: content ShareLink queue position, MusicService results, DIDL containers and alarms | Validation/projection is domain-specific; optional read helpers may return defaults, mutations may propagate errors. These are not all protected by the Apple adapter's version guard. ShareLink execution is a different queue path from saved-playlist construction. | `test_mutation_domains.py`, controller/favorites/content tests. Deliberate coupling retained; upgrades must rerun applicable behavior tests and approved live acceptance, not extrapolate from direct saved-queue tests. |

## Upgrade checklist

1. Open a narrowly scoped upgrade issue/PR. Record old/new SoCo versions and
   read release/source changes for sharelink, DIDL serialization, exceptions,
   events, subscription maps, discovery and ZoneGroupState. Re-run the import
   inventory above. Do not only change a version guard to make CI pass.
2. Use the project Mise runtime and reviewed lock-generation toolchain. Update
   direct requirements and regenerate both hashed locks as documented in
   CONTRIBUTING.md; review transitive changes and wheel availability. Never
   hand-edit lock hashes or install into system/plugin Python for testing.
3. Run the complete Python matrix, locked runtime import/version checks and
   advisory gate. Run the focused Apple-plan/transaction, live-update and
   controller tests, including #100 canonicalizer/magic/extract drift cases,
   plus #98/#99/#103 contract tests once available.
   A failed or incomplete audit is not a clean result.
4. Deliberately test old/mismatched version and changed Apple constants/extract
   behavior, absent service methods/update identity, conflicting resource IDs,
   malformed event headers/body, hook wiring and topology drift. Preserve exact
   identity, bounded diagnostics and partial-state behavior. Unknown contracts
   stay disabled/incomplete; do not introduce an unreviewed generic fallback.
5. Separately request household-owner approval for exact physical scenarios,
   rooms and disposable saved content. Record firmware, service/account
   context, before/after queue/playback/volume/group state, exact ordered
   playlist identity and failure outcomes. Mutating creation/playback/group or
   cleanup tests require explicit approval; no live action is implied by this
   checklist. Never log tokens, private resource URLs or raw credential metadata.
6. Review one exact candidate after green CI. Any necessary isolation/repair
   discovered by the upgrade must be separately scoped if it escapes that PR.
   Update this ADR/architecture claims and approval evidence before release.
   Reverting a package or code change cannot reverse remote device mutations.

## Conclusion and deferred work

Architecture is partially layered, not fully SoCo-independent. The serialized
protocol and MCP boundaries remain the important external isolation contracts;
internal SoCo coupling is acceptable when explicit and tested. No additional
all-domain inversion is justified by this review alone. #98/#99/#103 address
specific evidence gaps before considering extraction of event/topology adapters
or changes to the Apple guards.
Existing #19/#55 queue safety work and physical acceptance remain separate.
SoCo 0.31.2 and all production code are unchanged by this review.
