import json
import os

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


PHASE2D_DOCTYPES = [
    "NDIS Sandbox Accounting Posting Run",
    "NDIS Sandbox Accounting Posting Run Line",
]

JOURNAL_ENTRY_CUSTOM_FIELDS = {
    "Journal Entry": [
        {"fieldname": "custom_ndis_sandbox_section", "label": "NDIS Sandbox Posting", "fieldtype": "Section Break", "insert_after": "user_remark", "collapsible": 1},
        {"fieldname": "custom_ndis_sandbox_posting_run", "label": "NDIS Sandbox Posting Run", "fieldtype": "Link", "options": "NDIS Sandbox Accounting Posting Run", "insert_after": "custom_ndis_sandbox_section", "read_only": 1},
        {"fieldname": "custom_ndis_accounting_posting_request", "label": "NDIS Accounting Posting Request", "fieldtype": "Link", "options": "NDIS Accounting Posting Request", "insert_after": "custom_ndis_sandbox_posting_run", "read_only": 1},
        {"fieldname": "custom_ndis_sandbox_draft_only", "label": "NDIS Sandbox Draft Only", "fieldtype": "Check", "insert_after": "custom_ndis_accounting_posting_request", "read_only": 1, "default": "0"},
        {"fieldname": "custom_ndis_sandbox_acknowledgement", "label": "NDIS Sandbox Acknowledgement", "fieldtype": "Data", "insert_after": "custom_ndis_sandbox_draft_only", "read_only": 1},
    ]
}

REPORTS = [
    {"report_name": "NDIS Sandbox Accounting Posting Run Report", "ref_doctype": "NDIS Sandbox Accounting Posting Run"},
    {"report_name": "NDIS Sandbox Accounting Posting Run Line Report", "ref_doctype": "NDIS Sandbox Accounting Posting Run Line"},
]

REPORT_ROLES = ["System Manager", "NDIS CFO", "NDIS Finance Manager", "NDIS Finance Officer", "NDIS Finance Read Only"]

DOC_PERM_MATRIX = {
    "NDIS Sandbox Accounting Posting Run": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Sandbox Accounting Posting Run Line": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
}

WORKSPACE_NAME = "NDIS Finance"

WORKSPACE_SHORTCUTS = [
    {"label": "Sandbox Accounting Runs", "type": "DocType", "link_to": "NDIS Sandbox Accounting Posting Run"},
    {"label": "Sandbox Accounting Run Lines", "type": "DocType", "link_to": "NDIS Sandbox Accounting Posting Run Line"},
    {"label": "Sandbox Accounting Run Report", "type": "Report", "link_to": "NDIS Sandbox Accounting Posting Run Report"},
    {"label": "Sandbox Accounting Run Lines Report", "type": "Report", "link_to": "NDIS Sandbox Accounting Posting Run Line Report"},
]

REPORT_FILE_MAP = {
    "NDIS Sandbox Accounting Posting Run Report": "ndis_sandbox_accounting_posting_run_report",
    "NDIS Sandbox Accounting Posting Run Line Report": "ndis_sandbox_accounting_posting_run_line_report",
}


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_sandbox_run_doctype()
    create_sandbox_run_line_doctype()
    create_journal_entry_custom_fields()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Accounting Posting Request",
        "NDIS Accounting Posting Request Line",
        "NDIS Accounting Posting Preview",
        "NDIS Accounting Posting Policy",
        "NDIS Finance Production Readiness Check",
        "NDIS Executive Governance Pack",
        "Journal Entry",
        "Report",
        "Workspace",
    ]
    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]
    if missing:
        frappe.throw(_("Phase 2D requires Phase 2C, Phase 2B and ERPNext accounting. Missing DocTypes: {0}").format(", ".join(missing)))


def create_sandbox_run_doctype():
    _create_doctype(
        name="NDIS Sandbox Accounting Posting Run",
        autoname="field:run_id",
        title_field="run_id",
        fields=[
            {"fieldname": "run_id", "label": "Run ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nDry Run\nCreated Draft JE\nBlocked\nCancelled\nFailed", "default": "Draft", "in_list_view": 1},
            {"fieldname": "sandbox_mode", "label": "Sandbox Mode", "fieldtype": "Check", "default": "1", "read_only": 1, "in_list_view": 1},
            {"fieldname": "draft_only", "label": "Draft Only", "fieldtype": "Check", "default": "1", "read_only": 1},
            {"fieldname": "source_section", "label": "Source", "fieldtype": "Section Break"},
            {"fieldname": "posting_request", "label": "Posting Request", "fieldtype": "Link", "options": "NDIS Accounting Posting Request", "reqd": 1, "in_list_view": 1},
            {"fieldname": "posting_preview", "label": "Posting Preview", "fieldtype": "Link", "options": "NDIS Accounting Posting Preview"},
            {"fieldname": "policy", "label": "Posting Policy", "fieldtype": "Link", "options": "NDIS Accounting Posting Policy"},
            {"fieldname": "event_type", "label": "Event Type", "fieldtype": "Data"},
            {"fieldname": "source_doctype", "label": "Source DocType", "fieldtype": "Link", "options": "DocType"},
            {"fieldname": "source_name", "label": "Source Name", "fieldtype": "Dynamic Link", "options": "source_doctype"},
            {"fieldname": "control_section", "label": "Safety Controls", "fieldtype": "Section Break"},
            {"fieldname": "site_name", "label": "Site Name", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "sandbox_config_enabled", "label": "Sandbox Config Enabled", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "production_mode_detected", "label": "Production Mode Detected", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "readiness_check", "label": "Production Readiness Check", "fieldtype": "Link", "options": "NDIS Finance Production Readiness Check"},
            {"fieldname": "readiness_allowed", "label": "Readiness Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "governance_pack", "label": "Governance Pack", "fieldtype": "Link", "options": "NDIS Executive Governance Pack"},
            {"fieldname": "governance_signed_off", "label": "Governance Signed Off", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "request_approved", "label": "Request Approved", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "request_dry_run_passed", "label": "Request Dry-run Passed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "hard_posting_block_confirmed", "label": "Hard Posting Block Confirmed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "real_posting_disabled_confirmed", "label": "Real Posting Disabled Confirmed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "acknowledgement", "label": "Acknowledgement", "fieldtype": "Data"},
            {"fieldname": "required_acknowledgement", "label": "Required Acknowledgement", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "journal_section", "label": "Sandbox Journal Entry Draft", "fieldtype": "Section Break"},
            {"fieldname": "journal_entry", "label": "Draft Journal Entry", "fieldtype": "Link", "options": "Journal Entry", "read_only": 1, "in_list_view": 1},
            {"fieldname": "journal_entry_docstatus", "label": "Journal Entry Docstatus", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company"},
            {"fieldname": "posting_date", "label": "Posting Date", "fieldtype": "Date"},
            {"fieldname": "currency", "label": "Currency", "fieldtype": "Link", "options": "Currency"},
            {"fieldname": "total_debit", "label": "Total Debit", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "total_credit", "label": "Total Credit", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "variance_amount", "label": "Variance", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "line_count", "label": "Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "audit_section", "label": "Audit", "fieldtype": "Section Break"},
            {"fieldname": "created_on", "label": "Created On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "created_by_user", "label": "Created By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "cancelled_on", "label": "Cancelled On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "cancelled_by", "label": "Cancelled By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "validation_log", "label": "Validation Log", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
        ],
    )


def create_sandbox_run_line_doctype():
    _create_doctype(
        name="NDIS Sandbox Accounting Posting Run Line",
        autoname="hash",
        title_field="line_label",
        fields=[
            {"fieldname": "sandbox_run", "label": "Sandbox Run", "fieldtype": "Link", "options": "NDIS Sandbox Accounting Posting Run", "reqd": 1, "in_list_view": 1},
            {"fieldname": "posting_request_line", "label": "Posting Request Line", "fieldtype": "Link", "options": "NDIS Accounting Posting Request Line"},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nPrepared\nInserted In Draft JE\nWarning\nBlocker\nCancelled", "default": "Prepared", "in_list_view": 1},
            {"fieldname": "line_no", "label": "Line No", "fieldtype": "Int", "in_list_view": 1},
            {"fieldname": "line_label", "label": "Line Label", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "line_type", "label": "Line Type", "fieldtype": "Select", "options": "\nDebit\nCredit", "in_list_view": 1},
            {"fieldname": "account", "label": "Account", "fieldtype": "Link", "options": "Account", "in_list_view": 1},
            {"fieldname": "cost_center", "label": "Cost Center", "fieldtype": "Link", "options": "Cost Center"},
            {"fieldname": "party_type", "label": "Party Type", "fieldtype": "Link", "options": "DocType"},
            {"fieldname": "party", "label": "Party", "fieldtype": "Dynamic Link", "options": "party_type"},
            {"fieldname": "debit_amount", "label": "Debit Amount", "fieldtype": "Currency"},
            {"fieldname": "credit_amount", "label": "Credit Amount", "fieldtype": "Currency"},
            {"fieldname": "reference_doctype", "label": "Reference DocType", "fieldtype": "Link", "options": "DocType"},
            {"fieldname": "reference_name", "label": "Reference Name", "fieldtype": "Dynamic Link", "options": "reference_doctype"},
            {"fieldname": "note", "label": "Note", "fieldtype": "Small Text"},
        ],
    )


def create_journal_entry_custom_fields():
    create_custom_fields(JOURNAL_ENTRY_CUSTOM_FIELDS, update=True)
    for field in JOURNAL_ENTRY_CUSTOM_FIELDS["Journal Entry"]:
        frappe.db.set_value(
            "Custom Field",
            {"dt": "Journal Entry", "fieldname": field["fieldname"]},
            "module",
            MODULE,
            update_modified=False,
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
    if "Sandbox Accounting Adapter" not in text_blob:
        content.append({"id": "ndis_sandbox_accounting_adapter_heading", "type": "header", "data": {"text": "Sandbox Accounting Adapter", "col": 12}})
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
    doc_events = hooks.get("doc_events", {}) or {}
    journal_entry_events = json.dumps(doc_events.get("Journal Entry", {}), default=str)
    return {
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE2D_DOCTYPES},
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "journal_entry_custom_fields": {
            field["fieldname"]: bool(frappe.db.exists("Custom Field", {"dt": "Journal Entry", "fieldname": field["fieldname"]}))
            for field in JOURNAL_ENTRY_CUSTOM_FIELDS["Journal Entry"]
        },
        "permissions": {
            dt: frappe.get_all("DocPerm", filters={"parent": dt}, fields=["role", "read", "write", "create", "delete", "report", "export"], order_by="role asc")
            for dt in PHASE2D_DOCTYPES
        },
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "create_sandbox_journal_entry_draft": permission_matrix().get("create_sandbox_journal_entry_draft"),
            "cancel_sandbox_accounting_posting_run": permission_matrix().get("cancel_sandbox_accounting_posting_run"),
        },
        "js_hooks": {
            "NDIS Sandbox Accounting Posting Run": "NDIS Sandbox Accounting Posting Run" in doctype_js,
            "NDIS Sandbox Accounting Posting Run Line": "NDIS Sandbox Accounting Posting Run Line" in doctype_js,
        },
        "list_js_hooks": {
            "NDIS Sandbox Accounting Posting Run": "NDIS Sandbox Accounting Posting Run" in doctype_list_js,
            "NDIS Sandbox Accounting Posting Run Line": "NDIS Sandbox Accounting Posting Run Line" in doctype_list_js,
        },
        "journal_entry_submit_blocker_registered": "block_sandbox_journal_entry_submit" in journal_entry_events,
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "report_files": check_report_files(),
    }


def can_import_service():
    try:
        from ndis_finance.services.sandbox_accounting_posting import quick_sandbox_accounting_summary

        return callable(quick_sandbox_accounting_summary)
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
