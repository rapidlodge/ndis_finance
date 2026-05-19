import json
import os

import frappe
from frappe import _

from ndis_finance.services.permissions import permission_matrix
from ndis_finance.setup.install import MODULE, _create_doctype


PHASE1W_DOCTYPES = [
    "NDIS Executive Dashboard Snapshot",
    "NDIS Executive Dashboard Snapshot Metric",
]

REPORTS = [
    {
        "report_name": "NDIS Executive KPI Trend Report",
        "ref_doctype": "NDIS Executive Dashboard Snapshot",
    },
    {
        "report_name": "NDIS Executive Snapshot Detail Report",
        "ref_doctype": "NDIS Executive Dashboard Snapshot Metric",
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
    "NDIS Executive Dashboard Snapshot": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Automation Manager": "create_write_read_report",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Executive Dashboard Snapshot Metric": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Automation Manager": "create_write_read_report",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
}

WORKSPACE_NAME = "NDIS Finance"

WORKSPACE_SHORTCUTS = [
    {
        "label": "Executive Snapshots",
        "type": "DocType",
        "link_to": "NDIS Executive Dashboard Snapshot",
    },
    {
        "label": "Executive Snapshot Metrics",
        "type": "DocType",
        "link_to": "NDIS Executive Dashboard Snapshot Metric",
    },
    {
        "label": "Executive KPI Trends",
        "type": "Report",
        "link_to": "NDIS Executive KPI Trend Report",
    },
    {
        "label": "Executive Snapshot Detail",
        "type": "Report",
        "link_to": "NDIS Executive Snapshot Detail Report",
    },
]

REPORT_FILE_MAP = {
    "NDIS Executive KPI Trend Report": "ndis_executive_kpi_trend_report",
    "NDIS Executive Snapshot Detail Report": "ndis_executive_snapshot_detail_report",
}

DAILY_JOB = "ndis_finance.services.executive_snapshots.daily_executive_dashboard_snapshot_job"


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_snapshot_doctype()
    create_snapshot_metric_doctype()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Claim Line",
        "NDIS Funding Leakage Register",
        "NDIS Recovery Case",
        "NDIS Recovery Automation Log",
        "NDIS Payroll Cost Import",
        "NDIS Cost Pool",
        "NDIS Cost Allocation Entry",
        "Report",
        "Workspace",
    ]

    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]
    if missing:
        frappe.throw(
            _("Phase 1W requires previous phases. Missing DocTypes: {0}").format(
                ", ".join(missing)
            )
        )


def create_snapshot_doctype():
    _create_doctype(
        name="NDIS Executive Dashboard Snapshot",
        autoname="field:snapshot_id",
        title_field="snapshot_id",
        fields=[
            {"fieldname": "snapshot_id", "label": "Snapshot ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "snapshot_date", "label": "Snapshot Date", "fieldtype": "Date", "reqd": 1, "in_list_view": 1},
            {"fieldname": "snapshot_type", "label": "Snapshot Type", "fieldtype": "Select", "options": "\nManual\nScheduled", "default": "Manual", "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nActive\nCancelled\nFailed", "default": "Active", "in_list_view": 1},
            {"fieldname": "period_section", "label": "Period / Filters", "fieldtype": "Section Break"},
            {"fieldname": "period_start", "label": "Period Start", "fieldtype": "Date"},
            {"fieldname": "period_end", "label": "Period End", "fieldtype": "Date"},
            {"fieldname": "house", "label": "House", "fieldtype": "Link", "options": "NDIS House"},
            {"fieldname": "participant", "label": "Participant", "fieldtype": "Link", "options": "Customer"},
            {"fieldname": "funding_source", "label": "Funding Source", "fieldtype": "Link", "options": "NDIS Funding Source"},
            {"fieldname": "cost_type", "label": "Cost Type", "fieldtype": "Data"},
            {"fieldname": "filters_json", "label": "Filters JSON", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "kpi_section", "label": "Executive KPIs", "fieldtype": "Section Break"},
            {"fieldname": "gross_claim_amount", "label": "Gross Claims", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "paid_revenue", "label": "Paid Revenue", "fieldtype": "Currency", "read_only": 1, "in_list_view": 1},
            {"fieldname": "shortfall_amount", "label": "Shortfall", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "total_allocated_cost", "label": "Total Allocated Cost", "fieldtype": "Currency", "read_only": 1, "in_list_view": 1},
            {"fieldname": "payroll_cost", "label": "Payroll Cost", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "non_payroll_cost", "label": "Non-Payroll Cost", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "estimated_margin", "label": "Estimated Margin", "fieldtype": "Currency", "read_only": 1, "in_list_view": 1},
            {"fieldname": "estimated_margin_percent", "label": "Estimated Margin %", "fieldtype": "Percent", "read_only": 1},
            {"fieldname": "payroll_cost_ratio", "label": "Payroll Cost Ratio %", "fieldtype": "Percent", "read_only": 1},
            {"fieldname": "shortfall_ratio", "label": "Shortfall Ratio %", "fieldtype": "Percent", "read_only": 1},
            {"fieldname": "risk_section", "label": "Risk / Exceptions", "fieldtype": "Section Break"},
            {"fieldname": "open_leakage_amount", "label": "Open Leakage", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "open_recovery_amount", "label": "Open Recovery", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "unmapped_payroll_lines", "label": "Unmapped Payroll Lines", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "failed_automation_runs_7_days", "label": "Failed Automation Runs 7 Days", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "approved_drafts_not_sent", "label": "Approved Drafts Not Sent", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "escalation_candidates", "label": "Escalation Candidates", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "overdue_recovery_cases", "label": "Overdue Recovery Cases", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "metric_count", "label": "Metric Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "audit_section", "label": "Audit", "fieldtype": "Section Break"},
            {"fieldname": "created_on", "label": "Created On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "created_by_user", "label": "Created By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "cancelled_on", "label": "Cancelled On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "cancelled_by", "label": "Cancelled By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "raw_summary_json", "label": "Raw Summary JSON", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "warning_log", "label": "Warning Log", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
        ],
    )


def create_snapshot_metric_doctype():
    _create_doctype(
        name="NDIS Executive Dashboard Snapshot Metric",
        autoname="hash",
        title_field="metric",
        fields=[
            {"fieldname": "snapshot", "label": "Snapshot", "fieldtype": "Link", "options": "NDIS Executive Dashboard Snapshot", "reqd": 1, "in_list_view": 1},
            {"fieldname": "snapshot_date", "label": "Snapshot Date", "fieldtype": "Date", "in_list_view": 1},
            {"fieldname": "snapshot_type", "label": "Snapshot Type", "fieldtype": "Data"},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nActive\nCancelled", "default": "Active", "in_list_view": 1},
            {"fieldname": "section", "label": "Section", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "metric", "label": "Metric", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "amount", "label": "Amount", "fieldtype": "Currency", "in_list_view": 1},
            {"fieldname": "count_value", "label": "Count", "fieldtype": "Int"},
            {"fieldname": "percent_value", "label": "Percent", "fieldtype": "Percent"},
            {"fieldname": "risk_status", "label": "Risk Status", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "note", "label": "Note", "fieldtype": "Small Text"},
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
    elif profile == "create_write_read_report":
        base.update({"read": 1, "write": 1, "create": 1, "report": 1, "export": 1, "print": 1, "email": 1})
    elif profile == "read_report_export":
        base.update({"read": 1, "report": 1, "export": 1, "print": 1})
    elif profile == "read_report":
        base.update({"read": 1, "report": 1})
    else:
        frappe.throw(_("Unknown permission profile: {0}").format(profile))

    return base


def add_workspace_shortcuts():
    ws_name = frappe.db.exists("Workspace", WORKSPACE_NAME) or frappe.db.exists(
        "Workspace",
        {"label": WORKSPACE_NAME},
    )
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
    if "Executive Snapshot Trends" not in text_blob:
        content.append(
            {
                "id": "ndis_executive_snapshot_trends_heading",
                "type": "header",
                "data": {"text": "Executive Snapshot Trends", "col": 12},
            }
        )

    for shortcut in WORKSPACE_SHORTCUTS:
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            continue
        content.append(
            {
                "id": frappe.scrub(shortcut["label"]),
                "type": "shortcut",
                "data": {
                    "label": shortcut["label"],
                    "link_to": shortcut["link_to"],
                    "type": shortcut["type"],
                    "col": 3,
                },
            }
        )

    ws.content = json.dumps(content)


def add_shortcuts_to_child_table(ws):
    for fieldname in ["shortcuts", "links"]:
        if not ws.meta.has_field(fieldname):
            continue

        existing_blob = ""
        for row in getattr(ws, fieldname, []) or []:
            existing_blob += " " + str(getattr(row, "label", ""))
            existing_blob += " " + str(getattr(row, "link_to", ""))

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
    doctypes = {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE1W_DOCTYPES}
    reports = {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS}
    permissions = {}

    for dt in PHASE1W_DOCTYPES:
        permissions[dt] = frappe.get_all(
            "DocPerm",
            filters={"parent": dt},
            fields=["role", "read", "write", "create", "delete", "report", "export"],
            order_by="role asc",
        )

    hooks = frappe.get_hooks()
    doctype_js = hooks.get("doctype_js", {})
    doctype_list_js = hooks.get("doctype_list_js", {})
    scheduler_events = hooks.get("scheduler_events", {})
    daily_jobs = scheduler_events.get("daily", []) if isinstance(scheduler_events, dict) else []

    return {
        "doctypes": doctypes,
        "reports": reports,
        "permissions": permissions,
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "create_executive_snapshot": permission_matrix().get("create_executive_snapshot"),
            "cancel_executive_snapshot": permission_matrix().get("cancel_executive_snapshot"),
        },
        "js_hooks": {
            "NDIS Executive Dashboard Snapshot": "NDIS Executive Dashboard Snapshot" in doctype_js,
            "NDIS Executive Dashboard Snapshot Metric": "NDIS Executive Dashboard Snapshot Metric" in doctype_js,
        },
        "list_js_hooks": {
            "NDIS Executive Dashboard Snapshot": "NDIS Executive Dashboard Snapshot" in doctype_list_js,
            "NDIS Executive Dashboard Snapshot Metric": "NDIS Executive Dashboard Snapshot Metric" in doctype_list_js,
        },
        "daily_snapshot_job_registered": DAILY_JOB in daily_jobs,
        "report_files": report_files_exist(),
    }


def can_import_service():
    try:
        from ndis_finance.services.executive_snapshots import quick_executive_snapshot_summary

        return callable(quick_executive_snapshot_summary)
    except Exception:
        return False


def check_workspace_shortcuts():
    ws_name = frappe.db.exists("Workspace", WORKSPACE_NAME) or frappe.db.exists(
        "Workspace",
        {"label": WORKSPACE_NAME},
    )
    result = {shortcut["label"]: False for shortcut in WORKSPACE_SHORTCUTS}
    if not ws_name:
        return result

    ws = frappe.get_doc("Workspace", ws_name)
    text_blob = getattr(ws, "content", "") or ""
    for fieldname in ["shortcuts", "links"]:
        if not ws.meta.has_field(fieldname):
            continue
        for row in getattr(ws, fieldname, []) or []:
            text_blob += " " + str(getattr(row, "label", ""))
            text_blob += " " + str(getattr(row, "link_to", ""))

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
