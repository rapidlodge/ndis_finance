import json
import os

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


PHASE3C_DOCTYPES = ["NDIS Sandbox Payment Entry Run", "NDIS Sandbox Payment Entry Run Line"]

PAYMENT_ENTRY_CUSTOM_FIELDS = {
    "Payment Entry": [
        {"fieldname": "custom_ndis_sandbox_pe_section", "label": "NDIS Sandbox Payment Entry", "fieldtype": "Section Break", "insert_after": "remarks", "collapsible": 1},
        {"fieldname": "custom_ndis_sandbox_payment_entry_run", "label": "NDIS Sandbox Payment Entry Run", "fieldtype": "Link", "options": "NDIS Sandbox Payment Entry Run", "insert_after": "custom_ndis_sandbox_pe_section", "read_only": 1},
        {"fieldname": "custom_ndis_payment_entry_allocation_preview", "label": "NDIS Payment Entry Allocation Preview", "fieldtype": "Link", "options": "NDIS Payment Entry Allocation Preview", "insert_after": "custom_ndis_sandbox_payment_entry_run", "read_only": 1},
        {"fieldname": "custom_ndis_sandbox_payment_entry_draft_only", "label": "NDIS Sandbox Payment Entry Draft Only", "fieldtype": "Check", "insert_after": "custom_ndis_payment_entry_allocation_preview", "read_only": 1, "default": "0"},
        {"fieldname": "custom_ndis_sandbox_payment_entry_acknowledgement", "label": "NDIS Sandbox Payment Entry Acknowledgement", "fieldtype": "Data", "insert_after": "custom_ndis_sandbox_payment_entry_draft_only", "read_only": 1},
    ]
}

REPORTS = [
    {"report_name": "NDIS Sandbox Payment Entry Run Report", "ref_doctype": "NDIS Sandbox Payment Entry Run"},
    {"report_name": "NDIS Sandbox Payment Entry Run Line Report", "ref_doctype": "NDIS Sandbox Payment Entry Run Line"},
]

REPORT_FILE_MAP = {
    "NDIS Sandbox Payment Entry Run Report": "ndis_sandbox_payment_entry_run_report",
    "NDIS Sandbox Payment Entry Run Line Report": "ndis_sandbox_payment_entry_run_line_report",
}

REPORT_ROLES = ["System Manager", "NDIS CFO", "NDIS Finance Manager", "NDIS Finance Officer", "NDIS Finance Read Only"]

DOC_PERM_MATRIX = {
    "NDIS Sandbox Payment Entry Run": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Sandbox Payment Entry Run Line": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
}

WORKSPACE_NAME = "NDIS Finance"

WORKSPACE_SHORTCUTS = [
    {"label": "Sandbox Payment Entry Runs", "type": "DocType", "link_to": "NDIS Sandbox Payment Entry Run"},
    {"label": "Sandbox Payment Entry Run Lines", "type": "DocType", "link_to": "NDIS Sandbox Payment Entry Run Line"},
    {"label": "Sandbox Payment Entry Run Report", "type": "Report", "link_to": "NDIS Sandbox Payment Entry Run Report"},
    {"label": "Sandbox Payment Entry Lines Report", "type": "Report", "link_to": "NDIS Sandbox Payment Entry Run Line Report"},
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_sandbox_payment_entry_run_doctype()
    create_sandbox_payment_entry_run_line_doctype()
    create_payment_entry_custom_fields()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Payment Entry Allocation Preview",
        "NDIS Payment Entry Allocation Preview Line",
        "NDIS Payment Entry Mapping Rule",
        "NDIS Accounting Design Review",
        "NDIS Accounting Sandbox Completion Gate",
        "Payment Entry",
        "Sales Invoice",
        "Report",
        "Workspace",
    ]
    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]
    if missing:
        frappe.throw(_("Phase 3C requires completed Phase 3B and ERPNext accounting. Missing DocTypes: {0}").format(", ".join(missing)))


def create_sandbox_payment_entry_run_doctype():
    _create_doctype(
        name="NDIS Sandbox Payment Entry Run",
        autoname="field:run_id",
        title_field="run_id",
        fields=[
            {"fieldname": "run_id", "label": "Run ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nValidated\nCreated Draft Payment Entry\nBlocked\nCancelled\nFailed", "default": "Draft", "in_list_view": 1},
            {"fieldname": "sandbox_mode", "label": "Sandbox Mode", "fieldtype": "Check", "default": "1", "read_only": 1, "in_list_view": 1},
            {"fieldname": "draft_only", "label": "Draft Only", "fieldtype": "Check", "default": "1", "read_only": 1},
            {"fieldname": "source_section", "label": "Source", "fieldtype": "Section Break"},
            {"fieldname": "allocation_preview", "label": "Allocation Preview", "fieldtype": "Link", "options": "NDIS Payment Entry Allocation Preview", "reqd": 1, "in_list_view": 1},
            {"fieldname": "mapping_rule", "label": "Mapping Rule", "fieldtype": "Link", "options": "NDIS Payment Entry Mapping Rule"},
            {"fieldname": "remittance_import", "label": "Remittance Import", "fieldtype": "Link", "options": "NDIS Remittance Import"},
            {"fieldname": "control_section", "label": "Safety Controls", "fieldtype": "Section Break"},
            {"fieldname": "site_name", "label": "Site Name", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "sandbox_config_enabled", "label": "Sandbox Config Enabled", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "production_mode_detected", "label": "Production Mode Detected", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "sandbox_completion_gate", "label": "Sandbox Completion Gate", "fieldtype": "Link", "options": "NDIS Accounting Sandbox Completion Gate"},
            {"fieldname": "sandbox_completion_allowed", "label": "Sandbox Completion Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "design_review", "label": "Design Review", "fieldtype": "Link", "options": "NDIS Accounting Design Review"},
            {"fieldname": "design_approved", "label": "Design Approved", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "preview_validation_status", "label": "Preview Validation Status", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "required_acknowledgement", "label": "Required Acknowledgement", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "acknowledgement", "label": "Acknowledgement", "fieldtype": "Data"},
            {"fieldname": "acknowledgement_ok", "label": "Acknowledgement OK", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "payment_section", "label": "Draft Payment Entry", "fieldtype": "Section Break"},
            {"fieldname": "payment_entry", "label": "Draft Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "read_only": 1, "in_list_view": 1},
            {"fieldname": "payment_entry_docstatus", "label": "Payment Entry Docstatus", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_type", "label": "Payment Type", "fieldtype": "Data"},
            {"fieldname": "party_type", "label": "Party Type", "fieldtype": "Link", "options": "DocType"},
            {"fieldname": "party", "label": "Party", "fieldtype": "Dynamic Link", "options": "party_type"},
            {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company"},
            {"fieldname": "posting_date", "label": "Posting Date", "fieldtype": "Date"},
            {"fieldname": "mode_of_payment", "label": "Mode of Payment", "fieldtype": "Link", "options": "Mode of Payment"},
            {"fieldname": "paid_from", "label": "Paid From / Receivable Account", "fieldtype": "Link", "options": "Account"},
            {"fieldname": "paid_to", "label": "Paid To / Bank Account", "fieldtype": "Link", "options": "Account"},
            {"fieldname": "currency", "label": "Currency", "fieldtype": "Link", "options": "Currency"},
            {"fieldname": "paid_amount", "label": "Paid Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "received_amount", "label": "Received Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "summary_section", "label": "Summary", "fieldtype": "Section Break"},
            {"fieldname": "source_line_count", "label": "Source Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "included_line_count", "label": "Included Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "excluded_line_count", "label": "Excluded Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "duplicate_line_count", "label": "Duplicate Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "blocked_line_count", "label": "Blocked Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "total_allocation_amount", "label": "Total Allocation Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "blocker_count", "label": "Blocker Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "warning_count", "label": "Warning Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "audit_section", "label": "Audit", "fieldtype": "Section Break"},
            {"fieldname": "created_on", "label": "Created On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "created_by_user", "label": "Created By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "cancelled_on", "label": "Cancelled On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "cancelled_by", "label": "Cancelled By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "validation_log", "label": "Validation Log", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
        ],
    )


def create_sandbox_payment_entry_run_line_doctype():
    _create_doctype(
        name="NDIS Sandbox Payment Entry Run Line",
        autoname="hash",
        title_field="line_label",
        fields=[
            {"fieldname": "sandbox_run", "label": "Sandbox Run", "fieldtype": "Link", "options": "NDIS Sandbox Payment Entry Run", "reqd": 1, "in_list_view": 1},
            {"fieldname": "allocation_preview_line", "label": "Allocation Preview Line", "fieldtype": "Link", "options": "NDIS Payment Entry Allocation Preview Line"},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nIncluded In Draft PE\nExcluded\nDuplicate\nBlocked\nCancelled", "default": "Excluded", "in_list_view": 1},
            {"fieldname": "line_no", "label": "Line No", "fieldtype": "Int", "in_list_view": 1},
            {"fieldname": "line_label", "label": "Line Label", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "sales_invoice", "label": "Sales Invoice", "fieldtype": "Link", "options": "Sales Invoice", "in_list_view": 1},
            {"fieldname": "customer", "label": "Customer", "fieldtype": "Link", "options": "Customer"},
            {"fieldname": "invoice_status", "label": "Invoice Status", "fieldtype": "Data"},
            {"fieldname": "receipt_amount", "label": "Receipt Amount", "fieldtype": "Currency"},
            {"fieldname": "allocation_amount", "label": "Allocation Amount", "fieldtype": "Currency", "in_list_view": 1},
            {"fieldname": "outstanding_amount", "label": "Outstanding Amount", "fieldtype": "Currency"},
            {"fieldname": "source_status", "label": "Source Status", "fieldtype": "Data"},
            {"fieldname": "decision", "label": "Decision", "fieldtype": "Data"},
            {"fieldname": "duplicate_key", "label": "Duplicate Key", "fieldtype": "Data"},
            {"fieldname": "block_reason", "label": "Block Reason", "fieldtype": "Small Text"},
            {"fieldname": "payment_entry_reference_created", "label": "Payment Entry Reference Created", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "preview_only_note", "label": "Preview Only Note", "fieldtype": "Small Text"},
        ],
    )


def create_payment_entry_custom_fields():
    create_custom_fields(PAYMENT_ENTRY_CUSTOM_FIELDS, update=True)


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
    if "Sandbox Payment Entry Adapter" not in text_blob:
        content.append({"id": "ndis_sandbox_payment_entry_adapter_heading", "type": "header", "data": {"text": "Sandbox Payment Entry Adapter", "col": 12}})
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
    pe_events_blob = json.dumps(doc_events.get("Payment Entry", {}), default=str)
    return {
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE3C_DOCTYPES},
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "payment_entry_custom_fields": {
            field["fieldname"]: bool(frappe.db.exists("Custom Field", {"dt": "Payment Entry", "fieldname": field["fieldname"]}))
            for field in PAYMENT_ENTRY_CUSTOM_FIELDS["Payment Entry"]
        },
        "permissions": {
            dt: frappe.get_all("DocPerm", filters={"parent": dt}, fields=["role", "read", "write", "create", "delete", "report", "export"], order_by="role asc")
            for dt in PHASE3C_DOCTYPES
        },
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "create_sandbox_payment_entry_draft": permission_matrix().get("create_sandbox_payment_entry_draft"),
            "cancel_sandbox_payment_entry_run": permission_matrix().get("cancel_sandbox_payment_entry_run"),
        },
        "js_hooks": {dt: dt in doctype_js for dt in PHASE3C_DOCTYPES},
        "list_js_hooks": {dt: dt in doctype_list_js for dt in PHASE3C_DOCTYPES},
        "payment_entry_submit_blocker_registered": "block_sandbox_payment_entry_submit" in pe_events_blob,
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "report_files": check_report_files(),
    }


def can_import_service():
    try:
        from ndis_finance.services.sandbox_payment_entry_posting import quick_sandbox_payment_entry_summary

        return callable(quick_sandbox_payment_entry_summary)
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
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            result[shortcut["label"]] = True
    return result
