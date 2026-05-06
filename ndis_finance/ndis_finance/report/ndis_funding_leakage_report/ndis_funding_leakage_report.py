from ndis_finance.services.cfo_reporting import execute_funding_leakage_report


def execute(filters=None):
    return execute_funding_leakage_report(filters)
