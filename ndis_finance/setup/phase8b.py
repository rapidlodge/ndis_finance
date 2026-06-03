import json
from pathlib import Path

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


PREVIEW_DOCTYPE = "NDIS Controlled Production Batch Preview"
LINE_DOCTYPE = "NDIS Controlled Production Batch Preview Line"
PHASE8B_DOCTYPES = [PREVIEW_DOCTYPE, LINE_DOCTYPE]

REPORTS = [
    {"report_name": "NDIS Controlled Production Batch Preview Report", "ref_doctype": PREVIEW_DOCTYPE, "module_path": "ndis_controlled_production_batch_preview_report"},
    {"report_name": "NDIS Controlled Production Batch Preview Line Report", "ref_doctype": LINE_DOCTYPE, "module_path": "ndis_controlled_production_batch_preview_line_report"},
    {"report_name": "NDIS Controlled Production Batch Preview Exception Report", "ref_doctype": LINE_DOCTYPE, "module_path": "ndis_controlled_production_batch_preview_exception_report"},
]

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
    {"label": "Controlled Production Batch Previews", "type": "DocType", "link_to": PREVIEW_DOCTYPE},
    {"label": "Controlled Production Batch Preview Lines", "type": "DocType", "link_to": LINE_DOCTYPE},
    {"label": "Controlled Production Batch Preview Report", "type": "Report", "link_to": "NDIS Controlled Production Batch Preview Report"},
    {"label": "Controlled Production Batch Preview Line Report", "type": "Report", "link_to": "NDIS Controlled Production Batch Preview Line Report"},
    {"label": "Controlled Production Batch Preview Exceptions", "type": "Report", "link_to": "NDIS Controlled Production Batch Preview Exception Report"},
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
        "NDIS Controlled Production Batch Design Gate",
        "NDIS Controlled Production Batch Design Gate Item",
        "NDIS Controlled Production Batch Posting Policy",
        "NDIS Real Remittance Batch PE Evidence Freeze",
        "NDIS Real Remittance Batch Source Harness Run",
        "NDIS Real Remittance Batch Source Harness Line",
        "Payment Entry",
        "Payment Entry Reference",
        "Sales Invoice",
        "GL Entry",
        "Report",
        "Workspace",
    ]
    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]
    if missing:
        frappe.throw(_("Phase 8B requires completed Phase 8A design gate. Missing: {0}").format(", ".join(missing)))


def create_preview_doctype():
    _create_doctype(
        name=PREVIEW_DOCTYPE,
        autoname="field:preview_id",
        title_field="preview_id",
        fields=[
            {"fieldname": "preview_id", "label": "Preview ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nNeeds Review\nPreviewed\nBlocked\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "preview_status", "label": "Preview Status", "fieldtype": "Select", "options": "\nReady For Hard-block Adapter\nPreviewed With Exceptions\nNeeds Review\nBlocked\nCancelled", "read_only": 1, "in_list_view": 1},
            {"fieldname": "decision_section", "label": "Preview Decision", "fieldtype": "Section Break"},
            {"fieldname": "preview_approved_for_adapter_phase", "label": "Preview Approved For Adapter Phase", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "ready_for_hard_block_adapter", "label": "Ready For Hard-block Adapter", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "production_batch_posting_allowed", "label": "Production Batch Posting Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "real_posting_allowed", "label": "Real Posting Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "source_section", "label": "Source Evidence", "fieldtype": "Section Break"},
            {"fieldname": "design_gate", "label": "Phase 8A Design Gate", "fieldtype": "Link", "options": "NDIS Controlled Production Batch Design Gate", "in_list_view": 1},
            {"fieldname": "phase7h_freeze", "label": "Phase 7H Freeze", "fieldtype": "Link", "options": "NDIS Real Remittance Batch PE Evidence Freeze"},
            {"fieldname": "source_run", "label": "Phase 7E Source Run", "fieldtype": "Link", "options": "NDIS Real Remittance Batch Source Harness Run"},
            {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company", "in_list_view": 1},
            {"fieldname": "customer", "label": "Customer", "fieldtype": "Link", "options": "Customer"},
            {"fieldname": "bank_account", "label": "Bank Account", "fieldtype": "Link", "options": "Account"},
            {"fieldname": "receivable_account", "label": "Receivable Account", "fieldtype": "Link", "options": "Account"},
            {"fieldname": "cap_section", "label": "Caps", "fieldtype": "Section Break"},
            {"fieldname": "max_batch_lines", "label": "Max Batch Lines", "fieldtype": "Int", "read_only": 1, "in_list_view": 1},
            {"fieldname": "max_batch_amount", "label": "Max Batch Amount", "fieldtype": "Currency", "read_only": 1, "in_list_view": 1},
            {"fieldname": "result_section", "label": "Preview Result", "fieldtype": "Section Break"},
            {"fieldname": "source_line_count", "label": "Source Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "eligible_line_count", "label": "Eligible Line Count", "fieldtype": "Int", "read_only": 1, "in_list_view": 1},
            {"fieldname": "blocked_line_count", "label": "Blocked Line Count", "fieldtype": "Int", "read_only": 1, "in_list_view": 1},
            {"fieldname": "duplicate_line_count", "label": "Duplicate Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "overpayment_line_count", "label": "Overpayment Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "cross_company_line_count", "label": "Cross Company Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "would_create_payment_entry_count", "label": "Would Create PE Count", "fieldtype": "Int", "read_only": 1, "in_list_view": 1},
            {"fieldname": "preview_amount", "label": "Preview Amount", "fieldtype": "Currency", "read_only": 1, "in_list_view": 1},
            {"fieldname": "shortfall_preserved_amount", "label": "Shortfall Preserved Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "movement_section", "label": "No Movement Proof", "fieldtype": "Section Break"},
            {"fieldname": "actual_payment_entry_created_count", "label": "Actual PE Created Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "actual_gl_created_count", "label": "Actual GL Created Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "site_section", "label": "Site / Config", "fieldtype": "Section Break"},
            {"fieldname": "site_name", "label": "Site Name", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "sandbox_config_enabled", "label": "Sandbox Config Enabled", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "production_mode_detected", "label": "Production Mode Detected", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "live_payment_entry_posting_config", "label": "Live PE Posting Config", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "checked_on", "label": "Checked On", "fieldtype": "Datetime", "read_only": 1, "in_list_view": 1},
            {"fieldname": "checked_by", "label": "Checked By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "score_section", "label": "Preview Score", "fieldtype": "Section Break"},
            {"fieldname": "preview_score", "label": "Preview Score", "fieldtype": "Percent", "read_only": 1},
            {"fieldname": "blocker_count", "label": "Blocker Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "warning_count", "label": "Warning Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "pass_count", "label": "Pass Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "info_count", "label": "Info Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "item_count", "label": "Item Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "guardrail_section", "label": "Movement Guardrails", "fieldtype": "Section Break"},
            {"fieldname": "payment_entry_count_before", "label": "Payment Entry Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_count_after", "label": "Payment Entry Count After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_count_before", "label": "Payment Entry GL Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_count_after", "label": "Payment Entry GL Count After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "submitted_journal_entry_count_today", "label": "Submitted JE Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "purchase_invoice_count_today", "label": "Purchase Invoice Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "production_batch_enabled_policy_count", "label": "Production Batch Enabled Policy Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "live_posting_allowed_policy_count", "label": "Live Posting Allowed Policy Count", "fieldtype": "Int", "read_only": 1},
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
        title_field="line_label",
        fields=[
            {"fieldname": "preview", "label": "Preview", "fieldtype": "Link", "options": PREVIEW_DOCTYPE, "reqd": 1, "in_list_view": 1},
            {"fieldname": "line_no", "label": "Line No", "fieldtype": "Int", "in_list_view": 1},
            {"fieldname": "line_label", "label": "Line Label", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "line_status", "label": "Line Status", "fieldtype": "Select", "options": "\nEligible\nBlocked\nDuplicate\nCancelled", "default": "Blocked", "in_list_view": 1},
            {"fieldname": "block_reason", "label": "Block Reason", "fieldtype": "Small Text"},
            {"fieldname": "source_section", "label": "Source", "fieldtype": "Section Break"},
            {"fieldname": "source_run", "label": "Source Run", "fieldtype": "Link", "options": "NDIS Real Remittance Batch Source Harness Run"},
            {"fieldname": "source_line", "label": "Source Line", "fieldtype": "Link", "options": "NDIS Real Remittance Batch Source Harness Line"},
            {"fieldname": "sales_invoice", "label": "Sales Invoice", "fieldtype": "Link", "options": "Sales Invoice", "in_list_view": 1},
            {"fieldname": "claim_line", "label": "Claim Line", "fieldtype": "Link", "options": "NDIS Claim Line"},
            {"fieldname": "remittance_line", "label": "Remittance Line", "fieldtype": "Link", "options": "NDIS Remittance Import Line"},
            {"fieldname": "classification_section", "label": "Classification", "fieldtype": "Section Break"},
            {"fieldname": "expected_outcome", "label": "Expected Outcome", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "match_status", "label": "Match Status", "fieldtype": "Data"},
            {"fieldname": "duplicate_invoice", "label": "Duplicate Invoice", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "overpayment", "label": "Overpayment", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "cross_company", "label": "Cross Company", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "amount_section", "label": "Amount", "fieldtype": "Section Break"},
            {"fieldname": "invoice_total", "label": "Invoice Total", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "invoice_outstanding", "label": "Invoice Outstanding", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "remittance_amount", "label": "Remittance Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "allocatable_amount", "label": "Allocatable Amount", "fieldtype": "Currency", "read_only": 1, "in_list_view": 1},
            {"fieldname": "shortfall_amount", "label": "Shortfall Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "audit_section", "label": "Audit", "fieldtype": "Section Break"},
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
    base = {key: 0 for key in ["read", "write", "create", "delete", "submit", "cancel", "amend", "report", "export", "import", "share", "print", "email"]}
    base.update({"role": role, "permlevel": 0})
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
    if ws.meta.has_field("content"):
        try:
            content = json.loads(ws.content or "[]")
        except Exception:
            content = []
        text_blob = json.dumps(content)
        if "Controlled Production Batch Preview" not in text_blob:
            content.append({"id": "ndis_controlled_production_batch_preview_heading", "type": "header", "data": {"text": "Controlled Production Batch Preview", "col": 12}})
        for shortcut in WORKSPACE_SHORTCUTS:
            if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
                continue
            content.append({"id": frappe.scrub(shortcut["label"]), "type": "shortcut", "data": {"label": shortcut["label"], "link_to": shortcut["link_to"], "type": shortcut["type"], "col": 3}})
        ws.content = json.dumps(content)
    ws.save(ignore_permissions=True)


@frappe.whitelist()
def health_check():
    hooks = frappe.get_hooks()
    doctype_js = hooks.get("doctype_js", {})
    doctype_list_js = hooks.get("doctype_list_js", {})
    return {
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE8B_DOCTYPES},
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "report_files": check_report_files(),
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_controlled_production_batch_preview": permission_matrix().get("run_controlled_production_batch_preview"),
            "cancel_controlled_production_batch_preview": permission_matrix().get("cancel_controlled_production_batch_preview"),
        },
        "js_hooks": {dt: dt in doctype_js for dt in PHASE8B_DOCTYPES},
        "list_js_hooks": {dt: dt in doctype_list_js for dt in PHASE8B_DOCTYPES},
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_payment_entry_posting_config": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def check_report_files():
    base = Path(frappe.get_app_path("ndis_finance")) / "ndis_finance" / "report"
    return {
        report["report_name"]: {
            "python": (base / report["module_path"] / f"{report['module_path']}.py").exists(),
            "javascript": (base / report["module_path"] / f"{report['module_path']}.js").exists(),
            "init": (base / report["module_path"] / "__init__.py").exists(),
        }
        for report in REPORTS
    }


def can_import_service():
    try:
        from ndis_finance.services.controlled_production_batch_preview import quick_controlled_production_batch_preview_summary

        return callable(quick_controlled_production_batch_preview_summary)
    except Exception:
        return False


def check_workspace_shortcuts():
    result = {shortcut["label"]: False for shortcut in WORKSPACE_SHORTCUTS}
    ws_name = frappe.db.exists("Workspace", WORKSPACE_NAME) or frappe.db.exists("Workspace", {"label": WORKSPACE_NAME})
    if not ws_name:
        return result
    ws = frappe.get_doc("Workspace", ws_name)
    text_blob = getattr(ws, "content", "") or ""
    for shortcut in WORKSPACE_SHORTCUTS:
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            result[shortcut["label"]] = True
    return result
