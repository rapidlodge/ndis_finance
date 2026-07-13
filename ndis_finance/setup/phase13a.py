import json

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE
from ndis_finance.services.permissions import permission_matrix


DESIGN_DOCTYPE = "NDIS Next Governed Limited Op Design"
DESIGN_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Design Item"
PLANNING_DOCTYPE = "NDIS Next Governed Limited Op Planning"
PLANNING_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Planning Item"

PHASE13A_DOCTYPES = [DESIGN_DOCTYPE, DESIGN_ITEM_DOCTYPE]

REPORTS = [
    {"report_name": "NDIS Next Governed Limited Op Design Report", "ref_doctype": DESIGN_DOCTYPE},
    {"report_name": "NDIS Next Governed Limited Op Design Item Report", "ref_doctype": DESIGN_ITEM_DOCTYPE},
    {"report_name": "NDIS Next Governed Limited Op Design Guardrail Report", "ref_doctype": DESIGN_DOCTYPE},
]

REPORT_ROLES = ["System Manager", "NDIS CFO", "NDIS Finance Manager", "NDIS Finance Officer", "NDIS Finance Read Only"]

DOC_PERM_MATRIX = {
    DESIGN_DOCTYPE: {"System Manager": "full", "NDIS CFO": "read_report_export", "NDIS Finance Manager": "read_report_export", "NDIS Finance Officer": "read_report", "NDIS Finance Read Only": "read_report"},
    DESIGN_ITEM_DOCTYPE: {"System Manager": "full", "NDIS CFO": "read_report_export", "NDIS Finance Manager": "read_report_export", "NDIS Finance Officer": "read_report", "NDIS Finance Read Only": "read_report"},
}

WORKSPACE_NAME = "NDIS Finance"
WORKSPACE_SHORTCUTS = [
    {"label": "Next Governed Limited Op Design", "type": "DocType", "link_to": DESIGN_DOCTYPE},
    {"label": "Next Governed Limited Op Design Items", "type": "DocType", "link_to": DESIGN_ITEM_DOCTYPE},
    {"label": "Next Governed Limited Op Design Report", "type": "Report", "link_to": "NDIS Next Governed Limited Op Design Report"},
    {"label": "Next Governed Limited Op Design Item Report", "type": "Report", "link_to": "NDIS Next Governed Limited Op Design Item Report"},
    {"label": "Next Governed Limited Op Design Guardrails", "type": "Report", "link_to": "NDIS Next Governed Limited Op Design Guardrail Report"},
]

DESIGN_FIELDS = [
    {"fieldname": "phase12z_planning_verified", "label": "Phase 12Z Planning Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "planning_approved_verified", "label": "Planning Approved Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "planning_source_verified", "label": "Planning Source Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "planning_reference_verified", "label": "Planning Reference Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "planning_party_type_verified", "label": "Planning Party Type Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "planning_reference_set_locked_verified", "label": "Planning Reference Set Locked Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "planning_reference_set_verified", "label": "Planning Reference Set Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "planning_shape_verified", "label": "Planning Shape Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "planning_side_effects_blocked_verified", "label": "Planning Side Effects Blocked Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "invoice_submission_verified", "label": "Invoice Submission Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "invoice_outstanding_verified", "label": "Invoice Outstanding Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "design_source_locked", "label": "Design Source Locked", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "design_shape_locked", "label": "Design Shape Locked", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "design_reference_set_locked", "label": "Design Reference Set Locked", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "design_reference_set_verified", "label": "Design Reference Set Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "designed_source_doctype", "label": "Designed Source DocType", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "designed_reference_doctype", "label": "Designed Reference DocType", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "designed_party_type", "label": "Designed Party Type", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "designed_customer", "label": "Designed Customer", "fieldtype": "Link", "options": "Customer", "read_only": 1},
    {"fieldname": "designed_company", "label": "Designed Company", "fieldtype": "Link", "options": "Company", "read_only": 1},
    {"fieldname": "designed_currency", "label": "Designed Currency", "fieldtype": "Link", "options": "Currency", "read_only": 1},
    {"fieldname": "designed_invoice_names", "label": "Designed Invoice Names", "fieldtype": "Small Text", "read_only": 1},
    {"fieldname": "designed_invoice_count", "label": "Designed Invoice Count", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "designed_total_amount", "label": "Designed Total Amount", "fieldtype": "Currency", "read_only": 1},
    {"fieldname": "designed_payment_entry_count", "label": "Designed Payment Entry Count", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "designed_gl_entry_count", "label": "Designed GL Entry Count", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "designed_live_posting_allowed", "label": "Designed Live Posting Allowed", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "designed_journal_entry_side_effect_allowed", "label": "Designed JE Side Effect Allowed", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "designed_purchase_invoice_side_effect_allowed", "label": "Designed PI Side Effect Allowed", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "monitored_payment_entry_docstatus", "label": "Monitored PE Docstatus", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "monitored_payment_entry_status", "label": "Monitored PE Status", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "monitored_reversal_gl_rows", "label": "Monitored Reversal GL Rows", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "ready_for_next_governed_limited_op_candidate_selection_gate", "label": "Ready For Next Governed Limited Op Candidate Selection Gate", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
]

DESIGN_ITEM_FIELDS = [
    {"fieldname": "customer", "label": "Customer", "fieldtype": "Link", "options": "Customer", "read_only": 1},
    {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company", "read_only": 1},
    {"fieldname": "currency", "label": "Currency", "fieldtype": "Link", "options": "Currency", "read_only": 1},
    {"fieldname": "designed_amount", "label": "Designed Amount", "fieldtype": "Currency", "read_only": 1},
    {"fieldname": "invoice_docstatus", "label": "Invoice Docstatus", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "outstanding_sufficient", "label": "Outstanding Sufficient", "fieldtype": "Check", "read_only": 1},
]

FIELD_UPDATES = {
    DESIGN_DOCTYPE: {
        "design_status": {"options": "\nGoverned Limited Operation Design Approved\nNext Governed Limited Operation Design Approved\nNeeds Review\nBlocked\nCancelled"},
        "planning": {"label": "Phase 12Z Planning", "options": PLANNING_DOCTYPE},
        "monitor": {"label": "Phase 12Y Runtime Monitor", "options": "NDIS Next Governed Limited Op Runtime Monitor"},
        "baseline": {"label": "Phase 12X Baseline", "options": "NDIS Next Governed Limited Op Steady Baseline"},
        "closeout": {"label": "Phase 12W Closeout", "options": "NDIS Next Governed Limited Op Closeout"},
        "freeze": {"label": "Phase 12V Freeze", "options": "NDIS Next Governed Limited Op Rollback Freeze"},
        "rollback": {"label": "Phase 12U Rollback", "options": "NDIS Next Governed Limited Op Rollback"},
        "smoke": {"label": "Phase 12T Smoke", "options": "NDIS Next Governed Limited Op Smoke"},
        "execution_gate": {"label": "Phase 12S Execution Gate", "options": "NDIS Next Governed Limited Op Execution Gate"},
        "preview": {"label": "Phase 12R Preview", "options": "NDIS Next Governed Limited Op Preview"},
        "candidate_validation": {"label": "Phase 12Q Candidate Validation", "options": "NDIS Next Governed Limited Op Candidate Validation"},
        "candidate_selection": {"label": "Phase 12P Candidate Selection", "options": "NDIS Next Governed Limited Op Candidate Selection"},
        "previous_design": {"label": "Previous Design", "options": DESIGN_DOCTYPE},
    }
}


@frappe.whitelist()
def install():
    validate_previous_phases()
    ensure_phase13a_fields()
    update_field_properties()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        PLANNING_DOCTYPE,
        PLANNING_ITEM_DOCTYPE,
        DESIGN_DOCTYPE,
        DESIGN_ITEM_DOCTYPE,
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
        frappe.throw(_("Phase 13A requires completed Phase 12Z planning. Missing: {0}").format(", ".join(missing)))


def ensure_phase13a_fields():
    ensure_fields(DESIGN_DOCTYPE, DESIGN_FIELDS)
    ensure_fields(DESIGN_ITEM_DOCTYPE, DESIGN_ITEM_FIELDS)


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
    if "Next Governed Limited Operation Design" not in text_blob:
        content.append({"id": "next_governed_limited_op_design_heading", "type": "header", "data": {"text": "Next Governed Limited Operation Design", "col": 12}})
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
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE13A_DOCTYPES},
        "phase13a_fields": {
            DESIGN_DOCTYPE: {field["fieldname"]: frappe.get_meta(DESIGN_DOCTYPE).has_field(field["fieldname"]) for field in DESIGN_FIELDS},
            DESIGN_ITEM_DOCTYPE: {field["fieldname"]: frappe.get_meta(DESIGN_ITEM_DOCTYPE).has_field(field["fieldname"]) for field in DESIGN_ITEM_FIELDS},
        },
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_next_governed_limited_operation_design_gate": permission_matrix().get("run_next_governed_limited_operation_design_gate"),
            "cancel_next_governed_limited_operation_design_gate_audit": permission_matrix().get("cancel_next_governed_limited_operation_design_gate_audit"),
        },
        "js_hooks": {DESIGN_DOCTYPE: DESIGN_DOCTYPE in doctype_js, DESIGN_ITEM_DOCTYPE: DESIGN_ITEM_DOCTYPE in doctype_js},
        "list_js_hooks": {DESIGN_DOCTYPE: DESIGN_DOCTYPE in doctype_list_js, DESIGN_ITEM_DOCTYPE: DESIGN_ITEM_DOCTYPE in doctype_list_js},
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_payment_entry_posting_config": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def can_import_service():
    try:
        from ndis_finance.services.next_governed_limited_operation_design import quick_next_governed_limited_operation_design_summary

        return callable(quick_next_governed_limited_operation_design_summary)
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
