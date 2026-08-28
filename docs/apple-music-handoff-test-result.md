# Apple Music playlist handoff test result

**Status: PASS**  
**Observed:** 2026-08-28  
**Tracked by:** [#12](https://github.com/SurreptitiousFabric/omarchy-sonarchy/issues/12), [#14](https://github.com/SurreptitiousFabric/omarchy-sonarchy/issues/14), and [#15](https://github.com/SurreptitiousFabric/omarchy-sonarchy/issues/15)

This records the first complete proof that an AI-curated Apple Music catalogue playlist can be created in the user's Apple Music account and then played on a real Sonos room through Sonarchy's existing application/domain path.

Private identifiers, room UIDs, speaker addresses, and the full personal Apple playlist identifier are intentionally omitted from this public document.

## Proven chain

```text
Natural-language playlist request
        |
        v
ChatGPT selects candidate tracks
        |
        v
Apple Music plugin matches exact catalogue records
        |
        v
User reviews and approves playlist creation
        |
        v
Native Apple Music playlist appears in the user's account
        |
        v
Apple Music share URL is validated by Sonarchy
        |
        v
Pinned SoCo recognises it as a user-created playlist
        |
        v
Sonarchy content.apple.play targets an exact Sonos room
        |
        v
Sonos queues the two tracks and advances naturally
```

## Apple plugin result

The connected Apple Music plugin does not expose reads of the user's private library, existing personal playlists, or listening history. It does support:

- model-selected catalogue playlist drafting;
- exact matching to canonical Apple Music song records;
- a user-reviewed widget action that creates a genuine native Apple Music playlist.

A disposable two-track playlist was created successfully and independently confirmed in the user's Apple Music account.

## Non-mutating share-link validation

The real user-created playlist share URL was checked using the repository's pinned environment:

- Sonarchy URL validation: **PASS**
- SoCo version: **0.31.2**
- SoCo Apple Music recognition: **PASS**
- Canonical content type: `playlist`
- Canonical personal identifier shape: `pl.u-…`
- Sonos discovery or mutation during this stage: **None**

## Runtime pre-flight

A standalone, stopped test room was selected. Before mutation:

- topology was standalone;
- volume and mute were unchanged and safe;
- the existing Sonos queue contained 34 items;
- the Sonos queue transport was active;
- `content.apple.play` was available;
- the playlist URL remained accepted by both Sonarchy and SoCo.

The pre-flight made no Sonos mutation and required separate approval for playback.

## Runtime playback result

After explicit approval, Sonarchy's existing `content.apple.play` operation was invoked exactly once through the normal backend/application path.

Observed result:

| Queue position | Track |
|---:|---|
| 35 | **Just Like Heaven** — The Cure |
| 36 | **Life's What You Make It** — Talk Talk |

The existing 34 queue items remained intact. The operation appended the two playlist entries rather than clearing or replacing the queue.

Playback evidence:

- **Just Like Heaven** started in the exact standalone test room.
- It was seeked close to its end to shorten the test.
- Sonos advanced naturally to **Life's What You Make It**.
- `Next` was never invoked.
- The second title and artist were observed while it was playing.
- Playback was then stopped.
- Volume, mute, grouping, room identity, speaker settings, and the original 34 queue entries were not changed.
- The two test entries remain in the queue pending separately approved cleanup.

## Post-stop marker anomaly

After playback was stopped, Sonos no longer marked queue position 36 as the current item. The final post-stop position assertion therefore aborted without retrying.

This does not invalidate the playback result: the decisive evidence was captured while the second track was actively playing. It does reveal an acceptance-test rule for the MCP implementation:

> Verify the target item and natural transition while playback is active. Treat `stop` as a separate final action; do not require the stopped transport to retain a current-item marker.

The MCP result should report the observed playing item before stopping, followed by the independently verified stopped transport state.

## Architectural conclusion

For **AI-curated catalogue playlists**, Sonarchy does not need Apple credentials, private-library search, or personal-playlist lookup by name.

The minimum useful Sonarchy MCP surface is now narrower:

1. resolve an exact room and return its stable identity and topology;
2. inspect current playback, queue, capabilities, volume, and mute state;
3. validate an exact `https://music.apple.com/.../playlist/...` share URL;
4. play that validated share URL through the existing `content.apple.play` domain path;
5. return authoritative queue and active-playback evidence;
6. optionally seek for acceptance testing and stop after successful observation;
7. keep cleanup as a separate, explicitly approved queue mutation.

There must still be no generic arbitrary-URI, UPnP, shell, or protocol-passthrough MCP tool.

## What remains optional or unproven

A separate Apple Music MCP or Apple authorization path is still required for requests that specifically depend on private account data, for example:

- “Use only tracks already saved in my library.”
- “Base this on my listening history.”
- “Read or modify one of my existing personal playlists by name.”

The connected ChatGPT Apple Music plugin cannot currently perform those reads. That limitation does not block the now-proven catalogue-curation and share-link playback workflow.

## Remaining product work

- Implement the accepted Sonarchy MCP process/permission boundary from #11.
- Expose bounded read-only room, queue, and playback context from #13.
- Add the narrow exact-room Apple playlist playback tool under #14.
- Orchestrate Apple playlist drafting/creation and Sonarchy playback under #15.
- Decide how an approved Apple playlist share identity is transferred from the Apple widget to the local Codex/Sonarchy workflow without manual copy-and-paste.
- Perform separately approved cleanup of the two retained test queue entries.
