import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


MAPPING_ACK = "I_CONFIRM_HARDEN_PE_PRODUCTION_ACCOUNT_MAPPING_NO_LIVE_POSTING"

POLICY_DOCTYPE = "NDIS PE Production Posting Policy"
GATE_DOCTYPE = "NDIS PE Production Account Mapping Gate"
GATE_ITEM_DOCTYPE = "NDIS PE Production Account Mapping Gate Item"


def make_gate_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-PE-ACCT-MAP-{timestamp}-{frappe.generate_hash(length=5).upper()}"


def safe_json(value):
    try:
        return json.dumps(value, indent=2, default=str)
    except Exception:
        return str(value)


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


def count_dt(doctype, filters=None):
    if not frappe.db.exists("DocType", doctype):
        return 0
    return frappe.db.count(doctype, filters or {})


def latest_doc(doctype, filters=None, fields=None, order_by="creation desc"):
    rows = frappe.get_all(doctype, filters=filters or {}, fields=fields or ["name"], order_by=order_by, limit=1)
    return rows[0] if rows else None


def get_company(company=None):
    if company and frappe.db.exists("Company", company):
        return company
    default_company = frappe.defaults.get_user_default("Company")
    if default_company and frappe.db.exists("Company", default_company):
        return default_company
    rows = frappe.get_all("Company", fields=["name"], order_by="creation asc", limit=1)
    if rows:
        return rows[0].name
    frappe.throw(_("No Company found."))


def get_account_doc(account):
    if not account or not frappe.db.exists("Account", account):
        frappe.throw(_("Account not found: {0}").format(account))
    return frappe.get_doc("Account", account)


def validate_account(account, company, expected_kind=None):
    doc = get_account_doc(account)
    if int(doc.is_group or 0):
        frappe.throw(_("Account is a group account: {0}").format(account))
    if getattr(doc, "disabled", 0):
        frappe.throw(_("Account is disabled: {0}").format(account))
    if doc.company != company:
        frappe.throw(_("Account {0} belongs to {1}, not {2}.").format(account, doc.company, company))
    if expected_kind in ["bank", "receivable"] and doc.root_type != "Asset":
        frappe.throw(_("Account must be Asset root type: {0}").format(account))
    if expected_kind == "receivable" and doc.account_type and doc.account_type != "Receivable":
        frappe.throw(_("Receivable account should have account_type Receivable: {0}").format(account))
    return doc


def find_account(company, root_type=None, account_type=None):
    filters = {"company": company, "is_group": 0, "disabled": 0}
    if root_type:
        filters["root_type"] = root_type
    if account_type:
        filters["account_type"] = account_type
    rows = frappe.get_all("Account", filters=filters, fields=["name"], order_by="lft asc", limit=1)
    return rows[0].name if rows else None


def resolve_bank_account(company, provided=None):
    if provided:
        validate_account(provided, company, expected_kind="bank")
        return provided
    for account_type in ["Bank", "Cash"]:
        account = find_account(company, root_type="Asset", account_type=account_type)
        if account:
            return account
    account = find_account(company, root_type="Asset")
    if account:
        return account
    frappe.throw(_("No non-group bank/cash/asset account found for company {0}.").format(company))


def resolve_receivable_account(company, provided=None):
    if provided:
        validate_account(provided, company, expected_kind="receivable")
        return provided
    account = find_account(company, root_type="Asset", account_type="Receivable")
    if account:
        return account
    frappe.throw(_("No non-group receivable account found for company {0}.").format(company))


def evaluate_config(items):
    sandbox_enabled = int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0)
    production_mode = int(frappe.conf.get("ndis_finance_production_mode") or 0)
    live_pe_enabled = int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0)

    add_item(items, "Pass" if sandbox_enabled else "Warning", "Low" if sandbox_enabled else "Medium", "Site Config", "sandbox_enabled", "Sandbox config", "Sandbox posting config is enabled." if sandbox_enabled else "Sandbox posting config is not enabled.")
    if production_mode:
        add_item(items, "Blocker", "Critical", "Site Config", "production_mode", "Production mode", "Production mode is enabled.", "Disable production mode before Phase 5B.")
    else:
        add_item(items, "Pass", "Low", "Site Config", "production_mode", "Production mode", "Production mode is disabled.")
    if live_pe_enabled:
        add_item(items, "Blocker", "Critical", "Site Config", "live_pe_posting", "Live Payment Entry posting config", "Live Payment Entry posting config is enabled.", "Disable live PE posting before Phase 5B.")
    else:
        add_item(items, "Pass", "Low", "Site Config", "live_pe_posting", "Live Payment Entry posting config", "Live Payment Entry posting config is disabled.")
    return sandbox_enabled, production_mode, live_pe_enabled


def evaluate_prior_gates(items):
    phase5a_approved = count_dt("NDIS PE Production Design Gate", {"design_approved_for_next_phase": 1, "live_posting_allowed": 0, "blocker_count": 0})
    phase4d_ready = count_dt("NDIS PE Sandbox Readiness Freeze", {"readiness_allowed": 1, "ready_for_next_design_phase": 1, "blocker_count": 0})
    latest_phase5a = latest_doc("NDIS PE Production Design Gate", {"design_approved_for_next_phase": 1, "live_posting_allowed": 0, "blocker_count": 0}, ["name", "gate_id"], "checked_on desc, creation desc")

    if phase5a_approved:
        add_item(items, "Pass", "Low", "Prior Gate", "phase5a_approved", "Phase 5A design gate", f"{phase5a_approved} approved Phase 5A design gate(s) found.", None, "NDIS PE Production Design Gate", latest_phase5a.name if latest_phase5a else None)
    else:
        add_item(items, "Blocker", "Critical", "Prior Gate", "phase5a_approved", "Phase 5A design gate", "No approved Phase 5A design gate found.", "Complete Phase 5A before Phase 5B.")
    if phase4d_ready:
        add_item(items, "Pass", "Low", "Prior Gate", "phase4d_ready", "Phase 4D readiness freeze", f"{phase4d_ready} ready Phase 4D freeze record(s) found.")
    else:
        add_item(items, "Blocker", "Critical", "Prior Gate", "phase4d_ready", "Phase 4D readiness freeze", "No ready Phase 4D freeze found.", "Complete Phase 4D before Phase 5B.")
    return {"phase5a_approved_gate_count": phase5a_approved, "phase4d_ready_freeze_count": phase4d_ready}


def evaluate_accounts(items, company, bank_account, receivable_account):
    bank_doc = validate_account(bank_account, company, expected_kind="bank")
    rec_doc = validate_account(receivable_account, company, expected_kind="receivable")
    add_item(items, "Pass", "Low", "Account Control", "bank_account_valid", "Allowed bank account", f"Allowed bank/paid-to account is valid: {bank_account}. Root type: {bank_doc.root_type}, account type: {bank_doc.account_type}.", None, "Account", bank_account)
    add_item(items, "Pass", "Low", "Account Control", "receivable_account_valid", "Allowed receivable account", f"Allowed receivable/paid-from account is valid: {receivable_account}. Root type: {rec_doc.root_type}, account type: {rec_doc.account_type}.", None, "Account", receivable_account)
    if bank_doc.company == rec_doc.company == company:
        add_item(items, "Pass", "Low", "Account Control", "company_alignment", "Company alignment", f"Company, bank account, and receivable account all align to {company}.")
    else:
        add_item(items, "Blocker", "Critical", "Account Control", "company_alignment", "Company alignment", "Company/account mismatch found.")
    if bank_doc.account_type not in ["Bank", "Cash"]:
        add_item(items, "Warning", "Medium", "Account Control", "bank_account_type", "Bank account type", f"Selected paid-to account type is {bank_doc.account_type or 'blank'}, not Bank/Cash.", "Before live activation, prefer a Bank or Cash account.", "Account", bank_account)
    return bank_doc, rec_doc


def get_eligible_policies():
    return frappe.get_all(
        POLICY_DOCTYPE,
        filters={"posting_decision": "Eligible After Approval", "event_type": ["in", ["Paid Claim", "Short Paid Claim"]]},
        fields=[
            "name",
            "policy_id",
            "policy_name",
            "policy_status",
            "event_type",
            "claim_outcome",
            "posting_decision",
            "posting_mode",
            "mapping_rule",
            "company",
            "allowed_bank_account",
            "allowed_receivable_account",
            "allow_cross_company_posting",
            "allow_overpayment",
            "allow_negative_receipt",
            "production_posting_enabled",
        ],
        order_by="policy_id asc",
        limit=1000,
    )


def evaluate_and_optionally_harden_policies(items, company, bank_account, receivable_account, apply_changes=0):
    all_policy_count = count_dt(POLICY_DOCTYPE)
    eligible_rows = get_eligible_policies()
    hardened_count = 0
    missing_account_count = 0

    for row in eligible_rows:
        mapping_ok = bool(row.mapping_rule and frappe.db.exists("NDIS Payment Entry Mapping Rule", row.mapping_rule))
        if mapping_ok:
            add_item(items, "Pass", "Low", "Policy Mapping", f"mapping_{row.policy_id}", f"Mapping rule for {row.policy_id}", f"Mapping rule exists: {row.mapping_rule}.", None, POLICY_DOCTYPE, row.name)
        else:
            add_item(items, "Blocker", "Critical", "Policy Mapping", f"mapping_{row.policy_id}", f"Mapping rule for {row.policy_id}", "Mapping rule is missing or does not exist.", "Fix mapping rule before production preview phase.", POLICY_DOCTYPE, row.name)

        if int(row.production_posting_enabled or 0):
            add_item(items, "Blocker", "Critical", "Policy Control", f"live_enabled_{row.policy_id}", f"Live posting disabled for {row.policy_id}", "production_posting_enabled is 1.", "Phase 5B must not enable live posting.", POLICY_DOCTYPE, row.name)
        else:
            add_item(items, "Pass", "Low", "Policy Control", f"live_disabled_{row.policy_id}", f"Live posting disabled for {row.policy_id}", "production_posting_enabled is 0.", None, POLICY_DOCTYPE, row.name)

        already_hardened = (
            row.company == company
            and row.allowed_bank_account == bank_account
            and row.allowed_receivable_account == receivable_account
            and not int(row.allow_cross_company_posting or 0)
            and not int(row.allow_overpayment or 0)
            and not int(row.allow_negative_receipt or 0)
        )

        if already_hardened:
            hardened_count += 1
            add_item(items, "Pass", "Low", "Policy Account Control", f"hardened_{row.policy_id}", f"Account controls for {row.policy_id}", "Policy already has company, bank account, receivable account, and safety flags hardened.", None, POLICY_DOCTYPE, row.name)
        elif apply_changes:
            doc = frappe.get_doc(POLICY_DOCTYPE, row.name)
            doc.company = company
            doc.allowed_bank_account = bank_account
            doc.allowed_receivable_account = receivable_account
            doc.allow_cross_company_posting = 0
            doc.allow_overpayment = 0
            doc.allow_negative_receipt = 0
            doc.production_posting_enabled = 0
            doc.last_reviewed_on = now_datetime()
            doc.last_reviewed_by = frappe.session.user
            doc.save(ignore_permissions=True)
            hardened_count += 1
            add_item(items, "Pass", "Low", "Policy Account Control", f"hardened_{row.policy_id}", f"Account controls for {row.policy_id}", "Policy account controls hardened and saved.", None, POLICY_DOCTYPE, row.name)
        else:
            missing_account_count += 1
            add_item(items, "Warning", "High", "Policy Account Control", f"missing_accounts_{row.policy_id}", f"Account controls for {row.policy_id}", "Policy does not yet have the selected production account controls.", "Run real Phase 5B hardening with acknowledgement to apply selected company/accounts.", POLICY_DOCTYPE, row.name)

    live_enabled_policy_count = count_dt(POLICY_DOCTYPE, {"production_posting_enabled": 1})
    cross_company_allowed_count = count_dt(POLICY_DOCTYPE, {"allow_cross_company_posting": 1})
    overpayment_allowed_count = count_dt(POLICY_DOCTYPE, {"allow_overpayment": 1})
    negative_receipt_allowed_count = count_dt(POLICY_DOCTYPE, {"allow_negative_receipt": 1})

    add_item(items, "Blocker" if live_enabled_policy_count else "Pass", "Critical" if live_enabled_policy_count else "Low", "Policy Control", "live_enabled_any", "Live-enabled policies", f"{live_enabled_policy_count} live-enabled policy record(s) found." if live_enabled_policy_count else "No production policy is live-enabled.")
    add_item(items, "Blocker" if cross_company_allowed_count else "Pass", "Critical" if cross_company_allowed_count else "Low", "Policy Control", "cross_company_allowed", "Cross-company posting flag", f"{cross_company_allowed_count} policy record(s) allow cross-company posting." if cross_company_allowed_count else "Cross-company posting is blocked on all policies.")
    add_item(items, "Blocker" if overpayment_allowed_count else "Pass", "Critical" if overpayment_allowed_count else "Low", "Policy Control", "overpayment_allowed", "Overpayment flag", f"{overpayment_allowed_count} policy record(s) allow overpayment." if overpayment_allowed_count else "Overpayment is blocked on all policies.")
    add_item(items, "Blocker" if negative_receipt_allowed_count else "Pass", "Critical" if negative_receipt_allowed_count else "Low", "Policy Control", "negative_receipt_allowed", "Negative receipt flag", f"{negative_receipt_allowed_count} policy record(s) allow negative receipt." if negative_receipt_allowed_count else "Negative receipt is blocked on all policies.")

    return {
        "policy_count": all_policy_count,
        "eligible_policy_count": len(eligible_rows),
        "hardened_policy_count": hardened_count,
        "missing_account_policy_count": missing_account_count,
        "live_enabled_policy_count": live_enabled_policy_count,
        "cross_company_allowed_count": cross_company_allowed_count,
        "overpayment_allowed_count": overpayment_allowed_count,
        "negative_receipt_allowed_count": negative_receipt_allowed_count,
    }


def evaluate_block_policies(items):
    checks = [
        ("Rejected Claim", "rejected_block", "Rejected claim block"),
        ("Write Off", "writeoff_block", "Write-off block"),
        ("Cancelled Claim", "cancelled_block", "Cancelled claim block"),
    ]
    for event_type, key, label in checks:
        ok = count_dt(POLICY_DOCTYPE, {"event_type": event_type, "posting_decision": "Never Post Payment Entry", "production_posting_enabled": 0})
        add_item(items, "Pass" if ok else "Blocker", "Low" if ok else "Critical", "Block Policy", key, label, f"{label} policy blocks Payment Entry." if ok else f"{label} policy missing.")


def evaluate_guardrails(items):
    submitted_pe_today = count_dt("Payment Entry", {"creation": [">=", today()], "docstatus": 1})
    pe_gl_count = count_dt("GL Entry", {"voucher_type": "Payment Entry"}) if frappe.db.exists("DocType", "GL Entry") else 0
    pe_gl_today = count_dt("GL Entry", {"creation": [">=", today()], "voucher_type": "Payment Entry"}) if frappe.db.exists("DocType", "GL Entry") else 0
    submitted_je_today = count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}) if frappe.db.exists("DocType", "Journal Entry") else 0
    purchase_invoice_today = count_dt("Purchase Invoice", {"creation": [">=", today()]}) if frappe.db.exists("DocType", "Purchase Invoice") else 0

    checks = [
        (submitted_pe_today, "submitted_pe_today", "Submitted Payment Entries today", "submitted Payment Entry record(s) today.", "No submitted Payment Entry today."),
        (pe_gl_count, "pe_gl_count", "Payment Entry GL count", "Payment Entry GL record(s) found.", "No Payment Entry GL exists."),
        (pe_gl_today, "pe_gl_today", "Payment Entry GL today", "Payment Entry GL record(s) today.", "No Payment Entry GL today."),
        (submitted_je_today, "submitted_je_today", "Submitted Journal Entries today", "submitted Journal Entry record(s) today.", "No submitted Journal Entry today."),
        (purchase_invoice_today, "purchase_invoice_today", "Purchase Invoices today", "Purchase Invoice record(s) today.", "No Purchase Invoice today."),
    ]
    for count, key, label, fail_detail, pass_detail in checks:
        if count:
            add_item(items, "Blocker", "Critical", "Guardrail", key, label, f"{count} {fail_detail}")
        else:
            add_item(items, "Pass", "Low", "Guardrail", key, label, pass_detail)

    return {
        "submitted_payment_entry_count_today": submitted_pe_today,
        "payment_entry_gl_count": pe_gl_count,
        "payment_entry_gl_count_today": pe_gl_today,
        "submitted_journal_entry_count_today": submitted_je_today,
        "purchase_invoice_count_today": purchase_invoice_today,
    }


def summarise_items(items):
    return {
        "blocker_count": len([item for item in items if item["status"] == "Blocker"]),
        "warning_count": len([item for item in items if item["status"] == "Warning"]),
        "pass_count": len([item for item in items if item["status"] == "Pass"]),
        "info_count": len([item for item in items if item["status"] == "Info"]),
        "item_count": len(items),
    }


def calculate_score(blockers, warnings):
    score = 100 - (int(blockers or 0) * 25) - (int(warnings or 0) * 5)
    return max(0, round(score, 2))


def hardening_status(score, blockers, warnings):
    if blockers:
        return "Blocked"
    if warnings:
        return "Ready With Warnings"
    if score >= 95:
        return "Ready For Production Posting Preview"
    return "Needs Review"


@frappe.whitelist()
def run_pe_production_account_mapping_hardening(
    company=None,
    allowed_bank_account=None,
    allowed_receivable_account=None,
    acknowledgement=None,
    dry_run=1,
    notes=None,
):
    assert_action("run_pe_production_account_mapping_hardening")
    items = []

    sandbox_enabled, production_mode, live_pe_enabled = evaluate_config(items)
    prior = evaluate_prior_gates(items)

    company = get_company(company)
    allowed_bank_account = resolve_bank_account(company, allowed_bank_account)
    allowed_receivable_account = resolve_receivable_account(company, allowed_receivable_account)
    bank_doc, rec_doc = evaluate_accounts(items, company, allowed_bank_account, allowed_receivable_account)

    ack_ok = acknowledgement == MAPPING_ACK
    apply_changes = int(not int(dry_run or 0) and ack_ok)
    policy_results = evaluate_and_optionally_harden_policies(items, company, allowed_bank_account, allowed_receivable_account, apply_changes=apply_changes)
    evaluate_block_policies(items)
    guardrails = evaluate_guardrails(items)

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "mapping_ack", "Account mapping acknowledgement", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "mapping_ack", "Account mapping acknowledgement", f"Required acknowledgement not supplied. Required: {MAPPING_ACK}", "Provide exact acknowledgement to apply policy account hardening.")

    summary = summarise_items(items)
    score = calculate_score(summary["blocker_count"], summary["warning_count"])
    final_hardening_status = hardening_status(score, summary["blocker_count"], summary["warning_count"])
    account_mapping_hardened = int(summary["blocker_count"] == 0 and ack_ok and policy_results["missing_account_policy_count"] == 0)
    ready_for_preview_phase = int(summary["blocker_count"] == 0 and ack_ok)
    live_posting_allowed = 0

    if summary["blocker_count"]:
        status = "Blocked"
    elif not ack_ok or summary["warning_count"]:
        status = "Needs Review"
    else:
        status = "Hardened"

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": status,
        "account_mapping_hardened": account_mapping_hardened,
        "ready_for_preview_phase": ready_for_preview_phase,
        "live_posting_allowed": live_posting_allowed,
        "company": company,
        "allowed_bank_account": allowed_bank_account,
        "allowed_receivable_account": allowed_receivable_account,
        "bank_account_type": bank_doc.account_type,
        "receivable_account_type": rec_doc.account_type,
        "hardening_score": score,
        "hardening_status": final_hardening_status,
        "required_acknowledgement": MAPPING_ACK,
        "acknowledgement_ok": ack_ok,
        "summary": summary,
        "prior": prior,
        "policy_results": policy_results,
        "guardrails": guardrails,
        "items": items,
        "note": "Account mapping hardening only. Live posting remains blocked and no accounting/payment records are created.",
    }

    if int(dry_run or 0):
        return result

    doc = frappe.new_doc(GATE_DOCTYPE)
    doc.gate_id = make_gate_id()
    doc.status = status
    doc.gate_type = "Production Account Mapping Hardening"
    doc.account_mapping_hardened = account_mapping_hardened
    doc.ready_for_preview_phase = ready_for_preview_phase
    doc.live_posting_allowed = live_posting_allowed
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = sandbox_enabled
    doc.production_mode_detected = production_mode
    doc.live_payment_entry_posting_config = live_pe_enabled
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.company = company
    doc.allowed_bank_account = allowed_bank_account
    doc.allowed_receivable_account = allowed_receivable_account
    doc.bank_account_type = bank_doc.account_type
    doc.receivable_account_type = rec_doc.account_type
    doc.hardening_score = score
    doc.hardening_status = final_hardening_status
    doc.blocker_count = summary["blocker_count"]
    doc.warning_count = summary["warning_count"]
    doc.pass_count = summary["pass_count"]
    doc.info_count = summary["info_count"]
    doc.item_count = summary["item_count"]

    for fieldname, value in policy_results.items():
        setattr(doc, fieldname, value)
    for fieldname, value in prior.items():
        setattr(doc, fieldname, value)
    for fieldname, value in guardrails.items():
        setattr(doc, fieldname, value)

    doc.required_acknowledgement = MAPPING_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    for item in items:
        row = frappe.new_doc(GATE_ITEM_DOCTYPE)
        row.mapping_gate = doc.name
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

    frappe.db.commit()
    result["created"] = True
    result["mapping_gate"] = doc.name
    result["gate_id"] = doc.gate_id
    return result


@frappe.whitelist()
def cancel_pe_production_account_mapping_gate(mapping_gate, reason=None):
    assert_action("cancel_pe_production_account_mapping_gate")
    if not frappe.db.exists(GATE_DOCTYPE, mapping_gate):
        frappe.throw(_("PE Production Account Mapping Gate not found: {0}").format(mapping_gate))
    frappe.db.set_value(
        GATE_DOCTYPE,
        mapping_gate,
        {
            "status": "Cancelled",
            "account_mapping_hardened": 0,
            "ready_for_preview_phase": 0,
            "live_posting_allowed": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Production Payment Entry account mapping gate cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{GATE_ITEM_DOCTYPE}` SET status = 'Cancelled' WHERE mapping_gate = %(mapping_gate)s", {"mapping_gate": mapping_gate})
    frappe.db.commit()
    return {"mapping_gate": mapping_gate, "status": "Cancelled", "note": "Mapping gate cancelled only. No accounting/payment records were changed."}


@frappe.whitelist()
def quick_pe_production_account_mapping_summary(limit=20):
    gates = frappe.get_all(
        GATE_DOCTYPE,
        fields=[
            "name",
            "gate_id",
            "status",
            "account_mapping_hardened",
            "ready_for_preview_phase",
            "live_posting_allowed",
            "company",
            "allowed_bank_account",
            "allowed_receivable_account",
            "hardening_score",
            "hardening_status",
            "blocker_count",
            "warning_count",
            "hardened_policy_count",
            "missing_account_policy_count",
            "live_enabled_policy_count",
            "payment_entry_gl_count",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    policies = frappe.get_all(
        POLICY_DOCTYPE,
        fields=[
            "name",
            "policy_id",
            "policy_name",
            "policy_status",
            "event_type",
            "posting_decision",
            "production_posting_enabled",
            "company",
            "allowed_bank_account",
            "allowed_receivable_account",
            "allow_cross_company_posting",
            "allow_overpayment",
            "allow_negative_receipt",
        ],
        order_by="policy_id asc",
        limit=100,
    )
    items = frappe.get_all(
        GATE_ITEM_DOCTYPE,
        fields=["name", "mapping_gate", "status", "severity", "category", "check_label", "detail", "recommendation", "source_doctype", "source_name"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {"gates": gates, "policies": policies, "items": items, "required_acknowledgement": MAPPING_ACK, "note": "Production PE account mapping summary only. Live posting remains blocked."}


def execute_mapping_gate_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("status"):
        conditions.append("g.status = %(status)s")
        params["status"] = filters.status
    if filters.get("hardening_status"):
        conditions.append("g.hardening_status = %(hardening_status)s")
        params["hardening_status"] = filters.hardening_status
    if filters.get("from_date"):
        conditions.append("DATE(g.checked_on) >= %(from_date)s")
        params["from_date"] = filters.from_date
    if filters.get("to_date"):
        conditions.append("DATE(g.checked_on) <= %(to_date)s")
        params["to_date"] = filters.to_date

    columns = [
        {"fieldname": "mapping_gate", "label": _("Mapping Gate"), "fieldtype": "Link", "options": GATE_DOCTYPE, "width": 220},
        {"fieldname": "gate_id", "label": _("Gate ID"), "fieldtype": "Data", "width": 320},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "account_mapping_hardened", "label": _("Hardened"), "fieldtype": "Check", "width": 90},
        {"fieldname": "ready_for_preview_phase", "label": _("Preview Ready"), "fieldtype": "Check", "width": 110},
        {"fieldname": "live_posting_allowed", "label": _("Live Allowed"), "fieldtype": "Check", "width": 100},
        {"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 170},
        {"fieldname": "allowed_bank_account", "label": _("Bank Account"), "fieldtype": "Link", "options": "Account", "width": 210},
        {"fieldname": "allowed_receivable_account", "label": _("Receivable"), "fieldtype": "Link", "options": "Account", "width": 210},
        {"fieldname": "hardening_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "hardening_status", "label": _("Hardening Status"), "fieldtype": "Data", "width": 230},
        {"fieldname": "hardened_policy_count", "label": _("Hardened Policies"), "fieldtype": "Int", "width": 130},
        {"fieldname": "missing_account_policy_count", "label": _("Missing Accounts"), "fieldtype": "Int", "width": 130},
        {"fieldname": "blocker_count", "label": _("Blockers"), "fieldtype": "Int", "width": 90},
        {"fieldname": "warning_count", "label": _("Warnings"), "fieldtype": "Int", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]
    data = frappe.db.sql(
        f"""
        SELECT g.name AS mapping_gate, g.gate_id, g.status, g.account_mapping_hardened,
            g.ready_for_preview_phase, g.live_posting_allowed, g.company,
            g.allowed_bank_account, g.allowed_receivable_account, g.hardening_score,
            g.hardening_status, g.hardened_policy_count, g.missing_account_policy_count,
            g.blocker_count, g.warning_count, g.checked_on
        FROM `tab{GATE_DOCTYPE}` g
        {build_where(conditions)}
        ORDER BY g.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {"data": {"labels": [row.gate_id for row in data[:20]], "datasets": [{"name": "Score", "values": [flt(row.hardening_score) for row in data[:20]]}, {"name": "Blockers", "values": [int(row.blocker_count or 0) for row in data[:20]]}, {"name": "Warnings", "values": [int(row.warning_count or 0) for row in data[:20]]}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Mapping Gates"), "datatype": "Int"},
        {"value": len([row for row in data if row.account_mapping_hardened]), "indicator": "Green", "label": _("Hardened"), "datatype": "Int"},
        {"value": len([row for row in data if row.ready_for_preview_phase]), "indicator": "Green", "label": _("Preview Ready"), "datatype": "Int"},
        {"value": len([row for row in data if row.live_posting_allowed]), "indicator": "Red", "label": _("Live Allowed"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_mapping_exception_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    for fieldname in ["mapping_gate", "status", "severity", "category"]:
        if filters.get(fieldname):
            conditions.append(f"i.{fieldname} = %({fieldname})s")
            params[fieldname] = filters.get(fieldname)
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": GATE_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "mapping_gate", "label": _("Mapping Gate"), "fieldtype": "Link", "options": GATE_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 180},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 300},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 430},
        {"fieldname": "recommendation", "label": _("Recommendation"), "fieldtype": "Small Text", "width": 430},
        {"fieldname": "source_doctype", "label": _("Source DocType"), "fieldtype": "Data", "width": 180},
        {"fieldname": "source_name", "label": _("Source Name"), "fieldtype": "Data", "width": 220},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]
    data = frappe.db.sql(
        f"""
        SELECT i.name AS item, i.mapping_gate, i.status, i.severity, i.category,
            i.check_label, i.detail, i.recommendation, i.source_doctype,
            i.source_name, i.checked_on
        FROM `tab{GATE_ITEM_DOCTYPE}` i
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


def execute_mapping_control_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("event_type"):
        conditions.append("p.event_type = %(event_type)s")
        params["event_type"] = filters.event_type
    if filters.get("policy_status"):
        conditions.append("p.policy_status = %(policy_status)s")
        params["policy_status"] = filters.policy_status
    if filters.get("missing_accounts_only"):
        conditions.append("(p.allowed_bank_account IS NULL OR p.allowed_bank_account = '' OR p.allowed_receivable_account IS NULL OR p.allowed_receivable_account = '')")
    columns = [
        {"fieldname": "policy", "label": _("Policy"), "fieldtype": "Link", "options": POLICY_DOCTYPE, "width": 220},
        {"fieldname": "policy_id", "label": _("Policy ID"), "fieldtype": "Data", "width": 260},
        {"fieldname": "policy_status", "label": _("Status"), "fieldtype": "Data", "width": 130},
        {"fieldname": "event_type", "label": _("Event Type"), "fieldtype": "Data", "width": 150},
        {"fieldname": "posting_decision", "label": _("Posting Decision"), "fieldtype": "Data", "width": 210},
        {"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 170},
        {"fieldname": "allowed_bank_account", "label": _("Bank Account"), "fieldtype": "Link", "options": "Account", "width": 210},
        {"fieldname": "allowed_receivable_account", "label": _("Receivable"), "fieldtype": "Link", "options": "Account", "width": 210},
        {"fieldname": "mapping_rule", "label": _("Mapping Rule"), "fieldtype": "Link", "options": "NDIS Payment Entry Mapping Rule", "width": 210},
        {"fieldname": "production_posting_enabled", "label": _("Live Enabled"), "fieldtype": "Check", "width": 100},
        {"fieldname": "allow_cross_company_posting", "label": _("Cross Company"), "fieldtype": "Check", "width": 110},
        {"fieldname": "allow_overpayment", "label": _("Overpayment"), "fieldtype": "Check", "width": 110},
        {"fieldname": "allow_negative_receipt", "label": _("Negative Receipt"), "fieldtype": "Check", "width": 130},
        {"fieldname": "control_status", "label": _("Control Status"), "fieldtype": "Data", "width": 220},
    ]
    data = frappe.db.sql(
        f"""
        SELECT p.name AS policy, p.policy_id, p.policy_status, p.event_type,
            p.posting_decision, p.company, p.allowed_bank_account,
            p.allowed_receivable_account, p.mapping_rule, p.production_posting_enabled,
            p.allow_cross_company_posting, p.allow_overpayment, p.allow_negative_receipt,
            CASE
                WHEN p.production_posting_enabled = 1 THEN 'Critical - Live Enabled'
                WHEN p.allow_cross_company_posting = 1 THEN 'Critical - Cross-company Allowed'
                WHEN p.allow_overpayment = 1 THEN 'Critical - Overpayment Allowed'
                WHEN p.allow_negative_receipt = 1 THEN 'Critical - Negative Receipt Allowed'
                WHEN p.posting_decision = 'Eligible After Approval'
                    AND (p.allowed_bank_account IS NULL OR p.allowed_bank_account = '' OR p.allowed_receivable_account IS NULL OR p.allowed_receivable_account = '') THEN 'Needs Account Mapping'
                WHEN p.posting_decision = 'Eligible After Approval' THEN 'Hardened'
                ELSE 'Blocked / No Posting'
            END AS control_status
        FROM `tab{POLICY_DOCTYPE}` p
        {build_where(conditions)}
        ORDER BY p.policy_id ASC
        """,
        params,
        as_dict=True,
    )
    chart_map = {}
    for row in data:
        chart_map[row.control_status or "Unknown"] = chart_map.get(row.control_status or "Unknown", 0) + 1
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Policies", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Policies"), "datatype": "Int"},
        {"value": len([row for row in data if row.control_status == "Hardened"]), "indicator": "Green", "label": _("Hardened"), "datatype": "Int"},
        {"value": len([row for row in data if row.control_status == "Needs Account Mapping"]), "indicator": "Orange", "label": _("Needs Mapping"), "datatype": "Int"},
        {"value": len([row for row in data if "Critical" in str(row.control_status)]), "indicator": "Red", "label": _("Critical"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
