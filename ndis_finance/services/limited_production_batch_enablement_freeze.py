import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


FREEZE_ACK = "I_CONFIRM_PHASE9Q_FREEZE_LIMITED_PRODUCTION_BATCH_ENABLEMENT_EVIDENCE"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"


def make_freeze_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-LIMITED-PROD-BATCH-ENABLEMENT-FREEZE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_completed_rollback():
    rows = frappe.get_all(
        "NDIS Limited Production Batch Enablement Rollback Run",
        filters={
            "status": "Rolled Back",
            "limited_policy_rollback_completed": 1,
            "ready_for_enablement_freeze": 1,
            "phase9o_smoke_verified": 1,
            "phase9n_activation_gate_verified": 1,
            "phase9m_adapter_verified": 1,
            "phase9l_preview_verified": 1,
            "policy_caps_verified": 1,
            "target_policy_enabled_before_rollback": 1,
            "target_policy_enabled_after_rollback": 0,
            "target_policy_live_before_rollback": 0,
            "target_policy_live_after_rollback": 0,
            "policy_enabled_before_count": 1,
            "policy_enabled_after_count": 0,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
        },
        fields=[
            "name",
            "rollback_id",
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
            "live_posting_allowed_policy_count",
            "rollback_score",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_frozen_record(rollback_run):
    if not rollback_run:
        return None
    rows = frappe.get_all(
        "NDIS Limited Production Batch Enablement Evidence Freeze",
        filters={
            "rollback_run": rollback_run,
            "status": "Frozen",
            "evidence_freeze_allowed": 1,
            "ready_for_next_phase": 1,
        },
        fields=["name", "freeze_id"],
        limit=1,
    )
    return rows[0] if rows else None


def validate_source(rollback, guard):
    issues = []
    if not rollback:
        issues.append("No completed Phase 9P rollback found.")
        return issues

    existing = existing_frozen_record(rollback.name)
    if existing:
        issues.append(f"Phase 9Q freeze already exists for this rollback: {existing.freeze_id}")

    required_links = {
        "enablement_smoke": rollback.enablement_smoke,
        "activation_gate": rollback.activation_gate,
        "enablement_adapter": rollback.enablement_adapter,
        "enablement_preview": rollback.enablement_preview,
    }
    for label, value in required_links.items():
        if not value:
            issues.append(f"Missing evidence link: {label}")

    if rollback.enablement_smoke and not frappe.db.exists("NDIS Limited Production Batch Enablement Smoke Run", rollback.enablement_smoke):
        issues.append("Linked Phase 9O smoke run does not exist.")
    if rollback.activation_gate and not frappe.db.exists("NDIS Limited Production Batch Enablement Activation Gate", rollback.activation_gate):
        issues.append("Linked Phase 9N activation gate does not exist.")
    if rollback.target_policy and not frappe.db.exists(POLICY_DOCTYPE, rollback.target_policy):
        issues.append(f"Target policy does not exist: {rollback.target_policy}")

    expected_flags = {
        "target_policy_enabled_before_rollback": 1,
        "target_policy_enabled_after_rollback": 0,
        "target_policy_live_before_rollback": 0,
        "target_policy_live_after_rollback": 0,
        "policy_enabled_before_count": 1,
        "policy_enabled_after_count": 0,
        "actual_payment_entry_created_count": 0,
        "actual_gl_created_count": 0,
    }
    for fieldname, expected in expected_flags.items():
        if int(rollback.get(fieldname) or 0) != expected:
            issues.append(f"Phase 9P {fieldname} must be {expected}.")

    if rollback.target_policy:
        current_enabled = get_flag(POLICY_DOCTYPE, rollback.target_policy, "production_batch_enabled")
        current_live = get_flag(POLICY_DOCTYPE, rollback.target_policy, "live_posting_allowed")
        if current_enabled != 0:
            issues.append("Current target policy production_batch_enabled must be 0 before freeze.")
        if current_live != 0:
            issues.append("Current target policy live_posting_allowed must be 0 before freeze.")

    if int(rollback.payment_entry_count_before or 0) != int(rollback.payment_entry_count_after or 0):
        issues.append("Phase 9P Payment Entry count changed.")
    if int(rollback.payment_entry_gl_count_before or 0) != int(rollback.payment_entry_gl_count_after or 0):
        issues.append("Phase 9P Payment Entry GL count changed.")
    if guard["production_batch_enabled_policy_count"] != 0:
        issues.append("Controlled production batch enabled policy count must be 0 before freeze.")
    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must be 0 before freeze.")
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
    line = frappe.new_doc("NDIS Limited Production Batch Enablement Evidence Freeze Line")
    line.evidence_freeze = doc.name
    line.line_no = 1
    line.line_label = "Limited Production Batch Enablement Smoke And Rollback Evidence Frozen"
    line.line_status = "Frozen"
    line.policy_doctype = doc.target_policy_doctype
    line.policy_name = doc.target_policy
    line.policy_action = "Frozen evidence: enabled during Phase 9O, rolled back in Phase 9P"
    line.enabled_before_rollback = int(doc.target_policy_enabled_before_rollback or 0)
    line.enabled_after_rollback = int(doc.target_policy_enabled_after_rollback or 0)
    line.live_before_rollback = int(doc.target_policy_live_before_rollback or 0)
    line.live_after_rollback = int(doc.target_policy_live_after_rollback or 0)
    line.rollback_completed = int(doc.rollback_verified or 0)
    line.freeze_completed = int(doc.evidence_freeze_allowed or 0)
    line.production_batch_posting_allowed = 0
    line.real_posting_allowed = 0
    line.policy_live_enabled = 0
    line.detail = "Phase 9Q read-only evidence freeze completed. No policy, PE, or GL movement occurred."
    line.checked_on = doc.checked_on
    line.insert(ignore_permissions=True)


@frappe.whitelist()
def run_limited_production_batch_enablement_freeze(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_limited_production_batch_enablement_freeze")

    rollback = latest_completed_rollback()
    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }
    guard_before = guardrails()
    ack_ok = acknowledgement == FREEZE_ACK
    issues = validate_source(rollback, guard_before)
    allowed = int(ack_ok and not issues and rollback is not None)
    counts = count_status(issues, ack_ok, frozen=bool(allowed))
    guard_now = guardrails()

    base_result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Frozen" if allowed else "Needs Review",
        "freeze_status": "Limited Enablement Smoke Evidence Frozen" if allowed else "Needs Review",
        "evidence_freeze_allowed": allowed,
        "ready_for_next_phase": allowed,
        "phase9p_rollback_verified": 1 if rollback else 0,
        "phase9o_smoke_verified": 1 if rollback else 0,
        "phase9n_activation_gate_verified": 1 if rollback else 0,
        "phase9m_adapter_verified": 1 if rollback else 0,
        "phase9l_preview_verified": 1 if rollback else 0,
        "policy_caps_verified": 1 if rollback and int(rollback.max_batch_lines or 0) == 3 and flt(rollback.max_batch_amount or 0, 2) == 3 and int(rollback.max_payment_entry_count or 0) == 1 else 0,
        "rollback_verified": 1 if rollback else 0,
        "no_accounting_movement_verified": 1 if rollback and int(rollback.payment_entry_count_before or 0) == int(rollback.payment_entry_count_after or 0) and int(rollback.payment_entry_gl_count_before or 0) == int(rollback.payment_entry_gl_count_after or 0) else 0,
        "production_batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "policy_live_enabled": 0,
        "rollback_run": rollback.name if rollback else None,
        "enablement_smoke": rollback.enablement_smoke if rollback else None,
        "activation_gate": rollback.activation_gate if rollback else None,
        "enablement_adapter": rollback.enablement_adapter if rollback else None,
        "enablement_preview": rollback.enablement_preview if rollback else None,
        "enablement_gate": rollback.enablement_gate if rollback else None,
        "policy_lock": rollback.policy_lock if rollback else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": rollback.target_policy if rollback else None,
        "target_policy_name": rollback.target_policy_name if rollback else None,
        "enablement_field": "production_batch_enabled",
        "live_field": "live_posting_allowed",
        "target_policy_enabled_before_rollback": int(rollback.target_policy_enabled_before_rollback or 0) if rollback else 0,
        "target_policy_enabled_after_rollback": int(rollback.target_policy_enabled_after_rollback or 0) if rollback else 0,
        "target_policy_live_before_rollback": int(rollback.target_policy_live_before_rollback or 0) if rollback else 0,
        "target_policy_live_after_rollback": int(rollback.target_policy_live_after_rollback or 0) if rollback else 0,
        "policy_enabled_before_count": int(rollback.policy_enabled_before_count or 0) if rollback else 0,
        "policy_enabled_after_count": int(rollback.policy_enabled_after_count or 0) if rollback else 0,
        "actual_enabled_policy_count_before": int(rollback.actual_enabled_policy_count_before or 0) if rollback else 0,
        "actual_enabled_policy_count_after": int(rollback.actual_enabled_policy_count_after or 0) if rollback else 0,
        "max_batch_lines": int(rollback.max_batch_lines or 0) if rollback else 0,
        "max_batch_amount": flt(rollback.max_batch_amount or 0) if rollback else 0,
        "max_payment_entry_count": int(rollback.max_payment_entry_count or 0) if rollback else 0,
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
        "note": "Phase 9Q freezes Phase 9O/9P evidence only. It creates no Payment Entry, no GL, and enables no policy.",
    }

    if int(dry_run or 0):
        base_result.update(
            {
                "status": "Needs Review",
                "freeze_status": "Needs Review",
                "evidence_freeze_allowed": 0,
                "ready_for_next_phase": 0,
            }
        )
        return base_result

    doc = frappe.new_doc("NDIS Limited Production Batch Enablement Evidence Freeze")
    doc.freeze_id = make_freeze_id()
    for fieldname, value in base_result.items():
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
    doc.summary_json = safe_json(base_result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    if allowed:
        create_freeze_line(doc)

    frappe.db.commit()

    final_doc = frappe.get_doc("NDIS Limited Production Batch Enablement Evidence Freeze", doc.name)
    return {
        **base_result,
        "created": True,
        "evidence_freeze": final_doc.name,
        "freeze_id": final_doc.freeze_id,
        "status": final_doc.status,
        "freeze_status": final_doc.freeze_status,
        "evidence_freeze_allowed": int(final_doc.evidence_freeze_allowed or 0),
        "ready_for_next_phase": int(final_doc.ready_for_next_phase or 0),
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_limited_production_batch_enablement_freeze(evidence_freeze, reason=None):
    assert_action("cancel_limited_production_batch_enablement_freeze")
    if not frappe.db.exists("NDIS Limited Production Batch Enablement Evidence Freeze", evidence_freeze):
        frappe.throw(_("Evidence freeze not found: {0}").format(evidence_freeze))
    doc = frappe.get_doc("NDIS Limited Production Batch Enablement Evidence Freeze", evidence_freeze)
    if doc.status == "Cancelled":
        return {"evidence_freeze": evidence_freeze, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.evidence_freeze_allowed or 0):
        frappe.throw(_("Cannot cancel an approved Phase 9Q evidence freeze. Create a superseding freeze instead."))

    frappe.db.set_value(
        "NDIS Limited Production Batch Enablement Evidence Freeze",
        evidence_freeze,
        {
            "status": "Cancelled",
            "freeze_status": "Cancelled",
            "evidence_freeze_allowed": 0,
            "ready_for_next_phase": 0,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 9Q no-ack freeze audit cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(
        """
        UPDATE `tabNDIS Limited Production Batch Enablement Evidence Freeze Line`
        SET line_status = 'Cancelled'
        WHERE evidence_freeze = %(evidence_freeze)s
        """,
        {"evidence_freeze": evidence_freeze},
    )
    frappe.db.commit()
    return {
        "evidence_freeze": evidence_freeze,
        "status": "Cancelled",
        "note": "No-ack evidence freeze audit cancelled only. No policy or accounting movement occurred.",
    }


@frappe.whitelist()
def quick_limited_production_batch_enablement_freeze_summary(limit=20):
    freezes = frappe.get_all(
        "NDIS Limited Production Batch Enablement Evidence Freeze",
        fields=[
            "name",
            "freeze_id",
            "status",
            "freeze_status",
            "evidence_freeze_allowed",
            "ready_for_next_phase",
            "rollback_run",
            "enablement_smoke",
            "activation_gate",
            "target_policy",
            "target_policy_enabled_before_rollback",
            "target_policy_enabled_after_rollback",
            "target_policy_live_before_rollback",
            "target_policy_live_after_rollback",
            "policy_enabled_before_count",
            "policy_enabled_after_count",
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
        "NDIS Limited Production Batch Enablement Evidence Freeze Line",
        fields=[
            "name",
            "evidence_freeze",
            "line_no",
            "line_status",
            "policy_name",
            "policy_action",
            "enabled_before_rollback",
            "enabled_after_rollback",
            "live_before_rollback",
            "live_after_rollback",
            "rollback_completed",
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
        "note": "Phase 9Q evidence freeze summary. Read-only freeze, no accounting movement.",
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
            f.name AS evidence_freeze,
            f.freeze_id,
            f.status,
            f.freeze_status,
            f.evidence_freeze_allowed,
            f.ready_for_next_phase,
            f.rollback_run,
            f.enablement_smoke,
            f.activation_gate,
            f.target_policy,
            f.policy_enabled_before_count,
            f.policy_enabled_after_count,
            f.target_policy_enabled_before_rollback,
            f.target_policy_enabled_after_rollback,
            f.target_policy_live_before_rollback,
            f.target_policy_live_after_rollback,
            f.actual_payment_entry_created_count,
            f.actual_gl_created_count,
            f.freeze_score,
            f.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Limited Production Batch Enablement Evidence Freeze` f
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
                {"name": "Frozen", "values": [int(row.evidence_freeze_allowed or 0) for row in data[:20]]},
                {"name": "Enabled After", "values": [int(row.policy_enabled_after_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Evidence Freezes"), "datatype": "Int"},
        {"value": sum(int(row.evidence_freeze_allowed or 0) for row in data), "indicator": "Green", "label": _("Frozen"), "datatype": "Int"},
        {"value": sum(int(row.policy_enabled_after_count or 0) for row in data), "indicator": "Red", "label": _("Enabled After"), "datatype": "Int"},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PE"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def freeze_columns():
    return [
        {"fieldname": "evidence_freeze", "label": _("Evidence Freeze"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Evidence Freeze", "width": 220},
        {"fieldname": "freeze_id", "label": _("Freeze ID"), "fieldtype": "Data", "width": 450},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "freeze_status", "label": _("Freeze Status"), "fieldtype": "Data", "width": 310},
        {"fieldname": "evidence_freeze_allowed", "label": _("Frozen"), "fieldtype": "Check", "width": 90},
        {"fieldname": "ready_for_next_phase", "label": _("Ready Next"), "fieldtype": "Check", "width": 100},
        {"fieldname": "rollback_run", "label": _("Rollback Run"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Rollback Run", "width": 220},
        {"fieldname": "enablement_smoke", "label": _("Smoke Run"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Smoke Run", "width": 220},
        {"fieldname": "target_policy", "label": _("Target Policy"), "fieldtype": "Data", "width": 260},
        {"fieldname": "policy_enabled_before_count", "label": _("Enabled Before"), "fieldtype": "Int", "width": 120},
        {"fieldname": "policy_enabled_after_count", "label": _("Enabled After"), "fieldtype": "Int", "width": 120},
        {"fieldname": "target_policy_enabled_before_rollback", "label": _("Policy Before"), "fieldtype": "Check", "width": 110},
        {"fieldname": "target_policy_enabled_after_rollback", "label": _("Policy After"), "fieldtype": "Check", "width": 110},
        {"fieldname": "target_policy_live_after_rollback", "label": _("Live After"), "fieldtype": "Check", "width": 90},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "freeze_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_line_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    if filters.get("evidence_freeze"):
        conditions.append("l.evidence_freeze = %(evidence_freeze)s")
    if filters.get("line_status"):
        conditions.append("l.line_status = %(line_status)s")

    data = frappe.db.sql(
        f"""
        SELECT
            l.name AS line,
            l.evidence_freeze,
            l.line_no,
            l.line_status,
            l.policy_name,
            l.policy_action,
            l.enabled_before_rollback,
            l.enabled_after_rollback,
            l.live_before_rollback,
            l.live_after_rollback,
            l.rollback_completed,
            l.freeze_completed,
            l.detail,
            l.checked_on
        FROM `tabNDIS Limited Production Batch Enablement Evidence Freeze Line` l
        {build_where(conditions)}
        ORDER BY l.evidence_freeze DESC, l.line_no ASC
        """,
        filters,
        as_dict=True,
    )
    columns = [
        {"fieldname": "line", "label": _("Line"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Evidence Freeze Line", "width": 220},
        {"fieldname": "evidence_freeze", "label": _("Evidence Freeze"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Evidence Freeze", "width": 220},
        {"fieldname": "line_no", "label": _("Line No"), "fieldtype": "Int", "width": 80},
        {"fieldname": "line_status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "policy_name", "label": _("Policy"), "fieldtype": "Data", "width": 260},
        {"fieldname": "policy_action", "label": _("Action"), "fieldtype": "Data", "width": 390},
        {"fieldname": "enabled_before_rollback", "label": _("Enabled Before"), "fieldtype": "Check", "width": 120},
        {"fieldname": "enabled_after_rollback", "label": _("Enabled After"), "fieldtype": "Check", "width": 120},
        {"fieldname": "live_after_rollback", "label": _("Live After"), "fieldtype": "Check", "width": 90},
        {"fieldname": "rollback_completed", "label": _("Rollback Done"), "fieldtype": "Check", "width": 110},
        {"fieldname": "freeze_completed", "label": _("Freeze Done"), "fieldtype": "Check", "width": 110},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]
    chart = {
        "data": {
            "labels": [row.policy_name for row in data[:20]],
            "datasets": [
                {"name": "Enabled Before", "values": [int(row.enabled_before_rollback or 0) for row in data[:20]]},
                {"name": "Enabled After", "values": [int(row.enabled_after_rollback or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Freeze Lines"), "datatype": "Int"},
        {"value": sum(int(row.freeze_completed or 0) for row in data), "indicator": "Green", "label": _("Frozen"), "datatype": "Int"},
        {"value": sum(int(row.enabled_after_rollback or 0) for row in data), "indicator": "Red", "label": _("Enabled After"), "datatype": "Int"},
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
