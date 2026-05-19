import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.executive_dashboard import (
    execute_executive_dashboard_report,
    quick_executive_dashboard_summary,
)
from ndis_finance.services.permissions import assert_action


TREND_COLUMNS = [
    "paid_revenue",
    "total_allocated_cost",
    "payroll_cost",
    "non_payroll_cost",
    "estimated_margin",
]


def currency():
    return frappe.defaults.get_global_default("currency") or "AUD"


def make_snapshot_id(snapshot_type="Manual", snapshot_date=None):
    snapshot_date = snapshot_date or today()
    prefix = "NDIS-EXEC-DAILY" if snapshot_type == "Scheduled" else "NDIS-EXEC-SNAPSHOT"
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{snapshot_date}-{timestamp}-{frappe.generate_hash(length=5).upper()}"


def parse_filters(filters_json=None, filters=None):
    if filters:
        return frappe._dict(filters)

    if not filters_json:
        return frappe._dict()

    if isinstance(filters_json, dict):
        return frappe._dict(filters_json)

    try:
        parsed = json.loads(filters_json)
    except Exception:
        frappe.throw(_("Invalid filters_json. Must be a valid JSON object."))

    if not isinstance(parsed, dict):
        frappe.throw(_("Invalid filters_json. Must be a valid JSON object."))

    return frappe._dict(parsed)


def filters_key(filters):
    return json.dumps(filters or {}, sort_keys=True, default=str)


def as_serialisable(value):
    return json.dumps(value, default=str)


def get_section(summary, section):
    return frappe._dict(summary.get(section) or {})


def get_kpi(summary, key, default=0):
    return flt(get_section(summary, "kpis").get(key, default))


def get_claim(summary, key, default=0):
    return flt(get_section(summary, "claims").get(key, default))


def get_payroll(summary, key, default=0):
    return get_section(summary, "payroll").get(key, default)


def get_automation(summary, key, default=0):
    return get_section(summary, "automation").get(key, default)


@frappe.whitelist()
def create_executive_dashboard_snapshot(
    snapshot_type="Manual",
    snapshot_date=None,
    filters_json=None,
    filters=None,
    replace_existing=0,
    dry_run=0,
    notes=None,
):
    assert_action("create_executive_snapshot")

    snapshot_date = snapshot_date or today()
    filters = parse_filters(filters_json=filters_json, filters=filters)
    snapshot_type = snapshot_type or "Manual"
    dry_run = int(dry_run or 0)
    replace_existing = int(replace_existing or 0)

    summary = quick_executive_dashboard_summary(filters)
    _columns, rows, _message, _chart, _report_summary = execute_executive_dashboard_report(filters)

    if dry_run:
        return {
            "dry_run": True,
            "snapshot_type": snapshot_type,
            "snapshot_date": snapshot_date,
            "filters": filters,
            "kpis": summary.get("kpis"),
            "row_count": len(rows),
            "preview_rows": rows[:10],
            "note": "Dry run only. No snapshot or metric records created.",
        }

    existing = frappe.get_all(
        "NDIS Executive Dashboard Snapshot",
        filters={
            "snapshot_date": snapshot_date,
            "snapshot_type": snapshot_type,
            "status": "Active",
            "filters_json": filters_key(filters),
        },
        fields=["name"],
        limit=1,
    )

    if existing and not replace_existing:
        return {
            "created": False,
            "duplicate": True,
            "snapshot": existing[0].name,
            "snapshot_date": snapshot_date,
            "snapshot_type": snapshot_type,
            "message": "Active snapshot already exists for this date, type, and filter set.",
        }

    if existing and replace_existing:
        for row in existing:
            cancel_executive_dashboard_snapshot(
                snapshot=row.name,
                reason="Replaced by new snapshot.",
                ignore_permissions=True,
            )

    doc = frappe.new_doc("NDIS Executive Dashboard Snapshot")
    doc.snapshot_id = make_snapshot_id(snapshot_type=snapshot_type, snapshot_date=snapshot_date)
    doc.snapshot_date = snapshot_date
    doc.snapshot_type = snapshot_type
    doc.status = "Active"
    doc.period_start = filters.get("from_date")
    doc.period_end = filters.get("to_date")
    doc.house = filters.get("house")
    doc.participant = filters.get("participant")
    doc.funding_source = filters.get("funding_source")
    doc.cost_type = filters.get("cost_type")
    doc.filters_json = filters_key(filters)

    doc.gross_claim_amount = get_claim(summary, "gross_claim_amount")
    doc.paid_revenue = get_kpi(summary, "paid_revenue")
    doc.shortfall_amount = get_claim(summary, "shortfall_amount")
    doc.total_allocated_cost = get_kpi(summary, "total_allocated_cost")
    doc.payroll_cost = get_kpi(summary, "payroll_cost")
    doc.non_payroll_cost = get_kpi(summary, "non_payroll_cost")
    doc.estimated_margin = get_kpi(summary, "estimated_margin")
    doc.estimated_margin_percent = get_kpi(summary, "estimated_margin_percent")
    doc.payroll_cost_ratio = get_kpi(summary, "payroll_cost_ratio")
    doc.shortfall_ratio = get_kpi(summary, "shortfall_ratio")
    doc.open_leakage_amount = get_kpi(summary, "open_leakage")
    doc.open_recovery_amount = get_kpi(summary, "open_recovery")
    doc.unmapped_payroll_lines = int(get_payroll(summary, "unmapped_payroll_lines") or 0)
    doc.failed_automation_runs_7_days = int(get_automation(summary, "failed_runs_7_days") or 0)
    doc.approved_drafts_not_sent = int(get_automation(summary, "approved_drafts_not_sent") or 0)
    doc.escalation_candidates = int(get_automation(summary, "escalation_candidates") or 0)
    doc.overdue_recovery_cases = int(get_automation(summary, "overdue_recovery_cases") or 0)
    doc.metric_count = len(rows)
    doc.created_on = now_datetime()
    doc.created_by_user = frappe.session.user
    doc.raw_summary_json = as_serialisable(summary)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    metric_names = []
    for row in rows:
        metric = frappe.new_doc("NDIS Executive Dashboard Snapshot Metric")
        metric.snapshot = doc.name
        metric.snapshot_date = snapshot_date
        metric.snapshot_type = snapshot_type
        metric.status = "Active"
        metric.section = row.get("section")
        metric.metric = row.get("metric")
        metric.amount = flt(row.get("amount"))
        metric.count_value = int(row.get("count") or 0) if row.get("count") is not None else None
        metric.percent_value = flt(row.get("percent_value"))
        metric.risk_status = row.get("status")
        metric.note = row.get("note")
        metric.insert(ignore_permissions=True)
        metric_names.append(metric.name)

    frappe.db.commit()

    return {
        "created": True,
        "snapshot": doc.name,
        "snapshot_id": doc.snapshot_id,
        "snapshot_date": snapshot_date,
        "snapshot_type": snapshot_type,
        "metric_count": len(metric_names),
        "kpis": summary.get("kpis"),
        "note": "Executive snapshot created for historical trend tracking only. No accounting, payroll, STP, ABA, email, or payment movement created.",
    }


@frappe.whitelist()
def cancel_executive_dashboard_snapshot(snapshot, reason=None, ignore_permissions=False):
    if not ignore_permissions:
        assert_action("cancel_executive_snapshot")

    if not frappe.db.exists("NDIS Executive Dashboard Snapshot", snapshot):
        frappe.throw(_("NDIS Executive Dashboard Snapshot not found: {0}").format(snapshot))

    frappe.db.set_value(
        "NDIS Executive Dashboard Snapshot",
        snapshot,
        {
            "status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "warning_log": reason or "Snapshot cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(
        """
        UPDATE `tabNDIS Executive Dashboard Snapshot Metric`
        SET status = 'Cancelled'
        WHERE snapshot = %(snapshot)s
        """,
        {"snapshot": snapshot},
    )
    frappe.db.commit()

    return {
        "snapshot": snapshot,
        "status": "Cancelled",
        "note": "Snapshot cancelled only. No underlying finance, payroll, recovery, or accounting records were changed.",
    }


@frappe.whitelist()
def daily_executive_dashboard_snapshot_job():
    previous_user = frappe.session.user

    try:
        frappe.set_user("Administrator")
        return create_executive_dashboard_snapshot(
            snapshot_type="Scheduled",
            snapshot_date=today(),
            filters={},
            replace_existing=0,
            dry_run=0,
            notes="Daily scheduled executive dashboard snapshot.",
        )
    finally:
        frappe.set_user(previous_user)


@frappe.whitelist()
def quick_executive_snapshot_summary(limit=20):
    limit = int(limit or 20)
    snapshots = frappe.get_all(
        "NDIS Executive Dashboard Snapshot",
        fields=[
            "name",
            "snapshot_id",
            "snapshot_date",
            "snapshot_type",
            "status",
            "paid_revenue",
            "total_allocated_cost",
            "payroll_cost",
            "estimated_margin",
            "estimated_margin_percent",
            "open_leakage_amount",
            "open_recovery_amount",
            "unmapped_payroll_lines",
            "failed_automation_runs_7_days",
            "metric_count",
        ],
        order_by="snapshot_date desc, creation desc",
        limit=limit,
    )
    metrics = frappe.get_all(
        "NDIS Executive Dashboard Snapshot Metric",
        fields=[
            "name",
            "snapshot",
            "snapshot_date",
            "section",
            "metric",
            "amount",
            "count_value",
            "percent_value",
            "risk_status",
        ],
        order_by="snapshot_date desc, creation desc",
        limit=limit,
    )

    return {
        "snapshots": snapshots,
        "metrics": metrics,
        "note": "Snapshot summary only. No finance, payroll, recovery, accounting, STP, ABA, email, or payment movement created.",
    }


def execute_kpi_trend_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = ["status = 'Active'"]
    params = {"currency": currency()}

    for key in ["snapshot_type", "house", "participant"]:
        value = filters.get(key)
        if value:
            conditions.append(f"{key} = %({key})s")
            params[key] = value

    if filters.get("from_date"):
        conditions.append("snapshot_date >= %(from_date)s")
        params["from_date"] = filters.from_date
    if filters.get("to_date"):
        conditions.append("snapshot_date <= %(to_date)s")
        params["to_date"] = filters.to_date

    columns = [
        {"fieldname": "snapshot", "label": _("Snapshot"), "fieldtype": "Link", "options": "NDIS Executive Dashboard Snapshot", "width": 210},
        {"fieldname": "snapshot_date", "label": _("Snapshot Date"), "fieldtype": "Date", "width": 120},
        {"fieldname": "snapshot_type", "label": _("Type"), "fieldtype": "Data", "width": 100},
        {"fieldname": "paid_revenue", "label": _("Paid Revenue"), "fieldtype": "Currency", "options": "currency", "width": 140},
        {"fieldname": "total_allocated_cost", "label": _("Allocated Cost"), "fieldtype": "Currency", "options": "currency", "width": 140},
        {"fieldname": "payroll_cost", "label": _("Payroll Cost"), "fieldtype": "Currency", "options": "currency", "width": 140},
        {"fieldname": "non_payroll_cost", "label": _("Non-Payroll Cost"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "estimated_margin", "label": _("Estimated Margin"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "estimated_margin_percent", "label": _("Margin %"), "fieldtype": "Percent", "width": 110},
        {"fieldname": "shortfall_amount", "label": _("Shortfall"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "open_leakage_amount", "label": _("Open Leakage"), "fieldtype": "Currency", "options": "currency", "width": 140},
        {"fieldname": "open_recovery_amount", "label": _("Open Recovery"), "fieldtype": "Currency", "options": "currency", "width": 140},
        {"fieldname": "unmapped_payroll_lines", "label": _("Unmapped Payroll"), "fieldtype": "Int", "width": 140},
        {"fieldname": "failed_automation_runs_7_days", "label": _("Failed Automation"), "fieldtype": "Int", "width": 140},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            name AS snapshot,
            snapshot_date,
            snapshot_type,
            paid_revenue,
            total_allocated_cost,
            payroll_cost,
            non_payroll_cost,
            estimated_margin,
            estimated_margin_percent,
            shortfall_amount,
            open_leakage_amount,
            open_recovery_amount,
            unmapped_payroll_lines,
            failed_automation_runs_7_days,
            %(currency)s AS currency
        FROM `tabNDIS Executive Dashboard Snapshot`
        WHERE {" AND ".join(conditions)}
        ORDER BY snapshot_date ASC, creation ASC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [str(row.snapshot_date) for row in data],
            "datasets": [
                {"name": "Paid Revenue", "values": [flt(row.paid_revenue) for row in data]},
                {"name": "Allocated Cost", "values": [flt(row.total_allocated_cost) for row in data]},
                {"name": "Margin", "values": [flt(row.estimated_margin) for row in data]},
            ],
        },
        "type": "line",
    }
    latest = data[-1] if data else frappe._dict()
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Snapshots"), "datatype": "Int"},
        {"value": flt(latest.get("paid_revenue")), "indicator": "Green", "label": _("Latest Paid Revenue"), "datatype": "Currency", "currency": params["currency"]},
        {"value": flt(latest.get("estimated_margin")), "indicator": "Green" if flt(latest.get("estimated_margin")) >= 0 else "Red", "label": _("Latest Margin"), "datatype": "Currency", "currency": params["currency"]},
        {"value": flt(latest.get("estimated_margin_percent")), "indicator": "Green" if flt(latest.get("estimated_margin_percent")) >= 0 else "Red", "label": _("Latest Margin %"), "datatype": "Percent"},
    ]

    return columns, data, None, chart, summary


def execute_snapshot_detail_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = ["m.status = 'Active'"]
    params = {"currency": currency()}

    for key in ["snapshot", "section", "risk_status"]:
        value = filters.get(key)
        if value:
            conditions.append(f"m.{key} = %({key})s")
            params[key] = value

    if filters.get("from_date"):
        conditions.append("m.snapshot_date >= %(from_date)s")
        params["from_date"] = filters.from_date
    if filters.get("to_date"):
        conditions.append("m.snapshot_date <= %(to_date)s")
        params["to_date"] = filters.to_date

    columns = [
        {"fieldname": "snapshot", "label": _("Snapshot"), "fieldtype": "Link", "options": "NDIS Executive Dashboard Snapshot", "width": 210},
        {"fieldname": "snapshot_date", "label": _("Snapshot Date"), "fieldtype": "Date", "width": 120},
        {"fieldname": "snapshot_type", "label": _("Type"), "fieldtype": "Data", "width": 100},
        {"fieldname": "section", "label": _("Section"), "fieldtype": "Data", "width": 150},
        {"fieldname": "metric", "label": _("Metric"), "fieldtype": "Data", "width": 250},
        {"fieldname": "amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 140},
        {"fieldname": "count_value", "label": _("Count"), "fieldtype": "Int", "width": 90},
        {"fieldname": "percent_value", "label": _("Percent"), "fieldtype": "Percent", "width": 110},
        {"fieldname": "risk_status", "label": _("Risk Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "note", "label": _("Note"), "fieldtype": "Small Text", "width": 380},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            m.snapshot,
            m.snapshot_date,
            m.snapshot_type,
            m.section,
            m.metric,
            m.amount,
            m.count_value,
            m.percent_value,
            m.risk_status,
            m.note,
            %(currency)s AS currency
        FROM `tabNDIS Executive Dashboard Snapshot Metric` m
        WHERE {" AND ".join(conditions)}
        ORDER BY m.snapshot_date DESC, m.section ASC, m.creation ASC
        """,
        params,
        as_dict=True,
    )

    chart_map = {}
    for row in data:
        if row.risk_status in ["Risk", "Watch", "Good", "Info"]:
            chart_map[row.risk_status] = chart_map.get(row.risk_status, 0) + 1

    chart = {
        "data": {
            "labels": list(chart_map.keys()),
            "datasets": [{"name": "Metric Count", "values": list(chart_map.values())}],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Metrics"), "datatype": "Int"},
        {"value": len([row for row in data if row.risk_status == "Risk"]), "indicator": "Red", "label": _("Risk Metrics"), "datatype": "Int"},
        {"value": len([row for row in data if row.risk_status == "Watch"]), "indicator": "Orange", "label": _("Watch Metrics"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary
