import json

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE
from ndis_finance.services.permissions import permission_matrix


CANDIDATE_SELECTION_DOCTYPE = "NDIS Next Governed Limited Op Candidate Selection"
CANDIDATE_SELECTION_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Candidate Selection Item"
DESIGN_DOCTYPE = "NDIS Next Governed Limited Op Design"
DESIGN_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Design Item"

PHASE13B_DOCTYPES = [CANDIDATE_SELECTION_DOCTYPE, CANDIDATE_SELECTION_ITEM_DOCTYPE]

REPORTS = [
    {"report_name": "NDIS Next Governed Limited Op Candidate Selection Report", "ref_doctype": CANDIDATE_SELECTION_DOCTYPE},
    {"report_name": "NDIS Next Governed Limited Op Candidate Selection Item Report", "ref_doctype": CANDIDATE_SELECTION_ITEM_DOCTYPE},
    {"report_name": "NDIS Next Governed Limited Op Candidate Selection Guardrail Report", "ref_doctype": CANDIDATE_SELECTION_DOCTYPE},
]

REPORT_ROLES = ["System Manager", "NDIS CFO", "NDIS Finance Manager", "NDIS Finance Officer", "NDIS Finance Read Only"]

DOC_PERM_MATRIX = {
    CANDIDATE_SELECTION_DOCTYPE: {"System Manager": "full", "NDIS CFO": "read_report_export", "NDIS Finance Manager": "read_report_export", "NDIS Finance Officer": "read_report", "NDIS Finance Read Only": "read_report"},
    CANDIDATE_SELECTION_ITEM_DOCTYPE: {"System Manager": "full", "NDIS CFO": "read_report_export", "NDIS Finance Manager": "read_report_export", "NDIS Finance Officer": "read_report", "NDIS Finance Read Only": "read_report"},
}

WORKSPACE_NAME = "NDIS Finance"
WORKSPACE_SHORTCUTS = [
    {"label": "Next Governed Limited Op Candidate Selection", "type": "DocType", "link_to": CANDIDATE_SELECTION_DOCTYPE},
    {"label": "Next Governed Limited Op Candidate Selection Items", "type": "DocType", "link_to": CANDIDATE_SELECTION_ITEM_DOCTYPE},
    {"label": "Next Governed Limited Op Candidate Selection Report", "type": "Report", "link_to": "NDIS Next Governed Limited Op Candidate Selection Report"},
    {"label": "Next Governed Limited Op Candidate Selection Item Report", "type": "Report", "link_to": "NDIS Next Governed Limited Op Candidate Selection Item Report"},
    {"label": "Next Governed Limited Op Candidate Selection Guardrails", "type": "Report", "link_to": "NDIS Next Governed Limited Op Candidate Selection Guardrail Report"},
]

CANDIDATE_SELECTION_FIELDS = [
    {"fieldname": "candidate_selection_status", "label": "Candidate Selection Status", "fieldtype": "Data", "read_only": 1, "in_list_view": 1},
    {"fieldname": "phase13a_design_verified", "label": "Phase 13A Design Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "design_approved_verified", "label": "Design Approved Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "design_source_verified", "label": "Design Source Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "design_reference_verified", "label": "Design Reference Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "design_party_type_verified", "label": "Design Party Type Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "design_reference_set_locked_verified", "label": "Design Reference Set Locked Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "design_reference_set_verified", "label": "Design Reference Set Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "design_shape_verified", "label": "Design Shape Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "design_side_effects_blocked_verified", "label": "Design Side Effects Blocked Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "invoice_submission_verified", "label": "Invoice Submission Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "invoice_outstanding_verified", "label": "Invoice Outstanding Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "candidate_selection_source_locked", "label": "Candidate Selection Source Locked", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "candidate_selection_shape_locked", "label": "Candidate Selection Shape Locked", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "candidate_selection_reference_set_locked", "label": "Candidate Selection Reference Set Locked", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "candidate_selection_reference_set_verified", "label": "Candidate Selection Reference Set Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "policy_state_preserved_verified", "label": "Policy State Preserved Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "no_new_accounting_movement_verified", "label": "No New Accounting Movement Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "selected_source_doctype", "label": "Selected Source DocType", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "selected_reference_doctype", "label": "Selected Reference DocType", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "selected_party_type", "label": "Selected Party Type", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "selected_customer", "label": "Selected Customer", "fieldtype": "Link", "options": "Customer", "read_only": 1},
    {"fieldname": "selected_company", "label": "Selected Company", "fieldtype": "Link", "options": "Company", "read_only": 1},
    {"fieldname": "selected_currency", "label": "Selected Currency", "fieldtype": "Link", "options": "Currency", "read_only": 1},
    {"fieldname": "selected_invoice_names", "label": "Selected Invoice Names", "fieldtype": "Small Text", "read_only": 1},
    {"fieldname": "selected_invoice_count", "label": "Selected Invoice Count", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "selected_total_amount", "label": "Selected Total Amount", "fieldtype": "Currency", "read_only": 1},
    {"fieldname": "selected_payment_entry_count", "label": "Selected Payment Entry Count", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "selected_gl_entry_count", "label": "Selected GL Entry Count", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "selected_live_posting_allowed", "label": "Selected Live Posting Allowed", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "selected_journal_entry_side_effect_allowed", "label": "Selected JE Side Effect Allowed", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "selected_purchase_invoice_side_effect_allowed", "label": "Selected PI Side Effect Allowed", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "monitored_payment_entry_docstatus", "label": "Monitored PE Docstatus", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "monitored_payment_entry_status", "label": "Monitored PE Status", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "monitored_reversal_gl_rows", "label": "Monitored Reversal GL Rows", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "ready_for_next_governed_limited_op_candidate_validation_gate", "label": "Ready For Next Governed Limited Op Candidate Validation Gate", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
    {"fieldname": "candidate_selection_json", "label": "Candidate Selection JSON", "fieldtype": "Long Text", "read_only": 1},
]

CANDIDATE_SELECTION_ITEM_FIELDS = [
    {"fieldname": "customer", "label": "Customer", "fieldtype": "Link", "options": "Customer", "read_only": 1},
    {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company", "read_only": 1},
    {"fieldname": "currency", "label": "Currency", "fieldtype": "Link", "options": "Currency", "read_only": 1},
    {"fieldname": "selected_amount", "label": "Selected Amount", "fieldtype": "Currency", "read_only": 1},
    {"fieldname": "invoice_docstatus", "label": "Invoice Docstatus", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "outstanding_sufficient", "label": "Outstanding Sufficient", "fieldtype": "Check", "read_only": 1},
]

FIELD_UPDATES = {
    CANDIDATE_SELECTION_DOCTYPE: {
        "candidate_selection_status": {"label": "Candidate Selection Status"},
        "design": {"label": "Phase 13A Design", "options": DESIGN_DOCTYPE},
        "planning": {"label": "Phase 12Z Planning", "options": "NDIS Next Governed Limited Op Planning"},
        "monitor": {"label": "Phase 12Y Runtime Monitor", "options": "NDIS Next Governed Limited Op Runtime Monitor"},
        "baseline": {"label": "Phase 12X Baseline", "options": "NDIS Next Governed Limited Op Steady Baseline"},
        "closeout": {"label": "Phase 12W Closeout", "options": "NDIS Next Governed Limited Op Closeout"},
        "freeze": {"label": "Phase 12V Freeze", "options": "NDIS Next Governed Limited Op Rollback Freeze"},
        "rollback": {"label": "Phase 12U Rollback", "options": "NDIS Next Governed Limited Op Rollback"},
        "smoke": {"label": "Phase 12T Smoke", "options": "NDIS Next Governed Limited Op Smoke"},
        "execution_gate": {"label": "Phase 12S Execution Gate", "options": "NDIS Next Governed Limited Op Execution Gate"},
        "preview": {"label": "Phase 12R Preview", "options": "NDIS Next Governed Limited Op Preview"},
        "candidate_validation": {"label": "Phase 12Q Candidate Validation", "options": "NDIS Next Governed Limited Op Candidate Validation"},
        "previous_candidate_selection": {"label": "Previous Candidate Selection", "options": CANDIDATE_SELECTION_DOCTYPE},
    }
}


@frappe.whitelist()
def install():
    validate_previous_phases()
    ensure_phase13b_fields()
    update_field_properties()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        DESIGN_DOCTYPE,
        DESIGN_ITEM_DOCTYPE,
        CANDIDATE_SELECTION_DOCTYPE,
        CANDIDATE_SELECTION_ITEM_DOCTYPE,
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
        frappe.throw(_("Phase 13B requires completed Phase 13A design. Missing: {0}").format(", ".join(missing)))


def ensure_phase13b_fields():
    ensure_fields(CANDIDATE_SELECTION_DOCTYPE, CANDIDATE_SELECTION_FIELDS)
    ensure_fields(CANDIDATE_SELECTION_ITEM_DOCTYPE, CANDIDATE_SELECTION_ITEM_FIELDS)


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
    if "Next Governed Limited Operation Candidate Selection" not in text_blob:
        content.append({"id": "next_governed_limited_op_candidate_selection_heading", "type": "header", "data": {"text": "Next Governed Limited Operation Candidate Selection", "col": 12}})
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
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE13B_DOCTYPES},
        "phase13b_fields": {
            CANDIDATE_SELECTION_DOCTYPE: {field["fieldname"]: frappe.get_meta(CANDIDATE_SELECTION_DOCTYPE).has_field(field["fieldname"]) for field in CANDIDATE_SELECTION_FIELDS},
            CANDIDATE_SELECTION_ITEM_DOCTYPE: {field["fieldname"]: frappe.get_meta(CANDIDATE_SELECTION_ITEM_DOCTYPE).has_field(field["fieldname"]) for field in CANDIDATE_SELECTION_ITEM_FIELDS},
        },
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_next_governed_limited_operation_candidate_selection_gate": permission_matrix().get("run_next_governed_limited_operation_candidate_selection_gate"),
            "cancel_next_governed_limited_operation_candidate_selection_gate_audit": permission_matrix().get("cancel_next_governed_limited_operation_candidate_selection_gate_audit"),
        },
        "js_hooks": {CANDIDATE_SELECTION_DOCTYPE: CANDIDATE_SELECTION_DOCTYPE in doctype_js, CANDIDATE_SELECTION_ITEM_DOCTYPE: CANDIDATE_SELECTION_ITEM_DOCTYPE in doctype_js},
        "list_js_hooks": {CANDIDATE_SELECTION_DOCTYPE: CANDIDATE_SELECTION_DOCTYPE in doctype_list_js, CANDIDATE_SELECTION_ITEM_DOCTYPE: CANDIDATE_SELECTION_ITEM_DOCTYPE in doctype_list_js},
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_payment_entry_posting_config": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def can_import_service():
    try:
        from ndis_finance.services.next_governed_limited_operation_candidate_selection import quick_next_governed_limited_operation_candidate_selection_summary

        return callable(quick_next_governed_limited_operation_candidate_selection_summary)
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
