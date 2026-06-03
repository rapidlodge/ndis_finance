import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


PREVIEW_ACK = "I_CONFIRM_PHASE8B_CONTROLLED_PRODUCTION_BATCH_PREVIEW_ONLY_NO_POSTING"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
DESIGN_GATE_DOCTYPE = "NDIS Controlled Production Batch Design Gate"
PREVIEW_DOCTYPE = "NDIS Controlled Production Batch Preview"
LINE_DOCTYPE = "NDIS Controlled Production Batch Preview Line"


def make_preview_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-CTRL-PROD-BATCH-PREVIEW-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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
        "production_batch_enabled_policy_count": count_dt(POLICY_DOCTYPE, {"production_batch_enabled": 1}),
        "live_posting_allowed_policy_count": count_dt(POLICY_DOCTYPE, {"live_posting_allowed": 1}),
    }


def latest_design_gate():
    rows = frappe.get_all(
        DESIGN_GATE_DOCTYPE,
        filters={
            "status": "Approved",
            "design_approved_for_preview_phase": 1,
            "ready_for_controlled_production_preview": 1,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
        },
        fields=[
            "name",
            "design_gate_id",
            "phase7h_freeze",
            "phase7e_source_run",
            "company",
            "bank_account",
            "receivable_account",
            "max_batch_lines",
            "max_batch_amount",
            "policy_count",
            "active_policy_count",
            "live_enabled_policy_count",
            "unsafe_policy_count",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return frappe._dict(rows[0]) if rows else None


def policy_rules():
    rows = frappe.get_all(
        POLICY_DOCTYPE,
        fields=[
            "name",
            "policy_id",
            "policy_type",
            "status",
            "allow_paid",
            "allow_short_paid",
            "allow_rejected",
            "allow_unmatched",
            "allow_duplicate_invoice",
            "allow_overpayment",
            "allow_cross_company",
            "max_batch_lines",
            "max_batch_amount",
            "production_batch_enabled",
            "live_posting_allowed",
        ],
    )
    return {
        "allow_paid": any(int(row.allow_paid or 0) for row in rows),
        "allow_short_paid": any(int(row.allow_short_paid or 0) for row in rows),
        "allow_rejected": any(int(row.allow_rejected or 0) for row in rows),
        "allow_unmatched": any(int(row.allow_unmatched or 0) for row in rows),
        "allow_duplicate_invoice": any(int(row.allow_duplicate_invoice or 0) for row in rows),
        "allow_overpayment": any(int(row.allow_overpayment or 0) for row in rows),
        "allow_cross_company": any(int(row.allow_cross_company or 0) for row in rows),
        "live_enabled_policy_count": len([row for row in rows if int(row.production_batch_enabled or 0) or int(row.live_posting_allowed or 0)]),
        "policy_count": len(rows),
        "active_policy_count": len([row for row in rows if row.status == "Active"]),
        "max_batch_lines": min([int(row.max_batch_lines or 3) for row in rows] or [3]),
        "max_batch_amount": min([flt(row.max_batch_amount or 3) for row in rows] or [3]),
    }


def get_source_lines(source_run):
    return frappe.get_all(
        "NDIS Real Remittance Batch Source Harness Line",
        filters={"source_run": source_run, "line_status": "Ready"},
        fields=[
            "name",
            "line_no",
            "sales_invoice",
            "claim_line",
            "remittance_line",
            "expected_outcome",
            "match_status",
            "source_amount",
            "invoice_amount",
            "invoice_outstanding",
            "would_be_eligible_for_batch",
        ],
        order_by="line_no asc, creation asc",
    )


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


def classify_line(line, design_gate, rules, seen_invoices):
    reasons = []
    duplicate = 0
    overpayment = 0
    cross_company = 0
    invoice_total = 0
    outstanding = 0
    allocatable = 0
    shortfall = 0
    outcome = (line.expected_outcome or "").strip()
    outcome_normalized = outcome.lower().replace("-", " ").replace("_", " ")

    if line.sales_invoice in seen_invoices:
        duplicate = 1
        if not rules["allow_duplicate_invoice"]:
            reasons.append("Duplicate invoice in preview source.")

    if not line.sales_invoice or not frappe.db.exists("Sales Invoice", line.sales_invoice):
        reasons.append("Sales Invoice missing.")
        return build_line_result(line, "Blocked", reasons, invoice_total, outstanding, allocatable, shortfall, duplicate, overpayment, cross_company)

    si = frappe.get_doc("Sales Invoice", line.sales_invoice)
    invoice_total = flt(si.rounded_total or si.grand_total or 0)
    outstanding = flt(si.outstanding_amount or line.invoice_outstanding or 0)
    remittance_amount = flt(line.source_amount or 0)

    if si.docstatus != 1:
        reasons.append("Sales Invoice is not submitted.")
    if si.company != design_gate.company:
        cross_company = 1
        if not rules["allow_cross_company"]:
            reasons.append("Cross-company invoice blocked.")
    if outstanding <= 0:
        reasons.append("Sales Invoice has no outstanding amount.")
    if remittance_amount <= 0:
        reasons.append("Remittance amount is not positive.")
    if remittance_amount > outstanding:
        overpayment = 1
        if not rules["allow_overpayment"]:
            reasons.append("Remittance amount exceeds invoice outstanding.")
    if active_payment_entry_for_invoice(si.name):
        reasons.append("Active Payment Entry already exists for this invoice.")
    if "rejected" in outcome_normalized and not rules["allow_rejected"]:
        reasons.append("Rejected outcome blocked by policy.")
    if "unmatched" in outcome_normalized and not rules["allow_unmatched"]:
        reasons.append("Unmatched outcome blocked by policy.")
    if "short" in outcome_normalized and not rules["allow_short_paid"]:
        reasons.append("Short Paid outcome blocked by policy.")
    if outcome_normalized == "paid" and not rules["allow_paid"]:
        reasons.append("Paid outcome blocked by policy.")
    if not int(line.would_be_eligible_for_batch or 0):
        reasons.append("Source line was not marked eligible for batch.")

    if not reasons:
        allocatable = min(remittance_amount, outstanding)
        shortfall = max(outstanding - allocatable, 0)
        status = "Eligible"
    elif duplicate:
        status = "Duplicate"
    else:
        status = "Blocked"

    return build_line_result(line, status, reasons, invoice_total, outstanding, allocatable, shortfall, duplicate, overpayment, cross_company)


def build_line_result(line, status, reasons, invoice_total, outstanding, allocatable, shortfall, duplicate, overpayment, cross_company):
    return {
        "source_line": line.name,
        "line_no": int(line.line_no or 0),
        "sales_invoice": line.sales_invoice,
        "claim_line": line.claim_line,
        "remittance_line": line.remittance_line,
        "expected_outcome": line.expected_outcome,
        "match_status": line.match_status,
        "line_status": status,
        "block_reason": "; ".join(reasons),
        "duplicate_invoice": duplicate,
        "overpayment": overpayment,
        "cross_company": cross_company,
        "invoice_total": flt(invoice_total),
        "invoice_outstanding": flt(outstanding),
        "remittance_amount": flt(line.source_amount or 0),
        "allocatable_amount": flt(allocatable),
        "shortfall_amount": flt(shortfall),
    }


def apply_batch_caps(classified, max_lines, max_amount):
    capped = []
    total = 0
    for row in [r for r in classified if r["line_status"] == "Eligible"]:
        next_amount = flt(row["allocatable_amount"] or 0)
        if len(capped) + 1 > int(max_lines or 0):
            row["line_status"] = "Blocked"
            row["block_reason"] = "Blocked by max batch line cap."
            row["allocatable_amount"] = 0
            continue
        if flt(total + next_amount, 2) > flt(max_amount or 0):
            row["line_status"] = "Blocked"
            row["block_reason"] = "Blocked by max batch amount cap."
            row["allocatable_amount"] = 0
            continue
        capped.append(row)
        total += next_amount
    return classified


def add_item(items, status, severity, category, check_key, check_label, detail):
    items.append({"status": status, "severity": severity, "category": category, "check_key": check_key, "check_label": check_label, "detail": detail})


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


def create_preview_line(preview, source_run, row):
    doc = frappe.new_doc(LINE_DOCTYPE)
    doc.preview = preview
    doc.line_no = row["line_no"]
    doc.line_label = f"Phase 8B Preview Line {row['line_no']}"
    doc.line_status = row["line_status"]
    doc.block_reason = row["block_reason"]
    doc.source_run = source_run
    doc.source_line = row["source_line"]
    doc.sales_invoice = row["sales_invoice"]
    doc.claim_line = row["claim_line"]
    doc.remittance_line = row["remittance_line"]
    doc.expected_outcome = row["expected_outcome"]
    doc.match_status = row["match_status"]
    doc.duplicate_invoice = row["duplicate_invoice"]
    doc.overpayment = row["overpayment"]
    doc.cross_company = row["cross_company"]
    doc.invoice_total = row["invoice_total"]
    doc.invoice_outstanding = row["invoice_outstanding"]
    doc.remittance_amount = row["remittance_amount"]
    doc.allocatable_amount = row["allocatable_amount"]
    doc.shortfall_amount = row["shortfall_amount"]
    doc.checked_on = now_datetime()
    doc.insert(ignore_permissions=True)


@frappe.whitelist()
def run_controlled_production_batch_preview(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_controlled_production_batch_preview")
    design_gate = latest_design_gate()
    if not design_gate:
        frappe.throw(_("No approved Phase 8A controlled production batch design gate found."))

    config = config_state()
    guard_before = guardrails()
    rules = policy_rules()
    ack_ok = acknowledgement == PREVIEW_ACK

    source_lines = get_source_lines(design_gate.phase7e_source_run)
    seen = set()
    classified = []
    for line in source_lines:
        row = classify_line(line, design_gate, rules, seen)
        classified.append(row)
        if line.sales_invoice:
            seen.add(line.sales_invoice)
    classified = apply_batch_caps(classified, design_gate.max_batch_lines, design_gate.max_batch_amount)

    eligible = [row for row in classified if row["line_status"] == "Eligible"]
    blocked = [row for row in classified if row["line_status"] == "Blocked"]
    duplicates = [row for row in classified if row["line_status"] == "Duplicate" or int(row["duplicate_invoice"] or 0)]
    overpayments = [row for row in classified if int(row["overpayment"] or 0)]
    cross_company = [row for row in classified if int(row["cross_company"] or 0)]
    preview_amount = flt(sum(flt(row["allocatable_amount"] or 0) for row in eligible), 2)
    shortfall = flt(sum(flt(row["shortfall_amount"] or 0) for row in eligible), 2)

    items = []
    add_item(items, "Blocker" if config["production_mode"] else "Pass", "Critical" if config["production_mode"] else "Low", "Site Config", "production_mode", "Production Mode", "Production mode is enabled." if config["production_mode"] else "Production mode remains disabled.")
    add_item(items, "Blocker" if config["live_pe_enabled"] else "Pass", "Critical" if config["live_pe_enabled"] else "Low", "Site Config", "live_pe_posting", "Live PE Posting", "Live PE posting config is enabled." if config["live_pe_enabled"] else "Live PE posting remains disabled.")
    if guard_before["production_batch_enabled_policy_count"] == 0 and guard_before["live_posting_allowed_policy_count"] == 0:
        add_item(items, "Pass", "Low", "Policy Safety", "live_policies", "Live Policies", "No controlled production live-enabled policies.")
    else:
        add_item(items, "Blocker", "Critical", "Policy Safety", "live_policies", "Live Policies", "Live-enabled policy found.")
    add_item(items, "Pass" if rules["policy_count"] >= 8 else "Blocker", "Low" if rules["policy_count"] >= 8 else "Critical", "Policy", "policy_count", "Policy Count", f"{rules['policy_count']} policies found.")
    add_item(items, "Pass" if eligible else "Warning", "Low" if eligible else "Medium", "Preview", "eligible_lines", "Eligible Lines", f"{len(eligible)} eligible line(s), amount {preview_amount}." if eligible else "No eligible lines found.")
    add_item(items, "Pass" if preview_amount <= flt(design_gate.max_batch_amount or 0) and len(eligible) <= int(design_gate.max_batch_lines or 0) else "Blocker", "Low", "Cap", "batch_cap", "Batch Cap", f"Preview within cap: {len(eligible)} lines / {preview_amount}.")
    add_item(items, "Pass" if ack_ok else "Warning", "Low" if ack_ok else "Medium", "Acknowledgement", "preview_ack", "Preview Ack", "Exact acknowledgement supplied." if ack_ok else f"Required acknowledgement not supplied: {PREVIEW_ACK}")

    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    approved = int(ack_ok and item_summary["blocker_count"] == 0)
    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Previewed" if approved else "Needs Review",
        "preview_status": "Ready For Hard-block Adapter" if approved and eligible else "Previewed With Exceptions",
        "preview_approved_for_adapter_phase": approved,
        "ready_for_hard_block_adapter": approved,
        "production_batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "design_gate": design_gate.name,
        "phase7h_freeze": design_gate.phase7h_freeze,
        "source_run": design_gate.phase7e_source_run,
        "company": design_gate.company,
        "customer": frappe.db.get_value("NDIS Real Remittance Batch Source Harness Run", design_gate.phase7e_source_run, "customer"),
        "bank_account": design_gate.bank_account,
        "receivable_account": design_gate.receivable_account,
        "max_batch_lines": int(design_gate.max_batch_lines or 0),
        "max_batch_amount": flt(design_gate.max_batch_amount or 0),
        "source_line_count": len(source_lines),
        "eligible_line_count": len(eligible),
        "blocked_line_count": len(blocked),
        "duplicate_line_count": len(duplicates),
        "overpayment_line_count": len(overpayments),
        "cross_company_line_count": len(cross_company),
        "would_create_payment_entry_count": 1 if eligible else 0,
        "preview_amount": preview_amount,
        "shortfall_preserved_amount": shortfall,
        "actual_payment_entry_created_count": 0,
        "actual_gl_created_count": 0,
        "preview_score": score,
        **item_summary,
        "items": items,
        "lines": classified,
        "guardrails_before": guard_before,
        "guardrails_after": guardrails(),
        "config": config,
        "required_acknowledgement": PREVIEW_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 8B is preview-only. It creates preview records only; no Payment Entry or GL is created.",
    }

    if int(dry_run or 0):
        return result

    doc = frappe.new_doc(PREVIEW_DOCTYPE)
    doc.preview_id = make_preview_id()
    for fieldname in [
        "status",
        "preview_status",
        "preview_approved_for_adapter_phase",
        "ready_for_hard_block_adapter",
        "production_batch_posting_allowed",
        "real_posting_allowed",
        "design_gate",
        "phase7h_freeze",
        "source_run",
        "company",
        "customer",
        "bank_account",
        "receivable_account",
        "max_batch_lines",
        "max_batch_amount",
        "source_line_count",
        "eligible_line_count",
        "blocked_line_count",
        "duplicate_line_count",
        "overpayment_line_count",
        "cross_company_line_count",
        "would_create_payment_entry_count",
        "preview_amount",
        "shortfall_preserved_amount",
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
    doc.purchase_invoice_count_today = guard_before["purchase_invoice_count_today"]
    doc.production_batch_enabled_policy_count = guard_before["production_batch_enabled_policy_count"]
    doc.live_posting_allowed_policy_count = guard_before["live_posting_allowed_policy_count"]
    doc.required_acknowledgement = PREVIEW_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    for row in classified:
        create_preview_line(doc.name, design_gate.phase7e_source_run, row)

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
    result["preview"] = doc.name
    result["preview_id"] = doc.preview_id
    result["guardrails_after"] = guard_after
    return result


@frappe.whitelist()
def cancel_controlled_production_batch_preview(preview, reason=None):
    assert_action("cancel_controlled_production_batch_preview")
    if not frappe.db.exists(PREVIEW_DOCTYPE, preview):
        frappe.throw(_("Preview not found: {0}").format(preview))
    doc = frappe.get_doc(PREVIEW_DOCTYPE, preview)
    if doc.status == "Cancelled":
        return {"preview": preview, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.preview_approved_for_adapter_phase or 0):
        frappe.throw(_("Cannot cancel an approved preview. Create a superseding preview instead."))
    frappe.db.set_value(
        PREVIEW_DOCTYPE,
        preview,
        {
            "status": "Cancelled",
            "preview_status": "Cancelled",
            "preview_approved_for_adapter_phase": 0,
            "ready_for_hard_block_adapter": 0,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 8B preview audit cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{LINE_DOCTYPE}` SET line_status = 'Cancelled' WHERE preview = %(preview)s", {"preview": preview})
    frappe.db.commit()
    return {"preview": preview, "status": "Cancelled", "note": "Preview audit record cancelled only. No accounting movement occurred."}


@frappe.whitelist()
def quick_controlled_production_batch_preview_summary(limit=20):
    previews = frappe.get_all(
        PREVIEW_DOCTYPE,
        fields=[
            "name",
            "preview_id",
            "status",
            "preview_status",
            "preview_approved_for_adapter_phase",
            "ready_for_hard_block_adapter",
            "production_batch_posting_allowed",
            "real_posting_allowed",
            "design_gate",
            "source_run",
            "company",
            "customer",
            "eligible_line_count",
            "blocked_line_count",
            "duplicate_line_count",
            "would_create_payment_entry_count",
            "preview_amount",
            "shortfall_preserved_amount",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
            "preview_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    lines = frappe.get_all(
        LINE_DOCTYPE,
        fields=["name", "preview", "line_no", "line_status", "sales_invoice", "expected_outcome", "block_reason", "invoice_outstanding", "allocatable_amount", "shortfall_amount"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "previews": previews,
        "lines": lines,
        "required_acknowledgement": PREVIEW_ACK,
        "guardrails": guardrails(),
        "config": config_state(),
        "note": "Phase 8B preview summary. Preview-only; no accounting movement.",
    }


def execute_preview_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("p.status = %(status)s")
        params["status"] = filters.get("status")
    data = frappe.db.sql(
        f"""
        SELECT
            p.name AS preview, p.preview_id, p.status, p.preview_status,
            p.preview_approved_for_adapter_phase, p.ready_for_hard_block_adapter,
            p.production_batch_posting_allowed, p.real_posting_allowed, p.design_gate,
            p.company, p.eligible_line_count, p.blocked_line_count, p.duplicate_line_count,
            p.would_create_payment_entry_count, p.preview_amount,
            p.actual_payment_entry_created_count, p.actual_gl_created_count,
            p.preview_score, p.checked_on, %(currency)s AS currency
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
                {"name": "Actual PE", "values": [int(row.actual_payment_entry_created_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Previews"), "datatype": "Int"},
        {"value": sum(int(row.eligible_line_count or 0) for row in data), "indicator": "Green", "label": _("Eligible Lines"), "datatype": "Int"},
        {"value": sum(flt(row.preview_amount or 0) for row in data), "indicator": "Blue", "label": _("Preview Amount"), "datatype": "Currency", "currency": currency()},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PE"), "datatype": "Int"},
    ]
    return preview_columns(), data, None, chart, summary


def preview_columns():
    return [
        {"fieldname": "preview", "label": _("Preview"), "fieldtype": "Link", "options": PREVIEW_DOCTYPE, "width": 220},
        {"fieldname": "preview_id", "label": _("Preview ID"), "fieldtype": "Data", "width": 390},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "preview_status", "label": _("Preview Status"), "fieldtype": "Data", "width": 280},
        {"fieldname": "ready_for_hard_block_adapter", "label": _("Ready Adapter"), "fieldtype": "Check", "width": 120},
        {"fieldname": "eligible_line_count", "label": _("Eligible"), "fieldtype": "Int", "width": 90},
        {"fieldname": "blocked_line_count", "label": _("Blocked"), "fieldtype": "Int", "width": 90},
        {"fieldname": "would_create_payment_entry_count", "label": _("Would Create PE"), "fieldtype": "Int", "width": 130},
        {"fieldname": "preview_amount", "label": _("Preview Amount"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE"), "fieldtype": "Int", "width": 100},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL"), "fieldtype": "Int", "width": 100},
        {"fieldname": "preview_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_line_report(filters=None):
    return execute_preview_line_report(filters, exceptions_only=False)


def execute_exception_report(filters=None):
    return execute_preview_line_report(filters, exceptions_only=True)


def execute_preview_line_report(filters=None, exceptions_only=False):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("preview"):
        conditions.append("l.preview = %(preview)s")
        params["preview"] = filters.get("preview")
    if filters.get("line_status"):
        conditions.append("l.line_status = %(line_status)s")
        params["line_status"] = filters.get("line_status")
    if exceptions_only:
        conditions.append("l.line_status != 'Eligible'")
    data = frappe.db.sql(
        f"""
        SELECT
            l.name AS line, l.preview, l.line_no, l.line_status, l.sales_invoice,
            l.expected_outcome, l.block_reason, l.invoice_outstanding,
            l.allocatable_amount, l.shortfall_amount, %(currency)s AS currency
        FROM `tab{LINE_DOCTYPE}` l
        {build_where(conditions)}
        ORDER BY l.preview DESC, l.line_no ASC
        """,
        params,
        as_dict=True,
    )
    columns = [
        {"fieldname": "line", "label": _("Line"), "fieldtype": "Link", "options": LINE_DOCTYPE, "width": 220},
        {"fieldname": "preview", "label": _("Preview"), "fieldtype": "Link", "options": PREVIEW_DOCTYPE, "width": 220},
        {"fieldname": "line_no", "label": _("Line No"), "fieldtype": "Int", "width": 80},
        {"fieldname": "line_status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "sales_invoice", "label": _("Sales Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 170},
        {"fieldname": "expected_outcome", "label": _("Outcome"), "fieldtype": "Data", "width": 120},
        {"fieldname": "block_reason", "label": _("Block Reason"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "invoice_outstanding", "label": _("Outstanding"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "allocatable_amount", "label": _("Allocatable"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "shortfall_amount", "label": _("Shortfall"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    chart = {"data": {"labels": [str(row.line_no) for row in data[:20]], "datasets": [{"name": "Allocatable", "values": [flt(row.allocatable_amount or 0) for row in data[:20]]}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Lines"), "datatype": "Int"},
        {"value": len([row for row in data if row.line_status == "Eligible"]), "indicator": "Green", "label": _("Eligible"), "datatype": "Int"},
        {"value": len([row for row in data if row.line_status != "Eligible"]), "indicator": "Orange", "label": _("Exceptions"), "datatype": "Int"},
        {"value": sum(flt(row.allocatable_amount or 0) for row in data), "indicator": "Blue", "label": _("Allocatable"), "datatype": "Currency", "currency": currency()},
    ]
    return columns, data, None, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
