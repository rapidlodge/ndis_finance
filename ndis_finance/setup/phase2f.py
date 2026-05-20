import json
import os

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


PHASE2F_DOCTYPES = [
    "NDIS Accounting Sandbox Completion Gate",
    "NDIS Accounting Sandbox Completion Gate Item",
]

REPORTS = [
    {"report_name": "NDIS Accounting Sandbox Completion Gate Report", "ref_doctype": "NDIS Accounting Sandbox Completion Gate"},
    {"report_name": "NDIS Accounting Sandbox Completion Exception Report", "ref_doctype": "NDIS Accounting Sandbox Completion Gate Item"},
]

REPORT_FILE_MAP = {
    "NDIS Accounting Sandbox Completion Gate Report": "ndis_accounting_sandbox_completion_gate_report",
    "NDIS Accounting Sandbox Completion Exception Report": "ndis_accounting_sandbox_completion_exception_report",
}

REPORT_ROLES = ["System Manager", "NDIS CFO", "NDIS Finance Manager", "NDIS Finance Officer", "NDIS Finance Read Only"]

DOC_PERM_MATRIX = {
    "NDIS Accounting Sandbox Completion Gate": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Accounting Sandbox Completion Gate Item": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
}

WORKSPACE_NAME = "NDIS Finance"

WORKSPACE_SHORTCUTS = [
    {"label": "Sandbox Completion Gates", "type": "DocType", "link_to": "NDIS Accounting Sandbox Completion Gate"},
    {"label": "Sandbox Completion Items", "type": "DocType", "link_to": "NDIS Accounting Sandbox Completion Gate Item"},
    {"label": "Sandbox Completion Gate Report", "type": "Report", "link_to": "NDIS Accounting Sandbox Completion Gate Report"},
    {"label": "Sandbox Completion Exceptions", "type": "Report", "link_to": "NDIS Accounting Sandbox Completion Exception Report"},
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_gate_doctype()
    create_gate_item_doctype()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Finance Production Readiness Check",
        "NDIS Accounting Posting Policy",
        "NDIS Accounting Posting Preview",
        "NDIS Accounting Posting Request",
        "NDIS Accounting Posting Request Line",
        "NDIS Sandbox Accounting Posting Run",
        "NDIS Sandbox Accounting Posting Run Line",
        "NDIS Sandbox Accounting Cleanup Run",
        "NDIS Sandbox Accounting Cleanup Line",
        "Journal Entry",
        "Report",
        "Workspace",
    ]
    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]
    if missing:
        frappe.throw(_("Phase 2F requires completed Phase 2A to 2E. Missing DocTypes: {0}").format(", ".join(missing)))


def create_gate_doctype():
    _create_doctype(
        name="NDIS Accounting Sandbox Completion Gate",
        autoname="field:gate_id",
        title_field="gate_id",
        fields=[
            {"fieldname": "gate_id", "label": "Gate ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "gate_type", "label": "Gate Type", "fieldtype": "Select", "options": "\nAccounting Sandbox Completion\nPre Live-Posting Design Review", "default": "Accounting Sandbox Completion", "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nPassed\nNeeds Review\nBlocked\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "sandbox_completion_allowed", "label": "Sandbox Completion Allowed", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "site_section", "label": "Site / Config", "fieldtype": "Section Break"},
            {"fieldname": "site_name", "label": "Site Name", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "sandbox_config_enabled", "label": "Sandbox Config Enabled", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "production_mode_detected", "label": "Production Mode Detected", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "checked_on", "label": "Checked On", "fieldtype": "Datetime", "read_only": 1, "in_list_view": 1},
            {"fieldname": "checked_by", "label": "Checked By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "summary_section", "label": "Summary", "fieldtype": "Section Break"},
            {"fieldname": "blocker_count", "label": "Blocker Count", "fieldtype": "Int", "read_only": 1, "in_list_view": 1},
            {"fieldname": "warning_count", "label": "Warning Count", "fieldtype": "Int", "read_only": 1, "in_list_view": 1},
            {"fieldname": "pass_count", "label": "Pass Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "info_count", "label": "Info Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "item_count", "label": "Item Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "score_section", "label": "Sandbox Completion Score", "fieldtype": "Section Break"},
            {"fieldname": "completion_score", "label": "Completion Score", "fieldtype": "Percent", "read_only": 1},
            {"fieldname": "completion_status", "label": "Completion Status", "fieldtype": "Select", "options": "\nComplete\nWatch\nNeeds Cleanup\nBlocked", "read_only": 1, "in_list_view": 1},
            {"fieldname": "evidence_section", "label": "Evidence Counts", "fieldtype": "Section Break"},
            {"fieldname": "active_policy_count", "label": "Active Policy Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "allowed_readiness_check_count", "label": "Allowed Readiness Check Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "signed_governance_pack_count", "label": "Signed Governance Pack Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "approved_dry_run_request_count", "label": "Approved Dry-run Request Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "sandbox_draft_je_run_count", "label": "Sandbox Draft JE Run Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "cleaned_cleanup_run_count", "label": "Cleaned Cleanup Run Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "hygiene_section", "label": "Sandbox Hygiene", "fieldtype": "Section Break"},
            {"fieldname": "draft_sandbox_je_count", "label": "Draft Sandbox JE Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "submitted_sandbox_je_count", "label": "Submitted Sandbox JE Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "sandbox_gl_entry_count", "label": "Sandbox GL Entry Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "stale_draft_sandbox_je_count", "label": "Stale Draft Sandbox JE Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "unsafe_policy_count", "label": "Unsafe Policy Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "movement_section", "label": "Accounting Movement Guardrails", "fieldtype": "Section Break"},
            {"fieldname": "payment_entry_count_today", "label": "Payment Entry Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "submitted_journal_entry_count_today", "label": "Submitted JE Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "gl_entry_count_today", "label": "GL Entry Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "sales_invoice_count_today", "label": "Sales Invoice Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "purchase_invoice_count_today", "label": "Purchase Invoice Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "ack_section", "label": "Acknowledgement Gate", "fieldtype": "Section Break"},
            {"fieldname": "required_acknowledgement", "label": "Required Acknowledgement", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "acknowledgement", "label": "Acknowledgement", "fieldtype": "Data"},
            {"fieldname": "acknowledgement_ok", "label": "Acknowledgement OK", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "audit_section", "label": "Audit", "fieldtype": "Section Break"},
            {"fieldname": "cancelled_on", "label": "Cancelled On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "cancelled_by", "label": "Cancelled By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "summary_json", "label": "Summary JSON", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "warning_log", "label": "Warning Log", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
        ],
    )


def create_gate_item_doctype():
    _create_doctype(
        name="NDIS Accounting Sandbox Completion Gate Item",
        autoname="hash",
        title_field="check_label",
        fields=[
            {"fieldname": "completion_gate", "label": "Completion Gate", "fieldtype": "Link", "options": "NDIS Accounting Sandbox Completion Gate", "reqd": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nPass\nWarning\nBlocker\nInfo\nCancelled", "default": "Info", "in_list_view": 1},
            {"fieldname": "severity", "label": "Severity", "fieldtype": "Select", "options": "\nLow\nMedium\nHigh\nCritical", "default": "Low", "in_list_view": 1},
            {"fieldname": "category", "label": "Category", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "check_key", "label": "Check Key", "fieldtype": "Data"},
            {"fieldname": "check_label", "label": "Check Label", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "detail", "label": "Detail", "fieldtype": "Small Text"},
            {"fieldname": "recommendation", "label": "Recommendation", "fieldtype": "Small Text"},
            {"fieldname": "source_section", "label": "Source", "fieldtype": "Section Break"},
            {"fieldname": "source_doctype", "label": "Source DocType", "fieldtype": "Link", "options": "DocType"},
            {"fieldname": "source_name", "label": "Source Name", "fieldtype": "Dynamic Link", "options": "source_doctype"},
            {"fieldname": "checked_on", "label": "Checked On", "fieldtype": "Datetime", "read_only": 1},
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
    if "Accounting Sandbox Completion" not in text_blob:
        content.append({"id": "ndis_accounting_sandbox_completion_heading", "type": "header", "data": {"text": "Accounting Sandbox Completion", "col": 12}})
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
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE2F_DOCTYPES},
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "permissions": {
            dt: frappe.get_all("DocPerm", filters={"parent": dt}, fields=["role", "read", "write", "create", "delete", "report", "export"], order_by="role asc")
            for dt in PHASE2F_DOCTYPES
        },
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_accounting_sandbox_completion_gate": permission_matrix().get("run_accounting_sandbox_completion_gate"),
            "cancel_accounting_sandbox_completion_gate": permission_matrix().get("cancel_accounting_sandbox_completion_gate"),
        },
        "js_hooks": {
            "NDIS Accounting Sandbox Completion Gate": "NDIS Accounting Sandbox Completion Gate" in doctype_js,
            "NDIS Accounting Sandbox Completion Gate Item": "NDIS Accounting Sandbox Completion Gate Item" in doctype_js,
        },
        "list_js_hooks": {
            "NDIS Accounting Sandbox Completion Gate": "NDIS Accounting Sandbox Completion Gate" in doctype_list_js,
            "NDIS Accounting Sandbox Completion Gate Item": "NDIS Accounting Sandbox Completion Gate Item" in doctype_list_js,
        },
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "report_files": check_report_files(),
    }


def can_import_service():
    try:
        from ndis_finance.services.accounting_sandbox_completion import quick_accounting_sandbox_completion_summary

        return callable(quick_accounting_sandbox_completion_summary)
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
