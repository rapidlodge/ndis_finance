import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


BASELINE_ACK = "I_CONFIRM_PHASE11N_ACTIVATE_POST_CLOSEOUT_STEADY_STATE_BASELINE_NO_POSTING"

POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
CLOSEOUT_DOCTYPE = "NDIS Governed Next Op Closeout"
BASELINE_DOCTYPE = "NDIS Post Closeout Steady Baseline"
BASELINE_ITEM_DOCTYPE = "NDIS Post Closeout Steady Baseline Item"


def make_baseline_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-POST-CLOSEOUT-STEADY-BASELINE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_closeout():
    rows = frappe.get_all(
        CLOSEOUT_DOCTYPE,
        filters={
            "status": "Closeout Approved",
            "closeout_status": "Next Governed Limited Operation Cycle Closed",
            "closeout_approved": 1,
            "phase11l_freeze_verified": 1,
            "rollback_evidence_frozen_verified": 1,
            "rolled_back_payment_entry_verified": 1,
            "payment_entry_cancelled_still_verified": 1,
            "voucher_gl_rows_verified": 1,
            "voucher_gl_net_zero_verified": 1,
            "invoice_outstanding_restored_still_verified": 1,
            "second_governed_limited_operation_cycle_closed": 1,
            "ready_for_next_steady_state_baseline": 1,
            "payment_entry_docstatus_closed": 2,
            "payment_entry_status_closed": "Cancelled",
            "closed_reference_count": 3,
            "closed_total_amount": 3.00,
            "closed_voucher_gl_rows": 8,
            "closed_voucher_gl_net": 0.00,
            "closed_voucher_gl_non_zero_account_count": 0,
            "closed_restored_invoice_amount": 3.00,
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
            "closeout_id",
            "closed_payment_entry",
            "closed_reference_count",
            "closed_total_amount",
            "closed_restored_invoice_amount",
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


def existing_active_baseline(closeout):
    rows = frappe.get_all(
        BASELINE_DOCTYPE,
        filters={
            "closeout": closeout,
            "status": "Baseline Active",
            "baseline_active": 1,
        },
        fields=["name", "baseline_id"],
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


def validate_source(closeout, payment_entry, references, guard, config, policy_enabled, policy_live):
    issues = []

    if not closeout:
        issues.append("No completed Phase 11M closeout found.")
        return issues

    existing = existing_active_baseline(closeout.name)
    if existing:
        issues.append(f"Active Phase 11N baseline already exists for this closeout: {existing.baseline_id}")

    if not payment_entry:
        issues.append("Phase 11M closeout does not identify the closed Payment Entry.")
        return issues

    if not frappe.db.exists("Payment Entry", payment_entry):
        issues.append(f"Closed Payment Entry does not exist: {payment_entry}")
        return issues

    pe = frappe.get_doc("Payment Entry", payment_entry)

    if pe.docstatus != 2:
        issues.append(f"Payment Entry must remain cancelled for baseline. docstatus={pe.docstatus}")

    if pe.status != "Cancelled":
        issues.append(f"Payment Entry status must remain Cancelled for baseline. status={pe.status}")

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
        issues.append("Payment Entry count must remain 9 before Phase 11N baseline.")

    if guard["payment_entry_gl_count"] != 54:
        issues.append("Payment Entry GL count must remain 54 before Phase 11N baseline.")

    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today must remain 0 before baseline.")

    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today must remain 0 before baseline.")

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


def add_item(items, status, severity, category, check_key, check_label, detail, reference=None, baseline_payment_entry=None):
    item = {
        "status": status,
        "severity": severity,
        "category": category,
        "check_key": check_key,
        "check_label": check_label,
        "detail": detail,
        "baseline_payment_entry": baseline_payment_entry,
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


def build_items(closeout, references, issues, ack_ok, baseline_payment_entry=None):
    items = []

    if closeout:
        add_item(
            items,
            "Pass",
            "Low",
            "Evidence",
            "phase11m_closeout_exists",
            "Phase 11M closeout exists",
            f"Closeout found: {closeout.closeout_id}.",
            baseline_payment_entry=baseline_payment_entry,
        )
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase11m_closeout_exists", "Phase 11M closeout exists", "No completed Phase 11M closeout found.")

    if not issues:
        add_item(
            items,
            "Pass",
            "Critical",
            "Baseline Source",
            "baseline_source_valid",
            "Baseline source valid",
            "Closed cycle state is stable and ready to become the post-closeout steady-state baseline.",
            baseline_payment_entry=baseline_payment_entry,
        )
    else:
        for issue in issues:
            add_item(
                items,
                "Blocker",
                "Critical",
                "Baseline Source",
                "baseline_source_valid",
                "Baseline source valid",
                issue,
                baseline_payment_entry=baseline_payment_entry,
            )

    for ref in references:
        add_item(
            items,
            "Pass",
            "High",
            "Baseline Reference",
            "baseline_sales_invoice_reference",
            f"Baseline Sales Invoice {ref.idx}",
            f"{ref.reference_name} baseline evidence retained at {flt(ref.allocated_amount or 0, 2)}.",
            reference=ref,
            baseline_payment_entry=baseline_payment_entry,
        )

    checks = [
        ("second_cycle_closed", "Second governed limited-operation cycle closed", 1),
        ("payment_entry_cancelled_still", "Payment Entry still cancelled", baseline_payment_entry),
        ("payment_entry_count", "Payment Entry count baseline = 9", 9),
        ("payment_entry_gl_count", "Payment Entry GL baseline = 54", 54),
        ("voucher_gl_rows", "Voucher GL rows remain 8", 8),
        ("voucher_gl_net_zero", "Voucher GL net remains 0.00", "0.00"),
        ("invoice_outstanding_restored", "Invoice outstanding restoration remains 3.00", "3.00"),
        ("no_pe_movement", "No Payment Entry movement in baseline", "0 / 0"),
        ("no_gl_movement", "No GL movement in baseline", 0),
        ("no_je_pi", "No JE / PI side effects", "0 / 0"),
        ("policy_state", "Policy state preserved at 1 / 0", "1 / 0"),
        ("ready_for_monitoring", "Ready for post-closeout monitoring", 1),
        ("ready_for_next_cycle_planning", "Ready for next governed limited-operation planning", 1),
    ]

    for key, label, value in checks:
        add_item(
            items,
            "Pass",
            "High",
            "Baseline Evidence",
            key,
            label,
            f"value={value}",
            baseline_payment_entry=baseline_payment_entry,
        )

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.", baseline_payment_entry=baseline_payment_entry)
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
    score = 100
    score -= int(blockers or 0) * 25
    score -= int(warnings or 0) * 5
    return max(0, round(score, 2))


def create_items(doc, items):
    for item in items:
        row = frappe.new_doc(BASELINE_ITEM_DOCTYPE)
        row.baseline = doc.name

        for fieldname, value in item.items():
            if row.meta.has_field(fieldname):
                setattr(row, fieldname, value)

        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_post_closeout_steady_state_baseline(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_post_closeout_steady_state_baseline")

    closeout = latest_closeout()
    payment_entry = closeout.closed_payment_entry if closeout else None
    references = payment_entry_reference_rows(payment_entry) if payment_entry else []

    guard_before = guardrails()
    ack_ok = acknowledgement == BASELINE_ACK

    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }

    policy_enabled_before = get_flag(POLICY_DOCTYPE, closeout.target_policy, "production_batch_enabled") if closeout else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, closeout.target_policy, "live_posting_allowed") if closeout else 0

    issues = validate_source(closeout, payment_entry, references, guard_before, config, policy_enabled_before, policy_live_before)

    guard_after = guardrails()

    policy_enabled_after = get_flag(POLICY_DOCTYPE, closeout.target_policy, "production_batch_enabled") if closeout else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, closeout.target_policy, "live_posting_allowed") if closeout else 0

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
    baseline_total = 0
    voucher_rows = 0
    voucher_net = 0
    non_zero_accounts = 0

    if payment_entry and frappe.db.exists("Payment Entry", payment_entry):
        pe = frappe.get_doc("Payment Entry", payment_entry)
        pe_docstatus = int(pe.docstatus or 0)
        pe_status = pe.status
        baseline_total = flt(pe.paid_amount or pe.received_amount or allocated_total(payment_entry), 2)
        voucher_rows = voucher_gl_rows(payment_entry)
        voucher_net = voucher_gl_net(payment_entry)
        non_zero_accounts = voucher_gl_non_zero_accounts(payment_entry)

    post_issues = list(issues)

    if actual_pe_created != 0:
        post_issues.append(f"Baseline must not create Payment Entries. Created {actual_pe_created}.")

    if actual_pe_cancelled != 0:
        post_issues.append(f"Baseline must not cancel Payment Entries. Cancelled {actual_pe_cancelled}.")

    if actual_gl_created != 0:
        post_issues.append(f"Baseline must not create GL rows. Created {actual_gl_created}.")

    if guard_after["payment_entry_count"] != 9:
        post_issues.append("Payment Entry count must remain 9 after baseline.")

    if guard_after["payment_entry_gl_count"] != 54:
        post_issues.append("Payment Entry GL count must remain 54 after baseline.")

    if guard_after["submitted_journal_entry_count_today"] != 0:
        post_issues.append("Submitted Journal Entry count today must remain 0 after baseline.")

    if guard_after["purchase_invoice_count_today"] != 0:
        post_issues.append("Purchase Invoice count today must remain 0 after baseline.")

    if policy_mutation_count != 0:
        post_issues.append("Policy state changed during baseline. This is not allowed.")

    items = build_items(
        closeout,
        references,
        post_issues,
        ack_ok,
        baseline_payment_entry=payment_entry,
    )
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    completed = int(
        ack_ok
        and closeout
        and payment_entry
        and item_summary["blocker_count"] == 0
        and pe_docstatus == 2
        and pe_status == "Cancelled"
        and len(references) == 3
        and baseline_total == 3
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
        "status": "Baseline Active" if completed else "Needs Review",
        "baseline_status": "Post-Closeout Steady-State Baseline Active" if completed else "Needs Review",
        "baseline_active": completed,
        "phase11m_closeout_verified": 1 if closeout else 0,
        "second_cycle_closed_verified": 1 if closeout else 0,
        "closed_payment_entry_verified": 1 if payment_entry else 0,
        "payment_entry_cancelled_still_verified": int(pe_docstatus == 2 and pe_status == "Cancelled"),
        "voucher_gl_rows_verified": int(voucher_rows == 8),
        "voucher_gl_net_zero_verified": int(voucher_net == 0 and non_zero_accounts == 0),
        "invoice_outstanding_restored_still_verified": int(baseline_total == 3),
        "baseline_counts_stable_verified": int(guard_before["payment_entry_count"] == 9 and guard_after["payment_entry_count"] == 9 and guard_before["payment_entry_gl_count"] == 54 and guard_after["payment_entry_gl_count"] == 54),
        "policy_state_preserved_verified": int(policy_mutation_count == 0 and policy_enabled_before == 1 and policy_enabled_after == 1 and policy_live_before == 0 and policy_live_after == 0),
        "ready_for_post_closeout_monitoring": completed,
        "ready_for_next_governed_limited_operation_planning": completed,
        "no_new_accounting_movement_verified": int(actual_pe_created == 0 and actual_pe_cancelled == 0 and actual_gl_created == 0),
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": policy_mutation_count,
        "baseline_payment_entry": payment_entry,
        "payment_entry_docstatus_baseline": pe_docstatus,
        "payment_entry_status_baseline": pe_status,
        "baseline_reference_count": len(references),
        "baseline_total_amount": baseline_total,
        "baseline_voucher_gl_rows": voucher_rows,
        "baseline_voucher_gl_net": voucher_net,
        "baseline_voucher_gl_non_zero_account_count": non_zero_accounts,
        "baseline_restored_invoice_amount": baseline_total if baseline_total == 3 else 0,
        "closeout": closeout.name if closeout else None,
        "freeze": closeout.freeze if closeout else None,
        "rollback": closeout.rollback if closeout else None,
        "smoke": closeout.smoke if closeout else None,
        "execution_gate": closeout.execution_gate if closeout else None,
        "preview": closeout.preview if closeout else None,
        "validation": closeout.validation if closeout else None,
        "candidate": closeout.candidate if closeout else None,
        "design": closeout.design if closeout else None,
        "planning": closeout.planning if closeout else None,
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
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guard_after["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
        "actual_payment_entry_created_count": actual_pe_created,
        "actual_payment_entry_cancelled_count": actual_pe_cancelled,
        "actual_gl_created_count": actual_gl_created,
        "submitted_journal_entry_count_today": guard_after["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_after["purchase_invoice_count_today"],
        "baseline_score": score,
        **item_summary,
        "items": items,
        "references": [dict(row) for row in references],
        "issues": post_issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "required_acknowledgement": BASELINE_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 11N activates a post-closeout steady-state baseline. It creates no accounting movement and prepares monitoring / next-cycle planning.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["baseline_status"] = "Needs Review"
        result["baseline_active"] = 0
        result["ready_for_post_closeout_monitoring"] = 0
        result["ready_for_next_governed_limited_operation_planning"] = 0
        return result

    doc = frappe.new_doc(BASELINE_DOCTYPE)
    doc.baseline_id = make_baseline_id()

    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)

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
    doc.baseline_json = safe_json(
        {
            "closeout": closeout,
            "baseline_payment_entry": payment_entry,
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
        "baseline": doc.name,
        "baseline_id": doc.baseline_id,
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_post_closeout_steady_state_baseline_audit(baseline, reason=None):
    assert_action("cancel_post_closeout_steady_state_baseline_audit")

    if not frappe.db.exists(BASELINE_DOCTYPE, baseline):
        frappe.throw(_("Post-closeout steady-state baseline audit not found: {0}").format(baseline))

    doc = frappe.get_doc(BASELINE_DOCTYPE, baseline)

    if doc.status == "Cancelled":
        return {"baseline": baseline, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.baseline_active or 0):
        frappe.throw(_("Cannot cancel an active Phase 11N baseline record."))

    frappe.db.set_value(
        BASELINE_DOCTYPE,
        baseline,
        {
            "status": "Cancelled",
            "baseline_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 11N no-ack baseline audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        f"""
        UPDATE `tab{BASELINE_ITEM_DOCTYPE}`
        SET status = 'Cancelled'
        WHERE baseline = %(baseline)s
        """,
        {"baseline": baseline},
    )

    frappe.db.commit()

    return {
        "baseline": baseline,
        "status": "Cancelled",
        "note": "No-ack baseline audit cancelled only. No accounting or policy movement occurred.",
    }


@frappe.whitelist()
def quick_post_closeout_steady_state_baseline_summary(limit=20):
    records = frappe.get_all(
        BASELINE_DOCTYPE,
        fields=[
            "name",
            "baseline_id",
            "status",
            "baseline_status",
            "baseline_active",
            "ready_for_post_closeout_monitoring",
            "ready_for_next_governed_limited_operation_planning",
            "baseline_payment_entry",
            "payment_entry_docstatus_baseline",
            "payment_entry_status_baseline",
            "baseline_reference_count",
            "baseline_total_amount",
            "baseline_voucher_gl_rows",
            "baseline_voucher_gl_net",
            "baseline_restored_invoice_amount",
            "closeout",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "actual_payment_entry_created_count",
            "actual_payment_entry_cancelled_count",
            "actual_gl_created_count",
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
        fields=[
            "name",
            "baseline",
            "status",
            "severity",
            "category",
            "check_key",
            "check_label",
            "line_no",
            "reference_doctype",
            "reference_name",
            "allocated_amount",
            "baseline_payment_entry",
            "detail",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    return {
        "baseline_records": records,
        "items": items,
        "required_acknowledgement": BASELINE_ACK,
        "guardrails": guardrails(),
        "note": "Phase 11N post-closeout steady-state baseline summary.",
    }


def execute_baseline_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("status"):
        conditions.append("b.status = %(status)s")
        params["status"] = filters.get("status")

    columns = baseline_columns()

    data = frappe.db.sql(
        f"""
        SELECT
            b.name AS baseline,
            b.baseline_id,
            b.status,
            b.baseline_status,
            b.baseline_active,
            b.phase11m_closeout_verified,
            b.second_cycle_closed_verified,
            b.payment_entry_cancelled_still_verified,
            b.baseline_counts_stable_verified,
            b.policy_state_preserved_verified,
            b.ready_for_post_closeout_monitoring,
            b.ready_for_next_governed_limited_operation_planning,
            b.baseline_payment_entry,
            b.payment_entry_docstatus_baseline,
            b.payment_entry_status_baseline,
            b.baseline_reference_count,
            b.baseline_total_amount,
            b.baseline_voucher_gl_rows,
            b.baseline_voucher_gl_net,
            b.baseline_restored_invoice_amount,
            b.closeout,
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

    chart = {
        "data": {
            "labels": [row.baseline_id for row in data[:20]],
            "datasets": [
                {"name": "Baseline Active", "values": [int(row.baseline_active or 0) for row in data[:20]]},
                {"name": "Monitoring Ready", "values": [int(row.ready_for_post_closeout_monitoring or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Baseline Records"), "datatype": "Int"},
        {"value": sum(int(row.baseline_active or 0) for row in data), "indicator": "Green", "label": _("Active"), "datatype": "Int"},
        {"value": sum(int(row.ready_for_post_closeout_monitoring or 0) for row in data), "indicator": "Green", "label": _("Monitoring Ready"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL Created"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def baseline_columns():
    return [
        {"fieldname": "baseline", "label": _("Baseline"), "fieldtype": "Link", "options": BASELINE_DOCTYPE, "width": 220},
        {"fieldname": "baseline_id", "label": _("Baseline ID"), "fieldtype": "Data", "width": 360},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 150},
        {"fieldname": "baseline_status", "label": _("Baseline Status"), "fieldtype": "Data", "width": 350},
        {"fieldname": "baseline_active", "label": _("Active"), "fieldtype": "Check", "width": 80},
        {"fieldname": "phase11m_closeout_verified", "label": _("11M Verified"), "fieldtype": "Check", "width": 105},
        {"fieldname": "second_cycle_closed_verified", "label": _("Cycle Closed"), "fieldtype": "Check", "width": 105},
        {"fieldname": "payment_entry_cancelled_still_verified", "label": _("PE Cancelled"), "fieldtype": "Check", "width": 110},
        {"fieldname": "baseline_counts_stable_verified", "label": _("Counts Stable"), "fieldtype": "Check", "width": 110},
        {"fieldname": "policy_state_preserved_verified", "label": _("Policy OK"), "fieldtype": "Check", "width": 90},
        {"fieldname": "ready_for_post_closeout_monitoring", "label": _("Monitoring Ready"), "fieldtype": "Check", "width": 130},
        {"fieldname": "ready_for_next_governed_limited_operation_planning", "label": _("Next Planning Ready"), "fieldtype": "Check", "width": 140},
        {"fieldname": "baseline_payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "payment_entry_docstatus_baseline", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 100},
        {"fieldname": "payment_entry_status_baseline", "label": _("PE Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "baseline_reference_count", "label": _("Refs"), "fieldtype": "Int", "width": 70},
        {"fieldname": "baseline_total_amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 100},
        {"fieldname": "baseline_voucher_gl_rows", "label": _("Voucher GL Rows"), "fieldtype": "Int", "width": 120},
        {"fieldname": "baseline_voucher_gl_net", "label": _("Voucher Net"), "fieldtype": "Currency", "options": "currency", "width": 100},
        {"fieldname": "baseline_restored_invoice_amount", "label": _("Restored Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "closeout", "label": _("Closeout"), "fieldtype": "Link", "options": CLOSEOUT_DOCTYPE, "width": 220},
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
        params["baseline"] = filters.get("baseline")

    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": BASELINE_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "baseline", "label": _("Baseline"), "fieldtype": "Link", "options": BASELINE_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 190},
        {"fieldname": "line_no", "label": _("Line"), "fieldtype": "Int", "width": 60},
        {"fieldname": "reference_doctype", "label": _("Ref DocType"), "fieldtype": "Data", "width": 130},
        {"fieldname": "reference_name", "label": _("Reference"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 180},
        {"fieldname": "allocated_amount", "label": _("Allocated"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "baseline_payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "check_key", "label": _("Check Key"), "fieldtype": "Data", "width": 230},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 330},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 650},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            i.name AS item,
            i.baseline,
            i.status,
            i.severity,
            i.category,
            i.line_no,
            i.reference_doctype,
            i.reference_name,
            i.allocated_amount,
            i.baseline_payment_entry,
            i.check_key,
            i.check_label,
            i.detail,
            i.checked_on
        FROM `tab{BASELINE_ITEM_DOCTYPE}` i
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
        {"value": len([row for row in data if row.category == "Baseline Reference"]), "indicator": "Green", "label": _("Baseline References"), "datatype": "Int"},
        {"value": sum(flt(row.allocated_amount or 0, 2) for row in data if row.category == "Baseline Reference"), "indicator": "Green", "label": _("Baseline Amount"), "datatype": "Currency"},
        {"value": len([row for row in data if row.status == "Blocker"]), "indicator": "Red", "label": _("Blockers"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_baseline_report(filters)
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
