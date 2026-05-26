import json
import os

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


GATE_DOCTYPE = "NDIS PE Production Activation Gate"
ITEM_DOCTYPE = "NDIS PE Production Activation Gate Item"

PHASE5E_DOCTYPES = [GATE_DOCTYPE, ITEM_DOCTYPE]

REPORTS = [
    {"report_name": "NDIS PE Production Activation Gate Report", "ref_doctype": GATE_DOCTYPE},
    {"report_name": "NDIS PE Production Activation Exception Report", "ref_doctype": ITEM_DOCTYPE},
    {"report_name": "NDIS PE Production Activation Policy Readiness Report", "ref_doctype": "NDIS PE Production Posting Policy"},
]

REPORT_ROLES = ["System Manager", "NDIS CFO", "NDIS Finance Manager", "NDIS Finance Officer", "NDIS Finance Read Only"]

DOC_PERM_MATRIX = {
    GATE_DOCTYPE: {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
    ITEM_DOCTYPE: {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
}

WORKSPACE_NAME = "NDIS Finance"

WORKSPACE_SHORTCUTS = [
    {"label": "PE Production Activation Gates", "type": "DocType", "link_to": GATE_DOCTYPE},
    {"label": "PE Production Activation Gate Items", "type": "DocType", "link_to": ITEM_DOCTYPE},
    {"label": "PE Production Activation Gate Report", "type": "Report", "link_to": "NDIS PE Production Activation Gate Report"},
    {"label": "PE Production Activation Exceptions", "type": "Report", "link_to": "NDIS PE Production Activation Exception Report"},
    {"label": "PE Activation Policy Readiness", "type": "Report", "link_to": "NDIS PE Production Activation Policy Readiness Report"},
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_activation_gate_doctype()
    create_activation_gate_item_doctype()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS PE Production Adapter Run",
        "NDIS PE Production Adapter Run Line",
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
        frappe.throw(_("Phase 5E requires completed Phase 5D adapter hard block. Missing: {0}").format(", ".join(missing)))


def create_activation_gate_doctype():
    _create_doctype(
        name=GATE_DOCTYPE,
        autoname="field:activation_gate_id",
        title_field="activation_gate_id",
        fields=[
            {"fieldname": "activation_gate_id", "label": "Activation Gate ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nActivation Allowed\nNeeds Review\nBlocked\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "gate_type", "label": "Gate Type", "fieldtype": "Select", "options": "\nProduction Payment Entry Activation Readiness\nSingle-record Live Smoke Readiness", "default": "Production Payment Entry Activation Readiness", "in_list_view": 1},
            {"fieldname": "production_activation_allowed", "label": "Production Activation Allowed", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "ready_for_single_record_live_smoke", "label": "Ready For Single-record Live Smoke", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "live_posting_allowed", "label": "Live Posting Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "payment_entry_created", "label": "Payment Entry Created", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "account_section", "label": "Production Account Controls", "fieldtype": "Section Break"},
            {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company", "in_list_view": 1},
            {"fieldname": "allowed_bank_account", "label": "Allowed Bank Account", "fieldtype": "Link", "options": "Account", "in_list_view": 1},
            {"fieldname": "allowed_receivable_account", "label": "Allowed Receivable Account", "fieldtype": "Link", "options": "Account", "in_list_view": 1},
            {"fieldname": "bank_account_type", "label": "Bank Account Type", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "receivable_account_type", "label": "Receivable Account Type", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "source_section", "label": "Prior Evidence", "fieldtype": "Section Break"},
            {"fieldname": "source_adapter_run", "label": "Phase 5D Adapter Run", "fieldtype": "Link", "options": "NDIS PE Production Adapter Run"},
            {"fieldname": "source_preview", "label": "Phase 5C Posting Preview", "fieldtype": "Link", "options": "NDIS PE Production Posting Preview"},
            {"fieldname": "mapping_gate", "label": "Phase 5B Mapping Gate", "fieldtype": "Link", "options": "NDIS PE Production Account Mapping Gate"},
            {"fieldname": "design_gate", "label": "Phase 5A Design Gate", "fieldtype": "Link", "options": "NDIS PE Production Design Gate"},
            {"fieldname": "site_section", "label": "Site / Config", "fieldtype": "Section Break"},
            {"fieldname": "site_name", "label": "Site Name", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "sandbox_config_enabled", "label": "Sandbox Config Enabled", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "production_mode_detected", "label": "Production Mode Detected", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "live_payment_entry_posting_config", "label": "Live PE Posting Config", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "checked_on", "label": "Checked On", "fieldtype": "Datetime", "read_only": 1, "in_list_view": 1},
            {"fieldname": "checked_by", "label": "Checked By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "score_section", "label": "Activation Score", "fieldtype": "Section Break"},
            {"fieldname": "activation_score", "label": "Activation Score", "fieldtype": "Percent", "read_only": 1, "in_list_view": 1},
            {"fieldname": "activation_status", "label": "Activation Status", "fieldtype": "Select", "options": "\nReady For Single-record Live Smoke\nReady With Warnings\nNeeds Review\nBlocked", "read_only": 1, "in_list_view": 1},
            {"fieldname": "blocker_count", "label": "Blocker Count", "fieldtype": "Int", "read_only": 1, "in_list_view": 1},
            {"fieldname": "warning_count", "label": "Warning Count", "fieldtype": "Int", "read_only": 1, "in_list_view": 1},
            {"fieldname": "pass_count", "label": "Pass Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "info_count", "label": "Info Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "item_count", "label": "Item Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "evidence_section", "label": "Evidence Counts", "fieldtype": "Section Break"},
            {"fieldname": "phase5d_hard_blocked_run_count", "label": "Phase 5D Hard-blocked Run Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "phase5c_preview_count", "label": "Phase 5C Preview Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "phase5b_hardened_gate_count", "label": "Phase 5B Hardened Gate Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "phase5a_approved_gate_count", "label": "Phase 5A Approved Gate Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "phase4d_ready_freeze_count", "label": "Phase 4D Ready Freeze Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "policy_section", "label": "Policy Controls", "fieldtype": "Section Break"},
            {"fieldname": "policy_count", "label": "Policy Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "eligible_policy_count", "label": "Eligible Policy Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "hardened_eligible_policy_count", "label": "Hardened Eligible Policy Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "live_enabled_policy_count", "label": "Live Enabled Policy Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "rejected_block_policy_count", "label": "Rejected Block Policy Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "writeoff_block_policy_count", "label": "Write-off Block Policy Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "cancelled_block_policy_count", "label": "Cancelled Block Policy Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "cross_company_allowed_count", "label": "Cross-company Allowed Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "overpayment_allowed_count", "label": "Overpayment Allowed Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "negative_receipt_allowed_count", "label": "Negative Receipt Allowed Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "hard_block_section", "label": "Hard-block Verification", "fieldtype": "Section Break"},
            {"fieldname": "direct_live_creation_blocked", "label": "Direct Live Creation Blocked", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "direct_live_creation_error", "label": "Direct Live Creation Error", "fieldtype": "Small Text", "read_only": 1},
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


def create_activation_gate_item_doctype():
    _create_doctype(
        name=ITEM_DOCTYPE,
        autoname="hash",
        title_field="check_label",
        fields=[
            {"fieldname": "activation_gate", "label": "Activation Gate", "fieldtype": "Link", "options": GATE_DOCTYPE, "reqd": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nPass\nWarning\nBlocker\nInfo\nCancelled", "default": "Info", "in_list_view": 1},
            {"fieldname": "severity", "label": "Severity", "fieldtype": "Select", "options": "\nLow\nMedium\nHigh\nCritical", "default": "Low", "in_list_view": 1},
            {"fieldname": "category", "label": "Category", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "check_key", "label": "Check Key", "fieldtype": "Data"},
            {"fieldname": "check_label", "label": "Check Label", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "detail", "label": "Detail", "fieldtype": "Small Text"},
            {"fieldname": "recommendation", "label": "Recommendation", "fieldtype": "Small Text"},
            {"fieldname": "source_doctype", "label": "Source DocType", "fieldtype": "Link", "options": "DocType"},
            {"fieldname": "source_name", "label": "Source Name", "fieldtype": "Dynamic Link", "options": "source_doctype"},
            {"fieldname": "checked_on", "label": "Checked On", "fieldtype": "Datetime", "read_only": 1},
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
    add_workspace_entry(content, {"id": "ndis_pe_production_activation_heading", "type": "header", "data": {"text": "Production Payment Entry Activation", "col": 12}})
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
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE5E_DOCTYPES},
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "permissions": {
            dt: frappe.get_all(
                "DocPerm",
                filters={"parent": dt},
                fields=["role", "read", "write", "create", "delete", "report", "export"],
                order_by="role asc",
            )
            for dt in PHASE5E_DOCTYPES
        },
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_pe_production_activation_gate": permission_matrix().get("run_pe_production_activation_gate"),
            "cancel_pe_production_activation_gate": permission_matrix().get("cancel_pe_production_activation_gate"),
        },
        "js_hooks": {GATE_DOCTYPE: GATE_DOCTYPE in doctype_js, ITEM_DOCTYPE: ITEM_DOCTYPE in doctype_js},
        "list_js_hooks": {GATE_DOCTYPE: GATE_DOCTYPE in doctype_list_js, ITEM_DOCTYPE: ITEM_DOCTYPE in doctype_list_js},
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_payment_entry_posting_config": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
        "report_files": check_report_files(),
    }


def can_import_service():
    try:
        from ndis_finance.services.pe_production_activation_gate import quick_pe_production_activation_summary

        return callable(quick_pe_production_activation_summary)
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
