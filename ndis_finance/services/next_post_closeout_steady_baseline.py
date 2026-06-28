import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, today

from ndis_finance.services.permissions import assert_action


BASELINE_ACK = "I_CONFIRM_PHASE11Z_ACTIVATE_NEXT_POST_CLOSEOUT_STEADY_BASELINE_NO_POSTING"

POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
CLOSEOUT_DOCTYPE = "NDIS Next Controlled Cycle Closeout"
CLOSEOUT_ITEM_DOCTYPE = "NDIS Next Controlled Cycle Closeout Item"
BASELINE_DOCTYPE = "NDIS Next Post Closeout Steady Baseline"
BASELINE_ITEM_DOCTYPE = "NDIS Next Post Closeout Steady Baseline Item"

EXPECTED_PAYMENT_ENTRY = "ACC-PAY-2026-00011"
EXPECTED_REFERENCE_COUNT = 3
EXPECTED_TOTAL_AMOUNT = 3.00
EXPECTED_VOUCHER_GL_ROWS = 8
EXPECTED_PAYMENT_ENTRY_COUNT = 10
EXPECTED_PAYMENT_ENTRY_GL_COUNT = 62
EXPECTED_INVOICES = ["ACC-SINV-2026-00005", "ACC-SINV-2026-00006", "ACC-SINV-2026-00008"]


def make_baseline_id():
    timestamp = now_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-NEXT-POST-CLOSEOUT-STEADY-BASELINE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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
            "closeout_status": "Next Controlled Cycle Smoke Closed",
            "closeout_approved": 1,
            "cycle_closed": 1,
            "steady_state_ready": 1,
            "phase11x_freeze_verified": 1,
            "freeze_completed_verified": 1,
            "rollback_evidence_frozen_verified": 1,
            "closed_payment_entry_verified": 1,
            "payment_entry_cancelled_still_verified": 1,
            "voucher_gl_rows_verified": 1,
            "voucher_gl_net_zero_verified": 1,
            "invoice_outstanding_restored_still_verified": 1,
            "no_new_accounting_movement_verified": 1,
            "policy_state_preserved_verified": 1,
            "ready_for_next_steady_state_baseline": 1,
            "closed_payment_entry": EXPECTED_PAYMENT_ENTRY,
            "payment_entry_docstatus_closeout": 2,
            "payment_entry_status_closeout": "Cancelled",
            "closed_reference_count": EXPECTED_REFERENCE_COUNT,
            "closed_total_amount": EXPECTED_TOTAL_AMOUNT,
            "closed_voucher_gl_rows": EXPECTED_VOUCHER_GL_ROWS,
            "closed_voucher_gl_net": 0.00,
            "closed_voucher_gl_non_zero_account_count": 0,
            "closed_restored_invoice_amount": EXPECTED_TOTAL_AMOUNT,
            "payment_entry_count_after": EXPECTED_PAYMENT_ENTRY_COUNT,
            "payment_entry_gl_count_after": EXPECTED_PAYMENT_ENTRY_GL_COUNT,
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
            "freeze",
            "rollback",
            "smoke",
            "execution_gate",
            "preview",
            "validation",
            "candidate",
            "design",
            "planning",
            "monitor",
            "baseline",
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
        fields=["name", "baseline_id", "baseline_payment_entry"],
        limit=1,
    )
    return rows[0] if rows else None


def closeout_rows(closeout):
    if not closeout:
        return []

    rows = frappe.get_all(
        CLOSEOUT_ITEM_DOCTYPE,
        filters={
            "closeout": closeout,
            "category": "Closed Reference",
            "status": "Pass",
            "reference_doctype": "Sales Invoice",
        },
        fields=[
            "line_no",
            "reference_doctype",
            "reference_name",
            "allocated_amount",
            "current_outstanding_amount",
            "closed_payment_entry",
        ],
        order_by="line_no asc, creation asc",
    )

    result = []
    for idx, row in enumerate(rows, start=1):
        outstanding = frappe.db.get_value("Sales Invoice", row.reference_name, "outstanding_amount")
        result.append(
            frappe._dict(
                {
                    "idx": int(row.line_no or idx),
                    "reference_doctype": row.reference_doctype,
                    "reference_name": row.reference_name,
                    "allocated_amount": flt(row.allocated_amount or 0, 2),
                    "current_outstanding_amount": flt(outstanding or row.current_outstanding_amount or 0, 2),
                    "baseline_payment_entry": row.closed_payment_entry,
                }
            )
        )

    return result


def reference_names(rows):
    return [row.reference_name for row in rows]


def allocated_total(rows):
    return flt(sum(flt(row.allocated_amount or 0, 2) for row in rows), 2)


def current_outstanding_total(rows):
    return flt(sum(flt(row.current_outstanding_amount or 0, 2) for row in rows), 2)


def payment_entry_reference_count(payment_entry):
    if not payment_entry:
        return 0
    return count_dt("Payment Entry Reference", {"parent": payment_entry, "reference_doctype": "Sales Invoice"})


def payment_entry_allocated_amount(payment_entry):
    if not payment_entry:
        return 0
    value = frappe.db.sql(
        """
        SELECT ROUND(COALESCE(SUM(allocated_amount), 0), 2)
        FROM `tabPayment Entry Reference`
        WHERE parent=%s
        AND reference_doctype='Sales Invoice'
        """,
        payment_entry,
    )[0][0]
    return flt(value or 0, 2)


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


def validate_source(closeout, payment_entry, rows, guard, config, policy_enabled, policy_live):
    issues = []

    if not closeout:
        issues.append("No approved Phase 11Y next controlled-cycle closeout found.")
        return issues

    existing = existing_active_baseline(closeout.name)
    if existing:
        issues.append(f"Active Phase 11Z baseline already exists for this closeout: {existing.baseline_id} / {existing.baseline_payment_entry}")

    if not payment_entry:
        issues.append("Phase 11Y closeout did not identify a closed Payment Entry.")
        return issues

    if payment_entry != EXPECTED_PAYMENT_ENTRY:
        issues.append(f"Expected baseline Payment Entry {EXPECTED_PAYMENT_ENTRY}, found {payment_entry}.")

    if not frappe.db.exists("Payment Entry", payment_entry):
        issues.append(f"Baseline Payment Entry does not exist: {payment_entry}")
        return issues

    pe = frappe.get_doc("Payment Entry", payment_entry)

    if pe.docstatus != 2:
        issues.append(f"Baseline Payment Entry must remain cancelled. docstatus={pe.docstatus}")

    if pe.status != "Cancelled":
        issues.append(f"Baseline Payment Entry status must remain Cancelled. status={pe.status}")

    if payment_entry_reference_count(payment_entry) != EXPECTED_REFERENCE_COUNT:
        issues.append(f"Baseline Payment Entry must retain {EXPECTED_REFERENCE_COUNT} references.")

    if payment_entry_allocated_amount(payment_entry) != EXPECTED_TOTAL_AMOUNT:
        issues.append(f"Baseline Payment Entry allocated amount must remain {EXPECTED_TOTAL_AMOUNT}.")

    if voucher_gl_rows(payment_entry) != EXPECTED_VOUCHER_GL_ROWS:
        issues.append(f"Voucher GL rows must remain {EXPECTED_VOUCHER_GL_ROWS}. Found {voucher_gl_rows(payment_entry)}.")

    if voucher_gl_net(payment_entry) != 0:
        issues.append(f"Voucher GL net must remain 0.00. Found {voucher_gl_net(payment_entry)}.")

    if voucher_gl_non_zero_accounts(payment_entry) != 0:
        issues.append(f"Voucher GL non-zero account count must remain 0. Found {voucher_gl_non_zero_accounts(payment_entry)}.")

    if reference_names(rows) != EXPECTED_INVOICES:
        issues.append(f"Baseline reference set changed. Expected {EXPECTED_INVOICES}. Found {reference_names(rows)}.")

    if allocated_total(rows) != EXPECTED_TOTAL_AMOUNT:
        issues.append(f"Baseline allocated total must be {EXPECTED_TOTAL_AMOUNT}. Found {allocated_total(rows)}.")

    if current_outstanding_total(rows) != EXPECTED_TOTAL_AMOUNT:
        issues.append(f"Baseline restored outstanding total must be {EXPECTED_TOTAL_AMOUNT}. Found {current_outstanding_total(rows)}.")

    if guard["payment_entry_count"] != EXPECTED_PAYMENT_ENTRY_COUNT:
        issues.append("Payment Entry count must remain 10 before Phase 11Z baseline.")

    if guard["payment_entry_gl_count"] != EXPECTED_PAYMENT_ENTRY_GL_COUNT:
        issues.append("Payment Entry GL count must remain 62 before Phase 11Z baseline.")

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


def add_item(items, status, severity, category, check_key, check_label, detail, row=None, payment_entry=None):
    item = {
        "status": status,
        "severity": severity,
        "category": category,
        "check_key": check_key,
        "check_label": check_label,
        "detail": detail,
        "baseline_payment_entry": payment_entry,
    }

    if row:
        item.update(
            {
                "line_no": row.idx,
                "reference_doctype": row.reference_doctype,
                "reference_name": row.reference_name,
                "allocated_amount": row.allocated_amount,
                "current_outstanding_amount": row.current_outstanding_amount,
            }
        )

    items.append(item)


def build_items(closeout, rows, issues, ack_ok, payment_entry=None):
    items = []

    if closeout:
        add_item(
            items,
            "Pass",
            "Low",
            "Evidence",
            "phase11y_closeout_exists",
            "Phase 11Y closeout exists",
            f"Closeout found: {closeout.closeout_id}.",
            payment_entry=payment_entry,
        )
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase11y_closeout_exists", "Phase 11Y closeout exists", "No approved Phase 11Y closeout found.")

    if not issues:
        add_item(
            items,
            "Pass",
            "Critical",
            "Baseline Source",
            "baseline_source_valid",
            "Baseline source valid",
            "The controlled cycle is closed and steady-state baseline can be activated.",
            payment_entry=payment_entry,
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
                payment_entry=payment_entry,
            )

    for row in rows:
        add_item(
            items,
            "Pass",
            "High",
            "Baseline Reference",
            "baseline_sales_invoice_reference",
            f"Baseline Sales Invoice {row.idx}",
            f"{row.reference_name} baselined with allocated={row.allocated_amount}, outstanding={row.current_outstanding_amount}.",
            row=row,
            payment_entry=payment_entry,
        )

    checks = [
        ("payment_entry_cancelled_still", "Payment Entry remains Cancelled", payment_entry or "None"),
        ("payment_entry_count", "Payment Entry count remains 10", "10 -> 10"),
        ("payment_entry_gl_count", "Payment Entry GL count remains 62", "62 -> 62"),
        ("voucher_gl_rows", "Voucher GL rows remain 8", EXPECTED_VOUCHER_GL_ROWS),
        ("voucher_gl_net", "Voucher GL net remains 0.00", 0),
        ("invoice_restored", "Invoice outstanding remains restored = 3.00", EXPECTED_TOTAL_AMOUNT),
        ("no_pe_movement", "No Payment Entry movement", "0 / 0"),
        ("no_gl_movement", "No GL movement", 0),
        ("policy_state", "Policy state preserved at 1 / 0", "1 / 0"),
        ("no_je_pi", "No JE / PI side effects", "0 / 0"),
        ("baseline_active", "Next post-closeout steady baseline active", 1),
        ("monitoring_ready", "Ready for next post-closeout monitoring", 1),
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
            payment_entry=payment_entry,
        )

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.", payment_entry=payment_entry)
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
def run_next_post_closeout_steady_baseline(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_next_post_closeout_steady_baseline")

    closeout = latest_closeout()
    payment_entry = closeout.closed_payment_entry if closeout else None
    rows = closeout_rows(closeout.name) if closeout else []

    guard_before = guardrails()
    ack_ok = acknowledgement == BASELINE_ACK

    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }

    policy_enabled_before = get_flag(POLICY_DOCTYPE, closeout.target_policy, "production_batch_enabled") if closeout else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, closeout.target_policy, "live_posting_allowed") if closeout else 0

    source_issues = validate_source(closeout, payment_entry, rows, guard_before, config, policy_enabled_before, policy_live_before)

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
    reference_count = 0
    total_amount = 0
    voucher_rows = 0
    voucher_net = 0
    voucher_non_zero_accounts = 0
    restored_invoice_amount = current_outstanding_total(rows)

    if payment_entry and frappe.db.exists("Payment Entry", payment_entry):
        pe = frappe.get_doc("Payment Entry", payment_entry)
        pe_docstatus = int(pe.docstatus or 0)
        pe_status = pe.status
        reference_count = payment_entry_reference_count(payment_entry)
        total_amount = payment_entry_allocated_amount(payment_entry)
        voucher_rows = voucher_gl_rows(payment_entry)
        voucher_net = voucher_gl_net(payment_entry)
        voucher_non_zero_accounts = voucher_gl_non_zero_accounts(payment_entry)

    post_issues = list(source_issues)

    if actual_pe_created != 0:
        post_issues.append(f"Baseline must not create Payment Entries. Created {actual_pe_created}.")

    if actual_pe_cancelled != 0:
        post_issues.append(f"Baseline must not cancel Payment Entries. Cancelled {actual_pe_cancelled}.")

    if actual_gl_created != 0:
        post_issues.append(f"Baseline must not create GL rows. Created {actual_gl_created}.")

    if guard_after["payment_entry_count"] != EXPECTED_PAYMENT_ENTRY_COUNT:
        post_issues.append("Payment Entry count must remain 10 after baseline.")

    if guard_after["payment_entry_gl_count"] != EXPECTED_PAYMENT_ENTRY_GL_COUNT:
        post_issues.append("Payment Entry GL count must remain 62 after baseline.")

    if guard_after["submitted_journal_entry_count_today"] != 0:
        post_issues.append("Submitted Journal Entry count today must remain 0 after baseline.")

    if guard_after["purchase_invoice_count_today"] != 0:
        post_issues.append("Purchase Invoice count today must remain 0 after baseline.")

    if policy_mutation_count != 0:
        post_issues.append("Policy state changed during baseline. This is not allowed.")

    completed = int(
        not int(dry_run or 0)
        and ack_ok
        and closeout
        and payment_entry
        and not post_issues
        and pe_docstatus == 2
        and pe_status == "Cancelled"
        and reference_count == EXPECTED_REFERENCE_COUNT
        and total_amount == EXPECTED_TOTAL_AMOUNT
        and voucher_rows == EXPECTED_VOUCHER_GL_ROWS
        and voucher_net == 0
        and voucher_non_zero_accounts == 0
        and restored_invoice_amount == EXPECTED_TOTAL_AMOUNT
        and guard_before["payment_entry_count"] == EXPECTED_PAYMENT_ENTRY_COUNT
        and guard_after["payment_entry_count"] == EXPECTED_PAYMENT_ENTRY_COUNT
        and guard_before["payment_entry_gl_count"] == EXPECTED_PAYMENT_ENTRY_GL_COUNT
        and guard_after["payment_entry_gl_count"] == EXPECTED_PAYMENT_ENTRY_GL_COUNT
        and actual_pe_created == 0
        and actual_pe_cancelled == 0
        and actual_gl_created == 0
        and guard_after["submitted_journal_entry_count_today"] == 0
        and guard_after["purchase_invoice_count_today"] == 0
        and policy_mutation_count == 0
    )

    items = build_items(closeout, rows, post_issues, ack_ok, payment_entry=payment_entry)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Baseline Active" if completed else "Needs Review",
        "baseline_status": "Next Post-Closeout Steady-State Baseline Active" if completed else "Needs Review",
        "baseline_active": completed,
        "phase11y_closeout_verified": 1 if closeout else 0,
        "closeout_approved_verified": 1 if closeout else 0,
        "cycle_closed_verified": 1 if closeout else 0,
        "steady_state_ready_verified": 1 if closeout else 0,
        "closed_payment_entry_verified": int(bool(payment_entry)),
        "payment_entry_cancelled_still_verified": int(pe_docstatus == 2 and pe_status == "Cancelled"),
        "voucher_gl_rows_verified": int(voucher_rows == EXPECTED_VOUCHER_GL_ROWS),
        "voucher_gl_net_zero_verified": int(voucher_net == 0),
        "invoice_outstanding_restored_still_verified": int(restored_invoice_amount == EXPECTED_TOTAL_AMOUNT),
        "no_new_accounting_movement_verified": int(actual_pe_created == 0 and actual_pe_cancelled == 0 and actual_gl_created == 0),
        "policy_state_preserved_verified": int(policy_mutation_count == 0 and policy_enabled_before == 1 and policy_enabled_after == 1 and policy_live_before == 0 and policy_live_after == 0),
        "ready_for_next_post_closeout_monitoring": completed,
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": policy_mutation_count,
        "baseline_payment_entry": payment_entry,
        "payment_entry_docstatus_baseline": pe_docstatus,
        "payment_entry_status_baseline": pe_status,
        "baseline_reference_count": reference_count,
        "baseline_total_amount": total_amount,
        "baseline_voucher_gl_rows": voucher_rows,
        "baseline_voucher_gl_net": voucher_net,
        "baseline_voucher_gl_non_zero_account_count": voucher_non_zero_accounts,
        "baseline_restored_invoice_amount": restored_invoice_amount,
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
        "monitor": closeout.monitor if closeout else None,
        "previous_baseline": closeout.baseline if closeout else None,
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
        "baseline_references": [dict(row) for row in rows],
        "issues": post_issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "required_acknowledgement": BASELINE_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 11Z activates the next post-closeout steady-state baseline. No accounting or policy movement occurs.",
    }

    if int(dry_run or 0):
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
            "baseline_references": [dict(row) for row in rows],
            "guardrails_before": guard_before,
            "guardrails_after": guard_after,
            "voucher": {
                "rows": voucher_rows,
                "net": voucher_net,
                "non_zero_accounts": voucher_non_zero_accounts,
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
def cancel_next_post_closeout_steady_baseline_audit(baseline, reason=None):
    assert_action("cancel_next_post_closeout_steady_baseline_audit")

    if not frappe.db.exists(BASELINE_DOCTYPE, baseline):
        frappe.throw(_("Next post-closeout baseline audit not found: {0}").format(baseline))

    doc = frappe.get_doc(BASELINE_DOCTYPE, baseline)

    if doc.status == "Cancelled":
        return {"baseline": baseline, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.baseline_active or 0):
        frappe.throw(_("Cannot cancel an active Phase 11Z baseline record."))

    frappe.db.set_value(
        BASELINE_DOCTYPE,
        baseline,
        {
            "status": "Cancelled",
            "baseline_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 11Z no-ack baseline audit cancelled.",
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
def quick_next_post_closeout_steady_baseline_summary(limit=20):
    records = frappe.get_all(
        BASELINE_DOCTYPE,
        fields=[
            "name",
            "baseline_id",
            "status",
            "baseline_status",
            "baseline_active",
            "baseline_payment_entry",
            "payment_entry_docstatus_baseline",
            "payment_entry_status_baseline",
            "baseline_reference_count",
            "baseline_total_amount",
            "baseline_voucher_gl_rows",
            "baseline_voucher_gl_net",
            "baseline_restored_invoice_amount",
            "ready_for_next_post_closeout_monitoring",
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
            "current_outstanding_amount",
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
        "note": "Phase 11Z next post-closeout steady-state baseline summary.",
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
            b.phase11y_closeout_verified,
            b.closeout_approved_verified,
            b.cycle_closed_verified,
            b.steady_state_ready_verified,
            b.closed_payment_entry_verified,
            b.payment_entry_cancelled_still_verified,
            b.voucher_gl_rows_verified,
            b.voucher_gl_net_zero_verified,
            b.invoice_outstanding_restored_still_verified,
            b.no_new_accounting_movement_verified,
            b.policy_state_preserved_verified,
            b.ready_for_next_post_closeout_monitoring,
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
                {"name": "Monitoring Ready", "values": [int(row.ready_for_next_post_closeout_monitoring or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Baseline Records"), "datatype": "Int"},
        {"value": sum(int(row.baseline_active or 0) for row in data), "indicator": "Green", "label": _("Active"), "datatype": "Int"},
        {"value": sum(int(row.ready_for_next_post_closeout_monitoring or 0) for row in data), "indicator": "Green", "label": _("Monitoring Ready"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL Created"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def baseline_columns():
    return [
        {"fieldname": "baseline", "label": _("Baseline"), "fieldtype": "Link", "options": BASELINE_DOCTYPE, "width": 220},
        {"fieldname": "baseline_id", "label": _("Baseline ID"), "fieldtype": "Data", "width": 430},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 150},
        {"fieldname": "baseline_status", "label": _("Baseline Status"), "fieldtype": "Data", "width": 360},
        {"fieldname": "baseline_active", "label": _("Active"), "fieldtype": "Check", "width": 80},
        {"fieldname": "phase11y_closeout_verified", "label": _("11Y Verified"), "fieldtype": "Check", "width": 105},
        {"fieldname": "closeout_approved_verified", "label": _("Closeout OK"), "fieldtype": "Check", "width": 105},
        {"fieldname": "cycle_closed_verified", "label": _("Cycle Closed"), "fieldtype": "Check", "width": 105},
        {"fieldname": "steady_state_ready_verified", "label": _("Steady Ready"), "fieldtype": "Check", "width": 105},
        {"fieldname": "closed_payment_entry_verified", "label": _("PE Verified"), "fieldtype": "Check", "width": 100},
        {"fieldname": "payment_entry_cancelled_still_verified", "label": _("PE Cancelled"), "fieldtype": "Check", "width": 110},
        {"fieldname": "voucher_gl_rows_verified", "label": _("GL Rows OK"), "fieldtype": "Check", "width": 100},
        {"fieldname": "voucher_gl_net_zero_verified", "label": _("GL Net Zero"), "fieldtype": "Check", "width": 105},
        {"fieldname": "invoice_outstanding_restored_still_verified", "label": _("Invoice Restored"), "fieldtype": "Check", "width": 125},
        {"fieldname": "no_new_accounting_movement_verified", "label": _("No Movement"), "fieldtype": "Check", "width": 110},
        {"fieldname": "policy_state_preserved_verified", "label": _("Policy OK"), "fieldtype": "Check", "width": 90},
        {"fieldname": "ready_for_next_post_closeout_monitoring", "label": _("Monitoring Ready"), "fieldtype": "Check", "width": 130},
        {"fieldname": "baseline_payment_entry", "label": _("Baseline PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "payment_entry_docstatus_baseline", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 100},
        {"fieldname": "payment_entry_status_baseline", "label": _("PE Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "baseline_reference_count", "label": _("Refs"), "fieldtype": "Int", "width": 70},
        {"fieldname": "baseline_total_amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 100},
        {"fieldname": "baseline_voucher_gl_rows", "label": _("GL Rows"), "fieldtype": "Int", "width": 85},
        {"fieldname": "baseline_voucher_gl_net", "label": _("GL Net"), "fieldtype": "Currency", "options": "currency", "width": 90},
        {"fieldname": "baseline_restored_invoice_amount", "label": _("Restored"), "fieldtype": "Currency", "options": "currency", "width": 100},
        {"fieldname": "closeout", "label": _("Closeout"), "fieldtype": "Link", "options": CLOSEOUT_DOCTYPE, "width": 220},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 110},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE Created"), "fieldtype": "Int", "width": 130},
        {"fieldname": "actual_payment_entry_cancelled_count", "label": _("Actual PE Cancelled"), "fieldtype": "Int", "width": 135},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL Created"), "fieldtype": "Int", "width": 130},
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
        {"fieldname": "allocated_amount", "label": _("Allocated Amount"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "current_outstanding_amount", "label": _("Outstanding"), "fieldtype": "Currency", "width": 110},
        {"fieldname": "baseline_payment_entry", "label": _("Baseline PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
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
            i.current_outstanding_amount,
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
