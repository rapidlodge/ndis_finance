from ndis_finance.services.profitability_reporting import (
    execute_true_house_profitability_report,
)


def execute(filters=None):
    return execute_true_house_profitability_report(filters)
