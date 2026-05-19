from ndis_finance.services.production_readiness import execute_production_readiness_report


def execute(filters=None):
    return execute_production_readiness_report(filters)
