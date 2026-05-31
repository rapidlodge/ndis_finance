import json
from pathlib import Path

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


RUN_DOCTYPE = "NDIS PE One Submitted Smoke Run"
ITEM_DOCTYPE = "NDIS PE One Submitted Smoke Run Item"
PHASE5I_DOCTYPES = [RUN_DOCTYPE, ITEM_DOCTYPE]

REPORTS = [
    {
        "report_name": "NDIS PE One Submitted Smoke Run Report",
        "ref_doctype": RUN_DOCTYPE,
        "module_path": "ndis_pe_one_submitted_smoke_run_report",
    },
    {
        "report_name": "NDIS PE One Submitted Smoke Exception Report",
        "ref_doctype": ITEM_DOCTYPE,
        "module_path": "ndis_pe_one_submitted_smoke_exception_report",
    },
    {
        "report_name": "NDIS PE One Submitted Smoke GL Report",
        "ref_doctype": "Payment Entry",
        "module_path": "ndis_pe_one_submitted_smoke_gl_report",
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
    RUN_DOCTYPE: {
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
    {"label": "PE One Submitted Smoke Runs", "type": "DocType", "link_to": RUN_DOCTYPE},
    {"label": "PE One Submitted Smoke Run Items", "type": "DocType", "link_to": ITEM_DOCTYPE},
    {
        "label": "PE One Submitted Smoke Run Report",
        "type": "Report",
        "link_to": "NDIS PE One Submitted Smoke Run Report",
    },
    {
        "label": "PE One Submitted Smoke Exceptions",
        "type": "Report",
        "link_to": "NDIS PE One Submitted Smoke Exception Report",
    },
    {
        "label": "PE One Submitted Smoke GL",
        "type": "Report",
        "link_to": "NDIS PE One Submitted Smoke GL Report",
    },
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_payment_entry_custom_fields()
    create_run_doctype()
    create_run_item_doctype()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS PE Smoke Invoice Source Run",
        "NDIS PE Submitted Smoke Gate",
        "NDIS PE Single Record Draft Smoke Run",
        "NDIS PE Production Activation Gate",
        "Sales Invoice",
        "Payment Entry",
        "Payment Entry Reference",
        "GL Entry",
        "Account",
        "Company",
        "Report",
        "Workspace",
    ]
    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]
    if missing:
        frappe.throw(
            _("Phase 5I requires completed Phase 5H invoice source harness. Missing: {0}").format(
                ", ".join(missing)
            )
        )


def create_payment_entry_custom_fields():
    create_custom_fields(
        {
            "Payment Entry": [
                {
                    "fieldname": "custom_ndis_pe_one_submitted_smoke_section",
                    "label": "NDIS PE One Submitted Smoke",
                    "fieldtype": "Section Break",
                    "insert_after": "custom_ndis_pe_draft_smoke_note",
                },
                {
                    "fieldname": "custom_ndis_pe_one_submitted_smoke",
                    "label": "NDIS PE One Submitted Smoke",
                    "fieldtype": "Check",
                    "insert_after": "custom_ndis_pe_one_submitted_smoke_section",
                    "default": "0",
                    "read_only": 1,
                },
                {
                    "fieldname": "custom_ndis_pe_one_submitted_smoke_run",
                    "label": "NDIS PE One Submitted Smoke Run",
                    "fieldtype": "Link",
                    "options": RUN_DOCTYPE,
                    "insert_after": "custom_ndis_pe_one_submitted_smoke",
                    "read_only": 1,
                },
                {
                    "fieldname": "custom_ndis_pe_one_submitted_source_invoice",
                    "label": "NDIS PE One Submitted Source Invoice",
                    "fieldtype": "Link",
                    "options": "Sales Invoice",
                    "insert_after": "custom_ndis_pe_one_submitted_smoke_run",
                    "read_only": 1,
                },
                {
                    "fieldname": "custom_ndis_pe_one_submitted_phase",
                    "label": "NDIS PE One Submitted Phase",
                    "fieldtype": "Data",
                    "insert_after": "custom_ndis_pe_one_submitted_source_invoice",
                    "read_only": 1,
                },
                {
                    "fieldname": "custom_ndis_pe_one_submitted_note",
                    "label": "NDIS PE One Submitted Note",
                    "fieldtype": "Small Text",
                    "insert_after": "custom_ndis_pe_one_submitted_phase",
                    "read_only": 1,
                },
            ]
        },
        ignore_validate=True,
    )


def create_run_doctype():
    _create_doctype(
        name=RUN_DOCTYPE,
        autoname="field:submitted_run_id",
        title_field="submitted_run_id",
        fields=[
            {"fieldname": "submitted_run_id", "label": "Submitted Run ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nPreviewed\nNeeds Review\nBlocked\nSubmitted\nPayment Cancelled\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "run_type", "label": "Run Type", "fieldtype": "Select", "options": "\nOne Submitted Payment Entry Smoke\nPreview Only", "default": "One Submitted Payment Entry Smoke"},
            {"fieldname": "source_section", "label": "Source", "fieldtype": "Section Break"},
            {"fieldname": "source_sales_invoice", "label": "Source Sales Invoice", "fieldtype": "Link", "options": "Sales Invoice", "in_list_view": 1},
            {"fieldname": "source_invoice_run", "label": "Phase 5H Source Run", "fieldtype": "Link", "options": "NDIS PE Smoke Invoice Source Run"},
            {"fieldname": "submitted_smoke_gate", "label": "Phase 5G Submitted Smoke Gate", "fieldtype": "Link", "options": "NDIS PE Submitted Smoke Gate"},
            {"fieldname": "draft_smoke_run", "label": "Phase 5F Draft Smoke Run", "fieldtype": "Link", "options": "NDIS PE Single Record Draft Smoke Run"},
            {"fieldname": "activation_gate", "label": "Phase 5E Activation Gate", "fieldtype": "Link", "options": "NDIS PE Production Activation Gate"},
            {"fieldname": "payment_section", "label": "Payment Entry", "fieldtype": "Section Break"},
            {"fieldname": "payment_entry", "label": "Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "in_list_view": 1},
            {"fieldname": "payment_entry_created", "label": "Payment Entry Created", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "payment_entry_submitted", "label": "Payment Entry Submitted", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "payment_entry_cancelled", "label": "Payment Entry Cancelled", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "payment_entry_docstatus", "label": "Payment Entry Docstatus", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_amount", "label": "Payment Amount", "fieldtype": "Currency", "in_list_view": 1},
            {"fieldname": "account_section", "label": "Accounts", "fieldtype": "Section Break"},
            {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company", "in_list_view": 1},
            {"fieldname": "customer", "label": "Customer", "fieldtype": "Link", "options": "Customer"},
            {"fieldname": "allowed_bank_account", "label": "Allowed Bank Account", "fieldtype": "Link", "options": "Account"},
            {"fieldname": "allowed_receivable_account", "label": "Allowed Receivable Account", "fieldtype": "Link", "options": "Account"},
            {"fieldname": "invoice_section", "label": "Invoice Verification", "fieldtype": "Section Break"},
            {"fieldname": "invoice_outstanding_before", "label": "Invoice Outstanding Before", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "invoice_outstanding_after", "label": "Invoice Outstanding After", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "invoice_docstatus", "label": "Invoice Docstatus", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "gl_section", "label": "GL Verification", "fieldtype": "Section Break"},
            {"fieldname": "payment_entry_gl_count", "label": "Payment Entry GL Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_net", "label": "Payment Entry GL Net", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "sales_invoice_gl_count", "label": "Sales Invoice GL Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "sales_invoice_gl_net", "label": "Sales Invoice GL Net", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "site_section", "label": "Site / Config", "fieldtype": "Section Break"},
            {"fieldname": "site_name", "label": "Site Name", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "sandbox_config_enabled", "label": "Sandbox Config Enabled", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "production_mode_detected", "label": "Production Mode Detected", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "live_payment_entry_posting_config", "label": "Live PE Posting Config", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "executed_on", "label": "Executed On", "fieldtype": "Datetime", "read_only": 1, "in_list_view": 1},
            {"fieldname": "executed_by", "label": "Executed By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "score_section", "label": "Smoke Score", "fieldtype": "Section Break"},
            {"fieldname": "smoke_score", "label": "Smoke Score", "fieldtype": "Percent", "read_only": 1},
            {"fieldname": "smoke_status", "label": "Smoke Status", "fieldtype": "Select", "options": "\nReady To Submit One PE\nPayment Entry Submitted\nReady With Warnings\nNeeds Review\nBlocked", "read_only": 1},
            {"fieldname": "blocker_count", "label": "Blocker Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "warning_count", "label": "Warning Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "pass_count", "label": "Pass Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "info_count", "label": "Info Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "item_count", "label": "Item Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "control_section", "label": "Strict Controls", "fieldtype": "Section Break"},
            {"fieldname": "live_posting_allowed", "label": "Live Posting Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "live_enabled_policy_count", "label": "Live Enabled Policy Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "existing_phase5i_submitted_pe_count", "label": "Existing Phase 5I Submitted PE Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "guardrail_section", "label": "Other Movement Guardrails", "fieldtype": "Section Break"},
            {"fieldname": "submitted_journal_entry_count_today", "label": "Submitted JE Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "purchase_invoice_count_today", "label": "Purchase Invoice Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "ack_section", "label": "Acknowledgement", "fieldtype": "Section Break"},
            {"fieldname": "required_acknowledgement", "label": "Required Acknowledgement", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "acknowledgement", "label": "Acknowledgement", "fieldtype": "Data"},
            {"fieldname": "acknowledgement_ok", "label": "Acknowledgement OK", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "audit_section", "label": "Audit", "fieldtype": "Section Break"},
            {"fieldname": "payment_cancelled_on", "label": "Payment Cancelled On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "payment_cancelled_by", "label": "Payment Cancelled By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "cancelled_on", "label": "Run Cancelled On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "cancelled_by", "label": "Run Cancelled By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "summary_json", "label": "Summary JSON", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
        ],
    )


def create_run_item_doctype():
    _create_doctype(
        name=ITEM_DOCTYPE,
        autoname="hash",
        title_field="check_label",
        fields=[
            {"fieldname": "submitted_run", "label": "Submitted Run", "fieldtype": "Link", "options": RUN_DOCTYPE, "reqd": 1, "in_list_view": 1},
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
    if "One Submitted Payment Entry Smoke" not in text_blob:
        content.append(
            {
                "id": "ndis_pe_one_submitted_smoke_heading",
                "type": "header",
                "data": {"text": "One Submitted Payment Entry Smoke", "col": 12},
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
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE5I_DOCTYPES},
        "reports": {
            report["report_name"]: bool(frappe.db.exists("Report", report["report_name"]))
            for report in REPORTS
        },
        "report_files": check_report_files(),
        "payment_entry_fields": {
            fieldname: bool(frappe.db.exists("Custom Field", f"Payment Entry-{fieldname}"))
            for fieldname in [
                "custom_ndis_pe_one_submitted_smoke",
                "custom_ndis_pe_one_submitted_smoke_run",
                "custom_ndis_pe_one_submitted_source_invoice",
                "custom_ndis_pe_one_submitted_phase",
                "custom_ndis_pe_one_submitted_note",
            ]
        },
        "permissions": {
            dt: frappe.get_all(
                "DocPerm",
                filters={"parent": dt},
                fields=["role", "read", "write", "create", "delete", "report", "export"],
                order_by="role asc",
            )
            for dt in PHASE5I_DOCTYPES
        },
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_pe_one_submitted_smoke": permission_matrix().get("run_pe_one_submitted_smoke"),
            "cancel_pe_one_submitted_smoke_payment": permission_matrix().get(
                "cancel_pe_one_submitted_smoke_payment"
            ),
            "cancel_pe_one_submitted_smoke_run": permission_matrix().get("cancel_pe_one_submitted_smoke_run"),
        },
        "js_hooks": {
            RUN_DOCTYPE: RUN_DOCTYPE in doctype_js,
            ITEM_DOCTYPE: ITEM_DOCTYPE in doctype_js,
        },
        "list_js_hooks": {
            RUN_DOCTYPE: RUN_DOCTYPE in doctype_list_js,
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
        from ndis_finance.services.pe_one_submitted_smoke import quick_pe_one_submitted_smoke_summary

        return callable(quick_pe_one_submitted_smoke_summary)
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
