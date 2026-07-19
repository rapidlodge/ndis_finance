import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, today

from ndis_finance.services.permissions import assert_action


PLANNING_ACK = "I_CONFIRM_PHASE13X_APPROVE_NEXT_GOVERNED_LIMITED_OPERATION_PLANNING_NO_POSTING"

POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
MONITOR_DOCTYPE = "NDIS Next Governed Limited Op Runtime Monitor"
MONITOR_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Runtime Monitor Item"
PLANNING_DOCTYPE = "NDIS Next Governed Limited Op Planning"
PLANNING_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Planning Item"

MONITOR_READY_FIELD = "ready_for_next_governed_limited_op_planning"
PLANNING_READY_FIELD = "ready_for_next_governed_limited_op_design"

GATED_PAYMENT_ENTRY = "ACC-PAY-2026-00014"
PLANNING_PAYMENT_ENTRY = "ACC-PAY-2026-00015"
EXPECTED_INVOICES = ["ACC-SINV-2026-00005", "ACC-SINV-2026-00006", "ACC-SINV-2026-00008"]
EXPECTED_PAYMENT_ENTRY_COUNT = 14
EXPECTED_PAYMENT_ENTRY_GL_COUNT = 94
EXPECTED_TOTAL_AMOUNT = 3.00
EXPECTED_INVOICE_COUNT = 3
EXPECTED_GL_ROWS = 8
EXPECTED_REVERSAL_GL_ROWS = 4
EXPECTED_GL_NET = 0.00

PLANNING_SOURCE_DOCTYPE = "Sales Invoice"
PLANNING_REFERENCE_DOCTYPE = "Sales Invoice"
PLANNING_PARTY_TYPE = "Customer"


def make_planning_id():
    timestamp = now_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-NEXT-GOVERNED-LIMITED-OP-PLANNING-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_runtime_monitor():
    filters = {
        "status": "Runtime Monitor Active",
        "monitor_status": "Next Governed Limited Operation Runtime Monitor Active",
        "monitor_active": 1,
        "phase13v_baseline_verified": 1,
        "baseline_active_verified": 1,
        "baseline_payment_entry_verified": 1,
        "baseline_payment_entry_cancelled_verified": 1,
        "baseline_gl_rows_verified": 1,
        "baseline_reversal_gl_rows_verified": 1,
        "baseline_gl_net_zero_verified": 1,
        "baseline_restored_invoice_amount_verified": 1,
        "policy_state_preserved_verified": 1,
        "no_new_accounting_movement_verified": 1,
        "gated_payment_entry": GATED_PAYMENT_ENTRY,
        "gated_payment_entry_docstatus": 2,
        "gated_payment_entry_status": "Cancelled",
        "monitor_payment_entry": PLANNING_PAYMENT_ENTRY,
        "monitor_payment_entry_docstatus": 2,
        "monitor_payment_entry_status": "Cancelled",
        "monitor_source_doctype": PLANNING_SOURCE_DOCTYPE,
        "monitor_reference_doctype": PLANNING_REFERENCE_DOCTYPE,
        "monitor_party_type": PLANNING_PARTY_TYPE,
        "monitor_invoice_count": EXPECTED_INVOICE_COUNT,
        "monitor_total_amount": EXPECTED_TOTAL_AMOUNT,
        "monitor_restored_invoice_amount": EXPECTED_TOTAL_AMOUNT,
        "monitor_gl_rows": EXPECTED_GL_ROWS,
        "monitor_reversal_gl_rows": EXPECTED_REVERSAL_GL_ROWS,
        "monitor_gl_net": EXPECTED_GL_NET,
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
    if has_column(MONITOR_DOCTYPE, MONITOR_READY_FIELD):
        filters[MONITOR_READY_FIELD] = 1

    rows = frappe.get_all(
        MONITOR_DOCTYPE,
        filters=filters,
        fields=[
            "name",
            "monitor_id",
            "monitor_source_doctype",
            "monitor_reference_doctype",
            "monitor_party_type",
            "monitor_customer",
            "monitor_company",
            "monitor_currency",
            "monitor_invoice_names",
            "monitor_invoice_count",
            "monitor_total_amount",
            "monitor_restored_invoice_amount",
            "gated_payment_entry",
            "gated_payment_entry_docstatus",
            "gated_payment_entry_status",
            "monitor_payment_entry",
            "monitor_payment_entry_docstatus",
            "monitor_payment_entry_status",
            "monitor_gl_rows",
            "monitor_reversal_gl_rows",
            "monitor_gl_net",
            "baseline",
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
            "target_policy",
            "target_policy_name",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_approved_planning(monitor):
    rows = frappe.get_all(
        PLANNING_DOCTYPE,
        filters={"monitor": monitor, "status": "Planning Approved", "planning_approved": 1},
        fields=["name", "planning_id", "planning_payment_entry"],
        limit=1,
    )
    return rows[0] if rows else None


def monitor_rows(monitor):
    rows = frappe.get_all(
        MONITOR_ITEM_DOCTYPE,
        filters={"monitor": monitor, "category": "Monitor Reference", "status": "Pass", "reference_doctype": "Sales Invoice"},
        fields=["line_no", "reference_doctype", "reference_name", "customer", "company", "currency", "monitor_amount", "outstanding_amount", "monitor_payment_entry"],
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
                    "planning_amount": flt(row.monitor_amount or 0, 2),
                    "outstanding_amount": flt((si.outstanding_amount if si else row.outstanding_amount) or 0, 2),
                    "customer": si.customer if si else row.customer,
                    "company": si.company if si else row.company,
                    "currency": si.currency if si else row.currency,
                    "invoice_docstatus": int(si.docstatus or 0) if si else 0,
                    "planning_payment_entry": PLANNING_PAYMENT_ENTRY,
                    "gated_payment_entry": GATED_PAYMENT_ENTRY,
                }
            )
        )
    return result


def reference_names(rows):
    return [row.reference_name for row in rows]


def planning_total(rows):
    return flt(sum(flt(row.planning_amount or 0, 2) for row in rows), 2)


def unique_value(rows, fieldname):
    values = sorted(set(getattr(row, fieldname, None) for row in rows if getattr(row, fieldname, None)))
    return values[0] if len(values) == 1 else None


def validate_source(monitor, rows, guard, config, policy_enabled, policy_live):
    issues = []
    if not monitor:
        issues.append("No active Phase 13W runtime monitor found for Phase 13X planning.")
        return issues

    existing = existing_approved_planning(monitor.name)
    if existing:
        issues.append(f"Approved Phase 13X planning already exists for this runtime monitor: {existing.planning_id} / {existing.planning_payment_entry}")

    gated_state = payment_entry_state(GATED_PAYMENT_ENTRY)
    state = payment_entry_state(PLANNING_PAYMENT_ENTRY)
    if not frappe.db.exists("Payment Entry", GATED_PAYMENT_ENTRY):
        issues.append(f"Gated Payment Entry does not exist: {GATED_PAYMENT_ENTRY}")
    if gated_state.docstatus != 2 or gated_state.status != "Cancelled":
        issues.append(f"Gated Payment Entry must remain Cancelled / 2. Found {gated_state.status} / {gated_state.docstatus}")
    if not frappe.db.exists("Payment Entry", PLANNING_PAYMENT_ENTRY):
        issues.append(f"Planning Payment Entry does not exist: {PLANNING_PAYMENT_ENTRY}")
    if state.docstatus != 2 or state.status != "Cancelled":
        issues.append(f"Planning Payment Entry must remain Cancelled / 2. Found {state.status} / {state.docstatus}")
    if reference_names(rows) != EXPECTED_INVOICES:
        issues.append(f"Planning invoice set changed. Expected {EXPECTED_INVOICES}. Found {reference_names(rows)}.")
    if len(rows) != EXPECTED_INVOICE_COUNT:
        issues.append(f"Planning invoice count must be {EXPECTED_INVOICE_COUNT}. Found {len(rows)}.")
    if planning_total(rows) != EXPECTED_TOTAL_AMOUNT:
        issues.append(f"Planning total amount must be {EXPECTED_TOTAL_AMOUNT}. Found {planning_total(rows)}.")
    if outstanding_total(EXPECTED_INVOICES) != EXPECTED_TOTAL_AMOUNT:
        issues.append(f"Restored invoice outstanding must be {EXPECTED_TOTAL_AMOUNT} before planning.")
    if payment_entry_gl_rows(PLANNING_PAYMENT_ENTRY) != EXPECTED_GL_ROWS:
        issues.append(f"Planning Payment Entry must have {EXPECTED_GL_ROWS} GL rows.")
    if payment_entry_gl_net(PLANNING_PAYMENT_ENTRY) != EXPECTED_GL_NET:
        issues.append("Planning Payment Entry GL net must be 0.00.")
    if int(monitor.monitor_reversal_gl_rows or 0) != EXPECTED_REVERSAL_GL_ROWS:
        issues.append("Governed runtime monitor reversal rows must remain the four-row delta.")
    if guard["payment_entry_count"] != EXPECTED_PAYMENT_ENTRY_COUNT:
        issues.append("Payment Entry count must remain 14 before planning.")
    if guard["payment_entry_gl_count"] != EXPECTED_PAYMENT_ENTRY_GL_COUNT:
        issues.append("Payment Entry GL count must remain 94 before planning.")
    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today must remain 0 before planning.")
    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today must remain 0 before planning.")
    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must remain enabled before planning.")
    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must remain 0 before planning.")
    if policy_enabled != 1:
        issues.append("Target policy production_batch_enabled must remain 1.")
    if policy_live != 0:
        issues.append("Target policy live_posting_allowed must remain 0.")
    if config["sandbox_enabled"] != 1:
        issues.append("Sandbox config must be enabled for planning.")
    if config["production_mode"] != 0:
        issues.append("Production mode config must remain 0 for planning.")
    if config["live_pe_enabled"] != 0:
        issues.append("Live Payment Entry posting config must remain 0 for planning.")
    return issues


def build_items(rows, issues, ack_ok):
    items = []
    if not issues:
        items.append({"status": "Pass", "severity": "Critical", "category": "Planning Source", "check_key": "planning_source_valid", "check_label": "Planning source valid", "detail": f"Runtime monitor evidence for {PLANNING_PAYMENT_ENTRY} is stable and ready for planning approval.", "gated_payment_entry": GATED_PAYMENT_ENTRY, "planning_payment_entry": PLANNING_PAYMENT_ENTRY})
    else:
        for issue in issues:
            items.append({"status": "Blocker", "severity": "Critical", "category": "Planning Source", "check_key": "planning_source_valid", "check_label": "Planning source valid", "detail": issue, "gated_payment_entry": GATED_PAYMENT_ENTRY, "planning_payment_entry": PLANNING_PAYMENT_ENTRY})

    for row in rows:
        items.append(
            {
                "status": "Pass",
                "severity": "High",
                "category": "Planning Reference",
                "check_key": "planning_sales_invoice_reference",
                "check_label": f"Planning Sales Invoice {row.idx}",
                "detail": f"{row.reference_name} planning amount={row.planning_amount}, outstanding={row.outstanding_amount}.",
                "line_no": row.idx,
                "reference_doctype": row.reference_doctype,
                "reference_name": row.reference_name,
                "customer": row.customer,
                "company": row.company,
                "currency": row.currency,
                "planning_amount": row.planning_amount,
                "outstanding_amount": row.outstanding_amount,
                "gated_payment_entry": GATED_PAYMENT_ENTRY,
                "planning_payment_entry": PLANNING_PAYMENT_ENTRY,
            }
        )

    for key, label, value in [
        ("phase13w_monitor_verified", "Phase 13W runtime monitor verified", 1),
        ("gated_payment_entry", "Gated Payment Entry", GATED_PAYMENT_ENTRY),
        ("planning_payment_entry", "Planning Payment Entry", PLANNING_PAYMENT_ENTRY),
        ("planning_gl_rows", "Planning GL rows", EXPECTED_GL_ROWS),
        ("planning_reversal_gl_rows", "Governed reversal GL rows", EXPECTED_REVERSAL_GL_ROWS),
        ("design_ready", "Ready for next governed limited-operation design", 1),
    ]:
        items.append({"status": "Pass", "severity": "High", "category": "Planning Evidence", "check_key": key, "check_label": label, "detail": f"value={value}", "gated_payment_entry": GATED_PAYMENT_ENTRY, "planning_payment_entry": PLANNING_PAYMENT_ENTRY})

    items.append({"status": "Pass" if ack_ok else "Warning", "severity": "Low" if ack_ok else "Medium", "category": "Acknowledgement", "check_key": "ack_ok", "check_label": "Acknowledgement supplied", "detail": "Exact acknowledgement supplied." if ack_ok else f"Required acknowledgement not supplied: {PLANNING_ACK}", "gated_payment_entry": GATED_PAYMENT_ENTRY, "planning_payment_entry": PLANNING_PAYMENT_ENTRY})
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
        row = frappe.new_doc(PLANNING_ITEM_DOCTYPE)
        row.planning = doc.name
        for fieldname, value in item.items():
            if row.meta.has_field(fieldname):
                setattr(row, fieldname, value)
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_next_governed_limited_operation_planning_phase13x(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_next_governed_limited_operation_planning_phase13x")
    monitor = latest_runtime_monitor()
    rows = monitor_rows(monitor.name) if monitor else []
    guard_before = guardrails()
    ack_ok = acknowledgement == PLANNING_ACK
    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }
    policy_enabled_before = get_flag(POLICY_DOCTYPE, monitor.target_policy, "production_batch_enabled") if monitor else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, monitor.target_policy, "live_posting_allowed") if monitor else 0
    source_issues = validate_source(monitor, rows, guard_before, config, policy_enabled_before, policy_live_before)
    guard_after = guardrails()
    policy_enabled_after = get_flag(POLICY_DOCTYPE, monitor.target_policy, "production_batch_enabled") if monitor else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, monitor.target_policy, "live_posting_allowed") if monitor else 0

    state = payment_entry_state(PLANNING_PAYMENT_ENTRY)
    planning_gl_rows = payment_entry_gl_rows(PLANNING_PAYMENT_ENTRY)
    planning_gl_net = payment_entry_gl_net(PLANNING_PAYMENT_ENTRY)
    restored_amount = outstanding_total(EXPECTED_INVOICES)
    direct_cancelled_rows = direct_cancelled_gl_rows(PLANNING_PAYMENT_ENTRY)
    actual_pe_created = guard_after["payment_entry_count"] - guard_before["payment_entry_count"]
    actual_pe_cancelled = 0
    actual_gl_created = guard_after["payment_entry_gl_count"] - guard_before["payment_entry_gl_count"]
    policy_mutation_count = int(
        policy_enabled_before != policy_enabled_after
        or policy_live_before != policy_live_after
        or guard_before["production_batch_enabled_policy_count"] != guard_after["production_batch_enabled_policy_count"]
        or guard_before["live_posting_allowed_policy_count"] != guard_after["live_posting_allowed_policy_count"]
    )
    gated_state = payment_entry_state(GATED_PAYMENT_ENTRY)

    post_issues = list(source_issues)
    if actual_pe_created != 0:
        post_issues.append(f"Planning must create 0 Payment Entries. Created {actual_pe_created}.")
    if actual_pe_cancelled != 0:
        post_issues.append(f"Planning must cancel 0 Payment Entries. Cancelled {actual_pe_cancelled}.")
    if actual_gl_created != 0:
        post_issues.append(f"Planning must create 0 GL rows. Created {actual_gl_created}.")
    if guard_after["submitted_journal_entry_count_today"] != 0:
        post_issues.append("Submitted Journal Entry today must remain 0 after planning.")
    if guard_after["purchase_invoice_count_today"] != 0:
        post_issues.append("Purchase Invoice today must remain 0 after planning.")
    if policy_mutation_count != 0:
        post_issues.append("Policy state changed during planning. This is not allowed.")

    completed = int(
        not int(dry_run or 0)
        and ack_ok
        and monitor
        and not post_issues
        and gated_state.docstatus == 2
        and gated_state.status == "Cancelled"
        and state.docstatus == 2
        and state.status == "Cancelled"
        and reference_names(rows) == EXPECTED_INVOICES
        and planning_total(rows) == EXPECTED_TOTAL_AMOUNT
        and planning_gl_rows == EXPECTED_GL_ROWS
        and planning_gl_net == EXPECTED_GL_NET
        and restored_amount == EXPECTED_TOTAL_AMOUNT
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
        "status": "Planning Approved" if completed else "Needs Review",
        "planning_status": "Next Governed Limited Operation Planning Approved" if completed else "Needs Review",
        "planning_approved": completed,
        "phase13w_monitor_verified": 1 if monitor else 0,
        "monitor_active_verified": 1 if monitor else 0,
        "monitor_payment_entry_verified": int(monitor and monitor.monitor_payment_entry == PLANNING_PAYMENT_ENTRY),
        "monitor_payment_entry_cancelled_verified": int(state.docstatus == 2 and state.status == "Cancelled"),
        "monitor_gl_rows_verified": int(planning_gl_rows == EXPECTED_GL_ROWS),
        "monitor_reversal_gl_rows_verified": int(monitor and int(monitor.monitor_reversal_gl_rows or 0) == EXPECTED_REVERSAL_GL_ROWS),
        "monitor_gl_net_zero_verified": int(planning_gl_net == EXPECTED_GL_NET),
        "monitor_restored_invoice_amount_verified": int(restored_amount == EXPECTED_TOTAL_AMOUNT),
        "policy_state_preserved_verified": int(policy_mutation_count == 0 and policy_enabled_before == 1 and policy_enabled_after == 1 and policy_live_before == 0 and policy_live_after == 0),
        "no_new_accounting_movement_verified": int(actual_pe_created == 0 and actual_pe_cancelled == 0 and actual_gl_created == 0),
        "gated_payment_entry": GATED_PAYMENT_ENTRY,
        "gated_payment_entry_docstatus": gated_state.docstatus,
        "gated_payment_entry_status": gated_state.status,
        "planning_payment_entry": PLANNING_PAYMENT_ENTRY,
        "planning_payment_entry_docstatus": state.docstatus,
        "planning_payment_entry_status": state.status,
        "planning_source_doctype": PLANNING_SOURCE_DOCTYPE,
        "planning_reference_doctype": PLANNING_REFERENCE_DOCTYPE,
        "planning_party_type": PLANNING_PARTY_TYPE,
        "planning_customer": unique_value(rows, "customer"),
        "planning_company": unique_value(rows, "company"),
        "planning_currency": unique_value(rows, "currency"),
        "planning_invoice_names": ", ".join(reference_names(rows)),
        "planning_invoice_count": len(rows),
        "planning_total_amount": planning_total(rows),
        "planning_restored_invoice_amount": restored_amount,
        "planning_gl_rows": planning_gl_rows,
        "planning_reversal_gl_rows": EXPECTED_REVERSAL_GL_ROWS,
        "planning_gl_net": planning_gl_net,
        "planning_direct_cancelled_gl_rows": direct_cancelled_rows,
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
        "target_policy": monitor.target_policy if monitor else None,
        "target_policy_name": monitor.target_policy_name if monitor else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_before": policy_live_before,
        "target_policy_live_after": policy_live_after,
        "actual_policy_mutation_count": policy_mutation_count,
        PLANNING_READY_FIELD: completed,
        "monitor": monitor.name if monitor else None,
        "baseline": monitor.baseline if monitor else None,
        "closeout": monitor.closeout if monitor else None,
        "freeze": monitor.freeze if monitor else None,
        "rollback": monitor.rollback if monitor else None,
        "smoke": monitor.smoke if monitor else None,
        "execution_gate": monitor.execution_gate if monitor else None,
        "preview": monitor.preview if monitor else None,
        "candidate_validation": monitor.candidate_validation if monitor else None,
        "candidate_selection": monitor.candidate_selection if monitor else None,
        "design": monitor.design if monitor else None,
        "previous_planning": monitor.planning if monitor else None,
        **item_summary,
        "items": items,
        "issues": post_issues,
        "required_acknowledgement": PLANNING_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 13X approves next governed limited-operation planning. No accounting movement occurs.",
    }
    if int(dry_run or 0):
        return result
    doc = frappe.new_doc(PLANNING_DOCTYPE)
    doc.planning_id = make_planning_id()
    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = PLANNING_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.planning_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    create_items(doc, items)
    frappe.db.commit()
    return {**result, "created": True, "planning": doc.name, "planning_id": doc.planning_id, "gated_payment_entry": GATED_PAYMENT_ENTRY, "planning_payment_entry": PLANNING_PAYMENT_ENTRY, "guardrails_after": guardrails()}


@frappe.whitelist()
def cancel_next_governed_limited_operation_planning_phase13x_audit(planning, reason=None):
    assert_action("cancel_next_governed_limited_operation_planning_phase13x_audit")
    if not frappe.db.exists(PLANNING_DOCTYPE, planning):
        frappe.throw(_("Next governed limited-operation planning audit not found: {0}").format(planning))
    doc = frappe.get_doc(PLANNING_DOCTYPE, planning)
    if doc.status == "Cancelled":
        return {"planning": planning, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.planning_approved or 0):
        frappe.throw(_("Cannot cancel an approved Phase 13X planning record."))
    frappe.db.set_value(
        PLANNING_DOCTYPE,
        planning,
        {"status": "Cancelled", "planning_status": "Cancelled", "cancelled_on": now_datetime(), "cancelled_by": frappe.session.user, "summary_json": reason or "Phase 13X no-ack planning audit cancelled."},
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{PLANNING_ITEM_DOCTYPE}` SET status='Cancelled' WHERE planning=%(planning)s", {"planning": planning})
    frappe.db.commit()
    return {"planning": planning, "status": "Cancelled", "note": "No-ack planning audit cancelled only. No accounting movement occurred."}


@frappe.whitelist()
def quick_next_governed_limited_operation_planning_phase13x_summary(limit=20):
    return {
        "planning_records": frappe.get_all(
            PLANNING_DOCTYPE,
            filters={"planning_payment_entry": PLANNING_PAYMENT_ENTRY},
            fields=["name", "planning_id", "status", "planning_status", "planning_approved", "planning_payment_entry", "planning_payment_entry_docstatus", "planning_payment_entry_status", "planning_invoice_names", "planning_invoice_count", "planning_total_amount", "planning_restored_invoice_amount", "planning_gl_rows", "planning_reversal_gl_rows", "planning_gl_net", "payment_entry_count_before", "payment_entry_count_after", "payment_entry_gl_count_before", "payment_entry_gl_count_after", "actual_payment_entry_created_count", "actual_payment_entry_cancelled_count", "actual_gl_created_count", "submitted_journal_entry_count_today", "purchase_invoice_count_today", PLANNING_READY_FIELD, "checked_on", "checked_by"],
            order_by="creation desc",
            limit=int(limit or 20),
        ),
        "items": frappe.get_all(
            PLANNING_ITEM_DOCTYPE,
            fields=["name", "planning", "status", "severity", "category", "check_key", "check_label", "line_no", "reference_doctype", "reference_name", "customer", "company", "currency", "planning_amount", "outstanding_amount", "planning_payment_entry", "detail"],
            order_by="creation desc",
            limit=int(limit or 20),
        ),
        "required_acknowledgement": PLANNING_ACK,
        "guardrails": guardrails(),
        "note": "Phase 13X next governed limited-operation planning summary.",
    }


def execute_planning_phase13x_report(filters=None):
    columns = [
        {"fieldname": "planning", "label": _("Planning"), "fieldtype": "Link", "options": PLANNING_DOCTYPE, "width": 220},
        {"fieldname": "planning_id", "label": _("Planning ID"), "fieldtype": "Data", "width": 540},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 160},
        {"fieldname": "planning_status", "label": _("Planning Status"), "fieldtype": "Data", "width": 390},
        {"fieldname": "planning_approved", "label": _("Approved"), "fieldtype": "Check", "width": 90},
        {"fieldname": "planning_payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "planning_payment_entry_status", "label": _("PE Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "planning_invoice_names", "label": _("Invoices"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "planning_total_amount", "label": _("Amount"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "planning_restored_invoice_amount", "label": _("Restored"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "planning_gl_rows", "label": _("GL Rows"), "fieldtype": "Int", "width": 90},
        {"fieldname": "planning_reversal_gl_rows", "label": _("Reversal Rows"), "fieldtype": "Int", "width": 120},
        {"fieldname": "planning_gl_net", "label": _("GL Net"), "fieldtype": "Currency", "width": 100},
        {"fieldname": PLANNING_READY_FIELD, "label": _("Design Ready"), "fieldtype": "Check", "width": 120},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 115},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 115},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL Created"), "fieldtype": "Int", "width": 135},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]
    data = frappe.db.sql(
        f"""
        SELECT name AS planning, planning_id, status, planning_status, planning_approved,
            planning_payment_entry, planning_payment_entry_status, planning_invoice_names,
            planning_total_amount, planning_restored_invoice_amount, planning_gl_rows,
            planning_reversal_gl_rows, planning_gl_net,
            `{PLANNING_READY_FIELD}` AS `{PLANNING_READY_FIELD}`,
            payment_entry_count_before, payment_entry_count_after,
            payment_entry_gl_count_before, payment_entry_gl_count_after,
            actual_gl_created_count, checked_on
        FROM `tab{PLANNING_DOCTYPE}`
        WHERE planning_payment_entry=%(payment_entry)s
        ORDER BY creation DESC
        """,
        {"payment_entry": PLANNING_PAYMENT_ENTRY},
        as_dict=True,
    )
    chart = {"data": {"labels": [row.planning_id for row in data[:20]], "datasets": [{"name": "Planning Approved", "values": [int(row.planning_approved or 0) for row in data[:20]]}, {"name": "Design Ready", "values": [int(row.get(PLANNING_READY_FIELD) or 0) for row in data[:20]]}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Planning Records"), "datatype": "Int"},
        {"value": sum(int(row.planning_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL Created"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_item_report(filters=None):
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": PLANNING_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "planning", "label": _("Planning"), "fieldtype": "Link", "options": PLANNING_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 190},
        {"fieldname": "line_no", "label": _("Line"), "fieldtype": "Int", "width": 60},
        {"fieldname": "reference_doctype", "label": _("Ref DocType"), "fieldtype": "Data", "width": 130},
        {"fieldname": "reference_name", "label": _("Reference"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 180},
        {"fieldname": "planning_amount", "label": _("Planning Amount"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "outstanding_amount", "label": _("Outstanding"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "planning_payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 650},
    ]
    data = frappe.db.sql(
        f"""
        SELECT name AS item, planning, status, category, line_no, reference_doctype,
            reference_name, planning_amount, outstanding_amount, planning_payment_entry, detail
        FROM `tab{PLANNING_ITEM_DOCTYPE}`
        ORDER BY creation DESC
        """,
        as_dict=True,
    )
    chart = {"data": {"labels": ["Pass", "Warning", "Blocker", "Info"], "datasets": [{"name": "Items", "values": [len([row for row in data if row.status == status]) for status in ["Pass", "Warning", "Blocker", "Info"]]}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Items"), "datatype": "Int"},
        {"value": len([row for row in data if row.category == "Planning Reference"]), "indicator": "Green", "label": _("Planning References"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_planning_phase13x_report(filters)
    guard = guardrails()
    summary.append({"value": guard["payment_entry_count"], "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"})
    summary.append({"value": guard["payment_entry_gl_count"], "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"})
    summary.append({"value": guard["submitted_journal_entry_count_today"], "indicator": "Red", "label": _("Submitted JE Today"), "datatype": "Int"})
    summary.append({"value": guard["purchase_invoice_count_today"], "indicator": "Red", "label": _("Purchase Invoice Today"), "datatype": "Int"})
    summary.append({"value": guard["production_batch_enabled_policy_count"], "indicator": "Green", "label": _("Enabled Policies"), "datatype": "Int"})
    summary.append({"value": guard["live_posting_allowed_policy_count"], "indicator": "Red", "label": _("Live Policies"), "datatype": "Int"})
    return columns, data, message, chart, summary
