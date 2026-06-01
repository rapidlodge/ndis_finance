import json
from pathlib import Path

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


GATE_DOCTYPE = "NDIS Real Remittance PE Activation Gate"
ITEM_DOCTYPE = "NDIS Real Remittance PE Activation Gate Item"
PHASE6D_DOCTYPES = [GATE_DOCTYPE, ITEM_DOCTYPE]

REPORTS = [
    {
        "report_name": "NDIS Real Remittance PE Activation Gate Report",
        "ref_doctype": GATE_DOCTYPE,
        "module_path": "ndis_real_remittance_pe_activation_gate_report",
    },
    {
        "report_name": "NDIS Real Remittance PE Activation Exception Report",
        "ref_doctype": ITEM_DOCTYPE,
        "module_path": "ndis_real_remittance_pe_activation_exception_report",
    },
    {
        "report_name": "NDIS Real Remittance PE Activation Readiness Report",
        "ref_doctype": "NDIS Real Remittance PE Adapter Run",
        "module_path": "ndis_real_remittance_pe_activation_readiness_report",
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
    GATE_DOCTYPE: {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
    ITEM_DOCTYPE: {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
}

WORKSPACE_NAME = "NDIS Finance"
WORKSPACE_SHORTCUTS = [
    {"label": "Real Remittance PE Activation Gates", "type": "DocType", "link_to": GATE_DOCTYPE},
    {"label": "Real Remittance PE Activation Items", "type": "DocType", "link_to": ITEM_DOCTYPE},
    {
        "label": "Real Remittance PE Activation Gate Report",
        "type": "Report",
        "link_to": "NDIS Real Remittance PE Activation Gate Report",
    },
    {
        "label": "Real Remittance PE Activation Exceptions",
        "type": "Report",
        "link_to": "NDIS Real Remittance PE Activation Exception Report",
    },
    {
        "label": "Real Remittance PE Activation Readiness",
        "type": "Report",
        "link_to": "NDIS Real Remittance PE Activation Readiness Report",
    },
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_activation_gate_doctype()
    create_activation_gate_item_doctype()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Real Remittance PE Adapter Run",
        "NDIS Real Remittance PE Adapter Run Line",
        "NDIS Real Remittance PE Preview",
        "NDIS Real Remittance PE Preview Line",
        "NDIS Real Remittance PE Design Gate",
        "NDIS Remittance Import",
        "NDIS Remittance Import Line",
        "Payment Entry",
        "Payment Entry Reference",
        "GL Entry",
        "Report",
        "Workspace",
    ]
    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]
    if missing:
        frappe.throw(
            _("Phase 6D requires completed Phase 6C adapter foundation. Missing: {0}").format(
                ", ".join(missing)
            )
        )


def create_activation_gate_doctype():
    _create_doctype(
        name=GATE_DOCTYPE,
        autoname="field:activation_gate_id",
        title_field="activation_gate_id",
        fields=[
            {"fieldname": "activation_gate_id", "label": "Activation Gate ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nPreviewed\nNeeds Review\nSource Pending\nActivation Allowed\nBlocked\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "gate_type", "label": "Gate Type", "fieldtype": "Select", "options": "\nReal Remittance Payment Entry Activation\nNo Posting Gate", "default": "Real Remittance Payment Entry Activation", "in_list_view": 1},
            {"fieldname": "approval_section", "label": "Activation Decision", "fieldtype": "Section Break"},
            {"fieldname": "structural_ready_allowed", "label": "Structural Ready Allowed", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "ready_for_real_smoke", "label": "Ready For Real Smoke", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "real_posting_allowed", "label": "Real Posting Allowed", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "source_eligible_pending", "label": "Source Eligible Pending", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "source_section", "label": "Source Evidence", "fieldtype": "Section Break"},
            {"fieldname": "adapter_run", "label": "Phase 6C Adapter Run", "fieldtype": "Link", "options": "NDIS Real Remittance PE Adapter Run", "in_list_view": 1},
            {"fieldname": "preview", "label": "Phase 6B Preview", "fieldtype": "Link", "options": "NDIS Real Remittance PE Preview"},
            {"fieldname": "design_gate", "label": "Phase 6A Design Gate", "fieldtype": "Link", "options": "NDIS Real Remittance PE Design Gate"},
            {"fieldname": "source_remittance_import", "label": "Source Remittance Import", "fieldtype": "Link", "options": "NDIS Remittance Import"},
            {"fieldname": "scope_section", "label": "Locked Scope", "fieldtype": "Section Break"},
            {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company", "in_list_view": 1},
            {"fieldname": "bank_account", "label": "Bank Account", "fieldtype": "Link", "options": "Account"},
            {"fieldname": "receivable_account", "label": "Receivable Account", "fieldtype": "Link", "options": "Account"},
            {"fieldname": "batch_line_cap", "label": "Batch Line Cap", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "batch_amount_cap", "label": "Batch Amount Cap", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "readiness_section", "label": "Readiness Counts", "fieldtype": "Section Break"},
            {"fieldname": "source_preview_line_count", "label": "Source Preview Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "eligible_preview_line_count", "label": "Eligible Preview Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "blocked_preview_line_count", "label": "Blocked Preview Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "hard_blocked_line_count", "label": "Hard-blocked Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "validation_blocked_line_count", "label": "Validation-blocked Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "would_create_payment_entry_count", "label": "Would Create PE Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "would_create_payment_entry_amount", "label": "Would Create PE Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "actual_payment_entry_created_count", "label": "Actual PE Created Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "actual_gl_created_count", "label": "Actual GL Created Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "site_section", "label": "Site / Config", "fieldtype": "Section Break"},
            {"fieldname": "site_name", "label": "Site Name", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "sandbox_config_enabled", "label": "Sandbox Config Enabled", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "production_mode_detected", "label": "Production Mode Detected", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "live_payment_entry_posting_config", "label": "Live PE Posting Config", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "checked_on", "label": "Checked On", "fieldtype": "Datetime", "read_only": 1, "in_list_view": 1},
            {"fieldname": "checked_by", "label": "Checked By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "score_section", "label": "Activation Score", "fieldtype": "Section Break"},
            {"fieldname": "activation_score", "label": "Activation Score", "fieldtype": "Percent", "read_only": 1},
            {"fieldname": "activation_status", "label": "Activation Status", "fieldtype": "Select", "options": "\nReady For Single Real Smoke\nSource Eligible Pending\nStructural Ready Only\nNeeds Review\nBlocked", "read_only": 1},
            {"fieldname": "blocker_count", "label": "Blocker Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "warning_count", "label": "Warning Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "pass_count", "label": "Pass Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "info_count", "label": "Info Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "item_count", "label": "Item Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "guardrail_section", "label": "Movement Guardrails", "fieldtype": "Section Break"},
            {"fieldname": "payment_entry_count_before", "label": "Payment Entry Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_count_after", "label": "Payment Entry Count After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_count_before", "label": "Payment Entry GL Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_count_after", "label": "Payment Entry GL Count After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "submitted_journal_entry_count_today", "label": "Submitted JE Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "sales_invoice_count_today", "label": "Sales Invoice Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "purchase_invoice_count_today", "label": "Purchase Invoice Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "live_enabled_policy_count", "label": "Live Enabled Policy Count", "fieldtype": "Int", "read_only": 1},
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


def create_activation_gate_item_doctype():
    _create_doctype(
        name=ITEM_DOCTYPE,
        autoname="hash",
        title_field="check_label",
        fields=[
            {"fieldname": "activation_gate", "label": "Activation Gate", "fieldtype": "Link", "options": GATE_DOCTYPE, "reqd": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nPass\nWarning\nBlocker\nInfo\nCancelled", "default": "Info", "in_list_view": 1},
            {"fieldname": "severity", "label": "Severity", "fieldtype": "Select", "options": "\nLow\nMedium\nHigh\nCritical", "default": "Low", "in_list_view": 1},
            {"fieldname": "category", "label": "Category", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "check_key", "label": "Check Key", "fieldtype": "Data"},
            {"fieldname": "check_label", "label": "Check Label", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "detail", "label": "Detail", "fieldtype": "Small Text"},
            {"fieldname": "recommendation", "label": "Recommendation", "fieldtype": "Small Text"},
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
    if not existing:
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
    if not ws.meta.has_field("content"):
        return
    try:
        content = json.loads(ws.content or "[]")
    except Exception:
        content = []
    text_blob = json.dumps(content)
    if "Real Remittance Payment Entry Activation" not in text_blob:
        content.append(
            {
                "id": "ndis_real_remittance_pe_activation_heading",
                "type": "header",
                "data": {"text": "Real Remittance Payment Entry Activation", "col": 12},
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
    ws.save(ignore_permissions=True)


@frappe.whitelist()
def health_check():
    hooks = frappe.get_hooks()
    doctype_js = hooks.get("doctype_js", {})
    doctype_list_js = hooks.get("doctype_list_js", {})
    return {
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE6D_DOCTYPES},
        "reports": {
            report["report_name"]: bool(frappe.db.exists("Report", report["report_name"]))
            for report in REPORTS
        },
        "report_files": check_report_files(),
        "permissions": {
            dt: frappe.get_all(
                "DocPerm",
                filters={"parent": dt},
                fields=["role", "read", "write", "create", "delete", "report", "export"],
                order_by="role asc",
            )
            for dt in PHASE6D_DOCTYPES
        },
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_real_remittance_pe_activation_gate": permission_matrix().get("run_real_remittance_pe_activation_gate"),
            "cancel_real_remittance_pe_activation_gate": permission_matrix().get("cancel_real_remittance_pe_activation_gate"),
        },
        "js_hooks": {
            GATE_DOCTYPE: GATE_DOCTYPE in doctype_js,
            ITEM_DOCTYPE: ITEM_DOCTYPE in doctype_js,
        },
        "list_js_hooks": {
            GATE_DOCTYPE: GATE_DOCTYPE in doctype_list_js,
            ITEM_DOCTYPE: ITEM_DOCTYPE in doctype_list_js,
        },
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_payment_entry_posting_config": int(
            frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0
        ),
    }


def can_import_service():
    try:
        from ndis_finance.services.real_remittance_pe_activation_gate import quick_real_remittance_pe_activation_gate_summary

        return callable(quick_real_remittance_pe_activation_gate_summary)
    except Exception:
        return False


def check_report_files():
    report_root = Path(frappe.get_app_path("ndis_finance")) / "ndis_finance" / "report"
    return {
        report["report_name"]: {
            "python": (report_root / report["module_path"] / f"{report['module_path']}.py").exists(),
            "javascript": (report_root / report["module_path"] / f"{report['module_path']}.js").exists(),
        }
        for report in REPORTS
    }


def check_workspace_shortcuts():
    ws_name = frappe.db.exists("Workspace", WORKSPACE_NAME) or frappe.db.exists("Workspace", {"label": WORKSPACE_NAME})
    result = {shortcut["label"]: False for shortcut in WORKSPACE_SHORTCUTS}
    if not ws_name:
        return result
    ws = frappe.get_doc("Workspace", ws_name)
    text_blob = ws.content or ""
    for shortcut in WORKSPACE_SHORTCUTS:
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            result[shortcut["label"]] = True
    return result
