from ndis_finance.services.payroll_profitability_reporting import (
    execute_payroll_cost_by_participant_report,
)


def execute(filters=None):
    return execute_payroll_cost_by_participant_report(filters)
