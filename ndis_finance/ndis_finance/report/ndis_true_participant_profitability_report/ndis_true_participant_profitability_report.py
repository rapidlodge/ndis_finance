from ndis_finance.services.profitability_reporting import (
    execute_true_participant_profitability_report,
)


def execute(filters=None):
    return execute_true_participant_profitability_report(filters)
