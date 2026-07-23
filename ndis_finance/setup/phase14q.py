import json

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE
from ndis_finance.setup.phase13g import (
    DOC_PERM_MATRIX,
    REPORT_ROLES,
    ROLLBACK_DOCTYPE,
    ROLLBACK_ITEM_DOCTYPE,
    SMOKE_DOCTYPE,
    SMOKE_ITEM_DOCTYPE,
    WORKSPACE_NAME,
    add_shortcuts_to_child_table,
    add_shortcuts_to_content_json,
    build_perm_row,
    has_meta_field,
)
from ndis_finance.services.permissions import permission_matrix


ROLLBACK_READY_FIELD = "ready_for_next_governed_limited_op_rollback_freeze"

PHASE14Q_DOCTYPES = [ROLLBACK_DOCTYPE, ROLLBACK_ITEM_DOCTYPE]

REPORTS = [
    {"report_name": "NDIS Next Governed Limited Op Smoke Rollback Phase14Q Report", "ref_doctype": ROLLBACK_DOCTYPE},
    {"report_name": "NDIS Next Governed Limited Op Smoke Rollback Phase14Q Item Report", "ref_doctype": ROLLBACK_ITEM_DOCTYPE},
    {"report_name": "NDIS Next Governed Limited Op Smoke Rollback Phase14Q Guardrail Report", "ref_doctype": ROLLBACK_DOCTYPE},
]

WORKSPACE_SHORTCUTS = [
    {"label": "Phase14Q Smoke Rollback Report", "type": "Report", "link_to": "NDIS Next Governed Limited Op Smoke Rollback Phase14Q Report"},
    {"label": "Phase14Q Smoke Rollback Item Report", "type": "Report", "link_to": "NDIS Next Governed Limited Op Smoke Rollback Phase14Q Item Report"},
    {"label": "Phase14Q Smoke Rollback Guardrails", "type": "Report", "link_to": "NDIS Next Governed Limited Op Smoke Rollback Phase14Q Guardrail Report"},
]

PHASE14Q_FIELDS = [
    {"fieldname": "rollback_id", "label": "Rollback ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
    {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nNeeds Review\nRolled Back\nSmoke Rollback Completed\nBlocked\nCancelled", "default": "Draft", "in_list_view": 1},
    {"fieldname": "rollback_status", "label": "Rollback Status", "fieldtype": "Select", "options": "\nNext Governed Limited Operation Smoke Rolled Back\nNext Governed Limited Operation Smoke Rollback Completed\nNeeds Review\nBlocked\nCancelled", "read_only": 1, "in_list_view": 1},
    {"fieldname": "rollback_completed", "label": "Rollback Completed", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
    {"fieldname": "phase14p_smoke_verified", "label": "Phase 14P Smoke Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "smoke_completed_verified", "label": "Smoke Completed Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "smoke_payment_entry_verified", "label": "Smoke Payment Entry Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "smoke_payment_entry_submitted_verified", "label": "Smoke PE Submitted Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "smoke_gl_rows_verified", "label": "Smoke GL Rows Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "smoke_gl_net_zero_verified", "label": "Smoke GL Net Zero Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "smoke_invoice_outstanding_zero_verified", "label": "Smoke Invoice Outstanding Zero Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "gated_payment_entry", "label": "Gated Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "read_only": 1, "in_list_view": 1},
    {"fieldname": "gated_payment_entry_docstatus", "label": "Gated PE Docstatus", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "gated_payment_entry_status", "label": "Gated PE Status", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "previous_gated_payment_entry", "label": "Previous Gated Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "read_only": 1},
    {"fieldname": "previous_gated_payment_entry_docstatus", "label": "Previous Gated PE Docstatus", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "previous_gated_payment_entry_status", "label": "Previous Gated PE Status", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "historical_gated_payment_entry", "label": "Historical Gated Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "read_only": 1},
    {"fieldname": "historical_gated_payment_entry_docstatus", "label": "Historical Gated PE Docstatus", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "historical_gated_payment_entry_status", "label": "Historical Gated PE Status", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "rollback_payment_entry", "label": "Rollback Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "read_only": 1, "in_list_view": 1},
    {"fieldname": "rollback_payment_entry_docstatus_before", "label": "Rollback PE Docstatus Before", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "rollback_payment_entry_status_before", "label": "Rollback PE Status Before", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "rollback_payment_entry_docstatus_after", "label": "Rollback PE Docstatus After", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "rollback_payment_entry_status_after", "label": "Rollback PE Status After", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "rollback_source_doctype", "label": "Rollback Source DocType", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "rollback_reference_doctype", "label": "Rollback Reference DocType", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "rollback_party_type", "label": "Rollback Party Type", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "rollback_customer", "label": "Rollback Customer", "fieldtype": "Link", "options": "Customer", "read_only": 1},
    {"fieldname": "rollback_company", "label": "Rollback Company", "fieldtype": "Link", "options": "Company", "read_only": 1},
    {"fieldname": "rollback_currency", "label": "Rollback Currency", "fieldtype": "Link", "options": "Currency", "read_only": 1},
    {"fieldname": "rollback_invoice_names", "label": "Rollback Invoice Names", "fieldtype": "Small Text", "read_only": 1},
    {"fieldname": "rollback_invoice_count", "label": "Rollback Invoice Count", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "rollback_total_amount", "label": "Rollback Total Amount", "fieldtype": "Currency", "read_only": 1},
    {"fieldname": "invoice_outstanding_before_rollback", "label": "Invoice Outstanding Before Rollback", "fieldtype": "Currency", "read_only": 1},
    {"fieldname": "invoice_outstanding_after_rollback", "label": "Invoice Outstanding After Rollback", "fieldtype": "Currency", "read_only": 1},
    {"fieldname": "rollback_gl_rows", "label": "Rollback GL Rows", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "rollback_reversal_gl_rows", "label": "Rollback Reversal GL Rows", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "rollback_gl_net", "label": "Rollback GL Net", "fieldtype": "Currency", "read_only": 1},
    {"fieldname": "rollback_direct_cancelled_gl_rows", "label": "Rollback Direct Cancelled GL Rows", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "payment_entry_count_before", "label": "Payment Entry Count Before", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "payment_entry_count_after", "label": "Payment Entry Count After", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "payment_entry_gl_count_before", "label": "Payment Entry GL Count Before", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "payment_entry_gl_count_after", "label": "Payment Entry GL Count After", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "actual_payment_entry_created_count", "label": "Actual PE Created Count", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "actual_payment_entry_cancelled_count", "label": "Actual PE Cancelled Count", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "actual_gl_created_count", "label": "Actual GL Created Count", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "submitted_journal_entry_count_today", "label": "Submitted JE Count Today", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "purchase_invoice_count_today", "label": "Purchase Invoice Count Today", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "target_policy_enabled_before", "label": "Target Policy Enabled Before", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "target_policy_enabled_after", "label": "Target Policy Enabled After", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "target_policy_live_before", "label": "Target Policy Live Before", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "target_policy_live_after", "label": "Target Policy Live After", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "actual_policy_mutation_count", "label": "Actual Policy Mutation Count", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "smoke", "label": "Phase 14P Smoke", "fieldtype": "Link", "options": SMOKE_DOCTYPE, "in_list_view": 1},
    {"fieldname": "execution_gate", "label": "Phase 14O Execution Gate", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Execution Gate"},
    {"fieldname": "preview", "label": "Phase 14N Preview", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Preview"},
    {"fieldname": "candidate_validation", "label": "Phase 14M Candidate Validation", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Candidate Validation"},
    {"fieldname": "candidate_selection", "label": "Phase 14L Candidate Selection", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Candidate Selection"},
    {"fieldname": "design", "label": "Phase 14K Design", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Design"},
    {"fieldname": "planning", "label": "Phase 14J Planning", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Planning"},
    {"fieldname": "monitor", "label": "Phase 14I Runtime Monitor", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Runtime Monitor"},
    {"fieldname": "baseline", "label": "Phase 14H Baseline", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Steady Baseline"},
    {"fieldname": "closeout", "label": "Phase 14G Closeout", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Closeout"},
    {"fieldname": "freeze", "label": "Phase 14F Freeze", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Rollback Freeze"},
    {"fieldname": "previous_rollback", "label": "Previous Rollback", "fieldtype": "Link", "options": ROLLBACK_DOCTYPE},
    {"fieldname": "blocker_count", "label": "Blocker Count", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "warning_count", "label": "Warning Count", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "required_acknowledgement", "label": "Required Acknowledgement", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "acknowledgement", "label": "Acknowledgement", "fieldtype": "Data"},
    {"fieldname": "acknowledgement_ok", "label": "Acknowledgement OK", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "summary_json", "label": "Summary JSON", "fieldtype": "Long Text", "read_only": 1},
    {"fieldname": "rollback_json", "label": "Rollback JSON", "fieldtype": "Long Text", "read_only": 1},
    {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
    {"fieldname": ROLLBACK_READY_FIELD, "label": "Ready For Next Governed Limited Op Rollback Freeze", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
]

PHASE14Q_ITEM_FIELDS = [
    {"fieldname": "rollback", "label": "Rollback", "fieldtype": "Link", "options": ROLLBACK_DOCTYPE, "reqd": 1, "in_list_view": 1},
    {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nPass\nWarning\nBlocker\nInfo\nCancelled", "default": "Info", "in_list_view": 1},
    {"fieldname": "severity", "label": "Severity", "fieldtype": "Select", "options": "\nLow\nMedium\nHigh\nCritical", "default": "Low"},
    {"fieldname": "category", "label": "Category", "fieldtype": "Data", "in_list_view": 1},
    {"fieldname": "check_key", "label": "Check Key", "fieldtype": "Data"},
    {"fieldname": "check_label", "label": "Check Label", "fieldtype": "Data", "in_list_view": 1},
    {"fieldname": "detail", "label": "Detail", "fieldtype": "Small Text"},
    {"fieldname": "line_no", "label": "Line No", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "reference_doctype", "label": "Reference DocType", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "reference_name", "label": "Reference Name", "fieldtype": "Dynamic Link", "options": "reference_doctype", "read_only": 1},
    {"fieldname": "customer", "label": "Customer", "fieldtype": "Link", "options": "Customer", "read_only": 1},
    {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company", "read_only": 1},
    {"fieldname": "currency", "label": "Currency", "fieldtype": "Link", "options": "Currency", "read_only": 1},
    {"fieldname": "rollback_amount", "label": "Rollback Amount", "fieldtype": "Currency", "read_only": 1},
    {"fieldname": "outstanding_before", "label": "Outstanding Before", "fieldtype": "Currency", "read_only": 1},
    {"fieldname": "outstanding_after", "label": "Outstanding After", "fieldtype": "Currency", "read_only": 1},
    {"fieldname": "gated_payment_entry", "label": "Gated Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "read_only": 1},
    {"fieldname": "rollback_payment_entry", "label": "Rollback Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "read_only": 1},
    {"fieldname": "checked_on", "label": "Checked On", "fieldtype": "Datetime", "read_only": 1},
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    ensure_missing_fields(ROLLBACK_DOCTYPE, PHASE14Q_FIELDS)
    ensure_missing_fields(ROLLBACK_ITEM_DOCTYPE, PHASE14Q_ITEM_FIELDS)
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        SMOKE_DOCTYPE,
        SMOKE_ITEM_DOCTYPE,
        ROLLBACK_DOCTYPE,
        ROLLBACK_ITEM_DOCTYPE,
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
        frappe.throw(_("Phase 14Q requires completed Phase 14P smoke and rollback schema. Missing: {0}").format(", ".join(missing)))


def ensure_missing_fields(doctype, fields):
    doc = frappe.get_doc("DocType", doctype)
    existing = {field.fieldname for field in doc.fields}
    changed = False
    for field in fields:
        if field["fieldname"] in existing:
            continue
        doc.append("fields", field)
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


def add_workspace_shortcuts():
    ws_name = frappe.db.exists("Workspace", WORKSPACE_NAME) or frappe.db.exists("Workspace", {"label": WORKSPACE_NAME})
    if not ws_name:
        return
    ws = frappe.get_doc("Workspace", ws_name)
    add_shortcuts_to_content_json(ws)
    add_shortcuts_to_child_table(ws)
    add_phase14q_shortcuts(ws)
    ws.save(ignore_permissions=True)


def add_phase14q_shortcuts(ws):
    existing_blob = ws.content or ""
    for fieldname in ["shortcuts", "links"]:
        if ws.meta.has_field(fieldname):
            for row in getattr(ws, fieldname, []) or []:
                existing_blob += " " + str(getattr(row, "label", "")) + " " + str(getattr(row, "link_to", ""))

    for shortcut in WORKSPACE_SHORTCUTS:
        if shortcut["label"] in existing_blob or shortcut["link_to"] in existing_blob:
            continue
        if ws.meta.has_field("shortcuts"):
            row = ws.append("shortcuts", {})
            set_child_value(row, "label", shortcut["label"])
            set_child_value(row, "link_to", shortcut["link_to"])
            set_child_value(row, "type", shortcut["type"])
            set_child_value(row, "open_in_new_tab", 0)

    if ws.meta.has_field("content"):
        try:
            content = json.loads(ws.content or "[]")
        except Exception:
            content = []
        content_blob = json.dumps(content)
        for shortcut in WORKSPACE_SHORTCUTS:
            if shortcut["label"] in content_blob or shortcut["link_to"] in content_blob:
                continue
            content.append({"id": frappe.scrub(shortcut["label"]), "type": "shortcut", "data": {"label": shortcut["label"], "link_to": shortcut["link_to"], "type": shortcut["type"], "col": 3}})
        ws.content = json.dumps(content)


def set_child_value(row, fieldname, value):
    if row.meta.has_field(fieldname):
        setattr(row, fieldname, value)


@frappe.whitelist()
def health_check():
    hooks = frappe.get_hooks()
    doctype_js = hooks.get("doctype_js", {})
    doctype_list_js = hooks.get("doctype_list_js", {})
    return {
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE14Q_DOCTYPES},
        "phase14q_fields": {
            ROLLBACK_DOCTYPE: {field["fieldname"]: has_meta_field(ROLLBACK_DOCTYPE, field["fieldname"]) for field in PHASE14Q_FIELDS},
            ROLLBACK_ITEM_DOCTYPE: {field["fieldname"]: has_meta_field(ROLLBACK_ITEM_DOCTYPE, field["fieldname"]) for field in PHASE14Q_ITEM_FIELDS},
        },
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_next_governed_limited_operation_smoke_rollback_phase14q": permission_matrix().get("run_next_governed_limited_operation_smoke_rollback_phase14q"),
            "cancel_next_governed_limited_operation_smoke_rollback_phase14q_audit": permission_matrix().get("cancel_next_governed_limited_operation_smoke_rollback_phase14q_audit"),
        },
        "js_hooks": {
            ROLLBACK_DOCTYPE: ROLLBACK_DOCTYPE in doctype_js,
            ROLLBACK_ITEM_DOCTYPE: ROLLBACK_ITEM_DOCTYPE in doctype_js,
        },
        "list_js_hooks": {
            ROLLBACK_DOCTYPE: ROLLBACK_DOCTYPE in doctype_list_js,
            ROLLBACK_ITEM_DOCTYPE: ROLLBACK_ITEM_DOCTYPE in doctype_list_js,
        },
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_payment_entry_posting_config": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def can_import_service():
    try:
        from ndis_finance.services.next_governed_limited_operation_smoke_rollback_phase14q import quick_next_governed_limited_operation_smoke_rollback_phase14q_summary
        return callable(quick_next_governed_limited_operation_smoke_rollback_phase14q_summary)
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
