import json
from pathlib import Path

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


FREEZE_DOCTYPE = "NDIS PE Live Smoke Completion Freeze"
ITEM_DOCTYPE = "NDIS PE Live Smoke Completion Freeze Item"
PHASE5K_DOCTYPES = [FREEZE_DOCTYPE, ITEM_DOCTYPE]

REPORTS = [
    {
        "report_name": "NDIS PE Live Smoke Completion Freeze Report",
        "ref_doctype": FREEZE_DOCTYPE,
        "module_path": "ndis_pe_live_smoke_completion_freeze_report",
    },
    {
        "report_name": "NDIS PE Live Smoke Completion Exception Report",
        "ref_doctype": ITEM_DOCTYPE,
        "module_path": "ndis_pe_live_smoke_completion_exception_report",
    },
    {
        "report_name": "NDIS PE Live Smoke Completion GL Evidence Report",
        "ref_doctype": "GL Entry",
        "module_path": "ndis_pe_live_smoke_completion_gl_evidence_report",
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
    FREEZE_DOCTYPE: {
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
    {"label": "PE Live Smoke Completion Freezes", "type": "DocType", "link_to": FREEZE_DOCTYPE},
    {"label": "PE Live Smoke Completion Items", "type": "DocType", "link_to": ITEM_DOCTYPE},
    {
        "label": "PE Live Smoke Completion Freeze Report",
        "type": "Report",
        "link_to": "NDIS PE Live Smoke Completion Freeze Report",
    },
    {
        "label": "PE Live Smoke Completion Exceptions",
        "type": "Report",
        "link_to": "NDIS PE Live Smoke Completion Exception Report",
    },
    {
        "label": "PE Live Smoke Completion GL Evidence",
        "type": "Report",
        "link_to": "NDIS PE Live Smoke Completion GL Evidence Report",
    },
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_freeze_doctype()
    create_freeze_item_doctype()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS PE Smoke Rollback Run",
        "NDIS PE One Submitted Smoke Run",
        "NDIS PE Smoke Invoice Source Run",
        "NDIS PE Submitted Smoke Gate",
        "Sales Invoice",
        "Payment Entry",
        "GL Entry",
        "Report",
        "Workspace",
    ]
    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]
    if missing:
        frappe.throw(
            _("Phase 5K requires completed Phase 5J rollback verification. Missing: {0}").format(
                ", ".join(missing)
            )
        )


def create_freeze_doctype():
    _create_doctype(
        name=FREEZE_DOCTYPE,
        autoname="field:completion_freeze_id",
        title_field="completion_freeze_id",
        fields=[
            {"fieldname": "completion_freeze_id", "label": "Completion Freeze ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nPreviewed\nNeeds Review\nBlocked\nFrozen\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "freeze_type", "label": "Freeze Type", "fieldtype": "Select", "options": "\nPayment Entry Live Smoke Completion\nRead Only Evidence Freeze", "default": "Payment Entry Live Smoke Completion", "in_list_view": 1},
            {"fieldname": "completion_freeze_allowed", "label": "Completion Freeze Allowed", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "ready_for_next_phase", "label": "Ready For Next Phase", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "evidence_section", "label": "Phase Evidence", "fieldtype": "Section Break"},
            {"fieldname": "phase5h_source_run", "label": "Phase 5H Source Run", "fieldtype": "Link", "options": "NDIS PE Smoke Invoice Source Run"},
            {"fieldname": "phase5i_run", "label": "Phase 5I Submitted PE Run", "fieldtype": "Link", "options": "NDIS PE One Submitted Smoke Run"},
            {"fieldname": "phase5j_rollback_run", "label": "Phase 5J Rollback Run", "fieldtype": "Link", "options": "NDIS PE Smoke Rollback Run", "in_list_view": 1},
            {"fieldname": "source_sales_invoice", "label": "Source Sales Invoice", "fieldtype": "Link", "options": "Sales Invoice", "in_list_view": 1},
            {"fieldname": "payment_entry", "label": "Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "in_list_view": 1},
            {"fieldname": "state_section", "label": "Final Voucher State", "fieldtype": "Section Break"},
            {"fieldname": "payment_entry_docstatus", "label": "Payment Entry Docstatus", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "source_invoice_docstatus", "label": "Source Invoice Docstatus", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "source_invoice_cancelled_flag", "label": "Source Invoice Cancelled Flag", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "source_invoice_outstanding", "label": "Source Invoice Outstanding", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "gl_section", "label": "GL Evidence", "fieldtype": "Section Break"},
            {"fieldname": "payment_entry_gl_count", "label": "Payment Entry GL Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_net", "label": "Payment Entry GL Net", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "sales_invoice_gl_count", "label": "Sales Invoice GL Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "sales_invoice_gl_net", "label": "Sales Invoice GL Net", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "cycle_section", "label": "Cycle Counts", "fieldtype": "Section Break"},
            {"fieldname": "submitted_phase5i_pe_count", "label": "Submitted Phase 5I PE Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "cancelled_phase5i_pe_count", "label": "Cancelled Phase 5I PE Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "active_phase5h_source_invoice_count", "label": "Active Phase 5H Source Invoice Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "cancelled_phase5h_source_invoice_count", "label": "Cancelled Phase 5H Source Invoice Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "fully_rolled_back_count", "label": "Fully Rolled Back Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "site_section", "label": "Site / Config", "fieldtype": "Section Break"},
            {"fieldname": "site_name", "label": "Site Name", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "sandbox_config_enabled", "label": "Sandbox Config Enabled", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "production_mode_detected", "label": "Production Mode Detected", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "live_payment_entry_posting_config", "label": "Live PE Posting Config", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "checked_on", "label": "Checked On", "fieldtype": "Datetime", "read_only": 1, "in_list_view": 1},
            {"fieldname": "checked_by", "label": "Checked By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "score_section", "label": "Freeze Score", "fieldtype": "Section Break"},
            {"fieldname": "freeze_score", "label": "Freeze Score", "fieldtype": "Percent", "read_only": 1},
            {"fieldname": "freeze_status", "label": "Freeze Status", "fieldtype": "Select", "options": "\nReady To Freeze\nFrozen\nReady With Warnings\nNeeds Review\nBlocked", "read_only": 1},
            {"fieldname": "blocker_count", "label": "Blocker Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "warning_count", "label": "Warning Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "pass_count", "label": "Pass Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "info_count", "label": "Info Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "item_count", "label": "Item Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "guardrail_section", "label": "Guardrails", "fieldtype": "Section Break"},
            {"fieldname": "new_payment_entry_created", "label": "New Payment Entry Created", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "submitted_journal_entry_count_today", "label": "Submitted JE Count Today", "fieldtype": "Int", "read_only": 1},
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


def create_freeze_item_doctype():
    _create_doctype(
        name=ITEM_DOCTYPE,
        autoname="hash",
        title_field="check_label",
        fields=[
            {"fieldname": "completion_freeze", "label": "Completion Freeze", "fieldtype": "Link", "options": FREEZE_DOCTYPE, "reqd": 1, "in_list_view": 1},
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
    ws_name = frappe.db.exists("Workspace", WORKSPACE_NAME) or frappe.db.exists(
        "Workspace", {"label": WORKSPACE_NAME}
    )
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
    if "Payment Entry Live Smoke Completion" not in text_blob:
        content.append(
            {
                "id": "ndis_pe_live_smoke_completion_heading",
                "type": "header",
                "data": {"text": "Payment Entry Live Smoke Completion", "col": 12},
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
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE5K_DOCTYPES},
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
            for dt in PHASE5K_DOCTYPES
        },
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_pe_live_smoke_completion_freeze": permission_matrix().get("run_pe_live_smoke_completion_freeze"),
            "cancel_pe_live_smoke_completion_freeze": permission_matrix().get("cancel_pe_live_smoke_completion_freeze"),
        },
        "js_hooks": {
            FREEZE_DOCTYPE: FREEZE_DOCTYPE in doctype_js,
            ITEM_DOCTYPE: ITEM_DOCTYPE in doctype_js,
        },
        "list_js_hooks": {
            FREEZE_DOCTYPE: FREEZE_DOCTYPE in doctype_list_js,
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
        from ndis_finance.services.pe_live_smoke_completion_freeze import quick_pe_live_smoke_completion_freeze_summary

        return callable(quick_pe_live_smoke_completion_freeze_summary)
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
    ws_name = frappe.db.exists("Workspace", WORKSPACE_NAME) or frappe.db.exists(
        "Workspace", {"label": WORKSPACE_NAME}
    )
    result = {shortcut["label"]: False for shortcut in WORKSPACE_SHORTCUTS}
    if not ws_name:
        return result
    ws = frappe.get_doc("Workspace", ws_name)
    text_blob = ws.content or ""
    for shortcut in WORKSPACE_SHORTCUTS:
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            result[shortcut["label"]] = True
    return result
