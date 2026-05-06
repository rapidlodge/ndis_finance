import frappe
from frappe import _
from frappe.utils import add_days, flt, now_datetime, nowdate

from ndis_finance.services.claim_batch_engine import (
    record_claim_line_outcome,
    recalculate_claim_batch_totals,
    refresh_invoice_claim_status,
)


def make_reconciliation_id(payer_type=None):
    prefix = "NDIS-PAY"

    if payer_type == "Plan Manager":
        prefix = "NDIS-PM-PAY"
    elif payer_type == "Self Managed":
        prefix = "NDIS-SM-PAY"
    elif payer_type == "Other":
        prefix = "NDIS-OTHER-PAY"

    timestamp = now_datetime().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{timestamp}"


def safe_set_doc_field(doc, fieldname, value):
    if doc.meta.has_field(fieldname):
        setattr(doc, fieldname, value)


def safe_db_set(doctype, name, fieldname, value):
    if frappe.get_meta(doctype).has_field(fieldname):
        frappe.db.set_value(doctype, name, fieldname, value, update_modified=False)


@frappe.whitelist()
def create_payment_reconciliation_batch(
    payer_type="NDIA",
    claim_batch=None,
    funding_source=None,
    company=None,
    payment_entry=None,
    payment_date=None,
    external_payment_reference=None,
    received_amount=0,
    notes=None,
):
    """
    Creates an NDIS payment reconciliation batch.

    This is a control document only.
    It does not create GL Entries and does not replace ERPNext Payment Entry.
    """

    payment_date = payment_date or nowdate()

    if claim_batch and not frappe.db.exists("NDIS Claim Batch", claim_batch):
        frappe.throw(_("NDIS Claim Batch not found: {0}").format(claim_batch))

    if payment_entry and not frappe.db.exists("Payment Entry", payment_entry):
        frappe.throw(_("Payment Entry not found: {0}").format(payment_entry))

    expected_claim_amount = 0

    if claim_batch:
        expected_claim_amount = flt(
            frappe.db.get_value("NDIS Claim Batch", claim_batch, "total_claim_amount") or 0
        )

        batch_vals = frappe.db.get_value(
            "NDIS Claim Batch",
            claim_batch,
            ["funding_source", "company"],
            as_dict=True,
        ) or {}

        funding_source = funding_source or batch_vals.get("funding_source")
        company = company or batch_vals.get("company")

    doc = frappe.new_doc("NDIS Payment Reconciliation Batch")
    doc.reconciliation_id = make_reconciliation_id(payer_type)
    doc.payer_type = payer_type
    doc.status = "Draft"
    doc.company = company
    doc.funding_source = funding_source
    doc.claim_batch = claim_batch
    doc.payment_entry = payment_entry
    doc.payment_date = payment_date
    doc.external_payment_reference = external_payment_reference
    doc.expected_claim_amount = expected_claim_amount
    doc.received_amount = flt(received_amount)
    doc.allocated_amount = 0
    doc.unallocated_amount = flt(received_amount)
    doc.shortfall_amount = 0
    doc.rejected_amount = 0
    doc.line_count = 0
    doc.notes = notes

    doc.insert(ignore_permissions=True)

    if payment_entry:
        link_payment_entry_to_reconciliation(
            payment_entry=payment_entry,
            reconciliation_batch=doc.name,
            claim_batch=claim_batch,
            funding_source=funding_source,
            remittance_reference=external_payment_reference,
        )

    frappe.db.commit()

    return {
        "created": True,
        "reconciliation_batch": doc.name,
        "reconciliation_id": doc.reconciliation_id,
        "payer_type": payer_type,
        "claim_batch": claim_batch,
        "expected_claim_amount": expected_claim_amount,
        "received_amount": flt(received_amount),
    }


def link_payment_entry_to_reconciliation(
    payment_entry,
    reconciliation_batch,
    claim_batch=None,
    funding_source=None,
    remittance_reference=None,
):
    updates = {
        "custom_is_ndis_payment": 1,
        "custom_ndis_payment_reconciliation_batch": reconciliation_batch,
        "custom_ndis_claim_batch": claim_batch,
        "custom_ndis_funding_source": funding_source,
        "custom_ndis_remittance_reference": remittance_reference,
    }

    for fieldname, value in updates.items():
        safe_db_set("Payment Entry", payment_entry, fieldname, value)


@frappe.whitelist()
def record_payment_for_claim_line(
    reconciliation_batch,
    claim_line,
    paid_amount,
    rejection_reason=None,
    external_claim_reference=None,
    payment_entry=None,
):
    """
    Records payment outcome for one NDIS Claim Line.

    Outcome is calculated:
    - paid amount == claim amount: Paid
    - paid amount > 0 but less than claim amount: Short Paid
    - paid amount == 0: Rejected
    """

    if not frappe.db.exists("NDIS Payment Reconciliation Batch", reconciliation_batch):
        frappe.throw(
            _("NDIS Payment Reconciliation Batch not found: {0}").format(
                reconciliation_batch
            )
        )

    if not frappe.db.exists("NDIS Claim Line", claim_line):
        frappe.throw(_("NDIS Claim Line not found: {0}").format(claim_line))

    batch = frappe.get_doc("NDIS Payment Reconciliation Batch", reconciliation_batch)
    line = frappe.get_doc("NDIS Claim Line", claim_line)

    if batch.claim_batch and line.claim_batch != batch.claim_batch:
        frappe.throw(
            _(
                "Claim Line {0} belongs to Claim Batch {1}, not reconciliation batch Claim Batch {2}."
            ).format(line.name, line.claim_batch, batch.claim_batch)
        )

    paid_amount = flt(paid_amount)
    claim_amount = flt(line.claim_amount)

    if paid_amount < 0:
        frappe.throw(_("Paid Amount cannot be negative."))

    if paid_amount > claim_amount:
        frappe.throw(
            _("Paid Amount {0} cannot exceed Claim Amount {1}.").format(
                paid_amount, claim_amount
            )
        )

    if paid_amount == claim_amount:
        outcome = "Paid"
    elif paid_amount > 0:
        outcome = "Short Paid"
    else:
        outcome = "Rejected"

    outcome_result = record_claim_line_outcome(
        claim_line=claim_line,
        outcome=outcome,
        paid_amount=paid_amount,
        rejection_reason=rejection_reason,
        external_claim_reference=external_claim_reference,
    )

    reconciliation_line = upsert_reconciliation_line(
        reconciliation_batch=batch,
        claim_line=claim_line,
        paid_amount=paid_amount,
        outcome=outcome,
        rejection_reason=rejection_reason,
        external_claim_reference=external_claim_reference,
        payment_entry=payment_entry or batch.payment_entry,
    )

    updated_claim_line = frappe.get_doc("NDIS Claim Line", claim_line)

    safe_db_set("NDIS Claim Line", claim_line, "reconciliation_batch", reconciliation_batch)
    safe_db_set("NDIS Claim Line", claim_line, "reconciliation_line", reconciliation_line.name)
    safe_db_set("NDIS Claim Line", claim_line, "payment_entry", payment_entry or batch.payment_entry)
    safe_db_set("NDIS Claim Line", claim_line, "payment_date", batch.payment_date)
    safe_db_set("NDIS Claim Line", claim_line, "remittance_reference", batch.external_payment_reference)

    if outcome == "Paid":
        safe_db_set("NDIS Claim Line", claim_line, "reconciliation_status", "Reconciled")
        safe_db_set("NDIS Claim Line", claim_line, "recovery_status", "Not Required")
        resolve_existing_leakage(updated_claim_line)
    else:
        safe_db_set("NDIS Claim Line", claim_line, "reconciliation_status", "Exception")
        safe_db_set("NDIS Claim Line", claim_line, "recovery_status", "Open")
        safe_db_set("NDIS Claim Line", claim_line, "follow_up_due_date", add_days(nowdate(), 7))
        create_or_update_funding_leakage(
            claim_line_doc=updated_claim_line,
            reconciliation_batch=batch,
            reconciliation_line=reconciliation_line,
        )

    recalculate_payment_reconciliation_batch(reconciliation_batch)

    frappe.db.commit()

    return {
        "reconciliation_batch": reconciliation_batch,
        "reconciliation_line": reconciliation_line.name,
        "claim_line": claim_line,
        "outcome": outcome,
        "claim_amount": claim_amount,
        "paid_amount": paid_amount,
        "shortfall_amount": flt(updated_claim_line.shortfall_amount),
        "claim_line_result": outcome_result,
    }


def upsert_reconciliation_line(
    reconciliation_batch,
    claim_line,
    paid_amount,
    outcome,
    rejection_reason=None,
    external_claim_reference=None,
    payment_entry=None,
):
    existing = frappe.db.exists(
        "NDIS Payment Reconciliation Line",
        {
            "reconciliation_batch": reconciliation_batch.name,
            "claim_line": claim_line,
        },
    )

    claim = frappe.get_doc("NDIS Claim Line", claim_line)
    shortfall_amount = max(flt(claim.claim_amount) - flt(paid_amount), 0)

    if existing:
        doc = frappe.get_doc("NDIS Payment Reconciliation Line", existing)
    else:
        doc = frappe.new_doc("NDIS Payment Reconciliation Line")

    doc.reconciliation_batch = reconciliation_batch.name
    doc.claim_batch = claim.claim_batch
    doc.claim_line = claim.name
    doc.sales_invoice = claim.sales_invoice
    doc.sales_invoice_item = claim.sales_invoice_item
    doc.participant = claim.participant
    doc.service_date = claim.service_date
    doc.funding_source = claim.funding_source
    doc.service_type = claim.service_type
    doc.support_item = claim.support_item
    doc.support_item_number = claim.support_item_number
    doc.claim_amount = flt(claim.claim_amount)
    doc.paid_amount = flt(paid_amount)
    doc.shortfall_amount = flt(shortfall_amount)
    doc.outcome = outcome
    doc.external_claim_reference = external_claim_reference
    doc.rejection_reason = rejection_reason
    doc.payment_entry = payment_entry

    doc.save(ignore_permissions=True)

    return doc


@frappe.whitelist()
def recalculate_payment_reconciliation_batch(reconciliation_batch):
    if not frappe.db.exists("NDIS Payment Reconciliation Batch", reconciliation_batch):
        frappe.throw(
            _("NDIS Payment Reconciliation Batch not found: {0}").format(
                reconciliation_batch
            )
        )

    batch = frappe.get_doc("NDIS Payment Reconciliation Batch", reconciliation_batch)

    rows = frappe.db.sql(
        """
        SELECT
            COUNT(*) AS line_count,
            COALESCE(SUM(claim_amount), 0) AS expected_claim_amount,
            COALESCE(SUM(paid_amount), 0) AS allocated_amount,
            COALESCE(SUM(shortfall_amount), 0) AS shortfall_amount,
            COALESCE(SUM(CASE WHEN outcome = 'Rejected' THEN claim_amount ELSE 0 END), 0) AS rejected_amount,
            COALESCE(SUM(CASE WHEN outcome IN ('Short Paid', 'Rejected', 'Reclaim Required') THEN 1 ELSE 0 END), 0) AS exception_count
        FROM `tabNDIS Payment Reconciliation Line`
        WHERE reconciliation_batch = %(reconciliation_batch)s
        """,
        {"reconciliation_batch": reconciliation_batch},
        as_dict=True,
    )

    totals = rows[0] if rows else {}

    line_count = int(totals.get("line_count") or 0)
    allocated_amount = flt(totals.get("allocated_amount"))
    shortfall_amount = flt(totals.get("shortfall_amount"))
    rejected_amount = flt(totals.get("rejected_amount"))
    exception_count = int(totals.get("exception_count") or 0)

    expected_claim_amount = flt(batch.expected_claim_amount) or flt(
        totals.get("expected_claim_amount")
    )

    received_amount = flt(batch.received_amount)
    unallocated_amount = received_amount - allocated_amount

    if line_count == 0:
        status = "Draft"
    elif exception_count > 0 or shortfall_amount > 0:
        status = "Exception"
    elif received_amount and abs(unallocated_amount) > 0.01:
        status = "Partially Reconciled"
    else:
        status = "Reconciled"

    frappe.db.set_value(
        "NDIS Payment Reconciliation Batch",
        reconciliation_batch,
        {
            "expected_claim_amount": expected_claim_amount,
            "allocated_amount": allocated_amount,
            "unallocated_amount": unallocated_amount,
            "shortfall_amount": shortfall_amount,
            "rejected_amount": rejected_amount,
            "line_count": line_count,
            "status": status,
        },
        update_modified=False,
    )

    if batch.claim_batch:
        recalculate_claim_batch_totals(batch.claim_batch)

    return {
        "reconciliation_batch": reconciliation_batch,
        "status": status,
        "line_count": line_count,
        "expected_claim_amount": expected_claim_amount,
        "received_amount": received_amount,
        "allocated_amount": allocated_amount,
        "unallocated_amount": unallocated_amount,
        "shortfall_amount": shortfall_amount,
        "rejected_amount": rejected_amount,
    }


def create_or_update_funding_leakage(claim_line_doc, reconciliation_batch, reconciliation_line):
    leakage_type = "Payment Shortfall"

    if claim_line_doc.claim_status == "Rejected":
        leakage_type = "Rejected Claim"

    existing = frappe.db.exists(
        "NDIS Funding Leakage Register",
        {
            "source_doctype": "NDIS Claim Line",
            "source_name": claim_line_doc.name,
            "leakage_type": leakage_type,
        },
    )

    variance = flt(claim_line_doc.shortfall_amount)
    severity = get_leakage_severity(variance)

    if existing:
        doc = frappe.get_doc("NDIS Funding Leakage Register", existing)
    else:
        doc = frappe.new_doc("NDIS Funding Leakage Register")

    doc.participant = claim_line_doc.participant
    doc.house = claim_line_doc.house
    doc.service_date = claim_line_doc.service_date
    doc.leakage_type = leakage_type
    doc.source_doctype = "NDIS Claim Line"
    doc.source_name = claim_line_doc.name
    doc.expected_amount = flt(claim_line_doc.claim_amount)
    doc.actual_amount = flt(claim_line_doc.paid_amount)
    doc.variance_amount = variance
    doc.severity = severity
    doc.status = "Open"
    doc.resolution_note = claim_line_doc.rejection_reason

    safe_set_doc_field(doc, "claim_batch", claim_line_doc.claim_batch)
    safe_set_doc_field(doc, "claim_line", claim_line_doc.name)
    safe_set_doc_field(doc, "sales_invoice", claim_line_doc.sales_invoice)
    safe_set_doc_field(doc, "sales_invoice_item", claim_line_doc.sales_invoice_item)
    safe_set_doc_field(doc, "payment_reconciliation_batch", reconciliation_batch.name)
    safe_set_doc_field(doc, "payment_reconciliation_line", reconciliation_line.name)
    safe_set_doc_field(doc, "recovery_status", "Open")
    safe_set_doc_field(doc, "follow_up_due_date", add_days(nowdate(), 7))
    safe_set_doc_field(doc, "assigned_to", frappe.session.user)

    doc.save(ignore_permissions=True)

    frappe.db.set_value(
        "NDIS Payment Reconciliation Line",
        reconciliation_line.name,
        "funding_leakage",
        doc.name,
        update_modified=False,
    )

    return doc.name


def resolve_existing_leakage(claim_line_doc):
    leakages = frappe.get_all(
        "NDIS Funding Leakage Register",
        filters={
            "source_doctype": "NDIS Claim Line",
            "source_name": claim_line_doc.name,
            "status": ["in", ["Open", "In Review"]],
        },
        fields=["name"],
    )

    for leakage in leakages:
        updates = {
            "status": "Resolved",
            "resolution_note": "Resolved automatically because claim line was fully paid.",
        }

        if frappe.get_meta("NDIS Funding Leakage Register").has_field("recovery_status"):
            updates["recovery_status"] = "Resolved"

        frappe.db.set_value(
            "NDIS Funding Leakage Register",
            leakage.name,
            updates,
            update_modified=False,
        )


def get_leakage_severity(amount):
    amount = flt(amount)

    if amount >= 1000:
        return "Critical"
    if amount >= 250:
        return "High"
    if amount >= 50:
        return "Medium"

    return "Low"


@frappe.whitelist()
def quick_payment_reconciliation_summary(reconciliation_batch=None, limit=20):
    batch_filters = {}
    line_filters = {}

    if reconciliation_batch:
        batch_filters["name"] = reconciliation_batch
        line_filters["reconciliation_batch"] = reconciliation_batch

    batches = frappe.get_all(
        "NDIS Payment Reconciliation Batch",
        filters=batch_filters,
        fields=[
            "name",
            "reconciliation_id",
            "payer_type",
            "status",
            "claim_batch",
            "received_amount",
            "allocated_amount",
            "unallocated_amount",
            "shortfall_amount",
            "rejected_amount",
            "line_count",
        ],
        order_by="modified desc",
        limit=int(limit or 20),
    )

    lines = frappe.get_all(
        "NDIS Payment Reconciliation Line",
        filters=line_filters,
        fields=[
            "name",
            "reconciliation_batch",
            "claim_line",
            "sales_invoice",
            "participant",
            "support_item_number",
            "claim_amount",
            "paid_amount",
            "shortfall_amount",
            "outcome",
            "funding_leakage",
        ],
        order_by="modified desc",
        limit=int(limit or 20),
    )

    return {
        "batches": batches,
        "lines": lines,
    }


@frappe.whitelist()
def quick_funding_leakage_summary(limit=20):
    return frappe.get_all(
        "NDIS Funding Leakage Register",
        fields=[
            "name",
            "participant",
            "house",
            "service_date",
            "leakage_type",
            "expected_amount",
            "actual_amount",
            "variance_amount",
            "severity",
            "status",
            "source_doctype",
            "source_name",
        ],
        order_by="modified desc",
        limit=int(limit or 20),
    )
