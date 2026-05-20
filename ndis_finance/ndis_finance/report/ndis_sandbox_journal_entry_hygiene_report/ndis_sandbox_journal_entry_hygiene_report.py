from ndis_finance.services.sandbox_accounting_cleanup import execute_hygiene_report


def execute(filters=None):
    return execute_hygiene_report(filters)
