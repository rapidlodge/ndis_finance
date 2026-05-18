from ndis_finance.services.profitability_reporting import (
    execute_cost_type_analysis_report,
)


def execute(filters=None):
    return execute_cost_type_analysis_report(filters)
