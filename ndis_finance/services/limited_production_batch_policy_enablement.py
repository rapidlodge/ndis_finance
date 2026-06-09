import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


ENABLEMENT_ACK = "I_CONFIRM_PHASE9S_ENABLE_CONTROLLED_LIMITED_PRODUCTION_BATCH_POLICY_NO_POSTING"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"


def make_enablement_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-LIMITED-PROD-BATCH-POLICY-ENABLEMENT-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_readiness_gate():
    rows = frappe.get_all(
        "NDIS Limited Production Batch Enablement Readiness Gate",
        filters={
            "status": "Approved",
            "limited_enablement_readiness_approved": 1,
            "ready_for_controlled_policy_enablement": 1,
            "phase9q_freeze_verified": 1,
            "phase9p_rollback_verified": 1,
            "phase9o_smoke_verified": 1,
            "phase9n_activation_gate_verified": 1,
            "phase9m_adapter_verified": 1,
            "policy_caps_verified": 1,
            "rollback_verified": 1,
            "freeze_verified": 1,
            "no_accounting_movement_verified": 1,
            "current_target_policy_enabled": 0,
            "current_target_policy_live": 0,
            "production_batch_enabled_policy_count": 0,
            "live_posting_allowed_policy_count": 0,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
        },
        fields=[
            "name",
            "readiness_gate_id",
            "evidence_freeze",
            "rollback_run",
            "enablement_smoke",
            "activation_gate",
            "enablement_adapter",
            "enablement_preview",
            "enablement_gate",
            "policy_lock",
            "target_policy_doctype",
            "target_policy",
            "target_policy_name",
            "enablement_field",
            "live_field",
            "target_policy_enabled_before_rollback",
            "target_policy_enabled_after_rollback",
            "target_policy_live_before_rollback",
            "target_policy_live_after_rollback",
            "current_target_policy_enabled",
            "current_target_policy_live",
            "policy_enabled_before_count",
            "policy_enabled_after_count",
            "actual_enabled_policy_count_before",
            "actual_enabled_policy_count_after",
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
            "readiness_score",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_enabled_run(target_policy):
    if not target_policy or not frappe.db.exists("DocType", "NDIS Limited Production Batch Policy Enablement Run"):
        return None
    rows = frappe.get_all(
        "NDIS Limited Production Batch Policy Enablement Run",
        filters={
            "target_policy": target_policy,
            "status": "Enabled - Final Rollback Optional",
            "controlled_policy_enabled": 1,
            "ready_for_limited_batch_use": 1,
        },
        fields=["name", "enablement_id"],
        limit=1,
    )
    return rows[0] if rows else None


def validate_policy_schema():
    issues = []
    if not frappe.db.exists("DocType", POLICY_DOCTYPE):
        return [f"Missing DocType: {POLICY_DOCTYPE}"]
    for fieldname in ["production_batch_enabled", "live_posting_allowed"]:
        if not has_column(POLICY_DOCTYPE, fieldname):
            issues.append(f"Policy DocType is missing required field {fieldname}.")
    return issues


def validate_source(gate, guard, config):
    issues = []
    if config["production_mode"]:
        issues.append("Production mode must remain disabled for Phase 9S policy enablement.")
    if config["live_pe_enabled"]:
        issues.append("Live Payment Entry posting config must remain disabled for Phase 9S policy enablement.")
    if not gate:
        issues.append("No approved Phase 9R readiness gate found.")
        return issues

    issues.extend(validate_policy_schema())
    existing = existing_enabled_run(gate.target_policy)
    if existing:
        issues.append(f"Controlled policy already enabled by Phase 9S run: {existing.enablement_id}")

    required_links = {
        "evidence_freeze": gate.evidence_freeze,
        "rollback_run": gate.rollback_run,
        "enablement_smoke": gate.enablement_smoke,
        "activation_gate": gate.activation_gate,
        "enablement_adapter": gate.enablement_adapter,
    }
    for label, value in required_links.items():
        if not value:
            issues.append(f"Missing evidence link: {label}")

    if not gate.target_policy:
        issues.append("Phase 9R readiness gate has no target policy.")
    elif not frappe.db.exists(POLICY_DOCTYPE, gate.target_policy):
        issues.append(f"Target policy does not exist: {gate.target_policy}")
    else:
        if get_flag(POLICY_DOCTYPE, gate.target_policy, "production_batch_enabled") != 0:
            issues.append("Target policy must be disabled before Phase 9S enablement.")
        if get_flag(POLICY_DOCTYPE, gate.target_policy, "live_posting_allowed") != 0:
            issues.append("Target policy live_posting_allowed must be 0 before Phase 9S enablement.")

    expected_flags = {
        "target_policy_enabled_before_rollback": 1,
        "target_policy_enabled_after_rollback": 0,
        "target_policy_live_before_rollback": 0,
        "target_policy_live_after_rollback": 0,
        "actual_payment_entry_created_count": 0,
        "actual_gl_created_count": 0,
    }
    for fieldname, expected in expected_flags.items():
        if int(gate.get(fieldname) or 0) != expected:
            issues.append(f"Readiness gate {fieldname} must be {expected}.")

    if int(gate.max_batch_lines or 0) != 3:
        issues.append("Max batch lines must remain 3.")
    if flt(gate.max_batch_amount or 0, 2) != 3:
        issues.append("Max batch amount must remain 3.00.")
    if int(gate.max_payment_entry_count or 0) != 1:
        issues.append("Max Payment Entry count must remain 1.")
    if int(gate.payment_entry_count_before or 0) != int(gate.payment_entry_count_after or 0):
        issues.append("Phase 9R Payment Entry count changed.")
    if int(gate.payment_entry_gl_count_before or 0) != int(gate.payment_entry_gl_count_after or 0):
        issues.append("Phase 9R Payment Entry GL count changed.")
    if guard["production_batch_enabled_policy_count"] != 0:
        issues.append("Controlled production batch enabled policy count must be 0 before Phase 9S enablement.")
    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must be 0 before Phase 9S enablement.")
    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today is not zero.")
    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today is not zero.")
    return issues


def count_status(issues, ack_ok, enabled=False):
    blockers = len(issues)
    warnings = 0 if ack_ok else 1
    return {
        "blocker_count": blockers,
        "warning_count": warnings,
        "pass_count": 10 if not blockers else 0,
        "info_count": 2,
        "line_count": 1 if enabled else 0,
        "enablement_score": max(0, 100 - blockers * 25 - warnings * 5),
    }


def enable_target_policy(target_policy):
    if not target_policy:
        frappe.throw(_("Target policy is required for Phase 9S enablement."))
    before_enabled = get_flag(POLICY_DOCTYPE, target_policy, "production_batch_enabled")
    before_live = get_flag(POLICY_DOCTYPE, target_policy, "live_posting_allowed")
    if before_enabled != 0:
        frappe.throw(_("Target policy is already enabled before Phase 9S: {0}").format(target_policy))
    if before_live != 0:
        frappe.throw(_("Phase 9S safety violation: target policy live flag is enabled before enablement."))

    updates = {
        "production_batch_enabled": 1,
        "live_posting_allowed": 0,
    }
    for fieldname in ["production_batch_posting_allowed", "real_posting_allowed", "policy_live_enabled"]:
        if has_column(POLICY_DOCTYPE, fieldname):
            updates[fieldname] = 0
    frappe.db.set_value(POLICY_DOCTYPE, target_policy, updates, update_modified=True)

    after_enabled = get_flag(POLICY_DOCTYPE, target_policy, "production_batch_enabled")
    after_live = get_flag(POLICY_DOCTYPE, target_policy, "live_posting_allowed")
    if after_enabled != 1:
        frappe.throw(_("Phase 9S failed to enable target policy."))
    if after_live != 0:
        frappe.throw(_("Phase 9S safety violation: live_posting_allowed became enabled."))
    return {
        "target_policy_enabled_before": before_enabled,
        "target_policy_enabled_after": after_enabled,
        "target_policy_live_before": before_live,
        "target_policy_live_after": after_live,
    }


def create_enablement_line(doc):
    line = frappe.new_doc("NDIS Limited Production Batch Policy Enablement Line")
    line.enablement_run = doc.name
    line.line_no = 1
    line.line_label = "Controlled Limited Production Batch Policy Enabled"
    line.line_status = "Enabled"
    line.policy_doctype = doc.target_policy_doctype
    line.policy_name = doc.target_policy
    line.policy_action = "Enabled production_batch_enabled only; live posting remains blocked"
    line.enabled_before = int(doc.target_policy_enabled_before or 0)
    line.enabled_after = int(doc.target_policy_enabled_after or 0)
    line.live_before = int(doc.target_policy_live_before or 0)
    line.live_after = int(doc.target_policy_live_after or 0)
    line.actual_enabled = int(doc.controlled_policy_enabled or 0)
    line.production_batch_posting_allowed = 0
    line.real_posting_allowed = 0
    line.policy_live_enabled = 0
    line.detail = "Phase 9S enabled exactly one controlled limited production batch policy. No Payment Entry or GL was created."
    line.checked_on = doc.checked_on
    line.insert(ignore_permissions=True)


@frappe.whitelist()
def run_limited_production_batch_policy_enablement(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_limited_production_batch_policy_enablement")
    gate = latest_readiness_gate()
    config = config_state()
    guard_before = guardrails()
    ack_ok = acknowledgement == ENABLEMENT_ACK
    issues = validate_source(gate, guard_before, config)
    allowed = int(ack_ok and not issues and bool(gate))
    counts = count_status(issues, ack_ok, enabled=bool(allowed))

    result = build_base_result(gate, guard_before, config, ack_ok, issues, allowed, counts, dry_run)
    if int(dry_run or 0):
        result.update(
            {
                "status": "Needs Review",
                "enablement_status": "Needs Review",
                "controlled_policy_enabled": 0,
                "final_rollback_optional": 0,
                "ready_for_limited_batch_use": 0,
                "line_count": 0,
            }
        )
        return result

    doc = frappe.new_doc("NDIS Limited Production Batch Policy Enablement Run")
    doc.enablement_id = make_enablement_id()
    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = ENABLEMENT_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    if allowed:
        flag_result = enable_target_policy(gate.target_policy)
        guard_after = guardrails()
        updates = {
            **flag_result,
            "controlled_policy_enabled": 1,
            "final_rollback_optional": 1,
            "ready_for_limited_batch_use": 1,
            "policy_enabled_after_count": guard_after["production_batch_enabled_policy_count"],
            "actual_enabled_policy_count": guard_after["production_batch_enabled_policy_count"],
            "payment_entry_count_after": guard_after["payment_entry_count"],
            "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
            "production_batch_enabled_policy_count": guard_after["production_batch_enabled_policy_count"],
            "live_posting_allowed_policy_count": guard_after["live_posting_allowed_policy_count"],
            "line_count": 1,
        }
        for fieldname, value in updates.items():
            if doc.meta.has_field(fieldname):
                setattr(doc, fieldname, value)
        doc.summary_json = safe_json({**result, **updates, "guardrails_after": guard_after})
        doc.save(ignore_permissions=True)
        create_enablement_line(doc)
    else:
        guard_after = guardrails()
        frappe.db.set_value(
            "NDIS Limited Production Batch Policy Enablement Run",
            doc.name,
            {
                "payment_entry_count_after": guard_after["payment_entry_count"],
                "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
                "summary_json": safe_json({**result, "guardrails_after": guard_after}),
            },
            update_modified=False,
        )

    frappe.db.commit()
    final_doc = frappe.get_doc("NDIS Limited Production Batch Policy Enablement Run", doc.name)
    return {
        **result,
        "created": True,
        "enablement_run": final_doc.name,
        "enablement_id": final_doc.enablement_id,
        "status": final_doc.status,
        "enablement_status": final_doc.enablement_status,
        "controlled_policy_enabled": int(final_doc.controlled_policy_enabled or 0),
        "final_rollback_optional": int(final_doc.final_rollback_optional or 0),
        "ready_for_limited_batch_use": int(final_doc.ready_for_limited_batch_use or 0),
        "target_policy_enabled_before": int(final_doc.target_policy_enabled_before or 0),
        "target_policy_enabled_after": int(final_doc.target_policy_enabled_after or 0),
        "target_policy_live_before": int(final_doc.target_policy_live_before or 0),
        "target_policy_live_after": int(final_doc.target_policy_live_after or 0),
        "policy_enabled_before_count": int(final_doc.policy_enabled_before_count or 0),
        "policy_enabled_after_count": int(final_doc.policy_enabled_after_count or 0),
        "actual_enabled_policy_count": int(final_doc.actual_enabled_policy_count or 0),
        "guardrails_after": guardrails(),
    }


def build_base_result(gate, guard_before, config, ack_ok, issues, allowed, counts, dry_run):
    current_enabled = get_flag(POLICY_DOCTYPE, gate.target_policy, "production_batch_enabled") if gate else 0
    current_live = get_flag(POLICY_DOCTYPE, gate.target_policy, "live_posting_allowed") if gate else 0
    return {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Enabled - Final Rollback Optional" if allowed else "Needs Review",
        "enablement_status": "Controlled Limited Production Policy Enabled" if allowed else "Needs Review",
        "controlled_policy_enabled": allowed,
        "final_rollback_optional": allowed,
        "ready_for_limited_batch_use": allowed,
        "phase9r_readiness_gate_verified": 1 if gate else 0,
        "phase9q_freeze_verified": 1 if gate else 0,
        "phase9p_rollback_verified": 1 if gate else 0,
        "phase9o_smoke_verified": 1 if gate else 0,
        "phase9n_activation_gate_verified": 1 if gate else 0,
        "phase9m_adapter_verified": 1 if gate else 0,
        "policy_caps_verified": 1 if gate and int(gate.max_batch_lines or 0) == 3 and flt(gate.max_batch_amount or 0, 2) == 3 and int(gate.max_payment_entry_count or 0) == 1 else 0,
        "live_posting_blocked_verified": 1 if current_live == 0 and guard_before["live_posting_allowed_policy_count"] == 0 else 0,
        "no_accounting_movement_verified": 1 if gate and int(gate.payment_entry_count_before or 0) == int(gate.payment_entry_count_after or 0) and int(gate.payment_entry_gl_count_before or 0) == int(gate.payment_entry_gl_count_after or 0) else 0,
        "production_batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "policy_live_enabled": 0,
        "readiness_gate": gate.name if gate else None,
        "evidence_freeze": gate.evidence_freeze if gate else None,
        "rollback_run": gate.rollback_run if gate else None,
        "enablement_smoke": gate.enablement_smoke if gate else None,
        "activation_gate": gate.activation_gate if gate else None,
        "enablement_adapter": gate.enablement_adapter if gate else None,
        "enablement_preview": gate.enablement_preview if gate else None,
        "enablement_gate": gate.enablement_gate if gate else None,
        "policy_lock": gate.policy_lock if gate else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": gate.target_policy if gate else None,
        "target_policy_name": gate.target_policy_name if gate else None,
        "enablement_field": "production_batch_enabled",
        "live_field": "live_posting_allowed",
        "target_policy_enabled_before": current_enabled,
        "target_policy_enabled_after": current_enabled,
        "target_policy_live_before": current_live,
        "target_policy_live_after": current_live,
        "policy_enabled_before_count": guard_before["production_batch_enabled_policy_count"],
        "policy_enabled_after_count": guard_before["production_batch_enabled_policy_count"],
        "actual_enabled_policy_count": 0,
        "max_batch_lines": int(gate.max_batch_lines or 0) if gate else 0,
        "max_batch_amount": flt(gate.max_batch_amount or 0) if gate else 0,
        "max_payment_entry_count": int(gate.max_payment_entry_count or 0) if gate else 0,
        "actual_payment_entry_created_count": 0,
        "actual_gl_created_count": 0,
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guard_before["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guard_before["payment_entry_gl_count"],
        "submitted_journal_entry_count_today": guard_before["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_before["purchase_invoice_count_today"],
        "production_batch_enabled_policy_count": guard_before["production_batch_enabled_policy_count"],
        "live_posting_allowed_policy_count": guard_before["live_posting_allowed_policy_count"],
        **counts,
        "issues": issues,
        "guardrails_before": guard_before,
        "guardrails_after": guardrails(),
        "config": config,
        "required_acknowledgement": ENABLEMENT_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 9S enables one controlled limited production batch policy only. Live posting remains blocked. No PE or GL is created.",
    }


@frappe.whitelist()
def cancel_limited_production_batch_policy_enablement(enablement_run, reason=None):
    assert_action("cancel_limited_production_batch_policy_enablement")
    if not frappe.db.exists("NDIS Limited Production Batch Policy Enablement Run", enablement_run):
        frappe.throw(_("Enablement run not found: {0}").format(enablement_run))
    doc = frappe.get_doc("NDIS Limited Production Batch Policy Enablement Run", enablement_run)
    if doc.status == "Cancelled":
        return {"enablement_run": enablement_run, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.controlled_policy_enabled or 0):
        frappe.throw(_("Cannot cancel an enabled Phase 9S run. Use the optional final rollback phase if rollback is required."))
    frappe.db.set_value(
        "NDIS Limited Production Batch Policy Enablement Run",
        enablement_run,
        {
            "status": "Cancelled",
            "enablement_status": "Cancelled",
            "controlled_policy_enabled": 0,
            "final_rollback_optional": 0,
            "ready_for_limited_batch_use": 0,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 9S no-ack enablement audit cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(
        """
        UPDATE `tabNDIS Limited Production Batch Policy Enablement Line`
        SET line_status = 'Cancelled'
        WHERE enablement_run = %(enablement_run)s
        """,
        {"enablement_run": enablement_run},
    )
    frappe.db.commit()
    return {
        "enablement_run": enablement_run,
        "status": "Cancelled",
        "note": "No-ack enablement audit cancelled only. No policy or accounting movement occurred.",
    }


@frappe.whitelist()
def quick_limited_production_batch_policy_enablement_summary(limit=20):
    runs = frappe.get_all(
        "NDIS Limited Production Batch Policy Enablement Run",
        fields=[
            "name",
            "enablement_id",
            "status",
            "enablement_status",
            "controlled_policy_enabled",
            "final_rollback_optional",
            "ready_for_limited_batch_use",
            "readiness_gate",
            "evidence_freeze",
            "target_policy",
            "target_policy_enabled_before",
            "target_policy_enabled_after",
            "target_policy_live_before",
            "target_policy_live_after",
            "policy_enabled_before_count",
            "policy_enabled_after_count",
            "actual_enabled_policy_count",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
            "production_batch_enabled_policy_count",
            "live_posting_allowed_policy_count",
            "enablement_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    lines = frappe.get_all(
        "NDIS Limited Production Batch Policy Enablement Line",
        fields=[
            "name",
            "enablement_run",
            "line_no",
            "line_status",
            "policy_name",
            "policy_action",
            "enabled_before",
            "enabled_after",
            "live_before",
            "live_after",
            "actual_enabled",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "runs": runs,
        "lines": lines,
        "required_acknowledgement": ENABLEMENT_ACK,
        "guardrails": guardrails(),
        "note": "Phase 9S controlled limited production batch policy enablement summary. Live posting remains blocked.",
    }


def execute_enablement_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("e.status = %(status)s")
        params["status"] = filters.get("status")
    data = frappe.db.sql(
        f"""
        SELECT
            e.name AS enablement_run,
            e.enablement_id,
            e.status,
            e.enablement_status,
            e.controlled_policy_enabled,
            e.final_rollback_optional,
            e.ready_for_limited_batch_use,
            e.readiness_gate,
            e.evidence_freeze,
            e.target_policy,
            e.target_policy_enabled_before,
            e.target_policy_enabled_after,
            e.target_policy_live_before,
            e.target_policy_live_after,
            e.policy_enabled_before_count,
            e.policy_enabled_after_count,
            e.actual_enabled_policy_count,
            e.max_batch_lines,
            e.max_batch_amount,
            e.max_payment_entry_count,
            e.actual_payment_entry_created_count,
            e.actual_gl_created_count,
            e.production_batch_enabled_policy_count,
            e.live_posting_allowed_policy_count,
            e.enablement_score,
            e.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Limited Production Batch Policy Enablement Run` e
        {build_where(conditions)}
        ORDER BY e.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.enablement_id for row in data[:20]],
            "datasets": [
                {"name": "Controlled Policy Enabled", "values": [int(row.controlled_policy_enabled or 0) for row in data[:20]]},
                {"name": "Live Policies", "values": [int(row.live_posting_allowed_policy_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Enablement Runs"), "datatype": "Int"},
        {"value": sum(int(row.controlled_policy_enabled or 0) for row in data), "indicator": "Green", "label": _("Policies Enabled"), "datatype": "Int"},
        {"value": sum(int(row.live_posting_allowed_policy_count or 0) for row in data), "indicator": "Red", "label": _("Live Policies"), "datatype": "Int"},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PE"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL"), "datatype": "Int"},
    ]
    return enablement_columns(), data, None, chart, summary


def enablement_columns():
    return [
        {"fieldname": "enablement_run", "label": _("Enablement Run"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Policy Enablement Run", "width": 220},
        {"fieldname": "enablement_id", "label": _("Enablement ID"), "fieldtype": "Data", "width": 450},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 190},
        {"fieldname": "enablement_status", "label": _("Enablement Status"), "fieldtype": "Data", "width": 320},
        {"fieldname": "controlled_policy_enabled", "label": _("Enabled"), "fieldtype": "Check", "width": 90},
        {"fieldname": "final_rollback_optional", "label": _("Rollback Optional"), "fieldtype": "Check", "width": 130},
        {"fieldname": "ready_for_limited_batch_use", "label": _("Ready Use"), "fieldtype": "Check", "width": 100},
        {"fieldname": "readiness_gate", "label": _("Readiness Gate"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Readiness Gate", "width": 220},
        {"fieldname": "target_policy", "label": _("Target Policy"), "fieldtype": "Data", "width": 260},
        {"fieldname": "target_policy_enabled_before", "label": _("Policy Before"), "fieldtype": "Check", "width": 110},
        {"fieldname": "target_policy_enabled_after", "label": _("Policy After"), "fieldtype": "Check", "width": 110},
        {"fieldname": "target_policy_live_after", "label": _("Live After"), "fieldtype": "Check", "width": 90},
        {"fieldname": "policy_enabled_before_count", "label": _("Enabled Before"), "fieldtype": "Int", "width": 120},
        {"fieldname": "policy_enabled_after_count", "label": _("Enabled After"), "fieldtype": "Int", "width": 120},
        {"fieldname": "max_batch_lines", "label": _("Max Lines"), "fieldtype": "Int", "width": 90},
        {"fieldname": "max_batch_amount", "label": _("Max Amount"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "max_payment_entry_count", "label": _("Max PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "live_posting_allowed_policy_count", "label": _("Live Policies"), "fieldtype": "Int", "width": 110},
        {"fieldname": "enablement_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_line_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("enablement_run"):
        conditions.append("l.enablement_run = %(enablement_run)s")
        params["enablement_run"] = filters.get("enablement_run")
    if filters.get("line_status"):
        conditions.append("l.line_status = %(line_status)s")
        params["line_status"] = filters.get("line_status")
    data = frappe.db.sql(
        f"""
        SELECT
            l.name AS line,
            l.enablement_run,
            l.line_no,
            l.line_status,
            l.policy_name,
            l.policy_action,
            l.enabled_before,
            l.enabled_after,
            l.live_before,
            l.live_after,
            l.actual_enabled,
            l.detail,
            l.checked_on
        FROM `tabNDIS Limited Production Batch Policy Enablement Line` l
        {build_where(conditions)}
        ORDER BY l.enablement_run DESC, l.line_no ASC
        """,
        params,
        as_dict=True,
    )
    columns = [
        {"fieldname": "line", "label": _("Line"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Policy Enablement Line", "width": 220},
        {"fieldname": "enablement_run", "label": _("Enablement Run"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Policy Enablement Run", "width": 220},
        {"fieldname": "line_no", "label": _("Line No"), "fieldtype": "Int", "width": 80},
        {"fieldname": "line_status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "policy_name", "label": _("Policy"), "fieldtype": "Data", "width": 260},
        {"fieldname": "policy_action", "label": _("Action"), "fieldtype": "Data", "width": 360},
        {"fieldname": "enabled_before", "label": _("Enabled Before"), "fieldtype": "Check", "width": 110},
        {"fieldname": "enabled_after", "label": _("Enabled After"), "fieldtype": "Check", "width": 110},
        {"fieldname": "live_before", "label": _("Live Before"), "fieldtype": "Check", "width": 100},
        {"fieldname": "live_after", "label": _("Live After"), "fieldtype": "Check", "width": 100},
        {"fieldname": "actual_enabled", "label": _("Actual Enabled"), "fieldtype": "Check", "width": 110},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]
    chart = {
        "data": {
            "labels": [row.policy_name for row in data[:20]],
            "datasets": [
                {"name": "Enabled After", "values": [int(row.enabled_after or 0) for row in data[:20]]},
                {"name": "Live After", "values": [int(row.live_after or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Lines"), "datatype": "Int"},
        {"value": sum(int(row.actual_enabled or 0) for row in data), "indicator": "Green", "label": _("Enabled"), "datatype": "Int"},
        {"value": sum(int(row.live_after or 0) for row in data), "indicator": "Red", "label": _("Live After"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_enablement_report(filters)
    guard = guardrails()
    summary.extend(
        [
            {"value": guard["payment_entry_count"], "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"},
            {"value": guard["payment_entry_gl_count"], "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"},
            {"value": guard["production_batch_enabled_policy_count"], "indicator": "Green", "label": _("Enabled Policies"), "datatype": "Int"},
            {"value": guard["live_posting_allowed_policy_count"], "indicator": "Red", "label": _("Live Policies"), "datatype": "Int"},
            {"value": guard["submitted_journal_entry_count_today"], "indicator": "Red", "label": _("Submitted JE Today"), "datatype": "Int"},
            {"value": guard["purchase_invoice_count_today"], "indicator": "Red", "label": _("Purchase Invoice Today"), "datatype": "Int"},
        ]
    )
    return columns, data, message, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
