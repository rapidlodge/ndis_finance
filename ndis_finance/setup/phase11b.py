import json

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


MONITOR_DOCTYPE = "NDIS Governed Steady State Monitor"
MONITOR_ITEM_DOCTYPE = "NDIS Governed Steady State Monitor Item"
PHASE11B_DOCTYPES = [MONITOR_DOCTYPE, MONITOR_ITEM_DOCTYPE]

REPORTS = [
    {"report_name": "NDIS Governed Steady State Monitor Report", "ref_doctype": MONITOR_DOCTYPE},
    {"report_name": "NDIS Governed Steady State Monitor Item Report", "ref_doctype": MONITOR_ITEM_DOCTYPE},
    {"report_name": "NDIS Governed Steady State Monitor Guardrail Report", "ref_doctype": MONITOR_DOCTYPE},
]

REPORT_ROLES = ["System Manager", "NDIS CFO", "NDIS Finance Manager", "NDIS Finance Officer", "NDIS Finance Read Only"]
DOC_PERM_MATRIX = {
    MONITOR_DOCTYPE: {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
    MONITOR_ITEM_DOCTYPE: {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
}

WORKSPACE_NAME = "NDIS Finance"
WORKSPACE_SHORTCUTS = [
    {"label": "Governed Steady-State Monitors", "type": "DocType", "link_to": MONITOR_DOCTYPE},
    {"label": "Governed Steady-State Monitor Items", "type": "DocType", "link_to": MONITOR_ITEM_DOCTYPE},
    {"label": "Governed Steady-State Monitor Report", "type": "Report", "link_to": "NDIS Governed Steady State Monitor Report"},
    {"label": "Governed Steady-State Monitor Item Report", "type": "Report", "link_to": "NDIS Governed Steady State Monitor Item Report"},
    {"label": "Governed Steady-State Monitor Guardrails", "type": "Report", "link_to": "NDIS Governed Steady State Monitor Guardrail Report"},
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_monitor_doctype()
    create_item_doctype()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Governed Steady State Baseline",
        "NDIS Governed Steady State Baseline Item",
        "NDIS Governed Limited Op Closeout",
        "NDIS Governed Limited Op Freeze",
        "NDIS Governed Limited Op Rollback",
        "NDIS Governed Limited Op Smoke",
        "NDIS Controlled Production Batch Posting Policy",
        "Payment Entry",
        "Payment Entry Reference",
        "GL Entry",
        "Report",
        "Workspace",
    ]
    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]
    if missing:
        frappe.throw(_("Phase 11B requires completed Phase 11A baseline. Missing: {0}").format(", ".join(missing)))


def check_fields(names):
    return [{"fieldname": fieldname, "label": label, "fieldtype": "Check", "read_only": 1, **opts} for fieldname, label, opts in names]


def int_fields(names):
    return [{"fieldname": fieldname, "label": label, "fieldtype": "Int", "read_only": 1, **opts} for fieldname, label, opts in names]


def link_field(fieldname, label, options, **opts):
    return {"fieldname": fieldname, "label": label, "fieldtype": "Link", "options": options, **opts}


def create_monitor_doctype():
    _create_doctype(
        name=MONITOR_DOCTYPE,
        autoname="field:monitor_id",
        title_field="monitor_id",
        fields=[
            {"fieldname": "monitor_id", "label": "Monitor ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nNeeds Review\nMonitor Active\nBlocked\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "monitor_status", "label": "Monitor Status", "fieldtype": "Select", "options": "\nGoverned Steady-State Runtime Monitor Active\nNeeds Review\nBlocked\nCancelled", "read_only": 1, "in_list_view": 1},
            {"fieldname": "result_section", "label": "Monitor Result", "fieldtype": "Section Break"},
            *check_fields(
                [
                    ("monitor_active", "Monitor Active", {"in_list_view": 1}),
                    ("runtime_monitor_enabled", "Runtime Monitor Enabled", {}),
                    ("guardrail_watch_active", "Guardrail Watch Active", {}),
                    ("governed_steady_state_monitoring_ready", "Governed Steady-State Monitoring Ready", {}),
                    ("ready_for_next_governed_limited_operation_precheck", "Ready For Next Governed Limited Operation Precheck", {}),
                    ("phase11a_baseline_verified", "Phase 11A Baseline Verified", {}),
                    ("phase10z_closeout_verified", "Phase 10Z Closeout Verified", {}),
                    ("governed_limited_operation_cycle_closed_verified", "Governed Limited Operation Cycle Closed Verified", {}),
                    ("payment_entry_cancelled_verified", "Payment Entry Cancelled Verified", {}),
                    ("gl_net_zero_verified", "GL Net Zero Verified", {}),
                    ("invoice_outstanding_restored_verified", "Invoice Outstanding Restored Verified", {}),
                    ("no_new_accounting_movement_verified", "No New Accounting Movement Verified", {}),
                    ("policy_state_preserved_verified", "Policy State Preserved Verified", {}),
                    ("policy_mutation_performed", "Policy Mutation Performed", {}),
                ]
            ),
            {"fieldname": "actual_policy_mutation_count", "label": "Actual Policy Mutation Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "phase_section", "label": "Phase Verification", "fieldtype": "Section Break"},
            *check_fields(
                [
                    ("phase10y_freeze_verified", "Phase 10Y Freeze Verified", {}),
                    ("phase10x_rollback_verified", "Phase 10X Rollback Verified", {}),
                    ("phase10w_smoke_verified", "Phase 10W Smoke Verified", {}),
                    ("phase10v_execution_gate_verified", "Phase 10V Execution Gate Verified", {}),
                    ("phase10u_preview_verified", "Phase 10U Preview Verified", {}),
                    ("phase10t_pre_execution_verified", "Phase 10T Pre-Execution Verified", {}),
                    ("phase10s_readiness_verified", "Phase 10S Readiness Verified", {}),
                    ("phase10r_governance_closeout_verified", "Phase 10R Governance Closeout Verified", {}),
                    ("phase10q_freeze_verified", "Phase 10Q Freeze Verified", {}),
                    ("phase10p_simulation_verified", "Phase 10P Simulation Verified", {}),
                    ("phase10o_runtime_watch_verified", "Phase 10O Runtime Watch Verified", {}),
                    ("phase10n_baseline_verified", "Phase 10N Baseline Verified", {}),
                    ("controlled_policy_enabled_verified", "Controlled Policy Enabled Verified", {}),
                    ("live_posting_blocked_verified", "Live Posting Blocked Verified", {}),
                ]
            ),
            {"fieldname": "chain_section", "label": "Evidence Chain", "fieldtype": "Section Break"},
            link_field("baseline", "Phase 11A Baseline", "NDIS Governed Steady State Baseline", in_list_view=1),
            link_field("closeout", "Phase 10Z Closeout", "NDIS Governed Limited Op Closeout"),
            link_field("governed_freeze", "Phase 10Y Freeze", "NDIS Governed Limited Op Freeze"),
            link_field("rollback", "Phase 10X Rollback", "NDIS Governed Limited Op Rollback"),
            link_field("smoke", "Phase 10W Smoke", "NDIS Governed Limited Op Smoke"),
            link_field("execution_gate", "Phase 10V Execution Gate", "NDIS Governed Limited Op Exec Gate"),
            link_field("preview", "Phase 10U Preview", "NDIS Governed Limited Op Preview"),
            link_field("pre_execution_gate", "Phase 10T Pre-Execution Gate", "NDIS Governed Limited Op Pre Exec"),
            link_field("readiness", "Phase 10S Readiness", "NDIS Governed Limited Ops Readiness"),
            link_field("governance_closeout", "Phase 10R Governance Closeout", "NDIS Runtime Watch Governance Closeout"),
            link_field("runtime_watch", "Phase 10O Runtime Watch", "NDIS Controlled Limited Ops Runtime Watch"),
            link_field("prior_baseline", "Phase 10N Baseline", "NDIS Controlled Limited Ops Baseline"),
            link_field("monitoring_register", "Phase 10F Monitoring Register", "NDIS Controlled Limited Operations Monitoring Register"),
            {"fieldname": "policy_section", "label": "Policy Evidence", "fieldtype": "Section Break"},
            link_field("target_policy_doctype", "Target Policy DocType", "DocType", read_only=1),
            {"fieldname": "target_policy", "label": "Target Policy", "fieldtype": "Dynamic Link", "options": "target_policy_doctype"},
            {"fieldname": "target_policy_name", "label": "Target Policy Name", "fieldtype": "Data", "read_only": 1},
            *check_fields(
                [
                    ("target_policy_enabled_before", "Target Policy Enabled Before", {}),
                    ("target_policy_enabled_after", "Target Policy Enabled After", {}),
                    ("target_policy_live_before", "Target Policy Live Before", {}),
                    ("target_policy_live_after", "Target Policy Live After", {}),
                ]
            ),
            *int_fields(
                [
                    ("production_batch_enabled_policy_count_before", "Enabled Policy Count Before", {}),
                    ("production_batch_enabled_policy_count_after", "Enabled Policy Count After", {}),
                    ("live_posting_allowed_policy_count_before", "Live Policy Count Before", {}),
                    ("live_posting_allowed_policy_count_after", "Live Policy Count After", {}),
                ]
            ),
            {"fieldname": "baseline_lock_section", "label": "Baseline Lock", "fieldtype": "Section Break"},
            *int_fields(
                [
                    ("locked_payment_entry_count", "Locked Payment Entry Count", {}),
                    ("locked_payment_entry_gl_count", "Locked Payment Entry GL Count", {}),
                    ("locked_policy_enabled_count", "Locked Policy Enabled Count", {}),
                    ("locked_policy_live_allowed_count", "Locked Policy Live Allowed Count", {}),
                ]
            ),
            *check_fields(
                [
                    ("locked_live_posting", "Locked Live Posting", {}),
                    ("locked_journal_entry_side_effect", "Locked Journal Entry Side Effect", {}),
                    ("locked_purchase_invoice_side_effect", "Locked Purchase Invoice Side Effect", {}),
                ]
            ),
            {"fieldname": "payment_entry_section", "label": "Monitored Payment Entry Evidence", "fieldtype": "Section Break"},
            link_field("payment_entry", "Payment Entry", "Payment Entry", read_only=1, in_list_view=1),
            {"fieldname": "payment_entry_docstatus", "label": "Payment Entry Docstatus", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_status", "label": "Payment Entry Status", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "payment_entry_amount", "label": "Payment Entry Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "payment_entry_reference_count", "label": "Payment Entry Reference Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "invoice_outstanding_restored_amount", "label": "Invoice Outstanding Restored Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "voucher_gl_row_count", "label": "Voucher GL Row Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "voucher_gl_net_balance", "label": "Voucher GL Net Balance", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "gl_account_non_zero_count", "label": "GL Account Non Zero Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "movement_section", "label": "Movement Guardrails", "fieldtype": "Section Break"},
            *int_fields(
                [
                    ("payment_entry_count_before", "Payment Entry Count Before", {}),
                    ("payment_entry_count_after", "Payment Entry Count After", {}),
                    ("payment_entry_gl_count_before", "Payment Entry GL Count Before", {}),
                    ("payment_entry_gl_count_after", "Payment Entry GL Count After", {}),
                    ("actual_payment_entry_created_count", "Actual Payment Entry Created Count", {}),
                    ("actual_payment_entry_cancelled_count", "Actual Payment Entry Cancelled Count", {}),
                    ("actual_gl_created_count", "Actual GL Created Count", {}),
                    ("submitted_journal_entry_count_today", "Submitted JE Count Today", {}),
                    ("purchase_invoice_count_today", "Purchase Invoice Count Today", {}),
                ]
            ),
            {"fieldname": "site_section", "label": "Site / Config", "fieldtype": "Section Break"},
            {"fieldname": "site_name", "label": "Site Name", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "sandbox_config_enabled", "label": "Sandbox Config Enabled", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "production_mode_detected", "label": "Production Mode Detected", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "live_payment_entry_posting_config", "label": "Live PE Posting Config", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "checked_on", "label": "Checked On", "fieldtype": "Datetime", "read_only": 1, "in_list_view": 1},
            link_field("checked_by", "Checked By", "User", read_only=1),
            {"fieldname": "score_section", "label": "Monitor Score", "fieldtype": "Section Break"},
            {"fieldname": "monitor_score", "label": "Monitor Score", "fieldtype": "Percent", "read_only": 1},
            *int_fields([("blocker_count", "Blocker Count", {}), ("warning_count", "Warning Count", {}), ("pass_count", "Pass Count", {}), ("info_count", "Info Count", {}), ("item_count", "Item Count", {})]),
            {"fieldname": "ack_section", "label": "Acknowledgement", "fieldtype": "Section Break"},
            {"fieldname": "required_acknowledgement", "label": "Required Acknowledgement", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "acknowledgement", "label": "Acknowledgement", "fieldtype": "Data"},
            {"fieldname": "acknowledgement_ok", "label": "Acknowledgement OK", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "audit_section", "label": "Audit", "fieldtype": "Section Break"},
            {"fieldname": "cancelled_on", "label": "Cancelled On", "fieldtype": "Datetime", "read_only": 1},
            link_field("cancelled_by", "Cancelled By", "User", read_only=1),
            {"fieldname": "summary_json", "label": "Summary JSON", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "monitor_json", "label": "Monitor JSON", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
        ],
    )


def create_item_doctype():
    _create_doctype(
        name=MONITOR_ITEM_DOCTYPE,
        autoname="hash",
        title_field="check_label",
        fields=[
            link_field("monitor", "Monitor", MONITOR_DOCTYPE, reqd=1, in_list_view=1),
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nPass\nWarning\nBlocker\nInfo\nCancelled", "default": "Info", "in_list_view": 1},
            {"fieldname": "severity", "label": "Severity", "fieldtype": "Select", "options": "\nLow\nMedium\nHigh\nCritical", "default": "Low", "in_list_view": 1},
            {"fieldname": "category", "label": "Category", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "check_key", "label": "Check Key", "fieldtype": "Data"},
            {"fieldname": "check_label", "label": "Check Label", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "detail", "label": "Detail", "fieldtype": "Small Text"},
            link_field("source_doctype", "Source DocType", "DocType"),
            {"fieldname": "source_name", "label": "Source Name", "fieldtype": "Dynamic Link", "options": "source_doctype"},
            {"fieldname": "checked_on", "label": "Checked On", "fieldtype": "Datetime", "read_only": 1},
        ],
    )


def create_reports():
    for report in REPORTS:
        ensure_script_report(report["report_name"], report["ref_doctype"])


def ensure_script_report(report_name, ref_doctype):
    doc = frappe.get_doc("Report", report_name) if frappe.db.exists("Report", report_name) else frappe.new_doc("Report")
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
        "role": role,
        "permlevel": 0,
        "read": 0,
        "write": 0,
        "create": 0,
        "delete": 0,
        "submit": 0,
        "cancel": 0,
        "amend": 0,
        "report": 0,
        "export": 0,
        "import": 0,
        "share": 0,
        "print": 0,
        "email": 0,
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
    if "Governed Steady-State Runtime Monitor" not in text_blob:
        content.append({"id": "ndis_governed_steady_state_monitor_heading", "type": "header", "data": {"text": "Governed Steady-State Runtime Monitor", "col": 12}})
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
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE11B_DOCTYPES},
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_governed_steady_state_monitor": permission_matrix().get("run_governed_steady_state_monitor"),
            "cancel_governed_steady_state_monitor_audit": permission_matrix().get("cancel_governed_steady_state_monitor_audit"),
        },
        "js_hooks": {MONITOR_DOCTYPE: MONITOR_DOCTYPE in doctype_js, MONITOR_ITEM_DOCTYPE: MONITOR_ITEM_DOCTYPE in doctype_js},
        "list_js_hooks": {MONITOR_DOCTYPE: MONITOR_DOCTYPE in doctype_list_js, MONITOR_ITEM_DOCTYPE: MONITOR_ITEM_DOCTYPE in doctype_list_js},
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_payment_entry_posting_config": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def can_import_service():
    try:
        from ndis_finance.services.governed_steady_state_monitor import quick_governed_steady_state_monitor_summary

        return callable(quick_governed_steady_state_monitor_summary)
    except Exception:
        return False


def check_workspace_shortcuts():
    ws_name = frappe.db.exists("Workspace", WORKSPACE_NAME) or frappe.db.exists("Workspace", {"label": WORKSPACE_NAME})
    result = {shortcut["label"]: False for shortcut in WORKSPACE_SHORTCUTS}
    if not ws_name:
        return result
    ws = frappe.get_doc("Workspace", ws_name)
    text_blob = getattr(ws, "content", None) or ""
    for fieldname in ["shortcuts", "links"]:
        if ws.meta.has_field(fieldname):
            for row in getattr(ws, fieldname, []) or []:
                text_blob += " " + str(getattr(row, "label", "")) + " " + str(getattr(row, "link_to", ""))
    for shortcut in WORKSPACE_SHORTCUTS:
        result[shortcut["label"]] = shortcut["label"] in text_blob or shortcut["link_to"] in text_blob
    return result
