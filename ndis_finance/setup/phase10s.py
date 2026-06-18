import json

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


READINESS_DOCTYPE = "NDIS Governed Limited Ops Readiness"
READINESS_ITEM_DOCTYPE = "NDIS Governed Limited Ops Readiness Item"
PHASE10S_DOCTYPES = [READINESS_DOCTYPE, READINESS_ITEM_DOCTYPE]

REPORTS = [
    {"report_name": "NDIS Governed Limited Ops Readiness Report", "ref_doctype": READINESS_DOCTYPE},
    {"report_name": "NDIS Governed Limited Ops Readiness Item Report", "ref_doctype": READINESS_ITEM_DOCTYPE},
    {"report_name": "NDIS Governed Limited Ops Readiness Guardrail Report", "ref_doctype": READINESS_DOCTYPE},
]

REPORT_ROLES = ["System Manager", "NDIS CFO", "NDIS Finance Manager", "NDIS Finance Officer", "NDIS Finance Read Only"]
DOC_PERM_MATRIX = {
    READINESS_DOCTYPE: {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
    READINESS_ITEM_DOCTYPE: {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
}

WORKSPACE_NAME = "NDIS Finance"
WORKSPACE_SHORTCUTS = [
    {"label": "Governed Limited Ops Readiness", "type": "DocType", "link_to": READINESS_DOCTYPE},
    {"label": "Governed Limited Ops Readiness Items", "type": "DocType", "link_to": READINESS_ITEM_DOCTYPE},
    {"label": "Governed Limited Ops Readiness Report", "type": "Report", "link_to": "NDIS Governed Limited Ops Readiness Report"},
    {"label": "Governed Limited Ops Readiness Item Report", "type": "Report", "link_to": "NDIS Governed Limited Ops Readiness Item Report"},
    {"label": "Governed Limited Ops Readiness Guardrails", "type": "Report", "link_to": "NDIS Governed Limited Ops Readiness Guardrail Report"},
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_readiness_doctype()
    create_item_doctype()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Runtime Watch Governance Closeout",
        "NDIS Runtime Watch Governance Closeout Item",
        "NDIS Runtime Watch Violation Sim Freeze",
        "NDIS Runtime Watch Violation Sim",
        "NDIS Controlled Limited Ops Runtime Watch",
        "NDIS Controlled Limited Ops Baseline",
        "NDIS Limited Operation Closeout Gate",
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
        frappe.throw(_("Phase 10S requires completed Phase 10R governance closeout. Missing: {0}").format(", ".join(missing)))


def create_readiness_doctype():
    _create_doctype(
        name=READINESS_DOCTYPE,
        autoname="field:readiness_id",
        title_field="readiness_id",
        fields=[
            {"fieldname": "readiness_id", "label": "Readiness ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nNeeds Review\nReadiness Approved\nBlocked\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "readiness_status", "label": "Readiness Status", "fieldtype": "Select", "options": "\nGoverned Controlled Limited Operations Ready\nNeeds Review\nBlocked\nCancelled", "read_only": 1, "in_list_view": 1},
            {"fieldname": "result_section", "label": "Readiness Result", "fieldtype": "Section Break"},
            *[
                {"fieldname": fieldname, "label": label, "fieldtype": "Check", "read_only": 1, **({"in_list_view": 1} if fieldname in {"readiness_approved", "governed_controlled_limited_operations_ready"} else {})}
                for fieldname, label in [
                    ("readiness_approved", "Readiness Approved"),
                    ("governed_controlled_limited_operations_ready", "Governed Controlled Limited Operations Ready"),
                    ("ready_for_governed_limited_operation_pre_execution_gate", "Ready For Governed Limited Operation Pre-Execution Gate"),
                    ("runtime_watch_governance_closeout_verified", "Runtime Watch Governance Closeout Verified"),
                    ("governed_limits_locked", "Governed Limits Locked"),
                    ("locked_runtime_limits_verified", "Locked Runtime Limits Verified"),
                    ("live_posting_remains_blocked", "Live Posting Remains Blocked"),
                    ("journal_entry_side_effect_remains_blocked", "JE Side Effect Remains Blocked"),
                    ("purchase_invoice_side_effect_remains_blocked", "PI Side Effect Remains Blocked"),
                    ("no_new_accounting_movement_verified", "No New Accounting Movement Verified"),
                    ("policy_state_preserved_verified", "Policy State Preserved Verified"),
                    ("policy_mutation_performed", "Policy Mutation Performed"),
                ]
            ],
            {"fieldname": "actual_policy_mutation_count", "label": "Actual Policy Mutation Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "phase_section", "label": "Phase Verification", "fieldtype": "Section Break"},
            *[
                {"fieldname": fieldname, "label": label, "fieldtype": "Check", "read_only": 1}
                for fieldname, label in [
                    ("phase10r_governance_closeout_verified", "Phase 10R Governance Closeout Verified"),
                    ("phase10q_freeze_verified", "Phase 10Q Freeze Verified"),
                    ("phase10p_simulation_verified", "Phase 10P Simulation Verified"),
                    ("phase10o_runtime_watch_verified", "Phase 10O Runtime Watch Verified"),
                    ("phase10n_baseline_verified", "Phase 10N Baseline Verified"),
                    ("phase10m_closeout_verified", "Phase 10M Closeout Verified"),
                    ("controlled_policy_enabled_verified", "Controlled Policy Enabled Verified"),
                    ("live_posting_blocked_verified", "Live Posting Blocked Verified"),
                ]
            ],
            {"fieldname": "chain_section", "label": "Evidence Chain", "fieldtype": "Section Break"},
            {"fieldname": "governance_closeout", "label": "Phase 10R Governance Closeout", "fieldtype": "Link", "options": "NDIS Runtime Watch Governance Closeout", "in_list_view": 1},
            {"fieldname": "freeze", "label": "Phase 10Q Freeze", "fieldtype": "Link", "options": "NDIS Runtime Watch Violation Sim Freeze"},
            {"fieldname": "simulation", "label": "Phase 10P Simulation", "fieldtype": "Link", "options": "NDIS Runtime Watch Violation Sim"},
            {"fieldname": "runtime_watch", "label": "Phase 10O Runtime Watch", "fieldtype": "Link", "options": "NDIS Controlled Limited Ops Runtime Watch"},
            {"fieldname": "baseline", "label": "Phase 10N Baseline", "fieldtype": "Link", "options": "NDIS Controlled Limited Ops Baseline"},
            {"fieldname": "closeout", "label": "Phase 10M Closeout", "fieldtype": "Link", "options": "NDIS Limited Operation Closeout Gate"},
            {"fieldname": "monitoring_register", "label": "Phase 10F Monitoring Register", "fieldtype": "Link", "options": "NDIS Controlled Limited Operations Monitoring Register"},
            {"fieldname": "policy_decision", "label": "Phase 10E Policy Decision", "fieldtype": "Link", "options": "NDIS Guarded Adapter Final Policy Decision"},
            {"fieldname": "policy_section", "label": "Policy Evidence", "fieldtype": "Section Break"},
            {"fieldname": "target_policy_doctype", "label": "Target Policy DocType", "fieldtype": "Link", "options": "DocType", "read_only": 1},
            {"fieldname": "target_policy", "label": "Target Policy", "fieldtype": "Dynamic Link", "options": "target_policy_doctype"},
            {"fieldname": "target_policy_name", "label": "Target Policy Name", "fieldtype": "Data", "read_only": 1},
            *[
                {"fieldname": fieldname, "label": label, "fieldtype": fieldtype, "read_only": 1}
                for fieldname, label, fieldtype in [
                    ("target_policy_enabled_before", "Target Policy Enabled Before", "Check"),
                    ("target_policy_enabled_after", "Target Policy Enabled After", "Check"),
                    ("target_policy_live_before", "Target Policy Live Before", "Check"),
                    ("target_policy_live_after", "Target Policy Live After", "Check"),
                    ("production_batch_enabled_policy_count_before", "Enabled Policy Count Before", "Int"),
                    ("production_batch_enabled_policy_count_after", "Enabled Policy Count After", "Int"),
                    ("live_posting_allowed_policy_count_before", "Live Policy Count Before", "Int"),
                    ("live_posting_allowed_policy_count_after", "Live Policy Count After", "Int"),
                ]
            ],
            {"fieldname": "limits_section", "label": "Readiness Locked Limits", "fieldtype": "Section Break"},
            {"fieldname": "max_batch_line_count", "label": "Max Batch Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "max_batch_amount", "label": "Max Batch Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "max_payment_entry_count", "label": "Max Payment Entry Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "live_posting_allowed", "label": "Live Posting Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "journal_entry_side_effect_allowed", "label": "Journal Entry Side Effect Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "purchase_invoice_side_effect_allowed", "label": "Purchase Invoice Side Effect Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "violation_section", "label": "Governed Violation Evidence", "fieldtype": "Section Break"},
            {"fieldname": "violation_simulation_count", "label": "Violation Simulation Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "blocked_violation_count", "label": "Blocked Violation Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "failed_violation_count", "label": "Failed Violation Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "all_runtime_violations_blocked_verified", "label": "All Runtime Violations Blocked Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "movement_section", "label": "Movement Guardrails", "fieldtype": "Section Break"},
            *[
                {"fieldname": fieldname, "label": label, "fieldtype": "Int", "read_only": 1}
                for fieldname, label in [
                    ("payment_entry_count_before", "Payment Entry Count Before"),
                    ("payment_entry_count_after", "Payment Entry Count After"),
                    ("payment_entry_gl_count_before", "Payment Entry GL Count Before"),
                    ("payment_entry_gl_count_after", "Payment Entry GL Count After"),
                    ("actual_payment_entry_created_count", "Actual Payment Entry Created Count"),
                    ("actual_payment_entry_cancelled_count", "Actual Payment Entry Cancelled Count"),
                    ("actual_gl_created_count", "Actual GL Created Count"),
                    ("submitted_journal_entry_count_today", "Submitted JE Count Today"),
                    ("purchase_invoice_count_today", "Purchase Invoice Count Today"),
                ]
            ],
            {"fieldname": "site_section", "label": "Site / Config", "fieldtype": "Section Break"},
            {"fieldname": "site_name", "label": "Site Name", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "sandbox_config_enabled", "label": "Sandbox Config Enabled", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "production_mode_detected", "label": "Production Mode Detected", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "live_payment_entry_posting_config", "label": "Live PE Posting Config", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "checked_on", "label": "Checked On", "fieldtype": "Datetime", "read_only": 1, "in_list_view": 1},
            {"fieldname": "checked_by", "label": "Checked By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "score_section", "label": "Readiness Score", "fieldtype": "Section Break"},
            {"fieldname": "readiness_score", "label": "Readiness Score", "fieldtype": "Percent", "read_only": 1},
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
        name=READINESS_ITEM_DOCTYPE,
        autoname="hash",
        title_field="check_label",
        fields=[
            {"fieldname": "readiness", "label": "Readiness", "fieldtype": "Link", "options": READINESS_DOCTYPE, "reqd": 1, "in_list_view": 1},
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
    if not ws.meta.has_field("content"):
        return
    try:
        content = json.loads(ws.content or "[]")
    except Exception:
        content = []
    text_blob = json.dumps(content)
    if "Governed Limited Ops Readiness" not in text_blob:
        content.append({"id": "ndis_governed_limited_ops_readiness_heading", "type": "header", "data": {"text": "Governed Limited Ops Readiness", "col": 12}})
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
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE10S_DOCTYPES},
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_governed_limited_ops_readiness": permission_matrix().get("run_governed_limited_ops_readiness"),
            "cancel_governed_limited_ops_readiness_audit": permission_matrix().get("cancel_governed_limited_ops_readiness_audit"),
        },
        "js_hooks": {READINESS_DOCTYPE: READINESS_DOCTYPE in doctype_js, READINESS_ITEM_DOCTYPE: READINESS_ITEM_DOCTYPE in doctype_js},
        "list_js_hooks": {READINESS_DOCTYPE: READINESS_DOCTYPE in doctype_list_js, READINESS_ITEM_DOCTYPE: READINESS_ITEM_DOCTYPE in doctype_list_js},
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_payment_entry_posting_config": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def can_import_service():
    try:
        from ndis_finance.services.governed_limited_ops_readiness import quick_governed_limited_ops_readiness_summary

        return callable(quick_governed_limited_ops_readiness_summary)
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
        result[shortcut["label"]] = shortcut["label"] in text_blob or shortcut["link_to"] in text_blob
    return result
