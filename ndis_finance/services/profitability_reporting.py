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


def add_claim_filters(filters, alias="cl"):
    conditions = []
    params = {}
    prefix = f"{alias}." if alias else ""

    for key, fieldname in [
        ("from_date", "service_date"),
        ("to_date", "service_date"),
        ("house", "house"),
        ("participant", "participant"),
        ("funding_source", "funding_source"),
        ("support_item_number", "support_item_number"),
        ("claim_status", "claim_status"),
    ]:
        value = get_filter(filters, key)
        if not value:
            continue

        if key == "from_date":
            conditions.append(f"{prefix}{fieldname} >= %(from_date)s")
        elif key == "to_date":
            conditions.append(f"{prefix}{fieldname} <= %(to_date)s")
        else:
            conditions.append(f"{prefix}{fieldname} = %({key})s")

        params[key] = value

    return conditions, params


def add_cost_filters(filters, alias="cae"):
    conditions = [f"{alias}.status = 'Active'" if alias else "status = 'Active'"]
    params = {}
    prefix = f"{alias}." if alias else ""

    for key, fieldname in [
        ("from_date", "period_end"),
        ("to_date", "period_start"),
        ("house", "house"),
        ("participant", "participant"),
        ("cost_type", "cost_type"),
        ("allocation_method", "allocation_method"),
    ]:
        value = get_filter(filters, key)
        if not value:
            continue

        if key == "from_date":
            conditions.append(f"{prefix}{fieldname} >= %(from_date)s")
        elif key == "to_date":
            conditions.append(f"{prefix}{fieldname} <= %(to_date)s")
        else:
            conditions.append(f"{prefix}{fieldname} = %({key})s")

        params[key] = value

    return conditions, params


def margin_percent(revenue, cost):
    revenue = flt(revenue)
    cost = flt(cost)

    if revenue <= 0:
        return 0

    return round(((revenue - cost) / revenue) * 100, 2)


def leakage_percent(gross, shortfall):
    gross = flt(gross)
    shortfall = flt(shortfall)

    if gross <= 0:
        return 0

    return round((shortfall / gross) * 100, 2)


def realisation_percent(gross, paid):
    gross = flt(gross)
    paid = flt(paid)

    if gross <= 0:
        return 0

    return round((paid / gross) * 100, 2)


def get_revenue_by_group(filters, group_field):
    conditions, params = add_claim_filters(filters, "cl")
    group_expr = f"cl.{group_field}"

    return frappe.db.sql(
        f"""
        SELECT
            COALESCE(NULLIF({group_expr}, ''), 'Unassigned') AS group_key,
            COUNT(*) AS claim_line_count,
            COUNT(DISTINCT cl.sales_invoice) AS invoice_count,
            COALESCE(SUM(cl.claim_amount), 0) AS gross_claim_amount,
            COALESCE(SUM(cl.paid_amount), 0) AS paid_amount,
            COALESCE(SUM(cl.shortfall_amount), 0) AS shortfall_amount,
            COALESCE(SUM(CASE WHEN cl.claim_status = 'Paid' THEN 1 ELSE 0 END), 0) AS paid_count,
            COALESCE(SUM(CASE WHEN cl.claim_status = 'Short Paid' THEN 1 ELSE 0 END), 0) AS short_paid_count,
            COALESCE(SUM(CASE WHEN cl.claim_status = 'Rejected' THEN 1 ELSE 0 END), 0) AS rejected_count
        FROM `tabNDIS Claim Line` cl
        {build_where(conditions)}
        GROUP BY COALESCE(NULLIF({group_expr}, ''), 'Unassigned')
        """,
        params,
        as_dict=True,
    )


def get_cost_by_group(filters, group_field):
    conditions, params = add_cost_filters(filters, "cae")
    group_expr = f"cae.{group_field}"

    return frappe.db.sql(
        f"""
        SELECT
            COALESCE(NULLIF({group_expr}, ''), 'Unassigned') AS group_key,
            COUNT(*) AS cost_entry_count,
            COALESCE(SUM(cae.allocated_cost_amount), 0) AS allocated_cost_amount,
            COALESCE(SUM(CASE WHEN cae.cost_type = 'Payroll' THEN cae.allocated_cost_amount ELSE 0 END), 0) AS payroll_cost,
            COALESCE(SUM(CASE WHEN cae.cost_type = 'Rent' THEN cae.allocated_cost_amount ELSE 0 END), 0) AS rent_cost,
            COALESCE(SUM(CASE WHEN cae.cost_type = 'Utilities' THEN cae.allocated_cost_amount ELSE 0 END), 0) AS utilities_cost,
            COALESCE(SUM(CASE WHEN cae.cost_type = 'Food' THEN cae.allocated_cost_amount ELSE 0 END), 0) AS food_cost,
            COALESCE(SUM(CASE WHEN cae.cost_type = 'Transport' THEN cae.allocated_cost_amount ELSE 0 END), 0) AS transport_cost,
            COALESCE(SUM(CASE WHEN cae.cost_type = 'Non-Billable Support' THEN cae.allocated_cost_amount ELSE 0 END), 0) AS non_billable_support_cost,
            COALESCE(SUM(CASE WHEN cae.cost_type NOT IN ('Payroll', 'Rent', 'Utilities', 'Food', 'Transport', 'Non-Billable Support') THEN cae.allocated_cost_amount ELSE 0 END), 0) AS other_cost
        FROM `tabNDIS Cost Allocation Entry` cae
        {build_where(conditions)}
        GROUP BY COALESCE(NULLIF({group_expr}, ''), 'Unassigned')
        """,
        params,
        as_dict=True,
    )


def merge_profitability_rows(revenue_rows, cost_rows):
    revenue_map = {row.group_key: row for row in revenue_rows}
    cost_map = {row.group_key: row for row in cost_rows}
    keys = sorted(
        set(revenue_map).union(cost_map),
        key=lambda key: flt(getattr(revenue_map.get(key), "gross_claim_amount", 0)),
        reverse=True,
    )

    data = []

    for key in keys:
        rev = revenue_map.get(key) or frappe._dict()
        cost = cost_map.get(key) or frappe._dict()
        gross = flt(rev.get("gross_claim_amount"))
        paid = flt(rev.get("paid_amount"))
        shortfall = flt(rev.get("shortfall_amount"))
        allocated_cost = flt(cost.get("allocated_cost_amount"))
        margin = paid - allocated_cost

        data.append(
            frappe._dict(
                {
                    "group_key": key,
                    "claim_line_count": int(rev.get("claim_line_count") or 0),
                    "invoice_count": int(rev.get("invoice_count") or 0),
                    "cost_entry_count": int(cost.get("cost_entry_count") or 0),
                    "gross_claim_amount": gross,
                    "paid_amount": paid,
                    "shortfall_amount": shortfall,
                    "allocated_cost_amount": allocated_cost,
                    "estimated_margin_amount": margin,
                    "estimated_margin_percent": margin_percent(paid, allocated_cost),
                    "realisation_percent": realisation_percent(gross, paid),
                    "leakage_percent": leakage_percent(gross, shortfall),
                    "payroll_cost": flt(cost.get("payroll_cost")),
                    "rent_cost": flt(cost.get("rent_cost")),
                    "utilities_cost": flt(cost.get("utilities_cost")),
                    "food_cost": flt(cost.get("food_cost")),
                    "transport_cost": flt(cost.get("transport_cost")),
                    "non_billable_support_cost": flt(
                        cost.get("non_billable_support_cost")
                    ),
                    "other_cost": flt(cost.get("other_cost")),
                    "paid_count": int(rev.get("paid_count") or 0),
                    "short_paid_count": int(rev.get("short_paid_count") or 0),
                    "rejected_count": int(rev.get("rejected_count") or 0),
                    "currency": currency(),
                }
            )
        )

    return data


def profitability_columns(group_label, group_options):
    return [
        {
            "fieldname": "group_key",
            "label": _(group_label),
            "fieldtype": "Link" if group_options else "Data",
            "options": group_options,
            "width": 220,
        },
        {"fieldname": "claim_line_count", "label": _("Claim Lines"), "fieldtype": "Int", "width": 110},
        {"fieldname": "invoice_count", "label": _("Invoices"), "fieldtype": "Int", "width": 100},
        {"fieldname": "cost_entry_count", "label": _("Cost Entries"), "fieldtype": "Int", "width": 110},
        {"fieldname": "gross_claim_amount", "label": _("Gross Claims"), "fieldtype": "Currency", "options": "currency", "width": 140},
        {"fieldname": "paid_amount", "label": _("Paid Revenue"), "fieldtype": "Currency", "options": "currency", "width": 140},
        {"fieldname": "shortfall_amount", "label": _("Shortfall"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "allocated_cost_amount", "label": _("Allocated Cost"), "fieldtype": "Currency", "options": "currency", "width": 140},
        {"fieldname": "estimated_margin_amount", "label": _("Estimated Margin"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "estimated_margin_percent", "label": _("Margin %"), "fieldtype": "Percent", "width": 110},
        {"fieldname": "realisation_percent", "label": _("Realisation %"), "fieldtype": "Percent", "width": 120},
        {"fieldname": "leakage_percent", "label": _("Leakage %"), "fieldtype": "Percent", "width": 110},
        {"fieldname": "payroll_cost", "label": _("Payroll Cost"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "rent_cost", "label": _("Rent Cost"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "utilities_cost", "label": _("Utilities"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "food_cost", "label": _("Food"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "transport_cost", "label": _("Transport"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "non_billable_support_cost", "label": _("Non-Billable Support"), "fieldtype": "Currency", "options": "currency", "width": 170},
        {"fieldname": "other_cost", "label": _("Other Cost"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "paid_count", "label": _("Paid Lines"), "fieldtype": "Int", "width": 100},
        {"fieldname": "short_paid_count", "label": _("Short Paid"), "fieldtype": "Int", "width": 100},
        {"fieldname": "rejected_count", "label": _("Rejected"), "fieldtype": "Int", "width": 100},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def profitability_chart(data):
    return {
        "data": {
            "labels": [row.group_key for row in data[:20]],
            "datasets": [
                {"name": "Paid Revenue", "values": [flt(row.paid_amount) for row in data[:20]]},
                {"name": "Allocated Cost", "values": [flt(row.allocated_cost_amount) for row in data[:20]]},
                {"name": "Margin", "values": [flt(row.estimated_margin_amount) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }


def profitability_summary(data):
    gross = sum(flt(row.gross_claim_amount) for row in data)
    paid = sum(flt(row.paid_amount) for row in data)
    shortfall = sum(flt(row.shortfall_amount) for row in data)
    cost = sum(flt(row.allocated_cost_amount) for row in data)
    margin = paid - cost

    return [
        {"value": gross, "indicator": "Blue", "label": _("Gross Claims"), "datatype": "Currency", "currency": currency()},
        {"value": paid, "indicator": "Green", "label": _("Paid Revenue"), "datatype": "Currency", "currency": currency()},
        {"value": cost, "indicator": "Orange", "label": _("Allocated Cost"), "datatype": "Currency", "currency": currency()},
        {"value": margin, "indicator": "Green" if margin >= 0 else "Red", "label": _("Estimated Margin"), "datatype": "Currency", "currency": currency()},
        {"value": margin_percent(paid, cost), "indicator": "Green" if margin >= 0 else "Red", "label": _("Margin %"), "datatype": "Percent"},
        {"value": shortfall, "indicator": "Red" if shortfall else "Green", "label": _("Shortfall"), "datatype": "Currency", "currency": currency()},
    ]


def execute_true_house_profitability_report(filters=None):
    filters = frappe._dict(filters or {})
    revenue = get_revenue_by_group(filters, "house")
    cost = get_cost_by_group(filters, "house")
    data = merge_profitability_rows(revenue, cost)

    return (
        profitability_columns("House", "NDIS House"),
        data,
        None,
        profitability_chart(data),
        profitability_summary(data),
    )


def execute_true_participant_profitability_report(filters=None):
    filters = frappe._dict(filters or {})
    revenue = get_revenue_by_group(filters, "participant")
    cost = get_cost_by_group(filters, "participant")
    data = merge_profitability_rows(revenue, cost)

    return (
        profitability_columns("Participant", "Customer"),
        data,
        None,
        profitability_chart(data),
        profitability_summary(data),
    )


def execute_cost_type_analysis_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions, params = add_cost_filters(filters, "cae")
    params["currency"] = currency()

    data = frappe.db.sql(
        f"""
        SELECT
            COALESCE(NULLIF(cae.cost_type, ''), 'Unassigned') AS cost_type,
            COALESCE(NULLIF(cae.house, ''), 'Unassigned') AS house,
            COALESCE(NULLIF(cae.participant, ''), 'Unassigned') AS participant,
            cae.allocation_method,
            COUNT(*) AS cost_entry_count,
            COALESCE(SUM(cae.gross_claim_amount), 0) AS gross_claim_amount,
            COALESCE(SUM(cae.paid_amount), 0) AS paid_amount,
            COALESCE(SUM(cae.allocated_cost_amount), 0) AS allocated_cost_amount,
            COALESCE(SUM(cae.estimated_margin_amount), 0) AS estimated_margin_amount,
            CASE
                WHEN COALESCE(SUM(cae.paid_amount), 0) > 0
                THEN ROUND((COALESCE(SUM(cae.estimated_margin_amount), 0) / COALESCE(SUM(cae.paid_amount), 0)) * 100, 2)
                ELSE 0
            END AS estimated_margin_percent,
            %(currency)s AS currency
        FROM `tabNDIS Cost Allocation Entry` cae
        {build_where(conditions)}
        GROUP BY
            COALESCE(NULLIF(cae.cost_type, ''), 'Unassigned'),
            COALESCE(NULLIF(cae.house, ''), 'Unassigned'),
            COALESCE(NULLIF(cae.participant, ''), 'Unassigned'),
            cae.allocation_method
        ORDER BY allocated_cost_amount DESC
        """,
        params,
        as_dict=True,
    )

    columns = [
        {"fieldname": "cost_type", "label": _("Cost Type"), "fieldtype": "Data", "width": 160},
        {"fieldname": "house", "label": _("House"), "fieldtype": "Link", "options": "NDIS House", "width": 170},
        {"fieldname": "participant", "label": _("Participant"), "fieldtype": "Link", "options": "Customer", "width": 180},
        {"fieldname": "allocation_method", "label": _("Allocation Method"), "fieldtype": "Data", "width": 180},
        {"fieldname": "cost_entry_count", "label": _("Entries"), "fieldtype": "Int", "width": 90},
        {"fieldname": "gross_claim_amount", "label": _("Gross Claims"), "fieldtype": "Currency", "options": "currency", "width": 140},
        {"fieldname": "paid_amount", "label": _("Paid Revenue"), "fieldtype": "Currency", "options": "currency", "width": 140},
        {"fieldname": "allocated_cost_amount", "label": _("Allocated Cost"), "fieldtype": "Currency", "options": "currency", "width": 140},
        {"fieldname": "estimated_margin_amount", "label": _("Estimated Margin"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "estimated_margin_percent", "label": _("Margin %"), "fieldtype": "Percent", "width": 110},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]

    chart_map = {}
    for row in data:
        chart_map[row.cost_type] = chart_map.get(row.cost_type, 0) + flt(
            row.allocated_cost_amount
        )

    chart = {
        "data": {
            "labels": list(chart_map.keys()),
            "datasets": [{"name": "Allocated Cost", "values": list(chart_map.values())}],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Cost Rows"), "datatype": "Int"},
        {"value": sum(flt(row.allocated_cost_amount) for row in data), "indicator": "Orange", "label": _("Allocated Cost"), "datatype": "Currency", "currency": currency()},
        {"value": sum(flt(row.estimated_margin_amount) for row in data), "indicator": "Green", "label": _("Estimated Margin"), "datatype": "Currency", "currency": currency()},
    ]

    return columns, data, None, chart, summary


def execute_profitability_summary_report(filters=None):
    filters = frappe._dict(filters or {})
    house_data = merge_profitability_rows(
        get_revenue_by_group(filters, "house"),
        get_cost_by_group(filters, "house"),
    )
    participant_data = merge_profitability_rows(
        get_revenue_by_group(filters, "participant"),
        get_cost_by_group(filters, "participant"),
    )

    rows = []
    for view_type, source_rows in [
        ("House", house_data),
        ("Participant", participant_data),
    ]:
        for row in source_rows:
            rows.append(
                frappe._dict(
                    {
                        "view_type": view_type,
                        "record": row.group_key,
                        "gross_claim_amount": row.gross_claim_amount,
                        "paid_amount": row.paid_amount,
                        "shortfall_amount": row.shortfall_amount,
                        "allocated_cost_amount": row.allocated_cost_amount,
                        "estimated_margin_amount": row.estimated_margin_amount,
                        "estimated_margin_percent": row.estimated_margin_percent,
                        "leakage_percent": row.leakage_percent,
                        "currency": currency(),
                    }
                )
            )

    rows = sorted(rows, key=lambda row: flt(row.estimated_margin_amount))
    columns = [
        {"fieldname": "view_type", "label": _("View Type"), "fieldtype": "Data", "width": 120},
        {"fieldname": "record", "label": _("Record"), "fieldtype": "Data", "width": 220},
        {"fieldname": "gross_claim_amount", "label": _("Gross Claims"), "fieldtype": "Currency", "options": "currency", "width": 140},
        {"fieldname": "paid_amount", "label": _("Paid Revenue"), "fieldtype": "Currency", "options": "currency", "width": 140},
        {"fieldname": "shortfall_amount", "label": _("Shortfall"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "allocated_cost_amount", "label": _("Allocated Cost"), "fieldtype": "Currency", "options": "currency", "width": 140},
        {"fieldname": "estimated_margin_amount", "label": _("Estimated Margin"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "estimated_margin_percent", "label": _("Margin %"), "fieldtype": "Percent", "width": 110},
        {"fieldname": "leakage_percent", "label": _("Leakage %"), "fieldtype": "Percent", "width": 110},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]

    chart = {
        "data": {
            "labels": [row.record for row in rows[:20]],
            "datasets": [
                {
                    "name": "Estimated Margin",
                    "values": [flt(row.estimated_margin_amount) for row in rows[:20]],
                }
            ],
        },
        "type": "bar",
    }

    return columns, rows, None, chart, profitability_summary(house_data)


@frappe.whitelist()
def quick_true_profitability_summary():
    house_data = merge_profitability_rows(
        get_revenue_by_group({}, "house"),
        get_cost_by_group({}, "house"),
    )
    participant_data = merge_profitability_rows(
        get_revenue_by_group({}, "participant"),
        get_cost_by_group({}, "participant"),
    )
    total_paid = sum(flt(row.paid_amount) for row in house_data)
    total_cost = sum(flt(row.allocated_cost_amount) for row in house_data)
    total_margin = total_paid - total_cost

    return {
        "today": today(),
        "total_paid_revenue": total_paid,
        "total_allocated_cost": total_cost,
        "total_estimated_margin": total_margin,
        "estimated_margin_percent": margin_percent(total_paid, total_cost),
        "worst_houses_by_margin": sorted(
            house_data, key=lambda row: flt(row.estimated_margin_amount)
        )[:10],
        "worst_participants_by_margin": sorted(
            participant_data, key=lambda row: flt(row.estimated_margin_amount)
        )[:10],
        "note": "Profitability summary uses management cost allocation only. No GL, Journal Entry, Payment Entry, payroll posting, or accounting movement created.",
    }
