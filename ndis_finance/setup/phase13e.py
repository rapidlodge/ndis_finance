import json

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE
from ndis_finance.services.permissions import permission_matrix


EXECUTION_GATE_DOCTYPE = "NDIS Next Governed Limited Op Execution Gate"
EXECUTION_GATE_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Execution Gate Item"
PREVIEW_DOCTYPE = "NDIS Next Governed Limited Op Preview"
PREVIEW_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Preview Item"

PHASE13E_DOCTYPES = [EXECUTION_GATE_DOCTYPE, EXECUTION_GATE_ITEM_DOCTYPE]
EXECUTION_GATE_READY_FIELD = "ready_for_next_governed_limited_op_smoke"

REPORTS = [
    {"report_name": "NDIS Next Governed Limited Op Execution Gate Report", "ref_doctype": EXECUTION_GATE_DOCTYPE},
    {"report_name": "NDIS Next Governed Limited Op Execution Gate Item Report", "ref_doctype": EXECUTION_GATE_ITEM_DOCTYPE},
    {"report_name": "NDIS Next Governed Limited Op Execution Gate Guardrail Report", "ref_doctype": EXECUTION_GATE_DOCTYPE},
]

REPORT_ROLES = ["System Manager", "NDIS CFO", "NDIS Finance Manager", "NDIS Finance Officer", "NDIS Finance Read Only"]
DOC_PERM_MATRIX = {
    EXECUTION_GATE_DOCTYPE: {"System Manager": "full", "NDIS CFO": "read_report_export", "NDIS Finance Manager": "read_report_export", "NDIS Finance Officer": "read_report", "NDIS Finance Read Only": "read_report"},
    EXECUTION_GATE_ITEM_DOCTYPE: {"System Manager": "full", "NDIS CFO": "read_report_export", "NDIS Finance Manager": "read_report_export", "NDIS Finance Officer": "read_report", "NDIS Finance Read Only": "read_report"},
}

WORKSPACE_NAME = "NDIS Finance"
WORKSPACE_SHORTCUTS = [
    {"label": "Next Governed Limited Op Execution Gate", "type": "DocType", "link_to": EXECUTION_GATE_DOCTYPE},
    {"label": "Next Governed Limited Op Execution Gate Items", "type": "DocType", "link_to": EXECUTION_GATE_ITEM_DOCTYPE},
    {"label": "Next Governed Limited Op Execution Gate Report", "type": "Report", "link_to": "NDIS Next Governed Limited Op Execution Gate Report"},
    {"label": "Next Governed Limited Op Execution Gate Item Report", "type": "Report", "link_to": "NDIS Next Governed Limited Op Execution Gate Item Report"},
    {"label": "Next Governed Limited Op Execution Gate Guardrails", "type": "Report", "link_to": "NDIS Next Governed Limited Op Execution Gate Guardrail Report"},
]

EXECUTION_GATE_FIELDS = [
    {"fieldname": "phase13d_preview_verified", "label": "Phase 13D Preview Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "execution_gate_source_locked", "label": "Execution Gate Source Locked", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "execution_gate_shape_locked", "label": "Execution Gate Shape Locked", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "execution_gate_reference_set_locked", "label": "Execution Gate Reference Set Locked", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "execution_gate_reference_set_verified", "label": "Execution Gate Reference Set Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "execution_gate_smoke_allowed", "label": "Execution Gate Smoke Allowed", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "execution_gate_live_posting_blocked", "label": "Execution Gate Live Posting Blocked", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "execution_payment_type", "label": "Execution Payment Type", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "execution_party", "label": "Execution Party", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "execution_posting_allowed", "label": "Execution Posting Allowed", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "execution_submit_allowed", "label": "Execution Submit Allowed", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "execution_cancel_allowed", "label": "Execution Cancel Allowed", "fieldtype": "Check", "read_only": 1},
]

EXECUTION_GATE_ITEM_FIELDS = [
    {"fieldname": "execution_amount", "label": "Execution Amount", "fieldtype": "Currency", "read_only": 1},
    {"fieldname": "invoice_docstatus", "label": "Invoice Docstatus", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "outstanding_sufficient", "label": "Outstanding Sufficient", "fieldtype": "Check", "read_only": 1},
]

FIELD_UPDATES = {
    EXECUTION_GATE_DOCTYPE: {
        "execution_gate_status": {"options": "\nNext Governed Limited Operation Execution Gate Approved\nNeeds Review\nBlocked\nCancelled"},
        "preview": {"label": "Phase 13D Preview", "options": PREVIEW_DOCTYPE},
        "candidate_validation": {"label": "Phase 13C Candidate Validation", "options": "NDIS Next Governed Limited Op Candidate Validation"},
        "candidate_selection": {"label": "Phase 13B Candidate Selection", "options": "NDIS Next Governed Limited Op Candidate Selection"},
        "design": {"label": "Phase 13A Design", "options": "NDIS Next Governed Limited Op Design"},
        "planning": {"label": "Phase 12Z Planning", "options": "NDIS Next Governed Limited Op Planning"},
        "monitor": {"label": "Phase 12Y Runtime Monitor", "options": "NDIS Next Governed Limited Op Runtime Monitor"},
        "baseline": {"label": "Phase 12X Baseline", "options": "NDIS Next Governed Limited Op Steady Baseline"},
        "closeout": {"label": "Phase 12W Closeout", "options": "NDIS Next Governed Limited Op Closeout"},
        "freeze": {"label": "Phase 12V Freeze", "options": "NDIS Next Governed Limited Op Rollback Freeze"},
        "rollback": {"label": "Phase 12U Rollback", "options": "NDIS Next Governed Limited Op Rollback"},
        "smoke": {"label": "Phase 12T Smoke", "options": "NDIS Next Governed Limited Op Smoke"},
        "previous_execution_gate": {"label": "Previous Execution Gate", "options": EXECUTION_GATE_DOCTYPE},
    }
}


@frappe.whitelist()
def install():
    validate_previous_phases()
    ensure_phase13e_fields()
    update_field_properties()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        PREVIEW_DOCTYPE,
        PREVIEW_ITEM_DOCTYPE,
        EXECUTION_GATE_DOCTYPE,
        EXECUTION_GATE_ITEM_DOCTYPE,
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
        frappe.throw(_("Phase 13E requires completed Phase 13D preview. Missing: {0}").format(", ".join(missing)))


def ensure_phase13e_fields():
    ensure_fields(EXECUTION_GATE_DOCTYPE, EXECUTION_GATE_FIELDS)
    ensure_fields(EXECUTION_GATE_ITEM_DOCTYPE, EXECUTION_GATE_ITEM_FIELDS)


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
    if "Next Governed Limited Operation Execution Gate" not in text_blob:
        content.append({"id": "next_governed_limited_op_execution_gate_heading", "type": "header", "data": {"text": "Next Governed Limited Operation Execution Gate", "col": 12}})
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
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE13E_DOCTYPES},
        "phase13e_fields": {
            EXECUTION_GATE_DOCTYPE: {field["fieldname"]: has_meta_field(EXECUTION_GATE_DOCTYPE, field["fieldname"]) for field in EXECUTION_GATE_FIELDS},
            EXECUTION_GATE_ITEM_DOCTYPE: {field["fieldname"]: has_meta_field(EXECUTION_GATE_ITEM_DOCTYPE, field["fieldname"]) for field in EXECUTION_GATE_ITEM_FIELDS},
        },
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_next_governed_limited_operation_execution_gate": permission_matrix().get("run_next_governed_limited_operation_execution_gate"),
            "cancel_next_governed_limited_operation_execution_gate_audit": permission_matrix().get("cancel_next_governed_limited_operation_execution_gate_audit"),
        },
        "js_hooks": {
            EXECUTION_GATE_DOCTYPE: EXECUTION_GATE_DOCTYPE in doctype_js,
            EXECUTION_GATE_ITEM_DOCTYPE: EXECUTION_GATE_ITEM_DOCTYPE in doctype_js,
        },
        "list_js_hooks": {
            EXECUTION_GATE_DOCTYPE: EXECUTION_GATE_DOCTYPE in doctype_list_js,
            EXECUTION_GATE_ITEM_DOCTYPE: EXECUTION_GATE_ITEM_DOCTYPE in doctype_list_js,
        },
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_payment_entry_posting_config": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def has_meta_field(doctype, fieldname):
    return bool(frappe.get_meta(doctype).has_field(fieldname))


def can_import_service():
    try:
        from ndis_finance.services.next_governed_limited_operation_execution_gate import quick_next_governed_limited_operation_execution_gate_summary
        return callable(quick_next_governed_limited_operation_execution_gate_summary)
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
