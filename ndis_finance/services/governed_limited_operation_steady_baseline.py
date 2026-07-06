import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, today

from ndis_finance.services.permissions import assert_action


BASELINE_ACK = "I_CONFIRM_PHASE12L_ACTIVATE_GOVERNED_LIMITED_OPERATION_STEADY_STATE_BASELINE_NO_POSTING"

POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
CLOSEOUT_DOCTYPE = "NDIS Next Governed Limited Op Closeout"
CLOSEOUT_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Closeout Item"
BASELINE_DOCTYPE = "NDIS Next Governed Limited Op Steady Baseline"
BASELINE_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Steady Baseline Item"

EXPECTED_PAYMENT_ENTRY = "ACC-PAY-2026-00012"
EXPECTED_INVOICES = ["ACC-SINV-2026-00005", "ACC-SINV-2026-00006", "ACC-SINV-2026-00008"]

EXPECTED_PAYMENT_ENTRY_COUNT = 11
EXPECTED_PAYMENT_ENTRY_GL_COUNT = 70
EXPECTED_TOTAL_AMOUNT = 3.00
EXPECTED_INVOICE_COUNT = 3
EXPECTED_VOUCHER_GL_ROWS = 8
EXPECTED_VOUCHER_GL_NET = 0.00
EXPECTED_REVERSAL_GL_ROWS = 4


def make_baseline_id():
    timestamp = now_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-NEXT-GOVERNED-LIMITED-OP-STEADY-BASELINE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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
            "closeout_status": "Governed Limited Operation Smoke Closed",
            "closeout_approved": 1,
            "phase12j_freeze_verified": 1,
            "freeze_completed_verified": 1,
            "rollback_evidence_frozen_verified": 1,
            "frozen_payment_entry_verified": 1,
            "payment_entry_cancelled_still_verified": 1,
            "voucher_gl_rows_verified": 1,
            "voucher_gl_net_zero_verified": 1,
            "reversal_gl_rows_verified": 1,
            "restored_invoice_amount_verified": 1,
            "payment_entry_count_stable_verified": 1,
            "payment_entry_gl_count_stable_verified": 1,
            "policy_state_preserved_verified": 1,
            "no_new_accounting_movement_verified": 1,
            "cycle_closed": 1,
            "steady_state_ready": 1,
            "ready_for_governed_limited_operation_steady_state_baseline": 1,
            "closed_payment_entry": EXPECTED_PAYMENT_ENTRY,
            "closed_payment_entry_docstatus": 2,
            "closed_payment_entry_status": "Cancelled",
            "closed_invoice_count": EXPECTED_INVOICE_COUNT,
            "closed_total_amount": EXPECTED_TOTAL_AMOUNT,
            "closed_voucher_gl_rows": EXPECTED_VOUCHER_GL_ROWS,
            "closed_voucher_gl_net": 0,
            "closed_reversal_gl_rows": EXPECTED_REVERSAL_GL_ROWS,
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
            "cycle_closed",
            "steady_state_ready",
            "closed_payment_entry",
            "closed_payment_entry_docstatus",
            "closed_payment_entry_status",
            "closed_invoice_names",
            "closed_invoice_count",
            "closed_total_amount",
            "closed_voucher_gl_rows",
            "closed_voucher_gl_net",
            "closed_reversal_gl_rows",
            "closed_restored_invoice_amount",
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
            "customer",
            "company",
            "currency",
            "closeout_amount",
            "current_outstanding_amount",
            "closeout_payment_entry",
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
                    "baseline_amount": flt(row.closeout_amount or 0, 2),
                    "current_outstanding_amount": flt((si.outstanding_amount if si else 0) or 0, 2),
                    "customer": si.customer if si else row.customer,
                    "company": si.company if si else row.company,
                    "currency": si.currency if si else row.currency,
                    "docstatus": int(si.docstatus or 0) if si else None,
                    "closeout_payment_entry": row.closeout_payment_entry,
                }
            )
        )

    return result


def reference_names(rows):
    return [row.reference_name for row in rows]


def baseline_total(rows):
    return flt(sum(flt(row.baseline_amount or 0, 2) for row in rows), 2)


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


def reversal_gl_rows(payment_entry):
    rows = voucher_gl_rows(payment_entry)
    return max(0, int(rows or 0) - 4)


def validate_source(closeout, rows, guard, config, policy_enabled, policy_live):
    issues = []

    if not closeout:
        issues.append("No approved Phase 12K governed limited-operation closeout found.")
        return issues

    existing = existing_active_baseline(closeout.name)
    if existing:
        issues.append(f"Active Phase 12L baseline already exists for this closeout: {existing.baseline_id} / {existing.baseline_payment_entry}")

    payment_entry = closeout.closed_payment_entry

    if payment_entry != EXPECTED_PAYMENT_ENTRY:
        issues.append(f"Expected closed Payment Entry {EXPECTED_PAYMENT_ENTRY}. Found {payment_entry}.")

    if not frappe.db.exists("Payment Entry", payment_entry):
        issues.append(f"Closed Payment Entry does not exist: {payment_entry}")
        return issues

    pe = frappe.get_doc("Payment Entry", payment_entry)

    if pe.docstatus != 2:
        issues.append(f"Closed Payment Entry must remain cancelled. docstatus={pe.docstatus}")

    if pe.status != "Cancelled":
        issues.append(f"Closed Payment Entry status must remain Cancelled. status={pe.status}")

    if reference_names(rows) != EXPECTED_INVOICES:
        issues.append(f"Baseline invoice set changed. Expected {EXPECTED_INVOICES}. Found {reference_names(rows)}.")

    if len(rows) != EXPECTED_INVOICE_COUNT:
        issues.append(f"Baseline invoice count must be {EXPECTED_INVOICE_COUNT}. Found {len(rows)}.")

    if baseline_total(rows) != EXPECTED_TOTAL_AMOUNT:
        issues.append(f"Baseline total amount must be {EXPECTED_TOTAL_AMOUNT}. Found {baseline_total(rows)}.")

    if voucher_gl_rows(payment_entry) != EXPECTED_VOUCHER_GL_ROWS:
        issues.append(f"Voucher GL rows must remain {EXPECTED_VOUCHER_GL_ROWS}. Found {voucher_gl_rows(payment_entry)}.")

    if voucher_gl_net(payment_entry) != EXPECTED_VOUCHER_GL_NET:
        issues.append(f"Voucher GL net must remain 0.00. Found {voucher_gl_net(payment_entry)}.")

    if reversal_gl_rows(payment_entry) != EXPECTED_REVERSAL_GL_ROWS:
        issues.append(f"Reversal GL rows must remain {EXPECTED_REVERSAL_GL_ROWS}. Found {reversal_gl_rows(payment_entry)}.")

    restored = outstanding_total(EXPECTED_INVOICES)
    if restored != EXPECTED_TOTAL_AMOUNT:
        issues.append(f"Restored invoice amount must remain {EXPECTED_TOTAL_AMOUNT}. Found {restored}.")

    if guard["payment_entry_count"] != EXPECTED_PAYMENT_ENTRY_COUNT:
        issues.append("Payment Entry count must remain 11 before baseline.")

    if guard["payment_entry_gl_count"] != EXPECTED_PAYMENT_ENTRY_GL_COUNT:
        issues.append("Payment Entry GL count must remain 70 before baseline.")

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


def build_items(rows, issues, ack_ok, payment_entry=None):
    items = []

    if not issues:
        items.append({
            "status": "Pass",
            "severity": "Critical",
            "category": "Baseline Source",
            "check_key": "baseline_source_valid",
            "check_label": "Baseline source valid",
            "detail": "The Phase 12K closeout is stable and can be activated as the governed limited-operation steady-state baseline.",
            "baseline_payment_entry": payment_entry,
        })
    else:
        for issue in issues:
            items.append({
                "status": "Blocker",
                "severity": "Critical",
                "category": "Baseline Source",
                "check_key": "baseline_source_valid",
                "check_label": "Baseline source valid",
                "detail": issue,
                "baseline_payment_entry": payment_entry,
            })

    for row in rows:
        items.append({
            "status": "Pass",
            "severity": "High",
            "category": "Baseline Reference",
            "check_key": "baseline_sales_invoice_reference",
            "check_label": f"Baseline Sales Invoice {row.idx}",
            "detail": f"{row.reference_name} baseline amount={row.baseline_amount}, outstanding={row.current_outstanding_amount}.",
            "line_no": row.idx,
            "reference_doctype": row.reference_doctype,
            "reference_name": row.reference_name,
            "customer": row.customer,
            "company": row.company,
            "currency": row.currency,
            "baseline_amount": row.baseline_amount,
            "current_outstanding_amount": row.current_outstanding_amount,
            "baseline_payment_entry": payment_entry,
        })

    checks = [
        ("payment_entry_cancelled", "Payment Entry remains Cancelled", payment_entry or "None"),
        ("payment_entry_count_stable", "Payment Entry count stable", EXPECTED_PAYMENT_ENTRY_COUNT),
        ("payment_entry_gl_count_stable", "Payment Entry GL count stable", EXPECTED_PAYMENT_ENTRY_GL_COUNT),
        ("voucher_gl_rows", "Voucher GL rows baselined", EXPECTED_VOUCHER_GL_ROWS),
        ("reversal_gl_rows", "Reversal GL rows baselined", EXPECTED_REVERSAL_GL_ROWS),
        ("voucher_gl_net", "Voucher GL net baselined", 0),
        ("restored_invoice_amount", "Restored invoice amount baselined", EXPECTED_TOTAL_AMOUNT),
        ("baseline_active", "Baseline active", 1),
        ("runtime_monitor_ready", "Ready for governed limited-operation runtime monitor", 1),
    ]

    for key, label, value in checks:
        items.append({
            "status": "Pass",
            "severity": "High",
            "category": "Baseline Evidence",
            "check_key": key,
            "check_label": label,
            "detail": f"value={value}",
            "baseline_payment_entry": payment_entry,
        })

    items.append({
        "status": "Pass" if ack_ok else "Warning",
        "severity": "Low" if ack_ok else "Medium",
        "category": "Acknowledgement",
        "check_key": "ack_ok",
        "check_label": "Acknowledgement supplied",
        "detail": "Exact acknowledgement supplied." if ack_ok else f"Required acknowledgement not supplied: {BASELINE_ACK}",
        "baseline_payment_entry": payment_entry,
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
        row = frappe.new_doc(BASELINE_ITEM_DOCTYPE)
        row.baseline = doc.name
        for fieldname, value in item.items():
            if row.meta.has_field(fieldname):
                setattr(row, fieldname, value)
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_governed_limited_operation_steady_baseline(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_governed_limited_operation_steady_baseline")

    closeout = latest_closeout()
    rows = closeout_rows(closeout.name) if closeout else []
    payment_entry = closeout.closed_payment_entry if closeout else None

    guard_before = guardrails()
    ack_ok = acknowledgement == BASELINE_ACK

    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }

    policy_enabled_before = get_flag(POLICY_DOCTYPE, closeout.target_policy, "production_batch_enabled") if closeout else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, closeout.target_policy, "live_posting_allowed") if closeout else 0

    source_issues = validate_source(closeout, rows, guard_before, config, policy_enabled_before, policy_live_before)

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
    voucher_rows = 0
    voucher_net = 0
    reversal_rows = 0
    restored_amount = outstanding_total(EXPECTED_INVOICES)

    if payment_entry and frappe.db.exists("Payment Entry", payment_entry):
        pe = frappe.get_doc("Payment Entry", payment_entry)
        pe_docstatus = int(pe.docstatus or 0)
        pe_status = pe.status
        voucher_rows = voucher_gl_rows(payment_entry)
        voucher_net = voucher_gl_net(payment_entry)
        reversal_rows = reversal_gl_rows(payment_entry)

    post_issues = list(source_issues)

    if actual_pe_created != 0:
        post_issues.append(f"Baseline must create 0 Payment Entries. Created {actual_pe_created}.")
    if actual_pe_cancelled != 0:
        post_issues.append(f"Baseline must cancel 0 Payment Entries. Cancelled {actual_pe_cancelled}.")
    if actual_gl_created != 0:
        post_issues.append(f"Baseline must create 0 GL rows. Created {actual_gl_created}.")
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
        and reference_names(rows) == EXPECTED_INVOICES
        and baseline_total(rows) == EXPECTED_TOTAL_AMOUNT
        and voucher_rows == EXPECTED_VOUCHER_GL_ROWS
        and voucher_net == 0
        and reversal_rows == EXPECTED_REVERSAL_GL_ROWS
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

    items = build_items(rows, post_issues, ack_ok, payment_entry=payment_entry)
    item_summary = summarise_items(items)

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Baseline Active" if completed else "Needs Review",
        "baseline_status": "Governed Limited Operation Steady-State Baseline Active" if completed else "Needs Review",
        "baseline_active": completed,

        "phase12k_closeout_verified": 1 if closeout else 0,
        "closeout_approved_verified": 1 if closeout else 0,
        "cycle_closed_verified": int(closeout and int(closeout.cycle_closed or 0) == 1),
        "steady_state_ready_verified": int(closeout and int(closeout.steady_state_ready or 0) == 1),
        "closed_payment_entry_verified": int(payment_entry == EXPECTED_PAYMENT_ENTRY),
        "payment_entry_cancelled_still_verified": int(pe_docstatus == 2 and pe_status == "Cancelled"),
        "voucher_gl_rows_verified": int(voucher_rows == EXPECTED_VOUCHER_GL_ROWS),
        "voucher_gl_net_zero_verified": int(voucher_net == 0),
        "reversal_gl_rows_verified": int(reversal_rows == EXPECTED_REVERSAL_GL_ROWS),
        "restored_invoice_amount_verified": int(restored_amount == EXPECTED_TOTAL_AMOUNT),
        "payment_entry_count_stable_verified": int(guard_before["payment_entry_count"] == EXPECTED_PAYMENT_ENTRY_COUNT and guard_after["payment_entry_count"] == EXPECTED_PAYMENT_ENTRY_COUNT),
        "payment_entry_gl_count_stable_verified": int(guard_before["payment_entry_gl_count"] == EXPECTED_PAYMENT_ENTRY_GL_COUNT and guard_after["payment_entry_gl_count"] == EXPECTED_PAYMENT_ENTRY_GL_COUNT),
        "policy_state_preserved_verified": int(policy_mutation_count == 0 and policy_enabled_before == 1 and policy_enabled_after == 1 and policy_live_before == 0 and policy_live_after == 0),
        "no_new_accounting_movement_verified": int(actual_pe_created == 0 and actual_pe_cancelled == 0 and actual_gl_created == 0),
        "ready_for_governed_limited_operation_runtime_monitor": completed,

        "baseline_payment_entry": payment_entry,
        "baseline_payment_entry_docstatus": pe_docstatus,
        "baseline_payment_entry_status": pe_status,
        "baseline_invoice_names": ", ".join(reference_names(rows)),
        "baseline_invoice_count": len(rows),
        "baseline_total_amount": baseline_total(rows),
        "baseline_voucher_gl_rows": voucher_rows,
        "baseline_voucher_gl_net": voucher_net,
        "baseline_reversal_gl_rows": reversal_rows,
        "baseline_restored_invoice_amount": restored_amount,

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
        "target_policy": closeout.target_policy if closeout else None,
        "target_policy_name": closeout.target_policy_name if closeout else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_before": policy_live_before,
        "target_policy_live_after": policy_live_after,
        "actual_policy_mutation_count": policy_mutation_count,

        "closeout": closeout.name if closeout else None,
        "freeze": closeout.freeze if closeout else None,
        "rollback": closeout.rollback if closeout else None,
        "smoke": closeout.smoke if closeout else None,
        "execution_gate": closeout.execution_gate if closeout else None,
        "preview": closeout.preview if closeout else None,
        "candidate_validation": closeout.candidate_validation if closeout else None,
        "candidate_selection": closeout.candidate_selection if closeout else None,
        "design": closeout.design if closeout else None,
        "planning": closeout.planning if closeout else None,
        "monitor": closeout.monitor if closeout else None,
        "previous_baseline": closeout.baseline if closeout else None,

        **item_summary,
        "items": items,
        "issues": post_issues,
        "required_acknowledgement": BASELINE_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 12L activates the governed limited-operation steady-state baseline only. No accounting movement occurs.",
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
    doc.baseline_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    create_items(doc, items)
    frappe.db.commit()

    return {
        **result,
        "created": True,
        "baseline": doc.name,
        "baseline_id": doc.baseline_id,
        "baseline_payment_entry": payment_entry,
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_governed_limited_operation_steady_baseline_audit(baseline, reason=None):
    assert_action("cancel_governed_limited_operation_steady_baseline_audit")

    if not frappe.db.exists(BASELINE_DOCTYPE, baseline):
        frappe.throw(_("Governed limited-operation steady baseline audit not found: {0}").format(baseline))

    doc = frappe.get_doc(BASELINE_DOCTYPE, baseline)

    if doc.status == "Cancelled":
        return {"baseline": baseline, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.baseline_active or 0):
        frappe.throw(_("Cannot cancel an active Phase 12L baseline record."))

    frappe.db.set_value(
        BASELINE_DOCTYPE,
        baseline,
        {
            "status": "Cancelled",
            "baseline_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 12L no-ack baseline audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        f"""
        UPDATE `tab{BASELINE_ITEM_DOCTYPE}`
        SET status='Cancelled'
        WHERE baseline=%(baseline)s
        """,
        {"baseline": baseline},
    )

    frappe.db.commit()

    return {
        "baseline": baseline,
        "status": "Cancelled",
        "note": "No-ack baseline audit cancelled only. No accounting movement occurred.",
    }


@frappe.whitelist()
def quick_governed_limited_operation_steady_baseline_summary(limit=20):
    return {
        "baseline_records": frappe.get_all(
            BASELINE_DOCTYPE,
            fields=[
                "name",
                "baseline_id",
                "status",
                "baseline_status",
                "baseline_active",
                "baseline_payment_entry",
                "baseline_payment_entry_docstatus",
                "baseline_payment_entry_status",
                "baseline_invoice_names",
                "baseline_invoice_count",
                "baseline_total_amount",
                "baseline_voucher_gl_rows",
                "baseline_voucher_gl_net",
                "baseline_reversal_gl_rows",
                "baseline_restored_invoice_amount",
                "ready_for_governed_limited_operation_runtime_monitor",
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
                "customer",
                "company",
                "currency",
                "baseline_amount",
                "current_outstanding_amount",
                "baseline_payment_entry",
                "detail",
            ],
            order_by="creation desc",
            limit=int(limit or 20),
        ),
        "required_acknowledgement": BASELINE_ACK,
        "guardrails": guardrails(),
        "note": "Phase 12L governed limited-operation steady-state baseline summary.",
    }


def execute_baseline_report(filters=None):
    columns = [
        {"fieldname": "baseline", "label": _("Baseline"), "fieldtype": "Link", "options": BASELINE_DOCTYPE, "width": 220},
        {"fieldname": "baseline_id", "label": _("Baseline ID"), "fieldtype": "Data", "width": 480},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 150},
        {"fieldname": "baseline_status", "label": _("Baseline Status"), "fieldtype": "Data", "width": 360},
        {"fieldname": "baseline_active", "label": _("Active"), "fieldtype": "Check", "width": 80},
        {"fieldname": "baseline_payment_entry", "label": _("Baseline PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "baseline_payment_entry_docstatus", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 105},
        {"fieldname": "baseline_payment_entry_status", "label": _("PE Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "baseline_invoice_names", "label": _("Invoices"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "baseline_invoice_count", "label": _("Invoice Count"), "fieldtype": "Int", "width": 100},
        {"fieldname": "baseline_total_amount", "label": _("Amount"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "baseline_voucher_gl_rows", "label": _("Voucher GL Rows"), "fieldtype": "Int", "width": 125},
        {"fieldname": "baseline_voucher_gl_net", "label": _("Voucher GL Net"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "baseline_reversal_gl_rows", "label": _("Reversal GL Rows"), "fieldtype": "Int", "width": 130},
        {"fieldname": "baseline_restored_invoice_amount", "label": _("Restored Amount"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "ready_for_governed_limited_operation_runtime_monitor", "label": _("Runtime Monitor Ready"), "fieldtype": "Check", "width": 150},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 115},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 115},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL Created"), "fieldtype": "Int", "width": 130},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            name AS baseline,
            baseline_id,
            status,
            baseline_status,
            baseline_active,
            baseline_payment_entry,
            baseline_payment_entry_docstatus,
            baseline_payment_entry_status,
            baseline_invoice_names,
            baseline_invoice_count,
            baseline_total_amount,
            baseline_voucher_gl_rows,
            baseline_voucher_gl_net,
            baseline_reversal_gl_rows,
            baseline_restored_invoice_amount,
            ready_for_governed_limited_operation_runtime_monitor,
            payment_entry_count_before,
            payment_entry_count_after,
            payment_entry_gl_count_before,
            payment_entry_gl_count_after,
            actual_gl_created_count,
            checked_on
        FROM `tab{BASELINE_DOCTYPE}`
        ORDER BY creation DESC
        """,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.baseline_id for row in data[:20]],
            "datasets": [
                {"name": "Baseline Active", "values": [int(row.baseline_active or 0) for row in data[:20]]},
                {"name": "Runtime Monitor Ready", "values": [int(row.ready_for_governed_limited_operation_runtime_monitor or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Baseline Records"), "datatype": "Int"},
        {"value": sum(int(row.baseline_active or 0) for row in data), "indicator": "Green", "label": _("Active"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL Created"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_item_report(filters=None):
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": BASELINE_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "baseline", "label": _("Baseline"), "fieldtype": "Link", "options": BASELINE_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 180},
        {"fieldname": "line_no", "label": _("Line"), "fieldtype": "Int", "width": 60},
        {"fieldname": "reference_doctype", "label": _("Ref DocType"), "fieldtype": "Data", "width": 130},
        {"fieldname": "reference_name", "label": _("Reference"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 180},
        {"fieldname": "baseline_amount", "label": _("Baseline Amount"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "current_outstanding_amount", "label": _("Outstanding"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "baseline_payment_entry", "label": _("Baseline PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 300},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 650},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            name AS item,
            baseline,
            status,
            category,
            line_no,
            reference_doctype,
            reference_name,
            baseline_amount,
            current_outstanding_amount,
            baseline_payment_entry,
            check_label,
            detail
        FROM `tab{BASELINE_ITEM_DOCTYPE}`
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
        {"value": len([row for row in data if row.category == "Baseline Reference"]), "indicator": "Green", "label": _("Baseline References"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_baseline_report(filters)
    guard = guardrails()
    summary.append({"value": guard["payment_entry_count"], "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"})
    summary.append({"value": guard["payment_entry_gl_count"], "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"})
    summary.append({"value": guard["submitted_journal_entry_count_today"], "indicator": "Red", "label": _("Submitted JE Today"), "datatype": "Int"})
    summary.append({"value": guard["purchase_invoice_count_today"], "indicator": "Red", "label": _("Purchase Invoice Today"), "datatype": "Int"})
    summary.append({"value": guard["production_batch_enabled_policy_count"], "indicator": "Green", "label": _("Enabled Policies"), "datatype": "Int"})
    summary.append({"value": guard["live_posting_allowed_policy_count"], "indicator": "Red", "label": _("Live Policies"), "datatype": "Int"})
    return columns, data, message, chart, summary
