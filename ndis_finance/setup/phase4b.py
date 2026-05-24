import json
import os

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


PHASE4B_DOCTYPES = [
    "NDIS Invoice Backed PE Smoke Run",
    "NDIS Invoice Backed PE Smoke Line",
]

REPORTS = [
    {
        "report_name": "NDIS Invoice Backed PE Smoke Run Report",
        "ref_doctype": "NDIS Invoice Backed PE Smoke Run",
    },
    {
        "report_name": "NDIS Invoice Backed PE Smoke Line Report",
        "ref_doctype": "NDIS Invoice Backed PE Smoke Line",
    },
]

REPORT_FILE_MAP = {
    "NDIS Invoice Backed PE Smoke Run Report": "ndis_invoice_backed_pe_smoke_run_report",
    "NDIS Invoice Backed PE Smoke Line Report": "ndis_invoice_backed_pe_smoke_line_report",
}

REPORT_ROLES = [
    "System Manager",
    "NDIS CFO",
    "NDIS Finance Manager",
    "NDIS Finance Officer",
    "NDIS Finance Read Only",
]

DOC_PERM_MATRIX = {
    "NDIS Invoice Backed PE Smoke Run": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Invoice Backed PE Smoke Line": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
}

WORKSPACE_NAME = "NDIS Finance"

WORKSPACE_SHORTCUTS = [
    {
        "label": "Invoice-backed PE Smoke Runs",
        "type": "DocType",
        "link_to": "NDIS Invoice Backed PE Smoke Run",
    },
    {
        "label": "Invoice-backed PE Smoke Lines",
        "type": "DocType",
        "link_to": "NDIS Invoice Backed PE Smoke Line",
    },
    {
        "label": "Invoice-backed PE Smoke Run Report",
        "type": "Report",
        "link_to": "NDIS Invoice Backed PE Smoke Run Report",
    },
    {
        "label": "Invoice-backed PE Smoke Line Report",
        "type": "Report",
        "link_to": "NDIS Invoice Backed PE Smoke Line Report",
    },
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_smoke_run_doctype()
    create_smoke_line_doctype()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Sandbox Invoice Test Run",
        "NDIS Payment Entry Allocation Preview",
        "NDIS Payment Entry Allocation Preview Line",
        "NDIS Sandbox Payment Entry Run",
        "NDIS Sandbox Payment Entry Run Line",
        "NDIS Payment Entry Sandbox Completion Gate",
        "NDIS Remittance Import",
        "NDIS Remittance Import Line",
        "Sales Invoice",
        "Payment Entry",
        "Account",
        "Customer",
        "Report",
        "Workspace",
    ]
    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]

    if missing:
        frappe.throw(
            _("Phase 4B requires Phase 4A and Phase 3B/3C/3E. Missing: {0}").format(
                ", ".join(missing)
            )
        )


def create_smoke_run_doctype():
    _create_doctype(
        name="NDIS Invoice Backed PE Smoke Run",
        autoname="field:run_id",
        title_field="run_id",
        fields=[
            {"fieldname": "run_id", "label": "Run ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nValidated\nCompleted\nBlocked\nCancelled\nFailed", "default": "Draft", "in_list_view": 1},
            {"fieldname": "smoke_mode", "label": "Smoke Mode", "fieldtype": "Select", "options": "\nInvoice-backed Draft PE", "default": "Invoice-backed Draft PE", "in_list_view": 1},
            {"fieldname": "sandbox_only", "label": "Sandbox Only", "fieldtype": "Check", "default": "1", "read_only": 1},
            {"fieldname": "source_section", "label": "Source Evidence", "fieldtype": "Section Break"},
            {"fieldname": "sandbox_invoice_test_run", "label": "Sandbox Invoice Test Run", "fieldtype": "Link", "options": "NDIS Sandbox Invoice Test Run"},
            {"fieldname": "sales_invoice", "label": "Sandbox Sales Invoice", "fieldtype": "Link", "options": "Sales Invoice", "in_list_view": 1},
            {"fieldname": "sales_invoice_docstatus", "label": "Sales Invoice Docstatus", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "sales_invoice_outstanding_amount", "label": "Sales Invoice Outstanding", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "sales_invoice_gl_entry_count", "label": "Sales Invoice GL Entry Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "created_records_section", "label": "Created Smoke Records", "fieldtype": "Section Break"},
            {"fieldname": "remittance_import", "label": "Smoke Remittance Import", "fieldtype": "Link", "options": "NDIS Remittance Import"},
            {"fieldname": "remittance_import_line", "label": "Smoke Remittance Import Line", "fieldtype": "Link", "options": "NDIS Remittance Import Line"},
            {"fieldname": "allocation_preview", "label": "Allocation Preview", "fieldtype": "Link", "options": "NDIS Payment Entry Allocation Preview"},
            {"fieldname": "sandbox_payment_entry_run", "label": "Sandbox PE Run", "fieldtype": "Link", "options": "NDIS Sandbox Payment Entry Run"},
            {"fieldname": "payment_entry", "label": "Draft Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "in_list_view": 1},
            {"fieldname": "payment_entry_docstatus", "label": "Payment Entry Docstatus", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "control_section", "label": "Controls", "fieldtype": "Section Break"},
            {"fieldname": "site_name", "label": "Site Name", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "sandbox_config_enabled", "label": "Sandbox Config Enabled", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "production_mode_detected", "label": "Production Mode Detected", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "required_acknowledgement", "label": "Required Acknowledgement", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "acknowledgement", "label": "Acknowledgement", "fieldtype": "Data"},
            {"fieldname": "acknowledgement_ok", "label": "Acknowledgement OK", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "accounting_section", "label": "Draft Payment Entry Mapping", "fieldtype": "Section Break"},
            {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company"},
            {"fieldname": "customer", "label": "Customer", "fieldtype": "Link", "options": "Customer"},
            {"fieldname": "bank_account", "label": "Bank Account / Paid To", "fieldtype": "Link", "options": "Account"},
            {"fieldname": "receivable_account", "label": "Receivable Account / Paid From", "fieldtype": "Link", "options": "Account"},
            {"fieldname": "smoke_amount", "label": "Smoke Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "currency", "label": "Currency", "fieldtype": "Link", "options": "Currency"},
            {"fieldname": "summary_section", "label": "Summary", "fieldtype": "Section Break"},
            {"fieldname": "allocatable_line_count", "label": "Allocatable Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "allocation_preview_status", "label": "Allocation Preview Status", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "allocation_preview_validation_status", "label": "Allocation Preview Validation Status", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "payment_entry_gl_entry_count", "label": "Payment Entry GL Entry Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "submitted_payment_entry_count", "label": "Submitted Payment Entry Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "blocker_count", "label": "Blocker Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "warning_count", "label": "Warning Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "audit_section", "label": "Audit", "fieldtype": "Section Break"},
            {"fieldname": "created_on", "label": "Created On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "created_by_user", "label": "Created By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "cancelled_on", "label": "Cancelled On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "cancelled_by", "label": "Cancelled By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "validation_log", "label": "Validation Log", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
        ],
    )


def create_smoke_line_doctype():
    _create_doctype(
        name="NDIS Invoice Backed PE Smoke Line",
        autoname="hash",
        title_field="check_label",
        fields=[
            {"fieldname": "smoke_run", "label": "Smoke Run", "fieldtype": "Link", "options": "NDIS Invoice Backed PE Smoke Run", "reqd": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nPass\nWarning\nBlocker\nInfo\nCancelled", "default": "Info", "in_list_view": 1},
            {"fieldname": "severity", "label": "Severity", "fieldtype": "Select", "options": "\nLow\nMedium\nHigh\nCritical", "default": "Low", "in_list_view": 1},
            {"fieldname": "category", "label": "Category", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "check_key", "label": "Check Key", "fieldtype": "Data"},
            {"fieldname": "check_label", "label": "Check Label", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "detail", "label": "Detail", "fieldtype": "Small Text"},
            {"fieldname": "source_doctype", "label": "Source DocType", "fieldtype": "Link", "options": "DocType"},
            {"fieldname": "source_name", "label": "Source Name", "fieldtype": "Dynamic Link", "options": "source_doctype"},
            {"fieldname": "amount", "label": "Amount", "fieldtype": "Currency"},
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

    if "Invoice-backed Payment Entry Smoke" not in text_blob:
        content.append(
            {
                "id": "ndis_invoice_backed_pe_smoke_heading",
                "type": "header",
                "data": {"text": "Invoice-backed Payment Entry Smoke", "col": 12},
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
    return


@frappe.whitelist()
def health_check():
    doctypes = {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE4B_DOCTYPES}
    reports = {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS}

    permissions = {}
    for dt in PHASE4B_DOCTYPES:
        permissions[dt] = frappe.get_all(
            "DocPerm",
            filters={"parent": dt},
            fields=["role", "read", "write", "create", "delete", "report", "export"],
            order_by="role asc",
        )

    hooks = frappe.get_hooks()
    doctype_js = hooks.get("doctype_js", {})
    doctype_list_js = hooks.get("doctype_list_js", {})
    doc_events = hooks.get("doc_events", {}) or {}
    pe_events_blob = json.dumps(doc_events.get("Payment Entry", {}), default=str)

    return {
        "doctypes": doctypes,
        "reports": reports,
        "permissions": permissions,
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_invoice_backed_pe_smoke": permission_matrix().get("run_invoice_backed_pe_smoke"),
            "cancel_invoice_backed_pe_smoke": permission_matrix().get("cancel_invoice_backed_pe_smoke"),
        },
        "js_hooks": {
            "NDIS Invoice Backed PE Smoke Run": "NDIS Invoice Backed PE Smoke Run" in doctype_js,
            "NDIS Invoice Backed PE Smoke Line": "NDIS Invoice Backed PE Smoke Line" in doctype_js,
        },
        "list_js_hooks": {
            "NDIS Invoice Backed PE Smoke Run": "NDIS Invoice Backed PE Smoke Run" in doctype_list_js,
            "NDIS Invoice Backed PE Smoke Line": "NDIS Invoice Backed PE Smoke Line" in doctype_list_js,
        },
        "payment_entry_submit_blocker_still_registered": "block_sandbox_payment_entry_submit" in pe_events_blob,
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "report_files": check_report_files(),
    }


def can_import_service():
    try:
        from ndis_finance.services.invoice_backed_pe_smoke import quick_invoice_backed_pe_smoke_summary

        return callable(quick_invoice_backed_pe_smoke_summary)
    except Exception:
        return False


def check_workspace_shortcuts():
    ws_name = frappe.db.exists("Workspace", WORKSPACE_NAME) or frappe.db.exists("Workspace", {"label": WORKSPACE_NAME})
    result = {shortcut["label"]: False for shortcut in WORKSPACE_SHORTCUTS}

    if not ws_name:
        return result

    ws = frappe.get_doc("Workspace", ws_name)
    text_blob = getattr(ws, "content", None) or ""

    for shortcut in WORKSPACE_SHORTCUTS:
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            result[shortcut["label"]] = True

    return result


def check_report_files():
    base_path = frappe.get_app_path("ndis_finance", "ndis_finance", "report")
    result = {}

    for report_name, folder in REPORT_FILE_MAP.items():
        folder_path = os.path.join(base_path, folder)
        result[report_name] = {
            "python": os.path.exists(os.path.join(folder_path, f"{folder}.py")),
            "javascript": os.path.exists(os.path.join(folder_path, f"{folder}.js")),
            "init": os.path.exists(os.path.join(folder_path, "__init__.py")),
        }

    return result
