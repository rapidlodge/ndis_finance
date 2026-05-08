import json
import os

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from ndis_finance.services.permissions import permission_matrix
from ndis_finance.setup.install import MODULE, _create_doctype


PHASE1P_DOCTYPES = [
    "NDIS Claim Export Mapping Template",
]

CUSTOM_FIELDS = {
    "NDIS Claim Export": [
        "export_mapping_template",
    ],
}

DOC_PERM_MATRIX = {
    "NDIS Claim Export Mapping Template": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Catalogue Manager": "full_no_delete",
        "NDIS Claims Officer": "read_report_export",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
}

TEMPLATES = [
    {
        "template_name": "NDIS Default Claim Export",
        "export_type": "NDIA Claim CSV",
        "is_default": 1,
        "description": "Default safe claim export structure generated from NDIS Claim Lines.",
        "column_mapping": [
            {"column_label": "Claim Line", "source_field": "claim_line"},
            {"column_label": "Claim Batch", "source_field": "claim_batch"},
            {"column_label": "Sales Invoice", "source_field": "sales_invoice"},
            {"column_label": "Participant", "source_field": "participant"},
            {"column_label": "Participant Name", "source_field": "participant_name"},
            {"column_label": "Service Date", "source_field": "service_date"},
            {"column_label": "Support Item Number", "source_field": "support_item_number"},
            {"column_label": "Support Item Name", "source_field": "support_item_name"},
            {"column_label": "Quantity", "source_field": "qty"},
            {"column_label": "Rate", "source_field": "rate"},
            {"column_label": "Claim Amount", "source_field": "claim_amount"},
            {"column_label": "External Claim Reference", "source_field": "external_claim_reference"},
        ],
    },
    {
        "template_name": "NDIS Plan Manager Claim Export",
        "export_type": "Plan Manager CSV",
        "is_default": 1,
        "description": "Plan manager friendly CSV with invoice, participant and claim details.",
        "column_mapping": [
            {"column_label": "Invoice Number", "source_field": "sales_invoice"},
            {"column_label": "Participant Name", "source_field": "participant_name"},
            {"column_label": "Participant ID", "source_field": "participant"},
            {"column_label": "Service Date", "source_field": "service_date"},
            {"column_label": "Support Item", "source_field": "support_item_number"},
            {"column_label": "Description", "source_field": "support_item_name"},
            {"column_label": "Qty", "source_field": "qty"},
            {"column_label": "Unit Price", "source_field": "rate"},
            {"column_label": "Amount", "source_field": "claim_amount"},
            {"column_label": "Funding Source", "source_field": "funding_source"},
        ],
    },
    {
        "template_name": "NDIS Self Managed Claim Export",
        "export_type": "Self Managed CSV",
        "is_default": 1,
        "description": "Self-managed participant friendly CSV export.",
        "column_mapping": [
            {"column_label": "Participant Name", "source_field": "participant_name"},
            {"column_label": "Invoice Number", "source_field": "sales_invoice"},
            {"column_label": "Service Date", "source_field": "service_date"},
            {"column_label": "Support Description", "source_field": "support_item_name"},
            {"column_label": "Support Item Number", "source_field": "support_item_number"},
            {"column_label": "Quantity", "source_field": "qty"},
            {"column_label": "Rate", "source_field": "rate"},
            {"column_label": "Total", "source_field": "claim_amount"},
        ],
    },
    {
        "template_name": "NDIS Internal Review Claim Export",
        "export_type": "Internal Review CSV",
        "is_default": 1,
        "description": "Internal audit/review CSV with extra control fields.",
        "column_mapping": [
            {"column_label": "Claim Line", "source_field": "claim_line"},
            {"column_label": "Claim Batch", "source_field": "claim_batch"},
            {"column_label": "Claim Status", "source_field": "claim_status"},
            {"column_label": "Export Status", "source_field": "export_status"},
            {"column_label": "Sales Invoice", "source_field": "sales_invoice"},
            {"column_label": "Sales Invoice Item", "source_field": "sales_invoice_item"},
            {"column_label": "Participant", "source_field": "participant"},
            {"column_label": "Participant Name", "source_field": "participant_name"},
            {"column_label": "House", "source_field": "house"},
            {"column_label": "Funding Source", "source_field": "funding_source"},
            {"column_label": "Service Date", "source_field": "service_date"},
            {"column_label": "Support Item Number", "source_field": "support_item_number"},
            {"column_label": "Support Item Name", "source_field": "support_item_name"},
            {"column_label": "Qty", "source_field": "qty"},
            {"column_label": "Rate", "source_field": "rate"},
            {"column_label": "Claim Amount", "source_field": "claim_amount"},
            {"column_label": "External Claim Reference", "source_field": "external_claim_reference"},
        ],
    },
]

TEMPLATE_NAMES = [template["template_name"] for template in TEMPLATES]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_mapping_template_doctype()
    create_phase1p_custom_fields()
    seed_templates()
    harden_mapping_template_permissions()
    add_workspace_shortcut()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Claim Export",
        "NDIS Claim Export Line",
        "NDIS Claim Batch",
        "NDIS Claim Line",
        "Workspace",
    ]

    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]

    if missing:
        frappe.throw(
            _("Phase 1P requires previous phases. Missing DocTypes: {0}").format(
                ", ".join(missing)
            )
        )


def create_mapping_template_doctype():
    _create_doctype(
        name="NDIS Claim Export Mapping Template",
        autoname="field:template_name",
        title_field="template_name",
        fields=[
            {
                "fieldname": "template_name",
                "label": "Template Name",
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
                "fieldname": "active",
                "label": "Active",
                "fieldtype": "Check",
                "default": "1",
                "in_list_view": 1,
            },
            {
                "fieldname": "is_default",
                "label": "Default For Export Type",
                "fieldtype": "Check",
                "default": "0",
                "in_list_view": 1,
            },
            {
                "fieldname": "description",
                "label": "Description",
                "fieldtype": "Small Text",
            },
            {
                "fieldname": "column_mapping_json",
                "label": "Column Mapping JSON",
                "fieldtype": "Long Text",
                "reqd": 1,
            },
            {
                "fieldname": "notes",
                "label": "Notes",
                "fieldtype": "Small Text",
            },
        ],
    )


def create_phase1p_custom_fields():
    custom_fields = {
        "NDIS Claim Export": [
            {
                "fieldname": "export_mapping_template",
                "label": "Export Mapping Template",
                "fieldtype": "Link",
                "options": "NDIS Claim Export Mapping Template",
                "insert_after": "export_type",
                "read_only": 1,
                "module": MODULE,
            },
        ],
    }

    create_custom_fields(custom_fields, update=True)


def seed_templates():
    for template in TEMPLATES:
        existing = frappe.db.exists(
            "NDIS Claim Export Mapping Template",
            template["template_name"],
        )

        if existing:
            doc = frappe.get_doc("NDIS Claim Export Mapping Template", existing)
        else:
            doc = frappe.new_doc("NDIS Claim Export Mapping Template")
            doc.template_name = template["template_name"]

        doc.export_type = template["export_type"]
        doc.active = 1
        doc.is_default = template["is_default"]
        doc.description = template["description"]
        doc.column_mapping_json = json.dumps(template["column_mapping"], indent=2)
        doc.save(ignore_permissions=True)


def harden_mapping_template_permissions():
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
    label = "Claim Export Templates"
    link_to = "NDIS Claim Export Mapping Template"

    if ws.meta.has_field("content"):
        try:
            content = json.loads(ws.content or "[]")
        except Exception:
            content = []

        text_blob = json.dumps(content)

        if label not in text_blob and link_to not in text_blob:
            content.append(
                {
                    "id": "claim_export_templates",
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
    doctypes = {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE1P_DOCTYPES}

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

    templates = {
        template_name: bool(
            frappe.db.exists("NDIS Claim Export Mapping Template", template_name)
        )
        for template_name in TEMPLATE_NAMES
    }

    permissions = {}
    for dt in PHASE1P_DOCTYPES:
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
        "templates": templates,
        "permissions": permissions,
        "service_import": can_import_service(),
        "action_permissions": {
            "generate_claim_export": permission_matrix().get("generate_claim_export"),
            "cancel_claim_export": permission_matrix().get("cancel_claim_export"),
            "manage_claim_export_template": permission_matrix().get(
                "manage_claim_export_template"
            ),
        },
        "workspace_shortcut": workspace_shortcut_exists(),
        "js_files": {
            "public/js/ndis_claim_export_mapping_template.js": file_exists(
                "public/js/ndis_claim_export_mapping_template.js"
            ),
            "public/js/ndis_claim_export_mapping_template_list.js": file_exists(
                "public/js/ndis_claim_export_mapping_template_list.js"
            ),
        },
        "js_hooks": {
            "NDIS Claim Export Mapping Template": "NDIS Claim Export Mapping Template"
            in doctype_js,
        },
        "list_js_hooks": {
            "NDIS Claim Export Mapping Template": "NDIS Claim Export Mapping Template"
            in doctype_list_js,
        },
    }


def can_import_service():
    try:
        from ndis_finance.services.claim_exporter import preview_export_template

        return callable(preview_export_template)
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

    return "Claim Export Templates" in blob or "NDIS Claim Export Mapping Template" in blob
