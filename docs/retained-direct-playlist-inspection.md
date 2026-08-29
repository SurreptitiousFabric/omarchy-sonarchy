# Retained direct Apple Playlist inspection

This is a narrow owner-supervised diagnostic, tracked by issue #20. It exists
to determine what Sonos retained after a direct Apple saved-playlist addition,
including cases where the add call returned but authoritative verification was
absent or inconclusive.

## Contract

1. A read-only preflight validates one to 25 reviewed exact Apple song objects,
   an unused bounded playlist name, the household/coordinator anchor, direct
   capability, and the complete bounded Sonos Playlist inventory.
2. The preflight returns an opaque process-local token valid for at most 120
   seconds and states that catalogue identity does not prove Sonos acceptance.
3. A separately approved execution atomically consumes the token, revalidates
   the bound state, creates one empty native Sonos Playlist, and captures the
   exact create-returned `SQ:<id>`.
4. Each exact reviewed Apple song is added directly to that saved playlist once
   and reopened for bounded identity and metadata verification. There is no
   retry, substitution, queue staging, or playback.
5. Success and every attributable post-create failure retain the exact
   playlist. A failure also retains every successfully added prefix and returns
   safe evidence for manual inspection in the official Sonos app.

## Failure evidence

The bounded result distinguishes whether creation and the current add call
returned, whether the exact playlist reopened, the observed item count, the
failed position and `song:<catalogId>`, and one verification category such as
`item_absent`, `wrong_count`, `wrong_order`, `identity_mismatch`,
`metadata_incomplete`, or `metadata_mismatch`. Only the validated
`SoCoUPnPException.error_code` may cross as a Sonos error code.

Raw exceptions, addresses, credentials, public URLs, service/account fields,
URI values, DIDL, SOAP/XML, and provider metadata never cross the protocol.

## Cleanup and playback

Automatic cleanup is forbidden for this workflow. Later cleanup must use a
separately confirmed ordinary playlist deletion against the exact retained
`SQ:<id>`; title-only discovery is not an ownership proof. Creation never plays
the new playlist. Playback remains a separate operation and approval decision.

## Acceptance status

Fake-only tests cover exact success and every documented retention/failure
boundary. No real Sonos device was contacted while implementing this feature,
and direct retained creation must not be described as physically accepted
until a fresh owner-approved test is completed and inspected manually.
