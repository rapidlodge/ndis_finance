import json

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from ndis_finance.services.permissions import permission_matrix
from ndis_finance.setup.install import MODULE, _create_doctype


PHASE1T_DOCTYPES = [
    "NDIS Payroll Cost Import",
    "NDIS Payroll Cost Import Line",
]

CUSTOM_FIELDS = {
    "Employee": [
        "custom_ndis_payroll_costing_enabled",
        "custom_ndis_default_house",
        "custom_ndis_payroll_cost_allocation_method",
    ],
    "NDIS Cost Pool": [
        "payroll_cost_import",
        "payroll_cost_import_line",
        "au_payroll_run_log",
    ],
}

DOC_PERM_MATRIX = {
    "NDIS Payroll Cost Import": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Payroll Cost Import Line": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
}


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_payroll_cost_import_doctype()
    create_payroll_cost_import_line_doctype()
    create_phase1t_custom_fields()
    harden_permissions()
    add_workspace_shortcut()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Cost Pool",
        "NDIS Cost Allocation Entry",
        "NDIS House",
        "Employee",
        "Company",
        "Workspace",
        "AU Payroll Run Log",
        "AU Payroll Run Detail",
    ]

    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]
    if missing:
        frappe.throw(
            _("Phase 1T requires Phase 1R and au_payroll. Missing DocTypes: {0}").format(
                ", ".join(missing)
            )
        )


def create_payroll_cost_import_doctype():
    _create_doctype(
        name="NDIS Payroll Cost Import",
        autoname="field:import_id",
        title_field="import_id",
        fields=[
            field("import_id", "Import ID", "Data", reqd=1, unique=1, in_list_view=1),
            field(
                "status",
                "Status",
                "Select",
                options="\nDraft\nImported\nAllocated\nPartially Allocated\nCancelled\nFailed",
                default="Draft",
                in_list_view=1,
            ),
            field(
                "au_payroll_run_log",
                "AU Payroll Run Log",
                "Link",
                options="AU Payroll Run Log",
                reqd=1,
                in_list_view=1,
            ),
            field("company", "Company", "Link", options="Company", in_list_view=1),
            field("period_start", "Period Start", "Date", in_list_view=1),
            field("period_end", "Period End", "Date", in_list_view=1),
            field("default_house", "Default NDIS House", "Link", options="NDIS House"),
            field("settings_section", "Import Settings", "Section Break"),
            field(
                "cost_basis",
                "Cost Basis",
                "Select",
                options="\nGross + Employer Super\nGross Only\nEmployer Super Only\nEstimated Net Pay Only",
                default="Gross + Employer Super",
                in_list_view=1,
            ),
            field(
                "allocation_method",
                "Cost Pool Allocation Method",
                "Select",
                options="\nEqual Participant Split\nClaim Amount Share\nPaid Amount Share\nHouse Only",
                default="Paid Amount Share",
                in_list_view=1,
            ),
            field(
                "include_only_payroll_safe_rows",
                "Include Only Payroll Safe Rows",
                "Check",
                default="1",
            ),
            field("auto_allocate_cost_pools", "Auto Allocate Cost Pools", "Check", default="0"),
            field("replace_existing", "Replace Existing Import", "Check", default="0"),
            field("summary_section", "Summary", "Section Break"),
            field("line_count", "Line Count", "Int", read_only=1, in_list_view=1),
            field("mapped_line_count", "Mapped Line Count", "Int", read_only=1),
            field("unmapped_line_count", "Unmapped Line Count", "Int", read_only=1),
            field("cost_pool_count", "Cost Pool Count", "Int", read_only=1),
            field("allocated_cost_pool_count", "Allocated Cost Pool Count", "Int", read_only=1),
            field("amount_section", "Amounts", "Section Break"),
            field("total_gross_amount", "Total Gross Amount", "Currency", read_only=1),
            field(
                "total_employer_super_liability",
                "Total Employer Super Liability",
                "Currency",
                read_only=1,
            ),
            field("total_estimated_net_pay", "Total Estimated Net Pay", "Currency", read_only=1),
            field(
                "total_import_cost_amount",
                "Total Import Cost Amount",
                "Currency",
                read_only=1,
                in_list_view=1,
            ),
            field("audit_section", "Audit", "Section Break"),
            field("imported_on", "Imported On", "Datetime", read_only=1),
            field("imported_by", "Imported By", "Link", options="User", read_only=1),
            field("allocated_on", "Allocated On", "Datetime", read_only=1),
            field("cancelled_on", "Cancelled On", "Datetime", read_only=1),
            field("cancelled_by", "Cancelled By", "Link", options="User", read_only=1),
            field("warning_log", "Warning Log", "Long Text", read_only=1),
            field("notes", "Notes", "Small Text"),
        ],
    )


def create_payroll_cost_import_line_doctype():
    _create_doctype(
        name="NDIS Payroll Cost Import Line",
        autoname="hash",
        title_field="payroll_cost_import",
        fields=[
            field(
                "payroll_cost_import",
                "Payroll Cost Import",
                "Link",
                options="NDIS Payroll Cost Import",
                reqd=1,
                in_list_view=1,
            ),
            field(
                "status",
                "Status",
                "Select",
                options="\nImported\nMapped\nUnmapped\nCost Pool Created\nAllocated\nSkipped\nCancelled\nError",
                default="Imported",
                in_list_view=1,
            ),
            field("source_section", "AU Payroll Source", "Section Break"),
            field(
                "au_payroll_run_log",
                "AU Payroll Run Log",
                "Link",
                options="AU Payroll Run Log",
                in_list_view=1,
            ),
            field("au_payroll_run_detail_row", "AU Payroll Run Detail Row", "Data"),
            field("employee", "Employee", "Link", options="Employee", in_list_view=1),
            field("employee_name", "Employee Name", "Data"),
            field("salary_slip", "Salary Slip", "Link", options="Salary Slip"),
            field("payroll_safe_to_use", "Payroll Safe To Use", "Check", read_only=1),
            field("row_status", "AU Payroll Row Status", "Data"),
            field("mapping_section", "NDIS Mapping", "Section Break"),
            field("house", "NDIS House", "Link", options="NDIS House", in_list_view=1),
            field("cost_pool", "NDIS Cost Pool", "Link", options="NDIS Cost Pool", in_list_view=1),
            field("allocation_method", "Allocation Method", "Data"),
            field("amount_section", "Amounts", "Section Break"),
            field("gross_amount", "Gross Amount", "Currency"),
            field("employer_super_liability", "Employer Super Liability", "Currency"),
            field("estimated_net_pay", "Estimated Net Pay", "Currency"),
            field("import_cost_amount", "Import Cost Amount", "Currency", in_list_view=1),
            field("note_section", "Notes", "Section Break"),
            field("mapping_note", "Mapping Note", "Small Text"),
            field("error_log", "Error Log", "Long Text", read_only=1),
        ],
    )


def field(fieldname, label, fieldtype, **kwargs):
    row = {"fieldname": fieldname, "label": label, "fieldtype": fieldtype}
    row.update(kwargs)
    return row


def create_phase1t_custom_fields():
    custom_fields = {
        "Employee": [
            {
                "fieldname": "custom_ndis_payroll_costing_section",
                "label": "NDIS Payroll Costing",
                "fieldtype": "Section Break",
                "insert_after": "status",
                "collapsible": 1,
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_payroll_costing_enabled",
                "label": "NDIS Payroll Costing Enabled",
                "fieldtype": "Check",
                "default": "1",
                "insert_after": "custom_ndis_payroll_costing_section",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_default_house",
                "label": "Default NDIS House",
                "fieldtype": "Link",
                "options": "NDIS House",
                "insert_after": "custom_ndis_payroll_costing_enabled",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_payroll_cost_allocation_method",
                "label": "Payroll Cost Allocation Method",
                "fieldtype": "Select",
                "options": "\nEqual Participant Split\nClaim Amount Share\nPaid Amount Share\nHouse Only",
                "default": "Paid Amount Share",
                "insert_after": "custom_ndis_default_house",
                "module": MODULE,
            },
        ],
        "NDIS Cost Pool": [
            {
                "fieldname": "payroll_bridge_section",
                "label": "Payroll Bridge",
                "fieldtype": "Section Break",
                "insert_after": "warning_log",
                "collapsible": 1,
                "module": MODULE,
            },
            {
                "fieldname": "payroll_cost_import",
                "label": "Payroll Cost Import",
                "fieldtype": "Link",
                "options": "NDIS Payroll Cost Import",
                "insert_after": "payroll_bridge_section",
                "read_only": 1,
                "module": MODULE,
            },
            {
                "fieldname": "payroll_cost_import_line",
                "label": "Payroll Cost Import Line",
                "fieldtype": "Link",
                "options": "NDIS Payroll Cost Import Line",
                "insert_after": "payroll_cost_import",
                "read_only": 1,
                "module": MODULE,
            },
            {
                "fieldname": "au_payroll_run_log",
                "label": "AU Payroll Run Log",
                "fieldtype": "Link",
                "options": "AU Payroll Run Log",
                "insert_after": "payroll_cost_import_line",
                "read_only": 1,
                "module": MODULE,
            },
        ],
    }
    create_custom_fields(custom_fields, update=True)


def harden_permissions():
    for doctype, role_map in DOC_PERM_MATRIX.items():
        if not frappe.db.exists("DocType", doctype):
            continue

        doc = frappe.get_doc("DocType", doctype)
        doc.allow_import = 1
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
        base.update(
            {
                "read": 1,
                "write": 1,
                "create": 1,
                "delete": 1,
                "report": 1,
                "export": 1,
                "import": 1,
                "share": 1,
                "print": 1,
                "email": 1,
            }
        )
    elif profile == "full_no_delete":
        base.update(
            {
                "read": 1,
                "write": 1,
                "create": 1,
                "report": 1,
                "export": 1,
                "import": 1,
                "share": 1,
                "print": 1,
                "email": 1,
            }
        )
    elif profile == "read_report_export":
        base.update({"read": 1, "report": 1, "export": 1, "print": 1})
    elif profile == "read_report":
        base.update({"read": 1, "report": 1})
    else:
        frappe.throw(_("Unknown permission profile: {0}").format(profile))

    return base


def add_workspace_shortcut():
    ws_name = frappe.db.exists("Workspace", "NDIS Finance") or frappe.db.exists(
        "Workspace",
        {"label": "NDIS Finance"},
    )
    if not ws_name:
        return

    ws = frappe.get_doc("Workspace", ws_name)
    shortcuts = [
        {
            "label": "Payroll Cost Imports",
            "link_to": "NDIS Payroll Cost Import",
            "type": "DocType",
        },
        {
            "label": "Payroll Cost Import Lines",
            "link_to": "NDIS Payroll Cost Import Line",
            "type": "DocType",
        },
    ]

    add_shortcuts_to_content_json(ws, shortcuts)
    add_shortcuts_to_child_tables(ws, shortcuts)
    ws.save(ignore_permissions=True)


def add_shortcuts_to_content_json(ws, shortcuts):
    if not ws.meta.has_field("content"):
        return

    try:
        content = json.loads(ws.content or "[]")
    except Exception:
        content = []

    text_blob = json.dumps(content)
    if "Payroll Cost Bridge" not in text_blob:
        content.append(
            {
                "id": "ndis_payroll_cost_bridge_heading",
                "type": "header",
                "data": {"text": "Payroll Cost Bridge", "col": 12},
            }
        )

    for shortcut in shortcuts:
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


def add_shortcuts_to_child_tables(ws, shortcuts):
    for fieldname in ["shortcuts", "links"]:
        if not ws.meta.has_field(fieldname):
            continue

        existing_blob = ""
        for row in getattr(ws, fieldname, []) or []:
            existing_blob += " " + str(getattr(row, "label", ""))
            existing_blob += " " + str(getattr(row, "link_to", ""))

        for shortcut in shortcuts:
            if shortcut["label"] in existing_blob or shortcut["link_to"] in existing_blob:
                continue

            row = ws.append(fieldname, {})
            set_child_value(row, "label", shortcut["label"])
            set_child_value(row, "link_to", shortcut["link_to"])
            set_child_value(row, "type", shortcut["type"] if fieldname == "shortcuts" else "Link")
            set_child_value(row, "link_type", shortcut["type"])
            set_child_value(row, "open_in_new_tab", 0)


def set_child_value(row, fieldname, value):
    if row.meta.has_field(fieldname):
        setattr(row, fieldname, value)


@frappe.whitelist()
def health_check():
    doctypes = {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE1T_DOCTYPES}
    au_payroll_doctypes = {
        "AU Payroll Run Log": bool(frappe.db.exists("DocType", "AU Payroll Run Log")),
        "AU Payroll Run Detail": bool(frappe.db.exists("DocType", "AU Payroll Run Detail")),
    }

    custom_fields = {}
    for dt, fields in CUSTOM_FIELDS.items():
        custom_fields[dt] = {
            fieldname: bool(
                frappe.db.exists("Custom Field", {"dt": dt, "fieldname": fieldname})
            )
            for fieldname in fields
        }

    permissions = {}
    for dt in PHASE1T_DOCTYPES:
        permissions[dt] = frappe.get_all(
            "DocPerm",
            filters={"parent": dt},
            fields=["role", "read", "write", "create", "delete", "report", "export"],
            order_by="role asc",
        )

    hooks = frappe.get_hooks()
    doctype_js = hooks.get("doctype_js", {})
    doctype_list_js = hooks.get("doctype_list_js", {})

    return {
        "doctypes": doctypes,
        "au_payroll_doctypes": au_payroll_doctypes,
        "custom_fields": custom_fields,
        "permissions": permissions,
        "service_import": can_import_service(),
        "action_permissions": {
            "import_payroll_costs": permission_matrix().get("import_payroll_costs"),
            "cancel_payroll_cost_import": permission_matrix().get(
                "cancel_payroll_cost_import"
            ),
        },
        "js_hooks": {
            "NDIS Payroll Cost Import": "NDIS Payroll Cost Import" in doctype_js,
            "NDIS Payroll Cost Import Line": "NDIS Payroll Cost Import Line" in doctype_js,
        },
        "list_js_hooks": {
            "NDIS Payroll Cost Import": "NDIS Payroll Cost Import" in doctype_list_js,
            "NDIS Payroll Cost Import Line": "NDIS Payroll Cost Import Line"
            in doctype_list_js,
        },
        "workspace_shortcuts": check_workspace_shortcuts(),
    }


def check_workspace_shortcuts():
    ws_name = frappe.db.exists("Workspace", "NDIS Finance") or frappe.db.exists(
        "Workspace",
        {"label": "NDIS Finance"},
    )
    result = {
        "Payroll Cost Imports": False,
        "Payroll Cost Import Lines": False,
    }

    if not ws_name:
        return result

    ws = frappe.get_doc("Workspace", ws_name)
    text_blob = getattr(ws, "content", "") or ""

    for fieldname in ["shortcuts", "links"]:
        if not ws.meta.has_field(fieldname):
            continue

        for row in getattr(ws, fieldname, []) or []:
            text_blob += " " + str(getattr(row, "label", ""))
            text_blob += " " + str(getattr(row, "link_to", ""))

    for label in result:
        result[label] = label in text_blob

    return result


def can_import_service():
    try:
        from ndis_finance.services.payroll_cost_bridge import (
            quick_payroll_cost_import_summary,
        )

        return callable(quick_payroll_cost_import_summary)
    except Exception:
        return False
