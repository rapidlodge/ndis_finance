import json
import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


PLANNING_DOCTYPE = "NDIS Next Governed Limited Op Planning"
PLANNING_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Planning Item"

PHASE12B_DOCTYPES = [
    PLANNING_DOCTYPE,
    PLANNING_ITEM_DOCTYPE,
]

REPORTS = [
    {"report_name": "NDIS Next Governed Limited Op Planning Report", "ref_doctype": PLANNING_DOCTYPE},
    {"report_name": "NDIS Next Governed Limited Op Planning Item Report", "ref_doctype": PLANNING_ITEM_DOCTYPE},
    {"report_name": "NDIS Next Governed Limited Op Planning Guardrail Report", "ref_doctype": PLANNING_DOCTYPE},
]

REPORT_ROLES = [
    "System Manager",
    "NDIS CFO",
    "NDIS Finance Manager",
    "NDIS Finance Officer",
    "NDIS Finance Read Only",
]

DOC_PERM_MATRIX = {
    PLANNING_DOCTYPE: {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
    PLANNING_ITEM_DOCTYPE: {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
}

WORKSPACE_NAME = "NDIS Finance"

WORKSPACE_SHORTCUTS = [
    {"label": "Next Governed Limited Op Planning", "type": "DocType", "link_to": PLANNING_DOCTYPE},
    {"label": "Next Governed Limited Op Planning Items", "type": "DocType", "link_to": PLANNING_ITEM_DOCTYPE},
    {"label": "Next Governed Limited Op Planning Report", "type": "Report", "link_to": "NDIS Next Governed Limited Op Planning Report"},
    {"label": "Next Governed Limited Op Planning Item Report", "type": "Report", "link_to": "NDIS Next Governed Limited Op Planning Item Report"},
    {"label": "Next Governed Limited Op Planning Guardrails", "type": "Report", "link_to": "NDIS Next Governed Limited Op Planning Guardrail Report"},
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_planning_doctype()
    create_item_doctype()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Next Post Closeout Runtime Monitor",
        "NDIS Next Post Closeout Runtime Monitor Item",
        "NDIS Next Post Closeout Steady Baseline",
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
            _("Phase 12B requires completed Phase 12A monitor. Missing: {0}").format(
                ", ".join(missing)
            )
        )


def create_planning_doctype():
    _create_doctype(
        name=PLANNING_DOCTYPE,
        autoname="field:planning_id",
        title_field="planning_id",
        fields=[
            {"fieldname": "planning_id", "label": "Planning ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nNeeds Review\nPlanning Approved\nBlocked\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "planning_status", "label": "Planning Status", "fieldtype": "Select", "options": "\nGoverned Limited Operation Planning Approved\nNeeds Review\nBlocked\nCancelled", "read_only": 1, "in_list_view": 1},

            {"fieldname": "result_section", "label": "Planning Result", "fieldtype": "Section Break"},
            {"fieldname": "planning_approved", "label": "Planning Approved", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "phase12a_monitor_verified", "label": "Phase 12A Monitor Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "monitor_active_verified", "label": "Monitor Active Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "baseline_active_verified", "label": "Baseline Active Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "planning_envelope_locked", "label": "Planning Envelope Locked", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "planning_source_locked", "label": "Planning Source Locked", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "planning_shape_locked", "label": "Planning Shape Locked", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "candidate_selection_not_started", "label": "Candidate Selection Not Started", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "monitored_payment_entry_verified", "label": "Monitored Payment Entry Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "payment_entry_cancelled_still_verified", "label": "Payment Entry Cancelled Still Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "voucher_gl_rows_verified", "label": "Voucher GL Rows Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "voucher_gl_net_zero_verified", "label": "Voucher GL Net Zero Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "invoice_outstanding_restored_still_verified", "label": "Invoice Outstanding Restored Still Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "no_new_accounting_movement_verified", "label": "No New Accounting Movement Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "policy_state_preserved_verified", "label": "Policy State Preserved Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "ready_for_governed_limited_operation_design_gate", "label": "Ready For Governed Limited Operation Design Gate", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "policy_mutation_performed", "label": "Policy Mutation Performed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "actual_policy_mutation_count", "label": "Actual Policy Mutation Count", "fieldtype": "Int", "read_only": 1},

            {"fieldname": "planning_envelope_section", "label": "Planning Envelope", "fieldtype": "Section Break"},
            {"fieldname": "planned_source_doctype", "label": "Planned Source DocType", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "planned_reference_doctype", "label": "Planned Reference DocType", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "planned_party_type", "label": "Planned Party Type", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "planned_line_count", "label": "Planned Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "planned_total_amount", "label": "Planned Total Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "planned_payment_entry_count", "label": "Planned Payment Entry Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "planned_live_posting_allowed", "label": "Planned Live Posting Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "planned_journal_entry_side_effect_allowed", "label": "Planned JE Side Effect Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "planned_purchase_invoice_side_effect_allowed", "label": "Planned PI Side Effect Allowed", "fieldtype": "Check", "read_only": 1},

            {"fieldname": "monitor_section", "label": "Monitor Evidence", "fieldtype": "Section Break"},
            {"fieldname": "monitored_payment_entry", "label": "Monitored Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "read_only": 1, "in_list_view": 1},
            {"fieldname": "payment_entry_docstatus_planning", "label": "PE Docstatus Planning", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_status_planning", "label": "PE Status Planning", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "monitored_reference_count", "label": "Monitored Reference Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "monitored_total_amount", "label": "Monitored Total Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "monitored_voucher_gl_rows", "label": "Monitored Voucher GL Rows", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "monitored_voucher_gl_net", "label": "Monitored Voucher GL Net", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "monitored_voucher_gl_non_zero_account_count", "label": "Monitored Voucher GL Non-Zero Account Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "monitored_restored_invoice_amount", "label": "Monitored Restored Invoice Amount", "fieldtype": "Currency", "read_only": 1},

            {"fieldname": "chain_section", "label": "Evidence Chain", "fieldtype": "Section Break"},
            {"fieldname": "monitor", "label": "Phase 12A Monitor", "fieldtype": "Link", "options": "NDIS Next Post Closeout Runtime Monitor", "in_list_view": 1},
            {"fieldname": "baseline", "label": "Phase 11Z Baseline", "fieldtype": "Link", "options": "NDIS Next Post Closeout Steady Baseline"},
            {"fieldname": "closeout", "label": "Phase 11Y Closeout", "fieldtype": "Link", "options": "NDIS Next Controlled Cycle Closeout"},
            {"fieldname": "freeze", "label": "Phase 11X Freeze", "fieldtype": "Link", "options": "NDIS Next Controlled Cycle Rollback Freeze"},
            {"fieldname": "rollback", "label": "Phase 11W Rollback", "fieldtype": "Link", "options": "NDIS Next Controlled Cycle Rollback"},
            {"fieldname": "smoke", "label": "Phase 11V Smoke", "fieldtype": "Link", "options": "NDIS Next Controlled Cycle Smoke"},
            {"fieldname": "execution_gate", "label": "Phase 11U Execution Gate", "fieldtype": "Link", "options": "NDIS Next Controlled Cycle Exec Gate"},
            {"fieldname": "preview", "label": "Phase 11T Preview", "fieldtype": "Link", "options": "NDIS Next Controlled Cycle Preview"},
            {"fieldname": "validation", "label": "Phase 11S Validation", "fieldtype": "Link", "options": "NDIS Next Controlled Cycle Cand Valid"},
            {"fieldname": "candidate", "label": "Phase 11R Candidate", "fieldtype": "Link", "options": "NDIS Next Controlled Cycle Candidate"},
            {"fieldname": "design", "label": "Phase 11Q Design", "fieldtype": "Link", "options": "NDIS Next Controlled Cycle Design"},
            {"fieldname": "previous_planning", "label": "Previous Planning", "fieldtype": "Link", "options": "NDIS Next Controlled Cycle Planning"},

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
            {"fieldname": "actual_payment_entry_created_count", "label": "Actual PE Created Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "actual_payment_entry_cancelled_count", "label": "Actual PE Cancelled Count", "fieldtype": "Int", "read_only": 1},
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

            {"fieldname": "score_section", "label": "Planning Score", "fieldtype": "Section Break"},
            {"fieldname": "planning_score", "label": "Planning Score", "fieldtype": "Percent", "read_only": 1},
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
            {"fieldname": "planning_json", "label": "Planning JSON", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
        ],
    )


def create_item_doctype():
    _create_doctype(
        name=PLANNING_ITEM_DOCTYPE,
        autoname="hash",
        title_field="check_label",
        fields=[
            {"fieldname": "planning", "label": "Planning", "fieldtype": "Link", "options": PLANNING_DOCTYPE, "reqd": 1, "in_list_view": 1},
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
            {"fieldname": "current_outstanding_amount", "label": "Current Outstanding Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "monitored_payment_entry", "label": "Monitored Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "read_only": 1},
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
    if "Next Governed Limited Op Planning" not in text_blob:
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
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE12B_DOCTYPES},
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_governed_limited_operation_planning": permission_matrix().get("run_governed_limited_operation_planning"),
            "cancel_governed_limited_operation_planning_audit": permission_matrix().get("cancel_governed_limited_operation_planning_audit"),
        },
        "js_hooks": {
            PLANNING_DOCTYPE: PLANNING_DOCTYPE in doctype_js,
            PLANNING_ITEM_DOCTYPE: PLANNING_ITEM_DOCTYPE in doctype_js,
        },
        "list_js_hooks": {
            PLANNING_DOCTYPE: PLANNING_DOCTYPE in doctype_list_js,
            PLANNING_ITEM_DOCTYPE: PLANNING_ITEM_DOCTYPE in doctype_list_js,
        },
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_payment_entry_posting_config": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def can_import_service():
    try:
        from ndis_finance.services.governed_limited_operation_planning import quick_governed_limited_operation_planning_summary
        return callable(quick_governed_limited_operation_planning_summary)
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
