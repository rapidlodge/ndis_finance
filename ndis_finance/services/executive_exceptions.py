import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime

from ndis_finance.services.executive_dashboard import quick_executive_dashboard_summary
from ndis_finance.services.permissions import assert_action


METRIC_LABELS = {
    "estimated_margin_percent": "Estimated Margin %",
    "estimated_margin": "Estimated Margin",
    "payroll_cost_ratio": "Payroll Cost Ratio %",
    "shortfall_ratio": "Shortfall Ratio %",
    "open_leakage": "Open Leakage",
    "open_recovery": "Open Recovery",
    "unmapped_payroll_lines": "Unmapped Payroll Lines",
    "failed_automation_runs_7_days": "Failed Automation Runs 7 Days",
    "approved_drafts_not_sent": "Approved Drafts Not Sent",
    "escalation_candidates": "Escalation Candidates",
    "overdue_recovery_cases": "Overdue Recovery Cases",
    "paid_revenue": "Paid Revenue",
    "total_allocated_cost": "Total Allocated Cost",
    "payroll_cost": "Payroll Cost",
    "non_payroll_cost": "Non-Payroll Cost",
}

SNAPSHOT_FIELD_MAP = {
    "estimated_margin_percent": "estimated_margin_percent",
    "estimated_margin": "estimated_margin",
    "payroll_cost_ratio": "payroll_cost_ratio",
    "shortfall_ratio": "shortfall_ratio",
    "open_leakage": "open_leakage_amount",
    "open_recovery": "open_recovery_amount",
    "unmapped_payroll_lines": "unmapped_payroll_lines",
    "failed_automation_runs_7_days": "failed_automation_runs_7_days",
    "approved_drafts_not_sent": "approved_drafts_not_sent",
    "escalation_candidates": "escalation_candidates",
    "overdue_recovery_cases": "overdue_recovery_cases",
    "paid_revenue": "paid_revenue",
    "total_allocated_cost": "total_allocated_cost",
    "payroll_cost": "payroll_cost",
    "non_payroll_cost": "non_payroll_cost",
}

OPEN_STATUSES = ["Open", "In Review"]


def make_alert_id(rule_id):
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    safe_rule = frappe.scrub(rule_id).replace("_", "-").upper()
    return f"NDIS-EXEC-ALERT-{safe_rule}-{timestamp}-{frappe.generate_hash(length=5).upper()}"


def compare(metric_value, operator, threshold_value):
    metric_value = flt(metric_value)
    threshold_value = flt(threshold_value)
    if operator == "<":
        return metric_value < threshold_value
    if operator == "<=":
        return metric_value <= threshold_value
    if operator == ">":
        return metric_value > threshold_value
    if operator == ">=":
        return metric_value >= threshold_value
    if operator == "==":
        return metric_value == threshold_value
    if operator == "!=":
        return metric_value != threshold_value
    frappe.throw(_("Unsupported operator: {0}").format(operator))


def variance(metric_value, operator, threshold_value):
    metric_value = flt(metric_value)
    threshold_value = flt(threshold_value)
    if operator in [">", ">="]:
        return metric_value - threshold_value
    if operator in ["<", "<="]:
        return threshold_value - metric_value
    return metric_value - threshold_value


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)


def get_latest_snapshot():
    row = frappe.get_all(
        "NDIS Executive Dashboard Snapshot",
        filters={"status": "Active"},
        fields=["name"],
        order_by="snapshot_date desc, creation desc",
        limit=1,
    )
    return row[0].name if row else None


def get_metric_from_snapshot(snapshot, metric_key):
    fieldname = SNAPSHOT_FIELD_MAP.get(metric_key)
    if not fieldname:
        frappe.throw(_("Unsupported executive metric key: {0}").format(metric_key))
    return flt(frappe.db.get_value("NDIS Executive Dashboard Snapshot", snapshot, fieldname))


def get_live_metric(metric_key):
    summary = quick_executive_dashboard_summary()
    kpis = summary.get("kpis") or {}
    payroll = summary.get("payroll") or {}
    automation = summary.get("automation") or {}
    if metric_key in kpis:
        return flt(kpis.get(metric_key))
    if metric_key == "unmapped_payroll_lines":
        return flt(payroll.get("unmapped_payroll_lines"))
    if metric_key in automation:
        return flt(automation.get(metric_key))
    return 0


@frappe.whitelist()
def evaluate_executive_exception_rules(snapshot=None, use_live_dashboard=0, rule=None, dry_run=0):
    assert_action("evaluate_executive_exceptions")
    dry_run = int(dry_run or 0)
    use_live_dashboard = int(use_live_dashboard or 0)
    source = "Live Dashboard" if use_live_dashboard else "Latest Snapshot"

    if not use_live_dashboard:
        snapshot = snapshot or get_latest_snapshot()
        if not snapshot:
            frappe.throw(_("No active executive dashboard snapshot found. Create a snapshot first or use_live_dashboard=1."))
        source = "Selected Snapshot" if snapshot else "Latest Snapshot"

    rules = get_rules(rule)
    results = []
    created = 0
    triggered = 0
    skipped_duplicates = 0

    for rule_doc in rules:
        metric_value = get_live_metric(rule_doc.metric_key) if use_live_dashboard else get_metric_from_snapshot(snapshot, rule_doc.metric_key)
        is_triggered = compare(metric_value, rule_doc.operator, rule_doc.threshold_value)
        if not dry_run:
            update_rule_evaluation_status(rule_doc.name, metric_value, triggered=is_triggered)

        result = {
            "rule": rule_doc.name,
            "rule_id": rule_doc.rule_id,
            "rule_name": rule_doc.rule_name,
            "metric_key": rule_doc.metric_key,
            "metric_value": metric_value,
            "operator": rule_doc.operator,
            "threshold_value": flt(rule_doc.threshold_value),
            "triggered": is_triggered,
            "alert_created": False,
        }

        if is_triggered:
            triggered += 1
            if dry_run:
                result["dry_run"] = True
            else:
                duplicate = find_duplicate_alert(rule_doc, snapshot=snapshot)
                if duplicate:
                    skipped_duplicates += 1
                    result["duplicate_alert"] = duplicate
                else:
                    alert = create_alert(rule_doc, metric_value, snapshot=snapshot, source=source)
                    created += 1
                    result["alert_created"] = True
                    result["alert"] = alert

        results.append(result)

    if not dry_run:
        refresh_all_rule_open_counts()
        frappe.db.commit()

    return {
        "dry_run": bool(dry_run),
        "source": source,
        "snapshot": snapshot,
        "rules_checked": len(rules),
        "triggered": triggered,
        "alerts_created": created,
        "duplicate_alerts_skipped": skipped_duplicates,
        "results": results,
        "note": "Executive exception evaluation creates internal alert records only. No accounting, payroll, STP, ABA, email, or payment movement created.",
    }


def get_rules(rule=None):
    filters = {"active": 1}
    if rule:
        filters["name"] = rule
    return frappe.get_all(
        "NDIS Executive Exception Rule",
        filters=filters,
        fields=[
            "name",
            "rule_id",
            "rule_name",
            "active",
            "severity",
            "metric_key",
            "operator",
            "threshold_value",
            "duplicate_control",
            "description",
            "recommendation",
        ],
        order_by="severity desc, rule_name asc",
    )


def find_duplicate_alert(rule_doc, snapshot=None):
    if rule_doc.duplicate_control == "Allow Multiple":
        return None
    filters = {"rule": rule_doc.name, "status": ["in", OPEN_STATUSES]}
    if rule_doc.duplicate_control == "One Alert per Snapshot" and snapshot:
        filters["snapshot"] = snapshot
    existing = frappe.get_all(
        "NDIS Executive Exception Alert",
        filters=filters,
        fields=["name"],
        order_by="creation desc",
        limit=1,
    )
    return existing[0].name if existing else None


def create_alert(rule_doc, metric_value, snapshot=None, source="Latest Snapshot"):
    threshold = flt(rule_doc.threshold_value)
    metric_label = METRIC_LABELS.get(rule_doc.metric_key, rule_doc.metric_key)
    snapshot_date = None
    if snapshot:
        snapshot_date = frappe.db.get_value("NDIS Executive Dashboard Snapshot", snapshot, "snapshot_date")

    alert = frappe.new_doc("NDIS Executive Exception Alert")
    alert.alert_id = make_alert_id(rule_doc.rule_id)
    alert.status = "Open"
    alert.severity = rule_doc.severity
    alert.rule = rule_doc.name
    alert.rule_name = rule_doc.rule_name
    alert.source = source
    alert.snapshot = snapshot
    alert.snapshot_date = snapshot_date
    alert.metric_key = rule_doc.metric_key
    alert.metric_label = metric_label
    alert.metric_value = flt(metric_value)
    alert.operator = rule_doc.operator
    alert.threshold_value = threshold
    alert.variance_value = variance(metric_value, rule_doc.operator, threshold)
    alert.message = f"{metric_label} is {flt(metric_value):.2f}; rule requires {rule_doc.operator} {threshold:.2f}."
    alert.recommendation = rule_doc.recommendation
    alert.created_on = now_datetime()
    alert.created_by_user = frappe.session.user
    alert.insert(ignore_permissions=True)

    frappe.db.set_value("NDIS Executive Exception Rule", rule_doc.name, "last_triggered_on", now_datetime(), update_modified=False)
    return alert.name


def update_rule_evaluation_status(rule_name, metric_value, triggered=False):
    frappe.db.set_value(
        "NDIS Executive Exception Rule",
        rule_name,
        {"last_evaluated_on": now_datetime(), "last_metric_value": flt(metric_value)},
        update_modified=False,
    )


@frappe.whitelist()
def refresh_rule_open_count(rule):
    count = frappe.db.count("NDIS Executive Exception Alert", {"rule": rule, "status": ["in", OPEN_STATUSES]})
    frappe.db.set_value("NDIS Executive Exception Rule", rule, "open_alert_count", count, update_modified=False)
    return {"rule": rule, "open_alert_count": count}


def refresh_all_rule_open_counts():
    for rule in frappe.get_all("NDIS Executive Exception Rule", fields=["name"]):
        refresh_rule_open_count(rule.name)


@frappe.whitelist()
def mark_exception_alert_in_review(alert, note=None):
    assert_action("resolve_executive_exception_alert")
    if not frappe.db.exists("NDIS Executive Exception Alert", alert):
        frappe.throw(_("NDIS Executive Exception Alert not found: {0}").format(alert))
    frappe.db.set_value(
        "NDIS Executive Exception Alert",
        alert,
        {"status": "In Review", "reviewed_on": now_datetime(), "reviewed_by": frappe.session.user, "resolution_note": note},
        update_modified=False,
    )
    rule = frappe.db.get_value("NDIS Executive Exception Alert", alert, "rule")
    if rule:
        refresh_rule_open_count(rule)
    frappe.db.commit()
    return {"alert": alert, "status": "In Review"}


@frappe.whitelist()
def resolve_exception_alert(alert, resolution_note=None):
    assert_action("resolve_executive_exception_alert")
    if not frappe.db.exists("NDIS Executive Exception Alert", alert):
        frappe.throw(_("NDIS Executive Exception Alert not found: {0}").format(alert))
    frappe.db.set_value(
        "NDIS Executive Exception Alert",
        alert,
        {"status": "Resolved", "resolved_on": now_datetime(), "resolved_by": frappe.session.user, "resolution_note": resolution_note or "Resolved."},
        update_modified=False,
    )
    rule = frappe.db.get_value("NDIS Executive Exception Alert", alert, "rule")
    if rule:
        refresh_rule_open_count(rule)
    frappe.db.commit()
    return {"alert": alert, "status": "Resolved", "note": "Exception alert resolved only. No underlying finance/payroll/accounting records were changed."}


@frappe.whitelist()
def cancel_exception_alert(alert, reason=None):
    assert_action("resolve_executive_exception_alert")
    if not frappe.db.exists("NDIS Executive Exception Alert", alert):
        frappe.throw(_("NDIS Executive Exception Alert not found: {0}").format(alert))
    frappe.db.set_value(
        "NDIS Executive Exception Alert",
        alert,
        {"status": "Cancelled", "resolved_on": now_datetime(), "resolved_by": frappe.session.user, "resolution_note": reason or "Cancelled."},
        update_modified=False,
    )
    rule = frappe.db.get_value("NDIS Executive Exception Alert", alert, "rule")
    if rule:
        refresh_rule_open_count(rule)
    frappe.db.commit()
    return {"alert": alert, "status": "Cancelled", "note": "Exception alert cancelled only. No underlying finance/payroll/accounting records were changed."}


@frappe.whitelist()
def daily_executive_exception_evaluation_job():
    previous_user = frappe.session.user
    try:
        frappe.set_user("Administrator")
        return evaluate_executive_exception_rules(snapshot=None, use_live_dashboard=0, dry_run=0)
    finally:
        frappe.set_user(previous_user)


@frappe.whitelist()
def quick_executive_exception_summary(limit=20):
    limit = int(limit or 20)
    rules = frappe.get_all(
        "NDIS Executive Exception Rule",
        fields=[
            "name",
            "rule_id",
            "rule_name",
            "active",
            "severity",
            "metric_key",
            "operator",
            "threshold_value",
            "last_evaluated_on",
            "last_metric_value",
            "last_triggered_on",
            "open_alert_count",
        ],
        order_by="open_alert_count desc, rule_name asc",
        limit=limit,
    )
    alerts = frappe.get_all(
        "NDIS Executive Exception Alert",
        fields=[
            "name",
            "alert_id",
            "status",
            "severity",
            "rule",
            "rule_name",
            "snapshot",
            "snapshot_date",
            "metric_key",
            "metric_value",
            "operator",
            "threshold_value",
            "variance_value",
            "created_on",
        ],
        order_by="creation desc",
        limit=limit,
    )
    open_counts = frappe.db.sql(
        """
        SELECT severity, status, COUNT(*) AS count
        FROM `tabNDIS Executive Exception Alert`
        GROUP BY severity, status
        ORDER BY severity, status
        """,
        as_dict=True,
    )
    return {
        "rules": rules,
        "alerts": alerts,
        "open_counts": open_counts,
        "note": "Executive exception summary only. No accounting, payroll, STP, ABA, email, or payment movement created.",
    }


def execute_exception_register_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    for key in ["status", "severity", "rule", "snapshot"]:
        value = filters.get(key)
        if value:
            conditions.append(f"a.{key} = %({key})s")
            params[key] = value
    if filters.get("from_date"):
        conditions.append("a.snapshot_date >= %(from_date)s")
        params["from_date"] = filters.from_date
    if filters.get("to_date"):
        conditions.append("a.snapshot_date <= %(to_date)s")
        params["to_date"] = filters.to_date

    columns = [
        {"fieldname": "alert", "label": _("Alert"), "fieldtype": "Link", "options": "NDIS Executive Exception Alert", "width": 210},
        {"fieldname": "alert_id", "label": _("Alert ID"), "fieldtype": "Data", "width": 280},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 110},
        {"fieldname": "rule", "label": _("Rule"), "fieldtype": "Link", "options": "NDIS Executive Exception Rule", "width": 210},
        {"fieldname": "rule_name", "label": _("Rule Name"), "fieldtype": "Data", "width": 260},
        {"fieldname": "snapshot", "label": _("Snapshot"), "fieldtype": "Link", "options": "NDIS Executive Dashboard Snapshot", "width": 210},
        {"fieldname": "snapshot_date", "label": _("Snapshot Date"), "fieldtype": "Date", "width": 120},
        {"fieldname": "metric_label", "label": _("Metric"), "fieldtype": "Data", "width": 210},
        {"fieldname": "metric_value", "label": _("Metric Value"), "fieldtype": "Float", "width": 130},
        {"fieldname": "operator", "label": _("Operator"), "fieldtype": "Data", "width": 90},
        {"fieldname": "threshold_value", "label": _("Threshold"), "fieldtype": "Float", "width": 120},
        {"fieldname": "variance_value", "label": _("Variance"), "fieldtype": "Float", "width": 120},
        {"fieldname": "message", "label": _("Message"), "fieldtype": "Small Text", "width": 360},
        {"fieldname": "recommendation", "label": _("Recommendation"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "created_on", "label": _("Created On"), "fieldtype": "Datetime", "width": 160},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            a.name AS alert, a.alert_id, a.status, a.severity, a.rule, a.rule_name,
            a.snapshot, a.snapshot_date, a.metric_label, a.metric_value, a.operator,
            a.threshold_value, a.variance_value, a.message, a.recommendation, a.created_on
        FROM `tabNDIS Executive Exception Alert` a
        {build_where(conditions)}
        ORDER BY
            CASE a.severity WHEN 'Critical' THEN 1 WHEN 'High' THEN 2 WHEN 'Medium' THEN 3 WHEN 'Low' THEN 4 ELSE 5 END,
            a.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart_map = {}
    for row in data:
        key = f"{row.severity} / {row.status}"
        chart_map[key] = chart_map.get(key, 0) + 1
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Alert Count", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Alerts"), "datatype": "Int"},
        {"value": len([row for row in data if row.status in OPEN_STATUSES]), "indicator": "Red", "label": _("Open/In Review"), "datatype": "Int"},
        {"value": len([row for row in data if row.severity == "Critical"]), "indicator": "Red", "label": _("Critical"), "datatype": "Int"},
        {"value": len([row for row in data if row.severity == "High"]), "indicator": "Orange", "label": _("High"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_exception_rule_status_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("active") not in [None, ""]:
        conditions.append("r.active = %(active)s")
        params["active"] = int(filters.active)
    for key in ["severity", "metric_key"]:
        value = filters.get(key)
        if value:
            conditions.append(f"r.{key} = %({key})s")
            params[key] = value
    columns = [
        {"fieldname": "rule", "label": _("Rule"), "fieldtype": "Link", "options": "NDIS Executive Exception Rule", "width": 210},
        {"fieldname": "rule_id", "label": _("Rule ID"), "fieldtype": "Data", "width": 270},
        {"fieldname": "rule_name", "label": _("Rule Name"), "fieldtype": "Data", "width": 280},
        {"fieldname": "active", "label": _("Active"), "fieldtype": "Check", "width": 90},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 110},
        {"fieldname": "metric_key", "label": _("Metric Key"), "fieldtype": "Data", "width": 210},
        {"fieldname": "operator", "label": _("Operator"), "fieldtype": "Data", "width": 90},
        {"fieldname": "threshold_value", "label": _("Threshold"), "fieldtype": "Float", "width": 120},
        {"fieldname": "last_metric_value", "label": _("Last Metric Value"), "fieldtype": "Float", "width": 150},
        {"fieldname": "last_evaluated_on", "label": _("Last Evaluated On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "last_triggered_on", "label": _("Last Triggered On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "open_alert_count", "label": _("Open Alerts"), "fieldtype": "Int", "width": 120},
        {"fieldname": "description", "label": _("Description"), "fieldtype": "Small Text", "width": 360},
        {"fieldname": "recommendation", "label": _("Recommendation"), "fieldtype": "Small Text", "width": 420},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            r.name AS rule, r.rule_id, r.rule_name, r.active, r.severity, r.metric_key,
            r.operator, r.threshold_value, r.last_metric_value, r.last_evaluated_on,
            r.last_triggered_on, r.open_alert_count, r.description, r.recommendation
        FROM `tabNDIS Executive Exception Rule` r
        {build_where(conditions)}
        ORDER BY
            CASE r.severity WHEN 'Critical' THEN 1 WHEN 'High' THEN 2 WHEN 'Medium' THEN 3 WHEN 'Low' THEN 4 ELSE 5 END,
            r.open_alert_count DESC,
            r.rule_name ASC
        """,
        params,
        as_dict=True,
    )
    chart = {"data": {"labels": [row.rule_name for row in data], "datasets": [{"name": "Open Alerts", "values": [int(row.open_alert_count or 0) for row in data]}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Rules"), "datatype": "Int"},
        {"value": len([row for row in data if row.active]), "indicator": "Green", "label": _("Active Rules"), "datatype": "Int"},
        {"value": sum(int(row.open_alert_count or 0) for row in data), "indicator": "Red", "label": _("Open Alerts"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary
