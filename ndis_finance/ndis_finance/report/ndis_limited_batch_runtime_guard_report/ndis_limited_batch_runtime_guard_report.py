from ndis_finance.services.limited_batch_runtime_guard import execute_guard_report


def execute(filters=None):
    return execute_guard_report(filters)
