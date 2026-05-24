import json
import os

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


CLEANUP_PACK_DOCTYPE = "NDIS Sandbox Accounting Cleanup Pack"
CLEANUP_LINE_DOCTYPE = "NDIS Sandbox Accounting Cleanup Pack Line"

PHASE4C_DOCTYPES = [CLEANUP_PACK_DOCTYPE, CLEANUP_LINE_DOCTYPE]

REPORTS = [
    {"report_name": "NDIS Sandbox Accounting Cleanup Pack Report", "ref_doctype": CLEANUP_PACK_DOCTYPE},
    {"report_name": "NDIS Sandbox Accounting Cleanup Line Report", "ref_doctype": CLEANUP_LINE_DOCTYPE},
    {"report_name": "NDIS Sandbox Accounting Hygiene Report", "ref_doctype": "Sales Invoice"},
]

REPORT_FILE_MAP = {
    "NDIS Sandbox Accounting Cleanup Pack Report": "ndis_sandbox_accounting_cleanup_pack_report",
    "NDIS Sandbox Accounting Cleanup Line Report": "ndis_sandbox_accounting_cleanup_line_report",
    "NDIS Sandbox Accounting Hygiene Report": "ndis_sandbox_accounting_hygiene_report",
}

REPORT_ROLES = ["System Manager", "NDIS CFO", "NDIS Finance Manager", "NDIS Finance Officer", "NDIS Finance Read Only"]

DOC_PERM_MATRIX = {
    CLEANUP_PACK_DOCTYPE: {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
    CLEANUP_LINE_DOCTYPE: {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
}

WORKSPACE_NAME = "NDIS Finance"
WORKSPACE_SHORTCUTS = [
    {"label": "Sandbox Accounting Cleanup Packs", "type": "DocType", "link_to": CLEANUP_PACK_DOCTYPE},
    {"label": "Sandbox Accounting Cleanup Lines", "type": "DocType", "link_to": CLEANUP_LINE_DOCTYPE},
    {"label": "Sandbox Accounting Cleanup Report", "type": "Report", "link_to": "NDIS Sandbox Accounting Cleanup Pack Report"},
    {"label": "Sandbox Accounting Hygiene Report", "type": "Report", "link_to": "NDIS Sandbox Accounting Hygiene Report"},
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_cleanup_pack_doctype()
    create_cleanup_line_doctype()
    harden_existing_schema()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Invoice Backed PE Smoke Run",
        "NDIS Invoice Backed PE Smoke Line",
        "NDIS Sandbox Invoice Test Run",
        "NDIS Sandbox Payment Entry Run",
        "NDIS Payment Entry Sandbox Completion Gate",
        "Payment Entry",
        "Sales Invoice",
        "GL Entry",
        "Report",
        "Workspace",
    ]
    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]

    if missing:
        frappe.throw(_("Phase 4C requires Phase 4B and sandbox accounting evidence. Missing: {0}").format(", ".join(missing)))


def create_cleanup_pack_doctype():
    _create_doctype(
        name=CLEANUP_PACK_DOCTYPE,
        autoname="field:pack_id",
        title_field="pack_id",
        fields=[
            {"fieldname": "pack_id", "label": "Pack ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nPreviewed\nCleaned\nBlocked\nCancelled\nFailed", "default": "Draft", "in_list_view": 1},
            {"fieldname": "cleanup_scope", "label": "Cleanup Scope", "fieldtype": "Select", "options": "\nPayment Entry Drafts + Submitted Sandbox Invoices\nPayment Entry Drafts Only\nSubmitted Sandbox Invoices Only", "default": "Payment Entry Drafts + Submitted Sandbox Invoices", "in_list_view": 1},
            {"fieldname": "sandbox_only", "label": "Sandbox Only", "fieldtype": "Check", "default": "1", "read_only": 1},
            {"fieldname": "target_section", "label": "Targets", "fieldtype": "Section Break"},
            {"fieldname": "target_payment_entry", "label": "Target Draft Payment Entry", "fieldtype": "Link", "options": "Payment Entry"},
            {"fieldname": "target_sales_invoice", "label": "Target Submitted Sales Invoice", "fieldtype": "Link", "options": "Sales Invoice"},
            {"fieldname": "cleanup_payment_entries", "label": "Cleanup Draft Sandbox Payment Entries", "fieldtype": "Check", "default": "1"},
            {"fieldname": "cancel_submitted_invoices", "label": "Cancel Submitted Sandbox Sales Invoices", "fieldtype": "Check", "default": "1"},
            {"fieldname": "control_section", "label": "Controls", "fieldtype": "Section Break"},
            {"fieldname": "site_name", "label": "Site Name", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "sandbox_config_enabled", "label": "Sandbox Config Enabled", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "production_mode_detected", "label": "Production Mode Detected", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "required_acknowledgement", "label": "Required Acknowledgement", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "acknowledgement", "label": "Acknowledgement", "fieldtype": "Data"},
            {"fieldname": "acknowledgement_ok", "label": "Acknowledgement OK", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "summary_section", "label": "Summary", "fieldtype": "Section Break"},
            {"fieldname": "candidate_payment_entry_count", "label": "Candidate PE Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "deleted_payment_entry_count", "label": "Deleted PE Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "blocked_payment_entry_count", "label": "Blocked PE Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "candidate_sales_invoice_count", "label": "Candidate SI Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "cancelled_sales_invoice_count", "label": "Cancelled SI Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "blocked_sales_invoice_count", "label": "Blocked SI Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_count", "label": "Payment Entry GL Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "sales_invoice_gl_count_before", "label": "SI GL Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "sales_invoice_gl_count_after", "label": "SI GL Count After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "sandbox_si_gl_net_after", "label": "Sandbox SI GL Net After", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "blocker_count", "label": "Blocker Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "warning_count", "label": "Warning Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "guardrail_section", "label": "Strict Guardrails", "fieldtype": "Section Break"},
            {"fieldname": "submitted_sandbox_pe_count", "label": "Submitted Sandbox PE Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "submitted_payment_entry_count_today", "label": "Submitted PE Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_count_today", "label": "Payment Entry GL Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "submitted_journal_entry_count_today", "label": "Submitted JE Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "purchase_invoice_count_today", "label": "Purchase Invoice Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "audit_section", "label": "Audit", "fieldtype": "Section Break"},
            {"fieldname": "created_on", "label": "Created On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "created_by_user", "label": "Created By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "cancelled_on", "label": "Cancelled On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "cancelled_by", "label": "Cancelled By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "validation_log", "label": "Validation Log", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
        ],
    )


def create_cleanup_line_doctype():
    _create_doctype(
        name=CLEANUP_LINE_DOCTYPE,
        autoname="hash",
        title_field="record_name",
        fields=[
            {"fieldname": "cleanup_pack", "label": "Cleanup Pack", "fieldtype": "Link", "options": CLEANUP_PACK_DOCTYPE, "reqd": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nCandidate\nEligible\nDeleted\nCancelled\nBlocked\nWarning\nInfo", "default": "Candidate", "in_list_view": 1},
            {"fieldname": "severity", "label": "Severity", "fieldtype": "Select", "options": "\nLow\nMedium\nHigh\nCritical", "default": "Low", "in_list_view": 1},
            {"fieldname": "action_type", "label": "Action Type", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "record_doctype", "label": "Record DocType", "fieldtype": "Link", "options": "DocType", "in_list_view": 1},
            {"fieldname": "record_name", "label": "Record Name", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "record_exists_before", "label": "Exists Before", "fieldtype": "Check"},
            {"fieldname": "record_exists_after", "label": "Exists After", "fieldtype": "Check"},
            {"fieldname": "docstatus_before", "label": "Docstatus Before", "fieldtype": "Int"},
            {"fieldname": "docstatus_after", "label": "Docstatus After", "fieldtype": "Int"},
            {"fieldname": "linked_gl_count_before", "label": "Linked GL Before", "fieldtype": "Int"},
            {"fieldname": "linked_gl_count_after", "label": "Linked GL After", "fieldtype": "Int"},
            {"fieldname": "gl_net_after", "label": "GL Net After", "fieldtype": "Currency"},
            {"fieldname": "amount", "label": "Amount", "fieldtype": "Currency"},
            {"fieldname": "block_reason", "label": "Block Reason", "fieldtype": "Small Text"},
            {"fieldname": "action_taken", "label": "Action Taken", "fieldtype": "Small Text"},
        ],
    )


def harden_existing_schema():
    if not frappe.db.exists("DocType", CLEANUP_LINE_DOCTYPE):
        return

    doc = frappe.get_doc("DocType", CLEANUP_LINE_DOCTYPE)
    changed = False

    for field in doc.fields:
        if field.fieldname == "record_name":
            if field.fieldtype != "Data":
                field.fieldtype = "Data"
                changed = True
            if field.options:
                field.options = None
                changed = True

    if changed:
        doc.save(ignore_permissions=True)

    frappe.db.set_value(
        "DocField",
        {"parent": CLEANUP_LINE_DOCTYPE, "fieldname": "record_name"},
        "options",
        None,
        update_modified=False,
    )
    frappe.clear_cache(doctype=CLEANUP_LINE_DOCTYPE)


def create_reports():
    for report in REPORTS:
        ensure_script_report(report["report_name"], report["ref_doctype"])


def ensure_script_report(report_name, ref_doctype):
    existing = frappe.db.exists("Report", report_name)
    doc = frappe.get_doc("Report", existing) if existing else frappe.new_doc("Report")
    if not existing:
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
    ws.save(ignore_permissions=True)


def add_shortcuts_to_content_json(ws):
    if not ws.meta.has_field("content"):
        return
    try:
        content = json.loads(ws.content or "[]")
    except Exception:
        content = []
    text_blob = json.dumps(content)
    if "Sandbox Accounting Cleanup Pack" not in text_blob:
        content.append({"id": "ndis_sandbox_accounting_cleanup_pack_heading", "type": "header", "data": {"text": "Sandbox Accounting Cleanup Pack", "col": 12}})
    for shortcut in WORKSPACE_SHORTCUTS:
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            continue
        content.append({"id": frappe.scrub(shortcut["label"]), "type": "shortcut", "data": {"label": shortcut["label"], "link_to": shortcut["link_to"], "type": shortcut["type"], "col": 3}})
    ws.content = json.dumps(content)


@frappe.whitelist()
def health_check():
    doctypes = {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE4C_DOCTYPES}
    reports = {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS}
    permissions = {}
    for dt in PHASE4C_DOCTYPES:
        permissions[dt] = frappe.get_all("DocPerm", filters={"parent": dt}, fields=["role", "read", "write", "create", "delete", "report", "export"], order_by="role asc")
    hooks = frappe.get_hooks()
    doctype_js = hooks.get("doctype_js", {})
    doctype_list_js = hooks.get("doctype_list_js", {})
    doc_events = hooks.get("doc_events", {}) or {}
    pe_events_blob = json.dumps(doc_events.get("Payment Entry", {}), default=str)
    si_events_blob = json.dumps(doc_events.get("Sales Invoice", {}), default=str)
    return {
        "doctypes": doctypes,
        "reports": reports,
        "permissions": permissions,
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_sandbox_accounting_cleanup_pack": permission_matrix().get("run_sandbox_accounting_cleanup_pack"),
            "cancel_sandbox_accounting_cleanup_pack": permission_matrix().get("cancel_sandbox_accounting_cleanup_pack"),
        },
        "js_hooks": {
            CLEANUP_PACK_DOCTYPE: CLEANUP_PACK_DOCTYPE in doctype_js,
            CLEANUP_LINE_DOCTYPE: CLEANUP_LINE_DOCTYPE in doctype_js,
        },
        "list_js_hooks": {
            CLEANUP_PACK_DOCTYPE: CLEANUP_PACK_DOCTYPE in doctype_list_js,
            CLEANUP_LINE_DOCTYPE: CLEANUP_LINE_DOCTYPE in doctype_list_js,
        },
        "payment_entry_submit_blocker_still_registered": "block_sandbox_payment_entry_submit" in pe_events_blob,
        "sales_invoice_submit_safety_still_registered": "block_unacknowledged_sandbox_sales_invoice_submit" in si_events_blob,
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "report_files": check_report_files(),
    }


def can_import_service():
    try:
        from ndis_finance.services.sandbox_accounting_cleanup_pack import quick_sandbox_accounting_cleanup_summary

        return callable(quick_sandbox_accounting_cleanup_summary)
    except Exception:
        return False


def check_workspace_shortcuts():
    ws_name = frappe.db.exists("Workspace", WORKSPACE_NAME) or frappe.db.exists("Workspace", {"label": WORKSPACE_NAME})
    result = {shortcut["label"]: False for shortcut in WORKSPACE_SHORTCUTS}
    if not ws_name:
        return result
    ws = frappe.get_doc("Workspace", ws_name)
    text_blob = getattr(ws, "content", None) or ""
    for shortcut in WORKSPACE_SHORTCUTS:
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            result[shortcut["label"]] = True
    return result


def check_report_files():
    base_path = frappe.get_app_path("ndis_finance", "ndis_finance", "report")
    result = {}
    for report_name, folder in REPORT_FILE_MAP.items():
        folder_path = os.path.join(base_path, folder)
        result[report_name] = {
            "python": os.path.exists(os.path.join(folder_path, f"{folder}.py")),
            "javascript": os.path.exists(os.path.join(folder_path, f"{folder}.js")),
            "init": os.path.exists(os.path.join(folder_path, "__init__.py")),
        }
    return result
