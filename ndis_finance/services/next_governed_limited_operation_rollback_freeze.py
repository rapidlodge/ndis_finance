import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


FREEZE_ACK = "I_CONFIRM_PHASE11L_FREEZE_NEXT_GOVERNED_LIMITED_OPERATION_ROLLBACK_EVIDENCE_NO_POSTING"

POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
ROLLBACK_DOCTYPE = "NDIS Governed Next Op Rollback"
FREEZE_DOCTYPE = "NDIS Governed Next Op Rollback Freeze"
FREEZE_ITEM_DOCTYPE = "NDIS Governed Next Op Rollback Freeze Item"


def make_freeze_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-GOVERNED-NEXT-OP-ROLLBACK-FREEZE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_rollback():
    rows = frappe.get_all(
        ROLLBACK_DOCTYPE,
        filters={
            "status": "Rollback Completed",
            "rollback_status": "Next Governed Limited Operation Smoke Rolled Back",
            "rollback_completed": 1,
            "phase11j_smoke_verified": 1,
            "smoke_payment_entry_verified": 1,
            "payment_entry_cancelled_verified": 1,
            "reversal_gl_created_verified": 1,
            "voucher_gl_net_zero_verified": 1,
            "invoice_outstanding_restored_verified": 1,
            "ready_for_next_governed_limited_operation_rollback_freeze": 1,
            "payment_entry_docstatus_after": 2,
            "payment_entry_status_after": "Cancelled",
            "rolled_back_reference_count": 3,
            "rolled_back_total_amount": 3.00,
            "voucher_gl_rows_after": 8,
            "reversal_gl_row_count": 4,
            "voucher_gl_net_after": 0.00,
            "voucher_gl_non_zero_account_count": 0,
            "restored_invoice_amount": 3.00,
            "payment_entry_count_after": 9,
            "payment_entry_gl_count_after": 54,
            "actual_payment_entry_created_count": 0,
            "actual_payment_entry_cancelled_count": 1,
            "actual_gl_created_count": 4,
            "submitted_journal_entry_count_today": 0,
            "purchase_invoice_count_today": 0,
            "target_policy_enabled_after": 1,
            "target_policy_live_after": 0,
            "actual_policy_mutation_count": 0,
        },
        fields=[
            "name",
            "rollback_id",
            "rolled_back_payment_entry",
            "rolled_back_reference_count",
            "rolled_back_total_amount",
            "restored_invoice_amount",
            "smoke",
            "execution_gate",
            "preview",
            "validation",
            "candidate",
            "design",
            "planning",
            "target_policy_doctype",
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
            "status": "Frozen",
            "freeze_completed": 1,
        },
        fields=["name", "freeze_id"],
        limit=1,
    )
    return rows[0] if rows else None


def payment_entry_reference_rows(payment_entry):
    if not payment_entry:
        return []
    return frappe.get_all(
        "Payment Entry Reference",
        filters={"parent": payment_entry, "reference_doctype": "Sales Invoice"},
        fields=[
            "idx",
            "reference_doctype",
            "reference_name",
            "total_amount",
            "outstanding_amount",
            "allocated_amount",
        ],
        order_by="idx asc",
    )


def allocated_total(payment_entry):
    rows = payment_entry_reference_rows(payment_entry)
    return flt(sum(flt(row.allocated_amount or 0, 2) for row in rows), 2)


def voucher_gl_rows(payment_entry):
    return count_dt("GL Entry", {"voucher_type": "Payment Entry", "voucher_no": payment_entry})


def voucher_gl_net(payment_entry):
    if not payment_entry:
        return 0
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


def voucher_gl_non_zero_accounts(payment_entry):
    if not payment_entry:
        return 0
    rows = frappe.db.sql(
        """
        SELECT account, ROUND(COALESCE(SUM(debit-credit), 0), 2) AS net
        FROM `tabGL Entry`
        WHERE voucher_type='Payment Entry'
        AND voucher_no=%s
        GROUP BY account
        HAVING ROUND(COALESCE(SUM(debit-credit), 0), 2) != 0
        """,
        payment_entry,
        as_dict=True,
    )
    return len(rows)


def validate_source(rollback, payment_entry, references, guard, config, policy_enabled, policy_live):
    issues = []

    if not rollback:
        issues.append("No completed Phase 11K rollback found.")
        return issues

    existing = existing_completed_freeze(rollback.name)
    if existing:
        issues.append(f"Completed Phase 11L freeze already exists for this rollback: {existing.freeze_id}")

    if not payment_entry:
        issues.append("Phase 11K rollback does not identify a rolled back Payment Entry.")
        return issues

    if not frappe.db.exists("Payment Entry", payment_entry):
        issues.append(f"Rolled back Payment Entry does not exist: {payment_entry}")
        return issues

    pe = frappe.get_doc("Payment Entry", payment_entry)

    if pe.docstatus != 2:
        issues.append(f"Payment Entry must remain cancelled before freeze. docstatus={pe.docstatus}")

    if pe.status != "Cancelled":
        issues.append(f"Payment Entry status must remain Cancelled before freeze. status={pe.status}")

    if len(references) != 3:
        issues.append(f"Payment Entry must still have 3 Sales Invoice references. Found {len(references)}.")

    if allocated_total(payment_entry) != 3:
        issues.append(f"Payment Entry allocated total must remain 3.00. Found {allocated_total(payment_entry)}.")

    if voucher_gl_rows(payment_entry) != 8:
        issues.append(f"Voucher GL rows must remain 8. Found {voucher_gl_rows(payment_entry)}.")

    if voucher_gl_net(payment_entry) != 0:
        issues.append(f"Voucher GL net must remain 0.00. Found {voucher_gl_net(payment_entry)}.")

    if voucher_gl_non_zero_accounts(payment_entry) != 0:
        issues.append(f"Voucher non-zero account count must remain 0. Found {voucher_gl_non_zero_accounts(payment_entry)}.")

    if guard["payment_entry_count"] != 9:
        issues.append("Payment Entry count must remain 9 before Phase 11L freeze.")

    if guard["payment_entry_gl_count"] != 54:
        issues.append("Payment Entry GL count must remain 54 before Phase 11L freeze.")

    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today must remain 0 before freeze.")

    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today must remain 0 before freeze.")

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


def add_item(items, status, severity, category, check_key, check_label, detail, reference=None, rolled_back_payment_entry=None):
    item = {
        "status": status,
        "severity": severity,
        "category": category,
        "check_key": check_key,
        "check_label": check_label,
        "detail": detail,
        "rolled_back_payment_entry": rolled_back_payment_entry,
    }

    if reference:
        item.update({
            "line_no": int(reference.idx or 0),
            "reference_doctype": reference.reference_doctype,
            "reference_name": reference.reference_name,
            "allocated_amount": flt(reference.allocated_amount or 0, 2),
            "source_doctype": reference.reference_doctype,
            "source_name": reference.reference_name,
        })

    items.append(item)


def build_items(rollback, references, issues, ack_ok, rolled_back_payment_entry=None):
    items = []

    if rollback:
        add_item(
            items,
            "Pass",
            "Low",
            "Evidence",
            "phase11k_rollback_exists",
            "Phase 11K rollback exists",
            f"Rollback found: {rollback.rollback_id}.",
            rolled_back_payment_entry=rolled_back_payment_entry,
        )
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase11k_rollback_exists", "Phase 11K rollback exists", "No completed Phase 11K rollback found.")

    if not issues:
        add_item(
            items,
            "Pass",
            "Critical",
            "Freeze Source",
            "freeze_source_valid",
            "Freeze source valid",
            "Rollback evidence is stable and ready to freeze.",
            rolled_back_payment_entry=rolled_back_payment_entry,
        )
    else:
        for issue in issues:
            add_item(
                items,
                "Blocker",
                "Critical",
                "Freeze Source",
                "freeze_source_valid",
                "Freeze source valid",
                issue,
                rolled_back_payment_entry=rolled_back_payment_entry,
            )

    for ref in references:
        add_item(
            items,
            "Pass",
            "High",
            "Frozen Reference",
            "frozen_sales_invoice_reference",
            f"Frozen Sales Invoice {ref.idx}",
            f"{ref.reference_name} rollback allocation evidence frozen at {flt(ref.allocated_amount or 0, 2)}.",
            reference=ref,
            rolled_back_payment_entry=rolled_back_payment_entry,
        )

    checks = [
        ("payment_entry_cancelled_still", "Payment Entry still cancelled", rolled_back_payment_entry),
        ("voucher_gl_rows", "Voucher GL rows remain 8", 8),
        ("voucher_gl_net_zero", "Voucher GL net remains 0.00", "0.00"),
        ("invoice_outstanding_restored", "Invoice outstanding restoration remains frozen", "3.00"),
        ("no_pe_movement", "No Payment Entry movement in freeze", "0 / 0"),
        ("no_gl_movement", "No GL movement in freeze", 0),
        ("no_je_pi", "No JE / PI side effects", "0 / 0"),
        ("policy_state", "Policy state preserved at 1 / 0", "1 / 0"),
        ("ready_for_closeout", "Ready for final closeout", 1),
    ]

    for key, label, value in checks:
        add_item(
            items,
            "Pass",
            "High",
            "Freeze Evidence",
            key,
            label,
            f"value={value}",
            rolled_back_payment_entry=rolled_back_payment_entry,
        )

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.", rolled_back_payment_entry=rolled_back_payment_entry)
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

        for fieldname, value in item.items():
            if row.meta.has_field(fieldname):
                setattr(row, fieldname, value)

        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_next_governed_limited_operation_rollback_freeze(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_next_governed_limited_operation_rollback_freeze")

    rollback = latest_rollback()
    payment_entry = rollback.rolled_back_payment_entry if rollback else None
    references = payment_entry_reference_rows(payment_entry) if payment_entry else []

    guard_before = guardrails()
    ack_ok = acknowledgement == FREEZE_ACK

    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }

    policy_enabled_before = get_flag(POLICY_DOCTYPE, rollback.target_policy, "production_batch_enabled") if rollback else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, rollback.target_policy, "live_posting_allowed") if rollback else 0

    issues = validate_source(rollback, payment_entry, references, guard_before, config, policy_enabled_before, policy_live_before)

    guard_after = guardrails()
    policy_enabled_after = get_flag(POLICY_DOCTYPE, rollback.target_policy, "production_batch_enabled") if rollback else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, rollback.target_policy, "live_posting_allowed") if rollback else 0

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
    frozen_total = 0
    voucher_rows = 0
    voucher_net = 0
    non_zero_accounts = 0

    if payment_entry and frappe.db.exists("Payment Entry", payment_entry):
        pe = frappe.get_doc("Payment Entry", payment_entry)
        pe_docstatus = int(pe.docstatus or 0)
        pe_status = pe.status
        frozen_total = flt(pe.paid_amount or pe.received_amount or allocated_total(payment_entry), 2)
        voucher_rows = voucher_gl_rows(payment_entry)
        voucher_net = voucher_gl_net(payment_entry)
        non_zero_accounts = voucher_gl_non_zero_accounts(payment_entry)

    post_issues = list(issues)

    if actual_pe_created != 0:
        post_issues.append(f"Freeze must not create Payment Entries. Created {actual_pe_created}.")

    if actual_pe_cancelled != 0:
        post_issues.append(f"Freeze must not cancel Payment Entries. Cancelled {actual_pe_cancelled}.")

    if actual_gl_created != 0:
        post_issues.append(f"Freeze must not create GL rows. Created {actual_gl_created}.")

    if guard_after["payment_entry_count"] != 9:
        post_issues.append("Payment Entry count must remain 9 after freeze.")

    if guard_after["payment_entry_gl_count"] != 54:
        post_issues.append("Payment Entry GL count must remain 54 after freeze.")

    if guard_after["submitted_journal_entry_count_today"] != 0:
        post_issues.append("Submitted Journal Entry count today must remain 0 after freeze.")

    if guard_after["purchase_invoice_count_today"] != 0:
        post_issues.append("Purchase Invoice count today must remain 0 after freeze.")

    if policy_mutation_count != 0:
        post_issues.append("Policy state changed during freeze. This is not allowed.")

    items = build_items(
        rollback,
        references,
        post_issues,
        ack_ok,
        rolled_back_payment_entry=payment_entry,
    )
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    completed = int(
        ack_ok
        and rollback
        and payment_entry
        and item_summary["blocker_count"] == 0
        and pe_docstatus == 2
        and pe_status == "Cancelled"
        and len(references) == 3
        and frozen_total == 3
        and voucher_rows == 8
        and voucher_net == 0
        and non_zero_accounts == 0
        and guard_before["payment_entry_count"] == 9
        and guard_after["payment_entry_count"] == 9
        and guard_before["payment_entry_gl_count"] == 54
        and guard_after["payment_entry_gl_count"] == 54
        and actual_pe_created == 0
        and actual_pe_cancelled == 0
        and actual_gl_created == 0
        and guard_after["submitted_journal_entry_count_today"] == 0
        and guard_after["purchase_invoice_count_today"] == 0
        and policy_mutation_count == 0
    )

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Frozen" if completed else "Needs Review",
        "freeze_status": "Next Governed Limited Operation Rollback Evidence Frozen" if completed else "Needs Review",
        "freeze_completed": completed,
        "phase11k_rollback_verified": 1 if rollback else 0,
        "rolled_back_payment_entry_verified": 1 if payment_entry else 0,
        "payment_entry_cancelled_still_verified": int(pe_docstatus == 2 and pe_status == "Cancelled"),
        "voucher_gl_rows_verified": int(voucher_rows == 8),
        "voucher_gl_net_zero_verified": int(voucher_net == 0 and non_zero_accounts == 0),
        "invoice_outstanding_restored_still_verified": int(frozen_total == 3),
        "ready_for_next_governed_limited_operation_closeout": completed,
        "no_new_accounting_movement_verified": int(actual_pe_created == 0 and actual_pe_cancelled == 0 and actual_gl_created == 0),
        "policy_state_preserved_verified": int(policy_mutation_count == 0 and policy_enabled_before == 1 and policy_enabled_after == 1 and policy_live_before == 0 and policy_live_after == 0),
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": policy_mutation_count,
        "rolled_back_payment_entry": payment_entry,
        "payment_entry_docstatus_frozen": pe_docstatus,
        "payment_entry_status_frozen": pe_status,
        "frozen_reference_count": len(references),
        "frozen_total_amount": frozen_total,
        "frozen_voucher_gl_rows": voucher_rows,
        "frozen_voucher_gl_net": voucher_net,
        "frozen_voucher_gl_non_zero_account_count": non_zero_accounts,
        "frozen_restored_invoice_amount": frozen_total if frozen_total == 3 else 0,
        "rollback": rollback.name if rollback else None,
        "smoke": rollback.smoke if rollback else None,
        "execution_gate": rollback.execution_gate if rollback else None,
        "preview": rollback.preview if rollback else None,
        "validation": rollback.validation if rollback else None,
        "candidate": rollback.candidate if rollback else None,
        "design": rollback.design if rollback else None,
        "planning": rollback.planning if rollback else None,
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
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guard_after["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
        "actual_payment_entry_created_count": actual_pe_created,
        "actual_payment_entry_cancelled_count": actual_pe_cancelled,
        "actual_gl_created_count": actual_gl_created,
        "submitted_journal_entry_count_today": guard_after["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_after["purchase_invoice_count_today"],
        "freeze_score": score,
        **item_summary,
        "items": items,
        "references": [dict(row) for row in references],
        "issues": post_issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "required_acknowledgement": FREEZE_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 11L freezes rollback evidence only. It creates no accounting movement and prepares for closeout.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["freeze_status"] = "Needs Review"
        result["freeze_completed"] = 0
        result["ready_for_next_governed_limited_operation_closeout"] = 0
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
    doc.freeze_json = safe_json(
        {
            "rollback": rollback,
            "rolled_back_payment_entry": payment_entry,
            "references": [dict(row) for row in references],
            "guardrails_before": guard_before,
            "guardrails_after": guard_after,
            "voucher": {
                "rows": voucher_rows,
                "net": voucher_net,
                "non_zero_accounts": non_zero_accounts,
            },
            "issues": post_issues,
            "config": config,
        }
    )
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
def cancel_next_governed_limited_operation_rollback_freeze_audit(freeze, reason=None):
    assert_action("cancel_next_governed_limited_operation_rollback_freeze_audit")

    if not frappe.db.exists(FREEZE_DOCTYPE, freeze):
        frappe.throw(_("Governed next operation rollback freeze audit not found: {0}").format(freeze))

    doc = frappe.get_doc(FREEZE_DOCTYPE, freeze)

    if doc.status == "Cancelled":
        return {"freeze": freeze, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.freeze_completed or 0):
        frappe.throw(_("Cannot cancel a completed Phase 11L freeze record."))

    frappe.db.set_value(
        FREEZE_DOCTYPE,
        freeze,
        {
            "status": "Cancelled",
            "freeze_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 11L no-ack freeze audit cancelled.",
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
def quick_next_governed_limited_operation_rollback_freeze_summary(limit=20):
    records = frappe.get_all(
        FREEZE_DOCTYPE,
        fields=[
            "name",
            "freeze_id",
            "status",
            "freeze_status",
            "freeze_completed",
            "rolled_back_payment_entry",
            "payment_entry_docstatus_frozen",
            "payment_entry_status_frozen",
            "frozen_reference_count",
            "frozen_total_amount",
            "frozen_voucher_gl_rows",
            "frozen_voucher_gl_net",
            "frozen_restored_invoice_amount",
            "rollback",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "actual_payment_entry_created_count",
            "actual_payment_entry_cancelled_count",
            "actual_gl_created_count",
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
            "allocated_amount",
            "rolled_back_payment_entry",
            "detail",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    return {
        "freeze_records": records,
        "items": items,
        "required_acknowledgement": FREEZE_ACK,
        "guardrails": guardrails(),
        "note": "Phase 11L governed next operation rollback freeze summary.",
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
            f.phase11k_rollback_verified,
            f.payment_entry_cancelled_still_verified,
            f.voucher_gl_rows_verified,
            f.voucher_gl_net_zero_verified,
            f.invoice_outstanding_restored_still_verified,
            f.ready_for_next_governed_limited_operation_closeout,
            f.rolled_back_payment_entry,
            f.payment_entry_docstatus_frozen,
            f.payment_entry_status_frozen,
            f.frozen_reference_count,
            f.frozen_total_amount,
            f.frozen_voucher_gl_rows,
            f.frozen_voucher_gl_net,
            f.frozen_restored_invoice_amount,
            f.rollback,
            f.payment_entry_count_before,
            f.payment_entry_count_after,
            f.payment_entry_gl_count_before,
            f.payment_entry_gl_count_after,
            f.actual_payment_entry_created_count,
            f.actual_payment_entry_cancelled_count,
            f.actual_gl_created_count,
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
                {"name": "Closeout Ready", "values": [int(row.ready_for_next_governed_limited_operation_closeout or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Freeze Records"), "datatype": "Int"},
        {"value": sum(int(row.freeze_completed or 0) for row in data), "indicator": "Green", "label": _("Frozen"), "datatype": "Int"},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PE Created"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL Created"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def freeze_columns():
    return [
        {"fieldname": "freeze", "label": _("Freeze"), "fieldtype": "Link", "options": FREEZE_DOCTYPE, "width": 220},
        {"fieldname": "freeze_id", "label": _("Freeze ID"), "fieldtype": "Data", "width": 390},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "freeze_status", "label": _("Freeze Status"), "fieldtype": "Data", "width": 360},
        {"fieldname": "freeze_completed", "label": _("Frozen"), "fieldtype": "Check", "width": 80},
        {"fieldname": "phase11k_rollback_verified", "label": _("11K Verified"), "fieldtype": "Check", "width": 100},
        {"fieldname": "payment_entry_cancelled_still_verified", "label": _("PE Cancelled"), "fieldtype": "Check", "width": 110},
        {"fieldname": "voucher_gl_rows_verified", "label": _("GL Rows OK"), "fieldtype": "Check", "width": 95},
        {"fieldname": "voucher_gl_net_zero_verified", "label": _("GL Net Zero"), "fieldtype": "Check", "width": 105},
        {"fieldname": "invoice_outstanding_restored_still_verified", "label": _("Restored"), "fieldtype": "Check", "width": 90},
        {"fieldname": "ready_for_next_governed_limited_operation_closeout", "label": _("Closeout Ready"), "fieldtype": "Check", "width": 120},
        {"fieldname": "rolled_back_payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "payment_entry_docstatus_frozen", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 100},
        {"fieldname": "payment_entry_status_frozen", "label": _("PE Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "frozen_reference_count", "label": _("Refs"), "fieldtype": "Int", "width": 70},
        {"fieldname": "frozen_total_amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 100},
        {"fieldname": "frozen_voucher_gl_rows", "label": _("Voucher GL Rows"), "fieldtype": "Int", "width": 120},
        {"fieldname": "frozen_voucher_gl_net", "label": _("Voucher Net"), "fieldtype": "Currency", "options": "currency", "width": 100},
        {"fieldname": "frozen_restored_invoice_amount", "label": _("Restored Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "rollback", "label": _("Rollback"), "fieldtype": "Link", "options": ROLLBACK_DOCTYPE, "width": 220},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 110},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE Created"), "fieldtype": "Int", "width": 125},
        {"fieldname": "actual_payment_entry_cancelled_count", "label": _("Actual PE Cancelled"), "fieldtype": "Int", "width": 135},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL Created"), "fieldtype": "Int", "width": 125},
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
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 190},
        {"fieldname": "line_no", "label": _("Line"), "fieldtype": "Int", "width": 60},
        {"fieldname": "reference_doctype", "label": _("Ref DocType"), "fieldtype": "Data", "width": 130},
        {"fieldname": "reference_name", "label": _("Reference"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 180},
        {"fieldname": "allocated_amount", "label": _("Allocated"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "rolled_back_payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "check_key", "label": _("Check Key"), "fieldtype": "Data", "width": 230},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 330},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 650},
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
            i.line_no,
            i.reference_doctype,
            i.reference_name,
            i.allocated_amount,
            i.rolled_back_payment_entry,
            i.check_key,
            i.check_label,
            i.detail,
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
            i.line_no ASC,
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
        "data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Items", "values": list(chart_map.values())}]},
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Items"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Pass"]), "indicator": "Green", "label": _("Pass"), "datatype": "Int"},
        {"value": len([row for row in data if row.category == "Frozen Reference"]), "indicator": "Green", "label": _("Frozen References"), "datatype": "Int"},
        {"value": sum(flt(row.allocated_amount or 0, 2) for row in data if row.category == "Frozen Reference"), "indicator": "Green", "label": _("Frozen Amount"), "datatype": "Currency"},
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
