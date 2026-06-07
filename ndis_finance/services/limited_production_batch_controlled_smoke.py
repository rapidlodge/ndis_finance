import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


SMOKE_ACK = "I_CONFIRM_PHASE9F_SUBMIT_ONE_LIMITED_PRODUCTION_BATCH_PAYMENT_ENTRY"


def make_smoke_run_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-LIMITED-PROD-BATCH-SMOKE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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
        "production_batch_enabled_policy_count": count_dt("NDIS Controlled Production Batch Posting Policy", {"production_batch_enabled": 1}),
        "live_posting_allowed_policy_count": count_dt("NDIS Controlled Production Batch Posting Policy", {"live_posting_allowed": 1}),
        "submitted_phase9f_smoke_pe_count": submitted_phase9f_smoke_pe_count(),
    }


def submitted_phase9f_smoke_pe_count():
    if not frappe.db.has_column("Payment Entry", "custom_ndis_limited_prod_batch_smoke"):
        return 0

    return count_dt(
        "Payment Entry",
        {
            "docstatus": 1,
            "custom_ndis_limited_prod_batch_smoke": 1,
        },
    )


def latest_activation_gate():
    rows = frappe.get_all(
        "NDIS Limited Production Batch Activation Gate",
        filters={
            "status": "Activation Allowed",
            "limited_activation_allowed": 1,
            "ready_for_limited_batch_smoke": 1,
            "adapter_hard_block_verified": 1,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
        },
        fields=[
            "name",
            "activation_gate_id",
            "adapter_run",
            "policy_preview",
            "policy_design",
            "policy_review_gate",
            "phase8g_freeze",
            "source_preview",
            "company",
            "customer",
            "policy_mode",
            "max_batch_lines",
            "max_batch_amount",
            "max_payment_entry_count",
            "allowed_reference_doctype",
            "would_create_payment_entry_count",
            "would_create_reference_count",
            "would_create_payment_entry_amount",
            "allowed_smoke_payment_entry_count",
            "allowed_smoke_reference_count",
            "allowed_smoke_amount",
            "rollback_required_after_smoke",
            "freeze_required_after_rollback",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )

    return rows[0] if rows else None


def existing_submitted_smoke(activation_gate):
    if not frappe.db.has_column("Payment Entry", "custom_ndis_limited_prod_batch_activation_gate"):
        return None

    rows = frappe.get_all(
        "Payment Entry",
        filters={
            "docstatus": 1,
            "custom_ndis_limited_prod_batch_smoke": 1,
            "custom_ndis_limited_prod_batch_activation_gate": activation_gate,
        },
        fields=["name"],
        limit=1,
    )

    return rows[0] if rows else None


def get_adapter_lines(adapter_run):
    if not adapter_run:
        return []

    return frappe.get_all(
        "NDIS Limited Production Batch Adapter Run Line",
        filters={
            "adapter_run": adapter_run,
            "line_status": "Hard Blocked",
            "hard_block_verified": 1,
            "would_create_payment_entry": 1,
            "would_create_reference": 1,
            "actual_payment_entry_created": 0,
            "actual_gl_created": 0,
            "policy_live_enabled": 0,
        },
        fields=[
            "name",
            "line_no",
            "sales_invoice",
            "claim_line",
            "remittance_line",
            "invoice_outstanding",
            "allocatable_amount",
        ],
        order_by="line_no asc, creation asc",
    )


def invoice_outstanding_total(lines):
    total = 0
    for line in lines:
        if line.sales_invoice and frappe.db.exists("Sales Invoice", line.sales_invoice):
            total += flt(frappe.db.get_value("Sales Invoice", line.sales_invoice, "outstanding_amount") or 0)
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


def sales_invoice_outstanding(sales_invoice):
    if not sales_invoice or not frappe.db.exists("Sales Invoice", sales_invoice):
        return 0
    return flt(frappe.db.get_value("Sales Invoice", sales_invoice, "outstanding_amount") or 0, 2)


def get_existing_payment_accounts(company, customer):
    filters = {
        "payment_type": "Receive",
        "company": company,
        "party_type": "Customer",
        "docstatus": ["in", [1, 2]],
    }

    if customer:
        filters["party"] = customer

    rows = frappe.get_all(
        "Payment Entry",
        filters=filters,
        fields=["name", "paid_from", "paid_to", "bank_account", "mode_of_payment"],
        order_by="creation desc",
        limit=1,
    )

    return rows[0] if rows else None


def account_exists(account):
    return bool(account and frappe.db.exists("Account", account))


def bank_account_exists(bank_account):
    return bool(bank_account and frappe.db.exists("Bank Account", bank_account))


def find_bank_account_for_account(account):
    if not account or not frappe.db.exists("DocType", "Bank Account"):
        return None

    for filters in [
        {"account": account, "is_company_account": 1},
        {"account": account},
    ]:
        rows = frappe.get_all("Bank Account", filters=filters, pluck="name", limit=1)
        if rows:
            return rows[0]

    return None


def find_bank_account(company):
    rows = frappe.get_all(
        "Account",
        filters={
            "company": company,
            "is_group": 0,
            "account_type": "Bank",
        },
        pluck="name",
        order_by="name asc",
        limit=1,
    )

    return rows[0] if rows else None


def find_receivable_account(company):
    rows = frappe.get_all(
        "Account",
        filters={
            "company": company,
            "is_group": 0,
            "account_type": "Receivable",
        },
        pluck="name",
        order_by="name asc",
        limit=1,
    )

    return rows[0] if rows else None


def resolve_accounts(company, customer):
    existing = get_existing_payment_accounts(company, customer)

    paid_from = existing.paid_from if existing else None
    paid_to = existing.paid_to if existing else None
    bank_account = existing.bank_account if existing else None
    mode_of_payment = existing.mode_of_payment if existing else None

    if not account_exists(paid_from):
        for candidate in [
            "12010 - Trade Debtors - CHCPL",
            frappe.db.get_value("Company", company, "default_receivable_account") if company else None,
            find_receivable_account(company),
        ]:
            if account_exists(candidate):
                paid_from = candidate
                break

    if not account_exists(paid_to):
        for candidate in [
            "11510 - Every Day Bank Account - CHCPL",
            frappe.db.get_value("Company", company, "default_bank_account") if company else None,
            find_bank_account(company),
        ]:
            if account_exists(candidate):
                paid_to = candidate
                break

    if not bank_account_exists(bank_account):
        bank_account = find_bank_account_for_account(paid_to)

    if not mode_of_payment:
        for candidate in ["Bank Transfer", "EFT", "Electronic Funds Transfer"]:
            if frappe.db.exists("Mode of Payment", candidate):
                mode_of_payment = candidate
                break

    return frappe._dict(
        {
            "paid_from": paid_from,
            "paid_to": paid_to,
            "bank_account": bank_account,
            "mode_of_payment": mode_of_payment,
        }
    )


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


def validate_source(gate, lines, accounts, guard):
    issues = []

    if not gate:
        issues.append("No approved Phase 9E activation gate found.")
        return issues

    if existing_submitted_smoke(gate.name):
        issues.append("A submitted Phase 9F smoke Payment Entry already exists for this activation gate.")

    if int(gate.allowed_smoke_payment_entry_count or 0) != 1:
        issues.append("Allowed smoke Payment Entry count must be 1.")

    if int(gate.allowed_smoke_reference_count or 0) != 2:
        issues.append("Allowed smoke reference count must be 2.")

    if flt(gate.allowed_smoke_amount or 0, 2) != 2:
        issues.append("Allowed smoke amount must be 2.00.")

    if int(gate.rollback_required_after_smoke or 0) != 1:
        issues.append("Rollback required flag is missing.")

    if int(gate.freeze_required_after_rollback or 0) != 1:
        issues.append("Freeze required after rollback flag is missing.")

    if len(lines) != 2:
        issues.append(f"Expected exactly 2 hard-blocked source lines. Found {len(lines)}.")

    total = flt(sum(flt(line.allocatable_amount or 0) for line in lines), 2)

    if total != 2:
        issues.append(f"Expected allocatable smoke amount 2.00. Found {total}.")

    invoice_names = set()

    for line in lines:
        if not line.sales_invoice:
            issues.append(f"Source line {line.line_no} has no Sales Invoice.")
            continue

        if line.sales_invoice in invoice_names:
            issues.append(f"Duplicate Sales Invoice in smoke lines: {line.sales_invoice}")

        invoice_names.add(line.sales_invoice)

        if not frappe.db.exists("Sales Invoice", line.sales_invoice):
            issues.append(f"Sales Invoice does not exist: {line.sales_invoice}")
            continue

        docstatus = int(frappe.db.get_value("Sales Invoice", line.sales_invoice, "docstatus") or 0)
        if docstatus != 1:
            issues.append(f"Sales Invoice is not submitted: {line.sales_invoice}")

        outstanding = sales_invoice_outstanding(line.sales_invoice)
        if outstanding < flt(line.allocatable_amount or 0, 2):
            issues.append(f"Sales Invoice outstanding is below allocation for {line.sales_invoice}.")

    if not account_exists(accounts.paid_from):
        issues.append("Paid From receivable account is not resolved.")

    if not account_exists(accounts.paid_to):
        issues.append("Paid To bank account is not resolved.")

    if frappe.get_meta("Payment Entry").has_field("bank_account") and not bank_account_exists(accounts.bank_account):
        issues.append("Payment Entry bank_account is required/resolved poorly. No valid Bank Account found.")

    if guard["submitted_phase9f_smoke_pe_count"] != 0:
        issues.append("There is already a submitted Phase 9F smoke Payment Entry.")

    if guard["production_batch_enabled_policy_count"] != 0:
        issues.append("Controlled production batch enabled policy count is not zero.")

    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count is not zero.")

    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today is not zero.")

    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today is not zero.")

    return issues


def build_items(gate, lines, accounts, guard, issues, ack_ok):
    items = []

    if gate:
        add_item(items, "Pass", "Low", "Activation Gate", "phase9e_gate_exists", "Phase 9E activation gate exists", f"Activation gate found: {gate.activation_gate_id}.")
    else:
        add_item(items, "Blocker", "Critical", "Activation Gate", "phase9e_gate_exists", "Phase 9E activation gate exists", "No approved Phase 9E activation gate found.")

    if not issues:
        add_item(items, "Pass", "Low", "Smoke Source", "smoke_source_valid", "Smoke source valid", "Activation gate, source invoices, accounts, and caps are valid.")
    else:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Smoke Source", "smoke_source_valid", "Smoke source valid", issue)

    add_item(items, "Pass", "Low", "Accounts", "paid_from", "Paid From", accounts.paid_from or "Not resolved")
    add_item(items, "Pass", "Low", "Accounts", "paid_to", "Paid To", accounts.paid_to or "Not resolved")
    add_item(items, "Pass", "Low", "Accounts", "bank_account", "Bank Account", accounts.bank_account or "Not resolved")

    if guard["production_batch_enabled_policy_count"] == 0 and guard["live_posting_allowed_policy_count"] == 0:
        add_item(items, "Pass", "Low", "Policy Safety", "live_policies_zero", "Live policies", "No controlled production live-enabled policies.")
    else:
        add_item(items, "Blocker", "Critical", "Policy Safety", "live_policies_zero", "Live policies", "Live-enabled controlled production policy found.")

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "smoke_ack", "Smoke acknowledgement", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "smoke_ack", "Smoke acknowledgement", f"Required acknowledgement not supplied: {SMOKE_ACK}")

    return items


def create_draft_payment_entry(run_doc, gate, lines, accounts):
    amount = flt(sum(flt(line.allocatable_amount or 0) for line in lines), 2)

    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = "Receive"
    pe.company = gate.company
    pe.posting_date = today()
    pe.party_type = "Customer"
    pe.party = gate.customer
    pe.paid_from = accounts.paid_from
    pe.paid_to = accounts.paid_to
    pe.paid_amount = amount
    pe.received_amount = amount
    pe.reference_no = run_doc.smoke_run_id
    pe.reference_date = today()
    pe.remarks = f"Phase 9F limited production batch controlled smoke: {run_doc.smoke_run_id}"

    if pe.meta.has_field("bank_account") and accounts.bank_account:
        pe.bank_account = accounts.bank_account

    if pe.meta.has_field("mode_of_payment") and accounts.mode_of_payment:
        pe.mode_of_payment = accounts.mode_of_payment

    if pe.meta.has_field("custom_ndis_limited_prod_batch_smoke"):
        pe.custom_ndis_limited_prod_batch_smoke = 1

    if pe.meta.has_field("custom_ndis_limited_prod_batch_smoke_run"):
        pe.custom_ndis_limited_prod_batch_smoke_run = run_doc.name

    if pe.meta.has_field("custom_ndis_limited_prod_batch_activation_gate"):
        pe.custom_ndis_limited_prod_batch_activation_gate = gate.name

    if pe.meta.has_field("custom_ndis_limited_prod_batch_policy_preview"):
        pe.custom_ndis_limited_prod_batch_policy_preview = gate.policy_preview

    for line in lines:
        pe.append(
            "references",
            {
                "reference_doctype": "Sales Invoice",
                "reference_name": line.sales_invoice,
                "allocated_amount": flt(line.allocatable_amount or 0, 2),
            },
        )

    pe.insert(ignore_permissions=True)
    return pe


def create_smoke_lines(run_doc, lines, payment_entry):
    for line in lines:
        row = frappe.new_doc("NDIS Limited Production Batch Smoke Run Line")
        row.smoke_run = run_doc.name
        row.line_no = line.line_no
        row.line_label = f"Phase 9F Smoke Line {line.line_no}"
        row.line_status = "Submitted"
        row.payment_entry = payment_entry
        row.sales_invoice = line.sales_invoice
        row.claim_line = line.claim_line
        row.remittance_line = line.remittance_line
        row.invoice_outstanding_before = flt(line.invoice_outstanding or 0, 2)
        row.allocated_amount = flt(line.allocatable_amount or 0, 2)
        row.invoice_outstanding_after = sales_invoice_outstanding(line.sales_invoice)
        row.payment_entry_reference_created = 1
        row.gl_created = 1
        row.rollback_required = 1
        row.checked_on = run_doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_limited_production_batch_controlled_smoke(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_limited_production_batch_controlled_smoke")

    gate = latest_activation_gate()
    lines = get_adapter_lines(gate.adapter_run) if gate else []
    accounts = resolve_accounts(gate.company, gate.customer) if gate else frappe._dict({"paid_from": None, "paid_to": None, "bank_account": None, "mode_of_payment": None})

    config = config_state()
    guard_before = guardrails()
    ack_ok = acknowledgement == SMOKE_ACK

    issues = validate_source(gate, lines, accounts, guard_before)
    items = build_items(gate, lines, accounts, guard_before, issues, ack_ok)

    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    amount = flt(sum(flt(line.allocatable_amount or 0) for line in lines), 2)
    outstanding_before = invoice_outstanding_total(lines)

    should_submit = int(ack_ok and item_summary["blocker_count"] == 0 and gate and not int(dry_run or 0))

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Submitted - Rollback Required" if should_submit else "Needs Review",
        "smoke_status": "Submitted - Rollback Required" if should_submit else "Needs Review",
        "limited_batch_smoke_submitted": 1 if should_submit else 0,
        "rollback_required": 1 if should_submit else 0,
        "freeze_required_after_rollback": 1 if should_submit else 0,
        "production_batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "policy_live_enabled": 0,
        "activation_gate": gate.name if gate else None,
        "adapter_run": gate.adapter_run if gate else None,
        "policy_preview": gate.policy_preview if gate else None,
        "policy_design": gate.policy_design if gate else None,
        "policy_review_gate": gate.policy_review_gate if gate else None,
        "phase8g_freeze": gate.phase8g_freeze if gate else None,
        "source_preview": gate.source_preview if gate else None,
        "company": gate.company if gate else None,
        "customer": gate.customer if gate else None,
        "bank_account": accounts.bank_account,
        "paid_from": accounts.paid_from,
        "paid_to": accounts.paid_to,
        "policy_mode": gate.policy_mode if gate else "Limited Controlled Production Batch",
        "max_batch_lines": int(gate.max_batch_lines or 0) if gate else 0,
        "max_batch_amount": flt(gate.max_batch_amount or 0) if gate else 0,
        "max_payment_entry_count": int(gate.max_payment_entry_count or 0) if gate else 0,
        "allowed_reference_count": int(gate.allowed_smoke_reference_count or 0) if gate else 0,
        "allowed_smoke_amount": flt(gate.allowed_smoke_amount or 0) if gate else 0,
        "payment_entry": None,
        "payment_entry_docstatus": 0,
        "payment_entry_amount": amount,
        "reference_count": len(lines),
        "invoice_outstanding_before_total": outstanding_before,
        "invoice_outstanding_after_total": outstanding_before,
        "payment_entry_gl_count": 0,
        "payment_entry_gl_net": 0,
        "payment_entry_created_count": 0,
        "payment_entry_submitted_count": 0,
        "gl_created_count": 0,
        "smoke_score": score,
        **item_summary,
        "items": items,
        "guardrails_before": guard_before,
        "guardrails_after": guardrails(),
        "config": config,
        "required_acknowledgement": SMOKE_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 9F submits exactly one controlled tagged Payment Entry only when exact acknowledgement is supplied.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["smoke_status"] = "Needs Review"
        result["limited_batch_smoke_submitted"] = 0
        result["rollback_required"] = 0
        result["freeze_required_after_rollback"] = 0
        return result

    smoke_doc = frappe.new_doc("NDIS Limited Production Batch Smoke Run")
    smoke_doc.smoke_run_id = make_smoke_run_id()
    smoke_doc.status = result["status"]
    smoke_doc.smoke_status = result["smoke_status"]
    smoke_doc.limited_batch_smoke_submitted = result["limited_batch_smoke_submitted"]
    smoke_doc.rollback_required = result["rollback_required"]
    smoke_doc.freeze_required_after_rollback = result["freeze_required_after_rollback"]
    smoke_doc.production_batch_posting_allowed = 0
    smoke_doc.real_posting_allowed = 0
    smoke_doc.policy_live_enabled = 0

    for fieldname in [
        "activation_gate",
        "adapter_run",
        "policy_preview",
        "policy_design",
        "policy_review_gate",
        "phase8g_freeze",
        "source_preview",
        "company",
        "customer",
        "bank_account",
        "paid_from",
        "paid_to",
        "policy_mode",
        "max_batch_lines",
        "max_batch_amount",
        "max_payment_entry_count",
        "allowed_reference_count",
        "allowed_smoke_amount",
        "payment_entry_amount",
        "reference_count",
        "invoice_outstanding_before_total",
        "invoice_outstanding_after_total",
        "payment_entry_gl_count",
        "payment_entry_gl_net",
        "payment_entry_created_count",
        "payment_entry_submitted_count",
        "gl_created_count",
        "smoke_score",
        "blocker_count",
        "warning_count",
        "pass_count",
        "info_count",
        "item_count",
    ]:
        setattr(smoke_doc, fieldname, result.get(fieldname))

    smoke_doc.site_name = frappe.local.site
    smoke_doc.sandbox_config_enabled = config["sandbox_enabled"]
    smoke_doc.production_mode_detected = config["production_mode"]
    smoke_doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    smoke_doc.checked_on = now_datetime()
    smoke_doc.checked_by = frappe.session.user

    smoke_doc.payment_entry_count_before = guard_before["payment_entry_count"]
    smoke_doc.payment_entry_count_after = guardrails()["payment_entry_count"]
    smoke_doc.payment_entry_gl_count_before = guard_before["payment_entry_gl_count"]
    smoke_doc.payment_entry_gl_count_after = guardrails()["payment_entry_gl_count"]
    smoke_doc.submitted_journal_entry_count_today = guard_before["submitted_journal_entry_count_today"]
    smoke_doc.purchase_invoice_count_today = guard_before["purchase_invoice_count_today"]
    smoke_doc.production_batch_enabled_policy_count = guard_before["production_batch_enabled_policy_count"]
    smoke_doc.live_posting_allowed_policy_count = guard_before["live_posting_allowed_policy_count"]

    smoke_doc.required_acknowledgement = SMOKE_ACK
    smoke_doc.acknowledgement = acknowledgement
    smoke_doc.acknowledgement_ok = int(ack_ok)
    smoke_doc.summary_json = safe_json(result)
    smoke_doc.notes = notes
    smoke_doc.insert(ignore_permissions=True)

    if should_submit:
        pe = create_draft_payment_entry(smoke_doc, gate, lines, accounts)
        pe.submit()

        payment_entry = pe.name
        pe_docstatus = int(frappe.db.get_value("Payment Entry", payment_entry, "docstatus") or 0)
        pe_gl_count, pe_gl_net = pe_gl_count_net(payment_entry)
        outstanding_after = invoice_outstanding_total(lines)
        guard_after = guardrails()

        create_smoke_lines(smoke_doc, lines, payment_entry)

        result.update(
            {
                "payment_entry": payment_entry,
                "payment_entry_docstatus": pe_docstatus,
                "invoice_outstanding_after_total": outstanding_after,
                "payment_entry_gl_count": pe_gl_count,
                "payment_entry_gl_net": pe_gl_net,
                "payment_entry_created_count": 1,
                "payment_entry_submitted_count": 1 if pe_docstatus == 1 else 0,
                "gl_created_count": pe_gl_count,
                "guardrails_after": guard_after,
            }
        )

        frappe.db.set_value(
            "NDIS Limited Production Batch Smoke Run",
            smoke_doc.name,
            {
                "payment_entry": payment_entry,
                "payment_entry_docstatus": pe_docstatus,
                "invoice_outstanding_after_total": outstanding_after,
                "payment_entry_gl_count": pe_gl_count,
                "payment_entry_gl_net": pe_gl_net,
                "payment_entry_created_count": 1,
                "payment_entry_submitted_count": 1 if pe_docstatus == 1 else 0,
                "gl_created_count": pe_gl_count,
                "payment_entry_count_after": guard_after["payment_entry_count"],
                "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
                "summary_json": safe_json(result),
            },
            update_modified=False,
        )

    else:
        guard_after = guardrails()
        frappe.db.set_value(
            "NDIS Limited Production Batch Smoke Run",
            smoke_doc.name,
            {
                "payment_entry_count_after": guard_after["payment_entry_count"],
                "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
                "summary_json": safe_json({**result, "guardrails_after": guard_after}),
            },
            update_modified=False,
        )

    frappe.db.commit()

    result["created"] = True
    result["smoke_run"] = smoke_doc.name
    result["smoke_run_id"] = smoke_doc.smoke_run_id

    return result


@frappe.whitelist()
def cancel_limited_production_batch_controlled_smoke_audit(smoke_run, reason=None):
    assert_action("cancel_limited_production_batch_controlled_smoke_audit")

    if not frappe.db.exists("NDIS Limited Production Batch Smoke Run", smoke_run):
        frappe.throw(_("Smoke run not found: {0}").format(smoke_run))

    doc = frappe.get_doc("NDIS Limited Production Batch Smoke Run", smoke_run)

    if doc.status == "Cancelled":
        return {"smoke_run": smoke_run, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.limited_batch_smoke_submitted or 0) or doc.payment_entry:
        frappe.throw(_("Cannot cancel a submitted smoke run audit. Use Phase 9G rollback."))

    frappe.db.set_value(
        "NDIS Limited Production Batch Smoke Run",
        smoke_run,
        {
            "status": "Cancelled",
            "smoke_status": "Cancelled",
            "limited_batch_smoke_submitted": 0,
            "rollback_required": 0,
            "freeze_required_after_rollback": 0,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 9F smoke audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        """
        UPDATE `tabNDIS Limited Production Batch Smoke Run Line`
        SET line_status = 'Cancelled'
        WHERE smoke_run = %(smoke_run)s
        """,
        {"smoke_run": smoke_run},
    )

    frappe.db.commit()

    return {
        "smoke_run": smoke_run,
        "status": "Cancelled",
        "note": "Smoke audit record cancelled only. No accounting movement occurred.",
    }


@frappe.whitelist()
def quick_limited_production_batch_smoke_summary(limit=20):
    runs = frappe.get_all(
        "NDIS Limited Production Batch Smoke Run",
        fields=[
            "name",
            "smoke_run_id",
            "status",
            "smoke_status",
            "limited_batch_smoke_submitted",
            "rollback_required",
            "freeze_required_after_rollback",
            "production_batch_posting_allowed",
            "real_posting_allowed",
            "policy_live_enabled",
            "activation_gate",
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
            "smoke_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    lines = frappe.get_all(
        "NDIS Limited Production Batch Smoke Run Line",
        fields=[
            "name",
            "smoke_run",
            "line_no",
            "line_status",
            "payment_entry",
            "sales_invoice",
            "allocated_amount",
            "invoice_outstanding_before",
            "invoice_outstanding_after",
            "payment_entry_reference_created",
            "gl_created",
            "rollback_required",
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
        "note": "Phase 9F limited production batch controlled smoke summary. Rollback is required after successful smoke.",
    }


def execute_smoke_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("status"):
        conditions.append("s.status = %(status)s")
        params["status"] = filters.get("status")

    columns = smoke_columns()

    data = frappe.db.sql(
        f"""
        SELECT
            s.name AS smoke_run,
            s.smoke_run_id,
            s.status,
            s.smoke_status,
            s.limited_batch_smoke_submitted,
            s.rollback_required,
            s.freeze_required_after_rollback,
            s.activation_gate,
            s.payment_entry,
            s.payment_entry_docstatus,
            s.payment_entry_amount,
            s.reference_count,
            s.invoice_outstanding_before_total,
            s.invoice_outstanding_after_total,
            s.payment_entry_gl_count,
            s.payment_entry_gl_net,
            s.payment_entry_created_count,
            s.payment_entry_submitted_count,
            s.gl_created_count,
            s.production_batch_posting_allowed,
            s.real_posting_allowed,
            s.policy_live_enabled,
            s.smoke_score,
            s.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Limited Production Batch Smoke Run` s
        {build_where(conditions)}
        ORDER BY s.creation DESC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.smoke_run_id for row in data[:20]],
            "datasets": [
                {"name": "Submitted PE", "values": [int(row.payment_entry_submitted_count or 0) for row in data[:20]]},
                {"name": "GL Rows", "values": [int(row.payment_entry_gl_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Smoke Runs"), "datatype": "Int"},
        {"value": sum(int(row.limited_batch_smoke_submitted or 0) for row in data), "indicator": "Green", "label": _("Submitted Smokes"), "datatype": "Int"},
        {"value": sum(flt(row.payment_entry_amount or 0) for row in data), "indicator": "Blue", "label": _("Smoke Amount"), "datatype": "Currency", "currency": currency()},
        {"value": sum(int(row.rollback_required or 0) for row in data), "indicator": "Orange", "label": _("Rollback Required"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def smoke_columns():
    return [
        {"fieldname": "smoke_run", "label": _("Smoke Run"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Smoke Run", "width": 220},
        {"fieldname": "smoke_run_id", "label": _("Smoke Run ID"), "fieldtype": "Data", "width": 430},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 190},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 170},
        {"fieldname": "payment_entry_docstatus", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_amount", "label": _("PE Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "reference_count", "label": _("Refs"), "fieldtype": "Int", "width": 80},
        {"fieldname": "invoice_outstanding_before_total", "label": _("Outstanding Before"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "invoice_outstanding_after_total", "label": _("Outstanding After"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "payment_entry_gl_count", "label": _("PE GL Rows"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_net", "label": _("PE GL Net"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "rollback_required", "label": _("Rollback"), "fieldtype": "Check", "width": 90},
        {"fieldname": "policy_live_enabled", "label": _("Live Enabled"), "fieldtype": "Check", "width": 110},
        {"fieldname": "smoke_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


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
        {"fieldname": "line", "label": _("Line"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Smoke Run Line", "width": 220},
        {"fieldname": "smoke_run", "label": _("Smoke Run"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Smoke Run", "width": 220},
        {"fieldname": "line_no", "label": _("Line No"), "fieldtype": "Int", "width": 80},
        {"fieldname": "line_status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 170},
        {"fieldname": "sales_invoice", "label": _("Sales Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 170},
        {"fieldname": "allocated_amount", "label": _("Allocated"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "invoice_outstanding_before", "label": _("Outstanding Before"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "invoice_outstanding_after", "label": _("Outstanding After"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "payment_entry_reference_created", "label": _("PE Ref Created"), "fieldtype": "Check", "width": 120},
        {"fieldname": "gl_created", "label": _("GL Created"), "fieldtype": "Check", "width": 100},
        {"fieldname": "rollback_required", "label": _("Rollback"), "fieldtype": "Check", "width": 90},
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
            l.payment_entry,
            l.sales_invoice,
            l.allocated_amount,
            l.invoice_outstanding_before,
            l.invoice_outstanding_after,
            l.payment_entry_reference_created,
            l.gl_created,
            l.rollback_required,
            l.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Limited Production Batch Smoke Run Line` l
        {build_where(conditions)}
        ORDER BY l.smoke_run DESC, l.line_no ASC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [str(row.line_no) for row in data[:20]],
            "datasets": [{"name": "Allocated", "values": [flt(row.allocated_amount or 0) for row in data[:20]]}],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Lines"), "datatype": "Int"},
        {"value": len([row for row in data if row.line_status == "Submitted"]), "indicator": "Green", "label": _("Submitted"), "datatype": "Int"},
        {"value": sum(flt(row.allocated_amount or 0) for row in data), "indicator": "Blue", "label": _("Allocated"), "datatype": "Currency", "currency": currency()},
    ]

    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_smoke_report(filters)

    guard = guardrails()

    summary.append({"value": guard["payment_entry_count"], "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"})
    summary.append({"value": guard["payment_entry_gl_count"], "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"})
    summary.append({"value": guard["submitted_phase9f_smoke_pe_count"], "indicator": "Orange", "label": _("Submitted Phase 9F Smoke PE"), "datatype": "Int"})
    summary.append({"value": guard["submitted_journal_entry_count_today"], "indicator": "Red", "label": _("Submitted JE Today"), "datatype": "Int"})
    summary.append({"value": guard["purchase_invoice_count_today"], "indicator": "Red", "label": _("Purchase Invoice Today"), "datatype": "Int"})
    summary.append({"value": guard["production_batch_enabled_policy_count"], "indicator": "Red", "label": _("Production Batch Enabled Policies"), "datatype": "Int"})
    summary.append({"value": guard["live_posting_allowed_policy_count"], "indicator": "Red", "label": _("Live Posting Allowed Policies"), "datatype": "Int"})

    return columns, data, message, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
