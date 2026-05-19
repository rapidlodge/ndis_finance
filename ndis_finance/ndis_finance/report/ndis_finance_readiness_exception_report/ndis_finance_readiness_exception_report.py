from ndis_finance.services.production_readiness import execute_readiness_exception_report


def execute(filters=None):
    return execute_readiness_exception_report(filters)
