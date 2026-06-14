import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


FREEZE_ACK = "I_CONFIRM_PHASE10L_FREEZE_SINGLE_GUARDED_OPERATION_SMOKE_ROLLBACK_EVIDENCE"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
FREEZE_DOCTYPE = "NDIS Single Guarded Op Smoke Rollback Freeze"
FREEZE_ITEM_DOCTYPE = "NDIS Single Guarded Op Smoke Rollback Freeze Item"


def make_freeze_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-SINGLE-GUARDED-OP-SMOKE-ROLLBACK-FREEZE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_rollback():
    rows = frappe.get_all(
        "NDIS Single Guarded Limited Operation Smoke Rollback",
        filters={
            "status": "Rollback Completed",
            "rollback_status": "Single Guarded Limited Operation Smoke Rolled Back",
            "rollback_completed": 1,
            "ready_for_single_operation_smoke_freeze": 1,
            "freeze_required_after_rollback": 1,
            "payment_entry_cancelled_verified": 1,
            "invoice_outstanding_restored_verified": 1,
            "voucher_gl_reversal_verified": 1,
            "gl_net_zero_verified": 1,
            "policy_state_preserved_verified": 1,
            "policy_mutation_performed": 0,
            "actual_policy_mutation_count": 0,
            "phase10j_smoke_verified": 1,
            "phase10i_gate_verified": 1,
            "controlled_policy_enabled_verified": 1,
            "live_posting_blocked_verified": 1,
            "payment_entry_docstatus_after": 2,
            "payment_entry_status_after": "Cancelled",
            "payment_entry_reference_count": 3,
            "allocated_amount_total": 3,
            "gl_account_non_zero_count": 0,
            "actual_payment_entry_cancelled_count": 1,
            "submitted_journal_entry_count_today": 0,
            "purchase_invoice_count_today": 0,
        },
        fields=[
            "name",
            "rollback_id",
            "smoke",
            "execution_gate",
            "preview",
            "pre_check",
            "monitoring_register",
            "target_policy_doctype",
            "target_policy",
            "target_policy_name",
            "target_policy_enabled_after",
            "target_policy_live_after",
            "production_batch_enabled_policy_count_after",
            "live_posting_allowed_policy_count_after",
            "payment_entry",
            "payment_entry_amount",
            "payment_entry_reference_count",
            "allocated_amount_total",
            "invoice_outstanding_after_total",
            "invoice_outstanding_restored_delta",
            "voucher_gl_rows_after",
            "voucher_gl_reversal_rows",
            "gl_net_debit",
            "gl_net_credit",
            "gl_net_balance",
            "gl_account_non_zero_count",
            "payment_entry_count_after",
            "payment_entry_gl_count_after",
            "actual_payment_entry_cancelled_count",
            "actual_gl_created_count",
            "rollback_score",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_freeze(rollback):
    rows = frappe.get_all(
        FREEZE_DOCTYPE,
        filters={
            "rollback": rollback,
            "status": "Frozen",
            "freeze_completed": 1,
        },
        fields=["name", "freeze_id"],
        limit=1,
    )
    return rows[0] if rows else None


def reference_snapshot(payment_entry):
    if not payment_entry or not frappe.db.exists("Payment Entry", payment_entry):
        return []

    pe = frappe.get_doc("Payment Entry", payment_entry)
    rows = []

    for ref in pe.references:
        if ref.reference_doctype != "Sales Invoice":
            continue

        current_outstanding = flt(
            frappe.db.get_value("Sales Invoice", ref.reference_name, "outstanding_amount") or 0,
            2,
        )

        rows.append(
            {
                "reference_doctype": ref.reference_doctype,
                "reference_name": ref.reference_name,
                "allocated_amount": flt(ref.allocated_amount or 0, 2),
                "current_outstanding": current_outstanding,
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


def validate_source(rollback, guard, pe_doc, refs, gl_net, voucher_rows, policy_enabled, policy_live):
    issues = []

    if not rollback:
        issues.append("No completed Phase 10K rollback found.")
        return issues

    existing = existing_freeze(rollback.name)
    if existing:
        issues.append(f"Phase 10L freeze already exists for this rollback: {existing.freeze_id}")

    required_links = {
        "rollback": ("NDIS Single Guarded Limited Operation Smoke Rollback", rollback.name),
        "smoke": ("NDIS Single Guarded Limited Operation Smoke", rollback.smoke),
        "execution_gate": ("NDIS Guarded Limited Operation Execution Gate", rollback.execution_gate),
        "payment_entry": ("Payment Entry", rollback.payment_entry),
        "target_policy": (POLICY_DOCTYPE, rollback.target_policy),
    }

    for label, pair in required_links.items():
        doctype, name = pair
        if not name:
            issues.append(f"Missing evidence link: {label}")
        elif not frappe.db.exists(doctype, name):
            issues.append(f"Linked evidence does not exist: {doctype} {name}")

    if not pe_doc:
        issues.append("Payment Entry could not be loaded.")
    else:
        if int(pe_doc.docstatus or 0) != 2:
            issues.append(f"Payment Entry must remain cancelled docstatus 2. Current: {pe_doc.docstatus}")
        if pe_doc.status != "Cancelled":
            issues.append(f"Payment Entry must remain Cancelled. Current: {pe_doc.status}")
        if flt(pe_doc.paid_amount or 0, 2) != 3:
            issues.append(f"Payment Entry amount must remain 3.00. Current: {flt(pe_doc.paid_amount or 0, 2)}")
        if len(pe_doc.references or []) != 3:
            issues.append(f"Payment Entry must still have 3 references. Current: {len(pe_doc.references or [])}")

    allocated_total = round(sum(flt(row["allocated_amount"], 2) for row in refs), 2)
    outstanding_total = round(sum(flt(row["current_outstanding"], 2) for row in refs), 2)

    if allocated_total != flt(rollback.allocated_amount_total or 0, 2):
        issues.append("Allocated amount total no longer matches Phase 10K rollback evidence.")

    if abs(outstanding_total - flt(rollback.invoice_outstanding_after_total or 0, 2)) > 0.01:
        issues.append("Current invoice outstanding total no longer matches Phase 10K restored outstanding evidence.")

    if voucher_rows != int(rollback.voucher_gl_rows_after or 0):
        issues.append("Voucher GL row count no longer matches Phase 10K rollback evidence.")

    if abs(flt(gl_net["total_balance"], 2)) > 0.01:
        issues.append("Voucher GL net balance is no longer zero.")

    if gl_net["non_zero_count"] != 0:
        issues.append("One or more GL accounts have non-zero balance for the cancelled voucher.")

    if policy_enabled != 1:
        issues.append("Target policy production_batch_enabled must remain 1.")

    if policy_live != 0:
        issues.append("Target policy live_posting_allowed must remain 0.")

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


def build_items(rollback, issues, ack_ok, evidence=None):
    items = []

    if rollback:
        add_item(
            items,
            "Pass",
            "Low",
            "Evidence",
            "phase10k_rollback_exists",
            "Phase 10K rollback exists",
            f"Rollback found: {rollback.rollback_id}.",
            "NDIS Single Guarded Limited Operation Smoke Rollback",
            rollback.name,
        )
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase10k_rollback_exists", "Phase 10K rollback exists", "No completed Phase 10K rollback found.")

    if not issues:
        add_item(items, "Pass", "Low", "Freeze Source", "freeze_source_valid", "Freeze source valid", "Phase 10K rollback evidence is valid for freeze.")
    else:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Freeze Source", "freeze_source_valid", "Freeze source valid", issue)

    if evidence:
        add_item(items, "Pass", "High", "Payment Entry", "payment_entry_cancelled", "Payment Entry remains cancelled", f"{evidence['payment_entry']} docstatus={evidence['payment_entry_docstatus']} status={evidence['payment_entry_status']}", "Payment Entry", evidence["payment_entry"])
        add_item(items, "Pass", "High", "Invoice", "invoice_outstanding_restored", "Invoice outstanding remains restored", f"current={evidence['invoice_outstanding_total']} rollback_after={evidence['rollback_invoice_outstanding_after_total']}")
        add_item(items, "Pass", "High", "GL", "gl_net_zero", "GL remains net zero", f"debit={evidence['gl_net_debit']} credit={evidence['gl_net_credit']} balance={evidence['gl_net_balance']} non_zero_accounts={evidence['gl_account_non_zero_count']}")
        add_item(items, "Pass", "High", "Guardrail", "no_new_movement", "No new accounting movement", f"PE {evidence['payment_entry_count_before']} -> {evidence['payment_entry_count_after']}; PE GL {evidence['payment_entry_gl_count_before']} -> {evidence['payment_entry_gl_count_after']}")

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
        row = frappe.new_doc(FREEZE_ITEM_DOCTYPE)
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


def build_evidence(rollback, guard_before, guard_after, pe_doc, refs, gl_net, voucher_rows, policy_enabled_before, policy_enabled_after, policy_live_before, policy_live_after):
    allocated_total = round(sum(flt(row["allocated_amount"], 2) for row in refs), 2)
    outstanding_total = round(sum(flt(row["current_outstanding"], 2) for row in refs), 2)

    return {
        "rollback": rollback.name if rollback else None,
        "smoke": rollback.smoke if rollback else None,
        "execution_gate": rollback.execution_gate if rollback else None,
        "preview": rollback.preview if rollback else None,
        "pre_check": rollback.pre_check if rollback else None,
        "monitoring_register": rollback.monitoring_register if rollback else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": rollback.target_policy if rollback else None,
        "target_policy_name": rollback.target_policy_name if rollback else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_before": policy_live_before,
        "target_policy_live_after": policy_live_after,
        "production_batch_enabled_policy_count_before": guard_before["production_batch_enabled_policy_count"],
        "production_batch_enabled_policy_count_after": guard_after["production_batch_enabled_policy_count"],
        "live_posting_allowed_policy_count_before": guard_before["live_posting_allowed_policy_count"],
        "live_posting_allowed_policy_count_after": guard_after["live_posting_allowed_policy_count"],
        "payment_entry": rollback.payment_entry if rollback else None,
        "payment_entry_docstatus": int(pe_doc.docstatus or 0) if pe_doc else 0,
        "payment_entry_status": pe_doc.status if pe_doc else None,
        "payment_entry_amount": flt(pe_doc.paid_amount or 0, 2) if pe_doc else 0,
        "payment_entry_reference_count": len(pe_doc.references or []) if pe_doc else 0,
        "allocated_amount_total": allocated_total,
        "invoice_outstanding_total": outstanding_total,
        "rollback_invoice_outstanding_after_total": flt(rollback.invoice_outstanding_after_total or 0, 2) if rollback else 0,
        "voucher_gl_rows": voucher_rows,
        "rollback_voucher_gl_rows_after": int(rollback.voucher_gl_rows_after or 0) if rollback else 0,
        "gl_net_debit": gl_net["total_debit"],
        "gl_net_credit": gl_net["total_credit"],
        "gl_net_balance": gl_net["total_balance"],
        "gl_account_non_zero_count": gl_net["non_zero_count"],
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guard_after["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
        "actual_payment_entry_created_count": 0,
        "actual_payment_entry_cancelled_count": 0,
        "actual_gl_created_count": 0,
        "submitted_journal_entry_count_today": guard_after["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_after["purchase_invoice_count_today"],
    }


@frappe.whitelist()
def run_single_guarded_operation_smoke_rollback_freeze(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_single_guarded_operation_smoke_rollback_freeze")

    rollback = latest_rollback()
    guard_before = guardrails()
    ack_ok = acknowledgement == FREEZE_ACK

    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }

    pe_doc = None
    if rollback and rollback.payment_entry and frappe.db.exists("Payment Entry", rollback.payment_entry):
        pe_doc = frappe.get_doc("Payment Entry", rollback.payment_entry)

    refs = reference_snapshot(rollback.payment_entry) if rollback else []
    gl_net = voucher_gl_net(rollback.payment_entry) if rollback else {"rows": [], "total_debit": 0, "total_credit": 0, "total_balance": 0, "non_zero_count": 0}
    voucher_rows = voucher_gl_rows(rollback.payment_entry) if rollback else 0

    policy_enabled_before = get_flag(POLICY_DOCTYPE, rollback.target_policy, "production_batch_enabled") if rollback else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, rollback.target_policy, "live_posting_allowed") if rollback else 0

    guard_after = guardrails()

    policy_enabled_after = get_flag(POLICY_DOCTYPE, rollback.target_policy, "production_batch_enabled") if rollback else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, rollback.target_policy, "live_posting_allowed") if rollback else 0

    issues = validate_source(
        rollback,
        guard_before,
        pe_doc,
        refs,
        gl_net,
        voucher_rows,
        policy_enabled_before,
        policy_live_before,
    )

    evidence = build_evidence(
        rollback,
        guard_before,
        guard_after,
        pe_doc,
        refs,
        gl_net,
        voucher_rows,
        policy_enabled_before,
        policy_enabled_after,
        policy_live_before,
        policy_live_after,
    )

    no_new_movement = int(
        guard_before["payment_entry_count"] == guard_after["payment_entry_count"]
        and guard_before["payment_entry_gl_count"] == guard_after["payment_entry_gl_count"]
        and guard_before["submitted_journal_entry_count_today"] == guard_after["submitted_journal_entry_count_today"]
        and guard_before["purchase_invoice_count_today"] == guard_after["purchase_invoice_count_today"]
    )

    policy_preserved = int(
        policy_enabled_before == 1
        and policy_enabled_after == 1
        and policy_live_before == 0
        and policy_live_after == 0
        and guard_before["production_batch_enabled_policy_count"] == guard_after["production_batch_enabled_policy_count"]
        and guard_before["live_posting_allowed_policy_count"] == guard_after["live_posting_allowed_policy_count"]
    )

    if not no_new_movement:
        issues.append("Accounting movement changed while preparing freeze evidence.")

    items = build_items(rollback, issues, ack_ok, evidence)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    allowed = int(ack_ok and item_summary["blocker_count"] == 0 and bool(rollback))

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Frozen" if allowed else "Needs Review",
        "freeze_status": "Single Guarded Operation Smoke Rollback Evidence Frozen" if allowed else "Needs Review",
        "freeze_completed": allowed,
        "ready_for_final_limited_operation_closeout": allowed,
        "smoke_evidence_frozen": allowed,
        "rollback_evidence_frozen": allowed,
        "payment_entry_cancelled_verified": int(evidence["payment_entry_docstatus"] == 2 and evidence["payment_entry_status"] == "Cancelled"),
        "invoice_outstanding_restored_verified": int(abs(flt(evidence["invoice_outstanding_total"], 2) - flt(evidence["rollback_invoice_outstanding_after_total"], 2)) <= 0.01),
        "gl_net_zero_verified": int(abs(flt(evidence["gl_net_balance"], 2)) <= 0.01 and evidence["gl_account_non_zero_count"] == 0),
        "no_new_accounting_movement_verified": no_new_movement,
        "policy_state_preserved_verified": policy_preserved,
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": 0,
        "phase10k_rollback_verified": 1 if rollback else 0,
        "phase10j_smoke_verified": 1 if rollback else 0,
        "phase10i_gate_verified": 1 if rollback else 0,
        "controlled_policy_enabled_verified": int(policy_enabled_after == 1),
        "live_posting_blocked_verified": int(policy_live_after == 0),
        **evidence,
        "freeze_score": score,
        **item_summary,
        "items": items,
        "issues": issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "references": refs,
        "gl_net": gl_net,
        "required_acknowledgement": FREEZE_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 10L freezes Phase 10J smoke and Phase 10K rollback evidence only. No accounting movement or policy mutation is performed.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["freeze_status"] = "Needs Review"
        result["freeze_completed"] = 0
        result["ready_for_final_limited_operation_closeout"] = 0
        result["smoke_evidence_frozen"] = 0
        result["rollback_evidence_frozen"] = 0
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
    doc.reference_json = safe_json(refs)
    doc.gl_json = safe_json(gl_net)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    create_items(doc, items)
    frappe.db.commit()

    return {
        **result,
        "created": True,
        "freeze": doc.name,
        "freeze_id": doc.freeze_id,
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_single_guarded_operation_smoke_rollback_freeze_audit(freeze, reason=None):
    assert_action("cancel_single_guarded_operation_smoke_rollback_freeze_audit")

    if not frappe.db.exists(FREEZE_DOCTYPE, freeze):
        frappe.throw(_("Freeze audit not found: {0}").format(freeze))

    doc = frappe.get_doc(FREEZE_DOCTYPE, freeze)

    if doc.status == "Cancelled":
        return {"freeze": freeze, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.freeze_completed or 0):
        frappe.throw(_("Cannot cancel a completed Phase 10L freeze record."))

    frappe.db.set_value(
        FREEZE_DOCTYPE,
        freeze,
        {
            "status": "Cancelled",
            "freeze_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 10L no-ack freeze audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        f"""
        UPDATE `tab{FREEZE_ITEM_DOCTYPE}`
        SET status = 'Cancelled'
        WHERE freeze = %(freeze)s
        """,
        {"freeze": freeze},
    )

    frappe.db.commit()

    return {
        "freeze": freeze,
        "status": "Cancelled",
        "note": "No-ack freeze audit cancelled only. No accounting or policy movement occurred.",
    }


@frappe.whitelist()
def quick_single_guarded_operation_smoke_rollback_freeze_summary(limit=20):
    freezes = frappe.get_all(
        FREEZE_DOCTYPE,
        fields=[
            "name",
            "freeze_id",
            "status",
            "freeze_status",
            "freeze_completed",
            "ready_for_final_limited_operation_closeout",
            "rollback",
            "smoke",
            "payment_entry",
            "payment_entry_docstatus",
            "payment_entry_status",
            "payment_entry_amount",
            "payment_entry_reference_count",
            "invoice_outstanding_total",
            "gl_net_balance",
            "gl_account_non_zero_count",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "submitted_journal_entry_count_today",
            "purchase_invoice_count_today",
            "freeze_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    items = frappe.get_all(
        FREEZE_ITEM_DOCTYPE,
        fields=["name", "freeze", "status", "severity", "category", "check_label", "detail", "source_doctype", "source_name"],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    return {
        "freezes": freezes,
        "items": items,
        "required_acknowledgement": FREEZE_ACK,
        "guardrails": guardrails(),
        "note": "Phase 10L freeze summary. Frozen evidence is ready for final limited operation closeout.",
    }


def execute_freeze_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("status"):
        conditions.append("f.status = %(status)s")
        params["status"] = filters.get("status")

    columns = freeze_columns()

    data = frappe.db.sql(
        f"""
        SELECT
            f.name AS freeze,
            f.freeze_id,
            f.status,
            f.freeze_status,
            f.freeze_completed,
            f.ready_for_final_limited_operation_closeout,
            f.rollback,
            f.smoke,
            f.payment_entry,
            f.payment_entry_docstatus,
            f.payment_entry_status,
            f.payment_entry_amount,
            f.payment_entry_reference_count,
            f.invoice_outstanding_total,
            f.gl_net_balance,
            f.gl_account_non_zero_count,
            f.payment_entry_count_before,
            f.payment_entry_count_after,
            f.payment_entry_gl_count_before,
            f.payment_entry_gl_count_after,
            f.submitted_journal_entry_count_today,
            f.purchase_invoice_count_today,
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
                {"name": "Frozen", "values": [int(row.freeze_completed or 0) for row in data[:20]]},
                {"name": "JE Today", "values": [int(row.submitted_journal_entry_count_today or 0) for row in data[:20]]},
                {"name": "PI Today", "values": [int(row.purchase_invoice_count_today or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Freezes"), "datatype": "Int"},
        {"value": sum(int(row.freeze_completed or 0) for row in data), "indicator": "Green", "label": _("Frozen"), "datatype": "Int"},
        {"value": sum(int(row.ready_for_final_limited_operation_closeout or 0) for row in data), "indicator": "Green", "label": _("Ready Closeout"), "datatype": "Int"},
        {"value": sum(int(row.gl_account_non_zero_count or 0) for row in data), "indicator": "Red", "label": _("Non-Zero GL Accounts"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def freeze_columns():
    return [
        {"fieldname": "freeze", "label": _("Freeze"), "fieldtype": "Link", "options": FREEZE_DOCTYPE, "width": 220},
        {"fieldname": "freeze_id", "label": _("Freeze ID"), "fieldtype": "Data", "width": 430},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "freeze_status", "label": _("Freeze Status"), "fieldtype": "Data", "width": 330},
        {"fieldname": "freeze_completed", "label": _("Frozen"), "fieldtype": "Check", "width": 85},
        {"fieldname": "ready_for_final_limited_operation_closeout", "label": _("Ready Closeout"), "fieldtype": "Check", "width": 120},
        {"fieldname": "rollback", "label": _("Rollback"), "fieldtype": "Link", "options": "NDIS Single Guarded Limited Operation Smoke Rollback", "width": 220},
        {"fieldname": "smoke", "label": _("Smoke"), "fieldtype": "Link", "options": "NDIS Single Guarded Limited Operation Smoke", "width": 220},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "payment_entry_docstatus", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 105},
        {"fieldname": "payment_entry_status", "label": _("PE Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "payment_entry_amount", "label": _("PE Amount"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "payment_entry_reference_count", "label": _("Refs"), "fieldtype": "Int", "width": 70},
        {"fieldname": "invoice_outstanding_total", "label": _("Outstanding"), "fieldtype": "Currency", "options": "currency", "width": 115},
        {"fieldname": "gl_net_balance", "label": _("GL Balance"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "gl_account_non_zero_count", "label": _("Non-Zero GL Accounts"), "fieldtype": "Int", "width": 145},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 110},
        {"fieldname": "submitted_journal_entry_count_today", "label": _("JE Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "purchase_invoice_count_today", "label": _("PI Today"), "fieldtype": "Int", "width": 90},
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

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": FREEZE_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "freeze", "label": _("Freeze"), "fieldtype": "Link", "options": FREEZE_DOCTYPE, "width": 220},
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
            i.freeze,
            i.status,
            i.severity,
            i.category,
            i.check_label,
            i.detail,
            i.source_doctype,
            i.source_name,
            i.checked_on
        FROM `tab{FREEZE_ITEM_DOCTYPE}` i
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
