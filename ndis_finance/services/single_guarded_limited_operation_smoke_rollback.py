import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


ROLLBACK_ACK = "I_CONFIRM_PHASE10K_ROLLBACK_SINGLE_GUARDED_LIMITED_OPERATION_SMOKE_CANCEL_PE"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"


def make_rollback_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-SINGLE-GUARDED-LIMITED-OP-ROLLBACK-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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
    if not name or not has_column(doctype, fieldname):
        return default
    return int(frappe.db.get_value(doctype, name, fieldname) or 0)


def production_batch_enabled_policy_count():
    if not frappe.db.exists("DocType", POLICY_DOCTYPE):
        return 0
    if not has_column(POLICY_DOCTYPE, "production_batch_enabled"):
        return 0
    return count_dt(POLICY_DOCTYPE, {"production_batch_enabled": 1})


def live_posting_allowed_policy_count():
    if not frappe.db.exists("DocType", POLICY_DOCTYPE):
        return 0
    if not has_column(POLICY_DOCTYPE, "live_posting_allowed"):
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
        "NDIS Single Guarded Limited Operation Smoke",
        filters={
            "status": "Smoke Completed - Rollback Required",
            "smoke_status": "Single Guarded Limited Operation Smoke Completed",
            "smoke_execution_completed": 1,
            "rollback_required": 1,
            "freeze_required_after_rollback": 1,
            "ready_for_single_operation_smoke_rollback": 1,
            "payment_entry_docstatus": 1,
            "payment_entry_status": "Submitted",
            "payment_entry_amount": 3,
            "payment_entry_reference_count": 3,
            "actual_payment_entry_created_count": 1,
            "submitted_journal_entry_count_today": 0,
            "purchase_invoice_count_today": 0,
            "controlled_policy_enabled_verified": 1,
            "live_posting_blocked_verified": 1,
        },
        fields=[
            "name",
            "smoke_id",
            "execution_gate",
            "preview",
            "pre_check",
            "monitoring_register",
            "decision",
            "runtime_guard",
            "target_policy_doctype",
            "target_policy",
            "target_policy_name",
            "payment_entry",
            "payment_entry_amount",
            "payment_entry_reference_count",
            "payment_entry_gl_row_count",
            "production_batch_enabled_policy_count_after",
            "live_posting_allowed_policy_count_after",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_rollback(smoke):
    rows = frappe.get_all(
        "NDIS Single Guarded Limited Operation Smoke Rollback",
        filters={
            "smoke": smoke,
            "status": "Rollback Completed",
            "rollback_completed": 1,
        },
        fields=["name", "rollback_id", "payment_entry"],
        limit=1,
    )
    return rows[0] if rows else None


def reference_snapshot(payment_entry):
    pe = frappe.get_doc("Payment Entry", payment_entry)
    rows = []

    for ref in pe.references:
        if ref.reference_doctype != "Sales Invoice":
            continue

        outstanding = flt(
            frappe.db.get_value("Sales Invoice", ref.reference_name, "outstanding_amount") or 0,
            2,
        )

        rows.append(
            {
                "reference_doctype": ref.reference_doctype,
                "reference_name": ref.reference_name,
                "allocated_amount": flt(ref.allocated_amount or 0, 2),
                "outstanding_amount": outstanding,
            }
        )

    return rows


def voucher_gl_rows(payment_entry):
    return count_dt("GL Entry", {"voucher_type": "Payment Entry", "voucher_no": payment_entry})


def voucher_gl_net(payment_entry):
    rows = frappe.db.sql(
        """
        SELECT
            account,
            ROUND(SUM(debit), 2) AS debit,
            ROUND(SUM(credit), 2) AS credit,
            ROUND(SUM(debit - credit), 2) AS balance
        FROM `tabGL Entry`
        WHERE voucher_type = 'Payment Entry'
        AND voucher_no = %(payment_entry)s
        GROUP BY account
        ORDER BY account
        """,
        {"payment_entry": payment_entry},
        as_dict=True,
    )

    total_debit = round(sum(flt(row.debit or 0, 2) for row in rows), 2)
    total_credit = round(sum(flt(row.credit or 0, 2) for row in rows), 2)
    total_balance = round(total_debit - total_credit, 2)
    non_zero_count = len([row for row in rows if abs(flt(row.balance or 0, 2)) > 0.01])

    return {
        "rows": rows,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "total_balance": total_balance,
        "non_zero_count": non_zero_count,
    }


def validate_source(smoke, guard, pe):
    issues = []

    if not smoke:
        issues.append("No rollback-required Phase 10J smoke found.")
        return issues

    existing = existing_rollback(smoke.name)
    if existing:
        issues.append(f"Phase 10K rollback already exists for this smoke: {existing.rollback_id} / {existing.payment_entry}")

    required_links = {
        "smoke": ("NDIS Single Guarded Limited Operation Smoke", smoke.name),
        "execution_gate": ("NDIS Guarded Limited Operation Execution Gate", smoke.execution_gate),
        "payment_entry": ("Payment Entry", smoke.payment_entry),
        "target_policy": (POLICY_DOCTYPE, smoke.target_policy),
    }

    for label, pair in required_links.items():
        doctype, name = pair
        if not name:
            issues.append(f"Missing evidence link: {label}")
        elif not frappe.db.exists(doctype, name):
            issues.append(f"Linked evidence does not exist: {doctype} {name}")

    if not pe:
        issues.append("Payment Entry document could not be loaded.")
        return issues

    if int(pe.docstatus or 0) != 1:
        issues.append(f"Payment Entry must be submitted before rollback. Current docstatus: {pe.docstatus}")

    if pe.status != "Submitted":
        issues.append(f"Payment Entry status must be Submitted before rollback. Current status: {pe.status}")

    if flt(pe.paid_amount or 0, 2) != 3:
        issues.append(f"Payment Entry paid amount must be 3.00. Current: {flt(pe.paid_amount or 0, 2)}")

    if len(pe.references or []) != 3:
        issues.append(f"Payment Entry must have 3 references. Current: {len(pe.references or [])}")

    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must remain enabled.")

    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must remain 0.")

    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry count today must remain 0.")

    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice count today must remain 0.")

    return issues


def add_item(items, status, severity, category, check_key, check_label, detail, source_doctype=None, source_name=None):
    items.append(
        {
            "status": status,
            "severity": severity,
            "category": category,
            "check_key": check_key,
            "check_label": check_label,
            "detail": detail,
            "source_doctype": source_doctype,
            "source_name": source_name,
        }
    )


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
        row = frappe.new_doc("NDIS Single Guarded Limited Operation Smoke Rollback Item")
        row.rollback = doc.name
        row.status = item["status"]
        row.severity = item["severity"]
        row.category = item["category"]
        row.check_key = item["check_key"]
        row.check_label = item["check_label"]
        row.detail = item["detail"]
        row.source_doctype = item.get("source_doctype")
        row.source_name = item.get("source_name")
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


def build_items(smoke, issues, ack_ok, result=None):
    items = []

    if smoke:
        add_item(
            items,
            "Pass",
            "Low",
            "Evidence",
            "phase10j_smoke_exists",
            "Phase 10J smoke exists",
            f"Smoke found: {smoke.smoke_id}.",
            "NDIS Single Guarded Limited Operation Smoke",
            smoke.name,
        )
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase10j_smoke_exists", "Phase 10J smoke exists", "No rollback-required Phase 10J smoke found.")

    if not issues:
        add_item(items, "Pass", "Low", "Rollback Source", "rollback_source_valid", "Rollback source valid", "Phase 10J smoke is valid for rollback.")
    else:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Rollback Source", "rollback_source_valid", "Rollback source valid", issue)

    if result:
        add_item(items, "Pass", "High", "Rollback", "payment_entry_cancelled", "Payment Entry cancelled", f"{result['payment_entry']} docstatus {result['payment_entry_docstatus_before']} -> {result['payment_entry_docstatus_after']}", "Payment Entry", result["payment_entry"])
        add_item(items, "Pass", "High", "Rollback", "invoice_outstanding_restored", "Invoice outstanding restored", f"delta={result['invoice_outstanding_restored_delta']} allocated={result['allocated_amount_total']}")
        add_item(items, "Pass", "High", "Rollback", "voucher_gl_reversal_rows", "Voucher GL reversal rows created", f"{result['voucher_gl_rows_before']} -> {result['voucher_gl_rows_after']}; reversal={result['voucher_gl_reversal_rows']}")
        add_item(items, "Pass", "High", "Rollback", "gl_net_zero", "Voucher GL net zero verified", f"debit={result['gl_net_debit']} credit={result['gl_net_credit']} balance={result['gl_net_balance']} non_zero_accounts={result['gl_account_non_zero_count']}")

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {ROLLBACK_ACK}")

    return items


@frappe.whitelist()
def run_single_guarded_limited_operation_smoke_rollback(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_single_guarded_limited_operation_smoke_rollback")

    smoke = latest_smoke()
    guard_before = guardrails()
    ack_ok = acknowledgement == ROLLBACK_ACK

    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }

    pe = None
    if smoke and smoke.payment_entry and frappe.db.exists("Payment Entry", smoke.payment_entry):
        pe = frappe.get_doc("Payment Entry", smoke.payment_entry)

    issues = validate_source(smoke, guard_before, pe)

    refs_before = reference_snapshot(smoke.payment_entry) if smoke and smoke.payment_entry else []
    allocated_total = round(sum(flt(row["allocated_amount"], 2) for row in refs_before), 2)
    outstanding_before_total = round(sum(flt(row["outstanding_amount"], 2) for row in refs_before), 2)

    if int(dry_run or 0):
        items = build_items(smoke, issues, ack_ok, None)
        item_summary = summarise_items(items)
        score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

        return {
            "dry_run": True,
            "would_cancel_payment_entry": smoke.payment_entry if smoke else None,
            "payment_entry_docstatus": int(pe.docstatus or 0) if pe else None,
            "payment_entry_status": pe.status if pe else None,
            "reference_count": len(refs_before),
            "allocated_amount_total": allocated_total,
            "invoice_outstanding_before_total": outstanding_before_total,
            "required_acknowledgement": ROLLBACK_ACK,
            "acknowledgement_ok": ack_ok,
            "guardrails_before": guard_before,
            "guardrails_after": guardrails(),
            "rollback_score": score,
            **item_summary,
            "items": items,
            "issues": issues,
            "note": "Dry-run only. Payment Entry not cancelled.",
        }

    if not ack_ok or issues:
        items = build_items(smoke, issues, ack_ok, None)
        item_summary = summarise_items(items)
        score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

        doc = frappe.new_doc("NDIS Single Guarded Limited Operation Smoke Rollback")
        doc.rollback_id = make_rollback_id()
        doc.status = "Needs Review"
        doc.rollback_status = "Needs Review"
        doc.smoke = smoke.name if smoke else None
        doc.execution_gate = smoke.execution_gate if smoke else None
        doc.preview = smoke.preview if smoke else None
        doc.pre_check = smoke.pre_check if smoke else None
        doc.monitoring_register = smoke.monitoring_register if smoke else None
        doc.target_policy_doctype = POLICY_DOCTYPE
        doc.target_policy = smoke.target_policy if smoke else None
        doc.target_policy_name = smoke.target_policy_name if smoke else None
        doc.payment_entry = smoke.payment_entry if smoke else None
        doc.payment_entry_docstatus_before = int(pe.docstatus or 0) if pe else 0
        doc.payment_entry_docstatus_after = int(pe.docstatus or 0) if pe else 0
        doc.payment_entry_status_before = pe.status if pe else None
        doc.payment_entry_status_after = pe.status if pe else None
        doc.payment_entry_count_before = guard_before["payment_entry_count"]
        doc.payment_entry_count_after = guard_before["payment_entry_count"]
        doc.payment_entry_gl_count_before = guard_before["payment_entry_gl_count"]
        doc.payment_entry_gl_count_after = guard_before["payment_entry_gl_count"]
        doc.actual_payment_entry_cancelled_count = 0
        doc.actual_gl_created_count = 0
        doc.submitted_journal_entry_count_today = guard_before["submitted_journal_entry_count_today"]
        doc.purchase_invoice_count_today = guard_before["purchase_invoice_count_today"]
        doc.rollback_score = score
        doc.blocker_count = item_summary["blocker_count"]
        doc.warning_count = item_summary["warning_count"]
        doc.pass_count = item_summary["pass_count"]
        doc.info_count = item_summary["info_count"]
        doc.item_count = item_summary["item_count"]
        doc.site_name = frappe.local.site
        doc.sandbox_config_enabled = config["sandbox_enabled"]
        doc.production_mode_detected = config["production_mode"]
        doc.live_payment_entry_posting_config = config["live_pe_enabled"]
        doc.checked_on = now_datetime()
        doc.checked_by = frappe.session.user
        doc.required_acknowledgement = ROLLBACK_ACK
        doc.acknowledgement = acknowledgement
        doc.acknowledgement_ok = int(ack_ok)
        doc.summary_json = safe_json({"issues": issues, "guardrails": guard_before})
        doc.reference_json = safe_json(refs_before)
        doc.notes = notes
        doc.insert(ignore_permissions=True)

        create_items(doc, items)
        frappe.db.commit()

        return {
            "created": True,
            "rollback": doc.name,
            "rollback_id": doc.rollback_id,
            "status": doc.status,
            "rollback_status": doc.rollback_status,
            "issues": issues,
            "guardrails_after": guardrails(),
        }

    pe_docstatus_before = int(pe.docstatus or 0)
    pe_status_before = pe.status
    voucher_gl_before = voucher_gl_rows(pe.name)

    target_policy_enabled_before = get_flag(POLICY_DOCTYPE, smoke.target_policy, "production_batch_enabled")
    target_policy_live_before = get_flag(POLICY_DOCTYPE, smoke.target_policy, "live_posting_allowed")

    pe.cancel()
    frappe.db.commit()

    pe_after = frappe.get_doc("Payment Entry", pe.name)
    refs_after = reference_snapshot(pe.name)
    outstanding_after_total = round(sum(flt(row["outstanding_amount"], 2) for row in refs_after), 2)
    restored_delta = round(outstanding_after_total - outstanding_before_total, 2)

    guard_after = guardrails()
    voucher_gl_after = voucher_gl_rows(pe.name)
    reversal_rows = voucher_gl_after - voucher_gl_before
    gl_net = voucher_gl_net(pe.name)

    target_policy_enabled_after = get_flag(POLICY_DOCTYPE, smoke.target_policy, "production_batch_enabled")
    target_policy_live_after = get_flag(POLICY_DOCTYPE, smoke.target_policy, "live_posting_allowed")

    result = {
        "payment_entry": pe.name,
        "payment_entry_docstatus_before": pe_docstatus_before,
        "payment_entry_docstatus_after": int(pe_after.docstatus or 0),
        "payment_entry_status_before": pe_status_before,
        "payment_entry_status_after": pe_after.status,
        "payment_entry_amount": flt(pe_after.paid_amount or 0, 2),
        "payment_entry_reference_count": len(pe_after.references or []),
        "allocated_amount_total": allocated_total,
        "invoice_outstanding_before_total": outstanding_before_total,
        "invoice_outstanding_after_total": outstanding_after_total,
        "invoice_outstanding_restored_delta": restored_delta,
        "voucher_gl_rows_before": voucher_gl_before,
        "voucher_gl_rows_after": voucher_gl_after,
        "voucher_gl_reversal_rows": reversal_rows,
        "gl_net_debit": gl_net["total_debit"],
        "gl_net_credit": gl_net["total_credit"],
        "gl_net_balance": gl_net["total_balance"],
        "gl_account_non_zero_count": gl_net["non_zero_count"],
    }

    blockers = []

    if result["payment_entry_docstatus_after"] != 2:
        blockers.append("Payment Entry was not cancelled to docstatus 2.")

    if result["payment_entry_status_after"] != "Cancelled":
        blockers.append("Payment Entry status is not Cancelled.")

    if guard_after["payment_entry_count"] != guard_before["payment_entry_count"]:
        blockers.append("Payment Entry count changed during rollback.")

    if reversal_rows <= 0:
        blockers.append("No GL reversal rows were created.")

    if abs(flt(restored_delta, 2) - flt(allocated_total, 2)) > 0.01:
        blockers.append(f"Invoice outstanding restored delta {restored_delta} does not match allocated total {allocated_total}.")

    if abs(flt(gl_net["total_balance"], 2)) > 0.01 or gl_net["non_zero_count"] != 0:
        blockers.append("Voucher GL is not net zero after cancellation.")

    if guard_after["submitted_journal_entry_count_today"] != guard_before["submitted_journal_entry_count_today"]:
        blockers.append("Submitted Journal Entry count changed during rollback.")

    if guard_after["purchase_invoice_count_today"] != guard_before["purchase_invoice_count_today"]:
        blockers.append("Purchase Invoice count changed during rollback.")

    if target_policy_enabled_before != 1 or target_policy_enabled_after != 1 or target_policy_live_before != 0 or target_policy_live_after != 0:
        blockers.append("Policy state changed or is not enabled/live-blocked.")

    items = build_items(smoke, blockers, ack_ok, result)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    completed = int(item_summary["blocker_count"] == 0)

    doc = frappe.new_doc("NDIS Single Guarded Limited Operation Smoke Rollback")
    doc.rollback_id = make_rollback_id()
    doc.status = "Rollback Completed" if completed else "Blocked"
    doc.rollback_status = "Single Guarded Limited Operation Smoke Rolled Back" if completed else "Blocked"

    doc.rollback_completed = completed
    doc.ready_for_single_operation_smoke_freeze = completed
    doc.freeze_required_after_rollback = completed
    doc.payment_entry_cancelled_verified = int(result["payment_entry_docstatus_after"] == 2 and result["payment_entry_status_after"] == "Cancelled")
    doc.invoice_outstanding_restored_verified = int(abs(flt(restored_delta, 2) - flt(allocated_total, 2)) <= 0.01)
    doc.voucher_gl_reversal_verified = int(reversal_rows > 0)
    doc.gl_net_zero_verified = int(abs(flt(gl_net["total_balance"], 2)) <= 0.01 and gl_net["non_zero_count"] == 0)
    doc.policy_state_preserved_verified = int(target_policy_enabled_before == 1 and target_policy_enabled_after == 1 and target_policy_live_before == 0 and target_policy_live_after == 0)
    doc.policy_mutation_performed = 0
    doc.actual_policy_mutation_count = 0

    doc.phase10j_smoke_verified = 1
    doc.phase10i_gate_verified = 1
    doc.controlled_policy_enabled_verified = int(target_policy_enabled_after == 1)
    doc.live_posting_blocked_verified = int(target_policy_live_after == 0)

    doc.smoke = smoke.name
    doc.execution_gate = smoke.execution_gate
    doc.preview = smoke.preview
    doc.pre_check = smoke.pre_check
    doc.monitoring_register = smoke.monitoring_register

    doc.target_policy_doctype = POLICY_DOCTYPE
    doc.target_policy = smoke.target_policy
    doc.target_policy_name = smoke.target_policy_name
    doc.target_policy_enabled_before = target_policy_enabled_before
    doc.target_policy_enabled_after = target_policy_enabled_after
    doc.target_policy_live_before = target_policy_live_before
    doc.target_policy_live_after = target_policy_live_after
    doc.production_batch_enabled_policy_count_before = guard_before["production_batch_enabled_policy_count"]
    doc.production_batch_enabled_policy_count_after = guard_after["production_batch_enabled_policy_count"]
    doc.live_posting_allowed_policy_count_before = guard_before["live_posting_allowed_policy_count"]
    doc.live_posting_allowed_policy_count_after = guard_after["live_posting_allowed_policy_count"]

    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)

    doc.payment_entry_count_before = guard_before["payment_entry_count"]
    doc.payment_entry_count_after = guard_after["payment_entry_count"]
    doc.payment_entry_gl_count_before = guard_before["payment_entry_gl_count"]
    doc.payment_entry_gl_count_after = guard_after["payment_entry_gl_count"]
    doc.actual_payment_entry_cancelled_count = int(pe_docstatus_before == 1 and result["payment_entry_docstatus_after"] == 2)
    doc.actual_gl_created_count = guard_after["payment_entry_gl_count"] - guard_before["payment_entry_gl_count"]
    doc.submitted_journal_entry_count_today = guard_after["submitted_journal_entry_count_today"]
    doc.purchase_invoice_count_today = guard_after["purchase_invoice_count_today"]

    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.rollback_score = score
    doc.blocker_count = item_summary["blocker_count"]
    doc.warning_count = item_summary["warning_count"]
    doc.pass_count = item_summary["pass_count"]
    doc.info_count = item_summary["info_count"]
    doc.item_count = item_summary["item_count"]
    doc.required_acknowledgement = ROLLBACK_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(
        {
            "result": result,
            "guardrails_before": guard_before,
            "guardrails_after": guard_after,
            "blockers": blockers,
        }
    )
    doc.reference_json = safe_json({"before": refs_before, "after": refs_after})
    doc.gl_json = safe_json(gl_net)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    create_items(doc, items)
    frappe.db.commit()

    return {
        "created": True,
        "rollback": doc.name,
        "rollback_id": doc.rollback_id,
        "status": doc.status,
        "rollback_status": doc.rollback_status,
        "payment_entry": pe.name,
        "payment_entry_docstatus_before": pe_docstatus_before,
        "payment_entry_docstatus_after": result["payment_entry_docstatus_after"],
        "payment_entry_status_before": pe_status_before,
        "payment_entry_status_after": result["payment_entry_status_after"],
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guard_after["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
        "voucher_gl_rows_before": voucher_gl_before,
        "voucher_gl_rows_after": voucher_gl_after,
        "voucher_gl_reversal_rows": reversal_rows,
        "invoice_outstanding_restored_delta": restored_delta,
        "allocated_amount_total": allocated_total,
        "gl_net_debit": gl_net["total_debit"],
        "gl_net_credit": gl_net["total_credit"],
        "gl_net_balance": gl_net["total_balance"],
        "gl_account_non_zero_count": gl_net["non_zero_count"],
        "actual_payment_entry_cancelled_count": doc.actual_payment_entry_cancelled_count,
        "actual_gl_created_count": doc.actual_gl_created_count,
        "ready_for_single_operation_smoke_freeze": doc.ready_for_single_operation_smoke_freeze,
        "blockers": blockers,
        "guardrails_after": guard_after,
    }


@frappe.whitelist()
def cancel_single_guarded_limited_operation_smoke_rollback_audit(rollback, reason=None):
    assert_action("cancel_single_guarded_limited_operation_smoke_rollback_audit")

    if not frappe.db.exists("NDIS Single Guarded Limited Operation Smoke Rollback", rollback):
        frappe.throw(_("Rollback audit not found: {0}").format(rollback))

    doc = frappe.get_doc("NDIS Single Guarded Limited Operation Smoke Rollback", rollback)

    if doc.status == "Cancelled":
        return {"rollback": rollback, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.rollback_completed or 0):
        frappe.throw(_("Cannot cancel a completed Phase 10K rollback record."))

    frappe.db.set_value(
        "NDIS Single Guarded Limited Operation Smoke Rollback",
        rollback,
        {
            "status": "Cancelled",
            "rollback_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 10K no-ack rollback audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        """
        UPDATE `tabNDIS Single Guarded Limited Operation Smoke Rollback Item`
        SET status = 'Cancelled'
        WHERE rollback = %(rollback)s
        """,
        {"rollback": rollback},
    )

    frappe.db.commit()

    return {
        "rollback": rollback,
        "status": "Cancelled",
        "note": "No-ack rollback audit cancelled only. No accounting or policy movement occurred.",
    }


@frappe.whitelist()
def quick_single_guarded_limited_operation_smoke_rollback_summary(limit=20):
    rollbacks = frappe.get_all(
        "NDIS Single Guarded Limited Operation Smoke Rollback",
        fields=[
            "name",
            "rollback_id",
            "status",
            "rollback_status",
            "rollback_completed",
            "ready_for_single_operation_smoke_freeze",
            "payment_entry",
            "payment_entry_docstatus_before",
            "payment_entry_docstatus_after",
            "payment_entry_status_before",
            "payment_entry_status_after",
            "invoice_outstanding_restored_delta",
            "allocated_amount_total",
            "voucher_gl_reversal_rows",
            "gl_net_balance",
            "gl_account_non_zero_count",
            "actual_payment_entry_cancelled_count",
            "actual_gl_created_count",
            "rollback_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    items = frappe.get_all(
        "NDIS Single Guarded Limited Operation Smoke Rollback Item",
        fields=["name", "rollback", "status", "severity", "category", "check_label", "detail", "source_doctype", "source_name"],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    return {
        "rollbacks": rollbacks,
        "items": items,
        "required_acknowledgement": ROLLBACK_ACK,
        "guardrails": guardrails(),
        "note": "Phase 10K rollback summary. Completed rollback should be frozen in Phase 10L.",
    }


def execute_rollback_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("status"):
        conditions.append("r.status = %(status)s")
        params["status"] = filters.get("status")

    columns = rollback_columns()

    data = frappe.db.sql(
        f"""
        SELECT
            r.name AS rollback,
            r.rollback_id,
            r.status,
            r.rollback_status,
            r.rollback_completed,
            r.ready_for_single_operation_smoke_freeze,
            r.payment_entry,
            r.payment_entry_docstatus_before,
            r.payment_entry_docstatus_after,
            r.payment_entry_status_before,
            r.payment_entry_status_after,
            r.payment_entry_amount,
            r.payment_entry_reference_count,
            r.allocated_amount_total,
            r.invoice_outstanding_restored_delta,
            r.voucher_gl_rows_before,
            r.voucher_gl_rows_after,
            r.voucher_gl_reversal_rows,
            r.gl_net_debit,
            r.gl_net_credit,
            r.gl_net_balance,
            r.gl_account_non_zero_count,
            r.actual_payment_entry_cancelled_count,
            r.actual_gl_created_count,
            r.rollback_score,
            r.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Single Guarded Limited Operation Smoke Rollback` r
        {build_where(conditions)}
        ORDER BY r.creation DESC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.rollback_id for row in data[:20]],
            "datasets": [
                {"name": "Cancelled PE", "values": [int(row.actual_payment_entry_cancelled_count or 0) for row in data[:20]]},
                {"name": "Reversal GL", "values": [int(row.actual_gl_created_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Rollbacks"), "datatype": "Int"},
        {"value": sum(int(row.rollback_completed or 0) for row in data), "indicator": "Green", "label": _("Completed"), "datatype": "Int"},
        {"value": sum(int(row.actual_payment_entry_cancelled_count or 0) for row in data), "indicator": "Green", "label": _("Cancelled PE"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Orange", "label": _("Reversal GL"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def rollback_columns():
    return [
        {"fieldname": "rollback", "label": _("Rollback"), "fieldtype": "Link", "options": "NDIS Single Guarded Limited Operation Smoke Rollback", "width": 220},
        {"fieldname": "rollback_id", "label": _("Rollback ID"), "fieldtype": "Data", "width": 430},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 160},
        {"fieldname": "rollback_status", "label": _("Rollback Status"), "fieldtype": "Data", "width": 330},
        {"fieldname": "rollback_completed", "label": _("Completed"), "fieldtype": "Check", "width": 95},
        {"fieldname": "ready_for_single_operation_smoke_freeze", "label": _("Ready Freeze"), "fieldtype": "Check", "width": 110},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "payment_entry_docstatus_before", "label": _("Doc Before"), "fieldtype": "Int", "width": 95},
        {"fieldname": "payment_entry_docstatus_after", "label": _("Doc After"), "fieldtype": "Int", "width": 95},
        {"fieldname": "payment_entry_status_after", "label": _("PE Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "payment_entry_amount", "label": _("PE Amount"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "allocated_amount_total", "label": _("Allocated"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "invoice_outstanding_restored_delta", "label": _("Outstanding Delta"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "voucher_gl_reversal_rows", "label": _("Reversal Rows"), "fieldtype": "Int", "width": 115},
        {"fieldname": "gl_net_balance", "label": _("GL Balance"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "gl_account_non_zero_count", "label": _("Non-Zero Accounts"), "fieldtype": "Int", "width": 130},
        {"fieldname": "actual_payment_entry_cancelled_count", "label": _("Cancelled PE"), "fieldtype": "Int", "width": 110},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "rollback_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    if filters.get("rollback"):
        conditions.append("i.rollback = %(rollback)s")
        params["rollback"] = filters.get("rollback")

    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": "NDIS Single Guarded Limited Operation Smoke Rollback Item", "width": 220},
        {"fieldname": "rollback", "label": _("Rollback"), "fieldtype": "Link", "options": "NDIS Single Guarded Limited Operation Smoke Rollback", "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 180},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 340},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 620},
        {"fieldname": "source_doctype", "label": _("Source DocType"), "fieldtype": "Data", "width": 220},
        {"fieldname": "source_name", "label": _("Source Name"), "fieldtype": "Data", "width": 240},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            i.name AS item,
            i.rollback,
            i.status,
            i.severity,
            i.category,
            i.check_label,
            i.detail,
            i.source_doctype,
            i.source_name,
            i.checked_on
        FROM `tabNDIS Single Guarded Limited Operation Smoke Rollback Item` i
        {build_where(conditions)}
        ORDER BY
            CASE i.status
                WHEN 'Blocker' THEN 1
                WHEN 'Warning' THEN 2
                WHEN 'Pass' THEN 3
                WHEN 'Info' THEN 4
                ELSE 5
            END,
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
        "data": {
            "labels": list(chart_map.keys()),
            "datasets": [{"name": "Items", "values": list(chart_map.values())}],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Items"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Pass"]), "indicator": "Green", "label": _("Pass"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Warning"]), "indicator": "Orange", "label": _("Warnings"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Blocker"]), "indicator": "Red", "label": _("Blockers"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_rollback_report(filters)

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