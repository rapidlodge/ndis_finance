import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


SIM_ACK = "I_CONFIRM_PHASE10P_RUN_RUNTIME_WATCH_VIOLATION_SIMULATION_NO_POSTING"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
WATCH_DOCTYPE = "NDIS Controlled Limited Ops Runtime Watch"
SIM_DOCTYPE = "NDIS Runtime Watch Violation Sim"
SIM_ITEM_DOCTYPE = "NDIS Runtime Watch Violation Sim Item"


def make_simulation_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-RUNTIME-WATCH-VIOLATION-SIM-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def config_state():
    return {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def latest_runtime_watch():
    rows = frappe.get_all(
        WATCH_DOCTYPE,
        filters={
            "status": "Watch Active",
            "watch_status": "Controlled Limited Operations Runtime Watch Active",
            "watch_active": 1,
            "runtime_watch_enabled": 1,
            "guardrail_watch_active": 1,
            "ready_for_controlled_limited_runtime_checks": 1,
            "baseline_verified": 1,
            "runtime_limits_locked": 1,
            "live_posting_block_active": 1,
            "journal_entry_side_effect_block_active": 1,
            "purchase_invoice_side_effect_block_active": 1,
            "no_new_accounting_movement_verified": 1,
            "policy_state_preserved_verified": 1,
            "policy_mutation_performed": 0,
            "actual_policy_mutation_count": 0,
            "phase10n_baseline_verified": 1,
            "phase10m_closeout_verified": 1,
            "phase10f_monitoring_register_verified": 1,
            "controlled_policy_enabled_verified": 1,
            "live_posting_blocked_verified": 1,
            "target_policy_enabled_after": 1,
            "target_policy_live_after": 0,
            "max_batch_line_count": 3,
            "max_batch_amount": 3,
            "max_payment_entry_count": 1,
            "live_posting_allowed": 0,
            "journal_entry_side_effect_allowed": 0,
            "purchase_invoice_side_effect_allowed": 0,
            "actual_payment_entry_created_count": 0,
            "actual_payment_entry_cancelled_count": 0,
            "actual_gl_created_count": 0,
            "submitted_journal_entry_count_today": 0,
            "purchase_invoice_count_today": 0,
        },
        fields=[
            "name",
            "watch_id",
            "baseline",
            "closeout",
            "monitoring_register",
            "policy_decision",
            "target_policy_doctype",
            "target_policy",
            "target_policy_name",
            "max_batch_line_count",
            "max_batch_amount",
            "max_payment_entry_count",
            "live_posting_allowed",
            "journal_entry_side_effect_allowed",
            "purchase_invoice_side_effect_allowed",
            "payment_entry_count_after",
            "payment_entry_gl_count_after",
            "watch_score",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_completed_simulation(runtime_watch):
    if not runtime_watch:
        return None
    rows = frappe.get_all(
        SIM_DOCTYPE,
        filters={
            "runtime_watch": runtime_watch,
            "status": "Simulation Completed",
            "simulation_completed": 1,
            "ready_for_runtime_violation_freeze": 1,
        },
        fields=["name", "simulation_id"],
        order_by="creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def add_item(items, status, severity, category, scenario_key, scenario_label, detail, **values):
    item = {
        "status": status,
        "severity": severity,
        "category": category,
        "scenario_key": scenario_key,
        "scenario_label": scenario_label,
        "detail": detail,
    }
    item.update(values)
    items.append(item)


def build_violation_scenarios(watch):
    max_lines = int(watch.max_batch_line_count or 0) if watch else 0
    max_amount = flt(watch.max_batch_amount or 0, 2) if watch else 0
    max_pe = int(watch.max_payment_entry_count or 0) if watch else 0
    base = {
        "requested_batch_line_count": max_lines,
        "requested_batch_amount": max_amount,
        "requested_payment_entry_count": max_pe,
        "requested_live_posting": 0,
        "requested_journal_entry_side_effect": 0,
        "requested_purchase_invoice_side_effect": 0,
        "expected_decision": "Blocked",
    }
    return [
        {**base, "scenario_key": "over_line", "scenario_label": "Over Line", "requested_batch_line_count": max_lines + 1},
        {**base, "scenario_key": "over_amount", "scenario_label": "Over Amount", "requested_batch_amount": flt(max_amount + 0.01, 2)},
        {**base, "scenario_key": "over_payment_entry", "scenario_label": "Over Payment Entry Count", "requested_payment_entry_count": max_pe + 1},
        {**base, "scenario_key": "live_posting", "scenario_label": "Live Posting", "requested_live_posting": 1},
        {**base, "scenario_key": "journal_entry_side_effect", "scenario_label": "Journal Entry Side Effect", "requested_journal_entry_side_effect": 1},
        {**base, "scenario_key": "purchase_invoice_side_effect", "scenario_label": "Purchase Invoice Side Effect", "requested_purchase_invoice_side_effect": 1},
    ]


def evaluate_scenario(watch, scenario):
    reasons = []
    if not watch:
        reasons.append("No active Phase 10O runtime watch was available.")
    else:
        if int(scenario["requested_batch_line_count"] or 0) > int(watch.max_batch_line_count or 0):
            reasons.append("Requested batch line count exceeds locked runtime watch limit.")
        if flt(scenario["requested_batch_amount"] or 0, 2) > flt(watch.max_batch_amount or 0, 2):
            reasons.append("Requested batch amount exceeds locked runtime watch limit.")
        if int(scenario["requested_payment_entry_count"] or 0) > int(watch.max_payment_entry_count or 0):
            reasons.append("Requested Payment Entry count exceeds locked runtime watch limit.")
        if int(scenario["requested_live_posting"] or 0) and not int(watch.live_posting_allowed or 0):
            reasons.append("Live posting request is blocked by runtime watch.")
        if int(scenario["requested_journal_entry_side_effect"] or 0) and not int(watch.journal_entry_side_effect_allowed or 0):
            reasons.append("Journal Entry side effect request is blocked by runtime watch.")
        if int(scenario["requested_purchase_invoice_side_effect"] or 0) and not int(watch.purchase_invoice_side_effect_allowed or 0):
            reasons.append("Purchase Invoice side effect request is blocked by runtime watch.")
    decision = "Blocked" if reasons else "Allowed"
    blocked_as_expected = int(decision == scenario["expected_decision"] == "Blocked")
    return {
        **scenario,
        "watch_decision": decision,
        "blocked_as_expected": blocked_as_expected,
        "block_reasons": "; ".join(reasons),
        "status": "Pass" if blocked_as_expected else "Blocker",
        "severity": "High" if blocked_as_expected else "Critical",
        "category": "Runtime Violation",
        "detail": "Violation blocked by runtime watch." if blocked_as_expected else "Runtime watch did not block the simulated violation.",
        "source_doctype": WATCH_DOCTYPE if watch else None,
        "source_name": watch.name if watch else None,
    }


def validate_source(watch, guard_before, guard_after, policy_enabled_before, policy_enabled_after, policy_live_before, policy_live_after, config):
    issues = []
    if not watch:
        return ["No active Phase 10O runtime watch found."]

    existing = existing_completed_simulation(watch.name)
    if existing:
        issues.append(f"Completed Phase 10P simulation already exists for this runtime watch: {existing.simulation_id}")

    required_links = {
        "runtime_watch": (WATCH_DOCTYPE, watch.name),
        "baseline": ("NDIS Controlled Limited Ops Baseline", watch.baseline),
        "closeout": ("NDIS Limited Operation Closeout Gate", watch.closeout),
        "monitoring_register": ("NDIS Controlled Limited Operations Monitoring Register", watch.monitoring_register),
        "target_policy": (POLICY_DOCTYPE, watch.target_policy),
    }
    if watch.policy_decision:
        required_links["policy_decision"] = ("NDIS Guarded Adapter Final Policy Decision", watch.policy_decision)

    for label, (doctype, name) in required_links.items():
        if not name or not frappe.db.exists(doctype, name):
            issues.append(f"Missing or invalid evidence link: {label}")

    if int(watch.max_batch_line_count or 0) != 3:
        issues.append("Runtime watch line cap must remain 3.")
    if flt(watch.max_batch_amount or 0, 2) != 3:
        issues.append("Runtime watch amount cap must remain 3.00.")
    if int(watch.max_payment_entry_count or 0) != 1:
        issues.append("Runtime watch Payment Entry cap must remain 1.")
    if int(watch.live_posting_allowed or 0) != 0:
        issues.append("Runtime watch live posting must remain blocked.")
    if int(watch.journal_entry_side_effect_allowed or 0) != 0:
        issues.append("Runtime watch Journal Entry side effects must remain blocked.")
    if int(watch.purchase_invoice_side_effect_allowed or 0) != 0:
        issues.append("Runtime watch Purchase Invoice side effects must remain blocked.")
    if policy_enabled_before != 1 or policy_enabled_after != 1:
        issues.append("Target policy production_batch_enabled must remain 1 before and after simulation.")
    if policy_live_before != 0 or policy_live_after != 0:
        issues.append("Target policy live_posting_allowed must remain 0 before and after simulation.")
    if guard_before["production_batch_enabled_policy_count"] != 1 or guard_after["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must remain enabled.")
    if guard_before["live_posting_allowed_policy_count"] != 0 or guard_after["live_posting_allowed_policy_count"] != 0:
        issues.append("Live posting allowed policy count must remain 0.")
    if guard_before["payment_entry_count"] != guard_after["payment_entry_count"]:
        issues.append("Payment Entry count changed during simulation.")
    if guard_before["payment_entry_gl_count"] != guard_after["payment_entry_gl_count"]:
        issues.append("Payment Entry GL count changed during simulation.")
    if guard_after["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry count today must remain 0.")
    if guard_after["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice count today must remain 0.")
    if config["production_mode"] != 0:
        issues.append("Production mode config must remain 0.")
    if config["live_pe_enabled"] != 0:
        issues.append("Live Payment Entry posting config must remain 0.")
    return issues


def build_items(watch, scenario_results, issues, ack_ok):
    items = []
    if watch:
        add_item(
            items,
            "Pass",
            "Low",
            "Evidence",
            "phase10o_runtime_watch",
            "Phase 10O Runtime Watch",
            f"Runtime watch found: {watch.watch_id}.",
            source_doctype=WATCH_DOCTYPE,
            source_name=watch.name,
        )
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase10o_runtime_watch", "Phase 10O Runtime Watch", "No active Phase 10O runtime watch found.")

    if issues:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Simulation Source", "source_valid", "Simulation Source Valid", issue)
    else:
        add_item(items, "Pass", "Low", "Simulation Source", "source_valid", "Simulation Source Valid", "Runtime watch and policy state are valid for violation simulation.")

    for result in scenario_results:
        extra = {
            key: value
            for key, value in result.items()
            if key not in {"status", "severity", "category", "scenario_key", "scenario_label", "detail"}
        }
        add_item(items, result["status"], result["severity"], result["category"], result["scenario_key"], result["scenario_label"], result["detail"], **extra)

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {SIM_ACK}")
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
        row = frappe.new_doc(SIM_ITEM_DOCTYPE)
        row.simulation = doc.name
        for fieldname in [
            "status",
            "severity",
            "category",
            "scenario_key",
            "scenario_label",
            "requested_batch_line_count",
            "requested_batch_amount",
            "requested_payment_entry_count",
            "requested_live_posting",
            "requested_journal_entry_side_effect",
            "requested_purchase_invoice_side_effect",
            "watch_decision",
            "expected_decision",
            "blocked_as_expected",
            "block_reasons",
            "detail",
            "source_doctype",
            "source_name",
        ]:
            if row.meta.has_field(fieldname):
                setattr(row, fieldname, item.get(fieldname))
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


def violation_flags(scenario_results):
    result = {
        "over_line_violation_blocked": 0,
        "over_amount_violation_blocked": 0,
        "over_payment_entry_violation_blocked": 0,
        "live_posting_violation_blocked": 0,
        "journal_entry_side_effect_violation_blocked": 0,
        "purchase_invoice_side_effect_violation_blocked": 0,
    }
    for scenario in scenario_results:
        fieldname = f"{scenario['scenario_key']}_violation_blocked"
        if fieldname in result:
            result[fieldname] = int(scenario.get("blocked_as_expected") or 0)
    return result


@frappe.whitelist()
def run_runtime_watch_violation_simulation(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_runtime_watch_violation_simulation")

    watch = latest_runtime_watch()
    config = config_state()
    guard_before = guardrails()
    policy_enabled_before = get_flag(POLICY_DOCTYPE, watch.target_policy, "production_batch_enabled") if watch else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, watch.target_policy, "live_posting_allowed") if watch else 0

    scenarios = build_violation_scenarios(watch)
    scenario_results = [evaluate_scenario(watch, scenario) for scenario in scenarios]

    guard_after = guardrails()
    policy_enabled_after = get_flag(POLICY_DOCTYPE, watch.target_policy, "production_batch_enabled") if watch else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, watch.target_policy, "live_posting_allowed") if watch else 0

    issues = validate_source(watch, guard_before, guard_after, policy_enabled_before, policy_enabled_after, policy_live_before, policy_live_after, config)
    ack_ok = acknowledgement == SIM_ACK
    flags = violation_flags(scenario_results)
    blocked_count = sum(int(row.get("blocked_as_expected") or 0) for row in scenario_results)
    failed_count = len(scenario_results) - blocked_count
    all_blocked = int(len(scenario_results) == 6 and blocked_count == 6 and failed_count == 0)
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

    items = build_items(watch, scenario_results, issues, ack_ok)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    allowed = int(ack_ok and item_summary["blocker_count"] == 0 and all_blocked and bool(watch) and no_new_movement and policy_preserved)

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Simulation Completed" if allowed else "Needs Review",
        "simulation_status": "Runtime Watch Violation Simulation Completed" if allowed else "Needs Review",
        "simulation_completed": allowed,
        "all_runtime_violations_blocked": all_blocked,
        "ready_for_runtime_violation_freeze": allowed,
        "runtime_watch_verified": 1 if watch else 0,
        "simulation_only_verified": 1,
        "no_new_accounting_movement_verified": no_new_movement,
        "policy_state_preserved_verified": policy_preserved,
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": 0,
        "violation_simulation_count": len(scenario_results),
        "blocked_violation_count": blocked_count,
        "failed_violation_count": failed_count,
        **flags,
        "phase10o_runtime_watch_verified": 1 if watch else 0,
        "phase10n_baseline_verified": 1 if watch else 0,
        "phase10m_closeout_verified": 1 if watch else 0,
        "controlled_policy_enabled_verified": int(policy_enabled_after == 1),
        "live_posting_blocked_verified": int(policy_live_after == 0),
        "runtime_watch": watch.name if watch else None,
        "baseline": watch.baseline if watch else None,
        "closeout": watch.closeout if watch else None,
        "monitoring_register": watch.monitoring_register if watch else None,
        "policy_decision": watch.policy_decision if watch else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": watch.target_policy if watch else None,
        "target_policy_name": watch.target_policy_name if watch else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_before": policy_live_before,
        "target_policy_live_after": policy_live_after,
        "production_batch_enabled_policy_count_before": guard_before["production_batch_enabled_policy_count"],
        "production_batch_enabled_policy_count_after": guard_after["production_batch_enabled_policy_count"],
        "live_posting_allowed_policy_count_before": guard_before["live_posting_allowed_policy_count"],
        "live_posting_allowed_policy_count_after": guard_after["live_posting_allowed_policy_count"],
        "max_batch_line_count": int(watch.max_batch_line_count or 0) if watch else 0,
        "max_batch_amount": flt(watch.max_batch_amount or 0, 2) if watch else 0,
        "max_payment_entry_count": int(watch.max_payment_entry_count or 0) if watch else 0,
        "live_posting_allowed": int(watch.live_posting_allowed or 0) if watch else 0,
        "journal_entry_side_effect_allowed": int(watch.journal_entry_side_effect_allowed or 0) if watch else 0,
        "purchase_invoice_side_effect_allowed": int(watch.purchase_invoice_side_effect_allowed or 0) if watch else 0,
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guard_after["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
        "actual_payment_entry_created_count": 0,
        "actual_payment_entry_cancelled_count": 0,
        "actual_gl_created_count": 0,
        "submitted_journal_entry_count_today": guard_after["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_after["purchase_invoice_count_today"],
        "simulation_score": score,
        **item_summary,
        "items": items,
        "scenario_results": scenario_results,
        "issues": issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "config": config,
        "required_acknowledgement": SIM_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 10P simulates runtime watch violations only. No accounting movement or policy mutation is performed.",
    }

    if int(dry_run or 0):
        result.update(
            {
                "status": "Needs Review",
                "simulation_status": "Needs Review",
                "simulation_completed": 0,
                "ready_for_runtime_violation_freeze": 0,
            }
        )
        return result

    doc = frappe.new_doc(SIM_DOCTYPE)
    doc.simulation_id = make_simulation_id()
    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = SIM_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.scenario_json = safe_json(scenario_results)
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    create_items(doc, items)
    frappe.db.commit()
    return {**result, "created": True, "simulation": doc.name, "simulation_id": doc.simulation_id, "guardrails_after": guardrails()}


@frappe.whitelist()
def cancel_runtime_watch_violation_simulation_audit(simulation, reason=None):
    assert_action("cancel_runtime_watch_violation_simulation_audit")
    if not frappe.db.exists(SIM_DOCTYPE, simulation):
        frappe.throw(_("Runtime watch violation simulation audit not found: {0}").format(simulation))
    doc = frappe.get_doc(SIM_DOCTYPE, simulation)
    if doc.status == "Cancelled":
        return {"simulation": simulation, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.simulation_completed or 0):
        frappe.throw(_("Cannot cancel a completed Phase 10P simulation record."))
    frappe.db.set_value(
        SIM_DOCTYPE,
        simulation,
        {
            "status": "Cancelled",
            "simulation_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 10P no-ack simulation audit cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{SIM_ITEM_DOCTYPE}` SET status = 'Cancelled' WHERE simulation = %(simulation)s", {"simulation": simulation})
    frappe.db.commit()
    return {"simulation": simulation, "status": "Cancelled", "note": "No-ack runtime watch violation simulation audit cancelled only. No accounting or policy movement occurred."}


@frappe.whitelist()
def quick_runtime_watch_violation_simulation_summary(limit=20):
    simulations = frappe.get_all(
        SIM_DOCTYPE,
        fields=[
            "name",
            "simulation_id",
            "status",
            "simulation_status",
            "simulation_completed",
            "all_runtime_violations_blocked",
            "ready_for_runtime_violation_freeze",
            "runtime_watch",
            "violation_simulation_count",
            "blocked_violation_count",
            "failed_violation_count",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "production_batch_enabled_policy_count_after",
            "live_posting_allowed_policy_count_after",
            "simulation_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(
        SIM_ITEM_DOCTYPE,
        fields=["name", "simulation", "status", "severity", "category", "scenario_key", "scenario_label", "watch_decision", "blocked_as_expected", "detail"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "simulations": simulations,
        "items": items,
        "required_acknowledgement": SIM_ACK,
        "guardrails": guardrails(),
        "note": "Phase 10P violation simulation summary. Runtime violations are simulated and blocked without posting.",
    }


def execute_sim_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("s.status = %(status)s")
        params["status"] = filters.get("status")
    data = frappe.db.sql(
        f"""
        SELECT
            s.name AS simulation, s.simulation_id, s.status, s.simulation_status,
            s.simulation_completed, s.all_runtime_violations_blocked,
            s.ready_for_runtime_violation_freeze, s.runtime_watch,
            s.violation_simulation_count, s.blocked_violation_count, s.failed_violation_count,
            s.payment_entry_count_before, s.payment_entry_count_after,
            s.payment_entry_gl_count_before, s.payment_entry_gl_count_after,
            s.production_batch_enabled_policy_count_after,
            s.live_posting_allowed_policy_count_after,
            s.simulation_score, s.checked_on, %(currency)s AS currency
        FROM `tab{SIM_DOCTYPE}` s
        {build_where(conditions)}
        ORDER BY s.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.simulation_id for row in data[:20]],
            "datasets": [
                {"name": "Blocked", "values": [int(row.blocked_violation_count or 0) for row in data[:20]]},
                {"name": "Failed", "values": [int(row.failed_violation_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Simulations"), "datatype": "Int"},
        {"value": sum(int(row.simulation_completed or 0) for row in data), "indicator": "Green", "label": _("Completed"), "datatype": "Int"},
        {"value": sum(int(row.blocked_violation_count or 0) for row in data), "indicator": "Green", "label": _("Blocked Violations"), "datatype": "Int"},
        {"value": sum(int(row.failed_violation_count or 0) for row in data), "indicator": "Red", "label": _("Failed Violations"), "datatype": "Int"},
    ]
    return sim_columns(), data, None, chart, summary


def sim_columns():
    return [
        {"fieldname": "simulation", "label": _("Simulation"), "fieldtype": "Link", "options": SIM_DOCTYPE, "width": 220},
        {"fieldname": "simulation_id", "label": _("Simulation ID"), "fieldtype": "Data", "width": 380},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 150},
        {"fieldname": "simulation_status", "label": _("Simulation Status"), "fieldtype": "Data", "width": 360},
        {"fieldname": "simulation_completed", "label": _("Completed"), "fieldtype": "Check", "width": 90},
        {"fieldname": "all_runtime_violations_blocked", "label": _("All Blocked"), "fieldtype": "Check", "width": 100},
        {"fieldname": "ready_for_runtime_violation_freeze", "label": _("Ready Freeze"), "fieldtype": "Check", "width": 110},
        {"fieldname": "runtime_watch", "label": _("Runtime Watch"), "fieldtype": "Link", "options": WATCH_DOCTYPE, "width": 220},
        {"fieldname": "violation_simulation_count", "label": _("Violations"), "fieldtype": "Int", "width": 90},
        {"fieldname": "blocked_violation_count", "label": _("Blocked"), "fieldtype": "Int", "width": 90},
        {"fieldname": "failed_violation_count", "label": _("Failed"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 110},
        {"fieldname": "production_batch_enabled_policy_count_after", "label": _("Enabled Policies"), "fieldtype": "Int", "width": 130},
        {"fieldname": "live_posting_allowed_policy_count_after", "label": _("Live Policies"), "fieldtype": "Int", "width": 110},
        {"fieldname": "simulation_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("simulation"):
        conditions.append("i.simulation = %(simulation)s")
        params["simulation"] = filters.get("simulation")
    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")
    if filters.get("scenario_key"):
        conditions.append("i.scenario_key = %(scenario_key)s")
        params["scenario_key"] = filters.get("scenario_key")
    data = frappe.db.sql(
        f"""
        SELECT
            i.name AS item, i.simulation, i.status, i.severity, i.category,
            i.scenario_key, i.scenario_label, i.requested_batch_line_count,
            i.requested_batch_amount, i.requested_payment_entry_count,
            i.requested_live_posting, i.requested_journal_entry_side_effect,
            i.requested_purchase_invoice_side_effect, i.watch_decision,
            i.expected_decision, i.blocked_as_expected, i.block_reasons,
            i.detail, i.source_doctype, i.source_name, i.checked_on
        FROM `tab{SIM_ITEM_DOCTYPE}` i
        {build_where(conditions)}
        ORDER BY CASE i.status WHEN 'Blocker' THEN 1 WHEN 'Warning' THEN 2 WHEN 'Pass' THEN 3 WHEN 'Info' THEN 4 ELSE 5 END, i.creation DESC
        """,
        params,
        as_dict=True,
    )
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": SIM_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "simulation", "label": _("Simulation"), "fieldtype": "Link", "options": SIM_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 170},
        {"fieldname": "scenario_key", "label": _("Scenario Key"), "fieldtype": "Data", "width": 180},
        {"fieldname": "scenario_label", "label": _("Scenario"), "fieldtype": "Data", "width": 220},
        {"fieldname": "watch_decision", "label": _("Watch Decision"), "fieldtype": "Data", "width": 120},
        {"fieldname": "blocked_as_expected", "label": _("Blocked Expected"), "fieldtype": "Check", "width": 125},
        {"fieldname": "block_reasons", "label": _("Block Reasons"), "fieldtype": "Small Text", "width": 520},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 420},
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
        {"value": len([row for row in data if row.blocked_as_expected]), "indicator": "Green", "label": _("Blocked As Expected"), "datatype": "Int"},
    ]
    return columns, data, None, {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Items", "values": list(chart_map.values())}]}, "type": "bar"}, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_sim_report(filters)
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
