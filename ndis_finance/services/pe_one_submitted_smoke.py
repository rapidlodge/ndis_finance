import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action
from ndis_finance.services.pe_single_record_draft_smoke import ensure_smoke_bank_account


RUN_DOCTYPE = "NDIS PE One Submitted Smoke Run"
ITEM_DOCTYPE = "NDIS PE One Submitted Smoke Run Item"
SUBMIT_ACK = "I_CONFIRM_SUBMIT_ONE_PHASE5I_PAYMENT_ENTRY_ONLY"
CANCEL_ACK = "I_CONFIRM_CANCEL_PHASE5I_SUBMITTED_PAYMENT_ENTRY_ONLY"


def make_run_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-PE-ONE-SUBMITTED-SMOKE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def gl_count(voucher_type, voucher_no=None):
    filters = {"voucher_type": voucher_type}
    if voucher_no:
        filters["voucher_no"] = voucher_no
    return count_dt("GL Entry", filters)


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


def other_guardrails():
    return {
        "submitted_journal_entry_count_today": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}),
        "purchase_invoice_count_today": count_dt("Purchase Invoice", {"creation": [">=", today()]}),
    }


def latest_activation_gate():
    return latest_doc(
        "NDIS PE Production Activation Gate",
        {
            "production_activation_allowed": 1,
            "ready_for_single_record_live_smoke": 1,
            "live_posting_allowed": 0,
            "payment_entry_created": 0,
            "blocker_count": 0,
        },
        ["name", "activation_gate_id", "company", "allowed_bank_account", "allowed_receivable_account"],
        "checked_on desc, creation desc",
    )


def latest_source_run():
    return latest_doc(
        "NDIS PE Smoke Invoice Source Run",
        {
            "status": "Source Created",
            "source_invoice_created": 1,
            "source_invoice_submitted": 1,
            "payment_entry_created": 0,
            "payment_entry_submitted": 0,
            "live_posting_allowed": 0,
        },
        ["name", "source_run_id", "source_sales_invoice"],
        "executed_on desc, creation desc",
    )


def latest_source_ready_gate():
    return latest_doc(
        "NDIS PE Submitted Smoke Gate",
        {
            "status": "Source Ready",
            "submitted_smoke_source_ready": 1,
            "submitted_smoke_gate_allowed": 1,
            "live_posting_allowed": 0,
            "payment_entry_created": 0,
            "payment_entry_submitted": 0,
        },
        ["name", "submitted_smoke_gate_id", "sales_invoice"],
        "checked_on desc, creation desc",
    )


def latest_phase5f_clean_or_verified():
    return latest_doc(
        "NDIS PE Single Record Draft Smoke Run",
        {
            "status": ["in", ["Cleaned", "Submit Block Verified"]],
            "draft_payment_entry_submitted": 0,
            "payment_entry_gl_count": 0,
            "submit_block_verified": 1,
        },
        ["name", "smoke_run_id", "sales_invoice"],
        "executed_on desc, creation desc",
    )


def evaluate_config(items):
    config = config_state()
    if config["production_mode"]:
        add_item(items, "Blocker", "Critical", "Site Config", "production_mode", "Production mode", "Production mode is enabled.", "Keep disabled for Phase 5I.")
    else:
        add_item(items, "Pass", "Low", "Site Config", "production_mode", "Production mode", "Production mode remains disabled.")
    if config["live_pe_enabled"]:
        add_item(items, "Blocker", "Critical", "Site Config", "live_pe_enabled", "Live PE posting config", "Live PE posting config is enabled.", "Keep disabled globally. Phase 5I is service-gated only.")
    else:
        add_item(items, "Pass", "Low", "Site Config", "live_pe_enabled", "Live PE posting config", "Live PE posting config remains disabled globally.")
    if config["sandbox_enabled"]:
        add_item(items, "Pass", "Low", "Site Config", "sandbox_enabled", "Sandbox config", "Sandbox config remains enabled.")
    else:
        add_item(items, "Warning", "Medium", "Site Config", "sandbox_enabled", "Sandbox config", "Sandbox config is not enabled.")
    return config


def evaluate_evidence(items):
    activation = latest_activation_gate()
    source_run = latest_source_run()
    submitted_gate = latest_source_ready_gate()
    draft_run = latest_phase5f_clean_or_verified()

    if activation:
        add_item(items, "Pass", "Low", "Prior Evidence", "phase5e", "Phase 5E activation gate", f"Activation gate found: {activation.activation_gate_id}.", None, "NDIS PE Production Activation Gate", activation.name)
    else:
        add_item(items, "Blocker", "Critical", "Prior Evidence", "phase5e", "Phase 5E activation gate", "No valid Phase 5E activation gate found.")
    if source_run:
        add_item(items, "Pass", "Low", "Prior Evidence", "phase5h", "Phase 5H source invoice run", f"Source run found: {source_run.source_run_id}.", None, "NDIS PE Smoke Invoice Source Run", source_run.name)
    else:
        add_item(items, "Blocker", "Critical", "Prior Evidence", "phase5h", "Phase 5H source invoice run", "No valid Phase 5H source invoice run found.")
    if submitted_gate:
        add_item(items, "Pass", "Low", "Prior Evidence", "phase5g", "Phase 5G source-ready gate", f"Source-ready gate found: {submitted_gate.submitted_smoke_gate_id}.", None, "NDIS PE Submitted Smoke Gate", submitted_gate.name)
    else:
        add_item(items, "Blocker", "Critical", "Prior Evidence", "phase5g", "Phase 5G source-ready gate", "No valid Phase 5G source-ready gate found.")
    if draft_run:
        add_item(items, "Pass", "Low", "Prior Evidence", "phase5f", "Phase 5F draft smoke verified", f"Draft smoke verified: {draft_run.smoke_run_id}.", None, "NDIS PE Single Record Draft Smoke Run", draft_run.name)
    else:
        add_item(items, "Blocker", "Critical", "Prior Evidence", "phase5f", "Phase 5F draft smoke verified", "No verified/cleaned Phase 5F invoice-backed draft smoke run found.")

    return activation, source_run, submitted_gate, draft_run


def source_invoice_from_inputs(source_sales_invoice=None, source_run=None):
    if source_sales_invoice:
        return source_sales_invoice
    if source_run and frappe.db.exists("NDIS PE Smoke Invoice Source Run", source_run):
        return frappe.db.get_value("NDIS PE Smoke Invoice Source Run", source_run, "source_sales_invoice")
    source = latest_source_run()
    return source.source_sales_invoice if source else None


def evaluate_source_invoice(items, activation, source_sales_invoice):
    if not source_sales_invoice:
        add_item(items, "Blocker", "Critical", "Source Invoice", "source_invoice", "Source Sales Invoice", "No source Sales Invoice supplied/found.")
        return None
    if not frappe.db.exists("Sales Invoice", source_sales_invoice):
        add_item(items, "Blocker", "Critical", "Source Invoice", "source_invoice_exists", "Source Sales Invoice exists", f"Sales Invoice not found: {source_sales_invoice}.")
        return None

    si = frappe.get_doc("Sales Invoice", source_sales_invoice)
    if not int(getattr(si, "custom_ndis_pe_smoke_source_invoice", 0) or 0):
        add_item(items, "Blocker", "Critical", "Source Invoice", "source_invoice_tag", "Phase 5H source tag", "Sales Invoice is not tagged as Phase 5H smoke source.")
    else:
        add_item(items, "Pass", "Low", "Source Invoice", "source_invoice_tag", "Phase 5H source tag", "Sales Invoice is tagged as Phase 5H smoke source.", None, "Sales Invoice", si.name)
    if si.docstatus != 1:
        add_item(items, "Blocker", "Critical", "Source Invoice", "source_invoice_submitted", "Source invoice submitted", f"Sales Invoice docstatus is {si.docstatus}; expected 1.")
    else:
        add_item(items, "Pass", "Low", "Source Invoice", "source_invoice_submitted", "Source invoice submitted", "Sales Invoice is submitted.")
    if activation and si.company != activation.company:
        add_item(items, "Blocker", "Critical", "Source Invoice", "source_invoice_company", "Source invoice company", f"Invoice company {si.company} does not match activation company {activation.company}.")
    else:
        add_item(items, "Pass", "Low", "Source Invoice", "source_invoice_company", "Source invoice company", f"Company verified: {si.company}.")
    if flt(si.outstanding_amount) <= 0:
        add_item(items, "Blocker", "Critical", "Source Invoice", "source_invoice_outstanding", "Source invoice outstanding", f"Outstanding amount is {flt(si.outstanding_amount):.2f}; expected positive.")
    elif flt(si.outstanding_amount) > 1:
        add_item(items, "Blocker", "Critical", "Source Invoice", "source_invoice_cap", "Source invoice amount cap", f"Outstanding amount is {flt(si.outstanding_amount):.2f}; Phase 5I cap is 1.00.")
    else:
        add_item(items, "Pass", "Low", "Source Invoice", "source_invoice_outstanding", "Source invoice outstanding", f"Outstanding amount is {flt(si.outstanding_amount):.2f}.")
    if gl_count("Sales Invoice", si.name) <= 0:
        add_item(items, "Blocker", "Critical", "Source Invoice", "source_invoice_gl", "Source invoice GL", "No Sales Invoice GL found.")
    elif abs(gl_net("Sales Invoice", si.name)) > 0.0001:
        add_item(items, "Blocker", "Critical", "Source Invoice", "source_invoice_gl_net", "Source invoice GL net", f"Sales Invoice GL net is {gl_net('Sales Invoice', si.name)}; expected 0.")
    else:
        add_item(items, "Pass", "Low", "Source Invoice", "source_invoice_gl", "Source invoice GL", f"Sales Invoice GL exists and nets to 0. Rows: {gl_count('Sales Invoice', si.name)}.")
    return si


def evaluate_accounts(items, activation, si):
    if not activation or not si:
        return {}
    bank = frappe.get_doc("Account", activation.allowed_bank_account) if frappe.db.exists("Account", activation.allowed_bank_account) else None
    receivable = frappe.get_doc("Account", activation.allowed_receivable_account) if frappe.db.exists("Account", activation.allowed_receivable_account) else None
    if not bank:
        add_item(items, "Blocker", "Critical", "Accounts", "bank_account", "Allowed bank account", "Allowed bank account is missing.")
    elif bank.company != si.company or bank.root_type != "Asset" or int(bank.is_group or 0) or int(bank.disabled or 0):
        add_item(items, "Blocker", "Critical", "Accounts", "bank_account", "Allowed bank account", "Allowed bank account is invalid.")
    else:
        add_item(items, "Pass", "Low", "Accounts", "bank_account", "Allowed bank account", f"Bank account verified: {activation.allowed_bank_account}.", None, "Account", activation.allowed_bank_account)
    if not receivable:
        add_item(items, "Blocker", "Critical", "Accounts", "receivable_account", "Allowed receivable account", "Allowed receivable account is missing.")
    elif receivable.company != si.company or receivable.root_type != "Asset" or int(receivable.is_group or 0) or int(receivable.disabled or 0):
        add_item(items, "Blocker", "Critical", "Accounts", "receivable_account", "Allowed receivable account", "Allowed receivable account is invalid.")
    elif receivable.account_type and receivable.account_type != "Receivable":
        add_item(items, "Blocker", "Critical", "Accounts", "receivable_account", "Allowed receivable account", f"Receivable account type is {receivable.account_type}; expected Receivable.")
    else:
        add_item(items, "Pass", "Low", "Accounts", "receivable_account", "Allowed receivable account", f"Receivable account verified: {activation.allowed_receivable_account}.", None, "Account", activation.allowed_receivable_account)
    return {
        "company": si.company,
        "customer": si.customer,
        "allowed_bank_account": activation.allowed_bank_account,
        "allowed_receivable_account": activation.allowed_receivable_account,
    }


def evaluate_duplicates(items):
    existing_submitted = count_dt("Payment Entry", {"custom_ndis_pe_one_submitted_smoke": 1, "docstatus": 1})
    existing_draft = count_dt("Payment Entry", {"custom_ndis_pe_one_submitted_smoke": 1, "docstatus": 0})
    if existing_submitted:
        add_item(items, "Blocker", "Critical", "Duplicate Control", "existing_submitted_phase5i_pe", "Existing submitted Phase 5I PE", f"{existing_submitted} submitted Phase 5I Payment Entry already exists.")
    else:
        add_item(items, "Pass", "Low", "Duplicate Control", "existing_submitted_phase5i_pe", "Existing submitted Phase 5I PE", "No submitted Phase 5I Payment Entry exists.")
    if existing_draft:
        add_item(items, "Blocker", "Critical", "Duplicate Control", "existing_draft_phase5i_pe", "Existing draft Phase 5I PE", f"{existing_draft} draft Phase 5I Payment Entry exists.")
    else:
        add_item(items, "Pass", "Low", "Duplicate Control", "existing_draft_phase5i_pe", "Existing draft Phase 5I PE", "No draft Phase 5I Payment Entry exists.")
    return existing_submitted, existing_draft


def evaluate_policy_controls(items):
    checks = {
        "live_enabled_policy_count": count_dt("NDIS PE Production Posting Policy", {"production_posting_enabled": 1}),
        "cross_company_allowed_count": count_dt("NDIS PE Production Posting Policy", {"allow_cross_company_posting": 1}),
        "overpayment_allowed_count": count_dt("NDIS PE Production Posting Policy", {"allow_overpayment": 1}),
        "negative_receipt_allowed_count": count_dt("NDIS PE Production Posting Policy", {"allow_negative_receipt": 1}),
    }
    labels = {
        "live_enabled_policy_count": "Live-enabled policies",
        "cross_company_allowed_count": "Cross-company allowed policies",
        "overpayment_allowed_count": "Overpayment allowed policies",
        "negative_receipt_allowed_count": "Negative receipt allowed policies",
    }
    for key, value in checks.items():
        if value:
            add_item(items, "Blocker", "Critical", "Policy Control", key, labels[key], f"{value} record(s) found.")
        else:
            add_item(items, "Pass", "Low", "Policy Control", key, labels[key], "Zero.")
    return checks


def evaluate_other_guardrails(items):
    values = other_guardrails()
    for key, label in [
        ("submitted_journal_entry_count_today", "Submitted Journal Entries today"),
        ("purchase_invoice_count_today", "Purchase Invoices today"),
    ]:
        if values[key]:
            add_item(items, "Blocker", "Critical", "Other Movement Guardrail", key, label, f"{values[key]} record(s) found.")
        else:
            add_item(items, "Pass", "Low", "Other Movement Guardrail", key, label, "Zero.")
    return values


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


def smoke_status(score, blockers, warnings, submitted):
    if blockers:
        return "Blocked"
    if submitted:
        return "Payment Entry Submitted"
    if warnings:
        return "Ready With Warnings"
    if score >= 95:
        return "Ready To Submit One PE"
    return "Needs Review"


def create_run_items(run_doc, items):
    for item in items:
        row = frappe.new_doc(ITEM_DOCTYPE)
        row.submitted_run = run_doc.name
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


def create_and_submit_payment_entry(run_doc, si, controls, amount):
    from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

    pe = get_payment_entry("Sales Invoice", si.name)
    pe.paid_to = controls["allowed_bank_account"]
    pe.paid_from = controls["allowed_receivable_account"]
    pe.bank_account = ensure_smoke_bank_account(si.company, controls["allowed_bank_account"])
    pe.paid_amount = amount
    pe.received_amount = amount
    pe.reference_no = run_doc.submitted_run_id
    pe.reference_date = today()
    pe.remarks = f"Phase 5I controlled one submitted Payment Entry smoke for {si.name}. Run: {run_doc.name}"
    for row in pe.references:
        if row.reference_doctype == "Sales Invoice" and row.reference_name == si.name:
            row.allocated_amount = amount
    pe.custom_ndis_pe_one_submitted_smoke = 1
    pe.custom_ndis_pe_one_submitted_smoke_run = run_doc.name
    pe.custom_ndis_pe_one_submitted_source_invoice = si.name
    pe.custom_ndis_pe_one_submitted_phase = "Phase 5I"
    pe.custom_ndis_pe_one_submitted_note = "Controlled one submitted Payment Entry smoke. Amount capped at 1.00."
    pe.insert(ignore_permissions=True)
    pe.submit()
    return pe


@frappe.whitelist()
def run_pe_one_submitted_smoke(source_sales_invoice=None, source_run=None, amount=1, acknowledgement=None, dry_run=1, notes=None):
    assert_action("run_pe_one_submitted_smoke")
    amount = flt(amount or 1)
    items = []
    config = evaluate_config(items)
    activation, auto_source_run, submitted_gate, draft_run = evaluate_evidence(items)
    source_sales_invoice = source_invoice_from_inputs(
        source_sales_invoice=source_sales_invoice,
        source_run=source_run or (auto_source_run.name if auto_source_run else None),
    )
    si = evaluate_source_invoice(items, activation, source_sales_invoice)
    controls = evaluate_accounts(items, activation, si)
    existing_submitted, _existing_draft = evaluate_duplicates(items)
    policy_controls = evaluate_policy_controls(items)
    other_before = evaluate_other_guardrails(items)

    if amount <= 0:
        add_item(items, "Blocker", "Critical", "Amount", "payment_amount", "Payment amount", "Amount must be positive.")
    elif amount > 1:
        add_item(items, "Blocker", "Critical", "Amount", "payment_amount_cap", "Payment amount cap", f"Amount is {amount:.2f}. Phase 5I cap is 1.00.")
    elif si and amount > flt(si.outstanding_amount):
        add_item(items, "Blocker", "Critical", "Amount", "outstanding_cap", "Outstanding cap", f"Amount {amount:.2f} exceeds outstanding {flt(si.outstanding_amount):.2f}.")
    else:
        add_item(items, "Pass", "Low", "Amount", "payment_amount", "Payment amount", f"Payment amount verified: {amount:.2f}.")

    ack_ok = acknowledgement == SUBMIT_ACK
    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "submit_ack", "Submit acknowledgement", "Exact acknowledgement supplied.")
    elif int(dry_run or 0):
        add_item(items, "Info", "Low", "Acknowledgement", "submit_ack", "Submit acknowledgement", f"Dry-run preview only. Required for submission: {SUBMIT_ACK}")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "submit_ack", "Submit acknowledgement", f"Required acknowledgement not supplied. Required: {SUBMIT_ACK}", "Provide exact acknowledgement before submitting one Payment Entry.")

    summary = summarise_items(items)
    score = calculate_score(summary["blocker_count"], summary["warning_count"])
    if int(dry_run or 0):
        return {
            "dry_run": True,
            "status": "Previewed" if summary["blocker_count"] == 0 else "Blocked",
            "smoke_status": smoke_status(score, summary["blocker_count"], summary["warning_count"], False),
            "smoke_score": score,
            "payment_entry_created": 0,
            "payment_entry_submitted": 0,
            "payment_entry_gl_count": 0,
            "payment_entry_gl_net": 0,
            "source_sales_invoice": si.name if si else source_sales_invoice,
            "invoice_outstanding_before": flt(si.outstanding_amount) if si else 0,
            "invoice_outstanding_after": flt(si.outstanding_amount) if si else 0,
            "amount": amount,
            "required_acknowledgement": SUBMIT_ACK,
            "acknowledgement_ok": ack_ok,
            "summary": summary,
            "items": items,
            "config": config,
            "policy_controls": policy_controls,
            "other_guardrails_before": other_before,
            "note": "Dry-run only. No Payment Entry was created or submitted.",
        }

    run_doc = frappe.new_doc(RUN_DOCTYPE)
    run_doc.submitted_run_id = make_run_id()
    run_doc.status = "Needs Review" if not ack_ok else ("Blocked" if summary["blocker_count"] else "Previewed")
    run_doc.run_type = "One Submitted Payment Entry Smoke"
    run_doc.source_sales_invoice = si.name if si else source_sales_invoice
    run_doc.source_invoice_run = source_run or (auto_source_run.name if auto_source_run else None)
    run_doc.submitted_smoke_gate = submitted_gate.name if submitted_gate else None
    run_doc.draft_smoke_run = draft_run.name if draft_run else None
    run_doc.activation_gate = activation.name if activation else None
    run_doc.payment_amount = amount
    run_doc.company = si.company if si else (activation.company if activation else None)
    run_doc.customer = si.customer if si else None
    run_doc.allowed_bank_account = activation.allowed_bank_account if activation else None
    run_doc.allowed_receivable_account = activation.allowed_receivable_account if activation else None
    run_doc.invoice_outstanding_before = flt(si.outstanding_amount) if si else 0
    run_doc.invoice_outstanding_after = flt(si.outstanding_amount) if si else 0
    run_doc.invoice_docstatus = si.docstatus if si else 0
    run_doc.sales_invoice_gl_count = gl_count("Sales Invoice", si.name) if si else 0
    run_doc.sales_invoice_gl_net = gl_net("Sales Invoice", si.name) if si else 0
    run_doc.payment_entry_gl_count = 0
    run_doc.payment_entry_gl_net = 0
    run_doc.site_name = frappe.local.site
    run_doc.sandbox_config_enabled = config["sandbox_enabled"]
    run_doc.production_mode_detected = config["production_mode"]
    run_doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    run_doc.executed_on = now_datetime()
    run_doc.executed_by = frappe.session.user
    run_doc.smoke_score = score
    run_doc.smoke_status = smoke_status(score, summary["blocker_count"], summary["warning_count"], False)
    run_doc.blocker_count = summary["blocker_count"]
    run_doc.warning_count = summary["warning_count"]
    run_doc.pass_count = summary["pass_count"]
    run_doc.info_count = summary["info_count"]
    run_doc.item_count = summary["item_count"]
    run_doc.payment_entry_created = 0
    run_doc.payment_entry_submitted = 0
    run_doc.payment_entry_cancelled = 0
    run_doc.payment_entry_docstatus = 0
    run_doc.live_posting_allowed = 0
    run_doc.live_enabled_policy_count = policy_controls["live_enabled_policy_count"]
    run_doc.existing_phase5i_submitted_pe_count = existing_submitted
    run_doc.submitted_journal_entry_count_today = other_before["submitted_journal_entry_count_today"]
    run_doc.purchase_invoice_count_today = other_before["purchase_invoice_count_today"]
    run_doc.required_acknowledgement = SUBMIT_ACK
    run_doc.acknowledgement = acknowledgement
    run_doc.acknowledgement_ok = int(ack_ok)
    run_doc.notes = notes
    run_doc.insert(ignore_permissions=True)
    create_run_items(run_doc, items)

    pe = None
    if ack_ok and summary["blocker_count"] == 0 and si:
        pe = create_and_submit_payment_entry(run_doc, si, controls, amount)
        si.reload()
        frappe.db.set_value(
            RUN_DOCTYPE,
            run_doc.name,
            {
                "status": "Submitted",
                "smoke_status": "Payment Entry Submitted",
                "payment_entry": pe.name,
                "payment_entry_created": 1,
                "payment_entry_submitted": int(pe.docstatus == 1),
                "payment_entry_docstatus": pe.docstatus,
                "invoice_outstanding_after": flt(si.outstanding_amount),
                "payment_entry_gl_count": gl_count("Payment Entry", pe.name),
                "payment_entry_gl_net": gl_net("Payment Entry", pe.name),
                "submitted_journal_entry_count_today": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}),
                "purchase_invoice_count_today": count_dt("Purchase Invoice", {"creation": [">=", today()]}),
            },
            update_modified=False,
        )

    result = {
        "dry_run": False,
        "created": True,
        "submitted_run": run_doc.name,
        "submitted_run_id": run_doc.submitted_run_id,
        "status": frappe.db.get_value(RUN_DOCTYPE, run_doc.name, "status"),
        "smoke_status": frappe.db.get_value(RUN_DOCTYPE, run_doc.name, "smoke_status"),
        "smoke_score": score,
        "payment_entry": pe.name if pe else None,
        "payment_entry_created": 1 if pe else 0,
        "payment_entry_submitted": 1 if pe and pe.docstatus == 1 else 0,
        "payment_entry_docstatus": pe.docstatus if pe else 0,
        "source_sales_invoice": si.name if si else source_sales_invoice,
        "payment_amount": amount,
        "invoice_outstanding_before": flt(run_doc.invoice_outstanding_before),
        "invoice_outstanding_after": flt(frappe.db.get_value("Sales Invoice", si.name, "outstanding_amount")) if si else 0,
        "payment_entry_gl_count": gl_count("Payment Entry", pe.name) if pe else 0,
        "payment_entry_gl_net": gl_net("Payment Entry", pe.name) if pe else 0,
        "sales_invoice_gl_count": gl_count("Sales Invoice", si.name) if si else 0,
        "sales_invoice_gl_net": gl_net("Sales Invoice", si.name) if si else 0,
        "submitted_journal_entry_count_today": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}),
        "purchase_invoice_count_today": count_dt("Purchase Invoice", {"creation": [">=", today()]}),
        "required_acknowledgement": SUBMIT_ACK,
        "acknowledgement_ok": ack_ok,
        "summary": summary,
        "note": "Phase 5I submitted exactly one tagged Payment Entry when all checks passed.",
    }
    frappe.db.set_value(RUN_DOCTYPE, run_doc.name, {"summary_json": safe_json(result)}, update_modified=False)
    frappe.db.commit()
    return result


@frappe.whitelist()
def cancel_pe_one_submitted_smoke_payment(submitted_run, acknowledgement=None):
    assert_action("cancel_pe_one_submitted_smoke_payment")
    if acknowledgement != CANCEL_ACK:
        frappe.throw(_("Wrong acknowledgement. Required: {0}").format(CANCEL_ACK))
    if not frappe.db.exists(RUN_DOCTYPE, submitted_run):
        frappe.throw(_("Submitted smoke run not found: {0}").format(submitted_run))
    run = frappe.get_doc(RUN_DOCTYPE, submitted_run)
    if not run.payment_entry:
        frappe.throw(_("No Payment Entry linked to this run."))
    if not frappe.db.exists("Payment Entry", run.payment_entry):
        frappe.throw(_("Linked Payment Entry does not exist: {0}").format(run.payment_entry))
    pe = frappe.get_doc("Payment Entry", run.payment_entry)
    if not int(getattr(pe, "custom_ndis_pe_one_submitted_smoke", 0) or 0):
        frappe.throw(_("Payment Entry is not tagged as Phase 5I one submitted smoke."))
    if pe.docstatus == 1:
        pe.cancel()
    frappe.db.set_value(
        RUN_DOCTYPE,
        submitted_run,
        {
            "status": "Payment Cancelled",
            "payment_entry_cancelled": 1,
            "payment_entry_docstatus": frappe.db.get_value("Payment Entry", pe.name, "docstatus"),
            "invoice_outstanding_after": flt(frappe.db.get_value("Sales Invoice", run.source_sales_invoice, "outstanding_amount") or 0),
            "payment_entry_gl_count": gl_count("Payment Entry", pe.name),
            "payment_entry_gl_net": gl_net("Payment Entry", pe.name),
            "payment_cancelled_on": now_datetime(),
            "payment_cancelled_by": frappe.session.user,
        },
        update_modified=False,
    )
    frappe.db.commit()
    return {
        "status": "Payment Cancelled",
        "submitted_run": submitted_run,
        "payment_entry": pe.name,
        "payment_entry_docstatus": frappe.db.get_value("Payment Entry", pe.name, "docstatus"),
        "payment_entry_gl_count": gl_count("Payment Entry", pe.name),
        "payment_entry_gl_net": gl_net("Payment Entry", pe.name),
        "invoice_outstanding_after": flt(frappe.db.get_value("Sales Invoice", run.source_sales_invoice, "outstanding_amount") or 0),
        "note": "Phase 5I submitted Payment Entry cancelled. This creates normal Payment Entry reversal GL.",
    }


@frappe.whitelist()
def cancel_pe_one_submitted_smoke_run(submitted_run, reason=None):
    assert_action("cancel_pe_one_submitted_smoke_run")
    if not frappe.db.exists(RUN_DOCTYPE, submitted_run):
        frappe.throw(_("Submitted smoke run not found: {0}").format(submitted_run))
    run = frappe.get_doc(RUN_DOCTYPE, submitted_run)
    if run.payment_entry and frappe.db.exists("Payment Entry", run.payment_entry):
        pe_status = frappe.db.get_value("Payment Entry", run.payment_entry, "docstatus")
        if pe_status == 1:
            frappe.throw(_("Cancel the linked submitted Payment Entry first, or keep the run active as evidence: {0}").format(run.payment_entry))
    frappe.db.set_value(
        RUN_DOCTYPE,
        submitted_run,
        {
            "status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 5I run cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(
        f"UPDATE `tab{ITEM_DOCTYPE}` SET status = 'Cancelled' WHERE submitted_run = %(submitted_run)s",
        {"submitted_run": submitted_run},
    )
    frappe.db.commit()
    return {"submitted_run": submitted_run, "status": "Cancelled", "note": "Phase 5I run cancelled."}


@frappe.whitelist()
def quick_pe_one_submitted_smoke_summary(limit=20):
    runs = frappe.get_all(
        RUN_DOCTYPE,
        fields=[
            "name",
            "submitted_run_id",
            "status",
            "smoke_status",
            "smoke_score",
            "source_sales_invoice",
            "payment_entry",
            "payment_amount",
            "payment_entry_created",
            "payment_entry_submitted",
            "payment_entry_cancelled",
            "payment_entry_docstatus",
            "invoice_outstanding_before",
            "invoice_outstanding_after",
            "payment_entry_gl_count",
            "payment_entry_gl_net",
            "executed_on",
            "executed_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(
        ITEM_DOCTYPE,
        fields=["name", "submitted_run", "status", "severity", "category", "check_label", "detail", "recommendation", "source_doctype", "source_name"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "runs": runs,
        "items": items,
        "submit_acknowledgement": SUBMIT_ACK,
        "cancel_acknowledgement": CANCEL_ACK,
        "config": config_state(),
        "note": "Phase 5I summary. One submitted tagged Payment Entry is expected if smoke succeeded.",
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
        {"fieldname": "submitted_run", "label": _("Submitted Run"), "fieldtype": "Link", "options": RUN_DOCTYPE, "width": 220},
        {"fieldname": "submitted_run_id", "label": _("Run ID"), "fieldtype": "Data", "width": 340},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 130},
        {"fieldname": "source_sales_invoice", "label": _("Source SI"), "fieldtype": "Link", "options": "Sales Invoice", "width": 170},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 170},
        {"fieldname": "payment_amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 100},
        {"fieldname": "payment_entry_submitted", "label": _("PE Submitted"), "fieldtype": "Check", "width": 110},
        {"fieldname": "invoice_outstanding_before", "label": _("Outstanding Before"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "invoice_outstanding_after", "label": _("Outstanding After"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "payment_entry_gl_count", "label": _("PE GL Count"), "fieldtype": "Int", "width": 100},
        {"fieldname": "payment_entry_gl_net", "label": _("PE GL Net"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "executed_on", "label": _("Executed On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT r.name AS submitted_run, r.submitted_run_id, r.status, r.source_sales_invoice,
            r.payment_entry, r.payment_amount, r.payment_entry_submitted,
            r.invoice_outstanding_before, r.invoice_outstanding_after,
            r.payment_entry_gl_count, r.payment_entry_gl_net, r.executed_on,
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
            "labels": [row.submitted_run_id for row in data[:20]],
            "datasets": [
                {"name": "Submitted PE", "values": [int(row.payment_entry_submitted or 0) for row in data[:20]]},
                {"name": "PE GL Count", "values": [int(row.payment_entry_gl_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Runs"), "datatype": "Int"},
        {"value": sum(int(row.payment_entry_submitted or 0) for row in data), "indicator": "Green", "label": _("Submitted PEs"), "datatype": "Int"},
        {"value": sum(int(row.payment_entry_gl_count or 0) for row in data), "indicator": "Green", "label": _("PE GL Rows"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_exception_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    for fieldname in ["submitted_run", "status", "severity", "category"]:
        if filters.get(fieldname):
            conditions.append(f"i.{fieldname} = %({fieldname})s")
            params[fieldname] = filters.get(fieldname)
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": ITEM_DOCTYPE, "width": 220},
        {"fieldname": "submitted_run", "label": _("Submitted Run"), "fieldtype": "Link", "options": RUN_DOCTYPE, "width": 220},
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
        SELECT i.name AS item, i.submitted_run, i.status, i.severity, i.category,
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
    conditions = ["pe.custom_ndis_pe_one_submitted_smoke = 1"]
    params = {"currency": currency()}
    if filters.get("payment_entry"):
        conditions.append("pe.name = %(payment_entry)s")
        params["payment_entry"] = filters.payment_entry
    columns = [
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "docstatus", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 100},
        {"fieldname": "source_invoice", "label": _("Source Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 180},
        {"fieldname": "gl_entry", "label": _("GL Entry"), "fieldtype": "Link", "options": "GL Entry", "width": 220},
        {"fieldname": "account", "label": _("Account"), "fieldtype": "Link", "options": "Account", "width": 240},
        {"fieldname": "debit", "label": _("Debit"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "credit", "label": _("Credit"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "posting_date", "label": _("Posting Date"), "fieldtype": "Date", "width": 110},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT pe.name AS payment_entry, pe.docstatus,
            pe.custom_ndis_pe_one_submitted_source_invoice AS source_invoice,
            gl.name AS gl_entry, gl.account, gl.debit, gl.credit, gl.posting_date,
            %(currency)s AS currency
        FROM `tabPayment Entry` pe
        INNER JOIN `tabGL Entry` gl
            ON gl.voucher_type = 'Payment Entry'
            AND gl.voucher_no = pe.name
        {build_where(conditions)}
        ORDER BY pe.creation DESC, gl.creation ASC
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
        {"value": len(data), "indicator": "Green", "label": _("GL Rows"), "datatype": "Int"},
        {"value": sum(flt(row.debit) for row in data), "indicator": "Green", "label": _("Debit"), "datatype": "Currency", "currency": currency()},
        {"value": sum(flt(row.credit) for row in data), "indicator": "Green", "label": _("Credit"), "datatype": "Currency", "currency": currency()},
        {"value": sum(flt(row.debit) - flt(row.credit) for row in data), "indicator": "Blue", "label": _("Net"), "datatype": "Currency", "currency": currency()},
    ]
    return columns, data, None, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
