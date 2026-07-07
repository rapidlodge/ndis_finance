import json

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


VALIDATION_DOCTYPE = "NDIS Next Governed Limited Op Candidate Validation"
VALIDATION_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Candidate Validation Item"
PHASE12Q_DOCTYPES = [VALIDATION_DOCTYPE, VALIDATION_ITEM_DOCTYPE]

VALIDATION_READY_FIELD = "ready_for_next_governed_limited_op_preview_gate"

REPORTS = [
    {"report_name": "NDIS Next Governed Limited Op Candidate Validation Report", "ref_doctype": VALIDATION_DOCTYPE},
    {"report_name": "NDIS Next Governed Limited Op Candidate Validation Item Report", "ref_doctype": VALIDATION_ITEM_DOCTYPE},
    {"report_name": "NDIS Next Governed Limited Op Candidate Validation Guardrail Report", "ref_doctype": VALIDATION_DOCTYPE},
]

REPORT_ROLES = ["System Manager", "NDIS CFO", "NDIS Finance Manager", "NDIS Finance Officer", "NDIS Finance Read Only"]

DOC_PERM_MATRIX = {
    VALIDATION_DOCTYPE: {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
    VALIDATION_ITEM_DOCTYPE: {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
}

WORKSPACE_NAME = "NDIS Finance"
WORKSPACE_SHORTCUTS = [
    {"label": "Next Governed Limited Op Candidate Validation", "type": "DocType", "link_to": VALIDATION_DOCTYPE},
    {"label": "Next Governed Limited Op Candidate Validation Items", "type": "DocType", "link_to": VALIDATION_ITEM_DOCTYPE},
    {"label": "Next Governed Limited Op Candidate Validation Report", "type": "Report", "link_to": "NDIS Next Governed Limited Op Candidate Validation Report"},
    {"label": "Next Governed Limited Op Candidate Validation Item Report", "type": "Report", "link_to": "NDIS Next Governed Limited Op Candidate Validation Item Report"},
    {"label": "Next Governed Limited Op Candidate Validation Guardrails", "type": "Report", "link_to": "NDIS Next Governed Limited Op Candidate Validation Guardrail Report"},
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_candidate_validation_doctype()
    create_candidate_validation_item_doctype()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Next Governed Limited Op Candidate Selection",
        "NDIS Next Governed Limited Op Candidate Selection Item",
        "NDIS Controlled Production Batch Posting Policy",
        "Payment Entry",
        "GL Entry",
        "Sales Invoice",
        "Customer",
        "Company",
        "Currency",
        "Report",
        "Workspace",
    ]
    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]
    if missing:
        frappe.throw(_("Phase 12Q requires completed Phase 12P candidate selection. Missing: {0}").format(", ".join(missing)))


def create_candidate_validation_doctype():
    _create_doctype(
        name=VALIDATION_DOCTYPE,
        autoname="field:candidate_validation_id",
        title_field="candidate_validation_id",
        fields=[
            {"fieldname": "candidate_validation_id", "label": "Candidate Validation ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nNeeds Review\nCandidate Validation Approved\nBlocked\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "candidate_validation_status", "label": "Candidate Validation Status", "fieldtype": "Select", "options": "\nNext Governed Limited Operation Candidate Validation Approved\nNeeds Review\nBlocked\nCancelled", "read_only": 1, "in_list_view": 1},
            {"fieldname": "result_section", "label": "Candidate Validation Result", "fieldtype": "Section Break"},
            {"fieldname": "candidate_validation_approved", "label": "Candidate Validation Approved", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "phase12p_candidate_selection_verified", "label": "Phase 12P Candidate Selection Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "candidate_selection_approved_verified", "label": "Candidate Selection Approved Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "selected_source_verified", "label": "Selected Source Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "selected_reference_verified", "label": "Selected Reference Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "selected_party_type_verified", "label": "Selected Party Type Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "selected_reference_set_locked_verified", "label": "Selected Reference Set Locked Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "selected_reference_set_verified", "label": "Selected Reference Set Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "selected_shape_verified", "label": "Selected Shape Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "selected_side_effects_blocked_verified", "label": "Selected Side Effects Blocked Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "invoice_submission_verified", "label": "Invoice Submission Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "invoice_outstanding_verified", "label": "Invoice Outstanding Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "candidate_validation_locked", "label": "Candidate Validation Locked", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "validated_reference_set_locked", "label": "Validated Reference Set Locked", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "validated_reference_set_verified", "label": "Validated Reference Set Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "policy_state_preserved_verified", "label": "Policy State Preserved Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "no_new_accounting_movement_verified", "label": "No New Accounting Movement Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "validation_section", "label": "Validated Candidate Shape", "fieldtype": "Section Break"},
            {"fieldname": "validated_source_doctype", "label": "Validated Source DocType", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "validated_reference_doctype", "label": "Validated Reference DocType", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "validated_party_type", "label": "Validated Party Type", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "validated_customer", "label": "Validated Customer", "fieldtype": "Link", "options": "Customer", "read_only": 1},
            {"fieldname": "validated_company", "label": "Validated Company", "fieldtype": "Link", "options": "Company", "read_only": 1},
            {"fieldname": "validated_currency", "label": "Validated Currency", "fieldtype": "Link", "options": "Currency", "read_only": 1},
            {"fieldname": "validated_invoice_names", "label": "Validated Invoice Names", "fieldtype": "Small Text", "read_only": 1},
            {"fieldname": "validated_invoice_count", "label": "Validated Invoice Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "validated_total_amount", "label": "Validated Total Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "validated_payment_entry_count", "label": "Validated Payment Entry Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "validated_gl_entry_count", "label": "Validated GL Entry Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "validated_live_posting_allowed", "label": "Validated Live Posting Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "validated_journal_entry_side_effect_allowed", "label": "Validated JE Side Effect Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "validated_purchase_invoice_side_effect_allowed", "label": "Validated PI Side Effect Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": VALIDATION_READY_FIELD, "label": "Ready For Preview Gate", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "monitor_section", "label": "Monitor Evidence", "fieldtype": "Section Break"},
            {"fieldname": "monitored_payment_entry", "label": "Monitored Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "read_only": 1, "in_list_view": 1},
            {"fieldname": "monitored_payment_entry_docstatus", "label": "Monitored PE Docstatus", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "monitored_payment_entry_status", "label": "Monitored PE Status", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "monitored_voucher_gl_rows", "label": "Monitored Voucher GL Rows", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "monitored_voucher_gl_net", "label": "Monitored Voucher GL Net", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "monitored_reversal_gl_rows", "label": "Monitored Reversal GL Rows", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "monitored_restored_invoice_amount", "label": "Monitored Restored Invoice Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "chain_section", "label": "Evidence Chain", "fieldtype": "Section Break"},
            {"fieldname": "candidate_selection", "label": "Phase 12P Candidate Selection", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Candidate Selection", "in_list_view": 1},
            {"fieldname": "design", "label": "Phase 12O Design", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Design"},
            {"fieldname": "planning", "label": "Phase 12N Planning", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Planning"},
            {"fieldname": "monitor", "label": "Phase 12M Runtime Monitor", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Runtime Monitor"},
            {"fieldname": "baseline", "label": "Phase 12L Baseline", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Steady Baseline"},
            {"fieldname": "closeout", "label": "Phase 12K Closeout", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Closeout"},
            {"fieldname": "freeze", "label": "Phase 12J Freeze", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Rollback Freeze"},
            {"fieldname": "rollback", "label": "Phase 12I Rollback", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Rollback"},
            {"fieldname": "smoke", "label": "Phase 12H Smoke", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Smoke"},
            {"fieldname": "execution_gate", "label": "Phase 12G Execution Gate", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Exec Gate"},
            {"fieldname": "preview", "label": "Phase 12F Preview", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Preview"},
            {"fieldname": "previous_candidate_validation", "label": "Previous Candidate Validation", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Cand Valid"},
            {"fieldname": "policy_section", "label": "Policy Evidence", "fieldtype": "Section Break"},
            {"fieldname": "target_policy_doctype", "label": "Target Policy DocType", "fieldtype": "Link", "options": "DocType", "read_only": 1},
            {"fieldname": "target_policy", "label": "Target Policy", "fieldtype": "Dynamic Link", "options": "target_policy_doctype"},
            {"fieldname": "target_policy_name", "label": "Target Policy Name", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "target_policy_enabled_before", "label": "Target Policy Enabled Before", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "target_policy_enabled_after", "label": "Target Policy Enabled After", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "target_policy_live_before", "label": "Target Policy Live Before", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "target_policy_live_after", "label": "Target Policy Live After", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "actual_policy_mutation_count", "label": "Actual Policy Mutation Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "movement_section", "label": "Movement Guardrails", "fieldtype": "Section Break"},
            {"fieldname": "payment_entry_count_before", "label": "Payment Entry Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_count_after", "label": "Payment Entry Count After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_count_before", "label": "Payment Entry GL Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_count_after", "label": "Payment Entry GL Count After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "actual_payment_entry_created_count", "label": "Actual PE Created Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "actual_payment_entry_cancelled_count", "label": "Actual PE Cancelled Count", "fieldtype": "Int", "read_only": 1},
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
            {"fieldname": "score_section", "label": "Candidate Validation Score", "fieldtype": "Section Break"},
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
            {"fieldname": "validation_json", "label": "Validation JSON", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
        ],
    )


def create_candidate_validation_item_doctype():
    _create_doctype(
        name=VALIDATION_ITEM_DOCTYPE,
        autoname="hash",
        title_field="check_label",
        fields=[
            {"fieldname": "candidate_validation", "label": "Candidate Validation", "fieldtype": "Link", "options": VALIDATION_DOCTYPE, "reqd": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nPass\nWarning\nBlocker\nInfo\nCancelled", "default": "Info", "in_list_view": 1},
            {"fieldname": "severity", "label": "Severity", "fieldtype": "Select", "options": "\nLow\nMedium\nHigh\nCritical", "default": "Low", "in_list_view": 1},
            {"fieldname": "category", "label": "Category", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "check_key", "label": "Check Key", "fieldtype": "Data"},
            {"fieldname": "check_label", "label": "Check Label", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "detail", "label": "Detail", "fieldtype": "Small Text"},
            {"fieldname": "line_no", "label": "Line No", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "reference_doctype", "label": "Reference DocType", "fieldtype": "Link", "options": "DocType", "read_only": 1},
            {"fieldname": "reference_name", "label": "Reference Name", "fieldtype": "Dynamic Link", "options": "reference_doctype", "read_only": 1},
            {"fieldname": "customer", "label": "Customer", "fieldtype": "Link", "options": "Customer", "read_only": 1},
            {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company", "read_only": 1},
            {"fieldname": "currency", "label": "Currency", "fieldtype": "Link", "options": "Currency", "read_only": 1},
            {"fieldname": "validated_amount", "label": "Validated Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "current_outstanding_amount", "label": "Current Outstanding Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "invoice_docstatus", "label": "Invoice Docstatus", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "outstanding_sufficient", "label": "Outstanding Sufficient", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "monitored_payment_entry", "label": "Monitored Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "read_only": 1},
            {"fieldname": "checked_on", "label": "Checked On", "fieldtype": "Datetime", "read_only": 1},
        ],
    )


def create_reports():
    for report in REPORTS:
        ensure_script_report(report["report_name"], report["ref_doctype"])


def ensure_script_report(report_name, ref_doctype):
    existing = frappe.db.exists("Report", report_name)
    doc = frappe.get_doc("Report", existing) if existing else frappe.new_doc("Report")
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
    if "Next Governed Limited Operation Candidate Validation" not in text_blob:
        content.append({"id": "next_governed_limited_op_candidate_validation_heading", "type": "header", "data": {"text": "Next Governed Limited Operation Candidate Validation", "col": 12}})
    for shortcut in WORKSPACE_SHORTCUTS:
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            continue
        content.append({"id": frappe.scrub(shortcut["label"]), "type": "shortcut", "data": {"label": shortcut["label"], "link_to": shortcut["link_to"], "type": shortcut["type"], "col": 3}})
    ws.content = json.dumps(content)


def add_shortcuts_to_child_table(ws):
    # Workspace child-table schemas vary across Frappe versions; content JSON is
    # the stable shortcut surface for this workspace.
    return


@frappe.whitelist()
def health_check():
    hooks = frappe.get_hooks()
    doctype_js = hooks.get("doctype_js", {})
    doctype_list_js = hooks.get("doctype_list_js", {})
    return {
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE12Q_DOCTYPES},
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "preview_ready_field": has_column(VALIDATION_DOCTYPE, VALIDATION_READY_FIELD),
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_next_governed_limited_operation_candidate_validation": permission_matrix().get("run_next_governed_limited_operation_candidate_validation"),
            "cancel_next_governed_limited_operation_candidate_validation_audit": permission_matrix().get(
                "cancel_next_governed_limited_operation_candidate_validation_audit"
            ),
        },
        "js_hooks": {VALIDATION_DOCTYPE: VALIDATION_DOCTYPE in doctype_js, VALIDATION_ITEM_DOCTYPE: VALIDATION_ITEM_DOCTYPE in doctype_js},
        "list_js_hooks": {VALIDATION_DOCTYPE: VALIDATION_DOCTYPE in doctype_list_js, VALIDATION_ITEM_DOCTYPE: VALIDATION_ITEM_DOCTYPE in doctype_list_js},
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_payment_entry_posting_config": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def has_column(doctype, fieldname):
    try:
        return bool(frappe.db.has_column(doctype, fieldname))
    except Exception:
        return False


def can_import_service():
    try:
        from ndis_finance.services.next_governed_limited_operation_candidate_validation import (
            quick_next_governed_limited_operation_candidate_validation_summary,
        )

        return callable(quick_next_governed_limited_operation_candidate_validation_summary)
    except Exception:
        return False


def check_workspace_shortcuts():
    ws_name = frappe.db.exists("Workspace", WORKSPACE_NAME) or frappe.db.exists("Workspace", {"label": WORKSPACE_NAME})
    result = {shortcut["label"]: False for shortcut in WORKSPACE_SHORTCUTS}
    if not ws_name:
        return result
    ws = frappe.get_doc("Workspace", ws_name)
    text_blob = ws.content or ""
    for fieldname in ["shortcuts", "links"]:
        if ws.meta.has_field(fieldname):
            for row in getattr(ws, fieldname, []) or []:
                text_blob += " " + str(getattr(row, "label", "")) + " " + str(getattr(row, "link_to", ""))
    for shortcut in WORKSPACE_SHORTCUTS:
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            result[shortcut["label"]] = True
    return result
