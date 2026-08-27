# BPMN-oriented user journeys

This page answers **how a person completes an important goal and what decisions
or recovery paths occur**. The diagrams use responsibility lanes and BPMN-like
tasks/gateways while remaining directly renderable in GitHub Markdown.

## Journey catalogue

| Journey | Status | Primary acceptance focus |
|---|---|---|
| Start, discover, and select a room | Current | Cached discovery, SSDP fallback, no-room recovery, stable selection |
| Find and play content | Current | Source capability, nested browse, exact item identity, provider failure |
| Safely replace a queue | Current | Confirmation, complete backup, stale-item check, rollback |
| Stage and apply grouping | Current | No mutation while staged, same-household validation, topology convergence |
| Create or edit an alarm | Current | Authoritative room/program options, local validation, save refresh |
| Recover from an action or backend failure | Current | Error ownership, dismiss/refresh, automatic backend restart |
| Draft and play a bespoke playlist through MCP | Planned | Permission, exact room/items, review, deterministic validation, execution |

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
        Q4[Persist selected room UID]
    end

    subgraph Backend
        B1[Load bounded state and cached hosts]
        B2[Probe cached private-LAN hosts]
        B3[Run bounded SSDP and attached-network discovery]
        G1{Reachable rooms found?}
        G2{Saved room UID still visible?}
        B4[Select safe fallback room]
        B5[Emit versioned snapshot and capabilities]
    end

    subgraph Sonos
        S1[Return households, rooms, groups, and state]
    end

    U1 --> Q1 --> B1 --> B2 --> B3 --> S1 --> G1
    G1 -- No --> Q3 --> U4 --> B3
    G1 -- Yes --> G2
    G2 -- Yes --> B5
    G2 -- No --> B4 --> B5
    B5 --> Q2
    Q2 --> U2 --> Q4 --> B5 --> Q2 --> U3
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
        U4([Hear the selected content])
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
item again.

---

## 3. Safely replace a queue

Queue replacement is not modeled as ordinary playback because it destroys the
existing queue and therefore needs stronger preconditions and recovery.

```mermaid
flowchart LR
    subgraph User
        U1[Choose Replace queue]
        U2[Press the same focused action again within five seconds]
        U3([New queue plays])
        U4([Old queue preserved or restored])
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
        G2{Current queue at most 100 restorable items?}
        B2[Read complete queue backup and verifiable source position]
        G3{Backup complete and restorable?}
        B3[Clear queue, add replacement, and start it]
        G4{All required steps succeeded?}
        B4[Attempt exact queue and position restoration]
        B5[Refresh authoritative queue and playback]
    end

    subgraph Sonos
        S1[Read and mutate queue]
    end

    U1 --> Q1 --> U2 --> G1
    G1 -- No --> Q3 --> U5
    G1 -- Yes --> Q2 --> B1 --> G2
    G2 -- No --> Q4 --> U4
    G2 -- Yes --> B2 --> S1 --> G3
    G3 -- No --> Q4 --> U4
    G3 -- Yes --> B3 --> S1 --> G4
    G4 -- Yes --> B5 --> Q3 --> Q4 --> U3
    G4 -- No --> B4 --> S1 --> B5 --> Q3 --> Q4 --> U4
```

**Invariant:** a queue that cannot be backed up completely is left untouched.
A restoration attempt is reported honestly; it is not described as successful
unless the authoritative state proves it.

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
        B2[Apply one topology mutation]
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

**Invariant:** checking boxes changes only the draft. Sonos topology changes
once, after review and Apply.

---

## 5. Create or edit an alarm

```mermaid
flowchart LR
    subgraph User
        U1[Open alarm editor]
        U2[Choose room, schedule, volume, recurrence, and sound]
        U3[Choose Save]
        U4([Alarm list shows saved result])
        U5[Correct fields or cancel]
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
    G3 -- Yes --> B5 --> Q1 --> U4
    G3 -- No --> B4 --> B5 --> Q4 --> U5
```

**Invariant:** the visual form does not invent room or sound options and does
not partially project an invalid draft.

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
        Q4[Clear only by allowed owner, dismissal, or newer foreground action]
        Q5[Detect backend exit and restart it]
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
    U2 --> U3 --> Q4 --> B1
    G3 -- No --> Q5 --> B3 --> U4
```

**Invariant:** a successful background refresh cannot erase a foreground action
failure merely because it happened later. Backend restart proves recovery only
after a healthy snapshot.

---

## 7. Planned: bespoke playlist through MCP

This is a target journey, not current behavior. Its implementation is tracked by
[#10](https://github.com/SurreptitiousFabric/omarchy-sonarchy/issues/10) and
children [#11–#15](https://github.com/SurreptitiousFabric/omarchy-sonarchy/issues/11).

```mermaid
flowchart LR
    subgraph User
        U1[Ask local AI for a playlist and named room]
        U2[Review exact tracks, versions, source, duration, and action]
        G1{Approve?}
        U3([Hear approved sequence in the named room])
        U4([Nothing changed])
    end

    subgraph AI_Client[Local AI client]
        A1[Interpret mood, duration, inclusion, exclusion, and ordering constraints]
        A2[Call read-only Sonarchy MCP tools]
        A3[Propose ordered exact-item draft]
        A4[Revise unresolved or rejected items]
        A5[Call one permitted execution tool]
    end

    subgraph Sonarchy_MCP[Sonarchy MCP adapter and domains]
        M1[Resolve exact room or return ambiguity]
        M2[Return bounded authorized candidates with provenance]
        M3[Revalidate every item and complete draft]
        G2{Room, items, source, duration, and permissions valid?}
        M4[Return reviewable execution plan]
        M5[Require confirmation for the selected mutation]
        M6[Execute queue or supported playlist action]
        M7[Return authoritative result]
    end

    subgraph Apple_Sonos[Apple or Sonos-mediated source and speakers]
        P1[Return authorized content]
        P2[Accept or reject exact playback or playlist operation]
    end

    U1 --> A1 --> A2 --> M1 --> M2 --> P1 --> A3 --> M3 --> G2
    G2 -- No --> A4 --> A2
    G2 -- Yes --> M4 --> U2 --> G1
    G1 -- No --> U4
    G1 -- Yes --> M5 --> A5 --> M6 --> P2
    P2 -- Rejected --> M7 --> A4
    P2 -- Accepted --> M7 --> U3
```

**Required distinctions:**

- public Apple catalogue is not described as the user's private library;
- a temporary Sonos queue is not a Sonos playlist;
- a Sonos playlist is not a native Apple Music library playlist;
- the AI proposes; Sonarchy resolves, validates, authorizes, mutates, and reports.
