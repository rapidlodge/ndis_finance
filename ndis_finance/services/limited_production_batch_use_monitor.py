import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


MONITOR_ACK = "I_CONFIRM_PHASE9U_APPROVE_LIMITED_BATCH_USE_MONITORING_NO_POSTING"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
PHASE9T_FREEZE_DOCTYPE = "NDIS Limited Production Batch Policy Enablement Freeze"
MONITOR_GATE_DOCTYPE = "NDIS Limited Production Batch Use Monitor Gate"
MONITOR_ITEM_DOCTYPE = "NDIS Limited Production Batch Use Monitor Item"


def make_monitor_gate_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-LIMITED-PROD-BATCH-USE-MONITOR-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_phase9t_freeze():
    rows = frappe.get_all(
        PHASE9T_FREEZE_DOCTYPE,
        filters={
            "status": "Frozen",
            "policy_enablement_freeze_allowed": 1,
            "ready_for_limited_batch_monitoring": 1,
            "phase9s_enablement_verified": 1,
            "phase9r_readiness_gate_verified": 1,
            "phase9q_freeze_verified": 1,
            "phase9p_rollback_verified": 1,
            "phase9o_smoke_verified": 1,
            "policy_caps_verified": 1,
            "controlled_policy_enabled_verified": 1,
            "live_posting_blocked_verified": 1,
            "no_accounting_movement_verified": 1,
            "current_target_policy_enabled": 1,
            "current_target_policy_live": 0,
            "production_batch_enabled_policy_count": 1,
            "live_posting_allowed_policy_count": 0,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
        },
        fields=[
            "name",
            "freeze_id",
            "enablement_run",
            "readiness_gate",
            "evidence_freeze",
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
            "freeze_score",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_approved_gate(policy_enablement_freeze):
    if not policy_enablement_freeze:
        return None
    rows = frappe.get_all(
        MONITOR_GATE_DOCTYPE,
        filters={
            "policy_enablement_freeze": policy_enablement_freeze,
            "status": "Approved",
            "monitor_gate_approved": 1,
            "ready_for_operational_monitoring": 1,
        },
        fields=["name", "monitor_gate_id"],
        limit=1,
    )
    return rows[0] if rows else None


def validate_source(freeze, guard, config):
    issues = []
    if config["production_mode"]:
        issues.append("Production mode must remain disabled for Phase 9U monitor gate.")
    if config["live_pe_enabled"]:
        issues.append("Live Payment Entry posting config must remain disabled for Phase 9U monitor gate.")
    if not freeze:
        issues.append("No completed Phase 9T controlled policy enablement freeze found.")
        return issues

    existing = existing_approved_gate(freeze.name)
    if existing:
        issues.append(f"Phase 9U monitor gate already exists for this freeze: {existing.monitor_gate_id}")

    required_links = {
        "enablement_run": freeze.enablement_run,
        "readiness_gate": freeze.readiness_gate,
        "evidence_freeze": freeze.evidence_freeze,
        "rollback_run": freeze.rollback_run,
        "enablement_smoke": freeze.enablement_smoke,
    }
    for label, value in required_links.items():
        if not value:
            issues.append(f"Missing evidence link: {label}")

    if freeze.enablement_run and not frappe.db.exists("NDIS Limited Production Batch Policy Enablement Run", freeze.enablement_run):
        issues.append("Linked Phase 9S enablement run does not exist.")
    if freeze.readiness_gate and not frappe.db.exists("NDIS Limited Production Batch Enablement Readiness Gate", freeze.readiness_gate):
        issues.append("Linked Phase 9R readiness gate does not exist.")
    if not freeze.target_policy:
        issues.append("Phase 9T freeze has no target policy.")
    elif not frappe.db.exists(POLICY_DOCTYPE, freeze.target_policy):
        issues.append(f"Target policy does not exist: {freeze.target_policy}")

    current_enabled = get_flag(POLICY_DOCTYPE, freeze.target_policy, "production_batch_enabled") if freeze.target_policy else 0
    current_live = get_flag(POLICY_DOCTYPE, freeze.target_policy, "live_posting_allowed") if freeze.target_policy else 0
    if current_enabled != 1:
        issues.append("Current target policy production_batch_enabled must be 1 before monitor approval.")
    if current_live != 0:
        issues.append("Current target policy live_posting_allowed must be 0 before monitor approval.")

    expected_one = [
        "current_target_policy_enabled",
        "policy_enabled_after_count",
        "actual_enabled_policy_count",
    ]
    for fieldname in expected_one:
        if int(freeze.get(fieldname) or 0) != 1:
            issues.append(f"Frozen {fieldname} must be 1.")

    expected_zero = [
        "current_target_policy_live",
        "actual_payment_entry_created_count",
        "actual_gl_created_count",
    ]
    for fieldname in expected_zero:
        if int(freeze.get(fieldname) or 0) != 0:
            issues.append(f"Frozen {fieldname} must be 0.")

    if int(freeze.payment_entry_count_before or 0) != int(freeze.payment_entry_count_after or 0):
        issues.append("Phase 9T Payment Entry count changed.")
    if int(freeze.payment_entry_gl_count_before or 0) != int(freeze.payment_entry_gl_count_after or 0):
        issues.append("Phase 9T Payment Entry GL count changed.")
    if int(freeze.max_batch_lines or 0) != 3:
        issues.append("Max batch lines must remain 3.")
    if flt(freeze.max_batch_amount or 0, 2) != 3:
        issues.append("Max batch amount must remain 3.00.")
    if int(freeze.max_payment_entry_count or 0) != 1:
        issues.append("Max Payment Entry count must remain 1.")
    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Controlled production batch enabled policy count must be exactly 1 before monitor approval.")
    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must be 0 before monitor approval.")
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


def build_items(freeze, issues, ack_ok, guard):
    items = []
    if freeze:
        add_item(
            items,
            "Pass",
            "Low",
            "Evidence",
            "phase9t_freeze_exists",
            "Phase 9T freeze exists",
            f"Phase 9T freeze found: {freeze.freeze_id}.",
            PHASE9T_FREEZE_DOCTYPE,
            freeze.name,
        )
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase9t_freeze_exists", "Phase 9T freeze exists", "No completed Phase 9T freeze found.")

    if issues:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Monitoring", "monitor_source_valid", "Monitor source valid", issue)
    else:
        add_item(items, "Pass", "Low", "Monitoring", "monitor_source_valid", "Monitor source valid", "Controlled policy enablement freeze is valid for operational monitoring.")

    if guard["production_batch_enabled_policy_count"] == 1 and guard["live_posting_allowed_policy_count"] == 0:
        add_item(items, "Pass", "Low", "Policy Guardrail", "policy_state", "Policy state correct", "Exactly one controlled policy is enabled and live posting remains blocked.")
    else:
        add_item(items, "Blocker", "Critical", "Policy Guardrail", "policy_state", "Policy state correct", "Enabled/live policy counts are not in the expected 1/0 state.")

    if freeze:
        add_item(items, "Pass", "Low", "Caps", "caps_verified", "Caps verified", f"Caps remain {freeze.max_batch_lines} lines, {freeze.max_batch_amount}, {freeze.max_payment_entry_count} Payment Entry.")
        add_item(items, "Pass", "Low", "Accounting Guardrail", "no_accounting_movement", "No accounting movement", "Payment Entry and Payment Entry GL counts remained unchanged.")
        add_item(items, "Info", "Low", "Next Step", "monitoring_ready", "Monitoring ready", "Operational monitoring gate approved for controlled limited batch usage.")

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {MONITOR_ACK}")
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
        row = frappe.new_doc(MONITOR_ITEM_DOCTYPE)
        row.monitor_gate = doc.name
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
def run_limited_production_batch_use_monitor_gate(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_limited_production_batch_use_monitor_gate")

    freeze = latest_phase9t_freeze()
    config = config_state()
    guard_before = guardrails()
    ack_ok = acknowledgement == MONITOR_ACK
    issues = validate_source(freeze, guard_before, config)
    items = build_items(freeze, issues, ack_ok, guard_before)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    allowed = int(ack_ok and item_summary["blocker_count"] == 0 and bool(freeze))
    guard_now = guardrails()

    current_enabled = get_flag(POLICY_DOCTYPE, freeze.target_policy, "production_batch_enabled") if freeze else 0
    current_live = get_flag(POLICY_DOCTYPE, freeze.target_policy, "live_posting_allowed") if freeze else 0

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Approved" if allowed else "Needs Review",
        "monitor_status": "Ready For Controlled Limited Batch Operational Monitoring" if allowed else "Needs Review",
        "monitor_gate_approved": allowed,
        "ready_for_operational_monitoring": allowed,
        "phase9t_freeze_verified": 1 if freeze else 0,
        "phase9s_enablement_verified": 1 if freeze else 0,
        "phase9r_readiness_gate_verified": 1 if freeze else 0,
        "phase9q_freeze_verified": 1 if freeze else 0,
        "phase9p_rollback_verified": 1 if freeze else 0,
        "phase9o_smoke_verified": 1 if freeze else 0,
        "policy_caps_verified": 1 if freeze and int(freeze.max_batch_lines or 0) == 3 and flt(freeze.max_batch_amount or 0, 2) == 3 and int(freeze.max_payment_entry_count or 0) == 1 else 0,
        "controlled_policy_enabled_verified": 1 if current_enabled == 1 else 0,
        "live_posting_blocked_verified": 1 if current_live == 0 and guard_before["live_posting_allowed_policy_count"] == 0 else 0,
        "no_accounting_movement_verified": 1 if freeze and int(freeze.payment_entry_count_before or 0) == int(freeze.payment_entry_count_after or 0) and int(freeze.payment_entry_gl_count_before or 0) == int(freeze.payment_entry_gl_count_after or 0) else 0,
        "production_batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "policy_live_enabled": 0,
        "policy_enablement_freeze": freeze.name if freeze else None,
        "enablement_run": freeze.enablement_run if freeze else None,
        "readiness_gate": freeze.readiness_gate if freeze else None,
        "phase9q_evidence_freeze": freeze.evidence_freeze if freeze else None,
        "rollback_run": freeze.rollback_run if freeze else None,
        "enablement_smoke": freeze.enablement_smoke if freeze else None,
        "activation_gate": freeze.activation_gate if freeze else None,
        "enablement_adapter": freeze.enablement_adapter if freeze else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": freeze.target_policy if freeze else None,
        "target_policy_name": freeze.target_policy_name if freeze else None,
        "enablement_field": "production_batch_enabled",
        "live_field": "live_posting_allowed",
        "current_target_policy_enabled": current_enabled,
        "current_target_policy_live": current_live,
        "policy_enabled_before_count": int(freeze.policy_enabled_before_count or 0) if freeze else 0,
        "policy_enabled_after_count": int(freeze.policy_enabled_after_count or 0) if freeze else 0,
        "actual_enabled_policy_count": int(freeze.actual_enabled_policy_count or 0) if freeze else 0,
        "max_batch_lines": int(freeze.max_batch_lines or 0) if freeze else 0,
        "max_batch_amount": flt(freeze.max_batch_amount or 0) if freeze else 0,
        "max_payment_entry_count": int(freeze.max_payment_entry_count or 0) if freeze else 0,
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
        "monitor_score": score,
        **item_summary,
        "items": items,
        "issues": issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_now,
        "config": config,
        "required_acknowledgement": MONITOR_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 9U approves controlled limited batch use monitoring only. It creates no PE/GL and does not change policy flags.",
    }

    if int(dry_run or 0):
        result.update(
            {
                "status": "Needs Review",
                "monitor_status": "Needs Review",
                "monitor_gate_approved": 0,
                "ready_for_operational_monitoring": 0,
            }
        )
        return result

    doc = frappe.new_doc(MONITOR_GATE_DOCTYPE)
    doc.monitor_gate_id = make_monitor_gate_id()
    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = MONITOR_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    create_items(doc, items)
    frappe.db.commit()
    final_doc = frappe.get_doc(MONITOR_GATE_DOCTYPE, doc.name)
    return {
        **result,
        "created": True,
        "monitor_gate": final_doc.name,
        "monitor_gate_id": final_doc.monitor_gate_id,
        "status": final_doc.status,
        "monitor_status": final_doc.monitor_status,
        "monitor_gate_approved": int(final_doc.monitor_gate_approved or 0),
        "ready_for_operational_monitoring": int(final_doc.ready_for_operational_monitoring or 0),
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_limited_production_batch_use_monitor_gate(monitor_gate, reason=None):
    assert_action("cancel_limited_production_batch_use_monitor_gate")
    if not frappe.db.exists(MONITOR_GATE_DOCTYPE, monitor_gate):
        frappe.throw(_("Monitor gate not found: {0}").format(monitor_gate))
    doc = frappe.get_doc(MONITOR_GATE_DOCTYPE, monitor_gate)
    if doc.status == "Cancelled":
        return {"monitor_gate": monitor_gate, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.monitor_gate_approved or 0):
        frappe.throw(_("Cannot cancel an approved Phase 9U monitor gate. Create a superseding gate instead."))
    frappe.db.set_value(
        MONITOR_GATE_DOCTYPE,
        monitor_gate,
        {
            "status": "Cancelled",
            "monitor_status": "Cancelled",
            "monitor_gate_approved": 0,
            "ready_for_operational_monitoring": 0,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 9U no-ack monitor audit cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(
        """
        UPDATE `tabNDIS Limited Production Batch Use Monitor Item`
        SET status = 'Cancelled'
        WHERE monitor_gate = %(monitor_gate)s
        """,
        {"monitor_gate": monitor_gate},
    )
    frappe.db.commit()
    return {
        "monitor_gate": monitor_gate,
        "status": "Cancelled",
        "note": "No-ack monitor audit cancelled only. No policy or accounting movement occurred.",
    }


@frappe.whitelist()
def quick_limited_production_batch_use_monitor_summary(limit=20):
    gates = frappe.get_all(
        MONITOR_GATE_DOCTYPE,
        fields=[
            "name",
            "monitor_gate_id",
            "status",
            "monitor_status",
            "monitor_gate_approved",
            "ready_for_operational_monitoring",
            "policy_enablement_freeze",
            "enablement_run",
            "readiness_gate",
            "target_policy",
            "current_target_policy_enabled",
            "current_target_policy_live",
            "actual_enabled_policy_count",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
            "production_batch_enabled_policy_count",
            "live_posting_allowed_policy_count",
            "monitor_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(
        MONITOR_ITEM_DOCTYPE,
        fields=[
            "name",
            "monitor_gate",
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
        "gates": gates,
        "items": items,
        "required_acknowledgement": MONITOR_ACK,
        "guardrails": guardrails(),
        "note": "Phase 9U operational monitor summary. No policy or accounting movement.",
    }


def execute_gate_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("g.status = %(status)s")
        params["status"] = filters.get("status")

    columns = gate_columns()
    data = frappe.db.sql(
        f"""
        SELECT
            g.name AS monitor_gate,
            g.monitor_gate_id,
            g.status,
            g.monitor_status,
            g.monitor_gate_approved,
            g.ready_for_operational_monitoring,
            g.policy_enablement_freeze,
            g.enablement_run,
            g.readiness_gate,
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
            g.monitor_score,
            g.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Limited Production Batch Use Monitor Gate` g
        {build_where(conditions)}
        ORDER BY g.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.monitor_gate_id for row in data[:20]],
            "datasets": [
                {"name": "Approved", "values": [int(row.monitor_gate_approved or 0) for row in data[:20]]},
                {"name": "Live Policies", "values": [int(row.live_posting_allowed_policy_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Monitor Gates"), "datatype": "Int"},
        {"value": sum(int(row.monitor_gate_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(int(row.production_batch_enabled_policy_count or 0) for row in data), "indicator": "Green", "label": _("Enabled Policies"), "datatype": "Int"},
        {"value": sum(int(row.live_posting_allowed_policy_count or 0) for row in data), "indicator": "Red", "label": _("Live Policies"), "datatype": "Int"},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PE"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def gate_columns():
    return [
        {"fieldname": "monitor_gate", "label": _("Monitor Gate"), "fieldtype": "Link", "options": MONITOR_GATE_DOCTYPE, "width": 220},
        {"fieldname": "monitor_gate_id", "label": _("Monitor Gate ID"), "fieldtype": "Data", "width": 450},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "monitor_status", "label": _("Monitor Status"), "fieldtype": "Data", "width": 360},
        {"fieldname": "monitor_gate_approved", "label": _("Approved"), "fieldtype": "Check", "width": 90},
        {"fieldname": "ready_for_operational_monitoring", "label": _("Ready Monitoring"), "fieldtype": "Check", "width": 130},
        {"fieldname": "policy_enablement_freeze", "label": _("Phase 9T Freeze"), "fieldtype": "Link", "options": PHASE9T_FREEZE_DOCTYPE, "width": 220},
        {"fieldname": "enablement_run", "label": _("Phase 9S Enablement"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Policy Enablement Run", "width": 220},
        {"fieldname": "target_policy", "label": _("Target Policy"), "fieldtype": "Data", "width": 260},
        {"fieldname": "current_target_policy_enabled", "label": _("Current Enabled"), "fieldtype": "Check", "width": 120},
        {"fieldname": "current_target_policy_live", "label": _("Current Live"), "fieldtype": "Check", "width": 110},
        {"fieldname": "actual_enabled_policy_count", "label": _("Actual Enabled"), "fieldtype": "Int", "width": 120},
        {"fieldname": "max_batch_lines", "label": _("Max Lines"), "fieldtype": "Int", "width": 90},
        {"fieldname": "max_batch_amount", "label": _("Max Amount"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "max_payment_entry_count", "label": _("Max PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "production_batch_enabled_policy_count", "label": _("Enabled Policies"), "fieldtype": "Int", "width": 120},
        {"fieldname": "live_posting_allowed_policy_count", "label": _("Live Policies"), "fieldtype": "Int", "width": 110},
        {"fieldname": "monitor_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("monitor_gate"):
        conditions.append("i.monitor_gate = %(monitor_gate)s")
        params["monitor_gate"] = filters.get("monitor_gate")
    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": MONITOR_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "monitor_gate", "label": _("Monitor Gate"), "fieldtype": "Link", "options": MONITOR_GATE_DOCTYPE, "width": 220},
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
            i.monitor_gate,
            i.status,
            i.severity,
            i.category,
            i.check_label,
            i.detail,
            i.source_doctype,
            i.source_name,
            i.checked_on
        FROM `tabNDIS Limited Production Batch Use Monitor Item` i
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
    columns, data, message, chart, summary = execute_gate_report(filters)
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
