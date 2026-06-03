import json
from pathlib import Path

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
GATE_DOCTYPE = "NDIS Controlled Production Batch Design Gate"
ITEM_DOCTYPE = "NDIS Controlled Production Batch Design Gate Item"
PHASE8A_DOCTYPES = [POLICY_DOCTYPE, GATE_DOCTYPE, ITEM_DOCTYPE]

REPORTS = [
    {"report_name": "NDIS Controlled Production Batch Policy Report", "ref_doctype": POLICY_DOCTYPE, "module_path": "ndis_controlled_production_batch_policy_report"},
    {"report_name": "NDIS Controlled Production Batch Design Gate Report", "ref_doctype": GATE_DOCTYPE, "module_path": "ndis_controlled_production_batch_design_gate_report"},
    {"report_name": "NDIS Controlled Production Batch Design Exception Report", "ref_doctype": ITEM_DOCTYPE, "module_path": "ndis_controlled_production_batch_design_exception_report"},
]

REPORT_ROLES = ["System Manager", "NDIS CFO", "NDIS Finance Manager", "NDIS Finance Officer", "NDIS Finance Read Only"]

DOC_PERM_MATRIX = {
    POLICY_DOCTYPE: {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
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
    {"label": "Controlled Production Batch Policies", "type": "DocType", "link_to": POLICY_DOCTYPE},
    {"label": "Controlled Production Batch Design Gates", "type": "DocType", "link_to": GATE_DOCTYPE},
    {"label": "Controlled Production Batch Design Items", "type": "DocType", "link_to": ITEM_DOCTYPE},
    {"label": "Controlled Production Batch Policy Report", "type": "Report", "link_to": "NDIS Controlled Production Batch Policy Report"},
    {"label": "Controlled Production Batch Design Gate Report", "type": "Report", "link_to": "NDIS Controlled Production Batch Design Gate Report"},
    {"label": "Controlled Production Batch Design Exceptions", "type": "Report", "link_to": "NDIS Controlled Production Batch Design Exception Report"},
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_policy_doctype()
    create_design_gate_doctype()
    create_design_gate_item_doctype()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()

    from ndis_finance.services.controlled_production_batch_design_gate import seed_default_policies

    seed_default_policies()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Real Remittance Batch PE Evidence Freeze",
        "NDIS Real Remittance Batch PE Evidence Freeze Item",
        "NDIS Real Remittance Batch PE Rollback Run",
        "NDIS Real Remittance Batch PE Smoke Run",
        "NDIS Real Remittance Batch Source Harness Run",
        "NDIS Real Remittance Batch Activation Gate",
        "Payment Entry",
        "Sales Invoice",
        "GL Entry",
        "Report",
        "Workspace",
    ]
    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]
    if missing:
        frappe.throw(_("Phase 8A requires completed Phase 7H evidence freeze. Missing: {0}").format(", ".join(missing)))


def create_policy_doctype():
    _create_doctype(
        name=POLICY_DOCTYPE,
        autoname="field:policy_id",
        title_field="policy_id",
        fields=[
            {"fieldname": "policy_id", "label": "Policy ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "policy_name", "label": "Policy Name", "fieldtype": "Data", "reqd": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nActive\nInactive\nArchived", "default": "Active", "in_list_view": 1},
            {"fieldname": "scope_section", "label": "Controlled Production Scope", "fieldtype": "Section Break"},
            {"fieldname": "policy_type", "label": "Policy Type", "fieldtype": "Select", "options": "\nEligibility\nBatch Cap\nAccount Mapping\nSafety Guardrail\nRollback Requirement\nFreeze Requirement", "in_list_view": 1},
            {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company", "in_list_view": 1},
            {"fieldname": "bank_account", "label": "Bank Account", "fieldtype": "Link", "options": "Account"},
            {"fieldname": "receivable_account", "label": "Receivable Account", "fieldtype": "Link", "options": "Account"},
            {"fieldname": "rule_section", "label": "Rule Controls", "fieldtype": "Section Break"},
            {"fieldname": "allow_paid", "label": "Allow Paid Lines", "fieldtype": "Check", "default": 1},
            {"fieldname": "allow_short_paid", "label": "Allow Short Paid Lines", "fieldtype": "Check", "default": 1},
            {"fieldname": "allow_rejected", "label": "Allow Rejected Lines", "fieldtype": "Check", "default": 0},
            {"fieldname": "allow_unmatched", "label": "Allow Unmatched Lines", "fieldtype": "Check", "default": 0},
            {"fieldname": "allow_duplicate_invoice", "label": "Allow Duplicate Invoice", "fieldtype": "Check", "default": 0},
            {"fieldname": "allow_overpayment", "label": "Allow Overpayment", "fieldtype": "Check", "default": 0},
            {"fieldname": "allow_cross_company", "label": "Allow Cross Company", "fieldtype": "Check", "default": 0},
            {"fieldname": "cap_section", "label": "Production Batch Caps", "fieldtype": "Section Break"},
            {"fieldname": "max_batch_lines", "label": "Max Batch Lines", "fieldtype": "Int", "default": 3, "in_list_view": 1},
            {"fieldname": "max_batch_amount", "label": "Max Batch Amount", "fieldtype": "Currency", "default": 3, "in_list_view": 1},
            {"fieldname": "single_payment_entry_only", "label": "Single Payment Entry Only", "fieldtype": "Check", "default": 1},
            {"fieldname": "requires_preview_before_posting", "label": "Requires Preview Before Posting", "fieldtype": "Check", "default": 1},
            {"fieldname": "requires_cfo_acknowledgement", "label": "Requires CFO Acknowledgement", "fieldtype": "Check", "default": 1},
            {"fieldname": "requires_immediate_rollback_path", "label": "Requires Immediate Rollback Path", "fieldtype": "Check", "default": 1},
            {"fieldname": "requires_freeze_after_rollback", "label": "Requires Freeze After Rollback", "fieldtype": "Check", "default": 1},
            {"fieldname": "enable_section", "label": "Enablement State", "fieldtype": "Section Break"},
            {"fieldname": "design_policy_only", "label": "Design Policy Only", "fieldtype": "Check", "default": 1, "read_only": 1, "in_list_view": 1},
            {"fieldname": "production_batch_enabled", "label": "Production Batch Enabled", "fieldtype": "Check", "default": 0, "read_only": 1, "in_list_view": 1},
            {"fieldname": "live_posting_allowed", "label": "Live Posting Allowed", "fieldtype": "Check", "default": 0, "read_only": 1, "in_list_view": 1},
            {"fieldname": "audit_section", "label": "Audit", "fieldtype": "Section Break"},
            {"fieldname": "created_by_phase", "label": "Created By Phase", "fieldtype": "Data", "default": "Phase 8A"},
            {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
        ],
    )


def create_design_gate_doctype():
    _create_doctype(
        name=GATE_DOCTYPE,
        autoname="field:design_gate_id",
        title_field="design_gate_id",
        fields=[
            {"fieldname": "design_gate_id", "label": "Design Gate ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nNeeds Review\nApproved\nBlocked\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "design_status", "label": "Design Status", "fieldtype": "Select", "options": "\nApproved For Controlled Production Preview\nNeeds Review\nBlocked\nCancelled", "read_only": 1, "in_list_view": 1},
            {"fieldname": "decision_section", "label": "Design Decision", "fieldtype": "Section Break"},
            {"fieldname": "design_approved_for_preview_phase", "label": "Design Approved For Preview Phase", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "ready_for_controlled_production_preview", "label": "Ready For Controlled Production Preview", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "production_batch_posting_allowed", "label": "Production Batch Posting Allowed", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "real_posting_allowed", "label": "Real Posting Allowed", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "evidence_section", "label": "Required Evidence", "fieldtype": "Section Break"},
            {"fieldname": "phase7h_freeze", "label": "Phase 7H Evidence Freeze", "fieldtype": "Link", "options": "NDIS Real Remittance Batch PE Evidence Freeze", "in_list_view": 1},
            {"fieldname": "phase7g_rollback_run", "label": "Phase 7G Rollback Run", "fieldtype": "Link", "options": "NDIS Real Remittance Batch PE Rollback Run"},
            {"fieldname": "phase7f_smoke_run", "label": "Phase 7F Smoke Run", "fieldtype": "Link", "options": "NDIS Real Remittance Batch PE Smoke Run"},
            {"fieldname": "phase7e_source_run", "label": "Phase 7E Source Run", "fieldtype": "Link", "options": "NDIS Real Remittance Batch Source Harness Run"},
            {"fieldname": "scope_section", "label": "Controlled Production Scope", "fieldtype": "Section Break"},
            {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company", "in_list_view": 1},
            {"fieldname": "bank_account", "label": "Bank Account", "fieldtype": "Link", "options": "Account"},
            {"fieldname": "receivable_account", "label": "Receivable Account", "fieldtype": "Link", "options": "Account"},
            {"fieldname": "max_batch_lines", "label": "Max Batch Lines", "fieldtype": "Int", "read_only": 1, "in_list_view": 1},
            {"fieldname": "max_batch_amount", "label": "Max Batch Amount", "fieldtype": "Currency", "read_only": 1, "in_list_view": 1},
            {"fieldname": "policy_section", "label": "Policy Evidence", "fieldtype": "Section Break"},
            {"fieldname": "policy_count", "label": "Policy Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "active_policy_count", "label": "Active Policy Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "live_enabled_policy_count", "label": "Live Enabled Policy Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "unsafe_policy_count", "label": "Unsafe Policy Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "movement_section", "label": "No Movement Evidence", "fieldtype": "Section Break"},
            {"fieldname": "actual_payment_entry_created_count", "label": "Actual PE Created Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "actual_gl_created_count", "label": "Actual GL Created Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "site_section", "label": "Site / Config", "fieldtype": "Section Break"},
            {"fieldname": "site_name", "label": "Site Name", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "sandbox_config_enabled", "label": "Sandbox Config Enabled", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "production_mode_detected", "label": "Production Mode Detected", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "live_payment_entry_posting_config", "label": "Live PE Posting Config", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "checked_on", "label": "Checked On", "fieldtype": "Datetime", "read_only": 1, "in_list_view": 1},
            {"fieldname": "checked_by", "label": "Checked By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "score_section", "label": "Design Score", "fieldtype": "Section Break"},
            {"fieldname": "design_score", "label": "Design Score", "fieldtype": "Percent", "read_only": 1},
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


def create_design_gate_item_doctype():
    _create_doctype(
        name=ITEM_DOCTYPE,
        autoname="hash",
        title_field="check_label",
        fields=[
            {"fieldname": "design_gate", "label": "Design Gate", "fieldtype": "Link", "options": GATE_DOCTYPE, "reqd": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nPass\nWarning\nBlocker\nInfo\nCancelled", "default": "Info", "in_list_view": 1},
            {"fieldname": "severity", "label": "Severity", "fieldtype": "Select", "options": "\nLow\nMedium\nHigh\nCritical", "default": "Low", "in_list_view": 1},
            {"fieldname": "category", "label": "Category", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "check_key", "label": "Check Key", "fieldtype": "Data"},
            {"fieldname": "check_label", "label": "Check Label", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "detail", "label": "Detail", "fieldtype": "Small Text"},
            {"fieldname": "source_doctype", "label": "Source DocType", "fieldtype": "Link", "options": "DocType"},
            {"fieldname": "source_name", "label": "Source Name", "fieldtype": "Dynamic Link", "options": "source_doctype"},
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
        if "Controlled Production Batch Posting" not in text_blob:
            content.append({"id": "ndis_controlled_production_batch_heading", "type": "header", "data": {"text": "Controlled Production Batch Posting", "col": 12}})
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
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE8A_DOCTYPES},
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "report_files": check_report_files(),
        "policy_count": frappe.db.count(POLICY_DOCTYPE) if frappe.db.exists("DocType", POLICY_DOCTYPE) else 0,
        "live_enabled_policy_count": frappe.db.count(POLICY_DOCTYPE, {"production_batch_enabled": 1}) if frappe.db.exists("DocType", POLICY_DOCTYPE) else 0,
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_controlled_production_batch_design_gate": permission_matrix().get("run_controlled_production_batch_design_gate"),
            "cancel_controlled_production_batch_design_gate": permission_matrix().get("cancel_controlled_production_batch_design_gate"),
        },
        "js_hooks": {dt: dt in doctype_js for dt in PHASE8A_DOCTYPES},
        "list_js_hooks": {dt: dt in doctype_list_js for dt in PHASE8A_DOCTYPES},
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
        from ndis_finance.services.controlled_production_batch_design_gate import quick_controlled_production_batch_design_summary

        return callable(quick_controlled_production_batch_design_summary)
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
