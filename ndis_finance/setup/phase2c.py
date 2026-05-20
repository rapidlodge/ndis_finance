import json
import os

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


PHASE2C_DOCTYPES = [
    "NDIS Accounting Posting Request",
    "NDIS Accounting Posting Request Line",
]

REPORTS = [
    {"report_name": "NDIS Accounting Posting Request Register Report", "ref_doctype": "NDIS Accounting Posting Request"},
    {"report_name": "NDIS Accounting Posting Request Line Report", "ref_doctype": "NDIS Accounting Posting Request Line"},
]

REPORT_ROLES = ["System Manager", "NDIS CFO", "NDIS Finance Manager", "NDIS Finance Officer", "NDIS Finance Read Only"]

DOC_PERM_MATRIX = {
    "NDIS Accounting Posting Request": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Finance Officer": "create_write_read_report",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Accounting Posting Request Line": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Finance Officer": "create_write_read_report",
        "NDIS Finance Read Only": "read_report",
    },
}

WORKSPACE_NAME = "NDIS Finance"

WORKSPACE_SHORTCUTS = [
    {"label": "Accounting Posting Requests", "type": "DocType", "link_to": "NDIS Accounting Posting Request"},
    {"label": "Accounting Posting Request Lines", "type": "DocType", "link_to": "NDIS Accounting Posting Request Line"},
    {"label": "Posting Request Register", "type": "Report", "link_to": "NDIS Accounting Posting Request Register Report"},
    {"label": "Posting Request Lines", "type": "Report", "link_to": "NDIS Accounting Posting Request Line Report"},
]

REPORT_FILE_MAP = {
    "NDIS Accounting Posting Request Register Report": "ndis_accounting_posting_request_register_report",
    "NDIS Accounting Posting Request Line Report": "ndis_accounting_posting_request_line_report",
}


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_request_doctype()
    create_request_line_doctype()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Accounting Posting Policy",
        "NDIS Accounting Posting Preview",
        "NDIS Accounting Posting Preview Line",
        "NDIS Finance Production Readiness Check",
        "NDIS Executive Governance Pack",
        "Report",
        "Workspace",
    ]
    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]
    if missing:
        frappe.throw(_("Phase 2C requires Phase 2B and Phase 2A. Missing DocTypes: {0}").format(", ".join(missing)))


def create_request_doctype():
    _create_doctype(
        name="NDIS Accounting Posting Request",
        autoname="field:request_id",
        title_field="request_id",
        fields=[
            {"fieldname": "request_id", "label": "Request ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nPending Approval\nApproved\nRejected\nDry Run Passed\nDry Run Failed\nBlocked\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "approval_status", "label": "Approval Status", "fieldtype": "Select", "options": "\nNot Requested\nPending\nApproved\nRejected", "default": "Not Requested", "in_list_view": 1},
            {"fieldname": "validation_status", "label": "Validation Status", "fieldtype": "Select", "options": "\nPass\nWarning\nBlocked", "default": "Warning", "in_list_view": 1},
            {"fieldname": "request_section", "label": "Request Source", "fieldtype": "Section Break"},
            {"fieldname": "posting_preview", "label": "Posting Preview", "fieldtype": "Link", "options": "NDIS Accounting Posting Preview", "reqd": 1, "in_list_view": 1},
            {"fieldname": "policy", "label": "Posting Policy", "fieldtype": "Link", "options": "NDIS Accounting Posting Policy", "reqd": 1, "in_list_view": 1},
            {"fieldname": "event_type", "label": "Event Type", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "source_doctype", "label": "Source DocType", "fieldtype": "Link", "options": "DocType", "in_list_view": 1},
            {"fieldname": "source_name", "label": "Source Name", "fieldtype": "Dynamic Link", "options": "source_doctype", "in_list_view": 1},
            {"fieldname": "source_summary", "label": "Source Summary", "fieldtype": "Small Text"},
            {"fieldname": "control_section", "label": "Control Gate", "fieldtype": "Section Break"},
            {"fieldname": "readiness_check", "label": "Production Readiness Check", "fieldtype": "Link", "options": "NDIS Finance Production Readiness Check"},
            {"fieldname": "readiness_allowed", "label": "Readiness Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "governance_pack", "label": "Governance Pack", "fieldtype": "Link", "options": "NDIS Executive Governance Pack"},
            {"fieldname": "governance_signed_off", "label": "Governance Signed Off", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "cfo_approval_required", "label": "CFO Approval Required", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "hard_posting_block", "label": "Hard Posting Block", "fieldtype": "Check", "default": "1", "read_only": 1},
            {"fieldname": "real_posting_enabled", "label": "Real Posting Enabled", "fieldtype": "Check", "default": "0", "read_only": 1},
            {"fieldname": "posting_section", "label": "Posting Simulation", "fieldtype": "Section Break"},
            {"fieldname": "target_entry_type", "label": "Target Entry Type", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "posting_mode", "label": "Posting Mode", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company"},
            {"fieldname": "posting_date", "label": "Posting Date", "fieldtype": "Date"},
            {"fieldname": "currency", "label": "Currency", "fieldtype": "Link", "options": "Currency"},
            {"fieldname": "request_total_amount", "label": "Request Total Amount", "fieldtype": "Currency", "read_only": 1, "in_list_view": 1},
            {"fieldname": "debit_total", "label": "Debit Total", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "credit_total", "label": "Credit Total", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "variance_amount", "label": "Debit/Credit Variance", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "line_count", "label": "Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "blocker_count", "label": "Blocker Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "warning_count", "label": "Warning Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "approval_section", "label": "Approval", "fieldtype": "Section Break"},
            {"fieldname": "approved_by", "label": "Approved By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "approved_on", "label": "Approved On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "approval_note", "label": "Approval Note", "fieldtype": "Small Text"},
            {"fieldname": "rejected_by", "label": "Rejected By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "rejected_on", "label": "Rejected On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "rejection_reason", "label": "Rejection Reason", "fieldtype": "Small Text"},
            {"fieldname": "dry_run_section", "label": "Dry-run Result", "fieldtype": "Section Break"},
            {"fieldname": "dry_run_on", "label": "Dry-run On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "dry_run_by", "label": "Dry-run By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "dry_run_status", "label": "Dry-run Status", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "dry_run_result_json", "label": "Dry-run Result JSON", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "audit_section", "label": "Audit", "fieldtype": "Section Break"},
            {"fieldname": "created_on", "label": "Created On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "created_by_user", "label": "Created By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "cancelled_on", "label": "Cancelled On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "cancelled_by", "label": "Cancelled By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "validation_log", "label": "Validation Log", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
        ],
    )


def create_request_line_doctype():
    _create_doctype(
        name="NDIS Accounting Posting Request Line",
        autoname="hash",
        title_field="line_label",
        fields=[
            {"fieldname": "posting_request", "label": "Posting Request", "fieldtype": "Link", "options": "NDIS Accounting Posting Request", "reqd": 1, "in_list_view": 1},
            {"fieldname": "posting_preview_line", "label": "Posting Preview Line", "fieldtype": "Link", "options": "NDIS Accounting Posting Preview Line"},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nReady\nWarning\nBlocker\nSimulated\nCancelled", "default": "Ready", "in_list_view": 1},
            {"fieldname": "line_no", "label": "Line No", "fieldtype": "Int", "in_list_view": 1},
            {"fieldname": "line_label", "label": "Line Label", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "line_type", "label": "Line Type", "fieldtype": "Select", "options": "\nDebit\nCredit\nControl\nInformation", "default": "Information", "in_list_view": 1},
            {"fieldname": "target_entry_type", "label": "Target Entry Type", "fieldtype": "Data"},
            {"fieldname": "account", "label": "Account", "fieldtype": "Link", "options": "Account"},
            {"fieldname": "cost_center", "label": "Cost Center", "fieldtype": "Link", "options": "Cost Center"},
            {"fieldname": "party_type", "label": "Party Type", "fieldtype": "Link", "options": "DocType"},
            {"fieldname": "party", "label": "Party", "fieldtype": "Dynamic Link", "options": "party_type"},
            {"fieldname": "amount", "label": "Amount", "fieldtype": "Currency", "in_list_view": 1},
            {"fieldname": "reference_doctype", "label": "Reference DocType", "fieldtype": "Link", "options": "DocType"},
            {"fieldname": "reference_name", "label": "Reference Name", "fieldtype": "Dynamic Link", "options": "reference_doctype"},
            {"fieldname": "simulation_status", "label": "Simulation Status", "fieldtype": "Data"},
            {"fieldname": "note", "label": "Note", "fieldtype": "Small Text"},
        ],
    )


def create_reports():
    for report in REPORTS:
        doc = frappe.get_doc("Report", report["report_name"]) if frappe.db.exists("Report", report["report_name"]) else frappe.new_doc("Report")
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
    if "Accounting Dry-run Requests" not in text_blob:
        content.append({"id": "ndis_accounting_dry_run_requests_heading", "type": "header", "data": {"text": "Accounting Dry-run Requests", "col": 12}})
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
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE2C_DOCTYPES},
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "permissions": {
            dt: frappe.get_all("DocPerm", filters={"parent": dt}, fields=["role", "read", "write", "create", "delete", "report", "export"], order_by="role asc")
            for dt in PHASE2C_DOCTYPES
        },
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "create_accounting_posting_request": permission_matrix().get("create_accounting_posting_request"),
            "approve_accounting_posting_request": permission_matrix().get("approve_accounting_posting_request"),
            "reject_accounting_posting_request": permission_matrix().get("reject_accounting_posting_request"),
            "dry_run_accounting_posting_request": permission_matrix().get("dry_run_accounting_posting_request"),
            "cancel_accounting_posting_request": permission_matrix().get("cancel_accounting_posting_request"),
        },
        "js_hooks": {
            "NDIS Accounting Posting Request": "NDIS Accounting Posting Request" in doctype_js,
            "NDIS Accounting Posting Request Line": "NDIS Accounting Posting Request Line" in doctype_js,
        },
        "list_js_hooks": {
            "NDIS Accounting Posting Request": "NDIS Accounting Posting Request" in doctype_list_js,
            "NDIS Accounting Posting Request Line": "NDIS Accounting Posting Request Line" in doctype_list_js,
        },
        "report_files": check_report_files(),
    }


def can_import_service():
    try:
        from ndis_finance.services.accounting_posting_requests import quick_accounting_posting_request_summary

        return callable(quick_accounting_posting_request_summary)
    except Exception:
        return False


def check_report_files():
    app_path = frappe.get_app_path("ndis_finance")
    result = {}
    for report_name, folder in REPORT_FILE_MAP.items():
        path = os.path.join(app_path, "ndis_finance", "report", folder)
        result[report_name] = {
            "python": os.path.exists(os.path.join(path, f"{folder}.py")),
            "javascript": os.path.exists(os.path.join(path, f"{folder}.js")),
            "init": os.path.exists(os.path.join(path, "__init__.py")),
        }
    return result


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
                text_blob += f" {getattr(row, 'label', '')} {getattr(row, 'link_to', '')}"
    for shortcut in WORKSPACE_SHORTCUTS:
        result[shortcut["label"]] = shortcut["label"] in text_blob or shortcut["link_to"] in text_blob
    return result
