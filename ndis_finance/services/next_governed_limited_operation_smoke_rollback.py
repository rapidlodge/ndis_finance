import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, today

from ndis_finance.services.permissions import assert_action


ROLLBACK_ACK = "I_CONFIRM_PHASE13G_ROLLBACK_NEXT_GOVERNED_LIMITED_OPERATION_SMOKE_CANCEL_ONE_PAYMENT_ENTRY"

POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
SMOKE_DOCTYPE = "NDIS Next Governed Limited Op Smoke"
SMOKE_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Smoke Item"
ROLLBACK_DOCTYPE = "NDIS Next Governed Limited Op Smoke Rollback"
ROLLBACK_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Smoke Rollback Item"

SMOKE_READY_FIELD = "ready_for_next_governed_limited_op_smoke_rollback"
ROLLBACK_READY_FIELD = "ready_for_next_governed_limited_op_rollback_freeze"

ROLLBACK_PAYMENT_ENTRY = "ACC-PAY-2026-00014"
EXPECTED_INVOICES = ["ACC-SINV-2026-00005", "ACC-SINV-2026-00006", "ACC-SINV-2026-00008"]

EXPECTED_PAYMENT_ENTRY_COUNT_BEFORE = 13
EXPECTED_PAYMENT_ENTRY_COUNT_AFTER = 13
EXPECTED_PAYMENT_ENTRY_GL_COUNT_BEFORE = 82
EXPECTED_PAYMENT_ENTRY_GL_COUNT_AFTER = 86
EXPECTED_TOTAL_AMOUNT = 3.00
EXPECTED_INVOICE_COUNT = 3
EXPECTED_GL_ROWS_BEFORE = 4
EXPECTED_GL_ROWS_AFTER = 8
EXPECTED_REVERSAL_GL_ROWS = 4
EXPECTED_GL_NET = 0.00

ROLLBACK_SOURCE_DOCTYPE = "Sales Invoice"
ROLLBACK_REFERENCE_DOCTYPE = "Sales Invoice"
ROLLBACK_PARTY_TYPE = "Customer"


def make_rollback_id():
    timestamp = now_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-NEXT-GOVERNED-LIMITED-OP-SMOKE-ROLLBACK-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def row_get(row, fieldname, default=None):
    try:
        return row.get(fieldname, default)
    except Exception:
        return getattr(row, fieldname, default)


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


def payment_entry_state(payment_entry):
    if not payment_entry or not frappe.db.exists("Payment Entry", payment_entry):
        return frappe._dict({"docstatus": 0, "status": None})
    pe = frappe.get_doc("Payment Entry", payment_entry)
    return frappe._dict({"docstatus": int(pe.docstatus or 0), "status": pe.status})


def payment_entry_gl_rows(payment_entry):
    return count_dt("GL Entry", {"voucher_type": "Payment Entry", "voucher_no": payment_entry})


def payment_entry_gl_net(payment_entry):
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


def reversal_gl_rows(payment_entry):
    return max(0, int(payment_entry_gl_rows(payment_entry) or 0) - EXPECTED_GL_ROWS_BEFORE)


def outstanding_total(invoice_names):
    if not invoice_names:
        return 0
    value = frappe.db.sql(
        """
        SELECT ROUND(COALESCE(SUM(outstanding_amount), 0), 2)
        FROM `tabSales Invoice`
        WHERE name IN %(names)s
        """,
        {"names": tuple(invoice_names)},
    )[0][0]
    return flt(value or 0, 2)


def latest_smoke():
    filters = {
        "status": "Completed",
        "smoke_status": "Next Governed Limited Operation Smoke Completed",
        "smoke_completed": 1,
        "phase13e_execution_gate_verified": 1,
        "execution_gate_approved_verified": 1,
        "execution_gate_source_verified": 1,
        "execution_gate_reference_verified": 1,
        "execution_gate_party_type_verified": 1,
        "execution_gate_reference_set_verified": 1,
        "execution_gate_shape_verified": 1,
        "execution_gate_smoke_allowed_verified": 1,
        "invoice_submission_verified": 1,
        "invoice_outstanding_verified": 1,
        "policy_state_preserved_verified": 1,
        "accounting_movement_verified": 1,
        "smoke_source_doctype": ROLLBACK_SOURCE_DOCTYPE,
        "smoke_reference_doctype": ROLLBACK_REFERENCE_DOCTYPE,
        "smoke_party_type": ROLLBACK_PARTY_TYPE,
        "smoke_invoice_count": EXPECTED_INVOICE_COUNT,
        "smoke_total_amount": EXPECTED_TOTAL_AMOUNT,
        "smoke_payment_entry": ROLLBACK_PAYMENT_ENTRY,
        "smoke_payment_entry_docstatus": 1,
        "smoke_payment_entry_status": "Submitted",
        "smoke_gl_rows": EXPECTED_GL_ROWS_BEFORE,
        "smoke_gl_net": EXPECTED_GL_NET,
        "payment_entry_count_before": 12,
        "payment_entry_count_after": EXPECTED_PAYMENT_ENTRY_COUNT_BEFORE,
        "payment_entry_gl_count_before": 78,
        "payment_entry_gl_count_after": EXPECTED_PAYMENT_ENTRY_GL_COUNT_BEFORE,
        "actual_payment_entry_created_count": 1,
        "actual_payment_entry_cancelled_count": 0,
        "actual_gl_created_count": 4,
        "submitted_journal_entry_count_today": 0,
        "purchase_invoice_count_today": 0,
        "target_policy_enabled_after": 1,
        "target_policy_live_after": 0,
        "actual_policy_mutation_count": 0,
        "blocker_count": 0,
        "warning_count": 0,
    }

    if has_column(SMOKE_DOCTYPE, SMOKE_READY_FIELD):
        filters[SMOKE_READY_FIELD] = 1

    rows = frappe.get_all(
        SMOKE_DOCTYPE,
        filters=filters,
        fields=[
            "name",
            "smoke_id",
            "smoke_source_doctype",
            "smoke_reference_doctype",
            "smoke_party_type",
            "smoke_customer",
            "smoke_company",
            "smoke_currency",
            "smoke_invoice_names",
            "smoke_invoice_count",
            "smoke_total_amount",
            "smoke_payment_entry",
            "smoke_payment_entry_docstatus",
            "smoke_payment_entry_status",
            "smoke_gl_rows",
            "smoke_gl_net",
            "execution_gate",
            "preview",
            "candidate_validation",
            "candidate_selection",
            "design",
            "planning",
            "monitor",
            "baseline",
            "closeout",
            "freeze",
            "rollback",
            "target_policy",
            "target_policy_name",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_completed_rollback(smoke):
    rows = frappe.get_all(
        ROLLBACK_DOCTYPE,
        filters={
            "smoke": smoke,
            "status": "Rolled Back",
            "rollback_completed": 1,
        },
        fields=["name", "rollback_id", "rollback_payment_entry"],
        limit=1,
    )
    return rows[0] if rows else None


def smoke_rows(smoke):
    rows = frappe.get_all(
        SMOKE_ITEM_DOCTYPE,
        filters={
            "smoke": smoke,
            "category": "Smoke Reference",
            "status": "Pass",
            "reference_doctype": "Sales Invoice",
        },
        fields=[
            "line_no",
            "reference_doctype",
            "reference_name",
            "customer",
            "company",
            "currency",
            "smoke_amount",
            "allocated_amount",
            "invoice_docstatus",
            "outstanding_before",
            "outstanding_after",
            "smoke_payment_entry",
        ],
        order_by="line_no asc, creation asc",
    )

    result = []
    for idx, row in enumerate(rows, start=1):
        si = frappe.db.get_value(
            "Sales Invoice",
            row.reference_name,
            ["docstatus", "customer", "company", "currency", "outstanding_amount"],
            as_dict=True,
        ) if frappe.db.exists("Sales Invoice", row.reference_name) else None

        result.append(
            frappe._dict(
                {
                    "idx": int(row.line_no or idx),
                    "reference_doctype": row.reference_doctype,
                    "reference_name": row.reference_name,
                    "rollback_amount": flt(row.smoke_amount or row.allocated_amount or 0, 2),
                    "customer": si.customer if si else row.customer,
                    "company": si.company if si else row.company,
                    "currency": si.currency if si else row.currency,
                    "invoice_docstatus": int(si.docstatus or 0) if si else int(row.invoice_docstatus or 0),
                    "outstanding_before": flt((si.outstanding_amount if si else row.outstanding_after) or 0, 2),
                    "smoke_outstanding_before": flt(row.outstanding_before or 0, 2),
                    "smoke_payment_entry": row.smoke_payment_entry,
                }
            )
        )

    return result


def reference_names(rows):
    return [row.reference_name for row in rows]


def rollback_total(rows):
    return flt(sum(flt(row.rollback_amount or 0, 2) for row in rows), 2)


def unique_value(rows, fieldname):
    values = sorted(set([getattr(row, fieldname, None) for row in rows if getattr(row, fieldname, None)]))
    return values[0] if len(values) == 1 else None


def validate_source(smoke, rows, guard, config, policy_enabled, policy_live):
    issues = []

    if not smoke:
        issues.append("No completed Phase 13F smoke found for rollback.")
        return issues

    existing = existing_completed_rollback(smoke.name)
    if existing:
        issues.append(f"Completed Phase 13G rollback already exists for this smoke: {existing.rollback_id} / {existing.rollback_payment_entry}")

    state = payment_entry_state(ROLLBACK_PAYMENT_ENTRY)

    if not frappe.db.exists("Payment Entry", ROLLBACK_PAYMENT_ENTRY):
        issues.append(f"Rollback Payment Entry does not exist: {ROLLBACK_PAYMENT_ENTRY}")

    if state.docstatus != 1 or state.status != "Submitted":
        issues.append(f"Rollback Payment Entry must be submitted before rollback. Found {state.docstatus} / {state.status}")

    if reference_names(rows) != EXPECTED_INVOICES:
        issues.append(f"Rollback invoice set changed. Expected {EXPECTED_INVOICES}. Found {reference_names(rows)}.")

    if len(rows) != EXPECTED_INVOICE_COUNT:
        issues.append(f"Rollback invoice count must be {EXPECTED_INVOICE_COUNT}. Found {len(rows)}.")

    if rollback_total(rows) != EXPECTED_TOTAL_AMOUNT:
        issues.append(f"Rollback total amount must be {EXPECTED_TOTAL_AMOUNT}. Found {rollback_total(rows)}.")

    if payment_entry_gl_rows(ROLLBACK_PAYMENT_ENTRY) != EXPECTED_GL_ROWS_BEFORE:
        issues.append(f"Rollback Payment Entry must have {EXPECTED_GL_ROWS_BEFORE} GL rows before rollback.")

    if payment_entry_gl_net(ROLLBACK_PAYMENT_ENTRY) != EXPECTED_GL_NET:
        issues.append("Rollback Payment Entry GL net must be 0.00 before rollback.")

    if outstanding_total(EXPECTED_INVOICES) != 0:
        issues.append("Invoice outstanding total must be 0.00 before rollback.")

    if guard["payment_entry_count"] != EXPECTED_PAYMENT_ENTRY_COUNT_BEFORE:
        issues.append("Payment Entry count must be 13 before rollback.")

    if guard["payment_entry_gl_count"] != EXPECTED_PAYMENT_ENTRY_GL_COUNT_BEFORE:
        issues.append("Payment Entry GL count must be 82 before rollback.")

    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today must remain 0 before rollback.")

    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today must remain 0 before rollback.")

    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must remain enabled before rollback.")

    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must remain 0 before rollback.")

    if policy_enabled != 1:
        issues.append("Target policy production_batch_enabled must remain 1.")

    if policy_live != 0:
        issues.append("Target policy live_posting_allowed must remain 0.")

    if config["sandbox_enabled"] != 1:
        issues.append("Sandbox config must be enabled for governed rollback.")

    if config["production_mode"] != 0:
        issues.append("Production mode config must remain 0 for governed rollback.")

    if config["live_pe_enabled"] != 0:
        issues.append("Live Payment Entry posting config must remain 0 for governed rollback.")

    return issues


def cancel_payment_entry():
    pe = frappe.get_doc("Payment Entry", ROLLBACK_PAYMENT_ENTRY)
    if int(pe.docstatus or 0) != 1:
        frappe.throw(_("Payment Entry must be submitted before rollback: {0}").format(ROLLBACK_PAYMENT_ENTRY))
    pe.cancel()
    return pe


def build_items(rows, issues, ack_ok, completed=0):
    items = []

    if not issues:
        items.append({
            "status": "Pass",
            "severity": "Critical",
            "category": "Rollback Source",
            "check_key": "rollback_source_valid",
            "check_label": "Rollback source valid",
            "detail": f"Phase 13F smoke Payment Entry {ROLLBACK_PAYMENT_ENTRY} can be rolled back.",
            "rollback_payment_entry": ROLLBACK_PAYMENT_ENTRY,
        })
    else:
        for issue in issues:
            items.append({
                "status": "Blocker",
                "severity": "Critical",
                "category": "Rollback Source",
                "check_key": "rollback_source_valid",
                "check_label": "Rollback source valid",
                "detail": issue,
                "rollback_payment_entry": ROLLBACK_PAYMENT_ENTRY,
            })

    for row in rows:
        outstanding_after = frappe.db.get_value("Sales Invoice", row.reference_name, "outstanding_amount") if completed else row.outstanding_before
        items.append({
            "status": "Pass",
            "severity": "High",
            "category": "Rollback Reference",
            "check_key": "rollback_sales_invoice_reference",
            "check_label": f"Rollback Sales Invoice {row.idx}",
            "detail": f"{row.reference_name} rollback amount={row.rollback_amount}, before={row.outstanding_before}, after={flt(outstanding_after or 0, 2)}.",
            "line_no": row.idx,
            "reference_doctype": row.reference_doctype,
            "reference_name": row.reference_name,
            "customer": row.customer,
            "company": row.company,
            "currency": row.currency,
            "rollback_amount": row.rollback_amount,
            "outstanding_before": row.outstanding_before,
            "outstanding_after": flt(outstanding_after or 0, 2),
            "rollback_payment_entry": ROLLBACK_PAYMENT_ENTRY,
        })

    items.append({
        "status": "Pass" if ack_ok else "Warning",
        "severity": "Low" if ack_ok else "Medium",
        "category": "Acknowledgement",
        "check_key": "ack_ok",
        "check_label": "Acknowledgement supplied",
        "detail": "Exact acknowledgement supplied." if ack_ok else f"Required acknowledgement not supplied: {ROLLBACK_ACK}",
        "rollback_payment_entry": ROLLBACK_PAYMENT_ENTRY,
    })

    return items


def summarise_items(items):
    return {
        "blocker_count": len([i for i in items if i["status"] == "Blocker"]),
        "warning_count": len([i for i in items if i["status"] == "Warning"]),
        "pass_count": len([i for i in items if i["status"] == "Pass"]),
        "info_count": len([i for i in items if i["status"] == "Info"]),
        "item_count": len(items),
    }


def create_items(doc, items):
    for item in items:
        row = frappe.new_doc(ROLLBACK_ITEM_DOCTYPE)
        row.rollback = doc.name
        for fieldname, value in item.items():
            if row.meta.has_field(fieldname):
                setattr(row, fieldname, value)
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_next_governed_limited_operation_smoke_rollback(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_next_governed_limited_operation_smoke_rollback")

    smoke = latest_smoke()
    rows = smoke_rows(smoke.name) if smoke else []

    guard_before = guardrails()
    ack_ok = acknowledgement == ROLLBACK_ACK

    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }

    policy_enabled_before = get_flag(POLICY_DOCTYPE, smoke.target_policy, "production_batch_enabled") if smoke else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, smoke.target_policy, "live_posting_allowed") if smoke else 0

    state_before = payment_entry_state(ROLLBACK_PAYMENT_ENTRY)
    gl_rows_before = payment_entry_gl_rows(ROLLBACK_PAYMENT_ENTRY)
    gl_net_before = payment_entry_gl_net(ROLLBACK_PAYMENT_ENTRY)

    source_issues = validate_source(smoke, rows, guard_before, config, policy_enabled_before, policy_live_before)

    if not int(dry_run or 0) and ack_ok and not source_issues:
        cancel_payment_entry()

    guard_after = guardrails()

    policy_enabled_after = get_flag(POLICY_DOCTYPE, smoke.target_policy, "production_batch_enabled") if smoke else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, smoke.target_policy, "live_posting_allowed") if smoke else 0

    state_after = payment_entry_state(ROLLBACK_PAYMENT_ENTRY)
    gl_rows_after = payment_entry_gl_rows(ROLLBACK_PAYMENT_ENTRY)
    gl_net_after = payment_entry_gl_net(ROLLBACK_PAYMENT_ENTRY)
    reversal_rows = reversal_gl_rows(ROLLBACK_PAYMENT_ENTRY)
    restored_amount = outstanding_total(EXPECTED_INVOICES)

    actual_pe_created = guard_after["payment_entry_count"] - guard_before["payment_entry_count"]
    actual_pe_cancelled = int(state_before.docstatus == 1 and state_after.docstatus == 2)
    actual_gl_created = guard_after["payment_entry_gl_count"] - guard_before["payment_entry_gl_count"]

    policy_mutation_count = int(
        policy_enabled_before != policy_enabled_after
        or policy_live_before != policy_live_after
        or guard_before["production_batch_enabled_policy_count"] != guard_after["production_batch_enabled_policy_count"]
        or guard_before["live_posting_allowed_policy_count"] != guard_after["live_posting_allowed_policy_count"]
    )

    post_issues = list(source_issues)

    if not int(dry_run or 0) and ack_ok and not source_issues:
        if state_after.docstatus != 2:
            post_issues.append("Rollback Payment Entry must be cancelled after rollback.")
        if state_after.status != "Cancelled":
            post_issues.append("Rollback Payment Entry status must be Cancelled after rollback.")
        if gl_rows_after != EXPECTED_GL_ROWS_AFTER:
            post_issues.append(f"Voucher GL rows after rollback must be {EXPECTED_GL_ROWS_AFTER}. Found {gl_rows_after}.")
        if reversal_rows != EXPECTED_REVERSAL_GL_ROWS:
            post_issues.append(f"Reversal GL rows must be {EXPECTED_REVERSAL_GL_ROWS}. Found {reversal_rows}.")
        if gl_net_after != EXPECTED_GL_NET:
            post_issues.append(f"Voucher GL net after rollback must be {EXPECTED_GL_NET}. Found {gl_net_after}.")
        if restored_amount != EXPECTED_TOTAL_AMOUNT:
            post_issues.append(f"Restored invoice amount must be {EXPECTED_TOTAL_AMOUNT}. Found {restored_amount}.")
        if actual_pe_created != 0:
            post_issues.append(f"Rollback must create 0 Payment Entries. Created {actual_pe_created}.")
        if actual_pe_cancelled != 1:
            post_issues.append(f"Rollback must cancel exactly 1 Payment Entry. Cancelled {actual_pe_cancelled}.")
        if actual_gl_created != 4:
            post_issues.append(f"Rollback must create exactly 4 reversal GL rows. Created {actual_gl_created}.")
        if guard_after["payment_entry_count"] != EXPECTED_PAYMENT_ENTRY_COUNT_AFTER:
            post_issues.append("Payment Entry count must remain 13 after rollback.")
        if guard_after["payment_entry_gl_count"] != EXPECTED_PAYMENT_ENTRY_GL_COUNT_AFTER:
            post_issues.append("Payment Entry GL count must be 86 after rollback.")

    if guard_after["submitted_journal_entry_count_today"] != 0:
        post_issues.append("Submitted Journal Entry today must remain 0 after rollback.")
    if guard_after["purchase_invoice_count_today"] != 0:
        post_issues.append("Purchase Invoice today must remain 0 after rollback.")
    if policy_mutation_count != 0:
        post_issues.append("Policy state changed during rollback. This is not allowed.")

    completed = int(
        not int(dry_run or 0)
        and ack_ok
        and smoke
        and not post_issues
        and state_before.docstatus == 1
        and state_after.docstatus == 2
        and state_after.status == "Cancelled"
        and gl_rows_before == EXPECTED_GL_ROWS_BEFORE
        and gl_rows_after == EXPECTED_GL_ROWS_AFTER
        and reversal_rows == EXPECTED_REVERSAL_GL_ROWS
        and gl_net_after == EXPECTED_GL_NET
        and restored_amount == EXPECTED_TOTAL_AMOUNT
        and actual_pe_created == 0
        and actual_pe_cancelled == 1
        and actual_gl_created == 4
        and guard_before["payment_entry_count"] == EXPECTED_PAYMENT_ENTRY_COUNT_BEFORE
        and guard_after["payment_entry_count"] == EXPECTED_PAYMENT_ENTRY_COUNT_AFTER
        and guard_before["payment_entry_gl_count"] == EXPECTED_PAYMENT_ENTRY_GL_COUNT_BEFORE
        and guard_after["payment_entry_gl_count"] == EXPECTED_PAYMENT_ENTRY_GL_COUNT_AFTER
        and guard_after["submitted_journal_entry_count_today"] == 0
        and guard_after["purchase_invoice_count_today"] == 0
        and policy_mutation_count == 0
    )

    items = build_items(rows, post_issues, ack_ok, completed=completed)
    item_summary = summarise_items(items)

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Rolled Back" if completed else "Needs Review",
        "rollback_status": "Next Governed Limited Operation Smoke Rolled Back" if completed else "Needs Review",
        "rollback_completed": completed,

        "phase13f_smoke_verified": 1 if smoke else 0,
        "smoke_completed_verified": 1 if smoke else 0,
        "smoke_payment_entry_verified": int(smoke and smoke.smoke_payment_entry == ROLLBACK_PAYMENT_ENTRY),
        "smoke_payment_entry_submitted_before_verified": int(state_before.docstatus == 1 and state_before.status == "Submitted"),
        "smoke_payment_entry_cancelled_after_verified": int(state_after.docstatus == 2 and state_after.status == "Cancelled"),
        "smoke_gl_rows_before_verified": int(gl_rows_before == EXPECTED_GL_ROWS_BEFORE and gl_net_before == EXPECTED_GL_NET),
        "rollback_gl_rows_verified": int(actual_gl_created == 4),
        "voucher_gl_rows_verified": int(gl_rows_after == EXPECTED_GL_ROWS_AFTER),
        "voucher_gl_net_zero_verified": int(gl_net_after == EXPECTED_GL_NET),
        "invoice_outstanding_restored_verified": int(restored_amount == EXPECTED_TOTAL_AMOUNT),
        "policy_state_preserved_verified": int(policy_mutation_count == 0 and policy_enabled_before == 1 and policy_enabled_after == 1 and policy_live_before == 0 and policy_live_after == 0),
        "accounting_movement_verified": int(actual_pe_created == 0 and actual_pe_cancelled == 1 and actual_gl_created == 4),

        "rollback_payment_entry": ROLLBACK_PAYMENT_ENTRY,
        "rollback_payment_entry_docstatus_before": state_before.docstatus,
        "rollback_payment_entry_status_before": state_before.status,
        "rollback_payment_entry_docstatus_after": state_after.docstatus,
        "rollback_payment_entry_status_after": state_after.status,

        "rollback_source_doctype": ROLLBACK_SOURCE_DOCTYPE,
        "rollback_reference_doctype": ROLLBACK_REFERENCE_DOCTYPE,
        "rollback_party_type": ROLLBACK_PARTY_TYPE,
        "rollback_customer": unique_value(rows, "customer"),
        "rollback_company": unique_value(rows, "company"),
        "rollback_currency": unique_value(rows, "currency"),
        "rollback_invoice_names": ", ".join(reference_names(rows)),
        "rollback_invoice_count": len(rows),
        "rollback_total_amount": rollback_total(rows),
        "rollback_restored_invoice_amount": restored_amount,

        "rollback_gl_rows_before": gl_rows_before,
        "rollback_gl_rows_after": gl_rows_after,
        "rollback_reversal_gl_rows": reversal_rows,
        "rollback_gl_net": gl_net_after,

        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guard_after["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
        "actual_payment_entry_created_count": actual_pe_created,
        "actual_payment_entry_cancelled_count": actual_pe_cancelled,
        "actual_gl_created_count": actual_gl_created,

        "submitted_journal_entry_count_today": guard_after["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_after["purchase_invoice_count_today"],

        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": smoke.target_policy if smoke else None,
        "target_policy_name": smoke.target_policy_name if smoke else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_before": policy_live_before,
        "target_policy_live_after": policy_live_after,
        "actual_policy_mutation_count": policy_mutation_count,

        ROLLBACK_READY_FIELD: completed,

        "smoke": smoke.name if smoke else None,
        "execution_gate": smoke.execution_gate if smoke else None,
        "preview": smoke.preview if smoke else None,
        "candidate_validation": smoke.candidate_validation if smoke else None,
        "candidate_selection": smoke.candidate_selection if smoke else None,
        "design": smoke.design if smoke else None,
        "planning": smoke.planning if smoke else None,
        "monitor": smoke.monitor if smoke else None,
        "baseline": smoke.baseline if smoke else None,
        "closeout": smoke.closeout if smoke else None,
        "freeze": smoke.freeze if smoke else None,
        "previous_rollback": smoke.rollback if smoke else None,

        **item_summary,
        "items": items,
        "issues": post_issues,
        "required_acknowledgement": ROLLBACK_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 13G rolls back the next governed limited-operation smoke. Exactly one submitted Payment Entry is cancelled and four reversal GL rows are expected.",
    }

    if int(dry_run or 0):
        return result

    doc = frappe.new_doc(ROLLBACK_DOCTYPE)
    doc.rollback_id = make_rollback_id()

    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)

    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = ROLLBACK_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.rollback_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    create_items(doc, items)
    frappe.db.commit()

    return {
        **result,
        "created": True,
        "rollback": doc.name,
        "rollback_id": doc.rollback_id,
        "rollback_payment_entry": ROLLBACK_PAYMENT_ENTRY,
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_next_governed_limited_operation_smoke_rollback_audit(rollback, reason=None):
    assert_action("cancel_next_governed_limited_operation_smoke_rollback_audit")

    if not frappe.db.exists(ROLLBACK_DOCTYPE, rollback):
        frappe.throw(_("Next governed limited-operation smoke rollback audit not found: {0}").format(rollback))

    doc = frappe.get_doc(ROLLBACK_DOCTYPE, rollback)

    if doc.status == "Cancelled":
        return {"rollback": rollback, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.rollback_completed or 0):
        frappe.throw(_("Cannot cancel a completed Phase 13G rollback record."))

    frappe.db.set_value(
        ROLLBACK_DOCTYPE,
        rollback,
        {
            "status": "Cancelled",
            "rollback_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 13G no-ack rollback audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        f"""
        UPDATE `tab{ROLLBACK_ITEM_DOCTYPE}`
        SET status='Cancelled'
        WHERE rollback=%(rollback)s
        """,
        {"rollback": rollback},
    )

    frappe.db.commit()

    return {
        "rollback": rollback,
        "status": "Cancelled",
        "note": "No-ack rollback audit cancelled only. No accounting movement occurred.",
    }


@frappe.whitelist()
def quick_next_governed_limited_operation_smoke_rollback_summary(limit=20):
    return {
        "rollback_records": frappe.get_all(
            ROLLBACK_DOCTYPE,
            filters={"rollback_payment_entry": ROLLBACK_PAYMENT_ENTRY},
            fields=[
                "name",
                "rollback_id",
                "status",
                "rollback_status",
                "rollback_completed",
                "rollback_payment_entry",
                "rollback_payment_entry_docstatus_before",
                "rollback_payment_entry_status_before",
                "rollback_payment_entry_docstatus_after",
                "rollback_payment_entry_status_after",
                "rollback_invoice_names",
                "rollback_invoice_count",
                "rollback_total_amount",
                "rollback_restored_invoice_amount",
                "rollback_gl_rows_before",
                "rollback_gl_rows_after",
                "rollback_reversal_gl_rows",
                "rollback_gl_net",
                "payment_entry_count_before",
                "payment_entry_count_after",
                "payment_entry_gl_count_before",
                "payment_entry_gl_count_after",
                "actual_payment_entry_created_count",
                "actual_payment_entry_cancelled_count",
                "actual_gl_created_count",
                "submitted_journal_entry_count_today",
                "purchase_invoice_count_today",
                ROLLBACK_READY_FIELD,
                "checked_on",
                "checked_by",
            ],
            order_by="creation desc",
            limit=int(limit or 20),
        ),
        "items": frappe.get_all(
            ROLLBACK_ITEM_DOCTYPE,
            fields=[
                "name",
                "rollback",
                "status",
                "severity",
                "category",
                "check_key",
                "check_label",
                "line_no",
                "reference_doctype",
                "reference_name",
                "customer",
                "company",
                "currency",
                "rollback_amount",
                "outstanding_before",
                "outstanding_after",
                "rollback_payment_entry",
                "detail",
            ],
            order_by="creation desc",
            limit=int(limit or 20),
        ),
        "required_acknowledgement": ROLLBACK_ACK,
        "guardrails": guardrails(),
        "note": "Phase 13G next governed limited-operation smoke rollback summary.",
    }


def execute_rollback_report(filters=None):
    columns = [
        {"fieldname": "rollback", "label": _("Rollback"), "fieldtype": "Link", "options": ROLLBACK_DOCTYPE, "width": 220},
        {"fieldname": "rollback_id", "label": _("Rollback ID"), "fieldtype": "Data", "width": 560},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 140},
        {"fieldname": "rollback_status", "label": _("Rollback Status"), "fieldtype": "Data", "width": 410},
        {"fieldname": "rollback_completed", "label": _("Completed"), "fieldtype": "Check", "width": 100},
        {"fieldname": "rollback_payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "rollback_payment_entry_docstatus_after", "label": _("PE Docstatus After"), "fieldtype": "Int", "width": 140},
        {"fieldname": "rollback_payment_entry_status_after", "label": _("PE Status After"), "fieldtype": "Data", "width": 130},
        {"fieldname": "rollback_invoice_names", "label": _("Invoices"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "rollback_total_amount", "label": _("Amount"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "rollback_restored_invoice_amount", "label": _("Restored"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "rollback_gl_rows_after", "label": _("Voucher GL Rows"), "fieldtype": "Int", "width": 130},
        {"fieldname": "rollback_reversal_gl_rows", "label": _("Reversal Rows"), "fieldtype": "Int", "width": 120},
        {"fieldname": "rollback_gl_net", "label": _("GL Net"), "fieldtype": "Currency", "width": 100},
        {"fieldname": ROLLBACK_READY_FIELD, "label": _("Freeze Ready"), "fieldtype": "Check", "width": 120},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 115},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 115},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL Created"), "fieldtype": "Int", "width": 135},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            name AS rollback,
            rollback_id,
            status,
            rollback_status,
            rollback_completed,
            rollback_payment_entry,
            rollback_payment_entry_docstatus_after,
            rollback_payment_entry_status_after,
            rollback_invoice_names,
            rollback_total_amount,
            rollback_restored_invoice_amount,
            rollback_gl_rows_after,
            rollback_reversal_gl_rows,
            rollback_gl_net,
            `{ROLLBACK_READY_FIELD}` AS `{ROLLBACK_READY_FIELD}`,
            payment_entry_count_before,
            payment_entry_count_after,
            payment_entry_gl_count_before,
            payment_entry_gl_count_after,
            actual_gl_created_count,
            checked_on
        FROM `tab{ROLLBACK_DOCTYPE}`
        WHERE rollback_payment_entry=%(payment_entry)s
        ORDER BY creation DESC
        """,
        {"payment_entry": ROLLBACK_PAYMENT_ENTRY},
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.rollback_id for row in data[:20]],
            "datasets": [
                {"name": "Rollback Completed", "values": [int(row.rollback_completed or 0) for row in data[:20]]},
                {"name": "Freeze Ready", "values": [int(row.get(ROLLBACK_READY_FIELD) or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Rollback Records"), "datatype": "Int"},
        {"value": sum(int(row.rollback_completed or 0) for row in data), "indicator": "Green", "label": _("Completed"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Orange", "label": _("Actual GL Created"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_item_report(filters=None):
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": ROLLBACK_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "rollback", "label": _("Rollback"), "fieldtype": "Link", "options": ROLLBACK_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 190},
        {"fieldname": "line_no", "label": _("Line"), "fieldtype": "Int", "width": 60},
        {"fieldname": "reference_doctype", "label": _("Ref DocType"), "fieldtype": "Data", "width": 130},
        {"fieldname": "reference_name", "label": _("Reference"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 180},
        {"fieldname": "rollback_amount", "label": _("Rollback Amount"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "outstanding_before", "label": _("Outstanding Before"), "fieldtype": "Currency", "width": 145},
        {"fieldname": "outstanding_after", "label": _("Outstanding After"), "fieldtype": "Currency", "width": 140},
        {"fieldname": "rollback_payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 650},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            name AS item,
            rollback,
            status,
            category,
            line_no,
            reference_doctype,
            reference_name,
            rollback_amount,
            outstanding_before,
            outstanding_after,
            rollback_payment_entry,
            detail
        FROM `tab{ROLLBACK_ITEM_DOCTYPE}`
        ORDER BY creation DESC
        """,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": ["Pass", "Warning", "Blocker", "Info"],
            "datasets": [{
                "name": "Items",
                "values": [
                    len([row for row in data if row.status == "Pass"]),
                    len([row for row in data if row.status == "Warning"]),
                    len([row for row in data if row.status == "Blocker"]),
                    len([row for row in data if row.status == "Info"]),
                ],
            }],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Items"), "datatype": "Int"},
        {"value": len([row for row in data if row.category == "Rollback Reference"]), "indicator": "Green", "label": _("Rollback References"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_rollback_report(filters)
    guard = guardrails()
    summary.append({"value": guard["payment_entry_count"], "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"})
    summary.append({"value": guard["payment_entry_gl_count"], "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"})
    summary.append({"value": guard["submitted_journal_entry_count_today"], "indicator": "Red", "label": _("Submitted JE Today"), "datatype": "Int"})
    summary.append({"value": guard["purchase_invoice_count_today"], "indicator": "Red", "label": _("Purchase Invoice Today"), "datatype": "Int"})
    summary.append({"value": guard["production_batch_enabled_policy_count"], "indicator": "Green", "label": _("Enabled Policies"), "datatype": "Int"})
    summary.append({"value": guard["live_posting_allowed_policy_count"], "indicator": "Red", "label": _("Live Policies"), "datatype": "Int"})
    return columns, data, message, chart, summary