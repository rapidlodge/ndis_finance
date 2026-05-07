import json
import os

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from ndis_finance.services.permissions import permission_matrix
from ndis_finance.setup.install import MODULE, _create_doctype


PHASE1O_DOCTYPES = [
    "NDIS Claim Export",
    "NDIS Claim Export Line",
]

CUSTOM_FIELDS = {
    "NDIS Claim Batch": [
        "last_claim_export",
        "claim_export_count",
        "last_claim_export_on",
    ],
    "NDIS Claim Line": [
        "claim_export",
        "claim_export_line",
        "export_status",
        "exported_on",
    ],
}

DOC_PERM_MATRIX = {
    "NDIS Claim Export": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Claims Officer": "create_write_read_report",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Claim Export Line": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Claims Officer": "create_write_read_report",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
}


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_claim_export_doctype()
    create_claim_export_line_doctype()
    create_phase1o_custom_fields()
    harden_claim_export_permissions()
    add_workspace_shortcut()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Claim Batch",
        "NDIS Claim Line",
        "Sales Invoice",
        "Customer",
        "File",
        "Workspace",
    ]

    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]

    if missing:
        frappe.throw(
            _("Phase 1O requires previous phases. Missing DocTypes: {0}").format(
                ", ".join(missing)
            )
        )


def create_claim_export_doctype():
    _create_doctype(
        name="NDIS Claim Export",
        autoname="field:export_id",
        title_field="export_id",
        fields=[
            {
                "fieldname": "export_id",
                "label": "Export ID",
                "fieldtype": "Data",
                "reqd": 1,
                "unique": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "export_type",
                "label": "Export Type",
                "fieldtype": "Select",
                "options": "\nNDIA Claim CSV\nPlan Manager CSV\nSelf Managed CSV\nInternal Review CSV",
                "default": "NDIA Claim CSV",
                "in_list_view": 1,
            },
            {
                "fieldname": "status",
                "label": "Status",
                "fieldtype": "Select",
                "options": "\nDraft\nGenerated\nCancelled",
                "default": "Draft",
                "in_list_view": 1,
            },
            {
                "fieldname": "claim_batch",
                "label": "Claim Batch",
                "fieldtype": "Link",
                "options": "NDIS Claim Batch",
                "reqd": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "company",
                "label": "Company",
                "fieldtype": "Link",
                "options": "Company",
            },
            {
                "fieldname": "funding_source",
                "label": "Funding Source",
                "fieldtype": "Link",
                "options": "NDIS Funding Source",
                "in_list_view": 1,
            },
            {
                "fieldname": "claim_period_start",
                "label": "Claim Period Start",
                "fieldtype": "Date",
            },
            {
                "fieldname": "claim_period_end",
                "label": "Claim Period End",
                "fieldtype": "Date",
            },
            {
                "fieldname": "export_file",
                "label": "Export File",
                "fieldtype": "Attach",
                "read_only": 1,
            },
            {
                "fieldname": "amount_section",
                "label": "Amounts",
                "fieldtype": "Section Break",
            },
            {
                "fieldname": "line_count",
                "label": "Line Count",
                "fieldtype": "Int",
                "read_only": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "total_claim_amount",
                "label": "Total Claim Amount",
                "fieldtype": "Currency",
                "read_only": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "audit_section",
                "label": "Audit",
                "fieldtype": "Section Break",
            },
            {
                "fieldname": "generated_on",
                "label": "Generated On",
                "fieldtype": "Datetime",
                "read_only": 1,
            },
            {
                "fieldname": "generated_by",
                "label": "Generated By",
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
                "fieldname": "warning_log",
                "label": "Warning Log",
                "fieldtype": "Long Text",
                "read_only": 1,
            },
            {
                "fieldname": "notes",
                "label": "Notes",
                "fieldtype": "Small Text",
            },
        ],
    )


def create_claim_export_line_doctype():
    _create_doctype(
        name="NDIS Claim Export Line",
        autoname="hash",
        title_field="claim_export",
        fields=[
            {
                "fieldname": "claim_export",
                "label": "Claim Export",
                "fieldtype": "Link",
                "options": "NDIS Claim Export",
                "reqd": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "row_number",
                "label": "Row Number",
                "fieldtype": "Int",
                "in_list_view": 1,
            },
            {
                "fieldname": "claim_line",
                "label": "Claim Line",
                "fieldtype": "Link",
                "options": "NDIS Claim Line",
                "reqd": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "claim_batch",
                "label": "Claim Batch",
                "fieldtype": "Link",
                "options": "NDIS Claim Batch",
            },
            {
                "fieldname": "sales_invoice",
                "label": "Sales Invoice",
                "fieldtype": "Link",
                "options": "Sales Invoice",
                "in_list_view": 1,
            },
            {
                "fieldname": "sales_invoice_item",
                "label": "Sales Invoice Item Row ID",
                "fieldtype": "Data",
            },
            {
                "fieldname": "participant",
                "label": "Participant",
                "fieldtype": "Link",
                "options": "Customer",
                "in_list_view": 1,
            },
            {
                "fieldname": "house",
                "label": "NDIS House",
                "fieldtype": "Link",
                "options": "NDIS House",
            },
            {
                "fieldname": "funding_source",
                "label": "Funding Source",
                "fieldtype": "Link",
                "options": "NDIS Funding Source",
            },
            {
                "fieldname": "service_date",
                "label": "Service Date",
                "fieldtype": "Date",
                "in_list_view": 1,
            },
            {
                "fieldname": "support_item_number",
                "label": "Support Item Number",
                "fieldtype": "Data",
                "in_list_view": 1,
            },
            {
                "fieldname": "support_item_name",
                "label": "Support Item Name",
                "fieldtype": "Data",
            },
            {
                "fieldname": "qty",
                "label": "Qty",
                "fieldtype": "Float",
            },
            {
                "fieldname": "rate",
                "label": "Rate",
                "fieldtype": "Currency",
            },
            {
                "fieldname": "claim_amount",
                "label": "Claim Amount",
                "fieldtype": "Currency",
                "in_list_view": 1,
            },
            {
                "fieldname": "external_claim_reference",
                "label": "External Claim Reference",
                "fieldtype": "Data",
            },
            {
                "fieldname": "export_status",
                "label": "Export Status",
                "fieldtype": "Select",
                "options": "\nExported\nSkipped\nCancelled",
                "default": "Exported",
                "in_list_view": 1,
            },
            {
                "fieldname": "export_note",
                "label": "Export Note",
                "fieldtype": "Small Text",
            },
        ],
    )


def create_phase1o_custom_fields():
    custom_fields = {
        "NDIS Claim Batch": [
            {
                "fieldname": "last_claim_export",
                "label": "Last Claim Export",
                "fieldtype": "Link",
                "options": "NDIS Claim Export",
                "insert_after": "export_file",
                "read_only": 1,
                "module": MODULE,
            },
            {
                "fieldname": "claim_export_count",
                "label": "Claim Export Count",
                "fieldtype": "Int",
                "insert_after": "last_claim_export",
                "read_only": 1,
                "module": MODULE,
            },
            {
                "fieldname": "last_claim_export_on",
                "label": "Last Claim Export On",
                "fieldtype": "Datetime",
                "insert_after": "claim_export_count",
                "read_only": 1,
                "module": MODULE,
            },
        ],
        "NDIS Claim Line": [
            {
                "fieldname": "claim_export",
                "label": "Claim Export",
                "fieldtype": "Link",
                "options": "NDIS Claim Export",
                "insert_after": "remittance_import_line",
                "read_only": 1,
                "module": MODULE,
            },
            {
                "fieldname": "claim_export_line",
                "label": "Claim Export Line",
                "fieldtype": "Link",
                "options": "NDIS Claim Export Line",
                "insert_after": "claim_export",
                "read_only": 1,
                "module": MODULE,
            },
            {
                "fieldname": "export_status",
                "label": "Export Status",
                "fieldtype": "Select",
                "options": "\nNot Exported\nExported\nCancelled",
                "default": "Not Exported",
                "insert_after": "claim_export_line",
                "read_only": 1,
                "module": MODULE,
            },
            {
                "fieldname": "exported_on",
                "label": "Exported On",
                "fieldtype": "Datetime",
                "insert_after": "export_status",
                "read_only": 1,
                "module": MODULE,
            },
        ],
    }

    create_custom_fields(custom_fields, update=True)


def harden_claim_export_permissions():
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
                "report": 1,
                "export": 1,
                "share": 1,
                "print": 1,
                "email": 1,
            }
        )
    elif profile == "create_write_read_report":
        base.update(
            {
                "read": 1,
                "write": 1,
                "create": 1,
                "report": 1,
                "export": 1,
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
    label = "Claim Exports"
    link_to = "NDIS Claim Export"

    if ws.meta.has_field("content"):
        try:
            content = json.loads(ws.content or "[]")
        except Exception:
            content = []

        text_blob = json.dumps(content)

        if label not in text_blob and link_to not in text_blob:
            content.append(
                {
                    "id": "claim_exports",
                    "type": "shortcut",
                    "data": {
                        "label": label,
                        "link_to": link_to,
                        "type": "DocType",
                        "col": 3,
                    },
                }
            )

        ws.content = json.dumps(content)

    for fieldname in ["shortcuts", "links"]:
        if not ws.meta.has_field(fieldname):
            continue

        row_type = "DocType" if fieldname == "shortcuts" else "Link"
        existing = False
        for row in getattr(ws, fieldname, []) or []:
            if getattr(row, "label", None) == label or getattr(row, "link_to", None) == link_to:
                existing = True
                set_child_value(row, "label", label)
                set_child_value(row, "link_to", link_to)
                set_child_value(row, "type", row_type)
                set_child_value(row, "link_type", "DocType")
                set_child_value(row, "doc_view", "List")
                set_child_value(row, "open_in_new_tab", 0)

        if not existing:
            row = ws.append(fieldname, {})
            set_child_value(row, "label", label)
            set_child_value(row, "link_to", link_to)
            set_child_value(row, "type", row_type)
            set_child_value(row, "link_type", "DocType")
            set_child_value(row, "doc_view", "List")
            set_child_value(row, "open_in_new_tab", 0)

    ws.save(ignore_permissions=True)


def set_child_value(row, fieldname, value):
    if row.meta.has_field(fieldname):
        setattr(row, fieldname, value)


@frappe.whitelist()
def health_check():
    doctypes = {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE1O_DOCTYPES}

    custom_fields = {}
    for dt, fields in CUSTOM_FIELDS.items():
        custom_fields[dt] = {
            fieldname: bool(
                frappe.db.exists(
                    "Custom Field",
                    {"dt": dt, "fieldname": fieldname},
                )
            )
            for fieldname in fields
        }

    permissions = {}
    for dt in PHASE1O_DOCTYPES:
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
            "generate_claim_export": permission_matrix().get("generate_claim_export"),
            "cancel_claim_export": permission_matrix().get("cancel_claim_export"),
        },
        "workspace_shortcut": workspace_shortcut_exists(),
        "js_files": {
            "public/js/ndis_claim_export.js": file_exists("public/js/ndis_claim_export.js"),
            "public/js/ndis_claim_export_list.js": file_exists(
                "public/js/ndis_claim_export_list.js"
            ),
            "public/js/ndis_claim_export_line.js": file_exists(
                "public/js/ndis_claim_export_line.js"
            ),
            "public/js/ndis_claim_export_line_list.js": file_exists(
                "public/js/ndis_claim_export_line_list.js"
            ),
        },
        "js_hooks": {
            "NDIS Claim Export": "NDIS Claim Export" in doctype_js,
            "NDIS Claim Export Line": "NDIS Claim Export Line" in doctype_js,
        },
        "list_js_hooks": {
            "NDIS Claim Export": "NDIS Claim Export" in doctype_list_js,
            "NDIS Claim Export Line": "NDIS Claim Export Line" in doctype_list_js,
        },
    }


def can_import_service():
    try:
        from ndis_finance.services.claim_exporter import quick_claim_export_summary

        return callable(quick_claim_export_summary)
    except Exception:
        return False


def file_exists(relative_path):
    app_path = frappe.get_app_path("ndis_finance")
    app_root = os.path.dirname(app_path)
    return os.path.exists(os.path.join(app_root, "ndis_finance", relative_path))


def workspace_shortcut_exists():
    ws_name = frappe.db.exists("Workspace", "NDIS Finance") or frappe.db.exists(
        "Workspace",
        {"label": "NDIS Finance"},
    )

    if not ws_name:
        return False

    ws = frappe.get_doc("Workspace", ws_name)
    blob = getattr(ws, "content", None) or ""

    for fieldname in ["shortcuts", "links"]:
        if ws.meta.has_field(fieldname):
            for row in getattr(ws, fieldname, []) or []:
                blob += f" {getattr(row, 'label', '')} {getattr(row, 'link_to', '')}"

    return "Claim Exports" in blob or "NDIS Claim Export" in blob
