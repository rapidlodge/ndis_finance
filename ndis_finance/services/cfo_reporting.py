import frappe
from frappe import _
from frappe.utils import flt, today


OPEN_RECOVERY_STATUSES = ["Open", "In Follow Up", "Waiting For Response", "Escalated"]
EXCEPTION_CLAIM_STATUSES = ["Short Paid", "Rejected", "Reclaim Required"]


def get_filter(filters, key, default=None):
    if not filters:
        return default
    return filters.get(key) or default


def currency():
    return frappe.defaults.get_global_default("currency") or "AUD"


def get_date_filters(filters, date_field, alias=None):
    alias_prefix = f"{alias}." if alias else ""
    conditions = []
    params = {}

    from_date = get_filter(filters, "from_date")
    to_date = get_filter(filters, "to_date")

    if from_date:
        conditions.append(f"{alias_prefix}{date_field} >= %(from_date)s")
        params["from_date"] = from_date

    if to_date:
        conditions.append(f"{alias_prefix}{date_field} <= %(to_date)s")
        params["to_date"] = to_date

    return conditions, params


def add_common_conditions(filters, table_alias=None, fields=None):
    fields = fields or {}
    prefix = f"{table_alias}." if table_alias else ""
    conditions = []
    params = {}

    participant = get_filter(filters, "participant")
    funding_source = get_filter(filters, "funding_source")
    house = get_filter(filters, "house")
    status = get_filter(filters, "status")

    if participant and fields.get("participant", True):
        conditions.append(f"{prefix}participant = %(participant)s")
        params["participant"] = participant

    if funding_source and fields.get("funding_source", True):
        conditions.append(f"{prefix}funding_source = %(funding_source)s")
        params["funding_source"] = funding_source

    if house and fields.get("house", True):
        conditions.append(f"{prefix}house = %(house)s")
        params["house"] = house

    if status and fields.get("status", True):
        conditions.append(f"{prefix}status = %(status)s")
        params["status"] = status

    return conditions, params


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)


def get_report_summary():
    open_cases = frappe.db.count(
        "NDIS Recovery Case",
        {"status": ["in", OPEN_RECOVERY_STATUSES]},
    )

    overdue_cases = frappe.db.count(
        "NDIS Recovery Case",
        {
            "status": ["in", OPEN_RECOVERY_STATUSES],
            "next_follow_up_date": ["<=", today()],
        },
    )

    open_leakage_amount = frappe.db.sql(
        """
        SELECT COALESCE(SUM(variance_amount), 0)
        FROM `tabNDIS Funding Leakage Register`
        WHERE status IN ('Open', 'In Review')
        """
    )[0][0]

    claim_exception_amount = frappe.db.sql(
        """
        SELECT COALESCE(SUM(shortfall_amount), 0)
        FROM `tabNDIS Claim Line`
        WHERE claim_status IN ('Short Paid', 'Rejected', 'Reclaim Required')
        """
    )[0][0]

    rejected_claims = frappe.db.count(
        "NDIS Claim Line",
        {"claim_status": "Rejected"},
    )

    return [
        {
            "value": open_cases,
            "indicator": "Red" if open_cases else "Green",
            "label": _("Open Recovery Cases"),
            "datatype": "Int",
        },
        {
            "value": overdue_cases,
            "indicator": "Red" if overdue_cases else "Green",
            "label": _("Overdue Follow Ups"),
            "datatype": "Int",
        },
        {
            "value": flt(open_leakage_amount),
            "indicator": "Red" if flt(open_leakage_amount) else "Green",
            "label": _("Open Leakage Amount"),
            "datatype": "Currency",
            "currency": currency(),
        },
        {
            "value": flt(claim_exception_amount),
            "indicator": "Red" if flt(claim_exception_amount) else "Green",
            "label": _("Claim Exception Amount"),
            "datatype": "Currency",
            "currency": currency(),
        },
        {
            "value": rejected_claims,
            "indicator": "Red" if rejected_claims else "Green",
            "label": _("Rejected Claims"),
            "datatype": "Int",
        },
    ]


def get_cfo_exception_chart():
    rows = frappe.db.sql(
        """
        SELECT case_type AS label, COUNT(*) AS value
        FROM `tabNDIS Recovery Case`
        WHERE status IN ('Open', 'In Follow Up', 'Waiting For Response', 'Escalated')
        GROUP BY case_type
        ORDER BY value DESC
        """,
        as_dict=True,
    )

    return {
        "data": {
            "labels": [row.label or "Unknown" for row in rows],
            "datasets": [
                {
                    "name": "Open Cases",
                    "values": [row.value for row in rows],
                }
            ],
        },
        "type": "bar",
    }


def execute_cfo_exception_dashboard(filters=None):
    filters = frappe._dict(filters or {})

    columns = [
        {"fieldname": "source", "label": _("Source"), "fieldtype": "Data", "width": 150},
        {
            "fieldname": "record",
            "label": _("Record"),
            "fieldtype": "Dynamic Link",
            "options": "source_doctype",
            "width": 210,
        },
        {
            "fieldname": "source_doctype",
            "label": _("Source DocType"),
            "fieldtype": "Data",
            "hidden": 1,
        },
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 140},
        {"fieldname": "priority", "label": _("Priority"), "fieldtype": "Data", "width": 100},
        {
            "fieldname": "participant",
            "label": _("Participant"),
            "fieldtype": "Link",
            "options": "Customer",
            "width": 170,
        },
        {
            "fieldname": "house",
            "label": _("House"),
            "fieldtype": "Link",
            "options": "NDIS House",
            "width": 170,
        },
        {
            "fieldname": "funding_source",
            "label": _("Funding Source"),
            "fieldtype": "Link",
            "options": "NDIS Funding Source",
            "width": 150,
        },
        {
            "fieldname": "sales_invoice",
            "label": _("Sales Invoice"),
            "fieldtype": "Link",
            "options": "Sales Invoice",
            "width": 180,
        },
        {
            "fieldname": "claim_line",
            "label": _("Claim Line"),
            "fieldtype": "Link",
            "options": "NDIS Claim Line",
            "width": 180,
        },
        {
            "fieldname": "expected_amount",
            "label": _("Expected"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 120,
        },
        {
            "fieldname": "paid_amount",
            "label": _("Paid"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 120,
        },
        {
            "fieldname": "outstanding_amount",
            "label": _("Outstanding"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 130,
        },
        {
            "fieldname": "next_follow_up_date",
            "label": _("Next Follow Up"),
            "fieldtype": "Date",
            "width": 130,
        },
        {
            "fieldname": "assigned_to",
            "label": _("Assigned To"),
            "fieldtype": "Link",
            "options": "User",
            "width": 170,
        },
        {
            "fieldname": "currency",
            "label": _("Currency"),
            "fieldtype": "Link",
            "options": "Currency",
            "hidden": 1,
        },
    ]

    conditions = [
        "rc.status IN ('Open', 'In Follow Up', 'Waiting For Response', 'Escalated', 'Written Off')"
    ]
    params = {}

    common_conditions, common_params = add_common_conditions(filters, "rc")
    conditions.extend(common_conditions)
    params.update(common_params)

    if get_filter(filters, "case_type"):
        conditions.append("rc.case_type = %(case_type)s")
        params["case_type"] = get_filter(filters, "case_type")

    if get_filter(filters, "overdue_only"):
        conditions.append("rc.next_follow_up_date <= %(today)s")
        params["today"] = today()

    date_conditions, date_params = get_date_filters(filters, "case_opened_on", "rc")
    conditions.extend(date_conditions)
    params.update(date_params)

    data = frappe.db.sql(
        f"""
        SELECT
            'Recovery Case' AS source,
            rc.name AS record,
            'NDIS Recovery Case' AS source_doctype,
            rc.status,
            rc.priority,
            rc.participant,
            rc.house,
            rc.funding_source,
            rc.sales_invoice,
            rc.claim_line,
            rc.expected_amount,
            rc.paid_amount,
            rc.outstanding_amount,
            rc.next_follow_up_date,
            rc.assigned_to,
            %(currency)s AS currency
        FROM `tabNDIS Recovery Case` rc
        {build_where(conditions)}
        ORDER BY
            CASE rc.priority
                WHEN 'Critical' THEN 1
                WHEN 'High' THEN 2
                WHEN 'Medium' THEN 3
                ELSE 4
            END,
            rc.next_follow_up_date ASC,
            rc.modified DESC
        """,
        {**params, "currency": currency()},
        as_dict=True,
    )

    chart = get_cfo_exception_chart()
    summary = get_report_summary()

    return columns, data, None, chart, summary


def execute_recovery_ageing_report(filters=None):
    filters = frappe._dict(filters or {})

    columns = [
        {
            "fieldname": "recovery_case",
            "label": _("Recovery Case"),
            "fieldtype": "Link",
            "options": "NDIS Recovery Case",
            "width": 190,
        },
        {"fieldname": "case_type", "label": _("Case Type"), "fieldtype": "Data", "width": 170},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 140},
        {"fieldname": "priority", "label": _("Priority"), "fieldtype": "Data", "width": 100},
        {
            "fieldname": "participant",
            "label": _("Participant"),
            "fieldtype": "Link",
            "options": "Customer",
            "width": 170,
        },
        {
            "fieldname": "sales_invoice",
            "label": _("Sales Invoice"),
            "fieldtype": "Link",
            "options": "Sales Invoice",
            "width": 180,
        },
        {
            "fieldname": "claim_line",
            "label": _("Claim Line"),
            "fieldtype": "Link",
            "options": "NDIS Claim Line",
            "width": 180,
        },
        {
            "fieldname": "outstanding_amount",
            "label": _("Outstanding"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 130,
        },
        {
            "fieldname": "case_opened_on",
            "label": _("Opened On"),
            "fieldtype": "Datetime",
            "width": 160,
        },
        {"fieldname": "age_days", "label": _("Age Days"), "fieldtype": "Int", "width": 90},
        {"fieldname": "age_bucket", "label": _("Age Bucket"), "fieldtype": "Data", "width": 110},
        {
            "fieldname": "last_follow_up_on",
            "label": _("Last Follow Up"),
            "fieldtype": "Datetime",
            "width": 160,
        },
        {
            "fieldname": "next_follow_up_date",
            "label": _("Next Follow Up"),
            "fieldtype": "Date",
            "width": 130,
        },
        {
            "fieldname": "assigned_to",
            "label": _("Assigned To"),
            "fieldtype": "Link",
            "options": "User",
            "width": 170,
        },
        {
            "fieldname": "currency",
            "label": _("Currency"),
            "fieldtype": "Link",
            "options": "Currency",
            "hidden": 1,
        },
    ]

    conditions = []
    params = {"today": today(), "currency": currency()}

    if get_filter(filters, "status"):
        conditions.append("rc.status = %(status)s")
        params["status"] = get_filter(filters, "status")
    else:
        conditions.append("rc.status IN ('Open', 'In Follow Up', 'Waiting For Response', 'Escalated')")

    common_conditions, common_params = add_common_conditions(
        filters,
        "rc",
        fields={"status": False},
    )
    conditions.extend(common_conditions)
    params.update(common_params)

    if get_filter(filters, "overdue_only"):
        conditions.append("rc.next_follow_up_date <= %(today)s")

    rows = frappe.db.sql(
        f"""
        SELECT
            rc.name AS recovery_case,
            rc.case_type,
            rc.status,
            rc.priority,
            rc.participant,
            rc.sales_invoice,
            rc.claim_line,
            rc.outstanding_amount,
            rc.case_opened_on,
            DATEDIFF(%(today)s, DATE(rc.case_opened_on)) AS age_days,
            CASE
                WHEN DATEDIFF(%(today)s, DATE(rc.case_opened_on)) <= 7 THEN '0-7'
                WHEN DATEDIFF(%(today)s, DATE(rc.case_opened_on)) <= 14 THEN '8-14'
                WHEN DATEDIFF(%(today)s, DATE(rc.case_opened_on)) <= 30 THEN '15-30'
                WHEN DATEDIFF(%(today)s, DATE(rc.case_opened_on)) <= 60 THEN '31-60'
                ELSE '60+'
            END AS age_bucket,
            rc.last_follow_up_on,
            rc.next_follow_up_date,
            rc.assigned_to,
            %(currency)s AS currency
        FROM `tabNDIS Recovery Case` rc
        {build_where(conditions)}
        ORDER BY age_days DESC, rc.outstanding_amount DESC
        """,
        params,
        as_dict=True,
    )

    chart_map = {}
    for row in rows:
        chart_map[row.age_bucket] = chart_map.get(row.age_bucket, 0) + flt(row.outstanding_amount)

    labels = ["0-7", "8-14", "15-30", "31-60", "60+"]
    chart = {
        "data": {
            "labels": labels,
            "datasets": [
                {"name": "Outstanding", "values": [chart_map.get(label, 0) for label in labels]}
            ],
        },
        "type": "bar",
    }

    summary = [
        {
            "value": len(rows),
            "indicator": "Red" if rows else "Green",
            "label": _("Recovery Cases"),
            "datatype": "Int",
        },
        {
            "value": sum(flt(row.outstanding_amount) for row in rows),
            "indicator": "Red" if rows else "Green",
            "label": _("Outstanding"),
            "datatype": "Currency",
            "currency": currency(),
        },
    ]

    return columns, rows, None, chart, summary


def execute_claim_exception_report(filters=None):
    filters = frappe._dict(filters or {})

    columns = [
        {
            "fieldname": "claim_line",
            "label": _("Claim Line"),
            "fieldtype": "Link",
            "options": "NDIS Claim Line",
            "width": 180,
        },
        {
            "fieldname": "claim_batch",
            "label": _("Claim Batch"),
            "fieldtype": "Link",
            "options": "NDIS Claim Batch",
            "width": 180,
        },
        {
            "fieldname": "claim_status",
            "label": _("Claim Status"),
            "fieldtype": "Data",
            "width": 130,
        },
        {
            "fieldname": "payment_status",
            "label": _("Payment Status"),
            "fieldtype": "Data",
            "width": 130,
        },
        {
            "fieldname": "participant",
            "label": _("Participant"),
            "fieldtype": "Link",
            "options": "Customer",
            "width": 170,
        },
        {
            "fieldname": "house",
            "label": _("House"),
            "fieldtype": "Link",
            "options": "NDIS House",
            "width": 160,
        },
        {
            "fieldname": "funding_source",
            "label": _("Funding Source"),
            "fieldtype": "Link",
            "options": "NDIS Funding Source",
            "width": 150,
        },
        {"fieldname": "service_date", "label": _("Service Date"), "fieldtype": "Date", "width": 120},
        {
            "fieldname": "support_item_number",
            "label": _("Support Item No"),
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "fieldname": "sales_invoice",
            "label": _("Sales Invoice"),
            "fieldtype": "Link",
            "options": "Sales Invoice",
            "width": 180,
        },
        {
            "fieldname": "claim_amount",
            "label": _("Claim Amount"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 130,
        },
        {
            "fieldname": "paid_amount",
            "label": _("Paid Amount"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 130,
        },
        {
            "fieldname": "shortfall_amount",
            "label": _("Shortfall"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 130,
        },
        {
            "fieldname": "reconciliation_status",
            "label": _("Reconciliation"),
            "fieldtype": "Data",
            "width": 150,
        },
        {
            "fieldname": "recovery_status",
            "label": _("Recovery"),
            "fieldtype": "Data",
            "width": 140,
        },
        {
            "fieldname": "recovery_case",
            "label": _("Recovery Case"),
            "fieldtype": "Link",
            "options": "NDIS Recovery Case",
            "width": 180,
        },
        {"fieldname": "rejection_reason", "label": _("Reason"), "fieldtype": "Small Text", "width": 220},
        {
            "fieldname": "currency",
            "label": _("Currency"),
            "fieldtype": "Link",
            "options": "Currency",
            "hidden": 1,
        },
    ]

    conditions = ["cl.claim_status IN ('Short Paid', 'Rejected', 'Reclaim Required')"]
    params = {"currency": currency()}

    common_conditions, common_params = add_common_conditions(filters, "cl")
    conditions.extend(common_conditions)
    params.update(common_params)

    date_conditions, date_params = get_date_filters(filters, "service_date", "cl")
    conditions.extend(date_conditions)
    params.update(date_params)

    if get_filter(filters, "claim_status"):
        conditions.append("cl.claim_status = %(claim_status)s")
        params["claim_status"] = get_filter(filters, "claim_status")

    rows = frappe.db.sql(
        f"""
        SELECT
            cl.name AS claim_line,
            cl.claim_batch,
            cl.claim_status,
            cl.payment_status,
            cl.participant,
            cl.house,
            cl.funding_source,
            cl.service_date,
            cl.support_item_number,
            cl.sales_invoice,
            cl.claim_amount,
            cl.paid_amount,
            cl.shortfall_amount,
            cl.reconciliation_status,
            cl.recovery_status,
            cl.recovery_case,
            cl.rejection_reason,
            %(currency)s AS currency
        FROM `tabNDIS Claim Line` cl
        {build_where(conditions)}
        ORDER BY cl.service_date DESC, cl.shortfall_amount DESC
        """,
        params,
        as_dict=True,
    )

    chart_map = {}
    for row in rows:
        chart_map[row.claim_status] = chart_map.get(row.claim_status, 0) + flt(row.shortfall_amount)

    chart = {
        "data": {
            "labels": list(chart_map.keys()),
            "datasets": [{"name": "Shortfall", "values": list(chart_map.values())}],
        },
        "type": "bar",
    }

    summary = [
        {
            "value": len(rows),
            "indicator": "Red" if rows else "Green",
            "label": _("Claim Exceptions"),
            "datatype": "Int",
        },
        {
            "value": sum(flt(row.shortfall_amount) for row in rows),
            "indicator": "Red" if rows else "Green",
            "label": _("Total Shortfall"),
            "datatype": "Currency",
            "currency": currency(),
        },
    ]

    return columns, rows, None, chart, summary


def execute_funding_leakage_report(filters=None):
    filters = frappe._dict(filters or {})

    columns = [
        {
            "fieldname": "funding_leakage",
            "label": _("Funding Leakage"),
            "fieldtype": "Link",
            "options": "NDIS Funding Leakage Register",
            "width": 190,
        },
        {"fieldname": "leakage_type", "label": _("Leakage Type"), "fieldtype": "Data", "width": 160},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {
            "fieldname": "recovery_status",
            "label": _("Recovery Status"),
            "fieldtype": "Data",
            "width": 150,
        },
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {
            "fieldname": "participant",
            "label": _("Participant"),
            "fieldtype": "Link",
            "options": "Customer",
            "width": 170,
        },
        {
            "fieldname": "house",
            "label": _("House"),
            "fieldtype": "Link",
            "options": "NDIS House",
            "width": 160,
        },
        {"fieldname": "service_date", "label": _("Service Date"), "fieldtype": "Date", "width": 120},
        {
            "fieldname": "claim_line",
            "label": _("Claim Line"),
            "fieldtype": "Link",
            "options": "NDIS Claim Line",
            "width": 180,
        },
        {
            "fieldname": "sales_invoice",
            "label": _("Sales Invoice"),
            "fieldtype": "Link",
            "options": "Sales Invoice",
            "width": 180,
        },
        {
            "fieldname": "expected_amount",
            "label": _("Expected"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 120,
        },
        {
            "fieldname": "actual_amount",
            "label": _("Actual"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 120,
        },
        {
            "fieldname": "variance_amount",
            "label": _("Variance"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 120,
        },
        {
            "fieldname": "recovery_case",
            "label": _("Recovery Case"),
            "fieldtype": "Link",
            "options": "NDIS Recovery Case",
            "width": 180,
        },
        {
            "fieldname": "assigned_to",
            "label": _("Assigned To"),
            "fieldtype": "Link",
            "options": "User",
            "width": 160,
        },
        {
            "fieldname": "follow_up_due_date",
            "label": _("Follow Up Due"),
            "fieldtype": "Date",
            "width": 130,
        },
        {
            "fieldname": "currency",
            "label": _("Currency"),
            "fieldtype": "Link",
            "options": "Currency",
            "hidden": 1,
        },
    ]

    conditions = []
    params = {"currency": currency()}

    common_conditions, common_params = add_common_conditions(filters, "fl")
    conditions.extend(common_conditions)
    params.update(common_params)

    date_conditions, date_params = get_date_filters(filters, "service_date", "fl")
    conditions.extend(date_conditions)
    params.update(date_params)

    if get_filter(filters, "leakage_type"):
        conditions.append("fl.leakage_type = %(leakage_type)s")
        params["leakage_type"] = get_filter(filters, "leakage_type")

    if get_filter(filters, "open_only"):
        conditions.append("fl.status IN ('Open', 'In Review')")

    rows = frappe.db.sql(
        f"""
        SELECT
            fl.name AS funding_leakage,
            fl.leakage_type,
            fl.status,
            fl.recovery_status,
            fl.severity,
            fl.participant,
            fl.house,
            fl.service_date,
            fl.claim_line,
            fl.sales_invoice,
            fl.expected_amount,
            fl.actual_amount,
            fl.variance_amount,
            fl.recovery_case,
            fl.assigned_to,
            fl.follow_up_due_date,
            %(currency)s AS currency
        FROM `tabNDIS Funding Leakage Register` fl
        {build_where(conditions)}
        ORDER BY fl.service_date DESC, fl.variance_amount DESC
        """,
        params,
        as_dict=True,
    )

    chart_map = {}
    for row in rows:
        chart_map[row.leakage_type] = chart_map.get(row.leakage_type, 0) + flt(row.variance_amount)

    chart = {
        "data": {
            "labels": list(chart_map.keys()),
            "datasets": [{"name": "Leakage Amount", "values": list(chart_map.values())}],
        },
        "type": "bar",
    }

    summary = [
        {
            "value": len(rows),
            "indicator": "Red" if rows else "Green",
            "label": _("Leakage Records"),
            "datatype": "Int",
        },
        {
            "value": sum(flt(row.variance_amount) for row in rows),
            "indicator": "Red" if rows else "Green",
            "label": _("Total Leakage"),
            "datatype": "Currency",
            "currency": currency(),
        },
    ]

    return columns, rows, None, chart, summary


@frappe.whitelist()
def quick_cfo_summary():
    return {
        "report_summary": get_report_summary(),
        "overdue_recovery_cases": frappe.get_all(
            "NDIS Recovery Case",
            filters={
                "status": ["in", OPEN_RECOVERY_STATUSES],
                "next_follow_up_date": ["<=", today()],
            },
            fields=[
                "name",
                "case_id",
                "case_type",
                "status",
                "priority",
                "assigned_to",
                "participant",
                "sales_invoice",
                "outstanding_amount",
                "next_follow_up_date",
            ],
            order_by="next_follow_up_date asc",
            limit=20,
        ),
        "recent_claim_exceptions": frappe.get_all(
            "NDIS Claim Line",
            filters={"claim_status": ["in", EXCEPTION_CLAIM_STATUSES]},
            fields=[
                "name",
                "claim_batch",
                "claim_status",
                "participant",
                "sales_invoice",
                "claim_amount",
                "paid_amount",
                "shortfall_amount",
                "recovery_status",
                "recovery_case",
            ],
            order_by="modified desc",
            limit=20,
        ),
    }
