import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from ndis_finance.services.budget_control import update_usage_from_sales_invoice
from ndis_finance.services.permissions import assert_action


ACTIVE_CLAIM_STATUSES = [
    "Draft",
    "Ready to Claim",
    "Submitted",
    "Paid",
    "Short Paid",
    "Rejected",
    "Reclaim Required",
]


def set_doc_field(doc, fieldname, value):
    if doc.meta.has_field(fieldname):
        setattr(doc, fieldname, value)


def set_db_value_if_field_exists(doctype, name, fieldname, value):
    if frappe.get_meta(doctype).has_field(fieldname):
        frappe.db.set_value(doctype, name, fieldname, value, update_modified=False)


def make_batch_id(batch_type=None):
    prefix = "NDIS-CLAIM"

    if batch_type == "Plan Manager Invoice Batch":
        prefix = "NDIS-PM-BATCH"
    elif batch_type == "Self Managed Invoice Batch":
        prefix = "NDIS-SM-BATCH"
    elif batch_type == "Internal Review":
        prefix = "NDIS-REVIEW"

    timestamp = now_datetime().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{timestamp}"


def get_claimable_invoice_rows(
    claim_period_start,
    claim_period_end,
    funding_source=None,
    company=None,
    participant=None,
    batch_type=None,
    limit=None,
):
    conditions = [
        "si.docstatus = 1",
        "ifnull(si.custom_is_ndis_invoice, 0) = 1",
        "ifnull(sii.custom_ndis_claimable, 0) = 1",
        "sii.custom_ndis_service_date >= %(claim_period_start)s",
        "sii.custom_ndis_service_date <= %(claim_period_end)s",
        "sii.custom_ndis_support_item IS NOT NULL",
        "sii.custom_ndis_service_type IS NOT NULL",
        "sii.custom_ndis_service_date IS NOT NULL",
        """NOT EXISTS (
            SELECT 1
            FROM `tabNDIS Claim Line` ncl
            WHERE ncl.sales_invoice_item = sii.name
            AND ncl.claim_status IN %(active_statuses)s
        )""",
    ]

    params = {
        "claim_period_start": claim_period_start,
        "claim_period_end": claim_period_end,
        "active_statuses": tuple(ACTIVE_CLAIM_STATUSES),
    }

    if funding_source:
        conditions.append(
            "COALESCE(sii.custom_ndis_funding_source, si.custom_ndis_funding_source) = %(funding_source)s"
        )
        params["funding_source"] = funding_source

    if company:
        conditions.append("si.company = %(company)s")
        params["company"] = company

    if participant:
        conditions.append("COALESCE(sii.custom_ndis_participant, si.customer) = %(participant)s")
        params["participant"] = participant

    limit_clause = ""
    if limit:
        limit_clause = " LIMIT %(limit)s"
        params["limit"] = int(limit)

    rows = frappe.db.sql(
        f"""
        SELECT
            si.name AS sales_invoice,
            si.company AS company,
            si.customer AS customer,
            si.posting_date AS posting_date,
            si.custom_ndis_funding_source AS invoice_funding_source,
            si.custom_ndis_house AS invoice_house,
            si.custom_ndis_billing_status AS invoice_billing_status,

            sii.name AS sales_invoice_item,
            sii.idx AS row_idx,
            sii.item_code AS item_code,
            sii.item_name AS item_name,
            sii.qty AS qty,
            sii.rate AS rate,
            COALESCE(sii.net_amount, sii.amount, 0) AS claim_amount,

            COALESCE(sii.custom_ndis_participant, si.customer) AS participant,
            COALESCE(sii.custom_ndis_house, si.custom_ndis_house) AS house,
            COALESCE(sii.custom_ndis_funding_source, si.custom_ndis_funding_source) AS funding_source,
            sii.custom_ndis_service_date AS service_date,
            sii.custom_ndis_support_item AS support_item,
            sii.custom_ndis_service_type AS service_type,
            sii.custom_ndis_plan_budget AS plan_budget,
            sii.custom_ndis_service_booking AS service_booking,
            sii.custom_ndis_price_limit AS price_limit,
            sii.custom_ndis_gst_treatment AS gst_treatment,
            sii.custom_ndis_catalogue_version AS catalogue_version,

            nsi.support_item_number AS support_item_number,
            nsi.support_item_name AS support_item_name,
            nsi.support_category AS support_category

        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
        LEFT JOIN `tabNDIS Support Item` nsi ON nsi.name = sii.custom_ndis_support_item
        WHERE {" AND ".join(conditions)}
        ORDER BY sii.custom_ndis_service_date ASC, si.name ASC, sii.idx ASC
        {limit_clause}
        """,
        params,
        as_dict=True,
    )

    return rows


@frappe.whitelist()
def preview_claim_batch(
    claim_period_start,
    claim_period_end,
    funding_source=None,
    company=None,
    participant=None,
    batch_type="NDIA Claim",
    limit=20,
):
    rows = get_claimable_invoice_rows(
        claim_period_start=claim_period_start,
        claim_period_end=claim_period_end,
        funding_source=funding_source,
        company=company,
        participant=participant,
        batch_type=batch_type,
        limit=limit,
    )

    total = sum(flt(row.claim_amount) for row in rows)

    return {
        "batch_type": batch_type,
        "claim_period_start": claim_period_start,
        "claim_period_end": claim_period_end,
        "funding_source": funding_source,
        "company": company,
        "participant": participant,
        "line_count_preview": len(rows),
        "claim_total_preview": total,
        "rows": rows[: int(limit or 20)],
    }


@frappe.whitelist()
def create_claim_batch(
    claim_period_start,
    claim_period_end,
    funding_source=None,
    company=None,
    participant=None,
    batch_type="NDIA Claim",
    dry_run=0,
    limit=None,
):
    """
    Creates an NDIS Claim Batch from submitted NDIS Sales Invoice rows.

    Safe behaviour:
    - Only reads submitted Sales Invoices.
    - Only includes claimable rows.
    - Skips rows already linked to active claim lines.
    - Does not touch GL Entry.
    """

    assert_action("create_claim_batch")

    dry_run = int(dry_run or 0)

    rows = get_claimable_invoice_rows(
        claim_period_start=claim_period_start,
        claim_period_end=claim_period_end,
        funding_source=funding_source,
        company=company,
        participant=participant,
        batch_type=batch_type,
        limit=limit,
    )

    total = sum(flt(row.claim_amount) for row in rows)

    if dry_run:
        return {
            "dry_run": True,
            "batch_type": batch_type,
            "line_count": len(rows),
            "total_claim_amount": total,
            "preview": rows[:20],
        }

    if not rows:
        return {
            "created": False,
            "message": "No eligible claimable invoice rows found.",
            "line_count": 0,
            "total_claim_amount": 0,
        }

    batch_id = make_batch_id(batch_type=batch_type)

    batch = frappe.new_doc("NDIS Claim Batch")
    batch.claim_batch_id = batch_id
    batch.claim_period_start = claim_period_start
    batch.claim_period_end = claim_period_end
    batch.funding_source = funding_source
    batch.status = "Draft"
    batch.total_claim_amount = total
    batch.total_paid_amount = 0
    batch.total_shortfall_amount = 0

    set_doc_field(batch, "batch_type", batch_type)
    set_doc_field(batch, "company", company or rows[0].company)
    set_doc_field(batch, "claim_line_count", len(rows))
    set_doc_field(batch, "batch_notes", "Created from submitted NDIS Sales Invoice rows.")

    batch.insert(ignore_permissions=True)

    created_lines = []

    for row in rows:
        line = create_claim_line_from_invoice_row(batch, row, batch_type=batch_type)
        created_lines.append(line.name)

    recalculate_claim_batch_totals(batch.name)
    refresh_invoices_for_claim_lines(created_lines)

    frappe.db.commit()

    return {
        "created": True,
        "claim_batch": batch.name,
        "claim_batch_id": batch.claim_batch_id,
        "batch_type": batch_type,
        "line_count": len(created_lines),
        "total_claim_amount": total,
        "claim_lines_preview": created_lines[:20],
    }


def create_claim_line_from_invoice_row(batch, row, batch_type="NDIA Claim"):
    line = frappe.new_doc("NDIS Claim Line")

    line.claim_batch = batch.name
    line.batch_type = batch_type
    line.claim_status = "Ready to Claim"
    line.payment_status = "Not Paid"

    line.company = row.company
    line.sales_invoice = row.sales_invoice
    line.sales_invoice_item = row.sales_invoice_item
    line.posting_date = row.posting_date
    line.customer = row.customer

    line.participant = row.participant
    line.house = row.house
    line.service_date = row.service_date
    line.funding_source = row.funding_source
    line.service_type = row.service_type
    line.support_item = row.support_item
    line.support_item_number = row.support_item_number
    line.support_item_name = row.support_item_name

    line.qty = flt(row.qty)
    line.rate = flt(row.rate)
    line.claim_amount = flt(row.claim_amount)
    line.price_limit = flt(row.price_limit)
    line.gst_treatment = row.gst_treatment or "To Review"

    line.paid_amount = 0
    line.shortfall_amount = 0

    line.plan_budget = row.plan_budget
    line.service_booking = row.service_booking
    line.control_note = "Generated by Phase 1D Claim Batch Engine."

    line.insert(ignore_permissions=True)

    update_sales_invoice_item_from_claim_line(line)

    return line


def update_sales_invoice_item_from_claim_line(line):
    fields = {
        "custom_ndis_claim_line": line.name,
        "custom_ndis_claim_batch_row": line.claim_batch,
        "custom_ndis_claim_amount": flt(line.claim_amount),
        "custom_ndis_paid_amount": flt(line.paid_amount),
        "custom_ndis_shortfall_amount": flt(line.shortfall_amount),
        "custom_ndis_claim_status": "Not Claimed",
    }

    for fieldname, value in fields.items():
        set_db_value_if_field_exists("Sales Invoice Item", line.sales_invoice_item, fieldname, value)


@frappe.whitelist()
def mark_claim_batch_submitted(claim_batch, external_batch_reference=None):
    """
    Use after the finance team submits the claim externally.
    This updates claim-control records only.
    """

    assert_action("submit_claim_batch")

    if not frappe.db.exists("NDIS Claim Batch", claim_batch):
        frappe.throw(_("NDIS Claim Batch not found: {0}").format(claim_batch))

    lines = frappe.get_all(
        "NDIS Claim Line",
        filters={
            "claim_batch": claim_batch,
            "claim_status": ["in", ["Ready to Claim", "Draft"]],
        },
        fields=["name", "sales_invoice", "sales_invoice_item"],
    )

    if not lines:
        frappe.throw(_("No Ready to Claim lines found for this batch."))

    for line in lines:
        frappe.db.set_value(
            "NDIS Claim Line",
            line.name,
            {
                "claim_status": "Submitted",
                "payment_status": "Not Paid",
            },
            update_modified=False,
        )

        set_db_value_if_field_exists(
            "Sales Invoice Item",
            line.sales_invoice_item,
            "custom_ndis_claim_status",
            "Claimed",
        )

    update_values = {
        "status": "Submitted",
        "submitted_on": now_datetime(),
        "submitted_by": frappe.session.user,
    }

    if external_batch_reference:
        update_values["external_batch_reference"] = external_batch_reference

    safe_set_batch_values(claim_batch, update_values)

    refresh_invoices_for_claim_lines([line.name for line in lines])
    recalculate_claim_batch_totals(claim_batch)

    frappe.db.commit()

    return {
        "claim_batch": claim_batch,
        "status": "Submitted",
        "submitted_lines": len(lines),
        "external_batch_reference": external_batch_reference,
    }


@frappe.whitelist()
def record_claim_line_outcome(
    claim_line,
    outcome,
    paid_amount=0,
    rejection_reason=None,
    external_claim_reference=None,
):
    """
    Basic manual outcome updater.
    Phase 1E will later automate this from NDIA/plan-manager remittance files.
    """

    assert_action("record_claim_outcome")

    if outcome not in ["Paid", "Short Paid", "Rejected", "Reclaim Required", "Written Off"]:
        frappe.throw(
            _("Invalid outcome. Use Paid, Short Paid, Rejected, Reclaim Required, or Written Off.")
        )

    line = frappe.get_doc("NDIS Claim Line", claim_line)

    claim_amount = flt(line.claim_amount)
    paid_amount = flt(paid_amount)

    if outcome == "Paid":
        paid_amount = claim_amount
        shortfall_amount = 0
        payment_status = "Paid"
        claim_status = "Paid"

    elif outcome == "Short Paid":
        shortfall_amount = max(claim_amount - paid_amount, 0)
        payment_status = "Short Paid"
        claim_status = "Short Paid"

    elif outcome == "Rejected":
        paid_amount = 0
        shortfall_amount = claim_amount
        payment_status = "Rejected"
        claim_status = "Rejected"

    elif outcome == "Reclaim Required":
        shortfall_amount = max(claim_amount - paid_amount, 0)
        payment_status = "Part Paid" if paid_amount else "Rejected"
        claim_status = "Reclaim Required"

    else:
        shortfall_amount = max(claim_amount - paid_amount, 0)
        payment_status = "Written Off"
        claim_status = "Rejected"

    line.claim_status = claim_status
    line.payment_status = payment_status
    line.paid_amount = paid_amount
    line.shortfall_amount = shortfall_amount
    line.rejection_reason = rejection_reason
    line.external_claim_reference = external_claim_reference
    line.save(ignore_permissions=True)

    update_invoice_item_payment_fields(line)
    recalculate_claim_batch_totals(line.claim_batch)
    refresh_invoice_claim_status(line.sales_invoice)

    frappe.db.commit()

    return {
        "claim_line": line.name,
        "claim_status": claim_status,
        "payment_status": payment_status,
        "claim_amount": claim_amount,
        "paid_amount": paid_amount,
        "shortfall_amount": shortfall_amount,
    }


def update_invoice_item_payment_fields(line):
    updates = {
        "custom_ndis_claim_status": map_line_status_to_invoice_item_status(line.claim_status),
        "custom_ndis_paid_amount": flt(line.paid_amount),
        "custom_ndis_shortfall_amount": flt(line.shortfall_amount),
        "custom_ndis_external_claim_reference": line.external_claim_reference,
        "custom_ndis_rejection_reason": line.rejection_reason,
    }

    for fieldname, value in updates.items():
        set_db_value_if_field_exists("Sales Invoice Item", line.sales_invoice_item, fieldname, value)


def map_line_status_to_invoice_item_status(status):
    if status == "Paid":
        return "Paid"
    if status == "Short Paid":
        return "Short Paid"
    if status in ["Rejected", "Reclaim Required"]:
        return "Rejected"
    if status == "Submitted":
        return "Claimed"
    if status == "Invoice Cancelled":
        return "Not Claimable"

    return "Not Claimed"


@frappe.whitelist()
def recalculate_claim_batch_totals(claim_batch):
    rows = frappe.db.sql(
        """
        SELECT
            COUNT(*) AS line_count,
            COALESCE(SUM(claim_amount), 0) AS total_claim_amount,
            COALESCE(SUM(paid_amount), 0) AS total_paid_amount,
            COALESCE(SUM(shortfall_amount), 0) AS total_shortfall_amount
        FROM `tabNDIS Claim Line`
        WHERE claim_batch = %(claim_batch)s
        AND claim_status != 'Cancelled'
        """,
        {"claim_batch": claim_batch},
        as_dict=True,
    )

    totals = rows[0] if rows else {}

    update_values = {
        "total_claim_amount": flt(totals.get("total_claim_amount")),
        "total_paid_amount": flt(totals.get("total_paid_amount")),
        "total_shortfall_amount": flt(totals.get("total_shortfall_amount")),
        "claim_line_count": int(totals.get("line_count") or 0),
    }

    safe_set_batch_values(claim_batch, update_values)

    return update_values


def safe_set_batch_values(claim_batch, values):
    meta = frappe.get_meta("NDIS Claim Batch")
    safe_values = {}

    for fieldname, value in values.items():
        if fieldname in ["status", "total_claim_amount", "total_paid_amount", "total_shortfall_amount"]:
            safe_values[fieldname] = value
        elif meta.has_field(fieldname):
            safe_values[fieldname] = value

    if safe_values:
        frappe.db.set_value("NDIS Claim Batch", claim_batch, safe_values, update_modified=False)


def refresh_invoices_for_claim_lines(claim_lines):
    invoices = set()

    if not claim_lines:
        return

    rows = frappe.get_all(
        "NDIS Claim Line",
        filters={"name": ["in", claim_lines]},
        fields=["sales_invoice"],
    )

    for row in rows:
        invoices.add(row.sales_invoice)

    for invoice in invoices:
        refresh_invoice_claim_status(invoice)


@frappe.whitelist()
def refresh_invoice_claim_status(sales_invoice):
    lines = frappe.get_all(
        "NDIS Claim Line",
        filters={"sales_invoice": sales_invoice, "claim_status": ["!=", "Cancelled"]},
        fields=["name", "claim_status", "claim_amount", "paid_amount", "shortfall_amount"],
    )

    line_count = len(lines)
    total_claim = sum(flt(line.claim_amount) for line in lines)

    statuses = {line.claim_status for line in lines}

    if not lines:
        billing_status = "Draft"
        note = "No claim lines found."
    elif statuses == {"Paid"}:
        billing_status = "Paid"
        note = "All claim lines paid."
    elif "Short Paid" in statuses:
        billing_status = "Short Paid"
        note = "One or more claim lines short paid."
    elif "Rejected" in statuses or "Reclaim Required" in statuses:
        billing_status = "Rejected"
        note = "One or more claim lines rejected or require reclaim."
    elif "Submitted" in statuses:
        billing_status = "Claimed"
        note = "Claim batch submitted."
    elif "Ready to Claim" in statuses or "Draft" in statuses:
        billing_status = "Ready to Claim"
        note = "Claim lines created and ready for submission."
    elif "Invoice Cancelled" in statuses:
        billing_status = "On Hold"
        note = "Invoice has cancelled claim lines."
    else:
        billing_status = "Draft"
        note = "Claim status requires review."

    updates = {
        "custom_ndis_claim_line_count": line_count,
        "custom_ndis_claim_total": total_claim,
        "custom_ndis_claim_last_batched_on": now_datetime(),
        "custom_ndis_batching_note": note,
        "custom_ndis_billing_status": billing_status,
    }

    for fieldname, value in updates.items():
        set_db_value_if_field_exists("Sales Invoice", sales_invoice, fieldname, value)

    return {
        "sales_invoice": sales_invoice,
        "billing_status": billing_status,
        "claim_line_count": line_count,
        "claim_total": total_claim,
        "note": note,
    }


@frappe.whitelist()
def quick_claim_batch_summary(claim_batch=None, limit=20):
    filters = {}

    if claim_batch:
        filters["claim_batch"] = claim_batch

    lines = frappe.get_all(
        "NDIS Claim Line",
        filters=filters,
        fields=[
            "name",
            "claim_batch",
            "sales_invoice",
            "participant",
            "service_date",
            "support_item_number",
            "service_type",
            "funding_source",
            "claim_amount",
            "paid_amount",
            "shortfall_amount",
            "claim_status",
            "payment_status",
        ],
        order_by="modified desc",
        limit=int(limit or 20),
    )

    return lines


def before_sales_invoice_cancel(doc, method=None):
    """
    Prevent cancellation if invoice has claim lines that were already externally submitted
    or financially reconciled.
    """

    if not getattr(doc, "custom_is_ndis_invoice", 0):
        return

    blocked_lines = frappe.get_all(
        "NDIS Claim Line",
        filters={
            "sales_invoice": doc.name,
            "claim_status": ["in", ["Submitted", "Paid", "Short Paid", "Rejected", "Reclaim Required"]],
        },
        fields=["name", "claim_status", "claim_batch"],
    )

    if blocked_lines:
        detail = "<br>".join(
            [f"{row.name}: {row.claim_status} / {row.claim_batch}" for row in blocked_lines]
        )

        frappe.throw(
            _(
                "This NDIS invoice cannot be cancelled because claim lines already progressed externally:<br><br>{0}<br><br>"
                "Reverse or resolve the claim/reconciliation record first, then cancel the invoice."
            ).format(detail)
        )


def on_sales_invoice_cancelled(doc, method=None):
    """
    If invoice cancellation is allowed, mark draft/ready claim lines as Invoice Cancelled.
    Also keep the Phase 1C budget usage recalculation working.
    """

    update_usage_from_sales_invoice(doc, method=method)

    if not getattr(doc, "custom_is_ndis_invoice", 0):
        return

    lines = frappe.get_all(
        "NDIS Claim Line",
        filters={
            "sales_invoice": doc.name,
            "claim_status": ["in", ["Draft", "Ready to Claim"]],
        },
        fields=["name", "claim_batch", "sales_invoice_item"],
    )

    affected_batches = set()

    for line in lines:
        frappe.db.set_value(
            "NDIS Claim Line",
            line.name,
            {
                "claim_status": "Invoice Cancelled",
                "payment_status": "Rejected",
                "shortfall_amount": 0,
                "control_note": "Sales Invoice was cancelled before external claim submission.",
            },
            update_modified=False,
        )

        set_db_value_if_field_exists(
            "Sales Invoice Item",
            line.sales_invoice_item,
            "custom_ndis_claim_status",
            "Not Claimable",
        )

        affected_batches.add(line.claim_batch)

    for batch in affected_batches:
        recalculate_claim_batch_totals(batch)

    refresh_invoice_claim_status(doc.name)
