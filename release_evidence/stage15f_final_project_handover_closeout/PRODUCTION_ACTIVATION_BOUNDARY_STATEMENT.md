# Production Activation Boundary Statement

## Boundary

Production activation is not part of Stage 15F.

The current project ends with final handover and closeout.

## Current Safe State

- ndis_finance_sandbox_posting_enabled = 1
- ndis_finance_production_mode = 0
- ndis_finance_live_payment_entry_posting_enabled = 0
- controlled policy production_batch_enabled = 1
- controlled policy live_posting_allowed = 0

## Activation Requirements

Production activation requires a separate formally approved activation event.

Before activation, the following must be approved:

- release approval
- go/no-go decision
- finance owner approval
- technical owner approval
- security/permission approval
- rollback plan approval
- deployment window approval
- operator assignment
- rollback owner assignment
- post-deployment verification owner assignment

## Explicit Non-Authorization

This handover pack does not authorize:

- production mode enablement
- live Payment Entry posting enablement
- live_posting_allowed enablement
- manual posting/cancellation/amendment/reposting
- a new governed implementation cycle
