import json
import os

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


PHASE4A_DOCTYPES = [
    "NDIS Sandbox Invoice Test Run",
    "NDIS Sandbox Invoice Test Line",
]

CUSTOM_FIELDS = {
    "Customer": [
        {
            "fieldname": "custom_ndis_sandbox_customer",
            "label": "NDIS Sandbox Customer",
            "fieldtype": "Check",
            "insert_after": "customer_name",
            "read_only": 1,
            "default": "0",
        },
        {
            "fieldname": "custom_ndis_sandbox_invoice_test_run",
            "label": "NDIS Sandbox Invoice Test Run",
            "fieldtype": "Link",
            "options": "NDIS Sandbox Invoice Test Run",
            "insert_after": "custom_ndis_sandbox_customer",
            "read_only": 1,
        },
    ],
    "Item": [
        {
            "fieldname": "custom_ndis_sandbox_item",
            "label": "NDIS Sandbox Item",
            "fieldtype": "Check",
            "insert_after": "item_name",
            "read_only": 1,
            "default": "0",
        },
        {
            "fieldname": "custom_ndis_sandbox_invoice_test_run",
            "label": "NDIS Sandbox Invoice Test Run",
            "fieldtype": "Link",
            "options": "NDIS Sandbox Invoice Test Run",
            "insert_after": "custom_ndis_sandbox_item",
            "read_only": 1,
        },
    ],
    "Sales Invoice": [
        {
            "fieldname": "custom_ndis_sandbox_invoice_section",
            "label": "NDIS Sandbox Invoice Test",
            "fieldtype": "Section Break",
            "insert_after": "remarks",
            "collapsible": 1,
        },
        {
            "fieldname": "custom_ndis_sandbox_test_invoice",
            "label": "NDIS Sandbox Test Invoice",
            "fieldtype": "Check",
            "insert_after": "custom_ndis_sandbox_invoice_section",
            "read_only": 1,
            "default": "0",
        },
        {
            "fieldname": "custom_ndis_sandbox_invoice_test_run",
            "label": "NDIS Sandbox Invoice Test Run",
            "fieldtype": "Link",
            "options": "NDIS Sandbox Invoice Test Run",
            "insert_after": "custom_ndis_sandbox_test_invoice",
            "read_only": 1,
        },
        {
            "fieldname": "custom_ndis_sandbox_invoice_acknowledgement",
            "label": "NDIS Sandbox Invoice Acknowledgement",
            "fieldtype": "Data",
            "insert_after": "custom_ndis_sandbox_invoice_test_run",
            "read_only": 1,
        },
    ],
}

REPORTS = [
    {
        "report_name": "NDIS Sandbox Invoice Test Run Report",
        "ref_doctype": "NDIS Sandbox Invoice Test Run",
    },
    {
        "report_name": "NDIS Sandbox Invoice Test Line Report",
        "ref_doctype": "NDIS Sandbox Invoice Test Line",
    },
]

REPORT_FILE_MAP = {
    "NDIS Sandbox Invoice Test Run Report": "ndis_sandbox_invoice_test_run_report",
    "NDIS Sandbox Invoice Test Line Report": "ndis_sandbox_invoice_test_line_report",
}

REPORT_ROLES = [
    "System Manager",
    "NDIS CFO",
    "NDIS Finance Manager",
    "NDIS Finance Officer",
    "NDIS Finance Read Only",
]

DOC_PERM_MATRIX = {
    "NDIS Sandbox Invoice Test Run": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Sandbox Invoice Test Line": {
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
        "label": "Sandbox Invoice Test Runs",
        "type": "DocType",
        "link_to": "NDIS Sandbox Invoice Test Run",
    },
    {
        "label": "Sandbox Invoice Test Lines",
        "type": "DocType",
        "link_to": "NDIS Sandbox Invoice Test Line",
    },
    {
        "label": "Sandbox Invoice Test Run Report",
        "type": "Report",
        "link_to": "NDIS Sandbox Invoice Test Run Report",
    },
    {
        "label": "Sandbox Invoice Test Line Report",
        "type": "Report",
        "link_to": "NDIS Sandbox Invoice Test Line Report",
    },
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_test_run_doctype()
    create_test_line_doctype()
    create_custom_fields(CUSTOM_FIELDS, update=True)
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Payment Entry Sandbox Completion Gate",
        "NDIS Payment Entry Allocation Preview",
        "NDIS Sandbox Payment Entry Run",
        "Customer",
        "Item",
        "Sales Invoice",
        "Account",
        "Company",
        "Report",
        "Workspace",
    ]
    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]

    if missing:
        frappe.throw(
            _("Phase 4A requires Phase 3E and ERPNext accounting base DocTypes. Missing: {0}").format(
                ", ".join(missing)
            )
        )


def create_test_run_doctype():
    _create_doctype(
        name="NDIS Sandbox Invoice Test Run",
        autoname="field:run_id",
        title_field="run_id",
        fields=[
            {"fieldname": "run_id", "label": "Run ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nCreated Draft Invoice\nSubmitted Invoice Created\nBlocked\nCancelled\nFailed", "default": "Draft", "in_list_view": 1},
            {"fieldname": "test_mode", "label": "Test Mode", "fieldtype": "Select", "options": "\nDraft Invoice Only\nSubmitted Sandbox Invoice", "default": "Draft Invoice Only", "in_list_view": 1},
            {"fieldname": "sandbox_only", "label": "Sandbox Only", "fieldtype": "Check", "default": "1", "read_only": 1},
            {"fieldname": "site_section", "label": "Site / Config", "fieldtype": "Section Break"},
            {"fieldname": "site_name", "label": "Site Name", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "sandbox_config_enabled", "label": "Sandbox Config Enabled", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "production_mode_detected", "label": "Production Mode Detected", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "source_section", "label": "Created Records", "fieldtype": "Section Break"},
            {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company"},
            {"fieldname": "customer", "label": "Sandbox Customer", "fieldtype": "Link", "options": "Customer", "in_list_view": 1},
            {"fieldname": "item", "label": "Sandbox Item", "fieldtype": "Link", "options": "Item"},
            {"fieldname": "sales_invoice", "label": "Sandbox Sales Invoice", "fieldtype": "Link", "options": "Sales Invoice", "in_list_view": 1},
            {"fieldname": "sales_invoice_docstatus", "label": "Sales Invoice Docstatus", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "sales_invoice_outstanding_amount", "label": "Outstanding Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "accounting_section", "label": "Accounting Mapping Used", "fieldtype": "Section Break"},
            {"fieldname": "receivable_account", "label": "Receivable Account", "fieldtype": "Link", "options": "Account"},
            {"fieldname": "income_account", "label": "Income Account", "fieldtype": "Link", "options": "Account"},
            {"fieldname": "cost_center", "label": "Cost Center", "fieldtype": "Link", "options": "Cost Center"},
            {"fieldname": "invoice_amount", "label": "Invoice Amount", "fieldtype": "Currency", "default": "100"},
            {"fieldname": "currency", "label": "Currency", "fieldtype": "Link", "options": "Currency"},
            {"fieldname": "gl_section", "label": "GL Evidence", "fieldtype": "Section Break"},
            {"fieldname": "expected_gl_from_submitted_invoice", "label": "Expected GL From Submitted Invoice", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "linked_gl_entry_count", "label": "Linked GL Entry Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "unrelated_gl_entry_count_today", "label": "Unrelated GL Entry Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "control_section", "label": "Acknowledgement", "fieldtype": "Section Break"},
            {"fieldname": "required_acknowledgement", "label": "Required Acknowledgement", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "acknowledgement", "label": "Acknowledgement", "fieldtype": "Data"},
            {"fieldname": "acknowledgement_ok", "label": "Acknowledgement OK", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "audit_section", "label": "Audit", "fieldtype": "Section Break"},
            {"fieldname": "created_on", "label": "Created On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "created_by_user", "label": "Created By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "cancelled_on", "label": "Cancelled On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "cancelled_by", "label": "Cancelled By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "validation_log", "label": "Validation Log", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
        ],
    )


def create_test_line_doctype():
    _create_doctype(
        name="NDIS Sandbox Invoice Test Line",
        autoname="hash",
        title_field="record_name",
        fields=[
            {"fieldname": "test_run", "label": "Test Run", "fieldtype": "Link", "options": "NDIS Sandbox Invoice Test Run", "reqd": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nCreated\nReused\nSubmitted\nBlocked\nCancelled", "default": "Created", "in_list_view": 1},
            {"fieldname": "line_no", "label": "Line No", "fieldtype": "Int"},
            {"fieldname": "record_doctype", "label": "Record DocType", "fieldtype": "Link", "options": "DocType", "in_list_view": 1},
            {"fieldname": "record_name", "label": "Record Name", "fieldtype": "Dynamic Link", "options": "record_doctype", "in_list_view": 1},
            {"fieldname": "record_docstatus", "label": "Docstatus", "fieldtype": "Int"},
            {"fieldname": "amount", "label": "Amount", "fieldtype": "Currency"},
            {"fieldname": "gl_entry_count", "label": "GL Entry Count", "fieldtype": "Int"},
            {"fieldname": "action_taken", "label": "Action Taken", "fieldtype": "Small Text"},
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

    if "Sandbox Invoice Test Data" not in text_blob:
        content.append(
            {
                "id": "ndis_sandbox_invoice_test_data_heading",
                "type": "header",
                "data": {"text": "Sandbox Invoice Test Data", "col": 12},
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
    doctypes = {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE4A_DOCTYPES}
    reports = {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS}
    custom_fields = {}

    for dt, fields in CUSTOM_FIELDS.items():
        custom_fields[dt] = {
            field["fieldname"]: bool(frappe.db.exists("Custom Field", {"dt": dt, "fieldname": field["fieldname"]}))
            for field in fields
        }

    permissions = {}
    for dt in PHASE4A_DOCTYPES:
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
    si_events_blob = json.dumps(doc_events.get("Sales Invoice", {}), default=str)

    return {
        "doctypes": doctypes,
        "reports": reports,
        "custom_fields": custom_fields,
        "permissions": permissions,
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "create_sandbox_invoice_test_data": permission_matrix().get("create_sandbox_invoice_test_data"),
            "cancel_sandbox_invoice_test_run": permission_matrix().get("cancel_sandbox_invoice_test_run"),
        },
        "js_hooks": {
            "NDIS Sandbox Invoice Test Run": "NDIS Sandbox Invoice Test Run" in doctype_js,
            "NDIS Sandbox Invoice Test Line": "NDIS Sandbox Invoice Test Line" in doctype_js,
        },
        "list_js_hooks": {
            "NDIS Sandbox Invoice Test Run": "NDIS Sandbox Invoice Test Run" in doctype_list_js,
            "NDIS Sandbox Invoice Test Line": "NDIS Sandbox Invoice Test Line" in doctype_list_js,
        },
        "sales_invoice_submit_safety_registered": "block_unacknowledged_sandbox_sales_invoice_submit" in si_events_blob,
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "report_files": check_report_files(),
    }


def can_import_service():
    try:
        from ndis_finance.services.sandbox_invoice_test_harness import quick_sandbox_invoice_test_summary

        return callable(quick_sandbox_invoice_test_summary)
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
