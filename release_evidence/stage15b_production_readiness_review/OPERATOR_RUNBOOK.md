# Operator Runbook

## Scope

Governed NDIS payment-posting workflow after final implementation completion.

## Final State

The system is closed, baselined, and monitored.

Final monitor:

NDIS-NEXT-GOVERNED-LIMITED-OP-RUNTIME-MONITOR-20260726-144915-F5639

## What Operators Must Not Do

- Do not start a new governed implementation cycle.
- Do not create Phase 14V.
- Do not enable live posting without formal approval.
- Do not enable production mode without formal approval.
- Do not mutate historical runtime monitor records.
- Do not manually submit or cancel governed Payment Entries without approved recovery process.

## Daily/Pre-Release Checks

- Confirm final runtime monitor remains active.
- Confirm PE17/16/15/14 remain cancelled.
- Confirm Payment Entry count remains stable unless an approved deployment action occurs.
- Confirm Payment Entry GL count remains stable unless an approved deployment action occurs.
- Confirm controlled policy live posting remains disabled.
- Confirm repository is clean before deployment.

## Escalation

Escalate to the technical owner and finance owner if:

- Any final monitor flag changes unexpectedly.
- live_posting_allowed becomes 1 without approval.
- production mode becomes 1 without approval.
- Payment Entry or GL counts drift.
- A new governed planning flag appears on the final Phase 14U monitor.
