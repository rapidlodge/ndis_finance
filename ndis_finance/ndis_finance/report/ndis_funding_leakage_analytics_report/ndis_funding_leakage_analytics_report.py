from ndis_finance.services.finance_analytics import execute_funding_leakage_analytics_report


def execute(filters=None):
    return execute_funding_leakage_analytics_report(filters)
