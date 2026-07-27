# Post-Deployment Verification Checklist

## Purpose

This checklist verifies the governed payment-posting workflow after a future approved deployment or activation event.

## Pre-Check

- [ ] Deployment was formally approved
- [ ] Deployment window recorded
- [ ] Operator assigned
- [ ] Rollback owner assigned

## System Checks

- [ ] Site reachable
- [ ] App installed
- [ ] No migration failure
- [ ] No background worker error
- [ ] Reports load successfully
- [ ] Final implementation report loads successfully

## Final Monitor Checks

- [ ] Final Phase 14U monitor exists
- [ ] Runtime monitor active
- [ ] final_governed_payment_posting_implementation_complete = 1
- [ ] additional_governed_cycle_required = 0
- [ ] final Phase 14U next-planning flag = 0

## Accounting Checks

- [ ] PE17/16/15/14 remain cancelled unless approved activation specifically changes scope
- [ ] Payment Entry count reviewed
- [ ] Payment Entry GL count reviewed
- [ ] Invoice outstanding reviewed
- [ ] Journal Entry creation reviewed
- [ ] Purchase Invoice creation reviewed

## Policy and Config Checks

- [ ] Controlled policy reviewed
- [ ] live_posting_allowed reviewed
- [ ] production mode config reviewed
- [ ] live Payment Entry posting config reviewed
- [ ] sandbox posting config reviewed

## Sign-Off

- [ ] Post-deployment verification passed
- [ ] Finance owner notified
- [ ] Technical owner notified
- [ ] Release notes updated
