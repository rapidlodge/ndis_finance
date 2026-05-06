from ndis_finance.services.cfo_reporting import execute_recovery_ageing_report


def execute(filters=None):
    return execute_recovery_ageing_report(filters)
