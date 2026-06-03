import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


FREEZE_ACK = "I_CONFIRM_PHASE7H_FREEZE_BATCH_PE_SMOKE_ROLLBACK_EVIDENCE"
FREEZE_DOCTYPE = "NDIS Real Remittance Batch PE Evidence Freeze"
ITEM_DOCTYPE = "NDIS Real Remittance Batch PE Evidence Freeze Item"
ROLLBACK_DOCTYPE = "NDIS Real Remittance Batch PE Rollback Run"
ROLLBACK_LINE_DOCTYPE = "NDIS Real Remittance Batch PE Rollback Line"


def make_freeze_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-REAL-REMITTANCE-BATCH-PE-FREEZE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def guardrails():
    return {
        "payment_entry_count": count_dt("Payment Entry"),
        "payment_entry_gl_count": count_dt("GL Entry", {"voucher_type": "Payment Entry"}),
        "submitted_tagged_pe_count": tagged_pe_count(1),
        "cancelled_tagged_pe_count": tagged_pe_count(2),
        "submitted_journal_entry_count_today": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}),
        "purchase_invoice_count_today": count_dt("Purchase Invoice", {"creation": [">=", today()]}),
        "batch_live_enabled_policy_count": count_dt("NDIS Real Remittance Batch Posting Policy", {"batch_live_enabled": 1}),
        "production_live_enabled_policy_count": count_dt("NDIS PE Production Posting Policy", {"production_posting_enabled": 1}),
    }


def latest_rollback_run():
    rows = frappe.get_all(
        ROLLBACK_DOCTYPE,
        filters={
            "status": "Rolled Back",
            "rollback_completed": 1,
            "ready_for_freeze": 1,
            "controlled_payment_entry_cancelled": 1,
            "batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "payment_entry": ["!=", ""],
        },
        fields=[
            "name",
            "rollback_run_id",
            "smoke_run",
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
            "invoice_outstanding_after_total",
            "payment_entry_gl_count_after_specific",
            "payment_entry_gl_net_after_specific",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return frappe._dict(rows[0]) if rows else None


def existing_freeze_for_rollback(rollback_run):
    if not rollback_run or not frappe.db.exists("DocType", FREEZE_DOCTYPE):
        return None
    rows = frappe.get_all(
        FREEZE_DOCTYPE,
        filters={"rollback_run": rollback_run, "evidence_freeze_allowed": 1, "status": "Frozen"},
        fields=["name", "freeze_id"],
        limit=1,
    )
    return frappe._dict(rows[0]) if rows else None


def get_rollback_lines(rollback_run):
    if not rollback_run:
        return []
    return frappe.get_all(
        ROLLBACK_LINE_DOCTYPE,
        filters={"rollback_run": rollback_run},
        fields=[
            "name",
            "line_no",
            "line_label",
            "line_status",
            "sales_invoice",
            "payment_entry",
            "rollback_amount",
            "invoice_outstanding_after_rollback",
        ],
        order_by="line_no asc, creation asc",
    )


def pe_gl_count_net(payment_entry):
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


def si_gl_count_net(sales_invoices):
    sales_invoices = [si for si in sales_invoices if si]
    if not sales_invoices:
        return 0, 0
    rows = frappe.db.sql(
        """
        SELECT COUNT(*) AS gl_count, COALESCE(SUM(debit - credit), 0) AS gl_net
        FROM `tabGL Entry`
        WHERE voucher_type = 'Sales Invoice'
        AND voucher_no IN %(sales_invoices)s
        """,
        {"sales_invoices": tuple(sales_invoices)},
        as_dict=True,
    )
    return int(rows[0].gl_count or 0), flt(rows[0].gl_net or 0, 2)


def source_invoice_restored_count(lines):
    count = 0
    for line in lines:
        if not line.sales_invoice or not frappe.db.exists("Sales Invoice", line.sales_invoice):
            continue
        outstanding = flt(frappe.db.get_value("Sales Invoice", line.sales_invoice, "outstanding_amount") or 0, 2)
        if outstanding == flt(line.invoice_outstanding_after_rollback or 0, 2) and outstanding > 0:
            count += 1
    return count


def add_item(items, status, severity, category, check_key, check_label, detail, source_doctype=None, source_name=None):
    items.append(
        {
            "status": status,
            "severity": severity,
            "category": category,
            "check_key": check_key,
            "check_label": check_label,
            "detail": detail,
            "source_doctype": source_doctype,
            "source_name": source_name,
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
    score = 100 - int(blockers or 0) * 25 - int(warnings or 0) * 5
    return max(0, round(score, 2))


def evaluate_freeze(items, rollback, lines, evidence, config, guard):
    add_item(items, "Pass" if not config["production_mode"] else "Blocker", "Low" if not config["production_mode"] else "Critical", "Site Config", "production_mode", "Production mode", "Production mode remains disabled." if not config["production_mode"] else "Production mode is enabled.")
    add_item(items, "Pass" if not config["live_pe_enabled"] else "Blocker", "Low" if not config["live_pe_enabled"] else "Critical", "Site Config", "live_pe_enabled", "Live PE posting", "Live Payment Entry posting remains disabled." if not config["live_pe_enabled"] else "Live PE posting config is enabled.")

    live_policy_count = guard["batch_live_enabled_policy_count"] + guard["production_live_enabled_policy_count"]
    add_item(items, "Pass" if live_policy_count == 0 else "Blocker", "Low" if live_policy_count == 0 else "Critical", "Guardrail", "live_policies", "Live policies", "No live-enabled batch or production PE policies." if live_policy_count == 0 else f"{live_policy_count} live-enabled policy record(s) found.")

    if not rollback:
        add_item(items, "Blocker", "Critical", "Rollback Evidence", "rollback_run", "Phase 7G rollback", "No completed Phase 7G rollback run is available.")
        return

    duplicate = existing_freeze_for_rollback(rollback.name)
    if duplicate:
        add_item(items, "Blocker", "Critical", "Freeze Evidence", "duplicate_freeze", "Existing approved freeze", f"Rollback already has approved freeze {duplicate.name}.", FREEZE_DOCTYPE, duplicate.name)

    add_item(items, "Pass", "Low", "Rollback Evidence", "rollback_run", "Phase 7G rollback", f"Rollback run {rollback.rollback_run_id} is complete and ready for freeze.", ROLLBACK_DOCTYPE, rollback.name)

    pe_docstatus = evidence["payment_entry_docstatus_after_rollback"]
    add_item(items, "Pass" if pe_docstatus == 2 else "Blocker", "Low" if pe_docstatus == 2 else "Critical", "Payment Entry", "pe_cancelled", "Controlled PE cancelled", f"Payment Entry docstatus after rollback is {pe_docstatus}.", "Payment Entry", rollback.payment_entry)
    add_item(items, "Pass" if guard["submitted_tagged_pe_count"] == 0 else "Blocker", "Low" if guard["submitted_tagged_pe_count"] == 0 else "Critical", "Payment Entry", "submitted_tagged_pe", "Submitted tagged PE count", f"{guard['submitted_tagged_pe_count']} submitted tagged PE(s) found.")
    add_item(items, "Pass" if guard["cancelled_tagged_pe_count"] >= 1 else "Blocker", "Low" if guard["cancelled_tagged_pe_count"] >= 1 else "Critical", "Payment Entry", "cancelled_tagged_pe", "Cancelled tagged PE count", f"{guard['cancelled_tagged_pe_count']} cancelled tagged PE(s) found.")

    if lines:
        add_item(items, "Pass", "Low", "Invoice Evidence", "rollback_lines", "Rollback lines", f"{len(lines)} rollback line(s) found.")
    else:
        add_item(items, "Blocker", "Critical", "Invoice Evidence", "rollback_lines", "Rollback lines", "No rollback lines found.")

    restored = evidence["source_invoice_restored_count"]
    add_item(items, "Pass" if restored == evidence["invoice_count"] and restored > 0 else "Blocker", "Low" if restored == evidence["invoice_count"] and restored > 0 else "Critical", "Invoice Evidence", "invoices_restored", "Source invoices restored", f"{restored} of {evidence['invoice_count']} source invoice(s) restored.")

    pe_gl_count = evidence["payment_entry_gl_count_after_rollback"]
    pe_gl_net = flt(evidence["payment_entry_gl_net_after_rollback"], 2)
    add_item(items, "Pass" if pe_gl_count > 0 and pe_gl_net == 0 else "Blocker", "Low" if pe_gl_count > 0 and pe_gl_net == 0 else "Critical", "GL Evidence", "pe_gl_balanced", "Payment Entry GL balanced", f"{pe_gl_count} PE GL row(s), net {pe_gl_net:.2f}.", "Payment Entry", rollback.payment_entry)

    si_gl_net = flt(evidence["sales_invoice_gl_net"], 2)
    add_item(items, "Pass" if si_gl_net == 0 else "Blocker", "Low" if si_gl_net == 0 else "Critical", "GL Evidence", "si_gl_balanced", "Sales Invoice GL balanced", f"Sales Invoice GL net {si_gl_net:.2f}.")

    add_item(items, "Pass" if guard["submitted_journal_entry_count_today"] == 0 else "Blocker", "Low" if guard["submitted_journal_entry_count_today"] == 0 else "Critical", "Guardrail", "submitted_je_today", "Submitted JE today", f"{guard['submitted_journal_entry_count_today']} submitted Journal Entry record(s) found today.")
    add_item(items, "Pass" if guard["purchase_invoice_count_today"] == 0 else "Blocker", "Low" if guard["purchase_invoice_count_today"] == 0 else "Critical", "Guardrail", "purchase_invoice_today", "Purchase Invoice today", f"{guard['purchase_invoice_count_today']} Purchase Invoice record(s) found today.")


def collect_evidence(rollback, lines):
    payment_entry = rollback.payment_entry if rollback else None
    sales_invoices = [line.sales_invoice for line in lines]
    pe_gl_count, pe_gl_net = pe_gl_count_net(payment_entry)
    si_gl_count, si_gl_net = si_gl_count_net(sales_invoices)
    pe_docstatus = frappe.db.get_value("Payment Entry", payment_entry, "docstatus") if payment_entry else None
    return {
        "payment_entry_docstatus_after_rollback": int(pe_docstatus) if pe_docstatus is not None else None,
        "invoice_count": len(lines),
        "invoice_outstanding_after_rollback_total": flt(sum(flt(line.invoice_outstanding_after_rollback or 0) for line in lines), 2),
        "source_invoice_restored_count": source_invoice_restored_count(lines),
        "payment_entry_gl_count_after_rollback": pe_gl_count,
        "payment_entry_gl_net_after_rollback": pe_gl_net,
        "sales_invoice_gl_count": si_gl_count,
        "sales_invoice_gl_net": si_gl_net,
    }


def create_freeze_items(doc, items):
    for item in items:
        row = frappe.new_doc(ITEM_DOCTYPE)
        row.freeze = doc.name
        row.status = item["status"]
        row.severity = item["severity"]
        row.category = item["category"]
        row.check_key = item["check_key"]
        row.check_label = item["check_label"]
        row.detail = item["detail"]
        row.source_doctype = item.get("source_doctype")
        row.source_name = item.get("source_name")
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_real_remittance_batch_pe_freeze(rollback_run=None, dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_real_remittance_batch_pe_freeze")

    if rollback_run:
        if not frappe.db.exists(ROLLBACK_DOCTYPE, rollback_run):
            frappe.throw(_("Rollback run not found: {0}").format(rollback_run))
        rollback = frappe.get_doc(ROLLBACK_DOCTYPE, rollback_run)
    else:
        latest = latest_rollback_run()
        rollback = frappe.get_doc(ROLLBACK_DOCTYPE, latest.name) if latest else None

    lines = get_rollback_lines(rollback.name) if rollback else []
    config = config_state()
    guard_before = guardrails()
    evidence = collect_evidence(rollback, lines)

    items = []
    evaluate_freeze(items, rollback, lines, evidence, config, guard_before)

    ack_ok = acknowledgement == FREEZE_ACK
    add_item(items, "Pass" if ack_ok else "Warning", "Low" if ack_ok else "Medium", "Acknowledgement", "freeze_ack", "Freeze acknowledgement", "Exact acknowledgement supplied." if ack_ok else f"Required acknowledgement not supplied: {FREEZE_ACK}")

    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    allowed = int(ack_ok and item_summary["blocker_count"] == 0 and bool(rollback))
    status = "Frozen" if allowed else ("Blocked" if item_summary["blocker_count"] else "Needs Review")
    freeze_status = "Ready For Next Controlled Production Design Phase" if allowed else ("Blocked" if item_summary["blocker_count"] else "Needs Review")

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": status,
        "freeze_status": freeze_status,
        "freeze_score": score,
        "evidence_freeze_allowed": allowed,
        "ready_for_next_phase": allowed,
        "batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "rollback_run": rollback.name if rollback else None,
        "smoke_run": rollback.smoke_run if rollback else None,
        "source_run": rollback.source_run if rollback else None,
        "activation_gate": rollback.activation_gate if rollback else None,
        "adapter_run": rollback.adapter_run if rollback else None,
        "batch_preview": rollback.batch_preview if rollback else None,
        "design_gate": rollback.design_gate if rollback else None,
        "company": rollback.company if rollback else None,
        "customer": rollback.customer if rollback else None,
        "payment_entry": rollback.payment_entry if rollback else None,
        "payment_entry_amount": flt(rollback.payment_entry_amount or 0) if rollback else 0,
        "submitted_tagged_pe_count": guard_before["submitted_tagged_pe_count"],
        "cancelled_tagged_pe_count": guard_before["cancelled_tagged_pe_count"],
        **evidence,
        "items": items,
        "summary": item_summary,
        "guardrails_before": guard_before,
        "guardrails_after": guardrails(),
        "config": config,
        "required_acknowledgement": FREEZE_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 7H is a read-only evidence freeze. It creates no Payment Entry, GL Entry, Journal Entry, invoice, ABA, STP, payroll, email, Xero export, or bank allocation.",
    }

    if int(dry_run or 0):
        return result

    doc = frappe.new_doc(FREEZE_DOCTYPE)
    doc.freeze_id = make_freeze_id()
    doc.status = status
    doc.freeze_status = freeze_status
    doc.evidence_freeze_allowed = allowed
    doc.ready_for_next_phase = allowed
    doc.batch_posting_allowed = 0
    doc.real_posting_allowed = 0

    for fieldname in [
        "rollback_run",
        "smoke_run",
        "source_run",
        "activation_gate",
        "adapter_run",
        "batch_preview",
        "design_gate",
        "company",
        "customer",
        "payment_entry",
        "payment_entry_amount",
        "payment_entry_docstatus_after_rollback",
        "submitted_tagged_pe_count",
        "cancelled_tagged_pe_count",
        "invoice_count",
        "invoice_outstanding_after_rollback_total",
        "source_invoice_restored_count",
        "payment_entry_gl_count_after_rollback",
        "payment_entry_gl_net_after_rollback",
        "sales_invoice_gl_count",
        "sales_invoice_gl_net",
    ]:
        setattr(doc, fieldname, result.get(fieldname))

    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.freeze_score = score
    doc.blocker_count = item_summary["blocker_count"]
    doc.warning_count = item_summary["warning_count"]
    doc.pass_count = item_summary["pass_count"]
    doc.info_count = item_summary["info_count"]
    doc.item_count = item_summary["item_count"]
    doc.payment_entry_count_before = guard_before["payment_entry_count"]
    doc.payment_entry_count_after = guardrails()["payment_entry_count"]
    doc.payment_entry_gl_count_before = guard_before["payment_entry_gl_count"]
    doc.payment_entry_gl_count_after = guardrails()["payment_entry_gl_count"]
    doc.submitted_journal_entry_count_today = guard_before["submitted_journal_entry_count_today"]
    doc.purchase_invoice_count_today = guard_before["purchase_invoice_count_today"]
    doc.batch_live_enabled_policy_count = guard_before["batch_live_enabled_policy_count"]
    doc.production_live_enabled_policy_count = guard_before["production_live_enabled_policy_count"]
    doc.required_acknowledgement = FREEZE_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    create_freeze_items(doc, items)

    guard_after = guardrails()
    frappe.db.set_value(
        FREEZE_DOCTYPE,
        doc.name,
        {
            "payment_entry_count_after": guard_after["payment_entry_count"],
            "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
            "summary_json": safe_json({**result, "guardrails_after": guard_after}),
        },
        update_modified=False,
    )
    frappe.db.commit()
    result.update({"created": True, "freeze": doc.name, "freeze_id": doc.freeze_id, "guardrails_after": guard_after})
    return result


@frappe.whitelist()
def cancel_real_remittance_batch_pe_freeze(freeze, reason=None):
    assert_action("cancel_real_remittance_batch_pe_freeze")
    if not frappe.db.exists(FREEZE_DOCTYPE, freeze):
        frappe.throw(_("Evidence freeze not found: {0}").format(freeze))
    doc = frappe.get_doc(FREEZE_DOCTYPE, freeze)
    if doc.status == "Cancelled":
        return {"freeze": freeze, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.evidence_freeze_allowed or 0):
        frappe.throw(_("Cannot cancel an allowed Phase 7H freeze. Create a superseding freeze instead."))
    frappe.db.set_value(
        FREEZE_DOCTYPE,
        freeze,
        {
            "status": "Cancelled",
            "freeze_status": "Cancelled",
            "evidence_freeze_allowed": 0,
            "ready_for_next_phase": 0,
            "batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 7H evidence freeze cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{ITEM_DOCTYPE}` SET status = 'Cancelled' WHERE freeze = %(freeze)s", {"freeze": freeze})
    frappe.db.commit()
    return {"freeze": freeze, "status": "Cancelled", "note": "Freeze audit record cancelled only. No accounting movement occurred."}


@frappe.whitelist()
def quick_real_remittance_batch_pe_freeze_summary(limit=20):
    freezes = frappe.get_all(
        FREEZE_DOCTYPE,
        fields=[
            "name",
            "freeze_id",
            "status",
            "freeze_status",
            "freeze_score",
            "evidence_freeze_allowed",
            "ready_for_next_phase",
            "batch_posting_allowed",
            "real_posting_allowed",
            "rollback_run",
            "payment_entry",
            "payment_entry_docstatus_after_rollback",
            "submitted_tagged_pe_count",
            "cancelled_tagged_pe_count",
            "invoice_count",
            "invoice_outstanding_after_rollback_total",
            "source_invoice_restored_count",
            "payment_entry_gl_count_after_rollback",
            "payment_entry_gl_net_after_rollback",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(
        ITEM_DOCTYPE,
        fields=["name", "freeze", "status", "severity", "category", "check_label", "detail", "source_doctype", "source_name"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "freezes": freezes,
        "items": items,
        "required_acknowledgement": FREEZE_ACK,
        "guardrails": guardrails(),
        "config": config_state(),
        "note": "Phase 7H summary. Evidence freeze only; no accounting movement.",
    }


def freeze_columns():
    return [
        {"fieldname": "freeze", "label": _("Freeze"), "fieldtype": "Link", "options": FREEZE_DOCTYPE, "width": 220},
        {"fieldname": "freeze_id", "label": _("Freeze ID"), "fieldtype": "Data", "width": 380},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "freeze_status", "label": _("Freeze Status"), "fieldtype": "Data", "width": 300},
        {"fieldname": "freeze_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "evidence_freeze_allowed", "label": _("Freeze Allowed"), "fieldtype": "Check", "width": 120},
        {"fieldname": "ready_for_next_phase", "label": _("Ready Next Phase"), "fieldtype": "Check", "width": 140},
        {"fieldname": "real_posting_allowed", "label": _("Real Posting Allowed"), "fieldtype": "Check", "width": 150},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 170},
        {"fieldname": "invoice_count", "label": _("Invoices"), "fieldtype": "Int", "width": 90},
        {"fieldname": "invoice_outstanding_after_rollback_total", "label": _("Outstanding Total"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "payment_entry_gl_count_after_rollback", "label": _("PE GL Rows"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_net_after_rollback", "label": _("PE GL Net"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_freeze_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("f.status = %(status)s")
        params["status"] = filters.status
    if filters.get("from_date"):
        conditions.append("DATE(f.checked_on) >= %(from_date)s")
        params["from_date"] = filters.from_date
    if filters.get("to_date"):
        conditions.append("DATE(f.checked_on) <= %(to_date)s")
        params["to_date"] = filters.to_date
    data = frappe.db.sql(
        f"""
        SELECT
            f.name AS freeze,
            f.freeze_id,
            f.status,
            f.freeze_status,
            f.freeze_score,
            f.evidence_freeze_allowed,
            f.ready_for_next_phase,
            f.real_posting_allowed,
            f.payment_entry,
            f.invoice_count,
            f.invoice_outstanding_after_rollback_total,
            f.payment_entry_gl_count_after_rollback,
            f.payment_entry_gl_net_after_rollback,
            f.checked_on,
            %(currency)s AS currency
        FROM `tab{FREEZE_DOCTYPE}` f
        {build_where(conditions)}
        ORDER BY f.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.freeze_id for row in data[:20]],
            "datasets": [
                {"name": "Freeze Allowed", "values": [int(row.evidence_freeze_allowed or 0) for row in data[:20]]},
                {"name": "Ready Next Phase", "values": [int(row.ready_for_next_phase or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Freezes"), "datatype": "Int"},
        {"value": sum(int(row.evidence_freeze_allowed or 0) for row in data), "indicator": "Green", "label": _("Allowed"), "datatype": "Int"},
        {"value": sum(int(row.real_posting_allowed or 0) for row in data), "indicator": "Red", "label": _("Real Posting Allowed"), "datatype": "Int"},
    ]
    return freeze_columns(), data, None, chart, summary


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("freeze"):
        conditions.append("i.freeze = %(freeze)s")
        params["freeze"] = filters.freeze
    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.status
    if filters.get("severity"):
        conditions.append("i.severity = %(severity)s")
        params["severity"] = filters.severity
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": ITEM_DOCTYPE, "width": 220},
        {"fieldname": "freeze", "label": _("Freeze"), "fieldtype": "Link", "options": FREEZE_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 110},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 150},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 220},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "source_name", "label": _("Source"), "fieldtype": "Dynamic Link", "options": "source_doctype", "width": 220},
        {"fieldname": "source_doctype", "label": _("Source Type"), "fieldtype": "Data", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            i.name AS item,
            i.freeze,
            i.status,
            i.severity,
            i.category,
            i.check_label,
            i.detail,
            i.source_doctype,
            i.source_name
        FROM `tab{ITEM_DOCTYPE}` i
        {build_where(conditions)}
        ORDER BY
            CASE i.status
                WHEN 'Blocker' THEN 1
                WHEN 'Warning' THEN 2
                WHEN 'Info' THEN 3
                WHEN 'Pass' THEN 4
                ELSE 5
            END,
            i.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart_map = {}
    for row in data:
        chart_map[row.status or "Info"] = chart_map.get(row.status or "Info", 0) + 1
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Items", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Items"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Pass"]), "indicator": "Green", "label": _("Pass"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Warning"]), "indicator": "Orange", "label": _("Warnings"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Blocker"]), "indicator": "Red", "label": _("Blockers"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns = [
        {"fieldname": "metric", "label": _("Metric"), "fieldtype": "Data", "width": 280},
        {"fieldname": "count_value", "label": _("Count"), "fieldtype": "Int", "width": 120},
    ]
    guard = guardrails()
    data = [
        {"metric": "Submitted Tagged PE", "count_value": guard["submitted_tagged_pe_count"]},
        {"metric": "Cancelled Tagged PE", "count_value": guard["cancelled_tagged_pe_count"]},
        {"metric": "Payment Entry GL Count", "count_value": guard["payment_entry_gl_count"]},
        {"metric": "Submitted Journal Entry Today", "count_value": guard["submitted_journal_entry_count_today"]},
        {"metric": "Purchase Invoice Today", "count_value": guard["purchase_invoice_count_today"]},
        {"metric": "Batch Live Enabled Policies", "count_value": guard["batch_live_enabled_policy_count"]},
        {"metric": "Production Live Enabled Policies", "count_value": guard["production_live_enabled_policy_count"]},
    ]
    chart = {"data": {"labels": [row["metric"] for row in data], "datasets": [{"name": "Count", "values": [row["count_value"] for row in data]}]}, "type": "bar"}
    summary = [
        {"value": guard["submitted_tagged_pe_count"], "indicator": "Red" if guard["submitted_tagged_pe_count"] else "Green", "label": _("Submitted Tagged PE"), "datatype": "Int"},
        {"value": guard["cancelled_tagged_pe_count"], "indicator": "Blue", "label": _("Cancelled Tagged PE"), "datatype": "Int"},
        {"value": guard["batch_live_enabled_policy_count"] + guard["production_live_enabled_policy_count"], "indicator": "Red" if guard["batch_live_enabled_policy_count"] or guard["production_live_enabled_policy_count"] else "Green", "label": _("Live Policies"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
