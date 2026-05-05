import frappe
from frappe import _
from frappe.utils import getdate


def validate_sales_invoice(doc, method=None):
    """
    Safe NDIS invoice validation.

    Rules:
    - Only runs when 'Is NDIS Invoice' is ticked.
    - Does not alter GL Entry.
    - Does not change submitted accounting records.
    - Ensures NDIS invoice lines have key claim-control data.
    """

    if not getattr(doc, "custom_is_ndis_invoice", 0):
        return

    sync_header_values_to_lines(doc)
    validate_ndis_invoice_header(doc)
    validate_ndis_invoice_lines(doc)
    validate_participant_billing_hold(doc)


def sync_header_values_to_lines(doc):
    """
    Push common header values to item rows when row value is blank.
    This keeps data entry easier without removing row-level flexibility.
    """

    for row in doc.items:
        if not getattr(row, "custom_ndis_participant", None):
            row.custom_ndis_participant = doc.customer

        if not getattr(row, "custom_ndis_house", None):
            row.custom_ndis_house = getattr(doc, "custom_ndis_house", None)

        if not getattr(row, "custom_ndis_funding_source", None):
            row.custom_ndis_funding_source = getattr(doc, "custom_ndis_funding_source", None)


def validate_ndis_invoice_header(doc):
    if not getattr(doc, "customer", None):
        frappe.throw(_("Customer is required for NDIS invoice."))

    if not getattr(doc, "custom_ndis_funding_source", None):
        frappe.throw(_("Funding Source is required for NDIS invoice."))

    customer_is_ndis = frappe.db.get_value(
        "Customer",
        doc.customer,
        "custom_is_ndis_participant",
    )

    if not customer_is_ndis:
        frappe.msgprint(
            _(
                "This invoice is marked as NDIS Invoice, but the Customer is not marked as an NDIS Participant."
            ),
            indicator="orange",
            alert=True,
        )


def validate_ndis_invoice_lines(doc):
    missing = []

    for row in doc.items:
        row_label = row.idx or row.item_code or "Unknown Row"

        if not getattr(row, "custom_ndis_service_date", None):
            missing.append(f"Row {row_label}: Service Date is missing")

        if getattr(row, "custom_ndis_claimable", 0):
            if not getattr(row, "custom_ndis_support_item", None):
                missing.append(f"Row {row_label}: NDIS Support Item is missing")

            if not getattr(row, "custom_ndis_service_type", None):
                missing.append(f"Row {row_label}: NDIS Service Type is missing")

            if not getattr(row, "custom_ndis_funding_source", None):
                missing.append(f"Row {row_label}: Funding Source is missing")

    if missing:
        frappe.throw(
            _("NDIS invoice cannot be saved until these issues are fixed:<br><br>{0}").format(
                "<br>".join(missing)
            )
        )


def validate_participant_billing_hold(doc):
    profile = getattr(doc, "custom_ndis_participant_profile", None)

    if not profile:
        return

    billing_hold, reason, plan_start, plan_end = frappe.db.get_value(
        "NDIS Participant Financial Profile",
        profile,
        ["billing_hold", "billing_hold_reason", "plan_start_date", "plan_end_date"],
    ) or (0, None, None, None)

    if billing_hold:
        frappe.throw(
            _("Participant is on billing hold. Reason: {0}").format(
                reason or "No reason provided"
            )
        )

    posting_date = getdate(doc.posting_date) if doc.posting_date else None
    plan_start = getdate(plan_start) if plan_start else None
    plan_end = getdate(plan_end) if plan_end else None

    if plan_start and posting_date and posting_date < plan_start:
        frappe.msgprint(
            _("Invoice posting date is before participant plan start date."),
            indicator="orange",
            alert=True,
        )

    if plan_end and posting_date and posting_date > plan_end:
        frappe.msgprint(
            _("Invoice posting date is after participant plan end date."),
            indicator="orange",
            alert=True,
        )
