import json

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE
from ndis_finance.services.permissions import permission_matrix


PLANNING_DOCTYPE = "NDIS Next Governed Limited Op Planning"
PLANNING_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Planning Item"
MONITOR_DOCTYPE = "NDIS Next Governed Limited Op Runtime Monitor"
MONITOR_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Runtime Monitor Item"
PLANNING_READY_FIELD = "ready_for_next_governed_limited_op_design_gate"

PHASE12Z_DOCTYPES = [PLANNING_DOCTYPE, PLANNING_ITEM_DOCTYPE]

REPORTS = [
    {"report_name": "NDIS Next Governed Limited Op Planning Report", "ref_doctype": PLANNING_DOCTYPE},
    {"report_name": "NDIS Next Governed Limited Op Planning Item Report", "ref_doctype": PLANNING_ITEM_DOCTYPE},
    {"report_name": "NDIS Next Governed Limited Op Planning Guardrail Report", "ref_doctype": PLANNING_DOCTYPE},
]

REPORT_ROLES = ["System Manager", "NDIS CFO", "NDIS Finance Manager", "NDIS Finance Officer", "NDIS Finance Read Only"]

DOC_PERM_MATRIX = {
    PLANNING_DOCTYPE: {"System Manager": "full", "NDIS CFO": "read_report_export", "NDIS Finance Manager": "read_report_export", "NDIS Finance Officer": "read_report", "NDIS Finance Read Only": "read_report"},
    PLANNING_ITEM_DOCTYPE: {"System Manager": "full", "NDIS CFO": "read_report_export", "NDIS Finance Manager": "read_report_export", "NDIS Finance Officer": "read_report", "NDIS Finance Read Only": "read_report"},
}

WORKSPACE_NAME = "NDIS Finance"
WORKSPACE_SHORTCUTS = [
    {"label": "Next Governed Limited Op Planning", "type": "DocType", "link_to": PLANNING_DOCTYPE},
    {"label": "Next Governed Limited Op Planning Items", "type": "DocType", "link_to": PLANNING_ITEM_DOCTYPE},
    {"label": "Next Governed Limited Op Planning Report", "type": "Report", "link_to": "NDIS Next Governed Limited Op Planning Report"},
    {"label": "Next Governed Limited Op Planning Item Report", "type": "Report", "link_to": "NDIS Next Governed Limited Op Planning Item Report"},
    {"label": "Next Governed Limited Op Planning Guardrails", "type": "Report", "link_to": "NDIS Next Governed Limited Op Planning Guardrail Report"},
]

PLANNING_FIELDS = [
    {"fieldname": "phase12m_runtime_monitor_verified", "label": "Phase 12M Runtime Monitor Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "runtime_monitor_active_verified", "label": "Runtime Monitor Active Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "reversal_gl_rows_verified", "label": "Reversal GL Rows Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "restored_invoice_amount_verified", "label": "Restored Invoice Amount Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "payment_entry_count_stable_verified", "label": "Payment Entry Count Stable Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "payment_entry_gl_count_stable_verified", "label": "Payment Entry GL Count Stable Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "phase12y_runtime_monitor_verified", "label": "Phase 12Y Runtime Monitor Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "monitor_active_verified", "label": "Monitor Active Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "monitored_payment_entry_verified", "label": "Monitored Payment Entry Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "monitored_payment_entry_cancelled_still_verified", "label": "Monitored PE Cancelled Still Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "monitored_gl_rows_verified", "label": "Monitored GL Rows Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "monitored_reversal_gl_rows_verified", "label": "Monitored Reversal GL Rows Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "monitored_gl_net_zero_verified", "label": "Monitored GL Net Zero Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "invoice_submission_verified", "label": "Invoice Submission Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "invoice_outstanding_verified", "label": "Invoice Outstanding Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "planning_reference_set_locked", "label": "Planning Reference Set Locked", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "planning_reference_set_verified", "label": "Planning Reference Set Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "planned_customer", "label": "Planned Customer", "fieldtype": "Link", "options": "Customer", "read_only": 1},
    {"fieldname": "planned_company", "label": "Planned Company", "fieldtype": "Link", "options": "Company", "read_only": 1},
    {"fieldname": "planned_currency", "label": "Planned Currency", "fieldtype": "Link", "options": "Currency", "read_only": 1},
    {"fieldname": "planned_invoice_names", "label": "Planned Invoice Names", "fieldtype": "Small Text", "read_only": 1},
    {"fieldname": "planned_invoice_count", "label": "Planned Invoice Count", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "planned_gl_entry_count", "label": "Planned GL Entry Count", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "monitored_payment_entry_docstatus", "label": "Monitored PE Docstatus", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "monitored_payment_entry_status", "label": "Monitored PE Status", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "monitored_reversal_gl_rows", "label": "Monitored Reversal GL Rows", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "ready_for_next_governed_limited_operation_design_gate", "label": "Ready For Next Governed Limited Operation Design Gate", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
    {"fieldname": PLANNING_READY_FIELD, "label": "Ready For Next Governed Limited Op Design Gate", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
    {"fieldname": "candidate_validation", "label": "Phase 12Q Candidate Validation", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Candidate Validation"},
    {"fieldname": "candidate_selection", "label": "Phase 12P Candidate Selection", "fieldtype": "Link", "options": "NDIS Next Governed Limited Op Candidate Selection"},
]

ITEM_FIELDS = [
    {"fieldname": "customer", "label": "Customer", "fieldtype": "Link", "options": "Customer", "read_only": 1},
    {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company", "read_only": 1},
    {"fieldname": "currency", "label": "Currency", "fieldtype": "Link", "options": "Currency", "read_only": 1},
    {"fieldname": "planned_amount", "label": "Planned Amount", "fieldtype": "Currency", "read_only": 1},
    {"fieldname": "invoice_docstatus", "label": "Invoice Docstatus", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "outstanding_sufficient", "label": "Outstanding Sufficient", "fieldtype": "Check", "read_only": 1},
]

FIELD_UPDATES = {
    PLANNING_DOCTYPE: {
        "planning_status": {"options": "\nGoverned Limited Operation Planning Approved\nNext Governed Limited Operation Planning Approved\nNeeds Review\nBlocked\nCancelled"},
        "monitor": {"label": "Phase 12Y Runtime Monitor", "options": MONITOR_DOCTYPE},
        "baseline": {"label": "Phase 12X Baseline", "options": "NDIS Next Governed Limited Op Steady Baseline"},
        "closeout": {"label": "Phase 12W Closeout", "options": "NDIS Next Governed Limited Op Closeout"},
        "freeze": {"label": "Phase 12V Freeze", "options": "NDIS Next Governed Limited Op Rollback Freeze"},
        "rollback": {"label": "Phase 12U Rollback", "options": "NDIS Next Governed Limited Op Rollback"},
        "smoke": {"label": "Phase 12T Smoke", "options": "NDIS Next Governed Limited Op Smoke"},
        "execution_gate": {"label": "Phase 12S Execution Gate", "options": "NDIS Next Governed Limited Op Execution Gate"},
        "preview": {"label": "Phase 12R Preview", "options": "NDIS Next Governed Limited Op Preview"},
        "candidate_validation": {"label": "Phase 12Q Candidate Validation", "options": "NDIS Next Governed Limited Op Candidate Validation"},
        "candidate_selection": {"label": "Phase 12P Candidate Selection", "options": "NDIS Next Governed Limited Op Candidate Selection"},
        "design": {"label": "Phase 12O Design", "options": "NDIS Next Governed Limited Op Design"},
        "previous_planning": {"label": "Previous Planning", "options": PLANNING_DOCTYPE},
    }
}


@frappe.whitelist()
def install():
    validate_previous_phases()
    ensure_phase12z_fields()
    update_field_properties()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        MONITOR_DOCTYPE,
        MONITOR_ITEM_DOCTYPE,
        PLANNING_DOCTYPE,
        PLANNING_ITEM_DOCTYPE,
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
        frappe.throw(_("Phase 12Z requires completed Phase 12Y runtime monitor. Missing: {0}").format(", ".join(missing)))


def ensure_phase12z_fields():
    ensure_fields(PLANNING_DOCTYPE, PLANNING_FIELDS)
    ensure_fields(PLANNING_ITEM_DOCTYPE, ITEM_FIELDS)


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
    if "Next Governed Limited Operation Planning" not in text_blob:
        content.append({"id": "next_governed_limited_op_planning_heading", "type": "header", "data": {"text": "Next Governed Limited Operation Planning", "col": 12}})
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
    return {
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE12Z_DOCTYPES},
        "phase12z_fields": check_phase12z_fields(),
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_next_governed_limited_operation_planning_gate": permission_matrix().get("run_next_governed_limited_operation_planning_gate"),
            "cancel_next_governed_limited_operation_planning_gate_audit": permission_matrix().get("cancel_next_governed_limited_operation_planning_gate_audit"),
        },
        "js_hooks": {PLANNING_DOCTYPE: PLANNING_DOCTYPE in hooks.get("doctype_js", {}), PLANNING_ITEM_DOCTYPE: PLANNING_ITEM_DOCTYPE in hooks.get("doctype_js", {})},
        "list_js_hooks": {PLANNING_DOCTYPE: PLANNING_DOCTYPE in hooks.get("doctype_list_js", {}), PLANNING_ITEM_DOCTYPE: PLANNING_ITEM_DOCTYPE in hooks.get("doctype_list_js", {})},
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_payment_entry_posting_config": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def check_phase12z_fields():
    return {
        PLANNING_DOCTYPE: {field["fieldname"]: frappe.get_meta(PLANNING_DOCTYPE).has_field(field["fieldname"]) for field in PLANNING_FIELDS},
        PLANNING_ITEM_DOCTYPE: {field["fieldname"]: frappe.get_meta(PLANNING_ITEM_DOCTYPE).has_field(field["fieldname"]) for field in ITEM_FIELDS},
    }


def can_import_service():
    try:
        from ndis_finance.services.next_governed_limited_operation_planning import quick_next_governed_limited_operation_planning_summary

        return callable(quick_next_governed_limited_operation_planning_summary)
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
