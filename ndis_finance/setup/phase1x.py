import json
import os

import frappe
from frappe import _

from ndis_finance.services.permissions import permission_matrix
from ndis_finance.setup.install import MODULE, _create_doctype


PHASE1X_DOCTYPES = [
    "NDIS Executive Exception Rule",
    "NDIS Executive Exception Alert",
]

REPORTS = [
    {
        "report_name": "NDIS Executive Exception Register Report",
        "ref_doctype": "NDIS Executive Exception Alert",
    },
    {
        "report_name": "NDIS Executive Exception Rule Status Report",
        "ref_doctype": "NDIS Executive Exception Rule",
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
    "NDIS Executive Exception Rule": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Automation Manager": "read_report_export",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Executive Exception Alert": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Automation Manager": "read_report_export",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
}

WORKSPACE_NAME = "NDIS Finance"

WORKSPACE_SHORTCUTS = [
    {"label": "Executive Exception Rules", "type": "DocType", "link_to": "NDIS Executive Exception Rule"},
    {"label": "Executive Exception Alerts", "type": "DocType", "link_to": "NDIS Executive Exception Alert"},
    {"label": "Executive Exception Register", "type": "Report", "link_to": "NDIS Executive Exception Register Report"},
    {"label": "Executive Rule Status", "type": "Report", "link_to": "NDIS Executive Exception Rule Status Report"},
]

REPORT_FILE_MAP = {
    "NDIS Executive Exception Register Report": "ndis_executive_exception_register_report",
    "NDIS Executive Exception Rule Status Report": "ndis_executive_exception_rule_status_report",
}

DAILY_JOB = "ndis_finance.services.executive_exceptions.daily_executive_exception_evaluation_job"

DEFAULT_RULES = [
    {
        "rule_id": "NDIS-EXEC-RULE-MARGIN-PERCENT-LOW",
        "rule_name": "Estimated Margin % below 10%",
        "metric_key": "estimated_margin_percent",
        "operator": "<",
        "threshold_value": 10,
        "severity": "High",
        "description": "Flags when estimated margin percentage drops below 10%.",
        "recommendation": "Review revenue realisation, payroll cost ratio, non-payroll costs, leakage and recovery items.",
    },
    {
        "rule_id": "NDIS-EXEC-RULE-NEGATIVE-MARGIN",
        "rule_name": "Estimated Margin is negative",
        "metric_key": "estimated_margin",
        "operator": "<",
        "threshold_value": 0,
        "severity": "Critical",
        "description": "Flags when paid revenue less allocated costs is below zero.",
        "recommendation": "Review house/participant profitability, payroll allocations, leakage, and unclaimable/non-billable activity.",
    },
    {
        "rule_id": "NDIS-EXEC-RULE-PAYROLL-RATIO-HIGH",
        "rule_name": "Payroll cost ratio above 75%",
        "metric_key": "payroll_cost_ratio",
        "operator": ">",
        "threshold_value": 75,
        "severity": "High",
        "description": "Flags when payroll cost consumes more than 75% of paid revenue.",
        "recommendation": "Review roster efficiency, SCHADS cost mix, SIL ratios, overtime, broken shifts and non-billable payroll cost.",
    },
    {
        "rule_id": "NDIS-EXEC-RULE-SHORTFALL-RATIO-HIGH",
        "rule_name": "Shortfall ratio above 5%",
        "metric_key": "shortfall_ratio",
        "operator": ">",
        "threshold_value": 5,
        "severity": "Medium",
        "description": "Flags when claim shortfalls exceed 5% of gross claim value.",
        "recommendation": "Review claim rejection reasons, pricing, service booking controls and remittance exceptions.",
    },
    {
        "rule_id": "NDIS-EXEC-RULE-OPEN-LEAKAGE",
        "rule_name": "Open leakage above $1,000",
        "metric_key": "open_leakage",
        "operator": ">",
        "threshold_value": 1000,
        "severity": "High",
        "description": "Flags when open funding leakage exceeds $1,000.",
        "recommendation": "Prioritise high-severity leakage records and recovery actions.",
    },
    {
        "rule_id": "NDIS-EXEC-RULE-OPEN-RECOVERY",
        "rule_name": "Open recovery above $1,000",
        "metric_key": "open_recovery",
        "operator": ">",
        "threshold_value": 1000,
        "severity": "Medium",
        "description": "Flags when open recovery pipeline exceeds $1,000.",
        "recommendation": "Review overdue recovery cases, escalation candidates and approved drafts not sent.",
    },
    {
        "rule_id": "NDIS-EXEC-RULE-UNMAPPED-PAYROLL",
        "rule_name": "Unmapped payroll lines above zero",
        "metric_key": "unmapped_payroll_lines",
        "operator": ">",
        "threshold_value": 0,
        "severity": "High",
        "description": "Flags payroll rows that could not be mapped to NDIS house/costing records.",
        "recommendation": "Update Employee NDIS payroll costing fields and re-run payroll cost import if required.",
    },
    {
        "rule_id": "NDIS-EXEC-RULE-FAILED-AUTOMATION",
        "rule_name": "Failed automation runs above zero",
        "metric_key": "failed_automation_runs_7_days",
        "operator": ">",
        "threshold_value": 0,
        "severity": "High",
        "description": "Flags failed recovery automation runs in the last 7 days.",
        "recommendation": "Review automation logs and scheduler health.",
    },
    {
        "rule_id": "NDIS-EXEC-RULE-APPROVED-DRAFTS-NOT-SENT",
        "rule_name": "Approved drafts not sent above zero",
        "metric_key": "approved_drafts_not_sent",
        "operator": ">",
        "threshold_value": 0,
        "severity": "Medium",
        "description": "Flags approved recovery email drafts that have not been manually marked sent.",
        "recommendation": "Review approved drafts and complete manual send/mark-sent workflow.",
    },
    {
        "rule_id": "NDIS-EXEC-RULE-OVERDUE-RECOVERY",
        "rule_name": "Overdue recovery cases above zero",
        "metric_key": "overdue_recovery_cases",
        "operator": ">",
        "threshold_value": 0,
        "severity": "Medium",
        "description": "Flags overdue recovery follow-up cases.",
        "recommendation": "Review recovery ageing and follow-up overdue cases.",
    },
    {
        "rule_id": "NDIS-EXEC-RULE-ESCALATION-CANDIDATES",
        "rule_name": "Escalation candidates above zero",
        "metric_key": "escalation_candidates",
        "operator": ">",
        "threshold_value": 0,
        "severity": "Medium",
        "description": "Flags recovery cases that may need escalation.",
        "recommendation": "Review recovery automation exception report and escalate where appropriate.",
    },
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_exception_rule_doctype()
    create_exception_alert_doctype()
    create_reports()
    seed_default_rules()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Executive Dashboard Snapshot",
        "NDIS Executive Dashboard Snapshot Metric",
        "NDIS Payroll Cost Import",
        "NDIS Cost Allocation Entry",
        "NDIS Recovery Automation Log",
        "Report",
        "Workspace",
    ]
    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]
    if missing:
        frappe.throw(_("Phase 1X requires previous phases. Missing DocTypes: {0}").format(", ".join(missing)))


def create_exception_rule_doctype():
    _create_doctype(
        name="NDIS Executive Exception Rule",
        autoname="field:rule_id",
        title_field="rule_name",
        fields=[
            {"fieldname": "rule_id", "label": "Rule ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "rule_name", "label": "Rule Name", "fieldtype": "Data", "reqd": 1, "in_list_view": 1},
            {"fieldname": "active", "label": "Active", "fieldtype": "Check", "default": "1", "in_list_view": 1},
            {"fieldname": "severity", "label": "Severity", "fieldtype": "Select", "options": "\nLow\nMedium\nHigh\nCritical", "default": "Medium", "in_list_view": 1},
            {"fieldname": "rule_section", "label": "Rule Logic", "fieldtype": "Section Break"},
            {"fieldname": "metric_key", "label": "Metric Key", "fieldtype": "Select", "options": "\nestimated_margin_percent\nestimated_margin\npayroll_cost_ratio\nshortfall_ratio\nopen_leakage\nopen_recovery\nunmapped_payroll_lines\nfailed_automation_runs_7_days\napproved_drafts_not_sent\nescalation_candidates\noverdue_recovery_cases\npaid_revenue\ntotal_allocated_cost\npayroll_cost\nnon_payroll_cost", "reqd": 1, "in_list_view": 1},
            {"fieldname": "operator", "label": "Operator", "fieldtype": "Select", "options": "\n<\n<=\n>\n>=\n==\n!=", "default": ">", "reqd": 1},
            {"fieldname": "threshold_value", "label": "Threshold Value", "fieldtype": "Float", "reqd": 1, "in_list_view": 1},
            {"fieldname": "duplicate_control", "label": "Duplicate Control", "fieldtype": "Select", "options": "\nOne Open Alert per Rule\nOne Alert per Snapshot\nAllow Multiple", "default": "One Open Alert per Rule"},
            {"fieldname": "description", "label": "Description", "fieldtype": "Small Text"},
            {"fieldname": "recommendation", "label": "Recommendation", "fieldtype": "Small Text"},
            {"fieldname": "status_section", "label": "Status", "fieldtype": "Section Break"},
            {"fieldname": "last_evaluated_on", "label": "Last Evaluated On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "last_metric_value", "label": "Last Metric Value", "fieldtype": "Float", "read_only": 1},
            {"fieldname": "last_triggered_on", "label": "Last Triggered On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "open_alert_count", "label": "Open Alert Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
        ],
    )


def create_exception_alert_doctype():
    _create_doctype(
        name="NDIS Executive Exception Alert",
        autoname="field:alert_id",
        title_field="alert_id",
        fields=[
            {"fieldname": "alert_id", "label": "Alert ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nOpen\nIn Review\nResolved\nCancelled", "default": "Open", "in_list_view": 1},
            {"fieldname": "severity", "label": "Severity", "fieldtype": "Select", "options": "\nLow\nMedium\nHigh\nCritical", "in_list_view": 1},
            {"fieldname": "rule", "label": "Rule", "fieldtype": "Link", "options": "NDIS Executive Exception Rule", "reqd": 1, "in_list_view": 1},
            {"fieldname": "rule_name", "label": "Rule Name", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "snapshot_section", "label": "Snapshot / Source", "fieldtype": "Section Break"},
            {"fieldname": "source", "label": "Source", "fieldtype": "Select", "options": "\nLatest Snapshot\nSelected Snapshot\nLive Dashboard", "default": "Latest Snapshot"},
            {"fieldname": "snapshot", "label": "Snapshot", "fieldtype": "Link", "options": "NDIS Executive Dashboard Snapshot", "in_list_view": 1},
            {"fieldname": "snapshot_date", "label": "Snapshot Date", "fieldtype": "Date", "in_list_view": 1},
            {"fieldname": "metric_section", "label": "Metric", "fieldtype": "Section Break"},
            {"fieldname": "metric_key", "label": "Metric Key", "fieldtype": "Data"},
            {"fieldname": "metric_label", "label": "Metric Label", "fieldtype": "Data"},
            {"fieldname": "metric_value", "label": "Metric Value", "fieldtype": "Float", "in_list_view": 1},
            {"fieldname": "operator", "label": "Operator", "fieldtype": "Data"},
            {"fieldname": "threshold_value", "label": "Threshold Value", "fieldtype": "Float", "in_list_view": 1},
            {"fieldname": "variance_value", "label": "Variance Value", "fieldtype": "Float", "read_only": 1},
            {"fieldname": "message", "label": "Message", "fieldtype": "Small Text"},
            {"fieldname": "recommendation", "label": "Recommendation", "fieldtype": "Small Text"},
            {"fieldname": "workflow_section", "label": "Workflow", "fieldtype": "Section Break"},
            {"fieldname": "created_on", "label": "Created On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "created_by_user", "label": "Created By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "reviewed_on", "label": "Reviewed On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "reviewed_by", "label": "Reviewed By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "resolved_on", "label": "Resolved On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "resolved_by", "label": "Resolved By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "resolution_note", "label": "Resolution Note", "fieldtype": "Small Text"},
        ],
    )


def create_reports():
    for report in REPORTS:
        ensure_script_report(report["report_name"], report["ref_doctype"])


def ensure_script_report(report_name, ref_doctype):
    existing = frappe.db.exists("Report", report_name)
    doc = frappe.get_doc("Report", existing) if existing else frappe.new_doc("Report")
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


def seed_default_rules():
    for rule in DEFAULT_RULES:
        existing = frappe.db.exists("NDIS Executive Exception Rule", rule["rule_id"])
        doc = frappe.get_doc("NDIS Executive Exception Rule", existing) if existing else frappe.new_doc("NDIS Executive Exception Rule")
        doc.rule_id = rule["rule_id"]
        doc.rule_name = rule["rule_name"]
        doc.active = 1
        doc.metric_key = rule["metric_key"]
        doc.operator = rule["operator"]
        doc.threshold_value = rule["threshold_value"]
        doc.severity = rule["severity"]
        doc.duplicate_control = "One Open Alert per Rule"
        doc.description = rule["description"]
        doc.recommendation = rule["recommendation"]
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
        base.update({"read": 1, "write": 1, "create": 1, "report": 1, "export": 1, "share": 1, "print": 1, "email": 1})
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
    if "Executive Exceptions" not in text_blob:
        content.append({"id": "ndis_executive_exceptions_heading", "type": "header", "data": {"text": "Executive Exceptions", "col": 12}})
    for shortcut in WORKSPACE_SHORTCUTS:
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            continue
        content.append({"id": frappe.scrub(shortcut["label"]), "type": "shortcut", "data": {"label": shortcut["label"], "link_to": shortcut["link_to"], "type": shortcut["type"], "col": 3}})
    ws.content = json.dumps(content)


def add_shortcuts_to_child_table(ws):
    for fieldname in ["shortcuts", "links"]:
        if not ws.meta.has_field(fieldname):
            continue
        existing_blob = ""
        for row in getattr(ws, fieldname, []) or []:
            existing_blob += " " + str(getattr(row, "label", "")) + " " + str(getattr(row, "link_to", ""))
        for shortcut in WORKSPACE_SHORTCUTS:
            if shortcut["label"] in existing_blob or shortcut["link_to"] in existing_blob:
                continue
            row_type = shortcut["type"] if fieldname == "shortcuts" else "Link"
            row = ws.append(fieldname, {})
            set_child_value(row, "label", shortcut["label"])
            set_child_value(row, "link_to", shortcut["link_to"])
            set_child_value(row, "type", row_type)
            set_child_value(row, "link_type", shortcut["type"])
            set_child_value(row, "report_ref_doctype", report_ref_doctype(shortcut["link_to"]))
            set_child_value(row, "is_query_report", 1 if shortcut["type"] == "Report" else 0)
            set_child_value(row, "open_in_new_tab", 0)


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
    doctypes = {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE1X_DOCTYPES}
    reports = {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS}
    rules = {rule["rule_id"]: bool(frappe.db.exists("NDIS Executive Exception Rule", rule["rule_id"])) for rule in DEFAULT_RULES}
    permissions = {}
    for dt in PHASE1X_DOCTYPES:
        permissions[dt] = frappe.get_all("DocPerm", filters={"parent": dt}, fields=["role", "read", "write", "create", "delete", "report", "export"], order_by="role asc")
    hooks = frappe.get_hooks()
    doctype_js = hooks.get("doctype_js", {})
    doctype_list_js = hooks.get("doctype_list_js", {})
    scheduler_events = hooks.get("scheduler_events", {})
    daily_jobs = scheduler_events.get("daily", []) if isinstance(scheduler_events, dict) else []
    return {
        "doctypes": doctypes,
        "reports": reports,
        "default_rules": rules,
        "permissions": permissions,
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "manage_executive_exception_rule": permission_matrix().get("manage_executive_exception_rule"),
            "evaluate_executive_exceptions": permission_matrix().get("evaluate_executive_exceptions"),
            "resolve_executive_exception_alert": permission_matrix().get("resolve_executive_exception_alert"),
        },
        "js_hooks": {
            "NDIS Executive Exception Rule": "NDIS Executive Exception Rule" in doctype_js,
            "NDIS Executive Exception Alert": "NDIS Executive Exception Alert" in doctype_js,
        },
        "list_js_hooks": {
            "NDIS Executive Exception Rule": "NDIS Executive Exception Rule" in doctype_list_js,
            "NDIS Executive Exception Alert": "NDIS Executive Exception Alert" in doctype_list_js,
        },
        "daily_exception_job_registered": DAILY_JOB in daily_jobs,
        "report_files": report_files_exist(),
    }


def can_import_service():
    try:
        from ndis_finance.services.executive_exceptions import quick_executive_exception_summary

        return callable(quick_executive_exception_summary)
    except Exception:
        return False


def check_workspace_shortcuts():
    ws_name = frappe.db.exists("Workspace", WORKSPACE_NAME) or frappe.db.exists("Workspace", {"label": WORKSPACE_NAME})
    result = {shortcut["label"]: False for shortcut in WORKSPACE_SHORTCUTS}
    if not ws_name:
        return result
    ws = frappe.get_doc("Workspace", ws_name)
    text_blob = getattr(ws, "content", "") or ""
    for fieldname in ["shortcuts", "links"]:
        if ws.meta.has_field(fieldname):
            for row in getattr(ws, fieldname, []) or []:
                text_blob += " " + str(getattr(row, "label", "")) + " " + str(getattr(row, "link_to", ""))
    for shortcut in WORKSPACE_SHORTCUTS:
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            result[shortcut["label"]] = True
    return result


def report_files_exist():
    app_path = frappe.get_app_path("ndis_finance")
    base_path = os.path.join(app_path, "ndis_finance", "report")
    result = {}
    for report_name, folder in REPORT_FILE_MAP.items():
        report_path = os.path.join(base_path, folder)
        result[report_name] = {
            "python": os.path.exists(os.path.join(report_path, f"{folder}.py")),
            "javascript": os.path.exists(os.path.join(report_path, f"{folder}.js")),
            "init": os.path.exists(os.path.join(report_path, "__init__.py")),
        }
    return result
