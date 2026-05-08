import frappe
from frappe import _
from frappe.utils import flt, today


def currency():
    return frappe.defaults.get_global_default("currency") or "AUD"


def get_filter(filters, key, default=None):
    if not filters:
        return default
    return filters.get(key) or default


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)


def add_date_filters(filters, field, alias=None):
    prefix = f"{alias}." if alias else ""
    conditions = []
    params = {}

    from_date = get_filter(filters, "from_date")
    to_date = get_filter(filters, "to_date")

    if from_date:
        conditions.append(f"{prefix}{field} >= %(from_date)s")
        params["from_date"] = from_date

    if to_date:
        conditions.append(f"{prefix}{field} <= %(to_date)s")
        params["to_date"] = to_date

    return conditions, params


def add_common_claim_filters(filters, alias="cl"):
    conditions = []
    params = {}
    prefix = f"{alias}." if alias else ""

    participant = get_filter(filters, "participant")
    house = get_filter(filters, "house")
    funding_source = get_filter(filters, "funding_source")
    support_item_number = get_filter(filters, "support_item_number")
    claim_status = get_filter(filters, "claim_status")

    if participant:
        conditions.append(f"{prefix}participant = %(participant)s")
        params["participant"] = participant

    if house:
        conditions.append(f"{prefix}house = %(house)s")
        params["house"] = house

    if funding_source:
        conditions.append(f"{prefix}funding_source = %(funding_source)s")
        params["funding_source"] = funding_source

    if support_item_number:
        conditions.append(f"{prefix}support_item_number = %(support_item_number)s")
        params["support_item_number"] = support_item_number

    if claim_status:
        conditions.append(f"{prefix}claim_status = %(claim_status)s")
        params["claim_status"] = claim_status

    date_conditions, date_params = add_date_filters(filters, "service_date", alias)
    conditions.extend(date_conditions)
    params.update(date_params)

    return conditions, params


def execute_funding_leakage_analytics_report(filters=None):
    filters = frappe._dict(filters or {})
    group_by = get_filter(filters, "group_by", "House")

    group_map = {
        "House": ("fl.house", "House", "Link", "NDIS House"),
        "Participant": ("fl.participant", "Participant", "Link", "Customer"),
        "Leakage Type": ("fl.leakage_type", "Leakage Type", "Data", None),
        "Severity": ("fl.severity", "Severity", "Data", None),
        "Status": ("fl.status", "Status", "Data", None),
    }

    group_expr, group_label, group_fieldtype, group_options = group_map.get(
        group_by, group_map["House"]
    )

    columns = [
        {
            "fieldname": "group_key",
            "label": _(group_label),
            "fieldtype": group_fieldtype,
            "options": group_options,
            "width": 210,
        },
        {"fieldname": "leakage_count", "label": _("Leakage Count"), "fieldtype": "Int", "width": 120},
        {
            "fieldname": "expected_amount",
            "label": _("Expected Amount"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 150,
        },
        {
            "fieldname": "actual_amount",
            "label": _("Actual Amount"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 150,
        },
        {
            "fieldname": "variance_amount",
            "label": _("Variance / Leakage"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 150,
        },
        {
            "fieldname": "open_amount",
            "label": _("Open Amount"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 140,
        },
        {
            "fieldname": "resolved_amount",
            "label": _("Resolved Amount"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 150,
        },
        {
            "fieldname": "written_off_amount",
            "label": _("Written Off Amount"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 160,
        },
        {"fieldname": "critical_count", "label": _("Critical"), "fieldtype": "Int", "width": 90},
        {"fieldname": "high_count", "label": _("High"), "fieldtype": "Int", "width": 90},
        {"fieldname": "medium_count", "label": _("Medium"), "fieldtype": "Int", "width": 90},
        {"fieldname": "low_count", "label": _("Low"), "fieldtype": "Int", "width": 90},
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

    participant = get_filter(filters, "participant")
    house = get_filter(filters, "house")
    leakage_type = get_filter(filters, "leakage_type")
    status = get_filter(filters, "status")
    open_only = get_filter(filters, "open_only")

    if participant:
        conditions.append("fl.participant = %(participant)s")
        params["participant"] = participant

    if house:
        conditions.append("fl.house = %(house)s")
        params["house"] = house

    if leakage_type:
        conditions.append("fl.leakage_type = %(leakage_type)s")
        params["leakage_type"] = leakage_type

    if status:
        conditions.append("fl.status = %(status)s")
        params["status"] = status

    if open_only:
        conditions.append("fl.status IN ('Open', 'In Review')")

    date_conditions, date_params = add_date_filters(filters, "service_date", "fl")
    conditions.extend(date_conditions)
    params.update(date_params)

    data = frappe.db.sql(
        f"""
        SELECT
            COALESCE({group_expr}, 'Unassigned') AS group_key,
            COUNT(*) AS leakage_count,
            COALESCE(SUM(fl.expected_amount), 0) AS expected_amount,
            COALESCE(SUM(fl.actual_amount), 0) AS actual_amount,
            COALESCE(SUM(fl.variance_amount), 0) AS variance_amount,
            COALESCE(SUM(CASE WHEN fl.status IN ('Open', 'In Review') THEN fl.variance_amount ELSE 0 END), 0) AS open_amount,
            COALESCE(SUM(CASE WHEN fl.status = 'Resolved' THEN fl.variance_amount ELSE 0 END), 0) AS resolved_amount,
            COALESCE(SUM(CASE WHEN fl.status = 'Written Off' THEN fl.variance_amount ELSE 0 END), 0) AS written_off_amount,
            COALESCE(SUM(CASE WHEN fl.severity = 'Critical' THEN 1 ELSE 0 END), 0) AS critical_count,
            COALESCE(SUM(CASE WHEN fl.severity = 'High' THEN 1 ELSE 0 END), 0) AS high_count,
            COALESCE(SUM(CASE WHEN fl.severity = 'Medium' THEN 1 ELSE 0 END), 0) AS medium_count,
            COALESCE(SUM(CASE WHEN fl.severity = 'Low' THEN 1 ELSE 0 END), 0) AS low_count,
            %(currency)s AS currency
        FROM `tabNDIS Funding Leakage Register` fl
        {build_where(conditions)}
        GROUP BY COALESCE({group_expr}, 'Unassigned')
        ORDER BY variance_amount DESC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.group_key for row in data[:20]],
            "datasets": [
                {
                    "name": "Leakage Amount",
                    "values": [flt(row.variance_amount) for row in data[:20]],
                }
            ],
        },
        "type": "bar",
    }

    total_leakage = sum(flt(row.variance_amount) for row in data)
    open_leakage = sum(flt(row.open_amount) for row in data)
    critical_items = sum(int(row.critical_count or 0) for row in data)

    summary = [
        {
            "value": sum(int(row.leakage_count or 0) for row in data),
            "indicator": "Red" if data else "Green",
            "label": _("Leakage Records"),
            "datatype": "Int",
        },
        {
            "value": total_leakage,
            "indicator": "Red" if total_leakage else "Green",
            "label": _("Total Leakage"),
            "datatype": "Currency",
            "currency": currency(),
        },
        {
            "value": open_leakage,
            "indicator": "Orange" if open_leakage else "Green",
            "label": _("Open Leakage"),
            "datatype": "Currency",
            "currency": currency(),
        },
        {
            "value": critical_items,
            "indicator": "Red" if critical_items else "Green",
            "label": _("Critical Items"),
            "datatype": "Int",
        },
    ]

    return columns, data, None, chart, summary


def execute_claim_cycle_time_report(filters=None):
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
        {"fieldname": "claim_status", "label": _("Claim Status"), "fieldtype": "Data", "width": 130},
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
            "fieldname": "sales_invoice",
            "label": _("Sales Invoice"),
            "fieldtype": "Link",
            "options": "Sales Invoice",
            "width": 180,
        },
        {
            "fieldname": "claim_export",
            "label": _("Claim Export"),
            "fieldtype": "Link",
            "options": "NDIS Claim Export",
            "width": 180,
        },
        {
            "fieldname": "exported_on",
            "label": _("Exported On"),
            "fieldtype": "Datetime",
            "width": 160,
        },
        {
            "fieldname": "remittance_import",
            "label": _("Remittance Import"),
            "fieldtype": "Link",
            "options": "NDIS Remittance Import",
            "width": 180,
        },
        {"fieldname": "payment_date", "label": _("Payment Date"), "fieldtype": "Date", "width": 120},
        {
            "fieldname": "days_service_to_export",
            "label": _("Service To Export Days"),
            "fieldtype": "Int",
            "width": 155,
        },
        {
            "fieldname": "days_service_to_payment",
            "label": _("Service To Payment Days"),
            "fieldtype": "Int",
            "width": 165,
        },
        {
            "fieldname": "days_export_to_payment",
            "label": _("Export To Payment Days"),
            "fieldtype": "Int",
            "width": 155,
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
            "fieldname": "currency",
            "label": _("Currency"),
            "fieldtype": "Link",
            "options": "Currency",
            "hidden": 1,
        },
    ]

    conditions, params = add_common_claim_filters(filters, "cl")
    params["currency"] = currency()

    data = frappe.db.sql(
        f"""
        SELECT
            cl.name AS claim_line,
            cl.claim_batch,
            cl.claim_status,
            cl.participant,
            cl.house,
            cl.funding_source,
            cl.service_date,
            cl.sales_invoice,
            cl.claim_export,
            cl.exported_on,
            cl.remittance_import,
            cl.payment_date,
            CASE
                WHEN cl.service_date IS NOT NULL
                    AND cl.exported_on IS NOT NULL
                    AND DATE(cl.exported_on) >= cl.service_date
                    THEN DATEDIFF(DATE(cl.exported_on), cl.service_date)
                ELSE NULL
            END AS days_service_to_export,
            CASE
                WHEN cl.service_date IS NOT NULL
                    AND cl.payment_date IS NOT NULL
                    AND cl.payment_date >= cl.service_date
                    THEN DATEDIFF(cl.payment_date, cl.service_date)
                ELSE NULL
            END AS days_service_to_payment,
            CASE
                WHEN cl.exported_on IS NOT NULL
                    AND cl.payment_date IS NOT NULL
                    AND cl.payment_date >= DATE(cl.exported_on)
                    THEN DATEDIFF(cl.payment_date, DATE(cl.exported_on))
                ELSE NULL
            END AS days_export_to_payment,
            cl.claim_amount,
            cl.paid_amount,
            cl.shortfall_amount,
            %(currency)s AS currency
        FROM `tabNDIS Claim Line` cl
        {build_where(conditions)}
        ORDER BY cl.service_date DESC, cl.modified DESC
        LIMIT 500
        """,
        params,
        as_dict=True,
    )

    avg_service_to_export = average([row.days_service_to_export for row in data])
    avg_service_to_payment = average([row.days_service_to_payment for row in data])

    chart_buckets = {
        "0-7": 0,
        "8-14": 0,
        "15-30": 0,
        "31-60": 0,
        "60+": 0,
        "No Payment": 0,
    }

    for row in data:
        days = row.days_service_to_payment
        if days is None:
            chart_buckets["No Payment"] += 1
        elif days <= 7:
            chart_buckets["0-7"] += 1
        elif days <= 14:
            chart_buckets["8-14"] += 1
        elif days <= 30:
            chart_buckets["15-30"] += 1
        elif days <= 60:
            chart_buckets["31-60"] += 1
        else:
            chart_buckets["60+"] += 1

    chart = {
        "data": {
            "labels": list(chart_buckets.keys()),
            "datasets": [{"name": "Claim Lines", "values": list(chart_buckets.values())}],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Claim Lines"), "datatype": "Int"},
        {
            "value": avg_service_to_export,
            "indicator": "Blue",
            "label": _("Avg Service To Export Days"),
            "datatype": "Float",
        },
        {
            "value": avg_service_to_payment,
            "indicator": "Blue",
            "label": _("Avg Service To Payment Days"),
            "datatype": "Float",
        },
        {
            "value": sum(flt(row.shortfall_amount) for row in data),
            "indicator": "Red",
            "label": _("Total Shortfall"),
            "datatype": "Currency",
            "currency": currency(),
        },
    ]

    return columns, data, None, chart, summary


def execute_house_profitability_foundation_report(filters=None):
    return execute_profitability_foundation(
        filters=filters, group_by="house", label="House", options="NDIS House"
    )


def execute_participant_profitability_foundation_report(filters=None):
    return execute_profitability_foundation(
        filters=filters, group_by="participant", label="Participant", options="Customer"
    )


def execute_profitability_foundation(filters=None, group_by="house", label="House", options=None):
    filters = frappe._dict(filters or {})

    columns = [
        {
            "fieldname": "group_key",
            "label": _(label),
            "fieldtype": "Link",
            "options": options,
            "width": 220,
        },
        {"fieldname": "claim_line_count", "label": _("Claim Lines"), "fieldtype": "Int", "width": 110},
        {"fieldname": "invoice_count", "label": _("Invoices"), "fieldtype": "Int", "width": 100},
        {
            "fieldname": "gross_claim_amount",
            "label": _("Gross Claim Amount"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 160,
        },
        {
            "fieldname": "paid_amount",
            "label": _("Paid Amount"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 140,
        },
        {
            "fieldname": "shortfall_amount",
            "label": _("Shortfall Amount"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 150,
        },
        {
            "fieldname": "open_recovery_amount",
            "label": _("Open Recovery"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 150,
        },
        {
            "fieldname": "recovered_amount",
            "label": _("Recovered Amount"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 150,
        },
        {
            "fieldname": "written_off_amount",
            "label": _("Written Off"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 140,
        },
        {
            "fieldname": "revenue_realisation_percent",
            "label": _("Realisation %"),
            "fieldtype": "Percent",
            "width": 120,
        },
        {
            "fieldname": "leakage_percent",
            "label": _("Leakage %"),
            "fieldtype": "Percent",
            "width": 110,
        },
        {"fieldname": "paid_count", "label": _("Paid Lines"), "fieldtype": "Int", "width": 100},
        {"fieldname": "short_paid_count", "label": _("Short Paid"), "fieldtype": "Int", "width": 100},
        {"fieldname": "rejected_count", "label": _("Rejected"), "fieldtype": "Int", "width": 100},
        {
            "fieldname": "currency",
            "label": _("Currency"),
            "fieldtype": "Link",
            "options": "Currency",
            "hidden": 1,
        },
    ]

    conditions, params = add_common_claim_filters(filters, "cl")
    params["currency"] = currency()

    group_expr = f"cl.{group_by}"

    data = frappe.db.sql(
        f"""
        SELECT
            COALESCE({group_expr}, 'Unassigned') AS group_key,
            COUNT(*) AS claim_line_count,
            COUNT(DISTINCT cl.sales_invoice) AS invoice_count,
            COALESCE(SUM(cl.claim_amount), 0) AS gross_claim_amount,
            COALESCE(SUM(cl.paid_amount), 0) AS paid_amount,
            COALESCE(SUM(cl.shortfall_amount), 0) AS shortfall_amount,
            COALESCE(SUM(rc.open_recovery_amount), 0) AS open_recovery_amount,
            COALESCE(SUM(rc.recovered_amount), 0) AS recovered_amount,
            COALESCE(SUM(rc.written_off_amount), 0) AS written_off_amount,
            CASE
                WHEN COALESCE(SUM(cl.claim_amount), 0) > 0 THEN ROUND((COALESCE(SUM(cl.paid_amount), 0) / COALESCE(SUM(cl.claim_amount), 0)) * 100, 2)
                ELSE 0
            END AS revenue_realisation_percent,
            CASE
                WHEN COALESCE(SUM(cl.claim_amount), 0) > 0 THEN ROUND((COALESCE(SUM(cl.shortfall_amount), 0) / COALESCE(SUM(cl.claim_amount), 0)) * 100, 2)
                ELSE 0
            END AS leakage_percent,
            COALESCE(SUM(CASE WHEN cl.claim_status = 'Paid' THEN 1 ELSE 0 END), 0) AS paid_count,
            COALESCE(SUM(CASE WHEN cl.claim_status = 'Short Paid' THEN 1 ELSE 0 END), 0) AS short_paid_count,
            COALESCE(SUM(CASE WHEN cl.claim_status = 'Rejected' THEN 1 ELSE 0 END), 0) AS rejected_count,
            %(currency)s AS currency
        FROM `tabNDIS Claim Line` cl
        LEFT JOIN (
            SELECT
                claim_line,
                SUM(CASE WHEN status IN ('Open', 'In Follow Up', 'Waiting For Response', 'Escalated') THEN outstanding_amount ELSE 0 END) AS open_recovery_amount,
                SUM(recovered_amount) AS recovered_amount,
                SUM(written_off_amount) AS written_off_amount
            FROM `tabNDIS Recovery Case`
            WHERE claim_line IS NOT NULL AND claim_line != ''
            GROUP BY claim_line
        ) rc ON rc.claim_line = cl.name
        {build_where(conditions)}
        GROUP BY COALESCE({group_expr}, 'Unassigned')
        ORDER BY gross_claim_amount DESC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.group_key for row in data[:20]],
            "datasets": [
                {"name": "Gross Claims", "values": [flt(row.gross_claim_amount) for row in data[:20]]},
                {"name": "Paid", "values": [flt(row.paid_amount) for row in data[:20]]},
                {"name": "Shortfall", "values": [flt(row.shortfall_amount) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {
            "value": sum(flt(row.gross_claim_amount) for row in data),
            "indicator": "Blue",
            "label": _("Gross Claims"),
            "datatype": "Currency",
            "currency": currency(),
        },
        {
            "value": sum(flt(row.paid_amount) for row in data),
            "indicator": "Green",
            "label": _("Paid Amount"),
            "datatype": "Currency",
            "currency": currency(),
        },
        {
            "value": sum(flt(row.shortfall_amount) for row in data),
            "indicator": "Red",
            "label": _("Shortfall"),
            "datatype": "Currency",
            "currency": currency(),
        },
        {
            "value": average([row.revenue_realisation_percent for row in data]),
            "indicator": "Blue",
            "label": _("Avg Realisation %"),
            "datatype": "Percent",
        },
    ]

    return columns, data, None, chart, summary


def average(values):
    clean = [flt(value) for value in values if value is not None]
    if not clean:
        return 0
    return round(sum(clean) / len(clean), 2)


@frappe.whitelist()
def quick_finance_analytics_summary():
    open_leakage = frappe.db.sql(
        """
        SELECT COALESCE(SUM(variance_amount), 0) AS amount, COUNT(*) AS count
        FROM `tabNDIS Funding Leakage Register`
        WHERE status IN ('Open', 'In Review')
        """,
        as_dict=True,
    )[0]

    claim_totals = frappe.db.sql(
        """
        SELECT
            COALESCE(SUM(claim_amount), 0) AS gross_claims,
            COALESCE(SUM(paid_amount), 0) AS paid_amount,
            COALESCE(SUM(shortfall_amount), 0) AS shortfall_amount,
            COUNT(*) AS claim_line_count
        FROM `tabNDIS Claim Line`
        """,
        as_dict=True,
    )[0]

    top_house_leakage = frappe.db.sql(
        """
        SELECT
            COALESCE(house, 'Unassigned') AS house,
            COALESCE(SUM(variance_amount), 0) AS leakage_amount,
            COUNT(*) AS leakage_count
        FROM `tabNDIS Funding Leakage Register`
        GROUP BY COALESCE(house, 'Unassigned')
        ORDER BY leakage_amount DESC
        LIMIT 10
        """,
        as_dict=True,
    )

    top_participant_shortfalls = frappe.db.sql(
        """
        SELECT
            COALESCE(participant, 'Unassigned') AS participant,
            COALESCE(SUM(shortfall_amount), 0) AS shortfall_amount,
            COUNT(*) AS claim_line_count
        FROM `tabNDIS Claim Line`
        GROUP BY COALESCE(participant, 'Unassigned')
        ORDER BY shortfall_amount DESC
        LIMIT 10
        """,
        as_dict=True,
    )

    return {
        "today": today(),
        "open_leakage": open_leakage,
        "claim_totals": claim_totals,
        "top_house_leakage": top_house_leakage,
        "top_participant_shortfalls": top_participant_shortfalls,
        "note": (
            "Analytics only. No Payment Entry, Journal Entry, GL Entry, allocation, "
            "payroll costing, or accounting movement created."
        ),
    }
