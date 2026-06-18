import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


READINESS_ACK = "I_CONFIRM_PHASE10S_APPROVE_GOVERNED_CONTROLLED_LIMITED_OPERATIONS_READINESS_NO_POSTING"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
GOV_DOCTYPE = "NDIS Runtime Watch Governance Closeout"
GOV_ITEM_DOCTYPE = "NDIS Runtime Watch Governance Closeout Item"
READINESS_DOCTYPE = "NDIS Governed Limited Ops Readiness"
READINESS_ITEM_DOCTYPE = "NDIS Governed Limited Ops Readiness Item"


def make_readiness_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-GOVERNED-LIMITED-OPS-READINESS-{timestamp}-{frappe.generate_hash(length=5).upper()}"


def safe_json(value):
    try:
        return json.dumps(value, indent=2, default=str)
    except Exception:
        return str(value)


def currency():
    return frappe.defaults.get_global_default("currency") or "AUD"


def count_dt(doctype, filters=None):
    if not frappe.db.exists("DocType", doctype):
        return 0
    return frappe.db.count(doctype, filters or {})


def has_column(doctype, fieldname):
    try:
        return bool(frappe.db.has_column(doctype, fieldname))
    except Exception:
        return False


def get_value_if_has(doctype, name, fieldname, default=None):
    if not name or not frappe.db.exists(doctype, name) or not has_column(doctype, fieldname):
        return default
    value = frappe.db.get_value(doctype, name, fieldname)
    return default if value is None else value


def get_flag(doctype, name, fieldname, default=0):
    return int(get_value_if_has(doctype, name, fieldname, default) or 0)


def production_batch_enabled_policy_count():
    if not has_column(POLICY_DOCTYPE, "production_batch_enabled"):
        return 0
    return count_dt(POLICY_DOCTYPE, {"production_batch_enabled": 1})


def live_posting_allowed_policy_count():
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


def latest_governance_closeout():
    rows = frappe.get_all(
        GOV_DOCTYPE,
        filters={
            "status": "Governance Closeout Approved",
            "governance_status": "Controlled Limited Runtime Watch Governance Closed",
            "governance_closeout_approved": 1,
            "runtime_watch_governance_closed": 1,
            "ready_for_governed_controlled_limited_operations": 1,
            "runtime_watch_control_loop_closed": 1,
            "violation_simulation_governance_verified": 1,
            "frozen_evidence_verified": 1,
            "no_new_accounting_movement_verified": 1,
            "policy_state_preserved_verified": 1,
            "policy_mutation_performed": 0,
            "actual_policy_mutation_count": 0,
            "all_runtime_violations_blocked_verified": 1,
            "phase10q_freeze_verified": 1,
            "phase10p_simulation_verified": 1,
            "phase10o_runtime_watch_verified": 1,
            "phase10n_baseline_verified": 1,
            "phase10m_closeout_verified": 1,
            "controlled_policy_enabled_verified": 1,
            "live_posting_blocked_verified": 1,
            "target_policy_enabled_after": 1,
            "target_policy_live_after": 0,
            "max_batch_line_count": 3,
            "max_payment_entry_count": 1,
            "live_posting_allowed": 0,
            "journal_entry_side_effect_allowed": 0,
            "purchase_invoice_side_effect_allowed": 0,
            "violation_simulation_count": 6,
            "blocked_violation_count": 6,
            "failed_violation_count": 0,
            "actual_payment_entry_created_count": 0,
            "actual_payment_entry_cancelled_count": 0,
            "actual_gl_created_count": 0,
            "submitted_journal_entry_count_today": 0,
            "purchase_invoice_count_today": 0,
        },
        fields=[
            "name",
            "governance_id",
            "freeze",
            "simulation",
            "runtime_watch",
            "baseline",
            "closeout",
            "monitoring_register",
            "policy_decision",
            "target_policy_doctype",
            "target_policy",
            "target_policy_name",
            "target_policy_enabled_after",
            "target_policy_live_after",
            "production_batch_enabled_policy_count_after",
            "live_posting_allowed_policy_count_after",
            "max_batch_line_count",
            "max_batch_amount",
            "max_payment_entry_count",
            "live_posting_allowed",
            "journal_entry_side_effect_allowed",
            "purchase_invoice_side_effect_allowed",
            "violation_simulation_count",
            "blocked_violation_count",
            "failed_violation_count",
            "payment_entry_count_after",
            "payment_entry_gl_count_after",
            "governance_score",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_readiness(governance_closeout):
    rows = frappe.get_all(
        READINESS_DOCTYPE,
        filters={"governance_closeout": governance_closeout, "status": "Readiness Approved", "readiness_approved": 1},
        fields=["name", "readiness_id"],
        limit=1,
    )
    return rows[0] if rows else None


def governance_items(governance_closeout):
    if not governance_closeout:
        return []
    return frappe.get_all(
        GOV_ITEM_DOCTYPE,
        filters={"governance_closeout": governance_closeout},
        fields=["name", "status", "severity", "category", "check_key", "check_label", "detail", "source_doctype", "source_name"],
        order_by="creation asc",
    )


def validate_source(governance, source_items, guard, policy_enabled, policy_live, config):
    issues = []
    if not governance:
        return ["No approved Phase 10R runtime watch governance closeout found."]

    existing = existing_readiness(governance.name)
    if existing:
        issues.append(f"Phase 10S readiness already exists for this governance closeout: {existing.readiness_id}")

    required_links = {
        "governance_closeout": (GOV_DOCTYPE, governance.name),
        "freeze": ("NDIS Runtime Watch Violation Sim Freeze", governance.freeze),
        "simulation": ("NDIS Runtime Watch Violation Sim", governance.simulation),
        "runtime_watch": ("NDIS Controlled Limited Ops Runtime Watch", governance.runtime_watch),
        "baseline": ("NDIS Controlled Limited Ops Baseline", governance.baseline),
        "closeout": ("NDIS Limited Operation Closeout Gate", governance.closeout),
        "monitoring_register": ("NDIS Controlled Limited Operations Monitoring Register", governance.monitoring_register),
        "target_policy": (POLICY_DOCTYPE, governance.target_policy),
    }
    for label, (doctype, name) in required_links.items():
        if not name or not frappe.db.exists(doctype, name):
            issues.append(f"Missing or invalid evidence link: {label}")

    if len(source_items) < 8:
        issues.append("Phase 10R governance closeout should contain governance item rows.")
    if [row for row in source_items if row.status == "Blocker"]:
        issues.append("Phase 10R governance item blocker rows exist.")
    if [row for row in source_items if row.status == "Warning"]:
        issues.append("Phase 10R governance item warning rows exist.")
    if int(governance.violation_simulation_count or 0) != 6:
        issues.append("Governed violation simulation count must be 6.")
    if int(governance.blocked_violation_count or 0) != 6:
        issues.append("Governed blocked violation count must be 6.")
    if int(governance.failed_violation_count or 0) != 0:
        issues.append("Governed failed violation count must be 0.")
    if int(governance.max_batch_line_count or 0) != 3:
        issues.append("Governed max batch line count must be 3.")
    if flt(governance.max_batch_amount or 0, 2) != 3:
        issues.append("Governed max batch amount must be 3.00.")
    if int(governance.max_payment_entry_count or 0) != 1:
        issues.append("Governed max Payment Entry count must be 1.")
    if int(governance.live_posting_allowed or 0) != 0:
        issues.append("Governed live posting must remain blocked.")
    if int(governance.journal_entry_side_effect_allowed or 0) != 0:
        issues.append("Governed Journal Entry side effect must remain blocked.")
    if int(governance.purchase_invoice_side_effect_allowed or 0) != 0:
        issues.append("Governed Purchase Invoice side effect must remain blocked.")
    if policy_enabled != 1:
        issues.append("Target policy production_batch_enabled must be 1 before Phase 10S. Phase 10S must not repair this.")
    if policy_live != 0:
        issues.append("Target policy live_posting_allowed must be 0 before Phase 10S. Phase 10S must not repair this.")
    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must remain enabled.")
    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must remain 0.")
    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry count today must remain 0.")
    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice count today must remain 0.")
    if int(config["production_mode"]) != 0:
        issues.append("Production mode config must remain 0.")
    if int(config["live_pe_enabled"]) != 0:
        issues.append("Live Payment Entry posting config must remain 0.")
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


def build_readiness_items(governance, source_items, issues, ack_ok):
    items = []
    if governance:
        add_item(items, "Pass", "Low", "Evidence", "phase10r_governance_closeout_exists", "Phase 10R governance closeout exists", f"Governance closeout found: {governance.governance_id}.", GOV_DOCTYPE, governance.name)
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase10r_governance_closeout_exists", "Phase 10R governance closeout exists", "No approved Phase 10R governance closeout found.")

    if issues:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Readiness Source", "readiness_source_valid", "Readiness source valid", issue)
    else:
        add_item(items, "Pass", "Low", "Readiness Source", "readiness_source_valid", "Readiness source valid", "Phase 10R governance closeout is valid for governed readiness.")

    checks = [
        ("phase10q_freeze_verified", "Phase 10Q freeze verified", governance.freeze if governance else None, "NDIS Runtime Watch Violation Sim Freeze"),
        ("phase10p_simulation_verified", "Phase 10P simulation verified", governance.simulation if governance else None, "NDIS Runtime Watch Violation Sim"),
        ("phase10o_runtime_watch_verified", "Phase 10O runtime watch verified", governance.runtime_watch if governance else None, "NDIS Controlled Limited Ops Runtime Watch"),
        ("phase10n_baseline_verified", "Phase 10N baseline verified", governance.baseline if governance else None, "NDIS Controlled Limited Ops Baseline"),
        ("phase10m_closeout_verified", "Phase 10M closeout verified", governance.closeout if governance else None, "NDIS Limited Operation Closeout Gate"),
        ("locked_runtime_limits_verified", "Locked runtime limits verified", "3 lines / 3.00 / 1 PE / live blocked / JE blocked / PI blocked", None),
        ("governed_ready", "Governed controlled limited operations ready", "Readiness approved for pre-execution gate only; no posting.", None),
    ]
    for key, label, detail, source_doctype in checks:
        add_item(items, "Pass", "High", "Readiness Chain", key, label, str(detail), source_doctype, detail if source_doctype else None)

    for row in source_items:
        if row.category in ["Governance Chain", "Frozen Violation"]:
            add_item(items, "Pass", "Low", "Inherited Governance Evidence", row.check_key, row.check_label, row.detail, row.source_doctype, row.source_name)

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {READINESS_ACK}")
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
        row = frappe.new_doc(READINESS_ITEM_DOCTYPE)
        row.readiness = doc.name
        for fieldname in ["status", "severity", "category", "check_key", "check_label", "detail", "source_doctype", "source_name"]:
            setattr(row, fieldname, item.get(fieldname))
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


def build_evidence(governance, guard_before, guard_after, policy_enabled_before, policy_enabled_after, policy_live_before, policy_live_after):
    return {
        "governance_closeout": governance.name if governance else None,
        "freeze": governance.freeze if governance else None,
        "simulation": governance.simulation if governance else None,
        "runtime_watch": governance.runtime_watch if governance else None,
        "baseline": governance.baseline if governance else None,
        "closeout": governance.closeout if governance else None,
        "monitoring_register": governance.monitoring_register if governance else None,
        "policy_decision": governance.policy_decision if governance else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": governance.target_policy if governance else None,
        "target_policy_name": governance.target_policy_name if governance else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_before": policy_live_before,
        "target_policy_live_after": policy_live_after,
        "production_batch_enabled_policy_count_before": guard_before["production_batch_enabled_policy_count"],
        "production_batch_enabled_policy_count_after": guard_after["production_batch_enabled_policy_count"],
        "live_posting_allowed_policy_count_before": guard_before["live_posting_allowed_policy_count"],
        "live_posting_allowed_policy_count_after": guard_after["live_posting_allowed_policy_count"],
        "max_batch_line_count": int(governance.max_batch_line_count or 0) if governance else 0,
        "max_batch_amount": flt(governance.max_batch_amount or 0, 2) if governance else 0,
        "max_payment_entry_count": int(governance.max_payment_entry_count or 0) if governance else 0,
        "live_posting_allowed": int(governance.live_posting_allowed or 0) if governance else 0,
        "journal_entry_side_effect_allowed": int(governance.journal_entry_side_effect_allowed or 0) if governance else 0,
        "purchase_invoice_side_effect_allowed": int(governance.purchase_invoice_side_effect_allowed or 0) if governance else 0,
        "violation_simulation_count": int(governance.violation_simulation_count or 0) if governance else 0,
        "blocked_violation_count": int(governance.blocked_violation_count or 0) if governance else 0,
        "failed_violation_count": int(governance.failed_violation_count or 0) if governance else 0,
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guard_after["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
        "actual_payment_entry_created_count": 0,
        "actual_payment_entry_cancelled_count": 0,
        "actual_gl_created_count": 0,
        "submitted_journal_entry_count_today": guard_after["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_after["purchase_invoice_count_today"],
    }


@frappe.whitelist()
def run_governed_limited_ops_readiness(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_governed_limited_ops_readiness")
    governance = latest_governance_closeout()
    source_items = governance_items(governance.name) if governance else []
    guard_before = guardrails()
    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }
    ack_ok = acknowledgement == READINESS_ACK
    policy_enabled_before = get_flag(POLICY_DOCTYPE, governance.target_policy, "production_batch_enabled") if governance else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, governance.target_policy, "live_posting_allowed") if governance else 0
    guard_after = guardrails()
    policy_enabled_after = get_flag(POLICY_DOCTYPE, governance.target_policy, "production_batch_enabled") if governance else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, governance.target_policy, "live_posting_allowed") if governance else 0

    issues = validate_source(governance, source_items, guard_before, policy_enabled_before, policy_live_before, config)
    no_new_movement = int(
        guard_before["payment_entry_count"] == guard_after["payment_entry_count"]
        and guard_before["payment_entry_gl_count"] == guard_after["payment_entry_gl_count"]
        and guard_before["submitted_journal_entry_count_today"] == guard_after["submitted_journal_entry_count_today"]
        and guard_before["purchase_invoice_count_today"] == guard_after["purchase_invoice_count_today"]
    )
    policy_preserved = int(
        policy_enabled_before == policy_enabled_after == 1
        and policy_live_before == policy_live_after == 0
        and guard_before["production_batch_enabled_policy_count"] == guard_after["production_batch_enabled_policy_count"] == 1
        and guard_before["live_posting_allowed_policy_count"] == guard_after["live_posting_allowed_policy_count"] == 0
    )
    if not no_new_movement:
        issues.append("Accounting movement changed while preparing Phase 10S readiness evidence.")

    evidence = build_evidence(governance, guard_before, guard_after, policy_enabled_before, policy_enabled_after, policy_live_before, policy_live_after)
    locked_limits_verified = int(
        evidence["max_batch_line_count"] == 3
        and flt(evidence["max_batch_amount"], 2) == 3
        and evidence["max_payment_entry_count"] == 1
        and evidence["live_posting_allowed"] == 0
        and evidence["journal_entry_side_effect_allowed"] == 0
        and evidence["purchase_invoice_side_effect_allowed"] == 0
    )
    all_blocked_verified = int(evidence["violation_simulation_count"] == 6 and evidence["blocked_violation_count"] == 6 and evidence["failed_violation_count"] == 0)
    items = build_readiness_items(governance, source_items, issues, ack_ok)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    allowed = int(ack_ok and item_summary["blocker_count"] == 0 and bool(governance) and locked_limits_verified and all_blocked_verified and no_new_movement and policy_preserved)
    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Readiness Approved" if allowed else "Needs Review",
        "readiness_status": "Governed Controlled Limited Operations Ready" if allowed else "Needs Review",
        "readiness_approved": allowed,
        "governed_controlled_limited_operations_ready": allowed,
        "ready_for_governed_limited_operation_pre_execution_gate": allowed,
        "runtime_watch_governance_closeout_verified": 1 if governance else 0,
        "governed_limits_locked": locked_limits_verified,
        "locked_runtime_limits_verified": locked_limits_verified,
        "live_posting_remains_blocked": int(evidence["live_posting_allowed"] == 0),
        "journal_entry_side_effect_remains_blocked": int(evidence["journal_entry_side_effect_allowed"] == 0),
        "purchase_invoice_side_effect_remains_blocked": int(evidence["purchase_invoice_side_effect_allowed"] == 0),
        "no_new_accounting_movement_verified": no_new_movement,
        "policy_state_preserved_verified": policy_preserved,
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": 0,
        "phase10r_governance_closeout_verified": 1 if governance else 0,
        "phase10q_freeze_verified": 1 if governance else 0,
        "phase10p_simulation_verified": 1 if governance else 0,
        "phase10o_runtime_watch_verified": 1 if governance else 0,
        "phase10n_baseline_verified": 1 if governance else 0,
        "phase10m_closeout_verified": 1 if governance else 0,
        "controlled_policy_enabled_verified": int(policy_enabled_after == 1),
        "live_posting_blocked_verified": int(policy_live_after == 0),
        "all_runtime_violations_blocked_verified": all_blocked_verified,
        **evidence,
        "readiness_score": score,
        **item_summary,
        "items": items,
        "source_items": source_items,
        "issues": issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "required_acknowledgement": READINESS_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 10S approves governed readiness only. No accounting movement or policy mutation is performed.",
    }
    if int(dry_run or 0):
        result.update({"status": "Needs Review", "readiness_status": "Needs Review", "readiness_approved": 0, "governed_controlled_limited_operations_ready": 0, "ready_for_governed_limited_operation_pre_execution_gate": 0})
        return result

    doc = frappe.new_doc(READINESS_DOCTYPE)
    doc.readiness_id = make_readiness_id()
    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = READINESS_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.evidence_json = safe_json({"evidence": evidence, "source_items": source_items, "guardrails_before": guard_before, "guardrails_after": guard_after, "config": config})
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    create_items(doc, items)
    frappe.db.commit()
    return {**result, "created": True, "readiness": doc.name, "readiness_id": doc.readiness_id, "guardrails_after": guardrails()}


@frappe.whitelist()
def cancel_governed_limited_ops_readiness_audit(readiness, reason=None):
    assert_action("cancel_governed_limited_ops_readiness_audit")
    if not frappe.db.exists(READINESS_DOCTYPE, readiness):
        frappe.throw(_("Governed limited ops readiness audit not found: {0}").format(readiness))
    doc = frappe.get_doc(READINESS_DOCTYPE, readiness)
    if doc.status == "Cancelled":
        return {"readiness": readiness, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.readiness_approved or 0):
        frappe.throw(_("Cannot cancel an approved Phase 10S readiness record."))
    frappe.db.set_value(
        READINESS_DOCTYPE,
        readiness,
        {"status": "Cancelled", "readiness_status": "Cancelled", "cancelled_on": now_datetime(), "cancelled_by": frappe.session.user, "summary_json": reason or "Phase 10S no-ack readiness audit cancelled."},
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{READINESS_ITEM_DOCTYPE}` SET status = 'Cancelled' WHERE readiness = %(readiness)s", {"readiness": readiness})
    frappe.db.commit()
    return {"readiness": readiness, "status": "Cancelled", "note": "No-ack readiness audit cancelled only. No accounting or policy movement occurred."}


@frappe.whitelist()
def quick_governed_limited_ops_readiness_summary(limit=20):
    records = frappe.get_all(
        READINESS_DOCTYPE,
        fields=[
            "name",
            "readiness_id",
            "status",
            "readiness_status",
            "readiness_approved",
            "governed_controlled_limited_operations_ready",
            "ready_for_governed_limited_operation_pre_execution_gate",
            "governance_closeout",
            "runtime_watch",
            "baseline",
            "max_batch_line_count",
            "max_batch_amount",
            "max_payment_entry_count",
            "live_posting_allowed",
            "journal_entry_side_effect_allowed",
            "purchase_invoice_side_effect_allowed",
            "production_batch_enabled_policy_count_after",
            "live_posting_allowed_policy_count_after",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "submitted_journal_entry_count_today",
            "purchase_invoice_count_today",
            "readiness_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(READINESS_ITEM_DOCTYPE, fields=["name", "readiness", "status", "severity", "category", "check_key", "check_label", "detail", "source_doctype", "source_name"], order_by="creation desc", limit=int(limit or 20))
    return {"readiness_records": records, "items": items, "required_acknowledgement": READINESS_ACK, "guardrails": guardrails(), "note": "Phase 10S readiness summary. Approved record allows the next pre-execution gate only."}


def execute_readiness_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("r.status = %(status)s")
        params["status"] = filters.get("status")
    data = frappe.db.sql(
        f"""
        SELECT
            r.name AS readiness, r.readiness_id, r.status, r.readiness_status,
            r.readiness_approved, r.governed_controlled_limited_operations_ready,
            r.ready_for_governed_limited_operation_pre_execution_gate,
            r.governance_closeout, r.runtime_watch, r.baseline,
            r.max_batch_line_count, r.max_batch_amount, r.max_payment_entry_count,
            r.live_posting_allowed, r.journal_entry_side_effect_allowed,
            r.purchase_invoice_side_effect_allowed,
            r.production_batch_enabled_policy_count_after,
            r.live_posting_allowed_policy_count_after,
            r.payment_entry_count_before, r.payment_entry_count_after,
            r.payment_entry_gl_count_before, r.payment_entry_gl_count_after,
            r.submitted_journal_entry_count_today, r.purchase_invoice_count_today,
            r.readiness_score, r.checked_on, %(currency)s AS currency
        FROM `tab{READINESS_DOCTYPE}` r
        {build_where(conditions)}
        ORDER BY r.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {"data": {"labels": [row.readiness_id for row in data[:20]], "datasets": [{"name": "Approved", "values": [int(row.readiness_approved or 0) for row in data[:20]]}, {"name": "Ready", "values": [int(row.governed_controlled_limited_operations_ready or 0) for row in data[:20]]}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Readiness Records"), "datatype": "Int"},
        {"value": sum(int(row.readiness_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(int(row.governed_controlled_limited_operations_ready or 0) for row in data), "indicator": "Green", "label": _("Ready"), "datatype": "Int"},
        {"value": sum(int(row.live_posting_allowed or 0) for row in data), "indicator": "Red", "label": _("Live Allowed"), "datatype": "Int"},
    ]
    return readiness_columns(), data, None, chart, summary


def readiness_columns():
    return [
        {"fieldname": "readiness", "label": _("Readiness"), "fieldtype": "Link", "options": READINESS_DOCTYPE, "width": 220},
        {"fieldname": "readiness_id", "label": _("Readiness ID"), "fieldtype": "Data", "width": 390},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 140},
        {"fieldname": "readiness_status", "label": _("Readiness Status"), "fieldtype": "Data", "width": 330},
        {"fieldname": "readiness_approved", "label": _("Approved"), "fieldtype": "Check", "width": 90},
        {"fieldname": "governed_controlled_limited_operations_ready", "label": _("Ready"), "fieldtype": "Check", "width": 90},
        {"fieldname": "ready_for_governed_limited_operation_pre_execution_gate", "label": _("Ready Pre-Gate"), "fieldtype": "Check", "width": 120},
        {"fieldname": "governance_closeout", "label": _("Governance Closeout"), "fieldtype": "Link", "options": GOV_DOCTYPE, "width": 220},
        {"fieldname": "runtime_watch", "label": _("Runtime Watch"), "fieldtype": "Link", "options": "NDIS Controlled Limited Ops Runtime Watch", "width": 220},
        {"fieldname": "baseline", "label": _("Baseline"), "fieldtype": "Link", "options": "NDIS Controlled Limited Ops Baseline", "width": 220},
        {"fieldname": "max_batch_line_count", "label": _("Max Lines"), "fieldtype": "Int", "width": 90},
        {"fieldname": "max_batch_amount", "label": _("Max Amount"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "max_payment_entry_count", "label": _("Max PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "live_posting_allowed", "label": _("Live Allowed"), "fieldtype": "Check", "width": 95},
        {"fieldname": "journal_entry_side_effect_allowed", "label": _("JE Allowed"), "fieldtype": "Check", "width": 95},
        {"fieldname": "purchase_invoice_side_effect_allowed", "label": _("PI Allowed"), "fieldtype": "Check", "width": 95},
        {"fieldname": "production_batch_enabled_policy_count_after", "label": _("Enabled Policies"), "fieldtype": "Int", "width": 125},
        {"fieldname": "live_posting_allowed_policy_count_after", "label": _("Live Policies"), "fieldtype": "Int", "width": 105},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 110},
        {"fieldname": "submitted_journal_entry_count_today", "label": _("JE Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "purchase_invoice_count_today", "label": _("PI Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "readiness_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("readiness"):
        conditions.append("i.readiness = %(readiness)s")
        params["readiness"] = filters.get("readiness")
    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")
    data = frappe.db.sql(
        f"""
        SELECT i.name AS item, i.readiness, i.status, i.severity, i.category,
               i.check_key, i.check_label, i.detail, i.source_doctype,
               i.source_name, i.checked_on
        FROM `tab{READINESS_ITEM_DOCTYPE}` i
        {build_where(conditions)}
        ORDER BY CASE i.status WHEN 'Blocker' THEN 1 WHEN 'Warning' THEN 2 WHEN 'Pass' THEN 3 WHEN 'Info' THEN 4 ELSE 5 END, i.creation DESC
        """,
        params,
        as_dict=True,
    )
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": READINESS_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "readiness", "label": _("Readiness"), "fieldtype": "Link", "options": READINESS_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 200},
        {"fieldname": "check_key", "label": _("Check Key"), "fieldtype": "Data", "width": 220},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 330},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 650},
        {"fieldname": "source_doctype", "label": _("Source DocType"), "fieldtype": "Data", "width": 220},
        {"fieldname": "source_name", "label": _("Source Name"), "fieldtype": "Data", "width": 240},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]
    chart_map = {}
    for row in data:
        chart_map[row.status or "Info"] = chart_map.get(row.status or "Info", 0) + 1
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Items"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Pass"]), "indicator": "Green", "label": _("Pass"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Warning"]), "indicator": "Orange", "label": _("Warnings"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Blocker"]), "indicator": "Red", "label": _("Blockers"), "datatype": "Int"},
        {"value": len([row for row in data if row.category == "Readiness Chain"]), "indicator": "Green", "label": _("Readiness Chain"), "datatype": "Int"},
    ]
    return columns, data, None, {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Items", "values": list(chart_map.values())}]}, "type": "bar"}, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_readiness_report(filters)
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
