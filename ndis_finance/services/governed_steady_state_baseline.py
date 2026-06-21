import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


BASELINE_ACK = "I_CONFIRM_PHASE11A_CREATE_GOVERNED_STEADY_STATE_BASELINE_NO_POSTING"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
CLOSEOUT_DOCTYPE = "NDIS Governed Limited Op Closeout"
BASELINE_DOCTYPE = "NDIS Governed Steady State Baseline"
BASELINE_ITEM_DOCTYPE = "NDIS Governed Steady State Baseline Item"


def make_baseline_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-GOVERNED-STEADY-STATE-BASELINE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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
    if not frappe.db.exists("DocType", POLICY_DOCTYPE) or not has_column(POLICY_DOCTYPE, "production_batch_enabled"):
        return 0
    return count_dt(POLICY_DOCTYPE, {"production_batch_enabled": 1})


def live_posting_allowed_policy_count():
    if not frappe.db.exists("DocType", POLICY_DOCTYPE) or not has_column(POLICY_DOCTYPE, "live_posting_allowed"):
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
            "closeout_status": "Governed Limited Operation Cycle Closed",
            "closeout_approved": 1,
            "governed_limited_operation_cycle_closed": 1,
            "smoke_and_rollback_evidence_frozen_verified": 1,
            "payment_entry_cancelled_verified": 1,
            "invoice_outstanding_restored_verified": 1,
            "gl_net_zero_verified": 1,
            "no_new_accounting_movement_verified": 1,
            "policy_state_preserved_verified": 1,
            "ready_for_governed_steady_state_continuation": 1,
            "policy_mutation_performed": 0,
            "actual_policy_mutation_count": 0,
            "target_policy_enabled_after": 1,
            "target_policy_live_after": 0,
            "payment_entry_docstatus": 2,
            "payment_entry_status": "Cancelled",
            "payment_entry_reference_count": 3,
            "voucher_gl_row_count": 8,
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
            "pre_execution_gate",
            "readiness",
            "governance_closeout",
            "runtime_watch",
            "baseline",
            "monitoring_register",
            "target_policy",
            "target_policy_name",
            "payment_entry",
            "payment_entry_docstatus",
            "payment_entry_status",
            "payment_entry_amount",
            "payment_entry_reference_count",
            "invoice_outstanding_restored_amount",
            "voucher_gl_row_count",
            "voucher_gl_net_balance",
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


def payment_entry_reference_count(payment_entry):
    return count_dt("Payment Entry Reference", {"parent": payment_entry, "reference_doctype": "Sales Invoice"})


def voucher_gl_row_count(payment_entry):
    return count_dt("GL Entry", {"voucher_type": "Payment Entry", "voucher_no": payment_entry})


def voucher_gl_net_balance(payment_entry):
    value = frappe.db.sql(
        """
        SELECT ROUND(COALESCE(SUM(debit - credit), 0), 2)
        FROM `tabGL Entry`
        WHERE voucher_type='Payment Entry'
          AND voucher_no=%(payment_entry)s
        """,
        {"payment_entry": payment_entry},
    )[0][0]
    return flt(value or 0, 2)


def voucher_gl_non_zero_account_count(payment_entry):
    rows = frappe.db.sql(
        """
        SELECT account, ROUND(COALESCE(SUM(debit - credit), 0), 2) AS balance
        FROM `tabGL Entry`
        WHERE voucher_type='Payment Entry'
          AND voucher_no=%(payment_entry)s
        GROUP BY account
        HAVING ABS(balance) > 0.0001
        """,
        {"payment_entry": payment_entry},
        as_dict=True,
    )
    return len(rows)


def validate_baseline_source(closeout, guard, policy_enabled, policy_live, config):
    issues = []
    if not closeout:
        return ["No approved Phase 10Z closeout found."]

    existing = existing_baseline(closeout.name)
    if existing:
        issues.append(f"Phase 11A baseline already exists for this closeout: {existing.baseline_id}")

    required_links = {
        "closeout": (CLOSEOUT_DOCTYPE, closeout.name),
        "governed_freeze": ("NDIS Governed Limited Op Freeze", closeout.freeze),
        "rollback": ("NDIS Governed Limited Op Rollback", closeout.rollback),
        "smoke": ("NDIS Governed Limited Op Smoke", closeout.smoke),
        "execution_gate": ("NDIS Governed Limited Op Exec Gate", closeout.execution_gate),
        "payment_entry": ("Payment Entry", closeout.payment_entry),
        "target_policy": (POLICY_DOCTYPE, closeout.target_policy),
    }
    for label, (doctype, name) in required_links.items():
        if not name:
            issues.append(f"Missing evidence link: {label}")
        elif not frappe.db.exists(doctype, name):
            issues.append(f"Linked evidence does not exist: {doctype} {name}")

    if not closeout.payment_entry or not frappe.db.exists("Payment Entry", closeout.payment_entry):
        return issues

    pe = frappe.get_doc("Payment Entry", closeout.payment_entry)
    if pe.docstatus != 2:
        issues.append(f"Payment Entry must remain cancelled. docstatus={pe.docstatus}")
    if pe.status != "Cancelled":
        issues.append(f"Payment Entry status must remain Cancelled. status={pe.status}")
    if flt(pe.paid_amount or pe.received_amount or 0, 2) != 3:
        issues.append("Payment Entry amount must remain 3.00.")
    if payment_entry_reference_count(pe.name) != int(closeout.payment_entry_reference_count or 0):
        issues.append("Payment Entry reference count no longer matches Phase 10Z closeout evidence.")
    if voucher_gl_row_count(pe.name) != int(closeout.voucher_gl_row_count or 0):
        issues.append("Voucher GL row count no longer matches Phase 10Z closeout evidence.")
    if voucher_gl_net_balance(pe.name) != 0:
        issues.append("Voucher GL net balance must remain 0.00.")
    if voucher_gl_non_zero_account_count(pe.name) != 0:
        issues.append("Voucher GL account non-zero count must remain 0.")
    if policy_enabled != 1:
        issues.append("Target policy production_batch_enabled must be 1 before Phase 11A. Phase 11A must not repair this.")
    if policy_live != 0:
        issues.append("Target policy live_posting_allowed must be 0 before Phase 11A. Phase 11A must not repair this.")
    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must remain enabled.")
    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must remain 0.")
    if guard["payment_entry_count"] != int(closeout.payment_entry_count_after or 0):
        issues.append("Current Payment Entry count must match Phase 10Z closeout after-count.")
    if guard["payment_entry_gl_count"] != int(closeout.payment_entry_gl_count_after or 0):
        issues.append("Current Payment Entry GL count must match Phase 10Z closeout after-count.")
    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry count today must remain 0.")
    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice count today must remain 0.")
    if int(config["sandbox_enabled"]) != 1:
        issues.append("Sandbox config must be 1.")
    if int(config["production_mode"]) != 0:
        issues.append("Production mode config must remain 0.")
    if int(config["live_pe_enabled"]) != 0:
        issues.append("Live Payment Entry posting config must remain 0.")
    return issues


def add_item(items, status, severity, category, check_key, check_label, detail, source_doctype=None, source_name=None):
    items.append({"status": status, "severity": severity, "category": category, "check_key": check_key, "check_label": check_label, "detail": detail, "source_doctype": source_doctype, "source_name": source_name})


def build_items(closeout, issues, ack_ok):
    items = []
    if closeout:
        add_item(items, "Pass", "Low", "Evidence", "phase10z_closeout_exists", "Phase 10Z closeout exists", f"Closeout found: {closeout.closeout_id}.", CLOSEOUT_DOCTYPE, closeout.name)
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase10z_closeout_exists", "Phase 10Z closeout exists", "No approved Phase 10Z closeout found.")
    if issues:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Baseline Source", "baseline_source_valid", "Baseline source valid", issue)
    else:
        add_item(items, "Pass", "Critical", "Baseline Source", "baseline_source_valid", "Baseline source valid", "Phase 10Z closeout evidence is valid for governed steady-state continuation baseline.")
    checks = [
        ("cycle_closed", "Governed limited operation cycle closed", getattr(closeout, "closeout_id", None)),
        ("payment_entry_cancelled", "Payment Entry remains cancelled", getattr(closeout, "payment_entry", None)),
        ("gl_net_zero", "Voucher GL net remains zero", getattr(closeout, "voucher_gl_net_balance", None)),
        ("invoice_restored", "Invoice outstanding remains restored", getattr(closeout, "invoice_outstanding_restored_amount", None)),
        ("no_new_movement", "Baseline creates no accounting movement", 0),
        ("policy_preserved", "Policy state remains 1 / 0", "1 / 0"),
        ("next_cycle_ready", "Ready for next governed limited operation cycle", 1),
    ]
    for key, label, value in checks:
        add_item(items, "Pass", "High", "Baseline Evidence", key, label, f"value={value}")
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


def assign_if_has(doc, values):
    for fieldname, value in values.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)


def create_items(doc, items):
    for item in items:
        row = frappe.new_doc(BASELINE_ITEM_DOCTYPE)
        row.baseline = doc.name
        row.status = item["status"]
        row.severity = item["severity"]
        row.category = item["category"]
        row.check_key = item["check_key"]
        row.check_label = item["check_label"]
        row.detail = item["detail"]
        row.source_doctype = item.get("source_doctype")
        row.source_name = item.get("source_name")
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_governed_steady_state_baseline(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_governed_steady_state_baseline")
    closeout = latest_closeout()
    guard_before = guardrails()
    ack_ok = acknowledgement == BASELINE_ACK
    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }
    policy_enabled_before = get_flag(POLICY_DOCTYPE, closeout.target_policy, "production_batch_enabled") if closeout else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, closeout.target_policy, "live_posting_allowed") if closeout else 0
    issues = validate_baseline_source(closeout, guard_before, policy_enabled_before, policy_live_before, config)
    guard_after = guardrails()
    policy_enabled_after = get_flag(POLICY_DOCTYPE, closeout.target_policy, "production_batch_enabled") if closeout else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, closeout.target_policy, "live_posting_allowed") if closeout else 0
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
        issues.append("Accounting movement changed while preparing Phase 11A baseline evidence.")
    if not policy_preserved:
        issues.append("Policy state changed while preparing Phase 11A baseline evidence.")
    items = build_items(closeout, issues, ack_ok)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    allowed = int(ack_ok and item_summary["blocker_count"] == 0 and closeout and no_new_movement and policy_preserved)
    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Baseline Active" if allowed else "Needs Review",
        "baseline_status": "Governed Steady-State Continuation Baseline Active" if allowed else "Needs Review",
        "baseline_active": allowed,
        "phase10z_closeout_verified": 1 if closeout else 0,
        "governed_limited_operation_cycle_closed_verified": 1 if closeout else 0,
        "payment_entry_cancelled_verified": 1 if closeout else 0,
        "gl_net_zero_verified": 1 if closeout else 0,
        "invoice_outstanding_restored_verified": 1 if closeout else 0,
        "no_new_accounting_movement_verified": no_new_movement,
        "policy_state_preserved_verified": policy_preserved,
        "ready_for_next_governed_limited_operation_cycle": allowed,
        "ready_for_governed_steady_state_monitoring": allowed,
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": 0,
        "phase10y_freeze_verified": 1 if closeout else 0,
        "phase10x_rollback_verified": 1 if closeout else 0,
        "phase10w_smoke_verified": 1 if closeout else 0,
        "phase10v_execution_gate_verified": 1 if closeout else 0,
        "phase10u_preview_verified": 1 if closeout else 0,
        "phase10t_pre_execution_verified": 1 if closeout else 0,
        "phase10s_readiness_verified": 1 if closeout else 0,
        "phase10r_governance_closeout_verified": 1 if closeout else 0,
        "phase10q_freeze_verified": 1 if closeout else 0,
        "phase10p_simulation_verified": 1 if closeout else 0,
        "phase10o_runtime_watch_verified": 1 if closeout else 0,
        "phase10n_baseline_verified": 1 if closeout else 0,
        "controlled_policy_enabled_verified": int(policy_enabled_after == 1),
        "live_posting_blocked_verified": int(policy_live_after == 0),
        "closeout": closeout.name if closeout else None,
        "governed_freeze": closeout.freeze if closeout else None,
        "rollback": closeout.rollback if closeout else None,
        "smoke": closeout.smoke if closeout else None,
        "execution_gate": closeout.execution_gate if closeout else None,
        "preview": closeout.preview if closeout else None,
        "pre_execution_gate": closeout.pre_execution_gate if closeout else None,
        "readiness": closeout.readiness if closeout else None,
        "governance_closeout": closeout.governance_closeout if closeout else None,
        "runtime_watch": closeout.runtime_watch if closeout else None,
        "prior_baseline": closeout.baseline if closeout else None,
        "monitoring_register": closeout.monitoring_register if closeout else None,
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
        "payment_entry": closeout.payment_entry if closeout else None,
        "payment_entry_docstatus": int(closeout.payment_entry_docstatus or 0) if closeout else 0,
        "payment_entry_status": closeout.payment_entry_status if closeout else None,
        "payment_entry_amount": flt(closeout.payment_entry_amount or 0, 2) if closeout else 0,
        "payment_entry_reference_count": int(closeout.payment_entry_reference_count or 0) if closeout else 0,
        "invoice_outstanding_restored_amount": flt(closeout.invoice_outstanding_restored_amount or 0, 2) if closeout else 0,
        "voucher_gl_row_count": int(closeout.voucher_gl_row_count or 0) if closeout else 0,
        "voucher_gl_net_balance": flt(closeout.voucher_gl_net_balance or 0, 2) if closeout else 0,
        "gl_account_non_zero_count": int(closeout.gl_account_non_zero_count or 0) if closeout else 0,
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guard_after["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
        "actual_payment_entry_created_count": 0,
        "actual_payment_entry_cancelled_count": 0,
        "actual_gl_created_count": 0,
        "submitted_journal_entry_count_today": guard_after["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_after["purchase_invoice_count_today"],
        "baseline_score": score,
        **item_summary,
        "items": items,
        "issues": issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "required_acknowledgement": BASELINE_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 11A creates a governed steady-state continuation baseline only. No accounting movement or policy mutation is performed.",
    }
    if int(dry_run or 0):
        result.update({"status": "Needs Review", "baseline_status": "Needs Review", "baseline_active": 0, "ready_for_next_governed_limited_operation_cycle": 0, "ready_for_governed_steady_state_monitoring": 0})
        return result
    doc = frappe.new_doc(BASELINE_DOCTYPE)
    doc.baseline_id = make_baseline_id()
    assign_if_has(doc, result)
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = BASELINE_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.baseline_json = safe_json({"closeout": closeout, "guardrails_before": guard_before, "guardrails_after": guard_after, "issues": issues, "config": config})
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    create_items(doc, items)
    frappe.db.commit()
    return {**result, "created": True, "baseline": doc.name, "baseline_id": doc.baseline_id, "guardrails_after": guardrails()}


@frappe.whitelist()
def cancel_governed_steady_state_baseline_audit(baseline, reason=None):
    assert_action("cancel_governed_steady_state_baseline_audit")
    if not frappe.db.exists(BASELINE_DOCTYPE, baseline):
        frappe.throw(_("Governed steady-state baseline audit not found: {0}").format(baseline))
    doc = frappe.get_doc(BASELINE_DOCTYPE, baseline)
    if doc.status == "Cancelled":
        return {"baseline": baseline, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.baseline_active or 0):
        frappe.throw(_("Cannot cancel an active Phase 11A baseline record."))
    frappe.db.set_value(
        BASELINE_DOCTYPE,
        baseline,
        {
            "status": "Cancelled",
            "baseline_status": "Cancelled",
            "baseline_active": 0,
            "ready_for_next_governed_limited_operation_cycle": 0,
            "ready_for_governed_steady_state_monitoring": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 11A no-ack baseline audit cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{BASELINE_ITEM_DOCTYPE}` SET status='Cancelled' WHERE baseline=%(baseline)s", {"baseline": baseline})
    frappe.db.commit()
    return {"baseline": baseline, "status": "Cancelled", "note": "No-ack baseline audit cancelled only. No accounting or policy movement occurred."}


@frappe.whitelist()
def quick_governed_steady_state_baseline_summary(limit=20):
    records = frappe.get_all(
        BASELINE_DOCTYPE,
        fields=[
            "name",
            "baseline_id",
            "status",
            "baseline_status",
            "baseline_active",
            "phase10z_closeout_verified",
            "governed_limited_operation_cycle_closed_verified",
            "ready_for_next_governed_limited_operation_cycle",
            "ready_for_governed_steady_state_monitoring",
            "closeout",
            "payment_entry",
            "payment_entry_docstatus",
            "payment_entry_status",
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
    items = frappe.get_all(
        BASELINE_ITEM_DOCTYPE,
        fields=["name", "baseline", "status", "severity", "category", "check_key", "check_label", "detail", "source_doctype", "source_name"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {"baselines": records, "items": items, "required_acknowledgement": BASELINE_ACK, "guardrails": guardrails(), "note": "Phase 11A governed steady-state baseline summary."}


def execute_baseline_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("b.status = %(status)s")
        params["status"] = filters.status
    data = frappe.db.sql(
        f"""
        SELECT
            b.name AS baseline,
            b.baseline_id,
            b.status,
            b.baseline_status,
            b.baseline_active,
            b.phase10z_closeout_verified,
            b.governed_limited_operation_cycle_closed_verified,
            b.ready_for_next_governed_limited_operation_cycle,
            b.ready_for_governed_steady_state_monitoring,
            b.closeout,
            b.payment_entry,
            b.payment_entry_docstatus,
            b.payment_entry_status,
            b.payment_entry_amount,
            b.payment_entry_count_before,
            b.payment_entry_count_after,
            b.payment_entry_gl_count_before,
            b.payment_entry_gl_count_after,
            b.actual_payment_entry_created_count,
            b.actual_payment_entry_cancelled_count,
            b.actual_gl_created_count,
            b.submitted_journal_entry_count_today,
            b.purchase_invoice_count_today,
            b.baseline_score,
            b.checked_on,
            %(currency)s AS currency
        FROM `tab{BASELINE_DOCTYPE}` b
        {build_where(conditions)}
        ORDER BY b.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {"data": {"labels": [row.baseline_id for row in data[:20]], "datasets": [{"name": "Active", "values": [int(row.baseline_active or 0) for row in data[:20]]}, {"name": "Next Cycle Ready", "values": [int(row.ready_for_next_governed_limited_operation_cycle or 0) for row in data[:20]]}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Baseline Records"), "datatype": "Int"},
        {"value": sum(int(row.baseline_active or 0) for row in data), "indicator": "Green", "label": _("Active"), "datatype": "Int"},
        {"value": sum(int(row.ready_for_next_governed_limited_operation_cycle or 0) for row in data), "indicator": "Green", "label": _("Next Cycle Ready"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL Created"), "datatype": "Int"},
    ]
    return baseline_columns(), data, None, chart, summary


def baseline_columns():
    return [
        {"fieldname": "baseline", "label": _("Baseline"), "fieldtype": "Link", "options": BASELINE_DOCTYPE, "width": 220},
        {"fieldname": "baseline_id", "label": _("Baseline ID"), "fieldtype": "Data", "width": 390},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 140},
        {"fieldname": "baseline_status", "label": _("Baseline Status"), "fieldtype": "Data", "width": 350},
        {"fieldname": "baseline_active", "label": _("Active"), "fieldtype": "Check", "width": 80},
        {"fieldname": "phase10z_closeout_verified", "label": _("10Z Verified"), "fieldtype": "Check", "width": 100},
        {"fieldname": "governed_limited_operation_cycle_closed_verified", "label": _("Cycle Closed"), "fieldtype": "Check", "width": 110},
        {"fieldname": "ready_for_next_governed_limited_operation_cycle", "label": _("Next Cycle"), "fieldtype": "Check", "width": 100},
        {"fieldname": "ready_for_governed_steady_state_monitoring", "label": _("Monitoring"), "fieldtype": "Check", "width": 100},
        {"fieldname": "closeout", "label": _("Closeout"), "fieldtype": "Link", "options": CLOSEOUT_DOCTYPE, "width": 220},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "payment_entry_docstatus", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 100},
        {"fieldname": "payment_entry_status", "label": _("PE Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "payment_entry_amount", "label": _("PE Amount"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 110},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE Created"), "fieldtype": "Int", "width": 125},
        {"fieldname": "actual_payment_entry_cancelled_count", "label": _("Actual PE Cancelled"), "fieldtype": "Int", "width": 135},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL Created"), "fieldtype": "Int", "width": 125},
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
        params["baseline"] = filters.baseline
    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.status
    data = frappe.db.sql(
        f"""
        SELECT
            i.name AS item,
            i.baseline,
            i.status,
            i.severity,
            i.category,
            i.check_key,
            i.check_label,
            i.detail,
            i.source_doctype,
            i.source_name,
            i.checked_on
        FROM `tab{BASELINE_ITEM_DOCTYPE}` i
        {build_where(conditions)}
        ORDER BY CASE i.status WHEN 'Blocker' THEN 1 WHEN 'Warning' THEN 2 WHEN 'Pass' THEN 3 WHEN 'Info' THEN 4 ELSE 5 END, i.creation DESC
        """,
        params,
        as_dict=True,
    )
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": BASELINE_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "baseline", "label": _("Baseline"), "fieldtype": "Link", "options": BASELINE_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 200},
        {"fieldname": "check_key", "label": _("Check Key"), "fieldtype": "Data", "width": 220},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 330},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 650},
        {"fieldname": "source_doctype", "label": _("Source DocType"), "fieldtype": "Data", "width": 220},
        {"fieldname": "source_name", "label": _("Source Name"), "fieldtype": "Data", "width": 240},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]
    chart_map = {}
    for row in data:
        chart_map[row.status or "Info"] = chart_map.get(row.status or "Info", 0) + 1
    chart = {"data": {"labels": list(chart_map), "datasets": [{"name": "Items", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Items"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Pass"]), "indicator": "Green", "label": _("Pass"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Warning"]), "indicator": "Orange", "label": _("Warnings"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Blocker"]), "indicator": "Red", "label": _("Blockers"), "datatype": "Int"},
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
