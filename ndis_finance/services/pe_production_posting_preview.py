import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


PREVIEW_ACK = "I_CONFIRM_RUN_PE_PRODUCTION_POSTING_PREVIEW_NO_LIVE_POSTING"

POLICY_DOCTYPE = "NDIS PE Production Posting Policy"
PREVIEW_DOCTYPE = "NDIS PE Production Posting Preview"
LINE_DOCTYPE = "NDIS PE Production Posting Preview Line"


def make_preview_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-PE-PROD-PREVIEW-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def get_policy(event_type):
    rows = frappe.get_all(
        POLICY_DOCTYPE,
        filters={"event_type": event_type},
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
        order_by="creation asc",
        limit=1,
    )
    return rows[0] if rows else None


def get_hardened_context():
    gate = latest_doc(
        "NDIS PE Production Account Mapping Gate",
        {"account_mapping_hardened": 1, "ready_for_preview_phase": 1, "live_posting_allowed": 0, "blocker_count": 0},
        ["name", "gate_id", "company", "allowed_bank_account", "allowed_receivable_account", "hardening_score", "hardening_status"],
        "checked_on desc, creation desc",
    )
    if not gate:
        frappe.throw(_("No hardened Phase 5B production account mapping gate found."))
    return gate


def get_design_gate():
    return latest_doc(
        "NDIS PE Production Design Gate",
        {"design_approved_for_next_phase": 1, "live_posting_allowed": 0, "blocker_count": 0},
        ["name", "gate_id"],
        "checked_on desc, creation desc",
    )


def evaluate_config():
    return {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def strict_config_errors(config):
    errors = []
    if int(config["production_mode"]):
        errors.append("Production mode config is enabled. Phase 5C preview must not run in production mode.")
    if int(config["live_pe_enabled"]):
        errors.append("Live Payment Entry posting config is enabled. Phase 5C preview requires it to be disabled.")
    return errors


def guardrails():
    return {
        "payment_entry_count": count_dt("Payment Entry"),
        "submitted_payment_entry_count_today": count_dt("Payment Entry", {"creation": [">=", today()], "docstatus": 1}),
        "payment_entry_gl_count": count_dt("GL Entry", {"voucher_type": "Payment Entry"}) if frappe.db.exists("DocType", "GL Entry") else 0,
        "payment_entry_gl_count_today": count_dt("GL Entry", {"creation": [">=", today()], "voucher_type": "Payment Entry"}) if frappe.db.exists("DocType", "GL Entry") else 0,
        "submitted_journal_entry_count_today": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}) if frappe.db.exists("DocType", "Journal Entry") else 0,
        "purchase_invoice_count_today": count_dt("Purchase Invoice", {"creation": [">=", today()]}) if frappe.db.exists("DocType", "Purchase Invoice") else 0,
    }


def prior_gate_counts():
    return {
        "phase5b_hardened_gate_count": count_dt("NDIS PE Production Account Mapping Gate", {"account_mapping_hardened": 1, "ready_for_preview_phase": 1, "live_posting_allowed": 0, "blocker_count": 0}),
        "phase5a_approved_gate_count": count_dt("NDIS PE Production Design Gate", {"design_approved_for_next_phase": 1, "live_posting_allowed": 0, "blocker_count": 0}),
        "phase4d_ready_freeze_count": count_dt("NDIS PE Sandbox Readiness Freeze", {"readiness_allowed": 1, "ready_for_next_design_phase": 1, "blocker_count": 0}),
    }


def make_control_scenarios(context):
    company = context.company
    return [
        {"scenario_key": "PHASE5C-PAID-001", "event_type": "Paid Claim", "claim_outcome": "Paid", "source_reference": "PHASE5C-PAID-001", "source_company": company, "invoice_amount": 100, "paid_amount": 100, "participant_reference": "PHASE5C-PARTICIPANT-A"},
        {"scenario_key": "PHASE5C-SHORT-PAID-001", "event_type": "Short Paid Claim", "claim_outcome": "Short Paid", "source_reference": "PHASE5C-SHORT-PAID-001", "source_company": company, "invoice_amount": 100, "paid_amount": 80, "participant_reference": "PHASE5C-PARTICIPANT-B"},
        {"scenario_key": "PHASE5C-REJECTED-001", "event_type": "Rejected Claim", "claim_outcome": "Rejected", "source_reference": "PHASE5C-REJECTED-001", "source_company": company, "invoice_amount": 100, "paid_amount": 0, "participant_reference": "PHASE5C-PARTICIPANT-C"},
        {"scenario_key": "PHASE5C-DUPLICATE-001", "event_type": "Paid Claim", "claim_outcome": "Paid", "source_reference": "PHASE5C-PAID-001", "source_company": company, "invoice_amount": 100, "paid_amount": 100, "participant_reference": "PHASE5C-PARTICIPANT-A-DUP"},
        {"scenario_key": "PHASE5C-OVERPAYMENT-001", "event_type": "Paid Claim", "claim_outcome": "Paid", "source_reference": "PHASE5C-OVERPAYMENT-001", "source_company": company, "invoice_amount": 100, "paid_amount": 120, "participant_reference": "PHASE5C-PARTICIPANT-D"},
        {"scenario_key": "PHASE5C-NEGATIVE-001", "event_type": "Paid Claim", "claim_outcome": "Paid", "source_reference": "PHASE5C-NEGATIVE-001", "source_company": company, "invoice_amount": 100, "paid_amount": -10, "participant_reference": "PHASE5C-PARTICIPANT-E"},
        {"scenario_key": "PHASE5C-CROSS-COMPANY-001", "event_type": "Paid Claim", "claim_outcome": "Paid", "source_reference": "PHASE5C-CROSS-COMPANY-001", "source_company": "__PHASE5C_OTHER_COMPANY__", "invoice_amount": 100, "paid_amount": 100, "participant_reference": "PHASE5C-PARTICIPANT-F"},
    ]


def policy_for_scenario(scenario):
    return get_policy(scenario["event_type"])


def existing_duplicate_key_count(duplicate_key):
    if not duplicate_key:
        return 0
    return frappe.db.sql(
        f"""
        SELECT COUNT(*)
        FROM `tab{LINE_DOCTYPE}` l
        INNER JOIN `tab{PREVIEW_DOCTYPE}` p ON p.name = l.posting_preview
        WHERE l.duplicate_key = %(duplicate_key)s
        AND l.status = 'Preview Eligible'
        AND p.status = 'Previewed'
        """,
        {"duplicate_key": duplicate_key},
    )[0][0]


def evaluate_scenario(scenario, seen_keys):
    policy = policy_for_scenario(scenario)
    reasons = []
    flags = {
        "duplicate_detected": 0,
        "cross_company_blocked": 0,
        "overpayment_blocked": 0,
        "negative_receipt_blocked": 0,
        "rejected_claim_blocked": 0,
    }
    invoice_amount = flt(scenario.get("invoice_amount"))
    paid_amount = flt(scenario.get("paid_amount"))
    shortfall_amount = max(0, invoice_amount - max(paid_amount, 0))
    overpayment_amount = max(0, paid_amount - invoice_amount)
    duplicate_key = f"{scenario.get('source_reference')}|{scenario.get('event_type')}|{scenario.get('claim_outcome')}"

    if duplicate_key in seen_keys or existing_duplicate_key_count(duplicate_key):
        flags["duplicate_detected"] = 1
        reasons.append("Duplicate preview key detected.")
    seen_keys.add(duplicate_key)

    if not policy:
        reasons.append(f"No production posting policy found for event type {scenario.get('event_type')}.")
    if paid_amount < 0:
        flags["negative_receipt_blocked"] = 1
        reasons.append("Negative receipt amount is blocked.")
    if paid_amount > invoice_amount:
        flags["overpayment_blocked"] = 1
        reasons.append("Overpayment amount is blocked.")
    if policy:
        if int(policy.production_posting_enabled or 0):
            reasons.append("Policy has production_posting_enabled = 1; Phase 5C expects live posting disabled.")
        if policy.posting_decision == "Never Post Payment Entry":
            if scenario.get("event_type") == "Rejected Claim":
                flags["rejected_claim_blocked"] = 1
                reasons.append("Rejected claim correctly blocks Payment Entry preview.")
            else:
                reasons.append("Policy says never post Payment Entry.")
        if scenario.get("source_company") != policy.company:
            flags["cross_company_blocked"] = 1
            reasons.append("Source company does not match policy company. Cross-company posting is blocked.")
        if int(policy.allow_cross_company_posting or 0):
            reasons.append("Policy allows cross-company posting; expected blocked.")
        if int(policy.allow_overpayment or 0):
            reasons.append("Policy allows overpayment; expected blocked.")
        if int(policy.allow_negative_receipt or 0):
            reasons.append("Policy allows negative receipt; expected blocked.")
        if policy.posting_decision == "Eligible After Approval":
            if not policy.company or not policy.allowed_bank_account or not policy.allowed_receivable_account:
                reasons.append("Eligible policy is missing company/bank/receivable account control.")
            if not policy.mapping_rule:
                reasons.append("Eligible policy is missing mapping rule.")

    expected_block = any(flags.values())
    if reasons:
        if expected_block:
            status = "Duplicate" if flags["duplicate_detected"] else "Blocked"
            severity = "Low" if flags["rejected_claim_blocked"] else "Medium"
        else:
            status = "Blocked"
            severity = "Critical"
    else:
        status = "Preview Eligible"
        severity = "Low"

    would_create_payment_entry = int(status == "Preview Eligible")
    preview_payment_amount = paid_amount if would_create_payment_entry else 0
    return {
        "status": status,
        "severity": severity,
        "scenario_key": scenario["scenario_key"],
        "event_type": scenario["event_type"],
        "claim_outcome": scenario["claim_outcome"],
        "source_reference": scenario["source_reference"],
        "source_company": scenario["source_company"],
        "participant_reference": scenario.get("participant_reference"),
        "posting_policy": policy.name if policy else None,
        "posting_decision": policy.posting_decision if policy else None,
        "mapping_rule": policy.mapping_rule if policy else None,
        "policy_company": policy.company if policy else None,
        "allowed_bank_account": policy.allowed_bank_account if policy else None,
        "allowed_receivable_account": policy.allowed_receivable_account if policy else None,
        "invoice_amount": invoice_amount,
        "paid_amount": paid_amount,
        "preview_payment_amount": preview_payment_amount,
        "shortfall_amount": shortfall_amount if would_create_payment_entry else 0,
        "overpayment_amount": overpayment_amount,
        "would_create_payment_entry": would_create_payment_entry,
        "actual_payment_entry_created": 0,
        "duplicate_key": duplicate_key,
        "block_reason": "; ".join(reasons),
        "preview_note": preview_note(status, flags, paid_amount, shortfall_amount),
        **flags,
    }


def preview_note(status, flags, paid_amount, shortfall_amount):
    if status == "Preview Eligible":
        if shortfall_amount:
            return f"Would preview partial receipt of {flt(paid_amount):.2f}; shortfall preserved."
        return f"Would preview receipt of {flt(paid_amount):.2f}."
    if flags.get("rejected_claim_blocked"):
        return "Rejected claim blocked as designed. No Payment Entry preview allowed."
    if flags.get("duplicate_detected"):
        return "Duplicate prevented by preview duplicate key."
    if flags.get("overpayment_blocked"):
        return "Overpayment blocked."
    if flags.get("negative_receipt_blocked"):
        return "Negative receipt blocked."
    if flags.get("cross_company_blocked"):
        return "Cross-company posting blocked."
    return "Preview blocked."


def summarise_lines(lines):
    eligible = [line for line in lines if line["status"] == "Preview Eligible"]
    blocked = [line for line in lines if line["status"] == "Blocked"]
    duplicate = [line for line in lines if line["status"] == "Duplicate"]
    warnings = [line for line in lines if line["status"] == "Warning"]
    blockers_for_score = [
        line
        for line in blocked
        if not (line.get("rejected_claim_blocked") or line.get("overpayment_blocked") or line.get("negative_receipt_blocked") or line.get("cross_company_blocked"))
    ]
    expected_blocks = [line for line in lines if line.get("rejected_claim_blocked") or line.get("overpayment_blocked") or line.get("negative_receipt_blocked") or line.get("cross_company_blocked") or line.get("duplicate_detected")]
    return {
        "eligible_line_count": len(eligible),
        "blocked_line_count": len(blocked),
        "duplicate_line_count": len(duplicate),
        "paid_line_count": len([line for line in lines if line["claim_outcome"] == "Paid"]),
        "short_paid_line_count": len([line for line in lines if line["claim_outcome"] == "Short Paid"]),
        "rejected_line_count": len([line for line in lines if line["claim_outcome"] == "Rejected"]),
        "preview_total_amount": sum(flt(line["preview_payment_amount"]) for line in eligible),
        "shortfall_total_amount": sum(flt(line["shortfall_amount"]) for line in eligible),
        "line_count": len(lines),
        "pass_count": len(eligible) + len(expected_blocks),
        "warning_count": len(warnings),
        "blocker_count": len(blockers_for_score),
        "info_count": len([line for line in lines if line["status"] == "Info"]),
    }


def calculate_score(blockers, warnings):
    return max(0, round(100 - (int(blockers or 0) * 25) - (int(warnings or 0) * 5), 2))


def preview_status(score, blockers, warnings):
    if blockers:
        return "Blocked"
    if warnings:
        return "Ready With Warnings"
    if score >= 95:
        return "Ready For Controlled Live Adapter Design"
    return "Needs Review"


def create_preview_doc(context, design_gate, config, prior, guard_before, acknowledgement, result, notes):
    doc = frappe.new_doc(PREVIEW_DOCTYPE)
    doc.preview_id = make_preview_id()
    doc.status = result["status"]
    doc.preview_type = "Production Control Scenario Preview"
    doc.source_mode = "Synthetic Control Scenarios"
    doc.live_posting_allowed = 0
    doc.payment_entry_created = 0
    doc.company = context.company
    doc.allowed_bank_account = context.allowed_bank_account
    doc.allowed_receivable_account = context.allowed_receivable_account
    doc.mapping_gate = context.name
    doc.design_gate = design_gate.name if design_gate else None
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.previewed_on = now_datetime()
    doc.previewed_by = frappe.session.user
    doc.preview_score = result["preview_score"]
    doc.preview_status = result["preview_status"]
    for fieldname in ["blocker_count", "warning_count", "pass_count", "info_count", "line_count"]:
        setattr(doc, fieldname, result["summary"][fieldname])
    for fieldname in ["eligible_line_count", "blocked_line_count", "duplicate_line_count", "paid_line_count", "short_paid_line_count", "rejected_line_count", "preview_total_amount", "shortfall_total_amount"]:
        setattr(doc, fieldname, result["summary"][fieldname])
    for fieldname, value in prior.items():
        setattr(doc, fieldname, value)
    doc.payment_entry_count_before = guard_before["payment_entry_count"]
    doc.payment_entry_count_after = count_dt("Payment Entry")
    doc.submitted_payment_entry_count_today = guard_before["submitted_payment_entry_count_today"]
    doc.payment_entry_gl_count = guard_before["payment_entry_gl_count"]
    doc.payment_entry_gl_count_today = guard_before["payment_entry_gl_count_today"]
    doc.submitted_journal_entry_count_today = guard_before["submitted_journal_entry_count_today"]
    doc.purchase_invoice_count_today = guard_before["purchase_invoice_count_today"]
    doc.required_acknowledgement = PREVIEW_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(acknowledgement == PREVIEW_ACK)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    return doc


def save_lines(preview_doc, lines):
    for line in lines:
        row = frappe.new_doc(LINE_DOCTYPE)
        row.posting_preview = preview_doc.name
        for fieldname, value in line.items():
            if row.meta.has_field(fieldname):
                setattr(row, fieldname, value)
        row.checked_on = preview_doc.previewed_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_pe_production_posting_preview(acknowledgement=None, dry_run=1, notes=None):
    assert_action("run_pe_production_posting_preview")
    config = evaluate_config()
    config_errors = strict_config_errors(config)
    context = get_hardened_context()
    design_gate = get_design_gate()
    prior = prior_gate_counts()
    guard_before = guardrails()
    seen_keys = set()
    lines = [evaluate_scenario(scenario, seen_keys) for scenario in make_control_scenarios(context)]
    summary = summarise_lines(lines)
    summary["blocker_count"] += len(config_errors)
    for key in ["phase5b_hardened_gate_count", "phase5a_approved_gate_count", "phase4d_ready_freeze_count"]:
        if prior[key] < 1:
            summary["blocker_count"] += 1
    ack_ok = acknowledgement == PREVIEW_ACK
    if not ack_ok:
        summary["warning_count"] += 1
    score = calculate_score(summary["blocker_count"], summary["warning_count"])
    final_preview_status = preview_status(score, summary["blocker_count"], summary["warning_count"])
    if summary["blocker_count"]:
        status = "Blocked"
    elif not ack_ok or summary["warning_count"]:
        status = "Needs Review"
    else:
        status = "Previewed"
    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": status,
        "preview_status": final_preview_status,
        "preview_score": score,
        "live_posting_allowed": 0,
        "payment_entry_created": 0,
        "company": context.company,
        "allowed_bank_account": context.allowed_bank_account,
        "allowed_receivable_account": context.allowed_receivable_account,
        "mapping_gate": context.name,
        "design_gate": design_gate.name if design_gate else None,
        "required_acknowledgement": PREVIEW_ACK,
        "acknowledgement_ok": ack_ok,
        "config": config,
        "config_errors": config_errors,
        "prior": prior,
        "guardrails_before": guard_before,
        "summary": summary,
        "lines": lines,
        "note": "Production Payment Entry posting preview only. No Payment Entry or GL is created.",
    }
    if int(dry_run or 0):
        return result

    doc = create_preview_doc(context, design_gate, config, prior, guard_before, acknowledgement, result, notes)
    save_lines(doc, lines)
    guard_after = guardrails()
    frappe.db.set_value(
        PREVIEW_DOCTYPE,
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
    result["posting_preview"] = doc.name
    result["preview_id"] = doc.preview_id
    result["guardrails_after"] = guard_after
    return result


@frappe.whitelist()
def cancel_pe_production_posting_preview(posting_preview, reason=None):
    assert_action("cancel_pe_production_posting_preview")
    if not frappe.db.exists(PREVIEW_DOCTYPE, posting_preview):
        frappe.throw(_("PE Production Posting Preview not found: {0}").format(posting_preview))
    frappe.db.set_value(
        PREVIEW_DOCTYPE,
        posting_preview,
        {"status": "Cancelled", "live_posting_allowed": 0, "payment_entry_created": 0, "cancelled_on": now_datetime(), "cancelled_by": frappe.session.user, "summary_json": reason or "Production Payment Entry posting preview cancelled."},
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{LINE_DOCTYPE}` SET status = 'Cancelled' WHERE posting_preview = %(posting_preview)s", {"posting_preview": posting_preview})
    frappe.db.commit()
    return {"posting_preview": posting_preview, "status": "Cancelled", "note": "Preview cancelled only. No accounting/payment records were changed."}


@frappe.whitelist()
def quick_pe_production_posting_preview_summary(limit=20):
    previews = frappe.get_all(
        PREVIEW_DOCTYPE,
        fields=["name", "preview_id", "status", "preview_status", "preview_score", "company", "allowed_bank_account", "allowed_receivable_account", "eligible_line_count", "blocked_line_count", "duplicate_line_count", "preview_total_amount", "payment_entry_created", "payment_entry_gl_count", "live_posting_allowed", "previewed_on", "previewed_by"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    lines = frappe.get_all(
        LINE_DOCTYPE,
        fields=["name", "posting_preview", "status", "severity", "scenario_key", "event_type", "claim_outcome", "source_reference", "posting_policy", "preview_payment_amount", "shortfall_amount", "block_reason", "preview_note"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {"previews": previews, "lines": lines, "required_acknowledgement": PREVIEW_ACK, "guardrails": guardrails(), "note": "Production PE posting preview summary only. Live posting remains blocked."}


def execute_preview_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("p.status = %(status)s")
        params["status"] = filters.status
    if filters.get("preview_status"):
        conditions.append("p.preview_status = %(preview_status)s")
        params["preview_status"] = filters.preview_status
    if filters.get("from_date"):
        conditions.append("DATE(p.previewed_on) >= %(from_date)s")
        params["from_date"] = filters.from_date
    if filters.get("to_date"):
        conditions.append("DATE(p.previewed_on) <= %(to_date)s")
        params["to_date"] = filters.to_date
    columns = [
        {"fieldname": "posting_preview", "label": _("Posting Preview"), "fieldtype": "Link", "options": PREVIEW_DOCTYPE, "width": 220},
        {"fieldname": "preview_id", "label": _("Preview ID"), "fieldtype": "Data", "width": 330},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "preview_status", "label": _("Preview Status"), "fieldtype": "Data", "width": 260},
        {"fieldname": "preview_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 180},
        {"fieldname": "eligible_line_count", "label": _("Eligible"), "fieldtype": "Int", "width": 90},
        {"fieldname": "blocked_line_count", "label": _("Blocked"), "fieldtype": "Int", "width": 90},
        {"fieldname": "duplicate_line_count", "label": _("Duplicate"), "fieldtype": "Int", "width": 90},
        {"fieldname": "preview_total_amount", "label": _("Preview Amount"), "fieldtype": "Currency", "options": "currency", "width": 140},
        {"fieldname": "shortfall_total_amount", "label": _("Shortfall"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "payment_entry_created", "label": _("PE Created"), "fieldtype": "Check", "width": 100},
        {"fieldname": "payment_entry_gl_count", "label": _("PE GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "live_posting_allowed", "label": _("Live Allowed"), "fieldtype": "Check", "width": 100},
        {"fieldname": "previewed_on", "label": _("Previewed On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT p.name AS posting_preview, p.preview_id, p.status, p.preview_status,
            p.preview_score, p.company, p.eligible_line_count, p.blocked_line_count,
            p.duplicate_line_count, p.preview_total_amount, p.shortfall_total_amount,
            p.payment_entry_created, p.payment_entry_gl_count, p.live_posting_allowed,
            p.previewed_on, %(currency)s AS currency
        FROM `tab{PREVIEW_DOCTYPE}` p
        {build_where(conditions)}
        ORDER BY p.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {"data": {"labels": [row.preview_id for row in data[:20]], "datasets": [{"name": "Eligible", "values": [int(row.eligible_line_count or 0) for row in data[:20]]}, {"name": "Blocked", "values": [int(row.blocked_line_count or 0) for row in data[:20]]}, {"name": "Duplicate", "values": [int(row.duplicate_line_count or 0) for row in data[:20]]}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Previews"), "datatype": "Int"},
        {"value": sum(int(row.eligible_line_count or 0) for row in data), "indicator": "Green", "label": _("Eligible Lines"), "datatype": "Int"},
        {"value": sum(int(row.payment_entry_created or 0) for row in data), "indicator": "Red", "label": _("Payment Entries Created"), "datatype": "Int"},
        {"value": sum(int(row.payment_entry_gl_count or 0) for row in data), "indicator": "Red", "label": _("Payment Entry GL"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_preview_line_report(filters=None, exceptions_only=0):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    for fieldname in ["posting_preview", "status", "event_type", "claim_outcome"]:
        if filters.get(fieldname):
            conditions.append(f"l.{fieldname} = %({fieldname})s")
            params[fieldname] = filters.get(fieldname)
    if exceptions_only:
        conditions.append("l.status IN ('Blocked', 'Duplicate', 'Warning')")
    columns = [
        {"fieldname": "line", "label": _("Line"), "fieldtype": "Link", "options": LINE_DOCTYPE, "width": 220},
        {"fieldname": "posting_preview", "label": _("Posting Preview"), "fieldtype": "Link", "options": PREVIEW_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "scenario_key", "label": _("Scenario"), "fieldtype": "Data", "width": 230},
        {"fieldname": "event_type", "label": _("Event Type"), "fieldtype": "Data", "width": 150},
        {"fieldname": "claim_outcome", "label": _("Outcome"), "fieldtype": "Data", "width": 130},
        {"fieldname": "source_reference", "label": _("Source Reference"), "fieldtype": "Data", "width": 220},
        {"fieldname": "posting_policy", "label": _("Policy"), "fieldtype": "Link", "options": POLICY_DOCTYPE, "width": 220},
        {"fieldname": "preview_payment_amount", "label": _("Preview Payment"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "shortfall_amount", "label": _("Shortfall"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "would_create_payment_entry", "label": _("Would Create PE"), "fieldtype": "Check", "width": 110},
        {"fieldname": "actual_payment_entry_created", "label": _("Actual PE Created"), "fieldtype": "Check", "width": 120},
        {"fieldname": "block_reason", "label": _("Block Reason"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "preview_note", "label": _("Preview Note"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT l.name AS line, l.posting_preview, l.status, l.severity,
            l.scenario_key, l.event_type, l.claim_outcome, l.source_reference,
            l.posting_policy, l.preview_payment_amount, l.shortfall_amount,
            l.would_create_payment_entry, l.actual_payment_entry_created,
            l.block_reason, l.preview_note, %(currency)s AS currency
        FROM `tab{LINE_DOCTYPE}` l
        {build_where(conditions)}
        ORDER BY CASE l.status WHEN 'Blocked' THEN 1 WHEN 'Duplicate' THEN 2 WHEN 'Warning' THEN 3 WHEN 'Preview Eligible' THEN 4 ELSE 5 END, l.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart_map = {}
    for row in data:
        chart_map[row.status or "Info"] = chart_map.get(row.status or "Info", 0) + 1
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Lines", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Lines"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Preview Eligible"]), "indicator": "Green", "label": _("Eligible"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Blocked"]), "indicator": "Orange", "label": _("Blocked As Designed"), "datatype": "Int"},
        {"value": len([row for row in data if row.actual_payment_entry_created]), "indicator": "Red", "label": _("Actual PE Created"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_preview_exception_report(filters=None):
    return execute_preview_line_report(filters, exceptions_only=1)


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
