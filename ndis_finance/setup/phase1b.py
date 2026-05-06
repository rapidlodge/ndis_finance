import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from ndis_finance.setup.install import MODULE, _create_doctype


PHASE1B_DOCTYPES = [
    "NDIS Catalogue Import",
]

PHASE1B_ITEM_FIELDS = [
    "custom_is_ndis_billable_item",
    "custom_ndis_support_item",
    "custom_ndis_service_type",
    "custom_ndis_funding_source",
    "custom_ndis_default_claimable",
    "custom_ndis_gst_treatment",
]

PHASE1B_SALES_INVOICE_ITEM_FIELDS = [
    "custom_ndis_price_limit",
    "custom_ndis_gst_treatment",
    "custom_ndis_price_check_status",
    "custom_ndis_price_override_reason",
    "custom_ndis_catalogue_version",
]

PHASE1B_SALES_INVOICE_FIELDS = [
    "custom_ndis_price_control_mode",
]

PHASE1B_SUPPORT_ITEM_FIELDS = [
    "price_national",
    "price_nsw",
    "price_vic",
    "price_qld",
    "price_sa",
    "price_wa",
    "price_tas",
    "price_act",
    "price_nt",
    "price_remote",
    "price_very_remote",
    "quote_required",
    "provider_travel_allowed",
    "non_face_to_face_allowed",
    "cancellation_allowed",
    "ndia_requested_reports_allowed",
    "irregular_sil_allowed",
    "catalogue_source_file",
    "last_imported_on",
]


@frappe.whitelist()
def install():
    """
    Phase 1B installer.
    Safe to run multiple times.
    """
    validate_phase1a()
    create_catalogue_import_doctype()
    create_phase1b_custom_fields()
    frappe.db.commit()
    return health_check()


def validate_phase1a():
    required = [
        "NDIS Support Item",
        "NDIS Service Type",
        "NDIS Funding Source",
        "Sales Invoice",
        "Sales Invoice Item",
        "Item",
        "Customer",
    ]

    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]

    if missing:
        frappe.throw(
            _("Phase 1B requires Phase 1A and ERPNext. Missing DocTypes: {0}").format(
                ", ".join(missing)
            )
        )


def create_catalogue_import_doctype():
    _create_doctype(
        name="NDIS Catalogue Import",
        autoname="format:NDIS-CAT-.#####",
        title_field="catalogue_version",
        fields=[
            {
                "fieldname": "catalogue_version",
                "label": "Catalogue Version",
                "fieldtype": "Data",
                "reqd": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "effective_from",
                "label": "Effective From",
                "fieldtype": "Date",
                "in_list_view": 1,
            },
            {
                "fieldname": "source_url",
                "label": "Source URL",
                "fieldtype": "Small Text",
            },
            {
                "fieldname": "catalogue_file",
                "label": "Catalogue File",
                "fieldtype": "Attach",
            },
            {
                "fieldname": "status",
                "label": "Status",
                "fieldtype": "Select",
                "options": "\nDraft\nImported\nImported With Warnings\nFailed",
                "default": "Draft",
                "in_list_view": 1,
            },
            {
                "fieldname": "imported_on",
                "label": "Imported On",
                "fieldtype": "Datetime",
                "read_only": 1,
            },
            {
                "fieldname": "total_rows",
                "label": "Total Rows Read",
                "fieldtype": "Int",
                "read_only": 1,
            },
            {
                "fieldname": "created_count",
                "label": "Created",
                "fieldtype": "Int",
                "read_only": 1,
            },
            {
                "fieldname": "updated_count",
                "label": "Updated",
                "fieldtype": "Int",
                "read_only": 1,
            },
            {
                "fieldname": "skipped_count",
                "label": "Skipped",
                "fieldtype": "Int",
                "read_only": 1,
            },
            {
                "fieldname": "warning_log",
                "label": "Warning Log",
                "fieldtype": "Long Text",
                "read_only": 1,
            },
        ],
    )


def create_phase1b_custom_fields():
    custom_fields = {
        "Item": [
            {
                "fieldname": "custom_ndis_item_section",
                "label": "NDIS Billing Mapping",
                "fieldtype": "Section Break",
                "insert_after": "item_group",
                "collapsible": 1,
                "module": MODULE,
            },
            {
                "fieldname": "custom_is_ndis_billable_item",
                "label": "Is NDIS Billable Item",
                "fieldtype": "Check",
                "insert_after": "custom_ndis_item_section",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_support_item",
                "label": "NDIS Support Item",
                "fieldtype": "Link",
                "options": "NDIS Support Item",
                "insert_after": "custom_is_ndis_billable_item",
                "depends_on": "eval:doc.custom_is_ndis_billable_item",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_service_type",
                "label": "NDIS Service Type",
                "fieldtype": "Link",
                "options": "NDIS Service Type",
                "insert_after": "custom_ndis_support_item",
                "depends_on": "eval:doc.custom_is_ndis_billable_item",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_funding_source",
                "label": "Default Funding Source",
                "fieldtype": "Link",
                "options": "NDIS Funding Source",
                "insert_after": "custom_ndis_service_type",
                "depends_on": "eval:doc.custom_is_ndis_billable_item",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_default_claimable",
                "label": "Default Claimable",
                "fieldtype": "Check",
                "default": "1",
                "insert_after": "custom_ndis_funding_source",
                "depends_on": "eval:doc.custom_is_ndis_billable_item",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_gst_treatment",
                "label": "NDIS GST Treatment",
                "fieldtype": "Select",
                "options": "\nGST Free\nTaxable\nInput Taxed\nOut of Scope\nTo Review",
                "default": "To Review",
                "insert_after": "custom_ndis_default_claimable",
                "depends_on": "eval:doc.custom_is_ndis_billable_item",
                "module": MODULE,
            },
        ],
        "NDIS Support Item": [
            {
                "fieldname": "pricing_breakdown_section",
                "label": "Pricing Breakdown",
                "fieldtype": "Section Break",
                "insert_after": "price_limit",
                "collapsible": 1,
                "module": MODULE,
            },
            {
                "fieldname": "price_national",
                "label": "National Price",
                "fieldtype": "Currency",
                "insert_after": "pricing_breakdown_section",
                "module": MODULE,
            },
            {
                "fieldname": "price_nsw",
                "label": "NSW Price",
                "fieldtype": "Currency",
                "insert_after": "price_national",
                "module": MODULE,
            },
            {
                "fieldname": "price_vic",
                "label": "VIC Price",
                "fieldtype": "Currency",
                "insert_after": "price_nsw",
                "module": MODULE,
            },
            {
                "fieldname": "price_qld",
                "label": "QLD Price",
                "fieldtype": "Currency",
                "insert_after": "price_vic",
                "module": MODULE,
            },
            {
                "fieldname": "price_sa",
                "label": "SA Price",
                "fieldtype": "Currency",
                "insert_after": "price_qld",
                "module": MODULE,
            },
            {
                "fieldname": "price_wa",
                "label": "WA Price",
                "fieldtype": "Currency",
                "insert_after": "price_sa",
                "module": MODULE,
            },
            {
                "fieldname": "price_tas",
                "label": "TAS Price",
                "fieldtype": "Currency",
                "insert_after": "price_wa",
                "module": MODULE,
            },
            {
                "fieldname": "price_act",
                "label": "ACT Price",
                "fieldtype": "Currency",
                "insert_after": "price_tas",
                "module": MODULE,
            },
            {
                "fieldname": "price_nt",
                "label": "NT Price",
                "fieldtype": "Currency",
                "insert_after": "price_act",
                "module": MODULE,
            },
            {
                "fieldname": "price_remote",
                "label": "Remote Price",
                "fieldtype": "Currency",
                "insert_after": "price_nt",
                "module": MODULE,
            },
            {
                "fieldname": "price_very_remote",
                "label": "Very Remote Price",
                "fieldtype": "Currency",
                "insert_after": "price_remote",
                "module": MODULE,
            },
            {
                "fieldname": "claim_rules_section",
                "label": "Claim Rules",
                "fieldtype": "Section Break",
                "insert_after": "price_very_remote",
                "collapsible": 1,
                "module": MODULE,
            },
            {
                "fieldname": "quote_required",
                "label": "Quote Required",
                "fieldtype": "Check",
                "insert_after": "claim_rules_section",
                "module": MODULE,
            },
            {
                "fieldname": "provider_travel_allowed",
                "label": "Provider Travel Allowed",
                "fieldtype": "Check",
                "insert_after": "quote_required",
                "module": MODULE,
            },
            {
                "fieldname": "non_face_to_face_allowed",
                "label": "Non-Face-to-Face Allowed",
                "fieldtype": "Check",
                "insert_after": "provider_travel_allowed",
                "module": MODULE,
            },
            {
                "fieldname": "cancellation_allowed",
                "label": "Cancellation Allowed",
                "fieldtype": "Check",
                "insert_after": "non_face_to_face_allowed",
                "module": MODULE,
            },
            {
                "fieldname": "ndia_requested_reports_allowed",
                "label": "NDIA Requested Reports Allowed",
                "fieldtype": "Check",
                "insert_after": "cancellation_allowed",
                "module": MODULE,
            },
            {
                "fieldname": "irregular_sil_allowed",
                "label": "Irregular SIL Allowed",
                "fieldtype": "Check",
                "insert_after": "ndia_requested_reports_allowed",
                "module": MODULE,
            },
            {
                "fieldname": "import_audit_section",
                "label": "Import Audit",
                "fieldtype": "Section Break",
                "insert_after": "irregular_sil_allowed",
                "collapsible": 1,
                "module": MODULE,
            },
            {
                "fieldname": "catalogue_source_file",
                "label": "Catalogue Source File",
                "fieldtype": "Data",
                "insert_after": "import_audit_section",
                "read_only": 1,
                "module": MODULE,
            },
            {
                "fieldname": "last_imported_on",
                "label": "Last Imported On",
                "fieldtype": "Datetime",
                "insert_after": "catalogue_source_file",
                "read_only": 1,
                "module": MODULE,
            },
        ],
        "Sales Invoice": [
            {
                "fieldname": "custom_ndis_price_control_mode",
                "label": "NDIS Price Control Mode",
                "fieldtype": "Select",
                "options": "\nWarn and Block\nWarn Only\nDisabled",
                "default": "Warn and Block",
                "insert_after": "custom_ndis_recovery_status",
                "depends_on": "eval:doc.custom_is_ndis_invoice",
                "module": MODULE,
            },
        ],
        "Sales Invoice Item": [
            {
                "fieldname": "custom_ndis_price_limit",
                "label": "NDIS Price Limit",
                "fieldtype": "Currency",
                "insert_after": "custom_ndis_claim_status",
                "read_only": 1,
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_gst_treatment",
                "label": "NDIS GST Treatment",
                "fieldtype": "Select",
                "options": "\nGST Free\nTaxable\nInput Taxed\nOut of Scope\nTo Review",
                "insert_after": "custom_ndis_price_limit",
                "read_only": 1,
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_price_check_status",
                "label": "NDIS Price Check Status",
                "fieldtype": "Select",
                "options": "\nNot Checked\nWithin Limit\nOver Limit\nNo Price Limit\nQuote Required\nOverride Accepted",
                "default": "Not Checked",
                "insert_after": "custom_ndis_gst_treatment",
                "read_only": 1,
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_price_override_reason",
                "label": "Price Override Reason",
                "fieldtype": "Small Text",
                "insert_after": "custom_ndis_price_check_status",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_catalogue_version",
                "label": "Catalogue Version",
                "fieldtype": "Data",
                "insert_after": "custom_ndis_price_override_reason",
                "read_only": 1,
                "module": MODULE,
            },
        ],
    }

    create_custom_fields(custom_fields, update=True)


@frappe.whitelist()
def health_check():
    doctypes = {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE1B_DOCTYPES}

    item_fields = {
        fieldname: bool(
            frappe.db.exists(
                "Custom Field",
                {"dt": "Item", "fieldname": fieldname},
            )
        )
        for fieldname in PHASE1B_ITEM_FIELDS
    }

    support_item_fields = {
        fieldname: bool(
            frappe.db.exists(
                "Custom Field",
                {"dt": "NDIS Support Item", "fieldname": fieldname},
            )
        )
        for fieldname in PHASE1B_SUPPORT_ITEM_FIELDS
    }

    sales_invoice_fields = {
        fieldname: bool(
            frappe.db.exists(
                "Custom Field",
                {"dt": "Sales Invoice", "fieldname": fieldname},
            )
        )
        for fieldname in PHASE1B_SALES_INVOICE_FIELDS
    }

    sales_invoice_item_fields = {
        fieldname: bool(
            frappe.db.exists(
                "Custom Field",
                {"dt": "Sales Invoice Item", "fieldname": fieldname},
            )
        )
        for fieldname in PHASE1B_SALES_INVOICE_ITEM_FIELDS
    }

    return {
        "doctypes": doctypes,
        "item_mapping_fields": item_fields,
        "support_item_catalogue_fields": support_item_fields,
        "sales_invoice_fields": sales_invoice_fields,
        "sales_invoice_item_control_fields": sales_invoice_item_fields,
    }
