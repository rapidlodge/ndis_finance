import json
from pathlib import Path

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


RUN_DOCTYPE = "NDIS Real Remittance Batch PE Rollback Run"
LINE_DOCTYPE = "NDIS Real Remittance Batch PE Rollback Line"
PHASE7G_DOCTYPES = [RUN_DOCTYPE, LINE_DOCTYPE]

REPORTS = [
    {"report_name": "NDIS Real Remittance Batch PE Rollback Report", "ref_doctype": RUN_DOCTYPE, "module_path": "ndis_real_remittance_batch_pe_rollback_report"},
    {"report_name": "NDIS Real Remittance Batch PE Rollback Line Report", "ref_doctype": LINE_DOCTYPE, "module_path": "ndis_real_remittance_batch_pe_rollback_line_report"},
    {"report_name": "NDIS Real Remittance Batch PE Rollback Guardrail Report", "ref_doctype": RUN_DOCTYPE, "module_path": "ndis_real_remittance_batch_pe_rollback_guardrail_report"},
]

REPORT_ROLES = ["System Manager", "NDIS CFO", "NDIS Finance Manager", "NDIS Finance Officer", "NDIS Finance Read Only"]

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
    {"label": "Real Remittance Batch PE Rollback Runs", "type": "DocType", "link_to": RUN_DOCTYPE},
    {"label": "Real Remittance Batch PE Rollback Lines", "type": "DocType", "link_to": LINE_DOCTYPE},
    {"label": "Real Remittance Batch PE Rollback Report", "type": "Report", "link_to": "NDIS Real Remittance Batch PE Rollback Report"},
    {"label": "Real Remittance Batch PE Rollback Line Report", "type": "Report", "link_to": "NDIS Real Remittance Batch PE Rollback Line Report"},
    {"label": "Real Remittance Batch PE Rollback Guardrails", "type": "Report", "link_to": "NDIS Real Remittance Batch PE Rollback Guardrail Report"},
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_rollback_run_doctype()
    create_rollback_line_doctype()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Real Remittance Batch PE Smoke Run",
        "NDIS Real Remittance Batch PE Smoke Line",
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
        frappe.throw(_("Phase 7G requires completed Phase 7F PE smoke. Missing: {0}").format(", ".join(missing)))


def create_rollback_run_doctype():
    _create_doctype(
        name=RUN_DOCTYPE,
        autoname="field:rollback_run_id",
        title_field="rollback_run_id",
        fields=[
            {"fieldname": "rollback_run_id", "label": "Rollback Run ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nNeeds Review\nRolled Back\nSource Pending\nBlocked\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "rollback_status", "label": "Rollback Status", "fieldtype": "Select", "options": "\nRolled Back - Freeze Required\nAudit Only\nNeeds Review\nBlocked\nCancelled", "read_only": 1, "in_list_view": 1},
            {"fieldname": "decision_section", "label": "Rollback Decision", "fieldtype": "Section Break"},
            {"fieldname": "rollback_completed", "label": "Rollback Completed", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "ready_for_freeze", "label": "Ready For Freeze", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "controlled_payment_entry_cancelled", "label": "Controlled Payment Entry Cancelled", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "batch_posting_allowed", "label": "Batch Posting Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "real_posting_allowed", "label": "Real Posting Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "source_section", "label": "Source Evidence", "fieldtype": "Section Break"},
            {"fieldname": "smoke_run", "label": "Phase 7F Smoke Run", "fieldtype": "Link", "options": "NDIS Real Remittance Batch PE Smoke Run", "in_list_view": 1},
            {"fieldname": "source_run", "label": "Phase 7E Source Run", "fieldtype": "Link", "options": "NDIS Real Remittance Batch Source Harness Run"},
            {"fieldname": "activation_gate", "label": "Phase 7D Activation Gate", "fieldtype": "Link", "options": "NDIS Real Remittance Batch Activation Gate"},
            {"fieldname": "adapter_run", "label": "Phase 7C Adapter Run", "fieldtype": "Link", "options": "NDIS Real Remittance Batch Adapter Run"},
            {"fieldname": "batch_preview", "label": "Phase 7B Batch Preview", "fieldtype": "Link", "options": "NDIS Real Remittance Batch Preview"},
            {"fieldname": "design_gate", "label": "Phase 7A Design Gate", "fieldtype": "Link", "options": "NDIS Real Remittance Batch Design Gate"},
            {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company", "in_list_view": 1},
            {"fieldname": "customer", "label": "Customer", "fieldtype": "Link", "options": "Customer"},
            {"fieldname": "payment_entry", "label": "Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "in_list_view": 1},
            {"fieldname": "result_section", "label": "Rollback Results", "fieldtype": "Section Break"},
            {"fieldname": "payment_entry_docstatus_before", "label": "PE Docstatus Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_docstatus_after", "label": "PE Docstatus After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "invoice_count", "label": "Invoice Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_reference_count", "label": "PE Reference Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_amount", "label": "Payment Entry Amount", "fieldtype": "Currency", "read_only": 1, "in_list_view": 1},
            {"fieldname": "invoice_outstanding_before_total", "label": "Invoice Outstanding Before Total", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "invoice_outstanding_after_total", "label": "Invoice Outstanding After Total", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "payment_entry_gl_count_before_specific", "label": "PE GL Count Before Specific", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_count_after_specific", "label": "PE GL Count After Specific", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_net_after_specific", "label": "PE GL Net After Specific", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "site_section", "label": "Site / Config", "fieldtype": "Section Break"},
            {"fieldname": "site_name", "label": "Site Name", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "sandbox_config_enabled", "label": "Sandbox Config Enabled", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "production_mode_detected", "label": "Production Mode Detected", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "live_payment_entry_posting_config", "label": "Live PE Posting Config", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "checked_on", "label": "Checked On", "fieldtype": "Datetime", "read_only": 1, "in_list_view": 1},
            {"fieldname": "checked_by", "label": "Checked By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "score_section", "label": "Rollback Score", "fieldtype": "Section Break"},
            {"fieldname": "rollback_score", "label": "Rollback Score", "fieldtype": "Percent", "read_only": 1},
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
            {"fieldname": "submitted_tagged_pe_count_after", "label": "Submitted Tagged PE Count After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "cancelled_tagged_pe_count_after", "label": "Cancelled Tagged PE Count After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "submitted_journal_entry_count_today", "label": "Submitted JE Count Today", "fieldtype": "Int", "read_only": 1},
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


def create_rollback_line_doctype():
    _create_doctype(
        name=LINE_DOCTYPE,
        autoname="hash",
        title_field="line_label",
        fields=[
            {"fieldname": "rollback_run", "label": "Rollback Run", "fieldtype": "Link", "options": RUN_DOCTYPE, "reqd": 1, "in_list_view": 1},
            {"fieldname": "line_no", "label": "Line No", "fieldtype": "Int", "in_list_view": 1},
            {"fieldname": "line_label", "label": "Line Label", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "line_status", "label": "Line Status", "fieldtype": "Select", "options": "\nRestored\nNeeds Review\nBlocked\nCancelled", "default": "Restored", "in_list_view": 1},
            {"fieldname": "source_section", "label": "Source Records", "fieldtype": "Section Break"},
            {"fieldname": "smoke_run", "label": "Smoke Run", "fieldtype": "Link", "options": "NDIS Real Remittance Batch PE Smoke Run"},
            {"fieldname": "smoke_line", "label": "Smoke Line", "fieldtype": "Link", "options": "NDIS Real Remittance Batch PE Smoke Line"},
            {"fieldname": "source_run", "label": "Source Run", "fieldtype": "Link", "options": "NDIS Real Remittance Batch Source Harness Run"},
            {"fieldname": "sales_invoice", "label": "Sales Invoice", "fieldtype": "Link", "options": "Sales Invoice", "in_list_view": 1},
            {"fieldname": "payment_entry", "label": "Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "in_list_view": 1},
            {"fieldname": "amount_section", "label": "Amount", "fieldtype": "Section Break"},
            {"fieldname": "invoice_outstanding_before_rollback", "label": "Outstanding Before Rollback", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "rollback_amount", "label": "Rollback Amount", "fieldtype": "Currency", "read_only": 1, "in_list_view": 1},
            {"fieldname": "invoice_outstanding_after_rollback", "label": "Outstanding After Rollback", "fieldtype": "Currency", "read_only": 1},
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
        if "Real Remittance Batch PE Rollback" not in text_blob:
            content.append({"id": "ndis_real_remittance_batch_pe_rollback_heading", "type": "header", "data": {"text": "Real Remittance Batch PE Rollback", "col": 12}})
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
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE7G_DOCTYPES},
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "report_files": check_report_files(),
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_real_remittance_batch_pe_rollback": permission_matrix().get("run_real_remittance_batch_pe_rollback"),
            "cancel_real_remittance_batch_pe_rollback": permission_matrix().get("cancel_real_remittance_batch_pe_rollback"),
        },
        "js_hooks": {
            RUN_DOCTYPE: RUN_DOCTYPE in doctype_js,
            LINE_DOCTYPE: LINE_DOCTYPE in doctype_js,
        },
        "list_js_hooks": {
            RUN_DOCTYPE: RUN_DOCTYPE in doctype_list_js,
            LINE_DOCTYPE: LINE_DOCTYPE in doctype_list_js,
        },
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
        from ndis_finance.services.real_remittance_batch_pe_rollback import quick_real_remittance_batch_pe_rollback_summary
        return callable(quick_real_remittance_batch_pe_rollback_summary)
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
