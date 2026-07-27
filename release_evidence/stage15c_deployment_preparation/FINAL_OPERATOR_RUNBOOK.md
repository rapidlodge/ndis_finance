# Final Operator Runbook

## Scope

This runbook covers operational handling for the completed governed NDIS payment-posting implementation.

## Final Implementation Endpoint

- Final phase: Phase 14U - Final Governed Limited-Operation Runtime Monitor
- Final monitor: NDIS-NEXT-GOVERNED-LIMITED-OP-RUNTIME-MONITOR-20260726-144915-F5639
- Final implementation commit: 7c07bad

## Normal Safe State

- final_governed_payment_posting_implementation_complete = 1
- additional_governed_cycle_required = 0
- final Phase 14U ready_for_next_governed_limited_op_planning = 0
- PE17/16/15/14 all remain 2 / Cancelled
- Controlled policy remains 1 / 0
- sandbox/prod/live PE config remains 1 / 0 / 0

## Operator Daily / Pre-Deployment Check

Run the final monitor check:

```bash
bench --site "$SITE" mariadb -e "
SELECT
    name,
    status,
    monitor_status,
    monitor_active,
    final_governed_payment_posting_implementation_complete,
    additional_governed_cycle_required,
    COALESCE(ready_for_next_governed_limited_op_planning, 0) AS ready_for_next_governed_limited_op_planning
FROM \`tabNDIS Next Governed Limited Op Runtime Monitor\`
WHERE name='NDIS-NEXT-GOVERNED-LIMITED-OP-RUNTIME-MONITOR-20260726-144915-F5639';
"
```

Run accounting guardrails:

```bash
bench --site "$SITE" mariadb -e "
SELECT name, docstatus, status
FROM \`tabPayment Entry\`
WHERE name IN ('ACC-PAY-2026-00014','ACC-PAY-2026-00015','ACC-PAY-2026-00016','ACC-PAY-2026-00017')
ORDER BY name;
"
```

Run config guardrails:

```bash
bench --site "$SITE" show-config | grep -E "ndis_finance_sandbox_posting_enabled|ndis_finance_production_mode|ndis_finance_live_payment_entry_posting_enabled" || true
```

## Do Not Do

- Do not create Phase 14V
- Do not create a new governed implementation cycle
- Do not mutate historical runtime monitor records
- Do not enable production mode without formal approval
- Do not enable live Payment Entry posting without formal approval
- Do not change live_posting_allowed to 1 without formal production activation approval
- Do not manually create, submit, cancel, amend, or repost governed accounting documents

## Escalation

Escalate immediately if:

- Final monitor is not active
- additional_governed_cycle_required changes to 1
- final Phase 14U next-planning flag changes to 1
- PE count or PE GL count changes unexpectedly
- PE17/16/15/14 are not cancelled
- live posting becomes enabled unexpectedly
- production mode becomes enabled unexpectedly
