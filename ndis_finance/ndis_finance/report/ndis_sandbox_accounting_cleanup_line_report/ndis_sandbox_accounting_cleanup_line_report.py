from ndis_finance.services.sandbox_accounting_cleanup_pack import execute_cleanup_line_report


def execute(filters=None):
    return execute_cleanup_line_report(filters)
