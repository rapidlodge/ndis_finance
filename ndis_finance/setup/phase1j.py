import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from ndis_finance.setup.install import MODULE, _create_doctype


PHASE1J_DOCTYPES = [
    "NDIS Recovery Communication Template",
    "NDIS Recovery Email Draft",
]

RECOVERY_CASE_FIELDS = [
    "last_email_draft",
    "communication_status",
    "last_communication_on",
    "next_communication_due_date",
]

RECOVERY_ACTIVITY_FIELDS = [
    "email_draft",
]

TEMPLATES = [
    {
        "template_name": "NDIS Plan Manager Follow Up",
        "template_type": "Plan Manager Follow Up",
        "case_type": "Plan Manager Follow Up",
        "subject_template": "Follow-up request for NDIS invoice {{ sales_invoice.name or case.sales_invoice }}",
        "body_template": """Hi {{ case.contact_name or 'Team' }},

I hope you are well.

We are following up regarding the NDIS invoice below:

Participant: {{ participant.customer_name or case.participant }}
Invoice: {{ sales_invoice.name or case.sales_invoice }}
Expected Amount: ${{ "%.2f"|format(case.expected_amount or 0) }}
Outstanding Amount: ${{ "%.2f"|format(case.outstanding_amount or 0) }}

Could you please confirm the payment status or advise if you require a copy of the invoice/remittance details?

Thank you.

Kind regards,
Finance Team""",
        "default_for_type": 1,
    },
    {
        "template_name": "NDIS Remittance Request",
        "template_type": "Remittance Request",
        "case_type": "Payment Shortfall",
        "subject_template": "Remittance advice request - {{ sales_invoice.name or case.sales_invoice }}",
        "body_template": """Hi {{ case.contact_name or 'Team' }},

I hope you are well.

Could you please send through the remittance advice for the payment relating to:

Participant: {{ participant.customer_name or case.participant }}
Invoice: {{ sales_invoice.name or case.sales_invoice }}
Claim Line: {{ claim_line.name if claim_line else case.claim_line }}
Expected Amount: ${{ "%.2f"|format(case.expected_amount or 0) }}
Paid Amount: ${{ "%.2f"|format(case.paid_amount or 0) }}
Difference: ${{ "%.2f"|format(case.outstanding_amount or 0) }}

This will help us reconcile the payment correctly.

Thank you.

Kind regards,
Finance Team""",
        "default_for_type": 1,
    },
    {
        "template_name": "NDIS Invoice Resend",
        "template_type": "Invoice Resend",
        "case_type": "Invoice Overdue",
        "subject_template": "Invoice copy attached/requested - {{ sales_invoice.name or case.sales_invoice }}",
        "body_template": """Hi {{ case.contact_name or 'Team' }},

As requested, we are resending the invoice details below:

Participant: {{ participant.customer_name or case.participant }}
Invoice: {{ sales_invoice.name or case.sales_invoice }}
Amount: ${{ "%.2f"|format(case.expected_amount or 0) }}

Please let us know if anything further is required to process payment.

Kind regards,
Finance Team""",
        "default_for_type": 1,
    },
    {
        "template_name": "NDIS Rejected Claim Follow Up",
        "template_type": "NDIA Rejection Follow Up",
        "case_type": "Rejected Claim",
        "subject_template": "NDIS rejected claim follow-up - {{ claim_line.support_item_number if claim_line else '' }}",
        "body_template": """Hi {{ case.contact_name or 'Team' }},

We are following up on a rejected NDIS claim.

Participant: {{ participant.customer_name or case.participant }}
Invoice: {{ sales_invoice.name or case.sales_invoice }}
Claim Line: {{ claim_line.name if claim_line else case.claim_line }}
Support Item: {{ claim_line.support_item_number if claim_line else '' }}
Service Date: {{ claim_line.service_date if claim_line else '' }}
Claim Amount: ${{ "%.2f"|format(case.expected_amount or 0) }}

Reason/Note:
{{ case.case_summary or case.resolution_note or 'Please confirm the rejection reason and any required correction.' }}

Could you please advise the required correction or whether this can be reprocessed?

Kind regards,
Finance Team""",
        "default_for_type": 1,
    },
    {
        "template_name": "NDIS Short Payment Follow Up",
        "template_type": "Short Payment Follow Up",
        "case_type": "Payment Shortfall",
        "subject_template": "Short payment follow-up - {{ sales_invoice.name or case.sales_invoice }}",
        "body_template": """Hi {{ case.contact_name or 'Team' }},

We are following up on a short payment identified during reconciliation.

Participant: {{ participant.customer_name or case.participant }}
Invoice: {{ sales_invoice.name or case.sales_invoice }}
Expected Amount: ${{ "%.2f"|format(case.expected_amount or 0) }}
Paid Amount: ${{ "%.2f"|format(case.paid_amount or 0) }}
Shortfall: ${{ "%.2f"|format(case.outstanding_amount or 0) }}

Could you please confirm whether the balance will be paid, or advise the reason for the short payment?

Thank you.

Kind regards,
Finance Team""",
        "default_for_type": 1,
    },
    {
        "template_name": "NDIS Write Off Internal Review",
        "template_type": "Write Off Internal Review",
        "case_type": "Write Off Review",
        "subject_template": "Write-off review required - {{ case.case_id }}",
        "body_template": """Hi Team,

Please review the following NDIS recovery case for possible write-off control approval.

Recovery Case: {{ case.name }}
Case ID: {{ case.case_id }}
Case Type: {{ case.case_type }}
Participant: {{ participant.customer_name or case.participant }}
Invoice: {{ sales_invoice.name or case.sales_invoice }}
Outstanding Amount: ${{ "%.2f"|format(case.outstanding_amount or 0) }}

Case Summary:
{{ case.case_summary or '' }}

Current Resolution Note:
{{ case.resolution_note or '' }}

Please review and confirm the approved accounting treatment separately through ERPNext accounting controls.

Kind regards,
Finance Team""",
        "default_for_type": 1,
    },
]


@frappe.whitelist()
def install():
    validate_phase1i()
    create_recovery_communication_template_doctype()
    create_recovery_email_draft_doctype()
    create_phase1j_custom_fields()
    seed_templates()
    frappe.db.commit()
    return health_check()


def validate_phase1i():
    required = [
        "NDIS Recovery Case",
        "NDIS Recovery Activity",
        "NDIS Funding Leakage Register",
        "NDIS Claim Line",
        "Sales Invoice",
        "Customer",
        "User",
    ]

    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]

    if missing:
        frappe.throw(
            _("Phase 1J requires previous phases. Missing DocTypes: {0}").format(
                ", ".join(missing)
            )
        )


def create_recovery_communication_template_doctype():
    _create_doctype(
        name="NDIS Recovery Communication Template",
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
                "fieldname": "template_type",
                "label": "Template Type",
                "fieldtype": "Select",
                "options": "\nPlan Manager Follow Up\nRemittance Request\nInvoice Resend\nNDIA Rejection Follow Up\nShort Payment Follow Up\nWrite Off Internal Review\nOther",
                "reqd": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "case_type",
                "label": "Default Case Type",
                "fieldtype": "Select",
                "options": "\nPayment Shortfall\nRejected Claim\nPlan Manager Follow Up\nNDIA Follow Up\nSelf Managed Follow Up\nInvoice Overdue\nRemittance Request\nInvoice Resend\nWrite Off Review\nOther",
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
                "fieldname": "default_for_type",
                "label": "Default For Type",
                "fieldtype": "Check",
                "default": "0",
            },
            {
                "fieldname": "subject_template",
                "label": "Subject Template",
                "fieldtype": "Data",
                "reqd": 1,
            },
            {
                "fieldname": "body_template",
                "label": "Body Template",
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


def create_recovery_email_draft_doctype():
    _create_doctype(
        name="NDIS Recovery Email Draft",
        autoname="field:draft_id",
        title_field="draft_id",
        fields=[
            {
                "fieldname": "draft_id",
                "label": "Draft ID",
                "fieldtype": "Data",
                "reqd": 1,
                "unique": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "status",
                "label": "Status",
                "fieldtype": "Select",
                "options": "\nDraft\nApproved\nSent Manually\nCancelled",
                "default": "Draft",
                "in_list_view": 1,
            },
            {
                "fieldname": "draft_type",
                "label": "Draft Type",
                "fieldtype": "Select",
                "options": "\nPlan Manager Follow Up\nRemittance Request\nInvoice Resend\nNDIA Rejection Follow Up\nShort Payment Follow Up\nWrite Off Internal Review\nOther",
                "in_list_view": 1,
            },
            {
                "fieldname": "template",
                "label": "Template",
                "fieldtype": "Link",
                "options": "NDIS Recovery Communication Template",
                "in_list_view": 1,
            },
            {
                "fieldname": "recovery_case",
                "label": "Recovery Case",
                "fieldtype": "Link",
                "options": "NDIS Recovery Case",
                "reqd": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "source_section",
                "label": "Source Links",
                "fieldtype": "Section Break",
            },
            {
                "fieldname": "participant",
                "label": "Participant",
                "fieldtype": "Link",
                "options": "Customer",
            },
            {
                "fieldname": "sales_invoice",
                "label": "Sales Invoice",
                "fieldtype": "Link",
                "options": "Sales Invoice",
            },
            {
                "fieldname": "claim_line",
                "label": "Claim Line",
                "fieldtype": "Link",
                "options": "NDIS Claim Line",
            },
            {
                "fieldname": "funding_leakage",
                "label": "Funding Leakage",
                "fieldtype": "Link",
                "options": "NDIS Funding Leakage Register",
            },
            {
                "fieldname": "communication_section",
                "label": "Email Content",
                "fieldtype": "Section Break",
            },
            {
                "fieldname": "recipient_email",
                "label": "Recipient Email",
                "fieldtype": "Data",
                "options": "Email",
                "in_list_view": 1,
            },
            {
                "fieldname": "cc",
                "label": "CC",
                "fieldtype": "Small Text",
            },
            {
                "fieldname": "bcc",
                "label": "BCC",
                "fieldtype": "Small Text",
            },
            {
                "fieldname": "subject",
                "label": "Subject",
                "fieldtype": "Data",
                "reqd": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "body",
                "label": "Body",
                "fieldtype": "Text Editor",
                "reqd": 1,
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
                "read_only": 1,
            },
            {
                "fieldname": "paid_amount",
                "label": "Paid Amount",
                "fieldtype": "Currency",
                "read_only": 1,
            },
            {
                "fieldname": "outstanding_amount",
                "label": "Outstanding Amount",
                "fieldtype": "Currency",
                "read_only": 1,
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
                "fieldname": "approved_on",
                "label": "Approved On",
                "fieldtype": "Datetime",
                "read_only": 1,
            },
            {
                "fieldname": "approved_by",
                "label": "Approved By",
                "fieldtype": "Link",
                "options": "User",
                "read_only": 1,
            },
            {
                "fieldname": "sent_manually_on",
                "label": "Sent Manually On",
                "fieldtype": "Datetime",
                "read_only": 1,
            },
            {
                "fieldname": "sent_manually_by",
                "label": "Sent Manually By",
                "fieldtype": "Link",
                "options": "User",
                "read_only": 1,
            },
            {
                "fieldname": "activity",
                "label": "Recovery Activity",
                "fieldtype": "Link",
                "options": "NDIS Recovery Activity",
                "read_only": 1,
            },
            {
                "fieldname": "internal_note",
                "label": "Internal Note",
                "fieldtype": "Small Text",
            },
        ],
    )


def create_phase1j_custom_fields():
    custom_fields = {
        "NDIS Recovery Case": [
            {
                "fieldname": "communication_section",
                "label": "Communication Control",
                "fieldtype": "Section Break",
                "insert_after": "last_activity_note",
                "collapsible": 1,
                "module": MODULE,
            },
            {
                "fieldname": "last_email_draft",
                "label": "Last Email Draft",
                "fieldtype": "Link",
                "options": "NDIS Recovery Email Draft",
                "insert_after": "communication_section",
                "read_only": 1,
                "module": MODULE,
            },
            {
                "fieldname": "communication_status",
                "label": "Communication Status",
                "fieldtype": "Select",
                "options": "\nNot Started\nDraft Created\nApproved\nSent Manually\nCancelled",
                "default": "Not Started",
                "insert_after": "last_email_draft",
                "read_only": 1,
                "module": MODULE,
            },
            {
                "fieldname": "last_communication_on",
                "label": "Last Communication On",
                "fieldtype": "Datetime",
                "insert_after": "communication_status",
                "read_only": 1,
                "module": MODULE,
            },
            {
                "fieldname": "next_communication_due_date",
                "label": "Next Communication Due Date",
                "fieldtype": "Date",
                "insert_after": "last_communication_on",
                "module": MODULE,
            },
        ],
        "NDIS Recovery Activity": [
            {
                "fieldname": "email_draft",
                "label": "Email Draft",
                "fieldtype": "Link",
                "options": "NDIS Recovery Email Draft",
                "insert_after": "attachment",
                "read_only": 1,
                "module": MODULE,
            },
        ],
    }

    create_custom_fields(custom_fields, update=True)


def seed_templates():
    for template in TEMPLATES:
        existing = frappe.db.exists(
            "NDIS Recovery Communication Template",
            template["template_name"],
        )

        if existing:
            doc = frappe.get_doc("NDIS Recovery Communication Template", existing)
        else:
            doc = frappe.new_doc("NDIS Recovery Communication Template")
            doc.template_name = template["template_name"]

        doc.template_type = template["template_type"]
        doc.case_type = template["case_type"]
        doc.active = 1
        doc.default_for_type = template.get("default_for_type", 0)
        doc.subject_template = template["subject_template"]
        doc.body_template = template["body_template"]
        doc.save(ignore_permissions=True)


@frappe.whitelist()
def health_check():
    doctypes = {
        dt: bool(frappe.db.exists("DocType", dt))
        for dt in PHASE1J_DOCTYPES
    }

    recovery_case_fields = {
        fieldname: bool(
            frappe.db.exists(
                "Custom Field",
                {"dt": "NDIS Recovery Case", "fieldname": fieldname},
            )
        )
        for fieldname in RECOVERY_CASE_FIELDS
    }

    recovery_activity_fields = {
        fieldname: bool(
            frappe.db.exists(
                "Custom Field",
                {"dt": "NDIS Recovery Activity", "fieldname": fieldname},
            )
        )
        for fieldname in RECOVERY_ACTIVITY_FIELDS
    }

    templates = {
        template["template_name"]: bool(
            frappe.db.exists(
                "NDIS Recovery Communication Template",
                template["template_name"],
            )
        )
        for template in TEMPLATES
    }

    return {
        "doctypes": doctypes,
        "recovery_case_fields": recovery_case_fields,
        "recovery_activity_fields": recovery_activity_fields,
        "templates": templates,
    }
