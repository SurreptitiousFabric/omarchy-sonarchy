## Primary objective

<!-- One sentence naming the user-visible or maintainability outcome. -->

Linked issue:

## Intended scope

<!-- List the files, packages, or domains intentionally changed and why each belongs. -->

## Non-goals

<!-- What does this PR deliberately not solve? -->

## Cross-cutting changes

<!-- Write `None`, or list each change, why it is necessary here, and why it cannot use a separate issue and PR. -->

Unrelated browse, pagination, QML, protocol, security-boundary, dependency, or
infrastructure behavior belongs in a separate issue and PR.

## Acceptance contract

<!-- List the relevant issue criteria and whether they were locked before implementation. Link any owner-approved amendment. Map each criterion to evidence below; never silently rewrite criteria to match the implementation. -->

## Evidence

<!-- For each criterion: failing-before evidence for a real defect, passing-after evidence, feature-specific checks, and commands/results. When the boundary matters, include cross-layer production-path evidence and explain why any fake is at the lowest practical external boundary. -->

Green CI is required but is not sufficient evidence by itself.

## Security and side effects

<!-- Cover permissions, tokens, network, persistence, destructive effects, and rollback or partial failure. Write `Not applicable` with a reason when appropriate. -->

## Physical-device status

<!-- Select exactly one and give exact evidence and limitations. Fake-only tests are not physical acceptance. -->

- [ ] Not required
- [ ] Not run
- [ ] Read-only run
- [ ] Mutating run with explicit owner approval

## Review scope and stopping rule

<!-- List exact in-scope review concerns. Use one substantive review round and at most one in-scope repair round. File out-of-scope findings separately; if repair produces another substantive finding, stop for owner reassessment. -->

## Follow-up issues

<!-- Link deferred or newly discovered out-of-scope work, or write `None`. -->

## Completion checklist

- [ ] This PR has one primary objective and no hidden out-of-scope implementation.
- [ ] Intended scope and non-goals are explicit; cross-cutting changes are explained.
- [ ] Acceptance criteria were not weakened after implementation began, and evidence maps to each criterion.
- [ ] Green CI is not the only completion evidence.
- [ ] Cross-layer proof does not rely solely on a self-authored fake when the production boundary matters.
- [ ] Unrelated findings have separate issues, or there are none.
- [ ] No volatile suite count was added to durable documentation.
- [ ] Physical-test status is honest and exact.
