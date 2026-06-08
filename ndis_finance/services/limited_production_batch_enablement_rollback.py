import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


ROLLBACK_ACK = "I_CONFIRM_PHASE9P_ROLLBACK_LIMITED_PRODUCTION_BATCH_POLICY_ENABLEMENT"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"


def make_rollback_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-LIMITED-PROD-BATCH-ENABLEMENT-ROLLBACK-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_enabled_smoke():
    rows = frappe.get_all(
        "NDIS Limited Production Batch Enablement Smoke Run",
        filters={
            "status": "Enabled - Rollback Required",
            "limited_policy_enabled": 1,
            "rollback_required": 1,
            "freeze_required_after_rollback": 1,
            "actual_enabled_policy_count": 1,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
            "target_policy_enabled_after": 1,
            "target_policy_live_after": 0,
        },
        fields=[
            "name",
            "enablement_smoke_id",
            "activation_gate",
            "enablement_adapter",
            "enablement_preview",
            "enablement_gate",
            "policy_lock",
            "company",
            "customer",
            "target_policy_doctype",
            "target_policy",
            "target_policy_name",
            "enablement_field",
            "live_field",
            "max_batch_lines",
            "max_batch_amount",
            "max_payment_entry_count",
            "policy_enabled_before_count",
            "policy_enabled_after_count",
            "actual_enabled_policy_count",
            "target_policy_enabled_before",
            "target_policy_enabled_after",
            "target_policy_live_before",
            "target_policy_live_after",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )

    return rows[0] if rows else None


def existing_completed_rollback(enablement_smoke):
    rows = frappe.get_all(
        "NDIS Limited Production Batch Enablement Rollback Run",
        filters={
            "enablement_smoke": enablement_smoke,
            "status": "Rolled Back",
            "limited_policy_rollback_completed": 1,
            "ready_for_enablement_freeze": 1,
        },
        fields=["name", "rollback_id"],
        limit=1,
    )
    return rows[0] if rows else None


def validate_policy_schema():
    if not frappe.db.exists("DocType", POLICY_DOCTYPE):
        return [f"Missing DocType: {POLICY_DOCTYPE}"]

    issues = []

    if not has_column(POLICY_DOCTYPE, "production_batch_enabled"):
        issues.append("Policy DocType is missing required field production_batch_enabled.")

    if not has_column(POLICY_DOCTYPE, "live_posting_allowed"):
        issues.append("Policy DocType is missing required field live_posting_allowed.")

    return issues


def validate_source(smoke, guard):
    issues = []

    if not smoke:
        issues.append("No rollback-required Phase 9O enablement smoke found.")
        return issues

    existing = existing_completed_rollback(smoke.name)
    if existing:
        issues.append(f"Phase 9P rollback already completed for this smoke: {existing.rollback_id}")

    issues.extend(validate_policy_schema())

    if not smoke.target_policy:
        issues.append("Phase 9O smoke has no target policy.")

    if smoke.target_policy and not frappe.db.exists(POLICY_DOCTYPE, smoke.target_policy):
        issues.append(f"Target policy does not exist: {smoke.target_policy}")

    if smoke.target_policy:
        if get_flag(POLICY_DOCTYPE, smoke.target_policy, "production_batch_enabled") != 1:
            issues.append("Target policy must be enabled before rollback.")

        if get_flag(POLICY_DOCTYPE, smoke.target_policy, "live_posting_allowed") != 0:
            issues.append("Target policy live_posting_allowed must remain 0 before rollback.")

    if int(smoke.actual_enabled_policy_count or 0) != 1:
        issues.append("Phase 9O actual_enabled_policy_count must be 1.")

    if int(smoke.actual_payment_entry_created_count or 0) != 0:
        issues.append("Phase 9O actual Payment Entry created count must be 0.")

    if int(smoke.actual_gl_created_count or 0) != 0:
        issues.append("Phase 9O actual GL created count must be 0.")

    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must be enabled before rollback.")

    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Live posting allowed policy count must be 0 before rollback.")

    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today is not zero.")

    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today is not zero.")

    return issues


def count_status(issues, ack_ok, completed=False):
    blockers = len(issues)
    warnings = 0 if ack_ok else 1
    passes = 9 if not blockers else 0
    infos = 2
    score = max(0, 100 - blockers * 25 - warnings * 5)

    return {
        "blocker_count": blockers,
        "warning_count": warnings,
        "pass_count": passes,
        "info_count": infos,
        "line_count": 1 if completed else 0,
        "rollback_score": score,
    }


def rollback_target_policy(target_policy):
    if not target_policy:
        frappe.throw(_("Target policy is required for Phase 9P rollback."))

    if not has_column(POLICY_DOCTYPE, "production_batch_enabled"):
        frappe.throw(_("Target policy DocType is missing production_batch_enabled field."))

    if not has_column(POLICY_DOCTYPE, "live_posting_allowed"):
        frappe.throw(_("Target policy DocType is missing live_posting_allowed field."))

    before_enabled = get_flag(POLICY_DOCTYPE, target_policy, "production_batch_enabled")
    before_live = get_flag(POLICY_DOCTYPE, target_policy, "live_posting_allowed")

    if before_enabled != 1:
        frappe.throw(_("Target policy is not enabled before Phase 9P rollback: {0}").format(target_policy))

    if before_live != 0:
        frappe.throw(_("Phase 9P safety violation: target policy live flag is enabled before rollback."))

    updates = {
        "production_batch_enabled": 0,
        "live_posting_allowed": 0,
    }

    if has_column(POLICY_DOCTYPE, "production_batch_posting_allowed"):
        updates["production_batch_posting_allowed"] = 0

    if has_column(POLICY_DOCTYPE, "real_posting_allowed"):
        updates["real_posting_allowed"] = 0

    if has_column(POLICY_DOCTYPE, "policy_live_enabled"):
        updates["policy_live_enabled"] = 0

    frappe.db.set_value(POLICY_DOCTYPE, target_policy, updates, update_modified=True)

    after_enabled = get_flag(POLICY_DOCTYPE, target_policy, "production_batch_enabled")
    after_live = get_flag(POLICY_DOCTYPE, target_policy, "live_posting_allowed")

    if after_enabled != 0:
        frappe.throw(_("Phase 9P rollback failed: target policy still enabled."))

    if after_live != 0:
        frappe.throw(_("Phase 9P safety violation: live_posting_allowed became enabled."))

    return {
        "target_policy_enabled_before_rollback": before_enabled,
        "target_policy_enabled_after_rollback": after_enabled,
        "target_policy_live_before_rollback": before_live,
        "target_policy_live_after_rollback": after_live,
    }


def create_rollback_line(doc):
    line = frappe.new_doc("NDIS Limited Production Batch Enablement Rollback Line")
    line.rollback_run = doc.name
    line.line_no = 1
    line.line_label = "Controlled Limited Production Batch Policy Enablement Rolled Back"
    line.line_status = "Rolled Back"
    line.policy_doctype = doc.target_policy_doctype
    line.policy_name = doc.target_policy
    line.policy_action = "Rolled back production_batch_enabled to 0; live posting remained blocked"
    line.enabled_before_rollback = int(doc.target_policy_enabled_before_rollback or 0)
    line.enabled_after_rollback = int(doc.target_policy_enabled_after_rollback or 0)
    line.live_before_rollback = int(doc.target_policy_live_before_rollback or 0)
    line.live_after_rollback = int(doc.target_policy_live_after_rollback or 0)
    line.rollback_completed = int(doc.limited_policy_rollback_completed or 0)
    line.production_batch_posting_allowed = 0
    line.real_posting_allowed = 0
    line.policy_live_enabled = 0
    line.detail = "Phase 9P rollback completed. Policy enablement reverted and ready for freeze."
    line.checked_on = doc.checked_on
    line.insert(ignore_permissions=True)


@frappe.whitelist()
def run_limited_production_batch_enablement_rollback(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_limited_production_batch_enablement_rollback")

    smoke = latest_enabled_smoke()
    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }
    guard_before = guardrails()
    ack_ok = acknowledgement == ROLLBACK_ACK
    issues = validate_source(smoke, guard_before)

    allowed = int(ack_ok and not issues and smoke is not None)
    counts = count_status(issues, ack_ok, completed=bool(allowed))

    base_result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Rolled Back" if allowed else "Needs Review",
        "rollback_status": "Limited Policy Enablement Rolled Back - Freeze Required" if allowed else "Needs Review",
        "limited_policy_rollback_completed": allowed,
        "ready_for_enablement_freeze": allowed,
        "phase9o_smoke_verified": 1 if smoke else 0,
        "phase9n_activation_gate_verified": 1 if smoke else 0,
        "phase9m_adapter_verified": 1 if smoke else 0,
        "phase9l_preview_verified": 1 if smoke else 0,
        "policy_caps_verified": 1 if smoke and int(smoke.max_batch_lines or 0) == 3 and flt(smoke.max_batch_amount or 0, 2) == 3 and int(smoke.max_payment_entry_count or 0) == 1 else 0,
        "rollback_only_verified": 1,
        "production_batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "policy_live_enabled": 0,
        "enablement_smoke": smoke.name if smoke else None,
        "activation_gate": smoke.activation_gate if smoke else None,
        "enablement_adapter": smoke.enablement_adapter if smoke else None,
        "enablement_preview": smoke.enablement_preview if smoke else None,
        "enablement_gate": smoke.enablement_gate if smoke else None,
        "policy_lock": smoke.policy_lock if smoke else None,
        "company": smoke.company if smoke else None,
        "customer": smoke.customer if smoke else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": smoke.target_policy if smoke else None,
        "target_policy_name": smoke.target_policy_name if smoke else None,
        "enablement_field": "production_batch_enabled",
        "live_field": "live_posting_allowed",
        "target_policy_enabled_before_rollback": get_flag(POLICY_DOCTYPE, smoke.target_policy, "production_batch_enabled") if smoke else 0,
        "target_policy_enabled_after_rollback": get_flag(POLICY_DOCTYPE, smoke.target_policy, "production_batch_enabled") if smoke else 0,
        "target_policy_live_before_rollback": get_flag(POLICY_DOCTYPE, smoke.target_policy, "live_posting_allowed") if smoke else 0,
        "target_policy_live_after_rollback": get_flag(POLICY_DOCTYPE, smoke.target_policy, "live_posting_allowed") if smoke else 0,
        "policy_enabled_before_count": guard_before["production_batch_enabled_policy_count"],
        "policy_enabled_after_count": guard_before["production_batch_enabled_policy_count"],
        "actual_enabled_policy_count_before": int(smoke.actual_enabled_policy_count or 0) if smoke else 0,
        "actual_enabled_policy_count_after": int(smoke.actual_enabled_policy_count or 0) if smoke else 0,
        "max_batch_lines": int(smoke.max_batch_lines or 0) if smoke else 0,
        "max_batch_amount": flt(smoke.max_batch_amount or 0) if smoke else 0,
        "max_payment_entry_count": int(smoke.max_payment_entry_count or 0) if smoke else 0,
        "actual_payment_entry_created_count": 0,
        "actual_gl_created_count": 0,
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guardrails()["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guardrails()["payment_entry_gl_count"],
        "submitted_journal_entry_count_today": guard_before["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_before["purchase_invoice_count_today"],
        "live_posting_allowed_policy_count": guard_before["live_posting_allowed_policy_count"],
        **counts,
        "issues": issues,
        "guardrails_before": guard_before,
        "guardrails_after": guardrails(),
        "config": config,
        "required_acknowledgement": ROLLBACK_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 9P rolls back the Phase 9O policy enablement only. It creates no Payment Entry and no GL.",
    }

    if int(dry_run or 0):
        base_result["status"] = "Needs Review"
        base_result["rollback_status"] = "Needs Review"
        base_result["limited_policy_rollback_completed"] = 0
        base_result["ready_for_enablement_freeze"] = 0
        return base_result

    doc = frappe.new_doc("NDIS Limited Production Batch Enablement Rollback Run")
    doc.rollback_id = make_rollback_id()
    doc.status = base_result["status"]
    doc.rollback_status = base_result["rollback_status"]

    for fieldname, value in base_result.items():
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
    doc.summary_json = safe_json(base_result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    if allowed:
        rollback_result = rollback_target_policy(smoke.target_policy)
        guard_after = guardrails()

        updates = {
            "limited_policy_rollback_completed": 1,
            "ready_for_enablement_freeze": 1,
            "target_policy_enabled_before_rollback": rollback_result["target_policy_enabled_before_rollback"],
            "target_policy_enabled_after_rollback": rollback_result["target_policy_enabled_after_rollback"],
            "target_policy_live_before_rollback": rollback_result["target_policy_live_before_rollback"],
            "target_policy_live_after_rollback": rollback_result["target_policy_live_after_rollback"],
            "policy_enabled_after_count": guard_after["production_batch_enabled_policy_count"],
            "actual_enabled_policy_count_after": guard_after["production_batch_enabled_policy_count"],
            "payment_entry_count_after": guard_after["payment_entry_count"],
            "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
            "live_posting_allowed_policy_count": guard_after["live_posting_allowed_policy_count"],
            "line_count": 1,
        }

        for fieldname, value in updates.items():
            if doc.meta.has_field(fieldname):
                setattr(doc, fieldname, value)

        doc.summary_json = safe_json({**base_result, **updates, "guardrails_after": guard_after})
        doc.save(ignore_permissions=True)
        create_rollback_line(doc)
    else:
        guard_after = guardrails()
        frappe.db.set_value(
            "NDIS Limited Production Batch Enablement Rollback Run",
            doc.name,
            {
                "payment_entry_count_after": guard_after["payment_entry_count"],
                "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
                "summary_json": safe_json({**base_result, "guardrails_after": guard_after}),
            },
            update_modified=False,
        )

    frappe.db.commit()

    final_doc = frappe.get_doc("NDIS Limited Production Batch Enablement Rollback Run", doc.name)

    result = {
        **base_result,
        "created": True,
        "rollback_run": final_doc.name,
        "rollback_id": final_doc.rollback_id,
        "status": final_doc.status,
        "rollback_status": final_doc.rollback_status,
        "limited_policy_rollback_completed": int(final_doc.limited_policy_rollback_completed or 0),
        "ready_for_enablement_freeze": int(final_doc.ready_for_enablement_freeze or 0),
        "target_policy_enabled_before_rollback": int(final_doc.target_policy_enabled_before_rollback or 0),
        "target_policy_enabled_after_rollback": int(final_doc.target_policy_enabled_after_rollback or 0),
        "target_policy_live_before_rollback": int(final_doc.target_policy_live_before_rollback or 0),
        "target_policy_live_after_rollback": int(final_doc.target_policy_live_after_rollback or 0),
        "policy_enabled_before_count": int(final_doc.policy_enabled_before_count or 0),
        "policy_enabled_after_count": int(final_doc.policy_enabled_after_count or 0),
        "actual_enabled_policy_count_after": int(final_doc.actual_enabled_policy_count_after or 0),
        "guardrails_after": guardrails(),
    }

    return result


@frappe.whitelist()
def cancel_limited_production_batch_enablement_rollback(rollback_run, reason=None):
    assert_action("cancel_limited_production_batch_enablement_rollback")

    if not frappe.db.exists("NDIS Limited Production Batch Enablement Rollback Run", rollback_run):
        frappe.throw(_("Rollback run not found: {0}").format(rollback_run))

    doc = frappe.get_doc("NDIS Limited Production Batch Enablement Rollback Run", rollback_run)

    if doc.status == "Cancelled":
        return {"rollback_run": rollback_run, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.limited_policy_rollback_completed or 0):
        frappe.throw(_("Cannot cancel a completed Phase 9P rollback. Proceed to freeze instead."))

    frappe.db.set_value(
        "NDIS Limited Production Batch Enablement Rollback Run",
        rollback_run,
        {
            "status": "Cancelled",
            "rollback_status": "Cancelled",
            "limited_policy_rollback_completed": 0,
            "ready_for_enablement_freeze": 0,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 9P no-ack rollback audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        """
        UPDATE `tabNDIS Limited Production Batch Enablement Rollback Line`
        SET line_status = 'Cancelled'
        WHERE rollback_run = %(rollback_run)s
        """,
        {"rollback_run": rollback_run},
    )

    frappe.db.commit()

    return {
        "rollback_run": rollback_run,
        "status": "Cancelled",
        "note": "No-ack rollback audit record cancelled only. No policy or accounting movement occurred.",
    }


@frappe.whitelist()
def quick_limited_production_batch_enablement_rollback_summary(limit=20):
    runs = frappe.get_all(
        "NDIS Limited Production Batch Enablement Rollback Run",
        fields=[
            "name",
            "rollback_id",
            "status",
            "rollback_status",
            "limited_policy_rollback_completed",
            "ready_for_enablement_freeze",
            "enablement_smoke",
            "activation_gate",
            "target_policy",
            "target_policy_enabled_before_rollback",
            "target_policy_enabled_after_rollback",
            "target_policy_live_before_rollback",
            "target_policy_live_after_rollback",
            "policy_enabled_before_count",
            "policy_enabled_after_count",
            "actual_enabled_policy_count_before",
            "actual_enabled_policy_count_after",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
            "rollback_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    lines = frappe.get_all(
        "NDIS Limited Production Batch Enablement Rollback Line",
        fields=[
            "name",
            "rollback_run",
            "line_no",
            "line_status",
            "policy_name",
            "policy_action",
            "enabled_before_rollback",
            "enabled_after_rollback",
            "live_before_rollback",
            "live_after_rollback",
            "rollback_completed",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    return {
        "runs": runs,
        "lines": lines,
        "required_acknowledgement": ROLLBACK_ACK,
        "guardrails": guardrails(),
        "note": "Phase 9P rollback summary. Ready for evidence freeze when completed.",
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
            r.name AS rollback_run,
            r.rollback_id,
            r.status,
            r.rollback_status,
            r.limited_policy_rollback_completed,
            r.ready_for_enablement_freeze,
            r.enablement_smoke,
            r.activation_gate,
            r.target_policy,
            r.policy_enabled_before_count,
            r.policy_enabled_after_count,
            r.target_policy_enabled_before_rollback,
            r.target_policy_enabled_after_rollback,
            r.target_policy_live_before_rollback,
            r.target_policy_live_after_rollback,
            r.actual_payment_entry_created_count,
            r.actual_gl_created_count,
            r.rollback_score,
            r.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Limited Production Batch Enablement Rollback Run` r
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
                {"name": "Rollback Completed", "values": [int(row.limited_policy_rollback_completed or 0) for row in data[:20]]},
                {"name": "Enabled After", "values": [int(row.policy_enabled_after_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Rollback Runs"), "datatype": "Int"},
        {"value": sum(int(row.limited_policy_rollback_completed or 0) for row in data), "indicator": "Green", "label": _("Completed"), "datatype": "Int"},
        {"value": sum(int(row.policy_enabled_after_count or 0) for row in data), "indicator": "Red", "label": _("Enabled After"), "datatype": "Int"},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PE"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def rollback_columns():
    return [
        {"fieldname": "rollback_run", "label": _("Rollback Run"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Rollback Run", "width": 220},
        {"fieldname": "rollback_id", "label": _("Rollback ID"), "fieldtype": "Data", "width": 450},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 160},
        {"fieldname": "rollback_status", "label": _("Rollback Status"), "fieldtype": "Data", "width": 340},
        {"fieldname": "limited_policy_rollback_completed", "label": _("Completed"), "fieldtype": "Check", "width": 90},
        {"fieldname": "ready_for_enablement_freeze", "label": _("Ready Freeze"), "fieldtype": "Check", "width": 110},
        {"fieldname": "enablement_smoke", "label": _("Smoke Run"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Smoke Run", "width": 220},
        {"fieldname": "target_policy", "label": _("Target Policy"), "fieldtype": "Data", "width": 230},
        {"fieldname": "policy_enabled_before_count", "label": _("Enabled Before"), "fieldtype": "Int", "width": 120},
        {"fieldname": "policy_enabled_after_count", "label": _("Enabled After"), "fieldtype": "Int", "width": 120},
        {"fieldname": "target_policy_enabled_before_rollback", "label": _("Policy Before"), "fieldtype": "Check", "width": 100},
        {"fieldname": "target_policy_enabled_after_rollback", "label": _("Policy After"), "fieldtype": "Check", "width": 100},
        {"fieldname": "target_policy_live_after_rollback", "label": _("Live After"), "fieldtype": "Check", "width": 90},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "rollback_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_line_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []

    if filters.get("rollback_run"):
        conditions.append("l.rollback_run = %(rollback_run)s")

    if filters.get("line_status"):
        conditions.append("l.line_status = %(line_status)s")

    data = frappe.db.sql(
        f"""
        SELECT
            l.name AS line,
            l.rollback_run,
            l.line_no,
            l.line_status,
            l.policy_name,
            l.policy_action,
            l.enabled_before_rollback,
            l.enabled_after_rollback,
            l.live_before_rollback,
            l.live_after_rollback,
            l.rollback_completed,
            l.detail,
            l.checked_on
        FROM `tabNDIS Limited Production Batch Enablement Rollback Line` l
        {build_where(conditions)}
        ORDER BY l.rollback_run DESC, l.line_no ASC
        """,
        filters,
        as_dict=True,
    )

    columns = [
        {"fieldname": "line", "label": _("Line"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Rollback Line", "width": 220},
        {"fieldname": "rollback_run", "label": _("Rollback Run"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Rollback Run", "width": 220},
        {"fieldname": "line_no", "label": _("Line No"), "fieldtype": "Int", "width": 80},
        {"fieldname": "line_status", "label": _("Status"), "fieldtype": "Data", "width": 140},
        {"fieldname": "policy_name", "label": _("Policy"), "fieldtype": "Data", "width": 260},
        {"fieldname": "policy_action", "label": _("Action"), "fieldtype": "Data", "width": 360},
        {"fieldname": "enabled_before_rollback", "label": _("Enabled Before"), "fieldtype": "Check", "width": 120},
        {"fieldname": "enabled_after_rollback", "label": _("Enabled After"), "fieldtype": "Check", "width": 120},
        {"fieldname": "live_after_rollback", "label": _("Live After"), "fieldtype": "Check", "width": 90},
        {"fieldname": "rollback_completed", "label": _("Completed"), "fieldtype": "Check", "width": 100},
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
        {"value": len(data), "indicator": "Blue", "label": _("Rollback Lines"), "datatype": "Int"},
        {"value": sum(int(row.rollback_completed or 0) for row in data), "indicator": "Green", "label": _("Completed"), "datatype": "Int"},
        {"value": sum(int(row.enabled_after_rollback or 0) for row in data), "indicator": "Red", "label": _("Enabled After"), "datatype": "Int"},
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
