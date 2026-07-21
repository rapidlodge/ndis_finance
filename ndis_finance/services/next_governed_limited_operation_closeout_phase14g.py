import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, today

from ndis_finance.services.permissions import assert_action


CLOSEOUT_ACK = "I_CONFIRM_PHASE14G_CLOSE_NEXT_GOVERNED_LIMITED_OPERATION_NO_POSTING"

POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
FREEZE_DOCTYPE = "NDIS Next Governed Limited Op Rollback Freeze"
FREEZE_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Rollback Freeze Item"
CLOSEOUT_DOCTYPE = "NDIS Next Governed Limited Op Closeout"
CLOSEOUT_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Closeout Item"

FREEZE_READY_FIELD = "ready_for_next_governed_limited_op_closeout"
CLOSEOUT_READY_FIELD = "ready_for_next_governed_limited_op_steady_baseline"

GATED_PAYMENT_ENTRY = "ACC-PAY-2026-00015"
PREVIOUS_GATED_PAYMENT_ENTRY = "ACC-PAY-2026-00014"
CLOSEOUT_PAYMENT_ENTRY = "ACC-PAY-2026-00016"
EXPECTED_INVOICES = ["ACC-SINV-2026-00005", "ACC-SINV-2026-00006", "ACC-SINV-2026-00008"]

EXPECTED_PAYMENT_ENTRY_COUNT = 15
EXPECTED_PAYMENT_ENTRY_GL_COUNT = 102
EXPECTED_TOTAL_AMOUNT = 3.00
EXPECTED_INVOICE_COUNT = 3
EXPECTED_RESTORED_INVOICE_AMOUNT = 3.00
EXPECTED_CLOSEOUT_GL_ROWS = 8
EXPECTED_CLOSEOUT_REVERSAL_GL_ROWS = 4
EXPECTED_CLOSEOUT_GL_NET = 0.00

CLOSEOUT_SOURCE_DOCTYPE = "Sales Invoice"
CLOSEOUT_REFERENCE_DOCTYPE = "Sales Invoice"
CLOSEOUT_PARTY_TYPE = "Customer"


def make_closeout_id():
    timestamp = now_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-NEXT-GOVERNED-LIMITED-OP-CLOSEOUT-14G-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_freeze():
    filters = {
        "status": "Freeze Completed",
        "freeze_status": "Next Governed Limited Operation Rollback Evidence Frozen",
        "freeze_completed": 1,
        "phase14e_rollback_verified": 1,
        "rollback_completed_verified": 1,
        "rollback_payment_entry_verified": 1,
        "rollback_payment_entry_cancelled_verified": 1,
        "rollback_gl_rows_verified": 1,
        "rollback_reversal_gl_rows_verified": 1,
        "rollback_gl_net_zero_verified": 1,
        "rollback_restored_invoice_amount_verified": 1,
        "policy_state_preserved_verified": 1,
        "no_new_accounting_movement_verified": 1,
        "gated_payment_entry": GATED_PAYMENT_ENTRY,
        "gated_payment_entry_docstatus": 2,
        "gated_payment_entry_status": "Cancelled",
        "previous_gated_payment_entry": PREVIOUS_GATED_PAYMENT_ENTRY,
        "previous_gated_payment_entry_docstatus": 2,
        "previous_gated_payment_entry_status": "Cancelled",
        "freeze_payment_entry": CLOSEOUT_PAYMENT_ENTRY,
        "freeze_payment_entry_docstatus": 2,
        "freeze_payment_entry_status": "Cancelled",
        "freeze_source_doctype": CLOSEOUT_SOURCE_DOCTYPE,
        "freeze_reference_doctype": CLOSEOUT_REFERENCE_DOCTYPE,
        "freeze_party_type": CLOSEOUT_PARTY_TYPE,
        "freeze_invoice_count": EXPECTED_INVOICE_COUNT,
        "freeze_total_amount": EXPECTED_TOTAL_AMOUNT,
        "freeze_restored_invoice_amount": EXPECTED_TOTAL_AMOUNT,
        "freeze_gl_rows": EXPECTED_CLOSEOUT_GL_ROWS,
        "freeze_reversal_gl_rows": EXPECTED_CLOSEOUT_REVERSAL_GL_ROWS,
        "freeze_gl_net": EXPECTED_CLOSEOUT_GL_NET,
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
    if has_column(FREEZE_DOCTYPE, FREEZE_READY_FIELD):
        filters[FREEZE_READY_FIELD] = 1

    rows = frappe.get_all(
        FREEZE_DOCTYPE,
        filters=filters,
        fields=[
            "name",
            "freeze_id",
            "freeze_source_doctype",
            "freeze_reference_doctype",
            "freeze_party_type",
            "freeze_customer",
            "freeze_company",
            "freeze_currency",
            "freeze_invoice_names",
            "freeze_invoice_count",
            "freeze_total_amount",
            "freeze_restored_invoice_amount",
            "gated_payment_entry",
            "gated_payment_entry_docstatus",
            "gated_payment_entry_status",
            "previous_gated_payment_entry",
            "previous_gated_payment_entry_docstatus",
            "previous_gated_payment_entry_status",
            "freeze_payment_entry",
            "freeze_payment_entry_docstatus",
            "freeze_payment_entry_status",
            "freeze_gl_rows",
            "freeze_reversal_gl_rows",
            "freeze_gl_net",
            "rollback",
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
            "target_policy",
            "target_policy_name",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_completed_closeout(freeze):
    rows = frappe.get_all(
        CLOSEOUT_DOCTYPE,
        filters={"freeze": freeze, "status": "Closed", "closeout_completed": 1},
        fields=["name", "closeout_id", "closeout_payment_entry"],
        limit=1,
    )
    return rows[0] if rows else None


def freeze_rows(freeze):
    rows = frappe.get_all(
        FREEZE_ITEM_DOCTYPE,
        filters={"freeze": freeze, "category": "Freeze Reference", "status": "Pass", "reference_doctype": "Sales Invoice"},
        fields=[
            "line_no",
            "reference_doctype",
            "reference_name",
            "customer",
            "company",
            "currency",
            "freeze_amount",
            "outstanding_amount",
            "freeze_payment_entry",
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
                    "closeout_amount": flt(row.freeze_amount or 0, 2),
                    "outstanding_amount": flt((si.outstanding_amount if si else row.outstanding_amount) or 0, 2),
                    "customer": si.customer if si else row.customer,
                    "company": si.company if si else row.company,
                    "currency": si.currency if si else row.currency,
                    "invoice_docstatus": int(si.docstatus or 0) if si else 0,
                    "gated_payment_entry": GATED_PAYMENT_ENTRY,
                    "closeout_payment_entry": CLOSEOUT_PAYMENT_ENTRY,
                }
            )
        )
    return result


def reference_names(rows):
    return [row.reference_name for row in rows]


def closeout_total(rows):
    return flt(sum(flt(row.closeout_amount or 0, 2) for row in rows), 2)


def unique_value(rows, fieldname):
    values = sorted(set([getattr(row, fieldname, None) for row in rows if getattr(row, fieldname, None)]))
    return values[0] if len(values) == 1 else None


def validate_source(freeze, rows, guard, config, policy_enabled, policy_live):
    issues = []
    if not freeze:
        issues.append("No completed Phase 14F rollback freeze found for closeout.")
        return issues

    existing = existing_completed_closeout(freeze.name)
    if existing:
        issues.append(f"Completed Phase 14G closeout already exists for this freeze: {existing.closeout_id} / {existing.closeout_payment_entry}")

    closeout_state = payment_entry_state(CLOSEOUT_PAYMENT_ENTRY)
    gated_state = payment_entry_state(GATED_PAYMENT_ENTRY)
    previous_gated_state = payment_entry_state(PREVIOUS_GATED_PAYMENT_ENTRY)
    if not frappe.db.exists("Payment Entry", CLOSEOUT_PAYMENT_ENTRY):
        issues.append(f"Closeout Payment Entry does not exist: {CLOSEOUT_PAYMENT_ENTRY}")
    if closeout_state.docstatus != 2 or closeout_state.status != "Cancelled":
        issues.append(f"Closeout Payment Entry must remain Cancelled / 2. Found {closeout_state.status} / {closeout_state.docstatus}")
    if not frappe.db.exists("Payment Entry", GATED_PAYMENT_ENTRY):
        issues.append(f"Gated Payment Entry does not exist: {GATED_PAYMENT_ENTRY}")
    if gated_state.docstatus != 2 or gated_state.status != "Cancelled":
        issues.append(f"Gated Payment Entry must remain Cancelled / 2. Found {gated_state.status} / {gated_state.docstatus}")
    if not frappe.db.exists("Payment Entry", PREVIOUS_GATED_PAYMENT_ENTRY):
        issues.append(f"Previous gated Payment Entry does not exist: {PREVIOUS_GATED_PAYMENT_ENTRY}")
    if previous_gated_state.docstatus != 2 or previous_gated_state.status != "Cancelled":
        issues.append(f"Previous gated Payment Entry must remain Cancelled / 2. Found {previous_gated_state.status} / {previous_gated_state.docstatus}")
    if reference_names(rows) != EXPECTED_INVOICES:
        issues.append(f"Closeout invoice set changed. Expected {EXPECTED_INVOICES}. Found {reference_names(rows)}.")
    if len(rows) != EXPECTED_INVOICE_COUNT:
        issues.append(f"Closeout invoice count must be {EXPECTED_INVOICE_COUNT}. Found {len(rows)}.")
    if closeout_total(rows) != EXPECTED_TOTAL_AMOUNT:
        issues.append(f"Closeout total amount must be {EXPECTED_TOTAL_AMOUNT}. Found {closeout_total(rows)}.")
    if outstanding_total(EXPECTED_INVOICES) != EXPECTED_RESTORED_INVOICE_AMOUNT:
        issues.append(f"Restored invoice amount before closeout must be exactly {EXPECTED_RESTORED_INVOICE_AMOUNT}.")
    if payment_entry_gl_rows(CLOSEOUT_PAYMENT_ENTRY) != EXPECTED_CLOSEOUT_GL_ROWS:
        issues.append(f"Closeout Payment Entry must have {EXPECTED_CLOSEOUT_GL_ROWS} GL rows.")
    if payment_entry_gl_net(CLOSEOUT_PAYMENT_ENTRY) != EXPECTED_CLOSEOUT_GL_NET:
        issues.append("Closeout Payment Entry GL net must be 0.00.")
    if guard["payment_entry_count"] != EXPECTED_PAYMENT_ENTRY_COUNT:
        issues.append("Payment Entry count before Phase 14G must be exactly 15.")
    if guard["payment_entry_gl_count"] != EXPECTED_PAYMENT_ENTRY_GL_COUNT:
        issues.append("Payment Entry GL count before Phase 14G must be exactly 102.")
    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today must remain 0 before closeout.")
    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today must remain 0 before closeout.")
    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must remain enabled before closeout.")
    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must remain 0 before closeout.")
    if policy_enabled != 1:
        issues.append("Target policy production_batch_enabled must remain 1.")
    if policy_live != 0:
        issues.append("Target policy live_posting_allowed must remain 0.")
    if config["sandbox_enabled"] != 1:
        issues.append("Sandbox config must be enabled for closeout.")
    if config["production_mode"] != 0:
        issues.append("Production mode config must remain 0 for closeout.")
    if config["live_pe_enabled"] != 0:
        issues.append("Live Payment Entry posting config must remain 0 for closeout.")
    return issues


def build_items(rows, issues, ack_ok):
    items = []
    if not issues:
        items.append(
            {
                "status": "Pass",
                "severity": "Critical",
                "category": "Closeout Source",
                "check_key": "closeout_source_valid",
                "check_label": "Closeout source valid",
                "detail": f"Rollback freeze evidence for {CLOSEOUT_PAYMENT_ENTRY} is stable and ready to close.",
                "closeout_payment_entry": CLOSEOUT_PAYMENT_ENTRY,
            }
        )
    else:
        for issue in issues:
            items.append(
                {
                    "status": "Blocker",
                    "severity": "Critical",
                    "category": "Closeout Source",
                    "check_key": "closeout_source_valid",
                    "check_label": "Closeout source valid",
                    "detail": issue,
                    "closeout_payment_entry": CLOSEOUT_PAYMENT_ENTRY,
                }
            )
    for row in rows:
        items.append(
            {
                "status": "Pass",
                "severity": "High",
                "category": "Closeout Reference",
                "check_key": "closeout_sales_invoice_reference",
                "check_label": f"Closeout Sales Invoice {row.idx}",
                "detail": f"{row.reference_name} closeout amount={row.closeout_amount}, outstanding={row.outstanding_amount}.",
                "line_no": row.idx,
                "reference_doctype": row.reference_doctype,
                "reference_name": row.reference_name,
                "customer": row.customer,
                "company": row.company,
                "currency": row.currency,
                "closeout_amount": row.closeout_amount,
                "outstanding_amount": row.outstanding_amount,
                "gated_payment_entry": GATED_PAYMENT_ENTRY,
                "closeout_payment_entry": CLOSEOUT_PAYMENT_ENTRY,
            }
        )
    items.append(
        {
            "status": "Pass" if ack_ok else "Warning",
            "severity": "Low" if ack_ok else "Medium",
            "category": "Acknowledgement",
            "check_key": "ack_ok",
            "check_label": "Acknowledgement supplied",
            "detail": "Exact acknowledgement supplied." if ack_ok else f"Required acknowledgement not supplied: {CLOSEOUT_ACK}",
            "gated_payment_entry": GATED_PAYMENT_ENTRY,
            "closeout_payment_entry": CLOSEOUT_PAYMENT_ENTRY,
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
        row = frappe.new_doc(CLOSEOUT_ITEM_DOCTYPE)
        row.closeout = doc.name
        for fieldname, value in item.items():
            if row.meta.has_field(fieldname):
                setattr(row, fieldname, value)
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_next_governed_limited_operation_closeout_phase14g(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_next_governed_limited_operation_closeout_phase14g")

    freeze = latest_freeze()
    rows = freeze_rows(freeze.name) if freeze else []
    guard_before = guardrails()
    ack_ok = acknowledgement == CLOSEOUT_ACK
    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }
    policy_enabled_before = get_flag(POLICY_DOCTYPE, freeze.target_policy, "production_batch_enabled") if freeze else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, freeze.target_policy, "live_posting_allowed") if freeze else 0
    source_issues = validate_source(freeze, rows, guard_before, config, policy_enabled_before, policy_live_before)
    guard_after = guardrails()
    policy_enabled_after = get_flag(POLICY_DOCTYPE, freeze.target_policy, "production_batch_enabled") if freeze else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, freeze.target_policy, "live_posting_allowed") if freeze else 0

    closeout_state = payment_entry_state(CLOSEOUT_PAYMENT_ENTRY)
    gated_state = payment_entry_state(GATED_PAYMENT_ENTRY)
    previous_gated_state = payment_entry_state(PREVIOUS_GATED_PAYMENT_ENTRY)
    closeout_gl_rows = payment_entry_gl_rows(CLOSEOUT_PAYMENT_ENTRY)
    closeout_gl_net = payment_entry_gl_net(CLOSEOUT_PAYMENT_ENTRY)
    closeout_direct_cancelled_gl_rows = payment_entry_cancelled_gl_rows(CLOSEOUT_PAYMENT_ENTRY)
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
        post_issues.append(f"Closeout must create 0 Payment Entries. Created {actual_pe_created}.")
    if actual_pe_cancelled != 0:
        post_issues.append(f"Closeout must cancel 0 Payment Entries. Cancelled {actual_pe_cancelled}.")
    if actual_gl_created != 0:
        post_issues.append(f"Closeout must create 0 GL rows. Created {actual_gl_created}.")
    if guard_after["submitted_journal_entry_count_today"] != 0:
        post_issues.append("Submitted Journal Entry today must remain 0 after closeout.")
    if guard_after["purchase_invoice_count_today"] != 0:
        post_issues.append("Purchase Invoice today must remain 0 after closeout.")
    if policy_mutation_count != 0:
        post_issues.append("Policy state changed during closeout. This is not allowed.")

    completed = int(
        not int(dry_run or 0)
        and ack_ok
        and freeze
        and not post_issues
        and closeout_state.docstatus == 2
        and closeout_state.status == "Cancelled"
        and gated_state.docstatus == 2
        and gated_state.status == "Cancelled"
        and previous_gated_state.docstatus == 2
        and previous_gated_state.status == "Cancelled"
        and closeout_gl_rows == EXPECTED_CLOSEOUT_GL_ROWS
        and closeout_gl_net == EXPECTED_CLOSEOUT_GL_NET
        and restored_amount == EXPECTED_RESTORED_INVOICE_AMOUNT
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
        "status": "Closed" if completed else "Needs Review",
        "closeout_status": "Next Governed Limited Operation Closed" if completed else "Needs Review",
        "closeout_completed": completed,
        "phase14f_freeze_verified": 1 if freeze else 0,
        "freeze_completed_verified": 1 if freeze else 0,
        "freeze_payment_entry_verified": int(freeze and freeze.freeze_payment_entry == CLOSEOUT_PAYMENT_ENTRY),
        "freeze_payment_entry_cancelled_verified": int(closeout_state.docstatus == 2 and closeout_state.status == "Cancelled"),
        "freeze_gl_rows_verified": int(closeout_gl_rows == EXPECTED_CLOSEOUT_GL_ROWS),
        "freeze_reversal_gl_rows_verified": int(freeze and int(freeze.freeze_reversal_gl_rows or 0) == EXPECTED_CLOSEOUT_REVERSAL_GL_ROWS),
        "freeze_gl_net_zero_verified": int(closeout_gl_net == EXPECTED_CLOSEOUT_GL_NET),
        "freeze_restored_invoice_amount_verified": int(restored_amount == EXPECTED_RESTORED_INVOICE_AMOUNT),
        "policy_state_preserved_verified": int(policy_mutation_count == 0 and policy_enabled_before == 1 and policy_enabled_after == 1 and policy_live_before == 0 and policy_live_after == 0),
        "no_new_accounting_movement_verified": int(actual_pe_created == 0 and actual_pe_cancelled == 0 and actual_gl_created == 0),
        "gated_payment_entry": GATED_PAYMENT_ENTRY,
        "gated_payment_entry_docstatus": gated_state.docstatus,
        "gated_payment_entry_status": gated_state.status,
        "previous_gated_payment_entry": PREVIOUS_GATED_PAYMENT_ENTRY,
        "previous_gated_payment_entry_docstatus": previous_gated_state.docstatus,
        "previous_gated_payment_entry_status": previous_gated_state.status,
        "closeout_payment_entry": CLOSEOUT_PAYMENT_ENTRY,
        "closeout_payment_entry_docstatus": closeout_state.docstatus,
        "closeout_payment_entry_status": closeout_state.status,
        "closeout_source_doctype": CLOSEOUT_SOURCE_DOCTYPE,
        "closeout_reference_doctype": CLOSEOUT_REFERENCE_DOCTYPE,
        "closeout_party_type": CLOSEOUT_PARTY_TYPE,
        "closeout_customer": unique_value(rows, "customer"),
        "closeout_company": unique_value(rows, "company"),
        "closeout_currency": unique_value(rows, "currency"),
        "closeout_invoice_names": ", ".join(reference_names(rows)),
        "closeout_invoice_count": len(rows),
        "closeout_total_amount": closeout_total(rows),
        "closeout_restored_invoice_amount": restored_amount,
        "closeout_gl_rows": closeout_gl_rows,
        "closeout_reversal_gl_rows": EXPECTED_CLOSEOUT_REVERSAL_GL_ROWS,
        "closeout_gl_net": closeout_gl_net,
        "closeout_direct_cancelled_gl_rows": closeout_direct_cancelled_gl_rows,
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
        "target_policy": freeze.target_policy if freeze else None,
        "target_policy_name": freeze.target_policy_name if freeze else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_before": policy_live_before,
        "target_policy_live_after": policy_live_after,
        "actual_policy_mutation_count": policy_mutation_count,
        CLOSEOUT_READY_FIELD: completed,
        "freeze": freeze.name if freeze else None,
        "rollback": freeze.rollback if freeze else None,
        "smoke": freeze.smoke if freeze else None,
        "execution_gate": freeze.execution_gate if freeze else None,
        "preview": freeze.preview if freeze else None,
        "candidate_validation": freeze.candidate_validation if freeze else None,
        "candidate_selection": freeze.candidate_selection if freeze else None,
        "design": freeze.design if freeze else None,
        "planning": freeze.planning if freeze else None,
        "monitor": freeze.monitor if freeze else None,
        "baseline": freeze.baseline if freeze else None,
        "previous_closeout": freeze.closeout if freeze else None,
        **item_summary,
        "items": items,
        "issues": post_issues,
        "required_acknowledgement": CLOSEOUT_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 14G closes the next governed limited-operation cycle. No accounting movement occurs.",
    }
    if int(dry_run or 0):
        return result

    doc = frappe.new_doc(CLOSEOUT_DOCTYPE)
    doc.closeout_id = make_closeout_id()
    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = CLOSEOUT_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.closeout_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    create_items(doc, items)
    frappe.db.commit()
    return {**result, "created": True, "closeout": doc.name, "closeout_id": doc.closeout_id, "closeout_payment_entry": CLOSEOUT_PAYMENT_ENTRY, "guardrails_after": guardrails()}


@frappe.whitelist()
def cancel_next_governed_limited_operation_closeout_phase14g_audit(closeout, reason=None):
    assert_action("cancel_next_governed_limited_operation_closeout_phase14g_audit")
    if not frappe.db.exists(CLOSEOUT_DOCTYPE, closeout):
        frappe.throw(_("Next governed limited-operation closeout audit not found: {0}").format(closeout))
    doc = frappe.get_doc(CLOSEOUT_DOCTYPE, closeout)
    if doc.status == "Cancelled":
        return {"closeout": closeout, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.closeout_completed or 0):
        frappe.throw(_("Cannot cancel a completed Phase 14G closeout record."))
    frappe.db.set_value(
        CLOSEOUT_DOCTYPE,
        closeout,
        {"status": "Cancelled", "closeout_status": "Cancelled", "cancelled_on": now_datetime(), "cancelled_by": frappe.session.user, "summary_json": reason or "Phase 14G no-ack closeout audit cancelled."},
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{CLOSEOUT_ITEM_DOCTYPE}` SET status='Cancelled' WHERE closeout=%(closeout)s", {"closeout": closeout})
    frappe.db.commit()
    return {"closeout": closeout, "status": "Cancelled", "note": "No-ack closeout audit cancelled only. No accounting movement occurred."}


@frappe.whitelist()
def quick_next_governed_limited_operation_closeout_phase14g_summary(limit=20):
    return {
        "closeout_records": frappe.get_all(
            CLOSEOUT_DOCTYPE,
            filters={"closeout_payment_entry": CLOSEOUT_PAYMENT_ENTRY},
            fields=[
                "name",
                "closeout_id",
                "status",
                "closeout_status",
                "closeout_completed",
                "phase14f_freeze_verified",
                "gated_payment_entry",
                "gated_payment_entry_docstatus",
                "gated_payment_entry_status",
                "previous_gated_payment_entry",
                "previous_gated_payment_entry_docstatus",
                "previous_gated_payment_entry_status",
                "closeout_payment_entry",
                "closeout_payment_entry_docstatus",
                "closeout_payment_entry_status",
                "closeout_invoice_names",
                "closeout_invoice_count",
                "closeout_total_amount",
                "closeout_restored_invoice_amount",
                "closeout_gl_rows",
                "closeout_reversal_gl_rows",
                "closeout_gl_net",
                "payment_entry_count_before",
                "payment_entry_count_after",
                "payment_entry_gl_count_before",
                "payment_entry_gl_count_after",
                "actual_payment_entry_created_count",
                "actual_payment_entry_cancelled_count",
                "actual_gl_created_count",
                "submitted_journal_entry_count_today",
                "purchase_invoice_count_today",
                CLOSEOUT_READY_FIELD,
                "checked_on",
                "checked_by",
            ],
            order_by="creation desc",
            limit=int(limit or 20),
        ),
        "items": frappe.get_all(
            CLOSEOUT_ITEM_DOCTYPE,
            fields=[
                "name",
                "closeout",
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
                "closeout_amount",
                "outstanding_amount",
                "closeout_payment_entry",
                "detail",
            ],
            order_by="creation desc",
            limit=int(limit or 20),
        ),
        "required_acknowledgement": CLOSEOUT_ACK,
        "guardrails": guardrails(),
        "note": "Phase 14G next governed limited-operation closeout summary.",
    }


def execute_closeout_report(filters=None):
    columns = [
        {"fieldname": "closeout", "label": _("Closeout"), "fieldtype": "Link", "options": CLOSEOUT_DOCTYPE, "width": 220},
        {"fieldname": "closeout_id", "label": _("Closeout ID"), "fieldtype": "Data", "width": 540},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "closeout_status", "label": _("Closeout Status"), "fieldtype": "Data", "width": 400},
        {"fieldname": "closeout_completed", "label": _("Completed"), "fieldtype": "Check", "width": 100},
        {"fieldname": "closeout_payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "gated_payment_entry", "label": _("Gated PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "previous_gated_payment_entry", "label": _("Previous Gated PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "closeout_payment_entry_docstatus", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 115},
        {"fieldname": "closeout_payment_entry_status", "label": _("PE Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "closeout_invoice_names", "label": _("Invoices"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "closeout_total_amount", "label": _("Amount"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "closeout_restored_invoice_amount", "label": _("Restored"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "closeout_gl_rows", "label": _("GL Rows"), "fieldtype": "Int", "width": 90},
        {"fieldname": "closeout_reversal_gl_rows", "label": _("Reversal Rows"), "fieldtype": "Int", "width": 120},
        {"fieldname": "closeout_gl_net", "label": _("GL Net"), "fieldtype": "Currency", "width": 100},
        {"fieldname": CLOSEOUT_READY_FIELD, "label": _("Baseline Ready"), "fieldtype": "Check", "width": 130},
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
            name AS closeout,
            closeout_id,
            status,
            closeout_status,
            closeout_completed,
            closeout_payment_entry,
            gated_payment_entry,
            previous_gated_payment_entry,
            closeout_payment_entry_docstatus,
            closeout_payment_entry_status,
            closeout_invoice_names,
            closeout_total_amount,
            closeout_restored_invoice_amount,
            closeout_gl_rows,
            closeout_reversal_gl_rows,
            closeout_gl_net,
            `{CLOSEOUT_READY_FIELD}` AS `{CLOSEOUT_READY_FIELD}`,
            payment_entry_count_before,
            payment_entry_count_after,
            payment_entry_gl_count_before,
            payment_entry_gl_count_after,
            actual_gl_created_count,
            checked_on
        FROM `tab{CLOSEOUT_DOCTYPE}`
        WHERE closeout_payment_entry=%(payment_entry)s
        ORDER BY creation DESC
        """,
        {"payment_entry": CLOSEOUT_PAYMENT_ENTRY},
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.closeout_id for row in data[:20]],
            "datasets": [
                {"name": "Closeout Completed", "values": [int(row.closeout_completed or 0) for row in data[:20]]},
                {"name": "Baseline Ready", "values": [int(row.get(CLOSEOUT_READY_FIELD) or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Closeout Records"), "datatype": "Int"},
        {"value": sum(int(row.closeout_completed or 0) for row in data), "indicator": "Green", "label": _("Closed"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL Created"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_item_report(filters=None):
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": CLOSEOUT_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "closeout", "label": _("Closeout"), "fieldtype": "Link", "options": CLOSEOUT_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 190},
        {"fieldname": "line_no", "label": _("Line"), "fieldtype": "Int", "width": 60},
        {"fieldname": "reference_doctype", "label": _("Ref DocType"), "fieldtype": "Data", "width": 130},
        {"fieldname": "reference_name", "label": _("Reference"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 180},
        {"fieldname": "closeout_amount", "label": _("Closeout Amount"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "outstanding_amount", "label": _("Outstanding"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "closeout_payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 650},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            name AS item,
            closeout,
            status,
            category,
            line_no,
            reference_doctype,
            reference_name,
            closeout_amount,
            outstanding_amount,
            closeout_payment_entry,
            detail
        FROM `tab{CLOSEOUT_ITEM_DOCTYPE}`
        ORDER BY creation DESC
        """,
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
        {"value": len([row for row in data if row.category == "Closeout Reference"]), "indicator": "Green", "label": _("Closeout References"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_closeout_report(filters)
    guard = guardrails()
    summary.append({"value": guard["payment_entry_count"], "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"})
    summary.append({"value": guard["payment_entry_gl_count"], "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"})
    summary.append({"value": guard["submitted_journal_entry_count_today"], "indicator": "Red", "label": _("Submitted JE Today"), "datatype": "Int"})
    summary.append({"value": guard["purchase_invoice_count_today"], "indicator": "Red", "label": _("Purchase Invoice Today"), "datatype": "Int"})
    summary.append({"value": guard["production_batch_enabled_policy_count"], "indicator": "Green", "label": _("Enabled Policies"), "datatype": "Int"})
    summary.append({"value": guard["live_posting_allowed_policy_count"], "indicator": "Red", "label": _("Live Policies"), "datatype": "Int"})
    return columns, data, message, chart, summary
