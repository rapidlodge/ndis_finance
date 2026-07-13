import json

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE
from ndis_finance.services.permissions import permission_matrix


CANDIDATE_VALIDATION_DOCTYPE = "NDIS Next Governed Limited Op Candidate Validation"
CANDIDATE_VALIDATION_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Candidate Validation Item"
CANDIDATE_SELECTION_DOCTYPE = "NDIS Next Governed Limited Op Candidate Selection"
CANDIDATE_SELECTION_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Candidate Selection Item"

PHASE13C_DOCTYPES = [CANDIDATE_VALIDATION_DOCTYPE, CANDIDATE_VALIDATION_ITEM_DOCTYPE]

REPORTS = [
    {"report_name": "NDIS Next Governed Limited Op Candidate Validation Report", "ref_doctype": CANDIDATE_VALIDATION_DOCTYPE},
    {"report_name": "NDIS Next Governed Limited Op Candidate Validation Item Report", "ref_doctype": CANDIDATE_VALIDATION_ITEM_DOCTYPE},
    {"report_name": "NDIS Next Governed Limited Op Candidate Validation Guardrail Report", "ref_doctype": CANDIDATE_VALIDATION_DOCTYPE},
]

REPORT_ROLES = ["System Manager", "NDIS CFO", "NDIS Finance Manager", "NDIS Finance Officer", "NDIS Finance Read Only"]

DOC_PERM_MATRIX = {
    CANDIDATE_VALIDATION_DOCTYPE: {"System Manager": "full", "NDIS CFO": "read_report_export", "NDIS Finance Manager": "read_report_export", "NDIS Finance Officer": "read_report", "NDIS Finance Read Only": "read_report"},
    CANDIDATE_VALIDATION_ITEM_DOCTYPE: {"System Manager": "full", "NDIS CFO": "read_report_export", "NDIS Finance Manager": "read_report_export", "NDIS Finance Officer": "read_report", "NDIS Finance Read Only": "read_report"},
}

WORKSPACE_NAME = "NDIS Finance"
WORKSPACE_SHORTCUTS = [
    {"label": "Next Governed Limited Op Candidate Validation", "type": "DocType", "link_to": CANDIDATE_VALIDATION_DOCTYPE},
    {"label": "Next Governed Limited Op Candidate Validation Items", "type": "DocType", "link_to": CANDIDATE_VALIDATION_ITEM_DOCTYPE},
    {"label": "Next Governed Limited Op Candidate Validation Report", "type": "Report", "link_to": "NDIS Next Governed Limited Op Candidate Validation Report"},
    {"label": "Next Governed Limited Op Candidate Validation Item Report", "type": "Report", "link_to": "NDIS Next Governed Limited Op Candidate Validation Item Report"},
    {"label": "Next Governed Limited Op Candidate Validation Guardrails", "type": "Report", "link_to": "NDIS Next Governed Limited Op Candidate Validation Guardrail Report"},
]

CANDIDATE_VALIDATION_FIELDS = [
    {"fieldname": "candidate_validation_status", "label": "Candidate Validation Status", "fieldtype": "Data", "read_only": 1, "in_list_view": 1},
    {"fieldname": "phase13b_candidate_selection_verified", "label": "Phase 13B Candidate Selection Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "candidate_selection_approved_verified", "label": "Candidate Selection Approved Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "candidate_selection_source_verified", "label": "Candidate Selection Source Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "candidate_selection_reference_verified", "label": "Candidate Selection Reference Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "candidate_selection_party_type_verified", "label": "Candidate Selection Party Type Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "candidate_selection_reference_set_locked_verified", "label": "Candidate Selection Reference Set Locked Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "candidate_selection_reference_set_verified", "label": "Candidate Selection Reference Set Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "candidate_selection_shape_verified", "label": "Candidate Selection Shape Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "candidate_selection_side_effects_blocked_verified", "label": "Candidate Selection Side Effects Blocked Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "invoice_submission_verified", "label": "Invoice Submission Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "invoice_outstanding_verified", "label": "Invoice Outstanding Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "candidate_validation_source_locked", "label": "Candidate Validation Source Locked", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "candidate_validation_shape_locked", "label": "Candidate Validation Shape Locked", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "candidate_validation_reference_set_locked", "label": "Candidate Validation Reference Set Locked", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "candidate_validation_reference_set_verified", "label": "Candidate Validation Reference Set Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "policy_state_preserved_verified", "label": "Policy State Preserved Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "no_new_accounting_movement_verified", "label": "No New Accounting Movement Verified", "fieldtype": "Check", "read_only": 1},
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
    {"fieldname": "monitored_payment_entry_docstatus", "label": "Monitored PE Docstatus", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "monitored_payment_entry_status", "label": "Monitored PE Status", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "monitored_reversal_gl_rows", "label": "Monitored Reversal GL Rows", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "ready_for_next_governed_limited_op_preview_gate", "label": "Ready For Next Governed Limited Op Preview Gate", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
    {"fieldname": "candidate_validation_json", "label": "Candidate Validation JSON", "fieldtype": "Long Text", "read_only": 1},
]

CANDIDATE_VALIDATION_ITEM_FIELDS = [
    {"fieldname": "customer", "label": "Customer", "fieldtype": "Link", "options": "Customer", "read_only": 1},
    {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company", "read_only": 1},
    {"fieldname": "currency", "label": "Currency", "fieldtype": "Link", "options": "Currency", "read_only": 1},
    {"fieldname": "validated_amount", "label": "Validated Amount", "fieldtype": "Currency", "read_only": 1},
    {"fieldname": "invoice_docstatus", "label": "Invoice Docstatus", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "outstanding_sufficient", "label": "Outstanding Sufficient", "fieldtype": "Check", "read_only": 1},
]

FIELD_UPDATES = {
    CANDIDATE_VALIDATION_DOCTYPE: {
        "candidate_validation_status": {"label": "Candidate Validation Status"},
        "candidate_selection": {"label": "Phase 13B Candidate Selection", "options": CANDIDATE_SELECTION_DOCTYPE},
        "design": {"label": "Phase 13A Design", "options": "NDIS Next Governed Limited Op Design"},
        "planning": {"label": "Phase 12Z Planning", "options": "NDIS Next Governed Limited Op Planning"},
        "monitor": {"label": "Phase 12Y Runtime Monitor", "options": "NDIS Next Governed Limited Op Runtime Monitor"},
        "baseline": {"label": "Phase 12X Baseline", "options": "NDIS Next Governed Limited Op Steady Baseline"},
        "closeout": {"label": "Phase 12W Closeout", "options": "NDIS Next Governed Limited Op Closeout"},
        "freeze": {"label": "Phase 12V Freeze", "options": "NDIS Next Governed Limited Op Rollback Freeze"},
        "rollback": {"label": "Phase 12U Rollback", "options": "NDIS Next Governed Limited Op Rollback"},
        "smoke": {"label": "Phase 12T Smoke", "options": "NDIS Next Governed Limited Op Smoke"},
        "execution_gate": {"label": "Phase 12S Execution Gate", "options": "NDIS Next Governed Limited Op Execution Gate"},
        "preview": {"label": "Phase 12R Preview", "options": "NDIS Next Governed Limited Op Preview"},
        "previous_candidate_validation": {"label": "Previous Candidate Validation", "options": CANDIDATE_VALIDATION_DOCTYPE},
    }
}


@frappe.whitelist()
def install():
    validate_previous_phases()
    ensure_phase13c_fields()
    update_field_properties()
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
        frappe.throw(_("Phase 13C requires completed Phase 13B candidate selection. Missing: {0}").format(", ".join(missing)))


def ensure_phase13c_fields():
    ensure_fields(CANDIDATE_VALIDATION_DOCTYPE, CANDIDATE_VALIDATION_FIELDS)
    ensure_fields(CANDIDATE_VALIDATION_ITEM_DOCTYPE, CANDIDATE_VALIDATION_ITEM_FIELDS)


def ensure_fields(doctype, fields):
    doc = frappe.get_doc("DocType", doctype)
    existing = {field.fieldname: field for field in doc.fields}
    changed = False
    for field in fields:
        current = existing.get(field["fieldname"])
        if not current:
            doc.append("fields", field)
            changed = True
            continue
        for key in ("label", "fieldtype", "options", "read_only", "in_list_view", "reqd", "unique", "default"):
            if key in field and getattr(current, key, None) != field[key]:
                setattr(current, key, field[key])
                changed = True
    if changed:
        doc.save(ignore_permissions=True)
        frappe.clear_cache(doctype=doctype)


def update_field_properties():
    for doctype, field_map in FIELD_UPDATES.items():
        doc = frappe.get_doc("DocType", doctype)
        changed = False
        for row in doc.fields:
            updates = field_map.get(row.fieldname)
            if not updates:
                continue
            for fieldname, value in updates.items():
                if getattr(row, fieldname) == value:
                    continue
                setattr(row, fieldname, value)
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
    if "Next Governed Limited Operation Candidate Validation" not in text_blob:
        content.append({"id": "next_governed_limited_op_candidate_validation_heading", "type": "header", "data": {"text": "Next Governed Limited Operation Candidate Validation", "col": 12}})
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
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE13C_DOCTYPES},
        "phase13c_fields": {
            CANDIDATE_VALIDATION_DOCTYPE: {field["fieldname"]: frappe.get_meta(CANDIDATE_VALIDATION_DOCTYPE).has_field(field["fieldname"]) for field in CANDIDATE_VALIDATION_FIELDS},
            CANDIDATE_VALIDATION_ITEM_DOCTYPE: {field["fieldname"]: frappe.get_meta(CANDIDATE_VALIDATION_ITEM_DOCTYPE).has_field(field["fieldname"]) for field in CANDIDATE_VALIDATION_ITEM_FIELDS},
        },
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_next_governed_limited_operation_candidate_validation_gate": permission_matrix().get("run_next_governed_limited_operation_candidate_validation_gate"),
            "cancel_next_governed_limited_operation_candidate_validation_gate_audit": permission_matrix().get("cancel_next_governed_limited_operation_candidate_validation_gate_audit"),
        },
        "js_hooks": {CANDIDATE_VALIDATION_DOCTYPE: CANDIDATE_VALIDATION_DOCTYPE in doctype_js, CANDIDATE_VALIDATION_ITEM_DOCTYPE: CANDIDATE_VALIDATION_ITEM_DOCTYPE in doctype_js},
        "list_js_hooks": {CANDIDATE_VALIDATION_DOCTYPE: CANDIDATE_VALIDATION_DOCTYPE in doctype_list_js, CANDIDATE_VALIDATION_ITEM_DOCTYPE: CANDIDATE_VALIDATION_ITEM_DOCTYPE in doctype_list_js},
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_payment_entry_posting_config": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def can_import_service():
    try:
        from ndis_finance.services.next_governed_limited_operation_candidate_validation import quick_next_governed_limited_operation_candidate_validation_summary

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
                text_blob += f" {getattr(row, 'label', '')} {getattr(row, 'link_to', '')}"
    for shortcut in WORKSPACE_SHORTCUTS:
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            result[shortcut["label"]] = True
    return result
