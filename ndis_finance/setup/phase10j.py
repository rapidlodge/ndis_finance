import json
import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


PHASE10J_DOCTYPES = [
    "NDIS Single Guarded Limited Operation Smoke",
    "NDIS Single Guarded Limited Operation Smoke Item",
]

REPORTS = [
    {
        "report_name": "NDIS Single Guarded Limited Operation Smoke Report",
        "ref_doctype": "NDIS Single Guarded Limited Operation Smoke",
    },
    {
        "report_name": "NDIS Single Guarded Limited Operation Smoke Item Report",
        "ref_doctype": "NDIS Single Guarded Limited Operation Smoke Item",
    },
    {
        "report_name": "NDIS Single Guarded Limited Operation Smoke Guardrail Report",
        "ref_doctype": "NDIS Single Guarded Limited Operation Smoke",
    },
]

REPORT_ROLES = [
    "System Manager",
    "NDIS CFO",
    "NDIS Finance Manager",
    "NDIS Finance Officer",
    "NDIS Finance Read Only",
]

DOC_PERM_MATRIX = {
    "NDIS Single Guarded Limited Operation Smoke": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Single Guarded Limited Operation Smoke Item": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
}

WORKSPACE_NAME = "NDIS Finance"

WORKSPACE_SHORTCUTS = [
    {"label": "Single Guarded Limited Operation Smokes", "type": "DocType", "link_to": "NDIS Single Guarded Limited Operation Smoke"},
    {"label": "Single Guarded Limited Operation Smoke Items", "type": "DocType", "link_to": "NDIS Single Guarded Limited Operation Smoke Item"},
    {"label": "Single Guarded Limited Operation Smoke Report", "type": "Report", "link_to": "NDIS Single Guarded Limited Operation Smoke Report"},
    {"label": "Single Guarded Limited Operation Smoke Item Report", "type": "Report", "link_to": "NDIS Single Guarded Limited Operation Smoke Item Report"},
    {"label": "Single Guarded Limited Operation Smoke Guardrails", "type": "Report", "link_to": "NDIS Single Guarded Limited Operation Smoke Guardrail Report"},
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_smoke_doctype()
    create_item_doctype()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Guarded Limited Operation Execution Gate",
        "NDIS Guarded Limited Operation Execution Gate Item",
        "NDIS Guarded Limited Operation Preview",
        "NDIS Controlled Limited Operation Pre Check",
        "NDIS Controlled Limited Operations Monitoring Register",
        "NDIS Controlled Production Batch Posting Policy",
        "Payment Entry",
        "GL Entry",
        "Sales Invoice",
        "Report",
        "Workspace",
    ]

    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]

    if missing:
        frappe.throw(
            _("Phase 10J requires completed Phase 10I execution gate. Missing: {0}").format(
                ", ".join(missing)
            )
        )


def create_smoke_doctype():
    _create_doctype(
        name="NDIS Single Guarded Limited Operation Smoke",
        autoname="field:smoke_id",
        title_field="smoke_id",
        fields=[
            {"fieldname": "smoke_id", "label": "Smoke ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nNeeds Review\nSmoke Completed - Rollback Required\nBlocked\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "smoke_status", "label": "Smoke Status", "fieldtype": "Select", "options": "\nSingle Guarded Limited Operation Smoke Completed\nNeeds Review\nBlocked\nCancelled", "read_only": 1, "in_list_view": 1},

            {"fieldname": "smoke_section", "label": "Smoke Execution", "fieldtype": "Section Break"},
            {"fieldname": "smoke_execution_completed", "label": "Smoke Execution Completed", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "rollback_required", "label": "Rollback Required", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "freeze_required_after_rollback", "label": "Freeze Required After Rollback", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "ready_for_single_operation_smoke_rollback", "label": "Ready For Single Operation Smoke Rollback", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "execution_gate_consumed", "label": "Execution Gate Consumed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "single_operation_only", "label": "Single Operation Only", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "policy_state_preserved_verified", "label": "Policy State Preserved Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "policy_mutation_performed", "label": "Policy Mutation Performed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "actual_policy_mutation_count", "label": "Actual Policy Mutation Count", "fieldtype": "Int", "read_only": 1},

            {"fieldname": "verification_section", "label": "Evidence Verification", "fieldtype": "Section Break"},
            {"fieldname": "phase10i_gate_verified", "label": "Phase 10I Gate Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "phase10h_preview_verified", "label": "Phase 10H Preview Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "phase10g_pre_check_verified", "label": "Phase 10G Pre Check Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "phase10f_register_verified", "label": "Phase 10F Register Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "controlled_policy_enabled_verified", "label": "Controlled Policy Enabled Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "live_posting_blocked_verified", "label": "Live Posting Blocked Verified", "fieldtype": "Check", "read_only": 1},

            {"fieldname": "chain_section", "label": "Evidence Chain", "fieldtype": "Section Break"},
            {"fieldname": "execution_gate", "label": "Phase 10I Execution Gate", "fieldtype": "Link", "options": "NDIS Guarded Limited Operation Execution Gate", "in_list_view": 1},
            {"fieldname": "preview", "label": "Phase 10H Preview", "fieldtype": "Link", "options": "NDIS Guarded Limited Operation Preview"},
            {"fieldname": "pre_check", "label": "Phase 10G Pre Check", "fieldtype": "Link", "options": "NDIS Controlled Limited Operation Pre Check"},
            {"fieldname": "monitoring_register", "label": "Phase 10F Monitoring Register", "fieldtype": "Link", "options": "NDIS Controlled Limited Operations Monitoring Register"},
            {"fieldname": "decision", "label": "Phase 10E Decision", "fieldtype": "Link", "options": "NDIS Guarded Adapter Final Policy Decision"},
            {"fieldname": "runtime_guard", "label": "Phase 9V Runtime Guard", "fieldtype": "Link", "options": "NDIS Limited Batch Runtime Guard"},

            {"fieldname": "policy_section", "label": "Policy Evidence", "fieldtype": "Section Break"},
            {"fieldname": "target_policy_doctype", "label": "Target Policy DocType", "fieldtype": "Link", "options": "DocType", "read_only": 1},
            {"fieldname": "target_policy", "label": "Target Policy", "fieldtype": "Dynamic Link", "options": "target_policy_doctype", "in_list_view": 1},
            {"fieldname": "target_policy_name", "label": "Target Policy Name", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "target_policy_enabled_before", "label": "Target Policy Enabled Before", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "target_policy_enabled_after", "label": "Target Policy Enabled After", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "target_policy_live_before", "label": "Target Policy Live Before", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "target_policy_live_after", "label": "Target Policy Live After", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "production_batch_enabled_policy_count_before", "label": "Enabled Policy Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "production_batch_enabled_policy_count_after", "label": "Enabled Policy Count After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "live_posting_allowed_policy_count_before", "label": "Live Policy Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "live_posting_allowed_policy_count_after", "label": "Live Policy Count After", "fieldtype": "Int", "read_only": 1},

            {"fieldname": "locked_shape_section", "label": "Locked Shape", "fieldtype": "Section Break"},
            {"fieldname": "locked_batch_line_count", "label": "Locked Batch Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "locked_batch_amount", "label": "Locked Batch Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "locked_payment_entry_count", "label": "Locked Payment Entry Count", "fieldtype": "Int", "read_only": 1},

            {"fieldname": "actual_shape_section", "label": "Actual Smoke Shape", "fieldtype": "Section Break"},
            {"fieldname": "payment_entry", "label": "Created Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "read_only": 1, "in_list_view": 1},
            {"fieldname": "payment_entry_docstatus", "label": "Payment Entry Docstatus", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_status", "label": "Payment Entry Status", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "payment_entry_amount", "label": "Payment Entry Amount", "fieldtype": "Currency", "read_only": 1, "in_list_view": 1},
            {"fieldname": "payment_entry_reference_count", "label": "Payment Entry Reference Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_row_count", "label": "Payment Entry GL Row Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_naming_series", "label": "Payment Entry Naming Series", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "payment_type", "label": "Payment Type", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "party_type", "label": "Party Type", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "party", "label": "Party", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company", "read_only": 1},

            {"fieldname": "movement_guardrail_section", "label": "Movement Guardrails", "fieldtype": "Section Break"},
            {"fieldname": "payment_entry_count_before", "label": "Payment Entry Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_count_after", "label": "Payment Entry Count After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_count_before", "label": "Payment Entry GL Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_count_after", "label": "Payment Entry GL Count After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "actual_payment_entry_created_count", "label": "Actual Payment Entry Created Count", "fieldtype": "Int", "read_only": 1},
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

            {"fieldname": "score_section", "label": "Smoke Score", "fieldtype": "Section Break"},
            {"fieldname": "smoke_score", "label": "Smoke Score", "fieldtype": "Percent", "read_only": 1},
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
            {"fieldname": "reference_json", "label": "Reference JSON", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
        ],
    )


def create_item_doctype():
    _create_doctype(
        name="NDIS Single Guarded Limited Operation Smoke Item",
        autoname="hash",
        title_field="check_label",
        fields=[
            {"fieldname": "smoke", "label": "Smoke", "fieldtype": "Link", "options": "NDIS Single Guarded Limited Operation Smoke", "reqd": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nPass\nWarning\nBlocker\nInfo\nCancelled", "default": "Info", "in_list_view": 1},
            {"fieldname": "severity", "label": "Severity", "fieldtype": "Select", "options": "\nLow\nMedium\nHigh\nCritical", "default": "Low", "in_list_view": 1},
            {"fieldname": "category", "label": "Category", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "check_key", "label": "Check Key", "fieldtype": "Data"},
            {"fieldname": "check_label", "label": "Check Label", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "detail", "label": "Detail", "fieldtype": "Small Text"},
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

    if existing:
        doc = frappe.get_doc("Report", existing)
    else:
        doc = frappe.new_doc("Report")
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

    if "Single Guarded Limited Operation Smoke" not in text_blob:
        content.append(
            {
                "id": "ndis_single_guarded_limited_operation_smoke_heading",
                "type": "header",
                "data": {"text": "Single Guarded Limited Operation Smoke", "col": 12},
            }
        )

    for shortcut in WORKSPACE_SHORTCUTS:
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            continue

        content.append(
            {
                "id": frappe.scrub(shortcut["label"]),
                "type": "shortcut",
                "data": {
                    "label": shortcut["label"],
                    "link_to": shortcut["link_to"],
                    "type": shortcut["type"],
                    "col": 3,
                },
            }
        )

    ws.content = json.dumps(content)


def add_shortcuts_to_child_table(ws):
    # Workspace content JSON is the stable representation for these phase links.
    return

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
            set_child_value(row, "type", shortcut["type"])
            set_child_value(row, "link_type", shortcut["type"])
            set_child_value(row, "open_in_new_tab", 0)


def set_child_value(row, fieldname, value):
    if row.meta.has_field(fieldname):
        setattr(row, fieldname, value)


@frappe.whitelist()
def health_check():
    doctypes = {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE10J_DOCTYPES}

    reports = {
        report["report_name"]: bool(frappe.db.exists("Report", report["report_name"]))
        for report in REPORTS
    }

    hooks = frappe.get_hooks()
    doctype_js = hooks.get("doctype_js", {})
    doctype_list_js = hooks.get("doctype_list_js", {})

    return {
        "doctypes": doctypes,
        "reports": reports,
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_single_guarded_limited_operation_smoke": permission_matrix().get("run_single_guarded_limited_operation_smoke"),
            "cancel_single_guarded_limited_operation_smoke_audit": permission_matrix().get("cancel_single_guarded_limited_operation_smoke_audit"),
        },
        "js_hooks": {
            "NDIS Single Guarded Limited Operation Smoke": "NDIS Single Guarded Limited Operation Smoke" in doctype_js,
            "NDIS Single Guarded Limited Operation Smoke Item": "NDIS Single Guarded Limited Operation Smoke Item" in doctype_js,
        },
        "list_js_hooks": {
            "NDIS Single Guarded Limited Operation Smoke": "NDIS Single Guarded Limited Operation Smoke" in doctype_list_js,
            "NDIS Single Guarded Limited Operation Smoke Item": "NDIS Single Guarded Limited Operation Smoke Item" in doctype_list_js,
        },
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_payment_entry_posting_config": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def can_import_service():
    try:
        from ndis_finance.services.single_guarded_limited_operation_smoke import quick_single_guarded_limited_operation_smoke_summary
        return callable(quick_single_guarded_limited_operation_smoke_summary)
    except Exception:
        return False


def check_workspace_shortcuts():
    ws_name = frappe.db.exists("Workspace", WORKSPACE_NAME) or frappe.db.exists("Workspace", {"label": WORKSPACE_NAME})
    result = {shortcut["label"]: False for shortcut in WORKSPACE_SHORTCUTS}

    if not ws_name:
        return result

    ws = frappe.get_doc("Workspace", ws_name)

    text_blob = ""
    if getattr(ws, "content", None):
        text_blob += ws.content

    for fieldname in ["shortcuts", "links"]:
        if ws.meta.has_field(fieldname):
            for row in getattr(ws, fieldname, []) or []:
                text_blob += " " + str(getattr(row, "label", "")) + " " + str(getattr(row, "link_to", ""))

    for shortcut in WORKSPACE_SHORTCUTS:
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            result[shortcut["label"]] = True

    return result
