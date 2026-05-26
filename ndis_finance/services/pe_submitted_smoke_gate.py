import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


SUBMITTED_SMOKE_ACK = "I_CONFIRM_PE_SUBMITTED_SMOKE_GATE_NO_PAYMENT_ENTRY_NO_GL"
GATE_DOCTYPE = "NDIS PE Submitted Smoke Gate"
ITEM_DOCTYPE = "NDIS PE Submitted Smoke Gate Item"


def make_gate_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-PE-SUBMITTED-SMOKE-GATE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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
    rows = frappe.get_all(doctype, filters=filters or {}, fields=fields or ["name"], order_by=order_by, limit=1)
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
        ["name", "activation_gate_id", "company", "allowed_bank_account", "allowed_receivable_account"],
        "checked_on desc, creation desc",
    )


def latest_phase5f_run():
    return latest_doc(
        "NDIS PE Single Record Draft Smoke Run",
        {"status": ["in", ["Source Pending", "Cleaned", "Submit Block Verified"]], "draft_payment_entry_submitted": 0, "live_posting_allowed": 0},
        ["name", "smoke_run_id", "status", "sales_invoice", "draft_payment_entry", "submit_block_verified"],
        "executed_on desc, creation desc",
    )


def latest_phase5d_run():
    return latest_doc(
        "NDIS PE Production Adapter Run",
        {"status": "Hard Blocked", "acknowledgement_ok": 1, "payment_entry_created": 0, "live_posting_allowed": 0, "actual_payment_entry_created_count": 0, "blocker_count": 0},
        ["name", "adapter_run_id", "source_preview"],
        "executed_on desc, creation desc",
    )


def latest_phase5c_preview():
    return latest_doc(
        "NDIS PE Production Posting Preview",
        {"status": "Previewed", "acknowledgement_ok": 1, "payment_entry_created": 0, "live_posting_allowed": 0, "blocker_count": 0},
        ["name", "preview_id"],
        "previewed_on desc, creation desc",
    )


def account_doc(account):
    if not account or not frappe.db.exists("Account", account):
        return None
    return frappe.get_doc("Account", account)


def evaluate_config(items):
    config = config_state()
    add_item(items, "Blocker" if config["production_mode"] else "Pass", "Critical" if config["production_mode"] else "Low", "Site Config", "production_mode", "Production mode", "Production mode is enabled." if config["production_mode"] else "Production mode remains disabled.")
    add_item(items, "Blocker" if config["live_pe_enabled"] else "Pass", "Critical" if config["live_pe_enabled"] else "Low", "Site Config", "live_pe_enabled", "Live PE posting config", "Live Payment Entry posting config is enabled." if config["live_pe_enabled"] else "Live Payment Entry posting config remains disabled.")
    add_item(items, "Pass" if config["sandbox_enabled"] else "Warning", "Low" if config["sandbox_enabled"] else "Medium", "Site Config", "sandbox_enabled", "Sandbox config", "Sandbox config remains enabled." if config["sandbox_enabled"] else "Sandbox config is not enabled.")
    return config


def evaluate_evidence(items):
    activation = latest_activation_gate()
    phase5f = latest_phase5f_run()
    phase5d = latest_phase5d_run()
    phase5c = latest_phase5c_preview()
    counts = {
        "phase5f_completed_count": count_dt("NDIS PE Single Record Draft Smoke Run", {"status": ["in", ["Source Pending", "Cleaned", "Submit Block Verified"]], "draft_payment_entry_submitted": 0, "live_posting_allowed": 0}),
        "phase5f_draft_verified_count": count_dt("NDIS PE Single Record Draft Smoke Run", {"status": ["in", ["Submit Block Verified", "Cleaned"]], "submit_block_verified": 1, "draft_payment_entry_submitted": 0, "payment_entry_gl_count": 0}),
        "phase5e_activation_allowed_count": count_dt("NDIS PE Production Activation Gate", {"production_activation_allowed": 1, "ready_for_single_record_live_smoke": 1, "live_posting_allowed": 0, "payment_entry_created": 0, "blocker_count": 0}),
        "phase5d_hard_blocked_count": count_dt("NDIS PE Production Adapter Run", {"status": "Hard Blocked", "acknowledgement_ok": 1, "payment_entry_created": 0, "live_posting_allowed": 0, "actual_payment_entry_created_count": 0, "blocker_count": 0}),
        "phase5c_preview_count": count_dt("NDIS PE Production Posting Preview", {"status": "Previewed", "acknowledgement_ok": 1, "payment_entry_created": 0, "live_posting_allowed": 0, "blocker_count": 0}),
    }
    evidence_map = [
        ("phase5e_activation_allowed_count", "Phase 5E activation gate", activation, "NDIS PE Production Activation Gate"),
        ("phase5f_completed_count", "Phase 5F draft smoke harness", phase5f, "NDIS PE Single Record Draft Smoke Run"),
        ("phase5d_hard_blocked_count", "Phase 5D adapter hard block", phase5d, "NDIS PE Production Adapter Run"),
        ("phase5c_preview_count", "Phase 5C posting preview", phase5c, "NDIS PE Production Posting Preview"),
    ]
    for key, label, source, doctype in evidence_map:
        if counts[key] > 0 and source:
            add_item(items, "Pass", "Low", "Prior Evidence", key, label, f"{counts[key]} valid record(s) found.", None, doctype, source.name)
        else:
            add_item(items, "Blocker", "Critical", "Prior Evidence", key, label, "Required evidence is missing.", f"Complete {label} before Phase 5G.")
    if counts["phase5f_draft_verified_count"] > 0:
        add_item(items, "Pass", "Low", "Prior Evidence", "phase5f_draft_verified", "Phase 5F draft submit-block verification", "Phase 5F draft submit blocker has been verified.")
    else:
        add_item(items, "Warning", "High", "Prior Evidence", "phase5f_draft_verified", "Phase 5F draft submit-block verification", "No Phase 5F draft submit-block verification found. This is expected if no invoice-backed source exists.", "Before any real submitted PE smoke, complete invoice-backed Phase 5F draft smoke if possible.")
    return counts, activation, phase5f, phase5d, phase5c


def evaluate_accounts(items, activation):
    if not activation:
        return {}
    company = activation.company
    bank = account_doc(activation.allowed_bank_account)
    receivable = account_doc(activation.allowed_receivable_account)
    if not company or not frappe.db.exists("Company", company):
        add_item(items, "Blocker", "Critical", "Account Control", "company", "Company", "Activation gate company is missing or invalid.")
    else:
        add_item(items, "Pass", "Low", "Account Control", "company", "Company", f"Company verified: {company}.")
    if not bank or bank.company != company or bank.root_type != "Asset" or int(bank.is_group or 0) or int(bank.disabled or 0):
        add_item(items, "Blocker", "Critical", "Account Control", "bank", "Allowed bank account", "Allowed bank account is missing or invalid.")
    else:
        add_item(items, "Pass", "Low", "Account Control", "bank", "Allowed bank account", f"Allowed bank account verified: {activation.allowed_bank_account}.", None, "Account", activation.allowed_bank_account)
    if not receivable or receivable.company != company or receivable.root_type != "Asset" or int(receivable.is_group or 0) or int(receivable.disabled or 0) or (receivable.account_type and receivable.account_type != "Receivable"):
        add_item(items, "Blocker", "Critical", "Account Control", "receivable", "Allowed receivable account", "Allowed receivable account is missing or invalid.")
    else:
        add_item(items, "Pass", "Low", "Account Control", "receivable", "Allowed receivable account", f"Allowed receivable account verified: {activation.allowed_receivable_account}.", None, "Account", activation.allowed_receivable_account)
    return {"company": company, "allowed_bank_account": activation.allowed_bank_account, "allowed_receivable_account": activation.allowed_receivable_account}


def find_valid_invoice(company):
    rows = frappe.get_all("Sales Invoice", filters={"docstatus": 1, "company": company, "outstanding_amount": [">", 0]}, fields=["name"], order_by="creation desc", limit=1)
    return rows[0].name if rows else None


def evaluate_invoice_source(items, activation, sales_invoice=None):
    if not activation:
        return None, 1
    sales_invoice = sales_invoice or find_valid_invoice(activation.company)
    if not sales_invoice:
        add_item(items, "Warning", "High", "Source", "invoice_source", "Submitted outstanding Sales Invoice source", f"No submitted outstanding Sales Invoice found for {activation.company}. Submitted PE smoke must remain source-pending.", "Do not fabricate invoices in this phase. Use a legitimate outstanding invoice when available.")
        return None, 1
    if not frappe.db.exists("Sales Invoice", sales_invoice):
        add_item(items, "Blocker", "Critical", "Source", "invoice_exists", "Sales Invoice exists", f"Sales Invoice does not exist: {sales_invoice}.")
        return None, 0
    si = frappe.get_doc("Sales Invoice", sales_invoice)
    checks = [
        (si.docstatus == 1, "invoice_submitted", "Sales Invoice submitted", f"Sales Invoice {sales_invoice} is submitted.", f"Sales Invoice {sales_invoice} is not submitted."),
        (si.company == activation.company, "invoice_company", "Sales Invoice company", "Sales Invoice company matches activation gate.", f"Sales Invoice company {si.company} does not match activation company {activation.company}."),
        (flt(si.outstanding_amount) > 0, "invoice_outstanding", "Sales Invoice outstanding", f"Outstanding amount is {flt(si.outstanding_amount):.2f}.", f"Outstanding amount is {flt(si.outstanding_amount):.2f}."),
        (bool(getattr(si, "customer", None)), "invoice_customer", "Sales Invoice customer", f"Customer verified: {si.customer}.", "Sales Invoice customer is missing."),
    ]
    for ok, key, label, pass_detail, fail_detail in checks:
        add_item(items, "Pass" if ok else "Blocker", "Low" if ok else "Critical", "Source", key, label, pass_detail if ok else fail_detail, None, "Sales Invoice" if key == "invoice_submitted" else None, sales_invoice if key == "invoice_submitted" else None)
    return si, 0


def evaluate_policy_controls(items):
    values = {
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
    for key, value in values.items():
        add_item(items, "Blocker" if value else "Pass", "Critical" if value else "Low", "Policy Control", key, labels[key], f"{value} record(s) found." if value else "Zero.")
    return values


@frappe.whitelist()
def attempt_submitted_payment_entry_smoke():
    assert_action("attempt_submitted_payment_entry_smoke")
    frappe.throw(_("Phase 5G hard block confirmed: submitted Payment Entry smoke is not available until the next controlled live-submit phase is explicitly built and acknowledged."))


def verify_submitted_smoke_hard_block(items):
    try:
        attempt_submitted_payment_entry_smoke()
    except Exception as exc:
        message = str(exc)
        if "Phase 5G hard block confirmed" in message:
            add_item(items, "Pass", "Low", "Hard Block", "submitted_pe_attempt_blocked", "Submitted PE attempt hard block", "Submitted Payment Entry smoke attempt is hard-blocked.")
            return 1, message
        add_item(items, "Warning", "Medium", "Hard Block", "submitted_pe_attempt_blocked", "Submitted PE attempt hard block", f"Function threw a different error: {message}")
        return 1, message
    add_item(items, "Blocker", "Critical", "Hard Block", "submitted_pe_attempt_blocked", "Submitted PE attempt hard block", "Submitted Payment Entry smoke did not throw a hard-block error.")
    return 0, "No hard-block error raised."


def evaluate_guardrails(items):
    values = guardrails()
    checks = [
        ("submitted_payment_entry_count_today", "Submitted Payment Entries today"),
        ("payment_entry_gl_count", "Payment Entry GL"),
        ("payment_entry_gl_count_today", "Payment Entry GL today"),
        ("submitted_journal_entry_count_today", "Submitted Journal Entries today"),
        ("purchase_invoice_count_today", "Purchase Invoices today"),
    ]
    for key, label in checks:
        add_item(items, "Blocker" if values[key] else "Pass", "Critical" if values[key] else "Low", "Strict Guardrail", key, label, f"{values[key]} record(s) found." if values[key] else "Zero.")
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


def gate_status(score, blockers, warnings, source_pending, source_ready):
    if blockers:
        return "Blocked"
    if source_pending:
        return "Source Pending"
    if warnings:
        return "Ready With Warnings"
    if source_ready and score >= 95:
        return "Ready For Submitted PE Smoke"
    return "Needs Review"


@frappe.whitelist()
def run_pe_submitted_smoke_gate(sales_invoice=None, acknowledgement=None, dry_run=1, notes=None):
    assert_action("run_pe_submitted_smoke_gate")
    items = []
    config = evaluate_config(items)
    evidence, activation, phase5f, phase5d, phase5c = evaluate_evidence(items)
    controls = evaluate_accounts(items, activation)
    si, source_pending = evaluate_invoice_source(items, activation, sales_invoice=sales_invoice)
    policy_controls = evaluate_policy_controls(items)
    submitted_blocked, submitted_block_error = verify_submitted_smoke_hard_block(items)
    guard_before = evaluate_guardrails(items)
    ack_ok = acknowledgement == SUBMITTED_SMOKE_ACK
    add_item(items, "Pass" if ack_ok else "Warning", "Low" if ack_ok else "Medium", "Acknowledgement", "submitted_smoke_ack", "Submitted smoke gate acknowledgement", "Exact acknowledgement supplied." if ack_ok else f"Required acknowledgement not supplied. Required: {SUBMITTED_SMOKE_ACK}", None if ack_ok else "Provide exact acknowledgement to create source-readiness gate record.")
    summary = summarise_items(items)
    score = calculate_score(summary["blocker_count"], summary["warning_count"])
    source_ready = int(bool(si) and not source_pending and summary["blocker_count"] == 0)
    submitted_smoke_source_ready = int(source_ready and ack_ok)
    submitted_smoke_gate_allowed = int(source_ready and ack_ok and summary["blocker_count"] == 0)
    final_gate_status = gate_status(score, summary["blocker_count"], summary["warning_count"], source_pending, source_ready)
    if summary["blocker_count"]:
        status = "Blocked"
    elif source_pending:
        status = "Source Pending"
    elif not ack_ok or summary["warning_count"]:
        status = "Needs Review"
    else:
        status = "Source Ready"
    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": status,
        "gate_status": final_gate_status,
        "gate_score": score,
        "submitted_smoke_source_ready": submitted_smoke_source_ready,
        "submitted_smoke_gate_allowed": submitted_smoke_gate_allowed,
        "source_pending": int(source_pending),
        "live_posting_allowed": 0,
        "payment_entry_created": 0,
        "payment_entry_submitted": 0,
        "sales_invoice": si.name if si else sales_invoice,
        "customer": si.customer if si else None,
        "invoice_total": flt((si.rounded_total or si.grand_total) if si else 0),
        "invoice_outstanding_amount": flt(si.outstanding_amount) if si else 0,
        "proposed_smoke_amount": min(flt(si.outstanding_amount), 1.00) if si else 0,
        "company": activation.company if activation else None,
        "allowed_bank_account": activation.allowed_bank_account if activation else None,
        "allowed_receivable_account": activation.allowed_receivable_account if activation else None,
        "activation_gate": activation.name if activation else None,
        "draft_smoke_run": phase5f.name if phase5f else None,
        "adapter_run": phase5d.name if phase5d else None,
        "posting_preview": phase5c.name if phase5c else None,
        "required_acknowledgement": SUBMITTED_SMOKE_ACK,
        "acknowledgement_ok": ack_ok,
        "config": config,
        "evidence": evidence,
        "controls": controls,
        "policy_controls": policy_controls,
        "submitted_pe_attempt_blocked": submitted_blocked,
        "submitted_pe_attempt_error": submitted_block_error,
        "guardrails_before": guard_before,
        "summary": summary,
        "items": items,
        "note": "Submitted PE smoke gate only. No Payment Entry, no submission, and no GL are created.",
    }
    if int(dry_run or 0):
        return result
    doc = frappe.new_doc(GATE_DOCTYPE)
    for fieldname in [
        "status", "gate_status", "gate_score", "submitted_smoke_source_ready", "submitted_smoke_gate_allowed", "source_pending",
        "live_posting_allowed", "payment_entry_created", "payment_entry_submitted", "sales_invoice", "customer", "invoice_total",
        "invoice_outstanding_amount", "proposed_smoke_amount", "company", "allowed_bank_account", "allowed_receivable_account",
        "activation_gate", "draft_smoke_run", "adapter_run", "posting_preview",
    ]:
        setattr(doc, fieldname, result.get(fieldname))
    doc.submitted_smoke_gate_id = make_gate_id()
    doc.gate_type = "Submitted Payment Entry Smoke Source Gate"
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.blocker_count = summary["blocker_count"]
    doc.warning_count = summary["warning_count"]
    doc.pass_count = summary["pass_count"]
    doc.info_count = summary["info_count"]
    doc.item_count = summary["item_count"]
    for fieldname, value in evidence.items():
        setattr(doc, fieldname, value)
    for fieldname, value in policy_controls.items():
        setattr(doc, fieldname, value)
    doc.submitted_pe_attempt_blocked = submitted_blocked
    doc.submitted_pe_attempt_error = submitted_block_error
    doc.payment_entry_count_before = guard_before["payment_entry_count"]
    doc.payment_entry_count_after = count_dt("Payment Entry")
    doc.submitted_payment_entry_count_today = guard_before["submitted_payment_entry_count_today"]
    doc.payment_entry_gl_count = guard_before["payment_entry_gl_count"]
    doc.payment_entry_gl_count_today = guard_before["payment_entry_gl_count_today"]
    doc.submitted_journal_entry_count_today = guard_before["submitted_journal_entry_count_today"]
    doc.purchase_invoice_count_today = guard_before["purchase_invoice_count_today"]
    doc.required_acknowledgement = SUBMITTED_SMOKE_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    for item in items:
        row = frappe.new_doc(ITEM_DOCTYPE)
        row.submitted_smoke_gate = doc.name
        for fieldname in ["status", "severity", "category", "check_key", "check_label", "detail", "recommendation", "source_doctype", "source_name"]:
            setattr(row, fieldname, item.get(fieldname))
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)
    guard_after = guardrails()
    frappe.db.set_value(GATE_DOCTYPE, doc.name, {**{k: guard_after[k] for k in ["submitted_payment_entry_count_today", "payment_entry_gl_count", "payment_entry_gl_count_today", "submitted_journal_entry_count_today", "purchase_invoice_count_today"]}, "payment_entry_count_after": guard_after["payment_entry_count"], "summary_json": safe_json({**result, "guardrails_after": guard_after})}, update_modified=False)
    frappe.db.commit()
    return {**result, "created": True, "submitted_smoke_gate": doc.name, "submitted_smoke_gate_id": doc.submitted_smoke_gate_id, "guardrails_after": guard_after}


@frappe.whitelist()
def cancel_pe_submitted_smoke_gate(submitted_smoke_gate, reason=None):
    assert_action("cancel_pe_submitted_smoke_gate")
    if not frappe.db.exists(GATE_DOCTYPE, submitted_smoke_gate):
        frappe.throw(_("Submitted smoke gate not found: {0}").format(submitted_smoke_gate))
    frappe.db.set_value(GATE_DOCTYPE, submitted_smoke_gate, {"status": "Cancelled", "submitted_smoke_source_ready": 0, "submitted_smoke_gate_allowed": 0, "live_posting_allowed": 0, "payment_entry_created": 0, "payment_entry_submitted": 0, "cancelled_on": now_datetime(), "cancelled_by": frappe.session.user, "summary_json": reason or "Phase 5G submitted smoke gate cancelled."}, update_modified=False)
    frappe.db.sql(f"UPDATE `tab{ITEM_DOCTYPE}` SET status = 'Cancelled' WHERE submitted_smoke_gate = %(submitted_smoke_gate)s", {"submitted_smoke_gate": submitted_smoke_gate})
    frappe.db.commit()
    return {"submitted_smoke_gate": submitted_smoke_gate, "status": "Cancelled", "note": "Submitted smoke gate cancelled only. No accounting/payment movement occurred."}


@frappe.whitelist()
def quick_pe_submitted_smoke_gate_summary(limit=20):
    return {
        "gates": frappe.get_all(GATE_DOCTYPE, fields=["name", "submitted_smoke_gate_id", "status", "gate_status", "gate_score", "submitted_smoke_source_ready", "submitted_smoke_gate_allowed", "source_pending", "sales_invoice", "company", "invoice_outstanding_amount", "proposed_smoke_amount", "payment_entry_created", "payment_entry_submitted", "live_posting_allowed", "payment_entry_gl_count", "checked_on", "checked_by"], order_by="creation desc", limit=int(limit or 20)),
        "items": frappe.get_all(ITEM_DOCTYPE, fields=["name", "submitted_smoke_gate", "status", "severity", "category", "check_label", "detail", "recommendation", "source_doctype", "source_name"], order_by="creation desc", limit=int(limit or 20)),
        "required_acknowledgement": SUBMITTED_SMOKE_ACK,
        "guardrails": guardrails(),
        "config": config_state(),
        "note": "Phase 5G submitted smoke gate summary only. No Payment Entry or GL is created.",
    }


def execute_gate_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions, params = [], {"currency": currency()}
    if filters.get("status"):
        conditions.append("g.status = %(status)s")
        params["status"] = filters.status
    if filters.get("from_date"):
        conditions.append("DATE(g.checked_on) >= %(from_date)s")
        params["from_date"] = filters.from_date
    if filters.get("to_date"):
        conditions.append("DATE(g.checked_on) <= %(to_date)s")
        params["to_date"] = filters.to_date
    columns = [
        {"fieldname": "submitted_smoke_gate", "label": _("Submitted Smoke Gate"), "fieldtype": "Link", "options": GATE_DOCTYPE, "width": 220},
        {"fieldname": "submitted_smoke_gate_id", "label": _("Gate ID"), "fieldtype": "Data", "width": 360},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 130},
        {"fieldname": "gate_status", "label": _("Gate Status"), "fieldtype": "Data", "width": 230},
        {"fieldname": "gate_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "submitted_smoke_source_ready", "label": _("Source Ready"), "fieldtype": "Check", "width": 110},
        {"fieldname": "submitted_smoke_gate_allowed", "label": _("Gate Allowed"), "fieldtype": "Check", "width": 110},
        {"fieldname": "source_pending", "label": _("Source Pending"), "fieldtype": "Check", "width": 120},
        {"fieldname": "sales_invoice", "label": _("Sales Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 180},
        {"fieldname": "invoice_outstanding_amount", "label": _("Outstanding"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "payment_entry_created", "label": _("PE Created"), "fieldtype": "Check", "width": 100},
        {"fieldname": "payment_entry_submitted", "label": _("PE Submitted"), "fieldtype": "Check", "width": 110},
        {"fieldname": "payment_entry_gl_count", "label": _("PE GL"), "fieldtype": "Int", "width": 80},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(f"SELECT g.name AS submitted_smoke_gate, g.submitted_smoke_gate_id, g.status, g.gate_status, g.gate_score, g.submitted_smoke_source_ready, g.submitted_smoke_gate_allowed, g.source_pending, g.sales_invoice, g.invoice_outstanding_amount, g.payment_entry_created, g.payment_entry_submitted, g.payment_entry_gl_count, g.checked_on, %(currency)s AS currency FROM `tab{GATE_DOCTYPE}` g {build_where(conditions)} ORDER BY g.creation DESC", params, as_dict=True)
    chart = {"data": {"labels": [row.submitted_smoke_gate_id for row in data[:20]], "datasets": [{"name": "Source Ready", "values": [int(row.submitted_smoke_source_ready or 0) for row in data[:20]]}, {"name": "Source Pending", "values": [int(row.source_pending or 0) for row in data[:20]]}, {"name": "PE Submitted", "values": [int(row.payment_entry_submitted or 0) for row in data[:20]]}]}, "type": "bar"}
    summary = [{"value": len(data), "indicator": "Blue", "label": _("Submitted Smoke Gates"), "datatype": "Int"}, {"value": len([row for row in data if row.submitted_smoke_source_ready]), "indicator": "Green", "label": _("Source Ready"), "datatype": "Int"}, {"value": len([row for row in data if row.source_pending]), "indicator": "Orange", "label": _("Source Pending"), "datatype": "Int"}, {"value": sum(int(row.payment_entry_submitted or 0) for row in data), "indicator": "Red", "label": _("Submitted PE"), "datatype": "Int"}]
    return columns, data, None, chart, summary


def execute_exception_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions, params = [], {}
    for key in ["submitted_smoke_gate", "status", "severity", "category"]:
        if filters.get(key):
            conditions.append(f"i.{key} = %({key})s")
            params[key] = filters.get(key)
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": ITEM_DOCTYPE, "width": 220},
        {"fieldname": "submitted_smoke_gate", "label": _("Submitted Smoke Gate"), "fieldtype": "Link", "options": GATE_DOCTYPE, "width": 220},
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
    data = frappe.db.sql(f"SELECT i.name AS item, i.submitted_smoke_gate, i.status, i.severity, i.category, i.check_label, i.detail, i.recommendation, i.source_doctype, i.source_name, i.checked_on FROM `tab{ITEM_DOCTYPE}` i {build_where(conditions)} ORDER BY CASE i.status WHEN 'Blocker' THEN 1 WHEN 'Warning' THEN 2 WHEN 'Info' THEN 3 WHEN 'Pass' THEN 4 ELSE 5 END, i.creation DESC", params, as_dict=True)
    chart_map = {}
    for row in data:
        chart_map[row.status or "Info"] = chart_map.get(row.status or "Info", 0) + 1
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Items", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [{"value": len(data), "indicator": "Blue", "label": _("Items"), "datatype": "Int"}, {"value": len([row for row in data if row.status == "Pass"]), "indicator": "Green", "label": _("Pass"), "datatype": "Int"}, {"value": len([row for row in data if row.status == "Warning"]), "indicator": "Orange", "label": _("Warnings"), "datatype": "Int"}, {"value": len([row for row in data if row.status == "Blocker"]), "indicator": "Red", "label": _("Blockers"), "datatype": "Int"}]
    return columns, data, None, chart, summary


def execute_source_readiness_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions, params = ["si.docstatus = 1"], {"currency": currency()}
    if filters.get("company"):
        conditions.append("si.company = %(company)s")
        params["company"] = filters.company
    if filters.get("only_outstanding"):
        conditions.append("si.outstanding_amount > 0")
    columns = [
        {"fieldname": "sales_invoice", "label": _("Sales Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 180},
        {"fieldname": "customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 180},
        {"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 200},
        {"fieldname": "rounded_total", "label": _("Invoice Total"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "outstanding_amount", "label": _("Outstanding"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "readiness_status", "label": _("Readiness Status"), "fieldtype": "Data", "width": 180},
        {"fieldname": "posting_date", "label": _("Posting Date"), "fieldtype": "Date", "width": 110},
        {"fieldname": "creation", "label": _("Created On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(f"SELECT si.name AS sales_invoice, si.customer, si.company, si.rounded_total, si.outstanding_amount, CASE WHEN si.docstatus = 1 AND si.outstanding_amount > 0 THEN 'Ready Source' WHEN si.docstatus = 1 AND si.outstanding_amount <= 0 THEN 'No Outstanding' ELSE 'Not Submitted' END AS readiness_status, si.posting_date, si.creation, %(currency)s AS currency FROM `tabSales Invoice` si {build_where(conditions)} ORDER BY si.creation DESC LIMIT 500", params, as_dict=True)
    chart_map = {}
    for row in data:
        chart_map[row.readiness_status or "Unknown"] = chart_map.get(row.readiness_status or "Unknown", 0) + 1
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Invoices", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [{"value": len(data), "indicator": "Blue", "label": _("Submitted Invoices"), "datatype": "Int"}, {"value": len([row for row in data if row.readiness_status == "Ready Source"]), "indicator": "Green", "label": _("Ready Sources"), "datatype": "Int"}, {"value": sum(flt(row.outstanding_amount) for row in data if row.readiness_status == "Ready Source"), "indicator": "Green", "label": _("Outstanding Ready"), "datatype": "Currency", "currency": currency()}]
    return columns, data, None, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
