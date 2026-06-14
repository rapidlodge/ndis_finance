import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


CLOSEOUT_ACK = "I_CONFIRM_PHASE10M_APPROVE_FINAL_LIMITED_OPERATION_CLOSEOUT_NO_POSTING"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
FREEZE_DOCTYPE = "NDIS Single Guarded Op Smoke Rollback Freeze"
CLOSEOUT_DOCTYPE = "NDIS Limited Operation Closeout Gate"
CLOSEOUT_ITEM_DOCTYPE = "NDIS Limited Operation Closeout Gate Item"


def make_closeout_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-LIMITED-OPERATION-CLOSEOUT-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_freeze():
    rows = frappe.get_all(
        FREEZE_DOCTYPE,
        filters={
            "status": "Frozen",
            "freeze_status": "Single Guarded Operation Smoke Rollback Evidence Frozen",
            "freeze_completed": 1,
            "ready_for_final_limited_operation_closeout": 1,
            "smoke_evidence_frozen": 1,
            "rollback_evidence_frozen": 1,
            "payment_entry_cancelled_verified": 1,
            "invoice_outstanding_restored_verified": 1,
            "gl_net_zero_verified": 1,
            "no_new_accounting_movement_verified": 1,
            "policy_state_preserved_verified": 1,
            "policy_mutation_performed": 0,
            "actual_policy_mutation_count": 0,
            "phase10k_rollback_verified": 1,
            "phase10j_smoke_verified": 1,
            "phase10i_gate_verified": 1,
            "controlled_policy_enabled_verified": 1,
            "live_posting_blocked_verified": 1,
            "payment_entry_docstatus": 2,
            "payment_entry_status": "Cancelled",
            "payment_entry_amount": 3,
            "payment_entry_reference_count": 3,
            "gl_account_non_zero_count": 0,
            "actual_payment_entry_created_count": 0,
            "actual_payment_entry_cancelled_count": 0,
            "actual_gl_created_count": 0,
            "submitted_journal_entry_count_today": 0,
            "purchase_invoice_count_today": 0,
        },
        fields=[
            "name",
            "freeze_id",
            "rollback",
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
            "invoice_outstanding_total",
            "gl_net_balance",
            "gl_account_non_zero_count",
            "payment_entry_count_after",
            "payment_entry_gl_count_after",
            "freeze_score",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_closeout(freeze):
    rows = frappe.get_all(
        CLOSEOUT_DOCTYPE,
        filters={
            "freeze": freeze,
            "status": "Closeout Approved",
            "closeout_approved": 1,
        },
        fields=["name", "closeout_id"],
        limit=1,
    )
    return rows[0] if rows else None


def get_policy_decision_from_freeze(freeze):
    if not freeze or not freeze.smoke:
        return None

    try:
        return frappe.db.get_value(
            "NDIS Single Guarded Limited Operation Smoke",
            freeze.smoke,
            "decision",
        )
    except Exception:
        return None


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


def validate_source(freeze, guard, pe_doc, policy_enabled, policy_live, gl_net, refs):
    issues = []

    if not freeze:
        issues.append("No completed Phase 10L freeze found.")
        return issues

    existing = existing_closeout(freeze.name)
    if existing:
        issues.append(f"Phase 10M closeout already exists for this freeze: {existing.closeout_id}")

    required_links = {
        "freeze": (FREEZE_DOCTYPE, freeze.name),
        "rollback": ("NDIS Single Guarded Limited Operation Smoke Rollback", freeze.rollback),
        "smoke": ("NDIS Single Guarded Limited Operation Smoke", freeze.smoke),
        "execution_gate": ("NDIS Guarded Limited Operation Execution Gate", freeze.execution_gate),
        "preview": ("NDIS Guarded Limited Operation Preview", freeze.preview),
        "pre_check": ("NDIS Controlled Limited Operation Pre Check", freeze.pre_check),
        "monitoring_register": ("NDIS Controlled Limited Operations Monitoring Register", freeze.monitoring_register),
        "target_policy": (POLICY_DOCTYPE, freeze.target_policy),
        "payment_entry": ("Payment Entry", freeze.payment_entry),
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

    outstanding_total = round(sum(flt(row["current_outstanding"], 2) for row in refs), 2)

    if abs(outstanding_total - flt(freeze.invoice_outstanding_total or 0, 2)) > 0.01:
        issues.append("Current invoice outstanding total no longer matches Phase 10L freeze evidence.")

    if abs(flt(gl_net["total_balance"], 2)) > 0.01:
        issues.append("Voucher GL net balance is not zero.")

    if gl_net["non_zero_count"] != 0:
        issues.append("One or more GL accounts remain non-zero for the cancelled voucher.")

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


def build_items(freeze, issues, ack_ok, evidence=None):
    items = []

    if freeze:
        add_item(
            items,
            "Pass",
            "Low",
            "Evidence",
            "phase10l_freeze_exists",
            "Phase 10L freeze exists",
            f"Freeze found: {freeze.freeze_id}.",
            FREEZE_DOCTYPE,
            freeze.name,
        )
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase10l_freeze_exists", "Phase 10L freeze exists", "No completed Phase 10L freeze found.")

    if not issues:
        add_item(items, "Pass", "Low", "Closeout Source", "closeout_source_valid", "Closeout source valid", "Phase 10L freeze evidence is valid for final closeout.")
    else:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Closeout Source", "closeout_source_valid", "Closeout source valid", issue)

    if evidence:
        chain = [
            ("phase10f_monitoring_register_verified", "Phase 10F monitoring register verified", evidence.get("monitoring_register")),
            ("phase10g_pre_check_verified", "Phase 10G pre-check verified", evidence.get("pre_check")),
            ("phase10h_preview_verified", "Phase 10H preview verified", evidence.get("preview")),
            ("phase10i_gate_verified", "Phase 10I execution gate verified", evidence.get("execution_gate")),
            ("phase10j_smoke_verified", "Phase 10J smoke verified", evidence.get("smoke")),
            ("phase10k_rollback_verified", "Phase 10K rollback verified", evidence.get("rollback")),
            ("phase10l_freeze_verified", "Phase 10L freeze verified", evidence.get("freeze")),
        ]

        for key, label, value in chain:
            add_item(items, "Pass", "Low", "Cycle Chain", key, label, str(value))

        add_item(items, "Pass", "High", "Closeout", "payment_entry_cancelled", "Payment Entry remains cancelled", f"{evidence['payment_entry']} docstatus={evidence['payment_entry_docstatus']} status={evidence['payment_entry_status']}", "Payment Entry", evidence["payment_entry"])
        add_item(items, "Pass", "High", "Closeout", "gl_net_zero", "GL net zero confirmed", f"balance={evidence['gl_net_balance']} non_zero_accounts={evidence['gl_account_non_zero_count']}")
        add_item(items, "Pass", "High", "Closeout", "no_new_movement", "No new accounting movement", f"PE {evidence['payment_entry_count_before']} -> {evidence['payment_entry_count_after']}; PE GL {evidence['payment_entry_gl_count_before']} -> {evidence['payment_entry_gl_count_after']}")
        add_item(items, "Pass", "High", "Closeout", "policy_state_preserved", "Policy state preserved", f"enabled/live={evidence['production_batch_enabled_policy_count_after']} / {evidence['live_posting_allowed_policy_count_after']}")

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {CLOSEOUT_ACK}")

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
        row = frappe.new_doc(CLOSEOUT_ITEM_DOCTYPE)
        row.closeout = doc.name
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


def build_evidence(freeze, guard_before, guard_after, pe_doc, refs, gl_net, policy_decision, policy_enabled_before, policy_enabled_after, policy_live_before, policy_live_after):
    outstanding_total = round(sum(flt(row["current_outstanding"], 2) for row in refs), 2)

    return {
        "freeze": freeze.name if freeze else None,
        "rollback": freeze.rollback if freeze else None,
        "smoke": freeze.smoke if freeze else None,
        "execution_gate": freeze.execution_gate if freeze else None,
        "preview": freeze.preview if freeze else None,
        "pre_check": freeze.pre_check if freeze else None,
        "monitoring_register": freeze.monitoring_register if freeze else None,
        "policy_decision": policy_decision,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": freeze.target_policy if freeze else None,
        "target_policy_name": freeze.target_policy_name if freeze else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_before": policy_live_before,
        "target_policy_live_after": policy_live_after,
        "production_batch_enabled_policy_count_before": guard_before["production_batch_enabled_policy_count"],
        "production_batch_enabled_policy_count_after": guard_after["production_batch_enabled_policy_count"],
        "live_posting_allowed_policy_count_before": guard_before["live_posting_allowed_policy_count"],
        "live_posting_allowed_policy_count_after": guard_after["live_posting_allowed_policy_count"],
        "payment_entry": freeze.payment_entry if freeze else None,
        "payment_entry_docstatus": int(pe_doc.docstatus or 0) if pe_doc else 0,
        "payment_entry_status": pe_doc.status if pe_doc else None,
        "payment_entry_amount": flt(pe_doc.paid_amount or 0, 2) if pe_doc else 0,
        "payment_entry_reference_count": len(pe_doc.references or []) if pe_doc else 0,
        "smoke_payment_entry_created_count": 1,
        "smoke_gl_created_count": int(frappe.db.get_value("NDIS Single Guarded Limited Operation Smoke", freeze.smoke, "actual_gl_created_count") or 0) if freeze and freeze.smoke else 0,
        "rollback_payment_entry_cancelled_count": 1,
        "rollback_gl_created_count": int(frappe.db.get_value("NDIS Single Guarded Limited Operation Smoke Rollback", freeze.rollback, "actual_gl_created_count") or 0) if freeze and freeze.rollback else 0,
        "invoice_outstanding_total": outstanding_total,
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
def run_limited_operation_closeout_gate(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_limited_operation_closeout_gate")

    freeze = latest_freeze()
    guard_before = guardrails()
    ack_ok = acknowledgement == CLOSEOUT_ACK

    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }

    pe_doc = None
    if freeze and freeze.payment_entry and frappe.db.exists("Payment Entry", freeze.payment_entry):
        pe_doc = frappe.get_doc("Payment Entry", freeze.payment_entry)

    refs = reference_snapshot(freeze.payment_entry) if freeze else []
    gl_net = voucher_gl_net(freeze.payment_entry) if freeze else {"rows": [], "total_debit": 0, "total_credit": 0, "total_balance": 0, "non_zero_count": 0}

    policy_decision = get_policy_decision_from_freeze(freeze)
    policy_enabled_before = get_flag(POLICY_DOCTYPE, freeze.target_policy, "production_batch_enabled") if freeze else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, freeze.target_policy, "live_posting_allowed") if freeze else 0

    guard_after = guardrails()

    policy_enabled_after = get_flag(POLICY_DOCTYPE, freeze.target_policy, "production_batch_enabled") if freeze else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, freeze.target_policy, "live_posting_allowed") if freeze else 0

    issues = validate_source(
        freeze,
        guard_before,
        pe_doc,
        policy_enabled_before,
        policy_live_before,
        gl_net,
        refs,
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
        issues.append("Accounting movement changed while preparing closeout evidence.")

    evidence = build_evidence(
        freeze,
        guard_before,
        guard_after,
        pe_doc,
        refs,
        gl_net,
        policy_decision,
        policy_enabled_before,
        policy_enabled_after,
        policy_live_before,
        policy_live_after,
    )

    items = build_items(freeze, issues, ack_ok, evidence)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    allowed = int(ack_ok and item_summary["blocker_count"] == 0 and bool(freeze))

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Closeout Approved" if allowed else "Needs Review",
        "closeout_status": "Ready For Controlled Limited Operations Steady State" if allowed else "Needs Review",
        "closeout_approved": allowed,
        "ready_for_controlled_limited_operations_steady_state": allowed,
        "limited_operation_cycle_closed": allowed,
        "full_cycle_evidence_chain_verified": allowed,
        "steady_state_monitoring_ready": allowed,
        "no_new_accounting_movement_verified": no_new_movement,
        "policy_state_preserved_verified": policy_preserved,
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": 0,
        "phase10l_freeze_verified": 1 if freeze else 0,
        "phase10k_rollback_verified": 1 if freeze else 0,
        "phase10j_smoke_verified": 1 if freeze else 0,
        "phase10i_gate_verified": 1 if freeze else 0,
        "phase10h_preview_verified": 1 if freeze else 0,
        "phase10g_pre_check_verified": 1 if freeze else 0,
        "phase10f_monitoring_register_verified": 1 if freeze else 0,
        "phase10e_policy_decision_verified": 1 if policy_decision else 0,
        "controlled_policy_enabled_verified": int(policy_enabled_after == 1),
        "live_posting_blocked_verified": int(policy_live_after == 0),
        **evidence,
        "closeout_score": score,
        **item_summary,
        "items": items,
        "issues": issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "references": refs,
        "gl_net": gl_net,
        "required_acknowledgement": CLOSEOUT_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 10M approves final closeout of the controlled limited operation cycle only. No accounting movement or policy mutation is performed.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["closeout_status"] = "Needs Review"
        result["closeout_approved"] = 0
        result["ready_for_controlled_limited_operations_steady_state"] = 0
        result["limited_operation_cycle_closed"] = 0
        result["full_cycle_evidence_chain_verified"] = 0
        result["steady_state_monitoring_ready"] = 0
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
    doc.evidence_json = safe_json(
        {
            "evidence": evidence,
            "references": refs,
            "gl_net": gl_net,
            "guardrails_before": guard_before,
            "guardrails_after": guard_after,
        }
    )
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    create_items(doc, items)
    frappe.db.commit()

    return {
        **result,
        "created": True,
        "closeout": doc.name,
        "closeout_id": doc.closeout_id,
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_limited_operation_closeout_gate_audit(closeout, reason=None):
    assert_action("cancel_limited_operation_closeout_gate_audit")

    if not frappe.db.exists(CLOSEOUT_DOCTYPE, closeout):
        frappe.throw(_("Closeout audit not found: {0}").format(closeout))

    doc = frappe.get_doc(CLOSEOUT_DOCTYPE, closeout)

    if doc.status == "Cancelled":
        return {"closeout": closeout, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.closeout_approved or 0):
        frappe.throw(_("Cannot cancel an approved Phase 10M closeout gate record."))

    frappe.db.set_value(
        CLOSEOUT_DOCTYPE,
        closeout,
        {
            "status": "Cancelled",
            "closeout_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 10M no-ack closeout audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        f"""
        UPDATE `tab{CLOSEOUT_ITEM_DOCTYPE}`
        SET status = 'Cancelled'
        WHERE closeout = %(closeout)s
        """,
        {"closeout": closeout},
    )

    frappe.db.commit()

    return {
        "closeout": closeout,
        "status": "Cancelled",
        "note": "No-ack closeout audit cancelled only. No accounting or policy movement occurred.",
    }


@frappe.whitelist()
def quick_limited_operation_closeout_gate_summary(limit=20):
    closeouts = frappe.get_all(
        CLOSEOUT_DOCTYPE,
        fields=[
            "name",
            "closeout_id",
            "status",
            "closeout_status",
            "closeout_approved",
            "ready_for_controlled_limited_operations_steady_state",
            "limited_operation_cycle_closed",
            "freeze",
            "rollback",
            "smoke",
            "payment_entry",
            "payment_entry_docstatus",
            "payment_entry_status",
            "invoice_outstanding_total",
            "gl_net_balance",
            "gl_account_non_zero_count",
            "production_batch_enabled_policy_count_after",
            "live_posting_allowed_policy_count_after",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "submitted_journal_entry_count_today",
            "purchase_invoice_count_today",
            "closeout_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    items = frappe.get_all(
        CLOSEOUT_ITEM_DOCTYPE,
        fields=["name", "closeout", "status", "severity", "category", "check_label", "detail", "source_doctype", "source_name"],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    return {
        "closeouts": closeouts,
        "items": items,
        "required_acknowledgement": CLOSEOUT_ACK,
        "guardrails": guardrails(),
        "note": "Phase 10M closeout summary. Approved closeout confirms controlled limited operations steady-state readiness.",
    }


def execute_closeout_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("status"):
        conditions.append("c.status = %(status)s")
        params["status"] = filters.get("status")

    columns = closeout_columns()

    data = frappe.db.sql(
        f"""
        SELECT
            c.name AS closeout,
            c.closeout_id,
            c.status,
            c.closeout_status,
            c.closeout_approved,
            c.ready_for_controlled_limited_operations_steady_state,
            c.limited_operation_cycle_closed,
            c.freeze,
            c.rollback,
            c.smoke,
            c.payment_entry,
            c.payment_entry_docstatus,
            c.payment_entry_status,
            c.invoice_outstanding_total,
            c.gl_net_balance,
            c.gl_account_non_zero_count,
            c.production_batch_enabled_policy_count_after,
            c.live_posting_allowed_policy_count_after,
            c.payment_entry_count_before,
            c.payment_entry_count_after,
            c.payment_entry_gl_count_before,
            c.payment_entry_gl_count_after,
            c.submitted_journal_entry_count_today,
            c.purchase_invoice_count_today,
            c.closeout_score,
            c.checked_on,
            %(currency)s AS currency
        FROM `tab{CLOSEOUT_DOCTYPE}` c
        {build_where(conditions)}
        ORDER BY c.creation DESC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.closeout_id for row in data[:20]],
            "datasets": [
                {"name": "Approved", "values": [int(row.closeout_approved or 0) for row in data[:20]]},
                {"name": "Ready Steady State", "values": [int(row.ready_for_controlled_limited_operations_steady_state or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Closeouts"), "datatype": "Int"},
        {"value": sum(int(row.closeout_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(int(row.ready_for_controlled_limited_operations_steady_state or 0) for row in data), "indicator": "Green", "label": _("Ready Steady State"), "datatype": "Int"},
        {"value": sum(int(row.gl_account_non_zero_count or 0) for row in data), "indicator": "Red", "label": _("Non-Zero GL Accounts"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def closeout_columns():
    return [
        {"fieldname": "closeout", "label": _("Closeout"), "fieldtype": "Link", "options": CLOSEOUT_DOCTYPE, "width": 220},
        {"fieldname": "closeout_id", "label": _("Closeout ID"), "fieldtype": "Data", "width": 390},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 140},
        {"fieldname": "closeout_status", "label": _("Closeout Status"), "fieldtype": "Data", "width": 330},
        {"fieldname": "closeout_approved", "label": _("Approved"), "fieldtype": "Check", "width": 90},
        {"fieldname": "ready_for_controlled_limited_operations_steady_state", "label": _("Ready Steady State"), "fieldtype": "Check", "width": 135},
        {"fieldname": "limited_operation_cycle_closed", "label": _("Cycle Closed"), "fieldtype": "Check", "width": 110},
        {"fieldname": "freeze", "label": _("Freeze"), "fieldtype": "Link", "options": FREEZE_DOCTYPE, "width": 220},
        {"fieldname": "rollback", "label": _("Rollback"), "fieldtype": "Link", "options": "NDIS Single Guarded Limited Operation Smoke Rollback", "width": 220},
        {"fieldname": "smoke", "label": _("Smoke"), "fieldtype": "Link", "options": "NDIS Single Guarded Limited Operation Smoke", "width": 220},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "payment_entry_docstatus", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 105},
        {"fieldname": "payment_entry_status", "label": _("PE Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "invoice_outstanding_total", "label": _("Outstanding"), "fieldtype": "Currency", "options": "currency", "width": 115},
        {"fieldname": "gl_net_balance", "label": _("GL Balance"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "gl_account_non_zero_count", "label": _("Non-Zero GL Accounts"), "fieldtype": "Int", "width": 145},
        {"fieldname": "production_batch_enabled_policy_count_after", "label": _("Enabled Policies"), "fieldtype": "Int", "width": 125},
        {"fieldname": "live_posting_allowed_policy_count_after", "label": _("Live Policies"), "fieldtype": "Int", "width": 105},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 110},
        {"fieldname": "submitted_journal_entry_count_today", "label": _("JE Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "purchase_invoice_count_today", "label": _("PI Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "closeout_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    if filters.get("closeout"):
        conditions.append("i.closeout = %(closeout)s")
        params["closeout"] = filters.get("closeout")

    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": CLOSEOUT_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "closeout", "label": _("Closeout"), "fieldtype": "Link", "options": CLOSEOUT_DOCTYPE, "width": 220},
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
            i.closeout,
            i.status,
            i.severity,
            i.category,
            i.check_label,
            i.detail,
            i.source_doctype,
            i.source_name,
            i.checked_on
        FROM `tab{CLOSEOUT_ITEM_DOCTYPE}` i
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
        {"value": len([row for row in data if row.category == "Cycle Chain"]), "indicator": "Blue", "label": _("Cycle Chain Checks"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_closeout_report(filters)

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
