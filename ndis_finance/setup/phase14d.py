import json

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE
from ndis_finance.services.permissions import permission_matrix


SMOKE_DOCTYPE = "NDIS Next Governed Limited Op Smoke"
SMOKE_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Smoke Item"
EXECUTION_GATE_DOCTYPE = "NDIS Next Governed Limited Op Execution Gate"
EXECUTION_GATE_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Execution Gate Item"

PHASE14D_DOCTYPES = [SMOKE_DOCTYPE, SMOKE_ITEM_DOCTYPE]
SMOKE_READY_FIELD = "ready_for_next_governed_limited_op_smoke_rollback"

REPORTS = [
    {"report_name": "NDIS Next Governed Limited Op Smoke Phase14D Report", "ref_doctype": SMOKE_DOCTYPE},
    {"report_name": "NDIS Next Governed Limited Op Smoke Phase14D Item Report", "ref_doctype": SMOKE_ITEM_DOCTYPE},
    {"report_name": "NDIS Next Governed Limited Op Smoke Phase14D Guardrail Report", "ref_doctype": SMOKE_DOCTYPE},
]

REPORT_ROLES = ["System Manager", "NDIS CFO", "NDIS Finance Manager", "NDIS Finance Officer", "NDIS Finance Read Only"]
DOC_PERM_MATRIX = {
    SMOKE_DOCTYPE: {"System Manager": "full", "NDIS CFO": "read_report_export", "NDIS Finance Manager": "read_report_export", "NDIS Finance Officer": "read_report", "NDIS Finance Read Only": "read_report"},
    SMOKE_ITEM_DOCTYPE: {"System Manager": "full", "NDIS CFO": "read_report_export", "NDIS Finance Manager": "read_report_export", "NDIS Finance Officer": "read_report", "NDIS Finance Read Only": "read_report"},
}

WORKSPACE_NAME = "NDIS Finance"
WORKSPACE_SHORTCUTS = [
    {"label": "Next Governed Limited Op Smoke Phase14D Report", "type": "Report", "link_to": "NDIS Next Governed Limited Op Smoke Phase14D Report"},
    {"label": "Next Governed Limited Op Smoke Phase14D Item Report", "type": "Report", "link_to": "NDIS Next Governed Limited Op Smoke Phase14D Item Report"},
    {"label": "Next Governed Limited Op Smoke Phase14D Guardrails", "type": "Report", "link_to": "NDIS Next Governed Limited Op Smoke Phase14D Guardrail Report"},
]

SMOKE_FIELDS = [
    {"fieldname": "phase14c_execution_gate_verified", "label": "Phase 14C Execution Gate Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "execution_gate_approved_verified", "label": "Execution Gate Approved Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "execution_gate_payment_entry_verified", "label": "Execution Gate Payment Entry Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "execution_gate_payment_entry_cancelled_verified", "label": "Execution Gate Payment Entry Cancelled Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "execution_gate_gl_rows_verified", "label": "Execution Gate GL Rows Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "execution_gate_reversal_gl_rows_verified", "label": "Execution Gate Reversal GL Rows Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "execution_gate_gl_net_zero_verified", "label": "Execution Gate GL Net Zero Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "execution_gate_restored_invoice_amount_verified", "label": "Execution Gate Restored Invoice Amount Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "policy_state_preserved_verified", "label": "Policy State Preserved Verified", "fieldtype": "Check", "read_only": 1},
    {"fieldname": "gated_payment_entry", "label": "Gated Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "read_only": 1, "in_list_view": 1},
    {"fieldname": "gated_payment_entry_docstatus", "label": "Gated PE Docstatus", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "gated_payment_entry_status", "label": "Gated PE Status", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "previous_gated_payment_entry", "label": "Previous Gated Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "read_only": 1},
    {"fieldname": "previous_gated_payment_entry_docstatus", "label": "Previous Gated PE Docstatus", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "previous_gated_payment_entry_status", "label": "Previous Gated PE Status", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "smoke_payment_entry", "label": "Smoke Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "read_only": 1, "in_list_view": 1},
    {"fieldname": "smoke_payment_entry_docstatus", "label": "Smoke PE Docstatus", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "smoke_payment_entry_status", "label": "Smoke PE Status", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "smoke_source_doctype", "label": "Smoke Source DocType", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "smoke_reference_doctype", "label": "Smoke Reference DocType", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "smoke_party_type", "label": "Smoke Party Type", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "smoke_customer", "label": "Smoke Customer", "fieldtype": "Link", "options": "Customer", "read_only": 1},
    {"fieldname": "smoke_company", "label": "Smoke Company", "fieldtype": "Link", "options": "Company", "read_only": 1},
    {"fieldname": "smoke_currency", "label": "Smoke Currency", "fieldtype": "Link", "options": "Currency", "read_only": 1},
    {"fieldname": "smoke_invoice_names", "label": "Smoke Invoice Names", "fieldtype": "Small Text", "read_only": 1},
    {"fieldname": "smoke_invoice_count", "label": "Smoke Invoice Count", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "smoke_total_amount", "label": "Smoke Total Amount", "fieldtype": "Currency", "read_only": 1},
    {"fieldname": "invoice_outstanding_before_smoke", "label": "Invoice Outstanding Before Smoke", "fieldtype": "Currency", "read_only": 1},
    {"fieldname": "invoice_outstanding_after_smoke", "label": "Invoice Outstanding After Smoke", "fieldtype": "Currency", "read_only": 1},
    {"fieldname": "smoke_gl_rows", "label": "Smoke GL Rows", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "smoke_gl_net", "label": "Smoke GL Net", "fieldtype": "Currency", "read_only": 1},
    {"fieldname": "smoke_direct_cancelled_gl_rows", "label": "Smoke Direct Cancelled GL Rows", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "smoke_payment_type", "label": "Smoke Payment Type", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "smoke_party", "label": "Smoke Party", "fieldtype": "Data", "read_only": 1},
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
    {"fieldname": SMOKE_READY_FIELD, "label": "Ready For Next Governed Limited Op Smoke Rollback", "fieldtype": "Check", "read_only": 1},
]

SMOKE_ITEM_FIELDS = [
    {"fieldname": "smoke_payment_entry", "label": "Smoke Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "read_only": 1},
    {"fieldname": "outstanding_before", "label": "Outstanding Before", "fieldtype": "Currency", "read_only": 1},
    {"fieldname": "outstanding_after", "label": "Outstanding After", "fieldtype": "Currency", "read_only": 1},
    {"fieldname": "gated_payment_entry", "label": "Gated Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "read_only": 1},
]

FIELD_UPDATES = {
    SMOKE_DOCTYPE: {
        "status": {"options": "\nDraft\nNeeds Review\nCompleted\nSmoke Completed\nSmoke Completed - Rollback Required\nBlocked\nCancelled"},
        "smoke_status": {"options": "\nNext Governed Limited Operation Smoke Completed\nNeeds Review\nBlocked\nCancelled"},
        "execution_gate": {"label": "Phase 14C Execution Gate", "options": EXECUTION_GATE_DOCTYPE},
        "preview": {"label": "Phase 14B Preview", "options": "NDIS Next Governed Limited Op Preview"},
        "candidate_validation": {"label": "Phase 13O Candidate Validation", "options": "NDIS Next Governed Limited Op Candidate Validation"},
        "candidate_selection": {"label": "Phase 13N Candidate Selection", "options": "NDIS Next Governed Limited Op Candidate Selection"},
        "design": {"label": "Phase 13M Design", "options": "NDIS Next Governed Limited Op Design"},
        "planning": {"label": "Phase 13L Planning", "options": "NDIS Next Governed Limited Op Planning"},
        "monitor": {"label": "Phase 13K Runtime Monitor", "options": "NDIS Next Governed Limited Op Runtime Monitor"},
        "baseline": {"label": "Phase 13J Baseline", "options": "NDIS Next Governed Limited Op Steady Baseline"},
        "closeout": {"label": "Phase 13I Closeout", "options": "NDIS Next Governed Limited Op Closeout"},
        "freeze": {"label": "Phase 13H Freeze", "options": "NDIS Next Governed Limited Op Rollback Freeze"},
        "rollback": {"label": "Phase 13G Rollback", "options": "NDIS Next Governed Limited Op Smoke Rollback"},
        "previous_smoke": {"label": "Previous Smoke", "options": SMOKE_DOCTYPE},
    }
}


@frappe.whitelist()
def install():
    validate_previous_phases()
    ensure_phase14d_fields()
    update_field_properties()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        EXECUTION_GATE_DOCTYPE,
        EXECUTION_GATE_ITEM_DOCTYPE,
        SMOKE_DOCTYPE,
        SMOKE_ITEM_DOCTYPE,
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
        frappe.throw(_("Phase 14D requires completed Phase 14C execution gate. Missing: {0}").format(", ".join(missing)))


def ensure_phase14d_fields():
    ensure_fields(SMOKE_DOCTYPE, SMOKE_FIELDS)
    ensure_fields(SMOKE_ITEM_DOCTYPE, SMOKE_ITEM_FIELDS)


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
    if "Next Governed Limited Operation Smoke Phase14D" not in text_blob:
        content.append({"id": "next_governed_limited_op_smoke_phase14d_heading", "type": "header", "data": {"text": "Next Governed Limited Operation Smoke Phase14D", "col": 12}})
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
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE14D_DOCTYPES},
        "phase14d_fields": {
            SMOKE_DOCTYPE: {field["fieldname"]: has_meta_field(SMOKE_DOCTYPE, field["fieldname"]) for field in SMOKE_FIELDS},
            SMOKE_ITEM_DOCTYPE: {field["fieldname"]: has_meta_field(SMOKE_ITEM_DOCTYPE, field["fieldname"]) for field in SMOKE_ITEM_FIELDS},
        },
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_next_governed_limited_operation_smoke_phase14d": permission_matrix().get("run_next_governed_limited_operation_smoke_phase14d"),
            "cancel_next_governed_limited_operation_smoke_phase14d_audit": permission_matrix().get("cancel_next_governed_limited_operation_smoke_phase14d_audit"),
        },
        "js_hooks": {
            SMOKE_DOCTYPE: SMOKE_DOCTYPE in doctype_js,
            SMOKE_ITEM_DOCTYPE: SMOKE_ITEM_DOCTYPE in doctype_js,
        },
        "list_js_hooks": {
            SMOKE_DOCTYPE: SMOKE_DOCTYPE in doctype_list_js,
            SMOKE_ITEM_DOCTYPE: SMOKE_ITEM_DOCTYPE in doctype_list_js,
        },
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_payment_entry_posting_config": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def has_meta_field(doctype, fieldname):
    return bool(frappe.get_meta(doctype).has_field(fieldname))


def can_import_service():
    try:
        from ndis_finance.services.next_governed_limited_operation_smoke_phase14d import quick_next_governed_limited_operation_smoke_phase14d_summary
        return callable(quick_next_governed_limited_operation_smoke_phase14d_summary)
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
