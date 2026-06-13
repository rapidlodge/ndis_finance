import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


REVIEW_ACK = "I_CONFIRM_PHASE10D_REVIEW_FINAL_GUARDED_ADAPTER_POLICY_DECISION_NO_POSTING"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
REVIEW_DOCTYPE = "NDIS Guarded Adapter Final Policy Review"
ITEM_DOCTYPE = "NDIS Guarded Adapter Final Policy Review Item"
FREEZE_DOCTYPE = "NDIS Guarded Adapter Smoke Rollback Freeze"


def make_review_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-GUARDED-ADAPTER-FINAL-POLICY-REVIEW-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def decision_options():
    return [
        {
            "key": "keep_policy_enabled_for_limited_monitored_operation",
            "label": "Keep policy enabled for limited monitored operation",
            "effect": "No policy mutation in Phase 10D. A later decision phase may keep production_batch_enabled=1 and live_posting_allowed=0 with monitoring.",
            "allowed_in_phase10d": 0,
        },
        {
            "key": "disable_policy_and_return_to_locked_state",
            "label": "Disable policy and return to locked state",
            "effect": "No policy mutation in Phase 10D. A later decision phase may set production_batch_enabled=0 and keep live_posting_allowed=0.",
            "allowed_in_phase10d": 0,
        },
        {
            "key": "require_further_smoke_cycle",
            "label": "Require further smoke cycle",
            "effect": "No policy mutation in Phase 10D. A later planning phase may create another guarded smoke cycle.",
            "allowed_in_phase10d": 0,
        },
    ]


def latest_freeze():
    rows = frappe.get_all(
        FREEZE_DOCTYPE,
        filters={
            "status": "Frozen",
            "rollback_freeze_allowed": 1,
            "ready_for_final_guarded_adapter_policy_review": 1,
            "phase10b_rollback_verified": 1,
            "phase10a_smoke_verified": 1,
            "phase9z_activation_gate_verified": 1,
            "payment_entry_cancelled_verified": 1,
            "payment_entry_gl_reversal_verified": 1,
            "gl_net_zero_verified": 1,
            "invoice_outstanding_restored_verified": 1,
            "no_new_accounting_movement_verified": 1,
            "controlled_policy_enabled_verified": 1,
            "live_posting_blocked_verified": 1,
            "payment_entry_docstatus": 2,
            "payment_entry_status": "Cancelled",
            "gl_account_non_zero_count": 0,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
            "submitted_journal_entry_count_today": 0,
            "purchase_invoice_count_today": 0,
            "production_batch_enabled_policy_count": 1,
            "live_posting_allowed_policy_count": 0,
        },
        fields=[
            "name",
            "freeze_id",
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
            "invoice_reference_count",
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
            "freeze_score",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_review(freeze):
    rows = frappe.get_all(
        REVIEW_DOCTYPE,
        filters={
            "freeze": freeze,
            "status": "Approved",
            "final_policy_review_approved": 1,
            "ready_for_final_policy_decision": 1,
        },
        fields=["name", "review_id"],
        limit=1,
    )
    return rows[0] if rows else None


def validate_source(freeze, guard, config, pe_docstatus, pe_status):
    issues = []
    if not config["sandbox_enabled"]:
        issues.append("Sandbox posting config must remain enabled for this final review gate.")
    if config["production_mode"]:
        issues.append("Production mode config must remain disabled for Phase 10D.")
    if config["live_pe_enabled"]:
        issues.append("Live Payment Entry posting config must remain disabled for Phase 10D.")
    if not freeze:
        issues.append("No completed Phase 10C rollback freeze found.")
        return issues

    existing = existing_review(freeze.name)
    if existing:
        issues.append(f"Phase 10D final policy review already exists for this freeze: {existing.review_id}")

    required_links = {
        "rollback": ("NDIS Guarded Limited Adapter Smoke Rollback", freeze.rollback),
        "smoke": ("NDIS Guarded Limited Adapter Smoke", freeze.smoke),
        "activation_gate": ("NDIS Limited Batch Adapter Activation Gate", freeze.activation_gate),
        "payment_entry": ("Payment Entry", freeze.payment_entry),
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
    if int(freeze.current_target_policy_enabled or 0) != 1:
        issues.append("Freeze evidence must show current_target_policy_enabled = 1.")
    if int(freeze.current_target_policy_live or 0) != 0:
        issues.append("Freeze evidence must show current_target_policy_live = 0.")
    if int(freeze.payment_entry_docstatus or 0) != 2:
        issues.append("Freeze evidence must show payment_entry_docstatus = 2.")
    if freeze.payment_entry_status != "Cancelled":
        issues.append("Freeze evidence must show payment_entry_status = Cancelled.")
    if int(freeze.gl_account_non_zero_count or 0) != 0:
        issues.append("Freeze evidence must show GL account non-zero count = 0.")
    if abs(flt(freeze.gl_net_balance or 0, 2)) > 0.005:
        issues.append("Freeze evidence must show GL net balance = 0.")
    if int(freeze.actual_payment_entry_created_count or 0) != 0:
        issues.append("Freeze must not create Payment Entry.")
    if int(freeze.actual_gl_created_count or 0) != 0:
        issues.append("Freeze must not create GL.")
    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must remain enabled.")
    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must remain 0.")
    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today must be 0.")
    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today must be 0.")

    if freeze.target_policy:
        current_enabled = get_flag(POLICY_DOCTYPE, freeze.target_policy, "production_batch_enabled")
        current_live = get_flag(POLICY_DOCTYPE, freeze.target_policy, "live_posting_allowed")
        if current_enabled != 1:
            issues.append("Current target policy production_batch_enabled must be 1 at final review gate.")
        if current_live != 0:
            issues.append("Current target policy live_posting_allowed must be 0 at final review gate.")

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


def build_items(freeze, issues, ack_ok, pe_docstatus, guard):
    items = []
    if freeze:
        add_item(items, "Pass", "Low", "Evidence", "phase10c_freeze_exists", "Phase 10C freeze exists", f"Freeze found: {freeze.freeze_id}.", FREEZE_DOCTYPE, freeze.name)
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase10c_freeze_exists", "Phase 10C freeze exists", "No completed Phase 10C freeze found.")

    if not issues:
        add_item(items, "Pass", "Low", "Review Source", "review_source_valid", "Review source valid", "Phase 10C frozen rollback evidence is valid for final policy review.")
    else:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Review Source", "review_source_valid", "Review source valid", issue)

    if pe_docstatus == 2:
        add_item(items, "Pass", "Low", "Payment Entry", "payment_entry_cancelled", "Payment Entry cancelled", "Smoke Payment Entry remains cancelled.")
    else:
        add_item(items, "Blocker", "Critical", "Payment Entry", "payment_entry_cancelled", "Payment Entry cancelled", f"Payment Entry docstatus is {pe_docstatus}.")

    if guard["production_batch_enabled_policy_count"] == 1 and guard["live_posting_allowed_policy_count"] == 0:
        add_item(items, "Pass", "Low", "Policy", "policy_enabled_live_blocked", "Policy enabled and live blocked", "Controlled policy remains enabled while live posting remains blocked.")
    else:
        add_item(items, "Blocker", "Critical", "Policy", "policy_enabled_live_blocked", "Policy enabled and live blocked", "Policy state is not 1 enabled / 0 live.")

    for option in decision_options():
        add_item(items, "Info", "Low", "Decision Option", option["key"], option["label"], option["effect"])

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {REVIEW_ACK}")
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
        row.review = doc.name
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
def run_guarded_adapter_final_policy_review(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_guarded_adapter_final_policy_review")

    freeze = latest_freeze()
    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }
    guard_before = guardrails()
    ack_ok = acknowledgement == REVIEW_ACK

    pe_docstatus = 0
    pe_status = None
    if freeze and freeze.payment_entry and frappe.db.exists("Payment Entry", freeze.payment_entry):
        pe_doc = frappe.get_doc("Payment Entry", freeze.payment_entry)
        pe_docstatus = int(pe_doc.docstatus or 0)
        pe_status = pe_doc.status

    issues = validate_source(freeze, guard_before, config, pe_docstatus, pe_status)
    items = build_items(freeze, issues, ack_ok, pe_docstatus, guard_before)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    allowed = int(ack_ok and item_summary["blocker_count"] == 0 and bool(freeze))

    current_enabled = get_flag(POLICY_DOCTYPE, freeze.target_policy, "production_batch_enabled") if freeze else 0
    current_live = get_flag(POLICY_DOCTYPE, freeze.target_policy, "live_posting_allowed") if freeze else 0
    guard_after = guardrails()
    no_new_movement = int(
        guard_before["payment_entry_count"] == guard_after["payment_entry_count"]
        and guard_before["payment_entry_gl_count"] == guard_after["payment_entry_gl_count"]
        and guard_before["submitted_journal_entry_count_today"] == guard_after["submitted_journal_entry_count_today"]
        and guard_before["purchase_invoice_count_today"] == guard_after["purchase_invoice_count_today"]
        and guard_before["production_batch_enabled_policy_count"] == guard_after["production_batch_enabled_policy_count"]
        and guard_before["live_posting_allowed_policy_count"] == guard_after["live_posting_allowed_policy_count"]
    )

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Approved" if allowed else "Needs Review",
        "review_status": "Ready For Final Policy Decision" if allowed else "Needs Review",
        "final_policy_review_approved": allowed,
        "ready_for_final_policy_decision": allowed,
        "decision_options_prepared": 1 if freeze else 0,
        "keep_policy_enabled_option_prepared": 1 if freeze else 0,
        "disable_policy_option_prepared": 1 if freeze else 0,
        "further_smoke_cycle_option_prepared": 1 if freeze else 0,
        "selected_policy_decision": "Not Selected",
        "phase10c_freeze_verified": 1 if freeze else 0,
        "phase10b_rollback_verified": 1 if freeze else 0,
        "phase10a_smoke_verified": 1 if freeze else 0,
        "phase9z_activation_gate_verified": 1 if freeze else 0,
        "payment_entry_cancelled_verified": 1 if pe_docstatus == 2 else 0,
        "payment_entry_gl_reversal_verified": 1 if freeze and int(freeze.payment_entry_gl_reversal_count or 0) > 0 else 0,
        "gl_net_zero_verified": 1 if freeze and int(freeze.gl_account_non_zero_count or 0) == 0 and abs(flt(freeze.gl_net_balance or 0, 2)) <= 0.005 else 0,
        "invoice_outstanding_restored_verified": 1 if freeze and abs(flt(freeze.invoice_outstanding_restored_delta or 0, 2) - flt(freeze.allocated_amount_total or 0, 2)) <= 0.01 else 0,
        "no_new_accounting_movement_verified": no_new_movement,
        "controlled_policy_enabled_verified": 1 if current_enabled == 1 else 0,
        "live_posting_blocked_verified": 1 if current_live == 0 else 0,
        "freeze": freeze.name if freeze else None,
        "rollback": freeze.rollback if freeze else None,
        "smoke": freeze.smoke if freeze else None,
        "activation_gate": freeze.activation_gate if freeze else None,
        "runtime_guard": freeze.runtime_guard if freeze else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": freeze.target_policy if freeze else None,
        "target_policy_name": freeze.target_policy_name if freeze else None,
        "current_target_policy_enabled": current_enabled,
        "current_target_policy_live": current_live,
        "production_batch_enabled_policy_count": guard_before["production_batch_enabled_policy_count"],
        "live_posting_allowed_policy_count": guard_before["live_posting_allowed_policy_count"],
        "payment_entry": freeze.payment_entry if freeze else None,
        "payment_entry_docstatus": pe_docstatus,
        "payment_entry_status": pe_status,
        "payment_entry_amount": flt(freeze.payment_entry_amount or 0, 2) if freeze else 0,
        "payment_entry_reference_count": int(freeze.payment_entry_reference_count or 0) if freeze else 0,
        "payment_entry_gl_row_count": int(freeze.payment_entry_gl_row_count or 0) if freeze else 0,
        "payment_entry_gl_reversal_count": int(freeze.payment_entry_gl_reversal_count or 0) if freeze else 0,
        "invoice_reference_count": int(freeze.invoice_reference_count or 0) if freeze else 0,
        "allocated_amount_total": flt(freeze.allocated_amount_total or 0, 2) if freeze else 0,
        "invoice_outstanding_restored_delta": flt(freeze.invoice_outstanding_restored_delta or 0, 2) if freeze else 0,
        "gl_net_debit": flt(freeze.gl_net_debit or 0, 2) if freeze else 0,
        "gl_net_credit": flt(freeze.gl_net_credit or 0, 2) if freeze else 0,
        "gl_net_balance": flt(freeze.gl_net_balance or 0, 2) if freeze else 0,
        "gl_account_non_zero_count": int(freeze.gl_account_non_zero_count or 0) if freeze else 0,
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guard_after["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
        "actual_payment_entry_created_count": 0,
        "actual_gl_created_count": 0,
        "submitted_journal_entry_count_today": guard_before["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_before["purchase_invoice_count_today"],
        "review_score": score,
        **item_summary,
        "items": items,
        "issues": issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "decision_options": decision_options(),
        "config": config,
        "required_acknowledgement": REVIEW_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 10D prepares final policy decision options only. It does not mutate policy or create accounting movement.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["review_status"] = "Needs Review"
        result["final_policy_review_approved"] = 0
        result["ready_for_final_policy_decision"] = 0
        return result

    doc = frappe.new_doc(REVIEW_DOCTYPE)
    doc.review_id = make_review_id()
    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = REVIEW_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.decision_options_json = safe_json(decision_options())
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    create_items(doc, items)
    frappe.db.commit()

    return {**result, "created": True, "review": doc.name, "review_id": doc.review_id, "guardrails_after": guardrails()}


@frappe.whitelist()
def cancel_guarded_adapter_final_policy_review_audit(review, reason=None):
    assert_action("cancel_guarded_adapter_final_policy_review_audit")
    if not frappe.db.exists(REVIEW_DOCTYPE, review):
        frappe.throw(_("Final policy review audit not found: {0}").format(review))
    doc = frappe.get_doc(REVIEW_DOCTYPE, review)
    if doc.status == "Cancelled":
        return {"review": review, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.final_policy_review_approved or 0):
        frappe.throw(_("Cannot cancel an approved Phase 10D final policy review. Create a superseding review if required."))

    frappe.db.set_value(
        REVIEW_DOCTYPE,
        review,
        {
            "status": "Cancelled",
            "review_status": "Cancelled",
            "final_policy_review_approved": 0,
            "ready_for_final_policy_decision": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 10D no-ack final policy review audit cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{ITEM_DOCTYPE}` SET status = 'Cancelled' WHERE review = %(review)s", {"review": review})
    frappe.db.commit()
    return {"review": review, "status": "Cancelled", "note": "No-ack final policy review audit cancelled only. No accounting or policy movement occurred."}


@frappe.whitelist()
def quick_guarded_adapter_final_policy_review_summary(limit=20):
    reviews = frappe.get_all(
        REVIEW_DOCTYPE,
        fields=[
            "name",
            "review_id",
            "status",
            "review_status",
            "final_policy_review_approved",
            "ready_for_final_policy_decision",
            "decision_options_prepared",
            "freeze",
            "rollback",
            "smoke",
            "payment_entry",
            "payment_entry_docstatus",
            "payment_entry_status",
            "target_policy",
            "current_target_policy_enabled",
            "current_target_policy_live",
            "production_batch_enabled_policy_count",
            "live_posting_allowed_policy_count",
            "no_new_accounting_movement_verified",
            "review_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(
        ITEM_DOCTYPE,
        fields=["name", "review", "status", "severity", "category", "check_label", "detail", "source_doctype", "source_name"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "reviews": reviews,
        "items": items,
        "decision_options": decision_options(),
        "required_acknowledgement": REVIEW_ACK,
        "guardrails": guardrails(),
        "note": "Phase 10D final policy review summary. No policy or accounting movement.",
    }


def execute_review_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("r.status = %(status)s")
        params["status"] = filters.get("status")

    data = frappe.db.sql(
        f"""
        SELECT
            r.name AS review,
            r.review_id,
            r.status,
            r.review_status,
            r.final_policy_review_approved,
            r.ready_for_final_policy_decision,
            r.decision_options_prepared,
            r.freeze,
            r.rollback,
            r.smoke,
            r.payment_entry,
            r.payment_entry_docstatus,
            r.payment_entry_status,
            r.target_policy,
            r.current_target_policy_enabled,
            r.current_target_policy_live,
            r.production_batch_enabled_policy_count,
            r.live_posting_allowed_policy_count,
            r.no_new_accounting_movement_verified,
            r.actual_payment_entry_created_count,
            r.actual_gl_created_count,
            r.review_score,
            r.checked_on,
            %(currency)s AS currency
        FROM `tab{REVIEW_DOCTYPE}` r
        {build_where(conditions)}
        ORDER BY r.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.review_id for row in data[:20]],
            "datasets": [
                {"name": "Approved", "values": [int(row.final_policy_review_approved or 0) for row in data[:20]]},
                {"name": "Actual PE Created", "values": [int(row.actual_payment_entry_created_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Reviews"), "datatype": "Int"},
        {"value": sum(int(row.final_policy_review_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(int(row.ready_for_final_policy_decision or 0) for row in data), "indicator": "Green", "label": _("Ready Decision"), "datatype": "Int"},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PE"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL"), "datatype": "Int"},
    ]
    return review_columns(), data, None, chart, summary


def review_columns():
    return [
        {"fieldname": "review", "label": _("Review"), "fieldtype": "Link", "options": REVIEW_DOCTYPE, "width": 220},
        {"fieldname": "review_id", "label": _("Review ID"), "fieldtype": "Data", "width": 430},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "review_status", "label": _("Review Status"), "fieldtype": "Data", "width": 260},
        {"fieldname": "final_policy_review_approved", "label": _("Approved"), "fieldtype": "Check", "width": 90},
        {"fieldname": "ready_for_final_policy_decision", "label": _("Ready Decision"), "fieldtype": "Check", "width": 120},
        {"fieldname": "decision_options_prepared", "label": _("Options Prepared"), "fieldtype": "Check", "width": 130},
        {"fieldname": "freeze", "label": _("Phase 10C Freeze"), "fieldtype": "Link", "options": FREEZE_DOCTYPE, "width": 220},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "payment_entry_docstatus", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 100},
        {"fieldname": "payment_entry_status", "label": _("PE Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "target_policy", "label": _("Target Policy"), "fieldtype": "Data", "width": 260},
        {"fieldname": "current_target_policy_enabled", "label": _("Current Enabled"), "fieldtype": "Check", "width": 120},
        {"fieldname": "current_target_policy_live", "label": _("Current Live"), "fieldtype": "Check", "width": 110},
        {"fieldname": "production_batch_enabled_policy_count", "label": _("Enabled Policies"), "fieldtype": "Int", "width": 120},
        {"fieldname": "live_posting_allowed_policy_count", "label": _("Live Policies"), "fieldtype": "Int", "width": 110},
        {"fieldname": "no_new_accounting_movement_verified", "label": _("No New Movement"), "fieldtype": "Check", "width": 130},
        {"fieldname": "review_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("review"):
        conditions.append("i.review = %(review)s")
        params["review"] = filters.get("review")
    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": ITEM_DOCTYPE, "width": 220},
        {"fieldname": "review", "label": _("Review"), "fieldtype": "Link", "options": REVIEW_DOCTYPE, "width": 220},
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
            i.review,
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
        {"value": len([row for row in data if row.category == "Decision Option"]), "indicator": "Blue", "label": _("Decision Options"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_review_report(filters)
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
