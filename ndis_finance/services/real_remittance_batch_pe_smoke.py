import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


SMOKE_ACK = "I_CONFIRM_PHASE7F_CREATE_ONE_CONTROLLED_BATCH_PAYMENT_ENTRY_SMOKE"
RUN_DOCTYPE = "NDIS Real Remittance Batch PE Smoke Run"
LINE_DOCTYPE = "NDIS Real Remittance Batch PE Smoke Line"
SOURCE_RUN_DOCTYPE = "NDIS Real Remittance Batch Source Harness Run"
SOURCE_LINE_DOCTYPE = "NDIS Real Remittance Batch Source Harness Line"


def make_smoke_run_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-REAL-REMITTANCE-BATCH-PE-SMOKE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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
        "batch_live_enabled_policy_count": count_dt("NDIS Real Remittance Batch Posting Policy", {"batch_live_enabled": 1}),
        "production_live_enabled_policy_count": count_dt("NDIS PE Production Posting Policy", {"production_posting_enabled": 1}),
    }


def latest_source_run():
    rows = frappe.get_all(
        SOURCE_RUN_DOCTYPE,
        filters={
            "status": "Source Created",
            "source_created_for_batch_smoke": 1,
            "ready_for_batch_smoke": 1,
            "batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "actual_payment_entry_created_count": 0,
            "actual_payment_entry_gl_created_count": 0,
        },
        fields=[
            "name",
            "source_run_id",
            "activation_gate",
            "adapter_run",
            "batch_preview",
            "design_gate",
            "company",
            "customer",
            "source_remittance_import",
            "max_batch_lines",
            "max_batch_amount",
            "eligible_source_line_count",
            "source_amount",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return frappe._dict(rows[0]) if rows else None


def get_source_lines(source_run):
    if not source_run:
        return []
    return frappe.get_all(
        SOURCE_LINE_DOCTYPE,
        filters={
            "source_run": source_run,
            "line_status": "Ready",
            "would_be_eligible_for_batch": 1,
        },
        fields=[
            "name",
            "line_no",
            "sales_invoice",
            "claim_line",
            "remittance_line",
            "source_amount",
            "invoice_outstanding",
            "expected_outcome",
        ],
        order_by="line_no asc, creation asc",
    )


def get_account_from_policy(company, fieldnames):
    if not frappe.db.exists("DocType", "NDIS PE Production Posting Policy"):
        return None
    meta = frappe.get_meta("NDIS PE Production Posting Policy")
    existing_fields = [field for field in fieldnames if meta.has_field(field)]
    if not existing_fields:
        return None
    rows = frappe.db.sql(
        f"""
        SELECT {", ".join(existing_fields)}
        FROM `tabNDIS PE Production Posting Policy`
        WHERE IFNULL(production_posting_enabled, 0) = 0
        ORDER BY modified DESC
        LIMIT 20
        """,
        as_dict=True,
    )
    for row in rows:
        for field in existing_fields:
            value = row.get(field)
            if value and frappe.db.exists("Account", value) and frappe.db.get_value("Account", value, "company") == company:
                return value
    return None


def get_bank_account(company):
    policy_account = get_account_from_policy(company, ["bank_account", "paid_to", "payment_account", "account_paid_to", "default_bank_account"])
    if policy_account:
        return policy_account
    known = "11510 - Every Day Bank Account - CHCPL"
    if frappe.db.exists("Account", known) and frappe.db.get_value("Account", known, "company") == company:
        return known
    return (
        frappe.db.get_value("Account", {"company": company, "account_type": ["in", ["Bank", "Cash"]], "is_group": 0, "disabled": 0}, "name")
        or frappe.db.get_value("Account", {"company": company, "root_type": "Asset", "is_group": 0, "disabled": 0}, "name")
    )


def get_receivable_account(company, source_lines):
    for line in source_lines:
        if line.sales_invoice and frappe.db.exists("Sales Invoice", line.sales_invoice):
            debit_to = frappe.db.get_value("Sales Invoice", line.sales_invoice, "debit_to")
            if debit_to:
                return debit_to
    policy_account = get_account_from_policy(company, ["receivable_account", "paid_from", "account_paid_from", "default_receivable_account"])
    if policy_account:
        return policy_account
    known = "12010 - Trade Debtors - CHCPL"
    if frappe.db.exists("Account", known) and frappe.db.get_value("Account", known, "company") == company:
        return known
    return frappe.db.get_value("Account", {"company": company, "account_type": "Receivable", "is_group": 0, "disabled": 0}, "name")


def validate_account(account, company, label):
    if not account or not frappe.db.exists("Account", account):
        return f"{label} is missing or invalid."
    account_doc = frappe.get_doc("Account", account)
    if account_doc.company != company:
        return f"{label} {account} does not belong to {company}."
    if int(account_doc.is_group or 0):
        return f"{label} {account} is a group account."
    if int(account_doc.disabled or 0):
        return f"{label} {account} is disabled."
    return None


def bank_account_for_ledger(account, company):
    if not account or not frappe.db.exists("DocType", "Bank Account"):
        return None
    rows = frappe.get_all(
        "Bank Account",
        filters={"account": account, "company": company, "is_company_account": 1},
        fields=["name"],
        order_by="creation desc",
        limit=1,
    )
    if rows:
        return rows[0].name
    rows = frappe.get_all("Bank Account", filters={"account": account, "company": company}, fields=["name"], order_by="creation desc", limit=1)
    return rows[0].name if rows else None


def gl_count_and_net_for_payment_entry(payment_entry):
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


def active_payment_entry_for_invoice(sales_invoice):
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


def existing_active_smoke_pe(source_run):
    if not frappe.db.has_column("Payment Entry", "custom_ndis_real_remittance_batch_pe_smoke"):
        return None
    rows = frappe.get_all(
        "Payment Entry",
        filters={
            "custom_ndis_real_remittance_batch_pe_smoke": 1,
            "custom_ndis_real_remittance_batch_source_run": source_run,
            "docstatus": ["!=", 2],
        },
        fields=["name", "docstatus"],
        order_by="creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def validate_source(source_run, source_lines, paid_from=None, paid_to=None):
    warnings = []
    blockers = []
    if not source_lines:
        blockers.append("No ready Phase 7E source lines found.")
    if int(source_run.eligible_source_line_count or 0) != len(source_lines):
        warnings.append(f"Source run expected {source_run.eligible_source_line_count} eligible lines; found {len(source_lines)} ready lines.")
    if len(source_lines) > int(source_run.max_batch_lines or 0):
        blockers.append("Source line count exceeds activation cap.")

    total = flt(sum(flt(line.source_amount or 0) for line in source_lines), 2)
    if total <= 0:
        blockers.append("Total source amount is not positive.")
    if total > flt(source_run.max_batch_amount or 0):
        blockers.append("Source amount exceeds activation cap.")

    customer = None
    seen_invoices = set()
    for line in source_lines:
        if not line.sales_invoice or not frappe.db.exists("Sales Invoice", line.sales_invoice):
            blockers.append(f"Line {line.line_no}: Sales Invoice missing.")
            continue
        si = frappe.get_doc("Sales Invoice", line.sales_invoice)
        if si.docstatus != 1:
            blockers.append(f"Line {line.line_no}: Sales Invoice {si.name} is not submitted.")
        if si.company != source_run.company:
            blockers.append(f"Line {line.line_no}: Sales Invoice {si.name} company mismatch.")
        if customer is None:
            customer = si.customer
        elif customer != si.customer:
            blockers.append("All controlled source invoices must use the same customer for one grouped batch PE.")
        if si.name in seen_invoices:
            blockers.append(f"Line {line.line_no}: duplicate Sales Invoice {si.name}.")
        seen_invoices.add(si.name)

        outstanding = flt(si.outstanding_amount or 0)
        amount = flt(line.source_amount or 0)
        if outstanding <= 0:
            blockers.append(f"Line {line.line_no}: Sales Invoice {si.name} has no outstanding amount.")
        if amount <= 0:
            blockers.append(f"Line {line.line_no}: source amount is not positive.")
        if amount > outstanding:
            blockers.append(f"Line {line.line_no}: source amount exceeds invoice outstanding.")
        active_pe = active_payment_entry_for_invoice(si.name)
        if active_pe:
            blockers.append(f"Line {line.line_no}: active Payment Entry already exists for {si.name}: {active_pe.name}.")

    existing = existing_active_smoke_pe(source_run.name)
    if existing:
        blockers.append(f"Active Phase 7F smoke Payment Entry already exists: {existing.name}.")

    for account, label in [(paid_from, "Receivable account"), (paid_to, "Bank account")]:
        issue = validate_account(account, source_run.company, label)
        if issue:
            blockers.append(issue)

    return {
        "warnings": warnings,
        "blockers": blockers,
        "customer": customer or source_run.customer,
        "total_amount": total,
        "invoice_count": len(source_lines),
    }


def set_if_has(doc, fieldname, value):
    if doc.meta.has_field(fieldname):
        setattr(doc, fieldname, value)


def create_payment_entry(source_run, source_lines, smoke_run_name, paid_from, paid_to, customer, total_amount):
    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = "Receive"
    pe.company = source_run.company
    pe.posting_date = today()
    pe.party_type = "Customer"
    pe.party = customer
    pe.paid_from = paid_from
    pe.paid_to = paid_to
    bank_account = bank_account_for_ledger(paid_to, source_run.company)
    if bank_account:
        pe.bank_account = bank_account
    pe.paid_amount = flt(total_amount)
    pe.received_amount = flt(total_amount)
    pe.source_exchange_rate = 1
    pe.target_exchange_rate = 1
    pe.base_paid_amount = flt(total_amount)
    pe.base_received_amount = flt(total_amount)
    pe.reference_no = smoke_run_name
    pe.reference_date = today()
    pe.remarks = "Phase 7F controlled real remittance batch Payment Entry smoke. Rollback required in Phase 7G."
    account_currency = frappe.get_cached_value("Company", source_run.company, "default_currency") or currency()
    set_if_has(pe, "paid_from_account_currency", account_currency)
    set_if_has(pe, "paid_to_account_currency", account_currency)
    set_if_has(pe, "custom_ndis_real_remittance_batch_pe_smoke", 1)
    set_if_has(pe, "custom_ndis_real_remittance_batch_pe_smoke_run", smoke_run_name)
    set_if_has(pe, "custom_ndis_real_remittance_batch_source_run", source_run.name)
    set_if_has(pe, "custom_ndis_real_remittance_batch_pe_amount", total_amount)
    for line in source_lines:
        si = frappe.get_doc("Sales Invoice", line.sales_invoice)
        amount = flt(line.source_amount or 0)
        pe.append(
            "references",
            {
                "reference_doctype": "Sales Invoice",
                "reference_name": si.name,
                "total_amount": flt(si.grand_total or si.rounded_total or amount),
                "outstanding_amount": flt(si.outstanding_amount or amount),
                "allocated_amount": amount,
            },
        )
    pe.insert(ignore_permissions=True)
    pe.submit()
    return pe.name


def create_smoke_line(smoke_run, source_run, source_line, payment_entry, outstanding_before):
    after = frappe.db.get_value("Sales Invoice", source_line.sales_invoice, "outstanding_amount") or 0
    doc = frappe.new_doc(LINE_DOCTYPE)
    doc.smoke_run = smoke_run
    doc.line_no = source_line.line_no
    doc.line_label = f"Phase 7F PE Smoke Line {source_line.line_no}"
    doc.line_status = "Submitted"
    doc.source_run = source_run
    doc.source_line = source_line.name
    doc.sales_invoice = source_line.sales_invoice
    doc.claim_line = source_line.claim_line
    doc.remittance_line = source_line.remittance_line
    doc.payment_entry = payment_entry
    doc.invoice_outstanding_before = flt(outstanding_before or 0)
    doc.allocated_amount = flt(source_line.source_amount or 0)
    doc.invoice_outstanding_after = flt(after or 0)
    doc.checked_on = now_datetime()
    doc.insert(ignore_permissions=True)


def add_item(items, status, severity, category, check_key, check_label, detail):
    items.append({"status": status, "severity": severity, "category": category, "check_key": check_key, "check_label": check_label, "detail": detail})


def summarise_items(items):
    return {
        "blocker_count": len([item for item in items if item["status"] == "Blocker"]),
        "warning_count": len([item for item in items if item["status"] == "Warning"]),
        "pass_count": len([item for item in items if item["status"] == "Pass"]),
        "info_count": len([item for item in items if item["status"] == "Info"]),
        "item_count": len(items),
    }


def calculate_score(blockers, warnings):
    return max(0, round(100 - int(blockers or 0) * 25 - int(warnings or 0) * 5, 2))


@frappe.whitelist()
def run_real_remittance_batch_pe_smoke(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_real_remittance_batch_pe_smoke")

    source_run = latest_source_run()
    if not source_run:
        frappe.throw(_("No Phase 7E source harness run ready for controlled batch smoke."))

    config = config_state()
    guard_before = guardrails()
    source_lines = get_source_lines(source_run.name)
    paid_from = get_receivable_account(source_run.company, source_lines)
    paid_to = get_bank_account(source_run.company)
    source_validation = validate_source(source_run, source_lines, paid_from=paid_from, paid_to=paid_to)
    ack_ok = acknowledgement == SMOKE_ACK

    items = []
    add_item(items, "Blocker" if config["production_mode"] else "Pass", "Critical" if config["production_mode"] else "Low", "Site Config", "production_mode", "Production mode", "Production mode is enabled." if config["production_mode"] else "Production mode remains disabled.")
    add_item(items, "Blocker" if config["live_pe_enabled"] else "Pass", "Critical" if config["live_pe_enabled"] else "Low", "Site Config", "live_pe_enabled", "Live PE posting config", "Live PE posting config is enabled." if config["live_pe_enabled"] else "Live PE posting remains disabled.")
    if guard_before["batch_live_enabled_policy_count"] == 0 and guard_before["production_live_enabled_policy_count"] == 0:
        add_item(items, "Pass", "Low", "Guardrail", "live_policies", "Live policies", "No live-enabled batch or production PE policies.")
    else:
        add_item(items, "Blocker", "Critical", "Guardrail", "live_policies", "Live policies", "Live-enabled policy exists.")
    add_item(items, "Pass" if paid_from else "Blocker", "Low" if paid_from else "Critical", "Account", "paid_from", "Receivable account", f"Receivable account resolved: {paid_from}." if paid_from else "Could not resolve receivable account.")
    add_item(items, "Pass" if paid_to else "Blocker", "Low" if paid_to else "Critical", "Account", "paid_to", "Bank account", f"Bank account resolved: {paid_to}." if paid_to else "Could not resolve bank account.")
    for blocker in source_validation["blockers"]:
        add_item(items, "Blocker", "Critical", "Source", "source_validation", "Source validation", blocker)
    for warning in source_validation["warnings"]:
        add_item(items, "Warning", "Medium", "Source", "source_warning", "Source warning", warning)
    add_item(items, "Pass" if ack_ok else "Warning", "Low" if ack_ok else "Medium", "Acknowledgement", "smoke_ack", "Smoke acknowledgement", "Exact acknowledgement supplied." if ack_ok else f"Required acknowledgement not supplied: {SMOKE_ACK}")

    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    smoke_allowed = int(ack_ok and item_summary["blocker_count"] == 0)
    outstanding_before_total = flt(sum(flt(frappe.db.get_value("Sales Invoice", line.sales_invoice, "outstanding_amount") or 0) for line in source_lines), 2)

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Submitted" if smoke_allowed else "Needs Review",
        "smoke_status": "Submitted - Rollback Required" if smoke_allowed else "Audit Only",
        "controlled_smoke_submitted": 0,
        "rollback_required": 0,
        "freeze_required_after_rollback": 0,
        "batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "source_run": source_run.name,
        "activation_gate": source_run.activation_gate,
        "adapter_run": source_run.adapter_run,
        "batch_preview": source_run.batch_preview,
        "design_gate": source_run.design_gate,
        "company": source_run.company,
        "customer": source_validation["customer"],
        "paid_from": paid_from,
        "paid_to": paid_to,
        "source_line_count": len(source_lines),
        "invoice_count": source_validation["invoice_count"],
        "payment_entry_reference_count": len(source_lines) if smoke_allowed else 0,
        "payment_entry_count_created": 0,
        "payment_entry_submitted_count": 0,
        "payment_entry_amount": source_validation["total_amount"],
        "invoice_outstanding_before_total": outstanding_before_total,
        "invoice_outstanding_after_total": 0,
        "payment_entry_gl_count": 0,
        "payment_entry_gl_net": 0,
        "smoke_score": score,
        **item_summary,
        "items": items,
        "guardrails_before": guard_before,
        "guardrails_after": guardrails(),
        "config": config,
        "required_acknowledgement": SMOKE_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 7F creates exactly one controlled tagged submitted Payment Entry. Rollback is required in Phase 7G.",
    }
    if int(dry_run or 0):
        return result

    run = frappe.new_doc(RUN_DOCTYPE)
    run.smoke_run_id = make_smoke_run_id()
    for fieldname, value in result.items():
        if run.meta.has_field(fieldname):
            setattr(run, fieldname, value)
    run.site_name = frappe.local.site
    run.sandbox_config_enabled = config["sandbox_enabled"]
    run.production_mode_detected = config["production_mode"]
    run.live_payment_entry_posting_config = config["live_pe_enabled"]
    run.checked_on = now_datetime()
    run.checked_by = frappe.session.user
    run.payment_entry_count_before = guard_before["payment_entry_count"]
    run.payment_entry_count_after = guardrails()["payment_entry_count"]
    run.payment_entry_gl_count_before = guard_before["payment_entry_gl_count"]
    run.payment_entry_gl_count_after = guardrails()["payment_entry_gl_count"]
    run.submitted_journal_entry_count_today = guard_before["submitted_journal_entry_count_today"]
    run.purchase_invoice_count_today = guard_before["purchase_invoice_count_today"]
    run.batch_live_enabled_policy_count = guard_before["batch_live_enabled_policy_count"]
    run.production_live_enabled_policy_count = guard_before["production_live_enabled_policy_count"]
    run.required_acknowledgement = SMOKE_ACK
    run.acknowledgement = acknowledgement
    run.acknowledgement_ok = int(ack_ok)
    run.summary_json = safe_json(result)
    run.notes = notes
    run.insert(ignore_permissions=True)

    payment_entry = None
    if smoke_allowed:
        outstanding_before = {
            line.name: flt(frappe.db.get_value("Sales Invoice", line.sales_invoice, "outstanding_amount") or 0)
            for line in source_lines
        }
        payment_entry = create_payment_entry(
            source_run=source_run,
            source_lines=source_lines,
            smoke_run_name=run.name,
            paid_from=paid_from,
            paid_to=paid_to,
            customer=source_validation["customer"],
            total_amount=source_validation["total_amount"],
        )
        for line in source_lines:
            create_smoke_line(run.name, source_run.name, line, payment_entry, outstanding_before.get(line.name))

    pe_gl_count, pe_gl_net = gl_count_and_net_for_payment_entry(payment_entry)
    guard_after = guardrails()
    invoice_outstanding_after_total = flt(sum(flt(frappe.db.get_value("Sales Invoice", line.sales_invoice, "outstanding_amount") or 0) for line in source_lines), 2)
    updates = {
        "payment_entry": payment_entry,
        "controlled_smoke_submitted": 1 if payment_entry else 0,
        "rollback_required": 1 if payment_entry else 0,
        "freeze_required_after_rollback": 1 if payment_entry else 0,
        "payment_entry_count_created": 1 if payment_entry else 0,
        "payment_entry_submitted_count": 1 if payment_entry else 0,
        "payment_entry_reference_count": len(source_lines) if payment_entry else 0,
        "invoice_outstanding_after_total": invoice_outstanding_after_total,
        "payment_entry_gl_count": pe_gl_count,
        "payment_entry_gl_net": pe_gl_net,
        "payment_entry_count_after": guard_after["payment_entry_count"],
        "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
    }
    result.update(updates)
    result["created"] = True
    result["smoke_run"] = run.name
    result["smoke_run_id"] = run.smoke_run_id
    result["payment_entry"] = payment_entry
    result["guardrails_after"] = guard_after
    updates["summary_json"] = safe_json(result)
    frappe.db.set_value(RUN_DOCTYPE, run.name, updates, update_modified=False)
    frappe.db.commit()
    return result


@frappe.whitelist()
def cancel_real_remittance_batch_pe_smoke(smoke_run, reason=None):
    assert_action("cancel_real_remittance_batch_pe_smoke")
    if not frappe.db.exists(RUN_DOCTYPE, smoke_run):
        frappe.throw(_("PE smoke run not found: {0}").format(smoke_run))
    doc = frappe.get_doc(RUN_DOCTYPE, smoke_run)
    if doc.status == "Cancelled":
        return {"smoke_run": smoke_run, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.controlled_smoke_submitted or 0) or doc.payment_entry:
        frappe.throw(_("Cannot cancel a submitted controlled PE smoke. Roll it back in Phase 7G instead."))
    frappe.db.set_value(
        RUN_DOCTYPE,
        smoke_run,
        {
            "status": "Cancelled",
            "smoke_status": "Cancelled",
            "controlled_smoke_submitted": 0,
            "rollback_required": 0,
            "freeze_required_after_rollback": 0,
            "batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 7F PE smoke audit cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{LINE_DOCTYPE}` SET line_status = 'Cancelled' WHERE smoke_run = %(smoke_run)s", {"smoke_run": smoke_run})
    frappe.db.commit()
    return {"smoke_run": smoke_run, "status": "Cancelled", "note": "PE smoke audit record cancelled only. No accounting movement occurred."}


@frappe.whitelist()
def quick_real_remittance_batch_pe_smoke_summary(limit=20):
    runs = frappe.get_all(
        RUN_DOCTYPE,
        fields=[
            "name",
            "smoke_run_id",
            "status",
            "smoke_status",
            "controlled_smoke_submitted",
            "rollback_required",
            "freeze_required_after_rollback",
            "batch_posting_allowed",
            "real_posting_allowed",
            "source_run",
            "company",
            "customer",
            "payment_entry",
            "invoice_count",
            "payment_entry_reference_count",
            "payment_entry_count_created",
            "payment_entry_submitted_count",
            "payment_entry_amount",
            "invoice_outstanding_before_total",
            "invoice_outstanding_after_total",
            "payment_entry_gl_count",
            "payment_entry_gl_net",
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
            "smoke_run",
            "line_no",
            "line_status",
            "sales_invoice",
            "payment_entry",
            "invoice_outstanding_before",
            "allocated_amount",
            "invoice_outstanding_after",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "runs": runs,
        "lines": lines,
        "required_acknowledgement": SMOKE_ACK,
        "guardrails": guardrails(),
        "config": config_state(),
        "note": "Phase 7F PE smoke summary. Rollback required in Phase 7G after submitted smoke.",
    }


def smoke_columns():
    return [
        {"fieldname": "smoke_run", "label": _("Smoke Run"), "fieldtype": "Link", "options": RUN_DOCTYPE, "width": 220},
        {"fieldname": "smoke_run_id", "label": _("Smoke Run ID"), "fieldtype": "Data", "width": 390},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "smoke_status", "label": _("Smoke Status"), "fieldtype": "Data", "width": 260},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 170},
        {"fieldname": "invoice_count", "label": _("Invoices"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_reference_count", "label": _("References"), "fieldtype": "Int", "width": 100},
        {"fieldname": "payment_entry_amount", "label": _("PE Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "invoice_outstanding_before_total", "label": _("Outstanding Before"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "invoice_outstanding_after_total", "label": _("Outstanding After"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "payment_entry_gl_count", "label": _("PE GL Count"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_net", "label": _("PE GL Net"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "rollback_required", "label": _("Rollback Required"), "fieldtype": "Check", "width": 130},
        {"fieldname": "batch_posting_allowed", "label": _("Batch Posting Allowed"), "fieldtype": "Check", "width": 160},
        {"fieldname": "real_posting_allowed", "label": _("Real Posting Allowed"), "fieldtype": "Check", "width": 150},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_smoke_report(filters=None):
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
            r.name AS smoke_run,
            r.smoke_run_id,
            r.status,
            r.smoke_status,
            r.controlled_smoke_submitted,
            r.rollback_required,
            r.batch_posting_allowed,
            r.real_posting_allowed,
            r.source_run,
            r.company,
            r.customer,
            r.payment_entry,
            r.invoice_count,
            r.payment_entry_reference_count,
            r.payment_entry_count_created,
            r.payment_entry_submitted_count,
            r.payment_entry_amount,
            r.invoice_outstanding_before_total,
            r.invoice_outstanding_after_total,
            r.payment_entry_gl_count,
            r.payment_entry_gl_net,
            r.payment_entry_count_before,
            r.payment_entry_count_after,
            r.payment_entry_gl_count_before,
            r.payment_entry_gl_count_after,
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
            "labels": [row.smoke_run_id for row in data[:20]],
            "datasets": [
                {"name": "Submitted PE", "values": [int(row.payment_entry_submitted_count or 0) for row in data[:20]]},
                {"name": "PE GL", "values": [int(row.payment_entry_gl_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Smoke Runs"), "datatype": "Int"},
        {"value": sum(int(row.payment_entry_submitted_count or 0) for row in data), "indicator": "Green", "label": _("Submitted PEs"), "datatype": "Int"},
        {"value": sum(flt(row.payment_entry_amount or 0) for row in data), "indicator": "Blue", "label": _("PE Amount"), "datatype": "Currency", "currency": currency()},
        {"value": sum(int(row.rollback_required or 0) for row in data), "indicator": "Orange", "label": _("Rollback Required"), "datatype": "Int"},
    ]
    return smoke_columns(), data, None, chart, summary


def execute_line_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("smoke_run"):
        conditions.append("l.smoke_run = %(smoke_run)s")
        params["smoke_run"] = filters.get("smoke_run")
    if filters.get("line_status"):
        conditions.append("l.line_status = %(line_status)s")
        params["line_status"] = filters.get("line_status")
    columns = [
        {"fieldname": "line", "label": _("Line"), "fieldtype": "Link", "options": LINE_DOCTYPE, "width": 220},
        {"fieldname": "smoke_run", "label": _("Smoke Run"), "fieldtype": "Link", "options": RUN_DOCTYPE, "width": 220},
        {"fieldname": "line_no", "label": _("Line No"), "fieldtype": "Int", "width": 80},
        {"fieldname": "line_status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "sales_invoice", "label": _("Sales Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 170},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 170},
        {"fieldname": "invoice_outstanding_before", "label": _("Outstanding Before"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "allocated_amount", "label": _("Allocated"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "invoice_outstanding_after", "label": _("Outstanding After"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            l.name AS line,
            l.smoke_run,
            l.line_no,
            l.line_status,
            l.sales_invoice,
            l.payment_entry,
            l.invoice_outstanding_before,
            l.allocated_amount,
            l.invoice_outstanding_after,
            l.checked_on,
            %(currency)s AS currency
        FROM `tab{LINE_DOCTYPE}` l
        {build_where(conditions)}
        ORDER BY l.smoke_run DESC, l.line_no ASC
        """,
        params,
        as_dict=True,
    )
    chart = {"data": {"labels": [str(row.line_no) for row in data[:20]], "datasets": [{"name": "Allocated", "values": [flt(row.allocated_amount or 0) for row in data[:20]]}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Lines"), "datatype": "Int"},
        {"value": sum(flt(row.allocated_amount or 0) for row in data), "indicator": "Green", "label": _("Allocated"), "datatype": "Currency", "currency": currency()},
    ]
    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_smoke_report(filters)
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
