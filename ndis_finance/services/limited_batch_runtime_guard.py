import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


GUARD_ACK = "I_CONFIRM_PHASE9V_ACTIVATE_LIMITED_BATCH_RUNTIME_GUARD_NO_POSTING"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
MONITOR_GATE_DOCTYPE = "NDIS Limited Production Batch Use Monitor Gate"
PHASE9T_FREEZE_DOCTYPE = "NDIS Limited Production Batch Policy Enablement Freeze"
RUNTIME_GUARD_DOCTYPE = "NDIS Limited Batch Runtime Guard"
RUNTIME_GUARD_ITEM_DOCTYPE = "NDIS Limited Batch Runtime Guard Item"


def make_runtime_guard_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-LIMITED-BATCH-RUNTIME-GUARD-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def config_state():
    return {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def latest_monitor_gate():
    rows = frappe.get_all(
        MONITOR_GATE_DOCTYPE,
        filters={
            "status": "Approved",
            "monitor_gate_approved": 1,
            "ready_for_operational_monitoring": 1,
            "phase9t_freeze_verified": 1,
            "phase9s_enablement_verified": 1,
            "phase9r_readiness_gate_verified": 1,
            "controlled_policy_enabled_verified": 1,
            "live_posting_blocked_verified": 1,
            "no_accounting_movement_verified": 1,
            "current_target_policy_enabled": 1,
            "current_target_policy_live": 0,
            "actual_enabled_policy_count": 1,
            "production_batch_enabled_policy_count": 1,
            "live_posting_allowed_policy_count": 0,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
        },
        fields=[
            "name",
            "monitor_gate_id",
            "policy_enablement_freeze",
            "enablement_run",
            "readiness_gate",
            "phase9q_evidence_freeze",
            "rollback_run",
            "enablement_smoke",
            "activation_gate",
            "enablement_adapter",
            "target_policy_doctype",
            "target_policy",
            "target_policy_name",
            "enablement_field",
            "live_field",
            "current_target_policy_enabled",
            "current_target_policy_live",
            "policy_enabled_before_count",
            "policy_enabled_after_count",
            "actual_enabled_policy_count",
            "max_batch_lines",
            "max_batch_amount",
            "max_payment_entry_count",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "submitted_journal_entry_count_today",
            "purchase_invoice_count_today",
            "production_batch_enabled_policy_count",
            "live_posting_allowed_policy_count",
            "monitor_score",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_active_guard(monitor_gate):
    if not monitor_gate:
        return None
    rows = frappe.get_all(
        RUNTIME_GUARD_DOCTYPE,
        filters={
            "monitor_gate": monitor_gate,
            "status": "Guarded",
            "runtime_guard_active": 1,
            "ready_for_guarded_limited_batch_runtime": 1,
        },
        fields=["name", "runtime_guard_id"],
        limit=1,
    )
    return rows[0] if rows else None


def active_runtime_guard():
    rows = frappe.get_all(
        RUNTIME_GUARD_DOCTYPE,
        filters={
            "status": "Guarded",
            "runtime_guard_active": 1,
            "ready_for_guarded_limited_batch_runtime": 1,
            "controlled_policy_enabled_verified": 1,
            "live_posting_blocked_verified": 1,
            "runtime_validation_ready": 1,
        },
        fields=[
            "name",
            "runtime_guard_id",
            "target_policy",
            "max_batch_lines",
            "max_batch_amount",
            "max_payment_entry_count",
            "current_target_policy_enabled",
            "current_target_policy_live",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def validate_source(gate, guard, config):
    issues = []
    if config["production_mode"]:
        issues.append("Production mode must remain disabled for Phase 9V runtime guard.")
    if config["live_pe_enabled"]:
        issues.append("Live Payment Entry posting config must remain disabled for Phase 9V runtime guard.")
    if not gate:
        issues.append("No approved Phase 9U monitor gate found.")
        return issues

    existing = existing_active_guard(gate.name)
    if existing:
        issues.append(f"Phase 9V runtime guard already active for this monitor gate: {existing.runtime_guard_id}")

    if not gate.policy_enablement_freeze:
        issues.append("Phase 9U monitor gate has no Phase 9T freeze link.")
    elif not frappe.db.exists(PHASE9T_FREEZE_DOCTYPE, gate.policy_enablement_freeze):
        issues.append("Linked Phase 9T freeze does not exist.")

    if not gate.enablement_run:
        issues.append("Phase 9U monitor gate has no Phase 9S enablement run link.")
    if not gate.target_policy:
        issues.append("Phase 9U monitor gate has no target policy.")
    elif not frappe.db.exists(POLICY_DOCTYPE, gate.target_policy):
        issues.append(f"Target policy does not exist: {gate.target_policy}")

    current_enabled = get_flag(POLICY_DOCTYPE, gate.target_policy, "production_batch_enabled") if gate.target_policy else 0
    current_live = get_flag(POLICY_DOCTYPE, gate.target_policy, "live_posting_allowed") if gate.target_policy else 0
    if current_enabled != 1:
        issues.append("Current target policy production_batch_enabled must be 1 before runtime guard activation.")
    if current_live != 0:
        issues.append("Current target policy live_posting_allowed must be 0 before runtime guard activation.")

    expected_one = [
        "current_target_policy_enabled",
        "actual_enabled_policy_count",
    ]
    for fieldname in expected_one:
        if int(gate.get(fieldname) or 0) != 1:
            issues.append(f"Phase 9U {fieldname} must be 1.")

    if int(gate.current_target_policy_live or 0) != 0:
        issues.append("Phase 9U current_target_policy_live must be 0.")
    if int(gate.max_batch_lines or 0) != 3:
        issues.append("Runtime max batch lines must be 3.")
    if flt(gate.max_batch_amount or 0, 2) != 3:
        issues.append("Runtime max batch amount must be 3.00.")
    if int(gate.max_payment_entry_count or 0) != 1:
        issues.append("Runtime max Payment Entry count must be 1.")
    if int(gate.actual_payment_entry_created_count or 0) != 0:
        issues.append("Phase 9U actual Payment Entry created count must be 0.")
    if int(gate.actual_gl_created_count or 0) != 0:
        issues.append("Phase 9U actual GL created count must be 0.")
    if int(gate.payment_entry_count_before or 0) != int(gate.payment_entry_count_after or 0):
        issues.append("Phase 9U Payment Entry count changed.")
    if int(gate.payment_entry_gl_count_before or 0) != int(gate.payment_entry_gl_count_after or 0):
        issues.append("Phase 9U Payment Entry GL count changed.")
    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must be enabled before runtime guard activation.")
    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must be 0 before runtime guard activation.")
    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today is not zero.")
    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today is not zero.")
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


def build_items(gate, issues, ack_ok, guard):
    items = []
    if gate:
        add_item(
            items,
            "Pass",
            "Low",
            "Evidence",
            "phase9u_monitor_gate_exists",
            "Phase 9U monitor gate exists",
            f"Monitor gate found: {gate.monitor_gate_id}.",
            MONITOR_GATE_DOCTYPE,
            gate.name,
        )
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase9u_monitor_gate_exists", "Phase 9U monitor gate exists", "No approved Phase 9U monitor gate found.")

    if issues:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Runtime Source", "runtime_source_valid", "Runtime source valid", issue)
    else:
        add_item(items, "Pass", "Low", "Runtime Source", "runtime_source_valid", "Runtime source valid", "Runtime guard source evidence is valid.")

    if guard["production_batch_enabled_policy_count"] == 1 and guard["live_posting_allowed_policy_count"] == 0:
        add_item(items, "Pass", "Low", "Policy Guardrail", "policy_state", "Policy state correct", "Exactly one controlled policy is enabled and live posting remains blocked.")
    else:
        add_item(items, "Blocker", "Critical", "Policy Guardrail", "policy_state", "Policy state correct", "Policy state is not 1 enabled / 0 live.")

    if gate:
        add_item(items, "Pass", "Low", "Runtime Cap", "max_lines", "Max lines guarded", f"Runtime line cap is {gate.max_batch_lines}.")
        add_item(items, "Pass", "Low", "Runtime Cap", "max_amount", "Max amount guarded", f"Runtime amount cap is {gate.max_batch_amount}.")
        add_item(items, "Pass", "Low", "Runtime Cap", "max_payment_entry_count", "Max Payment Entry count guarded", f"Runtime Payment Entry cap is {gate.max_payment_entry_count}.")
        add_item(items, "Pass", "Low", "Live Guard", "live_posting_blocked", "Live posting blocked", "Runtime guard blocks live posting.")
        add_item(items, "Pass", "Low", "Side Effects", "je_pi_blocked", "JE/PI side effects blocked", "Runtime guard blocks JE/PI side-effect paths for this limited batch runtime.")
        add_item(items, "Pass", "Low", "Accounting Guardrail", "no_accounting_movement", "No accounting movement", "Payment Entry and Payment Entry GL counts stayed unchanged.")

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {GUARD_ACK}")
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
    return max(0, round(100 - int(blockers or 0) * 25 - int(warnings or 0) * 5, 2))


def create_items(doc, items):
    for item in items:
        row = frappe.new_doc(RUNTIME_GUARD_ITEM_DOCTYPE)
        row.runtime_guard = doc.name
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


def assert_limited_batch_runtime_guard(
    batch_line_count,
    batch_amount,
    payment_entry_count,
    live_posting_requested=0,
    allow_journal_entry_side_effect=0,
    allow_purchase_invoice_side_effect=0,
    context=None,
):
    guard = active_runtime_guard()
    if not guard:
        frappe.throw(_("Limited batch runtime guard is not active."))

    batch_line_count = int(batch_line_count or 0)
    batch_amount = flt(batch_amount or 0, 2)
    payment_entry_count = int(payment_entry_count or 0)
    live_posting_requested = int(live_posting_requested or 0)
    allow_journal_entry_side_effect = int(allow_journal_entry_side_effect or 0)
    allow_purchase_invoice_side_effect = int(allow_purchase_invoice_side_effect or 0)

    if batch_line_count <= 0:
        frappe.throw(_("Limited batch runtime guard blocked: batch line count must be greater than zero."))
    if batch_line_count > int(guard.max_batch_lines or 0):
        frappe.throw(_("Limited batch runtime guard blocked: max {0} lines allowed.").format(int(guard.max_batch_lines or 0)))
    if batch_amount <= 0:
        frappe.throw(_("Limited batch runtime guard blocked: batch amount must be greater than zero."))
    if batch_amount > flt(guard.max_batch_amount or 0, 2):
        frappe.throw(_("Limited batch runtime guard blocked: max amount is {0}.").format(flt(guard.max_batch_amount or 0, 2)))
    if payment_entry_count != 1:
        frappe.throw(_("Limited batch runtime guard blocked: exactly one Payment Entry is allowed."))
    if payment_entry_count > int(guard.max_payment_entry_count or 0):
        frappe.throw(_("Limited batch runtime guard blocked: max {0} Payment Entry allowed.").format(int(guard.max_payment_entry_count or 0)))
    if live_posting_requested:
        frappe.throw(_("Limited batch runtime guard blocked: live posting is not allowed."))
    if allow_journal_entry_side_effect:
        frappe.throw(_("Limited batch runtime guard blocked: Journal Entry side effect is not allowed."))
    if allow_purchase_invoice_side_effect:
        frappe.throw(_("Limited batch runtime guard blocked: Purchase Invoice side effect is not allowed."))
    if get_flag(POLICY_DOCTYPE, guard.target_policy, "production_batch_enabled") != 1:
        frappe.throw(_("Limited batch runtime guard blocked: target policy is not enabled."))
    if get_flag(POLICY_DOCTYPE, guard.target_policy, "live_posting_allowed") != 0:
        frappe.throw(_("Limited batch runtime guard blocked: live posting flag is enabled."))

    return {
        "status": "Passed",
        "runtime_guard": guard.name,
        "runtime_guard_id": guard.runtime_guard_id,
        "target_policy": guard.target_policy,
        "batch_line_count": batch_line_count,
        "batch_amount": batch_amount,
        "payment_entry_count": payment_entry_count,
        "live_posting_requested": live_posting_requested,
        "context": context,
        "note": "Runtime guard passed. This method does not create Payment Entry or GL.",
    }


@frappe.whitelist()
def simulate_limited_batch_runtime_guard(
    batch_line_count=3,
    batch_amount=3,
    payment_entry_count=1,
    live_posting_requested=0,
    allow_journal_entry_side_effect=0,
    allow_purchase_invoice_side_effect=0,
):
    assert_action("simulate_limited_batch_runtime_guard")
    return assert_limited_batch_runtime_guard(
        batch_line_count=batch_line_count,
        batch_amount=batch_amount,
        payment_entry_count=payment_entry_count,
        live_posting_requested=live_posting_requested,
        allow_journal_entry_side_effect=allow_journal_entry_side_effect,
        allow_purchase_invoice_side_effect=allow_purchase_invoice_side_effect,
        context="Phase 9V runtime guard simulation",
    )


@frappe.whitelist()
def run_limited_batch_runtime_guard(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_limited_batch_runtime_guard")

    gate = latest_monitor_gate()
    config = config_state()
    guard_before = guardrails()
    ack_ok = acknowledgement == GUARD_ACK
    issues = validate_source(gate, guard_before, config)
    items = build_items(gate, issues, ack_ok, guard_before)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    allowed = int(ack_ok and item_summary["blocker_count"] == 0 and bool(gate))
    guard_now = guardrails()
    current_enabled = get_flag(POLICY_DOCTYPE, gate.target_policy, "production_batch_enabled") if gate else 0
    current_live = get_flag(POLICY_DOCTYPE, gate.target_policy, "live_posting_allowed") if gate else 0

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Guarded" if allowed else "Needs Review",
        "guard_status": "Runtime Guard Active For Limited Batch Posting" if allowed else "Needs Review",
        "runtime_guard_active": allowed,
        "ready_for_guarded_limited_batch_runtime": allowed,
        "phase9u_monitor_gate_verified": 1 if gate else 0,
        "phase9t_freeze_verified": 1 if gate else 0,
        "phase9s_enablement_verified": 1 if gate else 0,
        "phase9r_readiness_gate_verified": 1 if gate else 0,
        "policy_caps_verified": 1 if gate and int(gate.max_batch_lines or 0) == 3 and flt(gate.max_batch_amount or 0, 2) == 3 and int(gate.max_payment_entry_count or 0) == 1 else 0,
        "controlled_policy_enabled_verified": 1 if current_enabled == 1 else 0,
        "live_posting_blocked_verified": 1 if current_live == 0 and guard_before["live_posting_allowed_policy_count"] == 0 else 0,
        "no_accounting_movement_verified": 1 if gate and int(gate.payment_entry_count_before or 0) == int(gate.payment_entry_count_after or 0) and int(gate.payment_entry_gl_count_before or 0) == int(gate.payment_entry_gl_count_after or 0) else 0,
        "runtime_validation_ready": allowed,
        "production_batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "policy_live_enabled": 0,
        "monitor_gate": gate.name if gate else None,
        "policy_enablement_freeze": gate.policy_enablement_freeze if gate else None,
        "enablement_run": gate.enablement_run if gate else None,
        "readiness_gate": gate.readiness_gate if gate else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": gate.target_policy if gate else None,
        "target_policy_name": gate.target_policy_name if gate else None,
        "enablement_field": "production_batch_enabled",
        "live_field": "live_posting_allowed",
        "current_target_policy_enabled": current_enabled,
        "current_target_policy_live": current_live,
        "actual_enabled_policy_count": int(gate.actual_enabled_policy_count or 0) if gate else 0,
        "max_batch_lines": int(gate.max_batch_lines or 0) if gate else 0,
        "max_batch_amount": flt(gate.max_batch_amount or 0) if gate else 0,
        "max_payment_entry_count": int(gate.max_payment_entry_count or 0) if gate else 0,
        "runtime_guard_allows_line_count_check": allowed,
        "runtime_guard_allows_amount_check": allowed,
        "runtime_guard_allows_payment_entry_count_check": allowed,
        "runtime_guard_blocks_live_posting": allowed,
        "runtime_guard_blocks_je_pi_side_effects": allowed,
        "actual_payment_entry_created_count": 0,
        "actual_gl_created_count": 0,
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guard_now["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guard_now["payment_entry_gl_count"],
        "submitted_journal_entry_count_today": guard_before["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_before["purchase_invoice_count_today"],
        "production_batch_enabled_policy_count": guard_before["production_batch_enabled_policy_count"],
        "live_posting_allowed_policy_count": guard_before["live_posting_allowed_policy_count"],
        "guard_score": score,
        **item_summary,
        "items": items,
        "issues": issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_now,
        "config": config,
        "required_acknowledgement": GUARD_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 9V activates runtime guard only. It creates no PE/GL and does not change policy flags.",
    }

    if int(dry_run or 0):
        result.update(
            {
                "status": "Needs Review",
                "guard_status": "Needs Review",
                "runtime_guard_active": 0,
                "ready_for_guarded_limited_batch_runtime": 0,
                "runtime_validation_ready": 0,
            }
        )
        return result

    doc = frappe.new_doc(RUNTIME_GUARD_DOCTYPE)
    doc.runtime_guard_id = make_runtime_guard_id()
    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = GUARD_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    create_items(doc, items)
    frappe.db.commit()

    final_doc = frappe.get_doc(RUNTIME_GUARD_DOCTYPE, doc.name)
    return {
        **result,
        "created": True,
        "runtime_guard": final_doc.name,
        "runtime_guard_id": final_doc.runtime_guard_id,
        "status": final_doc.status,
        "guard_status": final_doc.guard_status,
        "runtime_guard_active": int(final_doc.runtime_guard_active or 0),
        "ready_for_guarded_limited_batch_runtime": int(final_doc.ready_for_guarded_limited_batch_runtime or 0),
        "runtime_validation_ready": int(final_doc.runtime_validation_ready or 0),
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_limited_batch_runtime_guard(runtime_guard, reason=None):
    assert_action("cancel_limited_batch_runtime_guard")
    if not frappe.db.exists(RUNTIME_GUARD_DOCTYPE, runtime_guard):
        frappe.throw(_("Runtime guard not found: {0}").format(runtime_guard))
    doc = frappe.get_doc(RUNTIME_GUARD_DOCTYPE, runtime_guard)
    if doc.status == "Cancelled":
        return {"runtime_guard": runtime_guard, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.runtime_guard_active or 0):
        frappe.throw(_("Cannot cancel an active Phase 9V runtime guard. Create a superseding guard or proceed to rollback/deactivation phase."))
    frappe.db.set_value(
        RUNTIME_GUARD_DOCTYPE,
        runtime_guard,
        {
            "status": "Cancelled",
            "guard_status": "Cancelled",
            "runtime_guard_active": 0,
            "ready_for_guarded_limited_batch_runtime": 0,
            "runtime_validation_ready": 0,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 9V no-ack runtime guard audit cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(
        """
        UPDATE `tabNDIS Limited Batch Runtime Guard Item`
        SET status = 'Cancelled'
        WHERE runtime_guard = %(runtime_guard)s
        """,
        {"runtime_guard": runtime_guard},
    )
    frappe.db.commit()
    return {
        "runtime_guard": runtime_guard,
        "status": "Cancelled",
        "note": "No-ack runtime guard audit cancelled only. No policy or accounting movement occurred.",
    }


@frappe.whitelist()
def quick_limited_batch_runtime_guard_summary(limit=20):
    guards = frappe.get_all(
        RUNTIME_GUARD_DOCTYPE,
        fields=[
            "name",
            "runtime_guard_id",
            "status",
            "guard_status",
            "runtime_guard_active",
            "ready_for_guarded_limited_batch_runtime",
            "runtime_validation_ready",
            "monitor_gate",
            "policy_enablement_freeze",
            "enablement_run",
            "target_policy",
            "current_target_policy_enabled",
            "current_target_policy_live",
            "actual_enabled_policy_count",
            "max_batch_lines",
            "max_batch_amount",
            "max_payment_entry_count",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
            "production_batch_enabled_policy_count",
            "live_posting_allowed_policy_count",
            "guard_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(
        RUNTIME_GUARD_ITEM_DOCTYPE,
        fields=[
            "name",
            "runtime_guard",
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
        "guards": guards,
        "items": items,
        "required_acknowledgement": GUARD_ACK,
        "guardrails": guardrails(),
        "note": "Phase 9V runtime guard summary. No PE/GL or policy movement.",
    }


def execute_guard_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("g.status = %(status)s")
        params["status"] = filters.get("status")
    columns = guard_columns()
    data = frappe.db.sql(
        f"""
        SELECT
            g.name AS runtime_guard,
            g.runtime_guard_id,
            g.status,
            g.guard_status,
            g.runtime_guard_active,
            g.ready_for_guarded_limited_batch_runtime,
            g.runtime_validation_ready,
            g.monitor_gate,
            g.policy_enablement_freeze,
            g.enablement_run,
            g.target_policy,
            g.current_target_policy_enabled,
            g.current_target_policy_live,
            g.actual_enabled_policy_count,
            g.max_batch_lines,
            g.max_batch_amount,
            g.max_payment_entry_count,
            g.actual_payment_entry_created_count,
            g.actual_gl_created_count,
            g.production_batch_enabled_policy_count,
            g.live_posting_allowed_policy_count,
            g.guard_score,
            g.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Limited Batch Runtime Guard` g
        {build_where(conditions)}
        ORDER BY g.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.runtime_guard_id for row in data[:20]],
            "datasets": [
                {"name": "Active Guard", "values": [int(row.runtime_guard_active or 0) for row in data[:20]]},
                {"name": "Live Policies", "values": [int(row.live_posting_allowed_policy_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Runtime Guards"), "datatype": "Int"},
        {"value": sum(int(row.runtime_guard_active or 0) for row in data), "indicator": "Green", "label": _("Active"), "datatype": "Int"},
        {"value": sum(int(row.production_batch_enabled_policy_count or 0) for row in data), "indicator": "Green", "label": _("Enabled Policies"), "datatype": "Int"},
        {"value": sum(int(row.live_posting_allowed_policy_count or 0) for row in data), "indicator": "Red", "label": _("Live Policies"), "datatype": "Int"},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PE"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def guard_columns():
    return [
        {"fieldname": "runtime_guard", "label": _("Runtime Guard"), "fieldtype": "Link", "options": RUNTIME_GUARD_DOCTYPE, "width": 220},
        {"fieldname": "runtime_guard_id", "label": _("Runtime Guard ID"), "fieldtype": "Data", "width": 430},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "guard_status", "label": _("Guard Status"), "fieldtype": "Data", "width": 340},
        {"fieldname": "runtime_guard_active", "label": _("Active"), "fieldtype": "Check", "width": 80},
        {"fieldname": "ready_for_guarded_limited_batch_runtime", "label": _("Ready Runtime"), "fieldtype": "Check", "width": 120},
        {"fieldname": "runtime_validation_ready", "label": _("Validation Ready"), "fieldtype": "Check", "width": 120},
        {"fieldname": "monitor_gate", "label": _("Monitor Gate"), "fieldtype": "Link", "options": MONITOR_GATE_DOCTYPE, "width": 220},
        {"fieldname": "target_policy", "label": _("Target Policy"), "fieldtype": "Data", "width": 260},
        {"fieldname": "current_target_policy_enabled", "label": _("Current Enabled"), "fieldtype": "Check", "width": 120},
        {"fieldname": "current_target_policy_live", "label": _("Current Live"), "fieldtype": "Check", "width": 110},
        {"fieldname": "max_batch_lines", "label": _("Max Lines"), "fieldtype": "Int", "width": 90},
        {"fieldname": "max_batch_amount", "label": _("Max Amount"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "max_payment_entry_count", "label": _("Max PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "production_batch_enabled_policy_count", "label": _("Enabled Policies"), "fieldtype": "Int", "width": 120},
        {"fieldname": "live_posting_allowed_policy_count", "label": _("Live Policies"), "fieldtype": "Int", "width": 110},
        {"fieldname": "guard_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("runtime_guard"):
        conditions.append("i.runtime_guard = %(runtime_guard)s")
        params["runtime_guard"] = filters.get("runtime_guard")
    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": RUNTIME_GUARD_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "runtime_guard", "label": _("Runtime Guard"), "fieldtype": "Link", "options": RUNTIME_GUARD_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 170},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 300},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 520},
        {"fieldname": "source_doctype", "label": _("Source DocType"), "fieldtype": "Data", "width": 220},
        {"fieldname": "source_name", "label": _("Source Name"), "fieldtype": "Data", "width": 240},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            i.name AS item,
            i.runtime_guard,
            i.status,
            i.severity,
            i.category,
            i.check_label,
            i.detail,
            i.source_doctype,
            i.source_name,
            i.checked_on
        FROM `tabNDIS Limited Batch Runtime Guard Item` i
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
    columns, data, message, chart, summary = execute_guard_report(filters)
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
