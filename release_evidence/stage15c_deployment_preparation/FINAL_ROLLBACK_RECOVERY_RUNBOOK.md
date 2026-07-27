# Final Rollback and Recovery Runbook

## Purpose

This runbook defines the safe recovery position for the completed governed payment-posting implementation.

## Final Safe Recovery Baseline

- Final monitor: NDIS-NEXT-GOVERNED-LIMITED-OP-RUNTIME-MONITOR-20260726-144915-F5639
- Final Payment Entry evidence: ACC-PAY-2026-00017 = 2 / Cancelled
- Gated Payment Entry: ACC-PAY-2026-00016 = 2 / Cancelled
- Previous gated Payment Entry: ACC-PAY-2026-00015 = 2 / Cancelled
- Historical gated Payment Entry: ACC-PAY-2026-00014 = 2 / Cancelled
- Controlled policy: production_batch_enabled = 1, live_posting_allowed = 0
- Config: sandbox/prod/live PE = 1 / 0 / 0

## Recovery Principles

1. Stop all posting activity.
2. Do not open a new governed cycle.
3. Do not mutate historical runtime monitor records.
4. Verify final Phase 14U monitor.
5. Verify accounting guardrails.
6. Verify controlled policy and config.
7. Restore only safe config values unless a formal recovery plan approves more.
8. Do not manually cancel or repost accounting documents without separate approval.

## Safe Config Restore

```bash
bench --site "$SITE" set-config ndis_finance_sandbox_posting_enabled 1
bench --site "$SITE" set-config ndis_finance_production_mode 0
bench --site "$SITE" set-config ndis_finance_live_payment_entry_posting_enabled 0
```

## Controlled Policy Verification

```bash
bench --site "$SITE" mariadb -e "
SELECT name, production_batch_enabled, live_posting_allowed
FROM \`tabNDIS Controlled Production Batch Posting Policy\`
ORDER BY modified DESC;
"
```

Expected:

- Exactly one enabled policy
- Zero live-posting-allowed policies

## Accounting Verification

```bash
bench --site "$SITE" mariadb -e "
SELECT name, docstatus, status
FROM \`tabPayment Entry\`
WHERE name IN ('ACC-PAY-2026-00014','ACC-PAY-2026-00015','ACC-PAY-2026-00016','ACC-PAY-2026-00017')
ORDER BY name;
"
```

Expected:

- PE14/15/16/17 all cancelled

## No Manual Accounting Recovery Without Approval

Do not manually submit, cancel, amend, repost, or delete accounting records without a separate approved recovery plan.
