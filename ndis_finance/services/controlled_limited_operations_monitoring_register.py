import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


REGISTER_ACK = "I_CONFIRM_PHASE10F_ACTIVATE_CONTROLLED_LIMITED_OPERATIONS_MONITORING_NO_POSTING"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
REGISTER_DOCTYPE = "NDIS Controlled Limited Operations Monitoring Register"
ITEM_DOCTYPE = "NDIS Controlled Limited Operations Monitoring Register Item"
DECISION_DOCTYPE = "NDIS Guarded Adapter Final Policy Decision"


def make_register_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-CONTROLLED-LIMITED-OPS-MONITORING-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def monitoring_controls():
    return {
        "max_batch_line_count": 3,
        "max_batch_amount": 3.00,
        "max_payment_entry_count": 1,
        "live_posting_allowed": 0,
        "journal_entry_side_effect_allowed": 0,
        "purchase_invoice_side_effect_allowed": 0,
        "pre_operation_monitoring_required": 1,
        "post_operation_reconciliation_required": 1,
        "rollback_evidence_required": 1,
        "freeze_evidence_required": 1,
    }


def latest_decision():
    rows = frappe.get_all(
        DECISION_DOCTYPE,
        filters={
            "status": "Decision Applied",
            "decision_status": "Controlled Limited Operation Remains Enabled",
            "final_policy_decision_applied": 1,
            "keep_policy_enabled_decision_applied": 1,
            "ready_for_controlled_limited_operations_monitoring": 1,
            "selected_policy_decision": "Keep Policy Enabled For Limited Monitored Operation",
            "policy_state_preserved_verified": 1,
            "policy_mutation_performed": 0,
            "actual_policy_mutation_count": 0,
            "phase10d_review_verified": 1,
            "phase10c_freeze_verified": 1,
            "phase10b_rollback_verified": 1,
            "phase10a_smoke_verified": 1,
            "payment_entry_cancelled_verified": 1,
            "gl_net_zero_verified": 1,
            "invoice_outstanding_restored_verified": 1,
            "no_new_accounting_movement_verified": 1,
            "controlled_policy_enabled_verified": 1,
            "live_posting_blocked_verified": 1,
            "target_policy_enabled_before": 1,
            "target_policy_enabled_after": 1,
            "target_policy_live_before": 0,
            "target_policy_live_after": 0,
            "production_batch_enabled_policy_count_before": 1,
            "production_batch_enabled_policy_count_after": 1,
            "live_posting_allowed_policy_count_before": 0,
            "live_posting_allowed_policy_count_after": 0,
            "payment_entry_docstatus": 2,
            "payment_entry_status": "Cancelled",
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
            "submitted_journal_entry_count_today": 0,
            "purchase_invoice_count_today": 0,
        },
        fields=[
            "name",
            "decision_id",
            "review",
            "freeze",
            "rollback",
            "smoke",
            "activation_gate",
            "runtime_guard",
            "target_policy_doctype",
            "target_policy",
            "target_policy_name",
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
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_active_register(decision):
    rows = frappe.get_all(
        REGISTER_DOCTYPE,
        filters={
            "decision": decision,
            "status": "Active",
            "monitoring_register_active": 1,
            "ready_for_guarded_limited_operations": 1,
        },
        fields=["name", "register_id"],
        limit=1,
    )
    return rows[0] if rows else None


def validate_source(decision, guard, policy_enabled_before, policy_live_before, pe_docstatus, pe_status):
    issues = []
    if not decision:
        issues.append("No applied Phase 10E keep-enabled decision found.")
        return issues

    existing = existing_active_register(decision.name)
    if existing:
        issues.append(f"Phase 10F monitoring register already active for this decision: {existing.register_id}")

    required_links = {
        "review": ("NDIS Guarded Adapter Final Policy Review", decision.review),
        "freeze": ("NDIS Guarded Adapter Smoke Rollback Freeze", decision.freeze),
        "rollback": ("NDIS Guarded Limited Adapter Smoke Rollback", decision.rollback),
        "smoke": ("NDIS Guarded Limited Adapter Smoke", decision.smoke),
        "payment_entry": ("Payment Entry", decision.payment_entry),
        "target_policy": (POLICY_DOCTYPE, decision.target_policy),
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

    controls = monitoring_controls()
    if controls["max_batch_line_count"] != 3:
        issues.append("Monitoring control max_batch_line_count must be 3.")
    if flt(controls["max_batch_amount"], 2) != 3:
        issues.append("Monitoring control max_batch_amount must be 3.00.")
    if controls["max_payment_entry_count"] != 1:
        issues.append("Monitoring control max_payment_entry_count must be 1.")
    if controls["live_posting_allowed"] != 0:
        issues.append("Monitoring control live_posting_allowed must be 0.")
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


def build_items(decision, issues, ack_ok, policy_enabled_before, policy_live_before, guard):
    items = []
    if decision:
        add_item(items, "Pass", "Low", "Evidence", "phase10e_decision_exists", "Phase 10E decision exists", f"Decision found: {decision.decision_id}.", DECISION_DOCTYPE, decision.name)
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase10e_decision_exists", "Phase 10E decision exists", "No applied Phase 10E decision found.")

    if not issues:
        add_item(items, "Pass", "Low", "Monitoring Source", "monitoring_source_valid", "Monitoring source valid", "Phase 10E keep-enabled decision is valid for monitoring register activation.")
    else:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Monitoring Source", "monitoring_source_valid", "Monitoring source valid", issue)

    if policy_enabled_before == 1 and policy_live_before == 0:
        add_item(items, "Pass", "Low", "Policy", "policy_enabled_live_blocked", "Policy enabled and live blocked", "Policy remains production_batch_enabled=1 and live_posting_allowed=0.")
    else:
        add_item(items, "Blocker", "Critical", "Policy", "policy_enabled_live_blocked", "Policy enabled and live blocked", "Policy state is not enabled/live-blocked.")

    if guard["production_batch_enabled_policy_count"] == 1 and guard["live_posting_allowed_policy_count"] == 0:
        add_item(items, "Pass", "Low", "Policy", "policy_counts", "Policy counts valid", "One enabled controlled policy and zero live policies.")
    else:
        add_item(items, "Blocker", "Critical", "Policy", "policy_counts", "Policy counts valid", "Policy counts are not 1 enabled / 0 live.")

    controls = monitoring_controls()
    control_labels = [
        ("max_batch_line_count", "Max 3 lines per guarded operation"),
        ("max_batch_amount", "Max $3.00 per guarded operation"),
        ("max_payment_entry_count", "Max 1 Payment Entry per guarded operation"),
        ("live_posting_allowed", "Live posting remains blocked"),
        ("journal_entry_side_effect_allowed", "Journal Entry side effect blocked"),
        ("purchase_invoice_side_effect_allowed", "Purchase Invoice side effect blocked"),
        ("pre_operation_monitoring_required", "Pre-operation monitoring required"),
        ("post_operation_reconciliation_required", "Post-operation reconciliation required"),
        ("rollback_evidence_required", "Rollback evidence required for smoke"),
        ("freeze_evidence_required", "Freeze evidence required after rollback"),
    ]
    for key, label in control_labels:
        add_item(items, "Pass", "Low", "Monitoring Control", key, label, f"{key} = {controls[key]}")

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {REGISTER_ACK}")
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
        row.register = doc.name
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
def run_controlled_limited_operations_monitoring_register(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_controlled_limited_operations_monitoring_register")

    decision = latest_decision()
    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }
    guard_before = guardrails()
    ack_ok = acknowledgement == REGISTER_ACK

    policy_enabled_before = get_flag(POLICY_DOCTYPE, decision.target_policy, "production_batch_enabled") if decision else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, decision.target_policy, "live_posting_allowed") if decision else 0

    pe_docstatus = 0
    pe_status = None
    if decision and decision.payment_entry and frappe.db.exists("Payment Entry", decision.payment_entry):
        pe_doc = frappe.get_doc("Payment Entry", decision.payment_entry)
        pe_docstatus = int(pe_doc.docstatus or 0)
        pe_status = pe_doc.status

    issues = validate_source(decision, guard_before, policy_enabled_before, policy_live_before, pe_docstatus, pe_status)
    items = build_items(decision, issues, ack_ok, policy_enabled_before, policy_live_before, guard_before)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    allowed = int(ack_ok and item_summary["blocker_count"] == 0 and bool(decision))
    controls = monitoring_controls()

    # Phase 10F records monitoring readiness only. It must not write policy flags.
    policy_enabled_after = get_flag(POLICY_DOCTYPE, decision.target_policy, "production_batch_enabled") if decision else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, decision.target_policy, "live_posting_allowed") if decision else 0
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
        "status": "Active" if allowed else "Needs Review",
        "monitoring_status": "Controlled Limited Operations Monitoring Active" if allowed else "Needs Review",
        "monitoring_register_active": allowed,
        "ready_for_guarded_limited_operations": allowed,
        "ready_for_pre_operation_monitoring_check": allowed,
        "monitoring_controls_frozen": 1 if decision else 0,
        "policy_state_preserved_verified": policy_preserved,
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": 0,
        "phase10e_decision_verified": 1 if decision else 0,
        "phase10d_review_verified": 1 if decision else 0,
        "phase10c_freeze_verified": 1 if decision else 0,
        "phase10b_rollback_verified": 1 if decision else 0,
        "phase10a_smoke_verified": 1 if decision else 0,
        "payment_entry_cancelled_verified": 1 if pe_docstatus == 2 else 0,
        "gl_net_zero_verified": 1 if decision and int(decision.gl_account_non_zero_count or 0) == 0 else 0,
        "invoice_outstanding_restored_verified": 1 if decision and abs(flt(decision.invoice_outstanding_restored_delta or 0, 2) - flt(decision.allocated_amount_total or 0, 2)) <= 0.01 else 0,
        "no_new_accounting_movement_verified": no_new_movement,
        "controlled_policy_enabled_verified": 1 if policy_enabled_after == 1 else 0,
        "live_posting_blocked_verified": 1 if policy_live_after == 0 else 0,
        "decision": decision.name if decision else None,
        "review": decision.review if decision else None,
        "freeze": decision.freeze if decision else None,
        "rollback": decision.rollback if decision else None,
        "smoke": decision.smoke if decision else None,
        "activation_gate": decision.activation_gate if decision else None,
        "runtime_guard": decision.runtime_guard if decision else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": decision.target_policy if decision else None,
        "target_policy_name": decision.target_policy_name if decision else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_before": policy_live_before,
        "target_policy_live_after": policy_live_after,
        "production_batch_enabled_policy_count_before": guard_before["production_batch_enabled_policy_count"],
        "production_batch_enabled_policy_count_after": guard_after["production_batch_enabled_policy_count"],
        "live_posting_allowed_policy_count_before": guard_before["live_posting_allowed_policy_count"],
        "live_posting_allowed_policy_count_after": guard_after["live_posting_allowed_policy_count"],
        "payment_entry": decision.payment_entry if decision else None,
        "payment_entry_docstatus": pe_docstatus,
        "payment_entry_status": pe_status,
        "payment_entry_amount": flt(decision.payment_entry_amount or 0, 2) if decision else 0,
        "payment_entry_reference_count": int(decision.payment_entry_reference_count or 0) if decision else 0,
        "payment_entry_gl_row_count": int(decision.payment_entry_gl_row_count or 0) if decision else 0,
        "allocated_amount_total": flt(decision.allocated_amount_total or 0, 2) if decision else 0,
        "invoice_outstanding_restored_delta": flt(decision.invoice_outstanding_restored_delta or 0, 2) if decision else 0,
        "gl_net_debit": flt(decision.gl_net_debit or 0, 2) if decision else 0,
        "gl_net_credit": flt(decision.gl_net_credit or 0, 2) if decision else 0,
        "gl_net_balance": flt(decision.gl_net_balance or 0, 2) if decision else 0,
        "gl_account_non_zero_count": int(decision.gl_account_non_zero_count or 0) if decision else 0,
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guard_after["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
        "actual_payment_entry_created_count": 0,
        "actual_gl_created_count": 0,
        "submitted_journal_entry_count_today": guard_before["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_before["purchase_invoice_count_today"],
        "monitoring_score": score,
        **controls,
        **item_summary,
        "items": items,
        "issues": issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "monitoring_controls": controls,
        "config": config,
        "required_acknowledgement": REGISTER_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 10F activates monitoring register only. It creates no accounting movement and does not mutate policy flags.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["monitoring_status"] = "Needs Review"
        result["monitoring_register_active"] = 0
        result["ready_for_guarded_limited_operations"] = 0
        result["ready_for_pre_operation_monitoring_check"] = 0
        return result

    doc = frappe.new_doc(REGISTER_DOCTYPE)
    doc.register_id = make_register_id()
    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = REGISTER_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.monitoring_controls_json = safe_json(controls)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    create_items(doc, items)
    frappe.db.commit()
    return {**result, "created": True, "register": doc.name, "register_id": doc.register_id, "guardrails_after": guardrails()}


@frappe.whitelist()
def cancel_controlled_limited_operations_monitoring_register_audit(register, reason=None):
    assert_action("cancel_controlled_limited_operations_monitoring_register_audit")
    if not frappe.db.exists(REGISTER_DOCTYPE, register):
        frappe.throw(_("Monitoring register audit not found: {0}").format(register))
    doc = frappe.get_doc(REGISTER_DOCTYPE, register)
    if doc.status == "Cancelled":
        return {"register": register, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.monitoring_register_active or 0):
        frappe.throw(_("Cannot cancel an active Phase 10F monitoring register. Create a superseding governance record if required."))

    frappe.db.set_value(
        REGISTER_DOCTYPE,
        register,
        {
            "status": "Cancelled",
            "monitoring_status": "Cancelled",
            "monitoring_register_active": 0,
            "ready_for_guarded_limited_operations": 0,
            "ready_for_pre_operation_monitoring_check": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 10F no-ack monitoring register audit cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{ITEM_DOCTYPE}` SET status = 'Cancelled' WHERE register = %(register)s", {"register": register})
    frappe.db.commit()
    return {"register": register, "status": "Cancelled", "note": "No-ack monitoring register audit cancelled only. No accounting or policy movement occurred."}


@frappe.whitelist()
def quick_controlled_limited_operations_monitoring_register_summary(limit=20):
    registers = frappe.get_all(
        REGISTER_DOCTYPE,
        fields=[
            "name",
            "register_id",
            "status",
            "monitoring_status",
            "monitoring_register_active",
            "ready_for_guarded_limited_operations",
            "ready_for_pre_operation_monitoring_check",
            "monitoring_controls_frozen",
            "decision",
            "target_policy",
            "target_policy_enabled_before",
            "target_policy_enabled_after",
            "target_policy_live_before",
            "target_policy_live_after",
            "max_batch_line_count",
            "max_batch_amount",
            "max_payment_entry_count",
            "live_posting_allowed",
            "production_batch_enabled_policy_count_after",
            "live_posting_allowed_policy_count_after",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
            "monitoring_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(
        ITEM_DOCTYPE,
        fields=["name", "register", "status", "severity", "category", "check_label", "detail", "source_doctype", "source_name"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "registers": registers,
        "items": items,
        "monitoring_controls": monitoring_controls(),
        "required_acknowledgement": REGISTER_ACK,
        "guardrails": guardrails(),
        "note": "Phase 10F controlled limited operations monitoring register summary. No policy mutation and no accounting movement.",
    }


def execute_register_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("r.status = %(status)s")
        params["status"] = filters.get("status")

    data = frappe.db.sql(
        f"""
        SELECT
            r.name AS register,
            r.register_id,
            r.status,
            r.monitoring_status,
            r.monitoring_register_active,
            r.ready_for_guarded_limited_operations,
            r.ready_for_pre_operation_monitoring_check,
            r.monitoring_controls_frozen,
            r.decision,
            r.target_policy,
            r.target_policy_enabled_after,
            r.target_policy_live_after,
            r.max_batch_line_count,
            r.max_batch_amount,
            r.max_payment_entry_count,
            r.live_posting_allowed,
            r.production_batch_enabled_policy_count_after,
            r.live_posting_allowed_policy_count_after,
            r.actual_payment_entry_created_count,
            r.actual_gl_created_count,
            r.monitoring_score,
            r.checked_on,
            %(currency)s AS currency
        FROM `tab{REGISTER_DOCTYPE}` r
        {build_where(conditions)}
        ORDER BY r.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.register_id for row in data[:20]],
            "datasets": [
                {"name": "Active", "values": [int(row.monitoring_register_active or 0) for row in data[:20]]},
                {"name": "Actual PE Created", "values": [int(row.actual_payment_entry_created_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Registers"), "datatype": "Int"},
        {"value": sum(int(row.monitoring_register_active or 0) for row in data), "indicator": "Green", "label": _("Active"), "datatype": "Int"},
        {"value": sum(int(row.ready_for_guarded_limited_operations or 0) for row in data), "indicator": "Green", "label": _("Ready Operations"), "datatype": "Int"},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PE"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL"), "datatype": "Int"},
    ]
    return register_columns(), data, None, chart, summary


def register_columns():
    return [
        {"fieldname": "register", "label": _("Register"), "fieldtype": "Link", "options": REGISTER_DOCTYPE, "width": 220},
        {"fieldname": "register_id", "label": _("Register ID"), "fieldtype": "Data", "width": 420},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "monitoring_status", "label": _("Monitoring Status"), "fieldtype": "Data", "width": 330},
        {"fieldname": "monitoring_register_active", "label": _("Active"), "fieldtype": "Check", "width": 80},
        {"fieldname": "ready_for_guarded_limited_operations", "label": _("Ready Ops"), "fieldtype": "Check", "width": 100},
        {"fieldname": "ready_for_pre_operation_monitoring_check", "label": _("Ready Pre-Check"), "fieldtype": "Check", "width": 130},
        {"fieldname": "monitoring_controls_frozen", "label": _("Controls Frozen"), "fieldtype": "Check", "width": 130},
        {"fieldname": "decision", "label": _("Phase 10E Decision"), "fieldtype": "Link", "options": DECISION_DOCTYPE, "width": 220},
        {"fieldname": "target_policy", "label": _("Target Policy"), "fieldtype": "Data", "width": 260},
        {"fieldname": "target_policy_enabled_after", "label": _("Enabled"), "fieldtype": "Check", "width": 90},
        {"fieldname": "target_policy_live_after", "label": _("Live"), "fieldtype": "Check", "width": 80},
        {"fieldname": "max_batch_line_count", "label": _("Max Lines"), "fieldtype": "Int", "width": 90},
        {"fieldname": "max_batch_amount", "label": _("Max Amount"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "max_payment_entry_count", "label": _("Max PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "live_posting_allowed", "label": _("Live Allowed"), "fieldtype": "Check", "width": 110},
        {"fieldname": "production_batch_enabled_policy_count_after", "label": _("Enabled Policies"), "fieldtype": "Int", "width": 120},
        {"fieldname": "live_posting_allowed_policy_count_after", "label": _("Live Policies"), "fieldtype": "Int", "width": 110},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "monitoring_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("register"):
        conditions.append("i.register = %(register)s")
        params["register"] = filters.get("register")
    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": ITEM_DOCTYPE, "width": 220},
        {"fieldname": "register", "label": _("Register"), "fieldtype": "Link", "options": REGISTER_DOCTYPE, "width": 220},
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
            i.register,
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
        {"value": len([row for row in data if row.category == "Monitoring Control"]), "indicator": "Blue", "label": _("Controls"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_register_report(filters)
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
