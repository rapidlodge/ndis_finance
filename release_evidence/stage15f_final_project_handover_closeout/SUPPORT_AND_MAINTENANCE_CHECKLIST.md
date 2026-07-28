# Support and Maintenance Checklist

## Routine Checks

- [ ] Confirm final Phase 14U runtime monitor remains active
- [ ] Confirm final implementation complete flag remains 1
- [ ] Confirm additional governed cycle required remains 0
- [ ] Confirm final next-planning flag remains 0
- [ ] Confirm PE17/16/15/14 remain cancelled unless a future approved activation changes scope
- [ ] Confirm controlled policy enabled/live remains 1 / 0
- [ ] Confirm sandbox/prod/live PE config remains 1 / 0 / 0 until activation is approved

## Repository Checks

- [ ] App repository clean
- [ ] No destructive fixture churn committed
- [ ] Controlled policy fixture remains 1 / 0
- [ ] Release evidence directories preserved

## Escalation Triggers

Escalate if:

- production mode becomes 1 without approval
- live Payment Entry posting becomes 1 without approval
- live_posting_allowed becomes 1 without approval
- additional governed cycle required becomes 1
- final next-planning flag becomes 1
- PE or GL counts drift unexpectedly
- final monitor becomes inactive
- repository becomes dirty before deployment

## Maintenance Boundary

Maintenance should preserve evidence and safety state.

New capability work must be handled as a separate approved project.
