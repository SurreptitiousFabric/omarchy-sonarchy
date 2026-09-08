# Sonarchy working instructions

## Acceptance reporting and test bookkeeping

The owner's bounded work is the complete pre-publication release plan #48,
including its September 7 scope amendment. It is not just the latest defect or
the keyboard acceptance subtask. When asked whether the bounded work is done,
reconcile the whole #48 list. Upstream submission/adoption work was cancelled;
do not reintroduce it. A locally fixed defect does not complete release readiness.
The owner amended the QML release policy on September 8: zero warnings is not
required. Use the explicit upstream-warning baseline; do not report those accepted
warnings or waiting for upstream as release blockers. New warnings/errors still fail.

Before answering what remains to test, read `docs/acceptance-status.md` and
`ACCEPTANCE_TESTS.md`. Reconcile relevant newer owner confirmations, dated test
results and issue comments before reporting. An open issue or unchecked broad
checkbox is not evidence that all of its constituent checks are untested.

- Credit completed subcases first; name only the exact remaining scenario.
- Distinguish passed, partial, evidence missing, failed, not applicable, and
  future implementation. Missing evidence is not a confirmed unperformed test.
- Record owner confirmations immediately, with date and the scope actually
  stated. Unknown revision/interface details do not invalidate the confirmation
  and must not become a reason to repeat a working test.
- Update both acceptance files in the same task when new evidence changes
  status. Keep detailed historical evidence; mark superseded status explicitly.
- A newer candidate does not erase historical acceptance. Request a repeat only
  for a specific affected behavior or an explicit exact-release gate, and explain
  which change or requirement makes that repeat necessary.
- Never present optional research or unimplemented MCP actions as manual tests
  the owner still needs to perform.
- When asked what is next, continue the active acceptance track and its concrete
  blockers. Do not jump to unrelated checks merely because they are smaller.
- Reconciliation means reading and updating records, not running physical tests,
  creating alarms, restarting the desktop, or changing the user's session.

## Background UI testing

The owner works on this desktop while tests run. Use a separate headless
compositor with private runtime/display/input and session-bus isolation for
visual tests. Do not summon popups, send keys, take screenshots, change focus,
or restart components on the active desktop without explicit permission for
that live interaction. General authorization to test is not that permission.
Keep host display sockets, input devices and session bus absent from the test
sandbox. Preserve passed evidence and name any compositor/data limitations.
