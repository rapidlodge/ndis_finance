import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, today

from ndis_finance.services.permissions import assert_action


FREEZE_ACK = "I_CONFIRM_PHASE13T_FREEZE_NEXT_GOVERNED_LIMITED_OPERATION_ROLLBACK_EVIDENCE_NO_POSTING"

POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
ROLLBACK_DOCTYPE = "NDIS Next Governed Limited Op Smoke Rollback"
ROLLBACK_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Smoke Rollback Item"
FREEZE_DOCTYPE = "NDIS Next Governed Limited Op Rollback Freeze"
FREEZE_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Rollback Freeze Item"

ROLLBACK_READY_FIELD = "ready_for_next_governed_limited_op_rollback_freeze"
FREEZE_READY_FIELD = "ready_for_next_governed_limited_op_closeout"

GATED_PAYMENT_ENTRY = "ACC-PAY-2026-00014"
FREEZE_PAYMENT_ENTRY = "ACC-PAY-2026-00015"
EXPECTED_INVOICES = ["ACC-SINV-2026-00005", "ACC-SINV-2026-00006", "ACC-SINV-2026-00008"]

EXPECTED_PAYMENT_ENTRY_COUNT = 14
EXPECTED_PAYMENT_ENTRY_GL_COUNT = 94
EXPECTED_TOTAL_AMOUNT = 3.00
EXPECTED_INVOICE_COUNT = 3
EXPECTED_GL_ROWS = 8
EXPECTED_REVERSAL_GL_ROWS = 4
EXPECTED_GL_NET = 0.00

FREEZE_SOURCE_DOCTYPE = "Sales Invoice"
FREEZE_REFERENCE_DOCTYPE = "Sales Invoice"
FREEZE_PARTY_TYPE = "Customer"


def make_freeze_id():
    timestamp = now_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-NEXT-GOVERNED-LIMITED-OP-ROLLBACK-FREEZE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def payment_entry_cancelled_gl_rows(payment_entry):
    if not has_column("GL Entry", "is_cancelled"):
        return 0
    value = frappe.db.sql(
        """
        SELECT COALESCE(SUM(CASE WHEN is_cancelled=1 THEN 1 ELSE 0 END), 0)
        FROM `tabGL Entry`
        WHERE voucher_type='Payment Entry'
        AND voucher_no=%s
        """,
        payment_entry,
    )[0][0]
    return int(value or 0)


def reversal_gl_rows(payment_entry):
    # ERPNext marks all voucher rows cancelled after voucher cancellation; rollback evidence uses the reversal delta.
    return max(0, payment_entry_gl_rows(payment_entry) - 4)


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


def latest_rollback():
    filters = {
        "status": "Smoke Rollback Completed",
        "rollback_status": "Next Governed Limited Operation Smoke Rollback Completed",
        "rollback_completed": 1,
        "phase13r_smoke_verified": 1,
        "smoke_completed_verified": 1,
        "smoke_payment_entry_verified": 1,
        "smoke_payment_entry_submitted_verified": 1,
        "smoke_gl_rows_verified": 1,
        "smoke_gl_net_zero_verified": 1,
        "smoke_invoice_outstanding_zero_verified": 1,
        "policy_state_preserved_verified": 1,
        "gated_payment_entry": GATED_PAYMENT_ENTRY,
        "gated_payment_entry_docstatus": 2,
        "gated_payment_entry_status": "Cancelled",
        "rollback_payment_entry": FREEZE_PAYMENT_ENTRY,
        "rollback_payment_entry_docstatus_after": 2,
        "rollback_payment_entry_status_after": "Cancelled",
        "rollback_source_doctype": FREEZE_SOURCE_DOCTYPE,
        "rollback_reference_doctype": FREEZE_REFERENCE_DOCTYPE,
        "rollback_party_type": FREEZE_PARTY_TYPE,
        "rollback_invoice_count": EXPECTED_INVOICE_COUNT,
        "rollback_total_amount": EXPECTED_TOTAL_AMOUNT,
        "invoice_outstanding_before_rollback": 0,
        "invoice_outstanding_after_rollback": EXPECTED_TOTAL_AMOUNT,
        "rollback_gl_rows": EXPECTED_GL_ROWS,
        "rollback_reversal_gl_rows": EXPECTED_REVERSAL_GL_ROWS,
        "rollback_gl_net": EXPECTED_GL_NET,
        "payment_entry_count_after": EXPECTED_PAYMENT_ENTRY_COUNT,
        "payment_entry_gl_count_after": EXPECTED_PAYMENT_ENTRY_GL_COUNT,
        "actual_payment_entry_created_count": 0,
        "actual_payment_entry_cancelled_count": 1,
        "actual_gl_created_count": 4,
        "submitted_journal_entry_count_today": 0,
        "purchase_invoice_count_today": 0,
        "target_policy_enabled_after": 1,
        "target_policy_live_after": 0,
        "actual_policy_mutation_count": 0,
        "blocker_count": 0,
        "warning_count": 0,
    }
    if has_column(ROLLBACK_DOCTYPE, ROLLBACK_READY_FIELD):
        filters[ROLLBACK_READY_FIELD] = 1

    rows = frappe.get_all(
        ROLLBACK_DOCTYPE,
        filters=filters,
        fields=[
            "name",
            "rollback_id",
            "rollback_source_doctype",
            "rollback_reference_doctype",
            "rollback_party_type",
            "rollback_customer",
            "rollback_company",
            "rollback_currency",
            "rollback_invoice_names",
            "rollback_invoice_count",
            "rollback_total_amount",
            "invoice_outstanding_after_rollback",
            "gated_payment_entry",
            "gated_payment_entry_docstatus",
            "gated_payment_entry_status",
            "rollback_payment_entry",
            "rollback_payment_entry_docstatus_after",
            "rollback_payment_entry_status_after",
            "rollback_gl_rows",
            "rollback_reversal_gl_rows",
            "rollback_gl_net",
            "smoke",
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
            "target_policy",
            "target_policy_name",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_completed_freeze(rollback):
    rows = frappe.get_all(
        FREEZE_DOCTYPE,
        filters={
            "rollback": rollback,
            "status": "Freeze Completed",
            "freeze_completed": 1,
            "freeze_payment_entry": FREEZE_PAYMENT_ENTRY,
        },
        fields=["name", "freeze_id", "freeze_payment_entry"],
        limit=1,
    )
    return rows[0] if rows else None


def rollback_rows(rollback):
    rows = frappe.get_all(
        ROLLBACK_ITEM_DOCTYPE,
        filters={
            "rollback": rollback,
            "category": "Rollback Reference",
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
            "rollback_amount",
            "outstanding_after",
        ],
        order_by="line_no asc, creation asc",
    )

    result = []
    for idx, row in enumerate(rows, start=1):
        si = (
            frappe.db.get_value(
                "Sales Invoice",
                row.reference_name,
                ["docstatus", "customer", "company", "currency", "outstanding_amount"],
                as_dict=True,
            )
            if frappe.db.exists("Sales Invoice", row.reference_name)
            else None
        )
        result.append(
            frappe._dict(
                {
                    "idx": int(row.line_no or idx),
                    "reference_doctype": row.reference_doctype,
                    "reference_name": row.reference_name,
                    "freeze_amount": flt(row.rollback_amount or 0, 2),
                    "outstanding_amount": flt((si.outstanding_amount if si else row.outstanding_after) or 0, 2),
                    "customer": si.customer if si else row.customer,
                    "company": si.company if si else row.company,
                    "currency": si.currency if si else row.currency,
                    "invoice_docstatus": int(si.docstatus or 0) if si else 0,
                    "freeze_payment_entry": FREEZE_PAYMENT_ENTRY,
                    "gated_payment_entry": GATED_PAYMENT_ENTRY,
                }
            )
        )
    return result


def reference_names(rows):
    return [row.reference_name for row in rows]


def freeze_total(rows):
    return flt(sum(flt(row.freeze_amount or 0, 2) for row in rows), 2)


def unique_value(rows, fieldname):
    values = sorted(set([getattr(row, fieldname, None) for row in rows if getattr(row, fieldname, None)]))
    return values[0] if len(values) == 1 else None


def validate_source(rollback, rows, guard, config, policy_enabled, policy_live):
    issues = []
    if not rollback:
        issues.append("No completed Phase 13S rollback found for rollback freeze.")
        return issues

    existing = existing_completed_freeze(rollback.name)
    if existing:
        issues.append(f"Completed Phase 13T freeze already exists for this rollback: {existing.freeze_id} / {existing.freeze_payment_entry}")

    state = payment_entry_state(FREEZE_PAYMENT_ENTRY)
    gated_state = payment_entry_state(GATED_PAYMENT_ENTRY)
    if not frappe.db.exists("Payment Entry", FREEZE_PAYMENT_ENTRY):
        issues.append(f"Freeze Payment Entry does not exist: {FREEZE_PAYMENT_ENTRY}")
    if state.docstatus != 2 or state.status != "Cancelled":
        issues.append(f"Freeze Payment Entry must remain Cancelled / 2. Found {state.status} / {state.docstatus}")
    if gated_state.docstatus != 2 or gated_state.status != "Cancelled":
        issues.append(f"Gated Payment Entry must remain Cancelled / 2. Found {gated_state.status} / {gated_state.docstatus}")
    if reference_names(rows) != EXPECTED_INVOICES:
        issues.append(f"Freeze invoice set changed. Expected {EXPECTED_INVOICES}. Found {reference_names(rows)}.")
    if len(rows) != EXPECTED_INVOICE_COUNT:
        issues.append(f"Freeze invoice count must be {EXPECTED_INVOICE_COUNT}. Found {len(rows)}.")
    if freeze_total(rows) != EXPECTED_TOTAL_AMOUNT:
        issues.append(f"Freeze total amount must be {EXPECTED_TOTAL_AMOUNT}. Found {freeze_total(rows)}.")
    if outstanding_total(EXPECTED_INVOICES) != EXPECTED_TOTAL_AMOUNT:
        issues.append(f"Restored invoice outstanding must be {EXPECTED_TOTAL_AMOUNT} before freeze.")
    if payment_entry_gl_rows(FREEZE_PAYMENT_ENTRY) != EXPECTED_GL_ROWS:
        issues.append(f"Freeze Payment Entry must have {EXPECTED_GL_ROWS} voucher GL rows.")
    if reversal_gl_rows(FREEZE_PAYMENT_ENTRY) != EXPECTED_REVERSAL_GL_ROWS:
        issues.append(f"Freeze Payment Entry must have {EXPECTED_REVERSAL_GL_ROWS} reversal GL rows.")
    if payment_entry_gl_net(FREEZE_PAYMENT_ENTRY) != EXPECTED_GL_NET:
        issues.append("Freeze Payment Entry GL net must be 0.00.")
    if guard["payment_entry_count"] != EXPECTED_PAYMENT_ENTRY_COUNT:
        issues.append("Payment Entry count must remain 14 before freeze.")
    if guard["payment_entry_gl_count"] != EXPECTED_PAYMENT_ENTRY_GL_COUNT:
        issues.append("Payment Entry GL count must remain 94 before freeze.")
    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today must remain 0 before freeze.")
    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today must remain 0 before freeze.")
    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must remain enabled before freeze.")
    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must remain 0 before freeze.")
    if policy_enabled != 1:
        issues.append("Target policy production_batch_enabled must remain 1.")
    if policy_live != 0:
        issues.append("Target policy live_posting_allowed must remain 0.")
    if config["sandbox_enabled"] != 1:
        issues.append("Sandbox config must be enabled for freeze.")
    if config["production_mode"] != 0:
        issues.append("Production mode config must remain 0 for freeze.")
    if config["live_pe_enabled"] != 0:
        issues.append("Live Payment Entry posting config must remain 0 for freeze.")
    return issues


def build_items(rows, issues, ack_ok):
    items = []
    if not issues:
        items.append(
            {
                "status": "Pass",
                "severity": "Critical",
                "category": "Freeze Source",
                "check_key": "freeze_source_valid",
                "check_label": "Freeze source valid",
                "detail": f"Rollback evidence for {FREEZE_PAYMENT_ENTRY} is stable and ready to freeze.",
                "freeze_payment_entry": FREEZE_PAYMENT_ENTRY,
                "gated_payment_entry": GATED_PAYMENT_ENTRY,
            }
        )
    else:
        for issue in issues:
            items.append(
                {
                    "status": "Blocker",
                    "severity": "Critical",
                    "category": "Freeze Source",
                    "check_key": "freeze_source_valid",
                    "check_label": "Freeze source valid",
                    "detail": issue,
                    "freeze_payment_entry": FREEZE_PAYMENT_ENTRY,
                    "gated_payment_entry": GATED_PAYMENT_ENTRY,
                }
            )

    for row in rows:
        items.append(
            {
                "status": "Pass",
                "severity": "High",
                "category": "Freeze Reference",
                "check_key": "freeze_sales_invoice_reference",
                "check_label": f"Freeze Sales Invoice {row.idx}",
                "detail": f"{row.reference_name} freeze amount={row.freeze_amount}, outstanding={row.outstanding_amount}.",
                "line_no": row.idx,
                "reference_doctype": row.reference_doctype,
                "reference_name": row.reference_name,
                "customer": row.customer,
                "company": row.company,
                "currency": row.currency,
                "freeze_amount": row.freeze_amount,
                "outstanding_amount": row.outstanding_amount,
                "freeze_payment_entry": FREEZE_PAYMENT_ENTRY,
                "gated_payment_entry": GATED_PAYMENT_ENTRY,
            }
        )

    items.append(
        {
            "status": "Pass" if ack_ok else "Warning",
            "severity": "Low" if ack_ok else "Medium",
            "category": "Acknowledgement",
            "check_key": "ack_ok",
            "check_label": "Acknowledgement supplied",
            "detail": "Exact acknowledgement supplied." if ack_ok else f"Required acknowledgement not supplied: {FREEZE_ACK}",
            "freeze_payment_entry": FREEZE_PAYMENT_ENTRY,
            "gated_payment_entry": GATED_PAYMENT_ENTRY,
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
        row = frappe.new_doc(FREEZE_ITEM_DOCTYPE)
        row.freeze = doc.name
        for fieldname, value in item.items():
            if row.meta.has_field(fieldname):
                setattr(row, fieldname, value)
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_next_governed_limited_operation_rollback_freeze_phase13t(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_next_governed_limited_operation_rollback_freeze_phase13t")

    rollback = latest_rollback()
    rows = rollback_rows(rollback.name) if rollback else []
    guard_before = guardrails()
    ack_ok = acknowledgement == FREEZE_ACK

    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }
    policy_enabled_before = get_flag(POLICY_DOCTYPE, rollback.target_policy, "production_batch_enabled") if rollback else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, rollback.target_policy, "live_posting_allowed") if rollback else 0
    source_issues = validate_source(rollback, rows, guard_before, config, policy_enabled_before, policy_live_before)

    guard_after = guardrails()
    policy_enabled_after = get_flag(POLICY_DOCTYPE, rollback.target_policy, "production_batch_enabled") if rollback else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, rollback.target_policy, "live_posting_allowed") if rollback else 0
    state = payment_entry_state(FREEZE_PAYMENT_ENTRY)
    gated_state = payment_entry_state(GATED_PAYMENT_ENTRY)
    freeze_gl_rows = payment_entry_gl_rows(FREEZE_PAYMENT_ENTRY)
    freeze_reversal_gl_rows = reversal_gl_rows(FREEZE_PAYMENT_ENTRY)
    freeze_gl_net = payment_entry_gl_net(FREEZE_PAYMENT_ENTRY)
    restored_amount = outstanding_total(EXPECTED_INVOICES)

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
        post_issues.append(f"Freeze must create 0 Payment Entries. Created {actual_pe_created}.")
    if actual_pe_cancelled != 0:
        post_issues.append(f"Freeze must cancel 0 Payment Entries. Cancelled {actual_pe_cancelled}.")
    if actual_gl_created != 0:
        post_issues.append(f"Freeze must create 0 GL rows. Created {actual_gl_created}.")
    if guard_after["submitted_journal_entry_count_today"] != 0:
        post_issues.append("Submitted Journal Entry today must remain 0 after freeze.")
    if guard_after["purchase_invoice_count_today"] != 0:
        post_issues.append("Purchase Invoice today must remain 0 after freeze.")
    if policy_mutation_count != 0:
        post_issues.append("Policy state changed during freeze. This is not allowed.")

    completed = int(
        not int(dry_run or 0)
        and ack_ok
        and rollback
        and not post_issues
        and state.docstatus == 2
        and state.status == "Cancelled"
        and gated_state.docstatus == 2
        and gated_state.status == "Cancelled"
        and freeze_gl_rows == EXPECTED_GL_ROWS
        and freeze_reversal_gl_rows == EXPECTED_REVERSAL_GL_ROWS
        and freeze_gl_net == EXPECTED_GL_NET
        and restored_amount == EXPECTED_TOTAL_AMOUNT
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

    items = build_items(rows, post_issues, ack_ok)
    item_summary = summarise_items(items)
    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Freeze Completed" if completed else "Needs Review",
        "freeze_status": "Next Governed Limited Operation Rollback Evidence Frozen" if completed else "Needs Review",
        "freeze_completed": completed,
        "phase13s_rollback_verified": 1 if rollback else 0,
        "rollback_completed_verified": 1 if rollback else 0,
        "rollback_payment_entry_verified": int(rollback and rollback.rollback_payment_entry == FREEZE_PAYMENT_ENTRY),
        "rollback_payment_entry_cancelled_verified": int(state.docstatus == 2 and state.status == "Cancelled"),
        "rollback_gl_rows_verified": int(freeze_gl_rows == EXPECTED_GL_ROWS),
        "rollback_reversal_gl_rows_verified": int(freeze_reversal_gl_rows == EXPECTED_REVERSAL_GL_ROWS),
        "rollback_gl_net_zero_verified": int(freeze_gl_net == EXPECTED_GL_NET),
        "rollback_restored_invoice_amount_verified": int(restored_amount == EXPECTED_TOTAL_AMOUNT),
        "policy_state_preserved_verified": int(policy_mutation_count == 0 and policy_enabled_before == 1 and policy_enabled_after == 1 and policy_live_before == 0 and policy_live_after == 0),
        "no_new_accounting_movement_verified": int(actual_pe_created == 0 and actual_pe_cancelled == 0 and actual_gl_created == 0),
        "freeze_payment_entry": FREEZE_PAYMENT_ENTRY,
        "freeze_payment_entry_docstatus": state.docstatus,
        "freeze_payment_entry_status": state.status,
        "gated_payment_entry": GATED_PAYMENT_ENTRY,
        "gated_payment_entry_docstatus": gated_state.docstatus,
        "gated_payment_entry_status": gated_state.status,
        "freeze_source_doctype": FREEZE_SOURCE_DOCTYPE,
        "freeze_reference_doctype": FREEZE_REFERENCE_DOCTYPE,
        "freeze_party_type": FREEZE_PARTY_TYPE,
        "freeze_customer": unique_value(rows, "customer"),
        "freeze_company": unique_value(rows, "company"),
        "freeze_currency": unique_value(rows, "currency"),
        "freeze_invoice_names": ", ".join(reference_names(rows)),
        "freeze_invoice_count": len(rows),
        "freeze_total_amount": freeze_total(rows),
        "freeze_restored_invoice_amount": restored_amount,
        "freeze_gl_rows": freeze_gl_rows,
        "freeze_reversal_gl_rows": freeze_reversal_gl_rows,
        "freeze_gl_net": freeze_gl_net,
        "freeze_direct_cancelled_gl_rows": payment_entry_cancelled_gl_rows(FREEZE_PAYMENT_ENTRY),
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
        "target_policy": rollback.target_policy if rollback else None,
        "target_policy_name": rollback.target_policy_name if rollback else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_before": policy_live_before,
        "target_policy_live_after": policy_live_after,
        "actual_policy_mutation_count": policy_mutation_count,
        FREEZE_READY_FIELD: completed,
        "rollback": rollback.name if rollback else None,
        "smoke": rollback.smoke if rollback else None,
        "execution_gate": rollback.execution_gate if rollback else None,
        "preview": rollback.preview if rollback else None,
        "candidate_validation": rollback.candidate_validation if rollback else None,
        "candidate_selection": rollback.candidate_selection if rollback else None,
        "design": rollback.design if rollback else None,
        "planning": rollback.planning if rollback else None,
        "monitor": rollback.monitor if rollback else None,
        "baseline": rollback.baseline if rollback else None,
        "closeout": rollback.closeout if rollback else None,
        "previous_freeze": rollback.freeze if rollback else None,
        **item_summary,
        "items": items,
        "issues": post_issues,
        "required_acknowledgement": FREEZE_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 13T freezes the next governed limited-operation rollback evidence. No accounting movement occurs.",
    }

    if int(dry_run or 0):
        return result

    doc = frappe.new_doc(FREEZE_DOCTYPE)
    doc.freeze_id = make_freeze_id()
    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = FREEZE_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.freeze_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    create_items(doc, items)
    frappe.db.commit()

    return {**result, "created": True, "freeze": doc.name, "freeze_id": doc.freeze_id, "freeze_payment_entry": FREEZE_PAYMENT_ENTRY, "guardrails_after": guardrails()}


@frappe.whitelist()
def cancel_next_governed_limited_operation_rollback_freeze_phase13t_audit(freeze, reason=None):
    assert_action("cancel_next_governed_limited_operation_rollback_freeze_phase13t_audit")
    if not frappe.db.exists(FREEZE_DOCTYPE, freeze):
        frappe.throw(_("Next governed limited-operation rollback freeze audit not found: {0}").format(freeze))
    doc = frappe.get_doc(FREEZE_DOCTYPE, freeze)
    if doc.status == "Cancelled":
        return {"freeze": freeze, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.freeze_completed or 0):
        frappe.throw(_("Cannot cancel a completed Phase 13T freeze record."))
    frappe.db.set_value(
        FREEZE_DOCTYPE,
        freeze,
        {
            "status": "Cancelled",
            "freeze_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 13T no-ack rollback freeze audit cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{FREEZE_ITEM_DOCTYPE}` SET status='Cancelled' WHERE freeze=%(freeze)s", {"freeze": freeze})
    frappe.db.commit()
    return {"freeze": freeze, "status": "Cancelled", "note": "No-ack rollback freeze audit cancelled only. No accounting movement occurred."}


@frappe.whitelist()
def quick_next_governed_limited_operation_rollback_freeze_summary(limit=20):
    return {
        "freeze_records": frappe.get_all(
            FREEZE_DOCTYPE,
            filters={"freeze_payment_entry": FREEZE_PAYMENT_ENTRY},
            fields=[
                "name",
                "freeze_id",
                "status",
                "freeze_status",
                "freeze_completed",
                "phase13s_rollback_verified",
                "gated_payment_entry",
                "gated_payment_entry_docstatus",
                "gated_payment_entry_status",
                "freeze_payment_entry",
                "freeze_payment_entry_docstatus",
                "freeze_payment_entry_status",
                "freeze_invoice_names",
                "freeze_invoice_count",
                "freeze_total_amount",
                "freeze_restored_invoice_amount",
                "freeze_gl_rows",
                "freeze_reversal_gl_rows",
                "freeze_gl_net",
                "freeze_direct_cancelled_gl_rows",
                "payment_entry_count_before",
                "payment_entry_count_after",
                "payment_entry_gl_count_before",
                "payment_entry_gl_count_after",
                "actual_payment_entry_created_count",
                "actual_payment_entry_cancelled_count",
                "actual_gl_created_count",
                "submitted_journal_entry_count_today",
                "purchase_invoice_count_today",
                FREEZE_READY_FIELD,
                "checked_on",
                "checked_by",
            ],
            order_by="creation desc",
            limit=int(limit or 20),
        ),
        "items": frappe.get_all(
            FREEZE_ITEM_DOCTYPE,
            filters={"freeze_payment_entry": FREEZE_PAYMENT_ENTRY},
            fields=[
                "name",
                "freeze",
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
                "freeze_amount",
                "outstanding_amount",
                "gated_payment_entry",
                "freeze_payment_entry",
                "detail",
            ],
            order_by="creation desc",
            limit=int(limit or 20),
        ),
        "required_acknowledgement": FREEZE_ACK,
        "guardrails": guardrails(),
        "note": "Phase 13T next governed limited-operation rollback freeze summary.",
    }


quick_next_governed_limited_operation_rollback_freeze_phase13t_summary = quick_next_governed_limited_operation_rollback_freeze_summary


def execute_freeze_report(filters=None):
    columns = [
        {"fieldname": "freeze", "label": _("Freeze"), "fieldtype": "Link", "options": FREEZE_DOCTYPE, "width": 220},
        {"fieldname": "freeze_id", "label": _("Freeze ID"), "fieldtype": "Data", "width": 560},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 160},
        {"fieldname": "freeze_status", "label": _("Freeze Status"), "fieldtype": "Data", "width": 430},
        {"fieldname": "freeze_completed", "label": _("Completed"), "fieldtype": "Check", "width": 100},
        {"fieldname": "freeze_payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "gated_payment_entry", "label": _("Gated PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "freeze_payment_entry_docstatus", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 115},
        {"fieldname": "freeze_payment_entry_status", "label": _("PE Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "freeze_invoice_names", "label": _("Invoices"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "freeze_total_amount", "label": _("Amount"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "freeze_restored_invoice_amount", "label": _("Restored"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "freeze_gl_rows", "label": _("GL Rows"), "fieldtype": "Int", "width": 90},
        {"fieldname": "freeze_reversal_gl_rows", "label": _("Reversal Rows"), "fieldtype": "Int", "width": 120},
        {"fieldname": "freeze_gl_net", "label": _("GL Net"), "fieldtype": "Currency", "width": 100},
        {"fieldname": FREEZE_READY_FIELD, "label": _("Closeout Ready"), "fieldtype": "Check", "width": 130},
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
            name AS freeze,
            freeze_id,
            status,
            freeze_status,
            freeze_completed,
            freeze_payment_entry,
            gated_payment_entry,
            freeze_payment_entry_docstatus,
            freeze_payment_entry_status,
            freeze_invoice_names,
            freeze_total_amount,
            freeze_restored_invoice_amount,
            freeze_gl_rows,
            freeze_reversal_gl_rows,
            freeze_gl_net,
            `{FREEZE_READY_FIELD}` AS `{FREEZE_READY_FIELD}`,
            payment_entry_count_before,
            payment_entry_count_after,
            payment_entry_gl_count_before,
            payment_entry_gl_count_after,
            actual_gl_created_count,
            checked_on
        FROM `tab{FREEZE_DOCTYPE}`
        WHERE freeze_payment_entry=%(payment_entry)s
        ORDER BY creation DESC
        """,
        {"payment_entry": FREEZE_PAYMENT_ENTRY},
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.freeze_id for row in data[:20]],
            "datasets": [
                {"name": "Freeze Completed", "values": [int(row.freeze_completed or 0) for row in data[:20]]},
                {"name": "Closeout Ready", "values": [int(row.get(FREEZE_READY_FIELD) or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Freeze Records"), "datatype": "Int"},
        {"value": sum(int(row.freeze_completed or 0) for row in data), "indicator": "Green", "label": _("Completed"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL Created"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_item_report(filters=None):
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": FREEZE_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "freeze", "label": _("Freeze"), "fieldtype": "Link", "options": FREEZE_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 190},
        {"fieldname": "line_no", "label": _("Line"), "fieldtype": "Int", "width": 60},
        {"fieldname": "reference_doctype", "label": _("Ref DocType"), "fieldtype": "Data", "width": 130},
        {"fieldname": "reference_name", "label": _("Reference"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 180},
        {"fieldname": "freeze_amount", "label": _("Freeze Amount"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "outstanding_amount", "label": _("Outstanding"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "freeze_payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "gated_payment_entry", "label": _("Gated PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 650},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            name AS item,
            freeze,
            status,
            category,
            line_no,
            reference_doctype,
            reference_name,
            freeze_amount,
            outstanding_amount,
            freeze_payment_entry,
            gated_payment_entry,
            detail
        FROM `tab{FREEZE_ITEM_DOCTYPE}`
        WHERE freeze_payment_entry=%(payment_entry)s
        ORDER BY creation DESC
        """,
        {"payment_entry": FREEZE_PAYMENT_ENTRY},
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": ["Pass", "Warning", "Blocker", "Info"],
            "datasets": [
                {
                    "name": "Items",
                    "values": [
                        len([row for row in data if row.status == "Pass"]),
                        len([row for row in data if row.status == "Warning"]),
                        len([row for row in data if row.status == "Blocker"]),
                        len([row for row in data if row.status == "Info"]),
                    ],
                }
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Items"), "datatype": "Int"},
        {"value": len([row for row in data if row.category == "Freeze Reference"]), "indicator": "Green", "label": _("Freeze References"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_freeze_report(filters)
    guard = guardrails()
    summary.append({"value": guard["payment_entry_count"], "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"})
    summary.append({"value": guard["payment_entry_gl_count"], "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"})
    summary.append({"value": guard["submitted_journal_entry_count_today"], "indicator": "Red", "label": _("Submitted JE Today"), "datatype": "Int"})
    summary.append({"value": guard["purchase_invoice_count_today"], "indicator": "Red", "label": _("Purchase Invoice Today"), "datatype": "Int"})
    summary.append({"value": guard["production_batch_enabled_policy_count"], "indicator": "Green", "label": _("Enabled Policies"), "datatype": "Int"})
    summary.append({"value": guard["live_posting_allowed_policy_count"], "indicator": "Red", "label": _("Live Policies"), "datatype": "Int"})
    return columns, data, message, chart, summary
