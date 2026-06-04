import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


POLICY_PREVIEW_ACK = "I_CONFIRM_PHASE9C_PREVIEW_LIMITED_PRODUCTION_BATCH_POLICY_NO_POSTING"


def make_policy_preview_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-LIMITED-PROD-BATCH-POLICY-PREVIEW-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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
        "purchase_invoice_count_today": count_dt("Purchase Invoice", {"creation": [">=", today()]}),
        "production_batch_enabled_policy_count": count_dt("NDIS Controlled Production Batch Posting Policy", {"production_batch_enabled": 1}),
        "live_posting_allowed_policy_count": count_dt("NDIS Controlled Production Batch Posting Policy", {"live_posting_allowed": 1}),
    }


def latest_policy_design():
    rows = frappe.get_all(
        "NDIS Limited Production Batch Policy Design",
        filters={
            "status": "Designed",
            "limited_policy_design_complete": 1,
            "ready_for_limited_policy_preview": 1,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
        },
        fields=[
            "name",
            "policy_design_id",
            "policy_review_gate",
            "phase8g_freeze",
            "rollback_run",
            "smoke_run",
            "activation_gate",
            "adapter_run",
            "preview",
            "design_gate",
            "company",
            "customer",
            "policy_mode",
            "max_batch_lines",
            "max_batch_amount",
            "max_payment_entry_count",
            "allowed_payment_type",
            "allowed_reference_doctype",
            "payment_entry_docstatus_after_rollback",
            "payment_entry_amount",
            "invoice_count",
            "invoice_outstanding_after_rollback_total",
            "payment_entry_gl_count_after_rollback",
            "payment_entry_gl_net_after_rollback",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )

    return rows[0] if rows else None


def existing_completed_preview(policy_design):
    rows = frappe.get_all(
        "NDIS Limited Production Batch Policy Preview",
        filters={
            "policy_design": policy_design,
            "status": "Previewed",
            "limited_policy_preview_complete": 1,
            "ready_for_limited_hard_block_adapter": 1,
        },
        fields=["name", "policy_preview_id"],
        limit=1,
    )

    return rows[0] if rows else None


def meta_has(doctype, fieldname):
    try:
        return frappe.get_meta(doctype).has_field(fieldname)
    except Exception:
        return False


def doc_value(doc, possible_fields, default=None):
    for fieldname in possible_fields:
        if hasattr(doc, fieldname):
            value = getattr(doc, fieldname)
            if value not in (None, ""):
                return value
    return default


def get_source_preview_lines(source_preview):
    if not source_preview:
        return []

    names = frappe.get_all(
        "NDIS Controlled Production Batch Preview Line",
        filters={"preview": source_preview},
        pluck="name",
        order_by="idx asc, creation asc",
    )

    lines = []
    for name in names:
        lines.append(frappe.get_doc("NDIS Controlled Production Batch Preview Line", name))

    return lines


def active_payment_entry_for_invoice(sales_invoice):
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


def normalise_source_line(line):
    line_status = str(doc_value(line, ["line_status", "preview_line_status", "status"], "") or "")
    sales_invoice = doc_value(line, ["sales_invoice", "invoice", "reference_name"], None)
    claim_line = doc_value(line, ["claim_line", "ndis_claim_line"], None)
    remittance_line = doc_value(line, ["remittance_line", "remittance_import_line"], None)

    invoice_outstanding = flt(doc_value(line, ["invoice_outstanding", "outstanding_amount", "sales_invoice_outstanding"], 0) or 0)
    allocatable_amount = flt(doc_value(line, ["allocatable_amount", "allocated_amount", "preview_amount", "paid_amount", "amount"], 0) or 0)
    shortfall_amount = flt(doc_value(line, ["shortfall_amount", "short_paid_amount"], 0) or 0)

    if sales_invoice and frappe.db.exists("Sales Invoice", sales_invoice):
        si_outstanding = flt(frappe.db.get_value("Sales Invoice", sales_invoice, "outstanding_amount") or 0)
        invoice_outstanding = si_outstanding
        if not allocatable_amount:
            allocatable_amount = min(si_outstanding, 1)

    source_block_reason = str(doc_value(line, ["block_reason", "exception_reason", "status_detail"], "") or "")

    is_duplicate = int(doc_value(line, ["duplicate_line", "is_duplicate", "duplicate_detected"], 0) or 0)
    source_marked_blocked = line_status.lower() in ["blocked", "validation blocked", "duplicate", "rejected"]

    block_reason = None

    if source_marked_blocked:
        block_reason = source_block_reason or f"Source line status is {line_status}."

    if not sales_invoice:
        block_reason = "Sales Invoice missing."

    elif not frappe.db.exists("Sales Invoice", sales_invoice):
        block_reason = f"Sales Invoice does not exist: {sales_invoice}"

    elif flt(invoice_outstanding, 2) <= 0:
        block_reason = f"Sales Invoice has no outstanding amount: {sales_invoice}"

    elif flt(allocatable_amount, 2) <= 0:
        block_reason = "Allocatable amount is not positive."

    elif active_payment_entry_for_invoice(sales_invoice):
        pe = active_payment_entry_for_invoice(sales_invoice)
        block_reason = f"Active Payment Entry already exists for invoice {sales_invoice}: {pe.name}"

    if is_duplicate:
        block_reason = block_reason or "Duplicate source line detected."

    return frappe._dict(
        {
            "source_preview_line": line.name,
            "source_line_no": int(getattr(line, "idx", 0) or doc_value(line, ["line_no"], 0) or 0),
            "source_line_status": line_status,
            "sales_invoice": sales_invoice,
            "claim_line": claim_line,
            "remittance_line": remittance_line,
            "invoice_outstanding": flt(invoice_outstanding, 2),
            "allocatable_amount": flt(allocatable_amount, 2),
            "shortfall_amount": flt(shortfall_amount, 2),
            "is_duplicate": is_duplicate,
            "block_reason": block_reason,
        }
    )


def apply_policy_caps(design, source_rows):
    max_lines = int(design.max_batch_lines or 0)
    max_amount = flt(design.max_batch_amount or 0)
    max_pe_count = int(design.max_payment_entry_count or 0)

    result = []
    seen_invoices = set()
    eligible_count = 0
    eligible_amount = 0

    for idx, row in enumerate(source_rows, start=1):
        line = frappe._dict(row.copy())
        line.line_no = idx
        line.line_status = "Eligible"
        line.would_create_payment_entry = 0
        line.would_create_reference = 0
        line.within_line_cap = 0
        line.within_amount_cap = 0
        line.within_payment_entry_cap = 0

        if line.sales_invoice in seen_invoices:
            line.line_status = "Duplicate"
            line.block_reason = "Duplicate Sales Invoice in preview source."
            result.append(line)
            continue

        if line.sales_invoice:
            seen_invoices.add(line.sales_invoice)

        if line.block_reason:
            line.line_status = "Blocked"
            result.append(line)
            continue

        if eligible_count + 1 > max_lines:
            line.line_status = "Blocked"
            line.block_reason = f"Limited policy max batch lines exceeded: {max_lines}"
            result.append(line)
            continue

        if flt(eligible_amount + line.allocatable_amount, 2) > flt(max_amount, 2):
            line.line_status = "Blocked"
            line.block_reason = f"Limited policy max batch amount exceeded: {max_amount}"
            result.append(line)
            continue

        if max_pe_count != 1:
            line.line_status = "Blocked"
            line.block_reason = "Limited policy requires exactly one Payment Entry cap."
            result.append(line)
            continue

        eligible_count += 1
        eligible_amount = flt(eligible_amount + line.allocatable_amount, 2)
        line.would_create_payment_entry = 1
        line.would_create_reference = 1
        line.within_line_cap = 1
        line.within_amount_cap = 1
        line.within_payment_entry_cap = 1
        result.append(line)

    return result


def add_item(items, status, severity, category, check_key, check_label, detail):
    items.append(
        {
            "status": status,
            "severity": severity,
            "category": category,
            "check_key": check_key,
            "check_label": check_label,
            "detail": detail,
        }
    )


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


def validate_preview_source(design, preview_lines, guard):
    issues = []

    if not design:
        issues.append("No completed Phase 9B limited policy design found.")
        return issues

    if existing_completed_preview(design.name):
        issues.append("A completed Phase 9C preview already exists for this Phase 9B policy design.")

    if not design.preview:
        issues.append("Phase 9B design does not link to source controlled production preview.")

    if not preview_lines:
        issues.append("No source preview lines found.")

    if int(design.max_batch_lines or 0) != 3:
        issues.append("Policy max batch lines must be 3.")

    if flt(design.max_batch_amount or 0, 2) != 3:
        issues.append("Policy max batch amount must be 3.00.")

    if int(design.max_payment_entry_count or 0) != 1:
        issues.append("Policy max Payment Entry count must be 1.")

    if int(design.policy_live_enabled or 0):
        issues.append("Policy design is live-enabled, which is not allowed in Phase 9C.")

    if guard["production_batch_enabled_policy_count"] != 0:
        issues.append("Controlled production batch enabled policy count is not zero.")

    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count is not zero.")

    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today is not zero.")

    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today is not zero.")

    return issues


def build_items(design, config, guard, source_issues, summary, ack_ok):
    items = []

    if design:
        add_item(items, "Pass", "Low", "Policy Design", "phase9b_design_exists", "Phase 9B policy design exists", f"Design found: {design.policy_design_id}.")
    else:
        add_item(items, "Blocker", "Critical", "Policy Design", "phase9b_design_exists", "Phase 9B policy design exists", "No completed Phase 9B policy design found.")

    if not source_issues:
        add_item(items, "Pass", "Low", "Source", "preview_source_valid", "Preview source valid", "Source preview and policy caps are valid.")
    else:
        for issue in source_issues:
            add_item(items, "Blocker", "Critical", "Source", "preview_source_valid", "Preview source valid", issue)

    if summary["eligible_line_count"] > 0:
        add_item(items, "Pass", "Low", "Preview", "eligible_lines", "Eligible lines", f"{summary['eligible_line_count']} eligible lines found.")
    else:
        add_item(items, "Blocker", "Critical", "Preview", "eligible_lines", "Eligible lines", "No eligible lines found.")

    if summary["would_create_payment_entry_count"] == 1:
        add_item(items, "Pass", "Low", "Preview", "would_create_pe_count", "Would create PE count", "Preview would create exactly one Payment Entry.")
    else:
        add_item(items, "Blocker", "Critical", "Preview", "would_create_pe_count", "Would create PE count", f"Preview would create {summary['would_create_payment_entry_count']} Payment Entries.")

    if flt(summary["preview_amount"], 2) > 0 and flt(summary["preview_amount"], 2) <= 3:
        add_item(items, "Pass", "Low", "Preview", "preview_amount_cap", "Preview amount cap", f"Preview amount {summary['preview_amount']} is within 3.00 cap.")
    else:
        add_item(items, "Blocker", "Critical", "Preview", "preview_amount_cap", "Preview amount cap", f"Preview amount {summary['preview_amount']} is outside cap.")

    if config["production_mode"]:
        add_item(items, "Blocker", "Critical", "Site Config", "production_mode", "Production mode", "Production mode is enabled.")
    else:
        add_item(items, "Pass", "Low", "Site Config", "production_mode", "Production mode", "Production mode remains disabled.")

    if config["live_pe_enabled"]:
        add_item(items, "Blocker", "Critical", "Site Config", "live_pe_enabled", "Live PE posting config", "Live PE posting config is enabled.")
    else:
        add_item(items, "Pass", "Low", "Site Config", "live_pe_enabled", "Live PE posting config", "Live PE posting config remains disabled.")

    if guard["production_batch_enabled_policy_count"] == 0 and guard["live_posting_allowed_policy_count"] == 0:
        add_item(items, "Pass", "Low", "Policy Safety", "live_policies_zero", "Live policies", "No controlled production live-enabled policies.")
    else:
        add_item(items, "Blocker", "Critical", "Policy Safety", "live_policies_zero", "Live policies", "Live-enabled controlled production policy found.")

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "policy_preview_ack", "Policy preview acknowledgement", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "policy_preview_ack", "Policy preview acknowledgement", f"Required acknowledgement not supplied: {POLICY_PREVIEW_ACK}")

    return items


def summarise_preview_rows(rows):
    eligible = [row for row in rows if row.line_status == "Eligible"]
    blocked = [row for row in rows if row.line_status == "Blocked"]
    duplicate = [row for row in rows if row.line_status == "Duplicate"]

    return {
        "source_line_count": len(rows),
        "eligible_line_count": len(eligible),
        "blocked_line_count": len(blocked),
        "duplicate_line_count": len(duplicate),
        "would_create_payment_entry_count": 1 if eligible else 0,
        "would_create_reference_count": len(eligible),
        "preview_amount": flt(sum(flt(row.allocatable_amount or 0) for row in eligible), 2),
        "shortfall_amount": flt(sum(flt(row.shortfall_amount or 0) for row in rows), 2),
    }


def create_preview_lines(doc, rows):
    for row in rows:
        line = frappe.new_doc("NDIS Limited Production Batch Policy Preview Line")
        line.policy_preview = doc.name
        line.line_no = row.line_no
        line.line_label = f"Phase 9C Preview Line {row.line_no}"
        line.line_status = row.line_status
        line.block_reason = row.block_reason
        line.source_preview = doc.source_preview
        line.source_preview_line = row.source_preview_line
        line.sales_invoice = row.sales_invoice
        line.claim_line = row.claim_line
        line.remittance_line = row.remittance_line
        line.invoice_outstanding = row.invoice_outstanding
        line.allocatable_amount = row.allocatable_amount
        line.shortfall_amount = row.shortfall_amount
        line.would_create_payment_entry = row.would_create_payment_entry
        line.would_create_reference = row.would_create_reference
        line.within_line_cap = row.within_line_cap
        line.within_amount_cap = row.within_amount_cap
        line.within_payment_entry_cap = row.within_payment_entry_cap
        line.policy_live_enabled = 0
        line.checked_on = doc.checked_on
        line.insert(ignore_permissions=True)


@frappe.whitelist()
def run_limited_production_batch_policy_preview(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_limited_production_batch_policy_preview")

    design = latest_policy_design()
    source_lines = get_source_preview_lines(design.preview) if design else []
    normalised_rows = [normalise_source_line(line) for line in source_lines]
    preview_rows = apply_policy_caps(design, normalised_rows) if design else []

    config = config_state()
    guard_before = guardrails()
    ack_ok = acknowledgement == POLICY_PREVIEW_ACK

    preview_summary = summarise_preview_rows(preview_rows)
    source_issues = validate_preview_source(design, source_lines, guard_before)
    items = build_items(design, config, guard_before, source_issues, preview_summary, ack_ok)

    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    complete = int(ack_ok and item_summary["blocker_count"] == 0 and design is not None)

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Previewed" if complete else "Needs Review",
        "policy_preview_status": "Ready For Limited Hard-block Adapter" if complete else "Needs Review",
        "limited_policy_preview_complete": complete,
        "ready_for_limited_hard_block_adapter": complete,
        "production_batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "policy_live_enabled": 0,
        "policy_design": design.name if design else None,
        "policy_review_gate": design.policy_review_gate if design else None,
        "phase8g_freeze": design.phase8g_freeze if design else None,
        "source_preview": design.preview if design else None,
        "activation_gate": design.activation_gate if design else None,
        "adapter_run": design.adapter_run if design else None,
        "design_gate": design.design_gate if design else None,
        "company": design.company if design else None,
        "customer": design.customer if design else None,
        "policy_mode": design.policy_mode if design else "Limited Controlled Production Batch",
        "max_batch_lines": int(design.max_batch_lines or 0) if design else 0,
        "max_batch_amount": flt(design.max_batch_amount or 0) if design else 0,
        "max_payment_entry_count": int(design.max_payment_entry_count or 0) if design else 0,
        "allowed_payment_type": design.allowed_payment_type if design else "Receive",
        "allowed_reference_doctype": design.allowed_reference_doctype if design else "Sales Invoice",
        **preview_summary,
        "actual_payment_entry_created_count": 0,
        "actual_gl_created_count": 0,
        "policy_preview_score": score,
        **item_summary,
        "items": items,
        "preview_rows": preview_rows,
        "guardrails_before": guard_before,
        "guardrails_after": guardrails(),
        "config": config,
        "required_acknowledgement": POLICY_PREVIEW_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 9C creates limited policy preview records only. It creates no Payment Entry and no GL.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["policy_preview_status"] = "Needs Review"
        result["limited_policy_preview_complete"] = 0
        result["ready_for_limited_hard_block_adapter"] = 0
        return result

    doc = frappe.new_doc("NDIS Limited Production Batch Policy Preview")
    doc.policy_preview_id = make_policy_preview_id()
    doc.status = result["status"]
    doc.policy_preview_status = result["policy_preview_status"]
    doc.limited_policy_preview_complete = complete
    doc.ready_for_limited_hard_block_adapter = complete
    doc.production_batch_posting_allowed = 0
    doc.real_posting_allowed = 0
    doc.policy_live_enabled = 0

    for fieldname in [
        "policy_design",
        "policy_review_gate",
        "phase8g_freeze",
        "source_preview",
        "activation_gate",
        "adapter_run",
        "design_gate",
        "company",
        "customer",
        "policy_mode",
        "max_batch_lines",
        "max_batch_amount",
        "max_payment_entry_count",
        "allowed_payment_type",
        "allowed_reference_doctype",
        "source_line_count",
        "eligible_line_count",
        "blocked_line_count",
        "duplicate_line_count",
        "would_create_payment_entry_count",
        "would_create_reference_count",
        "preview_amount",
        "shortfall_amount",
        "actual_payment_entry_created_count",
        "actual_gl_created_count",
        "policy_preview_score",
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
    doc.purchase_invoice_count_today = guard_before["purchase_invoice_count_today"]
    doc.production_batch_enabled_policy_count = guard_before["production_batch_enabled_policy_count"]
    doc.live_posting_allowed_policy_count = guard_before["live_posting_allowed_policy_count"]

    doc.required_acknowledgement = POLICY_PREVIEW_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    if complete:
        create_preview_lines(doc, preview_rows)

    guard_after = guardrails()

    frappe.db.set_value(
        "NDIS Limited Production Batch Policy Preview",
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
    result["policy_preview"] = doc.name
    result["policy_preview_id"] = doc.policy_preview_id
    result["guardrails_after"] = guard_after

    return result


@frappe.whitelist()
def cancel_limited_production_batch_policy_preview(policy_preview, reason=None):
    assert_action("cancel_limited_production_batch_policy_preview")

    if not frappe.db.exists("NDIS Limited Production Batch Policy Preview", policy_preview):
        frappe.throw(_("Policy preview not found: {0}").format(policy_preview))

    doc = frappe.get_doc("NDIS Limited Production Batch Policy Preview", policy_preview)

    if doc.status == "Cancelled":
        return {"policy_preview": policy_preview, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.limited_policy_preview_complete or 0):
        frappe.throw(_("Cannot cancel a completed policy preview. Create a superseding preview instead."))

    frappe.db.set_value(
        "NDIS Limited Production Batch Policy Preview",
        policy_preview,
        {
            "status": "Cancelled",
            "policy_preview_status": "Cancelled",
            "limited_policy_preview_complete": 0,
            "ready_for_limited_hard_block_adapter": 0,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 9C policy preview audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        """
        UPDATE `tabNDIS Limited Production Batch Policy Preview Line`
        SET line_status = 'Cancelled'
        WHERE policy_preview = %(policy_preview)s
        """,
        {"policy_preview": policy_preview},
    )

    frappe.db.commit()

    return {
        "policy_preview": policy_preview,
        "status": "Cancelled",
        "note": "Policy preview audit record cancelled only. No accounting movement occurred.",
    }


@frappe.whitelist()
def quick_limited_production_batch_policy_preview_summary(limit=20):
    previews = frappe.get_all(
        "NDIS Limited Production Batch Policy Preview",
        fields=[
            "name",
            "policy_preview_id",
            "status",
            "policy_preview_status",
            "limited_policy_preview_complete",
            "ready_for_limited_hard_block_adapter",
            "production_batch_posting_allowed",
            "real_posting_allowed",
            "policy_live_enabled",
            "policy_design",
            "source_preview",
            "policy_mode",
            "max_batch_lines",
            "max_batch_amount",
            "max_payment_entry_count",
            "source_line_count",
            "eligible_line_count",
            "blocked_line_count",
            "duplicate_line_count",
            "would_create_payment_entry_count",
            "would_create_reference_count",
            "preview_amount",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
            "policy_preview_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    lines = frappe.get_all(
        "NDIS Limited Production Batch Policy Preview Line",
        fields=[
            "name",
            "policy_preview",
            "line_no",
            "line_status",
            "sales_invoice",
            "allocatable_amount",
            "would_create_payment_entry",
            "would_create_reference",
            "block_reason",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    return {
        "previews": previews,
        "lines": lines,
        "required_acknowledgement": POLICY_PREVIEW_ACK,
        "guardrails": guardrails(),
        "config": config_state(),
        "note": "Phase 9C limited production batch policy preview summary. No live posting enabled.",
    }


def execute_preview_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("status"):
        conditions.append("p.status = %(status)s")
        params["status"] = filters.get("status")

    columns = preview_columns()

    data = frappe.db.sql(
        f"""
        SELECT
            p.name AS policy_preview,
            p.policy_preview_id,
            p.status,
            p.policy_preview_status,
            p.limited_policy_preview_complete,
            p.ready_for_limited_hard_block_adapter,
            p.production_batch_posting_allowed,
            p.real_posting_allowed,
            p.policy_live_enabled,
            p.policy_design,
            p.source_preview,
            p.policy_mode,
            p.max_batch_lines,
            p.max_batch_amount,
            p.max_payment_entry_count,
            p.source_line_count,
            p.eligible_line_count,
            p.blocked_line_count,
            p.duplicate_line_count,
            p.would_create_payment_entry_count,
            p.would_create_reference_count,
            p.preview_amount,
            p.actual_payment_entry_created_count,
            p.actual_gl_created_count,
            p.policy_preview_score,
            p.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Limited Production Batch Policy Preview` p
        {build_where(conditions)}
        ORDER BY p.creation DESC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.policy_preview_id for row in data[:20]],
            "datasets": [
                {"name": "Eligible", "values": [int(row.eligible_line_count or 0) for row in data[:20]]},
                {"name": "Blocked", "values": [int(row.blocked_line_count or 0) for row in data[:20]]},
                {"name": "Actual PE", "values": [int(row.actual_payment_entry_created_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Policy Previews"), "datatype": "Int"},
        {"value": sum(int(row.limited_policy_preview_complete or 0) for row in data), "indicator": "Green", "label": _("Previewed"), "datatype": "Int"},
        {"value": sum(flt(row.preview_amount or 0) for row in data), "indicator": "Blue", "label": _("Preview Amount"), "datatype": "Currency", "currency": currency()},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PE"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def preview_columns():
    return [
        {"fieldname": "policy_preview", "label": _("Policy Preview"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Policy Preview", "width": 220},
        {"fieldname": "policy_preview_id", "label": _("Policy Preview ID"), "fieldtype": "Data", "width": 430},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "policy_preview_status", "label": _("Preview Status"), "fieldtype": "Data", "width": 260},
        {"fieldname": "ready_for_limited_hard_block_adapter", "label": _("Ready Adapter"), "fieldtype": "Check", "width": 120},
        {"fieldname": "source_line_count", "label": _("Source Lines"), "fieldtype": "Int", "width": 100},
        {"fieldname": "eligible_line_count", "label": _("Eligible"), "fieldtype": "Int", "width": 90},
        {"fieldname": "blocked_line_count", "label": _("Blocked"), "fieldtype": "Int", "width": 90},
        {"fieldname": "would_create_payment_entry_count", "label": _("Would Create PE"), "fieldtype": "Int", "width": 120},
        {"fieldname": "preview_amount", "label": _("Preview Amount"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "policy_live_enabled", "label": _("Live Enabled"), "fieldtype": "Check", "width": 110},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "policy_preview_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_line_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("policy_preview"):
        conditions.append("l.policy_preview = %(policy_preview)s")
        params["policy_preview"] = filters.get("policy_preview")

    if filters.get("line_status"):
        conditions.append("l.line_status = %(line_status)s")
        params["line_status"] = filters.get("line_status")

    columns = [
        {"fieldname": "line", "label": _("Line"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Policy Preview Line", "width": 220},
        {"fieldname": "policy_preview", "label": _("Policy Preview"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Policy Preview", "width": 220},
        {"fieldname": "line_no", "label": _("Line No"), "fieldtype": "Int", "width": 80},
        {"fieldname": "line_status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "sales_invoice", "label": _("Sales Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 170},
        {"fieldname": "invoice_outstanding", "label": _("Outstanding"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "allocatable_amount", "label": _("Allocatable"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "would_create_payment_entry", "label": _("Would Create PE"), "fieldtype": "Check", "width": 120},
        {"fieldname": "would_create_reference", "label": _("Would Create Ref"), "fieldtype": "Check", "width": 120},
        {"fieldname": "block_reason", "label": _("Block Reason"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            l.name AS line,
            l.policy_preview,
            l.line_no,
            l.line_status,
            l.sales_invoice,
            l.invoice_outstanding,
            l.allocatable_amount,
            l.would_create_payment_entry,
            l.would_create_reference,
            l.block_reason,
            l.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Limited Production Batch Policy Preview Line` l
        {build_where(conditions)}
        ORDER BY l.policy_preview DESC, l.line_no ASC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [str(row.line_no) for row in data[:20]],
            "datasets": [{"name": "Allocatable", "values": [flt(row.allocatable_amount or 0) for row in data[:20]]}],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Lines"), "datatype": "Int"},
        {"value": len([row for row in data if row.line_status == "Eligible"]), "indicator": "Green", "label": _("Eligible"), "datatype": "Int"},
        {"value": sum(flt(row.allocatable_amount or 0) for row in data if row.line_status == "Eligible"), "indicator": "Blue", "label": _("Eligible Amount"), "datatype": "Currency", "currency": currency()},
    ]

    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_preview_report(filters)

    guard = guardrails()

    summary.append({"value": guard["payment_entry_count"], "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"})
    summary.append({"value": guard["payment_entry_gl_count"], "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"})
    summary.append({"value": guard["submitted_journal_entry_count_today"], "indicator": "Red", "label": _("Submitted JE Today"), "datatype": "Int"})
    summary.append({"value": guard["purchase_invoice_count_today"], "indicator": "Red", "label": _("Purchase Invoice Today"), "datatype": "Int"})
    summary.append({"value": guard["production_batch_enabled_policy_count"], "indicator": "Red", "label": _("Production Batch Enabled Policies"), "datatype": "Int"})
    summary.append({"value": guard["live_posting_allowed_policy_count"], "indicator": "Red", "label": _("Live Posting Allowed Policies"), "datatype": "Int"})

    return columns, data, message, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
