# Production Activation Request Template

## Request Status

Draft only. Production activation is not performed in Stage 15C.

## Requested Action

Request approval to proceed with production activation planning for the governed NDIS payment-posting workflow.

## Implementation Reference

- Final implementation phase: Phase 14U
- Final implementation commit: 7c07bad
- Final runtime monitor: NDIS-NEXT-GOVERNED-LIMITED-OP-RUNTIME-MONITOR-20260726-144915-F5639

## Evidence References

- Stage 15A release review evidence
- Stage 15B production readiness review evidence
- Stage 15C deployment preparation pack

## Current Safe State

- final_governed_payment_posting_implementation_complete = 1
- ready_for_release_review = 1
- ready_for_production_readiness_review = 1
- additional_governed_cycle_required = 0
- final Phase 14U ready_for_next_governed_limited_op_planning = 0
- Policy enabled/live = 1 / 0
- Config sandbox/prod/live PE = 1 / 0 / 0

## Activation Preconditions

- [ ] Go/no-go decision approved
- [ ] Release approval signed
- [ ] Finance owner approval received
- [ ] NDIS CFO or delegated authority approval received
- [ ] Technical owner approval received
- [ ] Security/permission sign-off completed
- [ ] Rollback/recovery runbook accepted
- [ ] Operator runbook accepted
- [ ] Deployment window approved

## Activation Notes

Production activation must be performed under a separately approved activation procedure.

Stage 15C does not enable production mode or live posting.
