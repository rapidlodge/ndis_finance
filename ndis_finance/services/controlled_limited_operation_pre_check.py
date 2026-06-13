import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


PRE_CHECK_ACK = "I_CONFIRM_PHASE10G_APPROVE_SINGLE_GUARDED_OPERATION_PRE_CHECK_NO_POSTING"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"


def make_pre_check_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-CONTROLLED-LIMITED-OP-PRE-CHECK-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_register():
    rows = frappe.get_all(
        "NDIS Controlled Limited Operations Monitoring Register",
        filters={
            "status": "Active",
            "monitoring_status": "Controlled Limited Operations Monitoring Active",
            "monitoring_register_active": 1,
            "ready_for_guarded_limited_operations": 1,
            "ready_for_pre_operation_monitoring_check": 1,
            "monitoring_controls_frozen": 1,
            "policy_state_preserved_verified": 1,
            "policy_mutation_performed": 0,
            "actual_policy_mutation_count": 0,
            "phase10e_decision_verified": 1,
            "phase10d_review_verified": 1,
            "phase10c_freeze_verified": 1,
            "payment_entry_cancelled_verified": 1,
            "no_new_accounting_movement_verified": 1,
            "controlled_policy_enabled_verified": 1,
            "live_posting_blocked_verified": 1,
            "target_policy_enabled_after": 1,
            "target_policy_live_after": 0,
            "production_batch_enabled_policy_count_after": 1,
            "live_posting_allowed_policy_count_after": 0,
            "max_batch_line_count": 3,
            "max_payment_entry_count": 1,
            "live_posting_allowed": 0,
            "journal_entry_side_effect_allowed": 0,
            "purchase_invoice_side_effect_allowed": 0,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
            "submitted_journal_entry_count_today": 0,
            "purchase_invoice_count_today": 0,
        },
        fields=[
            "name",
            "register_id",
            "decision",
            "review",
            "freeze",
            "rollback",
            "smoke",
            "activation_gate",
            "runtime_guard",
            "target_policy_doctype",
            "target_policy",
            "target_policy_name",
            "target_policy_enabled_before",
            "target_policy_enabled_after",
            "target_policy_live_before",
            "target_policy_live_after",
            "production_batch_enabled_policy_count_before",
            "production_batch_enabled_policy_count_after",
            "live_posting_allowed_policy_count_before",
            "live_posting_allowed_policy_count_after",
            "max_batch_line_count",
            "max_batch_amount",
            "max_payment_entry_count",
            "live_posting_allowed",
            "journal_entry_side_effect_allowed",
            "purchase_invoice_side_effect_allowed",
            "pre_operation_monitoring_required",
            "post_operation_reconciliation_required",
            "payment_entry",
            "payment_entry_docstatus",
            "payment_entry_status",
            "payment_entry_amount",
            "payment_entry_reference_count",
            "payment_entry_gl_row_count",
            "allocated_amount_total",
            "invoice_outstanding_restored_delta",
            "gl_net_debit",
            "gl_net_credit",
            "gl_net_balance",
            "gl_account_non_zero_count",
            "monitoring_score",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )

    return rows[0] if rows else None


def existing_approved_pre_check(register):
    rows = frappe.get_all(
        "NDIS Controlled Limited Operation Pre Check",
        filters={
            "monitoring_register": register,
            "status": "Approved",
            "pre_operation_check_approved": 1,
            "ready_for_single_guarded_operation_preview": 1,
        },
        fields=["name", "pre_check_id"],
        limit=1,
    )
    return rows[0] if rows else None


def requested_shape(
    requested_batch_line_count=3,
    requested_batch_amount=3,
    requested_payment_entry_count=1,
    live_posting_requested=0,
    journal_entry_side_effect_requested=0,
    purchase_invoice_side_effect_requested=0,
):
    return {
        "requested_batch_line_count": int(requested_batch_line_count or 0),
        "requested_batch_amount": flt(requested_batch_amount or 0, 2),
        "requested_payment_entry_count": int(requested_payment_entry_count or 0),
        "live_posting_requested": int(live_posting_requested or 0),
        "journal_entry_side_effect_requested": int(journal_entry_side_effect_requested or 0),
        "purchase_invoice_side_effect_requested": int(purchase_invoice_side_effect_requested or 0),
    }


def validate_source(register, guard, policy_enabled_before, policy_live_before, pe_docstatus, pe_status, shape):
    issues = []

    if not register:
        issues.append("No active Phase 10F controlled limited operations monitoring register found.")
        return issues

    existing = existing_approved_pre_check(register.name)
    if existing:
        issues.append(f"An approved Phase 10G pre-check already exists for this register: {existing.pre_check_id}")

    required_links = {
        "decision": ("NDIS Guarded Adapter Final Policy Decision", register.decision),
        "review": ("NDIS Guarded Adapter Final Policy Review", register.review),
        "monitoring_register": ("NDIS Controlled Limited Operations Monitoring Register", register.name),
        "payment_entry": ("Payment Entry", register.payment_entry),
        "target_policy": (POLICY_DOCTYPE, register.target_policy),
    }

    for label, pair in required_links.items():
        doctype, name = pair
        if not name:
            issues.append(f"Missing evidence link: {label}")
        elif not frappe.db.exists(doctype, name):
            issues.append(f"Linked evidence does not exist: {doctype} {name}")

    if pe_docstatus != 2:
        issues.append(f"Historical smoke Payment Entry must remain cancelled docstatus 2. Current: {pe_docstatus}")

    if pe_status != "Cancelled":
        issues.append(f"Historical smoke Payment Entry status must remain Cancelled. Current: {pe_status}")

    if policy_enabled_before != 1:
        issues.append("Target policy production_batch_enabled must be 1.")

    if policy_live_before != 0:
        issues.append("Target policy live_posting_allowed must be 0.")

    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must remain enabled.")

    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must remain 0.")

    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today must be 0.")

    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today must be 0.")

    if shape["requested_batch_line_count"] <= 0:
        issues.append("Requested batch line count must be greater than 0.")

    if shape["requested_batch_line_count"] > int(register.max_batch_line_count or 0):
        issues.append("Requested batch line count exceeds monitoring limit.")

    if shape["requested_batch_amount"] <= 0:
        issues.append("Requested batch amount must be greater than 0.")

    if shape["requested_batch_amount"] > flt(register.max_batch_amount or 0, 2):
        issues.append("Requested batch amount exceeds monitoring limit.")

    if shape["requested_payment_entry_count"] <= 0:
        issues.append("Requested Payment Entry count must be greater than 0.")

    if shape["requested_payment_entry_count"] > int(register.max_payment_entry_count or 0):
        issues.append("Requested Payment Entry count exceeds monitoring limit.")

    if shape["live_posting_requested"] != 0:
        issues.append("Live posting request is blocked.")

    if shape["journal_entry_side_effect_requested"] != 0:
        issues.append("Journal Entry side effect request is blocked.")

    if shape["purchase_invoice_side_effect_requested"] != 0:
        issues.append("Purchase Invoice side effect request is blocked.")

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


def build_items(register, issues, ack_ok, shape):
    items = []

    if register:
        add_item(
            items,
            "Pass",
            "Low",
            "Evidence",
            "phase10f_register_exists",
            "Phase 10F register exists",
            f"Register found: {register.register_id}.",
            "NDIS Controlled Limited Operations Monitoring Register",
            register.name,
        )
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase10f_register_exists", "Phase 10F register exists", "No active Phase 10F register found.")

    if not issues:
        add_item(items, "Pass", "Low", "Pre-Check Source", "pre_check_source_valid", "Pre-check source valid", "Phase 10F register and requested operation shape are valid.")
    else:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Pre-Check Source", "pre_check_source_valid", "Pre-check source valid", issue)

    if register:
        checks = [
            (
                shape["requested_batch_line_count"] <= int(register.max_batch_line_count or 0),
                "Operation Shape",
                "line_count_limit",
                "Requested line count within limit",
                f"{shape['requested_batch_line_count']} <= {int(register.max_batch_line_count or 0)}",
            ),
            (
                shape["requested_batch_amount"] <= flt(register.max_batch_amount or 0, 2),
                "Operation Shape",
                "amount_limit",
                "Requested amount within limit",
                f"{shape['requested_batch_amount']} <= {flt(register.max_batch_amount or 0, 2)}",
            ),
            (
                shape["requested_payment_entry_count"] <= int(register.max_payment_entry_count or 0),
                "Operation Shape",
                "payment_entry_count_limit",
                "Requested Payment Entry count within limit",
                f"{shape['requested_payment_entry_count']} <= {int(register.max_payment_entry_count or 0)}",
            ),
            (
                shape["live_posting_requested"] == 0,
                "Operation Shape",
                "live_posting_blocked",
                "Live posting request blocked",
                f"live_posting_requested = {shape['live_posting_requested']}",
            ),
            (
                shape["journal_entry_side_effect_requested"] == 0,
                "Operation Shape",
                "je_side_effect_blocked",
                "Journal Entry side effect blocked",
                f"journal_entry_side_effect_requested = {shape['journal_entry_side_effect_requested']}",
            ),
            (
                shape["purchase_invoice_side_effect_requested"] == 0,
                "Operation Shape",
                "pi_side_effect_blocked",
                "Purchase Invoice side effect blocked",
                f"purchase_invoice_side_effect_requested = {shape['purchase_invoice_side_effect_requested']}",
            ),
        ]

        for passed, category, key, label, detail in checks:
            add_item(
                items,
                "Pass" if passed else "Blocker",
                "Low" if passed else "Critical",
                category,
                key,
                label,
                detail,
            )

    add_item(
        items,
        "Info",
        "Low",
        "Scope",
        "one_operation_only",
        "Approval is for one operation only",
        "Phase 10G approves only one upcoming guarded limited operation preview shape.",
    )

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {PRE_CHECK_ACK}")

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
        row = frappe.new_doc("NDIS Controlled Limited Operation Pre Check Item")
        row.pre_check = doc.name
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
def run_controlled_limited_operation_pre_check(
    dry_run=1,
    acknowledgement=None,
    requested_batch_line_count=3,
    requested_batch_amount=3,
    requested_payment_entry_count=1,
    live_posting_requested=0,
    journal_entry_side_effect_requested=0,
    purchase_invoice_side_effect_requested=0,
    notes=None,
):
    assert_action("run_controlled_limited_operation_pre_check")

    register = latest_register()

    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }

    guard_before = guardrails()
    ack_ok = acknowledgement == PRE_CHECK_ACK

    shape = requested_shape(
        requested_batch_line_count=requested_batch_line_count,
        requested_batch_amount=requested_batch_amount,
        requested_payment_entry_count=requested_payment_entry_count,
        live_posting_requested=live_posting_requested,
        journal_entry_side_effect_requested=journal_entry_side_effect_requested,
        purchase_invoice_side_effect_requested=purchase_invoice_side_effect_requested,
    )

    policy_enabled_before = get_flag(POLICY_DOCTYPE, register.target_policy, "production_batch_enabled") if register else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, register.target_policy, "live_posting_allowed") if register else 0

    pe_docstatus = 0
    pe_status = None

    if register and register.payment_entry and frappe.db.exists("Payment Entry", register.payment_entry):
        pe_doc = frappe.get_doc("Payment Entry", register.payment_entry)
        pe_docstatus = int(pe_doc.docstatus or 0)
        pe_status = pe_doc.status

    issues = validate_source(register, guard_before, policy_enabled_before, policy_live_before, pe_docstatus, pe_status, shape)
    items = build_items(register, issues, ack_ok, shape)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    allowed = int(ack_ok and item_summary["blocker_count"] == 0 and bool(register))

    policy_enabled_after = get_flag(POLICY_DOCTYPE, register.target_policy, "production_batch_enabled") if register else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, register.target_policy, "live_posting_allowed") if register else 0
    guard_after = guardrails()

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

    line_ok = int(register and shape["requested_batch_line_count"] <= int(register.max_batch_line_count or 0))
    amount_ok = int(register and shape["requested_batch_amount"] <= flt(register.max_batch_amount or 0, 2))
    pe_count_ok = int(register and shape["requested_payment_entry_count"] <= int(register.max_payment_entry_count or 0))
    live_blocked = int(shape["live_posting_requested"] == 0)
    je_blocked = int(shape["journal_entry_side_effect_requested"] == 0)
    pi_blocked = int(shape["purchase_invoice_side_effect_requested"] == 0)

    operation_shape_validated = int(
        line_ok
        and amount_ok
        and pe_count_ok
        and live_blocked
        and je_blocked
        and pi_blocked
        and no_new_movement
    )

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Approved" if allowed else "Needs Review",
        "check_status": "Ready For One Guarded Limited Operation" if allowed else "Needs Review",
        "pre_operation_check_approved": allowed,
        "ready_for_single_guarded_operation_preview": allowed,
        "operation_shape_validated": operation_shape_validated,
        "one_operation_only": 1 if register else 0,
        "policy_state_preserved_verified": policy_preserved,
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": 0,
        "phase10f_register_verified": 1 if register else 0,
        "phase10e_decision_verified": 1 if register else 0,
        "phase10d_review_verified": 1 if register else 0,
        "phase10c_freeze_verified": 1 if register else 0,
        "payment_entry_cancelled_verified": 1 if pe_docstatus == 2 else 0,
        "gl_net_zero_verified": 1 if register and int(register.gl_account_non_zero_count or 0) == 0 else 0,
        "invoice_outstanding_restored_verified": 1 if register and abs(flt(register.invoice_outstanding_restored_delta or 0, 2) - flt(register.allocated_amount_total or 0, 2)) <= 0.01 else 0,
        "no_new_accounting_movement_verified": no_new_movement,
        "controlled_policy_enabled_verified": 1 if policy_enabled_after == 1 else 0,
        "live_posting_blocked_verified": 1 if policy_live_after == 0 else 0,
        "monitoring_register": register.name if register else None,
        "decision": register.decision if register else None,
        "review": register.review if register else None,
        "freeze": register.freeze if register else None,
        "rollback": register.rollback if register else None,
        "smoke": register.smoke if register else None,
        "activation_gate": register.activation_gate if register else None,
        "runtime_guard": register.runtime_guard if register else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": register.target_policy if register else None,
        "target_policy_name": register.target_policy_name if register else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_before": policy_live_before,
        "target_policy_live_after": policy_live_after,
        "production_batch_enabled_policy_count_before": guard_before["production_batch_enabled_policy_count"],
        "production_batch_enabled_policy_count_after": guard_after["production_batch_enabled_policy_count"],
        "live_posting_allowed_policy_count_before": guard_before["live_posting_allowed_policy_count"],
        "live_posting_allowed_policy_count_after": guard_after["live_posting_allowed_policy_count"],
        "max_batch_line_count": int(register.max_batch_line_count or 0) if register else 0,
        "max_batch_amount": flt(register.max_batch_amount or 0, 2) if register else 0,
        "max_payment_entry_count": int(register.max_payment_entry_count or 0) if register else 0,
        "live_posting_allowed": int(register.live_posting_allowed or 0) if register else 0,
        "journal_entry_side_effect_allowed": int(register.journal_entry_side_effect_allowed or 0) if register else 0,
        "purchase_invoice_side_effect_allowed": int(register.purchase_invoice_side_effect_allowed or 0) if register else 0,
        "pre_operation_monitoring_required": int(register.pre_operation_monitoring_required or 0) if register else 0,
        "post_operation_reconciliation_required": int(register.post_operation_reconciliation_required or 0) if register else 0,
        **shape,
        "batch_line_count_within_limit": line_ok,
        "batch_amount_within_limit": amount_ok,
        "payment_entry_count_within_limit": pe_count_ok,
        "live_posting_request_blocked": live_blocked,
        "journal_entry_side_effect_blocked": je_blocked,
        "purchase_invoice_side_effect_blocked": pi_blocked,
        "payment_entry": register.payment_entry if register else None,
        "payment_entry_docstatus": pe_docstatus,
        "payment_entry_status": pe_status,
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guard_after["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
        "actual_payment_entry_created_count": 0,
        "actual_gl_created_count": 0,
        "submitted_journal_entry_count_today": guard_before["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_before["purchase_invoice_count_today"],
        "pre_check_score": score,
        **item_summary,
        "items": items,
        "issues": issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "operation_shape": shape,
        "config": config,
        "required_acknowledgement": PRE_CHECK_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 10G approves one upcoming guarded operation shape only. It creates no accounting movement and does not mutate policy flags.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["check_status"] = "Needs Review"
        result["pre_operation_check_approved"] = 0
        result["ready_for_single_guarded_operation_preview"] = 0
        return result

    doc = frappe.new_doc("NDIS Controlled Limited Operation Pre Check")
    doc.pre_check_id = make_pre_check_id()

    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)

    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = PRE_CHECK_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.operation_shape_json = safe_json(shape)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    create_items(doc, items)
    frappe.db.commit()

    return {
        **result,
        "created": True,
        "pre_check": doc.name,
        "pre_check_id": doc.pre_check_id,
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_controlled_limited_operation_pre_check_audit(pre_check, reason=None):
    assert_action("cancel_controlled_limited_operation_pre_check_audit")

    if not frappe.db.exists("NDIS Controlled Limited Operation Pre Check", pre_check):
        frappe.throw(_("Pre-check audit not found: {0}").format(pre_check))

    doc = frappe.get_doc("NDIS Controlled Limited Operation Pre Check", pre_check)

    if doc.status == "Cancelled":
        return {"pre_check": pre_check, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.pre_operation_check_approved or 0):
        frappe.throw(_("Cannot cancel an approved Phase 10G pre-check. Create a superseding governance record if required."))

    frappe.db.set_value(
        "NDIS Controlled Limited Operation Pre Check",
        pre_check,
        {
            "status": "Cancelled",
            "check_status": "Cancelled",
            "pre_operation_check_approved": 0,
            "ready_for_single_guarded_operation_preview": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 10G no-ack pre-check audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        """
        UPDATE `tabNDIS Controlled Limited Operation Pre Check Item`
        SET status = 'Cancelled'
        WHERE pre_check = %(pre_check)s
        """,
        {"pre_check": pre_check},
    )

    frappe.db.commit()

    return {
        "pre_check": pre_check,
        "status": "Cancelled",
        "note": "No-ack pre-check audit cancelled only. No accounting or policy movement occurred.",
    }


@frappe.whitelist()
def quick_controlled_limited_operation_pre_check_summary(limit=20):
    pre_checks = frappe.get_all(
        "NDIS Controlled Limited Operation Pre Check",
        fields=[
            "name",
            "pre_check_id",
            "status",
            "check_status",
            "pre_operation_check_approved",
            "ready_for_single_guarded_operation_preview",
            "operation_shape_validated",
            "monitoring_register",
            "target_policy",
            "target_policy_enabled_before",
            "target_policy_enabled_after",
            "target_policy_live_before",
            "target_policy_live_after",
            "requested_batch_line_count",
            "requested_batch_amount",
            "requested_payment_entry_count",
            "live_posting_requested",
            "journal_entry_side_effect_requested",
            "purchase_invoice_side_effect_requested",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
            "pre_check_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    items = frappe.get_all(
        "NDIS Controlled Limited Operation Pre Check Item",
        fields=[
            "name",
            "pre_check",
            "status",
            "severity",
            "category",
            "check_label",
            "detail",
            "source_doctype",
            "source_name",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    return {
        "pre_checks": pre_checks,
        "items": items,
        "required_acknowledgement": PRE_CHECK_ACK,
        "guardrails": guardrails(),
        "note": "Phase 10G pre-operation check summary. One operation shape only. No policy mutation and no accounting movement.",
    }


def execute_pre_check_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("status"):
        conditions.append("p.status = %(status)s")
        params["status"] = filters.get("status")

    columns = pre_check_columns()

    data = frappe.db.sql(
        f"""
        SELECT
            p.name AS pre_check,
            p.pre_check_id,
            p.status,
            p.check_status,
            p.pre_operation_check_approved,
            p.ready_for_single_guarded_operation_preview,
            p.operation_shape_validated,
            p.monitoring_register,
            p.target_policy,
            p.target_policy_enabled_after,
            p.target_policy_live_after,
            p.requested_batch_line_count,
            p.requested_batch_amount,
            p.requested_payment_entry_count,
            p.live_posting_requested,
            p.journal_entry_side_effect_requested,
            p.purchase_invoice_side_effect_requested,
            p.actual_payment_entry_created_count,
            p.actual_gl_created_count,
            p.pre_check_score,
            p.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Controlled Limited Operation Pre Check` p
        {build_where(conditions)}
        ORDER BY p.creation DESC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.pre_check_id for row in data[:20]],
            "datasets": [
                {"name": "Approved", "values": [int(row.pre_operation_check_approved or 0) for row in data[:20]]},
                {"name": "Actual PE Created", "values": [int(row.actual_payment_entry_created_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Pre Checks"), "datatype": "Int"},
        {"value": sum(int(row.pre_operation_check_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(int(row.ready_for_single_guarded_operation_preview or 0) for row in data), "indicator": "Green", "label": _("Ready Preview"), "datatype": "Int"},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PE"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def pre_check_columns():
    return [
        {"fieldname": "pre_check", "label": _("Pre Check"), "fieldtype": "Link", "options": "NDIS Controlled Limited Operation Pre Check", "width": 220},
        {"fieldname": "pre_check_id", "label": _("Pre Check ID"), "fieldtype": "Data", "width": 420},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "check_status", "label": _("Check Status"), "fieldtype": "Data", "width": 300},
        {"fieldname": "pre_operation_check_approved", "label": _("Approved"), "fieldtype": "Check", "width": 90},
        {"fieldname": "ready_for_single_guarded_operation_preview", "label": _("Ready Preview"), "fieldtype": "Check", "width": 120},
        {"fieldname": "operation_shape_validated", "label": _("Shape Validated"), "fieldtype": "Check", "width": 130},
        {"fieldname": "monitoring_register", "label": _("Register"), "fieldtype": "Link", "options": "NDIS Controlled Limited Operations Monitoring Register", "width": 220},
        {"fieldname": "target_policy", "label": _("Target Policy"), "fieldtype": "Data", "width": 260},
        {"fieldname": "target_policy_enabled_after", "label": _("Enabled"), "fieldtype": "Check", "width": 85},
        {"fieldname": "target_policy_live_after", "label": _("Live"), "fieldtype": "Check", "width": 75},
        {"fieldname": "requested_batch_line_count", "label": _("Req Lines"), "fieldtype": "Int", "width": 90},
        {"fieldname": "requested_batch_amount", "label": _("Req Amount"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "requested_payment_entry_count", "label": _("Req PE"), "fieldtype": "Int", "width": 80},
        {"fieldname": "live_posting_requested", "label": _("Live Requested"), "fieldtype": "Check", "width": 120},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "pre_check_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    if filters.get("pre_check"):
        conditions.append("i.pre_check = %(pre_check)s")
        params["pre_check"] = filters.get("pre_check")

    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": "NDIS Controlled Limited Operation Pre Check Item", "width": 220},
        {"fieldname": "pre_check", "label": _("Pre Check"), "fieldtype": "Link", "options": "NDIS Controlled Limited Operation Pre Check", "width": 220},
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
            i.pre_check,
            i.status,
            i.severity,
            i.category,
            i.check_label,
            i.detail,
            i.source_doctype,
            i.source_name,
            i.checked_on
        FROM `tabNDIS Controlled Limited Operation Pre Check Item` i
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
        {"value": len([row for row in data if row.category == "Operation Shape"]), "indicator": "Blue", "label": _("Shape Checks"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_pre_check_report(filters)

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
