from ndis_finance.services.profitability_reporting import (
    execute_profitability_summary_report,
)


def execute(filters=None):
    return execute_profitability_summary_report(filters)
