import json

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


PREVIEW_DOCTYPE = "NDIS Governed Limited Op Preview"
PREVIEW_ITEM_DOCTYPE = "NDIS Governed Limited Op Preview Item"
PHASE10U_DOCTYPES = [PREVIEW_DOCTYPE, PREVIEW_ITEM_DOCTYPE]

REPORTS = [
    {"report_name": "NDIS Governed Limited Op Preview Report", "ref_doctype": PREVIEW_DOCTYPE},
    {"report_name": "NDIS Governed Limited Op Preview Item Report", "ref_doctype": PREVIEW_ITEM_DOCTYPE},
    {"report_name": "NDIS Governed Limited Op Preview Guardrail Report", "ref_doctype": PREVIEW_DOCTYPE},
]

REPORT_ROLES = ["System Manager", "NDIS CFO", "NDIS Finance Manager", "NDIS Finance Officer", "NDIS Finance Read Only"]
DOC_PERM_MATRIX = {
    PREVIEW_DOCTYPE: {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
    PREVIEW_ITEM_DOCTYPE: {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
}

WORKSPACE_NAME = "NDIS Finance"
WORKSPACE_SHORTCUTS = [
    {"label": "Governed Limited Op Previews", "type": "DocType", "link_to": PREVIEW_DOCTYPE},
    {"label": "Governed Limited Op Preview Items", "type": "DocType", "link_to": PREVIEW_ITEM_DOCTYPE},
    {"label": "Governed Limited Op Preview Report", "type": "Report", "link_to": "NDIS Governed Limited Op Preview Report"},
    {"label": "Governed Limited Op Preview Item Report", "type": "Report", "link_to": "NDIS Governed Limited Op Preview Item Report"},
    {"label": "Governed Limited Op Preview Guardrails", "type": "Report", "link_to": "NDIS Governed Limited Op Preview Guardrail Report"},
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_preview_doctype()
    create_item_doctype()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Governed Limited Op Pre Exec",
        "NDIS Governed Limited Op Pre Exec Item",
        "NDIS Governed Limited Ops Readiness",
        "NDIS Runtime Watch Governance Closeout",
        "NDIS Runtime Watch Violation Sim Freeze",
        "NDIS Runtime Watch Violation Sim",
        "NDIS Controlled Limited Ops Runtime Watch",
        "NDIS Controlled Limited Ops Baseline",
        "NDIS Controlled Production Batch Posting Policy",
        "Payment Entry",
        "Payment Entry Reference",
        "Sales Invoice",
        "GL Entry",
        "Report",
        "Workspace",
    ]
    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]
    if missing:
        frappe.throw(_("Phase 10U requires completed Phase 10T pre-execution gate. Missing: {0}").format(", ".join(missing)))


def check_fields(names):
    return [{"fieldname": fieldname, "label": label, "fieldtype": "Check", "read_only": 1, **opts} for fieldname, label, opts in names]


def int_fields(names):
    return [{"fieldname": fieldname, "label": label, "fieldtype": "Int", "read_only": 1, **opts} for fieldname, label, opts in names]


def create_preview_doctype():
    _create_doctype(
        name=PREVIEW_DOCTYPE,
        autoname="field:preview_id",
        title_field="preview_id",
        fields=[
            {"fieldname": "preview_id", "label": "Preview ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nNeeds Review\nPreviewed\nBlocked\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "preview_status", "label": "Preview Status", "fieldtype": "Select", "options": "\nGoverned Limited Operation Preview Ready\nNeeds Review\nBlocked\nCancelled", "read_only": 1, "in_list_view": 1},
            {"fieldname": "result_section", "label": "Preview Result", "fieldtype": "Section Break"},
            *check_fields(
                [
                    ("preview_completed", "Preview Completed", {"in_list_view": 1}),
                    ("operation_previewed", "Operation Previewed", {"in_list_view": 1}),
                    ("operation_shape_verified", "Operation Shape Verified", {}),
                    ("operation_preview_locked", "Operation Preview Locked", {}),
                    ("ready_for_governed_limited_operation_execution_gate", "Ready For Governed Limited Operation Execution Gate", {}),
                    ("pre_execution_gate_verified", "Pre-Execution Gate Verified", {}),
                    ("preview_only_verified", "Preview Only Verified", {}),
                    ("no_new_accounting_movement_verified", "No New Accounting Movement Verified", {}),
                    ("policy_state_preserved_verified", "Policy State Preserved Verified", {}),
                    ("policy_mutation_performed", "Policy Mutation Performed", {}),
                ]
            ),
            {"fieldname": "actual_policy_mutation_count", "label": "Actual Policy Mutation Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "phase_section", "label": "Phase Verification", "fieldtype": "Section Break"},
            *check_fields(
                [
                    ("phase10t_pre_execution_verified", "Phase 10T Pre-Execution Verified", {}),
                    ("phase10s_readiness_verified", "Phase 10S Readiness Verified", {}),
                    ("phase10r_governance_closeout_verified", "Phase 10R Governance Closeout Verified", {}),
                    ("phase10q_freeze_verified", "Phase 10Q Freeze Verified", {}),
                    ("phase10p_simulation_verified", "Phase 10P Simulation Verified", {}),
                    ("phase10o_runtime_watch_verified", "Phase 10O Runtime Watch Verified", {}),
                    ("phase10n_baseline_verified", "Phase 10N Baseline Verified", {}),
                    ("controlled_policy_enabled_verified", "Controlled Policy Enabled Verified", {}),
                    ("live_posting_blocked_verified", "Live Posting Blocked Verified", {}),
                ]
            ),
            {"fieldname": "chain_section", "label": "Evidence Chain", "fieldtype": "Section Break"},
            {"fieldname": "pre_execution_gate", "label": "Phase 10T Pre-Execution Gate", "fieldtype": "Link", "options": "NDIS Governed Limited Op Pre Exec", "in_list_view": 1},
            {"fieldname": "readiness", "label": "Phase 10S Readiness", "fieldtype": "Link", "options": "NDIS Governed Limited Ops Readiness"},
            {"fieldname": "governance_closeout", "label": "Phase 10R Governance Closeout", "fieldtype": "Link", "options": "NDIS Runtime Watch Governance Closeout"},
            {"fieldname": "freeze", "label": "Phase 10Q Freeze", "fieldtype": "Link", "options": "NDIS Runtime Watch Violation Sim Freeze"},
            {"fieldname": "simulation", "label": "Phase 10P Simulation", "fieldtype": "Link", "options": "NDIS Runtime Watch Violation Sim"},
            {"fieldname": "runtime_watch", "label": "Phase 10O Runtime Watch", "fieldtype": "Link", "options": "NDIS Controlled Limited Ops Runtime Watch"},
            {"fieldname": "baseline", "label": "Phase 10N Baseline", "fieldtype": "Link", "options": "NDIS Controlled Limited Ops Baseline"},
            {"fieldname": "monitoring_register", "label": "Phase 10F Monitoring Register", "fieldtype": "Link", "options": "NDIS Controlled Limited Operations Monitoring Register"},
            {"fieldname": "policy_section", "label": "Policy Evidence", "fieldtype": "Section Break"},
            {"fieldname": "target_policy_doctype", "label": "Target Policy DocType", "fieldtype": "Link", "options": "DocType", "read_only": 1},
            {"fieldname": "target_policy", "label": "Target Policy", "fieldtype": "Dynamic Link", "options": "target_policy_doctype"},
            {"fieldname": "target_policy_name", "label": "Target Policy Name", "fieldtype": "Data", "read_only": 1},
            *check_fields(
                [
                    ("target_policy_enabled_before", "Target Policy Enabled Before", {}),
                    ("target_policy_enabled_after", "Target Policy Enabled After", {}),
                    ("target_policy_live_before", "Target Policy Live Before", {}),
                    ("target_policy_live_after", "Target Policy Live After", {}),
                ]
            ),
            *int_fields(
                [
                    ("production_batch_enabled_policy_count_before", "Enabled Policy Count Before", {}),
                    ("production_batch_enabled_policy_count_after", "Enabled Policy Count After", {}),
                    ("live_posting_allowed_policy_count_before", "Live Policy Count Before", {}),
                    ("live_posting_allowed_policy_count_after", "Live Policy Count After", {}),
                ]
            ),
            {"fieldname": "shape_section", "label": "Governed Operation Shape", "fieldtype": "Section Break"},
            {"fieldname": "requested_batch_line_count", "label": "Requested Batch Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "requested_batch_amount", "label": "Requested Batch Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "requested_payment_entry_count", "label": "Requested Payment Entry Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "requested_live_posting", "label": "Requested Live Posting", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "requested_journal_entry_side_effect", "label": "Requested Journal Entry Side Effect", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "requested_purchase_invoice_side_effect", "label": "Requested Purchase Invoice Side Effect", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "preview_section", "label": "Preview Build", "fieldtype": "Section Break"},
            {"fieldname": "preview_line_count", "label": "Preview Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "preview_total_amount", "label": "Preview Total Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "preview_customer", "label": "Preview Customer", "fieldtype": "Link", "options": "Customer", "read_only": 1},
            {"fieldname": "preview_company", "label": "Preview Company", "fieldtype": "Link", "options": "Company", "read_only": 1},
            {"fieldname": "source_payment_entry", "label": "Source Payment Entry Template", "fieldtype": "Link", "options": "Payment Entry", "read_only": 1},
            {"fieldname": "would_create_payment_entry_count", "label": "Would Create Payment Entry Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "would_create_gl_entry_count", "label": "Would Create GL Entry Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "movement_section", "label": "Movement Guardrails", "fieldtype": "Section Break"},
            *int_fields(
                [
                    ("payment_entry_count_before", "Payment Entry Count Before", {}),
                    ("payment_entry_count_after", "Payment Entry Count After", {}),
                    ("payment_entry_gl_count_before", "Payment Entry GL Count Before", {}),
                    ("payment_entry_gl_count_after", "Payment Entry GL Count After", {}),
                    ("actual_payment_entry_created_count", "Actual Payment Entry Created Count", {}),
                    ("actual_payment_entry_cancelled_count", "Actual Payment Entry Cancelled Count", {}),
                    ("actual_gl_created_count", "Actual GL Created Count", {}),
                    ("submitted_journal_entry_count_today", "Submitted JE Count Today", {}),
                    ("purchase_invoice_count_today", "Purchase Invoice Count Today", {}),
                ]
            ),
            {"fieldname": "site_section", "label": "Site / Config", "fieldtype": "Section Break"},
            {"fieldname": "site_name", "label": "Site Name", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "sandbox_config_enabled", "label": "Sandbox Config Enabled", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "production_mode_detected", "label": "Production Mode Detected", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "live_payment_entry_posting_config", "label": "Live PE Posting Config", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "checked_on", "label": "Checked On", "fieldtype": "Datetime", "read_only": 1, "in_list_view": 1},
            {"fieldname": "checked_by", "label": "Checked By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "score_section", "label": "Preview Score", "fieldtype": "Section Break"},
            {"fieldname": "preview_score", "label": "Preview Score", "fieldtype": "Percent", "read_only": 1},
            *int_fields(
                [
                    ("blocker_count", "Blocker Count", {}),
                    ("warning_count", "Warning Count", {}),
                    ("pass_count", "Pass Count", {}),
                    ("info_count", "Info Count", {}),
                    ("item_count", "Item Count", {}),
                ]
            ),
            {"fieldname": "ack_section", "label": "Acknowledgement", "fieldtype": "Section Break"},
            {"fieldname": "required_acknowledgement", "label": "Required Acknowledgement", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "acknowledgement", "label": "Acknowledgement", "fieldtype": "Data"},
            {"fieldname": "acknowledgement_ok", "label": "Acknowledgement OK", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "audit_section", "label": "Audit", "fieldtype": "Section Break"},
            {"fieldname": "cancelled_on", "label": "Cancelled On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "cancelled_by", "label": "Cancelled By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "summary_json", "label": "Summary JSON", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "preview_json", "label": "Preview JSON", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
        ],
    )


def create_item_doctype():
    _create_doctype(
        name=PREVIEW_ITEM_DOCTYPE,
        autoname="hash",
        title_field="reference_name",
        fields=[
            {"fieldname": "preview", "label": "Preview", "fieldtype": "Link", "options": PREVIEW_DOCTYPE, "reqd": 1, "in_list_view": 1},
            {"fieldname": "line_no", "label": "Line No", "fieldtype": "Int", "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nPass\nWarning\nBlocker\nInfo\nCancelled", "default": "Info", "in_list_view": 1},
            {"fieldname": "reference_doctype", "label": "Reference DocType", "fieldtype": "Link", "options": "DocType", "in_list_view": 1},
            {"fieldname": "reference_name", "label": "Reference Name", "fieldtype": "Dynamic Link", "options": "reference_doctype", "in_list_view": 1},
            {"fieldname": "customer", "label": "Customer", "fieldtype": "Link", "options": "Customer"},
            {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company"},
            {"fieldname": "posting_date", "label": "Posting Date", "fieldtype": "Date"},
            {"fieldname": "due_date", "label": "Due Date", "fieldtype": "Date"},
            {"fieldname": "outstanding_amount", "label": "Outstanding Amount", "fieldtype": "Currency"},
            {"fieldname": "allocated_amount", "label": "Allocated Amount", "fieldtype": "Currency"},
            {"fieldname": "preview_decision", "label": "Preview Decision", "fieldtype": "Select", "options": "\nIncluded\nBlocked"},
            {"fieldname": "detail", "label": "Detail", "fieldtype": "Small Text"},
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
    if "Governed Limited Operation Preview" not in text_blob:
        content.append({"id": "ndis_governed_limited_op_preview_heading", "type": "header", "data": {"text": "Governed Limited Operation Preview", "col": 12}})
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
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE10U_DOCTYPES},
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_governed_limited_operation_preview": permission_matrix().get("run_governed_limited_operation_preview"),
            "cancel_governed_limited_operation_preview_audit": permission_matrix().get("cancel_governed_limited_operation_preview_audit"),
        },
        "js_hooks": {PREVIEW_DOCTYPE: PREVIEW_DOCTYPE in doctype_js, PREVIEW_ITEM_DOCTYPE: PREVIEW_ITEM_DOCTYPE in doctype_js},
        "list_js_hooks": {PREVIEW_DOCTYPE: PREVIEW_DOCTYPE in doctype_list_js, PREVIEW_ITEM_DOCTYPE: PREVIEW_ITEM_DOCTYPE in doctype_list_js},
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_payment_entry_posting_config": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def can_import_service():
    try:
        from ndis_finance.services.governed_limited_operation_preview import quick_governed_limited_operation_preview_summary

        return callable(quick_governed_limited_operation_preview_summary)
    except Exception:
        return False


def check_workspace_shortcuts():
    ws_name = frappe.db.exists("Workspace", WORKSPACE_NAME) or frappe.db.exists("Workspace", {"label": WORKSPACE_NAME})
    result = {shortcut["label"]: False for shortcut in WORKSPACE_SHORTCUTS}
    if not ws_name:
        return result
    ws = frappe.get_doc("Workspace", ws_name)
    text_blob = getattr(ws, "content", "") or ""
    for shortcut in WORKSPACE_SHORTCUTS:
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            result[shortcut["label"]] = True
    return result
