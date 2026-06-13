import json
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


ROLLBACK_ACK = "I_CONFIRM_PHASE10B_ROLLBACK_GUARDED_LIMITED_ADAPTER_SMOKE_PAYMENT_ENTRY"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
ROLLBACK_DOCTYPE = "NDIS Guarded Limited Adapter Smoke Rollback"
ITEM_DOCTYPE = "NDIS Guarded Limited Adapter Smoke Rollback Item"


def make_rollback_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-GUARDED-LIMITED-ADAPTER-SMOKE-ROLLBACK-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_completed_smoke():
    rows = frappe.get_all(
        "NDIS Guarded Limited Adapter Smoke",
        filters={
            "status": "Smoke Completed - Rollback Required",
            "adapter_smoke_completed": 1,
            "rollback_required": 1,
            "freeze_required_after_rollback": 1,
            "ready_for_adapter_smoke_rollback": 1,
            "payment_entry_docstatus": 1,
            "actual_payment_entry_created_count": 1,
            "submitted_journal_entry_count_today": 0,
            "purchase_invoice_count_today": 0,
            "production_batch_enabled_policy_count": 1,
            "live_posting_allowed_policy_count": 0,
        },
        fields=[
            "name",
            "smoke_id",
            "activation_gate",
            "runtime_guard",
            "target_policy_doctype",
            "target_policy",
            "target_policy_name",
            "payment_entry",
            "payment_entry_amount",
            "payment_entry_reference_count",
            "payment_entry_gl_count",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    if not rows:
        return None
    smoke = rows[0]
    if not smoke.payment_entry or int(smoke.actual_gl_created_count or 0) <= 0:
        return None
    return smoke


def existing_rollback(smoke):
    rows = frappe.get_all(
        ROLLBACK_DOCTYPE,
        filters={"smoke": smoke, "status": "Rolled Back", "rollback_completed": 1},
        fields=["name", "rollback_id"],
        limit=1,
    )
    return rows[0] if rows else None


def payment_entry_gl_count(payment_entry):
    return count_dt("GL Entry", {"voucher_type": "Payment Entry", "voucher_no": payment_entry})


def payment_entry_reference_rows(payment_entry):
    if not payment_entry:
        return []
    return frappe.get_all(
        "Payment Entry Reference",
        filters={"parent": payment_entry, "parenttype": "Payment Entry"},
        fields=["reference_doctype", "reference_name", "allocated_amount"],
        order_by="idx asc",
    )


def invoice_outstanding_snapshot(payment_entry):
    rows = payment_entry_reference_rows(payment_entry)
    result = []
    total_outstanding = 0
    total_allocated = 0
    for row in rows:
        outstanding = 0
        if row.reference_doctype == "Sales Invoice" and row.reference_name:
            outstanding = flt(frappe.db.get_value("Sales Invoice", row.reference_name, "outstanding_amount") or 0, 2)
        allocated = flt(row.allocated_amount or 0, 2)
        total_outstanding += outstanding
        total_allocated += allocated
        result.append(
            {
                "reference_doctype": row.reference_doctype,
                "reference_name": row.reference_name,
                "allocated_amount": allocated,
                "outstanding_amount": outstanding,
            }
        )
    return {
        "rows": result,
        "reference_count": len(result),
        "total_outstanding": flt(total_outstanding, 2),
        "total_allocated": flt(total_allocated, 2),
    }


def gl_snapshot(payment_entry):
    rows = frappe.db.sql(
        """
        SELECT account, party_type, party, debit, credit, is_cancelled
        FROM `tabGL Entry`
        WHERE voucher_type = 'Payment Entry'
          AND voucher_no = %(payment_entry)s
        ORDER BY account, creation, name
        """,
        {"payment_entry": payment_entry},
        as_dict=True,
    )
    total_debit = sum(flt(row.debit or 0, 2) for row in rows)
    total_credit = sum(flt(row.credit or 0, 2) for row in rows)
    account_net = defaultdict(float)
    for row in rows:
        account_net[row.account] += flt(row.debit or 0, 2) - flt(row.credit or 0, 2)
    non_zero_accounts = {
        account: flt(balance, 2)
        for account, balance in account_net.items()
        if abs(flt(balance, 2)) > 0.005
    }
    return {
        "rows": rows,
        "row_count": len(rows),
        "total_debit": flt(total_debit, 2),
        "total_credit": flt(total_credit, 2),
        "net_balance": flt(total_debit - total_credit, 2),
        "account_net": {account: flt(balance, 2) for account, balance in account_net.items()},
        "non_zero_accounts": non_zero_accounts,
        "non_zero_account_count": len(non_zero_accounts),
    }


def validate_source(smoke, guard, config):
    issues = []
    if not config["sandbox_enabled"]:
        issues.append("Sandbox posting config must remain enabled for this guarded rollback.")
    if config["production_mode"]:
        issues.append("Production mode config must remain disabled for Phase 10B.")
    if config["live_pe_enabled"]:
        issues.append("Live Payment Entry posting config must remain disabled for Phase 10B.")
    if not smoke:
        issues.append("No completed Phase 10A smoke found.")
        return issues
    existing = existing_rollback(smoke.name)
    if existing:
        issues.append(f"Phase 10B rollback already exists for this smoke: {existing.rollback_id}")
    if not smoke.payment_entry:
        issues.append("Phase 10A smoke has no Payment Entry.")
    elif not frappe.db.exists("Payment Entry", smoke.payment_entry):
        issues.append(f"Payment Entry does not exist: {smoke.payment_entry}")
    else:
        pe_docstatus = int(frappe.db.get_value("Payment Entry", smoke.payment_entry, "docstatus") or 0)
        if pe_docstatus != 1:
            issues.append(f"Payment Entry must be submitted docstatus 1 before rollback. Current: {pe_docstatus}")
    if int(smoke.actual_payment_entry_created_count or 0) != 1:
        issues.append("Phase 10A actual Payment Entry created count must be 1.")
    if int(smoke.actual_gl_created_count or 0) <= 0:
        issues.append("Phase 10A actual GL created count must be greater than 0.")
    if int(smoke.payment_entry_reference_count or 0) <= 0:
        issues.append("Phase 10A Payment Entry reference count must be greater than 0.")
    if int(smoke.payment_entry_reference_count or 0) > 3:
        issues.append("Phase 10A Payment Entry reference count must be <= 3.")
    if not (0 < flt(smoke.payment_entry_amount or 0, 2) <= 3):
        issues.append("Phase 10A Payment Entry amount must be greater than 0 and <= 3.00.")
    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must be enabled before rollback.")
    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must be 0 before rollback.")
    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today must be 0 before rollback.")
    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today must be 0 before rollback.")
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
    score = 100 - int(blockers or 0) * 25 - int(warnings or 0) * 5
    return max(0, round(score, 2))


def build_pre_items(smoke, issues, ack_ok):
    items = []
    if smoke:
        add_item(items, "Pass", "Low", "Evidence", "phase10a_smoke_exists", "Phase 10A smoke exists", f"Smoke found: {smoke.smoke_id}.", "NDIS Guarded Limited Adapter Smoke", smoke.name)
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase10a_smoke_exists", "Phase 10A smoke exists", "No completed Phase 10A smoke found.")
    if issues:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Rollback Source", "rollback_source_valid", "Rollback source valid", issue)
    else:
        add_item(items, "Pass", "Low", "Rollback Source", "rollback_source_valid", "Rollback source valid", "Phase 10A smoke is valid for rollback.")
    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {ROLLBACK_ACK}")
    return items


def add_post_items(items, result):
    if result["payment_entry_docstatus_before"] == 1 and result["payment_entry_docstatus_after"] == 2:
        add_item(items, "Pass", "Low", "Payment Entry", "payment_entry_cancelled", "Payment Entry cancelled", "Payment Entry docstatus changed from 1 to 2.", "Payment Entry", result["payment_entry"])
    else:
        add_item(items, "Blocker", "Critical", "Payment Entry", "payment_entry_cancelled", "Payment Entry cancelled", "Payment Entry docstatus did not change from 1 to 2.")
    if result["actual_payment_entry_cancelled_count"] == 1:
        add_item(items, "Pass", "Low", "Payment Entry", "actual_cancel_count", "Actual PE cancelled count is 1", "Exactly one Payment Entry was cancelled.")
    else:
        add_item(items, "Blocker", "Critical", "Payment Entry", "actual_cancel_count", "Actual PE cancelled count is 1", f"Actual cancelled count: {result['actual_payment_entry_cancelled_count']}.")
    if result["actual_gl_reversal_created_count"] > 0:
        add_item(items, "Pass", "Low", "GL", "gl_reversal_created", "GL reversal rows created", f"GL reversal delta: {result['actual_gl_reversal_created_count']}.")
    else:
        add_item(items, "Blocker", "Critical", "GL", "gl_reversal_created", "GL reversal rows created", "No GL reversal rows were detected.")
    if result["gl_account_net_zero_count"] == 0:
        add_item(items, "Pass", "Low", "GL", "account_net_zero", "GL net by account is zero", "All Payment Entry GL accounts net to zero after rollback.")
    else:
        add_item(items, "Blocker", "Critical", "GL", "account_net_zero", "GL net by account is zero", f"Non-zero GL accounts: {result['gl_account_net_zero_count']}.")
    if abs(flt(result["invoice_outstanding_restored_delta"], 2) - flt(result["allocated_amount_total"], 2)) <= 0.01:
        add_item(items, "Pass", "Low", "Outstanding", "invoice_outstanding_restored", "Invoice outstanding restored", "Outstanding amount increased by the allocated amount.")
    else:
        add_item(items, "Blocker", "Critical", "Outstanding", "invoice_outstanding_restored", "Invoice outstanding restored", f"Restored delta {result['invoice_outstanding_restored_delta']} did not match allocation {result['allocated_amount_total']}.")
    if result["payment_entry_count_before"] == result["payment_entry_count_after"]:
        add_item(items, "Pass", "Low", "Guardrail", "pe_count_unchanged", "Payment Entry count unchanged", "Rollback cancelled existing PE only.")
    else:
        add_item(items, "Blocker", "Critical", "Guardrail", "pe_count_unchanged", "Payment Entry count unchanged", "Payment Entry count changed during rollback.")
    if result["submitted_journal_entry_count_today"] == 0:
        add_item(items, "Pass", "Low", "Guardrail", "no_journal_entry", "No Journal Entry created", "Submitted JE count today remains zero.")
    else:
        add_item(items, "Blocker", "Critical", "Guardrail", "no_journal_entry", "No Journal Entry created", "Submitted JE count today is not zero.")
    if result["purchase_invoice_count_today"] == 0:
        add_item(items, "Pass", "Low", "Guardrail", "no_purchase_invoice", "No Purchase Invoice created", "Purchase Invoice count today remains zero.")
    else:
        add_item(items, "Blocker", "Critical", "Guardrail", "no_purchase_invoice", "No Purchase Invoice created", "Purchase Invoice count today is not zero.")


def create_items(doc, items):
    for item in items:
        row = frappe.new_doc(ITEM_DOCTYPE)
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


def populate_doc(doc, result, config, acknowledgement, notes, reference_snapshot, gl_snapshot_data):
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
    doc.acknowledgement_ok = int(acknowledgement == ROLLBACK_ACK)
    doc.summary_json = safe_json(result)
    doc.reference_snapshot_json = safe_json(reference_snapshot)
    doc.gl_snapshot_json = safe_json(gl_snapshot_data)
    doc.notes = notes


@frappe.whitelist()
def run_guarded_limited_adapter_smoke_rollback(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_guarded_limited_adapter_smoke_rollback")
    smoke = latest_completed_smoke()
    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }
    guard_before = guardrails()
    ack_ok = acknowledgement == ROLLBACK_ACK
    issues = validate_source(smoke, guard_before, config)
    items = build_pre_items(smoke, issues, ack_ok)
    pre_summary = summarise_items(items)
    pre_score = calculate_score(pre_summary["blocker_count"], pre_summary["warning_count"])
    allowed = bool(ack_ok and pre_summary["blocker_count"] == 0 and smoke)

    payment_entry = smoke.payment_entry if smoke else None
    pe_docstatus_before = 0
    pe_status_before = None
    pe_amount = 0
    pe_ref_count = 0
    pe_gl_count_before = 0
    outstanding_before = {"rows": [], "reference_count": 0, "total_outstanding": 0, "total_allocated": 0}
    gl_before = {"rows": [], "row_count": 0, "total_debit": 0, "total_credit": 0, "net_balance": 0, "non_zero_account_count": 0}
    if payment_entry and frappe.db.exists("Payment Entry", payment_entry):
        pe = frappe.get_doc("Payment Entry", payment_entry)
        pe_docstatus_before = int(pe.docstatus or 0)
        pe_status_before = pe.status
        pe_amount = flt(pe.paid_amount or pe.received_amount or 0, 2)
        pe_ref_count = count_dt("Payment Entry Reference", {"parent": payment_entry, "parenttype": "Payment Entry"})
        pe_gl_count_before = payment_entry_gl_count(payment_entry)
        outstanding_before = invoice_outstanding_snapshot(payment_entry)
        gl_before = gl_snapshot(payment_entry)

    base_result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Needs Review",
        "rollback_status": "Needs Review",
        "rollback_completed": 0,
        "freeze_required_after_rollback": 0,
        "ready_for_adapter_smoke_freeze": 0,
        "phase10a_smoke_verified": 1 if smoke else 0,
        "phase9z_activation_gate_verified": 1 if smoke else 0,
        "smoke": smoke.name if smoke else None,
        "activation_gate": smoke.activation_gate if smoke else None,
        "runtime_guard": smoke.runtime_guard if smoke else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": smoke.target_policy if smoke else None,
        "target_policy_name": smoke.target_policy_name if smoke else None,
        "current_target_policy_enabled": get_flag(POLICY_DOCTYPE, smoke.target_policy, "production_batch_enabled") if smoke else 0,
        "current_target_policy_live": get_flag(POLICY_DOCTYPE, smoke.target_policy, "live_posting_allowed") if smoke else 0,
        "payment_entry": payment_entry,
        "payment_entry_docstatus_before": pe_docstatus_before,
        "payment_entry_status_before": pe_status_before,
        "payment_entry_amount": pe_amount,
        "payment_entry_reference_count": pe_ref_count,
        "payment_entry_gl_count_before": pe_gl_count_before,
        "invoice_reference_count": int(outstanding_before["reference_count"] or 0),
        "allocated_amount_total": flt(outstanding_before["total_allocated"] or 0, 2),
        "invoice_outstanding_before": flt(outstanding_before["total_outstanding"] or 0, 2),
        "gl_net_debit": flt(gl_before["total_debit"] or 0, 2),
        "gl_net_credit": flt(gl_before["total_credit"] or 0, 2),
        "gl_net_balance": flt(gl_before["net_balance"] or 0, 2),
        "gl_account_net_zero_count": int(gl_before["non_zero_account_count"] or 0),
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_gl_total_count_before": guard_before["payment_entry_gl_count"],
        "actual_payment_entry_created_count": 0,
        "actual_payment_entry_cancelled_count": 0,
        "actual_gl_reversal_created_count": 0,
        "submitted_journal_entry_count_today": guard_before["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_before["purchase_invoice_count_today"],
        "production_batch_enabled_policy_count": guard_before["production_batch_enabled_policy_count"],
        "live_posting_allowed_policy_count": guard_before["live_posting_allowed_policy_count"],
        "rollback_score": pre_score,
        **pre_summary,
        "items": items,
        "issues": issues,
        "guardrails_before": guard_before,
        "reference_snapshot_before": outstanding_before,
        "gl_snapshot_before": gl_before,
        "config": config,
        "required_acknowledgement": ROLLBACK_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 10B rolls back the Phase 10A smoke Payment Entry only. Completed rollback requires freeze.",
    }
    if int(dry_run or 0):
        return {**base_result, "guardrails_after": guardrails()}

    if not allowed:
        doc = frappe.new_doc(ROLLBACK_DOCTYPE)
        doc.rollback_id = make_rollback_id()
        populate_doc(doc, base_result, config, acknowledgement, notes, outstanding_before, gl_before)
        doc.insert(ignore_permissions=True)
        create_items(doc, items)
        frappe.db.commit()
        return {**base_result, "created": True, "rollback": doc.name, "rollback_id": doc.rollback_id, "guardrails_after": guardrails()}

    pe = frappe.get_doc("Payment Entry", payment_entry)
    pe.cancel()

    pe_after = frappe.get_doc("Payment Entry", payment_entry)
    outstanding_after = invoice_outstanding_snapshot(payment_entry)
    gl_after = gl_snapshot(payment_entry)
    guard_after = guardrails()
    pe_gl_count_after = payment_entry_gl_count(payment_entry)
    gl_reversal_count = pe_gl_count_after - pe_gl_count_before
    outstanding_delta = flt(outstanding_after["total_outstanding"] - outstanding_before["total_outstanding"], 2)

    result = {
        **base_result,
        "status": "Rolled Back",
        "rollback_status": "Guarded Limited Adapter Smoke Rolled Back - Freeze Required",
        "rollback_completed": 1,
        "freeze_required_after_rollback": 1,
        "ready_for_adapter_smoke_freeze": 1,
        "payment_entry_cancelled_verified": 1 if pe_docstatus_before == 1 and int(pe_after.docstatus or 0) == 2 else 0,
        "payment_entry_gl_reversal_verified": 1 if gl_reversal_count > 0 else 0,
        "gl_net_zero_verified": 1 if int(gl_after["non_zero_account_count"] or 0) == 0 else 0,
        "invoice_outstanding_restored_verified": 1 if abs(outstanding_delta - flt(outstanding_before["total_allocated"], 2)) <= 0.01 else 0,
        "no_journal_entry_verified": 1 if guard_after["submitted_journal_entry_count_today"] == 0 else 0,
        "no_purchase_invoice_verified": 1 if guard_after["purchase_invoice_count_today"] == 0 else 0,
        "controlled_policy_enabled_verified": 1 if guard_after["production_batch_enabled_policy_count"] == 1 else 0,
        "live_posting_blocked_verified": 1 if guard_after["live_posting_allowed_policy_count"] == 0 else 0,
        "payment_entry_docstatus_after": int(pe_after.docstatus or 0),
        "payment_entry_status_after": pe_after.status,
        "payment_entry_gl_count_after": pe_gl_count_after,
        "payment_entry_gl_reversal_count": gl_reversal_count,
        "invoice_outstanding_after": flt(outstanding_after["total_outstanding"], 2),
        "invoice_outstanding_restored_delta": outstanding_delta,
        "gl_net_debit": flt(gl_after["total_debit"], 2),
        "gl_net_credit": flt(gl_after["total_credit"], 2),
        "gl_net_balance": flt(gl_after["net_balance"], 2),
        "gl_account_net_zero_count": int(gl_after["non_zero_account_count"] or 0),
        "payment_entry_count_after": guard_after["payment_entry_count"],
        "payment_entry_gl_total_count_after": guard_after["payment_entry_gl_count"],
        "actual_payment_entry_created_count": 0,
        "actual_payment_entry_cancelled_count": 1 if pe_docstatus_before == 1 and int(pe_after.docstatus or 0) == 2 else 0,
        "actual_gl_reversal_created_count": gl_reversal_count,
        "submitted_journal_entry_count_today": guard_after["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_after["purchase_invoice_count_today"],
        "production_batch_enabled_policy_count": guard_after["production_batch_enabled_policy_count"],
        "live_posting_allowed_policy_count": guard_after["live_posting_allowed_policy_count"],
        "reference_snapshot_after": outstanding_after,
        "gl_snapshot_after": gl_after,
        "guardrails_after": guard_after,
    }
    add_post_items(items, result)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    if item_summary["blocker_count"]:
        result["status"] = "Blocked"
        result["rollback_status"] = "Blocked"
        result["rollback_completed"] = 0
        result["ready_for_adapter_smoke_freeze"] = 0
    result.update(item_summary)
    result["rollback_score"] = score
    result["items"] = items

    doc = frappe.new_doc(ROLLBACK_DOCTYPE)
    doc.rollback_id = make_rollback_id()
    populate_doc(doc, result, config, acknowledgement, notes, {"before": outstanding_before, "after": outstanding_after}, {"before": gl_before, "after": gl_after})
    doc.insert(ignore_permissions=True)
    create_items(doc, items)
    frappe.db.commit()
    return {**result, "created": True, "rollback": doc.name, "rollback_id": doc.rollback_id}


@frappe.whitelist()
def cancel_guarded_limited_adapter_smoke_rollback_audit(rollback, reason=None):
    assert_action("cancel_guarded_limited_adapter_smoke_rollback_audit")
    if not frappe.db.exists(ROLLBACK_DOCTYPE, rollback):
        frappe.throw(_("Rollback audit not found: {0}").format(rollback))
    doc = frappe.get_doc(ROLLBACK_DOCTYPE, rollback)
    if doc.status == "Cancelled":
        return {"rollback": rollback, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.rollback_completed or 0) or int(doc.actual_payment_entry_cancelled_count or 0):
        frappe.throw(_("Cannot cancel a completed Phase 10B rollback. Freeze this rollback instead."))
    frappe.db.set_value(
        ROLLBACK_DOCTYPE,
        rollback,
        {
            "status": "Cancelled",
            "rollback_status": "Cancelled",
            "rollback_completed": 0,
            "freeze_required_after_rollback": 0,
            "ready_for_adapter_smoke_freeze": 0,
            "gl_account_net_zero_count": 0,
            "actual_payment_entry_created_count": 0,
            "actual_payment_entry_cancelled_count": 0,
            "actual_gl_reversal_created_count": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 10B no-ack rollback audit cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{ITEM_DOCTYPE}` SET status = 'Cancelled' WHERE rollback = %(rollback)s", {"rollback": rollback})
    frappe.db.commit()
    return {"rollback": rollback, "status": "Cancelled", "note": "No-ack rollback audit cancelled only. No accounting movement occurred in the audit record."}


@frappe.whitelist()
def quick_guarded_limited_adapter_smoke_rollback_summary(limit=20):
    rollbacks = frappe.get_all(
        ROLLBACK_DOCTYPE,
        fields=[
            "name",
            "rollback_id",
            "status",
            "rollback_status",
            "rollback_completed",
            "freeze_required_after_rollback",
            "ready_for_adapter_smoke_freeze",
            "smoke",
            "payment_entry",
            "payment_entry_docstatus_before",
            "payment_entry_docstatus_after",
            "payment_entry_amount",
            "payment_entry_reference_count",
            "payment_entry_gl_reversal_count",
            "invoice_outstanding_restored_delta",
            "gl_account_net_zero_count",
            "actual_payment_entry_cancelled_count",
            "actual_gl_reversal_created_count",
            "production_batch_enabled_policy_count",
            "live_posting_allowed_policy_count",
            "rollback_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(
        ITEM_DOCTYPE,
        fields=["name", "rollback", "status", "severity", "category", "check_label", "detail", "source_doctype", "source_name"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "rollbacks": rollbacks,
        "items": items,
        "required_acknowledgement": ROLLBACK_ACK,
        "guardrails": guardrails(),
        "note": "Phase 10B guarded limited adapter smoke rollback summary. Completed rollback requires freeze.",
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
            r.freeze_required_after_rollback,
            r.ready_for_adapter_smoke_freeze,
            r.smoke,
            r.payment_entry,
            r.payment_entry_docstatus_before,
            r.payment_entry_docstatus_after,
            r.payment_entry_amount,
            r.payment_entry_reference_count,
            r.payment_entry_gl_reversal_count,
            r.invoice_outstanding_restored_delta,
            r.gl_account_net_zero_count,
            r.actual_payment_entry_cancelled_count,
            r.actual_gl_reversal_created_count,
            r.production_batch_enabled_policy_count,
            r.live_posting_allowed_policy_count,
            r.rollback_score,
            r.checked_on,
            %(currency)s AS currency
        FROM `tab{ROLLBACK_DOCTYPE}` r
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
                {"name": "PE Cancelled", "values": [int(row.actual_payment_entry_cancelled_count or 0) for row in data[:20]]},
                {"name": "GL Reversal Rows", "values": [int(row.actual_gl_reversal_created_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Rollbacks"), "datatype": "Int"},
        {"value": sum(int(row.rollback_completed or 0) for row in data), "indicator": "Green", "label": _("Completed"), "datatype": "Int"},
        {"value": sum(int(row.actual_payment_entry_cancelled_count or 0) for row in data), "indicator": "Green", "label": _("PE Cancelled"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_reversal_created_count or 0) for row in data), "indicator": "Orange", "label": _("GL Reversal Rows"), "datatype": "Int"},
        {"value": sum(int(row.gl_account_net_zero_count or 0) for row in data), "indicator": "Red", "label": _("Non-Zero GL Accounts"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def rollback_columns():
    return [
        {"fieldname": "rollback", "label": _("Rollback"), "fieldtype": "Link", "options": ROLLBACK_DOCTYPE, "width": 220},
        {"fieldname": "rollback_id", "label": _("Rollback ID"), "fieldtype": "Data", "width": 450},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "rollback_status", "label": _("Rollback Status"), "fieldtype": "Data", "width": 340},
        {"fieldname": "rollback_completed", "label": _("Completed"), "fieldtype": "Check", "width": 90},
        {"fieldname": "freeze_required_after_rollback", "label": _("Freeze Required"), "fieldtype": "Check", "width": 120},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "payment_entry_docstatus_before", "label": _("PE Before"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_docstatus_after", "label": _("PE After"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_amount", "label": _("PE Amount"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "payment_entry_reference_count", "label": _("PE Refs"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_gl_reversal_count", "label": _("GL Reversal"), "fieldtype": "Int", "width": 110},
        {"fieldname": "invoice_outstanding_restored_delta", "label": _("Outstanding Restored"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "gl_account_net_zero_count", "label": _("Non-Zero GL Accounts"), "fieldtype": "Int", "width": 150},
        {"fieldname": "actual_payment_entry_cancelled_count", "label": _("PE Cancelled"), "fieldtype": "Int", "width": 110},
        {"fieldname": "actual_gl_reversal_created_count", "label": _("GL Reversal Rows"), "fieldtype": "Int", "width": 130},
        {"fieldname": "production_batch_enabled_policy_count", "label": _("Enabled Policies"), "fieldtype": "Int", "width": 120},
        {"fieldname": "live_posting_allowed_policy_count", "label": _("Live Policies"), "fieldtype": "Int", "width": 110},
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
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": ITEM_DOCTYPE, "width": 220},
        {"fieldname": "rollback", "label": _("Rollback"), "fieldtype": "Link", "options": ROLLBACK_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 170},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 320},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 560},
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
        FROM `tab{ITEM_DOCTYPE}` i
        {build_where(conditions)}
        ORDER BY
            CASE i.status
                WHEN 'Blocker' THEN 1
                WHEN 'Warning' THEN 2
                WHEN 'Info' THEN 3
                WHEN 'Pass' THEN 4
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
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Items", "values": list(chart_map.values())}]}, "type": "bar"}
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
