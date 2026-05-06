import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from ndis_finance.setup.install import MODULE, _create_doctype


PHASE1E_DOCTYPES = [
    "NDIS Payment Reconciliation Batch",
    "NDIS Payment Reconciliation Line",
]

CLAIM_LINE_FIELDS = [
    "reconciliation_batch",
    "reconciliation_line",
    "payment_entry",
    "payment_date",
    "remittance_reference",
    "reconciliation_status",
    "recovery_status",
    "follow_up_due_date",
]

PAYMENT_ENTRY_FIELDS = [
    "custom_is_ndis_payment",
    "custom_ndis_payment_reconciliation_batch",
    "custom_ndis_claim_batch",
    "custom_ndis_funding_source",
    "custom_ndis_remittance_reference",
]

FUNDING_LEAKAGE_FIELDS = [
    "claim_batch",
    "claim_line",
    "sales_invoice",
    "sales_invoice_item",
    "payment_reconciliation_batch",
    "payment_reconciliation_line",
    "recovery_status",
    "follow_up_due_date",
    "assigned_to",
]


@frappe.whitelist()
def install():
    validate_phase1d()
    create_payment_reconciliation_batch_doctype()
    create_payment_reconciliation_line_doctype()
    create_phase1e_custom_fields()
    frappe.db.commit()
    return health_check()


def validate_phase1d():
    required = [
        "NDIS Claim Batch",
        "NDIS Claim Line",
        "NDIS Funding Leakage Register",
        "Sales Invoice",
        "Sales Invoice Item",
        "Payment Entry",
        "Customer",
    ]

    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]

    if missing:
        frappe.throw(
            _("Phase 1E requires previous phases. Missing DocTypes: {0}").format(
                ", ".join(missing)
            )
        )


def create_payment_reconciliation_batch_doctype():
    _create_doctype(
        name="NDIS Payment Reconciliation Batch",
        autoname="field:reconciliation_id",
        title_field="reconciliation_id",
        fields=[
            {
                "fieldname": "reconciliation_id",
                "label": "Reconciliation ID",
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
                "options": "\nDraft\nPartially Reconciled\nReconciled\nException\nClosed",
                "default": "Draft",
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
                "fieldname": "payment_entry",
                "label": "Payment Entry",
                "fieldtype": "Link",
                "options": "Payment Entry",
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
                "fieldname": "shortfall_amount",
                "label": "Shortfall Amount",
                "fieldtype": "Currency",
                "read_only": 1,
            },
            {
                "fieldname": "rejected_amount",
                "label": "Rejected Amount",
                "fieldtype": "Currency",
                "read_only": 1,
            },
            {
                "fieldname": "line_count",
                "label": "Line Count",
                "fieldtype": "Int",
                "read_only": 1,
            },
            {
                "fieldname": "notes",
                "label": "Notes",
                "fieldtype": "Small Text",
            },
        ],
    )


def create_payment_reconciliation_line_doctype():
    _create_doctype(
        name="NDIS Payment Reconciliation Line",
        autoname="hash",
        title_field="claim_line",
        fields=[
            {
                "fieldname": "reconciliation_batch",
                "label": "Reconciliation Batch",
                "fieldtype": "Link",
                "options": "NDIS Payment Reconciliation Batch",
                "reqd": 1,
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
                "fieldname": "claim_line",
                "label": "Claim Line",
                "fieldtype": "Link",
                "options": "NDIS Claim Line",
                "reqd": 1,
                "in_list_view": 1,
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
            },
            {
                "fieldname": "service_type",
                "label": "Service Type",
                "fieldtype": "Link",
                "options": "NDIS Service Type",
            },
            {
                "fieldname": "support_item",
                "label": "Support Item",
                "fieldtype": "Link",
                "options": "NDIS Support Item",
            },
            {
                "fieldname": "support_item_number",
                "label": "Support Item Number",
                "fieldtype": "Data",
                "in_list_view": 1,
            },
            {
                "fieldname": "amount_section",
                "label": "Amounts",
                "fieldtype": "Section Break",
            },
            {
                "fieldname": "claim_amount",
                "label": "Claim Amount",
                "fieldtype": "Currency",
                "in_list_view": 1,
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
                "in_list_view": 1,
            },
            {
                "fieldname": "outcome",
                "label": "Outcome",
                "fieldtype": "Select",
                "options": "\nPaid\nShort Paid\nRejected\nReclaim Required\nWritten Off",
                "in_list_view": 1,
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
                "fieldname": "funding_leakage",
                "label": "Funding Leakage Register",
                "fieldtype": "Link",
                "options": "NDIS Funding Leakage Register",
            },
            {
                "fieldname": "payment_entry",
                "label": "Payment Entry",
                "fieldtype": "Link",
                "options": "Payment Entry",
            },
        ],
    )


def create_phase1e_custom_fields():
    custom_fields = {
        "NDIS Claim Line": [
            {
                "fieldname": "reconciliation_section",
                "label": "Payment Reconciliation",
                "fieldtype": "Section Break",
                "insert_after": "control_note",
                "collapsible": 1,
                "module": MODULE,
            },
            {
                "fieldname": "reconciliation_batch",
                "label": "Payment Reconciliation Batch",
                "fieldtype": "Link",
                "options": "NDIS Payment Reconciliation Batch",
                "insert_after": "reconciliation_section",
                "read_only": 1,
                "module": MODULE,
            },
            {
                "fieldname": "reconciliation_line",
                "label": "Payment Reconciliation Line",
                "fieldtype": "Link",
                "options": "NDIS Payment Reconciliation Line",
                "insert_after": "reconciliation_batch",
                "read_only": 1,
                "module": MODULE,
            },
            {
                "fieldname": "payment_entry",
                "label": "Payment Entry",
                "fieldtype": "Link",
                "options": "Payment Entry",
                "insert_after": "reconciliation_line",
                "read_only": 1,
                "module": MODULE,
            },
            {
                "fieldname": "payment_date",
                "label": "Payment Date",
                "fieldtype": "Date",
                "insert_after": "payment_entry",
                "read_only": 1,
                "module": MODULE,
            },
            {
                "fieldname": "remittance_reference",
                "label": "Remittance Reference",
                "fieldtype": "Data",
                "insert_after": "payment_date",
                "read_only": 1,
                "module": MODULE,
            },
            {
                "fieldname": "reconciliation_status",
                "label": "Reconciliation Status",
                "fieldtype": "Select",
                "options": "\nNot Reconciled\nReconciled\nException\nFollow Up Required\nClosed",
                "default": "Not Reconciled",
                "insert_after": "remittance_reference",
                "read_only": 1,
                "module": MODULE,
            },
            {
                "fieldname": "recovery_status",
                "label": "Recovery Status",
                "fieldtype": "Select",
                "options": "\nNot Required\nOpen\nIn Follow Up\nEscalated\nResolved\nWritten Off",
                "default": "Not Required",
                "insert_after": "reconciliation_status",
                "module": MODULE,
            },
            {
                "fieldname": "follow_up_due_date",
                "label": "Follow Up Due Date",
                "fieldtype": "Date",
                "insert_after": "recovery_status",
                "module": MODULE,
            },
        ],
        "Payment Entry": [
            {
                "fieldname": "custom_ndis_payment_section",
                "label": "NDIS Payment Reconciliation",
                "fieldtype": "Section Break",
                "insert_after": "reference_no",
                "collapsible": 1,
                "module": MODULE,
            },
            {
                "fieldname": "custom_is_ndis_payment",
                "label": "Is NDIS Payment",
                "fieldtype": "Check",
                "insert_after": "custom_ndis_payment_section",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_payment_reconciliation_batch",
                "label": "NDIS Payment Reconciliation Batch",
                "fieldtype": "Link",
                "options": "NDIS Payment Reconciliation Batch",
                "insert_after": "custom_is_ndis_payment",
                "depends_on": "eval:doc.custom_is_ndis_payment",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_claim_batch",
                "label": "NDIS Claim Batch",
                "fieldtype": "Link",
                "options": "NDIS Claim Batch",
                "insert_after": "custom_ndis_payment_reconciliation_batch",
                "depends_on": "eval:doc.custom_is_ndis_payment",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_funding_source",
                "label": "NDIS Funding Source",
                "fieldtype": "Link",
                "options": "NDIS Funding Source",
                "insert_after": "custom_ndis_claim_batch",
                "depends_on": "eval:doc.custom_is_ndis_payment",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_remittance_reference",
                "label": "NDIS Remittance Reference",
                "fieldtype": "Data",
                "insert_after": "custom_ndis_funding_source",
                "depends_on": "eval:doc.custom_is_ndis_payment",
                "module": MODULE,
            },
        ],
        "NDIS Funding Leakage Register": [
            {
                "fieldname": "claim_batch",
                "label": "Claim Batch",
                "fieldtype": "Link",
                "options": "NDIS Claim Batch",
                "insert_after": "source_name",
                "module": MODULE,
            },
            {
                "fieldname": "claim_line",
                "label": "Claim Line",
                "fieldtype": "Link",
                "options": "NDIS Claim Line",
                "insert_after": "claim_batch",
                "module": MODULE,
            },
            {
                "fieldname": "sales_invoice",
                "label": "Sales Invoice",
                "fieldtype": "Link",
                "options": "Sales Invoice",
                "insert_after": "claim_line",
                "module": MODULE,
            },
            {
                "fieldname": "sales_invoice_item",
                "label": "Sales Invoice Item Row ID",
                "fieldtype": "Data",
                "insert_after": "sales_invoice",
                "module": MODULE,
            },
            {
                "fieldname": "payment_reconciliation_batch",
                "label": "Payment Reconciliation Batch",
                "fieldtype": "Link",
                "options": "NDIS Payment Reconciliation Batch",
                "insert_after": "sales_invoice_item",
                "module": MODULE,
            },
            {
                "fieldname": "payment_reconciliation_line",
                "label": "Payment Reconciliation Line",
                "fieldtype": "Link",
                "options": "NDIS Payment Reconciliation Line",
                "insert_after": "payment_reconciliation_batch",
                "module": MODULE,
            },
            {
                "fieldname": "recovery_status",
                "label": "Recovery Status",
                "fieldtype": "Select",
                "options": "\nOpen\nIn Follow Up\nEscalated\nResolved\nWritten Off\nClosed",
                "default": "Open",
                "insert_after": "status",
                "module": MODULE,
            },
            {
                "fieldname": "follow_up_due_date",
                "label": "Follow Up Due Date",
                "fieldtype": "Date",
                "insert_after": "recovery_status",
                "module": MODULE,
            },
            {
                "fieldname": "assigned_to",
                "label": "Assigned To",
                "fieldtype": "Link",
                "options": "User",
                "insert_after": "follow_up_due_date",
                "module": MODULE,
            },
        ],
    }

    create_custom_fields(custom_fields, update=True)


@frappe.whitelist()
def health_check():
    doctypes = {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE1E_DOCTYPES}

    claim_line_fields = {
        fieldname: bool(
            frappe.db.exists(
                "Custom Field",
                {"dt": "NDIS Claim Line", "fieldname": fieldname},
            )
        )
        for fieldname in CLAIM_LINE_FIELDS
    }

    payment_entry_fields = {
        fieldname: bool(
            frappe.db.exists(
                "Custom Field",
                {"dt": "Payment Entry", "fieldname": fieldname},
            )
        )
        for fieldname in PAYMENT_ENTRY_FIELDS
    }

    funding_leakage_fields = {
        fieldname: bool(
            frappe.db.exists(
                "Custom Field",
                {"dt": "NDIS Funding Leakage Register", "fieldname": fieldname},
            )
        )
        for fieldname in FUNDING_LEAKAGE_FIELDS
    }

    return {
        "doctypes": doctypes,
        "claim_line_fields": claim_line_fields,
        "payment_entry_fields": payment_entry_fields,
        "funding_leakage_fields": funding_leakage_fields,
    }
