import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


PREVIEW_DOCTYPE = "NDIS Real Remittance PE Preview"
LINE_DOCTYPE = "NDIS Real Remittance PE Preview Line"
DESIGN_DOCTYPE = "NDIS Real Remittance PE Design Gate"
PREVIEW_ACK = "I_CONFIRM_PHASE6B_REAL_REMITTANCE_PE_PREVIEW_ONLY_NO_POSTING"


def make_preview_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-REAL-REMITTANCE-PE-PREVIEW-{timestamp}-{frappe.generate_hash(length=5).upper()}"


def currency():
    return frappe.defaults.get_global_default("currency") or "AUD"


def safe_json(value):
    try:
        return json.dumps(value, indent=2, default=str)
    except Exception:
        return str(value)


def count_dt(doctype, filters=None):
    if not frappe.db.exists("DocType", doctype):
        return 0
    return frappe.db.count(doctype, filters or {})


def config_state():
    return {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def guardrails():
    return {
        "payment_entry_count": count_dt("Payment Entry"),
        "payment_entry_gl_count": count_dt("GL Entry", {"voucher_type": "Payment Entry"}),
        "submitted_journal_entry_count_today": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}),
        "sales_invoice_count_today": count_dt("Sales Invoice", {"creation": [">=", today()]}),
        "purchase_invoice_count_today": count_dt("Purchase Invoice", {"creation": [">=", today()]}),
        "live_enabled_policy_count": count_dt("NDIS PE Production Posting Policy", {"production_posting_enabled": 1}),
    }


def latest_approved_design_gate():
    rows = frappe.get_all(
        DESIGN_DOCTYPE,
        filters={
            "status": "Approved",
            "design_approved_for_preview_phase": 1,
            "real_posting_allowed": 0,
        },
        fields=[
            "name",
            "design_gate_id",
            "company",
            "bank_account",
            "receivable_account",
            "batch_line_cap",
            "batch_amount_cap",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def add_item(items, status, severity, category, check_key, check_label, detail, recommendation=None, source_doctype=None, source_name=None):
    items.append(
        {
            "status": status,
            "severity": severity,
            "category": category,
            "check_key": check_key,
            "check_label": check_label,
            "detail": detail,
            "recommendation": recommendation,
            "source_doctype": source_doctype,
            "source_name": source_name,
        }
    )


def meta_fieldnames(doctype):
    if not frappe.db.exists("DocType", doctype):
        return []
    return [df.fieldname for df in frappe.get_meta(doctype).fields]


def first_existing_field(fields, candidates):
    for candidate in candidates:
        if candidate in fields:
            return candidate
    return None


def get_line_mapping():
    fields = meta_fieldnames("NDIS Remittance Import Line")
    return {
        "parent_import": first_existing_field(fields, ["remittance_import", "ndis_remittance_import", "import_reference", "parent"]),
        "outcome": first_existing_field(fields, ["claim_outcome", "outcome", "payment_outcome", "status", "invoice_status", "match_status"]),
        "claim_line": first_existing_field(fields, ["claim_line", "matched_claim_line", "ndis_claim_line", "claim_line_reference", "reference_claim_line"]),
        "sales_invoice": first_existing_field(fields, ["sales_invoice", "invoice", "invoice_reference", "sales_invoice_reference", "erpnext_sales_invoice"]),
        "paid_amount": first_existing_field(fields, ["paid_amount", "payment_amount", "received_amount", "amount", "allocated_amount"]),
        "shortfall_amount": first_existing_field(fields, ["shortfall_amount", "variance_amount", "gap_amount", "rejected_amount"]),
    }


def get_claim_line_mapping():
    fields = meta_fieldnames("NDIS Claim Line")
    return {
        "sales_invoice": first_existing_field(fields, ["sales_invoice", "invoice", "sales_invoice_reference", "source_sales_invoice"]),
        "sales_invoice_item": first_existing_field(fields, ["sales_invoice_item", "invoice_item", "sales_invoice_detail"]),
        "claim_amount": first_existing_field(fields, ["claim_amount", "amount", "claimed_amount", "line_amount"]),
        "paid_amount": first_existing_field(fields, ["paid_amount", "received_amount", "settled_amount"]),
    }


def get_remittance_lines(remittance_import=None, limit=500):
    mapping = get_line_mapping()
    fields = ["name"]
    for fieldname in mapping.values():
        if fieldname and fieldname not in fields:
            fields.append(fieldname)
    filters = {}
    if remittance_import and mapping["parent_import"]:
        filters[mapping["parent_import"]] = remittance_import
    return frappe.get_all(
        "NDIS Remittance Import Line",
        filters=filters,
        fields=fields,
        order_by="creation asc",
        limit=int(limit or 500),
    )


def infer_source_import(rows, mapping, requested_import=None):
    if requested_import:
        return requested_import
    parent_field = mapping.get("parent_import")
    if not parent_field:
        return None
    values = {row.get(parent_field) for row in rows if row.get(parent_field)}
    return values.pop() if len(values) == 1 else None


def resolve_sales_invoice_from_claim_line(claim_line):
    if not claim_line or not frappe.db.exists("NDIS Claim Line", claim_line):
        return None
    invoice_field = get_claim_line_mapping().get("sales_invoice")
    if invoice_field:
        value = frappe.db.get_value("NDIS Claim Line", claim_line, invoice_field)
        if value and frappe.db.exists("Sales Invoice", value):
            return value
    return None


def existing_payment_reference_count(sales_invoice):
    if not sales_invoice:
        return 0
    return frappe.db.sql(
        """
        SELECT COUNT(*)
        FROM `tabPayment Entry Reference` per
        INNER JOIN `tabPayment Entry` pe ON pe.name = per.parent
        WHERE per.reference_doctype = 'Sales Invoice'
        AND per.reference_name = %(sales_invoice)s
        AND pe.docstatus != 2
        """,
        {"sales_invoice": sales_invoice},
    )[0][0]


def base_line(row, mapping):
    outcome = str(row.get(mapping["outcome"]) or "").strip() if mapping["outcome"] else ""
    claim_line = row.get(mapping["claim_line"]) if mapping["claim_line"] else None
    sales_invoice = row.get(mapping["sales_invoice"]) if mapping["sales_invoice"] else None
    source_amount = flt(row.get(mapping["paid_amount"]) or 0) if mapping["paid_amount"] else 0
    shortfall_amount = flt(row.get(mapping["shortfall_amount"]) or 0) if mapping["shortfall_amount"] else 0
    return {
        "source_remittance_import": row.get(mapping["parent_import"]) if mapping["parent_import"] else None,
        "source_remittance_line": row.name,
        "source_outcome": outcome,
        "claim_line": claim_line,
        "sales_invoice": sales_invoice,
        "company": None,
        "customer": None,
        "source_amount": source_amount,
        "allocatable_amount": 0,
        "invoice_outstanding_amount": 0,
        "shortfall_amount": shortfall_amount,
        "classification": "Review Required",
        "preview_status": "Review",
        "block_reason": "Outcome does not match allowed Paid / Short Paid logic.",
        "would_create_payment_entry": 0,
        "payment_entry_created": 0,
        "duplicate_detected": 0,
        "overpayment_detected": 0,
        "cross_company_detected": 0,
        "batch_cap_blocked": 0,
    }


def classify_line(row, mapping, design_gate, running_eligible_count, running_eligible_amount):
    result = base_line(row, mapping)
    outcome_l = result["source_outcome"].lower()
    sales_invoice = result["sales_invoice"] or resolve_sales_invoice_from_claim_line(result["claim_line"])
    result["sales_invoice"] = sales_invoice

    if "reject" in outcome_l:
        result.update(
            {
                "classification": "Blocked Rejected",
                "preview_status": "Blocked",
                "block_reason": "Rejected remittance/claim outcome is blocked from Payment Entry posting.",
            }
        )
        return result

    is_short_paid = "short" in outcome_l and "paid" in outcome_l
    is_paid = outcome_l in ["paid", "fully paid"]
    if not is_paid and not is_short_paid:
        return result

    if not result["claim_line"] and not sales_invoice:
        result.update(
            {
                "classification": "Blocked Unmatched",
                "preview_status": "Blocked",
                "block_reason": "No matched claim line or Sales Invoice reference found.",
            }
        )
        return result

    if not sales_invoice or not frappe.db.exists("Sales Invoice", sales_invoice):
        result.update(
            {
                "classification": "Blocked Missing Invoice / Claim Line",
                "preview_status": "Blocked",
                "block_reason": "Could not resolve a valid Sales Invoice from remittance line / claim line.",
            }
        )
        return result

    si = frappe.get_doc("Sales Invoice", sales_invoice)
    result["company"] = si.company
    result["customer"] = si.customer
    result["invoice_outstanding_amount"] = flt(si.outstanding_amount)

    if si.docstatus != 1:
        result.update(
            {
                "classification": "Blocked Missing Invoice / Claim Line",
                "preview_status": "Blocked",
                "block_reason": f"Sales Invoice docstatus is {si.docstatus}; expected submitted docstatus 1.",
            }
        )
        return result

    if si.company != design_gate.company:
        result.update(
            {
                "classification": "Blocked Cross-company",
                "preview_status": "Blocked",
                "block_reason": f"Invoice company {si.company} does not match design company {design_gate.company}.",
                "cross_company_detected": 1,
            }
        )
        return result

    if existing_payment_reference_count(si.name):
        result.update(
            {
                "classification": "Blocked Duplicate",
                "preview_status": "Blocked",
                "block_reason": "A non-cancelled Payment Entry Reference already exists for this Sales Invoice.",
                "duplicate_detected": 1,
            }
        )
        return result

    if result["source_amount"] <= 0:
        result.update(
            {
                "classification": "Review Required",
                "preview_status": "Review",
                "block_reason": "Source payment amount is zero or missing.",
            }
        )
        return result

    if result["source_amount"] > flt(si.outstanding_amount):
        result.update(
            {
                "classification": "Blocked Overpayment",
                "preview_status": "Blocked",
                "block_reason": f"Source amount {result['source_amount']:.2f} exceeds invoice outstanding {flt(si.outstanding_amount):.2f}.",
                "overpayment_detected": 1,
            }
        )
        return result

    if running_eligible_count + 1 > int(design_gate.batch_line_cap or 10):
        result.update(
            {
                "classification": "Blocked Batch Cap",
                "preview_status": "Blocked",
                "block_reason": "Future batch line cap would be exceeded.",
                "batch_cap_blocked": 1,
            }
        )
        return result

    if running_eligible_amount + result["source_amount"] > flt(design_gate.batch_amount_cap or 0):
        result.update(
            {
                "classification": "Blocked Batch Cap",
                "preview_status": "Blocked",
                "block_reason": "Future batch amount cap would be exceeded.",
                "batch_cap_blocked": 1,
            }
        )
        return result

    result.update(
        {
            "classification": "Eligible Short Paid" if is_short_paid else "Eligible Paid",
            "preview_status": "Eligible",
            "block_reason": "",
            "allocatable_amount": result["source_amount"],
            "would_create_payment_entry": 1,
        }
    )
    return result


def summarise_lines(lines):
    summary = {
        "source_line_count": len(lines),
        "eligible_line_count": 0,
        "blocked_line_count": 0,
        "review_line_count": 0,
        "eligible_paid_line_count": 0,
        "eligible_short_paid_line_count": 0,
        "blocked_rejected_line_count": 0,
        "blocked_duplicate_line_count": 0,
        "blocked_unmatched_line_count": 0,
        "blocked_overpayment_line_count": 0,
        "blocked_cross_company_line_count": 0,
        "blocked_missing_invoice_line_count": 0,
        "blocked_batch_cap_line_count": 0,
        "eligible_amount": 0,
        "blocked_amount": 0,
        "review_amount": 0,
        "would_create_payment_entry_count": 0,
        "actual_payment_entry_created_count": 0,
    }
    classification_keys = {
        "Eligible Paid": "eligible_paid_line_count",
        "Eligible Short Paid": "eligible_short_paid_line_count",
        "Blocked Rejected": "blocked_rejected_line_count",
        "Blocked Duplicate": "blocked_duplicate_line_count",
        "Blocked Unmatched": "blocked_unmatched_line_count",
        "Blocked Overpayment": "blocked_overpayment_line_count",
        "Blocked Cross-company": "blocked_cross_company_line_count",
        "Blocked Missing Invoice / Claim Line": "blocked_missing_invoice_line_count",
        "Blocked Batch Cap": "blocked_batch_cap_line_count",
    }
    for line in lines:
        amount = flt(line.get("source_amount") or 0)
        if line["preview_status"] == "Eligible":
            summary["eligible_line_count"] += 1
            summary["eligible_amount"] += flt(line.get("allocatable_amount") or 0)
        elif line["preview_status"] == "Blocked":
            summary["blocked_line_count"] += 1
            summary["blocked_amount"] += amount
        else:
            summary["review_line_count"] += 1
            summary["review_amount"] += amount
        if line["classification"] in classification_keys:
            summary[classification_keys[line["classification"]]] += 1
        summary["would_create_payment_entry_count"] += int(line.get("would_create_payment_entry") or 0)
    return summary


def add_preview_items(items, design_gate, line_summary, source_line_count):
    if not design_gate:
        add_item(items, "Blocker", "Critical", "Design Gate", "approved_design_gate", "Approved Phase 6A design gate", "No approved Phase 6A design gate found.")
        return
    add_item(
        items,
        "Pass",
        "Low",
        "Design Gate",
        "approved_design_gate",
        "Approved Phase 6A design gate",
        f"Approved design gate found: {design_gate.design_gate_id}.",
        None,
        DESIGN_DOCTYPE,
        design_gate.name,
    )
    if source_line_count:
        add_item(items, "Pass", "Low", "Source", "source_lines", "Source remittance lines", f"{source_line_count} source remittance line(s) scanned.")
    else:
        add_item(items, "Warning", "Medium", "Source", "source_lines", "Source remittance lines", "No remittance lines found for preview.")
    if line_summary["eligible_line_count"]:
        add_item(items, "Pass", "Low", "Preview Result", "eligible_lines", "Eligible lines", f"{line_summary['eligible_line_count']} line(s) eligible for future hard-block adapter.")
    else:
        add_item(items, "Warning", "Medium", "Preview Result", "eligible_lines", "Eligible lines", "No eligible paid/short-paid lines found.")
    if line_summary["blocked_line_count"]:
        add_item(items, "Info", "Low", "Preview Result", "blocked_lines", "Blocked lines", f"{line_summary['blocked_line_count']} line(s) blocked by preview controls.")
    if line_summary["review_line_count"]:
        add_item(items, "Info", "Low", "Preview Result", "review_lines", "Review lines", f"{line_summary['review_line_count']} line(s) require review.")
    add_item(items, "Pass", "Low", "Posting Guardrail", "no_posting", "No posting", "Phase 6B preview does not create Payment Entry or GL.")


def summarise_items(items):
    return {
        "blocker_count": len([i for i in items if i["status"] == "Blocker"]),
        "warning_count": len([i for i in items if i["status"] == "Warning"]),
        "pass_count": len([i for i in items if i["status"] == "Pass"]),
        "info_count": len([i for i in items if i["status"] == "Info"]),
        "item_count": len(items),
    }


def calculate_score(blockers, warnings):
    score = 100
    score -= int(blockers or 0) * 25
    score -= int(warnings or 0) * 5
    return max(0, round(score, 2))


def get_preview_status(blockers, eligible_count):
    if blockers:
        return "Blocked"
    if eligible_count:
        return "Ready For Hard-block Adapter"
    return "Previewed With Exceptions"


def create_preview_lines(preview_doc, lines):
    for line in lines:
        row = frappe.new_doc(LINE_DOCTYPE)
        row.preview = preview_doc.name
        row.source_remittance_import = line.get("source_remittance_import") or preview_doc.source_remittance_import
        row.source_remittance_line = line.get("source_remittance_line")
        row.source_outcome = line.get("source_outcome")
        row.classification = line.get("classification")
        row.preview_status = line.get("preview_status")
        row.block_reason = line.get("block_reason")
        row.claim_line = line.get("claim_line")
        row.sales_invoice = line.get("sales_invoice")
        row.company = line.get("company")
        row.customer = line.get("customer")
        row.source_amount = flt(line.get("source_amount") or 0)
        row.allocatable_amount = flt(line.get("allocatable_amount") or 0)
        row.invoice_outstanding_amount = flt(line.get("invoice_outstanding_amount") or 0)
        row.shortfall_amount = flt(line.get("shortfall_amount") or 0)
        row.would_create_payment_entry = int(line.get("would_create_payment_entry") or 0)
        row.payment_entry_created = 0
        row.duplicate_detected = int(line.get("duplicate_detected") or 0)
        row.overpayment_detected = int(line.get("overpayment_detected") or 0)
        row.cross_company_detected = int(line.get("cross_company_detected") or 0)
        row.batch_cap_blocked = int(line.get("batch_cap_blocked") or 0)
        row.checked_on = preview_doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_real_remittance_pe_preview(
    design_gate=None,
    remittance_import=None,
    dry_run=1,
    acknowledgement=None,
    limit=500,
    notes=None,
):
    assert_action("run_real_remittance_pe_preview")
    dry_run = int(dry_run or 0)
    if design_gate:
        if not frappe.db.exists(DESIGN_DOCTYPE, design_gate):
            frappe.throw(_("Design gate not found: {0}").format(design_gate))
        gate = frappe.get_doc(DESIGN_DOCTYPE, design_gate)
    else:
        latest = latest_approved_design_gate()
        gate = frappe.get_doc(DESIGN_DOCTYPE, latest.name) if latest else None

    guard_before = guardrails()
    config = config_state()
    mapping = get_line_mapping()
    rows = get_remittance_lines(remittance_import=remittance_import, limit=limit)
    source_import = infer_source_import(rows, mapping, remittance_import)
    preview_lines = []
    running_eligible_count = 0
    running_eligible_amount = 0

    for row in rows:
        if gate:
            classified = classify_line(row, mapping, gate, running_eligible_count, running_eligible_amount)
        else:
            classified = base_line(row, mapping)
            classified.update({"block_reason": "No approved Phase 6A design gate found."})
        if classified["preview_status"] == "Eligible":
            running_eligible_count += 1
            running_eligible_amount += flt(classified.get("allocatable_amount") or 0)
        preview_lines.append(classified)

    line_summary = summarise_lines(preview_lines)
    items = []
    if config["production_mode"]:
        add_item(items, "Blocker", "Critical", "Site Config", "production_mode", "Production mode", "Production mode is enabled.")
    else:
        add_item(items, "Pass", "Low", "Site Config", "production_mode", "Production mode", "Production mode remains disabled.")
    if config["live_pe_enabled"]:
        add_item(items, "Blocker", "Critical", "Site Config", "live_pe_enabled", "Live PE posting config", "Live Payment Entry posting config is enabled.")
    else:
        add_item(items, "Pass", "Low", "Site Config", "live_pe_enabled", "Live PE posting config", "Live Payment Entry posting remains disabled.")
    if guard_before["live_enabled_policy_count"]:
        add_item(items, "Blocker", "Critical", "Policy", "live_enabled_policy", "Live-enabled PE policy", f"{guard_before['live_enabled_policy_count']} live-enabled policy record(s) found.")
    else:
        add_item(items, "Pass", "Low", "Policy", "live_enabled_policy", "Live-enabled PE policy", "Zero live-enabled policy records.")
    add_preview_items(items, gate, line_summary, len(rows))

    ack_ok = acknowledgement == PREVIEW_ACK
    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "preview_ack", "Preview acknowledgement", "Exact acknowledgement supplied.")
    elif dry_run:
        add_item(items, "Info", "Low", "Acknowledgement", "preview_ack", "Preview acknowledgement", f"Required acknowledgement for approval: {PREVIEW_ACK}")
    else:
        add_item(
            items,
            "Warning",
            "Medium",
            "Acknowledgement",
            "preview_ack",
            "Preview acknowledgement",
            f"Required acknowledgement not supplied. Required: {PREVIEW_ACK}",
            "Provide exact acknowledgement to create approved preview records.",
        )

    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    approved = int(ack_ok and item_summary["blocker_count"] == 0)
    status_text = "Previewed" if approved else ("Blocked" if item_summary["blocker_count"] else ("Previewed" if dry_run else "Needs Review"))
    preview_status_text = get_preview_status(item_summary["blocker_count"], line_summary["eligible_line_count"])
    guard_after = guardrails()

    result = {
        "dry_run": bool(dry_run),
        "status": status_text,
        "preview_status": preview_status_text,
        "preview_score": score,
        "preview_approved_for_adapter_phase": approved,
        "real_posting_allowed": 0,
        "design_gate": gate.name if gate else None,
        "company": gate.company if gate else None,
        "bank_account": gate.bank_account if gate else None,
        "receivable_account": gate.receivable_account if gate else None,
        "source_remittance_import": source_import,
        "batch_line_cap": int(gate.batch_line_cap or 10) if gate else 0,
        "batch_amount_cap": flt(gate.batch_amount_cap or 0) if gate else 0,
        "line_summary": line_summary,
        "summary": item_summary,
        "items": items,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "config": config,
        "required_acknowledgement": PREVIEW_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 6B preview only. No Payment Entry, GL Entry, invoice, allocation, Xero, ABA, STP, payroll, or email movement is created.",
    }
    if dry_run:
        result["preview_lines"] = preview_lines[:50]
        return result

    doc = frappe.new_doc(PREVIEW_DOCTYPE)
    doc.preview_id = make_preview_id()
    doc.status = status_text
    doc.preview_type = "Limited Real Remittance To Payment Entry"
    doc.design_gate = gate.name if gate else None
    doc.preview_approved_for_adapter_phase = approved
    doc.real_posting_allowed = 0
    doc.company = gate.company if gate else None
    doc.bank_account = gate.bank_account if gate else None
    doc.receivable_account = gate.receivable_account if gate else None
    doc.source_remittance_import = source_import
    doc.batch_line_cap = int(gate.batch_line_cap or 10) if gate else 0
    doc.batch_amount_cap = flt(gate.batch_amount_cap or 0) if gate else 0
    for key, value in line_summary.items():
        if doc.meta.has_field(key):
            setattr(doc, key, value)
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.preview_score = score
    doc.preview_status = preview_status_text
    doc.blocker_count = item_summary["blocker_count"]
    doc.warning_count = item_summary["warning_count"]
    doc.pass_count = item_summary["pass_count"]
    doc.info_count = item_summary["info_count"]
    doc.item_count = item_summary["item_count"]
    doc.payment_entry_count_before = guard_before["payment_entry_count"]
    doc.payment_entry_count_after = guard_after["payment_entry_count"]
    doc.payment_entry_gl_count_before = guard_before["payment_entry_gl_count"]
    doc.payment_entry_gl_count_after = guard_after["payment_entry_gl_count"]
    doc.submitted_journal_entry_count_today = guard_before["submitted_journal_entry_count_today"]
    doc.sales_invoice_count_today = guard_before["sales_invoice_count_today"]
    doc.purchase_invoice_count_today = guard_before["purchase_invoice_count_today"]
    doc.live_enabled_policy_count = guard_before["live_enabled_policy_count"]
    doc.required_acknowledgement = PREVIEW_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    create_preview_lines(doc, preview_lines)

    guard_after = guardrails()
    result["guardrails_after"] = guard_after
    frappe.db.set_value(
        PREVIEW_DOCTYPE,
        doc.name,
        {
            "payment_entry_count_after": guard_after["payment_entry_count"],
            "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
            "summary_json": safe_json(result),
        },
        update_modified=False,
    )
    frappe.db.commit()
    result["created"] = True
    result["preview"] = doc.name
    result["preview_id"] = doc.preview_id
    return result


@frappe.whitelist()
def cancel_real_remittance_pe_preview(preview, reason=None):
    assert_action("cancel_real_remittance_pe_preview")
    if not frappe.db.exists(PREVIEW_DOCTYPE, preview):
        frappe.throw(_("Preview not found: {0}").format(preview))
    doc = frappe.get_doc(PREVIEW_DOCTYPE, preview)
    if doc.status == "Cancelled":
        return {"preview": preview, "status": "Cancelled", "note": "Already cancelled."}
    frappe.db.set_value(
        PREVIEW_DOCTYPE,
        preview,
        {
            "status": "Cancelled",
            "preview_approved_for_adapter_phase": 0,
            "real_posting_allowed": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 6B preview cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(
        f"""
        UPDATE `tab{LINE_DOCTYPE}`
        SET preview_status = 'Cancelled'
        WHERE preview = %(preview)s
        """,
        {"preview": preview},
    )
    frappe.db.commit()
    return {
        "preview": preview,
        "status": "Cancelled",
        "note": "Preview cancelled only. No accounting movement occurred.",
    }


@frappe.whitelist()
def quick_real_remittance_pe_preview_summary(limit=20):
    previews = frappe.get_all(
        PREVIEW_DOCTYPE,
        fields=[
            "name",
            "preview_id",
            "status",
            "preview_status",
            "preview_score",
            "preview_approved_for_adapter_phase",
            "real_posting_allowed",
            "eligible_line_count",
            "blocked_line_count",
            "review_line_count",
            "eligible_amount",
            "would_create_payment_entry_count",
            "actual_payment_entry_created_count",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    lines = frappe.get_all(
        LINE_DOCTYPE,
        fields=[
            "name",
            "preview",
            "source_remittance_line",
            "classification",
            "preview_status",
            "block_reason",
            "sales_invoice",
            "allocatable_amount",
            "would_create_payment_entry",
            "payment_entry_created",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "previews": previews,
        "lines": lines,
        "required_acknowledgement": PREVIEW_ACK,
        "guardrails": guardrails(),
        "config": config_state(),
        "note": "Phase 6B preview summary only. No Payment Entry or GL is created.",
    }


def execute_preview_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("p.status = %(status)s")
        params["status"] = filters.get("status")
    if filters.get("from_date"):
        conditions.append("DATE(p.checked_on) >= %(from_date)s")
        params["from_date"] = filters.get("from_date")
    if filters.get("to_date"):
        conditions.append("DATE(p.checked_on) <= %(to_date)s")
        params["to_date"] = filters.get("to_date")
    columns = [
        {"fieldname": "preview", "label": _("Preview"), "fieldtype": "Link", "options": PREVIEW_DOCTYPE, "width": 220},
        {"fieldname": "preview_id", "label": _("Preview ID"), "fieldtype": "Data", "width": 360},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "preview_status", "label": _("Preview Status"), "fieldtype": "Data", "width": 240},
        {"fieldname": "eligible_line_count", "label": _("Eligible"), "fieldtype": "Int", "width": 90},
        {"fieldname": "blocked_line_count", "label": _("Blocked"), "fieldtype": "Int", "width": 90},
        {"fieldname": "review_line_count", "label": _("Review"), "fieldtype": "Int", "width": 90},
        {"fieldname": "eligible_amount", "label": _("Eligible Amount"), "fieldtype": "Currency", "options": "currency", "width": 140},
        {"fieldname": "would_create_payment_entry_count", "label": _("Would Create PE"), "fieldtype": "Int", "width": 130},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE Created"), "fieldtype": "Int", "width": 140},
        {"fieldname": "real_posting_allowed", "label": _("Real Posting Allowed"), "fieldtype": "Check", "width": 150},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            p.name AS preview,
            p.preview_id,
            p.status,
            p.preview_status,
            p.eligible_line_count,
            p.blocked_line_count,
            p.review_line_count,
            p.eligible_amount,
            p.would_create_payment_entry_count,
            p.actual_payment_entry_created_count,
            p.real_posting_allowed,
            p.checked_on,
            %(currency)s AS currency
        FROM `tab{PREVIEW_DOCTYPE}` p
        {build_where(conditions)}
        ORDER BY p.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.preview_id for row in data[:20]],
            "datasets": [
                {"name": "Eligible", "values": [int(row.eligible_line_count or 0) for row in data[:20]]},
                {"name": "Blocked", "values": [int(row.blocked_line_count or 0) for row in data[:20]]},
                {"name": "Actual PE Created", "values": [int(row.actual_payment_entry_created_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Previews"), "datatype": "Int"},
        {"value": sum(int(row.eligible_line_count or 0) for row in data), "indicator": "Green", "label": _("Eligible Lines"), "datatype": "Int"},
        {"value": sum(int(row.blocked_line_count or 0) for row in data), "indicator": "Orange", "label": _("Blocked Lines"), "datatype": "Int"},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PE Created"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_line_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    for fieldname in ["preview", "preview_status", "classification"]:
        if filters.get(fieldname):
            conditions.append(f"l.{fieldname} = %({fieldname})s")
            params[fieldname] = filters.get(fieldname)
    columns = [
        {"fieldname": "line", "label": _("Preview Line"), "fieldtype": "Link", "options": LINE_DOCTYPE, "width": 220},
        {"fieldname": "preview", "label": _("Preview"), "fieldtype": "Link", "options": PREVIEW_DOCTYPE, "width": 220},
        {"fieldname": "source_remittance_line", "label": _("Remittance Line"), "fieldtype": "Link", "options": "NDIS Remittance Import Line", "width": 220},
        {"fieldname": "classification", "label": _("Classification"), "fieldtype": "Data", "width": 220},
        {"fieldname": "preview_status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "sales_invoice", "label": _("Sales Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 170},
        {"fieldname": "source_amount", "label": _("Source Amount"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "allocatable_amount", "label": _("Allocatable"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "invoice_outstanding_amount", "label": _("Outstanding"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "would_create_payment_entry", "label": _("Would Create PE"), "fieldtype": "Check", "width": 120},
        {"fieldname": "payment_entry_created", "label": _("PE Created"), "fieldtype": "Check", "width": 100},
        {"fieldname": "block_reason", "label": _("Reason"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            l.name AS line,
            l.preview,
            l.source_remittance_line,
            l.classification,
            l.preview_status,
            l.sales_invoice,
            l.source_amount,
            l.allocatable_amount,
            l.invoice_outstanding_amount,
            l.would_create_payment_entry,
            l.payment_entry_created,
            l.block_reason,
            %(currency)s AS currency
        FROM `tab{LINE_DOCTYPE}` l
        {build_where(conditions)}
        ORDER BY l.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart_map = {}
    for row in data:
        key = row.classification or "Unknown"
        chart_map[key] = chart_map.get(key, 0) + 1
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Lines", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Lines"), "datatype": "Int"},
        {"value": len([row for row in data if row.preview_status == "Eligible"]), "indicator": "Green", "label": _("Eligible"), "datatype": "Int"},
        {"value": len([row for row in data if row.preview_status == "Blocked"]), "indicator": "Orange", "label": _("Blocked"), "datatype": "Int"},
        {"value": sum(int(row.payment_entry_created or 0) for row in data), "indicator": "Red", "label": _("Actual PE Created"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_exception_report(filters=None):
    filters = frappe._dict(filters or {})
    filters["preview_status"] = filters.get("preview_status") or "Blocked"
    return execute_line_report(filters)


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
