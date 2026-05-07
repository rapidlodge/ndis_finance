import csv
import io
from datetime import date, datetime

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime
from frappe.utils.file_manager import save_file

from ndis_finance.services.permissions import assert_action


EXPORTABLE_STATUSES = ["Ready to Claim", "Draft"]


def make_export_id(export_type="NDIA Claim CSV"):
    prefix = "NDIS-CLAIM-EXPORT"

    if export_type == "Plan Manager CSV":
        prefix = "NDIS-PM-EXPORT"
    elif export_type == "Self Managed CSV":
        prefix = "NDIS-SM-EXPORT"
    elif export_type == "Internal Review CSV":
        prefix = "NDIS-REVIEW-EXPORT"

    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{timestamp}-{frappe.generate_hash(length=5).upper()}"


def safe_db_set(doctype, name, fieldname, value):
    if name and frappe.get_meta(doctype).has_field(fieldname):
        frappe.db.set_value(doctype, name, fieldname, value, update_modified=False)


def serialise_date(value):
    if not value:
        return ""

    if isinstance(value, datetime):
        return value.date().isoformat()

    if isinstance(value, date):
        return value.isoformat()

    return str(value)


def get_claim_export_rows(claim_batch, include_exported=0, include_submitted=0):
    if not frappe.db.exists("NDIS Claim Batch", claim_batch):
        frappe.throw(_("NDIS Claim Batch not found: {0}").format(claim_batch))

    statuses = list(EXPORTABLE_STATUSES)

    if int(include_submitted or 0):
        statuses.append("Submitted")

    conditions = [
        "claim_batch = %(claim_batch)s",
        "claim_status IN %(statuses)s",
    ]

    params = {
        "claim_batch": claim_batch,
        "statuses": tuple(statuses),
    }

    if not int(include_exported or 0):
        conditions.append(
            "(export_status IS NULL OR export_status = '' OR export_status = 'Not Exported')"
        )

    return frappe.db.sql(
        f"""
        SELECT
            name,
            claim_batch,
            sales_invoice,
            sales_invoice_item,
            participant,
            house,
            funding_source,
            service_date,
            support_item,
            support_item_number,
            support_item_name,
            qty,
            rate,
            claim_amount,
            external_claim_reference,
            claim_status,
            export_status
        FROM `tabNDIS Claim Line`
        WHERE {" AND ".join(conditions)}
        ORDER BY service_date ASC, sales_invoice ASC, name ASC
        """,
        params,
        as_dict=True,
    )


@frappe.whitelist()
def preview_claim_export(
    claim_batch,
    export_type="NDIA Claim CSV",
    include_exported=0,
    include_submitted=0,
    limit=20,
):
    rows = get_claim_export_rows(
        claim_batch=claim_batch,
        include_exported=include_exported,
        include_submitted=include_submitted,
    )

    total = sum(flt(row.claim_amount) for row in rows)

    return {
        "claim_batch": claim_batch,
        "export_type": export_type,
        "line_count": len(rows),
        "total_claim_amount": total,
        "preview": rows[: int(limit or 20)],
        "note": "Preview only. No export record or file created.",
    }


@frappe.whitelist()
def generate_claim_export(
    claim_batch,
    export_type="NDIA Claim CSV",
    include_exported=0,
    include_submitted=0,
    dry_run=0,
):
    assert_action("generate_claim_export")

    dry_run = int(dry_run or 0)

    if not frappe.db.exists("NDIS Claim Batch", claim_batch):
        frappe.throw(_("NDIS Claim Batch not found: {0}").format(claim_batch))

    batch = frappe.get_doc("NDIS Claim Batch", claim_batch)

    rows = get_claim_export_rows(
        claim_batch=claim_batch,
        include_exported=include_exported,
        include_submitted=include_submitted,
    )

    total = sum(flt(row.claim_amount) for row in rows)

    if dry_run:
        return {
            "dry_run": True,
            "claim_batch": claim_batch,
            "export_type": export_type,
            "line_count": len(rows),
            "total_claim_amount": total,
            "preview": rows[:20],
            "note": "Dry run only. No export record or file created.",
        }

    if not rows:
        return {
            "created": False,
            "claim_batch": claim_batch,
            "export_type": export_type,
            "line_count": 0,
            "total_claim_amount": 0,
            "message": "No eligible claim lines found for export.",
        }

    export = frappe.new_doc("NDIS Claim Export")
    export.export_id = make_export_id(export_type)
    export.export_type = export_type
    export.status = "Draft"
    export.claim_batch = claim_batch
    export.company = getattr(batch, "company", None)
    export.funding_source = getattr(batch, "funding_source", None)
    export.claim_period_start = getattr(batch, "claim_period_start", None)
    export.claim_period_end = getattr(batch, "claim_period_end", None)
    export.line_count = len(rows)
    export.total_claim_amount = total
    export.generated_on = now_datetime()
    export.generated_by = frappe.session.user
    export.notes = "Generated from NDIS Claim Batch. No external submission was performed."
    export.insert(ignore_permissions=True)

    csv_content = build_csv_content(rows, export=export)
    file_doc = save_file(
        fname=f"{export.export_id}.csv",
        content=csv_content.encode("utf-8"),
        dt="NDIS Claim Export",
        dn=export.name,
        is_private=1,
    )

    export.export_file = file_doc.file_url
    export.status = "Generated"
    export.save(ignore_permissions=True)

    created_lines = []
    exported_on = now_datetime()

    for idx, row in enumerate(rows, start=1):
        line = create_export_line(export, row, idx)
        created_lines.append(line.name)

        safe_db_set("NDIS Claim Line", row.name, "claim_export", export.name)
        safe_db_set("NDIS Claim Line", row.name, "claim_export_line", line.name)
        safe_db_set("NDIS Claim Line", row.name, "export_status", "Exported")
        safe_db_set("NDIS Claim Line", row.name, "exported_on", exported_on)

    refresh_claim_batch_export_summary(claim_batch)

    frappe.db.commit()

    return {
        "created": True,
        "claim_export": export.name,
        "export_id": export.export_id,
        "export_file": export.export_file,
        "claim_batch": claim_batch,
        "export_type": export_type,
        "line_count": len(created_lines),
        "total_claim_amount": total,
        "note": "Claim export file generated. No external submission or accounting movement was performed.",
    }


def build_csv_content(rows, export=None):
    output = io.StringIO()

    headers = [
        "export_id",
        "export_type",
        "claim_line",
        "claim_batch",
        "sales_invoice",
        "sales_invoice_item",
        "participant",
        "house",
        "funding_source",
        "service_date",
        "support_item_number",
        "support_item_name",
        "quantity",
        "rate",
        "claim_amount",
        "external_claim_reference",
        "claim_status",
    ]

    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()

    for row in rows:
        writer.writerow(
            {
                "export_id": export.export_id if export else "",
                "export_type": export.export_type if export else "",
                "claim_line": row.name,
                "claim_batch": row.claim_batch,
                "sales_invoice": row.sales_invoice,
                "sales_invoice_item": row.sales_invoice_item,
                "participant": row.participant,
                "house": row.house,
                "funding_source": row.funding_source,
                "service_date": serialise_date(row.service_date),
                "support_item_number": row.support_item_number,
                "support_item_name": row.support_item_name,
                "quantity": flt(row.qty),
                "rate": flt(row.rate),
                "claim_amount": flt(row.claim_amount),
                "external_claim_reference": row.external_claim_reference,
                "claim_status": row.claim_status,
            }
        )

    return output.getvalue()


def create_export_line(export, row, idx):
    line = frappe.new_doc("NDIS Claim Export Line")
    line.claim_export = export.name
    line.row_number = idx
    line.claim_line = row.name
    line.claim_batch = row.claim_batch
    line.sales_invoice = row.sales_invoice
    line.sales_invoice_item = row.sales_invoice_item
    line.participant = row.participant
    line.house = row.house
    line.funding_source = row.funding_source
    line.service_date = row.service_date
    line.support_item_number = row.support_item_number
    line.support_item_name = row.support_item_name
    line.qty = flt(row.qty)
    line.rate = flt(row.rate)
    line.claim_amount = flt(row.claim_amount)
    line.external_claim_reference = row.external_claim_reference
    line.export_status = "Exported"
    line.export_note = "Generated by Phase 1O claim export engine."
    line.insert(ignore_permissions=True)

    return line


@frappe.whitelist()
def cancel_claim_export(claim_export, reason=None):
    assert_action("cancel_claim_export")

    if not frappe.db.exists("NDIS Claim Export", claim_export):
        frappe.throw(_("NDIS Claim Export not found: {0}").format(claim_export))

    export = frappe.get_doc("NDIS Claim Export", claim_export)

    if export.status == "Cancelled":
        return {
            "claim_export": claim_export,
            "status": "Cancelled",
            "message": "Claim export was already cancelled.",
        }

    lines = frappe.get_all(
        "NDIS Claim Export Line",
        filters={"claim_export": claim_export, "export_status": "Exported"},
        fields=["name", "claim_line"],
    )

    for line in lines:
        frappe.db.set_value(
            "NDIS Claim Export Line",
            line.name,
            {
                "export_status": "Cancelled",
                "export_note": reason or "Claim export cancelled.",
            },
            update_modified=False,
        )

        if line.claim_line:
            safe_db_set("NDIS Claim Line", line.claim_line, "export_status", "Cancelled")

    export.status = "Cancelled"
    export.cancelled_on = now_datetime()
    export.cancelled_by = frappe.session.user
    export.warning_log = reason or "Claim export cancelled."
    export.save(ignore_permissions=True)

    refresh_claim_batch_export_summary(export.claim_batch)

    frappe.db.commit()

    return {
        "claim_export": claim_export,
        "status": "Cancelled",
        "cancelled_lines": len(lines),
        "note": "Claim export control status cancelled only. No external reversal or accounting action was performed.",
    }


@frappe.whitelist()
def refresh_claim_batch_export_summary(claim_batch):
    rows = frappe.db.sql(
        """
        SELECT
            COUNT(*) AS export_count,
            MAX(generated_on) AS last_export_on
        FROM `tabNDIS Claim Export`
        WHERE claim_batch = %(claim_batch)s
        AND status != 'Cancelled'
        """,
        {"claim_batch": claim_batch},
        as_dict=True,
    )

    totals = rows[0] if rows else {}

    last_export = frappe.get_all(
        "NDIS Claim Export",
        filters={"claim_batch": claim_batch, "status": ["!=", "Cancelled"]},
        fields=["name", "export_file"],
        order_by="generated_on desc",
        limit=1,
    )

    safe_db_set(
        "NDIS Claim Batch",
        claim_batch,
        "last_claim_export",
        last_export[0].name if last_export else None,
    )
    safe_db_set(
        "NDIS Claim Batch",
        claim_batch,
        "claim_export_count",
        int(totals.get("export_count") or 0),
    )
    safe_db_set(
        "NDIS Claim Batch",
        claim_batch,
        "last_claim_export_on",
        totals.get("last_export_on"),
    )
    safe_db_set(
        "NDIS Claim Batch",
        claim_batch,
        "export_file",
        last_export[0].export_file if last_export else None,
    )

    return {
        "claim_batch": claim_batch,
        "claim_export_count": int(totals.get("export_count") or 0),
        "last_claim_export": last_export[0].name if last_export else None,
        "last_claim_export_on": totals.get("last_export_on"),
    }


@frappe.whitelist()
def quick_claim_export_summary(limit=20):
    exports = frappe.get_all(
        "NDIS Claim Export",
        fields=[
            "name",
            "export_id",
            "export_type",
            "status",
            "claim_batch",
            "export_file",
            "line_count",
            "total_claim_amount",
            "generated_on",
            "generated_by",
        ],
        order_by="modified desc",
        limit=int(limit or 20),
    )

    lines = frappe.get_all(
        "NDIS Claim Export Line",
        fields=[
            "name",
            "claim_export",
            "row_number",
            "claim_line",
            "sales_invoice",
            "participant",
            "support_item_number",
            "service_date",
            "claim_amount",
            "export_status",
        ],
        order_by="modified desc",
        limit=int(limit or 20),
    )

    return {
        "exports": exports,
        "lines": lines,
    }
