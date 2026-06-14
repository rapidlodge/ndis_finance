import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


BASELINE_ACK = "I_CONFIRM_PHASE10N_ACTIVATE_CONTROLLED_LIMITED_OPERATIONS_STEADY_STATE_BASELINE_NO_POSTING"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
CLOSEOUT_DOCTYPE = "NDIS Limited Operation Closeout Gate"
BASELINE_DOCTYPE = "NDIS Controlled Limited Ops Baseline"
BASELINE_ITEM_DOCTYPE = "NDIS Controlled Limited Ops Baseline Item"


def make_baseline_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-CONTROLLED-LIMITED-OPS-BASELINE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def has_column(doctype, fieldname):
    try:
        return bool(frappe.db.has_column(doctype, fieldname))
    except Exception:
        return False


def get_value_if_has(doctype, name, fieldname, default=None):
    if not name or not frappe.db.exists(doctype, name) or not has_column(doctype, fieldname):
        return default
    value = frappe.db.get_value(doctype, name, fieldname)
    return default if value is None else value


def get_flag(doctype, name, fieldname, default=0):
    return int(get_value_if_has(doctype, name, fieldname, default) or 0)


def production_batch_enabled_policy_count():
    if not has_column(POLICY_DOCTYPE, "production_batch_enabled"):
        return 0
    return count_dt(POLICY_DOCTYPE, {"production_batch_enabled": 1})


def live_posting_allowed_policy_count():
    if not has_column(POLICY_DOCTYPE, "live_posting_allowed"):
        return 0
    return count_dt(POLICY_DOCTYPE, {"live_posting_allowed": 1})


def guardrails():
    return {
        "payment_entry_count": count_dt("Payment Entry"),
        "payment_entry_gl_count": count_dt("GL Entry", {"voucher_type": "Payment Entry"}),
        "submitted_journal_entry_count_today": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}),
        "purchase_invoice_count_today": count_dt("Purchase Invoice", {"creation": [">=", today()]}),
        "production_batch_enabled_policy_count": production_batch_enabled_policy_count(),
        "live_posting_allowed_policy_count": live_posting_allowed_policy_count(),
    }


def latest_closeout():
    rows = frappe.get_all(
        CLOSEOUT_DOCTYPE,
        filters={
            "status": "Closeout Approved",
            "closeout_status": "Ready For Controlled Limited Operations Steady State",
            "closeout_approved": 1,
            "ready_for_controlled_limited_operations_steady_state": 1,
            "limited_operation_cycle_closed": 1,
            "full_cycle_evidence_chain_verified": 1,
            "steady_state_monitoring_ready": 1,
            "no_new_accounting_movement_verified": 1,
            "policy_state_preserved_verified": 1,
            "policy_mutation_performed": 0,
            "actual_policy_mutation_count": 0,
            "phase10l_freeze_verified": 1,
            "phase10k_rollback_verified": 1,
            "phase10j_smoke_verified": 1,
            "phase10i_gate_verified": 1,
            "phase10h_preview_verified": 1,
            "phase10g_pre_check_verified": 1,
            "phase10f_monitoring_register_verified": 1,
            "phase10e_policy_decision_verified": 1,
            "controlled_policy_enabled_verified": 1,
            "live_posting_blocked_verified": 1,
            "payment_entry_docstatus": 2,
            "payment_entry_status": "Cancelled",
            "payment_entry_reference_count": 3,
            "gl_account_non_zero_count": 0,
            "actual_payment_entry_created_count": 0,
            "actual_payment_entry_cancelled_count": 0,
            "actual_gl_created_count": 0,
            "submitted_journal_entry_count_today": 0,
            "purchase_invoice_count_today": 0,
        },
        fields=[
            "name",
            "closeout_id",
            "freeze",
            "rollback",
            "smoke",
            "execution_gate",
            "preview",
            "pre_check",
            "monitoring_register",
            "policy_decision",
            "target_policy_doctype",
            "target_policy",
            "target_policy_name",
            "target_policy_enabled_after",
            "target_policy_live_after",
            "production_batch_enabled_policy_count_after",
            "live_posting_allowed_policy_count_after",
            "payment_entry",
            "payment_entry_amount",
            "payment_entry_reference_count",
            "invoice_outstanding_total",
            "gl_net_balance",
            "gl_account_non_zero_count",
            "payment_entry_count_after",
            "payment_entry_gl_count_after",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_baseline(closeout):
    rows = frappe.get_all(
        BASELINE_DOCTYPE,
        filters={"closeout": closeout, "status": "Baseline Active", "baseline_active": 1},
        fields=["name", "baseline_id"],
        limit=1,
    )
    return rows[0] if rows else None


def voucher_gl_net(payment_entry):
    if not payment_entry:
        return {"rows": [], "total_debit": 0, "total_credit": 0, "total_balance": 0, "non_zero_count": 0}
    rows = frappe.db.sql(
        """
        SELECT account, ROUND(SUM(debit), 2) AS debit, ROUND(SUM(credit), 2) AS credit,
               ROUND(SUM(debit - credit), 2) AS balance
        FROM `tabGL Entry`
        WHERE voucher_type = 'Payment Entry'
        AND voucher_no = %(payment_entry)s
        GROUP BY account
        ORDER BY account
        """,
        {"payment_entry": payment_entry},
        as_dict=True,
    )
    total_debit = round(sum(flt(row.debit or 0, 2) for row in rows), 2)
    total_credit = round(sum(flt(row.credit or 0, 2) for row in rows), 2)
    return {
        "rows": rows,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "total_balance": round(total_debit - total_credit, 2),
        "non_zero_count": len([row for row in rows if abs(flt(row.balance or 0, 2)) > 0.01]),
    }


def reference_snapshot(payment_entry):
    if not payment_entry or not frappe.db.exists("Payment Entry", payment_entry):
        return []
    pe = frappe.get_doc("Payment Entry", payment_entry)
    rows = []
    for ref in pe.references:
        if ref.reference_doctype != "Sales Invoice":
            continue
        rows.append(
            {
                "reference_doctype": ref.reference_doctype,
                "reference_name": ref.reference_name,
                "allocated_amount": flt(ref.allocated_amount or 0, 2),
                "current_outstanding": flt(frappe.db.get_value("Sales Invoice", ref.reference_name, "outstanding_amount") or 0, 2),
            }
        )
    return rows


def operating_limits(closeout):
    register = closeout.monitoring_register if closeout else None
    pre_check = closeout.pre_check if closeout else None
    preview = closeout.preview if closeout else None
    gate = closeout.execution_gate if closeout else None
    return {
        "max_batch_line_count": int(
            get_value_if_has("NDIS Controlled Limited Operations Monitoring Register", register, "max_batch_line_count")
            or get_value_if_has("NDIS Controlled Limited Operation Pre Check", pre_check, "requested_batch_line_count")
            or get_value_if_has("NDIS Guarded Limited Operation Preview", preview, "preview_batch_line_count")
            or get_value_if_has("NDIS Guarded Limited Operation Execution Gate", gate, "locked_batch_line_count")
            or 3
        ),
        "max_batch_amount": flt(
            get_value_if_has("NDIS Controlled Limited Operations Monitoring Register", register, "max_batch_amount")
            or get_value_if_has("NDIS Controlled Limited Operation Pre Check", pre_check, "requested_batch_amount")
            or get_value_if_has("NDIS Guarded Limited Operation Preview", preview, "preview_batch_amount")
            or get_value_if_has("NDIS Guarded Limited Operation Execution Gate", gate, "locked_batch_amount")
            or 3,
            2,
        ),
        "max_payment_entry_count": int(
            get_value_if_has("NDIS Controlled Limited Operations Monitoring Register", register, "max_payment_entry_count")
            or get_value_if_has("NDIS Controlled Limited Operation Pre Check", pre_check, "requested_payment_entry_count")
            or get_value_if_has("NDIS Guarded Limited Operation Preview", preview, "preview_payment_entry_count")
            or get_value_if_has("NDIS Guarded Limited Operation Execution Gate", gate, "locked_payment_entry_count")
            or 1
        ),
        "live_posting_allowed": int(get_value_if_has("NDIS Controlled Limited Operations Monitoring Register", register, "live_posting_allowed", 0) or 0),
        "journal_entry_side_effect_allowed": int(get_value_if_has("NDIS Controlled Limited Operations Monitoring Register", register, "journal_entry_side_effect_allowed", 0) or 0),
        "purchase_invoice_side_effect_allowed": int(get_value_if_has("NDIS Controlled Limited Operations Monitoring Register", register, "purchase_invoice_side_effect_allowed", 0) or 0),
    }


def validate_source(closeout, guard, pe_doc, policy_enabled, policy_live, gl_net, refs, limits):
    issues = []
    if not closeout:
        return ["No approved Phase 10M closeout found."]
    existing = existing_baseline(closeout.name)
    if existing:
        issues.append(f"Phase 10N baseline already exists for this closeout: {existing.baseline_id}")

    required_links = {
        "closeout": (CLOSEOUT_DOCTYPE, closeout.name),
        "freeze": ("NDIS Single Guarded Op Smoke Rollback Freeze", closeout.freeze),
        "rollback": ("NDIS Single Guarded Limited Operation Smoke Rollback", closeout.rollback),
        "smoke": ("NDIS Single Guarded Limited Operation Smoke", closeout.smoke),
        "execution_gate": ("NDIS Guarded Limited Operation Execution Gate", closeout.execution_gate),
        "preview": ("NDIS Guarded Limited Operation Preview", closeout.preview),
        "pre_check": ("NDIS Controlled Limited Operation Pre Check", closeout.pre_check),
        "monitoring_register": ("NDIS Controlled Limited Operations Monitoring Register", closeout.monitoring_register),
        "target_policy": (POLICY_DOCTYPE, closeout.target_policy),
        "payment_entry": ("Payment Entry", closeout.payment_entry),
    }
    for label, (doctype, name) in required_links.items():
        if not name or not frappe.db.exists(doctype, name):
            issues.append(f"Missing or invalid evidence link: {label}")

    if not pe_doc:
        issues.append("Payment Entry could not be loaded.")
    else:
        if int(pe_doc.docstatus or 0) != 2 or pe_doc.status != "Cancelled":
            issues.append(f"Payment Entry must remain docstatus 2 / Cancelled. Current: {pe_doc.docstatus} / {pe_doc.status}")
        if flt(pe_doc.paid_amount or 0, 2) != 3:
            issues.append(f"Payment Entry amount must remain 3.00. Current: {flt(pe_doc.paid_amount or 0, 2)}")
        if len(pe_doc.references or []) != 3:
            issues.append(f"Payment Entry must still have 3 references. Current: {len(pe_doc.references or [])}")

    outstanding_total = round(sum(flt(row["current_outstanding"], 2) for row in refs), 2)
    if abs(outstanding_total - flt(closeout.invoice_outstanding_total or 0, 2)) > 0.01:
        issues.append("Current invoice outstanding total no longer matches Phase 10M closeout evidence.")
    if abs(flt(gl_net["total_balance"], 2)) > 0.01 or gl_net["non_zero_count"] != 0:
        issues.append("Closed-cycle voucher GL must remain net zero with no non-zero accounts.")
    if policy_enabled != 1:
        issues.append("Target policy production_batch_enabled must be 1 before Phase 10N. Do not let Phase 10N repair this.")
    if policy_live != 0:
        issues.append("Target policy live_posting_allowed must be 0 before Phase 10N. Do not let Phase 10N repair this.")
    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must remain enabled.")
    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must remain 0.")
    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry count today must remain 0.")
    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice count today must remain 0.")
    if limits != {
        "max_batch_line_count": 3,
        "max_batch_amount": 3.0,
        "max_payment_entry_count": 1,
        "live_posting_allowed": 0,
        "journal_entry_side_effect_allowed": 0,
        "purchase_invoice_side_effect_allowed": 0,
    }:
        issues.append(f"Steady-state operating limits are not 3 / 3.00 / 1 with live, JE, and PI side effects blocked. Current: {limits}")
    return issues


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


def build_items(closeout, issues, ack_ok, evidence):
    items = []
    if closeout:
        add_item(items, "Pass", "Low", "Evidence", "phase10m_closeout_exists", "Phase 10M closeout exists", f"Closeout found: {closeout.closeout_id}.", CLOSEOUT_DOCTYPE, closeout.name)
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase10m_closeout_exists", "Phase 10M closeout exists", "No approved Phase 10M closeout found.")
    if issues:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Baseline Source", "baseline_source_valid", "Baseline source valid", issue)
    else:
        add_item(items, "Pass", "Low", "Baseline Source", "baseline_source_valid", "Baseline source valid", "Phase 10M closeout is valid for steady-state baseline.")

    chain = [
        ("phase10e_policy_decision_verified", "Phase 10E policy decision verified", "policy_decision"),
        ("phase10f_monitoring_register_verified", "Phase 10F monitoring register verified", "monitoring_register"),
        ("phase10g_pre_check_verified", "Phase 10G pre-check verified", "pre_check"),
        ("phase10h_preview_verified", "Phase 10H preview verified", "preview"),
        ("phase10i_gate_verified", "Phase 10I execution gate verified", "execution_gate"),
        ("phase10j_smoke_verified", "Phase 10J smoke verified", "smoke"),
        ("phase10k_rollback_verified", "Phase 10K rollback verified", "rollback"),
        ("phase10l_freeze_verified", "Phase 10L freeze verified", "freeze"),
        ("phase10m_closeout_verified", "Phase 10M closeout verified", "closeout"),
    ]
    for key, label, fieldname in chain:
        add_item(items, "Pass", "Low", "Cycle Chain", key, label, str(evidence.get(fieldname)))
    add_item(items, "Pass", "High", "Operating Limits", "limits_captured", "Steady-state operating limits captured", f"lines={evidence['max_batch_line_count']}, amount={evidence['max_batch_amount']}, PE={evidence['max_payment_entry_count']}")
    add_item(items, "Pass", "High", "Payment Entry", "payment_entry_cancelled", "Closed-cycle Payment Entry remains cancelled", f"{evidence['payment_entry']} docstatus={evidence['payment_entry_docstatus']} status={evidence['payment_entry_status']}", "Payment Entry", evidence["payment_entry"])
    add_item(items, "Pass", "High", "GL", "gl_net_zero", "Closed-cycle GL net zero confirmed", f"balance={evidence['gl_net_balance']} non_zero_accounts={evidence['gl_account_non_zero_count']}")
    add_item(items, "Pass", "High", "Guardrail", "no_new_movement", "No new accounting movement", f"PE {evidence['payment_entry_count_before']} -> {evidence['payment_entry_count_after']}; PE GL {evidence['payment_entry_gl_count_before']} -> {evidence['payment_entry_gl_count_after']}")
    add_item(items, "Pass", "High", "Policy", "policy_state_preserved", "Policy state preserved", f"enabled/live={evidence['production_batch_enabled_policy_count_after']} / {evidence['live_posting_allowed_policy_count_after']}")
    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {BASELINE_ACK}")
    return items


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


def create_items(doc, items):
    for item in items:
        row = frappe.new_doc(BASELINE_ITEM_DOCTYPE)
        row.baseline = doc.name
        for field in ["status", "severity", "category", "check_key", "check_label", "detail", "source_doctype", "source_name"]:
            setattr(row, field, item.get(field))
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


def build_evidence(closeout, guard_before, guard_after, pe_doc, refs, gl_net, limits, policy_enabled_before, policy_enabled_after, policy_live_before, policy_live_after):
    outstanding_total = round(sum(flt(row["current_outstanding"], 2) for row in refs), 2)
    return {
        "closeout": closeout.name if closeout else None,
        "freeze": closeout.freeze if closeout else None,
        "rollback": closeout.rollback if closeout else None,
        "smoke": closeout.smoke if closeout else None,
        "execution_gate": closeout.execution_gate if closeout else None,
        "preview": closeout.preview if closeout else None,
        "pre_check": closeout.pre_check if closeout else None,
        "monitoring_register": closeout.monitoring_register if closeout else None,
        "policy_decision": closeout.policy_decision if closeout else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": closeout.target_policy if closeout else None,
        "target_policy_name": closeout.target_policy_name if closeout else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_before": policy_live_before,
        "target_policy_live_after": policy_live_after,
        "production_batch_enabled_policy_count_before": guard_before["production_batch_enabled_policy_count"],
        "production_batch_enabled_policy_count_after": guard_after["production_batch_enabled_policy_count"],
        "live_posting_allowed_policy_count_before": guard_before["live_posting_allowed_policy_count"],
        "live_posting_allowed_policy_count_after": guard_after["live_posting_allowed_policy_count"],
        **limits,
        "payment_entry": closeout.payment_entry if closeout else None,
        "payment_entry_docstatus": int(pe_doc.docstatus or 0) if pe_doc else 0,
        "payment_entry_status": pe_doc.status if pe_doc else None,
        "payment_entry_amount": flt(pe_doc.paid_amount or 0, 2) if pe_doc else 0,
        "payment_entry_reference_count": len(pe_doc.references or []) if pe_doc else 0,
        "invoice_outstanding_total": outstanding_total,
        "gl_net_balance": gl_net["total_balance"],
        "gl_account_non_zero_count": gl_net["non_zero_count"],
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guard_after["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
        "actual_payment_entry_created_count": 0,
        "actual_payment_entry_cancelled_count": 0,
        "actual_gl_created_count": 0,
        "submitted_journal_entry_count_today": guard_after["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_after["purchase_invoice_count_today"],
    }


@frappe.whitelist()
def run_controlled_limited_operations_steady_state_baseline(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_controlled_limited_operations_steady_state_baseline")
    closeout = latest_closeout()
    guard_before = guardrails()
    ack_ok = acknowledgement == BASELINE_ACK
    pe_doc = frappe.get_doc("Payment Entry", closeout.payment_entry) if closeout and frappe.db.exists("Payment Entry", closeout.payment_entry) else None
    refs = reference_snapshot(closeout.payment_entry) if closeout else []
    gl_net = voucher_gl_net(closeout.payment_entry) if closeout else voucher_gl_net(None)
    limits = operating_limits(closeout)
    policy_enabled_before = get_flag(POLICY_DOCTYPE, closeout.target_policy, "production_batch_enabled") if closeout else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, closeout.target_policy, "live_posting_allowed") if closeout else 0
    guard_after = guardrails()
    policy_enabled_after = get_flag(POLICY_DOCTYPE, closeout.target_policy, "production_batch_enabled") if closeout else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, closeout.target_policy, "live_posting_allowed") if closeout else 0
    issues = validate_source(closeout, guard_before, pe_doc, policy_enabled_before, policy_live_before, gl_net, refs, limits)
    no_new_movement = int(
        guard_before["payment_entry_count"] == guard_after["payment_entry_count"]
        and guard_before["payment_entry_gl_count"] == guard_after["payment_entry_gl_count"]
        and guard_before["submitted_journal_entry_count_today"] == guard_after["submitted_journal_entry_count_today"]
        and guard_before["purchase_invoice_count_today"] == guard_after["purchase_invoice_count_today"]
    )
    policy_preserved = int(
        policy_enabled_before == 1
        and policy_enabled_after == 1
        and policy_live_before == 0
        and policy_live_after == 0
        and guard_before["production_batch_enabled_policy_count"] == guard_after["production_batch_enabled_policy_count"]
        and guard_before["live_posting_allowed_policy_count"] == guard_after["live_posting_allowed_policy_count"]
    )
    if not no_new_movement:
        issues.append("Accounting movement changed while preparing baseline evidence.")
    evidence = build_evidence(closeout, guard_before, guard_after, pe_doc, refs, gl_net, limits, policy_enabled_before, policy_enabled_after, policy_live_before, policy_live_after)
    items = build_items(closeout, issues, ack_ok, evidence)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    allowed = int(ack_ok and item_summary["blocker_count"] == 0 and bool(closeout))
    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Baseline Active" if allowed else "Needs Review",
        "baseline_status": "Controlled Limited Operations Steady-State Baseline Active" if allowed else "Needs Review",
        "baseline_active": allowed,
        "ready_for_controlled_limited_operations_execution": allowed,
        "ready_for_steady_state_monitoring": allowed,
        "steady_state_baseline_locked": allowed,
        "full_cycle_closeout_verified": allowed,
        "operating_limits_captured": int(limits == {"max_batch_line_count": 3, "max_batch_amount": 3.0, "max_payment_entry_count": 1, "live_posting_allowed": 0, "journal_entry_side_effect_allowed": 0, "purchase_invoice_side_effect_allowed": 0}),
        "no_new_accounting_movement_verified": no_new_movement,
        "policy_state_preserved_verified": policy_preserved,
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": 0,
        "phase10m_closeout_verified": 1 if closeout else 0,
        "phase10l_freeze_verified": 1 if closeout else 0,
        "phase10k_rollback_verified": 1 if closeout else 0,
        "phase10j_smoke_verified": 1 if closeout else 0,
        "phase10i_gate_verified": 1 if closeout else 0,
        "phase10h_preview_verified": 1 if closeout else 0,
        "phase10g_pre_check_verified": 1 if closeout else 0,
        "phase10f_monitoring_register_verified": 1 if closeout else 0,
        "phase10e_policy_decision_verified": 1 if closeout and closeout.policy_decision else 0,
        "controlled_policy_enabled_verified": int(policy_enabled_after == 1),
        "live_posting_blocked_verified": int(policy_live_after == 0),
        **evidence,
        "baseline_score": score,
        **item_summary,
        "items": items,
        "issues": issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "references": refs,
        "gl_net": gl_net,
        "required_acknowledgement": BASELINE_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 10N activates the steady-state baseline only. No accounting movement or policy mutation is performed.",
    }
    if int(dry_run or 0):
        result.update(
            {
                "status": "Needs Review",
                "baseline_status": "Needs Review",
                "baseline_active": 0,
                "ready_for_controlled_limited_operations_execution": 0,
                "ready_for_steady_state_monitoring": 0,
                "steady_state_baseline_locked": 0,
                "full_cycle_closeout_verified": 0,
            }
        )
        return result
    doc = frappe.new_doc(BASELINE_DOCTYPE)
    doc.baseline_id = make_baseline_id()
    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0)
    doc.production_mode_detected = int(frappe.conf.get("ndis_finance_production_mode") or 0)
    doc.live_payment_entry_posting_config = int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0)
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = BASELINE_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.evidence_json = safe_json({"evidence": evidence, "references": refs, "gl_net": gl_net, "guardrails_before": guard_before, "guardrails_after": guard_after, "limits": limits})
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    create_items(doc, items)
    frappe.db.commit()
    return {**result, "created": True, "baseline": doc.name, "baseline_id": doc.baseline_id, "guardrails_after": guardrails()}


@frappe.whitelist()
def cancel_controlled_limited_operations_steady_state_baseline_audit(baseline, reason=None):
    assert_action("cancel_controlled_limited_operations_steady_state_baseline_audit")
    if not frappe.db.exists(BASELINE_DOCTYPE, baseline):
        frappe.throw(_("Baseline audit not found: {0}").format(baseline))
    doc = frappe.get_doc(BASELINE_DOCTYPE, baseline)
    if doc.status == "Cancelled":
        return {"baseline": baseline, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.baseline_active or 0):
        frappe.throw(_("Cannot cancel an active Phase 10N steady-state baseline record."))
    frappe.db.set_value(
        BASELINE_DOCTYPE,
        baseline,
        {
            "status": "Cancelled",
            "baseline_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 10N no-ack baseline audit cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{BASELINE_ITEM_DOCTYPE}` SET status = 'Cancelled' WHERE baseline = %(baseline)s", {"baseline": baseline})
    frappe.db.commit()
    return {"baseline": baseline, "status": "Cancelled", "note": "No-ack baseline audit cancelled only. No accounting or policy movement occurred."}


@frappe.whitelist()
def quick_controlled_limited_operations_steady_state_baseline_summary(limit=20):
    baselines = frappe.get_all(
        BASELINE_DOCTYPE,
        fields=[
            "name",
            "baseline_id",
            "status",
            "baseline_status",
            "baseline_active",
            "ready_for_controlled_limited_operations_execution",
            "ready_for_steady_state_monitoring",
            "closeout",
            "monitoring_register",
            "target_policy",
            "max_batch_line_count",
            "max_batch_amount",
            "max_payment_entry_count",
            "live_posting_allowed",
            "payment_entry",
            "payment_entry_docstatus",
            "payment_entry_status",
            "production_batch_enabled_policy_count_after",
            "live_posting_allowed_policy_count_after",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "submitted_journal_entry_count_today",
            "purchase_invoice_count_today",
            "baseline_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(BASELINE_ITEM_DOCTYPE, fields=["name", "baseline", "status", "severity", "category", "check_label", "detail", "source_doctype", "source_name"], order_by="creation desc", limit=int(limit or 20))
    return {"baselines": baselines, "items": items, "required_acknowledgement": BASELINE_ACK, "guardrails": guardrails(), "note": "Phase 10N steady-state baseline summary. Active baseline allows controlled limited operations under captured limits."}


def execute_baseline_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("b.status = %(status)s")
        params["status"] = filters.get("status")
    data = frappe.db.sql(
        f"""
        SELECT b.name AS baseline, b.baseline_id, b.status, b.baseline_status, b.baseline_active,
               b.ready_for_controlled_limited_operations_execution, b.ready_for_steady_state_monitoring,
               b.closeout, b.monitoring_register, b.target_policy, b.max_batch_line_count, b.max_batch_amount,
               b.max_payment_entry_count, b.live_posting_allowed, b.journal_entry_side_effect_allowed,
               b.purchase_invoice_side_effect_allowed, b.payment_entry, b.payment_entry_docstatus,
               b.payment_entry_status, b.production_batch_enabled_policy_count_after,
               b.live_posting_allowed_policy_count_after, b.payment_entry_count_before,
               b.payment_entry_count_after, b.payment_entry_gl_count_before, b.payment_entry_gl_count_after,
               b.submitted_journal_entry_count_today, b.purchase_invoice_count_today, b.baseline_score,
               b.checked_on, %(currency)s AS currency
        FROM `tab{BASELINE_DOCTYPE}` b
        {build_where(conditions)}
        ORDER BY b.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {"data": {"labels": [row.baseline_id for row in data[:20]], "datasets": [{"name": "Active", "values": [int(row.baseline_active or 0) for row in data[:20]]}, {"name": "Ready Execution", "values": [int(row.ready_for_controlled_limited_operations_execution or 0) for row in data[:20]]}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Baselines"), "datatype": "Int"},
        {"value": sum(int(row.baseline_active or 0) for row in data), "indicator": "Green", "label": _("Active"), "datatype": "Int"},
        {"value": sum(int(row.ready_for_controlled_limited_operations_execution or 0) for row in data), "indicator": "Green", "label": _("Ready Execution"), "datatype": "Int"},
        {"value": sum(int(row.live_posting_allowed or 0) for row in data), "indicator": "Red", "label": _("Live Allowed"), "datatype": "Int"},
    ]
    return baseline_columns(), data, None, chart, summary


def baseline_columns():
    return [
        {"fieldname": "baseline", "label": _("Baseline"), "fieldtype": "Link", "options": BASELINE_DOCTYPE, "width": 220},
        {"fieldname": "baseline_id", "label": _("Baseline ID"), "fieldtype": "Data", "width": 390},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 130},
        {"fieldname": "baseline_status", "label": _("Baseline Status"), "fieldtype": "Data", "width": 360},
        {"fieldname": "baseline_active", "label": _("Active"), "fieldtype": "Check", "width": 80},
        {"fieldname": "ready_for_controlled_limited_operations_execution", "label": _("Ready Execution"), "fieldtype": "Check", "width": 125},
        {"fieldname": "ready_for_steady_state_monitoring", "label": _("Ready Monitoring"), "fieldtype": "Check", "width": 125},
        {"fieldname": "closeout", "label": _("Closeout"), "fieldtype": "Link", "options": CLOSEOUT_DOCTYPE, "width": 220},
        {"fieldname": "monitoring_register", "label": _("Monitoring Register"), "fieldtype": "Link", "options": "NDIS Controlled Limited Operations Monitoring Register", "width": 220},
        {"fieldname": "target_policy", "label": _("Target Policy"), "fieldtype": "Data", "width": 260},
        {"fieldname": "max_batch_line_count", "label": _("Max Lines"), "fieldtype": "Int", "width": 90},
        {"fieldname": "max_batch_amount", "label": _("Max Amount"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "max_payment_entry_count", "label": _("Max PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "live_posting_allowed", "label": _("Live Allowed"), "fieldtype": "Check", "width": 100},
        {"fieldname": "journal_entry_side_effect_allowed", "label": _("JE Allowed"), "fieldtype": "Check", "width": 95},
        {"fieldname": "purchase_invoice_side_effect_allowed", "label": _("PI Allowed"), "fieldtype": "Check", "width": 95},
        {"fieldname": "payment_entry", "label": _("Closed PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "payment_entry_docstatus", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 105},
        {"fieldname": "payment_entry_status", "label": _("PE Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "production_batch_enabled_policy_count_after", "label": _("Enabled Policies"), "fieldtype": "Int", "width": 125},
        {"fieldname": "live_posting_allowed_policy_count_after", "label": _("Live Policies"), "fieldtype": "Int", "width": 105},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 110},
        {"fieldname": "submitted_journal_entry_count_today", "label": _("JE Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "purchase_invoice_count_today", "label": _("PI Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "baseline_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("baseline"):
        conditions.append("i.baseline = %(baseline)s")
        params["baseline"] = filters.get("baseline")
    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": BASELINE_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "baseline", "label": _("Baseline"), "fieldtype": "Link", "options": BASELINE_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 180},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 340},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 620},
        {"fieldname": "source_doctype", "label": _("Source DocType"), "fieldtype": "Data", "width": 220},
        {"fieldname": "source_name", "label": _("Source Name"), "fieldtype": "Data", "width": 240},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]
    data = frappe.db.sql(
        f"""
        SELECT i.name AS item, i.baseline, i.status, i.severity, i.category, i.check_label,
               i.detail, i.source_doctype, i.source_name, i.checked_on
        FROM `tab{BASELINE_ITEM_DOCTYPE}` i
        {build_where(conditions)}
        ORDER BY CASE i.status WHEN 'Blocker' THEN 1 WHEN 'Warning' THEN 2 WHEN 'Pass' THEN 3 WHEN 'Info' THEN 4 ELSE 5 END, i.creation DESC
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
        {"value": len([row for row in data if row.category == "Operating Limits"]), "indicator": "Blue", "label": _("Operating Limit Checks"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_baseline_report(filters)
    guard = guardrails()
    summary.extend(
        [
            {"value": guard["payment_entry_count"], "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"},
            {"value": guard["payment_entry_gl_count"], "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"},
            {"value": guard["production_batch_enabled_policy_count"], "indicator": "Green", "label": _("Enabled Policies"), "datatype": "Int"},
            {"value": guard["live_posting_allowed_policy_count"], "indicator": "Red", "label": _("Live Policies"), "datatype": "Int"},
            {"value": guard["submitted_journal_entry_count_today"], "indicator": "Red", "label": _("Submitted JE Today"), "datatype": "Int"},
            {"value": guard["purchase_invoice_count_today"], "indicator": "Red", "label": _("Purchase Invoice Today"), "datatype": "Int"},
        ]
    )
    return columns, data, message, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
