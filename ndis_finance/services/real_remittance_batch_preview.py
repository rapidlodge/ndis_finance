import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


PREVIEW_ACK = "I_CONFIRM_PHASE7B_REAL_REMITTANCE_BATCH_PREVIEW_ONLY_NO_POSTING"
PREVIEW_DOCTYPE = "NDIS Real Remittance Batch Preview"
LINE_DOCTYPE = "NDIS Real Remittance Batch Preview Line"
DESIGN_DOCTYPE = "NDIS Real Remittance Batch Design Gate"


def make_preview_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-REAL-REMITTANCE-BATCH-PREVIEW-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def sales_invoice_today_guardrail_count():
    if frappe.db.has_column("Sales Invoice", "custom_ndis_real_remittance_pe_harness_invoice"):
        return frappe.db.sql(
            """
            SELECT COUNT(*)
            FROM `tabSales Invoice`
            WHERE creation >= %(today)s
            AND IFNULL(custom_ndis_real_remittance_pe_harness_invoice, 0) = 0
            """,
            {"today": today()},
        )[0][0]
    return count_dt("Sales Invoice", {"creation": [">=", today()]})


def guardrails():
    return {
        "payment_entry_count": count_dt("Payment Entry"),
        "payment_entry_gl_count": count_dt("GL Entry", {"voucher_type": "Payment Entry"}),
        "submitted_journal_entry_count_today": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}),
        "sales_invoice_count_today": sales_invoice_today_guardrail_count(),
        "purchase_invoice_count_today": count_dt("Purchase Invoice", {"creation": [">=", today()]}),
        "batch_live_enabled_policy_count": count_dt("NDIS Real Remittance Batch Posting Policy", {"batch_live_enabled": 1}),
        "production_live_enabled_policy_count": count_dt("NDIS PE Production Posting Policy", {"production_posting_enabled": 1}),
    }


def meta_has(doctype, fieldname):
    if not frappe.db.exists("DocType", doctype):
        return False
    return bool(frappe.get_meta(doctype).has_field(fieldname))


def existing_fields(doctype, fields):
    return [field for field in fields if meta_has(doctype, field)]


def latest_design_gate():
    fields = existing_fields(
        DESIGN_DOCTYPE,
        [
            "name",
            "design_gate_id",
            "evidence_freeze",
            "source_harness_run",
            "company",
            "bank_account",
            "receivable_account",
            "allowed_outcomes",
            "excluded_outcomes",
            "max_batch_lines",
            "max_batch_amount",
        ],
    )
    if "name" not in fields:
        fields.insert(0, "name")

    rows = frappe.get_all(
        DESIGN_DOCTYPE,
        filters={
            "status": "Approved",
            "design_approved_for_preview_phase": 1,
            "ready_for_batch_preview": 1,
            "batch_posting_allowed": 0,
            "real_posting_allowed": 0,
        },
        fields=fields,
        order_by="checked_on desc, creation desc",
        limit=1,
    )

    if not rows:
        return None

    row = frappe._dict(rows[0])
    for fieldname in [
        "evidence_freeze",
        "source_harness_run",
        "company",
        "bank_account",
        "receivable_account",
        "allowed_outcomes",
        "excluded_outcomes",
        "max_batch_lines",
        "max_batch_amount",
    ]:
        row.setdefault(fieldname, None)
    return row


def get_doc_if_exists(doctype, name):
    if name and frappe.db.exists(doctype, name):
        return frappe.get_doc(doctype, name)
    return None


def get_first_value(doc, fieldnames):
    if not doc:
        return None
    for fieldname in fieldnames:
        if doc.meta.has_field(fieldname):
            value = doc.get(fieldname)
            if value not in [None, ""]:
                return value
    return None


def normalise_text(value):
    return str(value or "").strip().lower().replace("_", " ")


def is_allowed_outcome(outcome):
    normalised = normalise_text(outcome)
    return normalised in ["paid", "short paid", "short-paid", "shortpaid", "fully paid"]


def get_active_payment_entry_for_invoice(sales_invoice):
    if not sales_invoice:
        return None

    rows = frappe.db.sql(
        """
        SELECT pe.name, pe.docstatus
        FROM `tabPayment Entry Reference` per
        INNER JOIN `tabPayment Entry` pe
            ON pe.name = per.parent
        WHERE per.reference_doctype = 'Sales Invoice'
        AND per.reference_name = %(sales_invoice)s
        AND pe.docstatus != 2
        ORDER BY pe.creation DESC
        LIMIT 1
        """,
        {"sales_invoice": sales_invoice},
        as_dict=True,
    )
    return rows[0] if rows else None


def collect_candidate_names(design):
    names = []
    harness = get_doc_if_exists("NDIS Real Remittance PE Source Harness Run", design.source_harness_run)

    if harness and getattr(harness, "remittance_line", None):
        names.append(harness.remittance_line)

    if meta_has("NDIS Remittance Import Line", "custom_ndis_real_remittance_pe_harness_source"):
        rows = frappe.get_all(
            "NDIS Remittance Import Line",
            filters={"custom_ndis_real_remittance_pe_harness_source": 1},
            fields=["name"],
            order_by="creation desc",
            limit=50,
        )
        names.extend(row.name for row in rows)

    seen = set()
    clean = []
    for name in names:
        if name and name not in seen and frappe.db.exists("NDIS Remittance Import Line", name):
            seen.add(name)
            clean.append(name)
    return clean


def line_to_candidate(line_name, design):
    line = get_doc_if_exists("NDIS Remittance Import Line", line_name)
    harness = get_doc_if_exists("NDIS Real Remittance PE Source Harness Run", design.source_harness_run)
    if not line:
        return None

    sales_invoice = get_first_value(
        line,
        ["sales_invoice", "invoice", "invoice_reference", "sales_invoice_reference", "erpnext_sales_invoice"],
    ) or (getattr(harness, "sales_invoice", None) if harness else None)

    claim_line = get_first_value(
        line,
        ["claim_line", "matched_claim_line", "ndis_claim_line", "claim_line_reference", "reference_claim_line"],
    ) or (getattr(harness, "claim_line", None) if harness else None)

    remittance_import = get_first_value(
        line,
        ["remittance_import", "ndis_remittance_import", "import_reference", "parent"],
    ) or (getattr(harness, "remittance_import", None) if harness else None)

    outcome = get_first_value(line, ["claim_outcome", "outcome", "payment_outcome", "invoice_status", "status"])
    if not outcome and harness and getattr(harness, "remittance_line", None) == line.name:
        outcome = "Paid"

    match_status = get_first_value(line, ["match_status", "matching_status"]) or (
        "Matched" if sales_invoice and claim_line else "Unmatched"
    )

    amount = get_first_value(line, ["paid_amount", "payment_amount", "received_amount", "allocated_amount", "amount"])
    if amount in [None, ""] and harness:
        amount = flt(getattr(harness, "source_amount", 0) or getattr(harness, "invoice_outstanding_before_payment", 0) or 0)

    return {
        "source_doctype": "NDIS Remittance Import Line",
        "source_name": line.name,
        "remittance_import": remittance_import,
        "remittance_line": line.name,
        "claim_line": claim_line,
        "sales_invoice": sales_invoice,
        "outcome": outcome or "Unknown",
        "match_status": match_status or "Unknown",
        "source_amount": flt(amount or 0),
    }


def evaluate_candidate(candidate, design, seen_invoices, running):
    result = dict(candidate)
    result.update(
        {
            "line_status": "Blocked",
            "block_reason": "",
            "would_create_payment_entry": 0,
            "duplicate_invoice": 0,
            "overpayment": 0,
            "cross_company": 0,
            "cap_exceeded": 0,
            "invoice_outstanding": 0,
            "preview_amount": 0,
        }
    )

    reasons = []

    if not is_allowed_outcome(candidate.get("outcome")):
        reasons.append("Outcome is not Paid or Short Paid.")

    if normalise_text(candidate.get("match_status")) not in ["matched", "match", "linked"]:
        reasons.append("Remittance line is not matched.")

    if not candidate.get("sales_invoice"):
        reasons.append("Missing Sales Invoice link.")

    if not candidate.get("claim_line"):
        reasons.append("Missing Claim Line link.")

    si = get_doc_if_exists("Sales Invoice", candidate.get("sales_invoice"))

    if not si:
        reasons.append("Sales Invoice does not exist.")
    else:
        result["invoice_outstanding"] = flt(si.outstanding_amount)
        if si.docstatus != 1:
            reasons.append("Sales Invoice is not submitted.")
        if design.company and si.company != design.company:
            result["cross_company"] = 1
            reasons.append("Sales Invoice company does not match design scope.")
        if flt(si.outstanding_amount) <= 0:
            reasons.append("Sales Invoice has no outstanding balance.")
        active_pe = get_active_payment_entry_for_invoice(si.name)
        if active_pe:
            reasons.append(f"Active Payment Entry already exists for this Sales Invoice: {active_pe.name}.")

    if flt(candidate.get("source_amount") or 0) <= 0:
        reasons.append("Source amount is not positive.")

    if si and flt(candidate.get("source_amount") or 0) > flt(si.outstanding_amount):
        result["overpayment"] = 1
        reasons.append("Source amount exceeds Sales Invoice outstanding amount.")

    if candidate.get("sales_invoice") in seen_invoices:
        result["duplicate_invoice"] = 1
        reasons.append("Duplicate invoice allocation within preview.")

    if reasons:
        result["line_status"] = "Duplicate" if result["duplicate_invoice"] else "Blocked"
        result["block_reason"] = " ".join(reasons)
        return result

    prospective_count = running["eligible_count"] + 1
    prospective_amount = flt(running["eligible_amount"] + flt(candidate.get("source_amount") or 0), 2)

    if prospective_count > int(design.max_batch_lines or 0):
        result["line_status"] = "Cap Blocked"
        result["cap_exceeded"] = 1
        result["block_reason"] = "Max batch line cap exceeded."
        return result

    if prospective_amount > flt(design.max_batch_amount or 0):
        result["line_status"] = "Cap Blocked"
        result["cap_exceeded"] = 1
        result["block_reason"] = "Max batch amount cap exceeded."
        return result

    result["line_status"] = "Eligible"
    result["would_create_payment_entry"] = 1
    result["preview_amount"] = flt(candidate.get("source_amount") or 0)
    running["eligible_count"] = prospective_count
    running["eligible_amount"] = prospective_amount
    seen_invoices.add(candidate.get("sales_invoice"))
    return result


def evaluate_preview(design):
    candidates = []
    for name in collect_candidate_names(design):
        candidate = line_to_candidate(name, design)
        if candidate:
            candidates.append(candidate)

    seen_invoices = set()
    running = {"eligible_count": 0, "eligible_amount": 0}
    return [evaluate_candidate(candidate, design, seen_invoices, running) for candidate in candidates]


def summarise_lines(lines):
    eligible = [line for line in lines if line["line_status"] == "Eligible"]
    blocked = [line for line in lines if line["line_status"] == "Blocked"]
    duplicates = [line for line in lines if line["line_status"] == "Duplicate"]
    cap_blocked = [line for line in lines if line["line_status"] == "Cap Blocked"]
    return {
        "source_line_count": len(lines),
        "eligible_line_count": len(eligible),
        "blocked_line_count": len(blocked),
        "duplicate_line_count": len(duplicates),
        "cap_blocked_line_count": len(cap_blocked),
        "would_create_payment_entry_count": len([line for line in eligible if int(line.get("would_create_payment_entry") or 0)]),
        "preview_amount": flt(sum(flt(line.get("preview_amount") or 0) for line in eligible), 2),
        "blocked_amount": flt(sum(flt(line.get("source_amount") or 0) for line in blocked + duplicates + cap_blocked), 2),
    }


def summarise_score(summary, ack_ok, guard):
    blocker_count = 0
    warning_count = 0
    pass_count = 0
    info_count = 0

    if summary["eligible_line_count"] > 0:
        pass_count += 1
    else:
        blocker_count += 1

    if guard["batch_live_enabled_policy_count"] == 0 and guard["production_live_enabled_policy_count"] == 0:
        pass_count += 1
    else:
        blocker_count += 1

    if ack_ok:
        pass_count += 1
    else:
        warning_count += 1

    if summary["blocked_line_count"] or summary["duplicate_line_count"] or summary["cap_blocked_line_count"]:
        warning_count += 1

    pass_count += 1
    item_count = blocker_count + warning_count + pass_count + info_count
    score = max(0, 100 - blocker_count * 25 - warning_count * 5)
    return {
        "blocker_count": blocker_count,
        "warning_count": warning_count,
        "pass_count": pass_count,
        "info_count": info_count,
        "item_count": item_count,
        "preview_score": score,
    }


def create_preview_line(preview_name, line):
    doc = frappe.new_doc(LINE_DOCTYPE)
    doc.batch_preview = preview_name
    doc.line_status = line.get("line_status")
    doc.line_label = f"{line.get('line_status')} - {line.get('sales_invoice') or line.get('source_name')}"
    doc.source_doctype = line.get("source_doctype")
    doc.source_name = line.get("source_name")
    doc.remittance_import = line.get("remittance_import")
    doc.remittance_line = line.get("remittance_line")
    doc.claim_line = line.get("claim_line")
    doc.sales_invoice = line.get("sales_invoice")
    doc.outcome = line.get("outcome")
    doc.match_status = line.get("match_status")
    doc.block_reason = line.get("block_reason")
    doc.would_create_payment_entry = int(line.get("would_create_payment_entry") or 0)
    doc.duplicate_invoice = int(line.get("duplicate_invoice") or 0)
    doc.overpayment = int(line.get("overpayment") or 0)
    doc.cross_company = int(line.get("cross_company") or 0)
    doc.cap_exceeded = int(line.get("cap_exceeded") or 0)
    doc.invoice_outstanding = flt(line.get("invoice_outstanding") or 0)
    doc.source_amount = flt(line.get("source_amount") or 0)
    doc.preview_amount = flt(line.get("preview_amount") or 0)
    doc.checked_on = now_datetime()
    doc.insert(ignore_permissions=True)


@frappe.whitelist()
def run_real_remittance_batch_preview(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_real_remittance_batch_preview")

    config = config_state()
    guard_before = guardrails()
    ack_ok = acknowledgement == PREVIEW_ACK
    design = latest_design_gate()

    if not design:
        frappe.throw(_("No approved Phase 7A batch design gate found."))

    lines = evaluate_preview(design)
    line_summary = summarise_lines(lines)
    score_summary = summarise_score(line_summary, ack_ok, guard_before)

    preview_approved = int(
        ack_ok
        and score_summary["blocker_count"] == 0
        and line_summary["eligible_line_count"] > 0
        and guard_before["batch_live_enabled_policy_count"] == 0
        and guard_before["production_live_enabled_policy_count"] == 0
    )
    status = "Previewed" if preview_approved else ("Blocked" if score_summary["blocker_count"] else "Needs Review")

    if preview_approved and (
        line_summary["blocked_line_count"]
        or line_summary["duplicate_line_count"]
        or line_summary["cap_blocked_line_count"]
    ):
        preview_status = "Previewed With Exceptions"
    elif preview_approved:
        preview_status = "Ready For Hard-block Adapter"
    elif line_summary["eligible_line_count"] == 0:
        preview_status = "Source Pending"
    else:
        preview_status = "Needs Review"

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": status,
        "preview_status": preview_status,
        "preview_score": score_summary["preview_score"],
        "preview_approved_for_adapter_phase": preview_approved,
        "ready_for_hard_block_adapter": preview_approved,
        "batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "design_gate": design.name,
        "evidence_freeze": design.evidence_freeze,
        "source_harness_run": design.source_harness_run,
        "source_remittance_import": None,
        "company": design.company,
        "max_batch_lines": int(design.max_batch_lines or 0),
        "max_batch_amount": flt(design.max_batch_amount or 0),
        "allowed_outcomes": design.allowed_outcomes,
        "excluded_outcomes": design.excluded_outcomes,
        **line_summary,
        "actual_payment_entry_created_count": 0,
        "actual_gl_created_count": 0,
        **score_summary,
        "lines": lines,
        "guardrails_before": guard_before,
        "guardrails_after": guardrails(),
        "config": config,
        "required_acknowledgement": PREVIEW_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 7B is preview-only. It creates no Payment Entry or GL Entry.",
    }

    if lines:
        result["source_remittance_import"] = lines[0].get("remittance_import")

    if int(dry_run or 0):
        return result

    doc = frappe.new_doc(PREVIEW_DOCTYPE)
    doc.preview_id = make_preview_id()
    doc.status = status
    doc.preview_status = preview_status
    doc.preview_approved_for_adapter_phase = preview_approved
    doc.ready_for_hard_block_adapter = preview_approved
    doc.batch_posting_allowed = 0
    doc.real_posting_allowed = 0
    doc.design_gate = design.name
    doc.evidence_freeze = design.evidence_freeze
    doc.source_harness_run = design.source_harness_run
    doc.source_remittance_import = result["source_remittance_import"]
    doc.company = design.company
    doc.max_batch_lines = int(design.max_batch_lines or 0)
    doc.max_batch_amount = flt(design.max_batch_amount or 0)
    doc.allowed_outcomes = design.allowed_outcomes
    doc.excluded_outcomes = design.excluded_outcomes

    for fieldname in [
        "source_line_count",
        "eligible_line_count",
        "blocked_line_count",
        "duplicate_line_count",
        "cap_blocked_line_count",
        "would_create_payment_entry_count",
        "preview_amount",
        "blocked_amount",
        "actual_payment_entry_created_count",
        "actual_gl_created_count",
        "preview_score",
        "blocker_count",
        "warning_count",
        "pass_count",
        "info_count",
        "item_count",
    ]:
        setattr(doc, fieldname, result.get(fieldname))

    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.payment_entry_count_before = guard_before["payment_entry_count"]
    doc.payment_entry_count_after = guardrails()["payment_entry_count"]
    doc.payment_entry_gl_count_before = guard_before["payment_entry_gl_count"]
    doc.payment_entry_gl_count_after = guardrails()["payment_entry_gl_count"]
    doc.submitted_journal_entry_count_today = guard_before["submitted_journal_entry_count_today"]
    doc.sales_invoice_count_today = guard_before["sales_invoice_count_today"]
    doc.purchase_invoice_count_today = guard_before["purchase_invoice_count_today"]
    doc.batch_live_enabled_policy_count = guard_before["batch_live_enabled_policy_count"]
    doc.production_live_enabled_policy_count = guard_before["production_live_enabled_policy_count"]
    doc.required_acknowledgement = PREVIEW_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    if ack_ok:
        for line in lines:
            create_preview_line(doc.name, line)

    guard_after = guardrails()
    frappe.db.set_value(
        PREVIEW_DOCTYPE,
        doc.name,
        {
            "payment_entry_count_after": guard_after["payment_entry_count"],
            "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
            "summary_json": safe_json({**result, "guardrails_after": guard_after}),
        },
        update_modified=False,
    )
    frappe.db.commit()

    result["created"] = True
    result["batch_preview"] = doc.name
    result["preview_id"] = doc.preview_id
    result["guardrails_after"] = guard_after
    return result


@frappe.whitelist()
def cancel_real_remittance_batch_preview(batch_preview, reason=None):
    assert_action("cancel_real_remittance_batch_preview")

    if not frappe.db.exists(PREVIEW_DOCTYPE, batch_preview):
        frappe.throw(_("Batch preview not found: {0}").format(batch_preview))

    doc = frappe.get_doc(PREVIEW_DOCTYPE, batch_preview)
    if doc.status == "Cancelled":
        return {"batch_preview": batch_preview, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.ready_for_hard_block_adapter or 0):
        frappe.throw(_("Cannot cancel an approved batch preview. Create a superseding preview instead."))

    frappe.db.set_value(
        PREVIEW_DOCTYPE,
        batch_preview,
        {
            "status": "Cancelled",
            "preview_status": "Cancelled",
            "preview_approved_for_adapter_phase": 0,
            "ready_for_hard_block_adapter": 0,
            "batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 7B batch preview cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(
        f"""
        UPDATE `tab{LINE_DOCTYPE}`
        SET line_status = 'Cancelled'
        WHERE batch_preview = %(batch_preview)s
        """,
        {"batch_preview": batch_preview},
    )
    frappe.db.commit()
    return {
        "batch_preview": batch_preview,
        "status": "Cancelled",
        "note": "Batch preview audit record cancelled only. No accounting movement occurred.",
    }


@frappe.whitelist()
def quick_real_remittance_batch_preview_summary(limit=20):
    previews = frappe.get_all(
        PREVIEW_DOCTYPE,
        fields=[
            "name",
            "preview_id",
            "status",
            "preview_status",
            "preview_score",
            "preview_approved_for_adapter_phase",
            "ready_for_hard_block_adapter",
            "batch_posting_allowed",
            "real_posting_allowed",
            "design_gate",
            "company",
            "max_batch_lines",
            "max_batch_amount",
            "source_line_count",
            "eligible_line_count",
            "blocked_line_count",
            "duplicate_line_count",
            "cap_blocked_line_count",
            "would_create_payment_entry_count",
            "preview_amount",
            "blocked_amount",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
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
            "batch_preview",
            "line_status",
            "line_label",
            "source_doctype",
            "source_name",
            "sales_invoice",
            "outcome",
            "match_status",
            "block_reason",
            "would_create_payment_entry",
            "source_amount",
            "preview_amount",
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
        "note": "Phase 7B preview summary. No Payment Entry or GL Entry is created.",
    }


def execute_preview_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("status"):
        conditions.append("p.status = %(status)s")
        params["status"] = filters.status
    if filters.get("from_date"):
        conditions.append("DATE(p.checked_on) >= %(from_date)s")
        params["from_date"] = filters.from_date
    if filters.get("to_date"):
        conditions.append("DATE(p.checked_on) <= %(to_date)s")
        params["to_date"] = filters.to_date

    data = frappe.db.sql(
        f"""
        SELECT
            p.name AS batch_preview,
            p.preview_id,
            p.status,
            p.preview_status,
            p.preview_score,
            p.ready_for_hard_block_adapter,
            p.batch_posting_allowed,
            p.real_posting_allowed,
            p.source_line_count,
            p.eligible_line_count,
            p.blocked_line_count,
            p.duplicate_line_count,
            p.cap_blocked_line_count,
            p.would_create_payment_entry_count,
            p.preview_amount,
            p.actual_payment_entry_created_count,
            p.actual_gl_created_count,
            p.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Real Remittance Batch Preview` p
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
                {"name": "Actual PE", "values": [int(row.actual_payment_entry_created_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Batch Previews"), "datatype": "Int"},
        {"value": sum(int(row.eligible_line_count or 0) for row in data), "indicator": "Green", "label": _("Eligible Lines"), "datatype": "Int"},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PEs Created"), "datatype": "Int"},
        {"value": sum(flt(row.preview_amount or 0) for row in data), "indicator": "Blue", "label": _("Preview Amount"), "datatype": "Currency", "currency": currency()},
    ]
    return preview_columns(), data, None, chart, summary


def preview_columns():
    return [
        {"fieldname": "batch_preview", "label": _("Batch Preview"), "fieldtype": "Link", "options": PREVIEW_DOCTYPE, "width": 220},
        {"fieldname": "preview_id", "label": _("Preview ID"), "fieldtype": "Data", "width": 360},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "preview_status", "label": _("Preview Status"), "fieldtype": "Data", "width": 220},
        {"fieldname": "preview_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "ready_for_hard_block_adapter", "label": _("Ready Adapter"), "fieldtype": "Check", "width": 120},
        {"fieldname": "batch_posting_allowed", "label": _("Batch Posting Allowed"), "fieldtype": "Check", "width": 160},
        {"fieldname": "real_posting_allowed", "label": _("Real Posting Allowed"), "fieldtype": "Check", "width": 150},
        {"fieldname": "source_line_count", "label": _("Source Lines"), "fieldtype": "Int", "width": 110},
        {"fieldname": "eligible_line_count", "label": _("Eligible"), "fieldtype": "Int", "width": 90},
        {"fieldname": "blocked_line_count", "label": _("Blocked"), "fieldtype": "Int", "width": 90},
        {"fieldname": "duplicate_line_count", "label": _("Duplicates"), "fieldtype": "Int", "width": 100},
        {"fieldname": "cap_blocked_line_count", "label": _("Cap Blocked"), "fieldtype": "Int", "width": 110},
        {"fieldname": "would_create_payment_entry_count", "label": _("Would Create PE"), "fieldtype": "Int", "width": 130},
        {"fieldname": "preview_amount", "label": _("Preview Amount"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE"), "fieldtype": "Int", "width": 100},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL"), "fieldtype": "Int", "width": 100},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_line_report(filters=None):
    return execute_line_query(filters, exceptions_only=False)


def execute_exception_report(filters=None):
    return execute_line_query(filters, exceptions_only=True)


def execute_line_query(filters=None, exceptions_only=False):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("batch_preview"):
        conditions.append("l.batch_preview = %(batch_preview)s")
        params["batch_preview"] = filters.batch_preview
    if filters.get("line_status"):
        conditions.append("l.line_status = %(line_status)s")
        params["line_status"] = filters.line_status
    if filters.get("outcome"):
        conditions.append("l.outcome = %(outcome)s")
        params["outcome"] = filters.outcome
    if exceptions_only:
        conditions.append("l.line_status IN ('Blocked', 'Duplicate', 'Cap Blocked')")

    columns = [
        {"fieldname": "line", "label": _("Line"), "fieldtype": "Link", "options": LINE_DOCTYPE, "width": 220},
        {"fieldname": "batch_preview", "label": _("Batch Preview"), "fieldtype": "Link", "options": PREVIEW_DOCTYPE, "width": 220},
        {"fieldname": "line_status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "sales_invoice", "label": _("Sales Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 170},
        {"fieldname": "remittance_line", "label": _("Remittance Line"), "fieldtype": "Link", "options": "NDIS Remittance Import Line", "width": 190},
        {"fieldname": "claim_line", "label": _("Claim Line"), "fieldtype": "Link", "options": "NDIS Claim Line", "width": 160},
        {"fieldname": "outcome", "label": _("Outcome"), "fieldtype": "Data", "width": 120},
        {"fieldname": "match_status", "label": _("Match Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "would_create_payment_entry", "label": _("Would Create PE"), "fieldtype": "Check", "width": 130},
        {"fieldname": "invoice_outstanding", "label": _("Outstanding"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "source_amount", "label": _("Source Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "preview_amount", "label": _("Preview Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "duplicate_invoice", "label": _("Duplicate"), "fieldtype": "Check", "width": 90},
        {"fieldname": "overpayment", "label": _("Overpayment"), "fieldtype": "Check", "width": 100},
        {"fieldname": "cross_company", "label": _("Cross Company"), "fieldtype": "Check", "width": 120},
        {"fieldname": "cap_exceeded", "label": _("Cap Exceeded"), "fieldtype": "Check", "width": 120},
        {"fieldname": "block_reason", "label": _("Block Reason"), "fieldtype": "Small Text", "width": 520},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            l.name AS line,
            l.batch_preview,
            l.line_status,
            l.sales_invoice,
            l.remittance_line,
            l.claim_line,
            l.outcome,
            l.match_status,
            l.would_create_payment_entry,
            l.invoice_outstanding,
            l.source_amount,
            l.preview_amount,
            l.duplicate_invoice,
            l.overpayment,
            l.cross_company,
            l.cap_exceeded,
            l.block_reason,
            l.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Real Remittance Batch Preview Line` l
        {build_where(conditions)}
        ORDER BY
            CASE l.line_status
                WHEN 'Blocked' THEN 1
                WHEN 'Duplicate' THEN 2
                WHEN 'Cap Blocked' THEN 3
                WHEN 'Eligible' THEN 4
                ELSE 5
            END,
            l.creation DESC
        """,
        params,
        as_dict=True,
    )

    chart_map = {}
    for row in data:
        key = row.line_status or "Info"
        chart_map[key] = chart_map.get(key, 0) + 1
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Lines", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Lines"), "datatype": "Int"},
        {"value": len([row for row in data if row.line_status == "Eligible"]), "indicator": "Green", "label": _("Eligible"), "datatype": "Int"},
        {"value": len([row for row in data if row.line_status in ["Blocked", "Duplicate", "Cap Blocked"]]), "indicator": "Orange", "label": _("Exceptions"), "datatype": "Int"},
        {"value": sum(flt(row.preview_amount or 0) for row in data), "indicator": "Blue", "label": _("Preview Amount"), "datatype": "Currency", "currency": currency()},
    ]
    return columns, data, None, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
