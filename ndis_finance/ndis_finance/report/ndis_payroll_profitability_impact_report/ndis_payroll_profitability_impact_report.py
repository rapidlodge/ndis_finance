from ndis_finance.services.payroll_profitability_reporting import (
    execute_payroll_profitability_impact_report,
)


def execute(filters=None):
    return execute_payroll_profitability_impact_report(filters)
