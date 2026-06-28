import json
import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


BASELINE_DOCTYPE = "NDIS Next Post Closeout Steady Baseline"
BASELINE_ITEM_DOCTYPE = "NDIS Next Post Closeout Steady Baseline Item"

PHASE11Z_DOCTYPES = [
    BASELINE_DOCTYPE,
    BASELINE_ITEM_DOCTYPE,
]

REPORTS = [
    {"report_name": "NDIS Next Post Closeout Steady Baseline Report", "ref_doctype": BASELINE_DOCTYPE},
    {"report_name": "NDIS Next Post Closeout Steady Baseline Item Report", "ref_doctype": BASELINE_ITEM_DOCTYPE},
    {"report_name": "NDIS Next Post Closeout Steady Baseline Guardrail Report", "ref_doctype": BASELINE_DOCTYPE},
]

REPORT_ROLES = [
    "System Manager",
    "NDIS CFO",
    "NDIS Finance Manager",
    "NDIS Finance Officer",
    "NDIS Finance Read Only",
]

DOC_PERM_MATRIX = {
    BASELINE_DOCTYPE: {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
    BASELINE_ITEM_DOCTYPE: {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
}

WORKSPACE_NAME = "NDIS Finance"

WORKSPACE_SHORTCUTS = [
    {"label": "Next Post Closeout Baselines", "type": "DocType", "link_to": BASELINE_DOCTYPE},
    {"label": "Next Post Closeout Baseline Items", "type": "DocType", "link_to": BASELINE_ITEM_DOCTYPE},
    {"label": "Next Post Closeout Baseline Report", "type": "Report", "link_to": "NDIS Next Post Closeout Steady Baseline Report"},
    {"label": "Next Post Closeout Baseline Item Report", "type": "Report", "link_to": "NDIS Next Post Closeout Steady Baseline Item Report"},
    {"label": "Next Post Closeout Baseline Guardrails", "type": "Report", "link_to": "NDIS Next Post Closeout Steady Baseline Guardrail Report"},
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_baseline_doctype()
    create_item_doctype()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Next Controlled Cycle Closeout",
        "NDIS Next Controlled Cycle Closeout Item",
        "NDIS Next Controlled Cycle Rollback Freeze",
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
            _("Phase 11Z requires completed Phase 11Y closeout. Missing: {0}").format(
                ", ".join(missing)
            )
        )


def create_baseline_doctype():
    _create_doctype(
        name=BASELINE_DOCTYPE,
        autoname="field:baseline_id",
        title_field="baseline_id",
        fields=[
            {"fieldname": "baseline_id", "label": "Baseline ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nNeeds Review\nBaseline Active\nBlocked\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "baseline_status", "label": "Baseline Status", "fieldtype": "Select", "options": "\nNext Post-Closeout Steady-State Baseline Active\nNeeds Review\nBlocked\nCancelled", "read_only": 1, "in_list_view": 1},

            {"fieldname": "result_section", "label": "Baseline Result", "fieldtype": "Section Break"},
            {"fieldname": "baseline_active", "label": "Baseline Active", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "phase11y_closeout_verified", "label": "Phase 11Y Closeout Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "closeout_approved_verified", "label": "Closeout Approved Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "cycle_closed_verified", "label": "Cycle Closed Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "steady_state_ready_verified", "label": "Steady State Ready Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "closed_payment_entry_verified", "label": "Closed Payment Entry Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "payment_entry_cancelled_still_verified", "label": "Payment Entry Cancelled Still Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "voucher_gl_rows_verified", "label": "Voucher GL Rows Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "voucher_gl_net_zero_verified", "label": "Voucher GL Net Zero Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "invoice_outstanding_restored_still_verified", "label": "Invoice Outstanding Restored Still Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "no_new_accounting_movement_verified", "label": "No New Accounting Movement Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "policy_state_preserved_verified", "label": "Policy State Preserved Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "ready_for_next_post_closeout_monitoring", "label": "Ready For Next Post-Closeout Monitoring", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "policy_mutation_performed", "label": "Policy Mutation Performed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "actual_policy_mutation_count", "label": "Actual Policy Mutation Count", "fieldtype": "Int", "read_only": 1},

            {"fieldname": "baseline_section", "label": "Baseline Payment Entry Evidence", "fieldtype": "Section Break"},
            {"fieldname": "baseline_payment_entry", "label": "Baseline Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "read_only": 1, "in_list_view": 1},
            {"fieldname": "payment_entry_docstatus_baseline", "label": "PE Docstatus Baseline", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_status_baseline", "label": "PE Status Baseline", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "baseline_reference_count", "label": "Baseline Reference Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "baseline_total_amount", "label": "Baseline Total Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "baseline_voucher_gl_rows", "label": "Baseline Voucher GL Rows", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "baseline_voucher_gl_net", "label": "Baseline Voucher GL Net", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "baseline_voucher_gl_non_zero_account_count", "label": "Baseline Voucher GL Non-Zero Account Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "baseline_restored_invoice_amount", "label": "Baseline Restored Invoice Amount", "fieldtype": "Currency", "read_only": 1},

            {"fieldname": "chain_section", "label": "Evidence Chain", "fieldtype": "Section Break"},
            {"fieldname": "closeout", "label": "Phase 11Y Closeout", "fieldtype": "Link", "options": "NDIS Next Controlled Cycle Closeout", "in_list_view": 1},
            {"fieldname": "freeze", "label": "Phase 11X Freeze", "fieldtype": "Link", "options": "NDIS Next Controlled Cycle Rollback Freeze"},
            {"fieldname": "rollback", "label": "Phase 11W Rollback", "fieldtype": "Link", "options": "NDIS Next Controlled Cycle Rollback"},
            {"fieldname": "smoke", "label": "Phase 11V Smoke", "fieldtype": "Link", "options": "NDIS Next Controlled Cycle Smoke"},
            {"fieldname": "execution_gate", "label": "Phase 11U Execution Gate", "fieldtype": "Link", "options": "NDIS Next Controlled Cycle Exec Gate"},
            {"fieldname": "preview", "label": "Phase 11T Preview", "fieldtype": "Link", "options": "NDIS Next Controlled Cycle Preview"},
            {"fieldname": "validation", "label": "Phase 11S Validation", "fieldtype": "Link", "options": "NDIS Next Controlled Cycle Cand Valid"},
            {"fieldname": "candidate", "label": "Phase 11R Candidate", "fieldtype": "Link", "options": "NDIS Next Controlled Cycle Candidate"},
            {"fieldname": "design", "label": "Phase 11Q Design", "fieldtype": "Link", "options": "NDIS Next Controlled Cycle Design"},
            {"fieldname": "planning", "label": "Phase 11P Planning", "fieldtype": "Link", "options": "NDIS Next Controlled Cycle Planning"},
            {"fieldname": "monitor", "label": "Phase 11O Monitor", "fieldtype": "Link", "options": "NDIS Post Closeout Runtime Monitor"},
            {"fieldname": "previous_baseline", "label": "Previous Baseline", "fieldtype": "Link", "options": "NDIS Post Closeout Steady Baseline"},

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

            {"fieldname": "score_section", "label": "Baseline Score", "fieldtype": "Section Break"},
            {"fieldname": "baseline_score", "label": "Baseline Score", "fieldtype": "Percent", "read_only": 1},
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
            {"fieldname": "baseline_json", "label": "Baseline JSON", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
        ],
    )


def create_item_doctype():
    _create_doctype(
        name=BASELINE_ITEM_DOCTYPE,
        autoname="hash",
        title_field="check_label",
        fields=[
            {"fieldname": "baseline", "label": "Baseline", "fieldtype": "Link", "options": BASELINE_DOCTYPE, "reqd": 1, "in_list_view": 1},
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
            {"fieldname": "baseline_payment_entry", "label": "Baseline Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "read_only": 1},
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
    if "Next Post Closeout Baseline" not in text_blob:
        content.append({"id": "next_post_closeout_baseline_heading", "type": "header", "data": {"text": "Next Post Closeout Baseline", "col": 12}})

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
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE11Z_DOCTYPES},
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_next_post_closeout_steady_baseline": permission_matrix().get("run_next_post_closeout_steady_baseline"),
            "cancel_next_post_closeout_steady_baseline_audit": permission_matrix().get("cancel_next_post_closeout_steady_baseline_audit"),
        },
        "js_hooks": {
            BASELINE_DOCTYPE: BASELINE_DOCTYPE in doctype_js,
            BASELINE_ITEM_DOCTYPE: BASELINE_ITEM_DOCTYPE in doctype_js,
        },
        "list_js_hooks": {
            BASELINE_DOCTYPE: BASELINE_DOCTYPE in doctype_list_js,
            BASELINE_ITEM_DOCTYPE: BASELINE_ITEM_DOCTYPE in doctype_list_js,
        },
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_payment_entry_posting_config": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def can_import_service():
    try:
        from ndis_finance.services.next_post_closeout_steady_baseline import quick_next_post_closeout_steady_baseline_summary
        return callable(quick_next_post_closeout_steady_baseline_summary)
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
