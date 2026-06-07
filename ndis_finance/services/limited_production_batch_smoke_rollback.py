import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


ROLLBACK_ACK = "I_CONFIRM_PHASE9G_ROLLBACK_LIMITED_PRODUCTION_BATCH_PAYMENT_ENTRY"


def make_rollback_run_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-LIMITED-PROD-BATCH-ROLLBACK-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def has_pe_smoke_field():
    return frappe.db.has_column("Payment Entry", "custom_ndis_limited_prod_batch_smoke")


def submitted_phase9f_smoke_pe_count():
    if not has_pe_smoke_field():
        return 0

    return count_dt(
        "Payment Entry",
        {
            "docstatus": 1,
            "custom_ndis_limited_prod_batch_smoke": 1,
        },
    )


def cancelled_phase9f_smoke_pe_count():
    if not has_pe_smoke_field():
        return 0

    return count_dt(
        "Payment Entry",
        {
            "docstatus": 2,
            "custom_ndis_limited_prod_batch_smoke": 1,
        },
    )


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
        "submitted_phase9f_smoke_pe_count": submitted_phase9f_smoke_pe_count(),
        "cancelled_phase9f_smoke_pe_count": cancelled_phase9f_smoke_pe_count(),
        "submitted_journal_entry_count_today": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}),
        "purchase_invoice_count_today": count_dt("Purchase Invoice", {"creation": [">=", today()]}),
        "production_batch_enabled_policy_count": count_dt("NDIS Controlled Production Batch Posting Policy", {"production_batch_enabled": 1}),
        "live_posting_allowed_policy_count": count_dt("NDIS Controlled Production Batch Posting Policy", {"live_posting_allowed": 1}),
    }


def latest_submitted_smoke_run():
    rows = frappe.get_all(
        "NDIS Limited Production Batch Smoke Run",
        filters={
            "status": "Submitted - Rollback Required",
            "limited_batch_smoke_submitted": 1,
            "rollback_required": 1,
            "freeze_required_after_rollback": 1,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "payment_entry_submitted_count": 1,
        },
        fields=[
            "name",
            "smoke_run_id",
            "activation_gate",
            "adapter_run",
            "policy_preview",
            "policy_design",
            "policy_review_gate",
            "phase8g_freeze",
            "company",
            "customer",
            "payment_entry",
            "payment_entry_docstatus",
            "payment_entry_amount",
            "reference_count",
            "invoice_outstanding_before_total",
            "invoice_outstanding_after_total",
            "payment_entry_gl_count",
            "payment_entry_gl_net",
            "payment_entry_created_count",
            "payment_entry_submitted_count",
            "gl_created_count",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )

    return rows[0] if rows else None


def existing_completed_rollback(smoke_run):
    rows = frappe.get_all(
        "NDIS Limited Production Batch Smoke Rollback Run",
        filters={
            "smoke_run": smoke_run,
            "status": "Rolled Back",
            "rollback_completed": 1,
            "ready_for_freeze": 1,
        },
        fields=["name", "rollback_run_id"],
        limit=1,
    )

    return rows[0] if rows else None


def get_smoke_lines(smoke_run):
    if not smoke_run:
        return []

    return frappe.get_all(
        "NDIS Limited Production Batch Smoke Run Line",
        filters={"smoke_run": smoke_run, "line_status": "Submitted"},
        fields=[
            "name",
            "line_no",
            "payment_entry",
            "sales_invoice",
            "claim_line",
            "remittance_line",
            "invoice_outstanding_before",
            "allocated_amount",
            "invoice_outstanding_after",
            "payment_entry_reference_created",
            "gl_created",
            "rollback_required",
        ],
        order_by="line_no asc, creation asc",
    )


def sales_invoice_outstanding(sales_invoice):
    if not sales_invoice or not frappe.db.exists("Sales Invoice", sales_invoice):
        return 0
    return flt(frappe.db.get_value("Sales Invoice", sales_invoice, "outstanding_amount") or 0, 2)


def invoice_outstanding_total(lines):
    total = 0
    for line in lines:
        total += sales_invoice_outstanding(line.sales_invoice)
    return flt(total, 2)


def pe_gl_count_net(payment_entry):
    rows = frappe.db.sql(
        """
        SELECT COUNT(*) AS gl_count, COALESCE(SUM(debit - credit), 0) AS gl_net
        FROM `tabGL Entry`
        WHERE voucher_type='Payment Entry'
        AND voucher_no=%(payment_entry)s
        """,
        {"payment_entry": payment_entry},
        as_dict=True,
    )

    return int(rows[0].gl_count or 0), flt(rows[0].gl_net or 0, 2)


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


def validate_source(smoke, smoke_lines, guard):
    issues = []

    if not smoke:
        issues.append("No submitted Phase 9F smoke run requiring rollback was found.")
        return issues

    if existing_completed_rollback(smoke.name):
        issues.append("A completed Phase 9G rollback already exists for this Phase 9F smoke run.")

    if not smoke.payment_entry or not frappe.db.exists("Payment Entry", smoke.payment_entry):
        issues.append("Smoke Payment Entry does not exist.")
        return issues

    pe_docstatus = int(frappe.db.get_value("Payment Entry", smoke.payment_entry, "docstatus") or 0)

    if pe_docstatus != 1:
        issues.append(f"Payment Entry must be submitted before rollback. Found docstatus {pe_docstatus}.")

    if int(smoke.payment_entry_docstatus or 0) != 1:
        issues.append("Smoke run did not record Payment Entry docstatus 1.")

    if flt(smoke.payment_entry_amount or 0, 2) != 2:
        issues.append("Smoke Payment Entry amount must be 2.00.")

    if int(smoke.reference_count or 0) != 2:
        issues.append("Smoke reference count must be 2.")

    if len(smoke_lines) != 2:
        issues.append(f"Expected exactly 2 smoke lines. Found {len(smoke_lines)}.")

    current_invoice_total = invoice_outstanding_total(smoke_lines)

    if flt(current_invoice_total, 2) != 0:
        issues.append(f"Invoice outstanding before rollback must be 0.00. Found {current_invoice_total}.")

    gl_count, gl_net = pe_gl_count_net(smoke.payment_entry)

    if int(gl_count) != int(smoke.payment_entry_gl_count or 0):
        issues.append("Current Payment Entry GL count does not match Phase 9F smoke evidence.")

    if flt(gl_net, 2) != 0:
        issues.append("Current Payment Entry GL net must be 0.00 before rollback.")

    for line in smoke_lines:
        if not line.sales_invoice or not frappe.db.exists("Sales Invoice", line.sales_invoice):
            issues.append(f"Smoke line {line.line_no} has missing Sales Invoice.")
        if not int(line.payment_entry_reference_created or 0):
            issues.append(f"Smoke line {line.line_no} did not record Payment Entry reference creation.")
        if not int(line.gl_created or 0):
            issues.append(f"Smoke line {line.line_no} did not record GL creation.")
        if not int(line.rollback_required or 0):
            issues.append(f"Smoke line {line.line_no} does not require rollback.")

    if guard["submitted_phase9f_smoke_pe_count"] != 1:
        issues.append(f"Submitted Phase 9F smoke PE count must be 1 before rollback. Found {guard['submitted_phase9f_smoke_pe_count']}.")

    if guard["production_batch_enabled_policy_count"] != 0:
        issues.append("Controlled production batch enabled policy count is not zero.")

    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count is not zero.")

    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today is not zero.")

    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today is not zero.")

    return issues


def build_items(smoke, smoke_lines, guard, issues, ack_ok):
    items = []

    if smoke:
        add_item(items, "Pass", "Low", "Smoke Run", "phase9f_smoke_exists", "Phase 9F smoke exists", f"Smoke run found: {smoke.smoke_run_id}.")
    else:
        add_item(items, "Blocker", "Critical", "Smoke Run", "phase9f_smoke_exists", "Phase 9F smoke exists", "No submitted Phase 9F smoke run found.")

    if not issues:
        add_item(items, "Pass", "Low", "Rollback Source", "rollback_source_valid", "Rollback source valid", "Submitted Payment Entry, invoices, GL, and smoke lines are valid for rollback.")
    else:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Rollback Source", "rollback_source_valid", "Rollback source valid", issue)

    if smoke and smoke.payment_entry:
        add_item(items, "Pass", "Low", "Payment Entry", "payment_entry_found", "Payment Entry found", smoke.payment_entry)

    add_item(items, "Pass", "Low", "Smoke Lines", "smoke_line_count", "Smoke line count", f"{len(smoke_lines)} smoke lines found.")

    if guard["production_batch_enabled_policy_count"] == 0 and guard["live_posting_allowed_policy_count"] == 0:
        add_item(items, "Pass", "Low", "Policy Safety", "live_policies_zero", "Live policies", "No controlled production live-enabled policies.")
    else:
        add_item(items, "Blocker", "Critical", "Policy Safety", "live_policies_zero", "Live policies", "Live-enabled controlled production policy found.")

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "rollback_ack", "Rollback acknowledgement", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "rollback_ack", "Rollback acknowledgement", f"Required acknowledgement not supplied: {ROLLBACK_ACK}")

    return items


def create_rollback_lines(rollback_doc, smoke_lines):
    for line in smoke_lines:
        after = sales_invoice_outstanding(line.sales_invoice)

        row = frappe.new_doc("NDIS Limited Production Batch Smoke Rollback Line")
        row.rollback_run = rollback_doc.name
        row.line_no = line.line_no
        row.line_label = f"Phase 9G Rollback Line {line.line_no}"
        row.line_status = "Rolled Back"
        row.smoke_run = rollback_doc.smoke_run
        row.smoke_line = line.name
        row.payment_entry = rollback_doc.payment_entry
        row.sales_invoice = line.sales_invoice
        row.allocated_amount = flt(line.allocated_amount or 0, 2)
        row.invoice_outstanding_before_rollback = flt(line.invoice_outstanding_after or 0, 2)
        row.invoice_outstanding_after_rollback = after
        row.payment_entry_cancelled = 1
        row.invoice_restored = 1 if flt(after, 2) >= flt(line.allocated_amount or 0, 2) else 0
        row.rollback_completed = 1
        row.checked_on = rollback_doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_limited_production_batch_smoke_rollback(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_limited_production_batch_smoke_rollback")

    smoke = latest_submitted_smoke_run()
    smoke_lines = get_smoke_lines(smoke.name) if smoke else []

    config = config_state()
    guard_before = guardrails()
    ack_ok = acknowledgement == ROLLBACK_ACK

    issues = validate_source(smoke, smoke_lines, guard_before)
    items = build_items(smoke, smoke_lines, guard_before, issues, ack_ok)

    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    pe_docstatus_before = int(frappe.db.get_value("Payment Entry", smoke.payment_entry, "docstatus") or 0) if smoke and smoke.payment_entry else 0
    gl_count_before, gl_net_before = pe_gl_count_net(smoke.payment_entry) if smoke and smoke.payment_entry else (0, 0)
    invoice_before = invoice_outstanding_total(smoke_lines)

    should_rollback = int(ack_ok and item_summary["blocker_count"] == 0 and smoke and not int(dry_run or 0))

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Rolled Back" if should_rollback else "Needs Review",
        "rollback_status": "Rolled Back - Freeze Required" if should_rollback else "Needs Review",
        "rollback_completed": 1 if should_rollback else 0,
        "ready_for_freeze": 1 if should_rollback else 0,
        "controlled_payment_entry_cancelled": 1 if should_rollback else 0,
        "production_batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "policy_live_enabled": 0,
        "smoke_run": smoke.name if smoke else None,
        "activation_gate": smoke.activation_gate if smoke else None,
        "adapter_run": smoke.adapter_run if smoke else None,
        "policy_preview": smoke.policy_preview if smoke else None,
        "policy_design": smoke.policy_design if smoke else None,
        "policy_review_gate": smoke.policy_review_gate if smoke else None,
        "phase8g_freeze": smoke.phase8g_freeze if smoke else None,
        "company": smoke.company if smoke else None,
        "customer": smoke.customer if smoke else None,
        "payment_entry": smoke.payment_entry if smoke else None,
        "payment_entry_docstatus_before": pe_docstatus_before,
        "payment_entry_docstatus_after": pe_docstatus_before,
        "payment_entry_amount": flt(smoke.payment_entry_amount or 0) if smoke else 0,
        "reference_count": int(smoke.reference_count or 0) if smoke else 0,
        "invoice_outstanding_before_rollback_total": invoice_before,
        "invoice_outstanding_after_rollback_total": invoice_before,
        "payment_entry_gl_count_before_rollback": gl_count_before,
        "payment_entry_gl_count_after_rollback": gl_count_before,
        "payment_entry_gl_net_after_rollback": gl_net_before,
        "gl_cancellation_created_count": 0,
        "payment_entry_cancelled_count": 0,
        "rollback_score": score,
        **item_summary,
        "items": items,
        "guardrails_before": guard_before,
        "guardrails_after": guardrails(),
        "config": config,
        "required_acknowledgement": ROLLBACK_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 9G cancels the submitted Phase 9F Payment Entry only when exact acknowledgement is supplied.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["rollback_status"] = "Needs Review"
        result["rollback_completed"] = 0
        result["ready_for_freeze"] = 0
        result["controlled_payment_entry_cancelled"] = 0
        return result

    rollback_doc = frappe.new_doc("NDIS Limited Production Batch Smoke Rollback Run")
    rollback_doc.rollback_run_id = make_rollback_run_id()
    rollback_doc.status = result["status"]
    rollback_doc.rollback_status = result["rollback_status"]
    rollback_doc.rollback_completed = result["rollback_completed"]
    rollback_doc.ready_for_freeze = result["ready_for_freeze"]
    rollback_doc.controlled_payment_entry_cancelled = result["controlled_payment_entry_cancelled"]
    rollback_doc.production_batch_posting_allowed = 0
    rollback_doc.real_posting_allowed = 0
    rollback_doc.policy_live_enabled = 0

    for fieldname in [
        "smoke_run",
        "activation_gate",
        "adapter_run",
        "policy_preview",
        "policy_design",
        "policy_review_gate",
        "phase8g_freeze",
        "company",
        "customer",
        "payment_entry",
        "payment_entry_docstatus_before",
        "payment_entry_docstatus_after",
        "payment_entry_amount",
        "reference_count",
        "invoice_outstanding_before_rollback_total",
        "invoice_outstanding_after_rollback_total",
        "payment_entry_gl_count_before_rollback",
        "payment_entry_gl_count_after_rollback",
        "payment_entry_gl_net_after_rollback",
        "gl_cancellation_created_count",
        "payment_entry_cancelled_count",
        "rollback_score",
        "blocker_count",
        "warning_count",
        "pass_count",
        "info_count",
        "item_count",
    ]:
        setattr(rollback_doc, fieldname, result.get(fieldname))

    rollback_doc.site_name = frappe.local.site
    rollback_doc.sandbox_config_enabled = config["sandbox_enabled"]
    rollback_doc.production_mode_detected = config["production_mode"]
    rollback_doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    rollback_doc.checked_on = now_datetime()
    rollback_doc.checked_by = frappe.session.user

    rollback_doc.payment_entry_count_before = guard_before["payment_entry_count"]
    rollback_doc.payment_entry_count_after = guardrails()["payment_entry_count"]
    rollback_doc.payment_entry_gl_count_before = guard_before["payment_entry_gl_count"]
    rollback_doc.payment_entry_gl_count_after = guardrails()["payment_entry_gl_count"]
    rollback_doc.submitted_phase9f_smoke_pe_count_before = guard_before["submitted_phase9f_smoke_pe_count"]
    rollback_doc.submitted_phase9f_smoke_pe_count_after = guard_before["submitted_phase9f_smoke_pe_count"]
    rollback_doc.cancelled_phase9f_smoke_pe_count_before = guard_before["cancelled_phase9f_smoke_pe_count"]
    rollback_doc.cancelled_phase9f_smoke_pe_count_after = guard_before["cancelled_phase9f_smoke_pe_count"]
    rollback_doc.submitted_journal_entry_count_today = guard_before["submitted_journal_entry_count_today"]
    rollback_doc.purchase_invoice_count_today = guard_before["purchase_invoice_count_today"]
    rollback_doc.production_batch_enabled_policy_count = guard_before["production_batch_enabled_policy_count"]
    rollback_doc.live_posting_allowed_policy_count = guard_before["live_posting_allowed_policy_count"]

    rollback_doc.required_acknowledgement = ROLLBACK_ACK
    rollback_doc.acknowledgement = acknowledgement
    rollback_doc.acknowledgement_ok = int(ack_ok)
    rollback_doc.summary_json = safe_json(result)
    rollback_doc.notes = notes
    rollback_doc.insert(ignore_permissions=True)

    if should_rollback:
        pe = frappe.get_doc("Payment Entry", smoke.payment_entry)

        if pe.meta.has_field("custom_ndis_limited_prod_batch_rollback_run"):
            frappe.db.set_value(
                "Payment Entry",
                pe.name,
                "custom_ndis_limited_prod_batch_rollback_run",
                rollback_doc.name,
                update_modified=False,
            )
            pe.reload()

        pe.cancel()

        pe_docstatus_after = int(frappe.db.get_value("Payment Entry", smoke.payment_entry, "docstatus") or 0)
        gl_count_after, gl_net_after = pe_gl_count_net(smoke.payment_entry)
        invoice_after = invoice_outstanding_total(smoke_lines)
        guard_after = guardrails()

        create_rollback_lines(rollback_doc, smoke_lines)

        result.update(
            {
                "payment_entry_docstatus_after": pe_docstatus_after,
                "invoice_outstanding_after_rollback_total": invoice_after,
                "payment_entry_gl_count_after_rollback": gl_count_after,
                "payment_entry_gl_net_after_rollback": gl_net_after,
                "gl_cancellation_created_count": max(0, gl_count_after - gl_count_before),
                "payment_entry_cancelled_count": 1 if pe_docstatus_after == 2 else 0,
                "guardrails_after": guard_after,
            }
        )

        frappe.db.set_value(
            "NDIS Limited Production Batch Smoke Rollback Run",
            rollback_doc.name,
            {
                "payment_entry_docstatus_after": pe_docstatus_after,
                "invoice_outstanding_after_rollback_total": invoice_after,
                "payment_entry_gl_count_after_rollback": gl_count_after,
                "payment_entry_gl_net_after_rollback": gl_net_after,
                "gl_cancellation_created_count": max(0, gl_count_after - gl_count_before),
                "payment_entry_cancelled_count": 1 if pe_docstatus_after == 2 else 0,
                "payment_entry_count_after": guard_after["payment_entry_count"],
                "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
                "submitted_phase9f_smoke_pe_count_after": guard_after["submitted_phase9f_smoke_pe_count"],
                "cancelled_phase9f_smoke_pe_count_after": guard_after["cancelled_phase9f_smoke_pe_count"],
                "summary_json": safe_json(result),
            },
            update_modified=False,
        )

    else:
        guard_after = guardrails()
        frappe.db.set_value(
            "NDIS Limited Production Batch Smoke Rollback Run",
            rollback_doc.name,
            {
                "payment_entry_count_after": guard_after["payment_entry_count"],
                "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
                "submitted_phase9f_smoke_pe_count_after": guard_after["submitted_phase9f_smoke_pe_count"],
                "cancelled_phase9f_smoke_pe_count_after": guard_after["cancelled_phase9f_smoke_pe_count"],
                "summary_json": safe_json({**result, "guardrails_after": guard_after}),
            },
            update_modified=False,
        )

    frappe.db.commit()

    result["created"] = True
    result["rollback_run"] = rollback_doc.name
    result["rollback_run_id"] = rollback_doc.rollback_run_id

    return result


@frappe.whitelist()
def cancel_limited_production_batch_smoke_rollback_audit(rollback_run, reason=None):
    assert_action("cancel_limited_production_batch_smoke_rollback_audit")

    if not frappe.db.exists("NDIS Limited Production Batch Smoke Rollback Run", rollback_run):
        frappe.throw(_("Rollback run not found: {0}").format(rollback_run))

    doc = frappe.get_doc("NDIS Limited Production Batch Smoke Rollback Run", rollback_run)

    if doc.status == "Cancelled":
        return {"rollback_run": rollback_run, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.rollback_completed or 0) or int(doc.controlled_payment_entry_cancelled or 0):
        frappe.throw(_("Cannot cancel a completed rollback audit. Proceed to Phase 9H freeze."))

    frappe.db.set_value(
        "NDIS Limited Production Batch Smoke Rollback Run",
        rollback_run,
        {
            "status": "Cancelled",
            "rollback_status": "Cancelled",
            "rollback_completed": 0,
            "ready_for_freeze": 0,
            "controlled_payment_entry_cancelled": 0,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 9G rollback audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        """
        UPDATE `tabNDIS Limited Production Batch Smoke Rollback Line`
        SET line_status = 'Cancelled'
        WHERE rollback_run = %(rollback_run)s
        """,
        {"rollback_run": rollback_run},
    )

    frappe.db.commit()

    return {
        "rollback_run": rollback_run,
        "status": "Cancelled",
        "note": "Rollback audit record cancelled only. No accounting movement occurred.",
    }


@frappe.whitelist()
def quick_limited_production_batch_smoke_rollback_summary(limit=20):
    runs = frappe.get_all(
        "NDIS Limited Production Batch Smoke Rollback Run",
        fields=[
            "name",
            "rollback_run_id",
            "status",
            "rollback_status",
            "rollback_completed",
            "ready_for_freeze",
            "controlled_payment_entry_cancelled",
            "smoke_run",
            "payment_entry",
            "payment_entry_docstatus_before",
            "payment_entry_docstatus_after",
            "payment_entry_amount",
            "reference_count",
            "invoice_outstanding_before_rollback_total",
            "invoice_outstanding_after_rollback_total",
            "payment_entry_gl_count_before_rollback",
            "payment_entry_gl_count_after_rollback",
            "payment_entry_gl_net_after_rollback",
            "gl_cancellation_created_count",
            "payment_entry_cancelled_count",
            "rollback_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    lines = frappe.get_all(
        "NDIS Limited Production Batch Smoke Rollback Line",
        fields=[
            "name",
            "rollback_run",
            "line_no",
            "line_status",
            "payment_entry",
            "sales_invoice",
            "allocated_amount",
            "invoice_outstanding_before_rollback",
            "invoice_outstanding_after_rollback",
            "payment_entry_cancelled",
            "invoice_restored",
            "rollback_completed",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    return {
        "runs": runs,
        "lines": lines,
        "required_acknowledgement": ROLLBACK_ACK,
        "guardrails": guardrails(),
        "config": config_state(),
        "note": "Phase 9G limited production batch smoke rollback summary. Freeze is required after successful rollback.",
    }


def execute_rollback_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("status"):
        conditions.append("r.status = %(status)s")
        params["status"] = filters.get("status")

    columns = rollback_columns()

    data = frappe.db.sql(
        f"""
        SELECT
            r.name AS rollback_run,
            r.rollback_run_id,
            r.status,
            r.rollback_status,
            r.rollback_completed,
            r.ready_for_freeze,
            r.controlled_payment_entry_cancelled,
            r.smoke_run,
            r.payment_entry,
            r.payment_entry_docstatus_before,
            r.payment_entry_docstatus_after,
            r.payment_entry_amount,
            r.reference_count,
            r.invoice_outstanding_before_rollback_total,
            r.invoice_outstanding_after_rollback_total,
            r.payment_entry_gl_count_before_rollback,
            r.payment_entry_gl_count_after_rollback,
            r.payment_entry_gl_net_after_rollback,
            r.gl_cancellation_created_count,
            r.payment_entry_cancelled_count,
            r.rollback_score,
            r.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Limited Production Batch Smoke Rollback Run` r
        {build_where(conditions)}
        ORDER BY r.creation DESC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.rollback_run_id for row in data[:20]],
            "datasets": [
                {"name": "Cancelled PE", "values": [int(row.payment_entry_cancelled_count or 0) for row in data[:20]]},
                {"name": "GL Rows After", "values": [int(row.payment_entry_gl_count_after_rollback or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Rollback Runs"), "datatype": "Int"},
        {"value": sum(int(row.rollback_completed or 0) for row in data), "indicator": "Green", "label": _("Completed"), "datatype": "Int"},
        {"value": sum(flt(row.invoice_outstanding_after_rollback_total or 0) for row in data), "indicator": "Blue", "label": _("Restored Outstanding"), "datatype": "Currency", "currency": currency()},
        {"value": sum(int(row.payment_entry_cancelled_count or 0) for row in data), "indicator": "Orange", "label": _("Cancelled PE"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def rollback_columns():
    return [
        {"fieldname": "rollback_run", "label": _("Rollback Run"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Smoke Rollback Run", "width": 220},
        {"fieldname": "rollback_run_id", "label": _("Rollback Run ID"), "fieldtype": "Data", "width": 430},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 130},
        {"fieldname": "rollback_status", "label": _("Rollback Status"), "fieldtype": "Data", "width": 250},
        {"fieldname": "ready_for_freeze", "label": _("Ready Freeze"), "fieldtype": "Check", "width": 110},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 170},
        {"fieldname": "payment_entry_docstatus_before", "label": _("PE Before"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_docstatus_after", "label": _("PE After"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_amount", "label": _("PE Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "invoice_outstanding_before_rollback_total", "label": _("Outstanding Before"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "invoice_outstanding_after_rollback_total", "label": _("Outstanding After"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "payment_entry_gl_count_before_rollback", "label": _("GL Before"), "fieldtype": "Int", "width": 100},
        {"fieldname": "payment_entry_gl_count_after_rollback", "label": _("GL After"), "fieldtype": "Int", "width": 100},
        {"fieldname": "payment_entry_gl_net_after_rollback", "label": _("GL Net"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "rollback_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_line_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("rollback_run"):
        conditions.append("l.rollback_run = %(rollback_run)s")
        params["rollback_run"] = filters.get("rollback_run")

    if filters.get("line_status"):
        conditions.append("l.line_status = %(line_status)s")
        params["line_status"] = filters.get("line_status")

    columns = [
        {"fieldname": "line", "label": _("Line"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Smoke Rollback Line", "width": 220},
        {"fieldname": "rollback_run", "label": _("Rollback Run"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Smoke Rollback Run", "width": 220},
        {"fieldname": "line_no", "label": _("Line No"), "fieldtype": "Int", "width": 80},
        {"fieldname": "line_status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 170},
        {"fieldname": "sales_invoice", "label": _("Sales Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 170},
        {"fieldname": "allocated_amount", "label": _("Allocated"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "invoice_outstanding_before_rollback", "label": _("Before Rollback"), "fieldtype": "Currency", "options": "currency", "width": 140},
        {"fieldname": "invoice_outstanding_after_rollback", "label": _("After Rollback"), "fieldtype": "Currency", "options": "currency", "width": 140},
        {"fieldname": "payment_entry_cancelled", "label": _("PE Cancelled"), "fieldtype": "Check", "width": 110},
        {"fieldname": "invoice_restored", "label": _("Invoice Restored"), "fieldtype": "Check", "width": 120},
        {"fieldname": "rollback_completed", "label": _("Rollback Done"), "fieldtype": "Check", "width": 110},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            l.name AS line,
            l.rollback_run,
            l.line_no,
            l.line_status,
            l.payment_entry,
            l.sales_invoice,
            l.allocated_amount,
            l.invoice_outstanding_before_rollback,
            l.invoice_outstanding_after_rollback,
            l.payment_entry_cancelled,
            l.invoice_restored,
            l.rollback_completed,
            l.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Limited Production Batch Smoke Rollback Line` l
        {build_where(conditions)}
        ORDER BY l.rollback_run DESC, l.line_no ASC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [str(row.line_no) for row in data[:20]],
            "datasets": [{"name": "Restored", "values": [flt(row.invoice_outstanding_after_rollback or 0) for row in data[:20]]}],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Lines"), "datatype": "Int"},
        {"value": len([row for row in data if row.line_status == "Rolled Back"]), "indicator": "Green", "label": _("Rolled Back"), "datatype": "Int"},
        {"value": sum(flt(row.invoice_outstanding_after_rollback or 0) for row in data), "indicator": "Blue", "label": _("Restored"), "datatype": "Currency", "currency": currency()},
    ]

    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_rollback_report(filters)

    guard = guardrails()

    summary.append({"value": guard["payment_entry_count"], "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"})
    summary.append({"value": guard["payment_entry_gl_count"], "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"})
    summary.append({"value": guard["submitted_phase9f_smoke_pe_count"], "indicator": "Red", "label": _("Submitted Phase 9F PE"), "datatype": "Int"})
    summary.append({"value": guard["cancelled_phase9f_smoke_pe_count"], "indicator": "Green", "label": _("Cancelled Phase 9F PE"), "datatype": "Int"})
    summary.append({"value": guard["submitted_journal_entry_count_today"], "indicator": "Red", "label": _("Submitted JE Today"), "datatype": "Int"})
    summary.append({"value": guard["purchase_invoice_count_today"], "indicator": "Red", "label": _("Purchase Invoice Today"), "datatype": "Int"})
    summary.append({"value": guard["production_batch_enabled_policy_count"], "indicator": "Red", "label": _("Production Batch Enabled Policies"), "datatype": "Int"})
    summary.append({"value": guard["live_posting_allowed_policy_count"], "indicator": "Red", "label": _("Live Posting Allowed Policies"), "datatype": "Int"})

    return columns, data, message, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
