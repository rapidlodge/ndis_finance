import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


ADAPTER_ACK = "I_CONFIRM_PHASE7C_REAL_REMITTANCE_BATCH_ADAPTER_HARD_BLOCK_NO_POSTING"
ADAPTER_DOCTYPE = "NDIS Real Remittance Batch Adapter Run"
LINE_DOCTYPE = "NDIS Real Remittance Batch Adapter Run Line"
PREVIEW_DOCTYPE = "NDIS Real Remittance Batch Preview"
PREVIEW_LINE_DOCTYPE = "NDIS Real Remittance Batch Preview Line"


def make_adapter_run_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-REAL-REMITTANCE-BATCH-ADAPTER-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_batch_preview():
    fields = existing_fields(
        PREVIEW_DOCTYPE,
        [
            "name",
            "preview_id",
            "design_gate",
            "evidence_freeze",
            "company",
            "bank_account",
            "receivable_account",
            "max_batch_lines",
            "max_batch_amount",
            "source_line_count",
            "eligible_line_count",
            "blocked_line_count",
            "duplicate_line_count",
            "cap_blocked_line_count",
            "would_create_payment_entry_count",
            "preview_amount",
        ],
    )
    if "name" not in fields:
        fields.insert(0, "name")

    rows = frappe.get_all(
        PREVIEW_DOCTYPE,
        filters={
            "status": "Previewed",
            "preview_approved_for_adapter_phase": 1,
            "ready_for_hard_block_adapter": 1,
            "batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
        },
        fields=fields,
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    if not rows:
        return None
    row = frappe._dict(rows[0])
    for fieldname in [
        "preview_id",
        "design_gate",
        "evidence_freeze",
        "company",
        "bank_account",
        "receivable_account",
        "max_batch_lines",
        "max_batch_amount",
        "source_line_count",
        "eligible_line_count",
        "blocked_line_count",
        "duplicate_line_count",
        "cap_blocked_line_count",
        "would_create_payment_entry_count",
        "preview_amount",
    ]:
        row.setdefault(fieldname, None)
    return row


def get_preview_lines(batch_preview):
    if not batch_preview:
        return []
    return frappe.get_all(
        PREVIEW_LINE_DOCTYPE,
        filters={"batch_preview": batch_preview},
        fields=[
            "name",
            "batch_preview",
            "line_status",
            "remittance_line",
            "claim_line",
            "sales_invoice",
            "outcome",
            "match_status",
            "would_create_payment_entry",
            "invoice_outstanding",
            "source_amount",
            "preview_amount",
            "duplicate_invoice",
            "overpayment",
            "cross_company",
            "cap_exceeded",
            "block_reason",
        ],
        order_by="creation asc",
    )


@frappe.whitelist()
def create_real_remittance_batch_payment_entries(*args, **kwargs):
    frappe.throw(
        _(
            "Phase 7C hard block active: real remittance batch Payment Entry creation is intentionally disabled. "
            "This adapter phase is evidence-only and must not create Payment Entry or GL Entry records."
        )
    )


def prove_direct_hard_block():
    try:
        create_real_remittance_batch_payment_entries()
    except Exception:
        return 1
    return 0


def classify_adapter_lines(preview_lines):
    adapter_lines = []
    for line in preview_lines:
        status = "Validation Blocked"
        reason = line.block_reason or ""

        if line.line_status == "Eligible" and int(line.would_create_payment_entry or 0):
            status = "Hard Blocked"
            reason = "Would create Payment Entry, but Phase 7C hard block prevents actual creation."
        elif line.line_status == "Duplicate":
            status = "Duplicate Blocked"
            reason = reason or "Duplicate invoice line from preview remains blocked."
        elif line.line_status == "Cap Blocked":
            status = "Cap Blocked"
            reason = reason or "Preview cap blocked this line."
        else:
            status = "Validation Blocked"
            reason = reason or "Preview line is not eligible for adapter."

        adapter_lines.append(
            {
                "preview_line": line.name,
                "batch_preview": line.batch_preview,
                "line_status": status,
                "line_label": f"{status} - {line.sales_invoice or line.name}",
                "remittance_line": line.remittance_line,
                "claim_line": line.claim_line,
                "sales_invoice": line.sales_invoice,
                "source_line_status": line.line_status,
                "outcome": line.outcome,
                "match_status": line.match_status,
                "would_create_payment_entry": int(line.line_status == "Eligible" and int(line.would_create_payment_entry or 0)),
                "hard_block_reason": reason,
                "invoice_outstanding": flt(line.invoice_outstanding or 0),
                "source_amount": flt(line.source_amount or 0),
                "would_create_amount": flt(line.preview_amount or 0) if line.line_status == "Eligible" else 0,
            }
        )
    return adapter_lines


def summarise_adapter_lines(lines):
    hard_blocked = [line for line in lines if line["line_status"] == "Hard Blocked"]
    validation_blocked = [line for line in lines if line["line_status"] == "Validation Blocked"]
    duplicate_blocked = [line for line in lines if line["line_status"] == "Duplicate Blocked"]
    cap_blocked = [line for line in lines if line["line_status"] == "Cap Blocked"]
    return {
        "source_line_count": len(lines),
        "eligible_preview_line_count": len(hard_blocked),
        "hard_blocked_line_count": len(hard_blocked),
        "validation_blocked_line_count": len(validation_blocked),
        "duplicate_blocked_line_count": len(duplicate_blocked),
        "cap_blocked_line_count": len(cap_blocked),
        "would_create_payment_entry_count": len([line for line in hard_blocked if int(line["would_create_payment_entry"] or 0)]),
        "would_create_payment_entry_amount": flt(sum(flt(line["would_create_amount"] or 0) for line in hard_blocked), 2),
    }


def summarise_score(summary, ack_ok, hard_blocked, guard):
    blocker_count = 0
    warning_count = 0
    pass_count = 0
    info_count = 0

    if summary["would_create_payment_entry_count"] > 0:
        pass_count += 1
    else:
        blocker_count += 1

    if hard_blocked:
        pass_count += 1
    else:
        blocker_count += 1

    if guard["batch_live_enabled_policy_count"] == 0 and guard["production_live_enabled_policy_count"] == 0:
        pass_count += 1
    else:
        blocker_count += 1

    pass_count += 1

    if ack_ok:
        pass_count += 1
    else:
        warning_count += 1

    if summary["validation_blocked_line_count"] or summary["duplicate_blocked_line_count"] or summary["cap_blocked_line_count"]:
        warning_count += 1

    item_count = blocker_count + warning_count + pass_count + info_count
    score = max(0, 100 - blocker_count * 25 - warning_count * 5)
    return {
        "blocker_count": blocker_count,
        "warning_count": warning_count,
        "pass_count": pass_count,
        "info_count": info_count,
        "item_count": item_count,
        "adapter_score": score,
    }


def create_adapter_line(adapter_run, line):
    doc = frappe.new_doc(LINE_DOCTYPE)
    doc.adapter_run = adapter_run
    doc.line_status = line["line_status"]
    doc.line_label = line["line_label"]
    doc.batch_preview = line["batch_preview"]
    doc.preview_line = line["preview_line"]
    doc.remittance_line = line["remittance_line"]
    doc.claim_line = line["claim_line"]
    doc.sales_invoice = line["sales_invoice"]
    doc.source_line_status = line["source_line_status"]
    doc.outcome = line["outcome"]
    doc.match_status = line["match_status"]
    doc.would_create_payment_entry = int(line["would_create_payment_entry"] or 0)
    doc.hard_block_reason = line["hard_block_reason"]
    doc.invoice_outstanding = flt(line["invoice_outstanding"] or 0)
    doc.source_amount = flt(line["source_amount"] or 0)
    doc.would_create_amount = flt(line["would_create_amount"] or 0)
    doc.checked_on = now_datetime()
    doc.insert(ignore_permissions=True)


@frappe.whitelist()
def run_real_remittance_batch_adapter(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_real_remittance_batch_adapter")

    config = config_state()
    guard_before = guardrails()
    ack_ok = acknowledgement == ADAPTER_ACK
    preview = latest_batch_preview()

    if not preview:
        frappe.throw(_("No approved Phase 7B batch preview found."))

    preview_lines = get_preview_lines(preview.name)
    adapter_lines = classify_adapter_lines(preview_lines)
    line_summary = summarise_adapter_lines(adapter_lines)
    direct_blocked = prove_direct_hard_block()
    score_summary = summarise_score(line_summary, ack_ok, direct_blocked, guard_before)

    approved = int(
        ack_ok
        and score_summary["blocker_count"] == 0
        and direct_blocked
        and line_summary["would_create_payment_entry_count"] > 0
        and guard_before["batch_live_enabled_policy_count"] == 0
        and guard_before["production_live_enabled_policy_count"] == 0
    )

    if approved:
        status = "Hard Blocked"
        adapter_status = "Ready For Activation Gate"
    elif line_summary["would_create_payment_entry_count"] <= 0:
        status = "Source Pending"
        adapter_status = "Structural Ready - Source Eligible Pending"
    else:
        status = "Needs Review"
        adapter_status = "Needs Review"

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": status,
        "adapter_status": adapter_status,
        "adapter_score": score_summary["adapter_score"],
        "adapter_approved_for_activation_gate": approved,
        "ready_for_activation_gate": approved,
        "direct_live_creation_blocked": direct_blocked,
        "batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "batch_preview": preview.name,
        "design_gate": preview.design_gate,
        "evidence_freeze": preview.evidence_freeze,
        "company": preview.company,
        "max_batch_lines": int(preview.max_batch_lines or 0),
        "max_batch_amount": flt(preview.max_batch_amount or 0),
        **line_summary,
        "actual_payment_entry_created_count": 0,
        "actual_gl_created_count": 0,
        **score_summary,
        "lines": adapter_lines,
        "guardrails_before": guard_before,
        "guardrails_after": guardrails(),
        "config": config,
        "required_acknowledgement": ADAPTER_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 7C is a hard-block adapter. It proves would-create lines but creates no Payment Entry or GL Entry.",
    }

    if int(dry_run or 0):
        return result

    doc = frappe.new_doc(ADAPTER_DOCTYPE)
    doc.adapter_run_id = make_adapter_run_id()
    doc.status = status
    doc.adapter_status = adapter_status
    doc.adapter_approved_for_activation_gate = approved
    doc.ready_for_activation_gate = approved
    doc.direct_live_creation_blocked = direct_blocked
    doc.batch_posting_allowed = 0
    doc.real_posting_allowed = 0
    doc.batch_preview = preview.name
    doc.design_gate = preview.design_gate
    doc.evidence_freeze = preview.evidence_freeze
    doc.company = preview.company
    doc.max_batch_lines = int(preview.max_batch_lines or 0)
    doc.max_batch_amount = flt(preview.max_batch_amount or 0)

    for fieldname in [
        "source_line_count",
        "eligible_preview_line_count",
        "hard_blocked_line_count",
        "validation_blocked_line_count",
        "duplicate_blocked_line_count",
        "cap_blocked_line_count",
        "would_create_payment_entry_count",
        "would_create_payment_entry_amount",
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
    doc.sales_invoice_count_today = guard_before["sales_invoice_count_today"]
    doc.purchase_invoice_count_today = guard_before["purchase_invoice_count_today"]
    doc.batch_live_enabled_policy_count = guard_before["batch_live_enabled_policy_count"]
    doc.production_live_enabled_policy_count = guard_before["production_live_enabled_policy_count"]
    doc.required_acknowledgement = ADAPTER_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    if ack_ok:
        for line in adapter_lines:
            create_adapter_line(doc.name, line)

    guard_after = guardrails()
    frappe.db.set_value(
        ADAPTER_DOCTYPE,
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
def cancel_real_remittance_batch_adapter(adapter_run, reason=None):
    assert_action("cancel_real_remittance_batch_adapter")

    if not frappe.db.exists(ADAPTER_DOCTYPE, adapter_run):
        frappe.throw(_("Adapter run not found: {0}").format(adapter_run))

    doc = frappe.get_doc(ADAPTER_DOCTYPE, adapter_run)
    if doc.status == "Cancelled":
        return {"adapter_run": adapter_run, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.ready_for_activation_gate or 0):
        frappe.throw(_("Cannot cancel an approved adapter run. Create a superseding adapter run instead."))

    frappe.db.set_value(
        ADAPTER_DOCTYPE,
        adapter_run,
        {
            "status": "Cancelled",
            "adapter_status": "Cancelled",
            "adapter_approved_for_activation_gate": 0,
            "ready_for_activation_gate": 0,
            "batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 7C adapter run cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(
        f"""
        UPDATE `tab{LINE_DOCTYPE}`
        SET line_status = 'Cancelled'
        WHERE adapter_run = %(adapter_run)s
        """,
        {"adapter_run": adapter_run},
    )
    frappe.db.commit()
    return {
        "adapter_run": adapter_run,
        "status": "Cancelled",
        "note": "Batch adapter audit record cancelled only. No accounting movement occurred.",
    }


@frappe.whitelist()
def quick_real_remittance_batch_adapter_summary(limit=20):
    runs = frappe.get_all(
        ADAPTER_DOCTYPE,
        fields=[
            "name",
            "adapter_run_id",
            "status",
            "adapter_status",
            "adapter_score",
            "adapter_approved_for_activation_gate",
            "ready_for_activation_gate",
            "direct_live_creation_blocked",
            "batch_posting_allowed",
            "real_posting_allowed",
            "batch_preview",
            "company",
            "eligible_preview_line_count",
            "hard_blocked_line_count",
            "would_create_payment_entry_count",
            "would_create_payment_entry_amount",
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
            "adapter_run",
            "line_status",
            "line_label",
            "preview_line",
            "sales_invoice",
            "outcome",
            "would_create_payment_entry",
            "would_create_amount",
            "hard_block_reason",
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
        "note": "Phase 7C adapter summary. Hard-block only; no Payment Entry or GL Entry is created.",
    }


def execute_adapter_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("status"):
        conditions.append("a.status = %(status)s")
        params["status"] = filters.status
    if filters.get("from_date"):
        conditions.append("DATE(a.checked_on) >= %(from_date)s")
        params["from_date"] = filters.from_date
    if filters.get("to_date"):
        conditions.append("DATE(a.checked_on) <= %(to_date)s")
        params["to_date"] = filters.to_date

    data = frappe.db.sql(
        f"""
        SELECT
            a.name AS adapter_run,
            a.adapter_run_id,
            a.status,
            a.adapter_status,
            a.adapter_score,
            a.ready_for_activation_gate,
            a.direct_live_creation_blocked,
            a.batch_posting_allowed,
            a.real_posting_allowed,
            a.eligible_preview_line_count,
            a.hard_blocked_line_count,
            a.validation_blocked_line_count,
            a.duplicate_blocked_line_count,
            a.cap_blocked_line_count,
            a.would_create_payment_entry_count,
            a.would_create_payment_entry_amount,
            a.actual_payment_entry_created_count,
            a.actual_gl_created_count,
            a.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Real Remittance Batch Adapter Run` a
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
        {"value": sum(int(row.would_create_payment_entry_count or 0) for row in data), "indicator": "Green", "label": _("Would Create PE"), "datatype": "Int"},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PE Created"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL Created"), "datatype": "Int"},
    ]
    return adapter_columns(), data, None, chart, summary


def adapter_columns():
    return [
        {"fieldname": "adapter_run", "label": _("Adapter Run"), "fieldtype": "Link", "options": ADAPTER_DOCTYPE, "width": 220},
        {"fieldname": "adapter_run_id", "label": _("Adapter Run ID"), "fieldtype": "Data", "width": 360},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "adapter_status", "label": _("Adapter Status"), "fieldtype": "Data", "width": 260},
        {"fieldname": "adapter_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "ready_for_activation_gate", "label": _("Ready Gate"), "fieldtype": "Check", "width": 110},
        {"fieldname": "direct_live_creation_blocked", "label": _("Direct Blocked"), "fieldtype": "Check", "width": 130},
        {"fieldname": "batch_posting_allowed", "label": _("Batch Posting Allowed"), "fieldtype": "Check", "width": 160},
        {"fieldname": "real_posting_allowed", "label": _("Real Posting Allowed"), "fieldtype": "Check", "width": 150},
        {"fieldname": "eligible_preview_line_count", "label": _("Eligible Lines"), "fieldtype": "Int", "width": 110},
        {"fieldname": "hard_blocked_line_count", "label": _("Hard-blocked"), "fieldtype": "Int", "width": 110},
        {"fieldname": "would_create_payment_entry_count", "label": _("Would Create PE"), "fieldtype": "Int", "width": 130},
        {"fieldname": "would_create_payment_entry_amount", "label": _("Would Create Amount"), "fieldtype": "Currency", "options": "currency", "width": 140},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE"), "fieldtype": "Int", "width": 100},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL"), "fieldtype": "Int", "width": 100},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_line_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("adapter_run"):
        conditions.append("l.adapter_run = %(adapter_run)s")
        params["adapter_run"] = filters.adapter_run
    if filters.get("line_status"):
        conditions.append("l.line_status = %(line_status)s")
        params["line_status"] = filters.line_status

    columns = [
        {"fieldname": "line", "label": _("Line"), "fieldtype": "Link", "options": LINE_DOCTYPE, "width": 220},
        {"fieldname": "adapter_run", "label": _("Adapter Run"), "fieldtype": "Link", "options": ADAPTER_DOCTYPE, "width": 220},
        {"fieldname": "line_status", "label": _("Status"), "fieldtype": "Data", "width": 130},
        {"fieldname": "preview_line", "label": _("Preview Line"), "fieldtype": "Link", "options": PREVIEW_LINE_DOCTYPE, "width": 220},
        {"fieldname": "sales_invoice", "label": _("Sales Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 170},
        {"fieldname": "remittance_line", "label": _("Remittance Line"), "fieldtype": "Link", "options": "NDIS Remittance Import Line", "width": 190},
        {"fieldname": "claim_line", "label": _("Claim Line"), "fieldtype": "Link", "options": "NDIS Claim Line", "width": 160},
        {"fieldname": "outcome", "label": _("Outcome"), "fieldtype": "Data", "width": 120},
        {"fieldname": "would_create_payment_entry", "label": _("Would Create PE"), "fieldtype": "Check", "width": 130},
        {"fieldname": "invoice_outstanding", "label": _("Outstanding"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "source_amount", "label": _("Source Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "would_create_amount", "label": _("Would Create Amount"), "fieldtype": "Currency", "options": "currency", "width": 140},
        {"fieldname": "hard_block_reason", "label": _("Hard Block Reason"), "fieldtype": "Small Text", "width": 520},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            l.name AS line,
            l.adapter_run,
            l.line_status,
            l.preview_line,
            l.sales_invoice,
            l.remittance_line,
            l.claim_line,
            l.outcome,
            l.would_create_payment_entry,
            l.invoice_outstanding,
            l.source_amount,
            l.would_create_amount,
            l.hard_block_reason,
            l.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Real Remittance Batch Adapter Run Line` l
        {build_where(conditions)}
        ORDER BY
            CASE l.line_status
                WHEN 'Hard Blocked' THEN 1
                WHEN 'Validation Blocked' THEN 2
                WHEN 'Duplicate Blocked' THEN 3
                WHEN 'Cap Blocked' THEN 4
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
        {"value": len([row for row in data if row.line_status == "Hard Blocked"]), "indicator": "Green", "label": _("Hard Blocked"), "datatype": "Int"},
        {"value": sum(flt(row.would_create_amount or 0) for row in data), "indicator": "Blue", "label": _("Would Create Amount"), "datatype": "Currency", "currency": currency()},
    ]
    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_adapter_report(filters)
    summary.extend(
        [
            {"value": count_dt("Payment Entry"), "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"},
            {"value": count_dt("GL Entry", {"voucher_type": "Payment Entry"}), "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"},
            {"value": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}), "indicator": "Red", "label": _("Submitted JEs Today"), "datatype": "Int"},
            {"value": count_dt("Purchase Invoice", {"creation": [">=", today()]}), "indicator": "Red", "label": _("Purchase Invoices Today"), "datatype": "Int"},
        ]
    )
    return columns, data, message, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
