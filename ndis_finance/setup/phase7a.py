import json
from pathlib import Path

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


POLICY_DOCTYPE = "NDIS Real Remittance Batch Posting Policy"
GATE_DOCTYPE = "NDIS Real Remittance Batch Design Gate"
ITEM_DOCTYPE = "NDIS Real Remittance Batch Design Gate Item"
PHASE7A_DOCTYPES = [POLICY_DOCTYPE, GATE_DOCTYPE, ITEM_DOCTYPE]

REPORTS = [
    {
        "report_name": "NDIS Real Remittance Batch Policy Register Report",
        "ref_doctype": POLICY_DOCTYPE,
        "module_path": "ndis_real_remittance_batch_policy_register_report",
    },
    {
        "report_name": "NDIS Real Remittance Batch Design Gate Report",
        "ref_doctype": GATE_DOCTYPE,
        "module_path": "ndis_real_remittance_batch_design_gate_report",
    },
    {
        "report_name": "NDIS Real Remittance Batch Design Exception Report",
        "ref_doctype": ITEM_DOCTYPE,
        "module_path": "ndis_real_remittance_batch_design_exception_report",
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
    {"label": "Real Remittance Batch Policies", "type": "DocType", "link_to": POLICY_DOCTYPE},
    {"label": "Real Remittance Batch Design Gates", "type": "DocType", "link_to": GATE_DOCTYPE},
    {"label": "Real Remittance Batch Design Items", "type": "DocType", "link_to": ITEM_DOCTYPE},
    {
        "label": "Real Remittance Batch Policy Register",
        "type": "Report",
        "link_to": "NDIS Real Remittance Batch Policy Register Report",
    },
    {
        "label": "Real Remittance Batch Design Gate Report",
        "type": "Report",
        "link_to": "NDIS Real Remittance Batch Design Gate Report",
    },
    {
        "label": "Real Remittance Batch Design Exceptions",
        "type": "Report",
        "link_to": "NDIS Real Remittance Batch Design Exception Report",
    },
]

DEFAULT_POLICIES = [
    ("BATCH_SCOPE_MATCHED_PAID_ONLY", "Only matched Paid / Short Paid remittance lines", "Source Eligibility", "Critical", 0, 0, "Batch posting may only include matched invoice/claim lines with Paid or Short Paid outcomes."),
    ("BATCH_EXCLUDE_REJECTED", "Exclude rejected lines", "Source Eligibility", "Critical", 0, 0, "Rejected remittance rows must never create Payment Entry records."),
    ("BATCH_EXCLUDE_UNMATCHED", "Exclude unmatched lines", "Source Eligibility", "Critical", 0, 0, "Unmatched rows must be blocked before batch preview."),
    ("BATCH_NO_DUPLICATE_INVOICE_ALLOCATION", "No duplicate invoice allocation", "Duplicate Protection", "Critical", 0, 0, "The same Sales Invoice must not be allocated twice in one controlled batch."),
    ("BATCH_NO_OVERPAYMENT", "No overpayment", "Amount Control", "Critical", 0, 0, "Allocated amount cannot exceed Sales Invoice outstanding balance."),
    ("BATCH_NO_CROSS_COMPANY", "No cross-company posting", "Company Control", "Critical", 0, 0, "Every source line must match the locked company scope."),
    ("BATCH_CAP_FIRST_RUN", "First controlled batch cap", "Batch Cap", "High", 3, 3, "The first controlled batch design is capped to 3 lines and 3.00 total amount."),
    ("BATCH_NO_EXTERNAL_MOVEMENT", "No external movement", "External Systems", "Critical", 0, 0, "No Xero export, ABA file, STP event, payroll movement, email, or bank allocation is allowed."),
    ("BATCH_NO_GENERAL_LIVE_POSTING", "No general live posting", "Live Posting Control", "Critical", 0, 0, "Phase 7A is design-only and must not enable broad live posting."),
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_policy_doctype()
    create_design_gate_doctype()
    create_design_gate_item_doctype()
    create_reports()
    seed_default_policies()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Real Remittance PE Evidence Freeze",
        "NDIS Real Remittance PE Rollback Run",
        "NDIS Real Remittance PE Smoke Run",
        "NDIS Real Remittance PE Source Harness Run",
        "NDIS Real Remittance PE Activation Gate",
        "NDIS Real Remittance PE Adapter Run",
        "NDIS Real Remittance PE Preview",
        "NDIS Real Remittance PE Design Gate",
        "Sales Invoice",
        "Payment Entry",
        "GL Entry",
        "Report",
        "Workspace",
    ]
    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]
    if missing:
        frappe.throw(_("Phase 7A requires completed Phase 6H evidence freeze. Missing: {0}").format(", ".join(missing)))


def create_policy_doctype():
    _create_doctype(
        name=POLICY_DOCTYPE,
        autoname="field:policy_key",
        title_field="policy_name",
        fields=[
            {"fieldname": "policy_key", "label": "Policy Key", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "policy_name", "label": "Policy Name", "fieldtype": "Data", "reqd": 1, "in_list_view": 1},
            {"fieldname": "policy_category", "label": "Policy Category", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "policy_status", "label": "Policy Status", "fieldtype": "Select", "options": "\nDraft\nActive\nRetired", "default": "Active", "in_list_view": 1},
            {"fieldname": "severity", "label": "Severity", "fieldtype": "Select", "options": "\nLow\nMedium\nHigh\nCritical", "default": "Critical", "in_list_view": 1},
            {"fieldname": "batch_live_enabled", "label": "Batch Live Enabled", "fieldtype": "Check", "default": 0, "in_list_view": 1},
            {"fieldname": "cap_section", "label": "Caps", "fieldtype": "Section Break"},
            {"fieldname": "max_batch_lines", "label": "Max Batch Lines", "fieldtype": "Int", "default": 0},
            {"fieldname": "max_batch_amount", "label": "Max Batch Amount", "fieldtype": "Currency", "default": 0},
            {"fieldname": "rule_section", "label": "Rule", "fieldtype": "Section Break"},
            {"fieldname": "rule_summary", "label": "Rule Summary", "fieldtype": "Small Text"},
            {"fieldname": "created_by_phase", "label": "Created By Phase", "fieldtype": "Data", "default": "Phase 7A", "read_only": 1},
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
            {"fieldname": "gate_type", "label": "Gate Type", "fieldtype": "Select", "options": "\nReal Remittance Batch Posting Design\nDesign Only Gate", "default": "Real Remittance Batch Posting Design", "in_list_view": 1},
            {"fieldname": "decision_section", "label": "Design Decision", "fieldtype": "Section Break"},
            {"fieldname": "design_approved_for_preview_phase", "label": "Design Approved For Preview Phase", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "ready_for_batch_preview", "label": "Ready For Batch Preview", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "batch_posting_allowed", "label": "Batch Posting Allowed", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "real_posting_allowed", "label": "Real Posting Allowed", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "evidence_section", "label": "Phase 6 Evidence", "fieldtype": "Section Break"},
            {"fieldname": "evidence_freeze", "label": "Phase 6H Evidence Freeze", "fieldtype": "Link", "options": "NDIS Real Remittance PE Evidence Freeze", "in_list_view": 1},
            {"fieldname": "rollback_run", "label": "Phase 6G Rollback Run", "fieldtype": "Link", "options": "NDIS Real Remittance PE Rollback Run"},
            {"fieldname": "smoke_run", "label": "Phase 6F Smoke Run", "fieldtype": "Link", "options": "NDIS Real Remittance PE Smoke Run"},
            {"fieldname": "source_harness_run", "label": "Phase 6E Source Harness Run", "fieldtype": "Link", "options": "NDIS Real Remittance PE Source Harness Run"},
            {"fieldname": "activation_gate", "label": "Phase 6D Activation Gate", "fieldtype": "Link", "options": "NDIS Real Remittance PE Activation Gate"},
            {"fieldname": "adapter_run", "label": "Phase 6C Adapter Run", "fieldtype": "Link", "options": "NDIS Real Remittance PE Adapter Run"},
            {"fieldname": "preview", "label": "Phase 6B Preview", "fieldtype": "Link", "options": "NDIS Real Remittance PE Preview"},
            {"fieldname": "scope_section", "label": "Locked Batch Scope", "fieldtype": "Section Break"},
            {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company", "in_list_view": 1},
            {"fieldname": "allowed_outcomes", "label": "Allowed Outcomes", "fieldtype": "Data", "default": "Paid, Short Paid"},
            {"fieldname": "excluded_outcomes", "label": "Excluded Outcomes", "fieldtype": "Data", "default": "Rejected, Unmatched, Duplicate, Overpayment, Cross Company"},
            {"fieldname": "cap_section", "label": "Controlled Batch Caps", "fieldtype": "Section Break"},
            {"fieldname": "max_batch_lines", "label": "Max Batch Lines", "fieldtype": "Int", "default": 3, "in_list_view": 1},
            {"fieldname": "max_batch_amount", "label": "Max Batch Amount", "fieldtype": "Currency", "default": 3, "in_list_view": 1},
            {"fieldname": "first_batch_only", "label": "First Batch Only", "fieldtype": "Check", "default": 1},
            {"fieldname": "requires_separate_activation_gate", "label": "Requires Separate Activation Gate", "fieldtype": "Check", "default": 1},
            {"fieldname": "proof_section", "label": "Proof Counts", "fieldtype": "Section Break"},
            {"fieldname": "policy_count", "label": "Policy Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "active_policy_count", "label": "Active Policy Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "live_enabled_policy_count", "label": "Live Enabled Policy Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "phase6h_ready_for_next_phase", "label": "Phase 6H Ready For Next Phase", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "phase6h_real_posting_allowed", "label": "Phase 6H Real Posting Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "site_section", "label": "Site / Config", "fieldtype": "Section Break"},
            {"fieldname": "site_name", "label": "Site Name", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "sandbox_config_enabled", "label": "Sandbox Config Enabled", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "production_mode_detected", "label": "Production Mode Detected", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "live_payment_entry_posting_config", "label": "Live PE Posting Config", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "checked_on", "label": "Checked On", "fieldtype": "Datetime", "read_only": 1, "in_list_view": 1},
            {"fieldname": "checked_by", "label": "Checked By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "score_section", "label": "Design Score", "fieldtype": "Section Break"},
            {"fieldname": "design_score", "label": "Design Score", "fieldtype": "Percent", "read_only": 1},
            {"fieldname": "design_status", "label": "Design Status", "fieldtype": "Select", "options": "\nApproved For Batch Preview\nNeeds Review\nBlocked", "read_only": 1},
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
            {"fieldname": "recommendation", "label": "Recommendation", "fieldtype": "Small Text"},
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


def seed_default_policies():
    for key, name, category, severity, max_lines, max_amount, summary in DEFAULT_POLICIES:
        existing = frappe.db.exists(POLICY_DOCTYPE, key)
        doc = frappe.get_doc(POLICY_DOCTYPE, existing) if existing else frappe.new_doc(POLICY_DOCTYPE)
        if not existing:
            doc.policy_key = key
        doc.policy_name = name
        doc.policy_category = category
        doc.policy_status = "Active"
        doc.severity = severity
        doc.batch_live_enabled = 0
        doc.max_batch_lines = int(max_lines or 0)
        doc.max_batch_amount = max_amount or 0
        doc.rule_summary = summary
        doc.created_by_phase = "Phase 7A"
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
    if "Real Remittance Batch Posting Design" not in text_blob:
        content.append({"id": "ndis_real_remittance_batch_design_heading", "type": "header", "data": {"text": "Real Remittance Batch Posting Design", "col": 12}})
    for shortcut in WORKSPACE_SHORTCUTS:
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            continue
        content.append(
            {
                "id": frappe.scrub(shortcut["label"]),
                "type": "shortcut",
                "data": {"label": shortcut["label"], "link_to": shortcut["link_to"], "type": shortcut["type"], "col": 3},
            }
        )
    ws.content = json.dumps(content)


@frappe.whitelist()
def health_check():
    hooks = frappe.get_hooks()
    doctype_js = hooks.get("doctype_js", {})
    doctype_list_js = hooks.get("doctype_list_js", {})
    return {
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE7A_DOCTYPES},
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "report_files": report_file_health(),
        "policy_count": count_policy(),
        "active_policy_count": count_policy({"policy_status": "Active"}),
        "live_policy_count": count_policy({"batch_live_enabled": 1}),
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_real_remittance_batch_design_gate": permission_matrix().get("run_real_remittance_batch_design_gate"),
            "cancel_real_remittance_batch_design_gate": permission_matrix().get("cancel_real_remittance_batch_design_gate"),
        },
        "js_hooks": {dt: dt in doctype_js for dt in PHASE7A_DOCTYPES},
        "list_js_hooks": {dt: dt in doctype_list_js for dt in PHASE7A_DOCTYPES},
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_payment_entry_posting_config": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def count_policy(filters=None):
    if not frappe.db.exists("DocType", POLICY_DOCTYPE):
        return 0
    return frappe.db.count(POLICY_DOCTYPE, filters or {})


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
        from ndis_finance.services.real_remittance_batch_design_gate import quick_real_remittance_batch_design_gate_summary

        return callable(quick_real_remittance_batch_design_gate_summary)
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
