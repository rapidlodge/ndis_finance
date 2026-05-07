import frappe
from frappe import _
from frappe.utils import flt, today

from ndis_finance.services.recovery_scheduler import build_recovery_monitor_summary


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


def execute_automation_health_report(filters=None):
    filters = frappe._dict(filters or {})

    columns = [
        {
            "fieldname": "automation_log",
            "label": _("Automation Log"),
            "fieldtype": "Link",
            "options": "NDIS Recovery Automation Log",
            "width": 220,
        },
        {"fieldname": "run_id", "label": _("Run ID"), "fieldtype": "Data", "width": 260},
        {"fieldname": "run_type", "label": _("Run Type"), "fieldtype": "Data", "width": 110},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 170},
        {
            "fieldname": "started_on",
            "label": _("Started On"),
            "fieldtype": "Datetime",
            "width": 170,
        },
        {
            "fieldname": "completed_on",
            "label": _("Completed On"),
            "fieldtype": "Datetime",
            "width": 170,
        },
        {"fieldname": "due_recovery_cases", "label": _("Due Cases"), "fieldtype": "Int", "width": 100},
        {
            "fieldname": "overdue_recovery_cases",
            "label": _("Overdue Cases"),
            "fieldtype": "Int",
            "width": 120,
        },
        {
            "fieldname": "open_leakage_without_case",
            "label": _("Leakage Without Case"),
            "fieldtype": "Int",
            "width": 150,
        },
        {
            "fieldname": "claim_exceptions_without_case",
            "label": _("Claim Exceptions Without Case"),
            "fieldtype": "Int",
            "width": 190,
        },
        {
            "fieldname": "approved_drafts_not_sent",
            "label": _("Approved Drafts Not Sent"),
            "fieldtype": "Int",
            "width": 180,
        },
        {
            "fieldname": "escalation_candidates",
            "label": _("Escalation Candidates"),
            "fieldtype": "Int",
            "width": 160,
        },
        {
            "fieldname": "created_recovery_cases",
            "label": _("Created Cases"),
            "fieldtype": "Int",
            "width": 120,
        },
        {
            "fieldname": "total_issues_found",
            "label": _("Total Issues"),
            "fieldtype": "Int",
            "width": 120,
        },
    ]

    conditions = []
    params = {}

    from_date = get_filter(filters, "from_date")
    to_date = get_filter(filters, "to_date")
    run_type = get_filter(filters, "run_type")
    status = get_filter(filters, "status")

    if from_date:
        conditions.append("DATE(started_on) >= %(from_date)s")
        params["from_date"] = from_date

    if to_date:
        conditions.append("DATE(started_on) <= %(to_date)s")
        params["to_date"] = to_date

    if run_type:
        conditions.append("run_type = %(run_type)s")
        params["run_type"] = run_type

    if status:
        conditions.append("status = %(status)s")
        params["status"] = status

    data = frappe.db.sql(
        f"""
        SELECT
            name AS automation_log,
            run_id,
            run_type,
            status,
            started_on,
            completed_on,
            due_recovery_cases,
            overdue_recovery_cases,
            open_leakage_without_case,
            claim_exceptions_without_case,
            approved_drafts_not_sent,
            escalation_candidates,
            created_recovery_cases,
            total_issues_found
        FROM `tabNDIS Recovery Automation Log`
        {build_where(conditions)}
        ORDER BY started_on DESC
        LIMIT 200
        """,
        params,
        as_dict=True,
    )

    chart_map = {}
    for row in data:
        label = row.status or "Unknown"
        chart_map[label] = chart_map.get(label, 0) + 1

    chart = {
        "data": {
            "labels": list(chart_map.keys()),
            "datasets": [{"name": "Runs", "values": list(chart_map.values())}],
        },
        "type": "bar",
    }

    failed_runs = len([row for row in data if row.status == "Failed"])
    exception_runs = len([row for row in data if row.status == "Completed With Exceptions"])
    scheduled_runs = len([row for row in data if row.run_type == "Scheduled"])

    summary = [
        {
            "value": len(data),
            "indicator": "Blue",
            "label": _("Automation Runs"),
            "datatype": "Int",
        },
        {
            "value": scheduled_runs,
            "indicator": "Blue",
            "label": _("Scheduled Runs"),
            "datatype": "Int",
        },
        {
            "value": exception_runs,
            "indicator": "Orange" if exception_runs else "Green",
            "label": _("Runs With Exceptions"),
            "datatype": "Int",
        },
        {
            "value": failed_runs,
            "indicator": "Red" if failed_runs else "Green",
            "label": _("Failed Runs"),
            "datatype": "Int",
        },
        {
            "value": sum(int(row.total_issues_found or 0) for row in data),
            "indicator": "Orange",
            "label": _("Issues Found"),
            "datatype": "Int",
        },
    ]

    return columns, data, None, chart, summary


def execute_automation_exception_report(filters=None):
    filters = frappe._dict(filters or {})

    exception_type = get_filter(filters, "exception_type")
    preview_limit = int(get_filter(filters, "preview_limit", 100) or 100)

    summary = build_recovery_monitor_summary(
        escalation_overdue_days=int(get_filter(filters, "escalation_overdue_days", 3) or 3),
        preview_limit=preview_limit,
    )

    columns = [
        {
            "fieldname": "exception_type",
            "label": _("Exception Type"),
            "fieldtype": "Data",
            "width": 210,
        },
        {
            "fieldname": "source_doctype",
            "label": _("Source DocType"),
            "fieldtype": "Data",
            "width": 190,
        },
        {
            "fieldname": "record",
            "label": _("Record"),
            "fieldtype": "Dynamic Link",
            "options": "source_doctype",
            "width": 220,
        },
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 150},
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
            "fieldname": "amount",
            "label": _("Amount / Variance"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 140,
        },
        {
            "fieldname": "due_date",
            "label": _("Due / Follow Up Date"),
            "fieldtype": "Date",
            "width": 150,
        },
        {
            "fieldname": "assigned_to",
            "label": _("Assigned To"),
            "fieldtype": "Link",
            "options": "User",
            "width": 160,
        },
        {"fieldname": "note", "label": _("Note"), "fieldtype": "Small Text", "width": 280},
        {
            "fieldname": "currency",
            "label": _("Currency"),
            "fieldtype": "Link",
            "options": "Currency",
            "hidden": 1,
        },
    ]

    data = []
    previews = summary.get("previews", {})

    def allowed(label):
        return not exception_type or exception_type == label

    if allowed("Due Recovery Cases"):
        for row in previews.get("due_recovery_cases", []):
            data.append(
                {
                    "exception_type": "Due Recovery Cases",
                    "source_doctype": "NDIS Recovery Case",
                    "record": row.name,
                    "status": row.status,
                    "priority": row.priority,
                    "participant": row.participant,
                    "sales_invoice": row.sales_invoice,
                    "claim_line": None,
                    "amount": flt(row.outstanding_amount),
                    "due_date": row.next_follow_up_date,
                    "assigned_to": row.assigned_to,
                    "note": "Recovery case is due today.",
                    "currency": currency(),
                }
            )

    if allowed("Overdue Recovery Cases"):
        for row in previews.get("overdue_recovery_cases", []):
            data.append(
                {
                    "exception_type": "Overdue Recovery Cases",
                    "source_doctype": "NDIS Recovery Case",
                    "record": row.name,
                    "status": row.status,
                    "priority": row.priority,
                    "participant": row.participant,
                    "sales_invoice": row.sales_invoice,
                    "claim_line": None,
                    "amount": flt(row.outstanding_amount),
                    "due_date": row.next_follow_up_date,
                    "assigned_to": row.assigned_to,
                    "note": "Recovery case is overdue.",
                    "currency": currency(),
                }
            )

    if allowed("Open Leakage Without Case"):
        for row in previews.get("open_leakage_without_case", []):
            data.append(
                {
                    "exception_type": "Open Leakage Without Case",
                    "source_doctype": "NDIS Funding Leakage Register",
                    "record": row.name,
                    "status": row.status,
                    "priority": row.severity,
                    "participant": row.participant,
                    "sales_invoice": row.sales_invoice,
                    "claim_line": row.claim_line,
                    "amount": flt(row.variance_amount),
                    "due_date": row.service_date,
                    "assigned_to": None,
                    "note": f"{row.leakage_type or 'Leakage'} has no recovery case.",
                    "currency": currency(),
                }
            )

    if allowed("Claim Exceptions Without Case"):
        for row in previews.get("claim_exceptions_without_case", []):
            data.append(
                {
                    "exception_type": "Claim Exceptions Without Case",
                    "source_doctype": "NDIS Claim Line",
                    "record": row.name,
                    "status": row.claim_status,
                    "priority": None,
                    "participant": row.participant,
                    "sales_invoice": row.sales_invoice,
                    "claim_line": row.name,
                    "amount": flt(row.shortfall_amount),
                    "due_date": row.service_date,
                    "assigned_to": None,
                    "note": "Claim exception has no recovery case.",
                    "currency": currency(),
                }
            )

    if allowed("Approved Drafts Not Sent"):
        for row in previews.get("approved_drafts_not_sent", []):
            data.append(
                {
                    "exception_type": "Approved Drafts Not Sent",
                    "source_doctype": "NDIS Recovery Email Draft",
                    "record": row.name,
                    "status": "Approved",
                    "priority": None,
                    "participant": row.participant,
                    "sales_invoice": row.sales_invoice,
                    "claim_line": None,
                    "amount": 0,
                    "due_date": row.approved_on,
                    "assigned_to": row.approved_by,
                    "note": f"Approved draft not marked sent: {row.subject or row.draft_id}",
                    "currency": currency(),
                }
            )

    if allowed("Escalation Candidates"):
        for row in previews.get("escalation_candidates", []):
            data.append(
                {
                    "exception_type": "Escalation Candidates",
                    "source_doctype": "NDIS Recovery Case",
                    "record": row.name,
                    "status": row.status,
                    "priority": row.priority,
                    "participant": row.participant,
                    "sales_invoice": row.sales_invoice,
                    "claim_line": None,
                    "amount": flt(row.outstanding_amount),
                    "due_date": row.next_follow_up_date,
                    "assigned_to": row.assigned_to,
                    "note": "Recovery case is old enough for escalation review.",
                    "currency": currency(),
                }
            )

    chart_map = {}
    for row in data:
        chart_map[row["exception_type"]] = chart_map.get(row["exception_type"], 0) + 1

    chart = {
        "data": {
            "labels": list(chart_map.keys()),
            "datasets": [{"name": "Exceptions", "values": list(chart_map.values())}],
        },
        "type": "bar",
    }

    counts = summary.get("counts", {})

    report_summary = [
        {
            "value": int(counts.get("due_recovery_cases") or 0),
            "indicator": "Orange",
            "label": _("Due Recovery Cases"),
            "datatype": "Int",
        },
        {
            "value": int(counts.get("overdue_recovery_cases") or 0),
            "indicator": "Red" if int(counts.get("overdue_recovery_cases") or 0) else "Green",
            "label": _("Overdue Recovery Cases"),
            "datatype": "Int",
        },
        {
            "value": int(counts.get("approved_drafts_not_sent") or 0),
            "indicator": "Orange" if int(counts.get("approved_drafts_not_sent") or 0) else "Green",
            "label": _("Approved Drafts Not Sent"),
            "datatype": "Int",
        },
        {
            "value": int(counts.get("escalation_candidates") or 0),
            "indicator": "Red" if int(counts.get("escalation_candidates") or 0) else "Green",
            "label": _("Escalation Candidates"),
            "datatype": "Int",
        },
    ]

    return columns, data, None, chart, report_summary


@frappe.whitelist()
def quick_automation_dashboard_summary():
    summary = build_recovery_monitor_summary(escalation_overdue_days=3, preview_limit=10)

    latest_runs = frappe.get_all(
        "NDIS Recovery Automation Log",
        fields=[
            "name",
            "run_id",
            "run_type",
            "status",
            "started_on",
            "completed_on",
            "total_issues_found",
            "created_recovery_cases",
        ],
        order_by="started_on desc",
        limit=10,
    )

    failed_runs = frappe.get_all(
        "NDIS Recovery Automation Log",
        filters={"status": "Failed"},
        fields=["name", "run_id", "run_type", "started_on", "completed_on"],
        order_by="started_on desc",
        limit=10,
    )

    return {
        "today": today(),
        "current_exception_summary": summary.get("counts", {}),
        "latest_runs": latest_runs,
        "failed_runs": failed_runs,
        "note": "Dashboard summary only. No emails sent and no accounting movement created.",
    }
