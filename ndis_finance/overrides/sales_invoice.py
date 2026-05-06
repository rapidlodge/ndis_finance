import frappe
from frappe import _
from frappe.utils import flt, getdate

from ndis_finance.services.budget_control import validate_budget_and_service_booking


def validate_sales_invoice(doc, method=None):
    """
    Safe NDIS invoice validation.

    Rules:
    - Only runs when 'Is NDIS Invoice' is ticked.
    - Does not alter GL Entry.
    - Does not change submitted accounting records.
    - Pulls NDIS mapping from Item where available.
    - Checks NDIS support item, service date, service type, funding source.
    - Checks invoice rate against NDIS price limit.
    """

    if not getattr(doc, "custom_is_ndis_invoice", 0):
        return

    apply_item_ndis_mapping(doc)
    sync_header_values_to_lines(doc)
    apply_ndis_accounting_dimensions(doc)
    validate_ndis_invoice_header(doc)
    validate_ndis_invoice_lines(doc)
    validate_ndis_price_limits(doc)
    validate_budget_and_service_booking(doc)
    validate_participant_billing_hold(doc)


def apply_item_ndis_mapping(doc):
    """
    Pull default NDIS mapping from ERPNext Item.
    This avoids manual coding on every invoice line.
    """

    for row in doc.items:
        if not getattr(row, "item_code", None):
            continue

        item_map = frappe.db.get_value(
            "Item",
            row.item_code,
            [
                "custom_is_ndis_billable_item",
                "custom_ndis_support_item",
                "custom_ndis_service_type",
                "custom_ndis_funding_source",
                "custom_ndis_default_claimable",
                "custom_ndis_gst_treatment",
            ],
            as_dict=True,
        )

        if not item_map or not item_map.custom_is_ndis_billable_item:
            continue

        if not getattr(row, "custom_ndis_support_item", None):
            row.custom_ndis_support_item = item_map.custom_ndis_support_item

        if not getattr(row, "custom_ndis_service_type", None):
            row.custom_ndis_service_type = item_map.custom_ndis_service_type

        if not getattr(row, "custom_ndis_funding_source", None):
            row.custom_ndis_funding_source = (
                item_map.custom_ndis_funding_source
                or getattr(doc, "custom_ndis_funding_source", None)
            )

        if hasattr(row, "custom_ndis_claimable"):
            row.custom_ndis_claimable = item_map.custom_ndis_default_claimable

        if hasattr(row, "custom_ndis_gst_treatment") and item_map.custom_ndis_gst_treatment:
            row.custom_ndis_gst_treatment = item_map.custom_ndis_gst_treatment

        apply_support_item_details_to_row(row)


def apply_support_item_details_to_row(row):
    support_item = getattr(row, "custom_ndis_support_item", None)

    if not support_item:
        return

    vals = frappe.db.get_value(
        "NDIS Support Item",
        support_item,
        [
            "price_limit",
            "gst_treatment",
            "service_type",
            "catalogue_version",
            "quote_required",
        ],
        as_dict=True,
    )

    if not vals:
        return

    if hasattr(row, "custom_ndis_price_limit"):
        row.custom_ndis_price_limit = vals.price_limit or 0

    if hasattr(row, "custom_ndis_gst_treatment"):
        row.custom_ndis_gst_treatment = vals.gst_treatment or "To Review"

    if hasattr(row, "custom_ndis_catalogue_version"):
        row.custom_ndis_catalogue_version = vals.catalogue_version

    if not getattr(row, "custom_ndis_service_type", None) and vals.service_type:
        row.custom_ndis_service_type = vals.service_type

    if hasattr(row, "custom_ndis_price_check_status"):
        if vals.quote_required:
            row.custom_ndis_price_check_status = "Quote Required"
        elif vals.price_limit:
            row.custom_ndis_price_check_status = "Not Checked"
        else:
            row.custom_ndis_price_check_status = "No Price Limit"


def sync_header_values_to_lines(doc):
    """
    Push common header values to item rows when row value is blank.
    Keeps data entry easier without removing row-level flexibility.
    """

    for row in doc.items:
        if not getattr(row, "custom_ndis_participant", None):
            row.custom_ndis_participant = doc.customer

        if not getattr(row, "custom_ndis_house", None):
            row.custom_ndis_house = getattr(doc, "custom_ndis_house", None)

        if not getattr(row, "custom_ndis_funding_source", None):
            row.custom_ndis_funding_source = getattr(doc, "custom_ndis_funding_source", None)

        apply_support_item_details_to_row(row)


def apply_ndis_accounting_dimensions(doc):
    """
    If ERPNext Accounting Dimension fields exist, populate them safely.
    This keeps standard reports useful without hardcoding GL.
    """

    if hasattr(doc, "ndis_participant") and not getattr(doc, "ndis_participant", None):
        doc.ndis_participant = doc.customer

    if hasattr(doc, "ndis_house") and not getattr(doc, "ndis_house", None):
        doc.ndis_house = getattr(doc, "custom_ndis_house", None)

    if hasattr(doc, "ndis_funding_source") and not getattr(doc, "ndis_funding_source", None):
        doc.ndis_funding_source = getattr(doc, "custom_ndis_funding_source", None)

    if hasattr(doc, "ndis_claim_batch") and not getattr(doc, "ndis_claim_batch", None):
        doc.ndis_claim_batch = getattr(doc, "custom_ndis_claim_batch", None)

    for row in doc.items:
        if hasattr(row, "ndis_participant") and not getattr(row, "ndis_participant", None):
            row.ndis_participant = getattr(row, "custom_ndis_participant", None) or doc.customer

        if hasattr(row, "ndis_house") and not getattr(row, "ndis_house", None):
            row.ndis_house = getattr(row, "custom_ndis_house", None)

        if hasattr(row, "ndis_support_item") and not getattr(row, "ndis_support_item", None):
            row.ndis_support_item = getattr(row, "custom_ndis_support_item", None)

        if hasattr(row, "ndis_service_type") and not getattr(row, "ndis_service_type", None):
            row.ndis_service_type = getattr(row, "custom_ndis_service_type", None)

        if hasattr(row, "ndis_funding_source") and not getattr(row, "ndis_funding_source", None):
            row.ndis_funding_source = getattr(row, "custom_ndis_funding_source", None)


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


def validate_ndis_price_limits(doc):
    mode = getattr(doc, "custom_ndis_price_control_mode", None) or "Warn and Block"

    if mode == "Disabled":
        return

    over_limit_messages = []
    warning_messages = []

    for row in doc.items:
        if not getattr(row, "custom_ndis_claimable", 0):
            continue

        support_item = getattr(row, "custom_ndis_support_item", None)

        if not support_item:
            continue

        vals = frappe.db.get_value(
            "NDIS Support Item",
            support_item,
            [
                "price_limit",
                "quote_required",
                "gst_treatment",
                "support_item_number",
                "support_item_name",
            ],
            as_dict=True,
        )

        if not vals:
            continue

        price_limit = flt(vals.price_limit)
        invoice_rate = flt(row.rate)

        if hasattr(row, "custom_ndis_price_limit"):
            row.custom_ndis_price_limit = price_limit

        if hasattr(row, "custom_ndis_gst_treatment"):
            row.custom_ndis_gst_treatment = vals.gst_treatment or "To Review"

        if vals.quote_required:
            if hasattr(row, "custom_ndis_price_check_status"):
                row.custom_ndis_price_check_status = "Quote Required"

            warning_messages.append(
                f"Row {row.idx}: {vals.support_item_number} requires quote/control review."
            )
            continue

        if not price_limit:
            if hasattr(row, "custom_ndis_price_check_status"):
                row.custom_ndis_price_check_status = "No Price Limit"

            warning_messages.append(
                f"Row {row.idx}: No price limit found for {vals.support_item_number}."
            )
            continue

        if invoice_rate <= price_limit:
            if hasattr(row, "custom_ndis_price_check_status"):
                row.custom_ndis_price_check_status = "Within Limit"
            continue

        override_reason = getattr(row, "custom_ndis_price_override_reason", None)

        if override_reason:
            if hasattr(row, "custom_ndis_price_check_status"):
                row.custom_ndis_price_check_status = "Override Accepted"

            warning_messages.append(
                f"Row {row.idx}: Rate {invoice_rate:.2f} is above limit {price_limit:.2f}, override reason provided."
            )
            continue

        if hasattr(row, "custom_ndis_price_check_status"):
            row.custom_ndis_price_check_status = "Over Limit"

        over_limit_messages.append(
            f"Row {row.idx}: {vals.support_item_number} rate {invoice_rate:.2f} exceeds price limit {price_limit:.2f}."
        )

    if warning_messages:
        frappe.msgprint(
            _("NDIS price/GST control warnings:<br><br>{0}").format(
                "<br>".join(warning_messages)
            ),
            indicator="orange",
            alert=True,
        )

    if over_limit_messages:
        message = _("NDIS price limit breach detected:<br><br>{0}").format(
            "<br>".join(over_limit_messages)
        )

        if mode == "Warn Only":
            frappe.msgprint(message, indicator="orange", alert=True)
        else:
            frappe.throw(
                message
                + _(
                    "<br><br>Add a Price Override Reason on the invoice row, reduce the rate, or change Price Control Mode to Warn Only if management approved."
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
