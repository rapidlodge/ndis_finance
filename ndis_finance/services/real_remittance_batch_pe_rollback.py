import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


ROLLBACK_ACK = "I_CONFIRM_PHASE7G_CANCEL_CONTROLLED_BATCH_PAYMENT_ENTRY_SMOKE"
RUN_DOCTYPE = "NDIS Real Remittance Batch PE Rollback Run"
LINE_DOCTYPE = "NDIS Real Remittance Batch PE Rollback Line"
SMOKE_RUN_DOCTYPE = "NDIS Real Remittance Batch PE Smoke Run"
SMOKE_LINE_DOCTYPE = "NDIS Real Remittance Batch PE Smoke Line"


def make_rollback_run_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-REAL-REMITTANCE-BATCH-PE-ROLLBACK-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def tagged_pe_count(docstatus):
    if not frappe.db.has_column("Payment Entry", "custom_ndis_real_remittance_batch_pe_smoke"):
        return 0
    return count_dt("Payment Entry", {"docstatus": docstatus, "custom_ndis_real_remittance_batch_pe_smoke": 1})


def guardrails(payment_entry=None):
    data = {
        "payment_entry_count": count_dt("Payment Entry"),
        "payment_entry_gl_count": count_dt("GL Entry", {"voucher_type": "Payment Entry"}),
        "submitted_journal_entry_count_today": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}),
        "purchase_invoice_count_today": count_dt("Purchase Invoice", {"creation": [">=", today()]}),
        "batch_live_enabled_policy_count": count_dt("NDIS Real Remittance Batch Posting Policy", {"batch_live_enabled": 1}),
        "production_live_enabled_policy_count": count_dt("NDIS PE Production Posting Policy", {"production_posting_enabled": 1}),
        "submitted_tagged_pe_count_after": tagged_pe_count(1),
        "cancelled_tagged_pe_count_after": tagged_pe_count(2),
    }
    if payment_entry:
        data["payment_entry_gl_count_specific"] = count_dt("GL Entry", {"voucher_type": "Payment Entry", "voucher_no": payment_entry})
    return data


def latest_smoke_run():
    rows = frappe.get_all(
        SMOKE_RUN_DOCTYPE,
        filters={
            "status": "Submitted",
            "controlled_smoke_submitted": 1,
            "rollback_required": 1,
            "freeze_required_after_rollback": 1,
            "batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "payment_entry": ["!=", ""],
        },
        fields=[
            "name",
            "smoke_run_id",
            "source_run",
            "activation_gate",
            "adapter_run",
            "batch_preview",
            "design_gate",
            "company",
            "customer",
            "payment_entry",
            "invoice_count",
            "payment_entry_reference_count",
            "payment_entry_amount",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return frappe._dict(rows[0]) if rows else None


def existing_completed_rollback(smoke_run):
    if not smoke_run or not frappe.db.exists("DocType", RUN_DOCTYPE):
        return None
    rows = frappe.get_all(
        RUN_DOCTYPE,
        filters={"smoke_run": smoke_run, "rollback_completed": 1, "status": "Rolled Back"},
        fields=["name", "rollback_run_id"],
        limit=1,
    )
    return rows[0] if rows else None


def get_smoke_lines(smoke_run):
    if not smoke_run:
        return []
    return frappe.get_all(
        SMOKE_LINE_DOCTYPE,
        filters={"smoke_run": smoke_run, "line_status": "Submitted"},
        fields=[
            "name",
            "line_no",
            "source_run",
            "sales_invoice",
            "payment_entry",
            "allocated_amount",
            "invoice_outstanding_before",
            "invoice_outstanding_after",
        ],
        order_by="line_no asc, creation asc",
    )


def gl_count_and_net(payment_entry):
    if not payment_entry:
        return 0, 0
    rows = frappe.db.sql(
        """
        SELECT COUNT(*) AS gl_count, COALESCE(SUM(debit - credit), 0) AS gl_net
        FROM `tabGL Entry`
        WHERE voucher_type = 'Payment Entry'
        AND voucher_no = %(payment_entry)s
        """,
        {"payment_entry": payment_entry},
        as_dict=True,
    )
    return int(rows[0].gl_count or 0), flt(rows[0].gl_net or 0, 2)


def invoice_outstanding_total(lines):
    total = 0
    for line in lines:
        if line.sales_invoice and frappe.db.exists("Sales Invoice", line.sales_invoice):
            total += flt(frappe.db.get_value("Sales Invoice", line.sales_invoice, "outstanding_amount") or 0)
    return flt(total, 2)


def validate_smoke(smoke, lines):
    blockers = []
    warnings = []
    if not smoke:
        blockers.append("No submitted Phase 7F smoke run found.")
        return blockers, warnings

    existing = existing_completed_rollback(smoke.name)
    if existing:
        blockers.append(f"A completed rollback already exists for this Phase 7F smoke run: {existing.name}.")

    if not smoke.payment_entry or not frappe.db.exists("Payment Entry", smoke.payment_entry):
        blockers.append("Phase 7F smoke Payment Entry is missing.")
    else:
        pe = frappe.get_doc("Payment Entry", smoke.payment_entry)
        if pe.docstatus != 1:
            blockers.append(f"Payment Entry {pe.name} is not submitted. Current docstatus: {pe.docstatus}.")
        if pe.meta.has_field("custom_ndis_real_remittance_batch_pe_smoke") and not int(pe.custom_ndis_real_remittance_batch_pe_smoke or 0):
            blockers.append(f"Payment Entry {pe.name} is not tagged as Phase 7F smoke.")
        if pe.meta.has_field("custom_ndis_real_remittance_batch_pe_smoke_run") and pe.custom_ndis_real_remittance_batch_pe_smoke_run != smoke.name:
            blockers.append(f"Payment Entry {pe.name} is not linked to smoke run {smoke.name}.")

    if not lines:
        blockers.append("No submitted Phase 7F smoke lines found.")
    if len(lines) != int(smoke.payment_entry_reference_count or 0):
        warnings.append(f"Smoke run reference count {smoke.payment_entry_reference_count}; smoke lines found {len(lines)}.")

    total_outstanding = invoice_outstanding_total(lines)
    if flt(total_outstanding) != 0:
        blockers.append(f"Source invoice outstanding before rollback should be 0.00, found {total_outstanding}.")

    pe_gl_count, pe_gl_net = gl_count_and_net(smoke.payment_entry)
    if pe_gl_count <= 0:
        blockers.append("Payment Entry GL rows not found before rollback.")
    if flt(pe_gl_net) != 0:
        blockers.append(f"Payment Entry GL net before rollback is not 0.00. Found {pe_gl_net}.")
    return blockers, warnings


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
    score = 100 - int(blockers or 0) * 25 - int(warnings or 0) * 5
    return max(0, round(score, 2))


def create_rollback_line(rollback_run, smoke, smoke_line, outstanding_before):
    outstanding_after = frappe.db.get_value("Sales Invoice", smoke_line.sales_invoice, "outstanding_amount") or 0
    doc = frappe.new_doc(LINE_DOCTYPE)
    doc.rollback_run = rollback_run
    doc.line_no = smoke_line.line_no
    doc.line_label = f"Phase 7G Rollback Line {smoke_line.line_no}"
    doc.line_status = "Restored"
    doc.smoke_run = smoke.name
    doc.smoke_line = smoke_line.name
    doc.source_run = smoke.source_run
    doc.sales_invoice = smoke_line.sales_invoice
    doc.payment_entry = smoke.payment_entry
    doc.invoice_outstanding_before_rollback = flt(outstanding_before or 0)
    doc.rollback_amount = flt(smoke_line.allocated_amount or 0)
    doc.invoice_outstanding_after_rollback = flt(outstanding_after or 0)
    doc.checked_on = now_datetime()
    doc.insert(ignore_permissions=True)


@frappe.whitelist()
def run_real_remittance_batch_pe_rollback(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_real_remittance_batch_pe_rollback")

    smoke = latest_smoke_run()
    lines = get_smoke_lines(smoke.name) if smoke else []
    config = config_state()
    guard_before = guardrails(smoke.payment_entry if smoke else None)
    ack_ok = acknowledgement == ROLLBACK_ACK
    blockers, warnings = validate_smoke(smoke, lines)

    items = []
    add_item(items, "Pass" if not config["production_mode"] else "Blocker", "Critical" if config["production_mode"] else "Low", "Site Config", "production_mode", "Production mode", "Production mode remains disabled." if not config["production_mode"] else "Production mode is enabled.")
    add_item(items, "Pass" if not config["live_pe_enabled"] else "Blocker", "Critical" if config["live_pe_enabled"] else "Low", "Site Config", "live_pe_enabled", "Live PE posting", "Live PE posting remains disabled." if not config["live_pe_enabled"] else "Live PE posting config is enabled.")
    live_policy_count = guard_before["batch_live_enabled_policy_count"] + guard_before["production_live_enabled_policy_count"]
    add_item(items, "Pass" if live_policy_count == 0 else "Blocker", "Critical" if live_policy_count else "Low", "Guardrail", "live_policies", "Live policies", "No live-enabled batch or production PE policies." if live_policy_count == 0 else "Live-enabled policy exists.")
    for blocker in blockers:
        add_item(items, "Blocker", "Critical", "Rollback Validation", "blocker", "Blocker", blocker)
    for warning in warnings:
        add_item(items, "Warning", "Medium", "Rollback Validation", "warning", "Warning", warning)
    add_item(items, "Pass" if ack_ok else "Warning", "Low" if ack_ok else "Medium", "Acknowledgement", "rollback_ack", "Rollback acknowledgement", "Exact acknowledgement supplied." if ack_ok else f"Required acknowledgement not supplied: {ROLLBACK_ACK}")

    item_summary = summarise_items(items)
    rollback_allowed = int(ack_ok and item_summary["blocker_count"] == 0)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    pe_docstatus_before = 0
    pe_gl_count_before_specific = 0
    pe_gl_net_before_specific = 0
    if smoke and smoke.payment_entry and frappe.db.exists("Payment Entry", smoke.payment_entry):
        pe_docstatus_before = frappe.db.get_value("Payment Entry", smoke.payment_entry, "docstatus")
        pe_gl_count_before_specific, pe_gl_net_before_specific = gl_count_and_net(smoke.payment_entry)

    invoice_outstanding_before_total = invoice_outstanding_total(lines)
    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Rolled Back" if rollback_allowed else "Needs Review",
        "rollback_status": "Rolled Back - Freeze Required" if rollback_allowed else "Audit Only",
        "rollback_completed": 0,
        "ready_for_freeze": 0,
        "controlled_payment_entry_cancelled": 0,
        "batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "smoke_run": smoke.name if smoke else None,
        "source_run": smoke.source_run if smoke else None,
        "activation_gate": smoke.activation_gate if smoke else None,
        "adapter_run": smoke.adapter_run if smoke else None,
        "batch_preview": smoke.batch_preview if smoke else None,
        "design_gate": smoke.design_gate if smoke else None,
        "company": smoke.company if smoke else None,
        "customer": smoke.customer if smoke else None,
        "payment_entry": smoke.payment_entry if smoke else None,
        "payment_entry_docstatus_before": pe_docstatus_before,
        "payment_entry_docstatus_after": pe_docstatus_before,
        "invoice_count": len(lines),
        "payment_entry_reference_count": int(smoke.payment_entry_reference_count or 0) if smoke else 0,
        "payment_entry_amount": flt(smoke.payment_entry_amount or 0) if smoke else 0,
        "invoice_outstanding_before_total": invoice_outstanding_before_total,
        "invoice_outstanding_after_total": invoice_outstanding_before_total,
        "payment_entry_gl_count_before_specific": pe_gl_count_before_specific,
        "payment_entry_gl_count_after_specific": pe_gl_count_before_specific,
        "payment_entry_gl_net_after_specific": pe_gl_net_before_specific,
        "rollback_score": score,
        **item_summary,
        "items": items,
        "guardrails_before": guard_before,
        "guardrails_after": guardrails(smoke.payment_entry if smoke else None),
        "config": config,
        "required_acknowledgement": ROLLBACK_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 7G cancels only the tagged controlled Phase 7F Payment Entry. No Journal Entry or Purchase Invoice is created.",
    }
    if int(dry_run or 0):
        return result

    run = frappe.new_doc(RUN_DOCTYPE)
    run.rollback_run_id = make_rollback_run_id()
    for fieldname in [
        "status",
        "rollback_status",
        "rollback_completed",
        "ready_for_freeze",
        "controlled_payment_entry_cancelled",
        "batch_posting_allowed",
        "real_posting_allowed",
        "smoke_run",
        "source_run",
        "activation_gate",
        "adapter_run",
        "batch_preview",
        "design_gate",
        "company",
        "customer",
        "payment_entry",
        "payment_entry_docstatus_before",
        "payment_entry_docstatus_after",
        "invoice_count",
        "payment_entry_reference_count",
        "payment_entry_amount",
        "invoice_outstanding_before_total",
        "invoice_outstanding_after_total",
        "payment_entry_gl_count_before_specific",
        "payment_entry_gl_count_after_specific",
        "payment_entry_gl_net_after_specific",
        "rollback_score",
        "blocker_count",
        "warning_count",
        "pass_count",
        "info_count",
        "item_count",
    ]:
        setattr(run, fieldname, result.get(fieldname))
    run.site_name = frappe.local.site
    run.sandbox_config_enabled = config["sandbox_enabled"]
    run.production_mode_detected = config["production_mode"]
    run.live_payment_entry_posting_config = config["live_pe_enabled"]
    run.checked_on = now_datetime()
    run.checked_by = frappe.session.user
    run.payment_entry_count_before = guard_before["payment_entry_count"]
    run.payment_entry_count_after = guard_before["payment_entry_count"]
    run.payment_entry_gl_count_before = guard_before["payment_entry_gl_count"]
    run.payment_entry_gl_count_after = guard_before["payment_entry_gl_count"]
    run.submitted_tagged_pe_count_after = guard_before["submitted_tagged_pe_count_after"]
    run.cancelled_tagged_pe_count_after = guard_before["cancelled_tagged_pe_count_after"]
    run.submitted_journal_entry_count_today = guard_before["submitted_journal_entry_count_today"]
    run.purchase_invoice_count_today = guard_before["purchase_invoice_count_today"]
    run.batch_live_enabled_policy_count = guard_before["batch_live_enabled_policy_count"]
    run.production_live_enabled_policy_count = guard_before["production_live_enabled_policy_count"]
    run.required_acknowledgement = ROLLBACK_ACK
    run.acknowledgement = acknowledgement
    run.acknowledgement_ok = int(ack_ok)
    run.summary_json = safe_json(result)
    run.notes = notes
    run.insert(ignore_permissions=True)

    if rollback_allowed:
        outstanding_before = {
            line.name: flt(frappe.db.get_value("Sales Invoice", line.sales_invoice, "outstanding_amount") or 0)
            for line in lines
        }
        pe = frappe.get_doc("Payment Entry", smoke.payment_entry)
        pe.flags.ignore_permissions = True
        pe.cancel()
        for line in lines:
            create_rollback_line(run.name, smoke, line, outstanding_before.get(line.name))

    pe_docstatus_after = pe_docstatus_before
    pe_gl_count_after_specific = pe_gl_count_before_specific
    pe_gl_net_after_specific = pe_gl_net_before_specific
    if smoke and smoke.payment_entry and frappe.db.exists("Payment Entry", smoke.payment_entry):
        pe_docstatus_after = frappe.db.get_value("Payment Entry", smoke.payment_entry, "docstatus")
        pe_gl_count_after_specific, pe_gl_net_after_specific = gl_count_and_net(smoke.payment_entry)

    guard_after = guardrails(smoke.payment_entry if smoke else None)
    updates = {
        "rollback_completed": 1 if rollback_allowed else 0,
        "ready_for_freeze": 1 if rollback_allowed else 0,
        "controlled_payment_entry_cancelled": 1 if rollback_allowed else 0,
        "payment_entry_docstatus_after": pe_docstatus_after,
        "invoice_outstanding_after_total": invoice_outstanding_total(lines),
        "payment_entry_gl_count_after_specific": pe_gl_count_after_specific,
        "payment_entry_gl_net_after_specific": pe_gl_net_after_specific,
        "payment_entry_count_after": guard_after["payment_entry_count"],
        "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
        "submitted_tagged_pe_count_after": guard_after["submitted_tagged_pe_count_after"],
        "cancelled_tagged_pe_count_after": guard_after["cancelled_tagged_pe_count_after"],
    }
    result.update(updates)
    result["created"] = True
    result["rollback_run"] = run.name
    result["rollback_run_id"] = run.rollback_run_id
    result["guardrails_after"] = guard_after
    updates["summary_json"] = safe_json(result)
    frappe.db.set_value(RUN_DOCTYPE, run.name, updates, update_modified=False)
    frappe.db.commit()
    return result


@frappe.whitelist()
def cancel_real_remittance_batch_pe_rollback(rollback_run, reason=None):
    assert_action("cancel_real_remittance_batch_pe_rollback")
    if not frappe.db.exists(RUN_DOCTYPE, rollback_run):
        frappe.throw(_("Rollback run not found: {0}").format(rollback_run))
    doc = frappe.get_doc(RUN_DOCTYPE, rollback_run)
    if doc.status == "Cancelled":
        return {"rollback_run": rollback_run, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.rollback_completed or 0):
        frappe.throw(_("Cannot cancel a completed rollback evidence run. Freeze it in Phase 7H instead."))
    frappe.db.set_value(
        RUN_DOCTYPE,
        rollback_run,
        {
            "status": "Cancelled",
            "rollback_status": "Cancelled",
            "rollback_completed": 0,
            "ready_for_freeze": 0,
            "controlled_payment_entry_cancelled": 0,
            "batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 7G rollback audit cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{LINE_DOCTYPE}` SET line_status = 'Cancelled' WHERE rollback_run = %(rollback_run)s", {"rollback_run": rollback_run})
    frappe.db.commit()
    return {"rollback_run": rollback_run, "status": "Cancelled", "note": "Rollback audit record cancelled only. No accounting movement occurred."}


@frappe.whitelist()
def quick_real_remittance_batch_pe_rollback_summary(limit=20):
    runs = frappe.get_all(
        RUN_DOCTYPE,
        fields=[
            "name",
            "rollback_run_id",
            "status",
            "rollback_status",
            "rollback_completed",
            "ready_for_freeze",
            "controlled_payment_entry_cancelled",
            "batch_posting_allowed",
            "real_posting_allowed",
            "smoke_run",
            "source_run",
            "company",
            "customer",
            "payment_entry",
            "payment_entry_docstatus_before",
            "payment_entry_docstatus_after",
            "invoice_count",
            "payment_entry_amount",
            "invoice_outstanding_before_total",
            "invoice_outstanding_after_total",
            "payment_entry_gl_count_before_specific",
            "payment_entry_gl_count_after_specific",
            "payment_entry_gl_net_after_specific",
            "submitted_tagged_pe_count_after",
            "cancelled_tagged_pe_count_after",
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
            "rollback_run",
            "line_no",
            "line_status",
            "sales_invoice",
            "payment_entry",
            "invoice_outstanding_before_rollback",
            "rollback_amount",
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
        "note": "Phase 7G rollback summary. Controlled PE cancelled; freeze evidence required next.",
    }


def rollback_columns():
    return [
        {"fieldname": "rollback_run", "label": _("Rollback Run"), "fieldtype": "Link", "options": RUN_DOCTYPE, "width": 220},
        {"fieldname": "rollback_run_id", "label": _("Rollback Run ID"), "fieldtype": "Data", "width": 400},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "rollback_status", "label": _("Rollback Status"), "fieldtype": "Data", "width": 260},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 170},
        {"fieldname": "payment_entry_docstatus_after", "label": _("PE Docstatus After"), "fieldtype": "Int", "width": 140},
        {"fieldname": "invoice_count", "label": _("Invoices"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_amount", "label": _("PE Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "invoice_outstanding_before_total", "label": _("Outstanding Before"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "invoice_outstanding_after_total", "label": _("Outstanding After"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "payment_entry_gl_count_after_specific", "label": _("PE GL Rows After"), "fieldtype": "Int", "width": 130},
        {"fieldname": "payment_entry_gl_net_after_specific", "label": _("PE GL Net After"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "submitted_tagged_pe_count_after", "label": _("Submitted Tagged PE"), "fieldtype": "Int", "width": 150},
        {"fieldname": "cancelled_tagged_pe_count_after", "label": _("Cancelled Tagged PE"), "fieldtype": "Int", "width": 150},
        {"fieldname": "ready_for_freeze", "label": _("Ready Freeze"), "fieldtype": "Check", "width": 110},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_rollback_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("r.status = %(status)s")
        params["status"] = filters.get("status")
    if filters.get("from_date"):
        conditions.append("DATE(r.checked_on) >= %(from_date)s")
        params["from_date"] = filters.get("from_date")
    if filters.get("to_date"):
        conditions.append("DATE(r.checked_on) <= %(to_date)s")
        params["to_date"] = filters.get("to_date")
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
            r.batch_posting_allowed,
            r.real_posting_allowed,
            r.smoke_run,
            r.source_run,
            r.company,
            r.customer,
            r.payment_entry,
            r.payment_entry_docstatus_before,
            r.payment_entry_docstatus_after,
            r.invoice_count,
            r.payment_entry_amount,
            r.invoice_outstanding_before_total,
            r.invoice_outstanding_after_total,
            r.payment_entry_gl_count_before_specific,
            r.payment_entry_gl_count_after_specific,
            r.payment_entry_gl_net_after_specific,
            r.submitted_tagged_pe_count_after,
            r.cancelled_tagged_pe_count_after,
            r.checked_on,
            %(currency)s AS currency
        FROM `tab{RUN_DOCTYPE}` r
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
                {"name": "Cancelled Tagged PE", "values": [int(row.cancelled_tagged_pe_count_after or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Rollback Runs"), "datatype": "Int"},
        {"value": sum(int(row.rollback_completed or 0) for row in data), "indicator": "Green", "label": _("Completed"), "datatype": "Int"},
        {"value": sum(flt(row.payment_entry_amount or 0) for row in data), "indicator": "Blue", "label": _("Rollback Amount"), "datatype": "Currency", "currency": currency()},
        {"value": sum(int(row.submitted_tagged_pe_count_after or 0) for row in data), "indicator": "Red", "label": _("Submitted Tagged PE After"), "datatype": "Int"},
    ]
    return rollback_columns(), data, None, chart, summary


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
        {"fieldname": "line", "label": _("Line"), "fieldtype": "Link", "options": LINE_DOCTYPE, "width": 220},
        {"fieldname": "rollback_run", "label": _("Rollback Run"), "fieldtype": "Link", "options": RUN_DOCTYPE, "width": 220},
        {"fieldname": "line_no", "label": _("Line No"), "fieldtype": "Int", "width": 80},
        {"fieldname": "line_status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "sales_invoice", "label": _("Sales Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 170},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 170},
        {"fieldname": "invoice_outstanding_before_rollback", "label": _("Outstanding Before Rollback"), "fieldtype": "Currency", "options": "currency", "width": 190},
        {"fieldname": "rollback_amount", "label": _("Rollback Amount"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "invoice_outstanding_after_rollback", "label": _("Outstanding After Rollback"), "fieldtype": "Currency", "options": "currency", "width": 190},
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
            l.sales_invoice,
            l.payment_entry,
            l.invoice_outstanding_before_rollback,
            l.rollback_amount,
            l.invoice_outstanding_after_rollback,
            l.checked_on,
            %(currency)s AS currency
        FROM `tab{LINE_DOCTYPE}` l
        {build_where(conditions)}
        ORDER BY l.rollback_run DESC, l.line_no ASC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [str(row.line_no) for row in data[:20]],
            "datasets": [{"name": "Restored Outstanding", "values": [flt(row.invoice_outstanding_after_rollback or 0) for row in data[:20]]}],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Lines"), "datatype": "Int"},
        {"value": sum(flt(row.rollback_amount or 0) for row in data), "indicator": "Green", "label": _("Rollback Amount"), "datatype": "Currency", "currency": currency()},
        {"value": sum(flt(row.invoice_outstanding_after_rollback or 0) for row in data), "indicator": "Blue", "label": _("Outstanding Restored"), "datatype": "Currency", "currency": currency()},
    ]
    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_rollback_report(filters)
    summary.extend(
        [
            {"value": count_dt("Payment Entry"), "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"},
            {"value": count_dt("GL Entry", {"voucher_type": "Payment Entry"}), "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"},
            {"value": tagged_pe_count(1), "indicator": "Red", "label": _("Submitted Tagged PE"), "datatype": "Int"},
            {"value": tagged_pe_count(2), "indicator": "Green", "label": _("Cancelled Tagged PE"), "datatype": "Int"},
            {"value": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}), "indicator": "Red", "label": _("Submitted JEs Today"), "datatype": "Int"},
            {"value": count_dt("Purchase Invoice", {"creation": [">=", today()]}), "indicator": "Red", "label": _("Purchase Invoices Today"), "datatype": "Int"},
        ]
    )
    return columns, data, message, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
