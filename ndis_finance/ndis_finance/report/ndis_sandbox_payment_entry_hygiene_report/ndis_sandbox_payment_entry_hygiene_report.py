from ndis_finance.services.sandbox_payment_entry_cleanup import execute_hygiene_report


def execute(filters=None):
    return execute_hygiene_report(filters)
