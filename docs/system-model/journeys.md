# BPMN-oriented user journeys

This page answers **how a person completes an important goal and what decisions
or recovery paths occur**. The diagrams use responsibility lanes and BPMN-like
tasks/gateways while remaining directly renderable in GitHub Markdown.

## Journey catalogue

| Journey | Status | Primary acceptance focus |
|---|---|---|
| Start, discover, and select a room | Current | Cached discovery, SSDP fallback, no-room recovery, stable selection |
| Find and play content | Current | Source capability, nested browse, exact item identity, provider failure |
| Play only if the queue is empty | Current | Confirmation, exact identity, authoritative empty guard, honest partial failure |
| Stage and apply grouping | Current | No mutation while staged, same-household validation, topology convergence |
| Create or edit an alarm | Current | Authoritative room/program options, local validation, save refresh |
| Recover from an action or backend failure | Current | Error ownership, dismiss/refresh, automatic backend restart |
| Create and separately play an exact playlist through MCP | Current narrow tools; curation is external | Independent permissions and approvals, exact room/items, fresh preflights, authoritative results |

The complete release checklist remains in
[`ACCEPTANCE_TESTS.md`](../../ACCEPTANCE_TESTS.md). These models explain the
flow; they do not replace the exact test steps.

---

## 1. Start, discover, and select a room

```mermaid
flowchart LR
    subgraph User
        U1([Open Sonarchy])
        U2[Choose an exact room]
        U3([Control surface ready])
        U4[Choose Search again]
    end

    subgraph QML
        Q1[Start or supervise the persistent backend]
        Q2[Apply newest authoritative snapshot]
        Q3[Show no-room recovery state]
        Q4[Send exact room selection]
    end

    subgraph Backend
        B1[Load bounded state and cached hosts]
        B2[Probe cached private-LAN hosts]
        G0{Cache found a reachable zone?}
        B3[Run bounded SSDP]
        G3{SSDP found a zone?}
        G4{Network fallback rate limit permits scan?}
        B6[Run bounded attached-network fallback]
        G1{Reachable rooms found?}
        G2{Saved room UID still visible?}
        B4[Select safe fallback room]
        B5[Emit versioned snapshot and capabilities]
        B7[Validate and persist selected room UID]
    end

    subgraph Sonos
        S1[Return households, rooms, groups, and state]
    end

    U1 --> Q1 --> B1 --> B2 --> G0
    G0 -- Yes, skip SSDP --> S1
    G0 -- No --> B3 --> G3
    G3 -- Yes --> S1
    G3 -- No --> G4
    G4 -- Yes --> B6 --> S1
    G4 -- No --> G1
    S1 --> G1
    G1 -- No --> Q3 --> U4 --> B2
    G1 -- Yes --> G2
    G2 -- Yes --> B5
    G2 -- No --> B4 --> B5
    B5 --> Q2
    Q2 --> U2 --> Q4 --> B7 --> B5 --> Q2 --> U3
```

**Invariant:** room display names may change or collide; authoritative selection
uses a stable room identity rather than silently choosing by label.

---

## 2. Find and play content

This generic journey covers Favorites, Sonos playlists, the local library,
public Apple catalogue, and supported music services. Individual adapters can
add provider-specific validation, but they do not change the trust boundary.

```mermaid
flowchart LR
    subgraph User
        U1[Choose Browse source]
        U2[Search or open a container]
        U3[Choose a playable item]
        U4([Inspect resulting playback state])
        U5[Refresh, go Back, or choose another item]
    end

    subgraph QML
        Q1[Send bounded browse/search request]
        Q2[Render normalized items and capabilities]
        Q3[Send exact item identity and room UID]
        Q4[Show scoped recovery instruction]
    end

    subgraph Backend
        B1[Validate source, query, path, page, and limits]
        B2[Re-read authoritative container or provider result]
        G1{Item still exists at the claimed identity?}
        G2{Playable in the current source and room?}
        B3[Build provider-specific safe playback request]
        G3{Home-theatre TV Autoplay conflict?}
        B4[Execute through content or queue domain]
        B5[Refresh authoritative playback and queue]
    end

    subgraph Provider_Sonos[Provider and Sonos]
        P1[Return bounded browse/search data]
        P2[Accept or reject playback]
    end

    U1 --> U2 --> Q1 --> B1 --> P1 --> B2 --> Q2 --> U3 --> Q3 --> G1
    G1 -- No --> Q4 --> U5
    G1 -- Yes --> G2
    G2 -- No --> Q4 --> U5
    G2 -- Yes --> B3 --> G3
    G3 -- Yes --> Q4 --> U5
    G3 -- No --> B4 --> P2
    P2 -- Rejected --> Q4 --> U5
    P2 -- Accepted --> B5 --> Q2 --> U4
```

**Invariant:** QML-supplied titles, artists, URLs, and positions are not treated
as authoritative provider objects. The backend resolves and validates the exact
item again. Device state is not itself a measurement of audible playback or
natural transition to the next track; physical acceptance records those
observations separately.

---

## 3. Play only if the queue is empty

The former replace mode is now exposed as **Play if queue empty**. It does not
provide general replacement or restoration of an existing provider queue.

```mermaid
flowchart LR
    subgraph User
        U1[Choose Play if queue empty]
        U2[Press the same focused action again within five seconds]
        U3([New queue plays])
        U4([Refused without writes])
        U6([Inspect reported partial state])
        U5([Cancel or confirmation expires])
    end

    subgraph QML
        Q1[Arm one exact pending action]
        G1{Matching second confirmation?}
        Q2[Send exact room, item, path, and replace mode]
        Q3[Clear pending confirmation]
        Q4[Show scoped result or recovery]
    end

    subgraph Backend
        B1[Re-resolve room, source path, absolute index, and item ID]
        G2{Queue authoritatively empty?}
        B3[Append exact item and start without clearing]
        G4{All required steps succeeded?}
        B4[Report failure without cleanup or rollback]
        B5[Refresh authoritative queue and playback]
    end

    subgraph Sonos
        S1[Read and mutate queue]
    end

    U1 --> Q1 --> U2 --> G1
    G1 -- No --> Q3 --> U5
    G1 -- Yes --> Q2 --> B1 --> G2
    G2 -- No --> Q4 --> U4
    G2 -- Yes --> B3 --> S1 --> G4
    G4 -- Yes --> B5 --> Q3 --> Q4 --> U3
    G4 -- No --> B4 --> B5 --> Q3 --> Q4 --> U6
```

**Invariant:** nonempty or unverifiable queues are refused before clear, add or
play calls. Even on the empty path there is no clear call. A successful append
may remain after a later failure. Use Next or End to retain an existing queue
without starting playback; general restoration remains issue #19.

---

## 4. Stage and apply grouping

```mermaid
flowchart LR
    subgraph User
        U1[Open Rooms]
        U2[Select desired group members]
        U3[Review staged membership]
        U4[Choose Apply]
        U5([Group matches approved membership])
        U6[Refresh or revise selection]
    end

    subgraph QML
        Q1[Keep membership as presentation-only draft]
        Q2[Send anchor room and exact member UIDs]
        Q3[Render authoritative topology]
        Q4[Show conflict or recovery instruction]
    end

    subgraph Backend
        B1[Resolve current household and topology]
        G1{All members visible, eligible, and in one household?}
        B2[Apply the approved membership request]
        B3[Wait for bounded topology convergence]
        G2{Observed membership matches request?}
        B4[Refresh and classify failure]
    end

    subgraph Sonos
        S1[Change and report group topology]
    end

    U1 --> U2 --> Q1 --> U3 --> U4 --> Q2 --> B1 --> G1
    G1 -- No --> Q4 --> U6
    G1 -- Yes --> B2 --> S1 --> B3 --> G2
    G2 -- Yes --> Q3 --> U5
    G2 -- No --> B4 --> Q4 --> U6
```

**Invariant:** checking boxes changes only the draft. Review and Apply send one
application request, which may require multiple Sonos join/unjoin calls. This
is not an atomic single-device mutation or a promise of rollback.

---

## 5. Create or edit an alarm

```mermaid
flowchart LR
    subgraph User
        U1[Open alarm editor]
        U2[Choose room, schedule, volume, recurrence, and sound]
        U3[Choose Save]
        U4([Alarm list shows saved result])
        U5[Correct fields or choose New to reset]
    end

    subgraph QML
        Q1[Create draft from authoritative alarm and options]
        Q2[Validate local field shapes]
        G1{Draft locally valid?}
        Q3[Project exact save request]
        Q4[Show field or action error]
    end

    subgraph Backend
        B1[Validate anchor room and requested alarm room]
        G2{Target visible in the same household?}
        B2[Resolve allowed program or Favorite]
        B3[Create or update through Sonos]
        G3{Mutation accepted?}
        B4[Restore cached fields if update rejected]
        B5[Refresh authoritative alarms]
    end

    subgraph Sonos
        S1[Store and return alarm state]
    end

    U1 --> Q1 --> U2 --> U3 --> Q2 --> G1
    G1 -- No --> Q4 --> U5
    G1 -- Yes --> Q3 --> B1 --> G2
    G2 -- No --> Q4 --> U5
    G2 -- Yes --> B2 --> B3 --> S1 --> G3
    G3 -- Yes --> B5 --> U4
    G3 -- No --> B4 --> B5 --> Q4 --> U5
```

**Invariant:** the visual form does not invent room or sound options and does
not partially project an invalid draft. New resets the editor immediately;
there is no dirty-draft detection or confirmation dialog before discarding its
unsaved edits.

---

## 6. Recover from an action or backend failure

```mermaid
flowchart LR
    subgraph User
        U1[Perform foreground action]
        U2[Read recovery instruction]
        U3[Dismiss, retry, refresh, or choose another action]
        U4([Healthy authoritative state])
    end

    subgraph QML
        Q1[Assign request ID and error owner]
        Q2[Show the foreground error]
        G1{Unrelated background result arrives?}
        Q3[Keep current foreground error]
        Q4[Clear by allowed owner or explicit dismissal]
        Q5[Detect backend exit and restart it]
        Q6[Request or transient error timer expires after ten seconds]
        Q7[Dismiss message without proving recovery]
    end

    subgraph Backend
        B1[Validate and execute]
        G2{Request succeeded?}
        B2[Return safe machine code and user message]
        B3[Emit authoritative snapshot]
        G3{Backend process healthy?}
    end

    U1 --> Q1 --> B1 --> G2
    G2 -- Yes --> B3 --> Q4 --> U4
    G2 -- No --> B2 --> Q2 --> G1
    G1 -- Yes --> Q3 --> U2
    G1 -- No --> U2
    Q2 --> Q6 --> Q7
    U2 --> U3 --> Q4 --> B1
    G3 -- No --> Q5 --> B3 --> U4
```

**Invariant:** a successful background refresh cannot erase a foreground action
failure merely because it happened later. Backend restart proves recovery only
after a healthy snapshot. New foreground failures can replace the displayed
error. Request and live transient-error timers also clear their messages after
ten seconds; the ownership rule does not prevent expiry. Dismissing an error
does not fix its underlying cause.

---

## 7. Create and separately play an exact playlist through MCP

These narrow tools are implemented. The AI client owns curation, chart/source
research, recording ambiguity and the human approval interaction; Sonarchy
does not supply an AI model. Broader orchestration evaluation remains #15/#61.

```mermaid
flowchart TD
    subgraph Client_and_person[AI client and person]
        A1[Resolve exact Apple recordings and explicit catalogue storefront]
        A2[Review create plan and obtain human approval]
        A3[Compare fresh preflight with approved plan]
        A4[Review separate exact playlist and room playback plan]
        A5[Obtain playback approval and compare fresh preflight]
        Stop([Stop and report; no automatic retry or substitution])
    end
    subgraph Same_backend[Thin MCP client to the single Sonarchy backend]
        C1[Read-only Apple create preflight]
        C2[Create once using only the fresh handle]
        C3[Verify exact saved playlist; no queue or playback changes]
        P1[Read-only exact playlist playback preflight]
        P2[Append once and start first appended item once]
        P3[Verify queue, position, transport, playlist and unchanged room state]
        Done([Return authoritative result])
    end
    A1 --> C1 --> A2 --> A3
    A3 -- Unchanged and permitted --> C2 --> C3
    A3 -- Changed or declined --> Stop
    C2 -- Failure or partial result --> Stop
    C3 -- Save only --> Done
    C3 -- Playback separately requested --> P1 --> A4 --> A5
    A5 -- Unchanged and permitted --> P2 --> P3 --> Done
    A5 -- Changed or declined --> Stop
    P2 -- Failure or partial result --> Stop
    P3 -- Inconclusive or mismatched --> Stop
```

Each preflight failure is read-only and must be reported before seeking a new
review. Creation and playback require independent optional permissions on top
of `read`; approving creation never approves playback. Execute only with the
second, freshly compared handle. Handles are short-lived and single-use;
`approved: true` is not proof that a person actually consented.

Create failure permits only the defined exact-ID partial-playlist cleanup.
Playback failure never clears, reconstructs or removes queue entries; an
append can remain even if start or verification fails. Device PLAYING alone
is insufficient: the exact fresh-state verification must also pass. Audible
playback and natural track transition remain separate physical observations.

A Sonos Playlist is neither a temporary queue nor a native Apple Music
playlist. Private Apple-library access and one-way Apple export remain outside
this implemented workflow. See [MCP setup](../mcp.md) for exact tools, bounds,
permissions and failure semantics.
