import json
import os

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from ndis_finance.services.permissions import permission_matrix
from ndis_finance.setup.install import MODULE, _create_doctype


PHASE1N_DOCTYPES = [
    "NDIS Remittance Import",
    "NDIS Remittance Import Line",
]

CUSTOM_FIELDS = {
    "NDIS Payment Reconciliation Batch": [
        "remittance_import",
    ],
    "NDIS Payment Reconciliation Line": [
        "remittance_import",
        "remittance_import_line",
    ],
    "NDIS Claim Line": [
        "remittance_import",
        "remittance_import_line",
    ],
}

DOC_PERM_MATRIX = {
    "NDIS Remittance Import": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Claims Officer": "create_write_read_report",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Remittance Import Line": {
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
    create_remittance_import_doctype()
    create_remittance_import_line_doctype()
    create_phase1n_custom_fields()
    harden_remittance_permissions()
    add_workspace_shortcut()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Claim Batch",
        "NDIS Claim Line",
        "NDIS Payment Reconciliation Batch",
        "NDIS Payment Reconciliation Line",
        "NDIS Funding Leakage Register",
        "NDIS Recovery Case",
        "Sales Invoice",
        "Customer",
        "Workspace",
    ]

    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]

    if missing:
        frappe.throw(
            _("Phase 1N requires previous phases. Missing DocTypes: {0}").format(
                ", ".join(missing)
            )
        )


def create_remittance_import_doctype():
    _create_doctype(
        name="NDIS Remittance Import",
        autoname="field:remittance_import_id",
        title_field="remittance_import_id",
        fields=[
            {
                "fieldname": "remittance_import_id",
                "label": "Remittance Import ID",
                "fieldtype": "Data",
                "reqd": 1,
                "unique": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "payer_type",
                "label": "Payer Type",
                "fieldtype": "Select",
                "options": "\nNDIA\nPlan Manager\nSelf Managed\nOther",
                "default": "NDIA",
                "in_list_view": 1,
            },
            {
                "fieldname": "status",
                "label": "Status",
                "fieldtype": "Select",
                "options": "\nDraft\nImported\nMatched\nPartially Matched\nApplied\nPartially Applied\nFailed\nCancelled",
                "default": "Draft",
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
                "fieldname": "claim_batch",
                "label": "Claim Batch",
                "fieldtype": "Link",
                "options": "NDIS Claim Batch",
                "in_list_view": 1,
            },
            {
                "fieldname": "payment_reconciliation_batch",
                "label": "Payment Reconciliation Batch",
                "fieldtype": "Link",
                "options": "NDIS Payment Reconciliation Batch",
                "read_only": 1,
            },
            {
                "fieldname": "payment_date",
                "label": "Payment Date",
                "fieldtype": "Date",
                "in_list_view": 1,
            },
            {
                "fieldname": "external_payment_reference",
                "label": "External Payment / Remittance Reference",
                "fieldtype": "Data",
                "in_list_view": 1,
            },
            {
                "fieldname": "remittance_file",
                "label": "Remittance File",
                "fieldtype": "Attach",
            },
            {
                "fieldname": "source_file_name",
                "label": "Source File Name",
                "fieldtype": "Data",
                "read_only": 1,
            },
            {
                "fieldname": "amount_section",
                "label": "Amounts",
                "fieldtype": "Section Break",
            },
            {
                "fieldname": "expected_claim_amount",
                "label": "Expected Claim Amount",
                "fieldtype": "Currency",
                "read_only": 1,
            },
            {
                "fieldname": "received_amount",
                "label": "Received Amount",
                "fieldtype": "Currency",
            },
            {
                "fieldname": "matched_amount",
                "label": "Matched Amount",
                "fieldtype": "Currency",
                "read_only": 1,
            },
            {
                "fieldname": "unmatched_amount",
                "label": "Unmatched Amount",
                "fieldtype": "Currency",
                "read_only": 1,
            },
            {
                "fieldname": "shortfall_amount",
                "label": "Shortfall Amount",
                "fieldtype": "Currency",
                "read_only": 1,
            },
            {
                "fieldname": "line_count",
                "label": "Line Count",
                "fieldtype": "Int",
                "read_only": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "matched_line_count",
                "label": "Matched Line Count",
                "fieldtype": "Int",
                "read_only": 1,
            },
            {
                "fieldname": "applied_line_count",
                "label": "Applied Line Count",
                "fieldtype": "Int",
                "read_only": 1,
            },
            {
                "fieldname": "audit_section",
                "label": "Audit",
                "fieldtype": "Section Break",
            },
            {
                "fieldname": "imported_on",
                "label": "Imported On",
                "fieldtype": "Datetime",
                "read_only": 1,
            },
            {
                "fieldname": "imported_by",
                "label": "Imported By",
                "fieldtype": "Link",
                "options": "User",
                "read_only": 1,
            },
            {
                "fieldname": "matched_on",
                "label": "Matched On",
                "fieldtype": "Datetime",
                "read_only": 1,
            },
            {
                "fieldname": "applied_on",
                "label": "Applied On",
                "fieldtype": "Datetime",
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


def create_remittance_import_line_doctype():
    _create_doctype(
        name="NDIS Remittance Import Line",
        autoname="hash",
        title_field="remittance_import",
        fields=[
            {
                "fieldname": "remittance_import",
                "label": "Remittance Import",
                "fieldtype": "Link",
                "options": "NDIS Remittance Import",
                "reqd": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "source_row",
                "label": "Source Row",
                "fieldtype": "Int",
                "in_list_view": 1,
            },
            {
                "fieldname": "status",
                "label": "Status",
                "fieldtype": "Select",
                "options": "\nImported\nMatched\nMultiple Matches\nUnmatched\nApplied\nError\nSkipped",
                "default": "Imported",
                "in_list_view": 1,
            },
            {
                "fieldname": "match_confidence",
                "label": "Match Confidence",
                "fieldtype": "Select",
                "options": "\nNone\nLow\nMedium\nHigh",
                "default": "None",
                "in_list_view": 1,
            },
            {
                "fieldname": "confidence_score",
                "label": "Confidence Score",
                "fieldtype": "Int",
                "read_only": 1,
            },
            {
                "fieldname": "matched_claim_line",
                "label": "Matched Claim Line",
                "fieldtype": "Link",
                "options": "NDIS Claim Line",
                "in_list_view": 1,
            },
            {
                "fieldname": "payment_reconciliation_line",
                "label": "Payment Reconciliation Line",
                "fieldtype": "Link",
                "options": "NDIS Payment Reconciliation Line",
                "read_only": 1,
            },
            {
                "fieldname": "source_section",
                "label": "Source Values",
                "fieldtype": "Section Break",
            },
            {
                "fieldname": "external_claim_reference",
                "label": "External Claim Reference",
                "fieldtype": "Data",
                "in_list_view": 1,
            },
            {
                "fieldname": "invoice_number",
                "label": "Invoice Number",
                "fieldtype": "Data",
                "in_list_view": 1,
            },
            {
                "fieldname": "sales_invoice",
                "label": "Sales Invoice",
                "fieldtype": "Link",
                "options": "Sales Invoice",
            },
            {
                "fieldname": "participant_name",
                "label": "Participant Name",
                "fieldtype": "Data",
            },
            {
                "fieldname": "participant",
                "label": "Participant",
                "fieldtype": "Link",
                "options": "Customer",
            },
            {
                "fieldname": "ndis_number",
                "label": "NDIS Number",
                "fieldtype": "Data",
            },
            {
                "fieldname": "support_item_number",
                "label": "Support Item Number",
                "fieldtype": "Data",
                "in_list_view": 1,
            },
            {
                "fieldname": "service_date",
                "label": "Service Date",
                "fieldtype": "Date",
                "in_list_view": 1,
            },
            {
                "fieldname": "amount_section",
                "label": "Amounts / Outcome",
                "fieldtype": "Section Break",
            },
            {
                "fieldname": "claim_amount",
                "label": "Claim Amount",
                "fieldtype": "Currency",
            },
            {
                "fieldname": "paid_amount",
                "label": "Paid Amount",
                "fieldtype": "Currency",
                "in_list_view": 1,
            },
            {
                "fieldname": "shortfall_amount",
                "label": "Shortfall Amount",
                "fieldtype": "Currency",
                "read_only": 1,
            },
            {
                "fieldname": "outcome",
                "label": "Outcome",
                "fieldtype": "Select",
                "options": "\nPaid\nShort Paid\nRejected",
                "in_list_view": 1,
            },
            {
                "fieldname": "rejection_reason",
                "label": "Rejection / Shortfall Reason",
                "fieldtype": "Small Text",
            },
            {
                "fieldname": "match_note",
                "label": "Match Note",
                "fieldtype": "Small Text",
                "read_only": 1,
            },
            {
                "fieldname": "raw_json",
                "label": "Raw Row JSON",
                "fieldtype": "Long Text",
                "read_only": 1,
            },
        ],
    )


def create_phase1n_custom_fields():
    custom_fields = {
        "NDIS Payment Reconciliation Batch": [
            {
                "fieldname": "remittance_import",
                "label": "Remittance Import",
                "fieldtype": "Link",
                "options": "NDIS Remittance Import",
                "insert_after": "external_payment_reference",
                "read_only": 1,
                "module": MODULE,
            },
        ],
        "NDIS Payment Reconciliation Line": [
            {
                "fieldname": "remittance_import",
                "label": "Remittance Import",
                "fieldtype": "Link",
                "options": "NDIS Remittance Import",
                "insert_after": "payment_entry",
                "read_only": 1,
                "module": MODULE,
            },
            {
                "fieldname": "remittance_import_line",
                "label": "Remittance Import Line",
                "fieldtype": "Link",
                "options": "NDIS Remittance Import Line",
                "insert_after": "remittance_import",
                "read_only": 1,
                "module": MODULE,
            },
        ],
        "NDIS Claim Line": [
            {
                "fieldname": "remittance_import",
                "label": "Remittance Import",
                "fieldtype": "Link",
                "options": "NDIS Remittance Import",
                "insert_after": "recovery_case",
                "read_only": 1,
                "module": MODULE,
            },
            {
                "fieldname": "remittance_import_line",
                "label": "Remittance Import Line",
                "fieldtype": "Link",
                "options": "NDIS Remittance Import Line",
                "insert_after": "remittance_import",
                "read_only": 1,
                "module": MODULE,
            },
        ],
    }

    create_custom_fields(custom_fields, update=True)


def harden_remittance_permissions():
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

    label = "Remittance Imports"
    link_to = "NDIS Remittance Import"

    if ws.meta.has_field("content"):
        try:
            content = json.loads(ws.content or "[]")
        except Exception:
            content = []

        text_blob = json.dumps(content)

        if label not in text_blob and link_to not in text_blob:
            content.append(
                {
                    "id": "remittance_imports",
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
    doctypes = {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE1N_DOCTYPES}

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
    for dt in PHASE1N_DOCTYPES:
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
            "import_remittance": permission_matrix().get("import_remittance"),
            "match_remittance": permission_matrix().get("match_remittance"),
            "apply_remittance": permission_matrix().get("apply_remittance"),
        },
        "workspace_shortcut": workspace_shortcut_exists(),
        "js_files": {
            "public/js/ndis_remittance_import.js": file_exists(
                "public/js/ndis_remittance_import.js"
            ),
            "public/js/ndis_remittance_import_list.js": file_exists(
                "public/js/ndis_remittance_import_list.js"
            ),
            "public/js/ndis_remittance_import_line.js": file_exists(
                "public/js/ndis_remittance_import_line.js"
            ),
            "public/js/ndis_remittance_import_line_list.js": file_exists(
                "public/js/ndis_remittance_import_line_list.js"
            ),
        },
        "js_hooks": {
            "NDIS Remittance Import": "NDIS Remittance Import" in doctype_js,
            "NDIS Remittance Import Line": "NDIS Remittance Import Line" in doctype_js,
        },
        "list_js_hooks": {
            "NDIS Remittance Import": "NDIS Remittance Import" in doctype_list_js,
            "NDIS Remittance Import Line": "NDIS Remittance Import Line" in doctype_list_js,
        },
    }


def can_import_service():
    try:
        from ndis_finance.services.remittance_importer import quick_remittance_import_summary

        return callable(quick_remittance_import_summary)
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

    return "Remittance Imports" in blob or "NDIS Remittance Import" in blob
