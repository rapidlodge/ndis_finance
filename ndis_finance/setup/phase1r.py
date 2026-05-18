import json

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from ndis_finance.services.permissions import permission_matrix
from ndis_finance.setup.install import MODULE, _create_doctype


PHASE1R_DOCTYPES = [
    "NDIS Cost Pool",
    "NDIS Cost Allocation Entry",
]

CUSTOM_FIELDS = {
    "NDIS House": [
        "custom_ndis_cost_center",
        "custom_ndis_default_cost_allocation_method",
        "custom_ndis_active_for_profitability",
    ],
    "Customer": [
        "custom_ndis_default_house",
        "custom_ndis_profitability_enabled",
    ],
}

DOC_PERM_MATRIX = {
    "NDIS Cost Pool": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Cost Allocation Entry": {
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
    create_cost_pool_doctype()
    create_cost_allocation_entry_doctype()
    create_phase1r_custom_fields()
    harden_cost_permissions()
    add_workspace_shortcut()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Claim Line",
        "NDIS Claim Batch",
        "NDIS House",
        "Customer",
        "Company",
        "Cost Center",
        "Workspace",
    ]

    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]
    if missing:
        frappe.throw(
            _("Phase 1R requires previous phases. Missing DocTypes: {0}").format(
                ", ".join(missing)
            )
        )


def create_cost_pool_doctype():
    _create_doctype(
        name="NDIS Cost Pool",
        autoname="field:cost_pool_id",
        title_field="cost_pool_id",
        fields=[
            {
                "fieldname": "cost_pool_id",
                "label": "Cost Pool ID",
                "fieldtype": "Data",
                "reqd": 1,
                "unique": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "status",
                "label": "Status",
                "fieldtype": "Select",
                "options": "\nDraft\nAllocated\nPartially Allocated\nCancelled",
                "default": "Draft",
                "in_list_view": 1,
            },
            {
                "fieldname": "cost_type",
                "label": "Cost Type",
                "fieldtype": "Select",
                "options": "\nPayroll\nRent\nUtilities\nFood\nTransport\nTravel\nTraining\nInsurance\nMaintenance\nAdministration\nNon-Billable Support\nOther",
                "default": "Other",
                "in_list_view": 1,
            },
            {
                "fieldname": "allocation_method",
                "label": "Allocation Method",
                "fieldtype": "Select",
                "options": "\nEqual Participant Split\nClaim Amount Share\nPaid Amount Share\nDirect Participant\nHouse Only",
                "default": "Equal Participant Split",
                "in_list_view": 1,
            },
            {
                "fieldname": "company",
                "label": "Company",
                "fieldtype": "Link",
                "options": "Company",
                "in_list_view": 1,
            },
            {
                "fieldname": "house",
                "label": "NDIS House",
                "fieldtype": "Link",
                "options": "NDIS House",
                "in_list_view": 1,
            },
            {
                "fieldname": "participant",
                "label": "Direct Participant",
                "fieldtype": "Link",
                "options": "Customer",
            },
            {
                "fieldname": "cost_center",
                "label": "Cost Center",
                "fieldtype": "Link",
                "options": "Cost Center",
            },
            {
                "fieldname": "period_section",
                "label": "Period",
                "fieldtype": "Section Break",
            },
            {
                "fieldname": "period_start",
                "label": "Period Start",
                "fieldtype": "Date",
                "reqd": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "period_end",
                "label": "Period End",
                "fieldtype": "Date",
                "reqd": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "amount_section",
                "label": "Amounts",
                "fieldtype": "Section Break",
            },
            {
                "fieldname": "total_cost_amount",
                "label": "Total Cost Amount",
                "fieldtype": "Currency",
                "reqd": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "allocated_amount",
                "label": "Allocated Amount",
                "fieldtype": "Currency",
                "read_only": 1,
            },
            {
                "fieldname": "unallocated_amount",
                "label": "Unallocated Amount",
                "fieldtype": "Currency",
                "read_only": 1,
            },
            {
                "fieldname": "allocation_count",
                "label": "Allocation Count",
                "fieldtype": "Int",
                "read_only": 1,
            },
            {
                "fieldname": "source_section",
                "label": "Source / Reference",
                "fieldtype": "Section Break",
            },
            {
                "fieldname": "source_doctype",
                "label": "Source DocType",
                "fieldtype": "Link",
                "options": "DocType",
            },
            {
                "fieldname": "source_name",
                "label": "Source Name",
                "fieldtype": "Dynamic Link",
                "options": "source_doctype",
            },
            {
                "fieldname": "source_reference",
                "label": "Source Reference",
                "fieldtype": "Data",
            },
            {
                "fieldname": "audit_section",
                "label": "Audit",
                "fieldtype": "Section Break",
            },
            {
                "fieldname": "allocated_on",
                "label": "Allocated On",
                "fieldtype": "Datetime",
                "read_only": 1,
            },
            {
                "fieldname": "allocated_by",
                "label": "Allocated By",
                "fieldtype": "Link",
                "options": "User",
                "read_only": 1,
            },
            {
                "fieldname": "cancelled_on",
                "label": "Cancelled On",
                "fieldtype": "Datetime",
                "read_only": 1,
            },
            {
                "fieldname": "cancelled_by",
                "label": "Cancelled By",
                "fieldtype": "Link",
                "options": "User",
                "read_only": 1,
            },
            {
                "fieldname": "notes",
                "label": "Notes",
                "fieldtype": "Small Text",
            },
            {
                "fieldname": "warning_log",
                "label": "Warning Log",
                "fieldtype": "Long Text",
                "read_only": 1,
            },
        ],
    )


def create_cost_allocation_entry_doctype():
    _create_doctype(
        name="NDIS Cost Allocation Entry",
        autoname="hash",
        title_field="cost_pool",
        fields=[
            {
                "fieldname": "cost_pool",
                "label": "Cost Pool",
                "fieldtype": "Link",
                "options": "NDIS Cost Pool",
                "reqd": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "status",
                "label": "Status",
                "fieldtype": "Select",
                "options": "\nActive\nCancelled",
                "default": "Active",
                "in_list_view": 1,
            },
            {
                "fieldname": "cost_type",
                "label": "Cost Type",
                "fieldtype": "Data",
                "in_list_view": 1,
            },
            {
                "fieldname": "allocation_method",
                "label": "Allocation Method",
                "fieldtype": "Data",
            },
            {
                "fieldname": "company",
                "label": "Company",
                "fieldtype": "Link",
                "options": "Company",
            },
            {
                "fieldname": "house",
                "label": "NDIS House",
                "fieldtype": "Link",
                "options": "NDIS House",
                "in_list_view": 1,
            },
            {
                "fieldname": "participant",
                "label": "Participant",
                "fieldtype": "Link",
                "options": "Customer",
                "in_list_view": 1,
            },
            {
                "fieldname": "period_start",
                "label": "Period Start",
                "fieldtype": "Date",
            },
            {
                "fieldname": "period_end",
                "label": "Period End",
                "fieldtype": "Date",
            },
            {
                "fieldname": "basis_section",
                "label": "Basis",
                "fieldtype": "Section Break",
            },
            {
                "fieldname": "gross_claim_amount",
                "label": "Gross Claim Amount",
                "fieldtype": "Currency",
                "read_only": 1,
            },
            {
                "fieldname": "paid_amount",
                "label": "Paid Amount",
                "fieldtype": "Currency",
                "read_only": 1,
            },
            {
                "fieldname": "claim_line_count",
                "label": "Claim Line Count",
                "fieldtype": "Int",
                "read_only": 1,
            },
            {
                "fieldname": "allocation_basis_amount",
                "label": "Allocation Basis Amount",
                "fieldtype": "Currency",
                "read_only": 1,
            },
            {
                "fieldname": "allocation_percent",
                "label": "Allocation Percent",
                "fieldtype": "Percent",
                "read_only": 1,
            },
            {
                "fieldname": "amount_section",
                "label": "Allocated Cost",
                "fieldtype": "Section Break",
            },
            {
                "fieldname": "allocated_cost_amount",
                "label": "Allocated Cost Amount",
                "fieldtype": "Currency",
                "in_list_view": 1,
            },
            {
                "fieldname": "estimated_margin_amount",
                "label": "Estimated Margin Amount",
                "fieldtype": "Currency",
                "read_only": 1,
            },
            {
                "fieldname": "estimated_margin_percent",
                "label": "Estimated Margin %",
                "fieldtype": "Percent",
                "read_only": 1,
            },
            {
                "fieldname": "allocation_note",
                "label": "Allocation Note",
                "fieldtype": "Small Text",
            },
        ],
    )


def create_phase1r_custom_fields():
    custom_fields = {
        "NDIS House": [
            {
                "fieldname": "custom_ndis_costing_section",
                "label": "NDIS Costing",
                "fieldtype": "Section Break",
                "insert_after": "modified_by",
                "collapsible": 1,
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_cost_center",
                "label": "NDIS Cost Center",
                "fieldtype": "Link",
                "options": "Cost Center",
                "insert_after": "custom_ndis_costing_section",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_default_cost_allocation_method",
                "label": "Default Cost Allocation Method",
                "fieldtype": "Select",
                "options": "\nEqual Participant Split\nClaim Amount Share\nPaid Amount Share\nHouse Only",
                "default": "Equal Participant Split",
                "insert_after": "custom_ndis_cost_center",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_active_for_profitability",
                "label": "Active For Profitability",
                "fieldtype": "Check",
                "default": "1",
                "insert_after": "custom_ndis_default_cost_allocation_method",
                "module": MODULE,
            },
        ],
        "Customer": [
            {
                "fieldname": "custom_ndis_profitability_section",
                "label": "NDIS Profitability",
                "fieldtype": "Section Break",
                "insert_after": "disabled",
                "collapsible": 1,
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_default_house",
                "label": "Default NDIS House",
                "fieldtype": "Link",
                "options": "NDIS House",
                "insert_after": "custom_ndis_profitability_section",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_profitability_enabled",
                "label": "NDIS Profitability Enabled",
                "fieldtype": "Check",
                "default": "1",
                "insert_after": "custom_ndis_default_house",
                "module": MODULE,
            },
        ],
    }

    create_custom_fields(custom_fields, update=True)


def harden_cost_permissions():
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
        base.update(
            {
                "read": 1,
                "write": 1,
                "create": 1,
                "delete": 1,
                "report": 1,
                "export": 1,
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
                "delete": 0,
                "report": 1,
                "export": 1,
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
        {"label": "Cost Pools", "link_to": "NDIS Cost Pool", "type": "DocType"},
        {
            "label": "Cost Allocation Entries",
            "link_to": "NDIS Cost Allocation Entry",
            "type": "DocType",
        },
    ]

    if ws.meta.has_field("content"):
        try:
            content = json.loads(ws.content or "[]")
        except Exception:
            content = []

        text_blob = json.dumps(content)
        if "Cost Allocation" not in text_blob:
            content.append(
                {
                    "id": "ndis_cost_allocation_heading",
                    "type": "header",
                    "data": {"text": "Cost Allocation", "col": 12},
                }
            )

        for shortcut in shortcuts:
            if shortcut["label"] not in text_blob and shortcut["link_to"] not in text_blob:
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
            if fieldname == "shortcuts":
                set_child_value(row, "type", shortcut["type"])
            else:
                set_child_value(row, "type", "Link")
                set_child_value(row, "link_type", shortcut["type"])
            set_child_value(row, "open_in_new_tab", 0)

    ws.save(ignore_permissions=True)


def set_child_value(row, fieldname, value):
    if row.meta.has_field(fieldname):
        setattr(row, fieldname, value)


@frappe.whitelist()
def health_check():
    doctypes = {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE1R_DOCTYPES}

    custom_fields = {}
    for dt, fields in CUSTOM_FIELDS.items():
        custom_fields[dt] = {
            fieldname: bool(
                frappe.db.exists("Custom Field", {"dt": dt, "fieldname": fieldname})
            )
            for fieldname in fields
        }

    permissions = {}
    for dt in PHASE1R_DOCTYPES:
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
        "custom_fields": custom_fields,
        "permissions": permissions,
        "service_import": can_import_service(),
        "action_permissions": {
            "manage_cost_pool": permission_matrix().get("manage_cost_pool"),
            "allocate_cost_pool": permission_matrix().get("allocate_cost_pool"),
            "cancel_cost_pool": permission_matrix().get("cancel_cost_pool"),
        },
        "js_hooks": {
            "NDIS Cost Pool": "NDIS Cost Pool" in doctype_js,
            "NDIS Cost Allocation Entry": "NDIS Cost Allocation Entry" in doctype_js,
        },
        "list_js_hooks": {
            "NDIS Cost Pool": "NDIS Cost Pool" in doctype_list_js,
            "NDIS Cost Allocation Entry": "NDIS Cost Allocation Entry" in doctype_list_js,
        },
    }


def can_import_service():
    try:
        from ndis_finance.services.cost_allocation import quick_cost_allocation_summary

        return callable(quick_cost_allocation_summary)
    except Exception:
        return False
