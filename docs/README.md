# Sonarchy documentation map

Use this page to choose the view that answers the question you have. Sonarchy
has deliberately separate product, workflow, state, architecture, protocol,
and security views; trying to put all of them into one diagram would make each
of them less useful.

## Start with the question

| Question | Read |
|---|---|
| What can a person do with Sonarchy? | [System model: capabilities](system-model/capabilities.md) |
| How does a person complete an important task? | [System model: journeys](system-model/journeys.md) |
| What can happen from the system's current state? | [System model: states](system-model/state-models.md) |
| Which software part owns the behavior? | [Architecture](../ARCHITECTURE.md) |
| What crosses the QML/backend boundary? | [Persistent protocol v1](protocol-v1.md) |
| How could a local AI control Sonarchy through MCP? | [AI and MCP roadmap](ai-mcp-roadmap.md) |
| Why was an architectural choice made? | [Architecture decisions](adr/) |
| What must pass before release? | [Acceptance tests](../ACCEPTANCE_TESTS.md) |
| How does a user operate the current application? | [User guide](../USER_GUIDE.md) |
| What machine and network privileges does the plugin use? | [Declared capabilities](../CAPABILITIES.md) |

The [system-model index](system-model/README.md) explains how the capability,
journey, state, and architecture views relate to one another.

## Document roles

The documents have different jobs:

- **User guide:** current, user-visible behavior and recovery instructions.
- **Capability model:** the product surface, including explicit boundaries.
- **Journey model:** ordered user goals, decisions, validation, and recovery.
- **State model:** legal transitions and capability-dependent actions.
- **Architecture:** ownership and dependency direction in the implementation.
- **Protocol:** the exact versioned contract between QML and Python.
- **ADR:** a durable decision plus alternatives and consequences.
- **Issue:** proposed work, uncertainty, and acceptance criteria; an open issue
  is not evidence that a capability exists.

## Maintenance rules

When behavior changes, update the smallest authoritative set rather than copying
implementation detail everywhere:

1. A new user-visible ability updates the user guide, capability model, relevant
   journey/state view, and acceptance coverage.
2. A new backend operation updates the protocol inventory and contract tests.
3. A changed responsibility or process boundary updates architecture and, when
   consequential, an ADR.
4. A proposed capability stays in GitHub Issues and is marked **planned** or
   **investigation** in explanatory documents until implemented and verified.
5. Diagrams use stable domain names and user language. They should not expose
   private addresses, service tokens, raw SoCo objects, or transient code names.
6. Mermaid diagrams in Markdown are the reviewable source for human-facing
   views. BPMN 2.0 files may be added under `system-model/bpmn/` when a workflow
   needs interchange with a dedicated modeler; the Markdown journey remains the
   readable entry point.

## Truth and drift

Code, tests, and observed speaker behavior ultimately determine what the current
build does. The system model exists to make that behavior understandable and to
make contradictions visible. If a diagram and verified behavior disagree, fix
the behavior or the diagram explicitly; do not quietly reinterpret one to fit
the other.
