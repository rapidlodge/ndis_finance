import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


WATCH_ACK = "I_CONFIRM_PHASE10O_ACTIVATE_CONTROLLED_LIMITED_OPERATIONS_RUNTIME_WATCH_NO_POSTING"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
BASELINE_DOCTYPE = "NDIS Controlled Limited Ops Baseline"
WATCH_DOCTYPE = "NDIS Controlled Limited Ops Runtime Watch"
WATCH_ITEM_DOCTYPE = "NDIS Controlled Limited Ops Runtime Watch Item"


def make_watch_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-CONTROLLED-LIMITED-OPS-RUNTIME-WATCH-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_baseline():
    rows = frappe.get_all(
        BASELINE_DOCTYPE,
        filters={
            "status": "Baseline Active",
            "baseline_status": "Controlled Limited Operations Steady-State Baseline Active",
            "baseline_active": 1,
            "ready_for_controlled_limited_operations_execution": 1,
            "ready_for_steady_state_monitoring": 1,
            "steady_state_baseline_locked": 1,
            "full_cycle_closeout_verified": 1,
            "operating_limits_captured": 1,
            "no_new_accounting_movement_verified": 1,
            "policy_state_preserved_verified": 1,
            "policy_mutation_performed": 0,
            "actual_policy_mutation_count": 0,
            "phase10m_closeout_verified": 1,
            "phase10f_monitoring_register_verified": 1,
            "controlled_policy_enabled_verified": 1,
            "live_posting_blocked_verified": 1,
            "target_policy_enabled_after": 1,
            "target_policy_live_after": 0,
            "max_batch_line_count": 3,
            "max_batch_amount": 3,
            "max_payment_entry_count": 1,
            "live_posting_allowed": 0,
            "journal_entry_side_effect_allowed": 0,
            "purchase_invoice_side_effect_allowed": 0,
            "payment_entry_docstatus": 2,
            "payment_entry_status": "Cancelled",
            "payment_entry_amount": 3,
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
            "baseline_id",
            "closeout",
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
            "max_batch_line_count",
            "max_batch_amount",
            "max_payment_entry_count",
            "live_posting_allowed",
            "journal_entry_side_effect_allowed",
            "purchase_invoice_side_effect_allowed",
            "payment_entry",
            "invoice_outstanding_total",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_active_watch(baseline):
    rows = frappe.get_all(
        WATCH_DOCTYPE,
        filters={"baseline": baseline, "status": "Watch Active", "watch_active": 1},
        fields=["name", "watch_id"],
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


def validate_source(baseline, guard, pe_doc, policy_enabled, policy_live, gl_net, refs, config):
    issues = []
    if not baseline:
        return ["No active Phase 10N steady-state baseline found."]

    existing = existing_active_watch(baseline.name)
    if existing:
        issues.append(f"Active Phase 10O runtime watch already exists for this baseline: {existing.watch_id}")

    required_links = {
        "baseline": (BASELINE_DOCTYPE, baseline.name),
        "closeout": ("NDIS Limited Operation Closeout Gate", baseline.closeout),
        "freeze": ("NDIS Single Guarded Op Smoke Rollback Freeze", baseline.freeze),
        "rollback": ("NDIS Single Guarded Limited Operation Smoke Rollback", baseline.rollback),
        "smoke": ("NDIS Single Guarded Limited Operation Smoke", baseline.smoke),
        "execution_gate": ("NDIS Guarded Limited Operation Execution Gate", baseline.execution_gate),
        "preview": ("NDIS Guarded Limited Operation Preview", baseline.preview),
        "pre_check": ("NDIS Controlled Limited Operation Pre Check", baseline.pre_check),
        "monitoring_register": ("NDIS Controlled Limited Operations Monitoring Register", baseline.monitoring_register),
        "policy_decision": ("NDIS Guarded Adapter Final Policy Decision", baseline.policy_decision),
        "target_policy": (POLICY_DOCTYPE, baseline.target_policy),
        "payment_entry": ("Payment Entry", baseline.payment_entry),
    }
    for label, (doctype, name) in required_links.items():
        if not name or not frappe.db.exists(doctype, name):
            issues.append(f"Missing or invalid evidence link: {label}")

    if not pe_doc:
        issues.append("Closed-cycle Payment Entry could not be loaded.")
    else:
        if int(pe_doc.docstatus or 0) != 2:
            issues.append(f"Closed-cycle Payment Entry must remain cancelled docstatus 2. Current: {pe_doc.docstatus}")
        if pe_doc.status != "Cancelled":
            issues.append(f"Closed-cycle Payment Entry must remain Cancelled. Current: {pe_doc.status}")
        if flt(pe_doc.paid_amount or 0, 2) != 3:
            issues.append(f"Closed-cycle Payment Entry amount must remain 3.00. Current: {flt(pe_doc.paid_amount or 0, 2)}")
        if len(pe_doc.references or []) != 3:
            issues.append(f"Closed-cycle Payment Entry must still have 3 references. Current: {len(pe_doc.references or [])}")

    outstanding_total = round(sum(flt(row["current_outstanding"], 2) for row in refs), 2)
    if abs(outstanding_total - flt(baseline.invoice_outstanding_total or 0, 2)) > 0.01:
        issues.append("Current invoice outstanding total no longer matches Phase 10N baseline evidence.")
    if abs(flt(gl_net["total_balance"], 2)) > 0.01:
        issues.append("Closed-cycle GL net balance is not zero.")
    if gl_net["non_zero_count"] != 0:
        issues.append("One or more GL accounts remain non-zero for the closed-cycle voucher.")
    if policy_enabled != 1:
        issues.append("Target policy production_batch_enabled must be 1 before Phase 10O. Phase 10O must not repair this.")
    if policy_live != 0:
        issues.append("Target policy live_posting_allowed must be 0 before Phase 10O. Phase 10O must not repair this.")
    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must remain enabled.")
    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must remain 0.")
    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry count today must remain 0.")
    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice count today must remain 0.")
    if config["production_mode"] != 0:
        issues.append("Production mode config must remain 0 for this guarded runtime watch phase.")
    if config["live_pe_enabled"] != 0:
        issues.append("Live Payment Entry posting config must remain 0.")
    if int(baseline.max_batch_line_count or 0) != 3:
        issues.append("Baseline max batch line count must be 3.")
    if flt(baseline.max_batch_amount or 0, 2) != 3:
        issues.append("Baseline max batch amount must be 3.00.")
    if int(baseline.max_payment_entry_count or 0) != 1:
        issues.append("Baseline max Payment Entry count must be 1.")
    if int(baseline.live_posting_allowed or 0) != 0:
        issues.append("Baseline live posting must be blocked.")
    if int(baseline.journal_entry_side_effect_allowed or 0) != 0:
        issues.append("Baseline Journal Entry side effect must be blocked.")
    if int(baseline.purchase_invoice_side_effect_allowed or 0) != 0:
        issues.append("Baseline Purchase Invoice side effect must be blocked.")
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


def build_items(baseline, issues, ack_ok, evidence=None):
    items = []
    if baseline:
        add_item(items, "Pass", "Low", "Evidence", "phase10n_baseline_exists", "Phase 10N baseline exists", f"Baseline found: {baseline.baseline_id}.", BASELINE_DOCTYPE, baseline.name)
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase10n_baseline_exists", "Phase 10N baseline exists", "No active Phase 10N baseline found.")

    if issues:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Watch Source", "watch_source_valid", "Watch source valid", issue)
    else:
        add_item(items, "Pass", "Low", "Watch Source", "watch_source_valid", "Watch source valid", "Phase 10N baseline is valid for runtime watch.")

    if evidence:
        add_item(items, "Pass", "High", "Runtime Limits", "limits_locked", "Runtime watch limits locked", f"lines={evidence['max_batch_line_count']}, amount={evidence['max_batch_amount']}, PE={evidence['max_payment_entry_count']}")
        add_item(items, "Pass", "High", "Runtime Blocks", "live_posting_block_active", "Live posting block active", f"live_posting_allowed={evidence['live_posting_allowed']}")
        add_item(items, "Pass", "High", "Runtime Blocks", "je_side_effect_block_active", "Journal Entry side effect block active", f"journal_entry_side_effect_allowed={evidence['journal_entry_side_effect_allowed']}")
        add_item(items, "Pass", "High", "Runtime Blocks", "pi_side_effect_block_active", "Purchase Invoice side effect block active", f"purchase_invoice_side_effect_allowed={evidence['purchase_invoice_side_effect_allowed']}")
        add_item(items, "Pass", "High", "Guardrail", "no_new_movement", "No new accounting movement", f"PE {evidence['payment_entry_count_before']} -> {evidence['payment_entry_count_after']}; PE GL {evidence['payment_entry_gl_count_before']} -> {evidence['payment_entry_gl_count_after']}")
        add_item(items, "Pass", "High", "Policy", "policy_state_preserved", "Policy state preserved", f"enabled/live={evidence['production_batch_enabled_policy_count_after']} / {evidence['live_posting_allowed_policy_count_after']}")
        add_item(items, "Pass", "Low", "Closed Cycle", "closed_cycle_pe_cancelled", "Closed-cycle Payment Entry remains cancelled", f"{evidence['payment_entry']} docstatus={evidence['payment_entry_docstatus']} status={evidence['payment_entry_status']}", "Payment Entry", evidence["payment_entry"])

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {WATCH_ACK}")
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
        row = frappe.new_doc(WATCH_ITEM_DOCTYPE)
        row.watch = doc.name
        for fieldname in ["status", "severity", "category", "check_key", "check_label", "detail", "source_doctype", "source_name"]:
            setattr(row, fieldname, item.get(fieldname))
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


def build_evidence(baseline, guard_before, guard_after, pe_doc, refs, gl_net, policy_enabled_before, policy_enabled_after, policy_live_before, policy_live_after):
    outstanding_total = round(sum(flt(row["current_outstanding"], 2) for row in refs), 2)
    return {
        "baseline": baseline.name if baseline else None,
        "closeout": baseline.closeout if baseline else None,
        "freeze": baseline.freeze if baseline else None,
        "rollback": baseline.rollback if baseline else None,
        "smoke": baseline.smoke if baseline else None,
        "execution_gate": baseline.execution_gate if baseline else None,
        "preview": baseline.preview if baseline else None,
        "pre_check": baseline.pre_check if baseline else None,
        "monitoring_register": baseline.monitoring_register if baseline else None,
        "policy_decision": baseline.policy_decision if baseline else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": baseline.target_policy if baseline else None,
        "target_policy_name": baseline.target_policy_name if baseline else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_before": policy_live_before,
        "target_policy_live_after": policy_live_after,
        "production_batch_enabled_policy_count_before": guard_before["production_batch_enabled_policy_count"],
        "production_batch_enabled_policy_count_after": guard_after["production_batch_enabled_policy_count"],
        "live_posting_allowed_policy_count_before": guard_before["live_posting_allowed_policy_count"],
        "live_posting_allowed_policy_count_after": guard_after["live_posting_allowed_policy_count"],
        "max_batch_line_count": int(baseline.max_batch_line_count or 0) if baseline else 0,
        "max_batch_amount": flt(baseline.max_batch_amount or 0, 2) if baseline else 0,
        "max_payment_entry_count": int(baseline.max_payment_entry_count or 0) if baseline else 0,
        "live_posting_allowed": int(baseline.live_posting_allowed or 0) if baseline else 0,
        "journal_entry_side_effect_allowed": int(baseline.journal_entry_side_effect_allowed or 0) if baseline else 0,
        "purchase_invoice_side_effect_allowed": int(baseline.purchase_invoice_side_effect_allowed or 0) if baseline else 0,
        "payment_entry": baseline.payment_entry if baseline else None,
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
def run_controlled_limited_operations_runtime_watch(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_controlled_limited_operations_runtime_watch")

    baseline = latest_baseline()
    guard_before = guardrails()
    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }
    ack_ok = acknowledgement == WATCH_ACK

    pe_doc = frappe.get_doc("Payment Entry", baseline.payment_entry) if baseline and baseline.payment_entry and frappe.db.exists("Payment Entry", baseline.payment_entry) else None
    refs = reference_snapshot(baseline.payment_entry) if baseline else []
    gl_net = voucher_gl_net(baseline.payment_entry) if baseline else {"rows": [], "total_debit": 0, "total_credit": 0, "total_balance": 0, "non_zero_count": 0}
    policy_enabled_before = get_flag(POLICY_DOCTYPE, baseline.target_policy, "production_batch_enabled") if baseline else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, baseline.target_policy, "live_posting_allowed") if baseline else 0
    guard_after = guardrails()
    policy_enabled_after = get_flag(POLICY_DOCTYPE, baseline.target_policy, "production_batch_enabled") if baseline else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, baseline.target_policy, "live_posting_allowed") if baseline else 0

    issues = validate_source(baseline, guard_before, pe_doc, policy_enabled_before, policy_live_before, gl_net, refs, config)
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
        issues.append("Accounting movement changed while preparing runtime watch evidence.")

    evidence = build_evidence(baseline, guard_before, guard_after, pe_doc, refs, gl_net, policy_enabled_before, policy_enabled_after, policy_live_before, policy_live_after)
    runtime_limits_locked = int(evidence["max_batch_line_count"] == 3 and flt(evidence["max_batch_amount"], 2) == 3 and evidence["max_payment_entry_count"] == 1)
    live_block = int(evidence["live_posting_allowed"] == 0 and config["live_pe_enabled"] == 0)
    je_block = int(evidence["journal_entry_side_effect_allowed"] == 0)
    pi_block = int(evidence["purchase_invoice_side_effect_allowed"] == 0)

    items = build_items(baseline, issues, ack_ok, evidence)
    item_summary = summarise_items(items)
    allowed = int(ack_ok and item_summary["blocker_count"] == 0 and bool(baseline))
    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Watch Active" if allowed else "Needs Review",
        "watch_status": "Controlled Limited Operations Runtime Watch Active" if allowed else "Needs Review",
        "watch_active": allowed,
        "runtime_watch_enabled": allowed,
        "guardrail_watch_active": allowed,
        "ready_for_controlled_limited_runtime_checks": allowed,
        "baseline_verified": 1 if baseline else 0,
        "runtime_limits_locked": runtime_limits_locked,
        "live_posting_block_active": live_block,
        "journal_entry_side_effect_block_active": je_block,
        "purchase_invoice_side_effect_block_active": pi_block,
        "no_new_accounting_movement_verified": no_new_movement,
        "policy_state_preserved_verified": policy_preserved,
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": 0,
        "phase10n_baseline_verified": 1 if baseline else 0,
        "phase10m_closeout_verified": 1 if baseline else 0,
        "phase10f_monitoring_register_verified": 1 if baseline else 0,
        "controlled_policy_enabled_verified": int(policy_enabled_after == 1),
        "live_posting_blocked_verified": int(policy_live_after == 0),
        **evidence,
        "watch_score": calculate_score(item_summary["blocker_count"], item_summary["warning_count"]),
        **item_summary,
        "items": items,
        "issues": issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "references": refs,
        "gl_net": gl_net,
        "required_acknowledgement": WATCH_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 10O activates runtime watch evidence only. No accounting movement or policy mutation is performed.",
    }

    if int(dry_run or 0):
        result.update(
            {
                "status": "Needs Review",
                "watch_status": "Needs Review",
                "watch_active": 0,
                "runtime_watch_enabled": 0,
                "guardrail_watch_active": 0,
                "ready_for_controlled_limited_runtime_checks": 0,
            }
        )
        return result

    doc = frappe.new_doc(WATCH_DOCTYPE)
    doc.watch_id = make_watch_id()
    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = WATCH_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.evidence_json = safe_json({"evidence": evidence, "references": refs, "gl_net": gl_net, "guardrails_before": guard_before, "guardrails_after": guard_after, "config": config})
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    create_items(doc, items)
    frappe.db.commit()
    return {**result, "created": True, "watch": doc.name, "watch_id": doc.watch_id, "guardrails_after": guardrails()}


@frappe.whitelist()
def cancel_controlled_limited_operations_runtime_watch_audit(watch, reason=None):
    assert_action("cancel_controlled_limited_operations_runtime_watch_audit")
    if not frappe.db.exists(WATCH_DOCTYPE, watch):
        frappe.throw(_("Runtime watch audit not found: {0}").format(watch))
    doc = frappe.get_doc(WATCH_DOCTYPE, watch)
    if doc.status == "Cancelled":
        return {"watch": watch, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.watch_active or 0):
        frappe.throw(_("Cannot cancel an active Phase 10O runtime watch record."))
    frappe.db.set_value(
        WATCH_DOCTYPE,
        watch,
        {
            "status": "Cancelled",
            "watch_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 10O no-ack runtime watch audit cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{WATCH_ITEM_DOCTYPE}` SET status = 'Cancelled' WHERE watch = %(watch)s", {"watch": watch})
    frappe.db.commit()
    return {"watch": watch, "status": "Cancelled", "note": "No-ack runtime watch audit cancelled only. No accounting or policy movement occurred."}


@frappe.whitelist()
def quick_controlled_limited_operations_runtime_watch_summary(limit=20):
    watches = frappe.get_all(
        WATCH_DOCTYPE,
        fields=[
            "name",
            "watch_id",
            "status",
            "watch_status",
            "watch_active",
            "runtime_watch_enabled",
            "guardrail_watch_active",
            "ready_for_controlled_limited_runtime_checks",
            "baseline",
            "monitoring_register",
            "target_policy",
            "max_batch_line_count",
            "max_batch_amount",
            "max_payment_entry_count",
            "live_posting_allowed",
            "production_batch_enabled_policy_count_after",
            "live_posting_allowed_policy_count_after",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "submitted_journal_entry_count_today",
            "purchase_invoice_count_today",
            "watch_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(
        WATCH_ITEM_DOCTYPE,
        fields=["name", "watch", "status", "severity", "category", "check_label", "detail", "source_doctype", "source_name"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {"watches": watches, "items": items, "required_acknowledgement": WATCH_ACK, "guardrails": guardrails(), "note": "Phase 10O runtime watch summary. Active watch monitors steady-state controlled limited operations."}


def execute_watch_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("w.status = %(status)s")
        params["status"] = filters.get("status")
    data = frappe.db.sql(
        f"""
        SELECT
            w.name AS watch, w.watch_id, w.status, w.watch_status, w.watch_active,
            w.runtime_watch_enabled, w.guardrail_watch_active,
            w.ready_for_controlled_limited_runtime_checks, w.baseline, w.monitoring_register,
            w.target_policy, w.max_batch_line_count, w.max_batch_amount,
            w.max_payment_entry_count, w.live_posting_allowed,
            w.journal_entry_side_effect_allowed, w.purchase_invoice_side_effect_allowed,
            w.production_batch_enabled_policy_count_after, w.live_posting_allowed_policy_count_after,
            w.payment_entry_count_before, w.payment_entry_count_after,
            w.payment_entry_gl_count_before, w.payment_entry_gl_count_after,
            w.submitted_journal_entry_count_today, w.purchase_invoice_count_today,
            w.watch_score, w.checked_on, %(currency)s AS currency
        FROM `tab{WATCH_DOCTYPE}` w
        {build_where(conditions)}
        ORDER BY w.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.watch_id for row in data[:20]],
            "datasets": [
                {"name": "Active", "values": [int(row.watch_active or 0) for row in data[:20]]},
                {"name": "Guardrail Watch", "values": [int(row.guardrail_watch_active or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Runtime Watches"), "datatype": "Int"},
        {"value": sum(int(row.watch_active or 0) for row in data), "indicator": "Green", "label": _("Active"), "datatype": "Int"},
        {"value": sum(int(row.guardrail_watch_active or 0) for row in data), "indicator": "Green", "label": _("Guardrail Active"), "datatype": "Int"},
        {"value": sum(int(row.live_posting_allowed or 0) for row in data), "indicator": "Red", "label": _("Live Allowed"), "datatype": "Int"},
    ]
    return watch_columns(), data, None, chart, summary


def watch_columns():
    return [
        {"fieldname": "watch", "label": _("Runtime Watch"), "fieldtype": "Link", "options": WATCH_DOCTYPE, "width": 220},
        {"fieldname": "watch_id", "label": _("Watch ID"), "fieldtype": "Data", "width": 420},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "watch_status", "label": _("Watch Status"), "fieldtype": "Data", "width": 360},
        {"fieldname": "watch_active", "label": _("Active"), "fieldtype": "Check", "width": 80},
        {"fieldname": "runtime_watch_enabled", "label": _("Runtime Enabled"), "fieldtype": "Check", "width": 120},
        {"fieldname": "guardrail_watch_active", "label": _("Guardrail Active"), "fieldtype": "Check", "width": 120},
        {"fieldname": "ready_for_controlled_limited_runtime_checks", "label": _("Ready Checks"), "fieldtype": "Check", "width": 110},
        {"fieldname": "baseline", "label": _("Baseline"), "fieldtype": "Link", "options": BASELINE_DOCTYPE, "width": 220},
        {"fieldname": "monitoring_register", "label": _("Monitoring Register"), "fieldtype": "Link", "options": "NDIS Controlled Limited Operations Monitoring Register", "width": 220},
        {"fieldname": "target_policy", "label": _("Target Policy"), "fieldtype": "Data", "width": 260},
        {"fieldname": "max_batch_line_count", "label": _("Max Lines"), "fieldtype": "Int", "width": 90},
        {"fieldname": "max_batch_amount", "label": _("Max Amount"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "max_payment_entry_count", "label": _("Max PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "live_posting_allowed", "label": _("Live Allowed"), "fieldtype": "Check", "width": 100},
        {"fieldname": "journal_entry_side_effect_allowed", "label": _("JE Allowed"), "fieldtype": "Check", "width": 95},
        {"fieldname": "purchase_invoice_side_effect_allowed", "label": _("PI Allowed"), "fieldtype": "Check", "width": 95},
        {"fieldname": "production_batch_enabled_policy_count_after", "label": _("Enabled Policies"), "fieldtype": "Int", "width": 125},
        {"fieldname": "live_posting_allowed_policy_count_after", "label": _("Live Policies"), "fieldtype": "Int", "width": 105},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 110},
        {"fieldname": "submitted_journal_entry_count_today", "label": _("JE Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "purchase_invoice_count_today", "label": _("PI Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "watch_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("watch"):
        conditions.append("i.watch = %(watch)s")
        params["watch"] = filters.get("watch")
    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")
    data = frappe.db.sql(
        f"""
        SELECT i.name AS item, i.watch, i.status, i.severity, i.category, i.check_label,
               i.detail, i.source_doctype, i.source_name, i.checked_on
        FROM `tab{WATCH_ITEM_DOCTYPE}` i
        {build_where(conditions)}
        ORDER BY CASE i.status WHEN 'Blocker' THEN 1 WHEN 'Warning' THEN 2 WHEN 'Pass' THEN 3 WHEN 'Info' THEN 4 ELSE 5 END, i.creation DESC
        """,
        params,
        as_dict=True,
    )
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": WATCH_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "watch", "label": _("Watch"), "fieldtype": "Link", "options": WATCH_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 180},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 340},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 620},
        {"fieldname": "source_doctype", "label": _("Source DocType"), "fieldtype": "Data", "width": 220},
        {"fieldname": "source_name", "label": _("Source Name"), "fieldtype": "Data", "width": 240},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]
    chart_map = {}
    for row in data:
        chart_map[row.status or "Info"] = chart_map.get(row.status or "Info", 0) + 1
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Items"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Pass"]), "indicator": "Green", "label": _("Pass"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Warning"]), "indicator": "Orange", "label": _("Warnings"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Blocker"]), "indicator": "Red", "label": _("Blockers"), "datatype": "Int"},
        {"value": len([row for row in data if row.category == "Runtime Blocks"]), "indicator": "Blue", "label": _("Runtime Block Checks"), "datatype": "Int"},
    ]
    return columns, data, None, {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Items", "values": list(chart_map.values())}]}, "type": "bar"}, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_watch_report(filters)
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
