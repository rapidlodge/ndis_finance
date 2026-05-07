import csv
import json
import os
import re
from datetime import date, datetime

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, getdate, now_datetime, nowdate
from frappe.utils.file_manager import get_file_path

from ndis_finance.services.payment_reconciliation_engine import (
    create_payment_reconciliation_batch,
    recalculate_payment_reconciliation_batch,
    record_payment_for_claim_line,
)
from ndis_finance.services.permissions import assert_action


ALIASES = {
    "external_claim_reference": [
        "claim reference",
        "external claim reference",
        "claim id",
        "claim number",
        "payment reference",
        "reference",
        "ndia reference",
    ],
    "invoice_number": [
        "invoice",
        "invoice number",
        "invoice no",
        "invoice id",
        "sales invoice",
    ],
    "participant_name": [
        "participant",
        "participant name",
        "client",
        "client name",
        "customer",
        "customer name",
    ],
    "ndis_number": [
        "ndis number",
        "participant ndis number",
        "ndis no",
    ],
    "support_item_number": [
        "support item",
        "support item number",
        "support item no",
        "item number",
        "support code",
        "claim code",
    ],
    "service_date": [
        "service date",
        "date of service",
        "delivered date",
        "claim date",
        "date",
    ],
    "claim_amount": [
        "claim amount",
        "claimed amount",
        "invoice amount",
        "expected amount",
        "gross amount",
        "amount claimed",
    ],
    "paid_amount": [
        "paid amount",
        "payment amount",
        "amount paid",
        "approved amount",
        "paid",
        "amount",
    ],
    "rejection_reason": [
        "rejection reason",
        "reason",
        "shortfall reason",
        "comment",
        "comments",
        "error",
        "error message",
        "rejection",
    ],
}


CLAIM_MATCH_STATUSES = [
    "Ready to Claim",
    "Submitted",
    "Short Paid",
    "Rejected",
    "Reclaim Required",
]


def make_import_id(payer_type="NDIA"):
    prefix = "NDIS-REM-IMP"

    if payer_type == "Plan Manager":
        prefix = "NDIS-PM-REM"
    elif payer_type == "Self Managed":
        prefix = "NDIS-SM-REM"
    elif payer_type == "Other":
        prefix = "NDIS-OTHER-REM"

    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{timestamp}-{frappe.generate_hash(length=5).upper()}"


def normalise_key(value):
    value = str(value or "").strip().lower()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def normalise_compact(value):
    return re.sub(r"[^a-z0-9]+", "", normalise_key(value))


def clean_text(value):
    if value is None:
        return ""

    return str(value).strip()


def clean_money(value):
    if value is None:
        return 0

    if isinstance(value, (int, float)):
        return float(value or 0)

    text = str(value).strip()
    if not text:
        return 0

    if text.lower() in ["-", "n/a", "na", "nil", "not applicable"]:
        return 0

    text = text.replace("$", "").replace(",", "").strip()
    match = re.search(r"-?\d+(\.\d+)?", text)

    if not match:
        return 0

    return float(match.group(0))


def clean_date(value):
    if not value:
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    text = str(value).strip()
    if not text:
        return None

    if re.match(r"^\d{4}-\d{1,2}-\d{1,2}$", text):
        try:
            return getdate(text)
        except Exception:
            pass

    try:
        from dateutil.parser import parse

        return parse(text, dayfirst=True).date()
    except Exception:
        try:
            return getdate(text)
        except Exception:
            return None


def get_physical_file_path(file_path=None, file_url=None, file_docname=None):
    if file_path:
        return file_path

    if file_docname:
        file_url = frappe.db.get_value("File", file_docname, "file_url")

    if file_url:
        return get_file_path(file_url)

    frappe.throw(_("Please provide file_path, file_url, or file_docname."))


def load_rows_from_file(path):
    ext = os.path.splitext(path)[1].lower()

    if ext in [".xlsx", ".xlsm"]:
        return load_rows_from_xlsx(path)

    if ext == ".csv":
        return load_rows_from_csv(path)

    frappe.throw(_("Unsupported file type: {0}. Please use XLSX or CSV.").format(ext))


def load_rows_from_xlsx(path):
    try:
        import openpyxl
    except ImportError:
        frappe.throw(_("openpyxl is required to import XLSX files."))

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)

    best_rows = []
    best_score = -1

    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        score = score_rows(rows)

        if score > best_score:
            best_score = score
            best_rows = rows

    return rows_to_dicts(best_rows)


def load_rows_from_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))

    return rows_to_dicts(rows)


def score_rows(rows):
    score = 0

    for row in rows[:30]:
        text = " ".join([normalise_key(value) for value in row if value is not None])

        if "invoice" in text:
            score += 2
        if "paid" in text or "payment" in text:
            score += 3
        if "claim" in text:
            score += 2
        if "participant" in text or "ndis" in text:
            score += 1

    return score


def find_header_row(rows):
    for idx, row in enumerate(rows[:40]):
        keys = [normalise_key(value) for value in row if value is not None]
        compact = [normalise_compact(value) for value in row if value is not None]
        joined = " ".join(keys)

        has_amount = (
            "paid amount" in joined
            or "payment amount" in joined
            or "amount paid" in joined
            or "paidamount" in compact
            or "amount" in keys
        )

        has_invoice_or_claim = (
            "invoice" in joined
            or "claim" in joined
            or "reference" in joined
        )

        if has_amount and has_invoice_or_claim:
            return idx

    return None


def rows_to_dicts(rows):
    header_index = find_header_row(rows)

    if header_index is None:
        frappe.throw(
            _("Could not find remittance header row. Expected invoice/claim and paid amount columns.")
        )

    headers = [clean_text(value) for value in rows[header_index]]
    output = []

    for raw in rows[header_index + 1 :]:
        if not raw:
            continue

        item = {}
        for idx, header in enumerate(headers):
            if not header:
                continue

            item[header] = raw[idx] if idx < len(raw) else None

        if any(clean_text(value) for value in item.values()):
            output.append(item)

    return output


def find_value(row, fieldname):
    aliases = ALIASES.get(fieldname, [])
    normalised = {}
    compact = {}

    for header, value in row.items():
        normalised[normalise_key(header)] = value
        compact[normalise_compact(header)] = value

    for alias in aliases:
        k1 = normalise_key(alias)
        k2 = normalise_compact(alias)

        if k1 in normalised:
            return normalised[k1]

        if k2 in compact:
            return compact[k2]

    return None


def get_participant_from_remittance_values(ndis_number=None, participant_name=None):
    if ndis_number and frappe.get_meta("Customer").has_field("custom_ndis_number"):
        participant = frappe.db.get_value("Customer", {"custom_ndis_number": ndis_number}, "name")
        if participant:
            return participant

    if participant_name:
        return frappe.db.get_value("Customer", {"customer_name": participant_name}, "name")

    return None


def parse_remittance_row(row):
    invoice_number = clean_text(find_value(row, "invoice_number"))
    external_claim_reference = clean_text(find_value(row, "external_claim_reference"))
    participant_name = clean_text(find_value(row, "participant_name"))
    ndis_number = clean_text(find_value(row, "ndis_number"))
    support_item_number = clean_text(find_value(row, "support_item_number"))
    service_date = clean_date(find_value(row, "service_date"))
    claim_amount = clean_money(find_value(row, "claim_amount"))
    paid_amount = clean_money(find_value(row, "paid_amount"))
    rejection_reason = clean_text(find_value(row, "rejection_reason"))

    sales_invoice = None
    if invoice_number and frappe.db.exists("Sales Invoice", invoice_number):
        sales_invoice = invoice_number

    participant = get_participant_from_remittance_values(
        ndis_number=ndis_number,
        participant_name=participant_name,
    )

    if paid_amount == 0 and rejection_reason:
        outcome = "Rejected"
    elif claim_amount and paid_amount and paid_amount < claim_amount:
        outcome = "Short Paid"
    else:
        outcome = "Paid"

    shortfall_amount = max(flt(claim_amount) - flt(paid_amount), 0) if claim_amount else 0

    return {
        "external_claim_reference": external_claim_reference,
        "invoice_number": invoice_number,
        "sales_invoice": sales_invoice,
        "participant_name": participant_name,
        "participant": participant,
        "ndis_number": ndis_number,
        "support_item_number": support_item_number,
        "service_date": service_date,
        "claim_amount": claim_amount,
        "paid_amount": paid_amount,
        "shortfall_amount": shortfall_amount,
        "outcome": outcome,
        "rejection_reason": rejection_reason,
        "raw_json": json.dumps(row, default=str),
    }


@frappe.whitelist()
def import_remittance_file(
    file_path=None,
    file_url=None,
    file_docname=None,
    payer_type="NDIA",
    claim_batch=None,
    funding_source=None,
    company=None,
    payment_date=None,
    external_payment_reference=None,
    received_amount=None,
    notes=None,
    dry_run=0,
    limit=None,
):
    assert_action("import_remittance")

    dry_run = int(dry_run or 0)
    limit = int(limit or 0)

    path = get_physical_file_path(
        file_path=file_path,
        file_url=file_url,
        file_docname=file_docname,
    )

    if not os.path.exists(path):
        frappe.throw(_("File does not exist: {0}").format(path))

    rows = load_rows_from_file(path)
    if limit:
        rows = rows[:limit]

    parsed_rows = [parse_remittance_row(row) for row in rows]

    total_paid = sum(flt(row.get("paid_amount")) for row in parsed_rows)
    total_claim = sum(flt(row.get("claim_amount")) for row in parsed_rows)
    received_amount = flt(received_amount) if received_amount is not None else total_paid

    if dry_run:
        return {
            "dry_run": True,
            "file": path,
            "payer_type": payer_type,
            "claim_batch": claim_batch,
            "line_count": len(parsed_rows),
            "received_amount": received_amount,
            "total_claim_amount_in_file": total_claim,
            "total_paid_amount_in_file": total_paid,
            "preview": parsed_rows[:20],
            "note": "Dry run only. No records created.",
        }

    doc = frappe.new_doc("NDIS Remittance Import")
    doc.remittance_import_id = make_import_id(payer_type)
    doc.payer_type = payer_type
    doc.status = "Imported"
    doc.company = company
    doc.funding_source = funding_source
    doc.claim_batch = claim_batch
    doc.payment_date = payment_date or nowdate()
    doc.external_payment_reference = external_payment_reference
    doc.source_file_name = os.path.basename(path)
    doc.expected_claim_amount = total_claim
    doc.received_amount = received_amount
    doc.line_count = len(parsed_rows)
    doc.imported_on = now_datetime()
    doc.imported_by = frappe.session.user
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    for idx, parsed in enumerate(parsed_rows, start=1):
        line = frappe.new_doc("NDIS Remittance Import Line")
        line.remittance_import = doc.name
        line.source_row = idx
        line.status = "Imported"
        line.match_confidence = "None"

        for fieldname, value in parsed.items():
            if line.meta.has_field(fieldname):
                setattr(line, fieldname, value)

        line.insert(ignore_permissions=True)

    update_import_summary(doc.name)
    frappe.db.commit()

    return {
        "created": True,
        "remittance_import": doc.name,
        "remittance_import_id": doc.remittance_import_id,
        "line_count": len(parsed_rows),
        "received_amount": received_amount,
        "total_claim_amount_in_file": total_claim,
        "total_paid_amount_in_file": total_paid,
        "note": "Import created. No accounting entry or payment allocation was created.",
    }


@frappe.whitelist()
def match_remittance_import(remittance_import):
    assert_action("match_remittance")

    if not frappe.db.exists("NDIS Remittance Import", remittance_import):
        frappe.throw(_("NDIS Remittance Import not found: {0}").format(remittance_import))

    parent = frappe.get_doc("NDIS Remittance Import", remittance_import)

    lines = frappe.get_all(
        "NDIS Remittance Import Line",
        filters={
            "remittance_import": remittance_import,
            "status": ["in", ["Imported", "Unmatched", "Multiple Matches", "Error"]],
        },
        fields=["name"],
        order_by="source_row asc",
    )

    results = []

    for row in lines:
        line = frappe.get_doc("NDIS Remittance Import Line", row.name)
        results.append(match_single_line(parent, line))

    update_import_summary(remittance_import)

    matched = len([row for row in results if row.get("status") == "Matched"])
    multiple = len([row for row in results if row.get("status") == "Multiple Matches"])
    unmatched = len([row for row in results if row.get("status") == "Unmatched"])

    new_status = "Matched"
    if matched and (multiple or unmatched):
        new_status = "Partially Matched"
    elif not matched:
        new_status = "Imported"

    frappe.db.set_value(
        "NDIS Remittance Import",
        remittance_import,
        {
            "status": new_status,
            "matched_on": now_datetime(),
        },
        update_modified=False,
    )

    frappe.db.commit()

    return {
        "remittance_import": remittance_import,
        "matched": matched,
        "multiple_matches": multiple,
        "unmatched": unmatched,
        "results": results[:50],
    }


def match_single_line(parent, line):
    candidates = get_match_candidates(parent, line)

    if not candidates:
        line.status = "Unmatched"
        line.match_confidence = "None"
        line.confidence_score = 0
        line.matched_claim_line = None
        line.match_note = "No matching claim line found."
        line.save(ignore_permissions=True)

        return {
            "line": line.name,
            "status": "Unmatched",
            "score": 0,
            "note": line.match_note,
        }

    candidates = sorted(candidates, key=lambda item: item["score"], reverse=True)
    best = candidates[0]

    if len(candidates) > 1 and candidates[1]["score"] == best["score"]:
        line.status = "Multiple Matches"
        line.match_confidence = "Low"
        line.confidence_score = best["score"]
        line.matched_claim_line = None
        line.match_note = "Multiple claim lines matched with same score. Manual review required."
        line.save(ignore_permissions=True)

        return {
            "line": line.name,
            "status": "Multiple Matches",
            "score": best["score"],
            "candidate_count": len(candidates),
            "note": line.match_note,
        }

    if best["score"] < 300:
        line.status = "Unmatched"
        line.match_confidence = "Low"
        line.confidence_score = best["score"]
        line.matched_claim_line = None
        line.match_note = f"Best score {best['score']} is below safe auto-match threshold."
        line.save(ignore_permissions=True)

        return {
            "line": line.name,
            "status": "Unmatched",
            "score": best["score"],
            "candidate": best["name"],
            "note": line.match_note,
        }

    confidence = "High" if best["score"] >= 500 else "Medium"

    line.status = "Matched"
    line.match_confidence = confidence
    line.confidence_score = best["score"]
    line.matched_claim_line = best["name"]
    line.match_note = best["note"]
    line.save(ignore_permissions=True)

    return {
        "line": line.name,
        "status": "Matched",
        "claim_line": best["name"],
        "score": best["score"],
        "confidence": confidence,
        "note": best["note"],
    }


def get_match_candidates(parent, line):
    params = {
        "statuses": tuple(CLAIM_MATCH_STATUSES),
    }

    conditions = [
        "cl.claim_status IN %(statuses)s",
        "cl.claim_status != 'Paid'",
    ]

    if parent.claim_batch:
        conditions.append("cl.claim_batch = %(claim_batch)s")
        params["claim_batch"] = parent.claim_batch

    rows = frappe.db.sql(
        f"""
        SELECT
            cl.name,
            cl.claim_batch,
            cl.sales_invoice,
            cl.participant,
            cl.service_date,
            cl.support_item_number,
            cl.claim_amount,
            cl.paid_amount,
            cl.shortfall_amount,
            cl.external_claim_reference,
            cl.claim_status,
            cl.payment_status
        FROM `tabNDIS Claim Line` cl
        WHERE {" AND ".join(conditions)}
        LIMIT 500
        """,
        params,
        as_dict=True,
    )

    candidates = []

    for claim in rows:
        score = 0
        reasons = []

        if line.external_claim_reference and claim.external_claim_reference:
            if line.external_claim_reference == claim.external_claim_reference:
                score += 500
                reasons.append("external claim reference")

        if line.sales_invoice and claim.sales_invoice == line.sales_invoice:
            score += 300
            reasons.append("sales invoice")

        if line.invoice_number and claim.sales_invoice == line.invoice_number:
            score += 300
            reasons.append("invoice number")

        if line.support_item_number and claim.support_item_number == line.support_item_number:
            score += 100
            reasons.append("support item")

        if line.service_date and claim.service_date and getdate(line.service_date) == getdate(claim.service_date):
            score += 80
            reasons.append("service date")

        if line.claim_amount and abs(flt(claim.claim_amount) - flt(line.claim_amount)) <= 0.01:
            score += 80
            reasons.append("claim amount")

        if line.participant and claim.participant == line.participant:
            score += 80
            reasons.append("participant")

        if score:
            candidates.append(
                {
                    "name": claim.name,
                    "score": score,
                    "note": "Matched by: " + ", ".join(reasons),
                }
            )

    return candidates


@frappe.whitelist()
def apply_remittance_import(remittance_import, create_reconciliation_batch=1):
    assert_action("apply_remittance")

    if not frappe.db.exists("NDIS Remittance Import", remittance_import):
        frappe.throw(_("NDIS Remittance Import not found: {0}").format(remittance_import))

    parent = frappe.get_doc("NDIS Remittance Import", remittance_import)

    if not parent.payment_reconciliation_batch and int(create_reconciliation_batch or 0):
        result = create_payment_reconciliation_batch(
            payer_type=parent.payer_type,
            claim_batch=parent.claim_batch,
            funding_source=parent.funding_source,
            company=parent.company,
            payment_date=parent.payment_date,
            external_payment_reference=parent.external_payment_reference,
            received_amount=parent.received_amount,
            notes=f"Created from Remittance Import {parent.name}",
        )

        parent.payment_reconciliation_batch = result.get("reconciliation_batch")
        parent.save(ignore_permissions=True)

        if parent.payment_reconciliation_batch:
            safe_db_set(
                "NDIS Payment Reconciliation Batch",
                parent.payment_reconciliation_batch,
                "remittance_import",
                parent.name,
            )

    if not parent.payment_reconciliation_batch:
        frappe.throw(_("Payment Reconciliation Batch is required before applying remittance."))

    lines = frappe.get_all(
        "NDIS Remittance Import Line",
        filters={
            "remittance_import": remittance_import,
            "status": "Matched",
        },
        fields=["name"],
        order_by="source_row asc",
    )

    applied = 0
    skipped = 0
    errors = []

    for row in lines:
        line = frappe.get_doc("NDIS Remittance Import Line", row.name)

        try:
            if not line.matched_claim_line:
                skipped += 1
                continue

            claim_status = frappe.db.get_value(
                "NDIS Claim Line",
                line.matched_claim_line,
                "claim_status",
            )
            if claim_status == "Paid":
                line.status = "Skipped"
                line.match_note = "Skipped because claim line is already Paid."
                line.save(ignore_permissions=True)
                skipped += 1
                continue

            outcome_result = record_payment_for_claim_line(
                reconciliation_batch=parent.payment_reconciliation_batch,
                claim_line=line.matched_claim_line,
                paid_amount=flt(line.paid_amount),
                rejection_reason=line.rejection_reason,
                external_claim_reference=line.external_claim_reference,
            )

            reconciliation_line = outcome_result.get("reconciliation_line")

            line.status = "Applied"
            line.payment_reconciliation_line = reconciliation_line
            line.shortfall_amount = outcome_result.get("shortfall_amount")
            line.outcome = outcome_result.get("outcome")
            line.match_note = "Applied to payment reconciliation."
            line.save(ignore_permissions=True)

            safe_db_set("NDIS Claim Line", line.matched_claim_line, "remittance_import", parent.name)
            safe_db_set("NDIS Claim Line", line.matched_claim_line, "remittance_import_line", line.name)

            if reconciliation_line:
                safe_db_set(
                    "NDIS Payment Reconciliation Line",
                    reconciliation_line,
                    "remittance_import",
                    parent.name,
                )
                safe_db_set(
                    "NDIS Payment Reconciliation Line",
                    reconciliation_line,
                    "remittance_import_line",
                    line.name,
                )

            applied += 1

        except Exception as exc:
            line.status = "Error"
            line.match_note = str(exc)
            line.save(ignore_permissions=True)
            errors.append(f"{line.name}: {str(exc)}")

    update_import_summary(remittance_import)

    status = "Applied"
    if errors or skipped:
        status = "Partially Applied"

    frappe.db.set_value(
        "NDIS Remittance Import",
        remittance_import,
        {
            "status": status,
            "applied_on": now_datetime(),
            "warning_log": "\n".join(errors[:100]),
        },
        update_modified=False,
    )

    if parent.payment_reconciliation_batch:
        recalculate_payment_reconciliation_batch(parent.payment_reconciliation_batch)

    frappe.db.commit()

    return {
        "remittance_import": remittance_import,
        "payment_reconciliation_batch": parent.payment_reconciliation_batch,
        "applied": applied,
        "skipped": skipped,
        "errors": errors[:20],
        "note": "Remittance applied to NDIS reconciliation controls only. No Payment Entry, Journal Entry, GL Entry, or allocation was created.",
    }


def update_import_summary(remittance_import):
    rows = frappe.db.sql(
        """
        SELECT
            COUNT(*) AS line_count,
            COALESCE(SUM(CASE WHEN status IN ('Matched', 'Applied') THEN 1 ELSE 0 END), 0) AS matched_line_count,
            COALESCE(SUM(CASE WHEN status = 'Applied' THEN 1 ELSE 0 END), 0) AS applied_line_count,
            COALESCE(SUM(CASE WHEN status IN ('Matched', 'Applied') THEN paid_amount ELSE 0 END), 0) AS matched_amount,
            COALESCE(SUM(CASE WHEN status IN ('Unmatched', 'Multiple Matches', 'Error') THEN paid_amount ELSE 0 END), 0) AS unmatched_amount,
            COALESCE(SUM(shortfall_amount), 0) AS shortfall_amount
        FROM `tabNDIS Remittance Import Line`
        WHERE remittance_import = %(remittance_import)s
        """,
        {"remittance_import": remittance_import},
        as_dict=True,
    )

    totals = rows[0] if rows else {}

    frappe.db.set_value(
        "NDIS Remittance Import",
        remittance_import,
        {
            "line_count": int(totals.get("line_count") or 0),
            "matched_line_count": int(totals.get("matched_line_count") or 0),
            "applied_line_count": int(totals.get("applied_line_count") or 0),
            "matched_amount": flt(totals.get("matched_amount")),
            "unmatched_amount": flt(totals.get("unmatched_amount")),
            "shortfall_amount": flt(totals.get("shortfall_amount")),
        },
        update_modified=False,
    )


def safe_db_set(doctype, name, fieldname, value):
    if name and frappe.get_meta(doctype).has_field(fieldname):
        frappe.db.set_value(doctype, name, fieldname, value, update_modified=False)


@frappe.whitelist()
def quick_remittance_import_summary(limit=20):
    imports = frappe.get_all(
        "NDIS Remittance Import",
        fields=[
            "name",
            "remittance_import_id",
            "payer_type",
            "status",
            "claim_batch",
            "payment_reconciliation_batch",
            "payment_date",
            "received_amount",
            "matched_amount",
            "unmatched_amount",
            "shortfall_amount",
            "line_count",
            "matched_line_count",
            "applied_line_count",
        ],
        order_by="modified desc",
        limit=int(limit or 20),
    )

    lines = frappe.get_all(
        "NDIS Remittance Import Line",
        fields=[
            "name",
            "remittance_import",
            "source_row",
            "status",
            "match_confidence",
            "confidence_score",
            "matched_claim_line",
            "invoice_number",
            "support_item_number",
            "service_date",
            "claim_amount",
            "paid_amount",
            "shortfall_amount",
            "outcome",
            "match_note",
        ],
        order_by="modified desc",
        limit=int(limit or 20),
    )

    return {
        "imports": imports,
        "lines": lines,
    }
