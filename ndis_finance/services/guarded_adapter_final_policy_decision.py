import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


DECISION_ACK = "I_CONFIRM_PHASE10E_KEEP_CONTROLLED_LIMITED_OPERATION_ENABLED_NO_POSTING"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
DECISION_DOCTYPE = "NDIS Guarded Adapter Final Policy Decision"
ITEM_DOCTYPE = "NDIS Guarded Adapter Final Policy Decision Item"
REVIEW_DOCTYPE = "NDIS Guarded Adapter Final Policy Review"


def make_decision_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-GUARDED-ADAPTER-FINAL-POLICY-DECISION-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_review():
    rows = frappe.get_all(
        REVIEW_DOCTYPE,
        filters={
            "status": "Approved",
            "review_status": "Ready For Final Policy Decision",
            "final_policy_review_approved": 1,
            "ready_for_final_policy_decision": 1,
            "decision_options_prepared": 1,
            "keep_policy_enabled_option_prepared": 1,
            "disable_policy_option_prepared": 1,
            "further_smoke_cycle_option_prepared": 1,
            "selected_policy_decision": "Not Selected",
            "phase10c_freeze_verified": 1,
            "phase10b_rollback_verified": 1,
            "phase10a_smoke_verified": 1,
            "phase9z_activation_gate_verified": 1,
            "payment_entry_cancelled_verified": 1,
            "gl_net_zero_verified": 1,
            "invoice_outstanding_restored_verified": 1,
            "no_new_accounting_movement_verified": 1,
            "controlled_policy_enabled_verified": 1,
            "live_posting_blocked_verified": 1,
            "payment_entry_docstatus": 2,
            "payment_entry_status": "Cancelled",
            "current_target_policy_enabled": 1,
            "current_target_policy_live": 0,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
            "submitted_journal_entry_count_today": 0,
            "purchase_invoice_count_today": 0,
            "production_batch_enabled_policy_count": 1,
            "live_posting_allowed_policy_count": 0,
        },
        fields=[
            "name",
            "review_id",
            "freeze",
            "rollback",
            "smoke",
            "activation_gate",
            "runtime_guard",
            "target_policy_doctype",
            "target_policy",
            "target_policy_name",
            "current_target_policy_enabled",
            "current_target_policy_live",
            "production_batch_enabled_policy_count",
            "live_posting_allowed_policy_count",
            "payment_entry",
            "payment_entry_docstatus",
            "payment_entry_status",
            "payment_entry_amount",
            "payment_entry_reference_count",
            "payment_entry_gl_row_count",
            "payment_entry_gl_reversal_count",
            "allocated_amount_total",
            "invoice_outstanding_restored_delta",
            "gl_net_debit",
            "gl_net_credit",
            "gl_net_balance",
            "gl_account_non_zero_count",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
            "review_score",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_decision(review):
    rows = frappe.get_all(
        DECISION_DOCTYPE,
        filters={
            "review": review,
            "status": "Decision Applied",
            "final_policy_decision_applied": 1,
            "keep_policy_enabled_decision_applied": 1,
        },
        fields=["name", "decision_id"],
        limit=1,
    )
    return rows[0] if rows else None


def validate_source(review, guard, policy_enabled_before, policy_live_before, pe_docstatus, pe_status):
    issues = []
    if not review:
        issues.append("No approved Phase 10D final policy review found.")
        return issues

    existing = existing_decision(review.name)
    if existing:
        issues.append(f"Phase 10E final policy decision already exists for this review: {existing.decision_id}")

    required_links = {
        "freeze": ("NDIS Guarded Adapter Smoke Rollback Freeze", review.freeze),
        "rollback": ("NDIS Guarded Limited Adapter Smoke Rollback", review.rollback),
        "smoke": ("NDIS Guarded Limited Adapter Smoke", review.smoke),
        "activation_gate": ("NDIS Limited Batch Adapter Activation Gate", review.activation_gate),
        "payment_entry": ("Payment Entry", review.payment_entry),
        "target_policy": (POLICY_DOCTYPE, review.target_policy),
    }
    for label, (doctype, name) in required_links.items():
        if not name:
            issues.append(f"Missing evidence link: {label}")
        elif not frappe.db.exists(doctype, name):
            issues.append(f"Linked evidence does not exist: {doctype} {name}")

    if pe_docstatus != 2:
        issues.append(f"Payment Entry must remain cancelled docstatus 2. Current: {pe_docstatus}")
    if pe_status != "Cancelled":
        issues.append(f"Payment Entry status must remain Cancelled. Current: {pe_status}")
    if policy_enabled_before != 1:
        issues.append("Target policy production_batch_enabled must already be 1.")
    if policy_live_before != 0:
        issues.append("Target policy live_posting_allowed must remain 0.")
    if int(review.current_target_policy_enabled or 0) != 1:
        issues.append("Review evidence must show current_target_policy_enabled = 1.")
    if int(review.current_target_policy_live or 0) != 0:
        issues.append("Review evidence must show current_target_policy_live = 0.")
    if int(review.actual_payment_entry_created_count or 0) != 0:
        issues.append("Review evidence must show actual Payment Entry created = 0.")
    if int(review.actual_gl_created_count or 0) != 0:
        issues.append("Review evidence must show actual GL created = 0.")
    if int(review.gl_account_non_zero_count or 0) != 0:
        issues.append("Review evidence must show GL account non-zero count = 0.")
    if abs(flt(review.gl_net_balance or 0, 2)) > 0.005:
        issues.append("Review evidence must show GL net balance = 0.")
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


def build_items(review, issues, ack_ok, policy_enabled_before, policy_live_before, guard):
    items = []
    if review:
        add_item(items, "Pass", "Low", "Evidence", "phase10d_review_exists", "Phase 10D review exists", f"Review found: {review.review_id}.", REVIEW_DOCTYPE, review.name)
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase10d_review_exists", "Phase 10D review exists", "No approved Phase 10D review found.")

    if not issues:
        add_item(items, "Pass", "Low", "Decision Source", "decision_source_valid", "Decision source valid", "Phase 10D review is valid for final keep-enabled decision.")
    else:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Decision Source", "decision_source_valid", "Decision source valid", issue)

    if policy_enabled_before == 1 and policy_live_before == 0:
        add_item(items, "Pass", "Low", "Policy", "policy_state_before", "Policy state before decision is correct", "Policy is enabled and live posting is blocked before decision.")
    else:
        add_item(items, "Blocker", "Critical", "Policy", "policy_state_before", "Policy state before decision is correct", "Policy state is not enabled/live-blocked before decision.")

    if guard["production_batch_enabled_policy_count"] == 1 and guard["live_posting_allowed_policy_count"] == 0:
        add_item(items, "Pass", "Low", "Policy", "single_enabled_zero_live", "One enabled policy and zero live policies", "Controlled limited operation remains enabled, live posting remains blocked.")
    else:
        add_item(items, "Blocker", "Critical", "Policy", "single_enabled_zero_live", "One enabled policy and zero live policies", "Policy counts are not 1 enabled / 0 live.")

    add_item(items, "Pass", "Low", "Decision", "keep_enabled_selected", "Keep enabled decision selected", "Selected decision is Keep Policy Enabled For Limited Monitored Operation.")
    add_item(items, "Info", "Low", "Decision Effect", "no_policy_mutation_required", "No policy mutation required", "The policy was already enabled; Phase 10E preserves production_batch_enabled=1 and live_posting_allowed=0.")
    add_item(items, "Info", "Low", "Monitoring", "ready_for_monitoring", "Ready for controlled limited operations monitoring", "Next phase should create the operational monitoring layer, not enable live posting.")

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {DECISION_ACK}")
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
        row.decision = doc.name
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
def run_guarded_adapter_final_policy_decision_keep_enabled(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_guarded_adapter_final_policy_decision_keep_enabled")

    review = latest_review()
    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }
    guard_before = guardrails()
    ack_ok = acknowledgement == DECISION_ACK

    policy_enabled_before = get_flag(POLICY_DOCTYPE, review.target_policy, "production_batch_enabled") if review else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, review.target_policy, "live_posting_allowed") if review else 0

    pe_docstatus = 0
    pe_status = None
    if review and review.payment_entry and frappe.db.exists("Payment Entry", review.payment_entry):
        pe_doc = frappe.get_doc("Payment Entry", review.payment_entry)
        pe_docstatus = int(pe_doc.docstatus or 0)
        pe_status = pe_doc.status

    issues = validate_source(review, guard_before, policy_enabled_before, policy_live_before, pe_docstatus, pe_status)
    items = build_items(review, issues, ack_ok, policy_enabled_before, policy_live_before, guard_before)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    allowed = int(ack_ok and item_summary["blocker_count"] == 0 and bool(review))

    # Phase 10E is an audit decision only. It must not write policy flags.
    policy_enabled_after = get_flag(POLICY_DOCTYPE, review.target_policy, "production_batch_enabled") if review else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, review.target_policy, "live_posting_allowed") if review else 0
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

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Decision Applied" if allowed else "Needs Review",
        "decision_status": "Controlled Limited Operation Remains Enabled" if allowed else "Needs Review",
        "final_policy_decision_applied": allowed,
        "keep_policy_enabled_decision_applied": allowed,
        "ready_for_controlled_limited_operations_monitoring": allowed,
        "selected_policy_decision": "Keep Policy Enabled For Limited Monitored Operation",
        "policy_state_preserved_verified": policy_preserved,
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": 0,
        "phase10d_review_verified": 1 if review else 0,
        "phase10c_freeze_verified": 1 if review else 0,
        "phase10b_rollback_verified": 1 if review else 0,
        "phase10a_smoke_verified": 1 if review else 0,
        "phase9z_activation_gate_verified": 1 if review else 0,
        "payment_entry_cancelled_verified": 1 if pe_docstatus == 2 else 0,
        "gl_net_zero_verified": 1 if review and int(review.gl_account_non_zero_count or 0) == 0 else 0,
        "invoice_outstanding_restored_verified": 1 if review and abs(flt(review.invoice_outstanding_restored_delta or 0, 2) - flt(review.allocated_amount_total or 0, 2)) <= 0.01 else 0,
        "no_new_accounting_movement_verified": no_new_movement,
        "controlled_policy_enabled_verified": 1 if policy_enabled_after == 1 else 0,
        "live_posting_blocked_verified": 1 if policy_live_after == 0 else 0,
        "review": review.name if review else None,
        "freeze": review.freeze if review else None,
        "rollback": review.rollback if review else None,
        "smoke": review.smoke if review else None,
        "activation_gate": review.activation_gate if review else None,
        "runtime_guard": review.runtime_guard if review else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": review.target_policy if review else None,
        "target_policy_name": review.target_policy_name if review else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_before": policy_live_before,
        "target_policy_live_after": policy_live_after,
        "production_batch_enabled_policy_count_before": guard_before["production_batch_enabled_policy_count"],
        "production_batch_enabled_policy_count_after": guard_after["production_batch_enabled_policy_count"],
        "live_posting_allowed_policy_count_before": guard_before["live_posting_allowed_policy_count"],
        "live_posting_allowed_policy_count_after": guard_after["live_posting_allowed_policy_count"],
        "payment_entry": review.payment_entry if review else None,
        "payment_entry_docstatus": pe_docstatus,
        "payment_entry_status": pe_status,
        "payment_entry_amount": flt(review.payment_entry_amount or 0, 2) if review else 0,
        "payment_entry_reference_count": int(review.payment_entry_reference_count or 0) if review else 0,
        "payment_entry_gl_row_count": int(review.payment_entry_gl_row_count or 0) if review else 0,
        "payment_entry_gl_reversal_count": int(review.payment_entry_gl_reversal_count or 0) if review else 0,
        "allocated_amount_total": flt(review.allocated_amount_total or 0, 2) if review else 0,
        "invoice_outstanding_restored_delta": flt(review.invoice_outstanding_restored_delta or 0, 2) if review else 0,
        "gl_net_debit": flt(review.gl_net_debit or 0, 2) if review else 0,
        "gl_net_credit": flt(review.gl_net_credit or 0, 2) if review else 0,
        "gl_net_balance": flt(review.gl_net_balance or 0, 2) if review else 0,
        "gl_account_non_zero_count": int(review.gl_account_non_zero_count or 0) if review else 0,
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guard_after["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
        "actual_payment_entry_created_count": 0,
        "actual_gl_created_count": 0,
        "submitted_journal_entry_count_today": guard_before["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_before["purchase_invoice_count_today"],
        "decision_score": score,
        **item_summary,
        "items": items,
        "issues": issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "config": config,
        "required_acknowledgement": DECISION_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 10E applies the keep-enabled final decision by evidence. It does not mutate policy flags and creates no accounting movement.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["decision_status"] = "Needs Review"
        result["final_policy_decision_applied"] = 0
        result["keep_policy_enabled_decision_applied"] = 0
        result["ready_for_controlled_limited_operations_monitoring"] = 0
        return result

    doc = frappe.new_doc(DECISION_DOCTYPE)
    doc.decision_id = make_decision_id()
    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = DECISION_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    create_items(doc, items)
    frappe.db.commit()
    return {**result, "created": True, "decision": doc.name, "decision_id": doc.decision_id, "guardrails_after": guardrails()}


@frappe.whitelist()
def cancel_guarded_adapter_final_policy_decision_audit(decision, reason=None):
    assert_action("cancel_guarded_adapter_final_policy_decision_audit")
    if not frappe.db.exists(DECISION_DOCTYPE, decision):
        frappe.throw(_("Final policy decision audit not found: {0}").format(decision))
    doc = frappe.get_doc(DECISION_DOCTYPE, decision)
    if doc.status == "Cancelled":
        return {"decision": decision, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.final_policy_decision_applied or 0):
        frappe.throw(_("Cannot cancel an applied Phase 10E final policy decision. Create a superseding governance decision if required."))

    frappe.db.set_value(
        DECISION_DOCTYPE,
        decision,
        {
            "status": "Cancelled",
            "decision_status": "Cancelled",
            "final_policy_decision_applied": 0,
            "keep_policy_enabled_decision_applied": 0,
            "ready_for_controlled_limited_operations_monitoring": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 10E no-ack final policy decision audit cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{ITEM_DOCTYPE}` SET status = 'Cancelled' WHERE decision = %(decision)s", {"decision": decision})
    frappe.db.commit()
    return {"decision": decision, "status": "Cancelled", "note": "No-ack final policy decision audit cancelled only. No accounting or policy movement occurred."}


@frappe.whitelist()
def quick_guarded_adapter_final_policy_decision_summary(limit=20):
    decisions = frappe.get_all(
        DECISION_DOCTYPE,
        fields=[
            "name",
            "decision_id",
            "status",
            "decision_status",
            "final_policy_decision_applied",
            "keep_policy_enabled_decision_applied",
            "ready_for_controlled_limited_operations_monitoring",
            "selected_policy_decision",
            "policy_state_preserved_verified",
            "policy_mutation_performed",
            "actual_policy_mutation_count",
            "review",
            "freeze",
            "payment_entry",
            "payment_entry_docstatus",
            "payment_entry_status",
            "target_policy",
            "target_policy_enabled_before",
            "target_policy_enabled_after",
            "target_policy_live_before",
            "target_policy_live_after",
            "production_batch_enabled_policy_count_before",
            "production_batch_enabled_policy_count_after",
            "live_posting_allowed_policy_count_before",
            "live_posting_allowed_policy_count_after",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
            "decision_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(
        ITEM_DOCTYPE,
        fields=["name", "decision", "status", "severity", "category", "check_label", "detail", "source_doctype", "source_name"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "decisions": decisions,
        "items": items,
        "required_acknowledgement": DECISION_ACK,
        "guardrails": guardrails(),
        "note": "Phase 10E final keep-enabled policy decision summary. No policy mutation and no accounting movement.",
    }


def execute_decision_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("d.status = %(status)s")
        params["status"] = filters.get("status")

    data = frappe.db.sql(
        f"""
        SELECT
            d.name AS decision,
            d.decision_id,
            d.status,
            d.decision_status,
            d.final_policy_decision_applied,
            d.keep_policy_enabled_decision_applied,
            d.ready_for_controlled_limited_operations_monitoring,
            d.selected_policy_decision,
            d.policy_state_preserved_verified,
            d.policy_mutation_performed,
            d.actual_policy_mutation_count,
            d.review,
            d.freeze,
            d.payment_entry,
            d.payment_entry_docstatus,
            d.payment_entry_status,
            d.target_policy,
            d.target_policy_enabled_before,
            d.target_policy_enabled_after,
            d.target_policy_live_before,
            d.target_policy_live_after,
            d.production_batch_enabled_policy_count_before,
            d.production_batch_enabled_policy_count_after,
            d.live_posting_allowed_policy_count_before,
            d.live_posting_allowed_policy_count_after,
            d.actual_payment_entry_created_count,
            d.actual_gl_created_count,
            d.decision_score,
            d.checked_on,
            %(currency)s AS currency
        FROM `tab{DECISION_DOCTYPE}` d
        {build_where(conditions)}
        ORDER BY d.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.decision_id for row in data[:20]],
            "datasets": [
                {"name": "Decision Applied", "values": [int(row.final_policy_decision_applied or 0) for row in data[:20]]},
                {"name": "Policy Mutations", "values": [int(row.actual_policy_mutation_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Decisions"), "datatype": "Int"},
        {"value": sum(int(row.final_policy_decision_applied or 0) for row in data), "indicator": "Green", "label": _("Applied"), "datatype": "Int"},
        {"value": sum(int(row.keep_policy_enabled_decision_applied or 0) for row in data), "indicator": "Green", "label": _("Keep Enabled"), "datatype": "Int"},
        {"value": sum(int(row.actual_policy_mutation_count or 0) for row in data), "indicator": "Orange", "label": _("Policy Mutations"), "datatype": "Int"},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PE"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL"), "datatype": "Int"},
    ]
    return decision_columns(), data, None, chart, summary


def decision_columns():
    return [
        {"fieldname": "decision", "label": _("Decision"), "fieldtype": "Link", "options": DECISION_DOCTYPE, "width": 220},
        {"fieldname": "decision_id", "label": _("Decision ID"), "fieldtype": "Data", "width": 430},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 130},
        {"fieldname": "decision_status", "label": _("Decision Status"), "fieldtype": "Data", "width": 300},
        {"fieldname": "final_policy_decision_applied", "label": _("Applied"), "fieldtype": "Check", "width": 80},
        {"fieldname": "keep_policy_enabled_decision_applied", "label": _("Keep Enabled"), "fieldtype": "Check", "width": 110},
        {"fieldname": "ready_for_controlled_limited_operations_monitoring", "label": _("Ready Monitoring"), "fieldtype": "Check", "width": 130},
        {"fieldname": "selected_policy_decision", "label": _("Selected Decision"), "fieldtype": "Data", "width": 330},
        {"fieldname": "policy_state_preserved_verified", "label": _("State Preserved"), "fieldtype": "Check", "width": 120},
        {"fieldname": "policy_mutation_performed", "label": _("Mutation"), "fieldtype": "Check", "width": 90},
        {"fieldname": "actual_policy_mutation_count", "label": _("Mutation Count"), "fieldtype": "Int", "width": 120},
        {"fieldname": "review", "label": _("Phase 10D Review"), "fieldtype": "Link", "options": REVIEW_DOCTYPE, "width": 220},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "payment_entry_docstatus", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 100},
        {"fieldname": "payment_entry_status", "label": _("PE Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "target_policy", "label": _("Target Policy"), "fieldtype": "Data", "width": 260},
        {"fieldname": "target_policy_enabled_before", "label": _("Enabled Before"), "fieldtype": "Check", "width": 115},
        {"fieldname": "target_policy_enabled_after", "label": _("Enabled After"), "fieldtype": "Check", "width": 110},
        {"fieldname": "target_policy_live_before", "label": _("Live Before"), "fieldtype": "Check", "width": 100},
        {"fieldname": "target_policy_live_after", "label": _("Live After"), "fieldtype": "Check", "width": 95},
        {"fieldname": "production_batch_enabled_policy_count_after", "label": _("Enabled Policies"), "fieldtype": "Int", "width": 120},
        {"fieldname": "live_posting_allowed_policy_count_after", "label": _("Live Policies"), "fieldtype": "Int", "width": 110},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "decision_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("decision"):
        conditions.append("i.decision = %(decision)s")
        params["decision"] = filters.get("decision")
    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": ITEM_DOCTYPE, "width": 220},
        {"fieldname": "decision", "label": _("Decision"), "fieldtype": "Link", "options": DECISION_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 170},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 320},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 620},
        {"fieldname": "source_doctype", "label": _("Source DocType"), "fieldtype": "Data", "width": 220},
        {"fieldname": "source_name", "label": _("Source Name"), "fieldtype": "Data", "width": 240},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            i.name AS item,
            i.decision,
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
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Items", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Items"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Pass"]), "indicator": "Green", "label": _("Pass"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Warning"]), "indicator": "Orange", "label": _("Warnings"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Blocker"]), "indicator": "Red", "label": _("Blockers"), "datatype": "Int"},
        {"value": len([row for row in data if row.category == "Decision"]), "indicator": "Green", "label": _("Decision Rows"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_decision_report(filters)
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
