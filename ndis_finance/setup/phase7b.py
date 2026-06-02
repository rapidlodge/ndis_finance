import json
from pathlib import Path

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


PREVIEW_DOCTYPE = "NDIS Real Remittance Batch Preview"
LINE_DOCTYPE = "NDIS Real Remittance Batch Preview Line"
PHASE7B_DOCTYPES = [PREVIEW_DOCTYPE, LINE_DOCTYPE]

REPORTS = [
    {
        "report_name": "NDIS Real Remittance Batch Preview Report",
        "ref_doctype": PREVIEW_DOCTYPE,
        "module_path": "ndis_real_remittance_batch_preview_report",
    },
    {
        "report_name": "NDIS Real Remittance Batch Preview Line Report",
        "ref_doctype": LINE_DOCTYPE,
        "module_path": "ndis_real_remittance_batch_preview_line_report",
    },
    {
        "report_name": "NDIS Real Remittance Batch Preview Exception Report",
        "ref_doctype": LINE_DOCTYPE,
        "module_path": "ndis_real_remittance_batch_preview_exception_report",
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
    {"label": "Real Remittance Batch Previews", "type": "DocType", "link_to": PREVIEW_DOCTYPE},
    {"label": "Real Remittance Batch Preview Lines", "type": "DocType", "link_to": LINE_DOCTYPE},
    {"label": "Real Remittance Batch Preview Report", "type": "Report", "link_to": "NDIS Real Remittance Batch Preview Report"},
    {"label": "Real Remittance Batch Preview Line Report", "type": "Report", "link_to": "NDIS Real Remittance Batch Preview Line Report"},
    {"label": "Real Remittance Batch Preview Exceptions", "type": "Report", "link_to": "NDIS Real Remittance Batch Preview Exception Report"},
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
        "NDIS Real Remittance Batch Design Gate",
        "NDIS Real Remittance Batch Posting Policy",
        "NDIS Real Remittance PE Evidence Freeze",
        "NDIS Real Remittance PE Source Harness Run",
        "NDIS Remittance Import Line",
        "Sales Invoice",
        "Payment Entry",
        "Payment Entry Reference",
        "GL Entry",
        "Report",
        "Workspace",
    ]
    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]
    if missing:
        frappe.throw(_("Phase 7B requires completed Phase 7A design gate. Missing: {0}").format(", ".join(missing)))


def create_preview_doctype():
    _create_doctype(
        name=PREVIEW_DOCTYPE,
        autoname="field:preview_id",
        title_field="preview_id",
        fields=[
            {"fieldname": "preview_id", "label": "Preview ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nNeeds Review\nPreviewed\nBlocked\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "preview_status", "label": "Preview Status", "fieldtype": "Select", "options": "\nReady For Hard-block Adapter\nPreviewed With Exceptions\nSource Pending\nNeeds Review\nBlocked\nCancelled", "read_only": 1, "in_list_view": 1},
            {"fieldname": "decision_section", "label": "Preview Decision", "fieldtype": "Section Break"},
            {"fieldname": "preview_approved_for_adapter_phase", "label": "Preview Approved For Adapter Phase", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "ready_for_hard_block_adapter", "label": "Ready For Hard-block Adapter", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "batch_posting_allowed", "label": "Batch Posting Allowed", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "real_posting_allowed", "label": "Real Posting Allowed", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "source_section", "label": "Design Source", "fieldtype": "Section Break"},
            {"fieldname": "design_gate", "label": "Phase 7A Design Gate", "fieldtype": "Link", "options": "NDIS Real Remittance Batch Design Gate", "in_list_view": 1},
            {"fieldname": "evidence_freeze", "label": "Phase 6H Evidence Freeze", "fieldtype": "Link", "options": "NDIS Real Remittance PE Evidence Freeze"},
            {"fieldname": "source_harness_run", "label": "Phase 6E Source Harness Run", "fieldtype": "Link", "options": "NDIS Real Remittance PE Source Harness Run"},
            {"fieldname": "source_remittance_import", "label": "Source Remittance Import", "fieldtype": "Link", "options": "NDIS Remittance Import"},
            {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company", "in_list_view": 1},
            {"fieldname": "cap_section", "label": "Batch Caps", "fieldtype": "Section Break"},
            {"fieldname": "max_batch_lines", "label": "Max Batch Lines", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "max_batch_amount", "label": "Max Batch Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "allowed_outcomes", "label": "Allowed Outcomes", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "excluded_outcomes", "label": "Excluded Outcomes", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "result_section", "label": "Preview Results", "fieldtype": "Section Break"},
            {"fieldname": "source_line_count", "label": "Source Line Count", "fieldtype": "Int", "read_only": 1, "in_list_view": 1},
            {"fieldname": "eligible_line_count", "label": "Eligible Line Count", "fieldtype": "Int", "read_only": 1, "in_list_view": 1},
            {"fieldname": "blocked_line_count", "label": "Blocked Line Count", "fieldtype": "Int", "read_only": 1, "in_list_view": 1},
            {"fieldname": "duplicate_line_count", "label": "Duplicate Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "cap_blocked_line_count", "label": "Cap Blocked Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "would_create_payment_entry_count", "label": "Would Create PE Count", "fieldtype": "Int", "read_only": 1, "in_list_view": 1},
            {"fieldname": "preview_amount", "label": "Preview Amount", "fieldtype": "Currency", "read_only": 1, "in_list_view": 1},
            {"fieldname": "blocked_amount", "label": "Blocked Amount", "fieldtype": "Currency", "read_only": 1},
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


def create_preview_line_doctype():
    _create_doctype(
        name=LINE_DOCTYPE,
        autoname="hash",
        title_field="line_label",
        fields=[
            {"fieldname": "batch_preview", "label": "Batch Preview", "fieldtype": "Link", "options": PREVIEW_DOCTYPE, "reqd": 1, "in_list_view": 1},
            {"fieldname": "line_status", "label": "Line Status", "fieldtype": "Select", "options": "\nEligible\nBlocked\nDuplicate\nCap Blocked\nInfo\nCancelled", "default": "Info", "in_list_view": 1},
            {"fieldname": "line_label", "label": "Line Label", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "source_section", "label": "Source", "fieldtype": "Section Break"},
            {"fieldname": "source_doctype", "label": "Source DocType", "fieldtype": "Link", "options": "DocType"},
            {"fieldname": "source_name", "label": "Source Name", "fieldtype": "Dynamic Link", "options": "source_doctype", "in_list_view": 1},
            {"fieldname": "remittance_import", "label": "Remittance Import", "fieldtype": "Link", "options": "NDIS Remittance Import"},
            {"fieldname": "remittance_line", "label": "Remittance Line", "fieldtype": "Link", "options": "NDIS Remittance Import Line"},
            {"fieldname": "claim_line", "label": "Claim Line", "fieldtype": "Link", "options": "NDIS Claim Line"},
            {"fieldname": "sales_invoice", "label": "Sales Invoice", "fieldtype": "Link", "options": "Sales Invoice", "in_list_view": 1},
            {"fieldname": "classification_section", "label": "Classification", "fieldtype": "Section Break"},
            {"fieldname": "outcome", "label": "Outcome", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "match_status", "label": "Match Status", "fieldtype": "Data"},
            {"fieldname": "block_reason", "label": "Block Reason", "fieldtype": "Small Text"},
            {"fieldname": "would_create_payment_entry", "label": "Would Create Payment Entry", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "duplicate_invoice", "label": "Duplicate Invoice", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "overpayment", "label": "Overpayment", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "cross_company", "label": "Cross Company", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "cap_exceeded", "label": "Cap Exceeded", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "amount_section", "label": "Amount", "fieldtype": "Section Break"},
            {"fieldname": "invoice_outstanding", "label": "Invoice Outstanding", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "source_amount", "label": "Source Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "preview_amount", "label": "Preview Amount", "fieldtype": "Currency", "read_only": 1, "in_list_view": 1},
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
    if "Real Remittance Batch Posting Preview" not in text_blob:
        content.append({"id": "ndis_real_remittance_batch_preview_heading", "type": "header", "data": {"text": "Real Remittance Batch Posting Preview", "col": 12}})
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
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE7B_DOCTYPES},
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "report_files": report_file_health(),
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_real_remittance_batch_preview": permission_matrix().get("run_real_remittance_batch_preview"),
            "cancel_real_remittance_batch_preview": permission_matrix().get("cancel_real_remittance_batch_preview"),
        },
        "js_hooks": {dt: dt in doctype_js for dt in PHASE7B_DOCTYPES},
        "list_js_hooks": {dt: dt in doctype_list_js for dt in PHASE7B_DOCTYPES},
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
        from ndis_finance.services.real_remittance_batch_preview import quick_real_remittance_batch_preview_summary

        return callable(quick_real_remittance_batch_preview_summary)
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
