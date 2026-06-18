import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


GOV_ACK = "I_CONFIRM_PHASE10R_APPROVE_RUNTIME_WATCH_GOVERNANCE_CLOSEOUT_NO_POSTING"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
FREEZE_DOCTYPE = "NDIS Runtime Watch Violation Sim Freeze"
FREEZE_ITEM_DOCTYPE = "NDIS Runtime Watch Violation Sim Freeze Item"
GOV_DOCTYPE = "NDIS Runtime Watch Governance Closeout"
GOV_ITEM_DOCTYPE = "NDIS Runtime Watch Governance Closeout Item"


def make_governance_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-RUNTIME-WATCH-GOVERNANCE-CLOSEOUT-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_freeze():
    rows = frappe.get_all(
        FREEZE_DOCTYPE,
        filters={
            "status": "Frozen",
            "freeze_status": "Runtime Watch Violation Simulation Evidence Frozen",
            "freeze_completed": 1,
            "simulation_evidence_frozen": 1,
            "all_runtime_violations_blocked_verified": 1,
            "ready_for_runtime_watch_governance_closeout": 1,
            "simulation_only_verified": 1,
            "no_new_accounting_movement_verified": 1,
            "policy_state_preserved_verified": 1,
            "policy_mutation_performed": 0,
            "actual_policy_mutation_count": 0,
            "violation_simulation_count": 6,
            "blocked_violation_count": 6,
            "failed_violation_count": 0,
            "over_line_violation_blocked": 1,
            "over_amount_violation_blocked": 1,
            "over_payment_entry_violation_blocked": 1,
            "live_posting_violation_blocked": 1,
            "journal_entry_side_effect_violation_blocked": 1,
            "purchase_invoice_side_effect_violation_blocked": 1,
            "phase10p_simulation_verified": 1,
            "phase10o_runtime_watch_verified": 1,
            "phase10n_baseline_verified": 1,
            "phase10m_closeout_verified": 1,
            "controlled_policy_enabled_verified": 1,
            "live_posting_blocked_verified": 1,
            "target_policy_enabled_after": 1,
            "target_policy_live_after": 0,
            "actual_payment_entry_created_count": 0,
            "actual_payment_entry_cancelled_count": 0,
            "actual_gl_created_count": 0,
            "submitted_journal_entry_count_today": 0,
            "purchase_invoice_count_today": 0,
        },
        fields=[
            "name",
            "freeze_id",
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
            "over_line_violation_blocked",
            "over_amount_violation_blocked",
            "over_payment_entry_violation_blocked",
            "live_posting_violation_blocked",
            "journal_entry_side_effect_violation_blocked",
            "purchase_invoice_side_effect_violation_blocked",
            "payment_entry_count_after",
            "payment_entry_gl_count_after",
            "freeze_score",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_governance_closeout(freeze):
    rows = frappe.get_all(
        GOV_DOCTYPE,
        filters={"freeze": freeze, "status": "Governance Closeout Approved", "governance_closeout_approved": 1},
        fields=["name", "governance_id"],
        limit=1,
    )
    return rows[0] if rows else None


def freeze_items(freeze):
    if not freeze:
        return []
    return frappe.get_all(
        FREEZE_ITEM_DOCTYPE,
        filters={"freeze": freeze},
        fields=[
            "name",
            "status",
            "severity",
            "category",
            "check_key",
            "check_label",
            "detail",
            "source_doctype",
            "source_name",
        ],
        order_by="creation asc",
    )


def validate_source(freeze, source_items, guard, policy_enabled, policy_live, config):
    issues = []
    if not freeze:
        return ["No completed Phase 10Q runtime watch violation simulation freeze found."]

    existing = existing_governance_closeout(freeze.name)
    if existing:
        issues.append(f"Phase 10R governance closeout already exists for this freeze: {existing.governance_id}")

    required_links = {
        "freeze": (FREEZE_DOCTYPE, freeze.name),
        "simulation": ("NDIS Runtime Watch Violation Sim", freeze.simulation),
        "runtime_watch": ("NDIS Controlled Limited Ops Runtime Watch", freeze.runtime_watch),
        "baseline": ("NDIS Controlled Limited Ops Baseline", freeze.baseline),
        "closeout": ("NDIS Limited Operation Closeout Gate", freeze.closeout),
        "monitoring_register": ("NDIS Controlled Limited Operations Monitoring Register", freeze.monitoring_register),
        "target_policy": (POLICY_DOCTYPE, freeze.target_policy),
    }
    for label, (doctype, name) in required_links.items():
        if not name or not frappe.db.exists(doctype, name):
            issues.append(f"Missing or invalid evidence link: {label}")

    if len(source_items) < 8:
        issues.append("Phase 10Q freeze should contain source evidence rows, including six frozen violations.")
    if [row for row in source_items if row.status == "Blocker"]:
        issues.append("Phase 10Q freeze item blocker rows exist.")
    if [row for row in source_items if row.status == "Warning"]:
        issues.append("Phase 10Q freeze item warning rows exist.")

    if int(freeze.violation_simulation_count or 0) != 6:
        issues.append("Frozen violation simulation count must be 6.")
    if int(freeze.blocked_violation_count or 0) != 6:
        issues.append("Frozen blocked violation count must be 6.")
    if int(freeze.failed_violation_count or 0) != 0:
        issues.append("Frozen failed violation count must be 0.")
    for flag in [
        "over_line_violation_blocked",
        "over_amount_violation_blocked",
        "over_payment_entry_violation_blocked",
        "live_posting_violation_blocked",
        "journal_entry_side_effect_violation_blocked",
        "purchase_invoice_side_effect_violation_blocked",
    ]:
        if not int(getattr(freeze, flag) or 0):
            issues.append(f"Frozen blocked flag is not set: {flag}")

    if policy_enabled != 1:
        issues.append("Target policy production_batch_enabled must be 1 before Phase 10R. Phase 10R must not repair this.")
    if policy_live != 0:
        issues.append("Target policy live_posting_allowed must be 0 before Phase 10R. Phase 10R must not repair this.")
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


def build_governance_items(freeze, source_items, issues, ack_ok):
    items = []
    if freeze:
        add_item(items, "Pass", "Low", "Evidence", "phase10q_freeze_exists", "Phase 10Q freeze exists", f"Freeze found: {freeze.freeze_id}.", FREEZE_DOCTYPE, freeze.name)
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase10q_freeze_exists", "Phase 10Q freeze exists", "No completed Phase 10Q freeze found.")

    if issues:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Governance Source", "governance_source_valid", "Governance source valid", issue)
    else:
        add_item(items, "Pass", "Low", "Governance Source", "governance_source_valid", "Governance source valid", "Phase 10Q freeze evidence is valid for runtime watch governance closeout.")

    checks = [
        ("phase10p_simulation_verified", "Phase 10P simulation verified", freeze.simulation if freeze else None, "NDIS Runtime Watch Violation Sim"),
        ("phase10o_runtime_watch_verified", "Phase 10O runtime watch verified", freeze.runtime_watch if freeze else None, "NDIS Controlled Limited Ops Runtime Watch"),
        ("phase10n_baseline_verified", "Phase 10N baseline verified", freeze.baseline if freeze else None, "NDIS Controlled Limited Ops Baseline"),
        ("phase10m_closeout_verified", "Phase 10M closeout verified", freeze.closeout if freeze else None, "NDIS Limited Operation Closeout Gate"),
        ("runtime_watch_control_loop_closed", "Runtime watch control loop closed", freeze.name if freeze else None, FREEZE_DOCTYPE),
        ("violation_simulation_governance_verified", "Violation simulation governance verified", freeze.simulation if freeze else None, "NDIS Runtime Watch Violation Sim"),
    ]
    for key, label, source_name, source_doctype in checks:
        add_item(items, "Pass", "High", "Governance Chain", key, label, str(source_name), source_doctype, source_name)

    for row in source_items:
        if row.category == "Frozen Violation":
            add_item(items, "Pass", "High", "Frozen Violation", row.check_key, row.check_label, row.detail, row.source_doctype, row.source_name)

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {GOV_ACK}")
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
        row = frappe.new_doc(GOV_ITEM_DOCTYPE)
        row.governance_closeout = doc.name
        for fieldname in ["status", "severity", "category", "check_key", "check_label", "detail", "source_doctype", "source_name"]:
            setattr(row, fieldname, item.get(fieldname))
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


def build_evidence(freeze, guard_before, guard_after, policy_enabled_before, policy_enabled_after, policy_live_before, policy_live_after):
    return {
        "freeze": freeze.name if freeze else None,
        "simulation": freeze.simulation if freeze else None,
        "runtime_watch": freeze.runtime_watch if freeze else None,
        "baseline": freeze.baseline if freeze else None,
        "closeout": freeze.closeout if freeze else None,
        "monitoring_register": freeze.monitoring_register if freeze else None,
        "policy_decision": freeze.policy_decision if freeze else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": freeze.target_policy if freeze else None,
        "target_policy_name": freeze.target_policy_name if freeze else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_before": policy_live_before,
        "target_policy_live_after": policy_live_after,
        "production_batch_enabled_policy_count_before": guard_before["production_batch_enabled_policy_count"],
        "production_batch_enabled_policy_count_after": guard_after["production_batch_enabled_policy_count"],
        "live_posting_allowed_policy_count_before": guard_before["live_posting_allowed_policy_count"],
        "live_posting_allowed_policy_count_after": guard_after["live_posting_allowed_policy_count"],
        "max_batch_line_count": int(freeze.max_batch_line_count or 0) if freeze else 0,
        "max_batch_amount": flt(freeze.max_batch_amount or 0, 2) if freeze else 0,
        "max_payment_entry_count": int(freeze.max_payment_entry_count or 0) if freeze else 0,
        "live_posting_allowed": int(freeze.live_posting_allowed or 0) if freeze else 0,
        "journal_entry_side_effect_allowed": int(freeze.journal_entry_side_effect_allowed or 0) if freeze else 0,
        "purchase_invoice_side_effect_allowed": int(freeze.purchase_invoice_side_effect_allowed or 0) if freeze else 0,
        "violation_simulation_count": int(freeze.violation_simulation_count or 0) if freeze else 0,
        "blocked_violation_count": int(freeze.blocked_violation_count or 0) if freeze else 0,
        "failed_violation_count": int(freeze.failed_violation_count or 0) if freeze else 0,
        "over_line_violation_blocked": int(freeze.over_line_violation_blocked or 0) if freeze else 0,
        "over_amount_violation_blocked": int(freeze.over_amount_violation_blocked or 0) if freeze else 0,
        "over_payment_entry_violation_blocked": int(freeze.over_payment_entry_violation_blocked or 0) if freeze else 0,
        "live_posting_violation_blocked": int(freeze.live_posting_violation_blocked or 0) if freeze else 0,
        "journal_entry_side_effect_violation_blocked": int(freeze.journal_entry_side_effect_violation_blocked or 0) if freeze else 0,
        "purchase_invoice_side_effect_violation_blocked": int(freeze.purchase_invoice_side_effect_violation_blocked or 0) if freeze else 0,
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
def run_runtime_watch_governance_closeout(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_runtime_watch_governance_closeout")

    freeze = latest_freeze()
    source_items = freeze_items(freeze.name) if freeze else []
    guard_before = guardrails()
    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }
    ack_ok = acknowledgement == GOV_ACK
    policy_enabled_before = get_flag(POLICY_DOCTYPE, freeze.target_policy, "production_batch_enabled") if freeze else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, freeze.target_policy, "live_posting_allowed") if freeze else 0
    guard_after = guardrails()
    policy_enabled_after = get_flag(POLICY_DOCTYPE, freeze.target_policy, "production_batch_enabled") if freeze else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, freeze.target_policy, "live_posting_allowed") if freeze else 0

    issues = validate_source(freeze, source_items, guard_before, policy_enabled_before, policy_live_before, config)
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
        issues.append("Accounting movement changed while preparing Phase 10R governance closeout evidence.")

    evidence = build_evidence(freeze, guard_before, guard_after, policy_enabled_before, policy_enabled_after, policy_live_before, policy_live_after)
    all_blocked_verified = int(
        evidence["violation_simulation_count"] == 6
        and evidence["blocked_violation_count"] == 6
        and evidence["failed_violation_count"] == 0
        and evidence["over_line_violation_blocked"]
        and evidence["over_amount_violation_blocked"]
        and evidence["over_payment_entry_violation_blocked"]
        and evidence["live_posting_violation_blocked"]
        and evidence["journal_entry_side_effect_violation_blocked"]
        and evidence["purchase_invoice_side_effect_violation_blocked"]
    )
    runtime_limits_valid = int(
        evidence["max_batch_line_count"] == 3
        and flt(evidence["max_batch_amount"], 2) == 3
        and evidence["max_payment_entry_count"] == 1
        and evidence["live_posting_allowed"] == 0
        and evidence["journal_entry_side_effect_allowed"] == 0
        and evidence["purchase_invoice_side_effect_allowed"] == 0
    )
    items = build_governance_items(freeze, source_items, issues, ack_ok)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    allowed = int(ack_ok and item_summary["blocker_count"] == 0 and bool(freeze) and all_blocked_verified and runtime_limits_valid and no_new_movement and policy_preserved)
    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Governance Closeout Approved" if allowed else "Needs Review",
        "governance_status": "Controlled Limited Runtime Watch Governance Closed" if allowed else "Needs Review",
        "governance_closeout_approved": allowed,
        "runtime_watch_governance_closed": allowed,
        "ready_for_governed_controlled_limited_operations": allowed,
        "runtime_watch_control_loop_closed": allowed,
        "violation_simulation_governance_verified": allowed,
        "frozen_evidence_verified": 1 if freeze else 0,
        "no_new_accounting_movement_verified": no_new_movement,
        "policy_state_preserved_verified": policy_preserved,
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": 0,
        "all_runtime_violations_blocked_verified": all_blocked_verified,
        "phase10q_freeze_verified": 1 if freeze else 0,
        "phase10p_simulation_verified": 1 if freeze else 0,
        "phase10o_runtime_watch_verified": 1 if freeze else 0,
        "phase10n_baseline_verified": 1 if freeze else 0,
        "phase10m_closeout_verified": 1 if freeze else 0,
        "controlled_policy_enabled_verified": int(policy_enabled_after == 1),
        "live_posting_blocked_verified": int(policy_live_after == 0),
        **evidence,
        "governance_score": score,
        **item_summary,
        "items": items,
        "source_items": source_items,
        "issues": issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "required_acknowledgement": GOV_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 10R closes runtime-watch governance only. No accounting movement or policy mutation is performed.",
    }

    if int(dry_run or 0):
        result.update(
            {
                "status": "Needs Review",
                "governance_status": "Needs Review",
                "governance_closeout_approved": 0,
                "runtime_watch_governance_closed": 0,
                "ready_for_governed_controlled_limited_operations": 0,
                "runtime_watch_control_loop_closed": 0,
                "violation_simulation_governance_verified": 0,
            }
        )
        return result

    doc = frappe.new_doc(GOV_DOCTYPE)
    doc.governance_id = make_governance_id()
    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = GOV_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.evidence_json = safe_json({"evidence": evidence, "source_items": source_items, "guardrails_before": guard_before, "guardrails_after": guard_after, "config": config})
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    create_items(doc, items)
    frappe.db.commit()
    return {**result, "created": True, "governance_closeout": doc.name, "governance_id": doc.governance_id, "guardrails_after": guardrails()}


@frappe.whitelist()
def cancel_runtime_watch_governance_closeout_audit(governance_closeout, reason=None):
    assert_action("cancel_runtime_watch_governance_closeout_audit")
    if not frappe.db.exists(GOV_DOCTYPE, governance_closeout):
        frappe.throw(_("Runtime watch governance closeout audit not found: {0}").format(governance_closeout))
    doc = frappe.get_doc(GOV_DOCTYPE, governance_closeout)
    if doc.status == "Cancelled":
        return {"governance_closeout": governance_closeout, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.governance_closeout_approved or 0):
        frappe.throw(_("Cannot cancel an approved Phase 10R governance closeout record."))
    frappe.db.set_value(
        GOV_DOCTYPE,
        governance_closeout,
        {
            "status": "Cancelled",
            "governance_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 10R no-ack governance closeout audit cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{GOV_ITEM_DOCTYPE}` SET status = 'Cancelled' WHERE governance_closeout = %(governance_closeout)s", {"governance_closeout": governance_closeout})
    frappe.db.commit()
    return {"governance_closeout": governance_closeout, "status": "Cancelled", "note": "No-ack governance closeout audit cancelled only. No accounting or policy movement occurred."}


@frappe.whitelist()
def quick_runtime_watch_governance_closeout_summary(limit=20):
    records = frappe.get_all(
        GOV_DOCTYPE,
        fields=[
            "name",
            "governance_id",
            "status",
            "governance_status",
            "governance_closeout_approved",
            "runtime_watch_governance_closed",
            "ready_for_governed_controlled_limited_operations",
            "freeze",
            "simulation",
            "runtime_watch",
            "baseline",
            "violation_simulation_count",
            "blocked_violation_count",
            "failed_violation_count",
            "production_batch_enabled_policy_count_after",
            "live_posting_allowed_policy_count_after",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "submitted_journal_entry_count_today",
            "purchase_invoice_count_today",
            "governance_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(
        GOV_ITEM_DOCTYPE,
        fields=["name", "governance_closeout", "status", "severity", "category", "check_key", "check_label", "detail", "source_doctype", "source_name"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {"governance_closeouts": records, "items": items, "required_acknowledgement": GOV_ACK, "guardrails": guardrails(), "note": "Phase 10R governance closeout summary. Approved record closes the runtime-watch governance loop."}


def execute_governance_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("status"):
        conditions.append("g.status = %(status)s")
        params["status"] = filters.get("status")
    data = frappe.db.sql(
        f"""
        SELECT
            g.name AS governance_closeout, g.governance_id, g.status,
            g.governance_status, g.governance_closeout_approved,
            g.runtime_watch_governance_closed,
            g.ready_for_governed_controlled_limited_operations,
            g.freeze, g.simulation, g.runtime_watch, g.baseline,
            g.violation_simulation_count, g.blocked_violation_count,
            g.failed_violation_count, g.all_runtime_violations_blocked_verified,
            g.production_batch_enabled_policy_count_after,
            g.live_posting_allowed_policy_count_after,
            g.payment_entry_count_before, g.payment_entry_count_after,
            g.payment_entry_gl_count_before, g.payment_entry_gl_count_after,
            g.submitted_journal_entry_count_today, g.purchase_invoice_count_today,
            g.governance_score, g.checked_on
        FROM `tab{GOV_DOCTYPE}` g
        {build_where(conditions)}
        ORDER BY g.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.governance_id for row in data[:20]],
            "datasets": [
                {"name": "Approved", "values": [int(row.governance_closeout_approved or 0) for row in data[:20]]},
                {"name": "Closed", "values": [int(row.runtime_watch_governance_closed or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Governance Closeouts"), "datatype": "Int"},
        {"value": sum(int(row.governance_closeout_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(int(row.runtime_watch_governance_closed or 0) for row in data), "indicator": "Green", "label": _("Closed"), "datatype": "Int"},
        {"value": sum(int(row.failed_violation_count or 0) for row in data), "indicator": "Red", "label": _("Failed Violations"), "datatype": "Int"},
    ]
    return governance_columns(), data, None, chart, summary


def governance_columns():
    return [
        {"fieldname": "governance_closeout", "label": _("Governance Closeout"), "fieldtype": "Link", "options": GOV_DOCTYPE, "width": 220},
        {"fieldname": "governance_id", "label": _("Governance ID"), "fieldtype": "Data", "width": 410},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 180},
        {"fieldname": "governance_status", "label": _("Governance Status"), "fieldtype": "Data", "width": 360},
        {"fieldname": "governance_closeout_approved", "label": _("Approved"), "fieldtype": "Check", "width": 90},
        {"fieldname": "runtime_watch_governance_closed", "label": _("Closed"), "fieldtype": "Check", "width": 90},
        {"fieldname": "ready_for_governed_controlled_limited_operations", "label": _("Ready Governed Ops"), "fieldtype": "Check", "width": 145},
        {"fieldname": "freeze", "label": _("Freeze"), "fieldtype": "Link", "options": FREEZE_DOCTYPE, "width": 220},
        {"fieldname": "simulation", "label": _("Simulation"), "fieldtype": "Link", "options": "NDIS Runtime Watch Violation Sim", "width": 220},
        {"fieldname": "runtime_watch", "label": _("Runtime Watch"), "fieldtype": "Link", "options": "NDIS Controlled Limited Ops Runtime Watch", "width": 220},
        {"fieldname": "baseline", "label": _("Baseline"), "fieldtype": "Link", "options": "NDIS Controlled Limited Ops Baseline", "width": 220},
        {"fieldname": "violation_simulation_count", "label": _("Scenarios"), "fieldtype": "Int", "width": 90},
        {"fieldname": "blocked_violation_count", "label": _("Blocked"), "fieldtype": "Int", "width": 90},
        {"fieldname": "failed_violation_count", "label": _("Failed"), "fieldtype": "Int", "width": 90},
        {"fieldname": "all_runtime_violations_blocked_verified", "label": _("All Blocked"), "fieldtype": "Check", "width": 100},
        {"fieldname": "production_batch_enabled_policy_count_after", "label": _("Enabled Policies"), "fieldtype": "Int", "width": 125},
        {"fieldname": "live_posting_allowed_policy_count_after", "label": _("Live Policies"), "fieldtype": "Int", "width": 105},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 110},
        {"fieldname": "submitted_journal_entry_count_today", "label": _("JE Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "purchase_invoice_count_today", "label": _("PI Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "governance_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("governance_closeout"):
        conditions.append("i.governance_closeout = %(governance_closeout)s")
        params["governance_closeout"] = filters.get("governance_closeout")
    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")
    data = frappe.db.sql(
        f"""
        SELECT i.name AS item, i.governance_closeout, i.status, i.severity,
               i.category, i.check_key, i.check_label, i.detail,
               i.source_doctype, i.source_name, i.checked_on
        FROM `tab{GOV_ITEM_DOCTYPE}` i
        {build_where(conditions)}
        ORDER BY CASE i.status WHEN 'Blocker' THEN 1 WHEN 'Warning' THEN 2 WHEN 'Pass' THEN 3 WHEN 'Info' THEN 4 ELSE 5 END, i.creation DESC
        """,
        params,
        as_dict=True,
    )
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": GOV_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "governance_closeout", "label": _("Governance Closeout"), "fieldtype": "Link", "options": GOV_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 190},
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
        {"value": len([row for row in data if row.category == "Frozen Violation"]), "indicator": "Green", "label": _("Frozen Violation Rows"), "datatype": "Int"},
    ]
    return columns, data, None, {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Items", "values": list(chart_map.values())}]}, "type": "bar"}, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_governance_report(filters)
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
