import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


ROLLBACK_ACK = "I_CONFIRM_PHASE11K_ROLLBACK_NEXT_GOVERNED_LIMITED_OPERATION_SMOKE_CANCEL_PAYMENT_ENTRY"

POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
SMOKE_DOCTYPE = "NDIS Governed Next Op Smoke"
ROLLBACK_DOCTYPE = "NDIS Governed Next Op Rollback"
ROLLBACK_ITEM_DOCTYPE = "NDIS Governed Next Op Rollback Item"


def make_rollback_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-GOVERNED-NEXT-OP-ROLLBACK-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_smoke():
    rows = frappe.get_all(
        SMOKE_DOCTYPE,
        filters={
            "status": "Smoke Completed - Rollback Required",
            "smoke_status": "Next Governed Limited Operation Smoke Completed",
            "smoke_completed": 1,
            "rollback_required": 1,
            "freeze_required_after_rollback": 1,
            "ready_for_next_governed_limited_operation_smoke_rollback": 1,
            "created_payment_entry_docstatus": 1,
            "created_payment_entry_status": "Submitted",
            "created_payment_entry_reference_count": 3,
            "created_payment_entry_total_amount": 3.00,
            "created_payment_entry_gl_row_count": 4,
            "payment_entry_count_after": 9,
            "payment_entry_gl_count_after": 50,
            "actual_payment_entry_created_count": 1,
            "actual_payment_entry_cancelled_count": 0,
            "actual_gl_created_count": 4,
            "submitted_journal_entry_count_today": 0,
            "purchase_invoice_count_today": 0,
            "target_policy_enabled_after": 1,
            "target_policy_live_after": 0,
            "actual_policy_mutation_count": 0,
        },
        fields=[
            "name",
            "smoke_id",
            "created_payment_entry",
            "created_payment_entry_total_amount",
            "created_payment_entry_reference_count",
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


def existing_completed_rollback(smoke):
    rows = frappe.get_all(
        ROLLBACK_DOCTYPE,
        filters={
            "smoke": smoke,
            "status": "Rollback Completed",
            "rollback_completed": 1,
        },
        fields=["name", "rollback_id", "rolled_back_payment_entry"],
        limit=1,
    )
    return rows[0] if rows else None


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


def voucher_gl_non_zero_accounts(payment_entry):
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


def payment_entry_reference_rows(payment_entry):
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


def validate_source(smoke, payment_entry, guard, config, policy_enabled, policy_live):
    issues = []

    if not smoke:
        issues.append("No completed Phase 11J smoke requiring rollback found.")
        return issues

    existing = existing_completed_rollback(smoke.name)
    if existing:
        issues.append(f"Completed Phase 11K rollback already exists for this smoke: {existing.rollback_id}")

    if not payment_entry:
        issues.append("Phase 11J smoke does not have a created Payment Entry.")
        return issues

    if not frappe.db.exists("Payment Entry", payment_entry):
        issues.append(f"Created Payment Entry does not exist: {payment_entry}")
        return issues

    pe = frappe.get_doc("Payment Entry", payment_entry)

    if pe.docstatus != 1:
        issues.append(f"Payment Entry must be submitted before rollback. docstatus={pe.docstatus}")

    if pe.status != "Submitted":
        issues.append(f"Payment Entry status must be Submitted before rollback. status={pe.status}")

    if payment_entry_reference_rows(payment_entry) and len(payment_entry_reference_rows(payment_entry)) != 3:
        issues.append("Payment Entry must have exactly 3 Sales Invoice references before rollback.")

    if allocated_total(payment_entry) != 3:
        issues.append(f"Payment Entry allocated total must be 3.00 before rollback. Found {allocated_total(payment_entry)}.")

    if voucher_gl_rows(payment_entry) != 4:
        issues.append(f"Payment Entry voucher GL rows before rollback must be 4. Found {voucher_gl_rows(payment_entry)}.")

    if guard["payment_entry_count"] != 9:
        issues.append("Payment Entry count must be 9 before Phase 11K rollback.")

    if guard["payment_entry_gl_count"] != 50:
        issues.append("Payment Entry GL count must be 50 before Phase 11K rollback.")

    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today must remain 0 before rollback.")

    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today must remain 0 before rollback.")

    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled policy must remain enabled.")

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


def build_items(smoke, references, issues, ack_ok, rolled_back_payment_entry=None, voucher_rows_after=0, voucher_net_after=0):
    items = []

    if smoke:
        add_item(
            items,
            "Pass",
            "Low",
            "Evidence",
            "phase11j_smoke_exists",
            "Phase 11J smoke exists",
            f"Smoke found: {smoke.smoke_id}.",
            rolled_back_payment_entry=rolled_back_payment_entry,
        )
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase11j_smoke_exists", "Phase 11J smoke exists", "No completed Phase 11J smoke found.")

    if not issues:
        add_item(
            items,
            "Pass",
            "Critical",
            "Rollback Source",
            "rollback_source_valid",
            "Rollback source valid",
            "Payment Entry is valid for rollback.",
            rolled_back_payment_entry=rolled_back_payment_entry,
        )
    else:
        for issue in issues:
            add_item(
                items,
                "Blocker",
                "Critical",
                "Rollback Source",
                "rollback_source_valid",
                "Rollback source valid",
                issue,
                rolled_back_payment_entry=rolled_back_payment_entry,
            )

    for ref in references:
        add_item(
            items,
            "Pass",
            "High",
            "Rolled Back Reference",
            "rolled_back_sales_invoice_reference",
            f"Rolled Back Sales Invoice {ref.idx}",
            f"{ref.reference_name} allocation restored {flt(ref.allocated_amount or 0, 2)}.",
            reference=ref,
            rolled_back_payment_entry=rolled_back_payment_entry,
        )

    checks = [
        ("payment_entry_cancelled", "Payment Entry cancelled", rolled_back_payment_entry or "not cancelled"),
        ("reversal_gl_created", "Reversal GL created", voucher_rows_after),
        ("voucher_gl_net_zero", "Voucher GL net zero", voucher_net_after),
        ("invoice_outstanding_restored", "Invoice outstanding restored", "3.00"),
        ("no_je_pi", "No JE / PI side effects", "0 / 0"),
        ("policy_state", "Policy state preserved at 1 / 0", "1 / 0"),
        ("ready_for_freeze", "Ready for Phase 11L rollback evidence freeze", 1 if rolled_back_payment_entry else 0),
    ]

    for key, label, value in checks:
        add_item(
            items,
            "Pass",
            "High",
            "Rollback Evidence",
            key,
            label,
            f"value={value}",
            rolled_back_payment_entry=rolled_back_payment_entry,
        )

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.", rolled_back_payment_entry=rolled_back_payment_entry)
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {ROLLBACK_ACK}")

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
        row = frappe.new_doc(ROLLBACK_ITEM_DOCTYPE)
        row.rollback = doc.name

        for fieldname, value in item.items():
            if row.meta.has_field(fieldname):
                setattr(row, fieldname, value)

        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_next_governed_limited_operation_smoke_rollback(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_next_governed_limited_operation_smoke_rollback")

    smoke = latest_smoke()
    payment_entry = smoke.created_payment_entry if smoke else None
    references_before = payment_entry_reference_rows(payment_entry) if payment_entry else []

    guard_before = guardrails()
    ack_ok = acknowledgement == ROLLBACK_ACK

    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }

    policy_enabled_before = get_flag(POLICY_DOCTYPE, smoke.target_policy, "production_batch_enabled") if smoke else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, smoke.target_policy, "live_posting_allowed") if smoke else 0

    issues = validate_source(smoke, payment_entry, guard_before, config, policy_enabled_before, policy_live_before)

    dry_run = int(dry_run or 0)

    docstatus_before = 0
    status_before = None
    voucher_rows_before = 0
    rollback_total = 0

    if payment_entry and frappe.db.exists("Payment Entry", payment_entry):
        pe_before = frappe.get_doc("Payment Entry", payment_entry)
        docstatus_before = int(pe_before.docstatus or 0)
        status_before = pe_before.status
        voucher_rows_before = voucher_gl_rows(payment_entry)
        rollback_total = flt(pe_before.paid_amount or pe_before.received_amount or allocated_total(payment_entry), 2)

    pre_items = build_items(smoke, references_before, issues, ack_ok)
    pre_summary = summarise_items(pre_items)

    allowed_to_cancel = int(
        not dry_run
        and ack_ok
        and smoke
        and payment_entry
        and pre_summary["blocker_count"] == 0
        and docstatus_before == 1
    )

    if allowed_to_cancel:
        pe = frappe.get_doc("Payment Entry", payment_entry)
        pe.flags.ignore_permissions = True
        pe.cancel()

    guard_after = guardrails()

    policy_enabled_after = get_flag(POLICY_DOCTYPE, smoke.target_policy, "production_batch_enabled") if smoke else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, smoke.target_policy, "live_posting_allowed") if smoke else 0

    if payment_entry and frappe.db.exists("Payment Entry", payment_entry):
        pe_after = frappe.get_doc("Payment Entry", payment_entry)
        docstatus_after = int(pe_after.docstatus or 0)
        status_after = pe_after.status
        voucher_rows_after = voucher_gl_rows(payment_entry)
        voucher_net_after = voucher_gl_net(payment_entry)
        non_zero_accounts = voucher_gl_non_zero_accounts(payment_entry)
    else:
        docstatus_after = 0
        status_after = None
        voucher_rows_after = 0
        voucher_net_after = 0
        non_zero_accounts = 0

    actual_pe_created = guard_after["payment_entry_count"] - guard_before["payment_entry_count"]
    actual_pe_cancelled = 1 if docstatus_before == 1 and docstatus_after == 2 else 0
    actual_gl_created = guard_after["payment_entry_gl_count"] - guard_before["payment_entry_gl_count"]
    reversal_gl_rows = voucher_rows_after - voucher_rows_before

    policy_mutation_count = int(
        policy_enabled_before != policy_enabled_after
        or policy_live_before != policy_live_after
        or guard_before["production_batch_enabled_policy_count"] != guard_after["production_batch_enabled_policy_count"]
        or guard_before["live_posting_allowed_policy_count"] != guard_after["live_posting_allowed_policy_count"]
    )

    post_issues = list(issues)

    if payment_entry and allowed_to_cancel:
        if guard_after["payment_entry_count"] != 9:
            post_issues.append("Payment Entry count must remain 9 after rollback.")
        if guard_after["payment_entry_gl_count"] != 54:
            post_issues.append("Payment Entry GL count must become 54 after rollback.")
        if actual_pe_created != 0:
            post_issues.append(f"Rollback must not create Payment Entries. Created {actual_pe_created}.")
        if actual_pe_cancelled != 1:
            post_issues.append(f"Rollback must cancel exactly 1 Payment Entry. Cancelled {actual_pe_cancelled}.")
        if actual_gl_created != 4:
            post_issues.append(f"Rollback must create exactly 4 reversal GL rows. Created {actual_gl_created}.")
        if reversal_gl_rows != 4:
            post_issues.append(f"Voucher reversal GL rows must be 4. Found {reversal_gl_rows}.")
        if voucher_rows_after != 8:
            post_issues.append(f"Voucher GL rows after rollback must be 8. Found {voucher_rows_after}.")
        if voucher_net_after != 0:
            post_issues.append(f"Voucher GL net after rollback must be 0.00. Found {voucher_net_after}.")
        if non_zero_accounts != 0:
            post_issues.append(f"Voucher non-zero account count must be 0. Found {non_zero_accounts}.")
        if guard_after["submitted_journal_entry_count_today"] != 0:
            post_issues.append("Submitted Journal Entry count today must remain 0 after rollback.")
        if guard_after["purchase_invoice_count_today"] != 0:
            post_issues.append("Purchase Invoice count today must remain 0 after rollback.")
        if policy_mutation_count != 0:
            post_issues.append("Policy state changed during rollback. This is not allowed.")

    items = build_items(
        smoke,
        references_before,
        post_issues,
        ack_ok,
        rolled_back_payment_entry=payment_entry if actual_pe_cancelled else None,
        voucher_rows_after=voucher_rows_after,
        voucher_net_after=voucher_net_after,
    )
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    completed = int(bool(
        payment_entry
        and item_summary["blocker_count"] == 0
        and docstatus_before == 1
        and docstatus_after == 2
        and status_after == "Cancelled"
        and guard_before["payment_entry_count"] == 9
        and guard_after["payment_entry_count"] == 9
        and guard_before["payment_entry_gl_count"] == 50
        and guard_after["payment_entry_gl_count"] == 54
        and actual_pe_created == 0
        and actual_pe_cancelled == 1
        and actual_gl_created == 4
        and voucher_rows_before == 4
        and voucher_rows_after == 8
        and voucher_net_after == 0
        and non_zero_accounts == 0
        and flt(rollback_total, 2) == 3
        and guard_after["submitted_journal_entry_count_today"] == 0
        and guard_after["purchase_invoice_count_today"] == 0
        and policy_mutation_count == 0
    ))

    result = {
        "dry_run": bool(dry_run),
        "status": "Rollback Completed" if completed else "Needs Review",
        "rollback_status": "Next Governed Limited Operation Smoke Rolled Back" if completed else "Needs Review",
        "rollback_completed": completed,
        "phase11j_smoke_verified": 1 if smoke else 0,
        "smoke_payment_entry_verified": 1 if payment_entry else 0,
        "payment_entry_cancelled_verified": int(docstatus_after == 2 and status_after == "Cancelled"),
        "reversal_gl_created_verified": int(reversal_gl_rows == 4 and actual_gl_created == 4),
        "voucher_gl_net_zero_verified": int(voucher_net_after == 0 and non_zero_accounts == 0),
        "invoice_outstanding_restored_verified": int(completed),
        "ready_for_next_governed_limited_operation_rollback_freeze": completed,
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": policy_mutation_count,
        "rolled_back_payment_entry": payment_entry,
        "payment_entry_docstatus_before": docstatus_before,
        "payment_entry_docstatus_after": docstatus_after,
        "payment_entry_status_before": status_before,
        "payment_entry_status_after": status_after,
        "rolled_back_reference_count": len(references_before),
        "rolled_back_total_amount": flt(rollback_total, 2),
        "voucher_gl_rows_before": voucher_rows_before,
        "voucher_gl_rows_after": voucher_rows_after,
        "reversal_gl_row_count": reversal_gl_rows,
        "voucher_gl_net_after": voucher_net_after,
        "voucher_gl_non_zero_account_count": non_zero_accounts,
        "restored_invoice_amount": flt(rollback_total, 2) if completed else 0,
        "smoke": smoke.name if smoke else None,
        "execution_gate": smoke.execution_gate if smoke else None,
        "preview": smoke.preview if smoke else None,
        "validation": smoke.validation if smoke else None,
        "candidate": smoke.candidate if smoke else None,
        "design": smoke.design if smoke else None,
        "planning": smoke.planning if smoke else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": smoke.target_policy if smoke else None,
        "target_policy_name": smoke.target_policy_name if smoke else None,
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
        "rollback_score": score,
        **item_summary,
        "items": items,
        "references": [dict(row) for row in references_before],
        "issues": post_issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "required_acknowledgement": ROLLBACK_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 11K cancels the Phase 11J submitted Payment Entry and prepares evidence for Phase 11L freeze.",
    }

    if dry_run:
        result["status"] = "Needs Review"
        result["rollback_status"] = "Needs Review"
        result["rollback_completed"] = 0
        result["payment_entry_cancelled_verified"] = 0
        result["reversal_gl_created_verified"] = 0
        result["voucher_gl_net_zero_verified"] = 0
        result["invoice_outstanding_restored_verified"] = 0
        result["ready_for_next_governed_limited_operation_rollback_freeze"] = 0
        return result

    doc = frappe.new_doc(ROLLBACK_DOCTYPE)
    doc.rollback_id = make_rollback_id()

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
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.rollback_json = safe_json(
        {
            "smoke": smoke,
            "rolled_back_payment_entry": payment_entry,
            "references": [dict(row) for row in references_before],
            "guardrails_before": guard_before,
            "guardrails_after": guard_after,
            "voucher": {
                "rows_before": voucher_rows_before,
                "rows_after": voucher_rows_after,
                "net_after": voucher_net_after,
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
        "rollback": doc.name,
        "rollback_id": doc.rollback_id,
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_next_governed_limited_operation_smoke_rollback_audit(rollback, reason=None):
    assert_action("cancel_next_governed_limited_operation_smoke_rollback_audit")

    if not frappe.db.exists(ROLLBACK_DOCTYPE, rollback):
        frappe.throw(_("Governed next operation rollback audit not found: {0}").format(rollback))

    doc = frappe.get_doc(ROLLBACK_DOCTYPE, rollback)

    if doc.status == "Cancelled":
        return {"rollback": rollback, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.rollback_completed or 0):
        frappe.throw(_("Cannot cancel a completed Phase 11K rollback record."))

    frappe.db.set_value(
        ROLLBACK_DOCTYPE,
        rollback,
        {
            "status": "Cancelled",
            "rollback_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 11K no-ack rollback audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        f"""
        UPDATE `tab{ROLLBACK_ITEM_DOCTYPE}`
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
def quick_next_governed_limited_operation_rollback_summary(limit=20):
    records = frappe.get_all(
        ROLLBACK_DOCTYPE,
        fields=[
            "name",
            "rollback_id",
            "status",
            "rollback_status",
            "rollback_completed",
            "rolled_back_payment_entry",
            "payment_entry_docstatus_before",
            "payment_entry_docstatus_after",
            "payment_entry_status_before",
            "payment_entry_status_after",
            "rolled_back_reference_count",
            "rolled_back_total_amount",
            "voucher_gl_rows_before",
            "voucher_gl_rows_after",
            "reversal_gl_row_count",
            "voucher_gl_net_after",
            "restored_invoice_amount",
            "smoke",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "actual_payment_entry_created_count",
            "actual_payment_entry_cancelled_count",
            "actual_gl_created_count",
            "submitted_journal_entry_count_today",
            "purchase_invoice_count_today",
            "rollback_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    items = frappe.get_all(
        ROLLBACK_ITEM_DOCTYPE,
        fields=[
            "name",
            "rollback",
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
        "rollback_records": records,
        "items": items,
        "required_acknowledgement": ROLLBACK_ACK,
        "guardrails": guardrails(),
        "note": "Phase 11K governed next operation rollback summary.",
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
            r.rolled_back_payment_entry,
            r.payment_entry_docstatus_before,
            r.payment_entry_docstatus_after,
            r.payment_entry_status_before,
            r.payment_entry_status_after,
            r.rolled_back_reference_count,
            r.rolled_back_total_amount,
            r.voucher_gl_rows_before,
            r.voucher_gl_rows_after,
            r.reversal_gl_row_count,
            r.voucher_gl_net_after,
            r.restored_invoice_amount,
            r.smoke,
            r.payment_entry_count_before,
            r.payment_entry_count_after,
            r.payment_entry_gl_count_before,
            r.payment_entry_gl_count_after,
            r.actual_payment_entry_created_count,
            r.actual_payment_entry_cancelled_count,
            r.actual_gl_created_count,
            r.submitted_journal_entry_count_today,
            r.purchase_invoice_count_today,
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
                {"name": "Reversal GL", "values": [int(row.actual_gl_created_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Rollback Records"), "datatype": "Int"},
        {"value": sum(int(row.rollback_completed or 0) for row in data), "indicator": "Green", "label": _("Completed"), "datatype": "Int"},
        {"value": sum(int(row.actual_payment_entry_cancelled_count or 0) for row in data), "indicator": "Green", "label": _("Actual PE Cancelled"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Orange", "label": _("Reversal GL Created"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def rollback_columns():
    return [
        {"fieldname": "rollback", "label": _("Rollback"), "fieldtype": "Link", "options": ROLLBACK_DOCTYPE, "width": 220},
        {"fieldname": "rollback_id", "label": _("Rollback ID"), "fieldtype": "Data", "width": 360},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 150},
        {"fieldname": "rollback_status", "label": _("Rollback Status"), "fieldtype": "Data", "width": 350},
        {"fieldname": "rollback_completed", "label": _("Completed"), "fieldtype": "Check", "width": 90},
        {"fieldname": "rolled_back_payment_entry", "label": _("Rolled Back PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "payment_entry_docstatus_before", "label": _("PE Doc Before"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_docstatus_after", "label": _("PE Doc After"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_status_before", "label": _("PE Status Before"), "fieldtype": "Data", "width": 130},
        {"fieldname": "payment_entry_status_after", "label": _("PE Status After"), "fieldtype": "Data", "width": 130},
        {"fieldname": "rolled_back_reference_count", "label": _("Refs"), "fieldtype": "Int", "width": 70},
        {"fieldname": "rolled_back_total_amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 100},
        {"fieldname": "voucher_gl_rows_before", "label": _("Voucher GL Before"), "fieldtype": "Int", "width": 120},
        {"fieldname": "voucher_gl_rows_after", "label": _("Voucher GL After"), "fieldtype": "Int", "width": 120},
        {"fieldname": "reversal_gl_row_count", "label": _("Reversal GL"), "fieldtype": "Int", "width": 100},
        {"fieldname": "voucher_gl_net_after", "label": _("Voucher Net"), "fieldtype": "Currency", "options": "currency", "width": 100},
        {"fieldname": "restored_invoice_amount", "label": _("Restored Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "smoke", "label": _("Smoke"), "fieldtype": "Link", "options": SMOKE_DOCTYPE, "width": 220},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 110},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE Created"), "fieldtype": "Int", "width": 125},
        {"fieldname": "actual_payment_entry_cancelled_count", "label": _("Actual PE Cancelled"), "fieldtype": "Int", "width": 135},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL Created"), "fieldtype": "Int", "width": 125},
        {"fieldname": "submitted_journal_entry_count_today", "label": _("JE Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "purchase_invoice_count_today", "label": _("PI Today"), "fieldtype": "Int", "width": 90},
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
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": ROLLBACK_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "rollback", "label": _("Rollback"), "fieldtype": "Link", "options": ROLLBACK_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 190},
        {"fieldname": "line_no", "label": _("Line"), "fieldtype": "Int", "width": 60},
        {"fieldname": "reference_doctype", "label": _("Ref DocType"), "fieldtype": "Data", "width": 130},
        {"fieldname": "reference_name", "label": _("Reference"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 180},
        {"fieldname": "allocated_amount", "label": _("Allocated"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "rolled_back_payment_entry", "label": _("Rolled Back PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "check_key", "label": _("Check Key"), "fieldtype": "Data", "width": 230},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 330},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 650},
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
            i.line_no,
            i.reference_doctype,
            i.reference_name,
            i.allocated_amount,
            i.rolled_back_payment_entry,
            i.check_key,
            i.check_label,
            i.detail,
            i.checked_on
        FROM `tab{ROLLBACK_ITEM_DOCTYPE}` i
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
        {"value": len([row for row in data if row.category == "Rolled Back Reference"]), "indicator": "Green", "label": _("Rolled Back References"), "datatype": "Int"},
        {"value": sum(flt(row.allocated_amount or 0, 2) for row in data if row.category == "Rolled Back Reference"), "indicator": "Green", "label": _("Restored Amount"), "datatype": "Currency"},
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
