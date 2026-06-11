from ndis_finance.services.limited_batch_runtime_guard import execute_guardrail_report


def execute(filters=None):
    return execute_guardrail_report(filters)
