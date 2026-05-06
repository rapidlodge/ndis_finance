import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from ndis_finance.setup.install import MODULE, _create_doctype


PHASE1D_DOCTYPES = [
    "NDIS Claim Line",
]

CLAIM_BATCH_FIELDS = [
    "batch_type",
    "company",
    "claim_line_count",
    "submitted_on",
    "submitted_by",
    "external_batch_reference",
    "export_file",
    "batch_notes",
]

SALES_INVOICE_FIELDS = [
    "custom_ndis_claim_line_count",
    "custom_ndis_claim_total",
    "custom_ndis_claim_last_batched_on",
    "custom_ndis_batching_note",
]

SALES_INVOICE_ITEM_FIELDS = [
    "custom_ndis_claim_line",
    "custom_ndis_claim_batch_row",
    "custom_ndis_claim_amount",
    "custom_ndis_paid_amount",
    "custom_ndis_shortfall_amount",
    "custom_ndis_external_claim_reference",
]


@frappe.whitelist()
def install():
    validate_phase1c()
    create_claim_line_doctype()
    create_phase1d_custom_fields()
    frappe.db.commit()
    return health_check()


def validate_phase1c():
    required = [
        "NDIS Claim Batch",
        "NDIS Support Item",
        "NDIS Service Type",
        "NDIS Funding Source",
        "NDIS Plan Budget",
        "NDIS Service Booking",
        "Sales Invoice",
        "Sales Invoice Item",
        "Customer",
    ]

    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]

    if missing:
        frappe.throw(
            _("Phase 1D requires previous phases. Missing DocTypes: {0}").format(
                ", ".join(missing)
            )
        )

    required_fields = [
        ("Sales Invoice", "custom_is_ndis_invoice"),
        ("Sales Invoice", "custom_ndis_billing_status"),
        ("Sales Invoice Item", "custom_ndis_support_item"),
        ("Sales Invoice Item", "custom_ndis_service_type"),
        ("Sales Invoice Item", "custom_ndis_service_date"),
        ("Sales Invoice Item", "custom_ndis_claimable"),
        ("Sales Invoice Item", "custom_ndis_claim_status"),
        ("Sales Invoice Item", "custom_ndis_plan_budget"),
        ("Sales Invoice Item", "custom_ndis_service_booking"),
    ]

    missing_fields = []
    for dt, fieldname in required_fields:
        if not frappe.db.exists("Custom Field", {"dt": dt, "fieldname": fieldname}):
            missing_fields.append(f"{dt}.{fieldname}")

    if missing_fields:
        frappe.throw(
            _("Phase 1D requires missing fields: {0}").format(", ".join(missing_fields))
        )


def create_claim_line_doctype():
    _create_doctype(
        name="NDIS Claim Line",
        autoname="hash",
        title_field="sales_invoice",
        fields=[
            {
                "fieldname": "claim_batch",
                "label": "Claim Batch",
                "fieldtype": "Link",
                "options": "NDIS Claim Batch",
                "in_list_view": 1,
            },
            {
                "fieldname": "batch_type",
                "label": "Batch Type",
                "fieldtype": "Select",
                "options": "\nNDIA Claim\nPlan Manager Invoice Batch\nSelf Managed Invoice Batch\nInternal Review",
                "default": "NDIA Claim",
                "in_list_view": 1,
            },
            {
                "fieldname": "claim_status",
                "label": "Claim Status",
                "fieldtype": "Select",
                "options": "\nDraft\nReady to Claim\nSubmitted\nPaid\nShort Paid\nRejected\nReclaim Required\nInvoice Cancelled\nCancelled",
                "default": "Ready to Claim",
                "in_list_view": 1,
            },
            {
                "fieldname": "payment_status",
                "label": "Payment Status",
                "fieldtype": "Select",
                "options": "\nNot Paid\nPaid\nPart Paid\nShort Paid\nRejected\nWritten Off",
                "default": "Not Paid",
                "in_list_view": 1,
            },
            {
                "fieldname": "invoice_section",
                "label": "Invoice Link",
                "fieldtype": "Section Break",
            },
            {
                "fieldname": "company",
                "label": "Company",
                "fieldtype": "Link",
                "options": "Company",
                "in_list_view": 1,
            },
            {
                "fieldname": "sales_invoice",
                "label": "Sales Invoice",
                "fieldtype": "Link",
                "options": "Sales Invoice",
                "reqd": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "sales_invoice_item",
                "label": "Sales Invoice Item Row ID",
                "fieldtype": "Data",
                "reqd": 1,
                "unique": 1,
            },
            {
                "fieldname": "posting_date",
                "label": "Invoice Posting Date",
                "fieldtype": "Date",
            },
            {
                "fieldname": "customer",
                "label": "Invoice Customer",
                "fieldtype": "Link",
                "options": "Customer",
            },
            {
                "fieldname": "participant_section",
                "label": "Participant / Service",
                "fieldtype": "Section Break",
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
                "in_list_view": 1,
            },
            {
                "fieldname": "service_date",
                "label": "Service Date",
                "fieldtype": "Date",
                "in_list_view": 1,
            },
            {
                "fieldname": "funding_source",
                "label": "Funding Source",
                "fieldtype": "Link",
                "options": "NDIS Funding Source",
                "in_list_view": 1,
            },
            {
                "fieldname": "service_type",
                "label": "Service Type",
                "fieldtype": "Link",
                "options": "NDIS Service Type",
                "in_list_view": 1,
            },
            {
                "fieldname": "support_item",
                "label": "NDIS Support Item",
                "fieldtype": "Link",
                "options": "NDIS Support Item",
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
                "fieldname": "amount_section",
                "label": "Claim Amount",
                "fieldtype": "Section Break",
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
                "fieldname": "price_limit",
                "label": "NDIS Price Limit",
                "fieldtype": "Currency",
            },
            {
                "fieldname": "gst_treatment",
                "label": "GST Treatment",
                "fieldtype": "Select",
                "options": "\nGST Free\nTaxable\nInput Taxed\nOut of Scope\nTo Review",
            },
            {
                "fieldname": "paid_amount",
                "label": "Paid Amount",
                "fieldtype": "Currency",
                "default": "0",
            },
            {
                "fieldname": "shortfall_amount",
                "label": "Shortfall Amount",
                "fieldtype": "Currency",
                "default": "0",
            },
            {
                "fieldname": "control_section",
                "label": "Controls",
                "fieldtype": "Section Break",
            },
            {
                "fieldname": "plan_budget",
                "label": "Plan Budget",
                "fieldtype": "Link",
                "options": "NDIS Plan Budget",
            },
            {
                "fieldname": "service_booking",
                "label": "Service Booking",
                "fieldtype": "Link",
                "options": "NDIS Service Booking",
            },
            {
                "fieldname": "external_claim_reference",
                "label": "External Claim Reference",
                "fieldtype": "Data",
            },
            {
                "fieldname": "rejection_reason",
                "label": "Rejection / Shortfall Reason",
                "fieldtype": "Small Text",
            },
            {
                "fieldname": "control_note",
                "label": "Control Note",
                "fieldtype": "Small Text",
            },
        ],
    )


def create_phase1d_custom_fields():
    custom_fields = {
        "NDIS Claim Batch": [
            {
                "fieldname": "batch_type",
                "label": "Batch Type",
                "fieldtype": "Select",
                "options": "\nNDIA Claim\nPlan Manager Invoice Batch\nSelf Managed Invoice Batch\nInternal Review",
                "default": "NDIA Claim",
                "insert_after": "claim_batch_id",
                "module": MODULE,
            },
            {
                "fieldname": "company",
                "label": "Company",
                "fieldtype": "Link",
                "options": "Company",
                "insert_after": "batch_type",
                "module": MODULE,
            },
            {
                "fieldname": "claim_line_count",
                "label": "Claim Line Count",
                "fieldtype": "Int",
                "read_only": 1,
                "insert_after": "total_shortfall_amount",
                "module": MODULE,
            },
            {
                "fieldname": "submitted_on",
                "label": "Submitted On",
                "fieldtype": "Datetime",
                "read_only": 1,
                "insert_after": "claim_line_count",
                "module": MODULE,
            },
            {
                "fieldname": "submitted_by",
                "label": "Submitted By",
                "fieldtype": "Link",
                "options": "User",
                "read_only": 1,
                "insert_after": "submitted_on",
                "module": MODULE,
            },
            {
                "fieldname": "external_batch_reference",
                "label": "External Batch Reference",
                "fieldtype": "Data",
                "insert_after": "submitted_by",
                "module": MODULE,
            },
            {
                "fieldname": "export_file",
                "label": "Export File",
                "fieldtype": "Attach",
                "insert_after": "external_batch_reference",
                "module": MODULE,
            },
            {
                "fieldname": "batch_notes",
                "label": "Batch Notes",
                "fieldtype": "Small Text",
                "insert_after": "export_file",
                "module": MODULE,
            },
        ],
        "Sales Invoice": [
            {
                "fieldname": "custom_ndis_claim_line_count",
                "label": "NDIS Claim Line Count",
                "fieldtype": "Int",
                "insert_after": "custom_ndis_validation_last_run",
                "read_only": 1,
                "depends_on": "eval:doc.custom_is_ndis_invoice",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_claim_total",
                "label": "NDIS Claim Total",
                "fieldtype": "Currency",
                "insert_after": "custom_ndis_claim_line_count",
                "read_only": 1,
                "depends_on": "eval:doc.custom_is_ndis_invoice",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_claim_last_batched_on",
                "label": "Last Batched On",
                "fieldtype": "Datetime",
                "insert_after": "custom_ndis_claim_total",
                "read_only": 1,
                "depends_on": "eval:doc.custom_is_ndis_invoice",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_batching_note",
                "label": "NDIS Batching Note",
                "fieldtype": "Small Text",
                "insert_after": "custom_ndis_claim_last_batched_on",
                "read_only": 1,
                "depends_on": "eval:doc.custom_is_ndis_invoice",
                "module": MODULE,
            },
        ],
        "Sales Invoice Item": [
            {
                "fieldname": "custom_ndis_claim_line",
                "label": "NDIS Claim Line",
                "fieldtype": "Link",
                "options": "NDIS Claim Line",
                "insert_after": "custom_ndis_budget_validation_note",
                "read_only": 1,
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_claim_batch_row",
                "label": "NDIS Claim Batch",
                "fieldtype": "Link",
                "options": "NDIS Claim Batch",
                "insert_after": "custom_ndis_claim_line",
                "read_only": 1,
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_claim_amount",
                "label": "NDIS Claim Amount",
                "fieldtype": "Currency",
                "insert_after": "custom_ndis_claim_batch_row",
                "read_only": 1,
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_paid_amount",
                "label": "NDIS Paid Amount",
                "fieldtype": "Currency",
                "insert_after": "custom_ndis_claim_amount",
                "read_only": 1,
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_shortfall_amount",
                "label": "NDIS Shortfall Amount",
                "fieldtype": "Currency",
                "insert_after": "custom_ndis_paid_amount",
                "read_only": 1,
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_external_claim_reference",
                "label": "External Claim Reference",
                "fieldtype": "Data",
                "insert_after": "custom_ndis_shortfall_amount",
                "read_only": 1,
                "module": MODULE,
            },
        ],
    }

    create_custom_fields(custom_fields, update=True)


@frappe.whitelist()
def health_check():
    doctypes = {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE1D_DOCTYPES}

    claim_batch_fields = {
        fieldname: bool(
            frappe.db.exists(
                "Custom Field",
                {"dt": "NDIS Claim Batch", "fieldname": fieldname},
            )
        )
        for fieldname in CLAIM_BATCH_FIELDS
    }

    sales_invoice_fields = {
        fieldname: bool(
            frappe.db.exists(
                "Custom Field",
                {"dt": "Sales Invoice", "fieldname": fieldname},
            )
        )
        for fieldname in SALES_INVOICE_FIELDS
    }

    sales_invoice_item_fields = {
        fieldname: bool(
            frappe.db.exists(
                "Custom Field",
                {"dt": "Sales Invoice Item", "fieldname": fieldname},
            )
        )
        for fieldname in SALES_INVOICE_ITEM_FIELDS
    }

    return {
        "doctypes": doctypes,
        "claim_batch_fields": claim_batch_fields,
        "sales_invoice_fields": sales_invoice_fields,
        "sales_invoice_item_fields": sales_invoice_item_fields,
    }
