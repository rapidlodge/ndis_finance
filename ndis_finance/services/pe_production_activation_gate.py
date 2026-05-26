import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


ACTIVATION_ACK = "I_CONFIRM_PE_PRODUCTION_ACTIVATION_GATE_READY_NO_PAYMENT_ENTRY"


def make_activation_gate_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-PE-PROD-ACT-GATE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_phase5d_run():
    return latest_doc(
        "NDIS PE Production Adapter Run",
        {
            "status": "Hard Blocked",
            "acknowledgement_ok": 1,
            "payment_entry_created": 0,
            "live_posting_allowed": 0,
            "actual_payment_entry_created_count": 0,
            "blocker_count": 0,
        },
        [
            "name",
            "adapter_run_id",
            "source_preview",
            "company",
            "allowed_bank_account",
            "allowed_receivable_account",
            "mapping_gate",
            "design_gate",
            "adapter_score",
        ],
        "executed_on desc, creation desc",
    )


def latest_phase5c_preview():
    return latest_doc(
        "NDIS PE Production Posting Preview",
        {"status": "Previewed", "acknowledgement_ok": 1, "payment_entry_created": 0, "live_posting_allowed": 0, "blocker_count": 0},
        ["name", "preview_id", "preview_score"],
        "previewed_on desc, creation desc",
    )


def latest_phase5b_gate():
    return latest_doc(
        "NDIS PE Production Account Mapping Gate",
        {"account_mapping_hardened": 1, "ready_for_preview_phase": 1, "live_posting_allowed": 0, "blocker_count": 0},
        ["name", "gate_id", "company", "allowed_bank_account", "allowed_receivable_account", "hardening_score"],
        "checked_on desc, creation desc",
    )


def latest_phase5a_gate():
    return latest_doc(
        "NDIS PE Production Design Gate",
        {"design_approved_for_next_phase": 1, "live_posting_allowed": 0, "blocker_count": 0},
        ["name", "gate_id", "design_score"],
        "checked_on desc, creation desc",
    )


def latest_phase4d_freeze():
    return latest_doc(
        "NDIS PE Sandbox Readiness Freeze",
        {"readiness_allowed": 1, "ready_for_next_design_phase": 1, "blocker_count": 0},
        ["name", "freeze_id", "readiness_score"],
        "frozen_on desc, creation desc",
    )


def account_doc(account):
    if not account or not frappe.db.exists("Account", account):
        return None
    return frappe.get_doc("Account", account)


def evaluate_config(items):
    config = config_state()
    if config["sandbox_enabled"]:
        add_item(items, "Pass", "Low", "Site Config", "sandbox_enabled", "Sandbox config", "Sandbox config remains enabled.")
    else:
        add_item(items, "Warning", "Medium", "Site Config", "sandbox_enabled", "Sandbox config", "Sandbox config is not enabled.")

    if config["production_mode"]:
        add_item(items, "Blocker", "Critical", "Site Config", "production_mode", "Production mode", "Production mode is enabled.", "Phase 5E must not enable production mode.")
    else:
        add_item(items, "Pass", "Low", "Site Config", "production_mode", "Production mode", "Production mode remains disabled.")

    if config["live_pe_enabled"]:
        add_item(items, "Blocker", "Critical", "Site Config", "live_pe_enabled", "Live PE posting config", "Live Payment Entry posting config is enabled.", "Phase 5E must keep live posting config disabled.")
    else:
        add_item(items, "Pass", "Low", "Site Config", "live_pe_enabled", "Live PE posting config", "Live Payment Entry posting config remains disabled.")
    return config


def evaluate_prior_evidence(items):
    phase5d = latest_phase5d_run()
    phase5c = latest_phase5c_preview()
    phase5b = latest_phase5b_gate()
    phase5a = latest_phase5a_gate()
    phase4d = latest_phase4d_freeze()

    counts = {
        "phase5d_hard_blocked_run_count": count_dt(
            "NDIS PE Production Adapter Run",
            {"status": "Hard Blocked", "acknowledgement_ok": 1, "payment_entry_created": 0, "live_posting_allowed": 0, "actual_payment_entry_created_count": 0, "blocker_count": 0},
        ),
        "phase5c_preview_count": count_dt("NDIS PE Production Posting Preview", {"status": "Previewed", "acknowledgement_ok": 1, "payment_entry_created": 0, "live_posting_allowed": 0, "blocker_count": 0}),
        "phase5b_hardened_gate_count": count_dt("NDIS PE Production Account Mapping Gate", {"account_mapping_hardened": 1, "ready_for_preview_phase": 1, "live_posting_allowed": 0, "blocker_count": 0}),
        "phase5a_approved_gate_count": count_dt("NDIS PE Production Design Gate", {"design_approved_for_next_phase": 1, "live_posting_allowed": 0, "blocker_count": 0}),
        "phase4d_ready_freeze_count": count_dt("NDIS PE Sandbox Readiness Freeze", {"readiness_allowed": 1, "ready_for_next_design_phase": 1, "blocker_count": 0}),
    }

    evidence_map = [
        ("phase5d_hard_blocked_run_count", "Phase 5D adapter hard block", phase5d, "NDIS PE Production Adapter Run"),
        ("phase5c_preview_count", "Phase 5C posting preview", phase5c, "NDIS PE Production Posting Preview"),
        ("phase5b_hardened_gate_count", "Phase 5B account mapping hardening", phase5b, "NDIS PE Production Account Mapping Gate"),
        ("phase5a_approved_gate_count", "Phase 5A design gate", phase5a, "NDIS PE Production Design Gate"),
        ("phase4d_ready_freeze_count", "Phase 4D sandbox readiness freeze", phase4d, "NDIS PE Sandbox Readiness Freeze"),
    ]
    for key, label, source, doctype in evidence_map:
        if counts[key] > 0 and source:
            add_item(items, "Pass", "Low", "Prior Evidence", key, label, f"{counts[key]} valid record(s) found.", None, doctype, source.name)
        else:
            add_item(items, "Blocker", "Critical", "Prior Evidence", key, label, "Required evidence is missing.", f"Complete {label} before Phase 5E activation gate.")
    return counts, phase5d, phase5c, phase5b, phase5a, phase4d


def evaluate_accounts(items, company, bank_account, receivable_account):
    bank = account_doc(bank_account)
    receivable = account_doc(receivable_account)

    if not company or not frappe.db.exists("Company", company):
        add_item(items, "Blocker", "Critical", "Account Control", "company_valid", "Company", "Company is missing or invalid.")
    else:
        add_item(items, "Pass", "Low", "Account Control", "company_valid", "Company", f"Company verified: {company}.")

    if not bank:
        add_item(items, "Blocker", "Critical", "Account Control", "bank_valid", "Allowed bank account", "Allowed bank account is missing or invalid.")
    else:
        if int(bank.is_group or 0) or int(bank.disabled or 0):
            add_item(items, "Blocker", "Critical", "Account Control", "bank_valid", "Allowed bank account", "Bank account is group/disabled.", "Use a non-group enabled account.")
        elif bank.company != company:
            add_item(items, "Blocker", "Critical", "Account Control", "bank_company", "Bank account company", f"Bank account company {bank.company} does not match {company}.")
        elif bank.root_type != "Asset":
            add_item(items, "Blocker", "Critical", "Account Control", "bank_root", "Bank account root type", f"Bank account root type is {bank.root_type}; expected Asset.")
        else:
            add_item(items, "Pass", "Low", "Account Control", "bank_valid", "Allowed bank account", f"Bank/paid-to account verified: {bank_account}.", None, "Account", bank_account)

        if bank.account_type not in ["Bank", "Cash"]:
            add_item(items, "Warning", "Medium", "Account Control", "bank_type", "Bank account type", f"Selected paid-to account type is {bank.account_type or 'blank'}, not Bank/Cash.", "Review before first live smoke.")
        else:
            add_item(items, "Pass", "Low", "Account Control", "bank_type", "Bank account type", f"Bank account type is {bank.account_type}.")

    if not receivable:
        add_item(items, "Blocker", "Critical", "Account Control", "receivable_valid", "Allowed receivable account", "Allowed receivable account is missing or invalid.")
    else:
        if int(receivable.is_group or 0) or int(receivable.disabled or 0):
            add_item(items, "Blocker", "Critical", "Account Control", "receivable_valid", "Allowed receivable account", "Receivable account is group/disabled.", "Use a non-group enabled receivable account.")
        elif receivable.company != company:
            add_item(items, "Blocker", "Critical", "Account Control", "receivable_company", "Receivable account company", f"Receivable account company {receivable.company} does not match {company}.")
        elif receivable.root_type != "Asset":
            add_item(items, "Blocker", "Critical", "Account Control", "receivable_root", "Receivable account root type", f"Receivable root type is {receivable.root_type}; expected Asset.")
        elif receivable.account_type and receivable.account_type != "Receivable":
            add_item(items, "Blocker", "High", "Account Control", "receivable_type", "Receivable account type", f"Receivable account type is {receivable.account_type}; expected Receivable.")
        else:
            add_item(items, "Pass", "Low", "Account Control", "receivable_valid", "Allowed receivable account", f"Receivable/paid-from account verified: {receivable_account}.", None, "Account", receivable_account)

    return {"bank_account_type": bank.account_type if bank else None, "receivable_account_type": receivable.account_type if receivable else None}


def evaluate_policies(items, company, bank_account, receivable_account):
    policy_count = count_dt("NDIS PE Production Posting Policy")
    live_enabled = count_dt("NDIS PE Production Posting Policy", {"production_posting_enabled": 1})
    cross_company = count_dt("NDIS PE Production Posting Policy", {"allow_cross_company_posting": 1})
    overpayment = count_dt("NDIS PE Production Posting Policy", {"allow_overpayment": 1})
    negative = count_dt("NDIS PE Production Posting Policy", {"allow_negative_receipt": 1})

    eligible = frappe.get_all(
        "NDIS PE Production Posting Policy",
        filters={"posting_decision": "Eligible After Approval", "event_type": ["in", ["Paid Claim", "Short Paid Claim"]]},
        fields=["name", "policy_id", "company", "allowed_bank_account", "allowed_receivable_account", "mapping_rule", "production_posting_enabled", "allow_cross_company_posting", "allow_overpayment", "allow_negative_receipt"],
        limit=1000,
    )

    hardened_eligible = 0
    for row in eligible:
        if (
            row.company == company
            and row.allowed_bank_account == bank_account
            and row.allowed_receivable_account == receivable_account
            and row.mapping_rule
            and not int(row.production_posting_enabled or 0)
            and not int(row.allow_cross_company_posting or 0)
            and not int(row.allow_overpayment or 0)
            and not int(row.allow_negative_receipt or 0)
        ):
            hardened_eligible += 1
            add_item(items, "Pass", "Low", "Policy Control", f"eligible_{row.policy_id}", f"Eligible policy {row.policy_id}", "Eligible paid/short-paid policy is hardened.", None, "NDIS PE Production Posting Policy", row.name)
        else:
            add_item(items, "Blocker", "Critical", "Policy Control", f"eligible_{row.policy_id}", f"Eligible policy {row.policy_id}", "Eligible policy is not fully hardened.", "Run/fix Phase 5B before activation.", "NDIS PE Production Posting Policy", row.name)

    rejected_block = count_dt("NDIS PE Production Posting Policy", {"event_type": "Rejected Claim", "posting_decision": "Never Post Payment Entry", "production_posting_enabled": 0})
    writeoff_block = count_dt("NDIS PE Production Posting Policy", {"event_type": "Write Off", "posting_decision": "Never Post Payment Entry", "production_posting_enabled": 0})
    cancelled_block = count_dt("NDIS PE Production Posting Policy", {"event_type": "Cancelled Claim", "posting_decision": "Never Post Payment Entry", "production_posting_enabled": 0})

    for count_value, key, label, detail in [
        (live_enabled, "live_enabled_policy", "Live-enabled policies", "live-enabled policy record(s) found."),
        (cross_company, "cross_company", "Cross-company flag", "policy record(s) allow cross-company posting."),
        (overpayment, "overpayment", "Overpayment flag", "policy record(s) allow overpayment."),
        (negative, "negative_receipt", "Negative receipt flag", "policy record(s) allow negative receipt."),
    ]:
        if count_value:
            add_item(items, "Blocker", "Critical", "Policy Control", key, label, f"{count_value} {detail}")
        else:
            add_item(items, "Pass", "Low", "Policy Control", key, label, f"{label} controlled.")

    for label, count_value, key in [
        ("Rejected claim block policy", rejected_block, "rejected_block"),
        ("Write-off block policy", writeoff_block, "writeoff_block"),
        ("Cancelled claim block policy", cancelled_block, "cancelled_block"),
    ]:
        if count_value:
            add_item(items, "Pass", "Low", "Policy Control", key, label, f"{label} verified.")
        else:
            add_item(items, "Blocker", "Critical", "Policy Control", key, label, f"{label} missing.")

    return {
        "policy_count": policy_count,
        "eligible_policy_count": len(eligible),
        "hardened_eligible_policy_count": hardened_eligible,
        "live_enabled_policy_count": live_enabled,
        "rejected_block_policy_count": rejected_block,
        "writeoff_block_policy_count": writeoff_block,
        "cancelled_block_policy_count": cancelled_block,
        "cross_company_allowed_count": cross_company,
        "overpayment_allowed_count": overpayment,
        "negative_receipt_allowed_count": negative,
    }


def verify_direct_hard_block(items):
    try:
        from ndis_finance.services.pe_production_adapter_hard_block import attempt_live_payment_entry_creation

        attempt_live_payment_entry_creation()
    except Exception as exc:
        message = str(exc)
        if "hard block" in message.lower() or "not available until phase 5e activation gate" in message.lower():
            add_item(items, "Pass", "Low", "Hard Block", "direct_live_creation_blocked", "Direct live creation hard block", "Direct live Payment Entry creation function is still hard-blocked.")
            return 1, message
        add_item(items, "Warning", "Medium", "Hard Block", "direct_live_creation_blocked", "Direct live creation hard block", f"Function threw a different error: {message}", "Review before Phase 5F.")
        return 1, message

    add_item(items, "Blocker", "Critical", "Hard Block", "direct_live_creation_blocked", "Direct live creation hard block", "Direct live Payment Entry creation did not throw a hard-block error.", "Do not proceed.")
    return 0, "No hard-block error raised."


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
        "blocker_count": len([item for item in items if item["status"] == "Blocker"]),
        "warning_count": len([item for item in items if item["status"] == "Warning"]),
        "pass_count": len([item for item in items if item["status"] == "Pass"]),
        "info_count": len([item for item in items if item["status"] == "Info"]),
        "item_count": len(items),
    }


def calculate_score(blockers, warnings):
    return max(0, round(100 - int(blockers or 0) * 25 - int(warnings or 0) * 5, 2))


def activation_status(score, blockers, warnings):
    if blockers:
        return "Blocked"
    if warnings:
        return "Ready With Warnings"
    if score >= 95:
        return "Ready For Single-record Live Smoke"
    return "Needs Review"


@frappe.whitelist()
def run_pe_production_activation_gate(acknowledgement=None, dry_run=1, notes=None):
    assert_action("run_pe_production_activation_gate")

    items = []
    config = evaluate_config(items)
    evidence, phase5d, phase5c, phase5b, phase5a, phase4d = evaluate_prior_evidence(items)

    company = phase5d.company if phase5d else (phase5b.company if phase5b else None)
    bank_account = phase5d.allowed_bank_account if phase5d else (phase5b.allowed_bank_account if phase5b else None)
    receivable_account = phase5d.allowed_receivable_account if phase5d else (phase5b.allowed_receivable_account if phase5b else None)

    account_info = evaluate_accounts(items, company, bank_account, receivable_account)
    policies = evaluate_policies(items, company, bank_account, receivable_account)
    direct_blocked, direct_block_error = verify_direct_hard_block(items)
    guard_before = evaluate_guardrails(items)

    ack_ok = acknowledgement == ACTIVATION_ACK
    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "activation_ack", "Activation acknowledgement", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "activation_ack", "Activation acknowledgement", f"Required acknowledgement not supplied. Required: {ACTIVATION_ACK}", "Provide exact acknowledgement to allow next-phase readiness.")

    summary = summarise_items(items)
    score = calculate_score(summary["blocker_count"], summary["warning_count"])
    final_activation_status = activation_status(score, summary["blocker_count"], summary["warning_count"])
    production_activation_allowed = int(summary["blocker_count"] == 0 and ack_ok)
    ready_for_single_record_live_smoke = production_activation_allowed

    if summary["blocker_count"]:
        status = "Blocked"
    elif not ack_ok or summary["warning_count"]:
        status = "Needs Review"
    else:
        status = "Activation Allowed"

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": status,
        "activation_status": final_activation_status,
        "activation_score": score,
        "production_activation_allowed": production_activation_allowed,
        "ready_for_single_record_live_smoke": ready_for_single_record_live_smoke,
        "live_posting_allowed": 0,
        "payment_entry_created": 0,
        "company": company,
        "allowed_bank_account": bank_account,
        "allowed_receivable_account": receivable_account,
        "required_acknowledgement": ACTIVATION_ACK,
        "acknowledgement_ok": ack_ok,
        "config": config,
        "evidence": evidence,
        "account_info": account_info,
        "policies": policies,
        "direct_live_creation_blocked": direct_blocked,
        "direct_live_creation_error": direct_block_error,
        "guardrails_before": guard_before,
        "summary": summary,
        "items": items,
        "note": "Activation gate only. It creates a readiness record only. Live config remains disabled and no Payment Entry/GL is created.",
    }

    if int(dry_run or 0):
        return result

    doc = frappe.new_doc("NDIS PE Production Activation Gate")
    doc.activation_gate_id = make_activation_gate_id()
    doc.status = status
    doc.gate_type = "Production Payment Entry Activation Readiness"
    doc.production_activation_allowed = production_activation_allowed
    doc.ready_for_single_record_live_smoke = ready_for_single_record_live_smoke
    doc.live_posting_allowed = 0
    doc.payment_entry_created = 0
    doc.company = company
    doc.allowed_bank_account = bank_account
    doc.allowed_receivable_account = receivable_account
    doc.bank_account_type = account_info.get("bank_account_type")
    doc.receivable_account_type = account_info.get("receivable_account_type")
    doc.source_adapter_run = phase5d.name if phase5d else None
    doc.source_preview = phase5c.name if phase5c else None
    doc.mapping_gate = phase5b.name if phase5b else None
    doc.design_gate = phase5a.name if phase5a else None
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.activation_score = score
    doc.activation_status = final_activation_status
    doc.blocker_count = summary["blocker_count"]
    doc.warning_count = summary["warning_count"]
    doc.pass_count = summary["pass_count"]
    doc.info_count = summary["info_count"]
    doc.item_count = summary["item_count"]

    for fieldname, value in evidence.items():
        setattr(doc, fieldname, value)
    for fieldname, value in policies.items():
        setattr(doc, fieldname, value)

    doc.direct_live_creation_blocked = direct_blocked
    doc.direct_live_creation_error = direct_block_error
    doc.payment_entry_count_before = guard_before["payment_entry_count"]
    doc.payment_entry_count_after = count_dt("Payment Entry")
    doc.submitted_payment_entry_count_today = guard_before["submitted_payment_entry_count_today"]
    doc.payment_entry_gl_count = guard_before["payment_entry_gl_count"]
    doc.payment_entry_gl_count_today = guard_before["payment_entry_gl_count_today"]
    doc.submitted_journal_entry_count_today = guard_before["submitted_journal_entry_count_today"]
    doc.purchase_invoice_count_today = guard_before["purchase_invoice_count_today"]
    doc.required_acknowledgement = ACTIVATION_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    for item in items:
        row = frappe.new_doc("NDIS PE Production Activation Gate Item")
        row.activation_gate = doc.name
        row.status = item["status"]
        row.severity = item["severity"]
        row.category = item["category"]
        row.check_key = item["check_key"]
        row.check_label = item["check_label"]
        row.detail = item["detail"]
        row.recommendation = item.get("recommendation")
        row.source_doctype = item.get("source_doctype")
        row.source_name = item.get("source_name")
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)

    guard_after = guardrails()
    frappe.db.set_value(
        "NDIS PE Production Activation Gate",
        doc.name,
        {
            "payment_entry_count_after": guard_after["payment_entry_count"],
            "submitted_payment_entry_count_today": guard_after["submitted_payment_entry_count_today"],
            "payment_entry_gl_count": guard_after["payment_entry_gl_count"],
            "payment_entry_gl_count_today": guard_after["payment_entry_gl_count_today"],
            "submitted_journal_entry_count_today": guard_after["submitted_journal_entry_count_today"],
            "purchase_invoice_count_today": guard_after["purchase_invoice_count_today"],
            "summary_json": safe_json({**result, "guardrails_after": guard_after}),
        },
        update_modified=False,
    )
    frappe.db.commit()

    result["created"] = True
    result["activation_gate"] = doc.name
    result["activation_gate_id"] = doc.activation_gate_id
    result["guardrails_after"] = guard_after
    return result


@frappe.whitelist()
def cancel_pe_production_activation_gate(activation_gate, reason=None):
    assert_action("cancel_pe_production_activation_gate")
    if not frappe.db.exists("NDIS PE Production Activation Gate", activation_gate):
        frappe.throw(_("PE Production Activation Gate not found: {0}").format(activation_gate))

    frappe.db.set_value(
        "NDIS PE Production Activation Gate",
        activation_gate,
        {
            "status": "Cancelled",
            "production_activation_allowed": 0,
            "ready_for_single_record_live_smoke": 0,
            "live_posting_allowed": 0,
            "payment_entry_created": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Production PE activation gate cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql("UPDATE `tabNDIS PE Production Activation Gate Item` SET status = 'Cancelled' WHERE activation_gate = %(activation_gate)s", {"activation_gate": activation_gate})
    frappe.db.commit()
    return {"activation_gate": activation_gate, "status": "Cancelled", "note": "Activation gate cancelled only. No accounting/payment records were changed."}


@frappe.whitelist()
def quick_pe_production_activation_summary(limit=20):
    gates = frappe.get_all(
        "NDIS PE Production Activation Gate",
        fields=[
            "name",
            "activation_gate_id",
            "status",
            "activation_status",
            "activation_score",
            "production_activation_allowed",
            "ready_for_single_record_live_smoke",
            "live_posting_allowed",
            "payment_entry_created",
            "company",
            "allowed_bank_account",
            "allowed_receivable_account",
            "blocker_count",
            "warning_count",
            "payment_entry_gl_count",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(
        "NDIS PE Production Activation Gate Item",
        fields=["name", "activation_gate", "status", "severity", "category", "check_label", "detail", "recommendation", "source_doctype", "source_name"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "gates": gates,
        "items": items,
        "required_acknowledgement": ACTIVATION_ACK,
        "guardrails": guardrails(),
        "config": config_state(),
        "note": "Activation summary only. No live posting config is enabled and no Payment Entry is created.",
    }


def execute_activation_gate_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("status"):
        conditions.append("g.status = %(status)s")
        params["status"] = filters.status
    if filters.get("activation_status"):
        conditions.append("g.activation_status = %(activation_status)s")
        params["activation_status"] = filters.activation_status
    if filters.get("from_date"):
        conditions.append("DATE(g.checked_on) >= %(from_date)s")
        params["from_date"] = filters.from_date
    if filters.get("to_date"):
        conditions.append("DATE(g.checked_on) <= %(to_date)s")
        params["to_date"] = filters.to_date

    columns = [
        {"fieldname": "activation_gate", "label": _("Activation Gate"), "fieldtype": "Link", "options": "NDIS PE Production Activation Gate", "width": 220},
        {"fieldname": "activation_gate_id", "label": _("Activation Gate ID"), "fieldtype": "Data", "width": 340},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 130},
        {"fieldname": "activation_status", "label": _("Activation Status"), "fieldtype": "Data", "width": 260},
        {"fieldname": "activation_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "production_activation_allowed", "label": _("Activation Allowed"), "fieldtype": "Check", "width": 130},
        {"fieldname": "ready_for_single_record_live_smoke", "label": _("Smoke Ready"), "fieldtype": "Check", "width": 110},
        {"fieldname": "live_posting_allowed", "label": _("Live Allowed"), "fieldtype": "Check", "width": 100},
        {"fieldname": "payment_entry_created", "label": _("PE Created"), "fieldtype": "Check", "width": 100},
        {"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 190},
        {"fieldname": "allowed_bank_account", "label": _("Bank Account"), "fieldtype": "Link", "options": "Account", "width": 220},
        {"fieldname": "allowed_receivable_account", "label": _("Receivable"), "fieldtype": "Link", "options": "Account", "width": 220},
        {"fieldname": "blocker_count", "label": _("Blockers"), "fieldtype": "Int", "width": 90},
        {"fieldname": "warning_count", "label": _("Warnings"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_gl_count", "label": _("PE GL"), "fieldtype": "Int", "width": 80},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]
    data = frappe.db.sql(
        f"""
        SELECT g.name AS activation_gate, g.activation_gate_id, g.status, g.activation_status,
            g.activation_score, g.production_activation_allowed, g.ready_for_single_record_live_smoke,
            g.live_posting_allowed, g.payment_entry_created, g.company, g.allowed_bank_account,
            g.allowed_receivable_account, g.blocker_count, g.warning_count, g.payment_entry_gl_count, g.checked_on
        FROM `tabNDIS PE Production Activation Gate` g
        {build_where(conditions)}
        ORDER BY g.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {"data": {"labels": [row.activation_gate_id for row in data[:20]], "datasets": [{"name": "Score", "values": [flt(row.activation_score) for row in data[:20]]}, {"name": "Blockers", "values": [int(row.blocker_count or 0) for row in data[:20]]}, {"name": "Warnings", "values": [int(row.warning_count or 0) for row in data[:20]]}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Activation Gates"), "datatype": "Int"},
        {"value": len([row for row in data if row.production_activation_allowed]), "indicator": "Green", "label": _("Activation Allowed"), "datatype": "Int"},
        {"value": len([row for row in data if row.live_posting_allowed]), "indicator": "Red", "label": _("Live Allowed"), "datatype": "Int"},
        {"value": sum(int(row.payment_entry_gl_count or 0) for row in data), "indicator": "Red", "label": _("Payment Entry GL"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_activation_exception_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    for fieldname in ["activation_gate", "status", "severity", "category"]:
        if filters.get(fieldname):
            conditions.append(f"i.{fieldname} = %({fieldname})s")
            params[fieldname] = filters.get(fieldname)

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": "NDIS PE Production Activation Gate Item", "width": 220},
        {"fieldname": "activation_gate", "label": _("Activation Gate"), "fieldtype": "Link", "options": "NDIS PE Production Activation Gate", "width": 220},
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
        SELECT i.name AS item, i.activation_gate, i.status, i.severity, i.category, i.check_label,
            i.detail, i.recommendation, i.source_doctype, i.source_name, i.checked_on
        FROM `tabNDIS PE Production Activation Gate Item` i
        {build_where(conditions)}
        ORDER BY CASE i.status WHEN 'Blocker' THEN 1 WHEN 'Warning' THEN 2 WHEN 'Info' THEN 3 WHEN 'Pass' THEN 4 ELSE 5 END, i.creation DESC
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


def execute_policy_readiness_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("event_type"):
        conditions.append("p.event_type = %(event_type)s")
        params["event_type"] = filters.event_type
    if filters.get("posting_decision"):
        conditions.append("p.posting_decision = %(posting_decision)s")
        params["posting_decision"] = filters.posting_decision

    readiness_case = """
        CASE
            WHEN p.production_posting_enabled = 1 THEN 'Blocked - Live Enabled'
            WHEN p.allow_cross_company_posting = 1 THEN 'Blocked - Cross-company Allowed'
            WHEN p.allow_overpayment = 1 THEN 'Blocked - Overpayment Allowed'
            WHEN p.allow_negative_receipt = 1 THEN 'Blocked - Negative Receipt Allowed'
            WHEN p.posting_decision = 'Eligible After Approval'
                AND (p.company IS NULL OR p.company = '' OR p.allowed_bank_account IS NULL OR p.allowed_bank_account = '' OR p.allowed_receivable_account IS NULL OR p.allowed_receivable_account = '' OR p.mapping_rule IS NULL OR p.mapping_rule = '') THEN 'Needs Mapping'
            WHEN p.posting_decision = 'Eligible After Approval' THEN 'Ready'
            WHEN p.posting_decision = 'Never Post Payment Entry' THEN 'Blocked By Design'
            ELSE 'Needs Review'
        END
    """
    having = ""
    if filters.get("readiness_status"):
        having = " HAVING readiness_status = %(readiness_status)s"
        params["readiness_status"] = filters.readiness_status

    columns = [
        {"fieldname": "policy", "label": _("Policy"), "fieldtype": "Link", "options": "NDIS PE Production Posting Policy", "width": 220},
        {"fieldname": "policy_id", "label": _("Policy ID"), "fieldtype": "Data", "width": 260},
        {"fieldname": "event_type", "label": _("Event Type"), "fieldtype": "Data", "width": 150},
        {"fieldname": "posting_decision", "label": _("Posting Decision"), "fieldtype": "Data", "width": 210},
        {"fieldname": "readiness_status", "label": _("Readiness Status"), "fieldtype": "Data", "width": 220},
        {"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 180},
        {"fieldname": "allowed_bank_account", "label": _("Bank Account"), "fieldtype": "Link", "options": "Account", "width": 220},
        {"fieldname": "allowed_receivable_account", "label": _("Receivable"), "fieldtype": "Link", "options": "Account", "width": 220},
        {"fieldname": "mapping_rule", "label": _("Mapping Rule"), "fieldtype": "Link", "options": "NDIS Payment Entry Mapping Rule", "width": 220},
        {"fieldname": "production_posting_enabled", "label": _("Live Enabled"), "fieldtype": "Check", "width": 100},
        {"fieldname": "allow_cross_company_posting", "label": _("Cross Company"), "fieldtype": "Check", "width": 110},
        {"fieldname": "allow_overpayment", "label": _("Overpayment"), "fieldtype": "Check", "width": 110},
        {"fieldname": "allow_negative_receipt", "label": _("Negative Receipt"), "fieldtype": "Check", "width": 130},
    ]
    data = frappe.db.sql(
        f"""
        SELECT p.name AS policy, p.policy_id, p.event_type, p.posting_decision, {readiness_case} AS readiness_status,
            p.company, p.allowed_bank_account, p.allowed_receivable_account, p.mapping_rule,
            p.production_posting_enabled, p.allow_cross_company_posting, p.allow_overpayment, p.allow_negative_receipt
        FROM `tabNDIS PE Production Posting Policy` p
        {build_where(conditions)}
        {having}
        ORDER BY p.policy_id ASC
        """,
        params,
        as_dict=True,
    )
    chart_map = {}
    for row in data:
        chart_map[row.readiness_status or "Unknown"] = chart_map.get(row.readiness_status or "Unknown", 0) + 1
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Policies", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Policies"), "datatype": "Int"},
        {"value": len([row for row in data if row.readiness_status == "Ready"]), "indicator": "Green", "label": _("Ready"), "datatype": "Int"},
        {"value": len([row for row in data if row.readiness_status == "Blocked By Design"]), "indicator": "Green", "label": _("Blocked By Design"), "datatype": "Int"},
        {"value": len([row for row in data if str(row.readiness_status).startswith("Blocked -")]), "indicator": "Red", "label": _("Critical Blocks"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
