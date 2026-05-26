import json
import os

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


PREVIEW_DOCTYPE = "NDIS PE Production Posting Preview"
LINE_DOCTYPE = "NDIS PE Production Posting Preview Line"

PHASE5C_DOCTYPES = [PREVIEW_DOCTYPE, LINE_DOCTYPE]

REPORTS = [
    {"report_name": "NDIS PE Production Posting Preview Report", "ref_doctype": PREVIEW_DOCTYPE},
    {"report_name": "NDIS PE Production Posting Preview Line Report", "ref_doctype": LINE_DOCTYPE},
    {"report_name": "NDIS PE Production Posting Preview Exception Report", "ref_doctype": LINE_DOCTYPE},
]

REPORT_FILE_MAP = {
    "NDIS PE Production Posting Preview Report": "ndis_pe_production_posting_preview_report",
    "NDIS PE Production Posting Preview Line Report": "ndis_pe_production_posting_preview_line_report",
    "NDIS PE Production Posting Preview Exception Report": "ndis_pe_production_posting_preview_exception_report",
}

REPORT_ROLES = ["System Manager", "NDIS CFO", "NDIS Finance Manager", "NDIS Finance Officer", "NDIS Finance Read Only"]

DOC_PERM_MATRIX = {
    PREVIEW_DOCTYPE: {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
    LINE_DOCTYPE: {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
}

WORKSPACE_NAME = "NDIS Finance"
WORKSPACE_SHORTCUTS = [
    {"label": "PE Production Posting Previews", "type": "DocType", "link_to": PREVIEW_DOCTYPE},
    {"label": "PE Production Posting Preview Lines", "type": "DocType", "link_to": LINE_DOCTYPE},
    {"label": "PE Production Posting Preview Report", "type": "Report", "link_to": "NDIS PE Production Posting Preview Report"},
    {"label": "PE Production Posting Preview Exceptions", "type": "Report", "link_to": "NDIS PE Production Posting Preview Exception Report"},
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_preview_doctype()
    create_preview_line_doctype()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS PE Production Posting Policy",
        "NDIS PE Production Account Mapping Gate",
        "NDIS PE Production Design Gate",
        "NDIS PE Sandbox Readiness Freeze",
        "NDIS Payment Entry Mapping Rule",
        "Payment Entry",
        "GL Entry",
        "Account",
        "Company",
        "Report",
        "Workspace",
    ]
    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]
    if missing:
        frappe.throw(_("Phase 5C requires completed Phase 5B account mapping hardening. Missing: {0}").format(", ".join(missing)))


def create_preview_doctype():
    _create_doctype(
        name=PREVIEW_DOCTYPE,
        autoname="field:preview_id",
        title_field="preview_id",
        fields=[
            {"fieldname": "preview_id", "label": "Preview ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nPreviewed\nNeeds Review\nBlocked\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "preview_type", "label": "Preview Type", "fieldtype": "Select", "options": "\nProduction Control Scenario Preview\nProduction Remittance Preview", "default": "Production Control Scenario Preview", "in_list_view": 1},
            {"fieldname": "source_mode", "label": "Source Mode", "fieldtype": "Select", "options": "\nSynthetic Control Scenarios\nRemittance Import", "default": "Synthetic Control Scenarios", "in_list_view": 1},
            {"fieldname": "live_posting_allowed", "label": "Live Posting Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "payment_entry_created", "label": "Payment Entry Created", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "source_section", "label": "Source / Control", "fieldtype": "Section Break"},
            {"fieldname": "source_remittance_import", "label": "Source Remittance Import", "fieldtype": "Link", "options": "NDIS Remittance Import"},
            {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company", "in_list_view": 1},
            {"fieldname": "allowed_bank_account", "label": "Allowed Bank Account", "fieldtype": "Link", "options": "Account", "in_list_view": 1},
            {"fieldname": "allowed_receivable_account", "label": "Allowed Receivable Account", "fieldtype": "Link", "options": "Account", "in_list_view": 1},
            {"fieldname": "mapping_gate", "label": "Phase 5B Mapping Gate", "fieldtype": "Link", "options": "NDIS PE Production Account Mapping Gate"},
            {"fieldname": "design_gate", "label": "Phase 5A Design Gate", "fieldtype": "Link", "options": "NDIS PE Production Design Gate"},
            {"fieldname": "site_section", "label": "Site / Config", "fieldtype": "Section Break"},
            {"fieldname": "site_name", "label": "Site Name", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "sandbox_config_enabled", "label": "Sandbox Config Enabled", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "production_mode_detected", "label": "Production Mode Detected", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "live_payment_entry_posting_config", "label": "Live PE Posting Config", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "previewed_on", "label": "Previewed On", "fieldtype": "Datetime", "read_only": 1, "in_list_view": 1},
            {"fieldname": "previewed_by", "label": "Previewed By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "score_section", "label": "Preview Score", "fieldtype": "Section Break"},
            {"fieldname": "preview_score", "label": "Preview Score", "fieldtype": "Percent", "read_only": 1, "in_list_view": 1},
            {"fieldname": "preview_status", "label": "Preview Status", "fieldtype": "Select", "options": "\nReady For Controlled Live Adapter Design\nReady With Warnings\nNeeds Review\nBlocked", "read_only": 1, "in_list_view": 1},
            {"fieldname": "blocker_count", "label": "Blocker Count", "fieldtype": "Int", "read_only": 1, "in_list_view": 1},
            {"fieldname": "warning_count", "label": "Warning Count", "fieldtype": "Int", "read_only": 1, "in_list_view": 1},
            {"fieldname": "pass_count", "label": "Pass Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "info_count", "label": "Info Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "line_count", "label": "Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "line_summary_section", "label": "Line Summary", "fieldtype": "Section Break"},
            {"fieldname": "eligible_line_count", "label": "Eligible Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "blocked_line_count", "label": "Blocked Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "duplicate_line_count", "label": "Duplicate Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "paid_line_count", "label": "Paid Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "short_paid_line_count", "label": "Short-paid Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "rejected_line_count", "label": "Rejected Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "preview_total_amount", "label": "Preview Total Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "shortfall_total_amount", "label": "Shortfall Total Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "prior_gate_section", "label": "Prior Gate Evidence", "fieldtype": "Section Break"},
            {"fieldname": "phase5b_hardened_gate_count", "label": "Phase 5B Hardened Gate Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "phase5a_approved_gate_count", "label": "Phase 5A Approved Gate Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "phase4d_ready_freeze_count", "label": "Phase 4D Ready Freeze Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "guardrail_section", "label": "Strict Guardrails", "fieldtype": "Section Break"},
            {"fieldname": "payment_entry_count_before", "label": "Payment Entry Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_count_after", "label": "Payment Entry Count After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "submitted_payment_entry_count_today", "label": "Submitted PE Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_count", "label": "Payment Entry GL Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_count_today", "label": "Payment Entry GL Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "submitted_journal_entry_count_today", "label": "Submitted JE Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "purchase_invoice_count_today", "label": "Purchase Invoice Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "ack_section", "label": "Acknowledgement", "fieldtype": "Section Break"},
            {"fieldname": "required_acknowledgement", "label": "Required Acknowledgement", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "acknowledgement", "label": "Acknowledgement", "fieldtype": "Data"},
            {"fieldname": "acknowledgement_ok", "label": "Acknowledgement OK", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "audit_section", "label": "Audit", "fieldtype": "Section Break"},
            {"fieldname": "cancelled_on", "label": "Cancelled On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "cancelled_by", "label": "Cancelled By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "summary_json", "label": "Summary JSON", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
        ],
    )


def create_preview_line_doctype():
    _create_doctype(
        name=LINE_DOCTYPE,
        autoname="hash",
        title_field="scenario_key",
        fields=[
            {"fieldname": "posting_preview", "label": "Posting Preview", "fieldtype": "Link", "options": PREVIEW_DOCTYPE, "reqd": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nPreview Eligible\nBlocked\nDuplicate\nWarning\nInfo\nCancelled", "default": "Info", "in_list_view": 1},
            {"fieldname": "severity", "label": "Severity", "fieldtype": "Select", "options": "\nLow\nMedium\nHigh\nCritical", "default": "Low", "in_list_view": 1},
            {"fieldname": "scenario_section", "label": "Scenario", "fieldtype": "Section Break"},
            {"fieldname": "scenario_key", "label": "Scenario Key", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "event_type", "label": "Event Type", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "claim_outcome", "label": "Claim Outcome", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "source_reference", "label": "Source Reference", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "sales_invoice", "label": "Sales Invoice", "fieldtype": "Link", "options": "Sales Invoice"},
            {"fieldname": "source_company", "label": "Source Company", "fieldtype": "Data"},
            {"fieldname": "participant_reference", "label": "Participant Reference", "fieldtype": "Data"},
            {"fieldname": "policy_section", "label": "Policy / Accounts", "fieldtype": "Section Break"},
            {"fieldname": "posting_policy", "label": "Posting Policy", "fieldtype": "Link", "options": "NDIS PE Production Posting Policy", "in_list_view": 1},
            {"fieldname": "posting_decision", "label": "Posting Decision", "fieldtype": "Data"},
            {"fieldname": "mapping_rule", "label": "Mapping Rule", "fieldtype": "Link", "options": "NDIS Payment Entry Mapping Rule"},
            {"fieldname": "policy_company", "label": "Policy Company", "fieldtype": "Link", "options": "Company"},
            {"fieldname": "allowed_bank_account", "label": "Allowed Bank Account", "fieldtype": "Link", "options": "Account"},
            {"fieldname": "allowed_receivable_account", "label": "Allowed Receivable Account", "fieldtype": "Link", "options": "Account"},
            {"fieldname": "amount_section", "label": "Amounts", "fieldtype": "Section Break"},
            {"fieldname": "invoice_amount", "label": "Invoice Amount", "fieldtype": "Currency"},
            {"fieldname": "paid_amount", "label": "Paid Amount", "fieldtype": "Currency"},
            {"fieldname": "preview_payment_amount", "label": "Preview Payment Amount", "fieldtype": "Currency"},
            {"fieldname": "shortfall_amount", "label": "Shortfall Amount", "fieldtype": "Currency"},
            {"fieldname": "overpayment_amount", "label": "Overpayment Amount", "fieldtype": "Currency"},
            {"fieldname": "control_section", "label": "Controls", "fieldtype": "Section Break"},
            {"fieldname": "would_create_payment_entry", "label": "Would Create Payment Entry", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "actual_payment_entry_created", "label": "Actual Payment Entry Created", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "duplicate_key", "label": "Duplicate Key", "fieldtype": "Data"},
            {"fieldname": "duplicate_detected", "label": "Duplicate Detected", "fieldtype": "Check"},
            {"fieldname": "cross_company_blocked", "label": "Cross-company Blocked", "fieldtype": "Check"},
            {"fieldname": "overpayment_blocked", "label": "Overpayment Blocked", "fieldtype": "Check"},
            {"fieldname": "negative_receipt_blocked", "label": "Negative Receipt Blocked", "fieldtype": "Check"},
            {"fieldname": "rejected_claim_blocked", "label": "Rejected Claim Blocked", "fieldtype": "Check"},
            {"fieldname": "result_section", "label": "Result", "fieldtype": "Section Break"},
            {"fieldname": "block_reason", "label": "Block Reason", "fieldtype": "Small Text"},
            {"fieldname": "preview_note", "label": "Preview Note", "fieldtype": "Small Text"},
            {"fieldname": "checked_on", "label": "Checked On", "fieldtype": "Datetime", "read_only": 1},
        ],
    )


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
    if "Production Payment Entry Posting Preview" not in text_blob:
        content.append({"id": "ndis_pe_production_posting_preview_heading", "type": "header", "data": {"text": "Production Payment Entry Posting Preview", "col": 12}})
    for shortcut in WORKSPACE_SHORTCUTS:
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            continue
        content.append({"id": frappe.scrub(shortcut["label"]), "type": "shortcut", "data": {"label": shortcut["label"], "link_to": shortcut["link_to"], "type": shortcut["type"], "col": 3}})
    ws.content = json.dumps(content)


@frappe.whitelist()
def health_check():
    hooks = frappe.get_hooks()
    doctype_js = hooks.get("doctype_js", {})
    doctype_list_js = hooks.get("doctype_list_js", {})
    return {
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE5C_DOCTYPES},
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "permissions": {
            dt: frappe.get_all("DocPerm", filters={"parent": dt}, fields=["role", "read", "write", "create", "delete", "report", "export"], order_by="role asc")
            for dt in PHASE5C_DOCTYPES
        },
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_pe_production_posting_preview": permission_matrix().get("run_pe_production_posting_preview"),
            "cancel_pe_production_posting_preview": permission_matrix().get("cancel_pe_production_posting_preview"),
        },
        "js_hooks": {dt: dt in doctype_js for dt in PHASE5C_DOCTYPES},
        "list_js_hooks": {dt: dt in doctype_list_js for dt in PHASE5C_DOCTYPES},
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_payment_entry_posting_config": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
        "report_files": check_report_files(),
    }


def can_import_service():
    try:
        from ndis_finance.services.pe_production_posting_preview import quick_pe_production_posting_preview_summary

        return callable(quick_pe_production_posting_preview_summary)
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
