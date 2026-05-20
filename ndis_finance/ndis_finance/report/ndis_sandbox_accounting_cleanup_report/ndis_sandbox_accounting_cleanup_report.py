from ndis_finance.services.sandbox_accounting_cleanup import execute_cleanup_report


def execute(filters=None):
    return execute_cleanup_report(filters)
