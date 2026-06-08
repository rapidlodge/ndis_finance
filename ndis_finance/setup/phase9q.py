import json

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


PHASE9Q_DOCTYPES = [
    "NDIS Limited Production Batch Enablement Evidence Freeze",
    "NDIS Limited Production Batch Enablement Evidence Freeze Line",
]

REPORTS = [
    {
        "report_name": "NDIS Limited Production Batch Enablement Freeze Report",
        "ref_doctype": "NDIS Limited Production Batch Enablement Evidence Freeze",
    },
    {
        "report_name": "NDIS Limited Production Batch Enablement Freeze Line Report",
        "ref_doctype": "NDIS Limited Production Batch Enablement Evidence Freeze Line",
    },
    {
        "report_name": "NDIS Limited Production Batch Enablement Freeze Guardrail Report",
        "ref_doctype": "NDIS Limited Production Batch Enablement Evidence Freeze",
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
    "NDIS Limited Production Batch Enablement Evidence Freeze": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Limited Production Batch Enablement Evidence Freeze Line": {
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
        "label": "Limited Production Batch Enablement Evidence Freezes",
        "type": "DocType",
        "link_to": "NDIS Limited Production Batch Enablement Evidence Freeze",
    },
    {
        "label": "Limited Production Batch Enablement Evidence Freeze Lines",
        "type": "DocType",
        "link_to": "NDIS Limited Production Batch Enablement Evidence Freeze Line",
    },
    {
        "label": "Limited Production Batch Enablement Freeze Report",
        "type": "Report",
        "link_to": "NDIS Limited Production Batch Enablement Freeze Report",
    },
    {
        "label": "Limited Production Batch Enablement Freeze Line Report",
        "type": "Report",
        "link_to": "NDIS Limited Production Batch Enablement Freeze Line Report",
    },
    {
        "label": "Limited Production Batch Enablement Freeze Guardrails",
        "type": "Report",
        "link_to": "NDIS Limited Production Batch Enablement Freeze Guardrail Report",
    },
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_freeze_doctype()
    create_freeze_line_doctype()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Limited Production Batch Enablement Rollback Run",
        "NDIS Limited Production Batch Enablement Rollback Line",
        "NDIS Limited Production Batch Enablement Smoke Run",
        "NDIS Limited Production Batch Enablement Activation Gate",
        "NDIS Limited Production Batch Enablement Adapter Run",
        "NDIS Limited Production Batch Enablement Preview",
        "NDIS Controlled Production Batch Posting Policy",
        "Payment Entry",
        "GL Entry",
        "Report",
        "Workspace",
    ]

    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]

    if missing:
        frappe.throw(
            _("Phase 9Q requires completed Phase 9P rollback. Missing: {0}").format(
                ", ".join(missing)
            )
        )


def create_freeze_doctype():
    _create_doctype(
        name="NDIS Limited Production Batch Enablement Evidence Freeze",
        autoname="field:freeze_id",
        title_field="freeze_id",
        fields=[
            {"fieldname": "freeze_id", "label": "Freeze ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nNeeds Review\nFrozen\nBlocked\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "freeze_status", "label": "Freeze Status", "fieldtype": "Select", "options": "\nLimited Enablement Smoke Evidence Frozen\nNeeds Review\nBlocked\nCancelled", "read_only": 1, "in_list_view": 1},
            {"fieldname": "decision_section", "label": "Freeze Decision", "fieldtype": "Section Break"},
            {"fieldname": "evidence_freeze_allowed", "label": "Evidence Freeze Allowed", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "ready_for_next_phase", "label": "Ready For Next Phase", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "phase9p_rollback_verified", "label": "Phase 9P Rollback Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "phase9o_smoke_verified", "label": "Phase 9O Smoke Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "phase9n_activation_gate_verified", "label": "Phase 9N Activation Gate Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "phase9m_adapter_verified", "label": "Phase 9M Adapter Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "phase9l_preview_verified", "label": "Phase 9L Preview Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "policy_caps_verified", "label": "Policy Caps Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "rollback_verified", "label": "Rollback Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "no_accounting_movement_verified", "label": "No Accounting Movement Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "production_batch_posting_allowed", "label": "Production Batch Posting Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "real_posting_allowed", "label": "Real Posting Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "policy_live_enabled", "label": "Policy Live Enabled", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "chain_section", "label": "Evidence Chain", "fieldtype": "Section Break"},
            {"fieldname": "rollback_run", "label": "Phase 9P Rollback Run", "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Rollback Run", "in_list_view": 1},
            {"fieldname": "enablement_smoke", "label": "Phase 9O Enablement Smoke", "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Smoke Run", "in_list_view": 1},
            {"fieldname": "activation_gate", "label": "Phase 9N Activation Gate", "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Activation Gate"},
            {"fieldname": "enablement_adapter", "label": "Phase 9M Enablement Adapter", "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Adapter Run"},
            {"fieldname": "enablement_preview", "label": "Phase 9L Enablement Preview", "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Preview"},
            {"fieldname": "enablement_gate", "label": "Phase 9K Enablement Design Gate", "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Design Gate"},
            {"fieldname": "policy_lock", "label": "Phase 9J Policy Lock", "fieldtype": "Link", "options": "NDIS Limited Production Batch Policy Lock"},
            {"fieldname": "policy_section", "label": "Frozen Policy Evidence", "fieldtype": "Section Break"},
            {"fieldname": "target_policy_doctype", "label": "Target Policy DocType", "fieldtype": "Link", "options": "DocType", "read_only": 1},
            {"fieldname": "target_policy", "label": "Target Policy", "fieldtype": "Dynamic Link", "options": "target_policy_doctype", "in_list_view": 1},
            {"fieldname": "target_policy_name", "label": "Target Policy Name", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "enablement_field", "label": "Enablement Field", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "live_field", "label": "Live Field", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "target_policy_enabled_before_rollback", "label": "Target Policy Enabled Before Rollback", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "target_policy_enabled_after_rollback", "label": "Target Policy Enabled After Rollback", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "target_policy_live_before_rollback", "label": "Target Policy Live Before Rollback", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "target_policy_live_after_rollback", "label": "Target Policy Live After Rollback", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "policy_enabled_before_count", "label": "Policy Enabled Before Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "policy_enabled_after_count", "label": "Policy Enabled After Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "actual_enabled_policy_count_before", "label": "Actual Enabled Policy Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "actual_enabled_policy_count_after", "label": "Actual Enabled Policy Count After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "locked_policy_caps_section", "label": "Locked Policy Caps", "fieldtype": "Section Break"},
            {"fieldname": "max_batch_lines", "label": "Max Batch Lines", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "max_batch_amount", "label": "Max Batch Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "max_payment_entry_count", "label": "Max Payment Entry Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "movement_guardrail_section", "label": "Movement Guardrails", "fieldtype": "Section Break"},
            {"fieldname": "actual_payment_entry_created_count", "label": "Actual Payment Entry Created Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "actual_gl_created_count", "label": "Actual GL Created Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_count_before", "label": "Payment Entry Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_count_after", "label": "Payment Entry Count After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_count_before", "label": "Payment Entry GL Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_count_after", "label": "Payment Entry GL Count After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "guardrail_section", "label": "Other Guardrails", "fieldtype": "Section Break"},
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
            {"fieldname": "score_section", "label": "Freeze Score", "fieldtype": "Section Break"},
            {"fieldname": "freeze_score", "label": "Freeze Score", "fieldtype": "Percent", "read_only": 1},
            {"fieldname": "blocker_count", "label": "Blocker Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "warning_count", "label": "Warning Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "pass_count", "label": "Pass Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "info_count", "label": "Info Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "line_count", "label": "Line Count", "fieldtype": "Int", "read_only": 1},
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


def create_freeze_line_doctype():
    _create_doctype(
        name="NDIS Limited Production Batch Enablement Evidence Freeze Line",
        autoname="hash",
        title_field="line_label",
        fields=[
            {"fieldname": "evidence_freeze", "label": "Evidence Freeze", "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Evidence Freeze", "reqd": 1, "in_list_view": 1},
            {"fieldname": "line_no", "label": "Line No", "fieldtype": "Int", "in_list_view": 1},
            {"fieldname": "line_label", "label": "Line Label", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "line_status", "label": "Line Status", "fieldtype": "Select", "options": "\nFrozen\nPreview Only\nBlocked\nCancelled", "default": "Preview Only", "in_list_view": 1},
            {"fieldname": "policy_doctype", "label": "Policy DocType", "fieldtype": "Data"},
            {"fieldname": "policy_name", "label": "Policy Name", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "policy_action", "label": "Policy Action", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "enabled_before_rollback", "label": "Enabled Before Rollback", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "enabled_after_rollback", "label": "Enabled After Rollback", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "live_before_rollback", "label": "Live Before Rollback", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "live_after_rollback", "label": "Live After Rollback", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "rollback_completed", "label": "Rollback Completed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "freeze_completed", "label": "Freeze Completed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "production_batch_posting_allowed", "label": "Production Batch Posting Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "real_posting_allowed", "label": "Real Posting Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "policy_live_enabled", "label": "Policy Live Enabled", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "detail", "label": "Detail", "fieldtype": "Small Text"},
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
    if "Limited Production Batch Enablement Evidence Freeze" not in text_blob:
        content.append(
            {
                "id": "ndis_limited_production_batch_enablement_freeze_heading",
                "type": "header",
                "data": {"text": "Limited Production Batch Enablement Evidence Freeze", "col": 12},
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


@frappe.whitelist()
def health_check():
    hooks = frappe.get_hooks()
    doctype_js = hooks.get("doctype_js", {})
    doctype_list_js = hooks.get("doctype_list_js", {})
    return {
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE9Q_DOCTYPES},
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_limited_production_batch_enablement_freeze": permission_matrix().get("run_limited_production_batch_enablement_freeze"),
            "cancel_limited_production_batch_enablement_freeze": permission_matrix().get("cancel_limited_production_batch_enablement_freeze"),
        },
        "js_hooks": {
            "NDIS Limited Production Batch Enablement Evidence Freeze": "NDIS Limited Production Batch Enablement Evidence Freeze" in doctype_js,
            "NDIS Limited Production Batch Enablement Evidence Freeze Line": "NDIS Limited Production Batch Enablement Evidence Freeze Line" in doctype_js,
        },
        "list_js_hooks": {
            "NDIS Limited Production Batch Enablement Evidence Freeze": "NDIS Limited Production Batch Enablement Evidence Freeze" in doctype_list_js,
            "NDIS Limited Production Batch Enablement Evidence Freeze Line": "NDIS Limited Production Batch Enablement Evidence Freeze Line" in doctype_list_js,
        },
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_payment_entry_posting_config": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def can_import_service():
    try:
        from ndis_finance.services.limited_production_batch_enablement_freeze import quick_limited_production_batch_enablement_freeze_summary

        return callable(quick_limited_production_batch_enablement_freeze_summary)
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
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            result[shortcut["label"]] = True
    return result
