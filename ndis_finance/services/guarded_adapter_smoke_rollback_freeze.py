import json
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


FREEZE_ACK = "I_CONFIRM_PHASE10C_FREEZE_GUARDED_ADAPTER_SMOKE_ROLLBACK_EVIDENCE_NO_POSTING"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
FREEZE_DOCTYPE = "NDIS Guarded Adapter Smoke Rollback Freeze"
ITEM_DOCTYPE = "NDIS Guarded Adapter Smoke Rollback Freeze Item"
ROLLBACK_DOCTYPE = "NDIS Guarded Limited Adapter Smoke Rollback"


def make_freeze_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-GUARDED-ADAPTER-SMOKE-ROLLBACK-FREEZE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_rollback():
    rows = frappe.get_all(
        ROLLBACK_DOCTYPE,
        filters={
            "status": "Rolled Back",
            "rollback_completed": 1,
            "freeze_required_after_rollback": 1,
            "ready_for_adapter_smoke_freeze": 1,
            "phase10a_smoke_verified": 1,
            "payment_entry_cancelled_verified": 1,
            "payment_entry_gl_reversal_verified": 1,
            "gl_net_zero_verified": 1,
            "invoice_outstanding_restored_verified": 1,
            "no_journal_entry_verified": 1,
            "no_purchase_invoice_verified": 1,
            "controlled_policy_enabled_verified": 1,
            "live_posting_blocked_verified": 1,
            "payment_entry_docstatus_after": 2,
            "actual_payment_entry_created_count": 0,
            "actual_payment_entry_cancelled_count": 1,
            "gl_account_net_zero_count": 0,
            "submitted_journal_entry_count_today": 0,
            "purchase_invoice_count_today": 0,
            "production_batch_enabled_policy_count": 1,
            "live_posting_allowed_policy_count": 0,
        },
        fields=[
            "name",
            "rollback_id",
            "smoke",
            "activation_gate",
            "runtime_guard",
            "target_policy_doctype",
            "target_policy",
            "target_policy_name",
            "payment_entry",
            "payment_entry_docstatus_before",
            "payment_entry_docstatus_after",
            "payment_entry_status_before",
            "payment_entry_status_after",
            "payment_entry_amount",
            "payment_entry_reference_count",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "payment_entry_gl_reversal_count",
            "invoice_reference_count",
            "allocated_amount_total",
            "invoice_outstanding_restored_delta",
            "gl_net_debit",
            "gl_net_credit",
            "gl_net_balance",
            "gl_account_net_zero_count",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_total_count_before",
            "payment_entry_gl_total_count_after",
            "actual_payment_entry_created_count",
            "actual_payment_entry_cancelled_count",
            "actual_gl_reversal_created_count",
            "production_batch_enabled_policy_count",
            "live_posting_allowed_policy_count",
            "rollback_score",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    if not rows:
        return None
    rollback = rows[0]
    if int(rollback.actual_gl_reversal_created_count or 0) <= 0:
        return None
    return rollback


def existing_freeze(rollback):
    rows = frappe.get_all(
        FREEZE_DOCTYPE,
        filters={"rollback": rollback, "status": "Frozen", "rollback_freeze_allowed": 1},
        fields=["name", "freeze_id"],
        limit=1,
    )
    return rows[0] if rows else None


def payment_entry_reference_snapshot(payment_entry):
    rows = frappe.get_all(
        "Payment Entry Reference",
        filters={"parent": payment_entry, "parenttype": "Payment Entry"},
        fields=["reference_doctype", "reference_name", "allocated_amount"],
        order_by="idx asc",
    )
    result = []
    total_allocated = 0
    for row in rows:
        outstanding = 0
        if row.reference_doctype == "Sales Invoice" and row.reference_name:
            outstanding = flt(frappe.db.get_value("Sales Invoice", row.reference_name, "outstanding_amount") or 0, 2)
        allocated = flt(row.allocated_amount or 0, 2)
        total_allocated += allocated
        result.append(
            {
                "reference_doctype": row.reference_doctype,
                "reference_name": row.reference_name,
                "allocated_amount": allocated,
                "current_outstanding_amount": outstanding,
            }
        )
    return {"rows": result, "reference_count": len(result), "total_allocated": flt(total_allocated, 2)}


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


def validate_source(rollback, guard, config, pe_docstatus, pe_status, ref_snapshot, gl):
    issues = []
    if not config["sandbox_enabled"]:
        issues.append("Sandbox posting config must remain enabled for this guarded freeze.")
    if config["production_mode"]:
        issues.append("Production mode config must remain disabled for Phase 10C.")
    if config["live_pe_enabled"]:
        issues.append("Live Payment Entry posting config must remain disabled for Phase 10C.")
    if not rollback:
        issues.append("No completed Phase 10B rollback found.")
        return issues
    existing = existing_freeze(rollback.name)
    if existing:
        issues.append(f"Phase 10C freeze already exists for this rollback: {existing.freeze_id}")
    if not rollback.smoke or not frappe.db.exists("NDIS Guarded Limited Adapter Smoke", rollback.smoke):
        issues.append("Linked Phase 10A smoke does not exist.")
    if not rollback.payment_entry or not frappe.db.exists("Payment Entry", rollback.payment_entry):
        issues.append("Rollback Payment Entry does not exist.")
    if pe_docstatus != 2:
        issues.append(f"Payment Entry must be cancelled docstatus 2. Current: {pe_docstatus}")
    if pe_status != "Cancelled":
        issues.append(f"Payment Entry status must be Cancelled. Current: {pe_status}")
    if int(rollback.payment_entry_docstatus_before or 0) != 1:
        issues.append("Rollback evidence must show PE docstatus before = 1.")
    if int(rollback.payment_entry_docstatus_after or 0) != 2:
        issues.append("Rollback evidence must show PE docstatus after = 2.")
    if int(rollback.actual_payment_entry_created_count or 0) != 0:
        issues.append("Rollback must not create Payment Entry.")
    if int(rollback.actual_payment_entry_cancelled_count or 0) != 1:
        issues.append("Rollback must cancel exactly one Payment Entry.")
    if int(rollback.actual_gl_reversal_created_count or 0) <= 0:
        issues.append("Rollback must create GL reversal rows.")
    if int(rollback.gl_account_net_zero_count or 0) != 0:
        issues.append("Rollback evidence must show GL account net zero count = 0.")
    if int(gl.get("non_zero_account_count") or 0) != 0:
        issues.append("Current GL snapshot has non-zero account balances.")
    if abs(flt(gl.get("net_balance") or 0, 2)) > 0.005:
        issues.append("Current GL snapshot net balance is not zero.")
    if int(ref_snapshot.get("reference_count") or 0) != int(rollback.invoice_reference_count or 0):
        issues.append("Current reference count does not match rollback evidence.")
    if abs(flt(ref_snapshot.get("total_allocated") or 0, 2) - flt(rollback.allocated_amount_total or 0, 2)) > 0.01:
        issues.append("Current allocated amount does not match rollback evidence.")
    if abs(flt(rollback.invoice_outstanding_restored_delta or 0, 2) - flt(rollback.allocated_amount_total or 0, 2)) > 0.01:
        issues.append("Rollback outstanding restored delta must match allocated amount.")
    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must remain enabled.")
    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must remain 0.")
    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today must be 0.")
    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today must be 0.")
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


def build_items(rollback, issues, ack_ok, pe_docstatus, gl):
    items = []
    if rollback:
        add_item(items, "Pass", "Low", "Evidence", "phase10b_rollback_exists", "Phase 10B rollback exists", f"Rollback found: {rollback.rollback_id}.", ROLLBACK_DOCTYPE, rollback.name)
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase10b_rollback_exists", "Phase 10B rollback exists", "No completed Phase 10B rollback found.")
    if not issues:
        add_item(items, "Pass", "Low", "Freeze Source", "freeze_source_valid", "Freeze source valid", "Phase 10B rollback evidence is valid for freeze.")
    else:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Freeze Source", "freeze_source_valid", "Freeze source valid", issue)
    if pe_docstatus == 2:
        add_item(items, "Pass", "Low", "Payment Entry", "payment_entry_cancelled", "Payment Entry cancelled", "Payment Entry is cancelled.")
    else:
        add_item(items, "Blocker", "Critical", "Payment Entry", "payment_entry_cancelled", "Payment Entry cancelled", f"Payment Entry docstatus is {pe_docstatus}.")
    if int(gl.get("non_zero_account_count") or 0) == 0:
        add_item(items, "Pass", "Low", "GL", "gl_net_zero", "GL net zero verified", "All accounts net to zero for the smoke Payment Entry.")
    else:
        add_item(items, "Blocker", "Critical", "GL", "gl_net_zero", "GL net zero verified", safe_json(gl.get("non_zero_accounts")))
    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {FREEZE_ACK}")
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
        row = frappe.new_doc(ITEM_DOCTYPE)
        row.freeze = doc.name
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


@frappe.whitelist()
def run_guarded_adapter_smoke_rollback_freeze(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_guarded_adapter_smoke_rollback_freeze")

    rollback = latest_rollback()
    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }
    guard_before = guardrails()
    ack_ok = acknowledgement == FREEZE_ACK

    pe_docstatus = 0
    pe_status = None
    ref_snapshot = {"rows": [], "reference_count": 0, "total_allocated": 0}
    gl = {"rows": [], "row_count": 0, "total_debit": 0, "total_credit": 0, "net_balance": 0, "non_zero_account_count": 0}

    if rollback and rollback.payment_entry and frappe.db.exists("Payment Entry", rollback.payment_entry):
        pe_doc = frappe.get_doc("Payment Entry", rollback.payment_entry)
        pe_docstatus = int(pe_doc.docstatus or 0)
        pe_status = pe_doc.status
        ref_snapshot = payment_entry_reference_snapshot(rollback.payment_entry)
        gl = gl_snapshot(rollback.payment_entry)

    issues = validate_source(rollback, guard_before, config, pe_docstatus, pe_status, ref_snapshot, gl)
    items = build_items(rollback, issues, ack_ok, pe_docstatus, gl)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    allowed = bool(ack_ok and item_summary["blocker_count"] == 0 and rollback)

    current_enabled = get_flag(POLICY_DOCTYPE, rollback.target_policy, "production_batch_enabled") if rollback else 0
    current_live = get_flag(POLICY_DOCTYPE, rollback.target_policy, "live_posting_allowed") if rollback else 0
    guard_after = guardrails()
    no_new_movement = int(
        guard_before["payment_entry_count"] == guard_after["payment_entry_count"]
        and guard_before["payment_entry_gl_count"] == guard_after["payment_entry_gl_count"]
        and guard_before["submitted_journal_entry_count_today"] == guard_after["submitted_journal_entry_count_today"]
        and guard_before["purchase_invoice_count_today"] == guard_after["purchase_invoice_count_today"]
    )

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Frozen" if allowed else "Needs Review",
        "freeze_status": "Guarded Limited Adapter Smoke Rollback Evidence Frozen" if allowed else "Needs Review",
        "rollback_freeze_allowed": int(allowed),
        "ready_for_final_guarded_adapter_policy_review": int(allowed),
        "phase10b_rollback_verified": 1 if rollback else 0,
        "phase10a_smoke_verified": 1 if rollback and rollback.smoke else 0,
        "phase9z_activation_gate_verified": 1 if rollback and rollback.activation_gate else 0,
        "payment_entry_cancelled_verified": 1 if pe_docstatus == 2 else 0,
        "payment_entry_gl_reversal_verified": 1 if rollback and int(rollback.actual_gl_reversal_created_count or 0) > 0 else 0,
        "gl_net_zero_verified": 1 if int(gl.get("non_zero_account_count") or 0) == 0 else 0,
        "invoice_outstanding_restored_verified": 1 if rollback and abs(flt(rollback.invoice_outstanding_restored_delta or 0, 2) - flt(rollback.allocated_amount_total or 0, 2)) <= 0.01 else 0,
        "no_new_accounting_movement_verified": no_new_movement,
        "controlled_policy_enabled_verified": 1 if current_enabled == 1 else 0,
        "live_posting_blocked_verified": 1 if current_live == 0 else 0,
        "rollback": rollback.name if rollback else None,
        "smoke": rollback.smoke if rollback else None,
        "activation_gate": rollback.activation_gate if rollback else None,
        "runtime_guard": rollback.runtime_guard if rollback else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": rollback.target_policy if rollback else None,
        "target_policy_name": rollback.target_policy_name if rollback else None,
        "current_target_policy_enabled": current_enabled,
        "current_target_policy_live": current_live,
        "production_batch_enabled_policy_count": guard_before["production_batch_enabled_policy_count"],
        "live_posting_allowed_policy_count": guard_before["live_posting_allowed_policy_count"],
        "payment_entry": rollback.payment_entry if rollback else None,
        "payment_entry_docstatus": pe_docstatus,
        "payment_entry_status": pe_status,
        "payment_entry_amount": flt(rollback.payment_entry_amount or 0, 2) if rollback else 0,
        "payment_entry_reference_count": int(ref_snapshot.get("reference_count") or 0),
        "payment_entry_gl_row_count": int(gl.get("row_count") or 0),
        "payment_entry_gl_reversal_count": int(rollback.payment_entry_gl_reversal_count or 0) if rollback else 0,
        "invoice_reference_count": int(ref_snapshot.get("reference_count") or 0),
        "allocated_amount_total": flt(ref_snapshot.get("total_allocated") or 0, 2),
        "invoice_outstanding_restored_delta": flt(rollback.invoice_outstanding_restored_delta or 0, 2) if rollback else 0,
        "gl_net_debit": flt(gl.get("total_debit") or 0, 2),
        "gl_net_credit": flt(gl.get("total_credit") or 0, 2),
        "gl_net_balance": flt(gl.get("net_balance") or 0, 2),
        "gl_account_non_zero_count": int(gl.get("non_zero_account_count") or 0),
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guard_after["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
        "actual_payment_entry_created_count": 0,
        "actual_payment_entry_cancelled_count": 0,
        "actual_gl_created_count": 0,
        "submitted_journal_entry_count_today": guard_before["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_before["purchase_invoice_count_today"],
        "freeze_score": score,
        **item_summary,
        "items": items,
        "issues": issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "reference_snapshot": ref_snapshot,
        "gl_snapshot": gl,
        "config": config,
        "required_acknowledgement": FREEZE_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 10C freezes Phase 10A/10B evidence only. No accounting movement is created.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["freeze_status"] = "Needs Review"
        result["rollback_freeze_allowed"] = 0
        result["ready_for_final_guarded_adapter_policy_review"] = 0
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
    doc.reference_snapshot_json = safe_json(ref_snapshot)
    doc.gl_snapshot_json = safe_json(gl)
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    create_items(doc, items)
    frappe.db.commit()

    return {**result, "created": True, "freeze": doc.name, "freeze_id": doc.freeze_id, "guardrails_after": guardrails()}


@frappe.whitelist()
def cancel_guarded_adapter_smoke_rollback_freeze_audit(freeze, reason=None):
    assert_action("cancel_guarded_adapter_smoke_rollback_freeze_audit")
    if not frappe.db.exists(FREEZE_DOCTYPE, freeze):
        frappe.throw(_("Freeze audit not found: {0}").format(freeze))
    doc = frappe.get_doc(FREEZE_DOCTYPE, freeze)
    if doc.status == "Cancelled":
        return {"freeze": freeze, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.rollback_freeze_allowed or 0):
        frappe.throw(_("Cannot cancel a completed Phase 10C freeze. Create a superseding review if required."))
    frappe.db.set_value(
        FREEZE_DOCTYPE,
        freeze,
        {
            "status": "Cancelled",
            "freeze_status": "Cancelled",
            "rollback_freeze_allowed": 0,
            "ready_for_final_guarded_adapter_policy_review": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 10C no-ack freeze audit cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(
        f"""
        UPDATE `tab{ITEM_DOCTYPE}`
        SET status = 'Cancelled'
        WHERE freeze = %(freeze)s
        """,
        {"freeze": freeze},
    )
    frappe.db.commit()
    return {"freeze": freeze, "status": "Cancelled", "note": "No-ack freeze audit cancelled only. No accounting movement occurred."}


@frappe.whitelist()
def quick_guarded_adapter_smoke_rollback_freeze_summary(limit=20):
    freezes = frappe.get_all(
        FREEZE_DOCTYPE,
        fields=[
            "name",
            "freeze_id",
            "status",
            "freeze_status",
            "rollback_freeze_allowed",
            "ready_for_final_guarded_adapter_policy_review",
            "rollback",
            "smoke",
            "payment_entry",
            "payment_entry_docstatus",
            "payment_entry_status",
            "payment_entry_amount",
            "payment_entry_reference_count",
            "payment_entry_gl_row_count",
            "payment_entry_gl_reversal_count",
            "gl_account_non_zero_count",
            "no_new_accounting_movement_verified",
            "production_batch_enabled_policy_count",
            "live_posting_allowed_policy_count",
            "freeze_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(
        ITEM_DOCTYPE,
        fields=["name", "freeze", "status", "severity", "category", "check_label", "detail", "source_doctype", "source_name"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "freezes": freezes,
        "items": items,
        "required_acknowledgement": FREEZE_ACK,
        "guardrails": guardrails(),
        "note": "Phase 10C guarded adapter smoke rollback freeze summary. No accounting movement.",
    }


def execute_freeze_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("f.status = %(status)s")
        params["status"] = filters.get("status")
    data = frappe.db.sql(
        f"""
        SELECT
            f.name AS freeze,
            f.freeze_id,
            f.status,
            f.freeze_status,
            f.rollback_freeze_allowed,
            f.ready_for_final_guarded_adapter_policy_review,
            f.rollback,
            f.smoke,
            f.payment_entry,
            f.payment_entry_docstatus,
            f.payment_entry_status,
            f.payment_entry_amount,
            f.payment_entry_reference_count,
            f.payment_entry_gl_row_count,
            f.gl_account_non_zero_count,
            f.no_new_accounting_movement_verified,
            f.production_batch_enabled_policy_count,
            f.live_posting_allowed_policy_count,
            f.freeze_score,
            f.checked_on,
            %(currency)s AS currency
        FROM `tab{FREEZE_DOCTYPE}` f
        {build_where(conditions)}
        ORDER BY f.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.freeze_id for row in data[:20]],
            "datasets": [
                {"name": "Frozen", "values": [int(row.rollback_freeze_allowed or 0) for row in data[:20]]},
                {"name": "Non-Zero GL Accounts", "values": [int(row.gl_account_non_zero_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Freezes"), "datatype": "Int"},
        {"value": sum(int(row.rollback_freeze_allowed or 0) for row in data), "indicator": "Green", "label": _("Frozen"), "datatype": "Int"},
        {"value": sum(int(row.ready_for_final_guarded_adapter_policy_review or 0) for row in data), "indicator": "Green", "label": _("Ready Review"), "datatype": "Int"},
        {"value": sum(int(row.gl_account_non_zero_count or 0) for row in data), "indicator": "Red", "label": _("Non-Zero GL Accounts"), "datatype": "Int"},
    ]
    return freeze_columns(), data, None, chart, summary


def freeze_columns():
    return [
        {"fieldname": "freeze", "label": _("Freeze"), "fieldtype": "Link", "options": FREEZE_DOCTYPE, "width": 220},
        {"fieldname": "freeze_id", "label": _("Freeze ID"), "fieldtype": "Data", "width": 440},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "freeze_status", "label": _("Freeze Status"), "fieldtype": "Data", "width": 340},
        {"fieldname": "rollback_freeze_allowed", "label": _("Frozen"), "fieldtype": "Check", "width": 80},
        {"fieldname": "ready_for_final_guarded_adapter_policy_review", "label": _("Ready Review"), "fieldtype": "Check", "width": 110},
        {"fieldname": "rollback", "label": _("Phase 10B Rollback"), "fieldtype": "Link", "options": ROLLBACK_DOCTYPE, "width": 220},
        {"fieldname": "smoke", "label": _("Phase 10A Smoke"), "fieldtype": "Link", "options": "NDIS Guarded Limited Adapter Smoke", "width": 220},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "payment_entry_docstatus", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 100},
        {"fieldname": "payment_entry_status", "label": _("PE Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "payment_entry_amount", "label": _("PE Amount"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "payment_entry_reference_count", "label": _("PE Refs"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_gl_row_count", "label": _("PE GL Rows"), "fieldtype": "Int", "width": 100},
        {"fieldname": "gl_account_non_zero_count", "label": _("Non-Zero GL Accounts"), "fieldtype": "Int", "width": 150},
        {"fieldname": "no_new_accounting_movement_verified", "label": _("No New Movement"), "fieldtype": "Check", "width": 130},
        {"fieldname": "production_batch_enabled_policy_count", "label": _("Enabled Policies"), "fieldtype": "Int", "width": 120},
        {"fieldname": "live_posting_allowed_policy_count", "label": _("Live Policies"), "fieldtype": "Int", "width": 110},
        {"fieldname": "freeze_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("freeze"):
        conditions.append("i.freeze = %(freeze)s")
        params["freeze"] = filters.get("freeze")
    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")
    data = frappe.db.sql(
        f"""
        SELECT
            i.name AS item,
            i.freeze,
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
    return item_columns(), data, None, chart, summary


def item_columns():
    return [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": ITEM_DOCTYPE, "width": 220},
        {"fieldname": "freeze", "label": _("Freeze"), "fieldtype": "Link", "options": FREEZE_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 170},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 320},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 560},
        {"fieldname": "source_doctype", "label": _("Source DocType"), "fieldtype": "Data", "width": 220},
        {"fieldname": "source_name", "label": _("Source Name"), "fieldtype": "Data", "width": 240},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_freeze_report(filters)
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
