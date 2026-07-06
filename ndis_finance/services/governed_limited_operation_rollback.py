import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, today

from ndis_finance.services.permissions import assert_action


ROLLBACK_ACK = "I_CONFIRM_PHASE12I_ROLLBACK_GOVERNED_LIMITED_OPERATION_SMOKE_PAYMENT_ENTRY"

POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
SMOKE_DOCTYPE = "NDIS Next Governed Limited Op Smoke"
SMOKE_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Smoke Item"
ROLLBACK_DOCTYPE = "NDIS Next Governed Limited Op Rollback"
ROLLBACK_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Rollback Item"

EXPECTED_PAYMENT_ENTRY = "ACC-PAY-2026-00012"
EXPECTED_INVOICES = ["ACC-SINV-2026-00005", "ACC-SINV-2026-00006", "ACC-SINV-2026-00008"]

EXPECTED_PAYMENT_ENTRY_COUNT_BEFORE = 11
EXPECTED_PAYMENT_ENTRY_COUNT_AFTER = 11
EXPECTED_PAYMENT_ENTRY_GL_COUNT_BEFORE = 66
EXPECTED_PAYMENT_ENTRY_GL_COUNT_AFTER = 70

EXPECTED_REFERENCE_COUNT = 3
EXPECTED_TOTAL_AMOUNT = 3.00
EXPECTED_VOUCHER_GL_ROWS_BEFORE = 4
EXPECTED_VOUCHER_GL_ROWS_AFTER = 8
EXPECTED_REVERSAL_GL_ROWS = 4


def make_rollback_id():
    timestamp = now_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-NEXT-GOVERNED-LIMITED-OP-ROLLBACK-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_smoke():
    rows = frappe.get_all(
        SMOKE_DOCTYPE,
        filters={
            "status": "Smoke Completed - Rollback Required",
            "smoke_status": "Governed Limited Operation Smoke Completed",
            "smoke_completed": 1,
            "phase12g_execution_gate_verified": 1,
            "execution_gate_approved_verified": 1,
            "smoke_only_authorised_verified": 1,
            "real_production_posting_blocked_verified": 1,
            "smoke_payment_entry": EXPECTED_PAYMENT_ENTRY,
            "smoke_payment_entry_created": 1,
            "smoke_payment_entry_submitted": 1,
            "smoke_payment_entry_docstatus": 1,
            "smoke_payment_entry_status": "Submitted",
            "smoke_invoice_count": EXPECTED_REFERENCE_COUNT,
            "smoke_total_amount": EXPECTED_TOTAL_AMOUNT,
            "smoke_reference_count": EXPECTED_REFERENCE_COUNT,
            "smoke_gl_row_count": EXPECTED_VOUCHER_GL_ROWS_BEFORE,
            "smoke_gl_net": 0,
            "rollback_required": 1,
            "ready_for_governed_limited_operation_rollback": 1,
            "payment_entry_count_before": 10,
            "payment_entry_count_after": EXPECTED_PAYMENT_ENTRY_COUNT_BEFORE,
            "payment_entry_gl_count_before": 62,
            "payment_entry_gl_count_after": EXPECTED_PAYMENT_ENTRY_GL_COUNT_BEFORE,
            "actual_payment_entry_created_count": 1,
            "actual_payment_entry_cancelled_count": 0,
            "actual_gl_created_count": EXPECTED_VOUCHER_GL_ROWS_BEFORE,
            "submitted_journal_entry_count_today": 0,
            "purchase_invoice_count_today": 0,
            "target_policy_enabled_after": 1,
            "target_policy_live_after": 0,
            "actual_policy_mutation_count": 0,
        },
        fields=[
            "name",
            "smoke_id",
            "smoke_payment_entry",
            "smoke_source_doctype",
            "smoke_reference_doctype",
            "smoke_party_type",
            "smoke_customer",
            "smoke_company",
            "smoke_currency",
            "smoke_invoice_names",
            "smoke_invoice_count",
            "smoke_total_amount",
            "smoke_reference_count",
            "smoke_gl_row_count",
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
            "target_policy_doctype",
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
            "status": "Rollback Completed",
            "rollback_completed": 1,
        },
        fields=["name", "rollback_id", "rolled_back_payment_entry"],
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
            "current_outstanding_amount",
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
                    "rollback_amount": flt(row.smoke_amount or 0, 2),
                    "current_outstanding_amount": flt((si.outstanding_amount if si else 0) or 0, 2),
                    "customer": si.customer if si else row.customer,
                    "company": si.company if si else row.company,
                    "currency": si.currency if si else row.currency,
                    "docstatus": int(si.docstatus or 0) if si else None,
                }
            )
        )

    return result


def reference_names(rows):
    return [row.reference_name for row in rows]


def rollback_total(rows):
    return flt(sum(flt(row.rollback_amount or 0, 2) for row in rows), 2)


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


def pe_reference_count(payment_entry):
    return count_dt("Payment Entry Reference", {"parent": payment_entry, "reference_doctype": "Sales Invoice"})


def pe_allocated_amount(payment_entry):
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


def validate_source(smoke, rows, guard, config, policy_enabled, policy_live):
    issues = []

    if not smoke:
        issues.append("No completed Phase 12H governed limited-operation smoke found.")
        return issues

    existing = existing_completed_rollback(smoke.name)
    if existing:
        issues.append(f"Completed Phase 12I rollback already exists for this smoke: {existing.rollback_id} / {existing.rolled_back_payment_entry}")

    pe_name = smoke.smoke_payment_entry

    if pe_name != EXPECTED_PAYMENT_ENTRY:
        issues.append(f"Expected smoke Payment Entry {EXPECTED_PAYMENT_ENTRY}. Found {pe_name}.")

    if not frappe.db.exists("Payment Entry", pe_name):
        issues.append(f"Smoke Payment Entry does not exist: {pe_name}")
        return issues

    pe = frappe.get_doc("Payment Entry", pe_name)

    if pe.docstatus != 1:
        issues.append(f"Smoke Payment Entry must be submitted before rollback. docstatus={pe.docstatus}")

    if pe.status != "Submitted":
        issues.append(f"Smoke Payment Entry status must be Submitted before rollback. status={pe.status}")

    if reference_names(rows) != EXPECTED_INVOICES:
        issues.append(f"Rollback invoice set changed. Expected {EXPECTED_INVOICES}. Found {reference_names(rows)}.")

    if len(rows) != EXPECTED_REFERENCE_COUNT:
        issues.append(f"Rollback reference count must be {EXPECTED_REFERENCE_COUNT}. Found {len(rows)}.")

    if rollback_total(rows) != EXPECTED_TOTAL_AMOUNT:
        issues.append(f"Rollback total amount must be {EXPECTED_TOTAL_AMOUNT}. Found {rollback_total(rows)}.")

    if pe_reference_count(pe_name) != EXPECTED_REFERENCE_COUNT:
        issues.append(f"Payment Entry reference count must be {EXPECTED_REFERENCE_COUNT}. Found {pe_reference_count(pe_name)}.")

    if pe_allocated_amount(pe_name) != EXPECTED_TOTAL_AMOUNT:
        issues.append(f"Payment Entry allocated amount must be {EXPECTED_TOTAL_AMOUNT}. Found {pe_allocated_amount(pe_name)}.")

    if voucher_gl_rows(pe_name) != EXPECTED_VOUCHER_GL_ROWS_BEFORE:
        issues.append(f"Voucher GL rows before rollback must be {EXPECTED_VOUCHER_GL_ROWS_BEFORE}. Found {voucher_gl_rows(pe_name)}.")

    if voucher_gl_net(pe_name) != 0:
        issues.append(f"Voucher GL net before rollback must be 0.00. Found {voucher_gl_net(pe_name)}.")

    if guard["payment_entry_count"] != EXPECTED_PAYMENT_ENTRY_COUNT_BEFORE:
        issues.append("Payment Entry count must be 11 before Phase 12I rollback.")

    if guard["payment_entry_gl_count"] != EXPECTED_PAYMENT_ENTRY_GL_COUNT_BEFORE:
        issues.append("Payment Entry GL count must be 66 before Phase 12I rollback.")

    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today must remain 0 before rollback.")

    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today must remain 0 before rollback.")

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


def cancel_smoke_payment_entry(payment_entry):
    pe = frappe.get_doc("Payment Entry", payment_entry)

    if pe.docstatus != 1:
        frappe.throw(_("Payment Entry must be submitted before rollback: {0}").format(payment_entry))

    pe.flags.ignore_permissions = True
    pe.cancel()

    return payment_entry


def build_items(rows, issues, ack_ok, payment_entry=None):
    items = []

    if not issues:
        items.append({
            "status": "Pass",
            "severity": "Critical",
            "category": "Rollback Source",
            "check_key": "rollback_source_valid",
            "check_label": "Rollback source valid",
            "detail": "The Phase 12H smoke Payment Entry can be rolled back.",
            "rollback_payment_entry": payment_entry,
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
                "rollback_payment_entry": payment_entry,
            })

    for row in rows:
        items.append({
            "status": "Pass",
            "severity": "High",
            "category": "Rollback Reference",
            "check_key": "rollback_sales_invoice_reference",
            "check_label": f"Rollback Sales Invoice {row.idx}",
            "detail": f"{row.reference_name} rollback amount={row.rollback_amount}, outstanding at check={row.current_outstanding_amount}.",
            "line_no": row.idx,
            "reference_doctype": row.reference_doctype,
            "reference_name": row.reference_name,
            "customer": row.customer,
            "company": row.company,
            "currency": row.currency,
            "rollback_amount": row.rollback_amount,
            "current_outstanding_amount": row.current_outstanding_amount,
            "rollback_payment_entry": payment_entry,
        })

    for key, label, value in [
        ("payment_entry_cancelled", "Payment Entry cancelled", payment_entry or "None"),
        ("voucher_gl_rows", "Voucher GL rows after rollback", EXPECTED_VOUCHER_GL_ROWS_AFTER),
        ("reversal_gl_rows", "Reversal GL rows", EXPECTED_REVERSAL_GL_ROWS),
        ("voucher_gl_net", "Voucher GL net", 0),
        ("restored_invoice_amount", "Restored invoice amount", EXPECTED_TOTAL_AMOUNT),
        ("rollback_freeze_ready", "Rollback freeze ready", 1),
    ]:
        items.append({
            "status": "Pass",
            "severity": "High",
            "category": "Rollback Evidence",
            "check_key": key,
            "check_label": label,
            "detail": f"value={value}",
            "rollback_payment_entry": payment_entry,
        })

    items.append({
        "status": "Pass" if ack_ok else "Warning",
        "severity": "Low" if ack_ok else "Medium",
        "category": "Acknowledgement",
        "check_key": "ack_ok",
        "check_label": "Acknowledgement supplied",
        "detail": "Exact acknowledgement supplied." if ack_ok else f"Required acknowledgement not supplied: {ROLLBACK_ACK}",
        "rollback_payment_entry": payment_entry,
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
def run_governed_limited_operation_rollback(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_governed_limited_operation_rollback")

    smoke = latest_smoke()
    rows = smoke_rows(smoke.name) if smoke else []
    payment_entry = smoke.smoke_payment_entry if smoke else None

    guard_before = guardrails()
    ack_ok = acknowledgement == ROLLBACK_ACK

    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }

    policy_enabled_before = get_flag(POLICY_DOCTYPE, smoke.target_policy, "production_batch_enabled") if smoke else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, smoke.target_policy, "live_posting_allowed") if smoke else 0

    source_issues = validate_source(smoke, rows, guard_before, config, policy_enabled_before, policy_live_before)

    pe_docstatus_before = 0
    pe_status_before = None
    voucher_rows_before = 0
    voucher_net_before = 0

    if payment_entry and frappe.db.exists("Payment Entry", payment_entry):
        pe = frappe.get_doc("Payment Entry", payment_entry)
        pe_docstatus_before = int(pe.docstatus or 0)
        pe_status_before = pe.status
        voucher_rows_before = voucher_gl_rows(payment_entry)
        voucher_net_before = voucher_gl_net(payment_entry)

    movement_attempted = 0

    if not int(dry_run or 0) and ack_ok and not source_issues:
        movement_attempted = 1
        cancel_smoke_payment_entry(payment_entry)

    guard_after = guardrails()

    policy_enabled_after = get_flag(POLICY_DOCTYPE, smoke.target_policy, "production_batch_enabled") if smoke else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, smoke.target_policy, "live_posting_allowed") if smoke else 0

    pe_docstatus_after = 0
    pe_status_after = None
    voucher_rows_after = 0
    voucher_net_after = 0
    restored_invoice_amount = outstanding_total(EXPECTED_INVOICES)

    if payment_entry and frappe.db.exists("Payment Entry", payment_entry):
        pe_after = frappe.get_doc("Payment Entry", payment_entry)
        pe_docstatus_after = int(pe_after.docstatus or 0)
        pe_status_after = pe_after.status
        voucher_rows_after = voucher_gl_rows(payment_entry)
        voucher_net_after = voucher_gl_net(payment_entry)

    actual_pe_created = guard_after["payment_entry_count"] - guard_before["payment_entry_count"]
    actual_pe_cancelled = int(movement_attempted and pe_docstatus_before == 1 and pe_docstatus_after == 2)
    actual_gl_created = guard_after["payment_entry_gl_count"] - guard_before["payment_entry_gl_count"]
    reversal_gl_rows = voucher_rows_after - voucher_rows_before

    policy_mutation_count = int(
        policy_enabled_before != policy_enabled_after
        or policy_live_before != policy_live_after
        or guard_before["production_batch_enabled_policy_count"] != guard_after["production_batch_enabled_policy_count"]
        or guard_before["live_posting_allowed_policy_count"] != guard_after["live_posting_allowed_policy_count"]
    )

    post_issues = list(source_issues)

    if movement_attempted:
        if pe_docstatus_after != 2:
            post_issues.append(f"Payment Entry must be cancelled after rollback. docstatus={pe_docstatus_after}.")
        if pe_status_after != "Cancelled":
            post_issues.append(f"Payment Entry status must be Cancelled after rollback. status={pe_status_after}.")
        if actual_pe_created != 0:
            post_issues.append(f"Rollback must create 0 Payment Entries. Created {actual_pe_created}.")
        if actual_pe_cancelled != 1:
            post_issues.append(f"Rollback must cancel exactly 1 Payment Entry. Cancelled {actual_pe_cancelled}.")
        if actual_gl_created != EXPECTED_REVERSAL_GL_ROWS:
            post_issues.append(f"Rollback must create {EXPECTED_REVERSAL_GL_ROWS} GL reversal rows. Created {actual_gl_created}.")
        if voucher_rows_after != EXPECTED_VOUCHER_GL_ROWS_AFTER:
            post_issues.append(f"Voucher GL rows after rollback must be {EXPECTED_VOUCHER_GL_ROWS_AFTER}. Found {voucher_rows_after}.")
        if reversal_gl_rows != EXPECTED_REVERSAL_GL_ROWS:
            post_issues.append(f"Reversal GL rows must be {EXPECTED_REVERSAL_GL_ROWS}. Found {reversal_gl_rows}.")
        if voucher_gl_net(payment_entry) != 0:
            post_issues.append(f"Voucher GL net must be 0.00 after rollback. Found {voucher_gl_net(payment_entry)}.")
        if restored_invoice_amount != EXPECTED_TOTAL_AMOUNT:
            post_issues.append(f"Restored invoice amount must be {EXPECTED_TOTAL_AMOUNT}. Found {restored_invoice_amount}.")

    if movement_attempted and guard_after["payment_entry_count"] != EXPECTED_PAYMENT_ENTRY_COUNT_AFTER:
        post_issues.append("Payment Entry count must remain 11 after rollback.")

    if movement_attempted and guard_after["payment_entry_gl_count"] != EXPECTED_PAYMENT_ENTRY_GL_COUNT_AFTER:
        post_issues.append("Payment Entry GL count must be 70 after rollback.")

    if guard_after["submitted_journal_entry_count_today"] != 0:
        post_issues.append("Submitted Journal Entry count today must remain 0 after rollback.")

    if guard_after["purchase_invoice_count_today"] != 0:
        post_issues.append("Purchase Invoice count today must remain 0 after rollback.")

    if policy_mutation_count != 0:
        post_issues.append("Policy state changed during rollback. This is not allowed.")

    completed = int(
        movement_attempted
        and payment_entry
        and not post_issues
        and pe_docstatus_before == 1
        and pe_docstatus_after == 2
        and pe_status_before == "Submitted"
        and pe_status_after == "Cancelled"
        and actual_pe_created == 0
        and actual_pe_cancelled == 1
        and actual_gl_created == EXPECTED_REVERSAL_GL_ROWS
        and guard_before["payment_entry_count"] == EXPECTED_PAYMENT_ENTRY_COUNT_BEFORE
        and guard_after["payment_entry_count"] == EXPECTED_PAYMENT_ENTRY_COUNT_AFTER
        and guard_before["payment_entry_gl_count"] == EXPECTED_PAYMENT_ENTRY_GL_COUNT_BEFORE
        and guard_after["payment_entry_gl_count"] == EXPECTED_PAYMENT_ENTRY_GL_COUNT_AFTER
        and voucher_rows_before == EXPECTED_VOUCHER_GL_ROWS_BEFORE
        and voucher_rows_after == EXPECTED_VOUCHER_GL_ROWS_AFTER
        and reversal_gl_rows == EXPECTED_REVERSAL_GL_ROWS
        and voucher_net_after == 0
        and restored_invoice_amount == EXPECTED_TOTAL_AMOUNT
        and guard_after["submitted_journal_entry_count_today"] == 0
        and guard_after["purchase_invoice_count_today"] == 0
        and policy_mutation_count == 0
    )

    items = build_items(rows, post_issues, ack_ok, payment_entry=payment_entry)
    item_summary = summarise_items(items)

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Rollback Completed" if completed else "Needs Review",
        "rollback_status": "Governed Limited Operation Smoke Rolled Back" if completed else "Needs Review",
        "rollback_completed": completed,

        "phase12h_smoke_verified": 1 if smoke else 0,
        "smoke_completed_verified": 1 if smoke else 0,
        "smoke_payment_entry_verified": int(bool(payment_entry)),
        "smoke_payment_entry_cancelled": int(pe_docstatus_after == 2 and pe_status_after == "Cancelled"),
        "smoke_payment_entry_docstatus_before": pe_docstatus_before,
        "smoke_payment_entry_docstatus_after": pe_docstatus_after,
        "smoke_payment_entry_status_before": pe_status_before,
        "smoke_payment_entry_status_after": pe_status_after,

        "rolled_back_payment_entry": payment_entry,
        "rollback_source_doctype": smoke.smoke_source_doctype if smoke else "Sales Invoice",
        "rollback_reference_doctype": smoke.smoke_reference_doctype if smoke else "Sales Invoice",
        "rollback_party_type": smoke.smoke_party_type if smoke else "Customer",
        "rollback_invoice_names": ", ".join(reference_names(rows)),
        "rollback_invoice_count": len(rows),
        "rollback_total_amount": rollback_total(rows),

        "voucher_gl_rows_before": voucher_rows_before,
        "voucher_gl_rows_after": voucher_rows_after,
        "reversal_gl_rows": reversal_gl_rows,
        "voucher_gl_net": voucher_net_after,
        "restored_invoice_amount": restored_invoice_amount,

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
        "production_batch_enabled_policy_count_before": guard_before["production_batch_enabled_policy_count"],
        "production_batch_enabled_policy_count_after": guard_after["production_batch_enabled_policy_count"],
        "live_posting_allowed_policy_count_before": guard_before["live_posting_allowed_policy_count"],
        "live_posting_allowed_policy_count_after": guard_after["live_posting_allowed_policy_count"],
        "actual_policy_mutation_count": policy_mutation_count,

        "policy_state_preserved_verified": int(policy_mutation_count == 0 and policy_enabled_before == 1 and policy_enabled_after == 1 and policy_live_before == 0 and policy_live_after == 0),
        "journal_entry_side_effect_not_allowed_verified": int(guard_after["submitted_journal_entry_count_today"] == 0),
        "purchase_invoice_side_effect_not_allowed_verified": int(guard_after["purchase_invoice_count_today"] == 0),
        "ready_for_governed_limited_operation_rollback_freeze": completed,

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
        "note": "Phase 12I rolls back the governed limited-operation smoke Payment Entry. Freeze rollback evidence next.",
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
        "rolled_back_payment_entry": payment_entry,
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_governed_limited_operation_rollback_audit(rollback, reason=None):
    assert_action("cancel_governed_limited_operation_rollback_audit")

    if not frappe.db.exists(ROLLBACK_DOCTYPE, rollback):
        frappe.throw(_("Governed limited-operation rollback audit not found: {0}").format(rollback))

    doc = frappe.get_doc(ROLLBACK_DOCTYPE, rollback)

    if doc.status == "Cancelled":
        return {"rollback": rollback, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.rollback_completed or 0):
        frappe.throw(_("Cannot cancel a completed Phase 12I rollback record."))

    frappe.db.set_value(
        ROLLBACK_DOCTYPE,
        rollback,
        {
            "status": "Cancelled",
            "rollback_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 12I no-ack rollback audit cancelled.",
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
def quick_governed_limited_operation_rollback_summary(limit=20):
    return {
        "rollback_records": frappe.get_all(
            ROLLBACK_DOCTYPE,
            fields=[
                "name",
                "rollback_id",
                "status",
                "rollback_status",
                "rollback_completed",
                "rolled_back_payment_entry",
                "smoke_payment_entry_docstatus_before",
                "smoke_payment_entry_docstatus_after",
                "smoke_payment_entry_status_before",
                "smoke_payment_entry_status_after",
                "rollback_invoice_names",
                "rollback_invoice_count",
                "rollback_total_amount",
                "voucher_gl_rows_before",
                "voucher_gl_rows_after",
                "reversal_gl_rows",
                "voucher_gl_net",
                "restored_invoice_amount",
                "ready_for_governed_limited_operation_rollback_freeze",
                "payment_entry_count_before",
                "payment_entry_count_after",
                "payment_entry_gl_count_before",
                "payment_entry_gl_count_after",
                "actual_payment_entry_created_count",
                "actual_payment_entry_cancelled_count",
                "actual_gl_created_count",
                "submitted_journal_entry_count_today",
                "purchase_invoice_count_today",
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
                "current_outstanding_amount",
                "rollback_payment_entry",
                "detail",
            ],
            order_by="creation desc",
            limit=int(limit or 20),
        ),
        "required_acknowledgement": ROLLBACK_ACK,
        "guardrails": guardrails(),
        "note": "Phase 12I governed limited-operation rollback summary.",
    }


def execute_rollback_report(filters=None):
    columns = [
        {"fieldname": "rollback", "label": _("Rollback"), "fieldtype": "Link", "options": ROLLBACK_DOCTYPE, "width": 220},
        {"fieldname": "rollback_id", "label": _("Rollback ID"), "fieldtype": "Data", "width": 450},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 170},
        {"fieldname": "rollback_status", "label": _("Rollback Status"), "fieldtype": "Data", "width": 330},
        {"fieldname": "rollback_completed", "label": _("Completed"), "fieldtype": "Check", "width": 90},
        {"fieldname": "rolled_back_payment_entry", "label": _("Rolled Back PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "rollback_invoice_names", "label": _("Invoices"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "rollback_invoice_count", "label": _("Invoice Count"), "fieldtype": "Int", "width": 100},
        {"fieldname": "rollback_total_amount", "label": _("Amount"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "voucher_gl_rows_before", "label": _("Voucher GL Before"), "fieldtype": "Int", "width": 125},
        {"fieldname": "voucher_gl_rows_after", "label": _("Voucher GL After"), "fieldtype": "Int", "width": 120},
        {"fieldname": "reversal_gl_rows", "label": _("Reversal GL"), "fieldtype": "Int", "width": 100},
        {"fieldname": "voucher_gl_net", "label": _("Voucher GL Net"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "restored_invoice_amount", "label": _("Restored Amount"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "ready_for_governed_limited_operation_rollback_freeze", "label": _("Freeze Ready"), "fieldtype": "Check", "width": 110},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 115},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 115},
        {"fieldname": "actual_payment_entry_cancelled_count", "label": _("Actual PE Cancelled"), "fieldtype": "Int", "width": 140},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL Created"), "fieldtype": "Int", "width": 130},
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
            rolled_back_payment_entry,
            rollback_invoice_names,
            rollback_invoice_count,
            rollback_total_amount,
            voucher_gl_rows_before,
            voucher_gl_rows_after,
            reversal_gl_rows,
            voucher_gl_net,
            restored_invoice_amount,
            ready_for_governed_limited_operation_rollback_freeze,
            payment_entry_count_before,
            payment_entry_count_after,
            payment_entry_gl_count_before,
            payment_entry_gl_count_after,
            actual_payment_entry_cancelled_count,
            actual_gl_created_count,
            checked_on
        FROM `tab{ROLLBACK_DOCTYPE}`
        ORDER BY creation DESC
        """,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.rollback_id for row in data[:20]],
            "datasets": [
                {"name": "Completed", "values": [int(row.rollback_completed or 0) for row in data[:20]]},
                {"name": "Freeze Ready", "values": [int(row.ready_for_governed_limited_operation_rollback_freeze or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Rollback Records"), "datatype": "Int"},
        {"value": sum(int(row.rollback_completed or 0) for row in data), "indicator": "Green", "label": _("Completed"), "datatype": "Int"},
        {"value": sum(int(row.actual_payment_entry_cancelled_count or 0) for row in data), "indicator": "Orange", "label": _("Actual PE Cancelled"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Orange", "label": _("Actual GL Created"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_item_report(filters=None):
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": ROLLBACK_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "rollback", "label": _("Rollback"), "fieldtype": "Link", "options": ROLLBACK_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 180},
        {"fieldname": "line_no", "label": _("Line"), "fieldtype": "Int", "width": 60},
        {"fieldname": "reference_doctype", "label": _("Ref DocType"), "fieldtype": "Data", "width": 130},
        {"fieldname": "reference_name", "label": _("Reference"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 180},
        {"fieldname": "rollback_amount", "label": _("Rollback Amount"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "current_outstanding_amount", "label": _("Outstanding"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "rollback_payment_entry", "label": _("Rollback PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 300},
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
            current_outstanding_amount,
            rollback_payment_entry,
            check_label,
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
