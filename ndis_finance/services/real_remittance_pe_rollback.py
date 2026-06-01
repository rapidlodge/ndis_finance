import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


RUN_DOCTYPE = "NDIS Real Remittance PE Rollback Run"
LINE_DOCTYPE = "NDIS Real Remittance PE Rollback Line"
SMOKE_DOCTYPE = "NDIS Real Remittance PE Smoke Run"
ROLLBACK_ACK = "I_CONFIRM_PHASE6G_CANCEL_ONE_CONTROLLED_REMITTANCE_PAYMENT_ENTRY"


def make_rollback_run_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-REAL-REMITTANCE-PE-ROLLBACK-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def guardrails():
    return {
        "payment_entry_count": count_dt("Payment Entry"),
        "payment_entry_gl_count": count_dt("GL Entry", {"voucher_type": "Payment Entry"}),
        "submitted_journal_entry_count_today": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}),
        "purchase_invoice_count_today": count_dt("Purchase Invoice", {"creation": [">=", today()]}),
        "live_enabled_policy_count": count_dt("NDIS PE Production Posting Policy", {"production_posting_enabled": 1}),
    }


def config_state():
    return {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def gl_count(voucher_type, voucher_no):
    if not voucher_no:
        return 0
    return count_dt("GL Entry", {"voucher_type": voucher_type, "voucher_no": voucher_no})


def gl_net(voucher_type, voucher_no):
    if not voucher_no:
        return 0
    value = frappe.db.sql(
        """
        SELECT COALESCE(SUM(debit - credit), 0)
        FROM `tabGL Entry`
        WHERE voucher_type = %(voucher_type)s
        AND voucher_no = %(voucher_no)s
        """,
        {"voucher_type": voucher_type, "voucher_no": voucher_no},
    )[0][0]
    return flt(value, 2)


def latest_submitted_smoke_run():
    rows = frappe.get_all(
        SMOKE_DOCTYPE,
        filters={
            "status": "Submitted",
            "payment_entry_created": 1,
            "payment_entry_submitted": 1,
            "real_posting_allowed": 0,
        },
        fields=[
            "name",
            "smoke_run_id",
            "source_harness_run",
            "sales_invoice",
            "payment_entry",
            "company",
            "customer",
            "bank_account",
            "receivable_account",
            "payment_amount",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def create_rollback_line(rollback_run, record_type, record_doctype, record_name, label, status="Info", amount=0, detail=None):
    row = frappe.new_doc(LINE_DOCTYPE)
    row.rollback_run = rollback_run
    row.record_type = record_type
    row.record_doctype = record_doctype
    row.record_name = record_name
    row.record_label = label
    row.status = status
    row.amount = flt(amount or 0)
    row.detail = detail
    row.checked_on = now_datetime()
    row.insert(ignore_permissions=True)


def validate_smoke_source(smoke):
    if not smoke:
        frappe.throw(_("No submitted Phase 6F controlled real remittance smoke run found."))
    if not smoke.payment_entry or not frappe.db.exists("Payment Entry", smoke.payment_entry):
        frappe.throw(_("Phase 6F smoke run is missing its controlled Payment Entry."))
    if not smoke.sales_invoice or not frappe.db.exists("Sales Invoice", smoke.sales_invoice):
        frappe.throw(_("Phase 6F smoke run is missing its controlled Sales Invoice."))

    pe = frappe.get_doc("Payment Entry", smoke.payment_entry)
    si = frappe.get_doc("Sales Invoice", smoke.sales_invoice)

    if pe.docstatus != 1:
        frappe.throw(_("Controlled Payment Entry must be submitted before rollback. Current docstatus: {0}").format(pe.docstatus))
    if not int(getattr(pe, "custom_ndis_real_remittance_pe_smoke", 0) or 0):
        frappe.throw(_("Payment Entry is not tagged as a Phase 6F controlled smoke Payment Entry."))
    if getattr(pe, "custom_ndis_real_remittance_pe_smoke_run", None) != smoke.name:
        frappe.throw(_("Payment Entry smoke run tag does not match the selected Phase 6F run."))
    if getattr(pe, "custom_ndis_real_remittance_pe_source_invoice", None) != si.name:
        frappe.throw(_("Payment Entry source invoice tag does not match the controlled invoice."))
    if si.docstatus != 1:
        frappe.throw(_("Controlled source Sales Invoice must remain submitted. Current docstatus: {0}").format(si.docstatus))
    if not int(getattr(si, "custom_ndis_real_remittance_pe_harness_invoice", 0) or 0):
        frappe.throw(_("Sales Invoice is not tagged as a Phase 6E controlled harness invoice."))
    if flt(si.outstanding_amount, 2) != 0:
        frappe.throw(_("Controlled Sales Invoice outstanding must be 0.00 before rollback. Current: {0}").format(flt(si.outstanding_amount, 2)))
    if flt(pe.paid_amount, 2) != 1:
        frappe.throw(_("Phase 6G expects exactly 1.00 on the controlled Payment Entry. Current: {0}").format(flt(pe.paid_amount, 2)))
    if gl_count("Payment Entry", pe.name) != 2:
        frappe.throw(_("Submitted controlled Payment Entry must have exactly 2 GL rows before rollback."))
    if flt(gl_net("Payment Entry", pe.name), 2) != 0:
        frappe.throw(_("Submitted controlled Payment Entry GL net must be 0.00 before rollback."))

    return pe, si


def build_base_result(smoke, pe=None, si=None, dry_run=1, acknowledgement=None, notes=None):
    guard_before = guardrails()
    return {
        "dry_run": bool(int(dry_run or 0)),
        "acknowledgement_ok": acknowledgement == ROLLBACK_ACK,
        "required_acknowledgement": ROLLBACK_ACK,
        "smoke_run": smoke.name if smoke else None,
        "smoke_run_id": smoke.smoke_run_id if smoke else None,
        "source_harness_run": smoke.source_harness_run if smoke else None,
        "sales_invoice": si.name if si else (smoke.sales_invoice if smoke else None),
        "payment_entry": pe.name if pe else (smoke.payment_entry if smoke else None),
        "payment_amount": flt(pe.paid_amount if pe else (smoke.payment_amount if smoke else 0)),
        "invoice_outstanding_before_rollback": flt(si.outstanding_amount if si else 0),
        "payment_entry_docstatus_before": pe.docstatus if pe else None,
        "payment_entry_gl_count_before": gl_count("Payment Entry", pe.name) if pe else 0,
        "payment_entry_gl_net_before": gl_net("Payment Entry", pe.name) if pe else 0,
        "rollback_allowed": 0,
        "payment_entry_cancelled": 0,
        "source_invoice_restored": 0,
        "real_posting_allowed": 0,
        "guardrails_before": guard_before,
        "guardrails_after": guardrails(),
        "config": config_state(),
        "notes": notes,
        "note": "Phase 6G cancels one controlled Phase 6F Payment Entry only when exact acknowledgement and rollback controls pass.",
    }


@frappe.whitelist()
def run_real_remittance_pe_smoke_rollback(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_real_remittance_pe_smoke_rollback")
    config = config_state()
    ack_ok = acknowledgement == ROLLBACK_ACK
    smoke = latest_submitted_smoke_run()
    pe = None
    si = None
    if smoke:
        pe, si = validate_smoke_source(smoke)

    result = build_base_result(smoke, pe, si, dry_run=dry_run, acknowledgement=acknowledgement, notes=notes)
    if int(dry_run or 0):
        result["status"] = "Previewed"
        return result

    guard_before = result["guardrails_before"]
    run = frappe.new_doc(RUN_DOCTYPE)
    run.rollback_run_id = make_rollback_run_id()
    run.status = "Needs Review"
    run.rollback_type = "Controlled Real Remittance Payment Entry Rollback"
    run.rollback_allowed = 0
    run.payment_entry_cancelled = 0
    run.source_invoice_restored = 0
    run.real_posting_allowed = 0
    run.smoke_run = smoke.name if smoke else None
    run.source_harness_run = smoke.source_harness_run if smoke else None
    run.sales_invoice = si.name if si else None
    run.payment_entry = pe.name if pe else None
    run.company = smoke.company if smoke else None
    run.customer = smoke.customer if smoke else None
    run.bank_account = smoke.bank_account if smoke else None
    run.receivable_account = smoke.receivable_account if smoke else None
    run.payment_amount = flt(pe.paid_amount if pe else 0)
    run.invoice_outstanding_before_rollback = flt(si.outstanding_amount if si else 0)
    run.payment_entry_docstatus_before = pe.docstatus if pe else None
    run.payment_entry_gl_count_before = gl_count("Payment Entry", pe.name) if pe else 0
    run.payment_entry_gl_net_before = gl_net("Payment Entry", pe.name) if pe else 0
    run.site_name = frappe.local.site
    run.sandbox_config_enabled = config["sandbox_enabled"]
    run.production_mode_detected = config["production_mode"]
    run.live_payment_entry_posting_config = config["live_pe_enabled"]
    run.checked_on = now_datetime()
    run.checked_by = frappe.session.user
    run.payment_entry_count_before = guard_before["payment_entry_count"]
    run.payment_entry_gl_count_before_total = guard_before["payment_entry_gl_count"]
    run.submitted_journal_entry_count_today = guard_before["submitted_journal_entry_count_today"]
    run.purchase_invoice_count_today = guard_before["purchase_invoice_count_today"]
    run.live_enabled_policy_count = guard_before["live_enabled_policy_count"]
    run.required_acknowledgement = ROLLBACK_ACK
    run.acknowledgement = acknowledgement
    run.acknowledgement_ok = int(ack_ok)
    run.notes = notes

    if not ack_ok:
        run.summary_json = safe_json(result)
        run.insert(ignore_permissions=True)
        create_rollback_line(run.name, "Payment Entry", "Payment Entry", pe.name if pe else None, "Controlled Payment Entry before rollback", "Validated", flt(pe.paid_amount if pe else 0), "No acknowledgement supplied; audit record only.")
        guard_after = guardrails()
        run.payment_entry_count_after = guard_after["payment_entry_count"]
        run.payment_entry_gl_count_after_total = guard_after["payment_entry_gl_count"]
        run.save(ignore_permissions=True)
        frappe.db.commit()
        result.update({"created": True, "rollback_run": run.name, "rollback_run_id": run.rollback_run_id, "status": run.status, "guardrails_after": guard_after})
        return result

    if config["production_mode"]:
        frappe.throw(_("Production mode config is enabled. Refusing Phase 6G rollback."))
    if config["live_pe_enabled"]:
        frappe.throw(_("Global live PE posting config is enabled. Phase 6G expects it to remain disabled."))
    if guard_before["live_enabled_policy_count"]:
        frappe.throw(_("Live-enabled PE policy exists. Refusing Phase 6G rollback."))

    run.rollback_allowed = 1
    run.insert(ignore_permissions=True)
    create_rollback_line(run.name, "Payment Entry", "Payment Entry", pe.name, "Controlled Payment Entry before rollback", "Validated", flt(pe.paid_amount), "Submitted Phase 6F controlled Payment Entry validated for rollback.")
    create_rollback_line(run.name, "Sales Invoice", "Sales Invoice", si.name, "Controlled source Sales Invoice before rollback", "Validated", flt(si.outstanding_amount), "Invoice was fully allocated before rollback.")

    pe.cancel()
    pe.reload()
    si.reload()

    pe_gl_count_after = gl_count("Payment Entry", pe.name)
    pe_gl_net_after = gl_net("Payment Entry", pe.name)
    guard_after = guardrails()

    run.status = "Rolled Back"
    run.payment_entry_cancelled = int(pe.docstatus == 2)
    run.source_invoice_restored = int(flt(si.outstanding_amount, 2) == 1)
    run.real_posting_allowed = 0
    run.invoice_outstanding_after_rollback = flt(si.outstanding_amount)
    run.payment_entry_docstatus_after = pe.docstatus
    run.payment_entry_gl_count_after = pe_gl_count_after
    run.payment_entry_gl_net_after = pe_gl_net_after
    run.payment_entry_count_after = guard_after["payment_entry_count"]
    run.payment_entry_gl_count_after_total = guard_after["payment_entry_gl_count"]

    create_rollback_line(run.name, "Payment Entry", "Payment Entry", pe.name, "Controlled Payment Entry cancelled", "Cancelled", flt(pe.paid_amount), "Payment Entry cancelled by Phase 6G controlled rollback.")
    create_rollback_line(run.name, "Sales Invoice", "Sales Invoice", si.name, "Controlled source Sales Invoice restored", "Restored", flt(si.outstanding_amount), "Invoice outstanding restored after Payment Entry cancellation.")

    if pe.docstatus != 2:
        frappe.throw(_("Payment Entry cancellation did not complete."))
    if flt(si.outstanding_amount, 2) != 1:
        frappe.throw(_("Sales Invoice outstanding was not restored to 1.00. Current: {0}").format(flt(si.outstanding_amount, 2)))
    if pe_gl_count_after != 4:
        frappe.throw(_("Payment Entry GL row count after rollback should be 4. Current: {0}").format(pe_gl_count_after))
    if flt(pe_gl_net_after, 2) != 0:
        frappe.throw(_("Payment Entry GL net after rollback should be 0.00. Current: {0}").format(flt(pe_gl_net_after, 2)))

    result.update(
        {
            "created": True,
            "rollback_run": run.name,
            "rollback_run_id": run.rollback_run_id,
            "status": run.status,
            "rollback_allowed": 1,
            "payment_entry_cancelled": run.payment_entry_cancelled,
            "source_invoice_restored": run.source_invoice_restored,
            "invoice_outstanding_after_rollback": flt(si.outstanding_amount),
            "payment_entry_docstatus_after": pe.docstatus,
            "payment_entry_gl_count_after": pe_gl_count_after,
            "payment_entry_gl_net_after": pe_gl_net_after,
            "guardrails_after": guard_after,
        }
    )
    run.summary_json = safe_json(result)
    run.save(ignore_permissions=True)
    frappe.db.commit()
    return result


@frappe.whitelist()
def cancel_real_remittance_pe_smoke_rollback_audit(rollback_run, reason=None):
    assert_action("cancel_real_remittance_pe_smoke_rollback_audit")
    if not frappe.db.exists(RUN_DOCTYPE, rollback_run):
        frappe.throw(_("Rollback run not found: {0}").format(rollback_run))
    doc = frappe.get_doc(RUN_DOCTYPE, rollback_run)
    if int(doc.payment_entry_cancelled or 0):
        frappe.throw(_("Cannot cancel a Phase 6G run that cancelled a Payment Entry."))
    frappe.db.set_value(
        RUN_DOCTYPE,
        rollback_run,
        {
            "status": "Cancelled",
            "rollback_allowed": 0,
            "payment_entry_cancelled": 0,
            "source_invoice_restored": 0,
            "real_posting_allowed": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 6G audit-only rollback run cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{LINE_DOCTYPE}` SET status = 'Cancelled' WHERE rollback_run = %(rollback_run)s", {"rollback_run": rollback_run})
    frappe.db.commit()
    return {"rollback_run": rollback_run, "status": "Cancelled", "note": "Audit-only Phase 6G rollback run cancelled. No Payment Entry was changed."}


@frappe.whitelist()
def quick_real_remittance_pe_rollback_summary(limit=20):
    runs = frappe.get_all(
        RUN_DOCTYPE,
        fields=[
            "name",
            "rollback_run_id",
            "status",
            "rollback_allowed",
            "payment_entry_cancelled",
            "source_invoice_restored",
            "real_posting_allowed",
            "sales_invoice",
            "payment_entry",
            "payment_amount",
            "invoice_outstanding_before_rollback",
            "invoice_outstanding_after_rollback",
            "payment_entry_docstatus_before",
            "payment_entry_docstatus_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "payment_entry_gl_net_before",
            "payment_entry_gl_net_after",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before_total",
            "payment_entry_gl_count_after_total",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    lines = frappe.get_all(
        LINE_DOCTYPE,
        fields=["name", "rollback_run", "record_type", "record_doctype", "record_name", "record_label", "status", "amount", "detail"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "runs": runs,
        "lines": lines,
        "required_acknowledgement": ROLLBACK_ACK,
        "guardrails": guardrails(),
        "config": config_state(),
        "note": "Phase 6G summary. One controlled Phase 6F Payment Entry should be cancelled after successful rollback.",
    }


def rollback_columns():
    return [
        {"fieldname": "rollback_run", "label": _("Rollback Run"), "fieldtype": "Link", "options": RUN_DOCTYPE, "width": 220},
        {"fieldname": "rollback_run_id", "label": _("Rollback Run ID"), "fieldtype": "Data", "width": 380},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "payment_entry_cancelled", "label": _("PE Cancelled"), "fieldtype": "Check", "width": 110},
        {"fieldname": "source_invoice_restored", "label": _("Invoice Restored"), "fieldtype": "Check", "width": 130},
        {"fieldname": "real_posting_allowed", "label": _("Real Posting Allowed"), "fieldtype": "Check", "width": 150},
        {"fieldname": "sales_invoice", "label": _("Sales Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 170},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 170},
        {"fieldname": "payment_amount", "label": _("Payment Amount"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "invoice_outstanding_before_rollback", "label": _("Outstanding Before"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "invoice_outstanding_after_rollback", "label": _("Outstanding After"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "payment_entry_docstatus_after", "label": _("PE Docstatus After"), "fieldtype": "Int", "width": 130},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL Count After"), "fieldtype": "Int", "width": 140},
        {"fieldname": "payment_entry_gl_net_after", "label": _("PE GL Net After"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_rollback_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("r.status = %(status)s")
        params["status"] = filters.status
    if filters.get("from_date"):
        conditions.append("DATE(r.checked_on) >= %(from_date)s")
        params["from_date"] = filters.from_date
    if filters.get("to_date"):
        conditions.append("DATE(r.checked_on) <= %(to_date)s")
        params["to_date"] = filters.to_date
    data = frappe.db.sql(
        f"""
        SELECT r.name AS rollback_run, r.rollback_run_id, r.status, r.rollback_allowed,
            r.payment_entry_cancelled, r.source_invoice_restored, r.real_posting_allowed,
            r.sales_invoice, r.payment_entry, r.payment_amount,
            r.invoice_outstanding_before_rollback, r.invoice_outstanding_after_rollback,
            r.payment_entry_docstatus_after, r.payment_entry_gl_count_after,
            r.payment_entry_gl_net_after, r.checked_on, %(currency)s AS currency
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
                {"name": "PE Cancelled", "values": [int(row.payment_entry_cancelled or 0) for row in data[:20]]},
                {"name": "Real Posting Allowed", "values": [int(row.real_posting_allowed or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Rollback Runs"), "datatype": "Int"},
        {"value": sum(int(row.payment_entry_cancelled or 0) for row in data), "indicator": "Green", "label": _("Cancelled PEs"), "datatype": "Int"},
        {"value": sum(int(row.real_posting_allowed or 0) for row in data), "indicator": "Red", "label": _("Real Posting Allowed"), "datatype": "Int"},
    ]
    return rollback_columns(), data, None, chart, summary


def execute_line_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("rollback_run"):
        conditions.append("l.rollback_run = %(rollback_run)s")
        params["rollback_run"] = filters.rollback_run
    if filters.get("record_type"):
        conditions.append("l.record_type = %(record_type)s")
        params["record_type"] = filters.record_type
    if filters.get("status"):
        conditions.append("l.status = %(status)s")
        params["status"] = filters.status
    columns = [
        {"fieldname": "line", "label": _("Line"), "fieldtype": "Link", "options": LINE_DOCTYPE, "width": 220},
        {"fieldname": "rollback_run", "label": _("Rollback Run"), "fieldtype": "Link", "options": RUN_DOCTYPE, "width": 220},
        {"fieldname": "record_type", "label": _("Record Type"), "fieldtype": "Data", "width": 150},
        {"fieldname": "record_doctype", "label": _("Record DocType"), "fieldtype": "Data", "width": 170},
        {"fieldname": "record_name", "label": _("Record Name"), "fieldtype": "Data", "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 500},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT l.name AS line, l.rollback_run, l.record_type, l.record_doctype, l.record_name,
            l.status, l.amount, l.detail, l.checked_on, %(currency)s AS currency
        FROM `tab{LINE_DOCTYPE}` l
        {build_where(conditions)}
        ORDER BY l.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart_map = {}
    for row in data:
        chart_map[row.status or "Unknown"] = chart_map.get(row.status or "Unknown", 0) + 1
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Lines", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Lines"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Cancelled"]), "indicator": "Green", "label": _("Cancelled"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Restored"]), "indicator": "Green", "label": _("Restored"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_rollback_report(filters)
    summary.extend(
        [
            {
                "value": count_dt("Payment Entry", {"docstatus": 1, "custom_ndis_real_remittance_pe_smoke": 1}),
                "indicator": "Orange",
                "label": _("Submitted Smoke PEs"),
                "datatype": "Int",
            },
            {
                "value": count_dt("Payment Entry", {"docstatus": 2, "custom_ndis_real_remittance_pe_smoke": 1}),
                "indicator": "Green",
                "label": _("Cancelled Smoke PEs"),
                "datatype": "Int",
            },
            {
                "value": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}),
                "indicator": "Red",
                "label": _("Submitted JEs Today"),
                "datatype": "Int",
            },
            {
                "value": count_dt("Purchase Invoice", {"creation": [">=", today()]}),
                "indicator": "Red",
                "label": _("Purchase Invoices Today"),
                "datatype": "Int",
            },
        ]
    )
    return columns, data, message, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
