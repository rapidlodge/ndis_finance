import json

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


PREVIEW_DOCTYPE = "NDIS Next Governed Limited Op Preview"
PREVIEW_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Preview Item"
PHASE12R_DOCTYPES = [PREVIEW_DOCTYPE, PREVIEW_ITEM_DOCTYPE]
PREVIEW_READY_FIELD = "ready_for_next_governed_limited_op_execution_gate"

REPORTS = [
    {"report_name": "NDIS Next Governed Limited Op Preview Report", "ref_doctype": PREVIEW_DOCTYPE},
    {"report_name": "NDIS Next Governed Limited Op Preview Item Report", "ref_doctype": PREVIEW_ITEM_DOCTYPE},
    {"report_name": "NDIS Next Governed Limited Op Preview Guardrail Report", "ref_doctype": PREVIEW_DOCTYPE},
]

REPORT_ROLES = ["System Manager", "NDIS CFO", "NDIS Finance Manager", "NDIS Finance Officer", "NDIS Finance Read Only"]
DOC_PERM_MATRIX = {
    PREVIEW_DOCTYPE: {"System Manager": "full", "NDIS CFO": "read_report_export", "NDIS Finance Manager": "read_report_export", "NDIS Finance Officer": "read_report", "NDIS Finance Read Only": "read_report"},
    PREVIEW_ITEM_DOCTYPE: {"System Manager": "full", "NDIS CFO": "read_report_export", "NDIS Finance Manager": "read_report_export", "NDIS Finance Officer": "read_report", "NDIS Finance Read Only": "read_report"},
}
WORKSPACE_NAME = "NDIS Finance"
WORKSPACE_SHORTCUTS = [
    {"label": "Next Governed Limited Op Preview", "type": "DocType", "link_to": PREVIEW_DOCTYPE},
    {"label": "Next Governed Limited Op Preview Items", "type": "DocType", "link_to": PREVIEW_ITEM_DOCTYPE},
    {"label": "Next Governed Limited Op Preview Report", "type": "Report", "link_to": "NDIS Next Governed Limited Op Preview Report"},
    {"label": "Next Governed Limited Op Preview Item Report", "type": "Report", "link_to": "NDIS Next Governed Limited Op Preview Item Report"},
    {"label": "Next Governed Limited Op Preview Guardrails", "type": "Report", "link_to": "NDIS Next Governed Limited Op Preview Guardrail Report"},
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_preview_doctype()
    create_preview_item_doctype()
    ensure_existing_schema()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Next Governed Limited Op Candidate Validation",
        "NDIS Next Governed Limited Op Candidate Validation Item",
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
        frappe.throw(_("Phase 12R requires completed Phase 12Q candidate validation. Missing: {0}").format(", ".join(missing)))


def create_preview_doctype():
    _create_doctype(
        name=PREVIEW_DOCTYPE,
        autoname="field:preview_id",
        title_field="preview_id",
        fields=[
            {"fieldname": "preview_id", "label": "Preview ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nNeeds Review\nPreview Approved\nBlocked\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "preview_status", "label": "Preview Status", "fieldtype": "Select", "options": "\nNext Governed Limited Operation Preview Approved\nNeeds Review\nBlocked\nCancelled", "read_only": 1, "in_list_view": 1},
            {"fieldname": "result_section", "label": "Preview Result", "fieldtype": "Section Break"},
            {"fieldname": "preview_approved", "label": "Preview Approved", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "phase12q_candidate_validation_verified", "label": "Phase 12Q Candidate Validation Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "candidate_validation_approved_verified", "label": "Candidate Validation Approved Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "validated_source_verified", "label": "Validated Source Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "validated_reference_verified", "label": "Validated Reference Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "validated_party_type_verified", "label": "Validated Party Type Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "validated_reference_set_locked_verified", "label": "Validated Reference Set Locked Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "validated_reference_set_verified", "label": "Validated Reference Set Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "validated_shape_verified", "label": "Validated Shape Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "validated_side_effects_blocked_verified", "label": "Validated Side Effects Blocked Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "invoice_submission_verified", "label": "Invoice Submission Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "invoice_outstanding_verified", "label": "Invoice Outstanding Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "preview_source_locked", "label": "Preview Source Locked", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "preview_shape_locked", "label": "Preview Shape Locked", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "preview_reference_set_locked", "label": "Preview Reference Set Locked", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "preview_reference_set_verified", "label": "Preview Reference Set Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "policy_state_preserved_verified", "label": "Policy State Preserved Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "no_new_accounting_movement_verified", "label": "No New Accounting Movement Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "preview_section", "label": "Preview Shape", "fieldtype": "Section Break"},
            {"fieldname": "preview_source_doctype", "label": "Preview Source DocType", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "preview_reference_doctype", "label": "Preview Reference DocType", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "preview_party_type", "label": "Preview Party Type", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "preview_customer", "label": "Preview Customer", "fieldtype": "Link", "options": "Customer", "read_only": 1},
            {"fieldname": "preview_company", "label": "Preview Company", "fieldtype": "Link", "options": "Company", "read_only": 1},
            {"fieldname": "preview_currency", "label": "Preview Currency", "fieldtype": "Link", "options": "Currency", "read_only": 1},
            {"fieldname": "preview_invoice_names", "label": "Preview Invoice Names", "fieldtype": "Small Text", "read_only": 1},
            {"fieldname": "preview_invoice_count", "label": "Preview Invoice Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "preview_total_amount", "label": "Preview Total Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "preview_payment_entry_count", "label": "Preview Payment Entry Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "preview_gl_entry_count", "label": "Preview GL Entry Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "preview_live_posting_allowed", "label": "Preview Live Posting Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "preview_journal_entry_side_effect_allowed", "label": "Preview JE Side Effect Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "preview_purchase_invoice_side_effect_allowed", "label": "Preview PI Side Effect Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": PREVIEW_READY_FIELD, "label": "Ready For Execution Gate", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "monitor_section", "label": "Monitor Evidence", "fieldtype": "Section Break"},
            {"fieldname": "monitored_payment_entry", "label": "Monitored Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "read_only": 1, "in_list_view": 1},
            {"fieldname": "monitored_payment_entry_docstatus", "label": "Monitored PE Docstatus", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "monitored_payment_entry_status", "label": "Monitored PE Status", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "monitored_voucher_gl_rows", "label": "Monitored Voucher GL Rows", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "monitored_voucher_gl_net", "label": "Monitored Voucher GL Net", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "monitored_reversal_gl_rows", "label": "Monitored Reversal GL Rows", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "monitored_restored_invoice_amount", "label": "Monitored Restored Invoice Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "chain_section", "label": "Evidence Chain", "fieldtype": "Section Break"},
            {"fieldname": "candidate_validation", "label": "Phase 12Q Candidate Validation", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Candidate Validation", "in_list_view": 1},
            {"fieldname": "candidate_selection", "label": "Phase 12P Candidate Selection", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Candidate Selection"},
            {"fieldname": "design", "label": "Phase 12O Design", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Design"},
            {"fieldname": "planning", "label": "Phase 12N Planning", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Planning"},
            {"fieldname": "monitor", "label": "Phase 12M Runtime Monitor", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Runtime Monitor"},
            {"fieldname": "baseline", "label": "Phase 12L Baseline", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Steady Baseline"},
            {"fieldname": "closeout", "label": "Phase 12K Closeout", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Closeout"},
            {"fieldname": "freeze", "label": "Phase 12J Freeze", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Rollback Freeze"},
            {"fieldname": "rollback", "label": "Phase 12I Rollback", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Rollback"},
            {"fieldname": "smoke", "label": "Phase 12H Smoke", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Smoke"},
            {"fieldname": "execution_gate", "label": "Phase 12G Execution Gate", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Exec Gate"},
            {"fieldname": "previous_preview", "label": "Previous Preview", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Preview"},
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
            {"fieldname": "score_section", "label": "Preview Score", "fieldtype": "Section Break"},
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
            {"fieldname": "preview_json", "label": "Preview JSON", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
        ],
    )


def create_preview_item_doctype():
    _create_doctype(
        name=PREVIEW_ITEM_DOCTYPE,
        autoname="hash",
        title_field="check_label",
        fields=[
            {"fieldname": "preview", "label": "Preview", "fieldtype": "Link", "options": PREVIEW_DOCTYPE, "reqd": 1, "in_list_view": 1},
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
            {"fieldname": "preview_amount", "label": "Preview Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "current_outstanding_amount", "label": "Current Outstanding Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "invoice_docstatus", "label": "Invoice Docstatus", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "outstanding_sufficient", "label": "Outstanding Sufficient", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "monitored_payment_entry", "label": "Monitored Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "read_only": 1},
            {"fieldname": "checked_on", "label": "Checked On", "fieldtype": "Datetime", "read_only": 1},
        ],
    )


def ensure_existing_schema():
    ensure_fields(
        PREVIEW_DOCTYPE,
        [
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nNeeds Review\nPreview Approved\nBlocked\nCancelled"},
            {"fieldname": "preview_status", "label": "Preview Status", "fieldtype": "Select", "options": "\nNext Governed Limited Operation Preview Approved\nNeeds Review\nBlocked\nCancelled", "read_only": 1},
            {"fieldname": "phase12q_candidate_validation_verified", "label": "Phase 12Q Candidate Validation Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "validated_source_verified", "label": "Validated Source Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "validated_reference_verified", "label": "Validated Reference Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "validated_party_type_verified", "label": "Validated Party Type Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "validated_reference_set_locked_verified", "label": "Validated Reference Set Locked Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "validated_reference_set_verified", "label": "Validated Reference Set Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "validated_shape_verified", "label": "Validated Shape Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "validated_side_effects_blocked_verified", "label": "Validated Side Effects Blocked Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "invoice_submission_verified", "label": "Invoice Submission Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "invoice_outstanding_verified", "label": "Invoice Outstanding Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": PREVIEW_READY_FIELD, "label": "Ready For Next Governed Limited Op Execution Gate", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "monitored_payment_entry_docstatus", "label": "Monitored PE Docstatus", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "monitored_payment_entry_status", "label": "Monitored PE Status", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "monitored_reversal_gl_rows", "label": "Monitored Reversal GL Rows", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "candidate_validation", "label": "Phase 12Q Candidate Validation", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Candidate Validation"},
            {"fieldname": "candidate_selection", "label": "Phase 12P Candidate Selection", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Candidate Selection"},
            {"fieldname": "design", "label": "Phase 12O Design", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Design"},
            {"fieldname": "planning", "label": "Phase 12N Planning", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Planning"},
            {"fieldname": "monitor", "label": "Phase 12M Runtime Monitor", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Runtime Monitor"},
            {"fieldname": "baseline", "label": "Phase 12L Baseline", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Steady Baseline"},
            {"fieldname": "closeout", "label": "Phase 12K Closeout", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Closeout"},
            {"fieldname": "freeze", "label": "Phase 12J Freeze", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Rollback Freeze"},
            {"fieldname": "rollback", "label": "Phase 12I Rollback", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Rollback"},
            {"fieldname": "smoke", "label": "Phase 12H Smoke", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Smoke"},
            {"fieldname": "execution_gate", "label": "Phase 12G Execution Gate", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Exec Gate"},
            {"fieldname": "previous_preview", "label": "Previous Preview", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Preview"},
        ],
    )
    ensure_fields(
        PREVIEW_ITEM_DOCTYPE,
        [
            {"fieldname": "invoice_docstatus", "label": "Invoice Docstatus", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "outstanding_sufficient", "label": "Outstanding Sufficient", "fieldtype": "Check", "read_only": 1},
        ],
    )


def ensure_fields(doctype, fields):
    if not frappe.db.exists("DocType", doctype):
        return

    doc = frappe.get_doc("DocType", doctype)
    existing = {row.fieldname: row for row in doc.fields}
    changed = False
    for field in fields:
        current = existing.get(field["fieldname"])
        if current:
            for key, value in field.items():
                if key == "fieldname" or not current.meta.has_field(key):
                    continue
                if getattr(current, key, None) != value:
                    setattr(current, key, value)
                    changed = True
            continue
        doc.append("fields", field)
        existing[field["fieldname"]] = doc.fields[-1]
        changed = True

    if changed:
        doc.save(ignore_permissions=True)
        frappe.clear_cache(doctype=doctype)


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
    base = {"role": role, "permlevel": 0, "read": 0, "write": 0, "create": 0, "delete": 0, "submit": 0, "cancel": 0, "amend": 0, "report": 0, "export": 0, "import": 0, "share": 0, "print": 0, "email": 0}
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
    if "Next Governed Limited Operation Preview" not in text_blob:
        content.append({"id": "next_governed_limited_op_preview_heading", "type": "header", "data": {"text": "Next Governed Limited Operation Preview", "col": 12}})
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
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE12R_DOCTYPES},
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "execution_ready_field": has_column(PREVIEW_DOCTYPE, PREVIEW_READY_FIELD),
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_next_governed_limited_operation_preview": permission_matrix().get("run_next_governed_limited_operation_preview"),
            "cancel_next_governed_limited_operation_preview_audit": permission_matrix().get("cancel_next_governed_limited_operation_preview_audit"),
        },
        "js_hooks": {PREVIEW_DOCTYPE: PREVIEW_DOCTYPE in doctype_js, PREVIEW_ITEM_DOCTYPE: PREVIEW_ITEM_DOCTYPE in doctype_js},
        "list_js_hooks": {PREVIEW_DOCTYPE: PREVIEW_DOCTYPE in doctype_list_js, PREVIEW_ITEM_DOCTYPE: PREVIEW_ITEM_DOCTYPE in doctype_list_js},
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
        from ndis_finance.services.next_governed_limited_operation_preview import quick_next_governed_limited_operation_preview_summary
        return callable(quick_next_governed_limited_operation_preview_summary)
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
