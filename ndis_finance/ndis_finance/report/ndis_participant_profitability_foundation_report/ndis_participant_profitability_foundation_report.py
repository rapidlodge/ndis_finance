from ndis_finance.services.finance_analytics import (
    execute_participant_profitability_foundation_report,
)


def execute(filters=None):
    return execute_participant_profitability_foundation_report(filters)
