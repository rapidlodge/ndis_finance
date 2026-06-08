import json
import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


PHASE9N_DOCTYPES = [
    "NDIS Limited Production Batch Enablement Activation Gate",
    "NDIS Limited Production Batch Enablement Activation Gate Item",
]

REPORTS = [
    {
        "report_name": "NDIS Limited Production Batch Enablement Activation Gate Report",
        "ref_doctype": "NDIS Limited Production Batch Enablement Activation Gate",
    },
    {
        "report_name": "NDIS Limited Production Batch Enablement Activation Gate Item Report",
        "ref_doctype": "NDIS Limited Production Batch Enablement Activation Gate Item",
    },
    {
        "report_name": "NDIS Limited Production Batch Enablement Activation Gate Guardrail Report",
        "ref_doctype": "NDIS Limited Production Batch Enablement Activation Gate",
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
    "NDIS Limited Production Batch Enablement Activation Gate": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Limited Production Batch Enablement Activation Gate Item": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
}

WORKSPACE_NAME = "NDIS Finance"

WORKSPACE_SHORTCUTS = [
    {
        "label": "Limited Production Batch Enablement Activation Gates",
        "type": "DocType",
        "link_to": "NDIS Limited Production Batch Enablement Activation Gate",
    },
    {
        "label": "Limited Production Batch Enablement Activation Gate Items",
        "type": "DocType",
        "link_to": "NDIS Limited Production Batch Enablement Activation Gate Item",
    },
    {
        "label": "Limited Production Batch Enablement Activation Gate Report",
        "type": "Report",
        "link_to": "NDIS Limited Production Batch Enablement Activation Gate Report",
    },
    {
        "label": "Limited Production Batch Enablement Activation Gate Item Report",
        "type": "Report",
        "link_to": "NDIS Limited Production Batch Enablement Activation Gate Item Report",
    },
    {
        "label": "Limited Production Batch Enablement Activation Gate Guardrails",
        "type": "Report",
        "link_to": "NDIS Limited Production Batch Enablement Activation Gate Guardrail Report",
    },
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_gate_doctype()
    create_gate_item_doctype()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Limited Production Batch Enablement Adapter Run",
        "NDIS Limited Production Batch Enablement Adapter Line",
        "NDIS Limited Production Batch Enablement Preview",
        "NDIS Limited Production Batch Enablement Design Gate",
        "NDIS Limited Production Batch Policy Lock",
        "NDIS Limited Production Batch Policy Finalisation Gate",
        "NDIS Limited Production Batch Smoke Evidence Freeze",
        "NDIS Limited Production Batch Smoke Rollback Run",
        "Payment Entry",
        "GL Entry",
        "Sales Invoice",
        "Report",
        "Workspace",
    ]

    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]

    if missing:
        frappe.throw(
            _("Phase 9N requires completed Phase 9M hard-block adapter. Missing: {0}").format(
                ", ".join(missing)
            )
        )


def create_gate_doctype():
    _create_doctype(
        name="NDIS Limited Production Batch Enablement Activation Gate",
        autoname="field:activation_gate_id",
        title_field="activation_gate_id",
        fields=[
            {"fieldname": "activation_gate_id", "label": "Activation Gate ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nSource Pending\nNeeds Review\nActivation Allowed\nBlocked\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "activation_status", "label": "Activation Status", "fieldtype": "Select", "options": "\nReady For Limited Controlled Enablement Smoke\nNeeds Review\nBlocked\nCancelled", "read_only": 1, "in_list_view": 1},

            {"fieldname": "decision_section", "label": "Activation Decision", "fieldtype": "Section Break"},
            {"fieldname": "limited_enablement_activation_allowed", "label": "Limited Enablement Activation Allowed", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "ready_for_limited_enablement_smoke", "label": "Ready For Limited Enablement Smoke", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "phase9m_adapter_verified", "label": "Phase 9M Adapter Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "phase9l_preview_verified", "label": "Phase 9L Preview Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "phase9k_enablement_design_verified", "label": "Phase 9K Enablement Design Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "phase9j_policy_lock_verified", "label": "Phase 9J Policy Lock Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "policy_caps_verified", "label": "Policy Caps Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "direct_enablement_blocked", "label": "Direct Enablement Blocked", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "hard_block_verified", "label": "Hard Block Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "production_batch_posting_allowed", "label": "Production Batch Posting Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "real_posting_allowed", "label": "Real Posting Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "policy_live_enabled", "label": "Policy Live Enabled", "fieldtype": "Check", "read_only": 1},

            {"fieldname": "chain_section", "label": "Evidence Chain", "fieldtype": "Section Break"},
            {"fieldname": "enablement_adapter", "label": "Phase 9M Enablement Adapter", "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Adapter Run", "in_list_view": 1},
            {"fieldname": "enablement_preview", "label": "Phase 9L Enablement Preview", "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Preview"},
            {"fieldname": "enablement_gate", "label": "Phase 9K Enablement Design Gate", "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Design Gate"},
            {"fieldname": "policy_lock", "label": "Phase 9J Policy Lock", "fieldtype": "Link", "options": "NDIS Limited Production Batch Policy Lock"},
            {"fieldname": "finalisation_gate", "label": "Phase 9I Finalisation Gate", "fieldtype": "Link", "options": "NDIS Limited Production Batch Policy Finalisation Gate"},
            {"fieldname": "phase9h_freeze", "label": "Phase 9H Evidence Freeze", "fieldtype": "Link", "options": "NDIS Limited Production Batch Smoke Evidence Freeze"},
            {"fieldname": "rollback_run", "label": "Phase 9G Rollback Run", "fieldtype": "Link", "options": "NDIS Limited Production Batch Smoke Rollback Run"},
            {"fieldname": "smoke_run", "label": "Phase 9F Smoke Run", "fieldtype": "Link", "options": "NDIS Limited Production Batch Smoke Run"},
            {"fieldname": "phase8g_freeze", "label": "Phase 8G Evidence Freeze", "fieldtype": "Link", "options": "NDIS Controlled Production Batch Smoke Evidence Freeze"},

            {"fieldname": "accounting_evidence_section", "label": "Accounting Evidence", "fieldtype": "Section Break"},
            {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company", "in_list_view": 1},
            {"fieldname": "customer", "label": "Customer", "fieldtype": "Link", "options": "Customer"},
            {"fieldname": "payment_entry", "label": "Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "in_list_view": 1},
            {"fieldname": "payment_entry_docstatus_after_rollback", "label": "Payment Entry Docstatus After Rollback", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_amount", "label": "Payment Entry Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "reference_count", "label": "Reference Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "invoice_outstanding_after_rollback_total", "label": "Invoice Outstanding After Rollback Total", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "payment_entry_gl_count_after_rollback", "label": "PE GL Count After Rollback", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_net_after_rollback", "label": "PE GL Net After Rollback", "fieldtype": "Currency", "read_only": 1},

            {"fieldname": "locked_policy_caps_section", "label": "Locked Policy Caps", "fieldtype": "Section Break"},
            {"fieldname": "max_batch_lines", "label": "Max Batch Lines", "fieldtype": "Int", "read_only": 1, "in_list_view": 1},
            {"fieldname": "max_batch_amount", "label": "Max Batch Amount", "fieldtype": "Currency", "read_only": 1, "in_list_view": 1},
            {"fieldname": "max_payment_entry_count", "label": "Max Payment Entry Count", "fieldtype": "Int", "read_only": 1, "in_list_view": 1},
            {"fieldname": "allowed_payment_type", "label": "Allowed Payment Type", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "allowed_reference_doctype", "label": "Allowed Reference Doctype", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "locked_policy_mode", "label": "Locked Policy Mode", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "approved_next_step", "label": "Approved Next Step", "fieldtype": "Data", "read_only": 1},

            {"fieldname": "activation_evidence_section", "label": "Activation Evidence", "fieldtype": "Section Break"},
            {"fieldname": "would_enable_policy_count", "label": "Would Enable Policy Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "hard_blocked_policy_count", "label": "Hard Blocked Policy Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "actual_enabled_policy_count", "label": "Actual Enabled Policy Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "would_enable_policy_name", "label": "Would Enable Policy Name", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "activation_gate_reason", "label": "Activation Gate Reason", "fieldtype": "Small Text", "read_only": 1},
            {"fieldname": "activation_next_step", "label": "Activation Next Step", "fieldtype": "Data", "read_only": 1},

            {"fieldname": "movement_guardrail_section", "label": "Movement Guardrails", "fieldtype": "Section Break"},
            {"fieldname": "actual_payment_entry_created_count", "label": "Actual Payment Entry Created Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "actual_gl_created_count", "label": "Actual GL Created Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_count_before", "label": "Payment Entry Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_count_after", "label": "Payment Entry Count After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_count_before", "label": "Payment Entry GL Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_count_after", "label": "Payment Entry GL Count After", "fieldtype": "Int", "read_only": 1},

            {"fieldname": "policy_guardrail_section", "label": "Policy Guardrails", "fieldtype": "Section Break"},
            {"fieldname": "submitted_phase9f_smoke_pe_count", "label": "Submitted Phase 9F Smoke PE", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "cancelled_phase9f_smoke_pe_count", "label": "Cancelled Phase 9F Smoke PE", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "submitted_journal_entry_count_today", "label": "Submitted JE Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "purchase_invoice_count_today", "label": "Purchase Invoice Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "production_batch_enabled_policy_count", "label": "Production Batch Enabled Policy Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "live_posting_allowed_policy_count", "label": "Live Posting Allowed Policy Count", "fieldtype": "Int", "read_only": 1},

            {"fieldname": "site_section", "label": "Site / Config", "fieldtype": "Section Break"},
            {"fieldname": "site_name", "label": "Site Name", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "sandbox_config_enabled", "label": "Sandbox Config Enabled", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "production_mode_detected", "label": "Production Mode Detected", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "live_payment_entry_posting_config", "label": "Live PE Posting Config", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "checked_on", "label": "Checked On", "fieldtype": "Datetime", "read_only": 1, "in_list_view": 1},
            {"fieldname": "checked_by", "label": "Checked By", "fieldtype": "Link", "options": "User", "read_only": 1},

            {"fieldname": "score_section", "label": "Activation Score", "fieldtype": "Section Break"},
            {"fieldname": "activation_score", "label": "Activation Score", "fieldtype": "Percent", "read_only": 1},
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
            {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
        ],
    )


def create_gate_item_doctype():
    _create_doctype(
        name="NDIS Limited Production Batch Enablement Activation Gate Item",
        autoname="hash",
        title_field="check_label",
        fields=[
            {"fieldname": "activation_gate", "label": "Activation Gate", "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Activation Gate", "reqd": 1, "in_list_view": 1},
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

    if "Limited Production Batch Enablement Activation Gate" not in text_blob:
        content.append(
            {
                "id": "ndis_limited_production_batch_enablement_activation_gate_heading",
                "type": "header",
                "data": {"text": "Limited Production Batch Enablement Activation Gate", "col": 12},
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
    doctypes = {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE9N_DOCTYPES}

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
            "run_limited_production_batch_enablement_activation_gate": permission_matrix().get("run_limited_production_batch_enablement_activation_gate"),
            "cancel_limited_production_batch_enablement_activation_gate": permission_matrix().get("cancel_limited_production_batch_enablement_activation_gate"),
        },
        "js_hooks": {
            "NDIS Limited Production Batch Enablement Activation Gate": "NDIS Limited Production Batch Enablement Activation Gate" in doctype_js,
            "NDIS Limited Production Batch Enablement Activation Gate Item": "NDIS Limited Production Batch Enablement Activation Gate Item" in doctype_js,
        },
        "list_js_hooks": {
            "NDIS Limited Production Batch Enablement Activation Gate": "NDIS Limited Production Batch Enablement Activation Gate" in doctype_list_js,
            "NDIS Limited Production Batch Enablement Activation Gate Item": "NDIS Limited Production Batch Enablement Activation Gate Item" in doctype_list_js,
        },
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_payment_entry_posting_config": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def can_import_service():
    try:
        from ndis_finance.services.limited_production_batch_enablement_activation_gate import quick_limited_production_batch_enablement_activation_gate_summary
        return callable(quick_limited_production_batch_enablement_activation_gate_summary)
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
