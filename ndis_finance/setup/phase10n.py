import json

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


BASELINE_DOCTYPE = "NDIS Controlled Limited Ops Baseline"
BASELINE_ITEM_DOCTYPE = "NDIS Controlled Limited Ops Baseline Item"

PHASE10N_DOCTYPES = [BASELINE_DOCTYPE, BASELINE_ITEM_DOCTYPE]

REPORTS = [
    {"report_name": "NDIS Controlled Limited Ops Baseline Report", "ref_doctype": BASELINE_DOCTYPE},
    {"report_name": "NDIS Controlled Limited Ops Baseline Item Report", "ref_doctype": BASELINE_ITEM_DOCTYPE},
    {"report_name": "NDIS Controlled Limited Ops Baseline Guardrail Report", "ref_doctype": BASELINE_DOCTYPE},
]

REPORT_ROLES = [
    "System Manager",
    "NDIS CFO",
    "NDIS Finance Manager",
    "NDIS Finance Officer",
    "NDIS Finance Read Only",
]

DOC_PERM_MATRIX = {
    BASELINE_DOCTYPE: {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
    BASELINE_ITEM_DOCTYPE: {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
}

WORKSPACE_NAME = "NDIS Finance"
WORKSPACE_SHORTCUTS = [
    {"label": "Controlled Limited Ops Baselines", "type": "DocType", "link_to": BASELINE_DOCTYPE},
    {"label": "Controlled Limited Ops Baseline Items", "type": "DocType", "link_to": BASELINE_ITEM_DOCTYPE},
    {"label": "Controlled Limited Ops Baseline Report", "type": "Report", "link_to": "NDIS Controlled Limited Ops Baseline Report"},
    {"label": "Controlled Limited Ops Baseline Item Report", "type": "Report", "link_to": "NDIS Controlled Limited Ops Baseline Item Report"},
    {"label": "Controlled Limited Ops Baseline Guardrails", "type": "Report", "link_to": "NDIS Controlled Limited Ops Baseline Guardrail Report"},
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_baseline_doctype()
    create_item_doctype()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Limited Operation Closeout Gate",
        "NDIS Limited Operation Closeout Gate Item",
        "NDIS Single Guarded Op Smoke Rollback Freeze",
        "NDIS Single Guarded Limited Operation Smoke Rollback",
        "NDIS Single Guarded Limited Operation Smoke",
        "NDIS Guarded Limited Operation Execution Gate",
        "NDIS Guarded Limited Operation Preview",
        "NDIS Controlled Limited Operation Pre Check",
        "NDIS Controlled Limited Operations Monitoring Register",
        "NDIS Guarded Adapter Final Policy Decision",
        "NDIS Controlled Production Batch Posting Policy",
        "Payment Entry",
        "GL Entry",
        "Report",
        "Workspace",
    ]
    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]
    if missing:
        frappe.throw(_("Phase 10N requires completed Phase 10M closeout. Missing: {0}").format(", ".join(missing)))


def create_baseline_doctype():
    _create_doctype(
        name=BASELINE_DOCTYPE,
        autoname="field:baseline_id",
        title_field="baseline_id",
        fields=[
            {"fieldname": "baseline_id", "label": "Baseline ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nNeeds Review\nBaseline Active\nBlocked\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "baseline_status", "label": "Baseline Status", "fieldtype": "Select", "options": "\nControlled Limited Operations Steady-State Baseline Active\nNeeds Review\nBlocked\nCancelled", "read_only": 1, "in_list_view": 1},
            {"fieldname": "baseline_section", "label": "Baseline Result", "fieldtype": "Section Break"},
            {"fieldname": "baseline_active", "label": "Baseline Active", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "ready_for_controlled_limited_operations_execution", "label": "Ready For Controlled Limited Operations Execution", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "ready_for_steady_state_monitoring", "label": "Ready For Steady State Monitoring", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "steady_state_baseline_locked", "label": "Steady State Baseline Locked", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "full_cycle_closeout_verified", "label": "Full Cycle Closeout Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "operating_limits_captured", "label": "Operating Limits Captured", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "no_new_accounting_movement_verified", "label": "No New Accounting Movement Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "policy_state_preserved_verified", "label": "Policy State Preserved Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "policy_mutation_performed", "label": "Policy Mutation Performed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "actual_policy_mutation_count", "label": "Actual Policy Mutation Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "phase_section", "label": "Phase Verification", "fieldtype": "Section Break"},
            *[
                {"fieldname": fieldname, "label": label, "fieldtype": "Check", "read_only": 1}
                for fieldname, label in [
                    ("phase10m_closeout_verified", "Phase 10M Closeout Verified"),
                    ("phase10l_freeze_verified", "Phase 10L Freeze Verified"),
                    ("phase10k_rollback_verified", "Phase 10K Rollback Verified"),
                    ("phase10j_smoke_verified", "Phase 10J Smoke Verified"),
                    ("phase10i_gate_verified", "Phase 10I Gate Verified"),
                    ("phase10h_preview_verified", "Phase 10H Preview Verified"),
                    ("phase10g_pre_check_verified", "Phase 10G Pre Check Verified"),
                    ("phase10f_monitoring_register_verified", "Phase 10F Monitoring Register Verified"),
                    ("phase10e_policy_decision_verified", "Phase 10E Policy Decision Verified"),
                    ("controlled_policy_enabled_verified", "Controlled Policy Enabled Verified"),
                    ("live_posting_blocked_verified", "Live Posting Blocked Verified"),
                ]
            ],
            {"fieldname": "chain_section", "label": "Evidence Chain", "fieldtype": "Section Break"},
            {"fieldname": "closeout", "label": "Phase 10M Closeout", "fieldtype": "Link", "options": "NDIS Limited Operation Closeout Gate", "in_list_view": 1},
            {"fieldname": "freeze", "label": "Phase 10L Freeze", "fieldtype": "Link", "options": "NDIS Single Guarded Op Smoke Rollback Freeze"},
            {"fieldname": "rollback", "label": "Phase 10K Rollback", "fieldtype": "Link", "options": "NDIS Single Guarded Limited Operation Smoke Rollback"},
            {"fieldname": "smoke", "label": "Phase 10J Smoke", "fieldtype": "Link", "options": "NDIS Single Guarded Limited Operation Smoke"},
            {"fieldname": "execution_gate", "label": "Phase 10I Execution Gate", "fieldtype": "Link", "options": "NDIS Guarded Limited Operation Execution Gate"},
            {"fieldname": "preview", "label": "Phase 10H Preview", "fieldtype": "Link", "options": "NDIS Guarded Limited Operation Preview"},
            {"fieldname": "pre_check", "label": "Phase 10G Pre Check", "fieldtype": "Link", "options": "NDIS Controlled Limited Operation Pre Check"},
            {"fieldname": "monitoring_register", "label": "Phase 10F Monitoring Register", "fieldtype": "Link", "options": "NDIS Controlled Limited Operations Monitoring Register"},
            {"fieldname": "policy_decision", "label": "Phase 10E Policy Decision", "fieldtype": "Link", "options": "NDIS Guarded Adapter Final Policy Decision"},
            {"fieldname": "policy_section", "label": "Policy Evidence", "fieldtype": "Section Break"},
            {"fieldname": "target_policy_doctype", "label": "Target Policy DocType", "fieldtype": "Link", "options": "DocType", "read_only": 1},
            {"fieldname": "target_policy", "label": "Target Policy", "fieldtype": "Dynamic Link", "options": "target_policy_doctype"},
            {"fieldname": "target_policy_name", "label": "Target Policy Name", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "target_policy_enabled_before", "label": "Target Policy Enabled Before", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "target_policy_enabled_after", "label": "Target Policy Enabled After", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "target_policy_live_before", "label": "Target Policy Live Before", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "target_policy_live_after", "label": "Target Policy Live After", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "production_batch_enabled_policy_count_before", "label": "Enabled Policy Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "production_batch_enabled_policy_count_after", "label": "Enabled Policy Count After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "live_posting_allowed_policy_count_before", "label": "Live Policy Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "live_posting_allowed_policy_count_after", "label": "Live Policy Count After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "limits_section", "label": "Steady-State Operating Limits", "fieldtype": "Section Break"},
            {"fieldname": "max_batch_line_count", "label": "Max Batch Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "max_batch_amount", "label": "Max Batch Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "max_payment_entry_count", "label": "Max Payment Entry Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "live_posting_allowed", "label": "Live Posting Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "journal_entry_side_effect_allowed", "label": "Journal Entry Side Effect Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "purchase_invoice_side_effect_allowed", "label": "Purchase Invoice Side Effect Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "payment_entry_section", "label": "Closed Cycle Payment Entry Evidence", "fieldtype": "Section Break"},
            {"fieldname": "payment_entry", "label": "Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "read_only": 1, "in_list_view": 1},
            {"fieldname": "payment_entry_docstatus", "label": "Payment Entry Docstatus", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_status", "label": "Payment Entry Status", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "payment_entry_amount", "label": "Payment Entry Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "payment_entry_reference_count", "label": "Payment Entry Reference Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "invoice_outstanding_total", "label": "Invoice Outstanding Total", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "gl_net_balance", "label": "GL Net Balance", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "gl_account_non_zero_count", "label": "GL Account Non-Zero Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "movement_guardrail_section", "label": "Movement Guardrails", "fieldtype": "Section Break"},
            {"fieldname": "payment_entry_count_before", "label": "Payment Entry Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_count_after", "label": "Payment Entry Count After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_count_before", "label": "Payment Entry GL Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_count_after", "label": "Payment Entry GL Count After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "actual_payment_entry_created_count", "label": "Actual Payment Entry Created Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "actual_payment_entry_cancelled_count", "label": "Actual Payment Entry Cancelled Count", "fieldtype": "Int", "read_only": 1},
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
            {"fieldname": "score_section", "label": "Baseline Score", "fieldtype": "Section Break"},
            {"fieldname": "baseline_score", "label": "Baseline Score", "fieldtype": "Percent", "read_only": 1},
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
            {"fieldname": "evidence_json", "label": "Evidence JSON", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
        ],
    )


def create_item_doctype():
    _create_doctype(
        name=BASELINE_ITEM_DOCTYPE,
        autoname="hash",
        title_field="check_label",
        fields=[
            {"fieldname": "baseline", "label": "Baseline", "fieldtype": "Link", "options": BASELINE_DOCTYPE, "reqd": 1, "in_list_view": 1},
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
    doc = frappe.get_doc("Report", report_name) if frappe.db.exists("Report", report_name) else frappe.new_doc("Report")
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
    if "Controlled Limited Ops Baseline" not in text_blob:
        content.append({"id": "ndis_controlled_limited_ops_baseline_heading", "type": "header", "data": {"text": "Controlled Limited Ops Baseline", "col": 12}})
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
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE10N_DOCTYPES},
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_controlled_limited_operations_steady_state_baseline": permission_matrix().get("run_controlled_limited_operations_steady_state_baseline"),
            "cancel_controlled_limited_operations_steady_state_baseline_audit": permission_matrix().get("cancel_controlled_limited_operations_steady_state_baseline_audit"),
        },
        "js_hooks": {
            BASELINE_DOCTYPE: BASELINE_DOCTYPE in doctype_js,
            BASELINE_ITEM_DOCTYPE: BASELINE_ITEM_DOCTYPE in doctype_js,
        },
        "list_js_hooks": {
            BASELINE_DOCTYPE: BASELINE_DOCTYPE in doctype_list_js,
            BASELINE_ITEM_DOCTYPE: BASELINE_ITEM_DOCTYPE in doctype_list_js,
        },
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_payment_entry_posting_config": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def can_import_service():
    try:
        from ndis_finance.services.controlled_limited_operations_steady_state_baseline import quick_controlled_limited_operations_steady_state_baseline_summary

        return callable(quick_controlled_limited_operations_steady_state_baseline_summary)
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
