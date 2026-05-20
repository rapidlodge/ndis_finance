from ndis_finance.services.accounting_posting_requests import execute_request_line_report


def execute(filters=None):
    return execute_request_line_report(filters)
