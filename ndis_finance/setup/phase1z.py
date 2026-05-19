import json
import os

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


PHASE1Z_DOCTYPES = ["NDIS Executive Governance Pack", "NDIS Executive Governance Pack Item"]

REPORTS = [
    {"report_name": "NDIS Executive Governance Pack Report", "ref_doctype": "NDIS Executive Governance Pack"},
    {"report_name": "NDIS Governance Pack Detail Report", "ref_doctype": "NDIS Executive Governance Pack Item"},
]

REPORT_ROLES = ["System Manager", "NDIS CFO", "NDIS Finance Manager", "NDIS Finance Officer", "NDIS Finance Read Only"]

DOC_PERM_MATRIX = {
    "NDIS Executive Governance Pack": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Executive Governance Pack Item": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
}

WORKSPACE_NAME = "NDIS Finance"

WORKSPACE_SHORTCUTS = [
    {"label": "Executive Governance Packs", "type": "DocType", "link_to": "NDIS Executive Governance Pack"},
    {"label": "Governance Pack Items", "type": "DocType", "link_to": "NDIS Executive Governance Pack Item"},
    {"label": "Executive Governance Pack Report", "type": "Report", "link_to": "NDIS Executive Governance Pack Report"},
    {"label": "Governance Pack Detail", "type": "Report", "link_to": "NDIS Governance Pack Detail Report"},
]

REPORT_FILE_MAP = {
    "NDIS Executive Governance Pack Report": "ndis_executive_governance_pack_report",
    "NDIS Governance Pack Detail Report": "ndis_governance_pack_detail_report",
}


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_governance_pack_doctype()
    create_governance_pack_item_doctype()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Executive Dashboard Snapshot",
        "NDIS Executive Dashboard Snapshot Metric",
        "NDIS Executive Exception Alert",
        "NDIS Executive Exception Rule",
        "NDIS Executive Exception Action Plan",
        "NDIS Executive Exception Action Step",
        "Report",
        "Workspace",
    ]
    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]
    if missing:
        frappe.throw(_("Phase 1Z requires Phase 1W, 1X and 1Y. Missing DocTypes: {0}").format(", ".join(missing)))


def create_governance_pack_doctype():
    _create_doctype(
        name="NDIS Executive Governance Pack",
        autoname="field:pack_id",
        title_field="pack_id",
        fields=[
            {"fieldname": "pack_id", "label": "Pack ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "pack_date", "label": "Pack Date", "fieldtype": "Date", "reqd": 1, "in_list_view": 1},
            {"fieldname": "pack_type", "label": "Pack Type", "fieldtype": "Select", "options": "\nManual\nMonthly\nBoard\nInternal Review", "default": "Manual", "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nGenerated\nSigned Off\nCancelled\nFailed", "default": "Draft", "in_list_view": 1},
            {"fieldname": "period_section", "label": "Period / Source", "fieldtype": "Section Break"},
            {"fieldname": "period_start", "label": "Period Start", "fieldtype": "Date"},
            {"fieldname": "period_end", "label": "Period End", "fieldtype": "Date"},
            {"fieldname": "source_snapshot", "label": "Source Snapshot", "fieldtype": "Link", "options": "NDIS Executive Dashboard Snapshot", "in_list_view": 1},
            {"fieldname": "snapshot_date", "label": "Snapshot Date", "fieldtype": "Date"},
            {"fieldname": "include_resolved_items", "label": "Include Resolved Items", "fieldtype": "Check", "default": "0"},
            {"fieldname": "summary_section", "label": "Executive Summary", "fieldtype": "Section Break"},
            {"fieldname": "paid_revenue", "label": "Paid Revenue", "fieldtype": "Currency", "read_only": 1, "in_list_view": 1},
            {"fieldname": "total_allocated_cost", "label": "Total Allocated Cost", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "payroll_cost", "label": "Payroll Cost", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "estimated_margin", "label": "Estimated Margin", "fieldtype": "Currency", "read_only": 1, "in_list_view": 1},
            {"fieldname": "estimated_margin_percent", "label": "Estimated Margin %", "fieldtype": "Percent", "read_only": 1},
            {"fieldname": "open_leakage_amount", "label": "Open Leakage", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "open_recovery_amount", "label": "Open Recovery", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "exception_section", "label": "Exceptions / Actions", "fieldtype": "Section Break"},
            {"fieldname": "open_exception_alert_count", "label": "Open Exception Alerts", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "critical_exception_count", "label": "Critical Exceptions", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "high_exception_count", "label": "High Exceptions", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "open_action_plan_count", "label": "Open Action Plans", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "overdue_action_plan_count", "label": "Overdue Action Plans", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "signed_off_action_plan_count", "label": "Signed-off Action Plans", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "export_section", "label": "Board Pack Export", "fieldtype": "Section Break"},
            {"fieldname": "board_pack_html_file", "label": "Board Pack HTML File", "fieldtype": "Attach", "read_only": 1},
            {"fieldname": "board_pack_csv_file", "label": "Board Pack CSV File", "fieldtype": "Attach", "read_only": 1},
            {"fieldname": "item_count", "label": "Item Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "governance_score", "label": "Governance Score", "fieldtype": "Percent", "read_only": 1},
            {"fieldname": "governance_status", "label": "Governance Status", "fieldtype": "Select", "options": "\nStrong\nWatch\nNeeds Attention\nCritical", "read_only": 1, "in_list_view": 1},
            {"fieldname": "signoff_section", "label": "Management Sign-off", "fieldtype": "Section Break"},
            {"fieldname": "management_sign_off", "label": "Management Sign-off", "fieldtype": "Check", "default": "0"},
            {"fieldname": "signed_off_by", "label": "Signed Off By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "signed_off_on", "label": "Signed Off On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "signoff_note", "label": "Sign-off Note", "fieldtype": "Small Text"},
            {"fieldname": "audit_section", "label": "Audit", "fieldtype": "Section Break"},
            {"fieldname": "generated_on", "label": "Generated On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "generated_by", "label": "Generated By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "cancelled_on", "label": "Cancelled On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "cancelled_by", "label": "Cancelled By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "warning_log", "label": "Warning Log", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
        ],
    )


def create_governance_pack_item_doctype():
    _create_doctype(
        name="NDIS Executive Governance Pack Item",
        autoname="hash",
        title_field="title",
        fields=[
            {"fieldname": "governance_pack", "label": "Governance Pack", "fieldtype": "Link", "options": "NDIS Executive Governance Pack", "reqd": 1, "in_list_view": 1},
            {"fieldname": "pack_date", "label": "Pack Date", "fieldtype": "Date", "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nActive\nCancelled", "default": "Active", "in_list_view": 1},
            {"fieldname": "section", "label": "Section", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "display_order", "label": "Display Order", "fieldtype": "Int"},
            {"fieldname": "title", "label": "Title", "fieldtype": "Data", "reqd": 1, "in_list_view": 1},
            {"fieldname": "risk_status", "label": "Risk Status", "fieldtype": "Select", "options": "\nGood\nInfo\nWatch\nRisk\nCritical", "default": "Info", "in_list_view": 1},
            {"fieldname": "amount", "label": "Amount", "fieldtype": "Currency"},
            {"fieldname": "count_value", "label": "Count", "fieldtype": "Int"},
            {"fieldname": "percent_value", "label": "Percent", "fieldtype": "Percent"},
            {"fieldname": "source_section", "label": "Source", "fieldtype": "Section Break"},
            {"fieldname": "source_doctype", "label": "Source DocType", "fieldtype": "Link", "options": "DocType"},
            {"fieldname": "source_name", "label": "Source Name", "fieldtype": "Dynamic Link", "options": "source_doctype"},
            {"fieldname": "source_reference", "label": "Source Reference", "fieldtype": "Data"},
            {"fieldname": "note", "label": "Note", "fieldtype": "Small Text"},
        ],
    )


def create_reports():
    for report in REPORTS:
        existing = frappe.db.exists("Report", report["report_name"])
        doc = frappe.get_doc("Report", existing) if existing else frappe.new_doc("Report")
        doc.report_name = report["report_name"]
        doc.ref_doctype = report["ref_doctype"]
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
    base = {"role": role, "permlevel": 0, "read": 0, "write": 0, "create": 0, "delete": 0, "submit": 0, "cancel": 0, "amend": 0, "report": 0, "export": 0, "import": 0, "share": 0, "print": 0, "email": 0}
    if profile == "full":
        base.update({"read": 1, "write": 1, "create": 1, "delete": 1, "report": 1, "export": 1, "share": 1, "print": 1, "email": 1})
    elif profile == "full_no_delete":
        base.update({"read": 1, "write": 1, "create": 1, "delete": 0, "report": 1, "export": 1, "share": 1, "print": 1, "email": 1})
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
    if "Governance Pack" not in text_blob:
        content.append({"id": "ndis_governance_pack_heading", "type": "header", "data": {"text": "Governance Pack", "col": 12}})
    for shortcut in WORKSPACE_SHORTCUTS:
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            continue
        content.append({"id": frappe.scrub(shortcut["label"]), "type": "shortcut", "data": {"label": shortcut["label"], "link_to": shortcut["link_to"], "type": shortcut["type"], "col": 3}})
    ws.content = json.dumps(content)


def add_shortcuts_to_child_table(ws):
    for fieldname in ["shortcuts", "links"]:
        if not ws.meta.has_field(fieldname):
            continue
        existing_blob = " ".join(f"{getattr(row, 'label', '')} {getattr(row, 'link_to', '')}" for row in (getattr(ws, fieldname, []) or []))
        for shortcut in WORKSPACE_SHORTCUTS:
            if shortcut["label"] in existing_blob or shortcut["link_to"] in existing_blob:
                continue
            row = ws.append(fieldname, {})
            set_child_value(row, "label", shortcut["label"])
            set_child_value(row, "link_to", shortcut["link_to"])
            set_child_value(row, "type", shortcut["type"] if fieldname == "shortcuts" else "Link")
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
    return {
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE1Z_DOCTYPES},
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "permissions": {
            dt: frappe.get_all("DocPerm", filters={"parent": dt}, fields=["role", "read", "write", "create", "delete", "report", "export"], order_by="role asc")
            for dt in PHASE1Z_DOCTYPES
        },
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "create_governance_pack": permission_matrix().get("create_governance_pack"),
            "signoff_governance_pack": permission_matrix().get("signoff_governance_pack"),
            "cancel_governance_pack": permission_matrix().get("cancel_governance_pack"),
        },
        "js_hooks": {dt: dt in doctype_js for dt in PHASE1Z_DOCTYPES},
        "list_js_hooks": {dt: dt in doctype_list_js for dt in PHASE1Z_DOCTYPES},
        "report_files": check_report_files(),
    }


def can_import_service():
    try:
        from ndis_finance.services.executive_governance_pack import quick_governance_pack_summary

        return callable(quick_governance_pack_summary)
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
