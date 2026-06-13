import json

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


PHASE10E_DOCTYPES = [
    "NDIS Guarded Adapter Final Policy Decision",
    "NDIS Guarded Adapter Final Policy Decision Item",
]

REPORTS = [
    {"report_name": "NDIS Guarded Adapter Final Policy Decision Report", "ref_doctype": "NDIS Guarded Adapter Final Policy Decision"},
    {"report_name": "NDIS Guarded Adapter Final Policy Decision Item Report", "ref_doctype": "NDIS Guarded Adapter Final Policy Decision Item"},
    {"report_name": "NDIS Guarded Adapter Final Policy Decision Guardrail Report", "ref_doctype": "NDIS Guarded Adapter Final Policy Decision"},
]

REPORT_ROLES = [
    "System Manager",
    "NDIS CFO",
    "NDIS Finance Manager",
    "NDIS Finance Officer",
    "NDIS Finance Read Only",
]

DOC_PERM_MATRIX = {
    "NDIS Guarded Adapter Final Policy Decision": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Guarded Adapter Final Policy Decision Item": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
}

WORKSPACE_NAME = "NDIS Finance"

WORKSPACE_SHORTCUTS = [
    {"label": "Guarded Adapter Final Policy Decisions", "type": "DocType", "link_to": "NDIS Guarded Adapter Final Policy Decision"},
    {"label": "Guarded Adapter Final Policy Decision Items", "type": "DocType", "link_to": "NDIS Guarded Adapter Final Policy Decision Item"},
    {"label": "Guarded Adapter Final Policy Decision Report", "type": "Report", "link_to": "NDIS Guarded Adapter Final Policy Decision Report"},
    {"label": "Guarded Adapter Final Policy Decision Item Report", "type": "Report", "link_to": "NDIS Guarded Adapter Final Policy Decision Item Report"},
    {"label": "Guarded Adapter Final Policy Decision Guardrails", "type": "Report", "link_to": "NDIS Guarded Adapter Final Policy Decision Guardrail Report"},
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_decision_doctype()
    create_item_doctype()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Guarded Adapter Final Policy Review",
        "NDIS Guarded Adapter Final Policy Review Item",
        "NDIS Guarded Adapter Smoke Rollback Freeze",
        "NDIS Guarded Limited Adapter Smoke Rollback",
        "NDIS Guarded Limited Adapter Smoke",
        "NDIS Limited Batch Adapter Activation Gate",
        "NDIS Controlled Production Batch Posting Policy",
        "Payment Entry",
        "GL Entry",
        "Report",
        "Workspace",
    ]
    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]
    if missing:
        frappe.throw(_("Phase 10E requires completed Phase 10D final policy review. Missing: {0}").format(", ".join(missing)))


def create_decision_doctype():
    _create_doctype(
        name="NDIS Guarded Adapter Final Policy Decision",
        autoname="field:decision_id",
        title_field="decision_id",
        fields=[
            {"fieldname": "decision_id", "label": "Decision ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nNeeds Review\nDecision Applied\nBlocked\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "decision_status", "label": "Decision Status", "fieldtype": "Select", "options": "\nControlled Limited Operation Remains Enabled\nNeeds Review\nBlocked\nCancelled", "read_only": 1, "in_list_view": 1},
            {"fieldname": "final_decision_section", "label": "Final Decision", "fieldtype": "Section Break"},
            {"fieldname": "final_policy_decision_applied", "label": "Final Policy Decision Applied", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "keep_policy_enabled_decision_applied", "label": "Keep Policy Enabled Decision Applied", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "ready_for_controlled_limited_operations_monitoring", "label": "Ready For Controlled Limited Operations Monitoring", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "selected_policy_decision", "label": "Selected Policy Decision", "fieldtype": "Select", "options": "\nKeep Policy Enabled For Limited Monitored Operation\nDisable Policy And Return To Locked State\nRequire Further Smoke Cycle", "read_only": 1},
            {"fieldname": "policy_state_preserved_verified", "label": "Policy State Preserved Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "policy_mutation_performed", "label": "Policy Mutation Performed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "actual_policy_mutation_count", "label": "Actual Policy Mutation Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "verification_section", "label": "Evidence Verification", "fieldtype": "Section Break"},
            {"fieldname": "phase10d_review_verified", "label": "Phase 10D Review Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "phase10c_freeze_verified", "label": "Phase 10C Freeze Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "phase10b_rollback_verified", "label": "Phase 10B Rollback Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "phase10a_smoke_verified", "label": "Phase 10A Smoke Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "phase9z_activation_gate_verified", "label": "Phase 9Z Activation Gate Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "payment_entry_cancelled_verified", "label": "Payment Entry Cancelled Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "gl_net_zero_verified", "label": "GL Net Zero Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "invoice_outstanding_restored_verified", "label": "Invoice Outstanding Restored Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "no_new_accounting_movement_verified", "label": "No New Accounting Movement Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "controlled_policy_enabled_verified", "label": "Controlled Policy Enabled Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "live_posting_blocked_verified", "label": "Live Posting Blocked Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "chain_section", "label": "Evidence Chain", "fieldtype": "Section Break"},
            {"fieldname": "review", "label": "Phase 10D Review", "fieldtype": "Link", "options": "NDIS Guarded Adapter Final Policy Review", "in_list_view": 1},
            {"fieldname": "freeze", "label": "Phase 10C Freeze", "fieldtype": "Link", "options": "NDIS Guarded Adapter Smoke Rollback Freeze"},
            {"fieldname": "rollback", "label": "Phase 10B Rollback", "fieldtype": "Link", "options": "NDIS Guarded Limited Adapter Smoke Rollback"},
            {"fieldname": "smoke", "label": "Phase 10A Smoke", "fieldtype": "Link", "options": "NDIS Guarded Limited Adapter Smoke"},
            {"fieldname": "activation_gate", "label": "Phase 9Z Activation Gate", "fieldtype": "Link", "options": "NDIS Limited Batch Adapter Activation Gate"},
            {"fieldname": "runtime_guard", "label": "Phase 9V Runtime Guard", "fieldtype": "Link", "options": "NDIS Limited Batch Runtime Guard"},
            {"fieldname": "policy_section", "label": "Policy Evidence", "fieldtype": "Section Break"},
            {"fieldname": "target_policy_doctype", "label": "Target Policy DocType", "fieldtype": "Link", "options": "DocType", "read_only": 1},
            {"fieldname": "target_policy", "label": "Target Policy", "fieldtype": "Dynamic Link", "options": "target_policy_doctype", "in_list_view": 1},
            {"fieldname": "target_policy_name", "label": "Target Policy Name", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "target_policy_enabled_before", "label": "Target Policy Enabled Before", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "target_policy_enabled_after", "label": "Target Policy Enabled After", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "target_policy_live_before", "label": "Target Policy Live Before", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "target_policy_live_after", "label": "Target Policy Live After", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "production_batch_enabled_policy_count_before", "label": "Production Batch Enabled Policy Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "production_batch_enabled_policy_count_after", "label": "Production Batch Enabled Policy Count After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "live_posting_allowed_policy_count_before", "label": "Live Posting Allowed Policy Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "live_posting_allowed_policy_count_after", "label": "Live Posting Allowed Policy Count After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_section", "label": "Payment Entry Evidence", "fieldtype": "Section Break"},
            {"fieldname": "payment_entry", "label": "Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "read_only": 1, "in_list_view": 1},
            {"fieldname": "payment_entry_docstatus", "label": "Payment Entry Docstatus", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_status", "label": "Payment Entry Status", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "payment_entry_amount", "label": "Payment Entry Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "payment_entry_reference_count", "label": "Payment Entry Reference Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_row_count", "label": "Payment Entry GL Row Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_reversal_count", "label": "Payment Entry GL Reversal Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "accounting_section", "label": "Accounting Evidence", "fieldtype": "Section Break"},
            {"fieldname": "allocated_amount_total", "label": "Allocated Amount Total", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "invoice_outstanding_restored_delta", "label": "Invoice Outstanding Restored Delta", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "gl_net_debit", "label": "GL Net Debit", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "gl_net_credit", "label": "GL Net Credit", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "gl_net_balance", "label": "GL Net Balance", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "gl_account_non_zero_count", "label": "GL Account Non-Zero Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "movement_guardrail_section", "label": "Movement Guardrails", "fieldtype": "Section Break"},
            {"fieldname": "payment_entry_count_before", "label": "Payment Entry Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_count_after", "label": "Payment Entry Count After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_count_before", "label": "Payment Entry GL Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_count_after", "label": "Payment Entry GL Count After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "actual_payment_entry_created_count", "label": "Actual Payment Entry Created Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "actual_gl_created_count", "label": "Actual GL Created Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "submitted_journal_entry_count_today", "label": "Submitted JE Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "purchase_invoice_count_today", "label": "Purchase Invoice Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "site_section", "label": "Site / Config", "fieldtype": "Section Break"},
            {"fieldname": "site_name", "label": "Site Name", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "sandbox_config_enabled", "label": "Sandbox Config Enabled", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "production_mode_detected", "label": "Production Mode Detected", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "live_payment_entry_posting_config", "label": "Live PE Posting Config", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "checked_on", "label": "Checked On", "fieldtype": "Datetime", "read_only": 1, "in_list_view": 1},
            {"fieldname": "checked_by", "label": "Checked By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "score_section", "label": "Decision Score", "fieldtype": "Section Break"},
            {"fieldname": "decision_score", "label": "Decision Score", "fieldtype": "Percent", "read_only": 1},
            {"fieldname": "blocker_count", "label": "Blocker Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "warning_count", "label": "Warning Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "pass_count", "label": "Pass Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "info_count", "label": "Info Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "item_count", "label": "Item Count", "fieldtype": "Int", "read_only": 1},
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


def create_item_doctype():
    _create_doctype(
        name="NDIS Guarded Adapter Final Policy Decision Item",
        autoname="hash",
        title_field="check_label",
        fields=[
            {"fieldname": "decision", "label": "Decision", "fieldtype": "Link", "options": "NDIS Guarded Adapter Final Policy Decision", "reqd": 1, "in_list_view": 1},
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
    add_shortcuts_to_child_table(ws)
    ws.save(ignore_permissions=True)


def add_shortcuts_to_content_json(ws):
    if not ws.meta.has_field("content"):
        return
    try:
        content = json.loads(ws.content or "[]")
    except Exception:
        content = []
    text_blob = json.dumps(content)
    if "Guarded Adapter Final Policy Decision" not in text_blob:
        content.append({"id": "ndis_guarded_adapter_final_policy_decision_heading", "type": "header", "data": {"text": "Guarded Adapter Final Policy Decision", "col": 12}})
    for shortcut in WORKSPACE_SHORTCUTS:
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            continue
        content.append({"id": frappe.scrub(shortcut["label"]), "type": "shortcut", "data": {"label": shortcut["label"], "link_to": shortcut["link_to"], "type": shortcut["type"], "col": 3}})
    ws.content = json.dumps(content)


def add_shortcuts_to_child_table(ws):
    # Workspace content JSON is the stable representation for these phase links.
    return


@frappe.whitelist()
def health_check():
    doctypes = {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE10E_DOCTYPES}
    reports = {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS}
    hooks = frappe.get_hooks()
    doctype_js = hooks.get("doctype_js", {})
    doctype_list_js = hooks.get("doctype_list_js", {})
    return {
        "doctypes": doctypes,
        "reports": reports,
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_guarded_adapter_final_policy_decision_keep_enabled": permission_matrix().get("run_guarded_adapter_final_policy_decision_keep_enabled"),
            "cancel_guarded_adapter_final_policy_decision_audit": permission_matrix().get("cancel_guarded_adapter_final_policy_decision_audit"),
        },
        "js_hooks": {
            "NDIS Guarded Adapter Final Policy Decision": "NDIS Guarded Adapter Final Policy Decision" in doctype_js,
            "NDIS Guarded Adapter Final Policy Decision Item": "NDIS Guarded Adapter Final Policy Decision Item" in doctype_js,
        },
        "list_js_hooks": {
            "NDIS Guarded Adapter Final Policy Decision": "NDIS Guarded Adapter Final Policy Decision" in doctype_list_js,
            "NDIS Guarded Adapter Final Policy Decision Item": "NDIS Guarded Adapter Final Policy Decision Item" in doctype_list_js,
        },
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_payment_entry_posting_config": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def can_import_service():
    try:
        from ndis_finance.services.guarded_adapter_final_policy_decision import quick_guarded_adapter_final_policy_decision_summary

        return callable(quick_guarded_adapter_final_policy_decision_summary)
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
