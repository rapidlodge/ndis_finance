import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


ADAPTER_ACK = "I_CONFIRM_PHASE8C_CONTROLLED_PRODUCTION_BATCH_ADAPTER_HARD_BLOCK_NO_POSTING"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
PREVIEW_DOCTYPE = "NDIS Controlled Production Batch Preview"
PREVIEW_LINE_DOCTYPE = "NDIS Controlled Production Batch Preview Line"
RUN_DOCTYPE = "NDIS Controlled Production Batch Adapter Run"
LINE_DOCTYPE = "NDIS Controlled Production Batch Adapter Line"


def make_adapter_run_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-CTRL-PROD-BATCH-ADAPTER-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_preview():
    rows = frappe.get_all(
        PREVIEW_DOCTYPE,
        filters={
            "status": "Previewed",
            "preview_approved_for_adapter_phase": 1,
            "ready_for_hard_block_adapter": 1,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
        },
        fields=[
            "name",
            "preview_id",
            "design_gate",
            "phase7h_freeze",
            "source_run",
            "company",
            "customer",
            "bank_account",
            "receivable_account",
            "max_batch_lines",
            "max_batch_amount",
            "eligible_line_count",
            "blocked_line_count",
            "would_create_payment_entry_count",
            "preview_amount",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return frappe._dict(rows[0]) if rows else None


def get_preview_lines(preview):
    return frappe.get_all(
        PREVIEW_LINE_DOCTYPE,
        filters={"preview": preview},
        fields=[
            "name",
            "line_no",
            "line_status",
            "source_run",
            "sales_invoice",
            "claim_line",
            "remittance_line",
            "invoice_outstanding",
            "allocatable_amount",
            "shortfall_amount",
            "block_reason",
        ],
        order_by="line_no asc, creation asc",
    )


@frappe.whitelist()
def create_controlled_production_batch_payment_entry_live(*args, **kwargs):
    frappe.throw(
        _(
            "Phase 8C hard block: controlled production batch Payment Entry live creation is intentionally disabled. "
            "This adapter may calculate would-create evidence only."
        ),
        frappe.ValidationError,
    )


def verify_direct_live_creation_block():
    try:
        create_controlled_production_batch_payment_entry_live()
    except frappe.ValidationError:
        return 1
    return 0


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


def validate_preview_line(line, preview):
    reasons = []
    if line.line_status != "Eligible":
        reasons.append(f"Preview line is not eligible: {line.line_status}.")

    if not line.sales_invoice or not frappe.db.exists("Sales Invoice", line.sales_invoice):
        reasons.append("Sales Invoice missing.")
        return reasons

    si = frappe.get_doc("Sales Invoice", line.sales_invoice)
    if si.docstatus != 1:
        reasons.append("Sales Invoice is not submitted.")
    if si.company != preview.company:
        reasons.append("Sales Invoice company mismatch.")
    if flt(si.outstanding_amount or 0) <= 0:
        reasons.append("Sales Invoice has no outstanding amount.")
    if flt(line.allocatable_amount or 0) <= 0:
        reasons.append("Allocatable amount is not positive.")
    if flt(line.allocatable_amount or 0) > flt(si.outstanding_amount or 0):
        reasons.append("Allocatable amount exceeds invoice outstanding.")
    if active_payment_entry_for_invoice(si.name):
        reasons.append("Active Payment Entry already exists for invoice.")
    return reasons


def build_adapter_lines(preview):
    adapter_lines = []
    for line in get_preview_lines(preview.name):
        reasons = validate_preview_line(line, preview)
        is_hard_blocked = line.line_status == "Eligible" and not reasons
        adapter_lines.append(
            {
                "preview_line": line.name,
                "line_no": int(line.line_no or 0),
                "line_status": "Hard Blocked" if is_hard_blocked else "Validation Blocked",
                "block_reason": (
                    "Would create Payment Entry reference, but Phase 8C hard-block prevents live creation."
                    if is_hard_blocked
                    else "; ".join(reasons or [line.block_reason or "Preview line is not eligible."])
                ),
                "source_run": line.source_run,
                "sales_invoice": line.sales_invoice,
                "claim_line": line.claim_line,
                "remittance_line": line.remittance_line,
                "invoice_outstanding": flt(line.invoice_outstanding or 0),
                "allocatable_amount": flt(line.allocatable_amount or 0),
                "shortfall_amount": flt(line.shortfall_amount or 0),
                "would_create_reference": 1 if is_hard_blocked else 0,
                "would_create_payment_entry": 1 if is_hard_blocked else 0,
                "hard_block_applied": 1 if is_hard_blocked else 0,
            }
        )
    return adapter_lines


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


def create_adapter_line(adapter_run, preview, row):
    doc = frappe.new_doc(LINE_DOCTYPE)
    doc.adapter_run = adapter_run
    doc.line_no = row["line_no"]
    doc.line_label = f"Phase 8C Adapter Line {row['line_no']}"
    doc.line_status = row["line_status"]
    doc.block_reason = row["block_reason"]
    doc.preview = preview.name
    doc.preview_line = row["preview_line"]
    doc.source_run = row["source_run"]
    doc.sales_invoice = row["sales_invoice"]
    doc.claim_line = row["claim_line"]
    doc.remittance_line = row["remittance_line"]
    doc.invoice_outstanding = row["invoice_outstanding"]
    doc.allocatable_amount = row["allocatable_amount"]
    doc.shortfall_amount = row["shortfall_amount"]
    doc.would_create_reference = row["would_create_reference"]
    doc.would_create_payment_entry = row["would_create_payment_entry"]
    doc.hard_block_applied = row["hard_block_applied"]
    doc.checked_on = now_datetime()
    doc.insert(ignore_permissions=True)


@frappe.whitelist()
def run_controlled_production_batch_adapter(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_controlled_production_batch_adapter")
    preview = latest_preview()
    if not preview:
        frappe.throw(_("No approved Phase 8B controlled production batch preview found."))

    config = config_state()
    guard_before = guardrails()
    ack_ok = acknowledgement == ADAPTER_ACK
    adapter_lines = build_adapter_lines(preview)
    hard_blocked_lines = [row for row in adapter_lines if row["line_status"] == "Hard Blocked"]
    validation_blocked_lines = [row for row in adapter_lines if row["line_status"] == "Validation Blocked"]
    direct_blocked = verify_direct_live_creation_block()
    would_create_count = 1 if hard_blocked_lines else 0
    would_create_amount = flt(sum(flt(row["allocatable_amount"] or 0) for row in hard_blocked_lines), 2)
    would_reference_count = len([row for row in hard_blocked_lines if int(row["would_create_reference"] or 0)])

    items = []
    add_item(items, "Blocker" if config["production_mode"] else "Pass", "Critical" if config["production_mode"] else "Low", "Site Config", "production_mode", "Production Mode", "Production mode is enabled." if config["production_mode"] else "Production mode remains disabled.")
    add_item(items, "Blocker" if config["live_pe_enabled"] else "Pass", "Critical" if config["live_pe_enabled"] else "Low", "Site Config", "live_pe_posting", "Live PE Posting", "Live PE posting config is enabled." if config["live_pe_enabled"] else "Live PE posting remains disabled.")
    if guard_before["production_batch_enabled_policy_count"] == 0 and guard_before["live_posting_allowed_policy_count"] == 0:
        add_item(items, "Pass", "Low", "Policy Safety", "live_policies", "Live Policies", "No controlled production live-enabled policies.")
    else:
        add_item(items, "Blocker", "Critical", "Policy Safety", "live_policies", "Live Policies", "Live-enabled policy found.")
    add_item(items, "Pass" if direct_blocked else "Blocker", "Low" if direct_blocked else "Critical", "Adapter Safety", "direct_live_creation_block", "Direct Live Creation Block", "Direct live PE creation is hard-blocked." if direct_blocked else "Direct live PE creation was not blocked.")
    add_item(items, "Pass" if hard_blocked_lines else "Warning", "Low" if hard_blocked_lines else "Medium", "Adapter Evidence", "would_create_lines", "Would Create Lines", f"{len(hard_blocked_lines)} line(s) would create PE references, amount {would_create_amount}." if hard_blocked_lines else "No adapter lines would create PE references.")
    add_item(items, "Pass" if would_create_amount <= flt(preview.max_batch_amount or 0) and len(hard_blocked_lines) <= int(preview.max_batch_lines or 0) else "Blocker", "Low", "Batch Cap", "batch_cap", "Batch Cap", f"Would-create result within cap: {len(hard_blocked_lines)} lines / {would_create_amount}.")
    add_item(items, "Pass" if ack_ok else "Warning", "Low" if ack_ok else "Medium", "Acknowledgement", "adapter_ack", "Adapter Ack", "Exact acknowledgement supplied." if ack_ok else f"Required acknowledgement not supplied: {ADAPTER_ACK}")

    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    approved = int(ack_ok and item_summary["blocker_count"] == 0 and direct_blocked)

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Hard Blocked" if approved else "Needs Review",
        "adapter_status": "Ready For Activation Gate" if approved and hard_blocked_lines else "Hard Blocked With Exceptions",
        "adapter_approved_for_activation_gate": approved,
        "ready_for_activation_gate": approved,
        "direct_live_creation_blocked": direct_blocked,
        "production_batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "preview": preview.name,
        "design_gate": preview.design_gate,
        "phase7h_freeze": preview.phase7h_freeze,
        "source_run": preview.source_run,
        "company": preview.company,
        "customer": preview.customer,
        "bank_account": preview.bank_account,
        "receivable_account": preview.receivable_account,
        "max_batch_lines": int(preview.max_batch_lines or 0),
        "max_batch_amount": flt(preview.max_batch_amount or 0),
        "source_preview_line_count": len(adapter_lines),
        "eligible_preview_line_count": len([row for row in adapter_lines if row["would_create_reference"]]),
        "blocked_preview_line_count": len(validation_blocked_lines),
        "would_create_payment_entry_count": would_create_count,
        "would_create_payment_entry_amount": would_create_amount,
        "would_create_reference_count": would_reference_count,
        "hard_blocked_line_count": len(hard_blocked_lines),
        "validation_blocked_line_count": len(validation_blocked_lines),
        "actual_payment_entry_created_count": 0,
        "actual_gl_created_count": 0,
        "adapter_score": score,
        **item_summary,
        "items": items,
        "lines": adapter_lines,
        "guardrails_before": guard_before,
        "guardrails_after": guardrails(),
        "config": config,
        "required_acknowledgement": ADAPTER_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 8C is hard-block adapter only. It proves would-create evidence but creates no Payment Entry or GL.",
    }

    if int(dry_run or 0):
        return result

    doc = frappe.new_doc(RUN_DOCTYPE)
    doc.adapter_run_id = make_adapter_run_id()
    for fieldname in [
        "status",
        "adapter_status",
        "adapter_approved_for_activation_gate",
        "ready_for_activation_gate",
        "direct_live_creation_blocked",
        "production_batch_posting_allowed",
        "real_posting_allowed",
        "preview",
        "design_gate",
        "phase7h_freeze",
        "source_run",
        "company",
        "customer",
        "bank_account",
        "receivable_account",
        "max_batch_lines",
        "max_batch_amount",
        "source_preview_line_count",
        "eligible_preview_line_count",
        "blocked_preview_line_count",
        "would_create_payment_entry_count",
        "would_create_payment_entry_amount",
        "would_create_reference_count",
        "hard_blocked_line_count",
        "validation_blocked_line_count",
        "actual_payment_entry_created_count",
        "actual_gl_created_count",
        "adapter_score",
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
    doc.required_acknowledgement = ADAPTER_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    for row in adapter_lines:
        create_adapter_line(doc.name, preview, row)

    guard_after = guardrails()
    frappe.db.set_value(
        RUN_DOCTYPE,
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
    result["adapter_run"] = doc.name
    result["adapter_run_id"] = doc.adapter_run_id
    result["guardrails_after"] = guard_after
    return result


@frappe.whitelist()
def cancel_controlled_production_batch_adapter(adapter_run, reason=None):
    assert_action("cancel_controlled_production_batch_adapter")
    if not frappe.db.exists(RUN_DOCTYPE, adapter_run):
        frappe.throw(_("Adapter run not found: {0}").format(adapter_run))
    doc = frappe.get_doc(RUN_DOCTYPE, adapter_run)
    if doc.status == "Cancelled":
        return {"adapter_run": adapter_run, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.adapter_approved_for_activation_gate or 0):
        frappe.throw(_("Cannot cancel an approved adapter run. Create a superseding adapter run instead."))
    frappe.db.set_value(
        RUN_DOCTYPE,
        adapter_run,
        {
            "status": "Cancelled",
            "adapter_status": "Cancelled",
            "adapter_approved_for_activation_gate": 0,
            "ready_for_activation_gate": 0,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 8C adapter audit cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{LINE_DOCTYPE}` SET line_status = 'Cancelled' WHERE adapter_run = %(adapter_run)s", {"adapter_run": adapter_run})
    frappe.db.commit()
    return {"adapter_run": adapter_run, "status": "Cancelled", "note": "Adapter audit record cancelled only. No accounting movement occurred."}


@frappe.whitelist()
def quick_controlled_production_batch_adapter_summary(limit=20):
    runs = frappe.get_all(
        RUN_DOCTYPE,
        fields=[
            "name",
            "adapter_run_id",
            "status",
            "adapter_status",
            "adapter_approved_for_activation_gate",
            "ready_for_activation_gate",
            "direct_live_creation_blocked",
            "production_batch_posting_allowed",
            "real_posting_allowed",
            "preview",
            "company",
            "customer",
            "source_preview_line_count",
            "eligible_preview_line_count",
            "would_create_payment_entry_count",
            "would_create_payment_entry_amount",
            "hard_blocked_line_count",
            "validation_blocked_line_count",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
            "adapter_score",
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
            "adapter_run",
            "line_no",
            "line_status",
            "sales_invoice",
            "block_reason",
            "allocatable_amount",
            "would_create_reference",
            "would_create_payment_entry",
            "hard_block_applied",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "runs": runs,
        "lines": lines,
        "required_acknowledgement": ADAPTER_ACK,
        "guardrails": guardrails(),
        "config": config_state(),
        "note": "Phase 8C adapter summary. Hard-block adapter only; no accounting movement.",
    }


def execute_adapter_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("a.status = %(status)s")
        params["status"] = filters.get("status")

    data = frappe.db.sql(
        f"""
        SELECT
            a.name AS adapter_run, a.adapter_run_id, a.status, a.adapter_status,
            a.adapter_approved_for_activation_gate, a.ready_for_activation_gate,
            a.direct_live_creation_blocked, a.production_batch_posting_allowed,
            a.real_posting_allowed, a.preview, a.company,
            a.eligible_preview_line_count, a.would_create_payment_entry_count,
            a.would_create_payment_entry_amount, a.hard_blocked_line_count,
            a.validation_blocked_line_count, a.actual_payment_entry_created_count,
            a.actual_gl_created_count, a.adapter_score, a.checked_on,
            %(currency)s AS currency
        FROM `tab{RUN_DOCTYPE}` a
        {build_where(conditions)}
        ORDER BY a.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.adapter_run_id for row in data[:20]],
            "datasets": [
                {"name": "Would Create PE", "values": [int(row.would_create_payment_entry_count or 0) for row in data[:20]]},
                {"name": "Actual PE", "values": [int(row.actual_payment_entry_created_count or 0) for row in data[:20]]},
                {"name": "Actual GL", "values": [int(row.actual_gl_created_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Adapter Runs"), "datatype": "Int"},
        {"value": sum(int(row.direct_live_creation_blocked or 0) for row in data), "indicator": "Green", "label": _("Direct Blocks"), "datatype": "Int"},
        {"value": sum(flt(row.would_create_payment_entry_amount or 0) for row in data), "indicator": "Blue", "label": _("Would Create Amount"), "datatype": "Currency", "currency": currency()},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PE"), "datatype": "Int"},
    ]
    return adapter_columns(), data, None, chart, summary


def adapter_columns():
    return [
        {"fieldname": "adapter_run", "label": _("Adapter Run"), "fieldtype": "Link", "options": RUN_DOCTYPE, "width": 220},
        {"fieldname": "adapter_run_id", "label": _("Adapter Run ID"), "fieldtype": "Data", "width": 390},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "adapter_status", "label": _("Adapter Status"), "fieldtype": "Data", "width": 250},
        {"fieldname": "ready_for_activation_gate", "label": _("Ready Gate"), "fieldtype": "Check", "width": 110},
        {"fieldname": "direct_live_creation_blocked", "label": _("Direct Blocked"), "fieldtype": "Check", "width": 130},
        {"fieldname": "eligible_preview_line_count", "label": _("Eligible"), "fieldtype": "Int", "width": 90},
        {"fieldname": "would_create_payment_entry_count", "label": _("Would PE"), "fieldtype": "Int", "width": 100},
        {"fieldname": "would_create_payment_entry_amount", "label": _("Would Amount"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE"), "fieldtype": "Int", "width": 100},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL"), "fieldtype": "Int", "width": 100},
        {"fieldname": "adapter_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_line_report(filters=None):
    return execute_adapter_line_report(filters, exceptions_only=False)


def execute_exception_report(filters=None):
    return execute_adapter_line_report(filters, exceptions_only=True)


def execute_adapter_line_report(filters=None, exceptions_only=False):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("adapter_run"):
        conditions.append("l.adapter_run = %(adapter_run)s")
        params["adapter_run"] = filters.get("adapter_run")
    if filters.get("line_status"):
        conditions.append("l.line_status = %(line_status)s")
        params["line_status"] = filters.get("line_status")
    if exceptions_only:
        conditions.append("l.line_status != 'Hard Blocked'")

    data = frappe.db.sql(
        f"""
        SELECT
            l.name AS line, l.adapter_run, l.line_no, l.line_status,
            l.sales_invoice, l.block_reason, l.invoice_outstanding,
            l.allocatable_amount, l.would_create_reference,
            l.would_create_payment_entry, l.hard_block_applied,
            %(currency)s AS currency
        FROM `tab{LINE_DOCTYPE}` l
        {build_where(conditions)}
        ORDER BY l.adapter_run DESC, l.line_no ASC
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
        {"value": len([row for row in data if row.line_status == "Hard Blocked"]), "indicator": "Green", "label": _("Hard Blocked"), "datatype": "Int"},
        {"value": len([row for row in data if row.line_status == "Validation Blocked"]), "indicator": "Orange", "label": _("Validation Blocked"), "datatype": "Int"},
        {"value": sum(flt(row.allocatable_amount or 0) for row in data), "indicator": "Blue", "label": _("Allocatable"), "datatype": "Currency", "currency": currency()},
    ]
    return line_columns(), data, None, chart, summary


def line_columns():
    return [
        {"fieldname": "line", "label": _("Line"), "fieldtype": "Link", "options": LINE_DOCTYPE, "width": 220},
        {"fieldname": "adapter_run", "label": _("Adapter Run"), "fieldtype": "Link", "options": RUN_DOCTYPE, "width": 220},
        {"fieldname": "line_no", "label": _("Line No"), "fieldtype": "Int", "width": 80},
        {"fieldname": "line_status", "label": _("Status"), "fieldtype": "Data", "width": 140},
        {"fieldname": "sales_invoice", "label": _("Sales Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 170},
        {"fieldname": "block_reason", "label": _("Block Reason"), "fieldtype": "Small Text", "width": 430},
        {"fieldname": "invoice_outstanding", "label": _("Outstanding"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "allocatable_amount", "label": _("Allocatable"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "would_create_reference", "label": _("Would Ref"), "fieldtype": "Check", "width": 90},
        {"fieldname": "would_create_payment_entry", "label": _("Would PE"), "fieldtype": "Check", "width": 90},
        {"fieldname": "hard_block_applied", "label": _("Hard Block"), "fieldtype": "Check", "width": 100},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
