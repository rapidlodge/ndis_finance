import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, today

from ndis_finance.services.permissions import assert_action


MONITOR_ACK = "I_CONFIRM_PHASE14I_ACTIVATE_NEXT_GOVERNED_LIMITED_OPERATION_RUNTIME_MONITOR_NO_POSTING"

POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
BASELINE_DOCTYPE = "NDIS Next Governed Limited Op Steady Baseline"
BASELINE_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Steady Baseline Item"
MONITOR_DOCTYPE = "NDIS Next Governed Limited Op Runtime Monitor"
MONITOR_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Runtime Monitor Item"

BASELINE_READY_FIELD = "ready_for_next_governed_limited_op_runtime_monitor"
MONITOR_READY_FIELD = "ready_for_next_governed_limited_op_planning"

GATED_PAYMENT_ENTRY = "ACC-PAY-2026-00015"
PREVIOUS_GATED_PAYMENT_ENTRY = "ACC-PAY-2026-00014"
MONITOR_PAYMENT_ENTRY = "ACC-PAY-2026-00016"
EXPECTED_INVOICES = ["ACC-SINV-2026-00005", "ACC-SINV-2026-00006", "ACC-SINV-2026-00008"]
EXPECTED_PAYMENT_ENTRY_COUNT = 15
EXPECTED_PAYMENT_ENTRY_GL_COUNT = 102
EXPECTED_TOTAL_AMOUNT = 3.00
EXPECTED_RESTORED_INVOICE_AMOUNT = 3.00
EXPECTED_INVOICE_COUNT = 3
EXPECTED_MONITOR_GL_ROWS = 8
EXPECTED_MONITOR_REVERSAL_GL_ROWS = 4
EXPECTED_MONITOR_GL_NET = 0.00

MONITOR_SOURCE_DOCTYPE = "Sales Invoice"
MONITOR_REFERENCE_DOCTYPE = "Sales Invoice"
MONITOR_PARTY_TYPE = "Customer"
BASELINE_REFERENCE_CATEGORY = "Steady Baseline Reference"


def make_monitor_id():
    timestamp = now_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-NEXT-GOVERNED-LIMITED-OP-RUNTIME-MONITOR-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def direct_cancelled_gl_rows(payment_entry):
    if not has_column("GL Entry", "is_cancelled"):
        return 0
    return count_dt("GL Entry", {"voucher_type": "Payment Entry", "voucher_no": payment_entry, "is_cancelled": 1})


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


def latest_baseline():
    filters = {
        "status": "Baseline Active",
        "baseline_status": "Next Governed Limited Operation Steady Baseline Active",
        "baseline_active": 1,
        "phase14g_closeout_verified": 1,
        "closeout_completed_verified": 1,
        "closeout_payment_entry_verified": 1,
        "closeout_payment_entry_cancelled_verified": 1,
        "closeout_gl_rows_verified": 1,
        "closeout_reversal_gl_rows_verified": 1,
        "closeout_gl_net_zero_verified": 1,
        "closeout_restored_invoice_amount_verified": 1,
        "policy_state_preserved_verified": 1,
        "no_new_accounting_movement_verified": 1,
        "gated_payment_entry": GATED_PAYMENT_ENTRY,
        "gated_payment_entry_docstatus": 2,
        "gated_payment_entry_status": "Cancelled",
        "previous_gated_payment_entry": PREVIOUS_GATED_PAYMENT_ENTRY,
        "previous_gated_payment_entry_docstatus": 2,
        "previous_gated_payment_entry_status": "Cancelled",
        "baseline_payment_entry": MONITOR_PAYMENT_ENTRY,
        "baseline_payment_entry_docstatus": 2,
        "baseline_payment_entry_status": "Cancelled",
        "baseline_source_doctype": MONITOR_SOURCE_DOCTYPE,
        "baseline_reference_doctype": MONITOR_REFERENCE_DOCTYPE,
        "baseline_party_type": MONITOR_PARTY_TYPE,
        "baseline_invoice_count": EXPECTED_INVOICE_COUNT,
        "baseline_total_amount": EXPECTED_TOTAL_AMOUNT,
        "baseline_restored_invoice_amount": EXPECTED_RESTORED_INVOICE_AMOUNT,
        "baseline_gl_rows": EXPECTED_MONITOR_GL_ROWS,
        "baseline_reversal_gl_rows": EXPECTED_MONITOR_REVERSAL_GL_ROWS,
        "baseline_gl_net": EXPECTED_MONITOR_GL_NET,
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
        "blocker_count": 0,
        "warning_count": 0,
    }
    if has_column(BASELINE_DOCTYPE, BASELINE_READY_FIELD):
        filters[BASELINE_READY_FIELD] = 1

    rows = frappe.get_all(
        BASELINE_DOCTYPE,
        filters=filters,
        fields=[
            "name",
            "baseline_id",
            "gated_payment_entry",
            "gated_payment_entry_docstatus",
            "gated_payment_entry_status",
            "previous_gated_payment_entry",
            "previous_gated_payment_entry_docstatus",
            "previous_gated_payment_entry_status",
            "baseline_payment_entry",
            "baseline_payment_entry_docstatus",
            "baseline_payment_entry_status",
            "baseline_source_doctype",
            "baseline_reference_doctype",
            "baseline_party_type",
            "baseline_customer",
            "baseline_company",
            "baseline_currency",
            "baseline_invoice_names",
            "baseline_invoice_count",
            "baseline_total_amount",
            "baseline_restored_invoice_amount",
            "baseline_gl_rows",
            "baseline_reversal_gl_rows",
            "baseline_gl_net",
            "baseline_direct_cancelled_gl_rows",
            "direct_erpnext_cancelled_gl_rows",
            "closeout",
            "freeze",
            "rollback",
            "smoke",
            "execution_gate",
            "preview",
            "candidate_validation",
            "candidate_selection",
            "design",
            "planning",
            "monitor",
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
        filters={"baseline": baseline, "status": "Runtime Monitor Active", "monitor_active": 1},
        fields=["name", "monitor_id", "monitor_payment_entry"],
        limit=1,
    )
    return rows[0] if rows else None


def baseline_rows(baseline):
    rows = frappe.get_all(
        BASELINE_ITEM_DOCTYPE,
        filters={"baseline": baseline, "category": BASELINE_REFERENCE_CATEGORY, "status": "Pass", "reference_doctype": "Sales Invoice"},
        fields=[
            "line_no",
            "reference_doctype",
            "reference_name",
            "customer",
            "company",
            "currency",
            "baseline_amount",
            "outstanding_amount",
            "gated_payment_entry",
            "baseline_payment_entry",
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
                    "monitor_amount": flt(row.baseline_amount or 0, 2),
                    "outstanding_amount": flt((si.outstanding_amount if si else row.outstanding_amount) or 0, 2),
                    "customer": si.customer if si else row.customer,
                    "company": si.company if si else row.company,
                    "currency": si.currency if si else row.currency,
                    "invoice_docstatus": int(si.docstatus or 0) if si else 0,
                    "gated_payment_entry": GATED_PAYMENT_ENTRY,
                    "monitor_payment_entry": MONITOR_PAYMENT_ENTRY,
                }
            )
        )
    return result


def reference_names(rows):
    return [row.reference_name for row in rows]


def monitor_total(rows):
    return flt(sum(flt(row.monitor_amount or 0, 2) for row in rows), 2)


def unique_value(rows, fieldname):
    values = sorted(set(getattr(row, fieldname, None) for row in rows if getattr(row, fieldname, None)))
    return values[0] if len(values) == 1 else None


def validate_source(baseline, rows, guard, config, policy_enabled, policy_live):
    issues = []
    if not baseline:
        issues.append("No active Phase 14H steady baseline found for runtime monitor.")
        return issues

    existing = existing_active_monitor(baseline.name)
    if existing:
        issues.append(f"Active Phase 14I runtime monitor already exists for this baseline: {existing.monitor_id} / {existing.monitor_payment_entry}")

    state = payment_entry_state(MONITOR_PAYMENT_ENTRY)
    gated_state = payment_entry_state(GATED_PAYMENT_ENTRY)
    previous_gated_state = payment_entry_state(PREVIOUS_GATED_PAYMENT_ENTRY)
    if not frappe.db.exists("Payment Entry", GATED_PAYMENT_ENTRY):
        issues.append(f"Gated Payment Entry does not exist: {GATED_PAYMENT_ENTRY}")
    if gated_state.docstatus != 2 or gated_state.status != "Cancelled":
        issues.append(f"Gated Payment Entry must remain Cancelled / 2. Found {gated_state.status} / {gated_state.docstatus}")
    if not frappe.db.exists("Payment Entry", PREVIOUS_GATED_PAYMENT_ENTRY):
        issues.append(f"Previous gated Payment Entry does not exist: {PREVIOUS_GATED_PAYMENT_ENTRY}")
    if previous_gated_state.docstatus != 2 or previous_gated_state.status != "Cancelled":
        issues.append(f"Previous gated Payment Entry must remain Cancelled / 2. Found {previous_gated_state.status} / {previous_gated_state.docstatus}")
    if not frappe.db.exists("Payment Entry", MONITOR_PAYMENT_ENTRY):
        issues.append(f"Monitor Payment Entry does not exist: {MONITOR_PAYMENT_ENTRY}")
    if state.docstatus != 2 or state.status != "Cancelled":
        issues.append(f"Monitor Payment Entry must remain Cancelled / 2. Found {state.status} / {state.docstatus}")
    if reference_names(rows) != EXPECTED_INVOICES:
        issues.append(f"Monitor invoice set changed. Expected {EXPECTED_INVOICES}. Found {reference_names(rows)}.")
    if len(rows) != EXPECTED_INVOICE_COUNT:
        issues.append(f"Monitor invoice count must be {EXPECTED_INVOICE_COUNT}. Found {len(rows)}.")
    if monitor_total(rows) != EXPECTED_TOTAL_AMOUNT:
        issues.append(f"Monitor total amount must be {EXPECTED_TOTAL_AMOUNT}. Found {monitor_total(rows)}.")
    if outstanding_total(EXPECTED_INVOICES) != EXPECTED_RESTORED_INVOICE_AMOUNT:
        issues.append(f"Restored invoice outstanding must be {EXPECTED_RESTORED_INVOICE_AMOUNT} before runtime monitor.")
    if payment_entry_gl_rows(MONITOR_PAYMENT_ENTRY) != EXPECTED_MONITOR_GL_ROWS:
        issues.append(f"Monitor Payment Entry must have {EXPECTED_MONITOR_GL_ROWS} GL rows.")
    if payment_entry_gl_net(MONITOR_PAYMENT_ENTRY) != EXPECTED_MONITOR_GL_NET:
        issues.append("Monitor Payment Entry GL net must be 0.00.")
    if int(baseline.baseline_reversal_gl_rows or 0) != EXPECTED_MONITOR_REVERSAL_GL_ROWS:
        issues.append("Governed baseline reversal rows must remain the four-row delta.")
    if guard["payment_entry_count"] != EXPECTED_PAYMENT_ENTRY_COUNT:
        issues.append("Payment Entry count must remain 15 before runtime monitor.")
    if guard["payment_entry_gl_count"] != EXPECTED_PAYMENT_ENTRY_GL_COUNT:
        issues.append("Payment Entry GL count must remain 102 before runtime monitor.")
    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today must remain 0 before runtime monitor.")
    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today must remain 0 before runtime monitor.")
    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must remain enabled before runtime monitor.")
    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must remain 0 before runtime monitor.")
    if policy_enabled != 1:
        issues.append("Target policy production_batch_enabled must remain 1.")
    if policy_live != 0:
        issues.append("Target policy live_posting_allowed must remain 0.")
    if config["sandbox_enabled"] != 1:
        issues.append("Sandbox config must be enabled for runtime monitor.")
    if config["production_mode"] != 0:
        issues.append("Production mode config must remain 0 for runtime monitor.")
    if config["live_pe_enabled"] != 0:
        issues.append("Live Payment Entry posting config must remain 0 for runtime monitor.")
    return issues


def build_items(rows, issues, ack_ok):
    items = []
    if not issues:
        items.append(
            {
                "status": "Pass",
                "severity": "Critical",
                "category": "Monitor Source",
                "check_key": "monitor_source_valid",
                "check_label": "Monitor source valid",
                "detail": f"Steady baseline evidence for {MONITOR_PAYMENT_ENTRY} is stable and ready for runtime monitoring.",
                "gated_payment_entry": GATED_PAYMENT_ENTRY,
                "monitor_payment_entry": MONITOR_PAYMENT_ENTRY,
            }
        )
    else:
        for issue in issues:
            items.append(
                {
                    "status": "Blocker",
                    "severity": "Critical",
                    "category": "Monitor Source",
                    "check_key": "monitor_source_valid",
                    "check_label": "Monitor source valid",
                    "detail": issue,
                    "gated_payment_entry": GATED_PAYMENT_ENTRY,
                    "monitor_payment_entry": MONITOR_PAYMENT_ENTRY,
                }
            )

    for row in rows:
        items.append(
            {
                "status": "Pass",
                "severity": "High",
                "category": "Runtime Monitor Reference",
                "check_key": "monitor_sales_invoice_reference",
                "check_label": f"Monitor Sales Invoice {row.idx}",
                "detail": f"{row.reference_name} monitor amount={row.monitor_amount}, outstanding={row.outstanding_amount}.",
                "line_no": row.idx,
                "reference_doctype": row.reference_doctype,
                "reference_name": row.reference_name,
                "customer": row.customer,
                "company": row.company,
                "currency": row.currency,
                "monitor_amount": row.monitor_amount,
                "outstanding_amount": row.outstanding_amount,
                "gated_payment_entry": GATED_PAYMENT_ENTRY,
                "monitor_payment_entry": MONITOR_PAYMENT_ENTRY,
            }
        )

    for key, label, value in [
        ("baseline_verified", "Phase 14H baseline verified", 1),
        ("gated_payment_entry", "Gated Payment Entry", GATED_PAYMENT_ENTRY),
        ("previous_gated_payment_entry", "Previous gated Payment Entry", PREVIOUS_GATED_PAYMENT_ENTRY),
        ("monitor_payment_entry", "Monitor Payment Entry", MONITOR_PAYMENT_ENTRY),
        ("monitor_gl_rows", "Monitor GL rows", EXPECTED_MONITOR_GL_ROWS),
        ("monitor_reversal_gl_rows", "Governed reversal GL rows", EXPECTED_MONITOR_REVERSAL_GL_ROWS),
        ("planning_ready", "Ready for next governed limited-operation planning", 1),
    ]:
        items.append(
            {
                "status": "Pass",
                "severity": "High",
                "category": "Monitor Evidence",
                "check_key": key,
                "check_label": label,
                "detail": f"value={value}",
                "gated_payment_entry": GATED_PAYMENT_ENTRY,
                "monitor_payment_entry": MONITOR_PAYMENT_ENTRY,
            }
        )

    items.append(
        {
            "status": "Pass" if ack_ok else "Warning",
            "severity": "Low" if ack_ok else "Medium",
            "category": "Acknowledgement",
            "check_key": "ack_ok",
            "check_label": "Acknowledgement supplied",
            "detail": "Exact acknowledgement supplied." if ack_ok else f"Required acknowledgement not supplied: {MONITOR_ACK}",
            "gated_payment_entry": GATED_PAYMENT_ENTRY,
            "monitor_payment_entry": MONITOR_PAYMENT_ENTRY,
        }
    )
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
        row = frappe.new_doc(MONITOR_ITEM_DOCTYPE)
        row.monitor = doc.name
        for fieldname, value in item.items():
            if row.meta.has_field(fieldname):
                setattr(row, fieldname, value)
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_next_governed_limited_operation_runtime_monitor_phase14i(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_next_governed_limited_operation_runtime_monitor_phase14i")

    baseline = latest_baseline()
    rows = baseline_rows(baseline.name) if baseline else []
    guard_before = guardrails()
    ack_ok = acknowledgement == MONITOR_ACK
    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }

    policy_enabled_before = get_flag(POLICY_DOCTYPE, baseline.target_policy, "production_batch_enabled") if baseline else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, baseline.target_policy, "live_posting_allowed") if baseline else 0
    source_issues = validate_source(baseline, rows, guard_before, config, policy_enabled_before, policy_live_before)

    guard_after = guardrails()
    policy_enabled_after = get_flag(POLICY_DOCTYPE, baseline.target_policy, "production_batch_enabled") if baseline else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, baseline.target_policy, "live_posting_allowed") if baseline else 0

    state = payment_entry_state(MONITOR_PAYMENT_ENTRY)
    gated_state = payment_entry_state(GATED_PAYMENT_ENTRY)
    previous_gated_state = payment_entry_state(PREVIOUS_GATED_PAYMENT_ENTRY)
    monitor_gl_rows = payment_entry_gl_rows(MONITOR_PAYMENT_ENTRY)
    monitor_gl_net = payment_entry_gl_net(MONITOR_PAYMENT_ENTRY)
    restored_amount = outstanding_total(EXPECTED_INVOICES)
    direct_cancelled_rows = direct_cancelled_gl_rows(MONITOR_PAYMENT_ENTRY)

    actual_pe_created = guard_after["payment_entry_count"] - guard_before["payment_entry_count"]
    actual_pe_cancelled = 0
    actual_gl_created = guard_after["payment_entry_gl_count"] - guard_before["payment_entry_gl_count"]
    policy_mutation_count = int(
        policy_enabled_before != policy_enabled_after
        or policy_live_before != policy_live_after
        or guard_before["production_batch_enabled_policy_count"] != guard_after["production_batch_enabled_policy_count"]
        or guard_before["live_posting_allowed_policy_count"] != guard_after["live_posting_allowed_policy_count"]
    )

    post_issues = list(source_issues)
    if actual_pe_created != 0:
        post_issues.append(f"Runtime monitor must create 0 Payment Entries. Created {actual_pe_created}.")
    if actual_pe_cancelled != 0:
        post_issues.append(f"Runtime monitor must cancel 0 Payment Entries. Cancelled {actual_pe_cancelled}.")
    if actual_gl_created != 0:
        post_issues.append(f"Runtime monitor must create 0 GL rows. Created {actual_gl_created}.")
    if guard_after["submitted_journal_entry_count_today"] != 0:
        post_issues.append("Submitted Journal Entry today must remain 0 after runtime monitor.")
    if guard_after["purchase_invoice_count_today"] != 0:
        post_issues.append("Purchase Invoice today must remain 0 after runtime monitor.")
    if policy_mutation_count != 0:
        post_issues.append("Policy state changed during runtime monitor. This is not allowed.")

    completed = int(
        not int(dry_run or 0)
        and ack_ok
        and baseline
        and not post_issues
        and state.docstatus == 2
        and state.status == "Cancelled"
        and gated_state.docstatus == 2
        and gated_state.status == "Cancelled"
        and previous_gated_state.docstatus == 2
        and previous_gated_state.status == "Cancelled"
        and reference_names(rows) == EXPECTED_INVOICES
        and monitor_total(rows) == EXPECTED_TOTAL_AMOUNT
        and monitor_gl_rows == EXPECTED_MONITOR_GL_ROWS
        and monitor_gl_net == EXPECTED_MONITOR_GL_NET
        and restored_amount == EXPECTED_RESTORED_INVOICE_AMOUNT
        and guard_before["payment_entry_count"] == EXPECTED_PAYMENT_ENTRY_COUNT
        and guard_after["payment_entry_count"] == EXPECTED_PAYMENT_ENTRY_COUNT
        and guard_before["payment_entry_gl_count"] == EXPECTED_PAYMENT_ENTRY_GL_COUNT
        and guard_after["payment_entry_gl_count"] == EXPECTED_PAYMENT_ENTRY_GL_COUNT
        and actual_pe_created == 0
        and actual_pe_cancelled == 0
        and actual_gl_created == 0
        and policy_mutation_count == 0
    )

    items = build_items(rows, post_issues, ack_ok)
    item_summary = summarise_items(items)
    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Runtime Monitor Active" if completed else "Needs Review",
        "monitor_status": "Next Governed Limited Operation Runtime Monitor Active" if completed else "Needs Review",
        "monitor_active": completed,
        "phase14h_baseline_verified": 1 if baseline else 0,
        "baseline_active_verified": int(bool(baseline)),
        "baseline_payment_entry_verified": int(baseline and baseline.baseline_payment_entry == MONITOR_PAYMENT_ENTRY),
        "baseline_payment_entry_cancelled_verified": int(state.docstatus == 2 and state.status == "Cancelled"),
        "baseline_gl_rows_verified": int(monitor_gl_rows == EXPECTED_MONITOR_GL_ROWS),
        "baseline_reversal_gl_rows_verified": int(baseline and int(baseline.baseline_reversal_gl_rows or 0) == EXPECTED_MONITOR_REVERSAL_GL_ROWS),
        "baseline_gl_net_zero_verified": int(monitor_gl_net == EXPECTED_MONITOR_GL_NET),
        "baseline_restored_invoice_amount_verified": int(restored_amount == EXPECTED_RESTORED_INVOICE_AMOUNT),
        "policy_state_preserved_verified": int(policy_mutation_count == 0 and policy_enabled_before == 1 and policy_enabled_after == 1 and policy_live_before == 0 and policy_live_after == 0),
        "no_new_accounting_movement_verified": int(actual_pe_created == 0 and actual_pe_cancelled == 0 and actual_gl_created == 0),
        "gated_payment_entry": GATED_PAYMENT_ENTRY,
        "gated_payment_entry_docstatus": gated_state.docstatus,
        "gated_payment_entry_status": gated_state.status,
        "previous_gated_payment_entry": PREVIOUS_GATED_PAYMENT_ENTRY,
        "previous_gated_payment_entry_docstatus": previous_gated_state.docstatus,
        "previous_gated_payment_entry_status": previous_gated_state.status,
        "monitor_payment_entry": MONITOR_PAYMENT_ENTRY,
        "monitor_payment_entry_docstatus": state.docstatus,
        "monitor_payment_entry_status": state.status,
        "monitor_source_doctype": MONITOR_SOURCE_DOCTYPE,
        "monitor_reference_doctype": MONITOR_REFERENCE_DOCTYPE,
        "monitor_party_type": MONITOR_PARTY_TYPE,
        "monitor_customer": unique_value(rows, "customer"),
        "monitor_company": unique_value(rows, "company"),
        "monitor_currency": unique_value(rows, "currency"),
        "monitor_invoice_names": ", ".join(reference_names(rows)),
        "monitor_invoice_count": len(rows),
        "monitor_total_amount": monitor_total(rows),
        "monitor_restored_invoice_amount": restored_amount,
        "monitor_gl_rows": monitor_gl_rows,
        "monitor_reversal_gl_rows": EXPECTED_MONITOR_REVERSAL_GL_ROWS,
        "monitor_gl_net": monitor_gl_net,
        "monitor_direct_cancelled_gl_rows": direct_cancelled_rows,
        "direct_erpnext_cancelled_gl_rows": direct_cancelled_rows,
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
        "target_policy": baseline.target_policy if baseline else None,
        "target_policy_name": baseline.target_policy_name if baseline else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_before": policy_live_before,
        "target_policy_live_after": policy_live_after,
        "actual_policy_mutation_count": policy_mutation_count,
        MONITOR_READY_FIELD: completed,
        "baseline": baseline.name if baseline else None,
        "closeout": baseline.closeout if baseline else None,
        "freeze": baseline.freeze if baseline else None,
        "rollback": baseline.rollback if baseline else None,
        "smoke": baseline.smoke if baseline else None,
        "execution_gate": baseline.execution_gate if baseline else None,
        "preview": baseline.preview if baseline else None,
        "candidate_validation": baseline.candidate_validation if baseline else None,
        "candidate_selection": baseline.candidate_selection if baseline else None,
        "design": baseline.design if baseline else None,
        "planning": baseline.planning if baseline else None,
        "previous_monitor": baseline.monitor if baseline else None,
        **item_summary,
        "items": items,
        "issues": post_issues,
        "required_acknowledgement": MONITOR_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 14I activates the next governed limited-operation runtime monitor. No accounting movement occurs.",
    }

    if int(dry_run or 0):
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
    doc.monitor_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    create_items(doc, items)
    frappe.db.commit()
    return {**result, "created": True, "monitor": doc.name, "monitor_id": doc.monitor_id, "gated_payment_entry": GATED_PAYMENT_ENTRY, "previous_gated_payment_entry": PREVIOUS_GATED_PAYMENT_ENTRY, "monitor_payment_entry": MONITOR_PAYMENT_ENTRY, "guardrails_after": guardrails()}


@frappe.whitelist()
def cancel_next_governed_limited_operation_runtime_monitor_phase14i_audit(monitor, reason=None):
    assert_action("cancel_next_governed_limited_operation_runtime_monitor_phase14i_audit")
    if not frappe.db.exists(MONITOR_DOCTYPE, monitor):
        frappe.throw(_("Next governed limited-operation runtime monitor audit not found: {0}").format(monitor))
    doc = frappe.get_doc(MONITOR_DOCTYPE, monitor)
    if doc.status == "Cancelled":
        return {"monitor": monitor, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.monitor_active or 0):
        frappe.throw(_("Cannot cancel an active Phase 14I runtime monitor record."))
    frappe.db.set_value(
        MONITOR_DOCTYPE,
        monitor,
        {"status": "Cancelled", "monitor_status": "Cancelled", "cancelled_on": now_datetime(), "cancelled_by": frappe.session.user, "summary_json": reason or "Phase 14I no-ack runtime monitor audit cancelled."},
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{MONITOR_ITEM_DOCTYPE}` SET status='Cancelled' WHERE monitor=%(monitor)s", {"monitor": monitor})
    frappe.db.commit()
    return {"monitor": monitor, "status": "Cancelled", "note": "No-ack runtime monitor audit cancelled only. No accounting movement occurred."}


@frappe.whitelist()
def quick_next_governed_limited_operation_runtime_monitor_phase14i_summary(limit=20):
    return {
        "monitor_records": frappe.get_all(
            MONITOR_DOCTYPE,
            filters={"monitor_payment_entry": MONITOR_PAYMENT_ENTRY},
            fields=[
                "name",
                "monitor_id",
                "status",
                "monitor_status",
                "monitor_active",
                "gated_payment_entry",
                "gated_payment_entry_docstatus",
                "gated_payment_entry_status",
                "previous_gated_payment_entry",
                "previous_gated_payment_entry_docstatus",
                "previous_gated_payment_entry_status",
                "monitor_payment_entry",
                "monitor_payment_entry_docstatus",
                "monitor_payment_entry_status",
                "monitor_invoice_names",
                "monitor_invoice_count",
                "monitor_total_amount",
                "monitor_restored_invoice_amount",
                "monitor_gl_rows",
                "monitor_reversal_gl_rows",
                "monitor_gl_net",
                "monitor_direct_cancelled_gl_rows",
                "payment_entry_count_before",
                "payment_entry_count_after",
                "payment_entry_gl_count_before",
                "payment_entry_gl_count_after",
                "actual_payment_entry_created_count",
                "actual_payment_entry_cancelled_count",
                "actual_gl_created_count",
                "submitted_journal_entry_count_today",
                "purchase_invoice_count_today",
                MONITOR_READY_FIELD,
                "checked_on",
                "checked_by",
            ],
            order_by="creation desc",
            limit=int(limit or 20),
        ),
        "items": frappe.get_all(
            MONITOR_ITEM_DOCTYPE,
            filters={"monitor_payment_entry": MONITOR_PAYMENT_ENTRY},
            fields=["name", "monitor", "status", "severity", "category", "check_key", "check_label", "line_no", "reference_doctype", "reference_name", "customer", "company", "currency", "monitor_amount", "outstanding_amount", "gated_payment_entry", "monitor_payment_entry", "detail"],
            order_by="creation desc",
            limit=int(limit or 20),
        ),
        "required_acknowledgement": MONITOR_ACK,
        "guardrails": guardrails(),
        "note": "Phase 14I next governed limited-operation runtime monitor summary.",
    }


def execute_runtime_monitor_report(filters=None):
    columns = [
        {"fieldname": "monitor", "label": _("Monitor"), "fieldtype": "Link", "options": MONITOR_DOCTYPE, "width": 220},
        {"fieldname": "monitor_id", "label": _("Monitor ID"), "fieldtype": "Data", "width": 560},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 190},
        {"fieldname": "monitor_status", "label": _("Monitor Status"), "fieldtype": "Data", "width": 430},
        {"fieldname": "monitor_active", "label": _("Active"), "fieldtype": "Check", "width": 90},
        {"fieldname": "gated_payment_entry", "label": _("Gated PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "previous_gated_payment_entry", "label": _("Previous Gated PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "monitor_payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "monitor_payment_entry_docstatus", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 115},
        {"fieldname": "monitor_payment_entry_status", "label": _("PE Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "monitor_invoice_names", "label": _("Invoices"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "monitor_total_amount", "label": _("Amount"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "monitor_restored_invoice_amount", "label": _("Restored"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "monitor_gl_rows", "label": _("GL Rows"), "fieldtype": "Int", "width": 90},
        {"fieldname": "monitor_reversal_gl_rows", "label": _("Reversal Rows"), "fieldtype": "Int", "width": 120},
        {"fieldname": "monitor_gl_net", "label": _("GL Net"), "fieldtype": "Currency", "width": 100},
        {"fieldname": MONITOR_READY_FIELD, "label": _("Planning Ready"), "fieldtype": "Check", "width": 130},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 115},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 115},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL Created"), "fieldtype": "Int", "width": 135},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]
    data = frappe.db.sql(
        f"""
        SELECT name AS monitor, monitor_id, status, monitor_status, monitor_active,
            gated_payment_entry, previous_gated_payment_entry,
            monitor_payment_entry, monitor_payment_entry_docstatus, monitor_payment_entry_status,
            monitor_invoice_names, monitor_total_amount, monitor_restored_invoice_amount,
            monitor_gl_rows, monitor_reversal_gl_rows, monitor_gl_net,
            `{MONITOR_READY_FIELD}` AS `{MONITOR_READY_FIELD}`,
            payment_entry_count_before, payment_entry_count_after,
            payment_entry_gl_count_before, payment_entry_gl_count_after,
            actual_gl_created_count, checked_on
        FROM `tab{MONITOR_DOCTYPE}`
        WHERE monitor_payment_entry=%(payment_entry)s
        ORDER BY creation DESC
        """,
        {"payment_entry": MONITOR_PAYMENT_ENTRY},
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.monitor_id for row in data[:20]],
            "datasets": [
                {"name": "Runtime Monitor Active", "values": [int(row.monitor_active or 0) for row in data[:20]]},
                {"name": "Planning Ready", "values": [int(row.get(MONITOR_READY_FIELD) or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Monitor Records"), "datatype": "Int"},
        {"value": sum(int(row.monitor_active or 0) for row in data), "indicator": "Green", "label": _("Active"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL Created"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_monitor_report(filters=None):
    return execute_runtime_monitor_report(filters)


def execute_item_report(filters=None):
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": MONITOR_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "monitor", "label": _("Monitor"), "fieldtype": "Link", "options": MONITOR_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 190},
        {"fieldname": "line_no", "label": _("Line"), "fieldtype": "Int", "width": 60},
        {"fieldname": "reference_doctype", "label": _("Ref DocType"), "fieldtype": "Data", "width": 130},
        {"fieldname": "reference_name", "label": _("Reference"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 180},
        {"fieldname": "monitor_amount", "label": _("Monitor Amount"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "outstanding_amount", "label": _("Outstanding"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "gated_payment_entry", "label": _("Gated PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "monitor_payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 650},
    ]
    data = frappe.db.sql(
        f"""
        SELECT name AS item, monitor, status, category, line_no, reference_doctype,
            reference_name, monitor_amount, outstanding_amount, gated_payment_entry, monitor_payment_entry, detail
        FROM `tab{MONITOR_ITEM_DOCTYPE}`
        WHERE monitor_payment_entry=%(payment_entry)s
        ORDER BY creation DESC
        """,
        {"payment_entry": MONITOR_PAYMENT_ENTRY},
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": ["Pass", "Warning", "Blocker", "Info"],
            "datasets": [{"name": "Items", "values": [len([row for row in data if row.status == status]) for status in ["Pass", "Warning", "Blocker", "Info"]]}],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Items"), "datatype": "Int"},
        {"value": len([row for row in data if row.category == "Runtime Monitor Reference"]), "indicator": "Green", "label": _("Monitor References"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_runtime_monitor_report(filters)
    guard = guardrails()
    summary.append({"value": guard["payment_entry_count"], "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"})
    summary.append({"value": guard["payment_entry_gl_count"], "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"})
    summary.append({"value": guard["submitted_journal_entry_count_today"], "indicator": "Red", "label": _("Submitted JE Today"), "datatype": "Int"})
    summary.append({"value": guard["purchase_invoice_count_today"], "indicator": "Red", "label": _("Purchase Invoice Today"), "datatype": "Int"})
    summary.append({"value": guard["production_batch_enabled_policy_count"], "indicator": "Green", "label": _("Enabled Policies"), "datatype": "Int"})
    summary.append({"value": guard["live_posting_allowed_policy_count"], "indicator": "Red", "label": _("Live Policies"), "datatype": "Int"})
    return columns, data, message, chart, summary
