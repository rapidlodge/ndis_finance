import json

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


PHASE10B_DOCTYPES = [
    "NDIS Guarded Limited Adapter Smoke Rollback",
    "NDIS Guarded Limited Adapter Smoke Rollback Item",
]

REPORTS = [
    {"report_name": "NDIS Guarded Limited Adapter Smoke Rollback Report", "ref_doctype": "NDIS Guarded Limited Adapter Smoke Rollback"},
    {"report_name": "NDIS Guarded Limited Adapter Smoke Rollback Item Report", "ref_doctype": "NDIS Guarded Limited Adapter Smoke Rollback Item"},
    {"report_name": "NDIS Guarded Limited Adapter Smoke Rollback Guardrail Report", "ref_doctype": "NDIS Guarded Limited Adapter Smoke Rollback"},
]

REPORT_ROLES = [
    "System Manager",
    "NDIS CFO",
    "NDIS Finance Manager",
    "NDIS Finance Officer",
    "NDIS Finance Read Only",
]

DOC_PERM_MATRIX = {
    "NDIS Guarded Limited Adapter Smoke Rollback": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Guarded Limited Adapter Smoke Rollback Item": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
}

WORKSPACE_NAME = "NDIS Finance"

WORKSPACE_SHORTCUTS = [
    {"label": "Guarded Limited Adapter Smoke Rollbacks", "type": "DocType", "link_to": "NDIS Guarded Limited Adapter Smoke Rollback"},
    {"label": "Guarded Limited Adapter Smoke Rollback Items", "type": "DocType", "link_to": "NDIS Guarded Limited Adapter Smoke Rollback Item"},
    {"label": "Guarded Limited Adapter Smoke Rollback Report", "type": "Report", "link_to": "NDIS Guarded Limited Adapter Smoke Rollback Report"},
    {"label": "Guarded Limited Adapter Smoke Rollback Item Report", "type": "Report", "link_to": "NDIS Guarded Limited Adapter Smoke Rollback Item Report"},
    {"label": "Guarded Limited Adapter Smoke Rollback Guardrails", "type": "Report", "link_to": "NDIS Guarded Limited Adapter Smoke Rollback Guardrail Report"},
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_rollback_doctype()
    create_item_doctype()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Guarded Limited Adapter Smoke",
        "NDIS Guarded Limited Adapter Smoke Item",
        "NDIS Limited Batch Adapter Activation Gate",
        "NDIS Limited Batch Runtime Guard",
        "NDIS Controlled Production Batch Posting Policy",
        "Payment Entry",
        "Payment Entry Reference",
        "GL Entry",
        "Sales Invoice",
        "Report",
        "Workspace",
    ]
    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]
    if missing:
        frappe.throw(_("Phase 10B requires completed Phase 10A smoke. Missing: {0}").format(", ".join(missing)))


def create_rollback_doctype():
    _create_doctype(
        name="NDIS Guarded Limited Adapter Smoke Rollback",
        autoname="field:rollback_id",
        title_field="rollback_id",
        fields=[
            {"fieldname": "rollback_id", "label": "Rollback ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nNeeds Review\nRolled Back\nBlocked\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "rollback_status", "label": "Rollback Status", "fieldtype": "Select", "options": "\nGuarded Limited Adapter Smoke Rolled Back - Freeze Required\nNeeds Review\nBlocked\nCancelled", "read_only": 1, "in_list_view": 1},
            {"fieldname": "decision_section", "label": "Rollback Decision", "fieldtype": "Section Break"},
            {"fieldname": "rollback_completed", "label": "Rollback Completed", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "freeze_required_after_rollback", "label": "Freeze Required After Rollback", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "ready_for_adapter_smoke_freeze", "label": "Ready For Adapter Smoke Freeze", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "phase10a_smoke_verified", "label": "Phase 10A Smoke Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "phase9z_activation_gate_verified", "label": "Phase 9Z Activation Gate Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "payment_entry_cancelled_verified", "label": "Payment Entry Cancelled Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "payment_entry_gl_reversal_verified", "label": "Payment Entry GL Reversal Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "gl_net_zero_verified", "label": "GL Net Zero Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "invoice_outstanding_restored_verified", "label": "Invoice Outstanding Restored Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "no_journal_entry_verified", "label": "No Journal Entry Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "no_purchase_invoice_verified", "label": "No Purchase Invoice Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "controlled_policy_enabled_verified", "label": "Controlled Policy Enabled Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "live_posting_blocked_verified", "label": "Live Posting Blocked Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "chain_section", "label": "Evidence Chain", "fieldtype": "Section Break"},
            {"fieldname": "smoke", "label": "Phase 10A Smoke", "fieldtype": "Link", "options": "NDIS Guarded Limited Adapter Smoke", "in_list_view": 1},
            {"fieldname": "activation_gate", "label": "Phase 9Z Activation Gate", "fieldtype": "Link", "options": "NDIS Limited Batch Adapter Activation Gate"},
            {"fieldname": "runtime_guard", "label": "Phase 9V Runtime Guard", "fieldtype": "Link", "options": "NDIS Limited Batch Runtime Guard"},
            {"fieldname": "policy_section", "label": "Policy Evidence", "fieldtype": "Section Break"},
            {"fieldname": "target_policy_doctype", "label": "Target Policy DocType", "fieldtype": "Link", "options": "DocType", "read_only": 1},
            {"fieldname": "target_policy", "label": "Target Policy", "fieldtype": "Dynamic Link", "options": "target_policy_doctype", "in_list_view": 1},
            {"fieldname": "target_policy_name", "label": "Target Policy Name", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "current_target_policy_enabled", "label": "Current Target Policy Enabled", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "current_target_policy_live", "label": "Current Target Policy Live", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "production_batch_enabled_policy_count", "label": "Production Batch Enabled Policy Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "live_posting_allowed_policy_count", "label": "Live Posting Allowed Policy Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_section", "label": "Payment Entry Rollback", "fieldtype": "Section Break"},
            {"fieldname": "payment_entry", "label": "Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "read_only": 1, "in_list_view": 1},
            {"fieldname": "payment_entry_docstatus_before", "label": "PE Docstatus Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_docstatus_after", "label": "PE Docstatus After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_status_before", "label": "PE Status Before", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "payment_entry_status_after", "label": "PE Status After", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "payment_entry_amount", "label": "Payment Entry Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "payment_entry_reference_count", "label": "Payment Entry Reference Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_count_before", "label": "Payment Entry GL Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_count_after", "label": "Payment Entry GL Count After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_reversal_count", "label": "Payment Entry GL Reversal Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "outstanding_section", "label": "Invoice Outstanding Restoration", "fieldtype": "Section Break"},
            {"fieldname": "invoice_reference_count", "label": "Invoice Reference Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "allocated_amount_total", "label": "Allocated Amount Total", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "invoice_outstanding_before", "label": "Invoice Outstanding Before", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "invoice_outstanding_after", "label": "Invoice Outstanding After", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "invoice_outstanding_restored_delta", "label": "Invoice Outstanding Restored Delta", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "gl_section", "label": "GL Net Zero Proof", "fieldtype": "Section Break"},
            {"fieldname": "gl_net_debit", "label": "GL Net Debit", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "gl_net_credit", "label": "GL Net Credit", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "gl_net_balance", "label": "GL Net Balance", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "gl_account_net_zero_count", "label": "GL Account Net Zero Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "movement_guardrail_section", "label": "Movement Guardrails", "fieldtype": "Section Break"},
            {"fieldname": "payment_entry_count_before", "label": "Payment Entry Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_count_after", "label": "Payment Entry Count After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_total_count_before", "label": "Payment Entry GL Total Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_total_count_after", "label": "Payment Entry GL Total Count After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "actual_payment_entry_created_count", "label": "Actual Payment Entry Created Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "actual_payment_entry_cancelled_count", "label": "Actual Payment Entry Cancelled Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "actual_gl_reversal_created_count", "label": "Actual GL Reversal Created Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "submitted_journal_entry_count_today", "label": "Submitted JE Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "purchase_invoice_count_today", "label": "Purchase Invoice Count Today", "fieldtype": "Int", "read_only": 1},
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
            {"fieldname": "ack_section", "label": "Acknowledgement", "fieldtype": "Section Break"},
            {"fieldname": "required_acknowledgement", "label": "Required Acknowledgement", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "acknowledgement", "label": "Acknowledgement", "fieldtype": "Data"},
            {"fieldname": "acknowledgement_ok", "label": "Acknowledgement OK", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "audit_section", "label": "Audit", "fieldtype": "Section Break"},
            {"fieldname": "cancelled_on", "label": "Cancelled On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "cancelled_by", "label": "Cancelled By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "summary_json", "label": "Summary JSON", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "reference_snapshot_json", "label": "Reference Snapshot JSON", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "gl_snapshot_json", "label": "GL Snapshot JSON", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
        ],
    )


def create_item_doctype():
    _create_doctype(
        name="NDIS Guarded Limited Adapter Smoke Rollback Item",
        autoname="hash",
        title_field="check_label",
        fields=[
            {"fieldname": "rollback", "label": "Rollback", "fieldtype": "Link", "options": "NDIS Guarded Limited Adapter Smoke Rollback", "reqd": 1, "in_list_view": 1},
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
    if "Guarded Limited Adapter Smoke Rollback" not in text_blob:
        content.append({"id": "ndis_guarded_limited_adapter_smoke_rollback_heading", "type": "header", "data": {"text": "Guarded Limited Adapter Smoke Rollback", "col": 12}})
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
    doctypes = {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE10B_DOCTYPES}
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
            "run_guarded_limited_adapter_smoke_rollback": permission_matrix().get("run_guarded_limited_adapter_smoke_rollback"),
            "cancel_guarded_limited_adapter_smoke_rollback_audit": permission_matrix().get("cancel_guarded_limited_adapter_smoke_rollback_audit"),
        },
        "js_hooks": {
            "NDIS Guarded Limited Adapter Smoke Rollback": "NDIS Guarded Limited Adapter Smoke Rollback" in doctype_js,
            "NDIS Guarded Limited Adapter Smoke Rollback Item": "NDIS Guarded Limited Adapter Smoke Rollback Item" in doctype_js,
        },
        "list_js_hooks": {
            "NDIS Guarded Limited Adapter Smoke Rollback": "NDIS Guarded Limited Adapter Smoke Rollback" in doctype_list_js,
            "NDIS Guarded Limited Adapter Smoke Rollback Item": "NDIS Guarded Limited Adapter Smoke Rollback Item" in doctype_list_js,
        },
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_payment_entry_posting_config": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def can_import_service():
    try:
        from ndis_finance.services.guarded_limited_adapter_smoke_rollback import quick_guarded_limited_adapter_smoke_rollback_summary

        return callable(quick_guarded_limited_adapter_smoke_rollback_summary)
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
