import json
import os

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


PHASE1Y_DOCTYPES = [
    "NDIS Executive Exception Action Plan",
    "NDIS Executive Exception Action Step",
]

REPORTS = [
    {
        "report_name": "NDIS Executive Action Plan Register Report",
        "ref_doctype": "NDIS Executive Exception Action Plan",
    },
    {
        "report_name": "NDIS Executive Action Plan Overdue Report",
        "ref_doctype": "NDIS Executive Exception Action Plan",
    },
]

REPORT_ROLES = [
    "System Manager",
    "NDIS CFO",
    "NDIS Finance Manager",
    "NDIS Finance Officer",
    "NDIS Finance Read Only",
]

DOC_PERM_MATRIX = {
    "NDIS Executive Exception Action Plan": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Automation Manager": "read_report_export",
        "NDIS Finance Officer": "create_write_read_report",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Executive Exception Action Step": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Automation Manager": "read_report_export",
        "NDIS Finance Officer": "create_write_read_report",
        "NDIS Finance Read Only": "read_report",
    },
}

WORKSPACE_NAME = "NDIS Finance"

WORKSPACE_SHORTCUTS = [
    {"label": "Executive Action Plans", "type": "DocType", "link_to": "NDIS Executive Exception Action Plan"},
    {"label": "Executive Action Steps", "type": "DocType", "link_to": "NDIS Executive Exception Action Step"},
    {"label": "Executive Action Plan Register", "type": "Report", "link_to": "NDIS Executive Action Plan Register Report"},
    {"label": "Overdue Executive Actions", "type": "Report", "link_to": "NDIS Executive Action Plan Overdue Report"},
]

REPORT_FILE_MAP = {
    "NDIS Executive Action Plan Register Report": "ndis_executive_action_plan_register_report",
    "NDIS Executive Action Plan Overdue Report": "ndis_executive_action_plan_overdue_report",
}

DAILY_JOB = "ndis_finance.services.executive_action_plans.daily_action_plan_overdue_monitor_job"


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_action_plan_doctype()
    create_action_step_doctype()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Executive Exception Rule",
        "NDIS Executive Exception Alert",
        "NDIS Executive Dashboard Snapshot",
        "Report",
        "Workspace",
    ]
    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]
    if missing:
        frappe.throw(_("Phase 1Y requires Phase 1X. Missing DocTypes: {0}").format(", ".join(missing)))


def create_action_plan_doctype():
    _create_doctype(
        name="NDIS Executive Exception Action Plan",
        autoname="field:action_plan_id",
        title_field="action_plan_id",
        fields=[
            {"fieldname": "action_plan_id", "label": "Action Plan ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nIn Progress\nOverdue\nEscalated\nCompleted\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "priority", "label": "Priority", "fieldtype": "Select", "options": "\nLow\nMedium\nHigh\nCritical", "default": "Medium", "in_list_view": 1},
            {"fieldname": "exception_section", "label": "Exception Source", "fieldtype": "Section Break"},
            {"fieldname": "exception_alert", "label": "Exception Alert", "fieldtype": "Link", "options": "NDIS Executive Exception Alert", "reqd": 1, "in_list_view": 1},
            {"fieldname": "exception_rule", "label": "Exception Rule", "fieldtype": "Link", "options": "NDIS Executive Exception Rule"},
            {"fieldname": "rule_name", "label": "Rule Name", "fieldtype": "Data"},
            {"fieldname": "severity", "label": "Severity", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "snapshot", "label": "Snapshot", "fieldtype": "Link", "options": "NDIS Executive Dashboard Snapshot"},
            {"fieldname": "snapshot_date", "label": "Snapshot Date", "fieldtype": "Date"},
            {"fieldname": "metric_key", "label": "Metric Key", "fieldtype": "Data"},
            {"fieldname": "metric_value", "label": "Metric Value", "fieldtype": "Float"},
            {"fieldname": "threshold_value", "label": "Threshold Value", "fieldtype": "Float"},
            {"fieldname": "plan_section", "label": "Action Plan", "fieldtype": "Section Break"},
            {"fieldname": "action_title", "label": "Action Title", "fieldtype": "Data", "reqd": 1, "in_list_view": 1},
            {"fieldname": "assigned_to", "label": "Assigned To", "fieldtype": "Link", "options": "User", "in_list_view": 1},
            {"fieldname": "due_date", "label": "Due Date", "fieldtype": "Date", "in_list_view": 1},
            {"fieldname": "escalation_level", "label": "Escalation Level", "fieldtype": "Select", "options": "\nNone\nLevel 1\nLevel 2\nLevel 3\nExecutive", "default": "None"},
            {"fieldname": "action_summary", "label": "Action Summary", "fieldtype": "Small Text"},
            {"fieldname": "recommendation", "label": "Recommendation", "fieldtype": "Small Text"},
            {"fieldname": "step_section", "label": "Step Summary", "fieldtype": "Section Break"},
            {"fieldname": "total_steps", "label": "Total Steps", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "completed_steps", "label": "Completed Steps", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "open_steps", "label": "Open Steps", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "overdue_steps", "label": "Overdue Steps", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "resolution_section", "label": "Resolution / Sign-off", "fieldtype": "Section Break"},
            {"fieldname": "resolution_summary", "label": "Resolution Summary", "fieldtype": "Small Text"},
            {"fieldname": "resolution_evidence", "label": "Resolution Evidence", "fieldtype": "Attach"},
            {"fieldname": "management_sign_off", "label": "Management Sign-off", "fieldtype": "Check", "default": "0"},
            {"fieldname": "signed_off_by", "label": "Signed Off By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "signed_off_on", "label": "Signed Off On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "audit_section", "label": "Audit", "fieldtype": "Section Break"},
            {"fieldname": "created_on", "label": "Created On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "created_by_user", "label": "Created By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "started_on", "label": "Started On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "completed_on", "label": "Completed On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "completed_by", "label": "Completed By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "cancelled_on", "label": "Cancelled On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "cancelled_by", "label": "Cancelled By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "warning_log", "label": "Warning Log", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
        ],
    )


def create_action_step_doctype():
    _create_doctype(
        name="NDIS Executive Exception Action Step",
        autoname="hash",
        title_field="action_title",
        fields=[
            {"fieldname": "action_plan", "label": "Action Plan", "fieldtype": "Link", "options": "NDIS Executive Exception Action Plan", "reqd": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nOpen\nIn Progress\nCompleted\nOverdue\nCancelled", "default": "Open", "in_list_view": 1},
            {"fieldname": "priority", "label": "Priority", "fieldtype": "Data"},
            {"fieldname": "step_no", "label": "Step No", "fieldtype": "Int", "in_list_view": 1},
            {"fieldname": "action_title", "label": "Action Title", "fieldtype": "Data", "reqd": 1, "in_list_view": 1},
            {"fieldname": "assigned_to", "label": "Assigned To", "fieldtype": "Link", "options": "User", "in_list_view": 1},
            {"fieldname": "due_date", "label": "Due Date", "fieldtype": "Date", "in_list_view": 1},
            {"fieldname": "detail_section", "label": "Details", "fieldtype": "Section Break"},
            {"fieldname": "action_detail", "label": "Action Detail", "fieldtype": "Small Text"},
            {"fieldname": "follow_up_note", "label": "Follow-up Note", "fieldtype": "Small Text"},
            {"fieldname": "completion_section", "label": "Completion", "fieldtype": "Section Break"},
            {"fieldname": "completed_on", "label": "Completed On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "completed_by", "label": "Completed By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "completion_note", "label": "Completion Note", "fieldtype": "Small Text"},
            {"fieldname": "evidence_attachment", "label": "Evidence Attachment", "fieldtype": "Attach"},
            {"fieldname": "cancelled_on", "label": "Cancelled On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "cancelled_by", "label": "Cancelled By", "fieldtype": "Link", "options": "User", "read_only": 1},
        ],
    )


def create_reports():
    for report in REPORTS:
        ensure_script_report(report["report_name"], report["ref_doctype"])


def ensure_script_report(report_name, ref_doctype):
    doc = frappe.get_doc("Report", report_name) if frappe.db.exists("Report", report_name) else frappe.new_doc("Report")
    doc.report_name = report_name
    doc.ref_doctype = ref_doctype
    doc.report_type = "Script Report"
    doc.module = MODULE
    doc.is_standard = "Yes"
    doc.disabled = 0
    doc.roles = []
    for role in REPORT_ROLES:
        if frappe.db.exists("Role", role):
            doc.append("roles", {"role": role})
    doc.save(ignore_permissions=True)


def harden_permissions():
    for doctype, role_map in DOC_PERM_MATRIX.items():
        if not frappe.db.exists("DocType", doctype):
            continue
        doc = frappe.get_doc("DocType", doctype)
        doc.permissions = []
        for role, profile in role_map.items():
            if frappe.db.exists("Role", role):
                doc.append("permissions", build_perm_row(role, profile))
        doc.save(ignore_permissions=True)
        frappe.clear_cache(doctype=doctype)


def build_perm_row(role, profile):
    base = {
        "role": role,
        "permlevel": 0,
        "read": 0,
        "write": 0,
        "create": 0,
        "delete": 0,
        "submit": 0,
        "cancel": 0,
        "amend": 0,
        "report": 0,
        "export": 0,
        "import": 0,
        "share": 0,
        "print": 0,
        "email": 0,
    }
    if profile == "full":
        base.update({"read": 1, "write": 1, "create": 1, "delete": 1, "report": 1, "export": 1, "share": 1, "print": 1, "email": 1})
    elif profile == "full_no_delete":
        base.update({"read": 1, "write": 1, "create": 1, "delete": 0, "report": 1, "export": 1, "share": 1, "print": 1, "email": 1})
    elif profile == "create_write_read_report":
        base.update({"read": 1, "write": 1, "create": 1, "delete": 0, "report": 1, "export": 1, "print": 1, "email": 1})
    elif profile == "read_report_export":
        base.update({"read": 1, "report": 1, "export": 1, "print": 1})
    elif profile == "read_report":
        base.update({"read": 1, "report": 1})
    else:
        frappe.throw(_("Unknown permission profile: {0}").format(profile))
    return base


def add_workspace_shortcuts():
    ws_name = frappe.db.exists("Workspace", WORKSPACE_NAME) or frappe.db.exists("Workspace", {"label": WORKSPACE_NAME})
    if not ws_name:
        return
    ws = frappe.get_doc("Workspace", ws_name)
    add_shortcuts_to_content_json(ws)
    add_shortcuts_to_child_table(ws)
    ws.save(ignore_permissions=True)


def add_shortcuts_to_content_json(ws):
    if not ws.meta.has_field("content"):
        return
    try:
        content = json.loads(ws.content or "[]")
    except Exception:
        content = []
    text_blob = json.dumps(content)
    if "Executive Action Plans" not in text_blob:
        content.append({"id": "ndis_executive_action_plans_heading", "type": "header", "data": {"text": "Executive Action Plans", "col": 12}})
    for shortcut in WORKSPACE_SHORTCUTS:
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            continue
        content.append({"id": frappe.scrub(shortcut["label"]), "type": "shortcut", "data": {"label": shortcut["label"], "link_to": shortcut["link_to"], "type": shortcut["type"], "col": 3}})
    ws.content = json.dumps(content)


def add_shortcuts_to_child_table(ws):
    for fieldname in ["shortcuts", "links"]:
        if not ws.meta.has_field(fieldname):
            continue
        existing_blob = " ".join(
            f"{getattr(row, 'label', '')} {getattr(row, 'link_to', '')}" for row in (getattr(ws, fieldname, []) or [])
        )
        for shortcut in WORKSPACE_SHORTCUTS:
            if shortcut["label"] in existing_blob or shortcut["link_to"] in existing_blob:
                continue
            row = ws.append(fieldname, {})
            set_child_value(row, "label", shortcut["label"])
            set_child_value(row, "link_to", shortcut["link_to"])
            if fieldname == "shortcuts":
                set_child_value(row, "type", shortcut["type"])
            else:
                set_child_value(row, "type", "Link")
            set_child_value(row, "link_type", shortcut["type"])
            set_child_value(row, "open_in_new_tab", 0)
            if shortcut["type"] == "Report":
                set_child_value(row, "is_query_report", 1)
                set_child_value(row, "report_ref_doctype", report_ref_doctype(shortcut["link_to"]))


def report_ref_doctype(report_name):
    for report in REPORTS:
        if report["report_name"] == report_name:
            return report["ref_doctype"]
    return None


def set_child_value(row, fieldname, value):
    if row.meta.has_field(fieldname):
        setattr(row, fieldname, value)


@frappe.whitelist()
def health_check():
    hooks = frappe.get_hooks()
    doctype_js = hooks.get("doctype_js", {})
    doctype_list_js = hooks.get("doctype_list_js", {})
    scheduler_events = hooks.get("scheduler_events", {})
    daily_jobs = scheduler_events.get("daily", []) if isinstance(scheduler_events, dict) else []
    return {
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE1Y_DOCTYPES},
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "permissions": {
            dt: frappe.get_all(
                "DocPerm",
                filters={"parent": dt},
                fields=["role", "read", "write", "create", "delete", "report", "export"],
                order_by="role asc",
            )
            for dt in PHASE1Y_DOCTYPES
        },
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "manage_executive_action_plan": permission_matrix().get("manage_executive_action_plan"),
            "update_executive_action_plan": permission_matrix().get("update_executive_action_plan"),
            "complete_executive_action_plan": permission_matrix().get("complete_executive_action_plan"),
            "cancel_executive_action_plan": permission_matrix().get("cancel_executive_action_plan"),
        },
        "js_hooks": {dt: dt in doctype_js for dt in PHASE1Y_DOCTYPES},
        "list_js_hooks": {dt: dt in doctype_list_js for dt in PHASE1Y_DOCTYPES},
        "daily_action_plan_job_registered": DAILY_JOB in daily_jobs,
        "report_files": check_report_files(),
    }


def can_import_service():
    try:
        from ndis_finance.services.executive_action_plans import quick_action_plan_summary

        return callable(quick_action_plan_summary)
    except Exception:
        return False


def check_workspace_shortcuts():
    ws_name = frappe.db.exists("Workspace", WORKSPACE_NAME) or frappe.db.exists("Workspace", {"label": WORKSPACE_NAME})
    result = {shortcut["label"]: False for shortcut in WORKSPACE_SHORTCUTS}
    if not ws_name:
        return result
    ws = frappe.get_doc("Workspace", ws_name)
    text_blob = getattr(ws, "content", None) or ""
    for fieldname in ["shortcuts", "links"]:
        if ws.meta.has_field(fieldname):
            for row in getattr(ws, fieldname, []) or []:
                text_blob += " " + str(getattr(row, "label", "")) + " " + str(getattr(row, "link_to", ""))
    for shortcut in WORKSPACE_SHORTCUTS:
        result[shortcut["label"]] = shortcut["label"] in text_blob or shortcut["link_to"] in text_blob
    return result


def check_report_files():
    app_path = frappe.get_app_path("ndis_finance")
    result = {}
    for report_name, folder in REPORT_FILE_MAP.items():
        report_dir = os.path.join(app_path, "ndis_finance", "report", folder)
        result[report_name] = {
            "python": os.path.exists(os.path.join(report_dir, f"{folder}.py")),
            "javascript": os.path.exists(os.path.join(report_dir, f"{folder}.js")),
            "init": os.path.exists(os.path.join(report_dir, "__init__.py")),
        }
    return result
