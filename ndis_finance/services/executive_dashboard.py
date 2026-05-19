import frappe
from frappe import _
from frappe.utils import add_days, flt, nowdate, today


OPEN_RECOVERY_STATUSES = ("Open", "In Follow Up", "Waiting For Response", "Escalated")
OPEN_LEAKAGE_STATUSES = ("Open", "In Review")


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


def has_field(doctype, fieldname):
    return frappe.get_meta(doctype).has_field(fieldname)


def claim_conditions(filters, alias="cl"):
    conditions = []
    params = {}
    prefix = f"{alias}." if alias else ""

    for key, fieldname in {
        "house": "house",
        "participant": "participant",
        "funding_source": "funding_source",
    }.items():
        value = get_filter(filters, key)
        if value:
            conditions.append(f"{prefix}{fieldname} = %({key})s")
            params[key] = value

    from_date = get_filter(filters, "from_date")
    to_date = get_filter(filters, "to_date")
    if from_date:
        conditions.append(f"{prefix}service_date >= %(from_date)s")
        params["from_date"] = from_date
    if to_date:
        conditions.append(f"{prefix}service_date <= %(to_date)s")
        params["to_date"] = to_date

    return conditions, params


def cost_conditions(filters, alias="cae"):
    conditions = [f"{alias}.status = 'Active'"]
    params = {}

    for key in ["house", "participant", "cost_type"]:
        value = get_filter(filters, key)
        if value:
            conditions.append(f"{alias}.{key} = %({key})s")
            params[key] = value

    from_date = get_filter(filters, "from_date")
    to_date = get_filter(filters, "to_date")
    if from_date:
        conditions.append(f"{alias}.period_end >= %(from_date)s")
        params["from_date"] = from_date
    if to_date:
        conditions.append(f"{alias}.period_start <= %(to_date)s")
        params["to_date"] = to_date

    return conditions, params


def leakage_conditions(filters, alias="fl"):
    conditions = []
    params = {}

    for key in ["house", "participant"]:
        value = get_filter(filters, key)
        if value:
            conditions.append(f"{alias}.{key} = %({key})s")
            params[key] = value

    from_date = get_filter(filters, "from_date")
    to_date = get_filter(filters, "to_date")
    if from_date:
        conditions.append(f"{alias}.service_date >= %(from_date)s")
        params["from_date"] = from_date
    if to_date:
        conditions.append(f"{alias}.service_date <= %(to_date)s")
        params["to_date"] = to_date

    return conditions, params


def margin_percent(revenue, cost):
    revenue = flt(revenue)
    if revenue <= 0:
        return 0
    return round(((revenue - flt(cost)) / revenue) * 100, 2)


def percent(numerator, denominator):
    denominator = flt(denominator)
    if denominator <= 0:
        return 0
    return round((flt(numerator) / denominator) * 100, 2)


def get_claim_summary(filters):
    conditions, params = claim_conditions(filters, "cl")
    return frappe.db.sql(
        f"""
        SELECT
            COUNT(*) AS claim_line_count,
            COUNT(DISTINCT cl.sales_invoice) AS invoice_count,
            COALESCE(SUM(cl.claim_amount), 0) AS gross_claim_amount,
            COALESCE(SUM(cl.paid_amount), 0) AS paid_amount,
            COALESCE(SUM(cl.shortfall_amount), 0) AS shortfall_amount,
            COALESCE(SUM(CASE WHEN cl.claim_status = 'Paid' THEN 1 ELSE 0 END), 0) AS paid_count,
            COALESCE(SUM(CASE WHEN cl.claim_status = 'Short Paid' THEN 1 ELSE 0 END), 0) AS short_paid_count,
            COALESCE(SUM(CASE WHEN cl.claim_status = 'Rejected' THEN 1 ELSE 0 END), 0) AS rejected_count,
            COALESCE(SUM(CASE WHEN cl.claim_status IN ('Ready to Claim', 'Submitted') THEN cl.claim_amount ELSE 0 END), 0) AS claim_pipeline_amount
        FROM `tabNDIS Claim Line` cl
        {build_where(conditions)}
        """,
        params,
        as_dict=True,
    )[0]


def get_cost_summary(filters):
    conditions, params = cost_conditions(filters, "cae")
    return frappe.db.sql(
        f"""
        SELECT
            COUNT(*) AS cost_entry_count,
            COALESCE(SUM(cae.allocated_cost_amount), 0) AS total_allocated_cost,
            COALESCE(SUM(CASE WHEN cae.cost_type = 'Payroll' THEN cae.allocated_cost_amount ELSE 0 END), 0) AS payroll_cost,
            COALESCE(SUM(CASE WHEN cae.cost_type != 'Payroll' THEN cae.allocated_cost_amount ELSE 0 END), 0) AS non_payroll_cost,
            COALESCE(SUM(CASE WHEN cae.cost_type = 'Rent' THEN cae.allocated_cost_amount ELSE 0 END), 0) AS rent_cost,
            COALESCE(SUM(CASE WHEN cae.cost_type = 'Utilities' THEN cae.allocated_cost_amount ELSE 0 END), 0) AS utilities_cost,
            COALESCE(SUM(CASE WHEN cae.cost_type = 'Transport' THEN cae.allocated_cost_amount ELSE 0 END), 0) AS transport_cost,
            COALESCE(SUM(CASE WHEN cae.cost_type = 'Non-Billable Support' THEN cae.allocated_cost_amount ELSE 0 END), 0) AS non_billable_support_cost
        FROM `tabNDIS Cost Allocation Entry` cae
        {build_where(conditions)}
        """,
        params,
        as_dict=True,
    )[0]


def get_leakage_summary(filters):
    conditions, params = leakage_conditions(filters, "fl")
    return frappe.db.sql(
        f"""
        SELECT
            COUNT(*) AS leakage_count,
            COALESCE(SUM(fl.variance_amount), 0) AS total_leakage_amount,
            COALESCE(SUM(CASE WHEN fl.status IN %(open_statuses)s THEN fl.variance_amount ELSE 0 END), 0) AS open_leakage_amount,
            COALESCE(SUM(CASE WHEN fl.status = 'Resolved' THEN fl.variance_amount ELSE 0 END), 0) AS resolved_leakage_amount,
            COALESCE(SUM(CASE WHEN fl.status = 'Written Off' THEN fl.variance_amount ELSE 0 END), 0) AS written_off_leakage_amount,
            COALESCE(SUM(CASE WHEN fl.severity = 'Critical' THEN 1 ELSE 0 END), 0) AS critical_leakage_count,
            COALESCE(SUM(CASE WHEN fl.severity = 'High' THEN 1 ELSE 0 END), 0) AS high_leakage_count
        FROM `tabNDIS Funding Leakage Register` fl
        {build_where(conditions)}
        """,
        dict(params, open_statuses=OPEN_LEAKAGE_STATUSES),
        as_dict=True,
    )[0]


def get_recovery_summary():
    return frappe.db.sql(
        """
        SELECT
            COUNT(*) AS recovery_case_count,
            COALESCE(SUM(outstanding_amount), 0) AS total_outstanding_recovery,
            COALESCE(SUM(CASE WHEN status IN %(open_statuses)s THEN outstanding_amount ELSE 0 END), 0) AS open_recovery_amount,
            COALESCE(SUM(CASE WHEN status = 'Resolved' THEN recovered_amount ELSE 0 END), 0) AS recovered_amount,
            COALESCE(SUM(CASE WHEN status = 'Written Off' THEN written_off_amount ELSE 0 END), 0) AS written_off_amount,
            COALESCE(SUM(CASE WHEN status IN %(open_statuses)s AND next_follow_up_date < CURDATE() THEN 1 ELSE 0 END), 0) AS overdue_recovery_cases,
            COALESCE(SUM(CASE WHEN status = 'Escalated' THEN 1 ELSE 0 END), 0) AS escalated_recovery_cases
        FROM `tabNDIS Recovery Case`
        """,
        {"open_statuses": OPEN_RECOVERY_STATUSES},
        as_dict=True,
    )[0]


def get_payroll_import_summary():
    return frappe.db.sql(
        """
        SELECT
            COUNT(*) AS payroll_import_count,
            COALESCE(SUM(total_import_cost_amount), 0) AS total_imported_payroll_cost,
            COALESCE(SUM(unmapped_line_count), 0) AS unmapped_payroll_lines,
            COALESCE(SUM(cost_pool_count), 0) AS payroll_cost_pool_count,
            COALESCE(SUM(allocated_cost_pool_count), 0) AS allocated_payroll_cost_pool_count
        FROM `tabNDIS Payroll Cost Import`
        WHERE status != 'Cancelled'
        """,
        as_dict=True,
    )[0]


def get_automation_summary():
    if not frappe.db.exists("DocType", "NDIS Recovery Automation Log"):
        return frappe._dict()

    cutoff = add_days(nowdate(), -7)
    date_field = "started_on" if has_field("NDIS Recovery Automation Log", "started_on") else "creation"
    fields = frappe.get_meta("NDIS Recovery Automation Log").fields
    fieldnames = {field.fieldname for field in fields}

    def sum_field(fieldname):
        if fieldname in fieldnames:
            return f"COALESCE(SUM({fieldname}), 0)"
        return "0"

    return frappe.db.sql(
        f"""
        SELECT
            COUNT(*) AS automation_runs_7_days,
            COALESCE(SUM(CASE WHEN status = 'Failed' THEN 1 ELSE 0 END), 0) AS failed_runs_7_days,
            COALESCE(SUM(CASE WHEN status = 'Completed With Exceptions' THEN 1 ELSE 0 END), 0) AS exception_runs_7_days,
            {sum_field("approved_drafts_not_sent")} AS approved_drafts_not_sent,
            {sum_field("escalation_candidates")} AS escalation_candidates,
            {sum_field("overdue_recovery_cases")} AS overdue_recovery_cases
        FROM `tabNDIS Recovery Automation Log`
        WHERE DATE({date_field}) >= %(cutoff)s
        """,
        {"cutoff": cutoff},
        as_dict=True,
    )[0]


def get_worst_houses(filters, limit=5):
    claim_rows = get_paid_by_group(filters, "house", "cl")
    cost_rows = get_cost_by_group(filters, "house", "cae")
    return merge_margin_rows(claim_rows, cost_rows, "house", limit)


def get_worst_participants(filters, limit=5):
    claim_rows = get_paid_by_group(filters, "participant", "cl")
    cost_rows = get_cost_by_group(filters, "participant", "cae")
    return merge_margin_rows(claim_rows, cost_rows, "participant", limit)


def get_paid_by_group(filters, group_field, alias):
    conditions, params = claim_conditions(filters, alias)
    return frappe.db.sql(
        f"""
        SELECT
            COALESCE(NULLIF({alias}.{group_field}, ''), 'Unassigned') AS group_key,
            COALESCE(SUM({alias}.paid_amount), 0) AS paid_amount
        FROM `tabNDIS Claim Line` {alias}
        {build_where(conditions)}
        GROUP BY COALESCE(NULLIF({alias}.{group_field}, ''), 'Unassigned')
        """,
        params,
        as_dict=True,
    )


def get_cost_by_group(filters, group_field, alias):
    conditions, params = cost_conditions(filters, alias)
    return frappe.db.sql(
        f"""
        SELECT
            COALESCE(NULLIF({alias}.{group_field}, ''), 'Unassigned') AS group_key,
            COALESCE(SUM({alias}.allocated_cost_amount), 0) AS allocated_cost
        FROM `tabNDIS Cost Allocation Entry` {alias}
        {build_where(conditions)}
        GROUP BY COALESCE(NULLIF({alias}.{group_field}, ''), 'Unassigned')
        """,
        params,
        as_dict=True,
    )


def merge_margin_rows(claim_rows, cost_rows, key_field, limit):
    claim_map = {row.group_key: row for row in claim_rows}
    cost_map = {row.group_key: row for row in cost_rows}
    rows = []

    for key in set(claim_map).union(set(cost_map)):
        paid = flt((claim_map.get(key) or {}).get("paid_amount"))
        cost = flt((cost_map.get(key) or {}).get("allocated_cost"))
        rows.append(
            frappe._dict(
                {
                    key_field: key,
                    "paid_amount": paid,
                    "allocated_cost": cost,
                    "margin": paid - cost,
                    "margin_percent": margin_percent(paid, cost),
                }
            )
        )

    return sorted(rows, key=lambda row: flt(row.margin))[:limit]


@frappe.whitelist()
def quick_executive_dashboard_summary(filters=None):
    filters = frappe._dict(filters or {})

    claims = get_claim_summary(filters)
    costs = get_cost_summary(filters)
    leakage = get_leakage_summary(filters)
    recovery = get_recovery_summary()
    payroll = get_payroll_import_summary()
    automation = get_automation_summary()

    paid = flt(claims.paid_amount)
    total_cost = flt(costs.total_allocated_cost)
    payroll_cost = flt(costs.payroll_cost)
    margin = paid - total_cost

    return {
        "today": today(),
        "claims": claims,
        "costs": costs,
        "leakage": leakage,
        "recovery": recovery,
        "payroll": payroll,
        "automation": automation,
        "kpis": {
            "paid_revenue": paid,
            "total_allocated_cost": total_cost,
            "payroll_cost": payroll_cost,
            "non_payroll_cost": flt(costs.non_payroll_cost),
            "estimated_margin": margin,
            "estimated_margin_percent": margin_percent(paid, total_cost),
            "payroll_cost_ratio": percent(payroll_cost, paid),
            "shortfall_ratio": percent(flt(claims.shortfall_amount), flt(claims.gross_claim_amount)),
            "open_leakage": flt(leakage.open_leakage_amount),
            "open_recovery": flt(recovery.open_recovery_amount),
        },
        "worst_houses": get_worst_houses(filters),
        "worst_participants": get_worst_participants(filters),
        "note": "Executive dashboard only. No Payment Entry, Journal Entry, GL Entry, payroll posting, STP, ABA, email sending, or accounting movement created.",
    }


def add_row(rows, section, metric, amount=0, count=None, percent_value=None, status="Info", note=""):
    rows.append(
        frappe._dict(
            {
                "section": section,
                "metric": metric,
                "amount": flt(amount),
                "count": count,
                "percent_value": percent_value,
                "status": status,
                "note": note,
                "currency": currency(),
            }
        )
    )


def execute_executive_dashboard_report(filters=None):
    filters = frappe._dict(filters or {})
    summary = quick_executive_dashboard_summary(filters)

    claims = frappe._dict(summary.get("claims"))
    costs = frappe._dict(summary.get("costs"))
    leakage = frappe._dict(summary.get("leakage"))
    recovery = frappe._dict(summary.get("recovery"))
    payroll = frappe._dict(summary.get("payroll"))
    automation = frappe._dict(summary.get("automation"))
    kpis = frappe._dict(summary.get("kpis"))

    rows = []

    add_row(rows, "Revenue", "Gross Claims", claims.gross_claim_amount, claims.claim_line_count, None, "Info", "Total claim value from NDIS Claim Lines.")
    add_row(rows, "Revenue", "Paid Revenue", claims.paid_amount, claims.paid_count, None, "Good", "Paid amount recorded on claim lines.")
    add_row(rows, "Revenue", "Shortfall", claims.shortfall_amount, claims.short_paid_count, kpis.shortfall_ratio, "Risk" if flt(claims.shortfall_amount) else "Good", "Short-paid/rejected claim gap.")
    add_row(rows, "Revenue", "Claim Pipeline", claims.claim_pipeline_amount, None, None, "Info", "Ready/submitted claim amount still in pipeline.")

    add_row(rows, "Cost", "Total Allocated Cost", costs.total_allocated_cost, costs.cost_entry_count, None, "Info", "All active management cost allocations.")
    add_row(rows, "Cost", "Payroll Cost", costs.payroll_cost, None, kpis.payroll_cost_ratio, "Info", "Payroll cost allocated through AU Payroll bridge.")
    add_row(rows, "Cost", "Non-Payroll Cost", costs.non_payroll_cost, None, None, "Info", "Rent, utilities, transport, non-billable support and other costs.")
    add_row(rows, "Cost", "Rent Cost", costs.rent_cost, None, None, "Info", "Active rent cost allocations.")
    add_row(rows, "Cost", "Utilities Cost", costs.utilities_cost, None, None, "Info", "Active utilities cost allocations.")
    add_row(rows, "Cost", "Transport Cost", costs.transport_cost, None, None, "Info", "Active transport cost allocations.")
    add_row(rows, "Cost", "Non-Billable Support Cost", costs.non_billable_support_cost, None, None, "Risk" if flt(costs.non_billable_support_cost) else "Good", "Non-billable support allocation.")

    add_row(rows, "Margin", "Estimated Margin", kpis.estimated_margin, None, kpis.estimated_margin_percent, "Good" if flt(kpis.estimated_margin) >= 0 else "Risk", "Paid revenue less allocated costs.")
    add_row(rows, "Margin", "Margin %", 0, None, kpis.estimated_margin_percent, "Good" if flt(kpis.estimated_margin_percent) >= 0 else "Risk", "Estimated margin percentage after allocated costs.")

    add_row(rows, "Leakage", "Open Leakage", leakage.open_leakage_amount, leakage.leakage_count, None, "Risk" if flt(leakage.open_leakage_amount) else "Good", "Open/In Review funding leakage.")
    add_row(rows, "Leakage", "Critical Leakage Count", 0, leakage.critical_leakage_count, None, "Risk" if int(leakage.critical_leakage_count or 0) else "Good", "Critical leakage records.")
    add_row(rows, "Leakage", "High Leakage Count", 0, leakage.high_leakage_count, None, "Risk" if int(leakage.high_leakage_count or 0) else "Good", "High leakage records.")

    add_row(rows, "Recovery", "Open Recovery", recovery.open_recovery_amount, recovery.recovery_case_count, None, "Risk" if flt(recovery.open_recovery_amount) else "Good", "Open recovery pipeline.")
    add_row(rows, "Recovery", "Recovered Amount", recovery.recovered_amount, None, None, "Good", "Resolved recovered amount.")
    add_row(rows, "Recovery", "Overdue Recovery Cases", 0, recovery.overdue_recovery_cases, None, "Risk" if int(recovery.overdue_recovery_cases or 0) else "Good", "Recovery cases overdue for follow-up.")
    add_row(rows, "Recovery", "Escalated Recovery Cases", 0, recovery.escalated_recovery_cases, None, "Risk" if int(recovery.escalated_recovery_cases or 0) else "Good", "Escalated recovery cases.")

    add_row(rows, "Payroll", "Imported Payroll Cost", payroll.total_imported_payroll_cost, payroll.payroll_import_count, None, "Info", "Total payroll cost imported into NDIS management costing.")
    add_row(rows, "Payroll", "Unmapped Payroll Lines", 0, payroll.unmapped_payroll_lines, None, "Risk" if int(payroll.unmapped_payroll_lines or 0) else "Good", "Payroll rows without NDIS mapping.")
    add_row(rows, "Payroll", "Payroll Cost Pools", 0, payroll.payroll_cost_pool_count, None, "Info", "Payroll cost pools created from AU Payroll.")
    add_row(rows, "Payroll", "Allocated Payroll Cost Pools", 0, payroll.allocated_payroll_cost_pool_count, None, "Good", "Payroll cost pools allocated to participants/houses.")

    add_row(rows, "Automation", "Automation Runs Last 7 Days", 0, automation.automation_runs_7_days, None, "Info", "Recent recovery scheduler runs.")
    add_row(rows, "Automation", "Failed Automation Runs Last 7 Days", 0, automation.failed_runs_7_days, None, "Risk" if int(automation.failed_runs_7_days or 0) else "Good", "Failed scheduler runs.")
    add_row(rows, "Automation", "Approved Drafts Not Sent", 0, automation.approved_drafts_not_sent, None, "Risk" if int(automation.approved_drafts_not_sent or 0) else "Good", "Approved recovery drafts not marked sent.")
    add_row(rows, "Automation", "Escalation Candidates", 0, automation.escalation_candidates, None, "Risk" if int(automation.escalation_candidates or 0) else "Good", "Cases identified for escalation.")

    for item in summary.get("worst_houses", []):
        add_row(
            rows,
            "Worst Houses",
            item.house,
            item.margin,
            None,
            item.margin_percent,
            "Risk" if flt(item.margin) < 0 else "Watch",
            f"Paid revenue {flt(item.paid_amount):.2f}; allocated cost {flt(item.allocated_cost):.2f}.",
        )

    for item in summary.get("worst_participants", []):
        add_row(
            rows,
            "Worst Participants",
            item.participant,
            item.margin,
            None,
            item.margin_percent,
            "Risk" if flt(item.margin) < 0 else "Watch",
            f"Paid revenue {flt(item.paid_amount):.2f}; allocated cost {flt(item.allocated_cost):.2f}.",
        )

    columns = [
        {"fieldname": "section", "label": _("Section"), "fieldtype": "Data", "width": 160},
        {"fieldname": "metric", "label": _("Metric"), "fieldtype": "Data", "width": 260},
        {"fieldname": "amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "count", "label": _("Count"), "fieldtype": "Int", "width": 100},
        {"fieldname": "percent_value", "label": _("Percent"), "fieldtype": "Percent", "width": 110},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "note", "label": _("Note"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]

    chart = {
        "data": {
            "labels": [
                "Paid Revenue",
                "Total Cost",
                "Payroll Cost",
                "Non-Payroll Cost",
                "Margin",
                "Shortfall",
                "Open Leakage",
                "Open Recovery",
            ],
            "datasets": [
                {
                    "name": "Executive Amounts",
                    "values": [
                        flt(kpis.paid_revenue),
                        flt(kpis.total_allocated_cost),
                        flt(kpis.payroll_cost),
                        flt(kpis.non_payroll_cost),
                        flt(kpis.estimated_margin),
                        flt(claims.shortfall_amount),
                        flt(kpis.open_leakage),
                        flt(kpis.open_recovery),
                    ],
                }
            ],
        },
        "type": "bar",
    }

    report_summary = [
        {"value": flt(kpis.paid_revenue), "indicator": "Green", "label": _("Paid Revenue"), "datatype": "Currency", "currency": currency()},
        {"value": flt(kpis.total_allocated_cost), "indicator": "Orange", "label": _("Allocated Cost"), "datatype": "Currency", "currency": currency()},
        {"value": flt(kpis.estimated_margin), "indicator": "Green" if flt(kpis.estimated_margin) >= 0 else "Red", "label": _("Estimated Margin"), "datatype": "Currency", "currency": currency()},
        {"value": flt(kpis.estimated_margin_percent), "indicator": "Green" if flt(kpis.estimated_margin_percent) >= 0 else "Red", "label": _("Margin %"), "datatype": "Percent"},
        {"value": int(automation.failed_runs_7_days or 0), "indicator": "Red" if int(automation.failed_runs_7_days or 0) else "Green", "label": _("Failed Automation Runs"), "datatype": "Int"},
        {"value": int(payroll.unmapped_payroll_lines or 0), "indicator": "Red" if int(payroll.unmapped_payroll_lines or 0) else "Green", "label": _("Unmapped Payroll Lines"), "datatype": "Int"},
    ]

    return columns, rows, None, chart, report_summary
