import json
from pathlib import Path

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


RUN_DOCTYPE = "NDIS Real Remittance Batch PE Smoke Run"
LINE_DOCTYPE = "NDIS Real Remittance Batch PE Smoke Line"
PHASE7F_DOCTYPES = [RUN_DOCTYPE, LINE_DOCTYPE]

REPORTS = [
    {"report_name": "NDIS Real Remittance Batch PE Smoke Report", "ref_doctype": RUN_DOCTYPE, "module_path": "ndis_real_remittance_batch_pe_smoke_report"},
    {"report_name": "NDIS Real Remittance Batch PE Smoke Line Report", "ref_doctype": LINE_DOCTYPE, "module_path": "ndis_real_remittance_batch_pe_smoke_line_report"},
    {"report_name": "NDIS Real Remittance Batch PE Smoke Guardrail Report", "ref_doctype": RUN_DOCTYPE, "module_path": "ndis_real_remittance_batch_pe_smoke_guardrail_report"},
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
    {"label": "Real Remittance Batch PE Smoke Runs", "type": "DocType", "link_to": RUN_DOCTYPE},
    {"label": "Real Remittance Batch PE Smoke Lines", "type": "DocType", "link_to": LINE_DOCTYPE},
    {"label": "Real Remittance Batch PE Smoke Report", "type": "Report", "link_to": "NDIS Real Remittance Batch PE Smoke Report"},
    {"label": "Real Remittance Batch PE Smoke Line Report", "type": "Report", "link_to": "NDIS Real Remittance Batch PE Smoke Line Report"},
    {"label": "Real Remittance Batch PE Smoke Guardrails", "type": "Report", "link_to": "NDIS Real Remittance Batch PE Smoke Guardrail Report"},
]

CUSTOM_FIELDS = {
    "Payment Entry": [
        {"fieldname": "custom_ndis_real_remittance_batch_pe_smoke", "label": "NDIS Real Remittance Batch PE Smoke", "fieldtype": "Check", "insert_after": "party", "default": 0, "allow_on_submit": 1, "read_only": 1, "no_copy": 1},
        {"fieldname": "custom_ndis_real_remittance_batch_pe_smoke_run", "label": "NDIS Real Remittance Batch PE Smoke Run", "fieldtype": "Link", "options": RUN_DOCTYPE, "insert_after": "custom_ndis_real_remittance_batch_pe_smoke", "allow_on_submit": 1, "read_only": 1, "no_copy": 1},
        {"fieldname": "custom_ndis_real_remittance_batch_source_run", "label": "NDIS Real Remittance Batch Source Run", "fieldtype": "Link", "options": "NDIS Real Remittance Batch Source Harness Run", "insert_after": "custom_ndis_real_remittance_batch_pe_smoke_run", "allow_on_submit": 1, "read_only": 1, "no_copy": 1},
        {"fieldname": "custom_ndis_real_remittance_batch_pe_amount", "label": "NDIS Real Remittance Batch PE Amount", "fieldtype": "Currency", "insert_after": "custom_ndis_real_remittance_batch_source_run", "allow_on_submit": 1, "read_only": 1, "no_copy": 1},
    ],
}


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_smoke_run_doctype()
    create_smoke_line_doctype()
    create_payment_entry_custom_fields()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Real Remittance Batch Source Harness Run",
        "NDIS Real Remittance Batch Source Harness Line",
        "NDIS Real Remittance Batch Activation Gate",
        "NDIS Real Remittance Batch Adapter Run",
        "NDIS Real Remittance Batch Preview",
        "NDIS Real Remittance Batch Design Gate",
        "Sales Invoice",
        "Payment Entry",
        "Payment Entry Reference",
        "GL Entry",
        "Account",
        "Company",
        "Report",
        "Workspace",
    ]
    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]
    if missing:
        frappe.throw(_("Phase 7F requires completed Phase 7E source harness. Missing: {0}").format(", ".join(missing)))


def create_smoke_run_doctype():
    _create_doctype(
        name=RUN_DOCTYPE,
        autoname="field:smoke_run_id",
        title_field="smoke_run_id",
        fields=[
            {"fieldname": "smoke_run_id", "label": "Smoke Run ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nNeeds Review\nSubmitted\nSource Pending\nBlocked\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "smoke_status", "label": "Smoke Status", "fieldtype": "Select", "options": "\nSubmitted - Rollback Required\nAudit Only\nNeeds Review\nBlocked\nCancelled", "read_only": 1, "in_list_view": 1},
            {"fieldname": "decision_section", "label": "Smoke Decision", "fieldtype": "Section Break"},
            {"fieldname": "controlled_smoke_submitted", "label": "Controlled Smoke Submitted", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "rollback_required", "label": "Rollback Required", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "freeze_required_after_rollback", "label": "Freeze Required After Rollback", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "batch_posting_allowed", "label": "Batch Posting Allowed", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "real_posting_allowed", "label": "Real Posting Allowed", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "source_section", "label": "Source Evidence", "fieldtype": "Section Break"},
            {"fieldname": "source_run", "label": "Phase 7E Source Run", "fieldtype": "Link", "options": "NDIS Real Remittance Batch Source Harness Run", "in_list_view": 1},
            {"fieldname": "activation_gate", "label": "Phase 7D Activation Gate", "fieldtype": "Link", "options": "NDIS Real Remittance Batch Activation Gate"},
            {"fieldname": "adapter_run", "label": "Phase 7C Adapter Run", "fieldtype": "Link", "options": "NDIS Real Remittance Batch Adapter Run"},
            {"fieldname": "batch_preview", "label": "Phase 7B Batch Preview", "fieldtype": "Link", "options": "NDIS Real Remittance Batch Preview"},
            {"fieldname": "design_gate", "label": "Phase 7A Design Gate", "fieldtype": "Link", "options": "NDIS Real Remittance Batch Design Gate"},
            {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company", "in_list_view": 1},
            {"fieldname": "customer", "label": "Customer", "fieldtype": "Link", "options": "Customer", "in_list_view": 1},
            {"fieldname": "payment_entry", "label": "Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "in_list_view": 1},
            {"fieldname": "account_section", "label": "Posting Accounts", "fieldtype": "Section Break"},
            {"fieldname": "paid_from", "label": "Paid From / Receivable", "fieldtype": "Link", "options": "Account"},
            {"fieldname": "paid_to", "label": "Paid To / Bank", "fieldtype": "Link", "options": "Account"},
            {"fieldname": "result_section", "label": "Smoke Results", "fieldtype": "Section Break"},
            {"fieldname": "source_line_count", "label": "Source Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "invoice_count", "label": "Invoice Count", "fieldtype": "Int", "read_only": 1, "in_list_view": 1},
            {"fieldname": "payment_entry_reference_count", "label": "Payment Entry Reference Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_count_created", "label": "Payment Entry Count Created", "fieldtype": "Int", "read_only": 1, "in_list_view": 1},
            {"fieldname": "payment_entry_submitted_count", "label": "Payment Entry Submitted Count", "fieldtype": "Int", "read_only": 1, "in_list_view": 1},
            {"fieldname": "payment_entry_amount", "label": "Payment Entry Amount", "fieldtype": "Currency", "read_only": 1, "in_list_view": 1},
            {"fieldname": "invoice_outstanding_before_total", "label": "Invoice Outstanding Before Total", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "invoice_outstanding_after_total", "label": "Invoice Outstanding After Total", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "payment_entry_gl_count", "label": "Payment Entry GL Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_net", "label": "Payment Entry GL Net", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "site_section", "label": "Site / Config", "fieldtype": "Section Break"},
            {"fieldname": "site_name", "label": "Site Name", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "sandbox_config_enabled", "label": "Sandbox Config Enabled", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "production_mode_detected", "label": "Production Mode Detected", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "live_payment_entry_posting_config", "label": "Live PE Posting Config", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "checked_on", "label": "Checked On", "fieldtype": "Datetime", "read_only": 1, "in_list_view": 1},
            {"fieldname": "checked_by", "label": "Checked By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "score_section", "label": "Smoke Score", "fieldtype": "Section Break"},
            {"fieldname": "smoke_score", "label": "Smoke Score", "fieldtype": "Percent", "read_only": 1},
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


def create_smoke_line_doctype():
    _create_doctype(
        name=LINE_DOCTYPE,
        autoname="hash",
        title_field="line_label",
        fields=[
            {"fieldname": "smoke_run", "label": "Smoke Run", "fieldtype": "Link", "options": RUN_DOCTYPE, "reqd": 1, "in_list_view": 1},
            {"fieldname": "line_no", "label": "Line No", "fieldtype": "Int", "in_list_view": 1},
            {"fieldname": "line_label", "label": "Line Label", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "line_status", "label": "Line Status", "fieldtype": "Select", "options": "\nSubmitted\nNeeds Review\nBlocked\nCancelled", "default": "Submitted", "in_list_view": 1},
            {"fieldname": "source_section", "label": "Source Records", "fieldtype": "Section Break"},
            {"fieldname": "source_run", "label": "Source Run", "fieldtype": "Link", "options": "NDIS Real Remittance Batch Source Harness Run"},
            {"fieldname": "source_line", "label": "Source Line", "fieldtype": "Link", "options": "NDIS Real Remittance Batch Source Harness Line"},
            {"fieldname": "sales_invoice", "label": "Sales Invoice", "fieldtype": "Link", "options": "Sales Invoice", "in_list_view": 1},
            {"fieldname": "claim_line", "label": "Claim Line", "fieldtype": "Link", "options": "NDIS Claim Line"},
            {"fieldname": "remittance_line", "label": "Remittance Line", "fieldtype": "Link", "options": "NDIS Remittance Import Line"},
            {"fieldname": "payment_entry", "label": "Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "in_list_view": 1},
            {"fieldname": "amount_section", "label": "Amount", "fieldtype": "Section Break"},
            {"fieldname": "invoice_outstanding_before", "label": "Invoice Outstanding Before", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "allocated_amount", "label": "Allocated Amount", "fieldtype": "Currency", "read_only": 1, "in_list_view": 1},
            {"fieldname": "invoice_outstanding_after", "label": "Invoice Outstanding After", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "audit_section", "label": "Audit", "fieldtype": "Section Break"},
            {"fieldname": "checked_on", "label": "Checked On", "fieldtype": "Datetime", "read_only": 1},
        ],
    )


def create_payment_entry_custom_fields():
    create_custom_fields(CUSTOM_FIELDS, update=True)


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
    if not ws.meta.has_field("content"):
        return
    try:
        content = json.loads(ws.content or "[]")
    except Exception:
        content = []
    text_blob = json.dumps(content)
    if "Real Remittance Batch PE Smoke" not in text_blob:
        content.append({"id": "ndis_real_remittance_batch_pe_smoke_heading", "type": "header", "data": {"text": "Real Remittance Batch PE Smoke", "col": 12}})
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
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE7F_DOCTYPES},
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "report_files": report_file_health(),
        "custom_fields": check_custom_fields(),
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_real_remittance_batch_pe_smoke": permission_matrix().get("run_real_remittance_batch_pe_smoke"),
            "cancel_real_remittance_batch_pe_smoke": permission_matrix().get("cancel_real_remittance_batch_pe_smoke"),
        },
        "js_hooks": {dt: dt in doctype_js for dt in PHASE7F_DOCTYPES},
        "list_js_hooks": {dt: dt in doctype_list_js for dt in PHASE7F_DOCTYPES},
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_payment_entry_posting_config": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def check_custom_fields():
    result = {}
    for doctype, fields in CUSTOM_FIELDS.items():
        for field in fields:
            result[f"{doctype}.{field['fieldname']}"] = has_field(doctype, field["fieldname"])
    return result


def has_field(doctype, fieldname):
    if not frappe.db.exists("DocType", doctype):
        return False
    return bool(frappe.get_meta(doctype).has_field(fieldname))


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
        from ndis_finance.services.real_remittance_batch_pe_smoke import quick_real_remittance_batch_pe_smoke_summary

        return callable(quick_real_remittance_batch_pe_smoke_summary)
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
