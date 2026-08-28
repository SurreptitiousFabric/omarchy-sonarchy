# Apple Music plugin test protocol

This is the first experiment for the local-AI playlist roadmap.

The preferred architecture is now to let the AI client orchestrate two specialised integrations:

```text
Person
  |
  v
Codex / ChatGPT
  |-- Apple Music plugin or MCP
  |     |-- private Apple library
  |     |-- Apple recommendations
  |     `-- native Apple playlists
  |
  `-- Sonarchy MCP
        |-- Sonos rooms and groups
        |-- queue and playback
        |-- bounded volume/mute
        `-- authoritative verification
```

If the Apple Music plugin already provides reliable, authorised private-library and playlist operations, Sonarchy should not duplicate Apple authentication or store Apple credentials.

Tracked work: [#12](https://github.com/SurreptitiousFabric/omarchy-sonarchy/issues/12) and [#15](https://github.com/SurreptitiousFabric/omarchy-sonarchy/issues/15).

## Why test the plugin first

Sonarchy's current Apple support searches the public Apple catalogue and hands validated Apple Music links to Sonos. Sonos then uses the Apple Music account already connected to the household. That is sufficient for playback of public catalogue items, but it does not give Sonarchy the user's private Apple library or personal playlists.

A connected Apple Music plugin may already own precisely that account-facing responsibility. Proving its actual capabilities is cheaper, safer, and architecturally cleaner than building Apple authentication into Sonarchy.

## Test 0 — identify the exact plugin

Use the exact Apple Music plugin selected by the user in ChatGPT/Codex. Record:

- displayed plugin name and publisher;
- whether it is available in ChatGPT, Codex, or both;
- whether it requires an Apple sign-in or other authorization;
- permission prompts shown before reads and writes;
- whether the client exposes any tool/capability list or connection-status view.

Do not install an unrelated third-party Apple Music MCP merely because it has a similar name if the selected plugin can perform the required work.

## Test 1 — read-only personal playlist proof

Ask:

> List five playlists from my Apple Music library. Do not create, edit, delete, add, remove, or play anything. For each playlist, return its name and whatever stable identifier or link you are allowed to expose so we can refer to the exact same playlist later.

### Pass

- It returns playlists that genuinely exist in the signed-in user's personal Apple Music library.
- It does not merely return public/editorial Apple playlists.
- It provides a repeatable identity or can reliably reopen the exact result later.

### Fail

- It can only search the public catalogue.
- It cannot distinguish personal from public playlists.
- It claims library access without returning a known personal playlist.

## Test 2 — known library-only item

Choose one item whose library membership you already know and ask:

> Find `[known item]` specifically in my Apple Music library, not merely in the public Apple Music catalogue. Do not change anything. Tell me whether the returned item is from my library, and give me the stable identity you can use to refer to that exact item again.

This is important because a public catalogue hit with the same title is not proof of private-library access.

## Test 3 — disposable native Apple playlist

Only after the read tests pass, explicitly approve one isolated write:

> Create a new Apple Music playlist named `Sonarchy Plugin Test`. Add exactly these two tracks in this order: `[track 1]`, `[track 2]`. Do not modify any existing playlist. When finished, read the new playlist back and show the exact tracks and versions in order, plus whatever playlist identity or share link you can expose.

Verify the result in an ordinary Apple Music client as an independent check.

### Record

- whether the playlist is a genuine native Apple Music library playlist;
- playlist ID, share URL, or other stable handle exposed by the plugin;
- track IDs/URLs exposed for the two entries;
- whether clean/explicit, live/studio, remaster/original, and album/single versions are distinguishable;
- whether the plugin can reopen the playlist by its returned identity.

## Test 4 — cleanup

If the plugin exposes deletion, explicitly ask it to delete **only** `Sonarchy Plugin Test`, then verify it is gone.

If deletion is not exposed, remove it manually in Apple Music and record that limitation. Cleanup capability is useful but is not required for the orchestration architecture.

## Test 5 — determine the Sonos handoff shape

The critical engineering question is what identity the Apple plugin can give Sonarchy after creating or resolving music.

Preferred possibilities, in order:

1. a normal Apple Music share URL for the exact playlist/container;
2. a catalogue or library playlist identifier that can be converted safely to a share URL;
3. an ordered list of exact Apple track URLs/IDs;
4. a weaker opaque handle that only the Apple plugin understands.

For each form, record whether it is stable across a later request.

### Direct playlist handoff

If the plugin exposes a normal Apple Music playlist/share URL, test separately whether Sonos/SoCo can accept it through the same safe share-link mechanism Sonarchy already uses for Apple songs and albums.

Do not add a generic `play_uri` path merely to make the test work.

### Track-expansion fallback

If Sonos cannot consume a personal Apple playlist directly, the preferred fallback is:

1. Apple Music plugin reads the exact ordered playlist tracks;
2. Codex passes those exact identities to Sonarchy MCP;
3. Sonarchy validates each supported Apple identity;
4. Sonarchy constructs the Sonos queue in the approved order;
5. Sonarchy starts playback in the exact requested room and reads authoritative state back.

This still avoids giving Sonarchy Apple account credentials.

## Test 6 — eventual two-plugin orchestration

Once a read-only Sonarchy MCP exists, the minimum end-to-end test is:

> Use my Apple Music library to make a two-track disposable test playlist. Show me the exact two tracks first. After I approve it, play those same two tracks in `[exact Sonos room]`. Do not group rooms, rename anything, alter alarms, change speaker settings, or change any existing Apple playlist.

Pass requires:

- Apple-side items came from the authorised library or are clearly labelled otherwise;
- the reviewed track identities exactly match the played identities;
- the requested Sonos room resolves unambiguously;
- the resulting Sonos queue order matches the approved order;
- track 1 actually advances to track 2;
- Sonarchy reports authoritative final playback state.

## Security observations to record

During testing, note:

- what permissions the plugin asks for;
- whether read and write actions can be distinguished;
- whether any Apple token, cookie, developer key, or credential appears in normal tool results, logs, or conversation text;
- whether the integration runs locally or through a hosted service, where that is disclosed;
- what account data it says it can access;
- whether a write asks for confirmation;
- whether access can be revoked cleanly.

Do not paste Apple tokens, session cookies, private keys, or other credentials into GitHub issues or repository fixtures.

## Architecture decision rule

Use the external Apple Music plugin/MCP as the preferred Apple integration if it proves:

1. genuine private-library access;
2. reliable exact-item identity;
3. personal playlist read/write needed by the use case;
4. an identity that can be handed to Sonarchy directly or expanded to exact tracks;
5. acceptable authorization, privacy, and maintenance behavior.

Only pursue Apple authentication inside Sonarchy if this orchestration route cannot satisfy the workflow.
