import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


FREEZE_ACK = "I_CONFIRM_PHASE9T_FREEZE_CONTROLLED_LIMITED_PRODUCTION_BATCH_POLICY_ENABLEMENT"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"


def make_freeze_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-LIMITED-PROD-BATCH-POLICY-ENABLEMENT-FREEZE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_enablement_run():
    rows = frappe.get_all(
        "NDIS Limited Production Batch Policy Enablement Run",
        filters={
            "status": "Enabled - Final Rollback Optional",
            "controlled_policy_enabled": 1,
            "final_rollback_optional": 1,
            "ready_for_limited_batch_use": 1,
            "phase9r_readiness_gate_verified": 1,
            "phase9q_freeze_verified": 1,
            "phase9p_rollback_verified": 1,
            "phase9o_smoke_verified": 1,
            "phase9n_activation_gate_verified": 1,
            "phase9m_adapter_verified": 1,
            "policy_caps_verified": 1,
            "live_posting_blocked_verified": 1,
            "no_accounting_movement_verified": 1,
            "target_policy_enabled_before": 0,
            "target_policy_enabled_after": 1,
            "target_policy_live_before": 0,
            "target_policy_live_after": 0,
            "policy_enabled_before_count": 0,
            "policy_enabled_after_count": 1,
            "actual_enabled_policy_count": 1,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
            "production_batch_enabled_policy_count": 1,
            "live_posting_allowed_policy_count": 0,
        },
        fields=[
            "name",
            "enablement_id",
            "controlled_policy_enabled",
            "final_rollback_optional",
            "ready_for_limited_batch_use",
            "phase9r_readiness_gate_verified",
            "phase9q_freeze_verified",
            "phase9p_rollback_verified",
            "phase9o_smoke_verified",
            "phase9n_activation_gate_verified",
            "phase9m_adapter_verified",
            "policy_caps_verified",
            "live_posting_blocked_verified",
            "no_accounting_movement_verified",
            "readiness_gate",
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
            "target_policy_enabled_before",
            "target_policy_enabled_after",
            "target_policy_live_before",
            "target_policy_live_after",
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
            "enablement_score",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_frozen_record(enablement_run):
    if not enablement_run:
        return None
    rows = frappe.get_all(
        "NDIS Limited Production Batch Policy Enablement Freeze",
        filters={
            "enablement_run": enablement_run,
            "status": "Frozen",
            "policy_enablement_freeze_allowed": 1,
            "ready_for_limited_batch_monitoring": 1,
        },
        fields=["name", "freeze_id"],
        limit=1,
    )
    return rows[0] if rows else None


def validate_source(enablement, guard, config):
    issues = []
    if config["production_mode"]:
        issues.append("Production mode must remain disabled for Phase 9T evidence freeze.")
    if config["live_pe_enabled"]:
        issues.append("Live Payment Entry posting config must remain disabled for Phase 9T evidence freeze.")
    if not enablement:
        issues.append("No completed Phase 9S controlled policy enablement run found.")
        return issues

    existing = existing_frozen_record(enablement.name)
    if existing:
        issues.append(f"Phase 9T freeze already exists for this enablement run: {existing.freeze_id}")

    required_links = {
        "readiness_gate": enablement.readiness_gate,
        "evidence_freeze": enablement.evidence_freeze,
        "rollback_run": enablement.rollback_run,
        "enablement_smoke": enablement.enablement_smoke,
        "activation_gate": enablement.activation_gate,
        "enablement_adapter": enablement.enablement_adapter,
    }
    for label, value in required_links.items():
        if not value:
            issues.append(f"Missing evidence link: {label}")

    if enablement.readiness_gate and not frappe.db.exists("NDIS Limited Production Batch Enablement Readiness Gate", enablement.readiness_gate):
        issues.append("Linked Phase 9R readiness gate does not exist.")
    if enablement.evidence_freeze and not frappe.db.exists("NDIS Limited Production Batch Enablement Evidence Freeze", enablement.evidence_freeze):
        issues.append("Linked Phase 9Q evidence freeze does not exist.")
    if not enablement.target_policy:
        issues.append("Phase 9S enablement has no target policy.")
    elif not frappe.db.exists(POLICY_DOCTYPE, enablement.target_policy):
        issues.append(f"Target policy does not exist: {enablement.target_policy}")

    expected_one = [
        "controlled_policy_enabled",
        "final_rollback_optional",
        "ready_for_limited_batch_use",
        "phase9r_readiness_gate_verified",
        "phase9q_freeze_verified",
        "phase9p_rollback_verified",
        "phase9o_smoke_verified",
        "phase9n_activation_gate_verified",
        "phase9m_adapter_verified",
        "policy_caps_verified",
        "live_posting_blocked_verified",
        "no_accounting_movement_verified",
        "target_policy_enabled_after",
        "actual_enabled_policy_count",
        "production_batch_enabled_policy_count",
    ]
    for fieldname in expected_one:
        if int(enablement.get(fieldname) or 0) != 1:
            issues.append(f"Phase 9S {fieldname} must be 1.")

    expected_zero = [
        "target_policy_enabled_before",
        "target_policy_live_before",
        "target_policy_live_after",
        "policy_enabled_before_count",
        "actual_payment_entry_created_count",
        "actual_gl_created_count",
        "live_posting_allowed_policy_count",
    ]
    for fieldname in expected_zero:
        if int(enablement.get(fieldname) or 0) != 0:
            issues.append(f"Phase 9S {fieldname} must be 0.")

    if int(enablement.policy_enabled_after_count or 0) != 1:
        issues.append("Phase 9S policy_enabled_after_count must be 1.")
    if int(enablement.payment_entry_count_before or 0) != int(enablement.payment_entry_count_after or 0):
        issues.append("Phase 9S Payment Entry count changed.")
    if int(enablement.payment_entry_gl_count_before or 0) != int(enablement.payment_entry_gl_count_after or 0):
        issues.append("Phase 9S Payment Entry GL count changed.")
    if int(enablement.max_batch_lines or 0) != 3:
        issues.append("Max batch lines must remain 3.")
    if flt(enablement.max_batch_amount or 0, 2) != 3:
        issues.append("Max batch amount must remain 3.00.")
    if int(enablement.max_payment_entry_count or 0) != 1:
        issues.append("Max Payment Entry count must remain 1.")

    if enablement.target_policy:
        current_enabled = get_flag(POLICY_DOCTYPE, enablement.target_policy, "production_batch_enabled")
        current_live = get_flag(POLICY_DOCTYPE, enablement.target_policy, "live_posting_allowed")
        if current_enabled != 1:
            issues.append("Current target policy production_batch_enabled must be 1 before Phase 9T freeze.")
        if current_live != 0:
            issues.append("Current target policy live_posting_allowed must be 0 before Phase 9T freeze.")

    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Controlled production batch enabled policy count must be exactly 1 before Phase 9T freeze.")
    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must be 0 before Phase 9T freeze.")
    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today is not zero.")
    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today is not zero.")
    return issues


def count_status(issues, ack_ok, frozen=False):
    blockers = len(issues)
    warnings = 0 if ack_ok else 1
    return {
        "blocker_count": blockers,
        "warning_count": warnings,
        "pass_count": 10 if not blockers else 0,
        "info_count": 2,
        "line_count": 1 if frozen else 0,
        "freeze_score": max(0, 100 - blockers * 25 - warnings * 5),
    }


def create_freeze_line(doc):
    line = frappe.new_doc("NDIS Limited Production Batch Policy Enablement Freeze Line")
    line.evidence_freeze = doc.name
    line.line_no = 1
    line.line_label = "Controlled Limited Production Batch Policy Enablement Evidence Frozen"
    line.line_status = "Frozen"
    line.policy_doctype = doc.target_policy_doctype
    line.policy_name = doc.target_policy
    line.policy_action = "Frozen evidence: production_batch_enabled is 1 and live posting remains blocked"
    line.enabled_before = int(doc.target_policy_enabled_before or 0)
    line.enabled_after = int(doc.target_policy_enabled_after or 0)
    line.live_before = int(doc.target_policy_live_before or 0)
    line.live_after = int(doc.target_policy_live_after or 0)
    line.current_enabled = int(doc.current_target_policy_enabled or 0)
    line.current_live = int(doc.current_target_policy_live or 0)
    line.freeze_completed = int(doc.policy_enablement_freeze_allowed or 0)
    line.production_batch_posting_allowed = 0
    line.real_posting_allowed = 0
    line.policy_live_enabled = 0
    line.detail = "Phase 9T read-only freeze completed. Policy remains enabled for controlled limited batch use; live posting remains blocked."
    line.checked_on = doc.checked_on
    line.insert(ignore_permissions=True)


@frappe.whitelist()
def run_limited_production_batch_policy_enablement_freeze(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_limited_production_batch_policy_enablement_freeze")

    enablement = latest_enablement_run()
    config = config_state()
    guard_before = guardrails()
    ack_ok = acknowledgement == FREEZE_ACK
    issues = validate_source(enablement, guard_before, config)
    allowed = int(ack_ok and not issues and bool(enablement))
    counts = count_status(issues, ack_ok, frozen=bool(allowed))
    guard_now = guardrails()

    current_enabled = get_flag(POLICY_DOCTYPE, enablement.target_policy, "production_batch_enabled") if enablement else 0
    current_live = get_flag(POLICY_DOCTYPE, enablement.target_policy, "live_posting_allowed") if enablement else 0

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Frozen" if allowed else "Needs Review",
        "freeze_status": "Controlled Limited Production Policy Enablement Frozen" if allowed else "Needs Review",
        "policy_enablement_freeze_allowed": allowed,
        "ready_for_limited_batch_monitoring": allowed,
        "phase9s_enablement_verified": 1 if enablement else 0,
        "phase9r_readiness_gate_verified": int(enablement.phase9r_readiness_gate_verified or 0) if enablement else 0,
        "phase9q_freeze_verified": int(enablement.phase9q_freeze_verified or 0) if enablement else 0,
        "phase9p_rollback_verified": int(enablement.phase9p_rollback_verified or 0) if enablement else 0,
        "phase9o_smoke_verified": int(enablement.phase9o_smoke_verified or 0) if enablement else 0,
        "phase9n_activation_gate_verified": int(enablement.phase9n_activation_gate_verified or 0) if enablement else 0,
        "phase9m_adapter_verified": int(enablement.phase9m_adapter_verified or 0) if enablement else 0,
        "policy_caps_verified": 1 if enablement and int(enablement.max_batch_lines or 0) == 3 and flt(enablement.max_batch_amount or 0, 2) == 3 and int(enablement.max_payment_entry_count or 0) == 1 else 0,
        "controlled_policy_enabled_verified": 1 if enablement and int(enablement.controlled_policy_enabled or 0) == 1 and current_enabled == 1 else 0,
        "live_posting_blocked_verified": 1 if current_live == 0 and guard_before["live_posting_allowed_policy_count"] == 0 else 0,
        "no_accounting_movement_verified": 1 if enablement and int(enablement.payment_entry_count_before or 0) == int(enablement.payment_entry_count_after or 0) and int(enablement.payment_entry_gl_count_before or 0) == int(enablement.payment_entry_gl_count_after or 0) else 0,
        "production_batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "policy_live_enabled": 0,
        "enablement_run": enablement.name if enablement else None,
        "readiness_gate": enablement.readiness_gate if enablement else None,
        "evidence_freeze": enablement.evidence_freeze if enablement else None,
        "rollback_run": enablement.rollback_run if enablement else None,
        "enablement_smoke": enablement.enablement_smoke if enablement else None,
        "activation_gate": enablement.activation_gate if enablement else None,
        "enablement_adapter": enablement.enablement_adapter if enablement else None,
        "enablement_preview": enablement.enablement_preview if enablement else None,
        "enablement_gate": enablement.enablement_gate if enablement else None,
        "policy_lock": enablement.policy_lock if enablement else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": enablement.target_policy if enablement else None,
        "target_policy_name": enablement.target_policy_name if enablement else None,
        "enablement_field": "production_batch_enabled",
        "live_field": "live_posting_allowed",
        "target_policy_enabled_before": int(enablement.target_policy_enabled_before or 0) if enablement else 0,
        "target_policy_enabled_after": int(enablement.target_policy_enabled_after or 0) if enablement else 0,
        "target_policy_live_before": int(enablement.target_policy_live_before or 0) if enablement else 0,
        "target_policy_live_after": int(enablement.target_policy_live_after or 0) if enablement else 0,
        "current_target_policy_enabled": current_enabled,
        "current_target_policy_live": current_live,
        "policy_enabled_before_count": int(enablement.policy_enabled_before_count or 0) if enablement else 0,
        "policy_enabled_after_count": int(enablement.policy_enabled_after_count or 0) if enablement else 0,
        "actual_enabled_policy_count": int(enablement.actual_enabled_policy_count or 0) if enablement else 0,
        "max_batch_lines": int(enablement.max_batch_lines or 0) if enablement else 0,
        "max_batch_amount": flt(enablement.max_batch_amount or 0) if enablement else 0,
        "max_payment_entry_count": int(enablement.max_payment_entry_count or 0) if enablement else 0,
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
        **counts,
        "issues": issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_now,
        "config": config,
        "required_acknowledgement": FREEZE_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 9T freezes the Phase 9S controlled limited production batch policy enablement evidence. No policy/accounting movement occurs.",
    }

    if int(dry_run or 0):
        result.update(
            {
                "status": "Needs Review",
                "freeze_status": "Needs Review",
                "policy_enablement_freeze_allowed": 0,
                "ready_for_limited_batch_monitoring": 0,
                "line_count": 0,
            }
        )
        return result

    doc = frappe.new_doc("NDIS Limited Production Batch Policy Enablement Freeze")
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
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    if allowed:
        create_freeze_line(doc)

    frappe.db.commit()
    final_doc = frappe.get_doc("NDIS Limited Production Batch Policy Enablement Freeze", doc.name)
    return {
        **result,
        "created": True,
        "policy_enablement_freeze": final_doc.name,
        "freeze_id": final_doc.freeze_id,
        "status": final_doc.status,
        "freeze_status": final_doc.freeze_status,
        "policy_enablement_freeze_allowed": int(final_doc.policy_enablement_freeze_allowed or 0),
        "ready_for_limited_batch_monitoring": int(final_doc.ready_for_limited_batch_monitoring or 0),
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_limited_production_batch_policy_enablement_freeze(policy_enablement_freeze, reason=None):
    assert_action("cancel_limited_production_batch_policy_enablement_freeze")
    if not frappe.db.exists("NDIS Limited Production Batch Policy Enablement Freeze", policy_enablement_freeze):
        frappe.throw(_("Policy enablement freeze not found: {0}").format(policy_enablement_freeze))
    doc = frappe.get_doc("NDIS Limited Production Batch Policy Enablement Freeze", policy_enablement_freeze)
    if doc.status == "Cancelled":
        return {"policy_enablement_freeze": policy_enablement_freeze, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.policy_enablement_freeze_allowed or 0):
        frappe.throw(_("Cannot cancel an approved Phase 9T freeze. Create a superseding freeze if required."))
    frappe.db.set_value(
        "NDIS Limited Production Batch Policy Enablement Freeze",
        policy_enablement_freeze,
        {
            "status": "Cancelled",
            "freeze_status": "Cancelled",
            "policy_enablement_freeze_allowed": 0,
            "ready_for_limited_batch_monitoring": 0,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 9T no-ack freeze audit cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(
        """
        UPDATE `tabNDIS Limited Production Batch Policy Enablement Freeze Line`
        SET line_status = 'Cancelled'
        WHERE evidence_freeze = %(policy_enablement_freeze)s
        """,
        {"policy_enablement_freeze": policy_enablement_freeze},
    )
    frappe.db.commit()
    return {
        "policy_enablement_freeze": policy_enablement_freeze,
        "status": "Cancelled",
        "note": "No-ack freeze audit cancelled only. No policy or accounting movement occurred.",
    }


@frappe.whitelist()
def quick_limited_production_batch_policy_enablement_freeze_summary(limit=20):
    freezes = frappe.get_all(
        "NDIS Limited Production Batch Policy Enablement Freeze",
        fields=[
            "name",
            "freeze_id",
            "status",
            "freeze_status",
            "policy_enablement_freeze_allowed",
            "ready_for_limited_batch_monitoring",
            "enablement_run",
            "readiness_gate",
            "evidence_freeze",
            "target_policy",
            "target_policy_enabled_before",
            "target_policy_enabled_after",
            "target_policy_live_before",
            "target_policy_live_after",
            "current_target_policy_enabled",
            "current_target_policy_live",
            "policy_enabled_before_count",
            "policy_enabled_after_count",
            "actual_enabled_policy_count",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
            "production_batch_enabled_policy_count",
            "live_posting_allowed_policy_count",
            "freeze_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    lines = frappe.get_all(
        "NDIS Limited Production Batch Policy Enablement Freeze Line",
        fields=[
            "name",
            "evidence_freeze",
            "line_no",
            "line_status",
            "policy_name",
            "policy_action",
            "enabled_before",
            "enabled_after",
            "live_before",
            "live_after",
            "current_enabled",
            "current_live",
            "freeze_completed",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "freezes": freezes,
        "lines": lines,
        "required_acknowledgement": FREEZE_ACK,
        "guardrails": guardrails(),
        "note": "Phase 9T policy enablement evidence freeze summary.",
    }


def execute_freeze_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("f.status = %(status)s")
        params["status"] = filters.get("status")
    data = frappe.db.sql(
        f"""
        SELECT
            f.name AS policy_enablement_freeze,
            f.freeze_id,
            f.status,
            f.freeze_status,
            f.policy_enablement_freeze_allowed,
            f.ready_for_limited_batch_monitoring,
            f.enablement_run,
            f.readiness_gate,
            f.evidence_freeze,
            f.target_policy,
            f.current_target_policy_enabled,
            f.current_target_policy_live,
            f.policy_enabled_before_count,
            f.policy_enabled_after_count,
            f.actual_enabled_policy_count,
            f.max_batch_lines,
            f.max_batch_amount,
            f.max_payment_entry_count,
            f.actual_payment_entry_created_count,
            f.actual_gl_created_count,
            f.production_batch_enabled_policy_count,
            f.live_posting_allowed_policy_count,
            f.freeze_score,
            f.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Limited Production Batch Policy Enablement Freeze` f
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
                {"name": "Frozen", "values": [int(row.policy_enablement_freeze_allowed or 0) for row in data[:20]]},
                {"name": "Enabled Policies", "values": [int(row.production_batch_enabled_policy_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Freezes"), "datatype": "Int"},
        {"value": sum(int(row.policy_enablement_freeze_allowed or 0) for row in data), "indicator": "Green", "label": _("Frozen"), "datatype": "Int"},
        {"value": sum(int(row.production_batch_enabled_policy_count or 0) for row in data), "indicator": "Green", "label": _("Enabled Policies"), "datatype": "Int"},
        {"value": sum(int(row.live_posting_allowed_policy_count or 0) for row in data), "indicator": "Red", "label": _("Live Policies"), "datatype": "Int"},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PE"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL"), "datatype": "Int"},
    ]
    return freeze_columns(), data, None, chart, summary


def freeze_columns():
    return [
        {"fieldname": "policy_enablement_freeze", "label": _("Policy Enablement Freeze"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Policy Enablement Freeze", "width": 230},
        {"fieldname": "freeze_id", "label": _("Freeze ID"), "fieldtype": "Data", "width": 470},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "freeze_status", "label": _("Freeze Status"), "fieldtype": "Data", "width": 360},
        {"fieldname": "policy_enablement_freeze_allowed", "label": _("Frozen"), "fieldtype": "Check", "width": 90},
        {"fieldname": "ready_for_limited_batch_monitoring", "label": _("Ready Monitoring"), "fieldtype": "Check", "width": 130},
        {"fieldname": "enablement_run", "label": _("Enablement Run"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Policy Enablement Run", "width": 220},
        {"fieldname": "readiness_gate", "label": _("Readiness Gate"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Readiness Gate", "width": 220},
        {"fieldname": "target_policy", "label": _("Target Policy"), "fieldtype": "Data", "width": 260},
        {"fieldname": "current_target_policy_enabled", "label": _("Current Enabled"), "fieldtype": "Check", "width": 120},
        {"fieldname": "current_target_policy_live", "label": _("Current Live"), "fieldtype": "Check", "width": 110},
        {"fieldname": "policy_enabled_before_count", "label": _("Enabled Before"), "fieldtype": "Int", "width": 120},
        {"fieldname": "policy_enabled_after_count", "label": _("Enabled After"), "fieldtype": "Int", "width": 120},
        {"fieldname": "actual_enabled_policy_count", "label": _("Actual Enabled"), "fieldtype": "Int", "width": 120},
        {"fieldname": "max_batch_lines", "label": _("Max Lines"), "fieldtype": "Int", "width": 90},
        {"fieldname": "max_batch_amount", "label": _("Max Amount"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "max_payment_entry_count", "label": _("Max PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "live_posting_allowed_policy_count", "label": _("Live Policies"), "fieldtype": "Int", "width": 110},
        {"fieldname": "freeze_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_line_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("evidence_freeze"):
        conditions.append("l.evidence_freeze = %(evidence_freeze)s")
        params["evidence_freeze"] = filters.get("evidence_freeze")
    if filters.get("line_status"):
        conditions.append("l.line_status = %(line_status)s")
        params["line_status"] = filters.get("line_status")
    data = frappe.db.sql(
        f"""
        SELECT
            l.name AS line,
            l.evidence_freeze,
            l.line_no,
            l.line_status,
            l.policy_name,
            l.policy_action,
            l.enabled_before,
            l.enabled_after,
            l.live_before,
            l.live_after,
            l.current_enabled,
            l.current_live,
            l.freeze_completed,
            l.detail,
            l.checked_on
        FROM `tabNDIS Limited Production Batch Policy Enablement Freeze Line` l
        {build_where(conditions)}
        ORDER BY l.evidence_freeze DESC, l.line_no ASC
        """,
        params,
        as_dict=True,
    )
    columns = [
        {"fieldname": "line", "label": _("Line"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Policy Enablement Freeze Line", "width": 220},
        {"fieldname": "evidence_freeze", "label": _("Evidence Freeze"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Policy Enablement Freeze", "width": 220},
        {"fieldname": "line_no", "label": _("Line No"), "fieldtype": "Int", "width": 80},
        {"fieldname": "line_status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "policy_name", "label": _("Policy"), "fieldtype": "Data", "width": 260},
        {"fieldname": "policy_action", "label": _("Action"), "fieldtype": "Data", "width": 390},
        {"fieldname": "enabled_before", "label": _("Enabled Before"), "fieldtype": "Check", "width": 110},
        {"fieldname": "enabled_after", "label": _("Enabled After"), "fieldtype": "Check", "width": 110},
        {"fieldname": "live_before", "label": _("Live Before"), "fieldtype": "Check", "width": 100},
        {"fieldname": "live_after", "label": _("Live After"), "fieldtype": "Check", "width": 100},
        {"fieldname": "current_enabled", "label": _("Current Enabled"), "fieldtype": "Check", "width": 120},
        {"fieldname": "current_live", "label": _("Current Live"), "fieldtype": "Check", "width": 110},
        {"fieldname": "freeze_completed", "label": _("Freeze Done"), "fieldtype": "Check", "width": 110},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]
    chart = {
        "data": {
            "labels": [row.policy_name for row in data[:20]],
            "datasets": [
                {"name": "Current Enabled", "values": [int(row.current_enabled or 0) for row in data[:20]]},
                {"name": "Current Live", "values": [int(row.current_live or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Freeze Lines"), "datatype": "Int"},
        {"value": sum(int(row.freeze_completed or 0) for row in data), "indicator": "Green", "label": _("Frozen"), "datatype": "Int"},
        {"value": sum(int(row.current_enabled or 0) for row in data), "indicator": "Green", "label": _("Enabled"), "datatype": "Int"},
        {"value": sum(int(row.current_live or 0) for row in data), "indicator": "Red", "label": _("Live"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_freeze_report(filters)
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
