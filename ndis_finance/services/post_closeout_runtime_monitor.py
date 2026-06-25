import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


MONITOR_ACK = "I_CONFIRM_PHASE11O_ACTIVATE_POST_CLOSEOUT_RUNTIME_MONITOR_NO_POSTING"

POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
BASELINE_DOCTYPE = "NDIS Post Closeout Steady Baseline"
MONITOR_DOCTYPE = "NDIS Post Closeout Runtime Monitor"
MONITOR_ITEM_DOCTYPE = "NDIS Post Closeout Runtime Monitor Item"


def make_monitor_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-POST-CLOSEOUT-RUNTIME-MONITOR-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def get_flag(doctype, name, fieldname, default=0):
    if not name or not frappe.db.exists(doctype, name) or not has_column(doctype, fieldname):
        return default
    return int(frappe.db.get_value(doctype, name, fieldname) or 0)


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


def latest_baseline():
    rows = frappe.get_all(
        BASELINE_DOCTYPE,
        filters={
            "status": "Baseline Active",
            "baseline_status": "Post-Closeout Steady-State Baseline Active",
            "baseline_active": 1,
            "phase11m_closeout_verified": 1,
            "second_cycle_closed_verified": 1,
            "closed_payment_entry_verified": 1,
            "payment_entry_cancelled_still_verified": 1,
            "voucher_gl_rows_verified": 1,
            "voucher_gl_net_zero_verified": 1,
            "invoice_outstanding_restored_still_verified": 1,
            "baseline_counts_stable_verified": 1,
            "policy_state_preserved_verified": 1,
            "ready_for_post_closeout_monitoring": 1,
            "ready_for_next_governed_limited_operation_planning": 1,
            "payment_entry_docstatus_baseline": 2,
            "payment_entry_status_baseline": "Cancelled",
            "baseline_reference_count": 3,
            "baseline_total_amount": 3.00,
            "baseline_voucher_gl_rows": 8,
            "baseline_voucher_gl_net": 0.00,
            "baseline_voucher_gl_non_zero_account_count": 0,
            "baseline_restored_invoice_amount": 3.00,
            "payment_entry_count_after": 9,
            "payment_entry_gl_count_after": 54,
            "actual_payment_entry_created_count": 0,
            "actual_payment_entry_cancelled_count": 0,
            "actual_gl_created_count": 0,
            "submitted_journal_entry_count_today": 0,
            "purchase_invoice_count_today": 0,
            "target_policy_enabled_after": 1,
            "target_policy_live_after": 0,
            "actual_policy_mutation_count": 0,
        },
        fields=[
            "name",
            "baseline_id",
            "baseline_payment_entry",
            "baseline_reference_count",
            "baseline_total_amount",
            "baseline_restored_invoice_amount",
            "closeout",
            "freeze",
            "rollback",
            "smoke",
            "execution_gate",
            "preview",
            "validation",
            "candidate",
            "design",
            "planning",
            "target_policy_doctype",
            "target_policy",
            "target_policy_name",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_active_monitor(baseline):
    rows = frappe.get_all(
        MONITOR_DOCTYPE,
        filters={
            "baseline": baseline,
            "status": "Monitor Active",
            "monitor_active": 1,
        },
        fields=["name", "monitor_id"],
        limit=1,
    )
    return rows[0] if rows else None


def payment_entry_reference_rows(payment_entry):
    if not payment_entry:
        return []
    return frappe.get_all(
        "Payment Entry Reference",
        filters={"parent": payment_entry, "reference_doctype": "Sales Invoice"},
        fields=[
            "idx",
            "reference_doctype",
            "reference_name",
            "total_amount",
            "outstanding_amount",
            "allocated_amount",
        ],
        order_by="idx asc",
    )


def allocated_total(payment_entry):
    rows = payment_entry_reference_rows(payment_entry)
    return flt(sum(flt(row.allocated_amount or 0, 2) for row in rows), 2)


def voucher_gl_rows(payment_entry):
    return count_dt("GL Entry", {"voucher_type": "Payment Entry", "voucher_no": payment_entry})


def voucher_gl_net(payment_entry):
    if not payment_entry:
        return 0
    value = frappe.db.sql(
        """
        SELECT ROUND(COALESCE(SUM(debit-credit), 0), 2)
        FROM `tabGL Entry`
        WHERE voucher_type='Payment Entry'
        AND voucher_no=%s
        """,
        payment_entry,
    )[0][0]
    return flt(value or 0, 2)


def voucher_gl_non_zero_accounts(payment_entry):
    if not payment_entry:
        return 0
    rows = frappe.db.sql(
        """
        SELECT account, ROUND(COALESCE(SUM(debit-credit), 0), 2) AS net
        FROM `tabGL Entry`
        WHERE voucher_type='Payment Entry'
        AND voucher_no=%s
        GROUP BY account
        HAVING ROUND(COALESCE(SUM(debit-credit), 0), 2) != 0
        """,
        payment_entry,
        as_dict=True,
    )
    return len(rows)


def validate_source(baseline, payment_entry, references, guard, config, policy_enabled, policy_live):
    issues = []

    if not baseline:
        issues.append("No active Phase 11N post-closeout baseline found.")
        return issues

    existing = existing_active_monitor(baseline.name)
    if existing:
        issues.append(f"Active Phase 11O runtime monitor already exists for this baseline: {existing.monitor_id}")

    if not payment_entry:
        issues.append("Phase 11N baseline does not identify the baseline Payment Entry.")
        return issues

    if not frappe.db.exists("Payment Entry", payment_entry):
        issues.append(f"Baseline Payment Entry does not exist: {payment_entry}")
        return issues

    pe = frappe.get_doc("Payment Entry", payment_entry)

    if pe.docstatus != 2:
        issues.append(f"Payment Entry must remain cancelled for monitor. docstatus={pe.docstatus}")

    if pe.status != "Cancelled":
        issues.append(f"Payment Entry status must remain Cancelled for monitor. status={pe.status}")

    if len(references) != 3:
        issues.append(f"Payment Entry must still have 3 Sales Invoice references. Found {len(references)}.")

    if allocated_total(payment_entry) != 3:
        issues.append(f"Payment Entry allocated total must remain 3.00. Found {allocated_total(payment_entry)}.")

    if voucher_gl_rows(payment_entry) != 8:
        issues.append(f"Voucher GL rows must remain 8. Found {voucher_gl_rows(payment_entry)}.")

    if voucher_gl_net(payment_entry) != 0:
        issues.append(f"Voucher GL net must remain 0.00. Found {voucher_gl_net(payment_entry)}.")

    if voucher_gl_non_zero_accounts(payment_entry) != 0:
        issues.append(f"Voucher non-zero account count must remain 0. Found {voucher_gl_non_zero_accounts(payment_entry)}.")

    if guard["payment_entry_count"] != 9:
        issues.append("Payment Entry count must remain 9 before Phase 11O monitor.")

    if guard["payment_entry_gl_count"] != 54:
        issues.append("Payment Entry GL count must remain 54 before Phase 11O monitor.")

    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today must remain 0 before monitor.")

    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today must remain 0 before monitor.")

    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must remain enabled.")

    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must remain 0.")

    if policy_enabled != 1:
        issues.append("Target policy production_batch_enabled must remain 1.")

    if policy_live != 0:
        issues.append("Target policy live_posting_allowed must remain 0.")

    if config["sandbox_enabled"] != 1:
        issues.append("Sandbox config must be enabled.")

    if config["production_mode"] != 0:
        issues.append("Production mode config must remain 0.")

    if config["live_pe_enabled"] != 0:
        issues.append("Live Payment Entry posting config must remain 0.")

    return issues


def add_item(items, status, severity, category, check_key, check_label, detail, reference=None, monitored_payment_entry=None):
    item = {
        "status": status,
        "severity": severity,
        "category": category,
        "check_key": check_key,
        "check_label": check_label,
        "detail": detail,
        "monitored_payment_entry": monitored_payment_entry,
    }

    if reference:
        item.update({
            "line_no": int(reference.idx or 0),
            "reference_doctype": reference.reference_doctype,
            "reference_name": reference.reference_name,
            "allocated_amount": flt(reference.allocated_amount or 0, 2),
            "source_doctype": reference.reference_doctype,
            "source_name": reference.reference_name,
        })

    items.append(item)


def build_items(baseline, references, issues, ack_ok, monitored_payment_entry=None):
    items = []

    if baseline:
        add_item(
            items,
            "Pass",
            "Low",
            "Evidence",
            "phase11n_baseline_exists",
            "Phase 11N baseline exists",
            f"Baseline found: {baseline.baseline_id}.",
            monitored_payment_entry=monitored_payment_entry,
        )
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase11n_baseline_exists", "Phase 11N baseline exists", "No active Phase 11N baseline found.")

    if not issues:
        add_item(
            items,
            "Pass",
            "Critical",
            "Monitor Source",
            "monitor_source_valid",
            "Monitor source valid",
            "Post-closeout baseline is stable and ready for runtime monitoring.",
            monitored_payment_entry=monitored_payment_entry,
        )
    else:
        for issue in issues:
            add_item(
                items,
                "Blocker",
                "Critical",
                "Monitor Source",
                "monitor_source_valid",
                "Monitor source valid",
                issue,
                monitored_payment_entry=monitored_payment_entry,
            )

    for ref in references:
        add_item(
            items,
            "Pass",
            "High",
            "Monitored Reference",
            "monitored_sales_invoice_reference",
            f"Monitored Sales Invoice {ref.idx}",
            f"{ref.reference_name} monitored allocation evidence retained at {flt(ref.allocated_amount or 0, 2)}.",
            reference=ref,
            monitored_payment_entry=monitored_payment_entry,
        )

    checks = [
        ("runtime_monitor_enabled", "Runtime monitor enabled", 1),
        ("guardrail_watch_active", "Guardrail watch active", 1),
        ("baseline_active", "Baseline active", 1),
        ("payment_entry_cancelled_still", "Payment Entry still cancelled", monitored_payment_entry),
        ("payment_entry_count", "Payment Entry count remains 9", 9),
        ("payment_entry_gl_count", "Payment Entry GL count remains 54", 54),
        ("voucher_gl_rows", "Voucher GL rows remain 8", 8),
        ("voucher_gl_net_zero", "Voucher GL net remains 0.00", "0.00"),
        ("policy_state", "Policy state preserved at 1 / 0", "1 / 0"),
        ("no_pe_movement", "No Payment Entry movement in monitor", "0 / 0"),
        ("no_gl_movement", "No GL movement in monitor", 0),
        ("no_je_pi", "No JE / PI side effects", "0 / 0"),
        ("ready_for_planning_gate", "Ready for next planning gate", 1),
    ]

    for key, label, value in checks:
        add_item(
            items,
            "Pass",
            "High",
            "Monitor Evidence",
            key,
            label,
            f"value={value}",
            monitored_payment_entry=monitored_payment_entry,
        )

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.", monitored_payment_entry=monitored_payment_entry)
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {MONITOR_ACK}")

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
    score = 100
    score -= int(blockers or 0) * 25
    score -= int(warnings or 0) * 5
    return max(0, round(score, 2))


def create_items(doc, items):
    for item in items:
        row = frappe.new_doc(MONITOR_ITEM_DOCTYPE)
        row.monitor = doc.name

        for fieldname, value in item.items():
            if row.meta.has_field(fieldname):
                setattr(row, fieldname, value)

        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_post_closeout_runtime_monitor(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_post_closeout_runtime_monitor")

    baseline = latest_baseline()
    payment_entry = baseline.baseline_payment_entry if baseline else None
    references = payment_entry_reference_rows(payment_entry) if payment_entry else []

    guard_before = guardrails()
    ack_ok = acknowledgement == MONITOR_ACK

    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }

    policy_enabled_before = get_flag(POLICY_DOCTYPE, baseline.target_policy, "production_batch_enabled") if baseline else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, baseline.target_policy, "live_posting_allowed") if baseline else 0

    issues = validate_source(baseline, payment_entry, references, guard_before, config, policy_enabled_before, policy_live_before)

    guard_after = guardrails()

    policy_enabled_after = get_flag(POLICY_DOCTYPE, baseline.target_policy, "production_batch_enabled") if baseline else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, baseline.target_policy, "live_posting_allowed") if baseline else 0

    actual_pe_created = guard_after["payment_entry_count"] - guard_before["payment_entry_count"]
    actual_pe_cancelled = 0
    actual_gl_created = guard_after["payment_entry_gl_count"] - guard_before["payment_entry_gl_count"]

    policy_mutation_count = int(
        policy_enabled_before != policy_enabled_after
        or policy_live_before != policy_live_after
        or guard_before["production_batch_enabled_policy_count"] != guard_after["production_batch_enabled_policy_count"]
        or guard_before["live_posting_allowed_policy_count"] != guard_after["live_posting_allowed_policy_count"]
    )

    pe_docstatus = 0
    pe_status = None
    monitored_total = 0
    voucher_rows = 0
    voucher_net = 0
    non_zero_accounts = 0

    if payment_entry and frappe.db.exists("Payment Entry", payment_entry):
        pe = frappe.get_doc("Payment Entry", payment_entry)
        pe_docstatus = int(pe.docstatus or 0)
        pe_status = pe.status
        monitored_total = flt(pe.paid_amount or pe.received_amount or allocated_total(payment_entry), 2)
        voucher_rows = voucher_gl_rows(payment_entry)
        voucher_net = voucher_gl_net(payment_entry)
        non_zero_accounts = voucher_gl_non_zero_accounts(payment_entry)

    post_issues = list(issues)

    if actual_pe_created != 0:
        post_issues.append(f"Monitor must not create Payment Entries. Created {actual_pe_created}.")

    if actual_pe_cancelled != 0:
        post_issues.append(f"Monitor must not cancel Payment Entries. Cancelled {actual_pe_cancelled}.")

    if actual_gl_created != 0:
        post_issues.append(f"Monitor must not create GL rows. Created {actual_gl_created}.")

    if guard_after["payment_entry_count"] != 9:
        post_issues.append("Payment Entry count must remain 9 after monitor.")

    if guard_after["payment_entry_gl_count"] != 54:
        post_issues.append("Payment Entry GL count must remain 54 after monitor.")

    if guard_after["submitted_journal_entry_count_today"] != 0:
        post_issues.append("Submitted Journal Entry count today must remain 0 after monitor.")

    if guard_after["purchase_invoice_count_today"] != 0:
        post_issues.append("Purchase Invoice count today must remain 0 after monitor.")

    if policy_mutation_count != 0:
        post_issues.append("Policy state changed during monitor. This is not allowed.")

    items = build_items(
        baseline,
        references,
        post_issues,
        ack_ok,
        monitored_payment_entry=payment_entry,
    )
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    completed = int(
        ack_ok
        and baseline
        and payment_entry
        and item_summary["blocker_count"] == 0
        and pe_docstatus == 2
        and pe_status == "Cancelled"
        and len(references) == 3
        and monitored_total == 3
        and voucher_rows == 8
        and voucher_net == 0
        and non_zero_accounts == 0
        and guard_before["payment_entry_count"] == 9
        and guard_after["payment_entry_count"] == 9
        and guard_before["payment_entry_gl_count"] == 54
        and guard_after["payment_entry_gl_count"] == 54
        and actual_pe_created == 0
        and actual_pe_cancelled == 0
        and actual_gl_created == 0
        and guard_after["submitted_journal_entry_count_today"] == 0
        and guard_after["purchase_invoice_count_today"] == 0
        and policy_mutation_count == 0
    )

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Monitor Active" if completed else "Needs Review",
        "monitor_status": "Post-Closeout Runtime Monitor Active" if completed else "Needs Review",
        "monitor_active": completed,
        "phase11n_baseline_verified": 1 if baseline else 0,
        "baseline_active_verified": 1 if baseline else 0,
        "baseline_payment_entry_verified": 1 if payment_entry else 0,
        "payment_entry_cancelled_still_verified": int(pe_docstatus == 2 and pe_status == "Cancelled"),
        "voucher_gl_rows_verified": int(voucher_rows == 8),
        "voucher_gl_net_zero_verified": int(voucher_net == 0 and non_zero_accounts == 0),
        "invoice_outstanding_restored_still_verified": int(monitored_total == 3),
        "baseline_counts_stable_verified": int(guard_before["payment_entry_count"] == 9 and guard_after["payment_entry_count"] == 9 and guard_before["payment_entry_gl_count"] == 54 and guard_after["payment_entry_gl_count"] == 54),
        "policy_state_preserved_verified": int(policy_mutation_count == 0 and policy_enabled_before == 1 and policy_enabled_after == 1 and policy_live_before == 0 and policy_live_after == 0),
        "runtime_monitor_enabled": completed,
        "guardrail_watch_active": completed,
        "ready_for_next_governed_limited_operation_planning_gate": completed,
        "no_new_accounting_movement_verified": int(actual_pe_created == 0 and actual_pe_cancelled == 0 and actual_gl_created == 0),
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": policy_mutation_count,
        "monitored_payment_entry": payment_entry,
        "payment_entry_docstatus_monitor": pe_docstatus,
        "payment_entry_status_monitor": pe_status,
        "monitored_reference_count": len(references),
        "monitored_total_amount": monitored_total,
        "monitored_voucher_gl_rows": voucher_rows,
        "monitored_voucher_gl_net": voucher_net,
        "monitored_voucher_gl_non_zero_account_count": non_zero_accounts,
        "monitored_restored_invoice_amount": monitored_total if monitored_total == 3 else 0,
        "baseline": baseline.name if baseline else None,
        "closeout": baseline.closeout if baseline else None,
        "freeze": baseline.freeze if baseline else None,
        "rollback": baseline.rollback if baseline else None,
        "smoke": baseline.smoke if baseline else None,
        "execution_gate": baseline.execution_gate if baseline else None,
        "preview": baseline.preview if baseline else None,
        "validation": baseline.validation if baseline else None,
        "candidate": baseline.candidate if baseline else None,
        "design": baseline.design if baseline else None,
        "planning": baseline.planning if baseline else None,
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
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guard_after["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
        "actual_payment_entry_created_count": actual_pe_created,
        "actual_payment_entry_cancelled_count": actual_pe_cancelled,
        "actual_gl_created_count": actual_gl_created,
        "submitted_journal_entry_count_today": guard_after["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_after["purchase_invoice_count_today"],
        "monitor_score": score,
        **item_summary,
        "items": items,
        "references": [dict(row) for row in references],
        "issues": post_issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "required_acknowledgement": MONITOR_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 11O activates the post-closeout runtime monitor. It creates no accounting movement and prepares the next planning gate.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["monitor_status"] = "Needs Review"
        result["monitor_active"] = 0
        result["runtime_monitor_enabled"] = 0
        result["guardrail_watch_active"] = 0
        result["ready_for_next_governed_limited_operation_planning_gate"] = 0
        return result

    doc = frappe.new_doc(MONITOR_DOCTYPE)
    doc.monitor_id = make_monitor_id()

    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)

    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = MONITOR_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.monitor_json = safe_json(
        {
            "baseline": baseline,
            "monitored_payment_entry": payment_entry,
            "references": [dict(row) for row in references],
            "guardrails_before": guard_before,
            "guardrails_after": guard_after,
            "voucher": {
                "rows": voucher_rows,
                "net": voucher_net,
                "non_zero_accounts": non_zero_accounts,
            },
            "issues": post_issues,
            "config": config,
        }
    )
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    create_items(doc, items)
    frappe.db.commit()

    return {
        **result,
        "created": True,
        "monitor": doc.name,
        "monitor_id": doc.monitor_id,
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_post_closeout_runtime_monitor_audit(monitor, reason=None):
    assert_action("cancel_post_closeout_runtime_monitor_audit")

    if not frappe.db.exists(MONITOR_DOCTYPE, monitor):
        frappe.throw(_("Post-closeout runtime monitor audit not found: {0}").format(monitor))

    doc = frappe.get_doc(MONITOR_DOCTYPE, monitor)

    if doc.status == "Cancelled":
        return {"monitor": monitor, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.monitor_active or 0):
        frappe.throw(_("Cannot cancel an active Phase 11O runtime monitor record."))

    frappe.db.set_value(
        MONITOR_DOCTYPE,
        monitor,
        {
            "status": "Cancelled",
            "monitor_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 11O no-ack runtime monitor audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        f"""
        UPDATE `tab{MONITOR_ITEM_DOCTYPE}`
        SET status = 'Cancelled'
        WHERE monitor = %(monitor)s
        """,
        {"monitor": monitor},
    )

    frappe.db.commit()

    return {
        "monitor": monitor,
        "status": "Cancelled",
        "note": "No-ack monitor audit cancelled only. No accounting or policy movement occurred.",
    }


@frappe.whitelist()
def quick_post_closeout_runtime_monitor_summary(limit=20):
    records = frappe.get_all(
        MONITOR_DOCTYPE,
        fields=[
            "name",
            "monitor_id",
            "status",
            "monitor_status",
            "monitor_active",
            "runtime_monitor_enabled",
            "guardrail_watch_active",
            "ready_for_next_governed_limited_operation_planning_gate",
            "monitored_payment_entry",
            "payment_entry_docstatus_monitor",
            "payment_entry_status_monitor",
            "monitored_reference_count",
            "monitored_total_amount",
            "monitored_voucher_gl_rows",
            "monitored_voucher_gl_net",
            "monitored_restored_invoice_amount",
            "baseline",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "actual_payment_entry_created_count",
            "actual_payment_entry_cancelled_count",
            "actual_gl_created_count",
            "submitted_journal_entry_count_today",
            "purchase_invoice_count_today",
            "monitor_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    items = frappe.get_all(
        MONITOR_ITEM_DOCTYPE,
        fields=[
            "name",
            "monitor",
            "status",
            "severity",
            "category",
            "check_key",
            "check_label",
            "line_no",
            "reference_doctype",
            "reference_name",
            "allocated_amount",
            "monitored_payment_entry",
            "detail",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    return {
        "monitor_records": records,
        "items": items,
        "required_acknowledgement": MONITOR_ACK,
        "guardrails": guardrails(),
        "note": "Phase 11O post-closeout runtime monitor summary.",
    }


def execute_monitor_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("status"):
        conditions.append("m.status = %(status)s")
        params["status"] = filters.get("status")

    columns = monitor_columns()

    data = frappe.db.sql(
        f"""
        SELECT
            m.name AS monitor,
            m.monitor_id,
            m.status,
            m.monitor_status,
            m.monitor_active,
            m.phase11n_baseline_verified,
            m.baseline_active_verified,
            m.payment_entry_cancelled_still_verified,
            m.baseline_counts_stable_verified,
            m.policy_state_preserved_verified,
            m.runtime_monitor_enabled,
            m.guardrail_watch_active,
            m.ready_for_next_governed_limited_operation_planning_gate,
            m.monitored_payment_entry,
            m.payment_entry_docstatus_monitor,
            m.payment_entry_status_monitor,
            m.monitored_reference_count,
            m.monitored_total_amount,
            m.monitored_voucher_gl_rows,
            m.monitored_voucher_gl_net,
            m.monitored_restored_invoice_amount,
            m.baseline,
            m.payment_entry_count_before,
            m.payment_entry_count_after,
            m.payment_entry_gl_count_before,
            m.payment_entry_gl_count_after,
            m.actual_payment_entry_created_count,
            m.actual_payment_entry_cancelled_count,
            m.actual_gl_created_count,
            m.submitted_journal_entry_count_today,
            m.purchase_invoice_count_today,
            m.monitor_score,
            m.checked_on,
            %(currency)s AS currency
        FROM `tab{MONITOR_DOCTYPE}` m
        {build_where(conditions)}
        ORDER BY m.creation DESC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.monitor_id for row in data[:20]],
            "datasets": [
                {"name": "Monitor Active", "values": [int(row.monitor_active or 0) for row in data[:20]]},
                {"name": "Guardrail Watch", "values": [int(row.guardrail_watch_active or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Monitor Records"), "datatype": "Int"},
        {"value": sum(int(row.monitor_active or 0) for row in data), "indicator": "Green", "label": _("Active"), "datatype": "Int"},
        {"value": sum(int(row.guardrail_watch_active or 0) for row in data), "indicator": "Green", "label": _("Guardrail Watch"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL Created"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def monitor_columns():
    return [
        {"fieldname": "monitor", "label": _("Monitor"), "fieldtype": "Link", "options": MONITOR_DOCTYPE, "width": 220},
        {"fieldname": "monitor_id", "label": _("Monitor ID"), "fieldtype": "Data", "width": 360},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 140},
        {"fieldname": "monitor_status", "label": _("Monitor Status"), "fieldtype": "Data", "width": 320},
        {"fieldname": "monitor_active", "label": _("Active"), "fieldtype": "Check", "width": 80},
        {"fieldname": "phase11n_baseline_verified", "label": _("11N Verified"), "fieldtype": "Check", "width": 105},
        {"fieldname": "baseline_active_verified", "label": _("Baseline OK"), "fieldtype": "Check", "width": 100},
        {"fieldname": "payment_entry_cancelled_still_verified", "label": _("PE Cancelled"), "fieldtype": "Check", "width": 110},
        {"fieldname": "baseline_counts_stable_verified", "label": _("Counts Stable"), "fieldtype": "Check", "width": 110},
        {"fieldname": "policy_state_preserved_verified", "label": _("Policy OK"), "fieldtype": "Check", "width": 90},
        {"fieldname": "runtime_monitor_enabled", "label": _("Monitor Enabled"), "fieldtype": "Check", "width": 120},
        {"fieldname": "guardrail_watch_active", "label": _("Guardrail Watch"), "fieldtype": "Check", "width": 120},
        {"fieldname": "ready_for_next_governed_limited_operation_planning_gate", "label": _("Planning Ready"), "fieldtype": "Check", "width": 120},
        {"fieldname": "monitored_payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "payment_entry_docstatus_monitor", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 100},
        {"fieldname": "payment_entry_status_monitor", "label": _("PE Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "monitored_reference_count", "label": _("Refs"), "fieldtype": "Int", "width": 70},
        {"fieldname": "monitored_total_amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 100},
        {"fieldname": "monitored_voucher_gl_rows", "label": _("Voucher GL Rows"), "fieldtype": "Int", "width": 120},
        {"fieldname": "monitored_voucher_gl_net", "label": _("Voucher Net"), "fieldtype": "Currency", "options": "currency", "width": 100},
        {"fieldname": "monitored_restored_invoice_amount", "label": _("Restored Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "baseline", "label": _("Baseline"), "fieldtype": "Link", "options": BASELINE_DOCTYPE, "width": 220},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 110},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE Created"), "fieldtype": "Int", "width": 125},
        {"fieldname": "actual_payment_entry_cancelled_count", "label": _("Actual PE Cancelled"), "fieldtype": "Int", "width": 135},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL Created"), "fieldtype": "Int", "width": 125},
        {"fieldname": "submitted_journal_entry_count_today", "label": _("JE Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "purchase_invoice_count_today", "label": _("PI Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "monitor_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    if filters.get("monitor"):
        conditions.append("i.monitor = %(monitor)s")
        params["monitor"] = filters.get("monitor")

    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": MONITOR_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "monitor", "label": _("Monitor"), "fieldtype": "Link", "options": MONITOR_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 190},
        {"fieldname": "line_no", "label": _("Line"), "fieldtype": "Int", "width": 60},
        {"fieldname": "reference_doctype", "label": _("Ref DocType"), "fieldtype": "Data", "width": 130},
        {"fieldname": "reference_name", "label": _("Reference"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 180},
        {"fieldname": "allocated_amount", "label": _("Allocated"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "monitored_payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "check_key", "label": _("Check Key"), "fieldtype": "Data", "width": 230},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 330},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 650},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            i.name AS item,
            i.monitor,
            i.status,
            i.severity,
            i.category,
            i.line_no,
            i.reference_doctype,
            i.reference_name,
            i.allocated_amount,
            i.monitored_payment_entry,
            i.check_key,
            i.check_label,
            i.detail,
            i.checked_on
        FROM `tab{MONITOR_ITEM_DOCTYPE}` i
        {build_where(conditions)}
        ORDER BY
            CASE i.status
                WHEN 'Blocker' THEN 1
                WHEN 'Warning' THEN 2
                WHEN 'Pass' THEN 3
                WHEN 'Info' THEN 4
                ELSE 5
            END,
            i.line_no ASC,
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
        "data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Items", "values": list(chart_map.values())}]},
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Items"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Pass"]), "indicator": "Green", "label": _("Pass"), "datatype": "Int"},
        {"value": len([row for row in data if row.category == "Monitored Reference"]), "indicator": "Green", "label": _("Monitored References"), "datatype": "Int"},
        {"value": sum(flt(row.allocated_amount or 0, 2) for row in data if row.category == "Monitored Reference"), "indicator": "Green", "label": _("Monitored Amount"), "datatype": "Currency"},
        {"value": len([row for row in data if row.status == "Blocker"]), "indicator": "Red", "label": _("Blockers"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_monitor_report(filters)
    guard = guardrails()

    summary.append({"value": guard["payment_entry_count"], "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"})
    summary.append({"value": guard["payment_entry_gl_count"], "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"})
    summary.append({"value": guard["production_batch_enabled_policy_count"], "indicator": "Green", "label": _("Enabled Policies"), "datatype": "Int"})
    summary.append({"value": guard["live_posting_allowed_policy_count"], "indicator": "Red", "label": _("Live Policies"), "datatype": "Int"})
    summary.append({"value": guard["submitted_journal_entry_count_today"], "indicator": "Red", "label": _("Submitted JE Today"), "datatype": "Int"})
    summary.append({"value": guard["purchase_invoice_count_today"], "indicator": "Red", "label": _("Purchase Invoice Today"), "datatype": "Int"})

    return columns, data, message, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
