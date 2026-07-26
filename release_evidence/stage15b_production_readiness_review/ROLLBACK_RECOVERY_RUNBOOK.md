# Rollback and Recovery Runbook

## Purpose

This runbook documents recovery steps for the governed payment-posting implementation after final implementation completion.

## Current Safe Baseline

- Final runtime monitor: NDIS-NEXT-GOVERNED-LIMITED-OP-RUNTIME-MONITOR-20260726-144915-F5639
- Final monitored Payment Entry: ACC-PAY-2026-00017
- PE17 status: 2 / Cancelled
- Gated Payment Entry: ACC-PAY-2026-00016
- PE16 status: 2 / Cancelled
- Controlled policy: production_batch_enabled = 1, live_posting_allowed = 0

## Immediate Recovery Principles

1. Stop all governed posting actions.
2. Do not create a new governed cycle.
3. Verify controlled policy state.
4. Verify Payment Entry and GL counts.
5. Verify invoice outstanding restoration.
6. Restore configuration to safe values if drift is detected.
7. Review final Phase 14U monitor evidence before any further action.

## Safe Config Baseline

Expected config:

- ndis_finance_sandbox_posting_enabled = 1
- ndis_finance_production_mode = 0
- ndis_finance_live_payment_entry_posting_enabled = 0

## Recovery Checks

```bash
bench --site "$SITE" show-config | grep -E "ndis_finance_sandbox_posting_enabled|ndis_finance_production_mode|ndis_finance_live_payment_entry_posting_enabled" || true

bench --site "$SITE" mariadb -e "
SELECT name, production_batch_enabled, live_posting_allowed
FROM \`tabNDIS Controlled Production Batch Posting Policy\`
ORDER BY modified DESC;
"
```

## Emergency Safe-State Restore

Only restore policy/config to the approved safe state:

```bash
bench --site "$SITE" set-config ndis_finance_sandbox_posting_enabled 1
bench --site "$SITE" set-config ndis_finance_production_mode 0
bench --site "$SITE" set-config ndis_finance_live_payment_entry_posting_enabled 0
```

Do not cancel, amend, or repost accounting documents without a separate approved recovery plan.
