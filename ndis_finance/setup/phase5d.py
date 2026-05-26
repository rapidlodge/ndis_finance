import json
import os

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


RUN_DOCTYPE = "NDIS PE Production Adapter Run"
LINE_DOCTYPE = "NDIS PE Production Adapter Run Line"

PHASE5D_DOCTYPES = [RUN_DOCTYPE, LINE_DOCTYPE]

REPORTS = [
    {"report_name": "NDIS PE Production Adapter Run Report", "ref_doctype": RUN_DOCTYPE},
    {"report_name": "NDIS PE Production Adapter Run Line Report", "ref_doctype": LINE_DOCTYPE},
    {"report_name": "NDIS PE Production Adapter Exception Report", "ref_doctype": LINE_DOCTYPE},
]

REPORT_ROLES = [
    "System Manager",
    "NDIS CFO",
    "NDIS Finance Manager",
    "NDIS Finance Officer",
    "NDIS Finance Read Only",
]

DOC_PERM_MATRIX = {
    RUN_DOCTYPE: {
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
    {"label": "PE Production Adapter Runs", "type": "DocType", "link_to": RUN_DOCTYPE},
    {"label": "PE Production Adapter Run Lines", "type": "DocType", "link_to": LINE_DOCTYPE},
    {"label": "PE Production Adapter Run Report", "type": "Report", "link_to": "NDIS PE Production Adapter Run Report"},
    {"label": "PE Production Adapter Exceptions", "type": "Report", "link_to": "NDIS PE Production Adapter Exception Report"},
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_adapter_run_doctype()
    create_adapter_line_doctype()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS PE Production Posting Preview",
        "NDIS PE Production Posting Preview Line",
        "NDIS PE Production Account Mapping Gate",
        "NDIS PE Production Design Gate",
        "NDIS PE Sandbox Readiness Freeze",
        "NDIS PE Production Posting Policy",
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
        frappe.throw(_("Phase 5D requires completed Phase 5C production posting preview. Missing: {0}").format(", ".join(missing)))


def create_adapter_run_doctype():
    _create_doctype(
        name=RUN_DOCTYPE,
        autoname="field:adapter_run_id",
        title_field="adapter_run_id",
        fields=[
            {"fieldname": "adapter_run_id", "label": "Adapter Run ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nHard Blocked\nNeeds Review\nBlocked\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "adapter_mode", "label": "Adapter Mode", "fieldtype": "Select", "options": "\nHard Block Shell\nFuture Controlled Live Adapter", "default": "Hard Block Shell", "in_list_view": 1},
            {"fieldname": "source_preview", "label": "Source Posting Preview", "fieldtype": "Link", "options": "NDIS PE Production Posting Preview", "in_list_view": 1},
            {"fieldname": "live_posting_allowed", "label": "Live Posting Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "future_activation_required", "label": "Future Activation Required", "fieldtype": "Check", "read_only": 1, "default": "1"},
            {"fieldname": "payment_entry_created", "label": "Payment Entry Created", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "source_section", "label": "Source / Account Controls", "fieldtype": "Section Break"},
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
            {"fieldname": "executed_on", "label": "Executed On", "fieldtype": "Datetime", "read_only": 1, "in_list_view": 1},
            {"fieldname": "executed_by", "label": "Executed By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "score_section", "label": "Adapter Score", "fieldtype": "Section Break"},
            {"fieldname": "adapter_score", "label": "Adapter Score", "fieldtype": "Percent", "read_only": 1, "in_list_view": 1},
            {"fieldname": "adapter_status", "label": "Adapter Status", "fieldtype": "Select", "options": "\nReady For Activation Gate Design\nReady With Warnings\nNeeds Review\nBlocked", "read_only": 1, "in_list_view": 1},
            {"fieldname": "blocker_count", "label": "Blocker Count", "fieldtype": "Int", "read_only": 1, "in_list_view": 1},
            {"fieldname": "warning_count", "label": "Warning Count", "fieldtype": "Int", "read_only": 1, "in_list_view": 1},
            {"fieldname": "pass_count", "label": "Pass Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "info_count", "label": "Info Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "line_count", "label": "Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "line_summary_section", "label": "Line Summary", "fieldtype": "Section Break"},
            {"fieldname": "hard_blocked_line_count", "label": "Hard-blocked Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "validation_blocked_line_count", "label": "Validation-blocked Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "duplicate_blocked_line_count", "label": "Duplicate-blocked Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "rejected_blocked_line_count", "label": "Rejected-blocked Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "would_create_payment_entry_count", "label": "Would Create PE Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "actual_payment_entry_created_count", "label": "Actual PE Created Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "preview_total_amount", "label": "Preview Total Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "adapter_blocked_amount", "label": "Adapter Blocked Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "prior_gate_section", "label": "Prior Gate Evidence", "fieldtype": "Section Break"},
            {"fieldname": "phase5c_preview_count", "label": "Phase 5C Preview Count", "fieldtype": "Int", "read_only": 1},
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


def create_adapter_line_doctype():
    _create_doctype(
        name=LINE_DOCTYPE,
        autoname="hash",
        title_field="scenario_key",
        fields=[
            {"fieldname": "adapter_run", "label": "Adapter Run", "fieldtype": "Link", "options": RUN_DOCTYPE, "reqd": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nHard Blocked\nValidation Blocked\nDuplicate Blocked\nRejected Blocked\nWarning\nInfo\nCancelled", "default": "Info", "in_list_view": 1},
            {"fieldname": "severity", "label": "Severity", "fieldtype": "Select", "options": "\nLow\nMedium\nHigh\nCritical", "default": "Low", "in_list_view": 1},
            {"fieldname": "source_section", "label": "Source Preview", "fieldtype": "Section Break"},
            {"fieldname": "source_preview_line", "label": "Source Preview Line", "fieldtype": "Link", "options": "NDIS PE Production Posting Preview Line"},
            {"fieldname": "scenario_key", "label": "Scenario Key", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "event_type", "label": "Event Type", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "claim_outcome", "label": "Claim Outcome", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "source_reference", "label": "Source Reference", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "sales_invoice", "label": "Sales Invoice", "fieldtype": "Link", "options": "Sales Invoice"},
            {"fieldname": "policy_section", "label": "Policy / Accounts", "fieldtype": "Section Break"},
            {"fieldname": "posting_policy", "label": "Posting Policy", "fieldtype": "Link", "options": "NDIS PE Production Posting Policy"},
            {"fieldname": "mapping_rule", "label": "Mapping Rule", "fieldtype": "Link", "options": "NDIS Payment Entry Mapping Rule"},
            {"fieldname": "policy_company", "label": "Policy Company", "fieldtype": "Link", "options": "Company"},
            {"fieldname": "allowed_bank_account", "label": "Allowed Bank Account", "fieldtype": "Link", "options": "Account"},
            {"fieldname": "allowed_receivable_account", "label": "Allowed Receivable Account", "fieldtype": "Link", "options": "Account"},
            {"fieldname": "amount_section", "label": "Amounts", "fieldtype": "Section Break"},
            {"fieldname": "preview_payment_amount", "label": "Preview Payment Amount", "fieldtype": "Currency"},
            {"fieldname": "shortfall_amount", "label": "Shortfall Amount", "fieldtype": "Currency"},
            {"fieldname": "adapter_blocked_amount", "label": "Adapter Blocked Amount", "fieldtype": "Currency"},
            {"fieldname": "control_section", "label": "Controls", "fieldtype": "Section Break"},
            {"fieldname": "would_create_payment_entry", "label": "Would Create Payment Entry", "fieldtype": "Check"},
            {"fieldname": "actual_payment_entry_created", "label": "Actual Payment Entry Created", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "attempted_payment_entry_name", "label": "Attempted Payment Entry Name", "fieldtype": "Data"},
            {"fieldname": "duplicate_detected", "label": "Duplicate Detected", "fieldtype": "Check"},
            {"fieldname": "cross_company_blocked", "label": "Cross-company Blocked", "fieldtype": "Check"},
            {"fieldname": "overpayment_blocked", "label": "Overpayment Blocked", "fieldtype": "Check"},
            {"fieldname": "negative_receipt_blocked", "label": "Negative Receipt Blocked", "fieldtype": "Check"},
            {"fieldname": "rejected_claim_blocked", "label": "Rejected Claim Blocked", "fieldtype": "Check"},
            {"fieldname": "future_activation_blocked", "label": "Future Activation Blocked", "fieldtype": "Check"},
            {"fieldname": "result_section", "label": "Result", "fieldtype": "Section Break"},
            {"fieldname": "block_reason", "label": "Block Reason", "fieldtype": "Small Text"},
            {"fieldname": "adapter_note", "label": "Adapter Note", "fieldtype": "Small Text"},
            {"fieldname": "checked_on", "label": "Checked On", "fieldtype": "Datetime", "read_only": 1},
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


def add_workspace_entry(content, entry):
    if entry["id"] not in {row.get("id") for row in content}:
        content.append(entry)


def add_shortcuts_to_content_json(ws):
    if not ws.meta.has_field("content"):
        return
    try:
        content = json.loads(ws.content or "[]")
    except Exception:
        content = []
    add_workspace_entry(content, {"id": "ndis_pe_production_adapter_heading", "type": "header", "data": {"text": "Production Payment Entry Adapter", "col": 12}})
    for shortcut in WORKSPACE_SHORTCUTS:
        add_workspace_entry(
            content,
            {
                "id": frappe.scrub(shortcut["label"]),
                "type": "shortcut",
                "data": {"label": shortcut["label"], "link_to": shortcut["link_to"], "type": shortcut["type"], "col": 3},
            },
        )
    ws.content = json.dumps(content)


@frappe.whitelist()
def health_check():
    hooks = frappe.get_hooks()
    doctype_js = hooks.get("doctype_js", {})
    doctype_list_js = hooks.get("doctype_list_js", {})
    return {
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE5D_DOCTYPES},
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "permissions": {
            dt: frappe.get_all(
                "DocPerm",
                filters={"parent": dt},
                fields=["role", "read", "write", "create", "delete", "report", "export"],
                order_by="role asc",
            )
            for dt in PHASE5D_DOCTYPES
        },
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_pe_production_adapter_hard_block": permission_matrix().get("run_pe_production_adapter_hard_block"),
            "cancel_pe_production_adapter_run": permission_matrix().get("cancel_pe_production_adapter_run"),
            "attempt_live_payment_entry_creation": permission_matrix().get("attempt_live_payment_entry_creation"),
        },
        "js_hooks": {RUN_DOCTYPE: RUN_DOCTYPE in doctype_js, LINE_DOCTYPE: LINE_DOCTYPE in doctype_js},
        "list_js_hooks": {RUN_DOCTYPE: RUN_DOCTYPE in doctype_list_js, LINE_DOCTYPE: LINE_DOCTYPE in doctype_list_js},
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_payment_entry_posting_config": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
        "report_files": check_report_files(),
    }


def can_import_service():
    try:
        from ndis_finance.services.pe_production_adapter_hard_block import quick_pe_production_adapter_summary

        return callable(quick_pe_production_adapter_summary)
    except Exception:
        return False


def check_workspace_shortcuts():
    ws_name = frappe.db.exists("Workspace", WORKSPACE_NAME) or frappe.db.exists("Workspace", {"label": WORKSPACE_NAME})
    result = {shortcut["label"]: False for shortcut in WORKSPACE_SHORTCUTS}
    if not ws_name:
        return result
    ws = frappe.get_doc("Workspace", ws_name)
    text_blob = ws.content or ""
    for shortcut in WORKSPACE_SHORTCUTS:
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            result[shortcut["label"]] = True
    return result


def check_report_files():
    app_path = frappe.get_app_path("ndis_finance")
    result = {}
    for report in REPORTS:
        folder = frappe.scrub(report["report_name"])
        base = f"{app_path}/ndis_finance/report/{folder}/{folder}"
        result[report["report_name"]] = {
            "python": os.path.exists(base + ".py"),
            "javascript": os.path.exists(base + ".js"),
            "init": os.path.exists(f"{app_path}/ndis_finance/report/{folder}/__init__.py"),
        }
    return result
