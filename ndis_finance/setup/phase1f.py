import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from ndis_finance.setup.install import MODULE, _create_doctype


PHASE1F_DOCTYPES = [
    "NDIS Recovery Case",
    "NDIS Recovery Activity",
]

SALES_INVOICE_FIELDS = [
    "custom_ndis_recovery_case_count",
    "custom_ndis_last_recovery_case",
    "custom_ndis_last_follow_up_on",
    "custom_ndis_next_follow_up_date",
]

FUNDING_LEAKAGE_FIELDS = [
    "recovery_case",
]

CLAIM_LINE_FIELDS = [
    "recovery_case",
]

PAYMENT_RECONCILIATION_LINE_FIELDS = [
    "recovery_case",
]


@frappe.whitelist()
def install():
    validate_phase1e()
    create_recovery_case_doctype()
    create_recovery_activity_doctype()
    ensure_recovery_activity_autoname()
    create_phase1f_custom_fields()
    frappe.db.commit()
    return health_check()


def validate_phase1e():
    required = [
        "NDIS Claim Batch",
        "NDIS Claim Line",
        "NDIS Funding Leakage Register",
        "NDIS Payment Reconciliation Batch",
        "NDIS Payment Reconciliation Line",
        "Sales Invoice",
        "Customer",
        "User",
    ]

    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]

    if missing:
        frappe.throw(
            _("Phase 1F requires previous phases. Missing DocTypes: {0}").format(
                ", ".join(missing)
            )
        )


def create_recovery_case_doctype():
    _create_doctype(
        name="NDIS Recovery Case",
        autoname="field:case_id",
        title_field="case_id",
        fields=[
            {
                "fieldname": "case_id",
                "label": "Case ID",
                "fieldtype": "Data",
                "reqd": 1,
                "unique": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "case_type",
                "label": "Case Type",
                "fieldtype": "Select",
                "options": "\nPayment Shortfall\nRejected Claim\nPlan Manager Follow Up\nNDIA Follow Up\nSelf Managed Follow Up\nInvoice Overdue\nRemittance Request\nInvoice Resend\nWrite Off Review\nOther",
                "default": "Payment Shortfall",
                "in_list_view": 1,
            },
            {
                "fieldname": "status",
                "label": "Status",
                "fieldtype": "Select",
                "options": "\nOpen\nIn Follow Up\nWaiting For Response\nEscalated\nResolved\nWritten Off\nClosed",
                "default": "Open",
                "in_list_view": 1,
            },
            {
                "fieldname": "priority",
                "label": "Priority",
                "fieldtype": "Select",
                "options": "\nLow\nMedium\nHigh\nCritical",
                "default": "Medium",
                "in_list_view": 1,
            },
            {
                "fieldname": "assigned_to",
                "label": "Assigned To",
                "fieldtype": "Link",
                "options": "User",
                "in_list_view": 1,
            },
            {
                "fieldname": "company",
                "label": "Company",
                "fieldtype": "Link",
                "options": "Company",
            },
            {
                "fieldname": "party_section",
                "label": "Party / Participant",
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
            },
            {
                "fieldname": "funding_source",
                "label": "Funding Source",
                "fieldtype": "Link",
                "options": "NDIS Funding Source",
                "in_list_view": 1,
            },
            {
                "fieldname": "payer_name",
                "label": "Payer / Plan Manager Name",
                "fieldtype": "Data",
            },
            {
                "fieldname": "contact_name",
                "label": "Contact Name",
                "fieldtype": "Data",
            },
            {
                "fieldname": "contact_email",
                "label": "Contact Email",
                "fieldtype": "Data",
                "options": "Email",
            },
            {
                "fieldname": "contact_phone",
                "label": "Contact Phone",
                "fieldtype": "Data",
                "options": "Phone",
            },
            {
                "fieldname": "source_section",
                "label": "Source Links",
                "fieldtype": "Section Break",
            },
            {
                "fieldname": "funding_leakage",
                "label": "Funding Leakage",
                "fieldtype": "Link",
                "options": "NDIS Funding Leakage Register",
                "in_list_view": 1,
            },
            {
                "fieldname": "claim_batch",
                "label": "Claim Batch",
                "fieldtype": "Link",
                "options": "NDIS Claim Batch",
            },
            {
                "fieldname": "claim_line",
                "label": "Claim Line",
                "fieldtype": "Link",
                "options": "NDIS Claim Line",
                "in_list_view": 1,
            },
            {
                "fieldname": "payment_reconciliation_batch",
                "label": "Payment Reconciliation Batch",
                "fieldtype": "Link",
                "options": "NDIS Payment Reconciliation Batch",
            },
            {
                "fieldname": "payment_reconciliation_line",
                "label": "Payment Reconciliation Line",
                "fieldtype": "Link",
                "options": "NDIS Payment Reconciliation Line",
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
                "fieldname": "amount_section",
                "label": "Amounts",
                "fieldtype": "Section Break",
            },
            {
                "fieldname": "expected_amount",
                "label": "Expected Amount",
                "fieldtype": "Currency",
            },
            {
                "fieldname": "paid_amount",
                "label": "Paid Amount",
                "fieldtype": "Currency",
            },
            {
                "fieldname": "outstanding_amount",
                "label": "Outstanding / Variance Amount",
                "fieldtype": "Currency",
                "in_list_view": 1,
            },
            {
                "fieldname": "recovered_amount",
                "label": "Recovered Amount",
                "fieldtype": "Currency",
                "default": "0",
            },
            {
                "fieldname": "written_off_amount",
                "label": "Written Off Amount",
                "fieldtype": "Currency",
                "default": "0",
            },
            {
                "fieldname": "timeline_section",
                "label": "Timeline",
                "fieldtype": "Section Break",
            },
            {
                "fieldname": "case_opened_on",
                "label": "Case Opened On",
                "fieldtype": "Datetime",
                "read_only": 1,
            },
            {
                "fieldname": "last_follow_up_on",
                "label": "Last Follow Up On",
                "fieldtype": "Datetime",
                "read_only": 1,
            },
            {
                "fieldname": "next_follow_up_date",
                "label": "Next Follow Up Date",
                "fieldtype": "Date",
                "in_list_view": 1,
            },
            {
                "fieldname": "escalated_on",
                "label": "Escalated On",
                "fieldtype": "Datetime",
                "read_only": 1,
            },
            {
                "fieldname": "resolved_on",
                "label": "Resolved / Closed On",
                "fieldtype": "Datetime",
                "read_only": 1,
            },
            {
                "fieldname": "notes_section",
                "label": "Notes",
                "fieldtype": "Section Break",
            },
            {
                "fieldname": "case_summary",
                "label": "Case Summary",
                "fieldtype": "Small Text",
            },
            {
                "fieldname": "last_activity_note",
                "label": "Last Activity Note",
                "fieldtype": "Small Text",
                "read_only": 1,
            },
            {
                "fieldname": "resolution_note",
                "label": "Resolution / Write-Off Note",
                "fieldtype": "Small Text",
            },
        ],
    )


def create_recovery_activity_doctype():
    _create_doctype(
        name="NDIS Recovery Activity",
        autoname="hash",
        title_field="recovery_case",
        fields=[
            {
                "fieldname": "recovery_case",
                "label": "Recovery Case",
                "fieldtype": "Link",
                "options": "NDIS Recovery Case",
                "reqd": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "activity_datetime",
                "label": "Activity Date/Time",
                "fieldtype": "Datetime",
                "read_only": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "activity_type",
                "label": "Activity Type",
                "fieldtype": "Select",
                "options": "\nCall\nEmail\nSMS\nNote\nRemittance Requested\nInvoice Resent\nEscalation\nPayment Received\nWrite Off Review\nWrite Off Approved\nResolved\nOther",
                "default": "Note",
                "in_list_view": 1,
            },
            {
                "fieldname": "performed_by",
                "label": "Performed By",
                "fieldtype": "Link",
                "options": "User",
                "read_only": 1,
            },
            {
                "fieldname": "outcome",
                "label": "Outcome",
                "fieldtype": "Select",
                "options": "\nNo Answer\nLeft Message\nSpoke to Contact\nAwaiting Response\nPromised Payment\nRemittance Requested\nInvoice Resent\nEscalated\nResolved\nWrite Off Requested\nWrite Off Approved\nClosed\nOther",
                "in_list_view": 1,
            },
            {
                "fieldname": "next_follow_up_date",
                "label": "Next Follow Up Date",
                "fieldtype": "Date",
            },
            {
                "fieldname": "activity_note",
                "label": "Activity Note",
                "fieldtype": "Small Text",
            },
            {
                "fieldname": "attachment",
                "label": "Attachment",
                "fieldtype": "Attach",
            },
        ],
    )


def ensure_recovery_activity_autoname():
    if frappe.db.exists("DocType", "NDIS Recovery Activity"):
        frappe.db.set_value(
            "DocType",
            "NDIS Recovery Activity",
            "autoname",
            "hash",
            update_modified=False,
        )


def create_phase1f_custom_fields():
    custom_fields = {
        "Sales Invoice": [
            {
                "fieldname": "custom_ndis_recovery_status",
                "label": "NDIS Recovery Status",
                "fieldtype": "Select",
                "options": "\nNot Due\nFollow Up Required\nIn Recovery\nIn Follow Up\nEscalated\nResolved\nDo Not Recover\nWritten Off",
                "default": "Not Due",
                "insert_after": "custom_ndis_billing_status",
                "read_only": 1,
                "depends_on": "eval:doc.custom_is_ndis_invoice",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_recovery_case_count",
                "label": "NDIS Recovery Case Count",
                "fieldtype": "Int",
                "insert_after": "custom_ndis_batching_note",
                "read_only": 1,
                "depends_on": "eval:doc.custom_is_ndis_invoice",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_last_recovery_case",
                "label": "Last NDIS Recovery Case",
                "fieldtype": "Link",
                "options": "NDIS Recovery Case",
                "insert_after": "custom_ndis_recovery_case_count",
                "read_only": 1,
                "depends_on": "eval:doc.custom_is_ndis_invoice",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_last_follow_up_on",
                "label": "Last Follow Up On",
                "fieldtype": "Datetime",
                "insert_after": "custom_ndis_last_recovery_case",
                "read_only": 1,
                "depends_on": "eval:doc.custom_is_ndis_invoice",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_next_follow_up_date",
                "label": "Next Follow Up Date",
                "fieldtype": "Date",
                "insert_after": "custom_ndis_last_follow_up_on",
                "read_only": 1,
                "depends_on": "eval:doc.custom_is_ndis_invoice",
                "module": MODULE,
            },
        ],
        "NDIS Funding Leakage Register": [
            {
                "fieldname": "recovery_case",
                "label": "Recovery Case",
                "fieldtype": "Link",
                "options": "NDIS Recovery Case",
                "insert_after": "assigned_to",
                "read_only": 1,
                "module": MODULE,
            },
        ],
        "NDIS Claim Line": [
            {
                "fieldname": "recovery_case",
                "label": "Recovery Case",
                "fieldtype": "Link",
                "options": "NDIS Recovery Case",
                "insert_after": "follow_up_due_date",
                "read_only": 1,
                "module": MODULE,
            },
        ],
        "NDIS Payment Reconciliation Line": [
            {
                "fieldname": "recovery_case",
                "label": "Recovery Case",
                "fieldtype": "Link",
                "options": "NDIS Recovery Case",
                "insert_after": "funding_leakage",
                "read_only": 1,
                "module": MODULE,
            },
        ],
    }

    create_custom_fields(custom_fields, update=True)


@frappe.whitelist()
def health_check():
    doctypes = {
        dt: bool(frappe.db.exists("DocType", dt))
        for dt in PHASE1F_DOCTYPES
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

    funding_leakage_fields = {
        fieldname: bool(
            frappe.db.exists(
                "Custom Field",
                {"dt": "NDIS Funding Leakage Register", "fieldname": fieldname},
            )
        )
        for fieldname in FUNDING_LEAKAGE_FIELDS
    }

    claim_line_fields = {
        fieldname: bool(
            frappe.db.exists(
                "Custom Field",
                {"dt": "NDIS Claim Line", "fieldname": fieldname},
            )
        )
        for fieldname in CLAIM_LINE_FIELDS
    }

    payment_reconciliation_line_fields = {
        fieldname: bool(
            frappe.db.exists(
                "Custom Field",
                {"dt": "NDIS Payment Reconciliation Line", "fieldname": fieldname},
            )
        )
        for fieldname in PAYMENT_RECONCILIATION_LINE_FIELDS
    }

    return {
        "doctypes": doctypes,
        "sales_invoice_fields": sales_invoice_fields,
        "funding_leakage_fields": funding_leakage_fields,
        "claim_line_fields": claim_line_fields,
        "payment_reconciliation_line_fields": payment_reconciliation_line_fields,
    }
