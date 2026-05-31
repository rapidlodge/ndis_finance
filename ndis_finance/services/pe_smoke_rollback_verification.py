import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


RUN_DOCTYPE = "NDIS PE Smoke Rollback Run"
ITEM_DOCTYPE = "NDIS PE Smoke Rollback Run Item"
ROLLBACK_ACK = "I_CONFIRM_ROLLBACK_PHASE5I_PE_AND_OPTIONAL_PHASE5H_SI"


def make_rollback_run_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-PE-SMOKE-ROLLBACK-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_doc(doctype, filters=None, fields=None, order_by="creation desc"):
    rows = frappe.get_all(
        doctype,
        filters=filters or {},
        fields=fields or ["name"],
        order_by=order_by,
        limit=1,
    )
    return rows[0] if rows else None


def add_item(items, status, severity, category, check_key, check_label, detail, recommendation=None, source_doctype=None, source_name=None):
    items.append(
        {
            "status": status,
            "severity": severity,
            "category": category,
            "check_key": check_key,
            "check_label": check_label,
            "detail": detail,
            "recommendation": recommendation,
            "source_doctype": source_doctype,
            "source_name": source_name,
        }
    )


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


def phase5i_run_from_inputs(phase5i_run=None, payment_entry=None):
    if phase5i_run and frappe.db.exists("NDIS PE One Submitted Smoke Run", phase5i_run):
        return frappe.get_doc("NDIS PE One Submitted Smoke Run", phase5i_run)
    filters = {
        "status": "Submitted",
        "payment_entry_created": 1,
        "payment_entry_submitted": 1,
        "payment_entry_cancelled": 0,
    }
    if payment_entry:
        filters["payment_entry"] = payment_entry
    row = latest_doc(
        "NDIS PE One Submitted Smoke Run",
        filters,
        ["name"],
        "executed_on desc, creation desc",
    )
    return frappe.get_doc("NDIS PE One Submitted Smoke Run", row.name) if row else None


def evaluate_config(items):
    config = config_state()
    if config["production_mode"]:
        add_item(items, "Blocker", "Critical", "Site Config", "production_mode", "Production mode", "Production mode is enabled.", "Keep disabled for Phase 5J.")
    else:
        add_item(items, "Pass", "Low", "Site Config", "production_mode", "Production mode", "Production mode remains disabled.")
    if config["live_pe_enabled"]:
        add_item(items, "Blocker", "Critical", "Site Config", "live_pe_enabled", "Live PE posting config", "Live PE posting config is enabled.", "Keep disabled for Phase 5J.")
    else:
        add_item(items, "Pass", "Low", "Site Config", "live_pe_enabled", "Live PE posting config", "Live PE posting remains disabled.")
    if config["sandbox_enabled"]:
        add_item(items, "Pass", "Low", "Site Config", "sandbox_enabled", "Sandbox config", "Sandbox config remains enabled.")
    else:
        add_item(items, "Warning", "Medium", "Site Config", "sandbox_enabled", "Sandbox config", "Sandbox config is not enabled.")
    return config


def evaluate_phase5i_evidence(items, phase5i_run_doc):
    if not phase5i_run_doc:
        add_item(items, "Blocker", "Critical", "Phase 5I Evidence", "phase5i_run", "Phase 5I submitted run", "No submitted Phase 5I run found.")
        return None, None
    add_item(items, "Pass", "Low", "Phase 5I Evidence", "phase5i_run", "Phase 5I submitted run", f"Phase 5I run found: {phase5i_run_doc.submitted_run_id}.", None, "NDIS PE One Submitted Smoke Run", phase5i_run_doc.name)

    pe = None
    si = None
    if phase5i_run_doc.payment_entry and frappe.db.exists("Payment Entry", phase5i_run_doc.payment_entry):
        pe = frappe.get_doc("Payment Entry", phase5i_run_doc.payment_entry)
        add_item(items, "Pass", "Low", "Phase 5I Evidence", "payment_entry_exists", "Payment Entry exists", f"Payment Entry found: {pe.name}.", None, "Payment Entry", pe.name)
    else:
        add_item(items, "Blocker", "Critical", "Phase 5I Evidence", "payment_entry_exists", "Payment Entry exists", "Linked Payment Entry is missing.")
    if phase5i_run_doc.source_sales_invoice and frappe.db.exists("Sales Invoice", phase5i_run_doc.source_sales_invoice):
        si = frappe.get_doc("Sales Invoice", phase5i_run_doc.source_sales_invoice)
        add_item(items, "Pass", "Low", "Phase 5I Evidence", "source_invoice_exists", "Source invoice exists", f"Source invoice found: {si.name}.", None, "Sales Invoice", si.name)
    else:
        add_item(items, "Blocker", "Critical", "Phase 5I Evidence", "source_invoice_exists", "Source invoice exists", "Linked source Sales Invoice is missing.")
    return pe, si


def evaluate_payment_entry(items, pe, si):
    if not pe:
        return
    if not int(getattr(pe, "custom_ndis_pe_one_submitted_smoke", 0) or 0):
        add_item(items, "Blocker", "Critical", "Payment Entry", "pe_tag", "Phase 5I PE tag", "Payment Entry is not tagged as Phase 5I smoke.")
    else:
        add_item(items, "Pass", "Low", "Payment Entry", "pe_tag", "Phase 5I PE tag", "Payment Entry is tagged as Phase 5I smoke.")
    if pe.docstatus != 1:
        add_item(items, "Blocker", "Critical", "Payment Entry", "pe_docstatus", "PE docstatus", f"Payment Entry docstatus is {pe.docstatus}; expected 1.")
    else:
        add_item(items, "Pass", "Low", "Payment Entry", "pe_docstatus", "PE docstatus", "Payment Entry is submitted.")
    if flt(pe.paid_amount) > 1 or flt(pe.received_amount) > 1:
        add_item(items, "Blocker", "Critical", "Payment Entry", "pe_amount_cap", "PE amount cap", f"Payment amount exceeds Phase 5I cap. Paid: {pe.paid_amount}, Received: {pe.received_amount}.")
    else:
        add_item(items, "Pass", "Low", "Payment Entry", "pe_amount_cap", "PE amount cap", f"Payment amount verified: {flt(pe.paid_amount):.2f}.")
    linked_si = getattr(pe, "custom_ndis_pe_one_submitted_source_invoice", None)
    if si and linked_si != si.name:
        add_item(items, "Blocker", "Critical", "Payment Entry", "pe_source_invoice", "PE source invoice", f"PE source invoice {linked_si} does not match {si.name}.")
    else:
        add_item(items, "Pass", "Low", "Payment Entry", "pe_source_invoice", "PE source invoice", f"PE source invoice verified: {linked_si}.")
    if gl_count("Payment Entry", pe.name) <= 0:
        add_item(items, "Blocker", "Critical", "Payment Entry GL", "pe_gl", "Payment Entry GL", "No Payment Entry GL found.")
    elif abs(gl_net("Payment Entry", pe.name)) > 0.0001:
        add_item(items, "Blocker", "Critical", "Payment Entry GL", "pe_gl_net", "Payment Entry GL net", f"Payment Entry GL net is {gl_net('Payment Entry', pe.name)}; expected 0.")
    else:
        add_item(items, "Pass", "Low", "Payment Entry GL", "pe_gl", "Payment Entry GL", f"Payment Entry GL exists and nets to 0. Rows: {gl_count('Payment Entry', pe.name)}.")


def evaluate_source_invoice(items, si):
    if not si:
        return
    if not int(getattr(si, "custom_ndis_pe_smoke_source_invoice", 0) or 0):
        add_item(items, "Blocker", "Critical", "Source Invoice", "si_tag", "Phase 5H source tag", "Sales Invoice is not tagged as Phase 5H source.")
    else:
        add_item(items, "Pass", "Low", "Source Invoice", "si_tag", "Phase 5H source tag", "Sales Invoice is tagged as Phase 5H source.")
    if si.docstatus != 1:
        add_item(items, "Blocker", "Critical", "Source Invoice", "si_docstatus", "Source invoice docstatus", f"Sales Invoice docstatus is {si.docstatus}; expected 1 before rollback.")
    else:
        add_item(items, "Pass", "Low", "Source Invoice", "si_docstatus", "Source invoice docstatus", "Source Sales Invoice is submitted.")
    if flt(si.outstanding_amount) != 0:
        add_item(items, "Warning", "Medium", "Source Invoice", "si_outstanding", "Source invoice outstanding", f"Outstanding is {flt(si.outstanding_amount):.2f}; expected 0.00 before PE cancellation.")
    else:
        add_item(items, "Pass", "Low", "Source Invoice", "si_outstanding", "Source invoice outstanding", "Outstanding is 0.00 before PE rollback.")
    if gl_count("Sales Invoice", si.name) <= 0:
        add_item(items, "Blocker", "Critical", "Source Invoice GL", "si_gl", "Sales Invoice GL", "No Sales Invoice GL found.")
    elif abs(gl_net("Sales Invoice", si.name)) > 0.0001:
        add_item(items, "Blocker", "Critical", "Source Invoice GL", "si_gl_net", "Sales Invoice GL net", f"Sales Invoice GL net is {gl_net('Sales Invoice', si.name)}; expected 0.")
    else:
        add_item(items, "Pass", "Low", "Source Invoice GL", "si_gl", "Sales Invoice GL", f"Sales Invoice GL exists and nets to 0. Rows: {gl_count('Sales Invoice', si.name)}.")


def evaluate_duplicates(items, pe):
    if not pe:
        return 0
    existing = count_dt(RUN_DOCTYPE, {"payment_entry": pe.name, "status": ["in", ["Payment Entry Cancelled", "Fully Rolled Back"]]})
    if existing:
        add_item(items, "Blocker", "Critical", "Duplicate Control", "duplicate_rollback", "Existing rollback run", f"{existing} successful rollback run(s) already exist for this Payment Entry.")
    else:
        add_item(items, "Pass", "Low", "Duplicate Control", "duplicate_rollback", "Existing rollback run", "No prior successful rollback run exists for this Payment Entry.")
    return existing


def evaluate_policy_and_other_guardrails(items):
    values = {
        "live_enabled_policy_count": count_dt("NDIS PE Production Posting Policy", {"production_posting_enabled": 1}),
        "submitted_journal_entry_count_today": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}),
        "purchase_invoice_count_today": count_dt("Purchase Invoice", {"creation": [">=", today()]}),
    }
    labels = {
        "live_enabled_policy_count": ("Policy Guardrail", "Live-enabled PE policies"),
        "submitted_journal_entry_count_today": ("Other Movement Guardrail", "Submitted Journal Entry today"),
        "purchase_invoice_count_today": ("Other Movement Guardrail", "Purchase Invoice today"),
    }
    for key, value in values.items():
        category, label = labels[key]
        if value:
            add_item(items, "Blocker", "Critical", category, key, label, f"{value} record(s) found.")
        else:
            add_item(items, "Pass", "Low", category, key, label, "Zero.")
    return values


def payment_references_for_invoice(si_name):
    return frappe.db.sql(
        """
        SELECT per.parent AS payment_entry, pe.docstatus, pe.custom_ndis_pe_one_submitted_smoke
        FROM `tabPayment Entry Reference` per
        INNER JOIN `tabPayment Entry` pe ON pe.name = per.parent
        WHERE per.reference_doctype = 'Sales Invoice'
        AND per.reference_name = %(si_name)s
        """,
        {"si_name": si_name},
        as_dict=True,
    )


def validate_source_invoice_cancel_allowed(items, si, pe):
    if not si or not pe:
        return False
    refs = payment_references_for_invoice(si.name)
    unsafe = []
    for ref in refs:
        if ref.payment_entry != pe.name:
            unsafe.append(f"{ref.payment_entry}: not the Phase 5I PE")
        elif int(ref.docstatus or 0) != 2:
            unsafe.append(f"{ref.payment_entry}: not cancelled")
        elif not int(ref.custom_ndis_pe_one_submitted_smoke or 0):
            unsafe.append(f"{ref.payment_entry}: not tagged Phase 5I")
    if unsafe:
        add_item(items, "Blocker", "Critical", "Source Invoice Cancel", "si_cancel_refs", "Source invoice PE references", "Unsafe Payment Entry Reference rows found: " + "; ".join(unsafe), "Cancel only after the linked tagged Phase 5I PE is cancelled.")
        return False
    add_item(items, "Pass", "Low", "Source Invoice Cancel", "si_cancel_refs", "Source invoice PE references", f"All Payment Entry references are safe for source invoice cancellation. Count: {len(refs)}.")
    return True


def summarise_items(items):
    return {
        "blocker_count": len([i for i in items if i["status"] == "Blocker"]),
        "warning_count": len([i for i in items if i["status"] == "Warning"]),
        "pass_count": len([i for i in items if i["status"] == "Pass"]),
        "info_count": len([i for i in items if i["status"] == "Info"]),
        "item_count": len(items),
    }


def calculate_score(blockers, warnings):
    return max(0, round(100 - int(blockers or 0) * 25 - int(warnings or 0) * 5, 2))


def rollback_status(score, blockers, warnings, pe_cancelled, si_cancelled, cancel_source_invoice):
    if blockers:
        return "Blocked"
    if pe_cancelled and si_cancelled:
        return "Fully Rolled Back"
    if pe_cancelled and not cancel_source_invoice:
        return "Payment Entry Rolled Back"
    if warnings:
        return "Ready With Warnings"
    if score >= 95:
        return "Ready To Roll Back"
    return "Needs Review"


def create_run_items(run_doc, items):
    for item in items:
        row = frappe.new_doc(ITEM_DOCTYPE)
        row.rollback_run = run_doc.name
        row.status = item["status"]
        row.severity = item["severity"]
        row.category = item["category"]
        row.check_key = item["check_key"]
        row.check_label = item["check_label"]
        row.detail = item["detail"]
        row.recommendation = item.get("recommendation")
        row.source_doctype = item.get("source_doctype")
        row.source_name = item.get("source_name")
        row.checked_on = run_doc.executed_on
        row.insert(ignore_permissions=True)


def append_runtime_item(run_doc, item):
    row = frappe.new_doc(ITEM_DOCTYPE)
    row.rollback_run = run_doc.name
    row.status = item["status"]
    row.severity = item["severity"]
    row.category = item["category"]
    row.check_key = item["check_key"]
    row.check_label = item["check_label"]
    row.detail = item["detail"]
    row.recommendation = item.get("recommendation")
    row.source_doctype = item.get("source_doctype")
    row.source_name = item.get("source_name")
    row.checked_on = now_datetime()
    row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_pe_smoke_rollback_verification(phase5i_run=None, payment_entry=None, cancel_source_invoice=1, acknowledgement=None, dry_run=1, notes=None):
    assert_action("run_pe_smoke_rollback_verification")
    cancel_source_invoice = int(cancel_source_invoice or 0)
    items = []
    config = evaluate_config(items)
    phase5i_run_doc = phase5i_run_from_inputs(phase5i_run=phase5i_run, payment_entry=payment_entry)
    pe, si = evaluate_phase5i_evidence(items, phase5i_run_doc)
    evaluate_payment_entry(items, pe, si)
    evaluate_source_invoice(items, si)
    evaluate_duplicates(items, pe)
    guardrails = evaluate_policy_and_other_guardrails(items)

    if cancel_source_invoice:
        add_item(items, "Info", "Low", "Rollback Scope", "rollback_scope", "Rollback scope", "Rollback will cancel the tagged Payment Entry and the tagged Phase 5H source invoice.")
    else:
        add_item(items, "Info", "Low", "Rollback Scope", "rollback_scope", "Rollback scope", "Rollback will cancel the tagged Payment Entry only and keep the source invoice submitted/outstanding.")

    ack_ok = acknowledgement == ROLLBACK_ACK
    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "rollback_ack", "Rollback acknowledgement", "Exact acknowledgement supplied.")
    elif int(dry_run or 0):
        add_item(items, "Info", "Low", "Acknowledgement", "rollback_ack", "Rollback acknowledgement", f"Dry-run preview only. Required for rollback: {ROLLBACK_ACK}")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "rollback_ack", "Rollback acknowledgement", f"Required acknowledgement not supplied. Required: {ROLLBACK_ACK}", "Provide exact acknowledgement before rolling back.")

    summary = summarise_items(items)
    score = calculate_score(summary["blocker_count"], summary["warning_count"])

    if int(dry_run or 0):
        return {
            "dry_run": True,
            "status": "Previewed" if summary["blocker_count"] == 0 else "Blocked",
            "rollback_status": rollback_status(score, summary["blocker_count"], summary["warning_count"], False, False, cancel_source_invoice),
            "rollback_score": score,
            "phase5i_run": phase5i_run_doc.name if phase5i_run_doc else None,
            "payment_entry": pe.name if pe else payment_entry,
            "source_sales_invoice": si.name if si else None,
            "cancel_source_invoice": cancel_source_invoice,
            "payment_entry_cancelled": 0,
            "source_invoice_cancelled": 0,
            "new_payment_entry_created": 0,
            "required_acknowledgement": ROLLBACK_ACK,
            "acknowledgement_ok": ack_ok,
            "payment_entry_docstatus_before": pe.docstatus if pe else None,
            "invoice_docstatus_before": si.docstatus if si else None,
            "invoice_outstanding_before": flt(si.outstanding_amount) if si else None,
            "payment_entry_gl_count_before": gl_count("Payment Entry", pe.name) if pe else 0,
            "payment_entry_gl_net_before": gl_net("Payment Entry", pe.name) if pe else 0,
            "sales_invoice_gl_count_before": gl_count("Sales Invoice", si.name) if si else 0,
            "sales_invoice_gl_net_before": gl_net("Sales Invoice", si.name) if si else 0,
            "guardrails": guardrails,
            "summary": summary,
            "items": items,
            "note": "Dry-run only. No cancellation performed.",
        }

    pe_count_before = count_dt("Payment Entry")
    run_doc = frappe.new_doc(RUN_DOCTYPE)
    run_doc.rollback_run_id = make_rollback_run_id()
    run_doc.status = "Needs Review" if not ack_ok else ("Blocked" if summary["blocker_count"] else "Previewed")
    run_doc.rollback_scope = "Payment Entry And Source Invoice" if cancel_source_invoice else "Payment Entry Only"
    run_doc.phase5i_run = phase5i_run_doc.name if phase5i_run_doc else None
    run_doc.phase5h_source_run = phase5i_run_doc.source_invoice_run if phase5i_run_doc else None
    run_doc.source_sales_invoice = si.name if si else None
    run_doc.payment_entry = pe.name if pe else payment_entry
    run_doc.payment_entry_docstatus_before = pe.docstatus if pe else 0
    run_doc.invoice_docstatus_before = si.docstatus if si else 0
    run_doc.invoice_outstanding_before = flt(si.outstanding_amount) if si else 0
    run_doc.payment_entry_gl_count_before = gl_count("Payment Entry", pe.name) if pe else 0
    run_doc.payment_entry_gl_net_before = gl_net("Payment Entry", pe.name) if pe else 0
    run_doc.sales_invoice_gl_count_before = gl_count("Sales Invoice", si.name) if si else 0
    run_doc.sales_invoice_gl_net_before = gl_net("Sales Invoice", si.name) if si else 0
    run_doc.payment_entry_cancelled = 0
    run_doc.payment_entry_docstatus_after = pe.docstatus if pe else 0
    run_doc.invoice_outstanding_after_pe_cancel = flt(si.outstanding_amount) if si else 0
    run_doc.payment_entry_gl_count_after = gl_count("Payment Entry", pe.name) if pe else 0
    run_doc.payment_entry_gl_net_after = gl_net("Payment Entry", pe.name) if pe else 0
    run_doc.source_invoice_cancelled = 0
    run_doc.invoice_docstatus_after = si.docstatus if si else 0
    run_doc.invoice_outstanding_after_source_cancel = flt(si.outstanding_amount) if si else 0
    run_doc.sales_invoice_gl_count_after = gl_count("Sales Invoice", si.name) if si else 0
    run_doc.sales_invoice_gl_net_after = gl_net("Sales Invoice", si.name) if si else 0
    run_doc.site_name = frappe.local.site
    run_doc.sandbox_config_enabled = config["sandbox_enabled"]
    run_doc.production_mode_detected = config["production_mode"]
    run_doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    run_doc.executed_on = now_datetime()
    run_doc.executed_by = frappe.session.user
    run_doc.rollback_score = score
    run_doc.rollback_status = rollback_status(score, summary["blocker_count"], summary["warning_count"], False, False, cancel_source_invoice)
    run_doc.blocker_count = summary["blocker_count"]
    run_doc.warning_count = summary["warning_count"]
    run_doc.pass_count = summary["pass_count"]
    run_doc.info_count = summary["info_count"]
    run_doc.item_count = summary["item_count"]
    run_doc.new_payment_entry_created = 0
    run_doc.submitted_journal_entry_count_today = guardrails["submitted_journal_entry_count_today"]
    run_doc.purchase_invoice_count_today = guardrails["purchase_invoice_count_today"]
    run_doc.live_enabled_policy_count = guardrails["live_enabled_policy_count"]
    run_doc.required_acknowledgement = ROLLBACK_ACK
    run_doc.acknowledgement = acknowledgement
    run_doc.acknowledgement_ok = int(ack_ok)
    run_doc.notes = notes
    run_doc.insert(ignore_permissions=True)
    create_run_items(run_doc, items)

    pe_cancelled = 0
    si_cancelled = 0
    if ack_ok and summary["blocker_count"] == 0 and pe and si:
        if pe.docstatus == 1:
            pe.cancel()
        pe.reload()
        si.reload()
        pe_cancelled = int(pe.docstatus == 2)
        frappe.db.set_value(
            RUN_DOCTYPE,
            run_doc.name,
            {
                "status": "Payment Entry Cancelled",
                "rollback_status": "Payment Entry Rolled Back",
                "payment_entry_cancelled": pe_cancelled,
                "payment_entry_docstatus_after": pe.docstatus,
                "invoice_outstanding_after_pe_cancel": flt(si.outstanding_amount),
                "payment_entry_gl_count_after": gl_count("Payment Entry", pe.name),
                "payment_entry_gl_net_after": gl_net("Payment Entry", pe.name),
            },
            update_modified=False,
        )
        frappe.db.set_value(
            "NDIS PE One Submitted Smoke Run",
            phase5i_run_doc.name,
            {
                "status": "Payment Cancelled",
                "payment_entry_cancelled": 1,
                "payment_entry_docstatus": pe.docstatus,
                "invoice_outstanding_after": flt(si.outstanding_amount),
                "payment_entry_gl_count": gl_count("Payment Entry", pe.name),
                "payment_entry_gl_net": gl_net("Payment Entry", pe.name),
            },
            update_modified=False,
        )
        if cancel_source_invoice:
            validation_items = []
            validate_source_invoice_cancel_allowed(validation_items, si, pe)
            for validation_item in validation_items:
                append_runtime_item(run_doc, validation_item)
            if any(item["status"] == "Blocker" for item in validation_items):
                frappe.throw(_("Source invoice cancellation blocked because unsafe Payment Entry references remain."))
            if si.docstatus == 1:
                si.cancel()
            frappe.db.set_value("Sales Invoice", si.name, {"custom_ndis_pe_smoke_source_cancelled": 1}, update_modified=False)
            si.reload()
            si_cancelled = int(si.docstatus == 2)
            if phase5i_run_doc.source_invoice_run and frappe.db.exists("NDIS PE Smoke Invoice Source Run", phase5i_run_doc.source_invoice_run):
                frappe.db.set_value(
                    "NDIS PE Smoke Invoice Source Run",
                    phase5i_run_doc.source_invoice_run,
                    {
                        "status": "Source Cancelled",
                        "source_invoice_cancelled": 1,
                        "invoice_docstatus": si.docstatus,
                        "invoice_outstanding_amount": flt(si.outstanding_amount),
                        "invoice_gl_count": gl_count("Sales Invoice", si.name),
                        "invoice_gl_net": gl_net("Sales Invoice", si.name),
                        "source_cancelled_on": now_datetime(),
                        "source_cancelled_by": frappe.session.user,
                    },
                    update_modified=False,
                )
            frappe.db.set_value(
                RUN_DOCTYPE,
                run_doc.name,
                {
                    "status": "Fully Rolled Back",
                    "rollback_status": "Fully Rolled Back",
                    "source_invoice_cancelled": si_cancelled,
                    "invoice_docstatus_after": si.docstatus,
                    "invoice_outstanding_after_source_cancel": flt(si.outstanding_amount),
                    "sales_invoice_gl_count_after": gl_count("Sales Invoice", si.name),
                    "sales_invoice_gl_net_after": gl_net("Sales Invoice", si.name),
                },
                update_modified=False,
            )

    result = {
        "dry_run": False,
        "created": True,
        "rollback_run": run_doc.name,
        "rollback_run_id": run_doc.rollback_run_id,
        "status": frappe.db.get_value(RUN_DOCTYPE, run_doc.name, "status"),
        "rollback_status": frappe.db.get_value(RUN_DOCTYPE, run_doc.name, "rollback_status"),
        "rollback_score": score,
        "phase5i_run": phase5i_run_doc.name if phase5i_run_doc else None,
        "payment_entry": pe.name if pe else payment_entry,
        "source_sales_invoice": si.name if si else None,
        "cancel_source_invoice": cancel_source_invoice,
        "payment_entry_cancelled": pe_cancelled,
        "source_invoice_cancelled": si_cancelled,
        "payment_entry_docstatus_after": frappe.db.get_value("Payment Entry", pe.name, "docstatus") if pe else None,
        "invoice_docstatus_after": frappe.db.get_value("Sales Invoice", si.name, "docstatus") if si else None,
        "invoice_outstanding_after_pe_cancel": frappe.db.get_value(RUN_DOCTYPE, run_doc.name, "invoice_outstanding_after_pe_cancel"),
        "invoice_outstanding_after_source_cancel": frappe.db.get_value(RUN_DOCTYPE, run_doc.name, "invoice_outstanding_after_source_cancel"),
        "payment_entry_gl_count_after": gl_count("Payment Entry", pe.name) if pe else 0,
        "payment_entry_gl_net_after": gl_net("Payment Entry", pe.name) if pe else 0,
        "sales_invoice_gl_count_after": gl_count("Sales Invoice", si.name) if si else 0,
        "sales_invoice_gl_net_after": gl_net("Sales Invoice", si.name) if si else 0,
        "new_payment_entry_created": int(count_dt("Payment Entry") > pe_count_before),
        "submitted_journal_entry_count_today": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}),
        "purchase_invoice_count_today": count_dt("Purchase Invoice", {"creation": [">=", today()]}),
        "live_enabled_policy_count": count_dt("NDIS PE Production Posting Policy", {"production_posting_enabled": 1}),
        "required_acknowledgement": ROLLBACK_ACK,
        "acknowledgement_ok": ack_ok,
        "summary": summary,
        "note": "Phase 5J rollback verification completed. No new Payment Entry, Journal Entry, or Purchase Invoice was created.",
    }
    frappe.db.set_value(
        RUN_DOCTYPE,
        run_doc.name,
        {
            "new_payment_entry_created": result["new_payment_entry_created"],
            "submitted_journal_entry_count_today": result["submitted_journal_entry_count_today"],
            "purchase_invoice_count_today": result["purchase_invoice_count_today"],
            "live_enabled_policy_count": result["live_enabled_policy_count"],
            "summary_json": safe_json(result),
        },
        update_modified=False,
    )
    frappe.db.commit()
    return result


@frappe.whitelist()
def cancel_pe_smoke_rollback_run(rollback_run, reason=None):
    assert_action("cancel_pe_smoke_rollback_run")
    if not frappe.db.exists(RUN_DOCTYPE, rollback_run):
        frappe.throw(_("Rollback run not found: {0}").format(rollback_run))
    run = frappe.get_doc(RUN_DOCTYPE, rollback_run)
    if run.status in ["Payment Entry Cancelled", "Fully Rolled Back"]:
        frappe.throw(_("Cannot cancel a completed rollback evidence run."))
    frappe.db.set_value(
        RUN_DOCTYPE,
        rollback_run,
        {
            "status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 5J rollback run cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{ITEM_DOCTYPE}` SET status = 'Cancelled' WHERE rollback_run = %(rollback_run)s", {"rollback_run": rollback_run})
    frappe.db.commit()
    return {"rollback_run": rollback_run, "status": "Cancelled", "note": "Rollback audit run cancelled only. No accounting movement occurred."}


@frappe.whitelist()
def quick_pe_smoke_rollback_summary(limit=20):
    runs = frappe.get_all(
        RUN_DOCTYPE,
        fields=[
            "name",
            "rollback_run_id",
            "status",
            "rollback_scope",
            "rollback_status",
            "rollback_score",
            "phase5i_run",
            "payment_entry",
            "source_sales_invoice",
            "payment_entry_cancelled",
            "source_invoice_cancelled",
            "payment_entry_docstatus_after",
            "invoice_docstatus_after",
            "invoice_outstanding_after_pe_cancel",
            "payment_entry_gl_count_after",
            "payment_entry_gl_net_after",
            "sales_invoice_gl_count_after",
            "sales_invoice_gl_net_after",
            "executed_on",
            "executed_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(
        ITEM_DOCTYPE,
        fields=["name", "rollback_run", "status", "severity", "category", "check_label", "detail", "recommendation", "source_doctype", "source_name"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "runs": runs,
        "items": items,
        "rollback_acknowledgement": ROLLBACK_ACK,
        "config": config_state(),
        "note": "Phase 5J rollback summary. Cancelled GL is expected and should net to 0.00.",
    }


def execute_run_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("r.status = %(status)s")
        params["status"] = filters.status
    if filters.get("from_date"):
        conditions.append("DATE(r.executed_on) >= %(from_date)s")
        params["from_date"] = filters.from_date
    if filters.get("to_date"):
        conditions.append("DATE(r.executed_on) <= %(to_date)s")
        params["to_date"] = filters.to_date
    columns = [
        {"fieldname": "rollback_run", "label": _("Rollback Run"), "fieldtype": "Link", "options": RUN_DOCTYPE, "width": 220},
        {"fieldname": "rollback_run_id", "label": _("Rollback Run ID"), "fieldtype": "Data", "width": 340},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 150},
        {"fieldname": "rollback_scope", "label": _("Scope"), "fieldtype": "Data", "width": 220},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 170},
        {"fieldname": "source_sales_invoice", "label": _("Source Sales Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 180},
        {"fieldname": "payment_entry_cancelled", "label": _("PE Cancelled"), "fieldtype": "Check", "width": 110},
        {"fieldname": "source_invoice_cancelled", "label": _("SI Cancelled"), "fieldtype": "Check", "width": 110},
        {"fieldname": "invoice_outstanding_after_pe_cancel", "label": _("Outstanding After PE Cancel"), "fieldtype": "Currency", "options": "currency", "width": 180},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL Rows"), "fieldtype": "Int", "width": 100},
        {"fieldname": "payment_entry_gl_net_after", "label": _("PE GL Net"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "sales_invoice_gl_count_after", "label": _("SI GL Rows"), "fieldtype": "Int", "width": 100},
        {"fieldname": "sales_invoice_gl_net_after", "label": _("SI GL Net"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "executed_on", "label": _("Executed On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT r.name AS rollback_run, r.rollback_run_id, r.status, r.rollback_scope,
            r.payment_entry, r.source_sales_invoice, r.payment_entry_cancelled,
            r.source_invoice_cancelled, r.invoice_outstanding_after_pe_cancel,
            r.payment_entry_gl_count_after, r.payment_entry_gl_net_after,
            r.sales_invoice_gl_count_after, r.sales_invoice_gl_net_after, r.executed_on,
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
                {"name": "PE Cancelled", "values": [int(row.payment_entry_cancelled or 0) for row in data[:20]]},
                {"name": "SI Cancelled", "values": [int(row.source_invoice_cancelled or 0) for row in data[:20]]},
                {"name": "PE GL Rows", "values": [int(row.payment_entry_gl_count_after or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Rollback Runs"), "datatype": "Int"},
        {"value": sum(int(row.payment_entry_cancelled or 0) for row in data), "indicator": "Green", "label": _("PE Cancelled"), "datatype": "Int"},
        {"value": sum(int(row.source_invoice_cancelled or 0) for row in data), "indicator": "Green", "label": _("SI Cancelled"), "datatype": "Int"},
        {"value": sum(flt(row.payment_entry_gl_net_after) for row in data), "indicator": "Blue", "label": _("PE GL Net"), "datatype": "Currency", "currency": currency()},
    ]
    return columns, data, None, chart, summary


def execute_exception_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    for fieldname in ["rollback_run", "status", "severity", "category"]:
        if filters.get(fieldname):
            conditions.append(f"i.{fieldname} = %({fieldname})s")
            params[fieldname] = filters.get(fieldname)
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": ITEM_DOCTYPE, "width": 220},
        {"fieldname": "rollback_run", "label": _("Rollback Run"), "fieldtype": "Link", "options": RUN_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 180},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 320},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 460},
        {"fieldname": "recommendation", "label": _("Recommendation"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "source_doctype", "label": _("Source DocType"), "fieldtype": "Data", "width": 180},
        {"fieldname": "source_name", "label": _("Source Name"), "fieldtype": "Data", "width": 220},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]
    data = frappe.db.sql(
        f"""
        SELECT i.name AS item, i.rollback_run, i.status, i.severity, i.category,
            i.check_label, i.detail, i.recommendation, i.source_doctype, i.source_name, i.checked_on
        FROM `tab{ITEM_DOCTYPE}` i
        {build_where(conditions)}
        ORDER BY CASE i.status WHEN 'Blocker' THEN 1 WHEN 'Warning' THEN 2 WHEN 'Info' THEN 3 WHEN 'Pass' THEN 4 ELSE 5 END,
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


def execute_gl_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("voucher_no"):
        conditions.append("gl.voucher_no = %(voucher_no)s")
        params["voucher_no"] = filters.voucher_no
    if filters.get("voucher_type"):
        conditions.append("gl.voucher_type = %(voucher_type)s")
        params["voucher_type"] = filters.voucher_type
    else:
        conditions.append("gl.voucher_type IN ('Payment Entry', 'Sales Invoice')")
    columns = [
        {"fieldname": "voucher_type", "label": _("Voucher Type"), "fieldtype": "Data", "width": 140},
        {"fieldname": "voucher_no", "label": _("Voucher No"), "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 180},
        {"fieldname": "gl_entry", "label": _("GL Entry"), "fieldtype": "Link", "options": "GL Entry", "width": 220},
        {"fieldname": "account", "label": _("Account"), "fieldtype": "Link", "options": "Account", "width": 240},
        {"fieldname": "debit", "label": _("Debit"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "credit", "label": _("Credit"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "is_cancelled", "label": _("Is Cancelled"), "fieldtype": "Check", "width": 100},
        {"fieldname": "posting_date", "label": _("Posting Date"), "fieldtype": "Date", "width": 110},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT gl.voucher_type, gl.voucher_no, gl.name AS gl_entry, gl.account,
            gl.debit, gl.credit, gl.is_cancelled, gl.posting_date, %(currency)s AS currency
        FROM `tabGL Entry` gl
        {build_where(conditions)}
        ORDER BY gl.voucher_type, gl.voucher_no, gl.creation ASC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": ["Debit", "Credit"],
            "datasets": [{"name": "GL", "values": [sum(flt(row.debit) for row in data), sum(flt(row.credit) for row in data)]}],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("GL Rows"), "datatype": "Int"},
        {"value": sum(flt(row.debit) for row in data), "indicator": "Green", "label": _("Debit"), "datatype": "Currency", "currency": currency()},
        {"value": sum(flt(row.credit) for row in data), "indicator": "Green", "label": _("Credit"), "datatype": "Currency", "currency": currency()},
        {"value": sum(flt(row.debit) - flt(row.credit) for row in data), "indicator": "Blue", "label": _("Net"), "datatype": "Currency", "currency": currency()},
    ]
    return columns, data, None, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
