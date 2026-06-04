import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


ROLLBACK_ACK = "I_CONFIRM_PHASE8F_ROLLBACK_CONTROLLED_PRODUCTION_BATCH_PAYMENT_ENTRY"


def make_rollback_run_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-CTRL-PROD-BATCH-ROLLBACK-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def has_pe_phase8e_fields():
    return frappe.db.has_column("Payment Entry", "custom_ndis_controlled_prod_batch_smoke")


def submitted_phase8e_smoke_pe_count():
    if not has_pe_phase8e_fields():
        return 0

    return count_dt(
        "Payment Entry",
        {
            "docstatus": 1,
            "custom_ndis_controlled_prod_batch_smoke": 1,
        },
    )


def cancelled_phase8e_smoke_pe_count():
    if not has_pe_phase8e_fields():
        return 0

    return count_dt(
        "Payment Entry",
        {
            "docstatus": 2,
            "custom_ndis_controlled_prod_batch_smoke": 1,
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
        "submitted_journal_entry_count_today": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}),
        "purchase_invoice_count_today": count_dt("Purchase Invoice", {"creation": [">=", today()]}),
        "production_batch_enabled_policy_count": count_dt("NDIS Controlled Production Batch Posting Policy", {"production_batch_enabled": 1}),
        "live_posting_allowed_policy_count": count_dt("NDIS Controlled Production Batch Posting Policy", {"live_posting_allowed": 1}),
        "submitted_phase8e_smoke_pe_count": submitted_phase8e_smoke_pe_count(),
        "cancelled_phase8e_smoke_pe_count": cancelled_phase8e_smoke_pe_count(),
    }


def latest_smoke_run():
    rows = frappe.get_all(
        "NDIS Controlled Production Batch Smoke Run",
        filters={
            "status": "Submitted - Rollback Required",
            "controlled_smoke_submitted": 1,
            "rollback_required": 1,
            "freeze_required_after_rollback": 1,
            "payment_entry_submitted": 1,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
        },
        fields=[
            "name",
            "smoke_run_id",
            "activation_gate",
            "adapter_run",
            "preview",
            "design_gate",
            "phase7h_freeze",
            "source_run",
            "company",
            "customer",
            "payment_entry",
            "payment_entry_docstatus",
            "payment_entry_amount",
            "invoice_count",
            "invoice_outstanding_after_total",
            "payment_entry_gl_count",
            "payment_entry_gl_net",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )

    return rows[0] if rows else None


def existing_completed_rollback(smoke_run):
    rows = frappe.get_all(
        "NDIS Controlled Production Batch Smoke Rollback Run",
        filters={
            "smoke_run": smoke_run,
            "rollback_completed": 1,
            "controlled_payment_entry_cancelled": 1,
            "status": "Rolled Back",
        },
        fields=["name", "rollback_run_id", "payment_entry"],
        limit=1,
    )

    return rows[0] if rows else None


def get_smoke_lines(smoke_run):
    return frappe.get_all(
        "NDIS Controlled Production Batch Smoke Line",
        filters={
            "smoke_run": smoke_run,
            "line_status": "Submitted",
            "payment_entry_reference_created": 1,
        },
        fields=[
            "name",
            "line_no",
            "sales_invoice",
            "payment_entry",
            "allocated_amount",
            "invoice_outstanding_before",
            "invoice_outstanding_after",
        ],
        order_by="line_no asc, creation asc",
    )


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


def validate_rollback_source(smoke, lines):
    issues = []

    if not smoke:
        issues.append("No Phase 8E submitted rollback-required smoke run found.")
        return issues

    if existing_completed_rollback(smoke.name):
        issues.append("A completed rollback already exists for this Phase 8E smoke run.")

    if not smoke.payment_entry:
        issues.append("Smoke run has no Payment Entry linked.")
        return issues

    if not frappe.db.exists("Payment Entry", smoke.payment_entry):
        issues.append(f"Payment Entry does not exist: {smoke.payment_entry}")
        return issues

    pe = frappe.get_doc("Payment Entry", smoke.payment_entry)

    if pe.docstatus != 1:
        issues.append(f"Payment Entry must be submitted before rollback. Current docstatus: {pe.docstatus}")

    if pe.meta.has_field("custom_ndis_controlled_prod_batch_smoke") and not int(pe.custom_ndis_controlled_prod_batch_smoke or 0):
        issues.append("Payment Entry is not tagged as Phase 8E controlled production batch smoke.")

    if pe.meta.has_field("custom_ndis_controlled_prod_batch_smoke_run") and pe.custom_ndis_controlled_prod_batch_smoke_run != smoke.name:
        issues.append("Payment Entry smoke run tag does not match the selected smoke run.")

    if flt(pe.paid_amount or pe.received_amount or 0) != flt(smoke.payment_entry_amount or 0):
        issues.append("Payment Entry amount does not match smoke run amount.")

    if not lines:
        issues.append("No submitted Phase 8E smoke lines found.")

    if len(lines) != int(smoke.invoice_count or 0):
        issues.append("Smoke line count does not match smoke invoice count.")

    for line in lines:
        if line.payment_entry != smoke.payment_entry:
            issues.append(f"Line {line.line_no}: Payment Entry does not match smoke run Payment Entry.")

        if not line.sales_invoice or not frappe.db.exists("Sales Invoice", line.sales_invoice):
            issues.append(f"Line {line.line_no}: Sales Invoice missing.")
            continue

        outstanding_now = flt(frappe.db.get_value("Sales Invoice", line.sales_invoice, "outstanding_amount") or 0)

        if outstanding_now != flt(line.invoice_outstanding_after or 0):
            issues.append(
                f"Line {line.line_no}: Current outstanding {outstanding_now} does not match smoke after amount {flt(line.invoice_outstanding_after or 0)}."
            )

    return issues


def build_items(smoke, lines, config, guard, source_issues, ack_ok):
    items = []

    if smoke:
        add_item(items, "Pass", "Low", "Smoke", "smoke_exists", "Phase 8E smoke exists", f"Smoke run found: {smoke.smoke_run_id}.")
    else:
        add_item(items, "Blocker", "Critical", "Smoke", "smoke_exists", "Phase 8E smoke exists", "No submitted rollback-required Phase 8E smoke run found.")

    if not source_issues:
        add_item(items, "Pass", "Low", "Source", "source_valid", "Rollback source valid", f"{len(lines)} smoke lines validated.")
    else:
        for issue in source_issues:
            add_item(items, "Blocker", "Critical", "Source", "source_valid", "Rollback source valid", issue)

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

    if guard["submitted_phase8e_smoke_pe_count"] == 1:
        add_item(items, "Pass", "Low", "Rollback Target", "submitted_smoke_pe_one", "Exactly one submitted Phase 8E smoke PE", "One submitted tagged Phase 8E Payment Entry is available for rollback.")
    else:
        add_item(items, "Blocker", "Critical", "Rollback Target", "submitted_smoke_pe_one", "Exactly one submitted Phase 8E smoke PE", f"Found {guard['submitted_phase8e_smoke_pe_count']} submitted Phase 8E smoke PEs.")

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "rollback_ack", "Rollback acknowledgement", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "rollback_ack", "Rollback acknowledgement", f"Required acknowledgement not supplied: {ROLLBACK_ACK}")

    return items


def create_rollback_line(rollback_run, smoke, smoke_line, payment_entry):
    outstanding_after = 0

    if smoke_line.sales_invoice and frappe.db.exists("Sales Invoice", smoke_line.sales_invoice):
        outstanding_after = flt(frappe.db.get_value("Sales Invoice", smoke_line.sales_invoice, "outstanding_amount") or 0)

    doc = frappe.new_doc("NDIS Controlled Production Batch Smoke Rollback Line")
    doc.rollback_run = rollback_run
    doc.line_no = smoke_line.line_no
    doc.line_label = f"Phase 8F Rollback Line {smoke_line.line_no}"
    doc.line_status = "Restored"
    doc.status_detail = "Invoice outstanding restored after Payment Entry cancellation."
    doc.smoke_run = smoke.name
    doc.smoke_line = smoke_line.name
    doc.sales_invoice = smoke_line.sales_invoice
    doc.payment_entry = payment_entry
    doc.allocated_amount = flt(smoke_line.allocated_amount or 0)
    doc.invoice_outstanding_before_rollback = flt(smoke_line.invoice_outstanding_after or 0)
    doc.invoice_outstanding_after_rollback = outstanding_after
    doc.checked_on = now_datetime()
    doc.insert(ignore_permissions=True)


@frappe.whitelist()
def run_controlled_production_batch_smoke_rollback(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_controlled_production_batch_smoke_rollback")

    smoke = latest_smoke_run()
    lines = get_smoke_lines(smoke.name) if smoke else []

    config = config_state()
    guard_before = guardrails()
    ack_ok = acknowledgement == ROLLBACK_ACK

    source_issues = validate_rollback_source(smoke, lines)
    items = build_items(smoke, lines, config, guard_before, source_issues, ack_ok)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    payment_entry = smoke.payment_entry if smoke else None
    pe_docstatus_before = int(frappe.db.get_value("Payment Entry", payment_entry, "docstatus") or 0) if payment_entry else 0
    pe_gl_count_before, pe_gl_net_before = pe_gl_count_net(payment_entry) if payment_entry else (0, 0)

    invoice_before_rollback = flt(sum(flt(line.invoice_outstanding_after or 0) for line in lines), 2)
    expected_invoice_after = flt(sum(flt(line.invoice_outstanding_before or 0) for line in lines), 2)

    can_rollback = bool(ack_ok and item_summary["blocker_count"] == 0 and smoke and payment_entry)

    base_result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Rolled Back" if can_rollback else "Needs Review",
        "rollback_status": "Rolled Back - Freeze Required" if can_rollback else "Needs Review",
        "rollback_completed": 1 if can_rollback else 0,
        "ready_for_freeze": 1 if can_rollback else 0,
        "controlled_payment_entry_cancelled": 1 if can_rollback else 0,
        "production_batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "smoke_run": smoke.name if smoke else None,
        "activation_gate": smoke.activation_gate if smoke else None,
        "adapter_run": smoke.adapter_run if smoke else None,
        "preview": smoke.preview if smoke else None,
        "design_gate": smoke.design_gate if smoke else None,
        "phase7h_freeze": smoke.phase7h_freeze if smoke else None,
        "source_run": smoke.source_run if smoke else None,
        "company": smoke.company if smoke else None,
        "customer": smoke.customer if smoke else None,
        "payment_entry": payment_entry,
        "payment_entry_docstatus_before": pe_docstatus_before,
        "payment_entry_docstatus_after": pe_docstatus_before,
        "payment_entry_amount": flt(smoke.payment_entry_amount or 0) if smoke else 0,
        "invoice_count": len(lines),
        "invoice_outstanding_before_rollback_total": invoice_before_rollback,
        "invoice_outstanding_after_rollback_total": invoice_before_rollback,
        "expected_invoice_outstanding_after_rollback_total": expected_invoice_after,
        "payment_entry_gl_count_before_rollback": pe_gl_count_before,
        "payment_entry_gl_count_after_rollback": pe_gl_count_before,
        "payment_entry_gl_net_after_rollback": pe_gl_net_before,
        "submitted_phase8e_smoke_pe_count_after": guard_before["submitted_phase8e_smoke_pe_count"],
        "cancelled_phase8e_smoke_pe_count_after": guard_before["cancelled_phase8e_smoke_pe_count"],
        "rollback_score": score,
        **item_summary,
        "items": items,
        "guardrails_before": guard_before,
        "guardrails_after": guardrails(),
        "config": config,
        "required_acknowledgement": ROLLBACK_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 8F cancels only the tagged Phase 8E controlled production batch Payment Entry and prepares freeze evidence.",
    }

    if int(dry_run or 0):
        base_result["rollback_completed"] = 0
        base_result["ready_for_freeze"] = 0
        base_result["controlled_payment_entry_cancelled"] = 0
        base_result["status"] = "Needs Review"
        base_result["rollback_status"] = "Needs Review"
        return base_result

    doc = frappe.new_doc("NDIS Controlled Production Batch Smoke Rollback Run")
    doc.rollback_run_id = make_rollback_run_id()
    doc.status = "Needs Review"
    doc.rollback_status = "Needs Review"
    doc.rollback_completed = 0
    doc.ready_for_freeze = 0
    doc.controlled_payment_entry_cancelled = 0
    doc.production_batch_posting_allowed = 0
    doc.real_posting_allowed = 0

    for fieldname in [
        "smoke_run",
        "activation_gate",
        "adapter_run",
        "preview",
        "design_gate",
        "phase7h_freeze",
        "source_run",
        "company",
        "customer",
        "payment_entry",
        "payment_entry_docstatus_before",
        "payment_entry_docstatus_after",
        "payment_entry_amount",
        "invoice_count",
        "invoice_outstanding_before_rollback_total",
        "invoice_outstanding_after_rollback_total",
        "payment_entry_gl_count_before_rollback",
        "payment_entry_gl_count_after_rollback",
        "payment_entry_gl_net_after_rollback",
        "submitted_phase8e_smoke_pe_count_after",
        "cancelled_phase8e_smoke_pe_count_after",
        "rollback_score",
        "blocker_count",
        "warning_count",
        "pass_count",
        "info_count",
        "item_count",
    ]:
        setattr(doc, fieldname, base_result.get(fieldname))

    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user

    doc.payment_entry_count_before = guard_before["payment_entry_count"]
    doc.payment_entry_count_after = guard_before["payment_entry_count"]
    doc.payment_entry_gl_count_before = guard_before["payment_entry_gl_count"]
    doc.payment_entry_gl_count_after = guard_before["payment_entry_gl_count"]
    doc.submitted_journal_entry_count_today = guard_before["submitted_journal_entry_count_today"]
    doc.purchase_invoice_count_today = guard_before["purchase_invoice_count_today"]
    doc.production_batch_enabled_policy_count = guard_before["production_batch_enabled_policy_count"]
    doc.live_posting_allowed_policy_count = guard_before["live_posting_allowed_policy_count"]

    doc.required_acknowledgement = ROLLBACK_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(base_result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    if not can_rollback:
        base_result["created"] = True
        base_result["rollback_run"] = doc.name
        base_result["rollback_run_id"] = doc.rollback_run_id
        return base_result

    try:
        pe = frappe.get_doc("Payment Entry", payment_entry)
        pe.cancel()

        for line in lines:
            create_rollback_line(doc.name, smoke, line, payment_entry)

        invoice_after = 0
        for line in lines:
            invoice_after += flt(frappe.db.get_value("Sales Invoice", line.sales_invoice, "outstanding_amount") or 0)

        pe_docstatus_after = int(frappe.db.get_value("Payment Entry", payment_entry, "docstatus") or 0)
        pe_gl_count_after, pe_gl_net_after = pe_gl_count_net(payment_entry)
        guard_after = guardrails()

        update_values = {
            "status": "Rolled Back",
            "rollback_status": "Rolled Back - Freeze Required",
            "rollback_completed": 1,
            "ready_for_freeze": 1,
            "controlled_payment_entry_cancelled": 1,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "payment_entry_docstatus_after": pe_docstatus_after,
            "invoice_outstanding_after_rollback_total": flt(invoice_after, 2),
            "payment_entry_gl_count_after_rollback": pe_gl_count_after,
            "payment_entry_gl_net_after_rollback": pe_gl_net_after,
            "submitted_phase8e_smoke_pe_count_after": guard_after["submitted_phase8e_smoke_pe_count"],
            "cancelled_phase8e_smoke_pe_count_after": guard_after["cancelled_phase8e_smoke_pe_count"],
            "payment_entry_count_after": guard_after["payment_entry_count"],
            "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
        }

        result = {
            **base_result,
            **update_values,
            "created": True,
            "rollback_run": doc.name,
            "rollback_run_id": doc.rollback_run_id,
            "guardrails_after": guard_after,
        }

        update_values["summary_json"] = safe_json(result)

        frappe.db.set_value(
            "NDIS Controlled Production Batch Smoke Rollback Run",
            doc.name,
            update_values,
            update_modified=False,
        )

        frappe.db.commit()
        return result

    except Exception as exc:
        frappe.db.rollback()

        frappe.db.set_value(
            "NDIS Controlled Production Batch Smoke Rollback Run",
            doc.name,
            {
                "status": "Failed",
                "rollback_status": "Failed",
                "rollback_completed": 0,
                "ready_for_freeze": 0,
                "controlled_payment_entry_cancelled": 0,
                "summary_json": safe_json({"error": str(exc), **base_result}),
            },
            update_modified=False,
        )
        frappe.db.commit()
        raise


@frappe.whitelist()
def cancel_controlled_production_batch_smoke_rollback_audit(rollback_run, reason=None):
    assert_action("cancel_controlled_production_batch_smoke_rollback_audit")

    if not frappe.db.exists("NDIS Controlled Production Batch Smoke Rollback Run", rollback_run):
        frappe.throw(_("Rollback run not found: {0}").format(rollback_run))

    doc = frappe.get_doc("NDIS Controlled Production Batch Smoke Rollback Run", rollback_run)

    if doc.status == "Cancelled":
        return {"rollback_run": rollback_run, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.rollback_completed or 0) or int(doc.controlled_payment_entry_cancelled or 0):
        frappe.throw(_("Cannot cancel a completed rollback run."))

    frappe.db.set_value(
        "NDIS Controlled Production Batch Smoke Rollback Run",
        rollback_run,
        {
            "status": "Cancelled",
            "rollback_status": "Cancelled",
            "rollback_completed": 0,
            "ready_for_freeze": 0,
            "controlled_payment_entry_cancelled": 0,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 8F rollback audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        """
        UPDATE `tabNDIS Controlled Production Batch Smoke Rollback Line`
        SET line_status = 'Cancelled'
        WHERE rollback_run = %(rollback_run)s
        """,
        {"rollback_run": rollback_run},
    )

    frappe.db.commit()

    return {
        "rollback_run": rollback_run,
        "status": "Cancelled",
        "note": "Rollback audit record cancelled only. No Payment Entry was cancelled by this audit action.",
    }


@frappe.whitelist()
def quick_controlled_production_batch_smoke_rollback_summary(limit=20):
    runs = frappe.get_all(
        "NDIS Controlled Production Batch Smoke Rollback Run",
        fields=[
            "name",
            "rollback_run_id",
            "status",
            "rollback_status",
            "rollback_completed",
            "ready_for_freeze",
            "controlled_payment_entry_cancelled",
            "production_batch_posting_allowed",
            "real_posting_allowed",
            "smoke_run",
            "payment_entry",
            "payment_entry_docstatus_before",
            "payment_entry_docstatus_after",
            "payment_entry_amount",
            "invoice_count",
            "invoice_outstanding_before_rollback_total",
            "invoice_outstanding_after_rollback_total",
            "payment_entry_gl_count_before_rollback",
            "payment_entry_gl_count_after_rollback",
            "payment_entry_gl_net_after_rollback",
            "submitted_phase8e_smoke_pe_count_after",
            "cancelled_phase8e_smoke_pe_count_after",
            "rollback_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    lines = frappe.get_all(
        "NDIS Controlled Production Batch Smoke Rollback Line",
        fields=[
            "name",
            "rollback_run",
            "line_no",
            "line_status",
            "sales_invoice",
            "payment_entry",
            "allocated_amount",
            "invoice_outstanding_before_rollback",
            "invoice_outstanding_after_rollback",
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
        "note": "Phase 8F rollback summary. Freeze evidence should be created in Phase 8G after rollback.",
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
            r.production_batch_posting_allowed,
            r.real_posting_allowed,
            r.smoke_run,
            r.payment_entry,
            r.payment_entry_docstatus_before,
            r.payment_entry_docstatus_after,
            r.payment_entry_amount,
            r.invoice_count,
            r.invoice_outstanding_before_rollback_total,
            r.invoice_outstanding_after_rollback_total,
            r.payment_entry_gl_count_before_rollback,
            r.payment_entry_gl_count_after_rollback,
            r.payment_entry_gl_net_after_rollback,
            r.submitted_phase8e_smoke_pe_count_after,
            r.cancelled_phase8e_smoke_pe_count_after,
            r.rollback_score,
            r.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Controlled Production Batch Smoke Rollback Run` r
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
                {"name": "Rolled Back", "values": [int(row.rollback_completed or 0) for row in data[:20]]},
                {"name": "Ready Freeze", "values": [int(row.ready_for_freeze or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Rollback Runs"), "datatype": "Int"},
        {"value": sum(int(row.rollback_completed or 0) for row in data), "indicator": "Green", "label": _("Rolled Back"), "datatype": "Int"},
        {
            "value": sum(flt(row.payment_entry_amount or 0) for row in data if int(row.rollback_completed or 0)),
            "indicator": "Blue",
            "label": _("Rolled Back Amount"),
            "datatype": "Currency",
            "currency": currency(),
        },
        {"value": sum(int(row.ready_for_freeze or 0) for row in data), "indicator": "Orange", "label": _("Ready Freeze"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def rollback_columns():
    return [
        {"fieldname": "rollback_run", "label": _("Rollback Run"), "fieldtype": "Link", "options": "NDIS Controlled Production Batch Smoke Rollback Run", "width": 220},
        {"fieldname": "rollback_run_id", "label": _("Rollback Run ID"), "fieldtype": "Data", "width": 410},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 140},
        {"fieldname": "rollback_status", "label": _("Rollback Status"), "fieldtype": "Data", "width": 250},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 170},
        {"fieldname": "payment_entry_docstatus_before", "label": _("PE Before"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_docstatus_after", "label": _("PE After"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_amount", "label": _("PE Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "invoice_outstanding_before_rollback_total", "label": _("Outstanding Before Rollback"), "fieldtype": "Currency", "options": "currency", "width": 180},
        {"fieldname": "invoice_outstanding_after_rollback_total", "label": _("Outstanding After Rollback"), "fieldtype": "Currency", "options": "currency", "width": 180},
        {"fieldname": "payment_entry_gl_count_after_rollback", "label": _("PE GL Rows After"), "fieldtype": "Int", "width": 130},
        {"fieldname": "payment_entry_gl_net_after_rollback", "label": _("PE GL Net After"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "ready_for_freeze", "label": _("Ready Freeze"), "fieldtype": "Check", "width": 110},
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
        {"fieldname": "line", "label": _("Line"), "fieldtype": "Link", "options": "NDIS Controlled Production Batch Smoke Rollback Line", "width": 220},
        {"fieldname": "rollback_run", "label": _("Rollback Run"), "fieldtype": "Link", "options": "NDIS Controlled Production Batch Smoke Rollback Run", "width": 220},
        {"fieldname": "line_no", "label": _("Line No"), "fieldtype": "Int", "width": 80},
        {"fieldname": "line_status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "sales_invoice", "label": _("Sales Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 170},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 170},
        {"fieldname": "allocated_amount", "label": _("Allocated"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "invoice_outstanding_before_rollback", "label": _("Outstanding Before Rollback"), "fieldtype": "Currency", "options": "currency", "width": 190},
        {"fieldname": "invoice_outstanding_after_rollback", "label": _("Outstanding After Rollback"), "fieldtype": "Currency", "options": "currency", "width": 190},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            l.name AS line,
            l.rollback_run,
            l.line_no,
            l.line_status,
            l.sales_invoice,
            l.payment_entry,
            l.allocated_amount,
            l.invoice_outstanding_before_rollback,
            l.invoice_outstanding_after_rollback,
            %(currency)s AS currency
        FROM `tabNDIS Controlled Production Batch Smoke Rollback Line` l
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
        {"value": len([row for row in data if row.line_status == "Restored"]), "indicator": "Green", "label": _("Restored"), "datatype": "Int"},
        {"value": sum(flt(row.invoice_outstanding_after_rollback or 0) for row in data), "indicator": "Blue", "label": _("Outstanding Restored"), "datatype": "Currency", "currency": currency()},
    ]

    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_rollback_report(filters)

    guard = guardrails()

    summary.append({"value": guard["payment_entry_count"], "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"})
    summary.append({"value": guard["payment_entry_gl_count"], "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"})
    summary.append({"value": guard["submitted_phase8e_smoke_pe_count"], "indicator": "Green", "label": _("Submitted Phase 8E Smoke PE"), "datatype": "Int"})
    summary.append({"value": guard["cancelled_phase8e_smoke_pe_count"], "indicator": "Orange", "label": _("Cancelled Phase 8E Smoke PE"), "datatype": "Int"})
    summary.append({"value": guard["submitted_journal_entry_count_today"], "indicator": "Red", "label": _("Submitted JE Today"), "datatype": "Int"})
    summary.append({"value": guard["purchase_invoice_count_today"], "indicator": "Red", "label": _("Purchase Invoice Today"), "datatype": "Int"})
    summary.append({"value": guard["production_batch_enabled_policy_count"], "indicator": "Red", "label": _("Production Batch Enabled Policies"), "datatype": "Int"})
    summary.append({"value": guard["live_posting_allowed_policy_count"], "indicator": "Red", "label": _("Live Posting Allowed Policies"), "datatype": "Int"})

    return columns, data, message, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
