import json
from pathlib import Path

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


ADAPTER_DOCTYPE = "NDIS Real Remittance Batch Adapter Run"
LINE_DOCTYPE = "NDIS Real Remittance Batch Adapter Run Line"
PHASE7C_DOCTYPES = [ADAPTER_DOCTYPE, LINE_DOCTYPE]

REPORTS = [
    {
        "report_name": "NDIS Real Remittance Batch Adapter Report",
        "ref_doctype": ADAPTER_DOCTYPE,
        "module_path": "ndis_real_remittance_batch_adapter_report",
    },
    {
        "report_name": "NDIS Real Remittance Batch Adapter Line Report",
        "ref_doctype": LINE_DOCTYPE,
        "module_path": "ndis_real_remittance_batch_adapter_line_report",
    },
    {
        "report_name": "NDIS Real Remittance Batch Adapter Guardrail Report",
        "ref_doctype": ADAPTER_DOCTYPE,
        "module_path": "ndis_real_remittance_batch_adapter_guardrail_report",
    },
]

REPORT_ROLES = [
    "System Manager",
    "NDIS CFO",
    "NDIS Finance Manager",
    "NDIS Finance Officer",
    "NDIS Finance Read Only",
]

DOC_PERM_MATRIX = {
    ADAPTER_DOCTYPE: {
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
    {"label": "Real Remittance Batch Adapter Runs", "type": "DocType", "link_to": ADAPTER_DOCTYPE},
    {"label": "Real Remittance Batch Adapter Lines", "type": "DocType", "link_to": LINE_DOCTYPE},
    {"label": "Real Remittance Batch Adapter Report", "type": "Report", "link_to": "NDIS Real Remittance Batch Adapter Report"},
    {"label": "Real Remittance Batch Adapter Line Report", "type": "Report", "link_to": "NDIS Real Remittance Batch Adapter Line Report"},
    {"label": "Real Remittance Batch Adapter Guardrails", "type": "Report", "link_to": "NDIS Real Remittance Batch Adapter Guardrail Report"},
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
        "NDIS Real Remittance Batch Preview",
        "NDIS Real Remittance Batch Preview Line",
        "NDIS Real Remittance Batch Design Gate",
        "NDIS Real Remittance Batch Posting Policy",
        "Sales Invoice",
        "Payment Entry",
        "Payment Entry Reference",
        "GL Entry",
        "Report",
        "Workspace",
    ]
    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]
    if missing:
        frappe.throw(_("Phase 7C requires completed Phase 7B batch preview. Missing: {0}").format(", ".join(missing)))


def create_adapter_run_doctype():
    _create_doctype(
        name=ADAPTER_DOCTYPE,
        autoname="field:adapter_run_id",
        title_field="adapter_run_id",
        fields=[
            {"fieldname": "adapter_run_id", "label": "Adapter Run ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nNeeds Review\nHard Blocked\nSource Pending\nBlocked\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "adapter_status", "label": "Adapter Status", "fieldtype": "Select", "options": "\nReady For Activation Gate\nStructural Ready - Source Eligible Pending\nNeeds Review\nBlocked\nCancelled", "read_only": 1, "in_list_view": 1},
            {"fieldname": "decision_section", "label": "Adapter Decision", "fieldtype": "Section Break"},
            {"fieldname": "adapter_approved_for_activation_gate", "label": "Adapter Approved For Activation Gate", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "ready_for_activation_gate", "label": "Ready For Activation Gate", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "direct_live_creation_blocked", "label": "Direct Live Creation Blocked", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "batch_posting_allowed", "label": "Batch Posting Allowed", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "real_posting_allowed", "label": "Real Posting Allowed", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "source_section", "label": "Source Evidence", "fieldtype": "Section Break"},
            {"fieldname": "batch_preview", "label": "Phase 7B Batch Preview", "fieldtype": "Link", "options": "NDIS Real Remittance Batch Preview", "in_list_view": 1},
            {"fieldname": "design_gate", "label": "Phase 7A Design Gate", "fieldtype": "Link", "options": "NDIS Real Remittance Batch Design Gate"},
            {"fieldname": "evidence_freeze", "label": "Phase 6H Evidence Freeze", "fieldtype": "Link", "options": "NDIS Real Remittance PE Evidence Freeze"},
            {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company", "in_list_view": 1},
            {"fieldname": "cap_section", "label": "Batch Caps", "fieldtype": "Section Break"},
            {"fieldname": "max_batch_lines", "label": "Max Batch Lines", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "max_batch_amount", "label": "Max Batch Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "result_section", "label": "Adapter Results", "fieldtype": "Section Break"},
            {"fieldname": "source_line_count", "label": "Source Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "eligible_preview_line_count", "label": "Eligible Preview Line Count", "fieldtype": "Int", "read_only": 1, "in_list_view": 1},
            {"fieldname": "hard_blocked_line_count", "label": "Hard-blocked Line Count", "fieldtype": "Int", "read_only": 1, "in_list_view": 1},
            {"fieldname": "validation_blocked_line_count", "label": "Validation Blocked Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "duplicate_blocked_line_count", "label": "Duplicate Blocked Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "cap_blocked_line_count", "label": "Cap Blocked Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "would_create_payment_entry_count", "label": "Would Create PE Count", "fieldtype": "Int", "read_only": 1, "in_list_view": 1},
            {"fieldname": "would_create_payment_entry_amount", "label": "Would Create PE Amount", "fieldtype": "Currency", "read_only": 1, "in_list_view": 1},
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
            {"fieldname": "score_section", "label": "Adapter Score", "fieldtype": "Section Break"},
            {"fieldname": "adapter_score", "label": "Adapter Score", "fieldtype": "Percent", "read_only": 1},
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
            {"fieldname": "sales_invoice_count_today", "label": "Sales Invoice Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "purchase_invoice_count_today", "label": "Purchase Invoice Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "batch_live_enabled_policy_count", "label": "Batch Live Enabled Policy Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "production_live_enabled_policy_count", "label": "Production Live Enabled Policy Count", "fieldtype": "Int", "read_only": 1},
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
        title_field="line_label",
        fields=[
            {"fieldname": "adapter_run", "label": "Adapter Run", "fieldtype": "Link", "options": ADAPTER_DOCTYPE, "reqd": 1, "in_list_view": 1},
            {"fieldname": "line_status", "label": "Line Status", "fieldtype": "Select", "options": "\nHard Blocked\nValidation Blocked\nDuplicate Blocked\nCap Blocked\nInfo\nCancelled", "default": "Info", "in_list_view": 1},
            {"fieldname": "line_label", "label": "Line Label", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "source_section", "label": "Source", "fieldtype": "Section Break"},
            {"fieldname": "batch_preview", "label": "Batch Preview", "fieldtype": "Link", "options": "NDIS Real Remittance Batch Preview"},
            {"fieldname": "preview_line", "label": "Preview Line", "fieldtype": "Link", "options": "NDIS Real Remittance Batch Preview Line"},
            {"fieldname": "remittance_line", "label": "Remittance Line", "fieldtype": "Link", "options": "NDIS Remittance Import Line"},
            {"fieldname": "claim_line", "label": "Claim Line", "fieldtype": "Link", "options": "NDIS Claim Line"},
            {"fieldname": "sales_invoice", "label": "Sales Invoice", "fieldtype": "Link", "options": "Sales Invoice", "in_list_view": 1},
            {"fieldname": "classification_section", "label": "Classification", "fieldtype": "Section Break"},
            {"fieldname": "source_line_status", "label": "Source Line Status", "fieldtype": "Data"},
            {"fieldname": "outcome", "label": "Outcome", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "match_status", "label": "Match Status", "fieldtype": "Data"},
            {"fieldname": "would_create_payment_entry", "label": "Would Create Payment Entry", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "hard_block_reason", "label": "Hard Block Reason", "fieldtype": "Small Text"},
            {"fieldname": "amount_section", "label": "Amount", "fieldtype": "Section Break"},
            {"fieldname": "invoice_outstanding", "label": "Invoice Outstanding", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "source_amount", "label": "Source Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "would_create_amount", "label": "Would Create Amount", "fieldtype": "Currency", "read_only": 1, "in_list_view": 1},
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
    if "Real Remittance Batch Hard-block Adapter" not in text_blob:
        content.append({"id": "ndis_real_remittance_batch_adapter_heading", "type": "header", "data": {"text": "Real Remittance Batch Hard-block Adapter", "col": 12}})
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
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE7C_DOCTYPES},
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "report_files": report_file_health(),
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_real_remittance_batch_adapter": permission_matrix().get("run_real_remittance_batch_adapter"),
            "cancel_real_remittance_batch_adapter": permission_matrix().get("cancel_real_remittance_batch_adapter"),
        },
        "js_hooks": {dt: dt in doctype_js for dt in PHASE7C_DOCTYPES},
        "list_js_hooks": {dt: dt in doctype_list_js for dt in PHASE7C_DOCTYPES},
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_payment_entry_posting_config": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def report_file_health():
    report_root = Path(frappe.get_app_path("ndis_finance", "ndis_finance", "report"))
    result = {}
    for report in REPORTS:
        module_path = report["module_path"]
        result[report["report_name"]] = {
            "python": (report_root / module_path / f"{module_path}.py").exists(),
            "javascript": (report_root / module_path / f"{module_path}.js").exists(),
        }
    return result


def can_import_service():
    try:
        from ndis_finance.services.real_remittance_batch_adapter import quick_real_remittance_batch_adapter_summary

        return callable(quick_real_remittance_batch_adapter_summary)
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
