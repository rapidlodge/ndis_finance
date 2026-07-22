import json

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE
from ndis_finance.services.permissions import permission_matrix


CANDIDATE_SELECTION_DOCTYPE = "NDIS Next Governed Limited Op Candidate Selection"
CANDIDATE_SELECTION_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Candidate Selection Item"
CANDIDATE_VALIDATION_DOCTYPE = "NDIS Next Governed Limited Op Candidate Validation"
CANDIDATE_VALIDATION_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Candidate Validation Item"
CANDIDATE_VALIDATION_READY_FIELD = "ready_for_next_governed_limited_op_preview"

PHASE14M_DOCTYPES = [CANDIDATE_VALIDATION_DOCTYPE, CANDIDATE_VALIDATION_ITEM_DOCTYPE]

REPORTS = [
    {"report_name": "NDIS Next Governed Limited Op Candidate Validation Phase14M Report", "ref_doctype": CANDIDATE_VALIDATION_DOCTYPE},
    {"report_name": "NDIS Next Governed Limited Op Candidate Validation Phase14M Item Report", "ref_doctype": CANDIDATE_VALIDATION_ITEM_DOCTYPE},
    {"report_name": "NDIS Next Governed Limited Op Candidate Validation Phase14M Guardrail Report", "ref_doctype": CANDIDATE_VALIDATION_DOCTYPE},
]

REPORT_ROLES = ["System Manager", "NDIS CFO", "NDIS Finance Manager", "NDIS Finance Officer", "NDIS Finance Read Only"]

DOC_PERM_MATRIX = {
    CANDIDATE_VALIDATION_DOCTYPE: {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
    CANDIDATE_VALIDATION_ITEM_DOCTYPE: {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
}

WORKSPACE_NAME = "NDIS Finance"
WORKSPACE_SHORTCUTS = [
    {"label": "Next Governed Limited Op Candidate Validation Phase14M Report", "type": "Report", "link_to": "NDIS Next Governed Limited Op Candidate Validation Phase14M Report"},
    {"label": "Next Governed Limited Op Candidate Validation Phase14M Item Report", "type": "Report", "link_to": "NDIS Next Governed Limited Op Candidate Validation Phase14M Item Report"},
    {"label": "Next Governed Limited Op Candidate Validation Phase14M Guardrails", "type": "Report", "link_to": "NDIS Next Governed Limited Op Candidate Validation Phase14M Guardrail Report"},
]

CANDIDATE_VALIDATION_FIELDS = [
    {"fieldname": "candidate_validation_id", "label": "Candidate Validation ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
    {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nNeeds Review\nCandidate Validation Approved\nBlocked\nCancelled", "default": "Draft", "in_list_view": 1},
    {"fieldname": "candidate_validation_status", "label": "Candidate Validation Status", "fieldtype": "Data", "read_only": 1, "in_list_view": 1},
    {"fieldname": "candidate_validation_approved", "label": "Candidate Validation Approved", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
    {"fieldname": "phase14m_result_section", "label": "Phase 14M Candidate Validation Result", "fieldtype": "Section Break"},
    {"fieldname": "phase14l_candidate_selection_verified", "label": "Phase 14L Candidate Selection Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "candidate_selection_approved_verified", "label": "Candidate Selection Approved Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "candidate_selection_payment_entry_verified", "label": "Candidate Selection Payment Entry Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "candidate_selection_payment_entry_cancelled_verified", "label": "Candidate Selection Payment Entry Cancelled Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "candidate_selection_gl_rows_verified", "label": "Candidate Selection GL Rows Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "candidate_selection_reversal_gl_rows_verified", "label": "Candidate Selection Reversal GL Rows Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "candidate_selection_gl_net_zero_verified", "label": "Candidate Selection GL Net Zero Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "candidate_selection_restored_invoice_amount_verified", "label": "Candidate Selection Restored Invoice Amount Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "policy_state_preserved_verified", "label": "Policy State Preserved Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "no_new_accounting_movement_verified", "label": "No New Accounting Movement Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": CANDIDATE_VALIDATION_READY_FIELD, "label": "Ready For Next Governed Limited Op Preview", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
    {"fieldname": "phase14m_evidence_section", "label": "Candidate Validation Evidence", "fieldtype": "Section Break"},
    {"fieldname": "gated_payment_entry", "label": "Gated Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "read_only": 1},
    {"fieldname": "gated_payment_entry_docstatus", "label": "Gated PE Docstatus", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "gated_payment_entry_status", "label": "Gated PE Status", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "previous_gated_payment_entry", "label": "Previous Gated Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "read_only": 1},
    {"fieldname": "previous_gated_payment_entry_docstatus", "label": "Previous Gated PE Docstatus", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "previous_gated_payment_entry_status", "label": "Previous Gated PE Status", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "candidate_validation_payment_entry", "label": "Candidate Validation Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "read_only": 1, "in_list_view": 1},
    {"fieldname": "candidate_validation_payment_entry_docstatus", "label": "Candidate Validation PE Docstatus", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "candidate_validation_payment_entry_status", "label": "Candidate Validation PE Status", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "candidate_validation_source_doctype", "label": "Candidate Validation Source DocType", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "candidate_validation_reference_doctype", "label": "Candidate Validation Reference DocType", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "candidate_validation_party_type", "label": "Candidate Validation Party Type", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "candidate_validation_customer", "label": "Candidate Validation Customer", "fieldtype": "Link", "options": "Customer", "read_only": 1},
    {"fieldname": "candidate_validation_company", "label": "Candidate Validation Company", "fieldtype": "Link", "options": "Company", "read_only": 1},
    {"fieldname": "candidate_validation_currency", "label": "Candidate Validation Currency", "fieldtype": "Link", "options": "Currency", "read_only": 1},
    {"fieldname": "candidate_validation_invoice_names", "label": "Candidate Validation Invoice Names", "fieldtype": "Small Text", "read_only": 1},
    {"fieldname": "candidate_validation_invoice_count", "label": "Candidate Validation Invoice Count", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "candidate_validation_total_amount", "label": "Candidate Validation Total Amount", "fieldtype": "Currency", "read_only": 1},
    {"fieldname": "candidate_validation_restored_invoice_amount", "label": "Candidate Validation Restored Invoice Amount", "fieldtype": "Currency", "read_only": 1},
    {"fieldname": "candidate_validation_gl_rows", "label": "Candidate Validation GL Rows", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "candidate_validation_reversal_gl_rows", "label": "Candidate Validation Reversal GL Rows", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "candidate_validation_gl_net", "label": "Candidate Validation GL Net", "fieldtype": "Currency", "read_only": 1},
    {"fieldname": "candidate_validation_direct_cancelled_gl_rows", "label": "Candidate Validation Direct Cancelled GL Rows", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "direct_erpnext_cancelled_gl_rows", "label": "Direct ERPNext Cancelled GL Rows", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "phase14m_movement_section", "label": "Movement Guardrails", "fieldtype": "Section Break"},
    {"fieldname": "payment_entry_count_before", "label": "Payment Entry Count Before", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "payment_entry_count_after", "label": "Payment Entry Count After", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "payment_entry_gl_count_before", "label": "Payment Entry GL Count Before", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "payment_entry_gl_count_after", "label": "Payment Entry GL Count After", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "actual_payment_entry_created_count", "label": "Actual PE Created Count", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "actual_payment_entry_cancelled_count", "label": "Actual PE Cancelled Count", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "actual_gl_created_count", "label": "Actual GL Created Count", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "submitted_journal_entry_count_today", "label": "Submitted JE Count Today", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "purchase_invoice_count_today", "label": "Purchase Invoice Count Today", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "phase14m_policy_section", "label": "Policy Evidence", "fieldtype": "Section Break"},
    {"fieldname": "target_policy_doctype", "label": "Target Policy DocType", "fieldtype": "Link", "options": "DocType", "read_only": 1},
    {"fieldname": "target_policy", "label": "Target Policy", "fieldtype": "Dynamic Link", "options": "target_policy_doctype"},
    {"fieldname": "target_policy_name", "label": "Target Policy Name", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "target_policy_enabled_before", "label": "Target Policy Enabled Before", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "target_policy_enabled_after", "label": "Target Policy Enabled After", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "target_policy_live_before", "label": "Target Policy Live Before", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "target_policy_live_after", "label": "Target Policy Live After", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "actual_policy_mutation_count", "label": "Actual Policy Mutation Count", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "phase14m_chain_section", "label": "Evidence Chain", "fieldtype": "Section Break"},
    {"fieldname": "candidate_selection", "label": "Phase 14L Candidate Selection", "fieldtype": "Link", "options": CANDIDATE_SELECTION_DOCTYPE},
    {"fieldname": "design", "label": "Phase 14K Design", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Design"},
    {"fieldname": "planning", "label": "Phase 14J Planning", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Planning"},
    {"fieldname": "monitor", "label": "Phase 14I Runtime Monitor", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Runtime Monitor"},
    {"fieldname": "baseline", "label": "Phase 14H Baseline", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Steady Baseline"},
    {"fieldname": "closeout", "label": "Phase 14G Closeout", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Closeout"},
    {"fieldname": "freeze", "label": "Phase 14F Freeze", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Rollback Freeze"},
    {"fieldname": "rollback", "label": "Phase 14E Rollback", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Smoke Rollback"},
    {"fieldname": "smoke", "label": "Phase 14D Smoke", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Smoke"},
    {"fieldname": "execution_gate", "label": "Phase 14C Execution Gate", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Execution Gate"},
    {"fieldname": "preview", "label": "Phase 14B Preview", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Preview"},
    {"fieldname": "previous_candidate_validation", "label": "Previous Candidate Validation", "fieldtype": "Link", "options": CANDIDATE_VALIDATION_DOCTYPE},
    {"fieldname": "phase14m_site_section", "label": "Site / Config", "fieldtype": "Section Break"},
    {"fieldname": "site_name", "label": "Site Name", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "sandbox_config_enabled", "label": "Sandbox Config Enabled", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "production_mode_detected", "label": "Production Mode Detected", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "live_payment_entry_posting_config", "label": "Live PE Posting Config", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "checked_on", "label": "Checked On", "fieldtype": "Datetime", "read_only": 1, "in_list_view": 1},
    {"fieldname": "checked_by", "label": "Checked By", "fieldtype": "Link", "options": "User", "read_only": 1},
    {"fieldname": "phase14m_score_section", "label": "Audit Counts", "fieldtype": "Section Break"},
    {"fieldname": "blocker_count", "label": "Blocker Count", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "warning_count", "label": "Warning Count", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "pass_count", "label": "Pass Count", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "info_count", "label": "Info Count", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "item_count", "label": "Item Count", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "phase14m_ack_section", "label": "Acknowledgement", "fieldtype": "Section Break"},
    {"fieldname": "required_acknowledgement", "label": "Required Acknowledgement", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "acknowledgement", "label": "Acknowledgement", "fieldtype": "Data"},
    {"fieldname": "acknowledgement_ok", "label": "Acknowledgement OK", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "phase14m_audit_section", "label": "Audit", "fieldtype": "Section Break"},
    {"fieldname": "cancelled_on", "label": "Cancelled On", "fieldtype": "Datetime", "read_only": 1},
    {"fieldname": "cancelled_by", "label": "Cancelled By", "fieldtype": "Link", "options": "User", "read_only": 1},
    {"fieldname": "summary_json", "label": "Summary JSON", "fieldtype": "Long Text", "read_only": 1},
    {"fieldname": "candidate_validation_json", "label": "Candidate Validation JSON", "fieldtype": "Long Text", "read_only": 1},
    {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
]

CANDIDATE_VALIDATION_ITEM_FIELDS = [
    {"fieldname": "candidate_validation", "label": "Candidate Validation", "fieldtype": "Link", "options": CANDIDATE_VALIDATION_DOCTYPE, "reqd": 1, "in_list_view": 1},
    {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nPass\nWarning\nBlocker\nInfo\nCancelled", "default": "Info", "in_list_view": 1},
    {"fieldname": "severity", "label": "Severity", "fieldtype": "Select", "options": "\nLow\nMedium\nHigh\nCritical", "default": "Low"},
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
    {"fieldname": "candidate_validation_amount", "label": "Candidate Validation Amount", "fieldtype": "Currency", "read_only": 1},
    {"fieldname": "outstanding_amount", "label": "Outstanding Amount", "fieldtype": "Currency", "read_only": 1},
    {"fieldname": "gated_payment_entry", "label": "Gated Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "read_only": 1},
    {"fieldname": "candidate_validation_payment_entry", "label": "Candidate Validation Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "read_only": 1},
    {"fieldname": "checked_on", "label": "Checked On", "fieldtype": "Datetime", "read_only": 1},
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    ensure_missing_fields(CANDIDATE_VALIDATION_DOCTYPE, CANDIDATE_VALIDATION_FIELDS)
    ensure_missing_fields(CANDIDATE_VALIDATION_ITEM_DOCTYPE, CANDIDATE_VALIDATION_ITEM_FIELDS)
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        CANDIDATE_SELECTION_DOCTYPE,
        CANDIDATE_SELECTION_ITEM_DOCTYPE,
        CANDIDATE_VALIDATION_DOCTYPE,
        CANDIDATE_VALIDATION_ITEM_DOCTYPE,
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
        frappe.throw(_("Phase 14M requires completed Phase 14L candidate selection. Missing: {0}").format(", ".join(missing)))


def ensure_missing_fields(doctype, fields):
    doc = frappe.get_doc("DocType", doctype)
    existing = {field.fieldname for field in doc.fields}
    changed = False
    for field in fields:
        if field["fieldname"] not in existing:
            doc.append("fields", field)
            existing.add(field["fieldname"])
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
    if "Next Governed Limited Operation Candidate Validation Phase14M" not in text_blob:
        content.append({"id": "next_governed_limited_op_candidate_validation_phase14m_heading", "type": "header", "data": {"text": "Next Governed Limited Operation Candidate Validation Phase14M", "col": 12}})
    for shortcut in WORKSPACE_SHORTCUTS:
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            continue
        content.append({"id": frappe.scrub(shortcut["label"]), "type": "shortcut", "data": {"label": shortcut["label"], "link_to": shortcut["link_to"], "type": shortcut["type"], "col": 3}})
    ws.content = json.dumps(content)


def add_shortcuts_to_child_table(ws):
    for fieldname in ["shortcuts", "links"]:
        if not ws.meta.has_field(fieldname):
            continue
        existing_blob = " ".join(f"{getattr(row, 'label', '')} {getattr(row, 'link_to', '')}" for row in (getattr(ws, fieldname, []) or []))
        for shortcut in WORKSPACE_SHORTCUTS:
            if shortcut["label"] in existing_blob or shortcut["link_to"] in existing_blob:
                continue
            row = ws.append(fieldname, {})
            set_child_value(row, "label", shortcut["label"])
            set_child_value(row, "link_to", shortcut["link_to"])
            if fieldname == "links":
                set_child_value(row, "type", "Link")
                set_child_value(row, "link_type", shortcut["type"])
            else:
                set_child_value(row, "type", shortcut["type"])
            set_child_value(row, "open_in_new_tab", 0)


def set_child_value(row, fieldname, value):
    if row.meta.has_field(fieldname):
        setattr(row, fieldname, value)


@frappe.whitelist()
def health_check():
    hooks = frappe.get_hooks()
    doctype_js = hooks.get("doctype_js", {})
    doctype_list_js = hooks.get("doctype_list_js", {})
    return {
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE14M_DOCTYPES},
        "phase14m_fields": {
            CANDIDATE_VALIDATION_DOCTYPE: {field["fieldname"]: frappe.get_meta(CANDIDATE_VALIDATION_DOCTYPE).has_field(field["fieldname"]) for field in CANDIDATE_VALIDATION_FIELDS},
            CANDIDATE_VALIDATION_ITEM_DOCTYPE: {field["fieldname"]: frappe.get_meta(CANDIDATE_VALIDATION_ITEM_DOCTYPE).has_field(field["fieldname"]) for field in CANDIDATE_VALIDATION_ITEM_FIELDS},
        },
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_next_governed_limited_operation_candidate_validation_phase14m": permission_matrix().get("run_next_governed_limited_operation_candidate_validation_phase14m"),
            "cancel_next_governed_limited_operation_candidate_validation_phase14m_audit": permission_matrix().get("cancel_next_governed_limited_operation_candidate_validation_phase14m_audit"),
        },
        "js_hooks": {CANDIDATE_VALIDATION_DOCTYPE: CANDIDATE_VALIDATION_DOCTYPE in doctype_js, CANDIDATE_VALIDATION_ITEM_DOCTYPE: CANDIDATE_VALIDATION_ITEM_DOCTYPE in doctype_js},
        "list_js_hooks": {CANDIDATE_VALIDATION_DOCTYPE: CANDIDATE_VALIDATION_DOCTYPE in doctype_list_js, CANDIDATE_VALIDATION_ITEM_DOCTYPE: CANDIDATE_VALIDATION_ITEM_DOCTYPE in doctype_list_js},
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_payment_entry_posting_config": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def can_import_service():
    try:
        from ndis_finance.services.next_governed_limited_operation_candidate_validation_phase14m import quick_next_governed_limited_operation_candidate_validation_phase14m_summary

        return callable(quick_next_governed_limited_operation_candidate_validation_phase14m_summary)
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
                text_blob += f" {getattr(row, 'label', '')} {getattr(row, 'link_to', '')}"
    for shortcut in WORKSPACE_SHORTCUTS:
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            result[shortcut["label"]] = True
    return result
