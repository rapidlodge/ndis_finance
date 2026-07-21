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
    ensure_doctype,
    has_meta_field,
)
from ndis_finance.services.permissions import permission_matrix


ROLLBACK_READY_FIELD = "ready_for_next_governed_limited_op_rollback_freeze"

PHASE14E_DOCTYPES = [ROLLBACK_DOCTYPE, ROLLBACK_ITEM_DOCTYPE]

REPORTS = [
    {"report_name": "NDIS Next Governed Limited Op Smoke Rollback Phase14E Report", "ref_doctype": ROLLBACK_DOCTYPE},
    {"report_name": "NDIS Next Governed Limited Op Smoke Rollback Phase14E Item Report", "ref_doctype": ROLLBACK_ITEM_DOCTYPE},
    {"report_name": "NDIS Next Governed Limited Op Smoke Rollback Phase14E Guardrail Report", "ref_doctype": ROLLBACK_DOCTYPE},
]

WORKSPACE_SHORTCUTS = [
    {"label": "Phase14E Smoke Rollback Report", "type": "Report", "link_to": "NDIS Next Governed Limited Op Smoke Rollback Phase14E Report"},
    {"label": "Phase14E Smoke Rollback Item Report", "type": "Report", "link_to": "NDIS Next Governed Limited Op Smoke Rollback Phase14E Item Report"},
    {"label": "Phase14E Smoke Rollback Guardrails", "type": "Report", "link_to": "NDIS Next Governed Limited Op Smoke Rollback Phase14E Guardrail Report"},
]

PHASE14E_FIELDS = [
    {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nNeeds Review\nRolled Back\nSmoke Rollback Completed\nBlocked\nCancelled", "default": "Draft", "in_list_view": 1},
    {"fieldname": "rollback_status", "label": "Rollback Status", "fieldtype": "Select", "options": "\nNext Governed Limited Operation Smoke Rolled Back\nNext Governed Limited Operation Smoke Rollback Completed\nNeeds Review\nBlocked\nCancelled", "read_only": 1, "in_list_view": 1},
    {"fieldname": "phase14d_smoke_verified", "label": "Phase 14D Smoke Verified", "fieldtype": "Check", "read_only": 1},
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
    {"fieldname": "invoice_outstanding_before_rollback", "label": "Invoice Outstanding Before Rollback", "fieldtype": "Currency", "read_only": 1},
    {"fieldname": "invoice_outstanding_after_rollback", "label": "Invoice Outstanding After Rollback", "fieldtype": "Currency", "read_only": 1},
    {"fieldname": "rollback_gl_rows", "label": "Rollback GL Rows", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "rollback_direct_cancelled_gl_rows", "label": "Rollback Direct Cancelled GL Rows", "fieldtype": "Int", "read_only": 1},
]

PHASE14E_ITEM_FIELDS = [
    {"fieldname": "gated_payment_entry", "label": "Gated Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "read_only": 1},
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    ensure_doctype(ROLLBACK_DOCTYPE, "field:rollback_id", "rollback_id", PHASE14E_FIELDS)
    ensure_doctype(ROLLBACK_ITEM_DOCTYPE, "hash", "check_label", PHASE14E_ITEM_FIELDS)
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
        frappe.throw(_("Phase 14E requires completed Phase 14D smoke and Phase 13G rollback schema. Missing: {0}").format(", ".join(missing)))


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
    add_phase14e_shortcuts(ws)
    ws.save(ignore_permissions=True)


def add_phase14e_shortcuts(ws):
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
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE14E_DOCTYPES},
        "phase14e_fields": {
            ROLLBACK_DOCTYPE: {field["fieldname"]: has_meta_field(ROLLBACK_DOCTYPE, field["fieldname"]) for field in PHASE14E_FIELDS},
            ROLLBACK_ITEM_DOCTYPE: {field["fieldname"]: has_meta_field(ROLLBACK_ITEM_DOCTYPE, field["fieldname"]) for field in PHASE14E_ITEM_FIELDS},
        },
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_next_governed_limited_operation_smoke_rollback_phase14e": permission_matrix().get("run_next_governed_limited_operation_smoke_rollback_phase14e"),
            "cancel_next_governed_limited_operation_smoke_rollback_phase14e_audit": permission_matrix().get("cancel_next_governed_limited_operation_smoke_rollback_phase14e_audit"),
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
        from ndis_finance.services.next_governed_limited_operation_smoke_rollback_phase14e import quick_next_governed_limited_operation_smoke_rollback_phase14e_summary
        return callable(quick_next_governed_limited_operation_smoke_rollback_phase14e_summary)
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
