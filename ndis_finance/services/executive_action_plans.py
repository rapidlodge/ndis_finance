import frappe
from frappe import _
from frappe.utils import add_days, flt, get_datetime, getdate, now_datetime, today

from ndis_finance.services.permissions import assert_action


DEFAULT_STEPS = [
    {
        "title": "Review exception source",
        "detail": "Review the exception alert, related rule, dashboard snapshot and supporting metrics.",
    },
    {
        "title": "Identify root cause",
        "detail": "Identify the operational or finance driver causing this exception.",
    },
    {
        "title": "Apply corrective action",
        "detail": "Complete the agreed corrective action and document the result.",
    },
    {
        "title": "Attach evidence and request sign-off",
        "detail": "Attach supporting evidence and prepare the action plan for management sign-off.",
    },
]

OPEN_PLAN_STATUSES = ["Draft", "In Progress", "Overdue", "Escalated"]
OPEN_STEP_STATUSES = ["Open", "In Progress", "Overdue"]


def make_action_plan_id(alert):
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    safe_alert = frappe.scrub(alert).replace("_", "-").upper()
    return f"NDIS-EXEC-ACTION-{safe_alert}-{timestamp}-{frappe.generate_hash(length=5).upper()}"


def default_due_date(priority):
    if priority == "Critical":
        return add_days(today(), 2)
    if priority == "High":
        return add_days(today(), 5)
    if priority == "Medium":
        return add_days(today(), 7)
    return add_days(today(), 14)


def get_alert(alert):
    if not frappe.db.exists("NDIS Executive Exception Alert", alert):
        frappe.throw(_("NDIS Executive Exception Alert not found: {0}").format(alert))
    return frappe.get_doc("NDIS Executive Exception Alert", alert)


def find_open_action_plan(alert):
    rows = frappe.get_all(
        "NDIS Executive Exception Action Plan",
        filters={"exception_alert": alert, "status": ["in", OPEN_PLAN_STATUSES]},
        fields=["name"],
        order_by="creation desc",
        limit=1,
    )
    return rows[0].name if rows else None


@frappe.whitelist()
def create_action_plan_from_alert(
    alert,
    assigned_to=None,
    due_date=None,
    priority=None,
    action_title=None,
    action_summary=None,
    replace_existing=0,
    dry_run=0,
    notes=None,
):
    assert_action("manage_executive_action_plan")

    alert_doc = get_alert(alert)
    priority = priority or alert_doc.severity or "Medium"
    due_date = due_date or default_due_date(priority)
    assigned_to = assigned_to or frappe.session.user
    action_title = action_title or f"Action Plan for {alert_doc.rule_name}"
    action_summary = action_summary or alert_doc.message
    existing = find_open_action_plan(alert)

    if existing and not int(replace_existing or 0):
        return {
            "created": False,
            "duplicate": True,
            "action_plan": existing,
            "message": "Open action plan already exists for this alert.",
        }

    if int(dry_run or 0):
        return {
            "dry_run": True,
            "alert": alert,
            "priority": priority,
            "assigned_to": assigned_to,
            "due_date": due_date,
            "action_title": action_title,
            "default_steps": DEFAULT_STEPS,
            "note": "Dry run only. No action plan or action steps created.",
        }

    if existing and int(replace_existing or 0):
        cancel_action_plan(existing, reason="Cancelled by replace_existing action plan creation.", ignore_permissions=True)

    plan = frappe.new_doc("NDIS Executive Exception Action Plan")
    plan.action_plan_id = make_action_plan_id(alert)
    plan.status = "In Progress"
    plan.priority = priority
    plan.exception_alert = alert
    plan.exception_rule = alert_doc.rule
    plan.rule_name = alert_doc.rule_name
    plan.severity = alert_doc.severity
    plan.snapshot = alert_doc.snapshot
    plan.snapshot_date = alert_doc.snapshot_date
    plan.metric_key = alert_doc.metric_key
    plan.metric_value = flt(alert_doc.metric_value)
    plan.threshold_value = flt(alert_doc.threshold_value)
    plan.action_title = action_title
    plan.assigned_to = assigned_to
    plan.due_date = due_date
    plan.escalation_level = "None"
    plan.action_summary = action_summary
    plan.recommendation = alert_doc.recommendation
    plan.created_on = now_datetime()
    plan.created_by_user = frappe.session.user
    plan.started_on = now_datetime()
    plan.notes = notes
    plan.insert(ignore_permissions=True)

    created_steps = []
    for idx, step in enumerate(DEFAULT_STEPS, start=1):
        step_doc = create_step(
            action_plan=plan.name,
            step_no=idx,
            action_title=step["title"],
            action_detail=step["detail"],
            assigned_to=assigned_to,
            due_date=due_date,
            priority=priority,
            commit=False,
        )
        created_steps.append(step_doc.name)

    refresh_action_plan_summary(plan.name)

    if alert_doc.status == "Open":
        frappe.db.set_value(
            "NDIS Executive Exception Alert",
            alert,
            {
                "status": "In Review",
                "reviewed_on": now_datetime(),
                "reviewed_by": frappe.session.user,
                "resolution_note": "Action plan created.",
            },
            update_modified=False,
        )

    frappe.db.commit()

    return {
        "created": True,
        "action_plan": plan.name,
        "action_plan_id": plan.action_plan_id,
        "step_count": len(created_steps),
        "steps": created_steps,
        "note": "Action plan created for internal management follow-up only. No accounting, payroll, STP, ABA, email, or payment movement created.",
    }


def create_step(action_plan, step_no, action_title, action_detail=None, assigned_to=None, due_date=None, priority=None, commit=True):
    if not frappe.db.exists("NDIS Executive Exception Action Plan", action_plan):
        frappe.throw(_("Action Plan not found: {0}").format(action_plan))

    step = frappe.new_doc("NDIS Executive Exception Action Step")
    step.action_plan = action_plan
    step.status = "Open"
    step.priority = priority
    step.step_no = int(step_no or 0)
    step.action_title = action_title
    step.assigned_to = assigned_to
    step.due_date = due_date
    step.action_detail = action_detail
    step.insert(ignore_permissions=True)

    if commit:
        refresh_action_plan_summary(action_plan)
        frappe.db.commit()

    return step


@frappe.whitelist()
def add_action_step(action_plan, action_title, action_detail=None, assigned_to=None, due_date=None):
    assert_action("update_executive_action_plan")
    existing = frappe.get_all(
        "NDIS Executive Exception Action Step",
        filters={"action_plan": action_plan},
        fields=["step_no"],
        order_by="step_no desc",
        limit=1,
    )
    next_no = int(existing[0].step_no or 0) + 1 if existing else 1
    priority = frappe.db.get_value("NDIS Executive Exception Action Plan", action_plan, "priority")
    step = create_step(action_plan, next_no, action_title, action_detail, assigned_to, due_date, priority, commit=True)
    return {"created": True, "step": step.name, "step_no": next_no}


@frappe.whitelist()
def mark_step_in_progress(step, note=None):
    assert_action("update_executive_action_plan")
    if not frappe.db.exists("NDIS Executive Exception Action Step", step):
        frappe.throw(_("Action Step not found: {0}").format(step))
    action_plan = frappe.db.get_value("NDIS Executive Exception Action Step", step, "action_plan")
    frappe.db.set_value(
        "NDIS Executive Exception Action Step",
        step,
        {"status": "In Progress", "follow_up_note": note},
        update_modified=False,
    )
    refresh_action_plan_summary(action_plan)
    frappe.db.commit()
    return {"step": step, "status": "In Progress"}


@frappe.whitelist()
def complete_action_step(step, completion_note=None, evidence_attachment=None):
    assert_action("update_executive_action_plan")
    if not frappe.db.exists("NDIS Executive Exception Action Step", step):
        frappe.throw(_("Action Step not found: {0}").format(step))
    action_plan = frappe.db.get_value("NDIS Executive Exception Action Step", step, "action_plan")
    frappe.db.set_value(
        "NDIS Executive Exception Action Step",
        step,
        {
            "status": "Completed",
            "completed_on": now_datetime(),
            "completed_by": frappe.session.user,
            "completion_note": completion_note,
            "evidence_attachment": evidence_attachment,
        },
        update_modified=False,
    )
    refresh_action_plan_summary(action_plan)
    frappe.db.commit()
    return {"step": step, "status": "Completed"}


@frappe.whitelist()
def escalate_action_plan(action_plan, escalation_level="Level 1", escalation_note=None):
    assert_action("update_executive_action_plan")
    if not frappe.db.exists("NDIS Executive Exception Action Plan", action_plan):
        frappe.throw(_("Action Plan not found: {0}").format(action_plan))
    frappe.db.set_value(
        "NDIS Executive Exception Action Plan",
        action_plan,
        {"status": "Escalated", "escalation_level": escalation_level, "warning_log": escalation_note or f"Escalated to {escalation_level}."},
        update_modified=False,
    )
    frappe.db.commit()
    return {
        "action_plan": action_plan,
        "status": "Escalated",
        "escalation_level": escalation_level,
        "note": "Action plan escalated internally only. No email or external notification sent.",
    }


@frappe.whitelist()
def complete_action_plan(action_plan, resolution_summary, resolution_evidence=None, management_sign_off=1):
    assert_action("complete_executive_action_plan")
    if not frappe.db.exists("NDIS Executive Exception Action Plan", action_plan):
        frappe.throw(_("Action Plan not found: {0}").format(action_plan))

    plan = frappe.get_doc("NDIS Executive Exception Action Plan", action_plan)
    open_steps = frappe.db.count(
        "NDIS Executive Exception Action Step",
        {"action_plan": action_plan, "status": ["in", OPEN_STEP_STATUSES]},
    )
    if open_steps:
        frappe.throw(_("Cannot complete action plan while {0} action step(s) remain open.").format(open_steps))

    signed_off = int(management_sign_off or 0)
    frappe.db.set_value(
        "NDIS Executive Exception Action Plan",
        action_plan,
        {
            "status": "Completed",
            "resolution_summary": resolution_summary,
            "resolution_evidence": resolution_evidence,
            "management_sign_off": signed_off,
            "signed_off_by": frappe.session.user if signed_off else None,
            "signed_off_on": now_datetime() if signed_off else None,
            "completed_on": now_datetime(),
            "completed_by": frappe.session.user,
        },
        update_modified=False,
    )

    if plan.exception_alert:
        frappe.db.set_value(
            "NDIS Executive Exception Alert",
            plan.exception_alert,
            {
                "status": "Resolved",
                "resolved_on": now_datetime(),
                "resolved_by": frappe.session.user,
                "resolution_note": resolution_summary,
            },
            update_modified=False,
        )
        rule = frappe.db.get_value("NDIS Executive Exception Alert", plan.exception_alert, "rule")
        if rule and frappe.db.exists("NDIS Executive Exception Rule", rule):
            refresh_rule_open_count(rule)

    refresh_action_plan_summary(action_plan)
    frappe.db.commit()
    return {
        "action_plan": action_plan,
        "status": "Completed",
        "note": "Action plan completed and related alert resolved internally only. No accounting, payroll, STP, ABA, email, or payment movement created.",
    }


def refresh_rule_open_count(rule):
    count = frappe.db.count("NDIS Executive Exception Alert", {"rule": rule, "status": ["in", ["Open", "In Review"]]})
    frappe.db.set_value("NDIS Executive Exception Rule", rule, "open_alert_count", count, update_modified=False)


@frappe.whitelist()
def cancel_action_plan(action_plan, reason=None, ignore_permissions=False):
    if not ignore_permissions:
        assert_action("cancel_executive_action_plan")
    if not frappe.db.exists("NDIS Executive Exception Action Plan", action_plan):
        frappe.throw(_("Action Plan not found: {0}").format(action_plan))
    frappe.db.set_value(
        "NDIS Executive Exception Action Plan",
        action_plan,
        {
            "status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "warning_log": reason or "Action plan cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(
        """
        UPDATE `tabNDIS Executive Exception Action Step`
        SET status = 'Cancelled',
            cancelled_on = %(now)s,
            cancelled_by = %(user)s
        WHERE action_plan = %(action_plan)s
        AND status NOT IN ('Completed', 'Cancelled')
        """,
        {"now": now_datetime(), "user": frappe.session.user, "action_plan": action_plan},
    )
    refresh_action_plan_summary(action_plan)
    frappe.db.commit()
    return {
        "action_plan": action_plan,
        "status": "Cancelled",
        "note": "Action plan cancelled internally only. No underlying finance/payroll/accounting records were changed.",
    }


@frappe.whitelist()
def refresh_action_plan_summary(action_plan):
    if not frappe.db.exists("NDIS Executive Exception Action Plan", action_plan):
        frappe.throw(_("Action Plan not found: {0}").format(action_plan))
    totals = frappe.db.sql(
        """
        SELECT
            COUNT(*) AS total_steps,
            COALESCE(SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END), 0) AS completed_steps,
            COALESCE(SUM(CASE WHEN status NOT IN ('Completed', 'Cancelled') THEN 1 ELSE 0 END), 0) AS open_steps,
            COALESCE(SUM(CASE WHEN status NOT IN ('Completed', 'Cancelled') AND due_date < CURDATE() THEN 1 ELSE 0 END), 0) AS overdue_steps
        FROM `tabNDIS Executive Exception Action Step`
        WHERE action_plan = %(action_plan)s
        """,
        {"action_plan": action_plan},
        as_dict=True,
    )[0]
    current_status, due_date = frappe.db.get_value(
        "NDIS Executive Exception Action Plan",
        action_plan,
        ["status", "due_date"],
    )
    new_status = current_status
    if current_status not in ["Completed", "Cancelled", "Escalated"]:
        if int(totals.overdue_steps or 0) or (due_date and getdate(due_date) < getdate(today())):
            new_status = "Overdue"
        elif int(totals.open_steps or 0):
            new_status = "In Progress"
    frappe.db.set_value(
        "NDIS Executive Exception Action Plan",
        action_plan,
        {
            "total_steps": int(totals.total_steps or 0),
            "completed_steps": int(totals.completed_steps or 0),
            "open_steps": int(totals.open_steps or 0),
            "overdue_steps": int(totals.overdue_steps or 0),
            "status": new_status,
        },
        update_modified=False,
    )
    return {
        "action_plan": action_plan,
        "total_steps": int(totals.total_steps or 0),
        "completed_steps": int(totals.completed_steps or 0),
        "open_steps": int(totals.open_steps or 0),
        "overdue_steps": int(totals.overdue_steps or 0),
        "status": new_status,
    }


@frappe.whitelist()
def daily_action_plan_overdue_monitor_job():
    previous_user = frappe.session.user
    try:
        frappe.set_user("Administrator")
        plans = frappe.get_all(
            "NDIS Executive Exception Action Plan",
            filters={"status": ["not in", ["Completed", "Cancelled"]]},
            fields=["name"],
        )
        updated = 0
        for plan in plans:
            result = refresh_action_plan_summary(plan.name)
            if result.get("status") == "Overdue":
                updated += 1
        frappe.db.commit()
        return {
            "checked": len(plans),
            "marked_overdue_or_still_overdue": updated,
            "note": "Overdue monitor updates internal action plan status only. No emails or accounting movement created.",
        }
    finally:
        frappe.set_user(previous_user)


@frappe.whitelist()
def quick_action_plan_summary(limit=20):
    limit = int(limit or 20)
    plans = frappe.get_all(
        "NDIS Executive Exception Action Plan",
        fields=[
            "name",
            "action_plan_id",
            "status",
            "priority",
            "exception_alert",
            "rule_name",
            "severity",
            "assigned_to",
            "due_date",
            "escalation_level",
            "total_steps",
            "completed_steps",
            "open_steps",
            "overdue_steps",
            "management_sign_off",
        ],
        order_by="modified desc",
        limit=limit,
    )
    steps = frappe.get_all(
        "NDIS Executive Exception Action Step",
        fields=["name", "action_plan", "status", "priority", "step_no", "action_title", "assigned_to", "due_date", "completed_on", "completed_by"],
        order_by="modified desc",
        limit=limit,
    )
    summary = frappe.db.sql(
        """
        SELECT status, priority, COUNT(*) AS count
        FROM `tabNDIS Executive Exception Action Plan`
        GROUP BY status, priority
        ORDER BY status, priority
        """,
        as_dict=True,
    )
    return {
        "plans": plans,
        "steps": steps,
        "summary": summary,
        "note": "Action plan summary only. No finance, payroll, accounting, STP, ABA, email, or payment movement created.",
    }


def execute_action_plan_register_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions, params = action_plan_filter_conditions(filters)
    columns = register_columns()
    data = frappe.db.sql(
        f"""
        SELECT
            p.name AS action_plan,
            p.action_plan_id,
            p.status,
            p.priority,
            p.severity,
            p.exception_alert,
            p.rule_name,
            p.assigned_to,
            p.due_date,
            p.escalation_level,
            p.total_steps,
            p.completed_steps,
            p.open_steps,
            p.overdue_steps,
            p.management_sign_off,
            p.action_title,
            p.recommendation
        FROM `tabNDIS Executive Exception Action Plan` p
        {build_where(conditions)}
        ORDER BY
            CASE p.priority WHEN 'Critical' THEN 1 WHEN 'High' THEN 2 WHEN 'Medium' THEN 3 WHEN 'Low' THEN 4 ELSE 5 END,
            p.due_date ASC,
            p.creation DESC
        """,
        params,
        as_dict=True,
    )
    return build_action_plan_report_response(columns, data)


def action_plan_filter_conditions(filters):
    conditions = []
    params = {}
    for key in ["status", "priority", "severity", "assigned_to", "exception_alert"]:
        value = filters.get(key)
        if value:
            conditions.append(f"p.{key} = %({key})s")
            params[key] = value
    if filters.get("from_date"):
        conditions.append("p.due_date >= %(from_date)s")
        params["from_date"] = filters.from_date
    if filters.get("to_date"):
        conditions.append("p.due_date <= %(to_date)s")
        params["to_date"] = filters.to_date
    return conditions, params


def register_columns():
    return [
        {"fieldname": "action_plan", "label": _("Action Plan"), "fieldtype": "Link", "options": "NDIS Executive Exception Action Plan", "width": 210},
        {"fieldname": "action_plan_id", "label": _("Action Plan ID"), "fieldtype": "Data", "width": 280},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "priority", "label": _("Priority"), "fieldtype": "Data", "width": 110},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 110},
        {"fieldname": "exception_alert", "label": _("Exception Alert"), "fieldtype": "Link", "options": "NDIS Executive Exception Alert", "width": 210},
        {"fieldname": "rule_name", "label": _("Rule Name"), "fieldtype": "Data", "width": 260},
        {"fieldname": "assigned_to", "label": _("Assigned To"), "fieldtype": "Link", "options": "User", "width": 180},
        {"fieldname": "due_date", "label": _("Due Date"), "fieldtype": "Date", "width": 120},
        {"fieldname": "escalation_level", "label": _("Escalation"), "fieldtype": "Data", "width": 120},
        {"fieldname": "total_steps", "label": _("Steps"), "fieldtype": "Int", "width": 80},
        {"fieldname": "completed_steps", "label": _("Completed"), "fieldtype": "Int", "width": 100},
        {"fieldname": "open_steps", "label": _("Open"), "fieldtype": "Int", "width": 80},
        {"fieldname": "overdue_steps", "label": _("Overdue"), "fieldtype": "Int", "width": 90},
        {"fieldname": "management_sign_off", "label": _("Signed Off"), "fieldtype": "Check", "width": 100},
        {"fieldname": "action_title", "label": _("Action Title"), "fieldtype": "Data", "width": 280},
        {"fieldname": "recommendation", "label": _("Recommendation"), "fieldtype": "Small Text", "width": 420},
    ]


def execute_action_plan_overdue_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = ["p.status NOT IN ('Completed', 'Cancelled')", "(p.due_date < CURDATE() OR p.overdue_steps > 0)"]
    params = {}
    for key in ["assigned_to", "priority", "severity"]:
        value = filters.get(key)
        if value:
            conditions.append(f"p.{key} = %({key})s")
            params[key] = value
    columns = [
        {"fieldname": "action_plan", "label": _("Action Plan"), "fieldtype": "Link", "options": "NDIS Executive Exception Action Plan", "width": 210},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "priority", "label": _("Priority"), "fieldtype": "Data", "width": 110},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 110},
        {"fieldname": "rule_name", "label": _("Rule Name"), "fieldtype": "Data", "width": 260},
        {"fieldname": "assigned_to", "label": _("Assigned To"), "fieldtype": "Link", "options": "User", "width": 180},
        {"fieldname": "due_date", "label": _("Due Date"), "fieldtype": "Date", "width": 120},
        {"fieldname": "days_overdue", "label": _("Days Overdue"), "fieldtype": "Int", "width": 120},
        {"fieldname": "overdue_steps", "label": _("Overdue Steps"), "fieldtype": "Int", "width": 120},
        {"fieldname": "open_steps", "label": _("Open Steps"), "fieldtype": "Int", "width": 100},
        {"fieldname": "escalation_level", "label": _("Escalation"), "fieldtype": "Data", "width": 120},
        {"fieldname": "action_title", "label": _("Action Title"), "fieldtype": "Data", "width": 300},
        {"fieldname": "recommendation", "label": _("Recommendation"), "fieldtype": "Small Text", "width": 420},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            p.name AS action_plan,
            p.status,
            p.priority,
            p.severity,
            p.rule_name,
            p.assigned_to,
            p.due_date,
            CASE WHEN p.due_date IS NOT NULL AND p.due_date < CURDATE() THEN DATEDIFF(CURDATE(), p.due_date) ELSE 0 END AS days_overdue,
            p.overdue_steps,
            p.open_steps,
            p.escalation_level,
            p.action_title,
            p.recommendation
        FROM `tabNDIS Executive Exception Action Plan` p
        WHERE {" AND ".join(conditions)}
        ORDER BY days_overdue DESC, p.priority ASC, p.due_date ASC
        """,
        params,
        as_dict=True,
    )
    chart_map = {}
    for row in data:
        chart_map[row.priority or "Unassigned"] = chart_map.get(row.priority or "Unassigned", 0) + 1
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Overdue Plans", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Red" if data else "Green", "label": _("Overdue Plans"), "datatype": "Int"},
        {"value": sum(int(row.overdue_steps or 0) for row in data), "indicator": "Red" if data else "Green", "label": _("Overdue Steps"), "datatype": "Int"},
        {"value": len([row for row in data if row.priority == "Critical"]), "indicator": "Red", "label": _("Critical"), "datatype": "Int"},
        {"value": len([row for row in data if row.priority == "High"]), "indicator": "Orange", "label": _("High"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def build_action_plan_report_response(columns, data):
    chart_map = {}
    for row in data:
        chart_map[row.status or "Unknown"] = chart_map.get(row.status or "Unknown", 0) + 1
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Action Plans", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Action Plans"), "datatype": "Int"},
        {"value": len([row for row in data if row.status in ["In Progress", "Overdue", "Escalated"]]), "indicator": "Orange", "label": _("Open Plans"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Overdue"]), "indicator": "Red", "label": _("Overdue"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Completed"]), "indicator": "Green", "label": _("Completed"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
