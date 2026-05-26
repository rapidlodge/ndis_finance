import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


DRAFT_SMOKE_ACK = "I_CONFIRM_CREATE_ONE_DRAFT_PE_ONLY_NO_SUBMIT_NO_GL"
CLEANUP_ACK = "I_CONFIRM_DELETE_PHASE5F_DRAFT_PE_ONLY"
RUN_DOCTYPE = "NDIS PE Single Record Draft Smoke Run"
ITEM_DOCTYPE = "NDIS PE Single Record Draft Smoke Run Item"


def make_smoke_run_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-PE-DRAFT-SMOKE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def guardrails():
    return {
        "payment_entry_count": count_dt("Payment Entry"),
        "submitted_payment_entry_count_today": count_dt("Payment Entry", {"creation": [">=", today()], "docstatus": 1}),
        "payment_entry_gl_count": count_dt("GL Entry", {"voucher_type": "Payment Entry"}),
        "payment_entry_gl_count_today": count_dt("GL Entry", {"creation": [">=", today()], "voucher_type": "Payment Entry"}),
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
        [
            "name",
            "activation_gate_id",
            "company",
            "allowed_bank_account",
            "allowed_receivable_account",
            "activation_score",
        ],
        "checked_on desc, creation desc",
    )


def get_source_preview_line(source_preview_line=None):
    if source_preview_line:
        if not frappe.db.exists("NDIS PE Production Posting Preview Line", source_preview_line):
            frappe.throw(_("Source preview line not found: {0}").format(source_preview_line))
        return frappe.get_doc("NDIS PE Production Posting Preview Line", source_preview_line)

    row = latest_doc(
        "NDIS PE Production Posting Preview Line",
        {
            "status": "Preview Eligible",
            "event_type": "Paid Claim",
            "claim_outcome": "Paid",
            "would_create_payment_entry": 1,
            "actual_payment_entry_created": 0,
        },
        [
            "name",
            "posting_preview",
            "sales_invoice",
            "preview_payment_amount",
            "posting_policy",
            "policy_company",
            "allowed_bank_account",
            "allowed_receivable_account",
        ],
        "creation desc",
    )

    if row:
        return frappe.get_doc("NDIS PE Production Posting Preview Line", row.name)

    return None


def account_doc(account):
    if not account or not frappe.db.exists("Account", account):
        return None
    return frappe.get_doc("Account", account)


def validate_activation_gate(items):
    gate = latest_activation_gate()

    if gate:
        add_item(
            items,
            "Pass",
            "Low",
            "Activation Gate",
            "activation_gate",
            "Phase 5E activation gate",
            f"Activation gate is ready: {gate.activation_gate_id}.",
            None,
            "NDIS PE Production Activation Gate",
            gate.name,
        )
    else:
        add_item(
            items,
            "Blocker",
            "Critical",
            "Activation Gate",
            "activation_gate",
            "Phase 5E activation gate",
            "No valid Phase 5E activation gate found.",
            "Complete Phase 5E before Phase 5F.",
        )

    return gate


def validate_config(items):
    config = config_state()

    if config["production_mode"]:
        add_item(items, "Blocker", "Critical", "Site Config", "production_mode", "Production mode", "Production mode config is enabled.", "Keep disabled for Phase 5F.")
    else:
        add_item(items, "Pass", "Low", "Site Config", "production_mode", "Production mode", "Production mode remains disabled.")

    if config["live_pe_enabled"]:
        add_item(items, "Blocker", "Critical", "Site Config", "live_pe_enabled", "Live PE posting config", "Live Payment Entry posting config is enabled.", "Keep disabled for Phase 5F.")
    else:
        add_item(items, "Pass", "Low", "Site Config", "live_pe_enabled", "Live PE posting config", "Live Payment Entry posting config remains disabled.")

    if config["sandbox_enabled"]:
        add_item(items, "Pass", "Low", "Site Config", "sandbox_enabled", "Sandbox config", "Sandbox config remains enabled.")
    else:
        add_item(items, "Warning", "Medium", "Site Config", "sandbox_enabled", "Sandbox config", "Sandbox config is not enabled.")

    return config


def validate_accounts(items, gate):
    if not gate:
        return {}

    company = gate.company
    bank = account_doc(gate.allowed_bank_account)
    receivable = account_doc(gate.allowed_receivable_account)

    if not company or not frappe.db.exists("Company", company):
        add_item(items, "Blocker", "Critical", "Account Control", "company", "Company", "Activation gate company is missing or invalid.")
    else:
        add_item(items, "Pass", "Low", "Account Control", "company", "Company", f"Company verified: {company}.")

    if not bank:
        add_item(items, "Blocker", "Critical", "Account Control", "bank", "Allowed bank account", "Allowed bank account missing.")
    elif bank.company != company or bank.root_type != "Asset" or int(bank.is_group or 0) or int(bank.disabled or 0):
        add_item(items, "Blocker", "Critical", "Account Control", "bank", "Allowed bank account", "Allowed bank account is invalid for draft smoke.")
    else:
        add_item(items, "Pass", "Low", "Account Control", "bank", "Allowed bank account", f"Allowed bank account verified: {gate.allowed_bank_account}.", None, "Account", gate.allowed_bank_account)

    if not receivable:
        add_item(items, "Blocker", "Critical", "Account Control", "receivable", "Allowed receivable account", "Allowed receivable account missing.")
    elif receivable.company != company or receivable.root_type != "Asset" or int(receivable.is_group or 0) or int(receivable.disabled or 0):
        add_item(items, "Blocker", "Critical", "Account Control", "receivable", "Allowed receivable account", "Allowed receivable account is invalid for draft smoke.")
    elif receivable.account_type and receivable.account_type != "Receivable":
        add_item(items, "Blocker", "Critical", "Account Control", "receivable", "Allowed receivable account", f"Receivable account type is {receivable.account_type}; expected Receivable.")
    else:
        add_item(items, "Pass", "Low", "Account Control", "receivable", "Allowed receivable account", f"Allowed receivable account verified: {gate.allowed_receivable_account}.", None, "Account", gate.allowed_receivable_account)

    return {
        "company": company,
        "allowed_bank_account": gate.allowed_bank_account,
        "allowed_receivable_account": gate.allowed_receivable_account,
    }


def validate_sales_invoice(items, gate, sales_invoice=None, source_preview_line=None):
    source_line = get_source_preview_line(source_preview_line)

    if not sales_invoice and source_line and source_line.sales_invoice:
        sales_invoice = source_line.sales_invoice

    if not sales_invoice:
        add_item(
            items,
            "Warning",
            "High",
            "Source",
            "invoice_backed_source",
            "Invoice-backed source",
            "No submitted invoice-backed source was provided/found. Draft Payment Entry will not be created.",
            "Provide a valid submitted Sales Invoice with outstanding amount when ready.",
        )
        return None, source_line, 1

    if not frappe.db.exists("Sales Invoice", sales_invoice):
        add_item(items, "Blocker", "Critical", "Source", "sales_invoice_exists", "Sales Invoice exists", f"Sales Invoice does not exist: {sales_invoice}.")
        return None, source_line, 0

    si = frappe.get_doc("Sales Invoice", sales_invoice)

    if si.docstatus != 1:
        add_item(items, "Blocker", "Critical", "Source", "sales_invoice_submitted", "Sales Invoice submitted", f"Sales Invoice {sales_invoice} is not submitted.")
    else:
        add_item(items, "Pass", "Low", "Source", "sales_invoice_submitted", "Sales Invoice submitted", f"Sales Invoice {sales_invoice} is submitted.", None, "Sales Invoice", sales_invoice)

    if si.company != gate.company:
        add_item(items, "Blocker", "Critical", "Source", "sales_invoice_company", "Sales Invoice company", f"Sales Invoice company {si.company} does not match activation gate company {gate.company}.")
    else:
        add_item(items, "Pass", "Low", "Source", "sales_invoice_company", "Sales Invoice company", "Sales Invoice company matches activation gate.")

    if flt(si.outstanding_amount) <= 0:
        add_item(items, "Blocker", "Critical", "Source", "sales_invoice_outstanding", "Sales Invoice outstanding", f"Sales Invoice outstanding amount is {flt(si.outstanding_amount)}.")
    else:
        add_item(items, "Pass", "Low", "Source", "sales_invoice_outstanding", "Sales Invoice outstanding", f"Outstanding amount is {flt(si.outstanding_amount):.2f}.")

    if not getattr(si, "customer", None):
        add_item(items, "Blocker", "Critical", "Source", "sales_invoice_customer", "Sales Invoice customer", "Sales Invoice customer is missing.")
    else:
        add_item(items, "Pass", "Low", "Source", "sales_invoice_customer", "Sales Invoice customer", f"Customer verified: {si.customer}.")

    return si, source_line, 0


def validate_existing_draft_smoke(items):
    existing = count_dt(
        "Payment Entry",
        {
            "custom_ndis_pe_single_record_draft_smoke": 1,
            "docstatus": 0,
        },
    )

    if existing:
        add_item(
            items,
            "Blocker",
            "Critical",
            "Cleanup",
            "existing_draft_smoke_pe",
            "Existing draft smoke Payment Entry",
            f"{existing} existing draft smoke Payment Entry record(s) found.",
            "Clean up existing Phase 5F draft Payment Entry before creating another.",
        )
    else:
        add_item(items, "Pass", "Low", "Cleanup", "existing_draft_smoke_pe", "Existing draft smoke Payment Entry", "No existing draft smoke Payment Entry remains.")

    return existing


def validate_policy_controls(items):
    live_enabled = count_dt("NDIS PE Production Posting Policy", {"production_posting_enabled": 1})
    cross_company = count_dt("NDIS PE Production Posting Policy", {"allow_cross_company_posting": 1})
    overpayment = count_dt("NDIS PE Production Posting Policy", {"allow_overpayment": 1})
    negative = count_dt("NDIS PE Production Posting Policy", {"allow_negative_receipt": 1})

    checks = [
        ("live_enabled", "Live-enabled policies", live_enabled),
        ("cross_company", "Cross-company allowed policies", cross_company),
        ("overpayment", "Overpayment allowed policies", overpayment),
        ("negative_receipt", "Negative receipt allowed policies", negative),
    ]

    for key, label, value in checks:
        if value:
            add_item(items, "Blocker", "Critical", "Policy Control", key, label, f"{value} record(s) found.")
        else:
            add_item(items, "Pass", "Low", "Policy Control", key, label, "Zero.")

    return {
        "live_enabled_policy_count": live_enabled,
        "cross_company_allowed_count": cross_company,
        "overpayment_allowed_count": overpayment,
        "negative_receipt_allowed_count": negative,
    }


def evaluate_guardrails(items):
    values = guardrails()

    checks = [
        ("submitted_payment_entry_count_today", "Submitted Payment Entries today", values["submitted_payment_entry_count_today"]),
        ("payment_entry_gl_count", "Payment Entry GL", values["payment_entry_gl_count"]),
        ("payment_entry_gl_count_today", "Payment Entry GL today", values["payment_entry_gl_count_today"]),
        ("submitted_journal_entry_count_today", "Submitted Journal Entries today", values["submitted_journal_entry_count_today"]),
        ("purchase_invoice_count_today", "Purchase Invoices today", values["purchase_invoice_count_today"]),
    ]

    for key, label, value in checks:
        if value:
            add_item(items, "Blocker", "Critical", "Strict Guardrail", key, label, f"{value} record(s) found.")
        else:
            add_item(items, "Pass", "Low", "Strict Guardrail", key, label, "Zero.")

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
    score = 100
    score -= int(blockers or 0) * 25
    score -= int(warnings or 0) * 5
    return max(0, round(score, 2))


def smoke_status(score, blockers, warnings, invoice_pending, draft_created):
    if blockers:
        return "Blocked"
    if draft_created:
        return "Draft PE Created"
    if invoice_pending:
        return "Source Pending"
    if warnings:
        return "Ready With Warnings"
    if score >= 95:
        return "Ready For Draft PE"
    return "Needs Review"


def create_draft_payment_entry(smoke_run_doc, sales_invoice_doc, amount):
    from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

    pe = get_payment_entry("Sales Invoice", sales_invoice_doc.name)
    pe.paid_to = smoke_run_doc.allowed_bank_account
    pe.paid_from = smoke_run_doc.allowed_receivable_account
    pe.bank_account = ensure_smoke_bank_account(
        smoke_run_doc.company,
        smoke_run_doc.allowed_bank_account,
    )
    pe.paid_amount = amount
    pe.received_amount = amount
    pe.reference_no = smoke_run_doc.smoke_run_id
    pe.reference_date = today()
    pe.remarks = f"NDIS Phase 5F draft-only Payment Entry smoke test for {sales_invoice_doc.name}. Do not submit."

    for row in pe.references:
        if row.reference_doctype == "Sales Invoice" and row.reference_name == sales_invoice_doc.name:
            row.allocated_amount = amount

    pe.custom_ndis_pe_single_record_draft_smoke = 1
    pe.custom_ndis_pe_draft_smoke_run = smoke_run_doc.name
    pe.custom_ndis_pe_activation_gate = smoke_run_doc.activation_gate
    pe.custom_ndis_pe_source_preview_line = smoke_run_doc.source_preview_line
    pe.custom_ndis_pe_draft_smoke_note = "Phase 5F draft-only smoke Payment Entry. Submission is blocked by hook."

    pe.insert(ignore_permissions=True)
    return pe


def ensure_smoke_bank_account(company, account):
    if not account:
        return None

    existing = frappe.db.get_value("Bank Account", {"account": account}, "name")
    if existing:
        return existing

    bank_name = "NDIS PE Smoke Test Bank"
    if not frappe.db.exists("Bank", bank_name):
        bank = frappe.new_doc("Bank")
        bank.bank_name = bank_name
        bank.insert(ignore_permissions=True)

    account_doc = frappe.get_doc("Account", account)
    bank_account = frappe.new_doc("Bank Account")
    bank_account.account_name = "NDIS PE Smoke Test Bank Account"
    bank_account.bank = bank_name
    bank_account.account = account
    bank_account.company = company or account_doc.company
    bank_account.is_company_account = 1
    bank_account.insert(ignore_permissions=True)

    return bank_account.name


def block_single_record_draft_smoke_submit(doc, method=None):
    if int(getattr(doc, "custom_ndis_pe_single_record_draft_smoke", 0) or 0):
        frappe.throw(
            _("Phase 5F submit block: this draft Payment Entry was created for single-record smoke testing only and cannot be submitted.")
        )


@frappe.whitelist()
def verify_pe_single_record_draft_submit_block(payment_entry):
    assert_action("verify_pe_single_record_draft_submit_block")

    if not frappe.db.exists("Payment Entry", payment_entry):
        frappe.throw(_("Payment Entry not found: {0}").format(payment_entry))

    doc = frappe.get_doc("Payment Entry", payment_entry)

    if not int(getattr(doc, "custom_ndis_pe_single_record_draft_smoke", 0) or 0):
        frappe.throw(_("Payment Entry is not tagged as Phase 5F draft smoke."))

    if doc.docstatus != 0:
        frappe.throw(_("Payment Entry is not draft. Current docstatus: {0}").format(doc.docstatus))

    try:
        doc.submit()
    except Exception as exc:
        message = str(exc)
        if "Phase 5F submit block" in message:
            smoke_run = getattr(doc, "custom_ndis_pe_draft_smoke_run", None)
            if smoke_run and frappe.db.exists(RUN_DOCTYPE, smoke_run):
                frappe.db.set_value(
                    RUN_DOCTYPE,
                    smoke_run,
                    {
                        "status": "Submit Block Verified",
                        "submit_block_verified": 1,
                        "draft_payment_entry_submitted": 0,
                        "payment_entry_gl_count": count_dt("GL Entry", {"voucher_type": "Payment Entry"}),
                        "payment_entry_gl_count_today": count_dt("GL Entry", {"creation": [">=", today()], "voucher_type": "Payment Entry"}),
                    },
                    update_modified=False,
                )
                frappe.db.commit()

            return {
                "submit_block_verified": 1,
                "payment_entry": payment_entry,
                "docstatus": frappe.db.get_value("Payment Entry", payment_entry, "docstatus"),
                "message": message,
                "payment_entry_gl_count": count_dt("GL Entry", {"voucher_type": "Payment Entry"}),
            }

        frappe.throw(_("Payment Entry submit failed, but not with the Phase 5F blocker: {0}").format(message))

    frappe.throw(_("CRITICAL: Phase 5F draft Payment Entry submitted unexpectedly."))


@frappe.whitelist()
def run_pe_single_record_draft_smoke(
    sales_invoice=None,
    source_preview_line=None,
    amount=None,
    acknowledgement=None,
    dry_run=1,
    notes=None,
):
    assert_action("run_pe_single_record_draft_smoke")

    items = []
    config = validate_config(items)
    gate = validate_activation_gate(items)
    controls = validate_accounts(items, gate) if gate else {}
    policy_controls = validate_policy_controls(items)
    existing_draft_count = validate_existing_draft_smoke(items)
    guard_before = evaluate_guardrails(items)

    si = None
    source_line = None
    invoice_pending = 0

    if gate:
        si, source_line, invoice_pending = validate_sales_invoice(
            items,
            gate,
            sales_invoice=sales_invoice,
            source_preview_line=source_preview_line,
        )

    ack_ok = acknowledgement == DRAFT_SMOKE_ACK

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "draft_smoke_ack", "Draft smoke acknowledgement", "Exact acknowledgement supplied.")
    else:
        add_item(
            items,
            "Warning",
            "Medium",
            "Acknowledgement",
            "draft_smoke_ack",
            "Draft smoke acknowledgement",
            f"Required acknowledgement not supplied. Required: {DRAFT_SMOKE_ACK}",
            "Provide exact acknowledgement before creating one draft Payment Entry.",
        )

    summary = summarise_items(items)
    score = calculate_score(summary["blocker_count"], summary["warning_count"])
    draft_created = 0
    draft_pe = None
    dry_run = int(dry_run or 0)

    can_create_draft = (
        not dry_run
        and ack_ok
        and si
        and summary["blocker_count"] == 0
        and existing_draft_count == 0
    )

    if dry_run:
        status = "Source Pending" if invoice_pending else ("Needs Review" if not ack_ok else "Draft")
        final_smoke_status = smoke_status(score, summary["blocker_count"], summary["warning_count"], invoice_pending, 0)

        return {
            "dry_run": True,
            "status": status,
            "smoke_status": final_smoke_status,
            "smoke_score": score,
            "invoice_backed_source_required": int(invoice_pending),
            "draft_payment_entry_created": 0,
            "draft_payment_entry_submitted": 0,
            "live_posting_allowed": 0,
            "payment_entry_created": 0,
            "required_acknowledgement": DRAFT_SMOKE_ACK,
            "acknowledgement_ok": ack_ok,
            "activation_gate": gate.name if gate else None,
            "sales_invoice": si.name if si else sales_invoice,
            "source_preview_line": source_line.name if source_line else source_preview_line,
            "controls": controls,
            "policy_controls": policy_controls,
            "config": config,
            "guardrails_before": guard_before,
            "summary": summary,
            "items": items,
            "note": "Dry-run only. No Payment Entry was created.",
        }

    run_doc = frappe.new_doc(RUN_DOCTYPE)
    run_doc.smoke_run_id = make_smoke_run_id()

    if invoice_pending:
        run_doc.status = "Source Pending"
        run_doc.smoke_mode = "Readiness Only"
    elif si:
        run_doc.status = "Needs Review" if not ack_ok else "Draft"
        run_doc.smoke_mode = "Explicit Sales Invoice" if sales_invoice else "Preview Line With Invoice"
    elif summary["blocker_count"]:
        run_doc.status = "Blocked"
        run_doc.smoke_mode = "Readiness Only"
    else:
        run_doc.status = "Needs Review"
        run_doc.smoke_mode = "Readiness Only"

    run_doc.activation_gate = gate.name if gate else None
    run_doc.source_preview_line = source_line.name if source_line else source_preview_line
    run_doc.sales_invoice = si.name if si else sales_invoice
    run_doc.company = gate.company if gate else None
    run_doc.allowed_bank_account = gate.allowed_bank_account if gate else None
    run_doc.allowed_receivable_account = gate.allowed_receivable_account if gate else None
    run_doc.customer = si.customer if si else None
    run_doc.invoice_outstanding_amount = flt(si.outstanding_amount) if si else 0
    run_doc.draft_amount = flt(amount) if amount else (min(flt(si.outstanding_amount), 1.00) if si else 0)
    run_doc.invoice_backed_source_required = int(invoice_pending)
    run_doc.draft_payment_entry_created = 0
    run_doc.draft_payment_entry_submitted = 0
    run_doc.submit_block_verified = 0
    run_doc.cleanup_required = 0
    run_doc.live_posting_allowed = 0
    run_doc.site_name = frappe.local.site
    run_doc.sandbox_config_enabled = config["sandbox_enabled"]
    run_doc.production_mode_detected = config["production_mode"]
    run_doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    run_doc.executed_on = now_datetime()
    run_doc.executed_by = frappe.session.user
    run_doc.smoke_score = score
    run_doc.smoke_status = smoke_status(score, summary["blocker_count"], summary["warning_count"], invoice_pending, 0)
    run_doc.blocker_count = summary["blocker_count"]
    run_doc.warning_count = summary["warning_count"]
    run_doc.pass_count = summary["pass_count"]
    run_doc.info_count = summary["info_count"]
    run_doc.item_count = summary["item_count"]
    run_doc.payment_entry_count_before = guard_before["payment_entry_count"]
    run_doc.payment_entry_count_after = count_dt("Payment Entry")
    run_doc.submitted_payment_entry_count_today = guard_before["submitted_payment_entry_count_today"]
    run_doc.payment_entry_gl_count = guard_before["payment_entry_gl_count"]
    run_doc.payment_entry_gl_count_today = guard_before["payment_entry_gl_count_today"]
    run_doc.submitted_journal_entry_count_today = guard_before["submitted_journal_entry_count_today"]
    run_doc.purchase_invoice_count_today = guard_before["purchase_invoice_count_today"]
    run_doc.required_acknowledgement = DRAFT_SMOKE_ACK
    run_doc.acknowledgement = acknowledgement
    run_doc.acknowledgement_ok = int(ack_ok)
    run_doc.notes = notes
    run_doc.insert(ignore_permissions=True)

    for item in items:
        row = frappe.new_doc(ITEM_DOCTYPE)
        row.smoke_run = run_doc.name
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

    if can_create_draft:
        draft_amount = flt(amount) if amount else min(flt(si.outstanding_amount), 1.00)
        if draft_amount <= 0:
            frappe.throw(_("Draft amount must be positive."))

        if draft_amount > flt(si.outstanding_amount):
            frappe.throw(_("Draft amount cannot exceed Sales Invoice outstanding amount."))

        draft_pe = create_draft_payment_entry(run_doc, si, draft_amount)
        draft_created = 1

        frappe.db.set_value(
            RUN_DOCTYPE,
            run_doc.name,
            {
                "status": "Draft Created",
                "smoke_status": "Draft PE Created",
                "draft_payment_entry": draft_pe.name,
                "draft_payment_entry_created": 1,
                "draft_payment_entry_submitted": 0,
                "cleanup_required": 1,
                "payment_entry_count_after": count_dt("Payment Entry"),
                "submitted_payment_entry_count_today": count_dt("Payment Entry", {"creation": [">=", today()], "docstatus": 1}),
                "payment_entry_gl_count": count_dt("GL Entry", {"voucher_type": "Payment Entry"}),
                "payment_entry_gl_count_today": count_dt("GL Entry", {"creation": [">=", today()], "voucher_type": "Payment Entry"}),
            },
            update_modified=False,
        )

    guard_after = guardrails()

    result = {
        "dry_run": False,
        "created": True,
        "smoke_run": run_doc.name,
        "smoke_run_id": run_doc.smoke_run_id,
        "status": frappe.db.get_value(RUN_DOCTYPE, run_doc.name, "status"),
        "smoke_status": frappe.db.get_value(RUN_DOCTYPE, run_doc.name, "smoke_status"),
        "smoke_score": score,
        "invoice_backed_source_required": int(invoice_pending),
        "draft_payment_entry_created": draft_created,
        "draft_payment_entry": draft_pe.name if draft_pe else None,
        "draft_payment_entry_submitted": 0,
        "live_posting_allowed": 0,
        "required_acknowledgement": DRAFT_SMOKE_ACK,
        "acknowledgement_ok": ack_ok,
        "activation_gate": gate.name if gate else None,
        "sales_invoice": si.name if si else sales_invoice,
        "source_preview_line": source_line.name if source_line else source_preview_line,
        "draft_amount": flt(run_doc.draft_amount),
        "summary": summary,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "note": "One draft Payment Entry may be created only when a valid invoice-backed source is provided. Submission remains blocked.",
    }

    frappe.db.set_value(
        RUN_DOCTYPE,
        run_doc.name,
        {
            "payment_entry_count_after": guard_after["payment_entry_count"],
            "submitted_payment_entry_count_today": guard_after["submitted_payment_entry_count_today"],
            "payment_entry_gl_count": guard_after["payment_entry_gl_count"],
            "payment_entry_gl_count_today": guard_after["payment_entry_gl_count_today"],
            "submitted_journal_entry_count_today": guard_after["submitted_journal_entry_count_today"],
            "purchase_invoice_count_today": guard_after["purchase_invoice_count_today"],
            "summary_json": safe_json(result),
        },
        update_modified=False,
    )

    frappe.db.commit()
    return result


@frappe.whitelist()
def cleanup_pe_single_record_draft_smoke(smoke_run, acknowledgement=None):
    assert_action("cleanup_pe_single_record_draft_smoke")

    if acknowledgement != CLEANUP_ACK:
        frappe.throw(_("Wrong acknowledgement. Required: {0}").format(CLEANUP_ACK))

    if not frappe.db.exists(RUN_DOCTYPE, smoke_run):
        frappe.throw(_("Smoke run not found: {0}").format(smoke_run))

    run = frappe.get_doc(RUN_DOCTYPE, smoke_run)
    pe_name = run.draft_payment_entry

    if not pe_name:
        frappe.db.set_value(
            RUN_DOCTYPE,
            smoke_run,
            {
                "status": "Cleaned",
                "cleanup_required": 0,
                "cleaned_on": now_datetime(),
                "cleaned_by": frappe.session.user,
            },
            update_modified=False,
        )
        frappe.db.commit()
        return {"status": "Cleaned", "deleted_payment_entry": None, "note": "No draft Payment Entry was linked."}

    if not frappe.db.exists("Payment Entry", pe_name):
        frappe.db.set_value(
            RUN_DOCTYPE,
            smoke_run,
            {
                "status": "Cleaned",
                "cleanup_required": 0,
                "cleaned_on": now_datetime(),
                "cleaned_by": frappe.session.user,
            },
            update_modified=False,
        )
        frappe.db.commit()
        return {"status": "Cleaned", "deleted_payment_entry": None, "note": "Linked draft Payment Entry already missing."}

    pe = frappe.get_doc("Payment Entry", pe_name)

    if pe.docstatus != 0:
        frappe.throw(_("Cannot delete Payment Entry because it is not draft. Docstatus: {0}").format(pe.docstatus))

    if not int(getattr(pe, "custom_ndis_pe_single_record_draft_smoke", 0) or 0):
        frappe.throw(_("Cannot delete Payment Entry because it is not tagged as Phase 5F draft smoke."))

    gl_count = count_dt("GL Entry", {"voucher_type": "Payment Entry", "voucher_no": pe_name})
    if gl_count:
        frappe.throw(_("Cannot delete draft smoke Payment Entry because linked GL Entry exists: {0}").format(gl_count))

    frappe.delete_doc("Payment Entry", pe_name, ignore_permissions=True, force=True)

    frappe.db.set_value(
        RUN_DOCTYPE,
        smoke_run,
        {
            "status": "Cleaned",
            "draft_payment_entry": None,
            "cleanup_required": 0,
            "cleaned_on": now_datetime(),
            "cleaned_by": frappe.session.user,
            "payment_entry_count_after": count_dt("Payment Entry"),
            "submitted_payment_entry_count_today": count_dt("Payment Entry", {"creation": [">=", today()], "docstatus": 1}),
            "payment_entry_gl_count": count_dt("GL Entry", {"voucher_type": "Payment Entry"}),
            "payment_entry_gl_count_today": count_dt("GL Entry", {"creation": [">=", today()], "voucher_type": "Payment Entry"}),
        },
        update_modified=False,
    )

    frappe.db.commit()

    return {
        "status": "Cleaned",
        "deleted_payment_entry": pe_name,
        "payment_entry_gl_count": count_dt("GL Entry", {"voucher_type": "Payment Entry"}),
        "submitted_payment_entry_count_today": count_dt("Payment Entry", {"creation": [">=", today()], "docstatus": 1}),
    }


@frappe.whitelist()
def cancel_pe_single_record_draft_smoke(smoke_run, reason=None):
    assert_action("cancel_pe_single_record_draft_smoke")

    if not frappe.db.exists(RUN_DOCTYPE, smoke_run):
        frappe.throw(_("Smoke run not found: {0}").format(smoke_run))

    run = frappe.get_doc(RUN_DOCTYPE, smoke_run)

    if run.draft_payment_entry and frappe.db.exists("Payment Entry", run.draft_payment_entry):
        pe_docstatus = frappe.db.get_value("Payment Entry", run.draft_payment_entry, "docstatus")
        if pe_docstatus == 0:
            frappe.throw(_("Clean up linked draft Payment Entry before cancelling this smoke run: {0}").format(run.draft_payment_entry))

    frappe.db.set_value(
        RUN_DOCTYPE,
        smoke_run,
        {
            "status": "Cancelled",
            "live_posting_allowed": 0,
            "draft_payment_entry_submitted": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 5F smoke run cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        f"""
        UPDATE `tab{ITEM_DOCTYPE}`
        SET status = 'Cancelled'
        WHERE smoke_run = %(smoke_run)s
        """,
        {"smoke_run": smoke_run},
    )

    frappe.db.commit()

    return {
        "smoke_run": smoke_run,
        "status": "Cancelled",
        "note": "Smoke run cancelled. No accounting/payment submission occurred.",
    }


@frappe.whitelist()
def quick_pe_single_record_draft_smoke_summary(limit=20):
    runs = frappe.get_all(
        RUN_DOCTYPE,
        fields=[
            "name",
            "smoke_run_id",
            "status",
            "smoke_status",
            "smoke_score",
            "activation_gate",
            "sales_invoice",
            "draft_payment_entry",
            "draft_payment_entry_created",
            "draft_payment_entry_submitted",
            "submit_block_verified",
            "cleanup_required",
            "live_posting_allowed",
            "payment_entry_gl_count",
            "executed_on",
            "executed_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    items = frappe.get_all(
        ITEM_DOCTYPE,
        fields=[
            "name",
            "smoke_run",
            "status",
            "severity",
            "category",
            "check_label",
            "detail",
            "recommendation",
            "source_doctype",
            "source_name",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    return {
        "runs": runs,
        "items": items,
        "required_acknowledgement": DRAFT_SMOKE_ACK,
        "cleanup_acknowledgement": CLEANUP_ACK,
        "guardrails": guardrails(),
        "config": config_state(),
        "note": "Phase 5F draft-only summary. Submitted Payment Entry and GL must remain zero.",
    }


def execute_smoke_run_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    status = filters.get("status")
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")

    if status:
        conditions.append("r.status = %(status)s")
        params["status"] = status
    if from_date:
        conditions.append("DATE(r.executed_on) >= %(from_date)s")
        params["from_date"] = from_date
    if to_date:
        conditions.append("DATE(r.executed_on) <= %(to_date)s")
        params["to_date"] = to_date

    columns = [
        {"fieldname": "smoke_run", "label": _("Smoke Run"), "fieldtype": "Link", "options": RUN_DOCTYPE, "width": 220},
        {"fieldname": "smoke_run_id", "label": _("Smoke Run ID"), "fieldtype": "Data", "width": 330},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 130},
        {"fieldname": "smoke_status", "label": _("Smoke Status"), "fieldtype": "Data", "width": 220},
        {"fieldname": "smoke_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "sales_invoice", "label": _("Sales Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 180},
        {"fieldname": "draft_payment_entry", "label": _("Draft PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "draft_amount", "label": _("Draft Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "draft_payment_entry_created", "label": _("Draft PE Created"), "fieldtype": "Check", "width": 120},
        {"fieldname": "draft_payment_entry_submitted", "label": _("Submitted"), "fieldtype": "Check", "width": 90},
        {"fieldname": "submit_block_verified", "label": _("Submit Block"), "fieldtype": "Check", "width": 110},
        {"fieldname": "cleanup_required", "label": _("Cleanup"), "fieldtype": "Check", "width": 90},
        {"fieldname": "payment_entry_gl_count", "label": _("PE GL"), "fieldtype": "Int", "width": 80},
        {"fieldname": "executed_on", "label": _("Executed On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            r.name AS smoke_run,
            r.smoke_run_id,
            r.status,
            r.smoke_status,
            r.smoke_score,
            r.sales_invoice,
            r.draft_payment_entry,
            r.draft_amount,
            r.draft_payment_entry_created,
            r.draft_payment_entry_submitted,
            r.submit_block_verified,
            r.cleanup_required,
            r.payment_entry_gl_count,
            r.executed_on,
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
                {"name": "Draft PE Created", "values": [int(row.draft_payment_entry_created or 0) for row in data[:20]]},
                {"name": "Submitted", "values": [int(row.draft_payment_entry_submitted or 0) for row in data[:20]]},
                {"name": "PE GL", "values": [int(row.payment_entry_gl_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Smoke Runs"), "datatype": "Int"},
        {"value": sum(int(row.draft_payment_entry_created or 0) for row in data), "indicator": "Green", "label": _("Draft PE Created"), "datatype": "Int"},
        {"value": sum(int(row.draft_payment_entry_submitted or 0) for row in data), "indicator": "Red", "label": _("Submitted PE"), "datatype": "Int"},
        {"value": sum(int(row.payment_entry_gl_count or 0) for row in data), "indicator": "Red", "label": _("Payment Entry GL"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_smoke_exception_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    for key in ["smoke_run", "status", "severity", "category"]:
        if filters.get(key):
            conditions.append(f"i.{key} = %({key})s")
            params[key] = filters.get(key)

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": ITEM_DOCTYPE, "width": 220},
        {"fieldname": "smoke_run", "label": _("Smoke Run"), "fieldtype": "Link", "options": RUN_DOCTYPE, "width": 220},
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
        SELECT
            i.name AS item,
            i.smoke_run,
            i.status,
            i.severity,
            i.category,
            i.check_label,
            i.detail,
            i.recommendation,
            i.source_doctype,
            i.source_name,
            i.checked_on
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
        key = row.status or "Info"
        chart_map[key] = chart_map.get(key, 0) + 1

    chart = {
        "data": {
            "labels": list(chart_map.keys()),
            "datasets": [{"name": "Items", "values": list(chart_map.values())}],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Items"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Pass"]), "indicator": "Green", "label": _("Pass"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Warning"]), "indicator": "Orange", "label": _("Warnings"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Blocker"]), "indicator": "Red", "label": _("Blockers"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_hygiene_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = ["p.custom_ndis_pe_single_record_draft_smoke = 1"]
    params = {"currency": currency()}

    docstatus = filters.get("docstatus")
    if docstatus not in [None, ""]:
        conditions.append("p.docstatus = %(docstatus)s")
        params["docstatus"] = int(docstatus)
    if filters.get("cleanup_required"):
        conditions.append("r.cleanup_required = 1")

    columns = [
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "docstatus", "label": _("Docstatus"), "fieldtype": "Int", "width": 80},
        {"fieldname": "smoke_run", "label": _("Smoke Run"), "fieldtype": "Link", "options": RUN_DOCTYPE, "width": 220},
        {"fieldname": "sales_invoice", "label": _("Sales Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 180},
        {"fieldname": "party", "label": _("Party"), "fieldtype": "Dynamic Link", "options": "party_type", "width": 180},
        {"fieldname": "paid_amount", "label": _("Paid Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "received_amount", "label": _("Received Amount"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "gl_count", "label": _("GL Count"), "fieldtype": "Int", "width": 90},
        {"fieldname": "cleanup_required", "label": _("Cleanup Required"), "fieldtype": "Check", "width": 120},
        {"fieldname": "creation", "label": _("Created On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            p.name AS payment_entry,
            p.docstatus,
            p.custom_ndis_pe_draft_smoke_run AS smoke_run,
            r.sales_invoice,
            p.party_type,
            p.party,
            p.paid_amount,
            p.received_amount,
            (
                SELECT COUNT(*)
                FROM `tabGL Entry` gl
                WHERE gl.voucher_type = 'Payment Entry'
                AND gl.voucher_no = p.name
            ) AS gl_count,
            r.cleanup_required,
            p.creation,
            %(currency)s AS currency
        FROM `tabPayment Entry` p
        LEFT JOIN `tab{RUN_DOCTYPE}` r
            ON r.name = p.custom_ndis_pe_draft_smoke_run
        {build_where(conditions)}
        ORDER BY p.creation DESC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": ["Draft", "Submitted", "Cancelled"],
            "datasets": [
                {
                    "name": "Payment Entries",
                    "values": [
                        len([row for row in data if row.docstatus == 0]),
                        len([row for row in data if row.docstatus == 1]),
                        len([row for row in data if row.docstatus == 2]),
                    ],
                }
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Tagged Draft Smoke PEs"), "datatype": "Int"},
        {"value": len([row for row in data if row.docstatus == 0]), "indicator": "Orange", "label": _("Draft"), "datatype": "Int"},
        {"value": len([row for row in data if row.docstatus == 1]), "indicator": "Red", "label": _("Submitted"), "datatype": "Int"},
        {"value": sum(int(row.gl_count or 0) for row in data), "indicator": "Red", "label": _("Linked GL"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
