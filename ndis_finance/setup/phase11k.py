import json
import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


ROLLBACK_DOCTYPE = "NDIS Governed Next Op Rollback"
ROLLBACK_ITEM_DOCTYPE = "NDIS Governed Next Op Rollback Item"

PHASE11K_DOCTYPES = [
    ROLLBACK_DOCTYPE,
    ROLLBACK_ITEM_DOCTYPE,
]

REPORTS = [
    {"report_name": "NDIS Governed Next Op Rollback Report", "ref_doctype": ROLLBACK_DOCTYPE},
    {"report_name": "NDIS Governed Next Op Rollback Item Report", "ref_doctype": ROLLBACK_ITEM_DOCTYPE},
    {"report_name": "NDIS Governed Next Op Rollback Guardrail Report", "ref_doctype": ROLLBACK_DOCTYPE},
]

REPORT_ROLES = [
    "System Manager",
    "NDIS CFO",
    "NDIS Finance Manager",
    "NDIS Finance Officer",
    "NDIS Finance Read Only",
]

DOC_PERM_MATRIX = {
    ROLLBACK_DOCTYPE: {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
    ROLLBACK_ITEM_DOCTYPE: {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
}

WORKSPACE_NAME = "NDIS Finance"

WORKSPACE_SHORTCUTS = [
    {"label": "Governed Next Op Rollbacks", "type": "DocType", "link_to": ROLLBACK_DOCTYPE},
    {"label": "Governed Next Op Rollback Items", "type": "DocType", "link_to": ROLLBACK_ITEM_DOCTYPE},
    {"label": "Governed Next Op Rollback Report", "type": "Report", "link_to": "NDIS Governed Next Op Rollback Report"},
    {"label": "Governed Next Op Rollback Item Report", "type": "Report", "link_to": "NDIS Governed Next Op Rollback Item Report"},
    {"label": "Governed Next Op Rollback Guardrails", "type": "Report", "link_to": "NDIS Governed Next Op Rollback Guardrail Report"},
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_rollback_doctype()
    create_item_doctype()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Governed Next Op Smoke",
        "NDIS Governed Next Op Smoke Item",
        "NDIS Governed Next Op Exec Gate",
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
        frappe.throw(
            _("Phase 11K requires completed Phase 11J smoke. Missing: {0}").format(
                ", ".join(missing)
            )
        )


def create_rollback_doctype():
    _create_doctype(
        name=ROLLBACK_DOCTYPE,
        autoname="field:rollback_id",
        title_field="rollback_id",
        fields=[
            {"fieldname": "rollback_id", "label": "Rollback ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nNeeds Review\nRollback Completed\nBlocked\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "rollback_status", "label": "Rollback Status", "fieldtype": "Select", "options": "\nNext Governed Limited Operation Smoke Rolled Back\nNeeds Review\nBlocked\nCancelled", "read_only": 1, "in_list_view": 1},

            {"fieldname": "result_section", "label": "Rollback Result", "fieldtype": "Section Break"},
            {"fieldname": "rollback_completed", "label": "Rollback Completed", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "phase11j_smoke_verified", "label": "Phase 11J Smoke Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "smoke_payment_entry_verified", "label": "Smoke Payment Entry Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "payment_entry_cancelled_verified", "label": "Payment Entry Cancelled Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "reversal_gl_created_verified", "label": "Reversal GL Created Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "voucher_gl_net_zero_verified", "label": "Voucher GL Net Zero Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "invoice_outstanding_restored_verified", "label": "Invoice Outstanding Restored Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "ready_for_next_governed_limited_operation_rollback_freeze", "label": "Ready For Rollback Freeze", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "policy_mutation_performed", "label": "Policy Mutation Performed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "actual_policy_mutation_count", "label": "Actual Policy Mutation Count", "fieldtype": "Int", "read_only": 1},

            {"fieldname": "payment_entry_section", "label": "Rolled Back Payment Entry", "fieldtype": "Section Break"},
            {"fieldname": "rolled_back_payment_entry", "label": "Rolled Back Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "read_only": 1, "in_list_view": 1},
            {"fieldname": "payment_entry_docstatus_before", "label": "PE Docstatus Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_docstatus_after", "label": "PE Docstatus After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_status_before", "label": "PE Status Before", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "payment_entry_status_after", "label": "PE Status After", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "rolled_back_reference_count", "label": "Rolled Back Reference Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "rolled_back_total_amount", "label": "Rolled Back Total Amount", "fieldtype": "Currency", "read_only": 1},

            {"fieldname": "voucher_gl_section", "label": "Voucher GL Evidence", "fieldtype": "Section Break"},
            {"fieldname": "voucher_gl_rows_before", "label": "Voucher GL Rows Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "voucher_gl_rows_after", "label": "Voucher GL Rows After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "reversal_gl_row_count", "label": "Reversal GL Row Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "voucher_gl_net_after", "label": "Voucher GL Net After", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "voucher_gl_non_zero_account_count", "label": "Voucher GL Non-Zero Account Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "restored_invoice_amount", "label": "Restored Invoice Amount", "fieldtype": "Currency", "read_only": 1},

            {"fieldname": "chain_section", "label": "Evidence Chain", "fieldtype": "Section Break"},
            {"fieldname": "smoke", "label": "Phase 11J Smoke", "fieldtype": "Link", "options": "NDIS Governed Next Op Smoke", "in_list_view": 1},
            {"fieldname": "execution_gate", "label": "Phase 11I Execution Gate", "fieldtype": "Link", "options": "NDIS Governed Next Op Exec Gate"},
            {"fieldname": "preview", "label": "Phase 11H Preview", "fieldtype": "Link", "options": "NDIS Governed Next Op Preview"},
            {"fieldname": "validation", "label": "Phase 11G Validation", "fieldtype": "Link", "options": "NDIS Governed Limited Op Candidate Validation"},
            {"fieldname": "candidate", "label": "Phase 11F Candidate", "fieldtype": "Link", "options": "NDIS Governed Limited Op Candidate"},
            {"fieldname": "design", "label": "Phase 11E Design", "fieldtype": "Link", "options": "NDIS Governed Limited Op Design"},
            {"fieldname": "planning", "label": "Phase 11D Planning", "fieldtype": "Link", "options": "NDIS Governed Limited Op Planning"},

            {"fieldname": "policy_section", "label": "Policy Evidence", "fieldtype": "Section Break"},
            {"fieldname": "target_policy_doctype", "label": "Target Policy DocType", "fieldtype": "Link", "options": "DocType", "read_only": 1},
            {"fieldname": "target_policy", "label": "Target Policy", "fieldtype": "Dynamic Link", "options": "target_policy_doctype"},
            {"fieldname": "target_policy_name", "label": "Target Policy Name", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "target_policy_enabled_before", "label": "Target Policy Enabled Before", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "target_policy_enabled_after", "label": "Target Policy Enabled After", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "target_policy_live_before", "label": "Target Policy Live Before", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "target_policy_live_after", "label": "Target Policy Live After", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "production_batch_enabled_policy_count_before", "label": "Enabled Policy Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "production_batch_enabled_policy_count_after", "label": "Enabled Policy Count After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "live_posting_allowed_policy_count_before", "label": "Live Policy Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "live_posting_allowed_policy_count_after", "label": "Live Policy Count After", "fieldtype": "Int", "read_only": 1},

            {"fieldname": "movement_section", "label": "Movement Guardrails", "fieldtype": "Section Break"},
            {"fieldname": "payment_entry_count_before", "label": "Payment Entry Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_count_after", "label": "Payment Entry Count After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_count_before", "label": "Payment Entry GL Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_count_after", "label": "Payment Entry GL Count After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "actual_payment_entry_created_count", "label": "Actual Payment Entry Created Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "actual_payment_entry_cancelled_count", "label": "Actual Payment Entry Cancelled Count", "fieldtype": "Int", "read_only": 1},
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

            {"fieldname": "score_section", "label": "Rollback Score", "fieldtype": "Section Break"},
            {"fieldname": "rollback_score", "label": "Rollback Score", "fieldtype": "Percent", "read_only": 1},
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
            {"fieldname": "rollback_json", "label": "Rollback JSON", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
        ],
    )


def create_item_doctype():
    _create_doctype(
        name=ROLLBACK_ITEM_DOCTYPE,
        autoname="hash",
        title_field="check_label",
        fields=[
            {"fieldname": "rollback", "label": "Rollback", "fieldtype": "Link", "options": ROLLBACK_DOCTYPE, "reqd": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nPass\nWarning\nBlocker\nInfo\nCancelled", "default": "Info", "in_list_view": 1},
            {"fieldname": "severity", "label": "Severity", "fieldtype": "Select", "options": "\nLow\nMedium\nHigh\nCritical", "default": "Low", "in_list_view": 1},
            {"fieldname": "category", "label": "Category", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "check_key", "label": "Check Key", "fieldtype": "Data"},
            {"fieldname": "check_label", "label": "Check Label", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "detail", "label": "Detail", "fieldtype": "Small Text"},
            {"fieldname": "line_no", "label": "Line No", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "reference_doctype", "label": "Reference DocType", "fieldtype": "Link", "options": "DocType", "read_only": 1},
            {"fieldname": "reference_name", "label": "Reference Name", "fieldtype": "Dynamic Link", "options": "reference_doctype", "read_only": 1},
            {"fieldname": "allocated_amount", "label": "Allocated Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "rolled_back_payment_entry", "label": "Rolled Back Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "read_only": 1},
            {"fieldname": "source_doctype", "label": "Source DocType", "fieldtype": "Link", "options": "DocType"},
            {"fieldname": "source_name", "label": "Source Name", "fieldtype": "Dynamic Link", "options": "source_doctype"},
            {"fieldname": "checked_on", "label": "Checked On", "fieldtype": "Datetime", "read_only": 1},
        ],
    )


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
    base = {
        "role": role, "permlevel": 0, "read": 0, "write": 0, "create": 0, "delete": 0,
        "submit": 0, "cancel": 0, "amend": 0, "report": 0, "export": 0,
        "import": 0, "share": 0, "print": 0, "email": 0,
    }

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
    if "Next Governed Limited Operation Rollback" not in text_blob:
        content.append({"id": "ndis_governed_next_op_rollback_heading", "type": "header", "data": {"text": "Next Governed Limited Operation Rollback", "col": 12}})

    for shortcut in WORKSPACE_SHORTCUTS:
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            continue
        content.append({"id": frappe.scrub(shortcut["label"]), "type": "shortcut", "data": {"label": shortcut["label"], "link_to": shortcut["link_to"], "type": shortcut["type"], "col": 3}})

    ws.content = json.dumps(content)


def add_shortcuts_to_child_table(ws):
    for fieldname in ["shortcuts", "links"]:
        if not ws.meta.has_field(fieldname):
            continue

        existing_blob = ""
        for row in getattr(ws, fieldname, []) or []:
            existing_blob += " " + str(getattr(row, "label", "")) + " " + str(getattr(row, "link_to", ""))

        for shortcut in WORKSPACE_SHORTCUTS:
            if shortcut["label"] in existing_blob or shortcut["link_to"] in existing_blob:
                continue
            row = ws.append(fieldname, {})
            set_child_value(row, "label", shortcut["label"])
            set_child_value(row, "link_to", shortcut["link_to"])
            set_child_value(row, "type", "Link" if fieldname == "links" else shortcut["type"])
            set_child_value(row, "link_type", shortcut["type"])
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
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE11K_DOCTYPES},
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_next_governed_limited_operation_smoke_rollback": permission_matrix().get("run_next_governed_limited_operation_smoke_rollback"),
            "cancel_next_governed_limited_operation_smoke_rollback_audit": permission_matrix().get("cancel_next_governed_limited_operation_smoke_rollback_audit"),
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
        from ndis_finance.services.next_governed_limited_operation_rollback import quick_next_governed_limited_operation_rollback_summary
        return callable(quick_next_governed_limited_operation_rollback_summary)
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
