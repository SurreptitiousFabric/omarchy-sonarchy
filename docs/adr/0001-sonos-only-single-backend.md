# ADR 0001: Sonos-only scope and one persistent backend

- Status: accepted
- Date: 2026-08-26

## Context

Sonarchy grew from a one-shot Sonos bridge into an event-driven controller while
retaining the original bridge for browsing and advanced mutations. QML now
coordinates both paths. This duplicates orchestration and gives presentation
code responsibility for process lifecycle, validation choices, retries, and
state reconciliation.

Bluetooth speakers and local PipeWire outputs were considered as additional
targets. They expose a fundamentally different capability set and are already
owned by Omarchy's Audio and Bluetooth components.

## Decision

Sonarchy remains a Sonos LAN controller. Bluetooth, PipeWire, AirPlay, account
administration, firmware, ownership, and initial speaker setup remain outside
its scope.

All runtime reads and mutations use one supervised persistent Python backend.
QML communicates with it through the versioned JSON-line protocol. The former
legacy bridge was deleted after operation-by-operation parity was proven.

Advanced features such as alarms, playlists and device settings may remain, but
each belongs to an isolated domain module and capability-driven page section.

## Consequences

- The backend becomes the only authoritative owner of Sonos state and errors.
- QML becomes smaller and independently testable as presentation code.
- Bluetooth support, if desired, belongs in a separate composing Audio Hub.
- Migration must be incremental because room grouping, queue mutation and
  alarms require real-speaker safety gates.
- Temporary adapters are allowed; duplicated domain implementations are not.
