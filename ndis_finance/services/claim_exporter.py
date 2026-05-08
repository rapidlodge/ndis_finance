import csv
import io
import json
from datetime import date, datetime

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime
from frappe.utils.file_manager import save_file

from ndis_finance.services.permissions import assert_action


EXPORTABLE_STATUSES = ["Ready to Claim", "Draft"]

DEFAULT_FIELDS = [
    {"column_label": "export_id", "source_field": "export_id"},
    {"column_label": "export_type", "source_field": "export_type"},
    {"column_label": "claim_line", "source_field": "claim_line"},
    {"column_label": "claim_batch", "source_field": "claim_batch"},
    {"column_label": "sales_invoice", "source_field": "sales_invoice"},
    {"column_label": "sales_invoice_item", "source_field": "sales_invoice_item"},
    {"column_label": "participant", "source_field": "participant"},
    {"column_label": "house", "source_field": "house"},
    {"column_label": "funding_source", "source_field": "funding_source"},
    {"column_label": "service_date", "source_field": "service_date"},
    {"column_label": "support_item_number", "source_field": "support_item_number"},
    {"column_label": "support_item_name", "source_field": "support_item_name"},
    {"column_label": "quantity", "source_field": "qty"},
    {"column_label": "rate", "source_field": "rate"},
    {"column_label": "claim_amount", "source_field": "claim_amount"},
    {"column_label": "external_claim_reference", "source_field": "external_claim_reference"},
    {"column_label": "claim_status", "source_field": "claim_status"},
]

ALLOWED_SOURCE_FIELDS = {
    "export_id",
    "export_type",
    "claim_line",
    "claim_batch",
    "sales_invoice",
    "sales_invoice_item",
    "participant",
    "participant_name",
    "house",
    "funding_source",
    "service_date",
    "support_item",
    "support_item_number",
    "support_item_name",
    "service_type",
    "qty",
    "rate",
    "claim_amount",
    "external_claim_reference",
    "claim_status",
    "export_status",
}


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


def serialise_value(value):
    if value is None:
        return ""

    if isinstance(value, datetime):
        return value.date().isoformat()

    if isinstance(value, date):
        return value.isoformat()

    return value


def get_default_template_for_export_type(export_type):
    template = frappe.get_all(
        "NDIS Claim Export Mapping Template",
        filters={
            "export_type": export_type,
            "active": 1,
            "is_default": 1,
        },
        fields=["name"],
        order_by="modified desc",
        limit=1,
    )

    if template:
        return template[0].name

    template = frappe.get_all(
        "NDIS Claim Export Mapping Template",
        filters={
            "export_type": export_type,
            "active": 1,
        },
        fields=["name"],
        order_by="modified desc",
        limit=1,
    )

    return template[0].name if template else None


def get_mapping(export_mapping_template=None, export_type="NDIA Claim CSV"):
    if not frappe.db.exists("DocType", "NDIS Claim Export Mapping Template"):
        return DEFAULT_FIELDS, None

    if not export_mapping_template:
        export_mapping_template = get_default_template_for_export_type(export_type)

    if not export_mapping_template:
        return DEFAULT_FIELDS, None

    template = frappe.get_doc("NDIS Claim Export Mapping Template", export_mapping_template)

    if not template.active:
        frappe.throw(_("Export mapping template is inactive: {0}").format(export_mapping_template))

    try:
        mapping = json.loads(template.column_mapping_json or "[]")
    except Exception:
        frappe.throw(_("Invalid JSON in export mapping template: {0}").format(export_mapping_template))

    if not isinstance(mapping, list) or not mapping:
        frappe.throw(_("Export mapping template must contain a list of column mappings."))

    validate_mapping(mapping)

    return mapping, template.name


def validate_mapping(mapping):
    for idx, column in enumerate(mapping, start=1):
        label = (column.get("column_label") or "").strip()
        source_field = (column.get("source_field") or "").strip()
        static_value = column.get("static_value")

        if not label:
            frappe.throw(_("Column mapping row {0} is missing column_label.").format(idx))

        if not source_field and static_value is None:
            frappe.throw(_("Column mapping row {0} must have source_field or static_value.").format(idx))

        if source_field and source_field not in ALLOWED_SOURCE_FIELDS:
            frappe.throw(
                _("Column mapping row {0} has unsupported source_field: {1}").format(
                    idx,
                    source_field,
                )
            )

        column["column_label"] = label
        if source_field:
            column["source_field"] = source_field


def get_claim_export_rows(claim_batch, include_exported=0, include_submitted=0):
    if not frappe.db.exists("NDIS Claim Batch", claim_batch):
        frappe.throw(_("NDIS Claim Batch not found: {0}").format(claim_batch))

    statuses = list(EXPORTABLE_STATUSES)

    if int(include_submitted or 0):
        statuses.append("Submitted")

    conditions = [
        "cl.claim_batch = %(claim_batch)s",
        "cl.claim_status IN %(statuses)s",
    ]

    params = {
        "claim_batch": claim_batch,
        "statuses": tuple(statuses),
    }

    if not int(include_exported or 0):
        conditions.append(
            "(cl.export_status IS NULL OR cl.export_status = '' OR cl.export_status = 'Not Exported')"
        )

    return frappe.db.sql(
        f"""
        SELECT
            cl.name AS claim_line,
            cl.name AS name,
            cl.claim_batch,
            cl.sales_invoice,
            cl.sales_invoice_item,
            cl.participant,
            cust.customer_name AS participant_name,
            cl.house,
            cl.funding_source,
            cl.service_date,
            cl.support_item,
            cl.support_item_number,
            cl.support_item_name,
            cl.service_type,
            cl.qty,
            cl.rate,
            cl.claim_amount,
            cl.external_claim_reference,
            cl.claim_status,
            cl.export_status
        FROM `tabNDIS Claim Line` cl
        LEFT JOIN `tabCustomer` cust ON cust.name = cl.participant
        WHERE {" AND ".join(conditions)}
        ORDER BY cl.service_date ASC, cl.sales_invoice ASC, cl.name ASC
        """,
        params,
        as_dict=True,
    )


@frappe.whitelist()
def preview_export_template(export_mapping_template=None, export_type="NDIA Claim CSV", limit=10):
    mapping, template = get_mapping(export_mapping_template, export_type)

    return {
        "export_type": export_type,
        "export_mapping_template": template,
        "columns": [column.get("column_label") for column in mapping],
        "mapping_preview": mapping[: int(limit or 10)],
    }


@frappe.whitelist()
def preview_claim_export(
    claim_batch,
    export_type="NDIA Claim CSV",
    export_mapping_template=None,
    include_exported=0,
    include_submitted=0,
    limit=20,
):
    rows = get_claim_export_rows(
        claim_batch=claim_batch,
        include_exported=include_exported,
        include_submitted=include_submitted,
    )

    mapping, template = get_mapping(export_mapping_template, export_type)
    total = sum(flt(row.claim_amount) for row in rows)

    return {
        "claim_batch": claim_batch,
        "export_type": export_type,
        "export_mapping_template": template,
        "line_count": len(rows),
        "total_claim_amount": total,
        "columns": [column.get("column_label") for column in mapping],
        "preview": [build_mapped_row(row, mapping) for row in rows[: int(limit or 20)]],
        "note": "Preview only. No export record or file created.",
    }


@frappe.whitelist()
def generate_claim_export(
    claim_batch,
    export_type="NDIA Claim CSV",
    export_mapping_template=None,
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

    mapping, template = get_mapping(export_mapping_template, export_type)
    total = sum(flt(row.claim_amount) for row in rows)

    if dry_run:
        return {
            "dry_run": True,
            "claim_batch": claim_batch,
            "export_type": export_type,
            "export_mapping_template": template,
            "line_count": len(rows),
            "total_claim_amount": total,
            "columns": [column.get("column_label") for column in mapping],
            "preview": [build_mapped_row(row, mapping) for row in rows[:20]],
            "note": "Dry run only. No export record or file created.",
        }

    if not rows:
        return {
            "created": False,
            "claim_batch": claim_batch,
            "export_type": export_type,
            "export_mapping_template": template,
            "line_count": 0,
            "total_claim_amount": 0,
            "message": "No eligible claim lines found for export.",
        }

    export = frappe.new_doc("NDIS Claim Export")
    export.export_id = make_export_id(export_type)
    export.export_type = export_type
    export.export_mapping_template = template
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
    export.notes = "Generated from NDIS Claim Batch using mapping template. No external submission was performed."
    export.insert(ignore_permissions=True)

    csv_content = build_csv_content(rows, mapping, export=export)
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
        "export_mapping_template": template,
        "line_count": len(created_lines),
        "total_claim_amount": total,
        "note": "Claim export file generated. No external submission or accounting movement was performed.",
    }


def build_mapped_row(row, mapping, export=None):
    output = {}

    for column in mapping:
        label = column.get("column_label")
        source_field = column.get("source_field")

        if source_field == "export_id":
            value = export.export_id if export else ""
        elif source_field == "export_type":
            value = export.export_type if export else ""
        elif source_field:
            value = row.get(source_field)
        else:
            value = column.get("static_value")

        output[label] = serialise_value(value)

    return output


def build_csv_content(rows, mapping, export=None):
    output = io.StringIO()

    headers = [column.get("column_label") for column in mapping]
    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()

    for row in rows:
        writer.writerow(build_mapped_row(row, mapping, export=export))

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
    line.export_note = "Generated by Phase 1P template-aware claim export engine."
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
            "export_mapping_template",
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
