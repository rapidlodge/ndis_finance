import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


FREEZE_ACK = "I_CONFIRM_PHASE10Q_FREEZE_RUNTIME_WATCH_VIOLATION_SIMULATION_EVIDENCE_NO_POSTING"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
SIM_DOCTYPE = "NDIS Runtime Watch Violation Sim"
SIM_ITEM_DOCTYPE = "NDIS Runtime Watch Violation Sim Item"
FREEZE_DOCTYPE = "NDIS Runtime Watch Violation Sim Freeze"
FREEZE_ITEM_DOCTYPE = "NDIS Runtime Watch Violation Sim Freeze Item"


def make_freeze_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-RUNTIME-WATCH-VIOLATION-SIM-FREEZE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_simulation():
    rows = frappe.get_all(
        SIM_DOCTYPE,
        filters={
            "status": "Simulation Completed",
            "simulation_status": "Runtime Watch Violation Simulation Completed",
            "simulation_completed": 1,
            "all_runtime_violations_blocked": 1,
            "ready_for_runtime_violation_freeze": 1,
            "runtime_watch_verified": 1,
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
            "simulation_id",
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
            "simulation_score",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_freeze(simulation):
    if not simulation:
        return None
    rows = frappe.get_all(
        FREEZE_DOCTYPE,
        filters={"simulation": simulation, "status": "Frozen", "freeze_completed": 1},
        fields=["name", "freeze_id"],
        limit=1,
    )
    return rows[0] if rows else None


def simulation_items(simulation):
    if not simulation:
        return []
    return frappe.get_all(
        SIM_ITEM_DOCTYPE,
        filters={"simulation": simulation},
        fields=[
            "name",
            "status",
            "severity",
            "category",
            "scenario_key",
            "scenario_label",
            "watch_decision",
            "expected_decision",
            "blocked_as_expected",
            "block_reasons",
            "detail",
        ],
        order_by="creation asc",
    )


def violation_items(items):
    return [
        row
        for row in items
        if row.category == "Runtime Violation"
        or row.scenario_key
        in {
            "over_line",
            "over_amount",
            "over_payment_entry",
            "live_posting",
            "journal_entry_side_effect",
            "purchase_invoice_side_effect",
        }
    ]


def validate_source(sim, source_items, guard_before, guard_after, policy_enabled_before, policy_enabled_after, policy_live_before, policy_live_after, config):
    issues = []
    if not sim:
        return ["No completed Phase 10P runtime watch violation simulation found."]

    existing = existing_freeze(sim.name)
    if existing:
        issues.append(f"Phase 10Q freeze already exists for this simulation: {existing.freeze_id}")

    required_links = {
        "simulation": (SIM_DOCTYPE, sim.name),
        "runtime_watch": ("NDIS Controlled Limited Ops Runtime Watch", sim.runtime_watch),
        "baseline": ("NDIS Controlled Limited Ops Baseline", sim.baseline),
        "closeout": ("NDIS Limited Operation Closeout Gate", sim.closeout),
        "monitoring_register": ("NDIS Controlled Limited Operations Monitoring Register", sim.monitoring_register),
        "target_policy": (POLICY_DOCTYPE, sim.target_policy),
    }
    for label, (doctype, name) in required_links.items():
        if not name or not frappe.db.exists(doctype, name):
            issues.append(f"Missing or invalid evidence link: {label}")

    expected = {"over_line", "over_amount", "over_payment_entry", "live_posting", "journal_entry_side_effect", "purchase_invoice_side_effect"}
    rows = violation_items(source_items)
    found = {row.scenario_key for row in rows}
    if found != expected:
        issues.append(f"Simulation violation item scenario set mismatch. Found: {sorted(found)}")
    if len(rows) != 6:
        issues.append(f"Simulation must include exactly six violation item rows. Found: {len(rows)}")
    if [row for row in rows if row.status == "Blocker"]:
        issues.append("Simulation item blocker rows exist.")
    if [row for row in rows if not int(row.blocked_as_expected or 0)]:
        issues.append("One or more simulated violations were not blocked as expected.")

    if int(sim.violation_simulation_count or 0) != 6:
        issues.append("Simulation violation count must be 6.")
    if int(sim.blocked_violation_count or 0) != 6:
        issues.append("Blocked violation count must be 6.")
    if int(sim.failed_violation_count or 0) != 0:
        issues.append("Failed violation count must be 0.")
    for flag in [
        "over_line_violation_blocked",
        "over_amount_violation_blocked",
        "over_payment_entry_violation_blocked",
        "live_posting_violation_blocked",
        "journal_entry_side_effect_violation_blocked",
        "purchase_invoice_side_effect_violation_blocked",
    ]:
        if not int(getattr(sim, flag) or 0):
            issues.append(f"Required blocked flag is not set: {flag}")

    if policy_enabled_before != 1 or policy_enabled_after != 1:
        issues.append("Target policy production_batch_enabled must remain 1 before and after Phase 10Q.")
    if policy_live_before != 0 or policy_live_after != 0:
        issues.append("Target policy live_posting_allowed must remain 0 before and after Phase 10Q.")
    if guard_before["production_batch_enabled_policy_count"] != 1 or guard_after["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must remain enabled.")
    if guard_before["live_posting_allowed_policy_count"] != 0 or guard_after["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must remain 0.")
    if guard_before["payment_entry_count"] != guard_after["payment_entry_count"]:
        issues.append("Payment Entry count changed while preparing Phase 10Q evidence.")
    if guard_before["payment_entry_gl_count"] != guard_after["payment_entry_gl_count"]:
        issues.append("Payment Entry GL count changed while preparing Phase 10Q evidence.")
    if guard_after["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry count today must remain 0.")
    if guard_after["purchase_invoice_count_today"] != 0:
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


def build_freeze_items(sim, source_items, issues, ack_ok):
    items = []
    if sim:
        add_item(items, "Pass", "Low", "Evidence", "phase10p_simulation_exists", "Phase 10P simulation exists", f"Simulation found: {sim.simulation_id}.", SIM_DOCTYPE, sim.name)
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase10p_simulation_exists", "Phase 10P simulation exists", "No completed Phase 10P simulation found.")

    if issues:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Freeze Source", "freeze_source_valid", "Freeze source valid", issue)
    else:
        add_item(items, "Pass", "Low", "Freeze Source", "freeze_source_valid", "Freeze source valid", "Phase 10P simulation evidence is valid for freeze.")

    for row in violation_items(source_items):
        status = "Pass" if row.status == "Pass" and int(row.blocked_as_expected or 0) else "Blocker"
        add_item(
            items,
            status,
            "High" if status == "Pass" else "Critical",
            "Frozen Violation",
            row.scenario_key,
            row.scenario_label,
            f"decision={row.watch_decision}; expected={row.expected_decision}; blocked_as_expected={int(row.blocked_as_expected or 0)}; reasons={row.block_reasons}",
            SIM_ITEM_DOCTYPE,
            row.name,
        )

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {FREEZE_ACK}")
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
        row = frappe.new_doc(FREEZE_ITEM_DOCTYPE)
        row.freeze = doc.name
        for fieldname in ["status", "severity", "category", "check_key", "check_label", "detail", "source_doctype", "source_name"]:
            setattr(row, fieldname, item.get(fieldname))
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


def build_evidence(sim, guard_before, guard_after, policy_enabled_before, policy_enabled_after, policy_live_before, policy_live_after):
    return {
        "simulation": sim.name if sim else None,
        "runtime_watch": sim.runtime_watch if sim else None,
        "baseline": sim.baseline if sim else None,
        "closeout": sim.closeout if sim else None,
        "monitoring_register": sim.monitoring_register if sim else None,
        "policy_decision": sim.policy_decision if sim else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": sim.target_policy if sim else None,
        "target_policy_name": sim.target_policy_name if sim else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_before": policy_live_before,
        "target_policy_live_after": policy_live_after,
        "production_batch_enabled_policy_count_before": guard_before["production_batch_enabled_policy_count"],
        "production_batch_enabled_policy_count_after": guard_after["production_batch_enabled_policy_count"],
        "live_posting_allowed_policy_count_before": guard_before["live_posting_allowed_policy_count"],
        "live_posting_allowed_policy_count_after": guard_after["live_posting_allowed_policy_count"],
        "max_batch_line_count": int(sim.max_batch_line_count or 0) if sim else 0,
        "max_batch_amount": flt(sim.max_batch_amount or 0, 2) if sim else 0,
        "max_payment_entry_count": int(sim.max_payment_entry_count or 0) if sim else 0,
        "live_posting_allowed": int(sim.live_posting_allowed or 0) if sim else 0,
        "journal_entry_side_effect_allowed": int(sim.journal_entry_side_effect_allowed or 0) if sim else 0,
        "purchase_invoice_side_effect_allowed": int(sim.purchase_invoice_side_effect_allowed or 0) if sim else 0,
        "violation_simulation_count": int(sim.violation_simulation_count or 0) if sim else 0,
        "blocked_violation_count": int(sim.blocked_violation_count or 0) if sim else 0,
        "failed_violation_count": int(sim.failed_violation_count or 0) if sim else 0,
        "over_line_violation_blocked": int(sim.over_line_violation_blocked or 0) if sim else 0,
        "over_amount_violation_blocked": int(sim.over_amount_violation_blocked or 0) if sim else 0,
        "over_payment_entry_violation_blocked": int(sim.over_payment_entry_violation_blocked or 0) if sim else 0,
        "live_posting_violation_blocked": int(sim.live_posting_violation_blocked or 0) if sim else 0,
        "journal_entry_side_effect_violation_blocked": int(sim.journal_entry_side_effect_violation_blocked or 0) if sim else 0,
        "purchase_invoice_side_effect_violation_blocked": int(sim.purchase_invoice_side_effect_violation_blocked or 0) if sim else 0,
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
def run_runtime_watch_violation_simulation_freeze(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_runtime_watch_violation_simulation_freeze")

    sim = latest_simulation()
    source_items = simulation_items(sim.name) if sim else []
    guard_before = guardrails()
    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }
    ack_ok = acknowledgement == FREEZE_ACK
    policy_enabled_before = get_flag(POLICY_DOCTYPE, sim.target_policy, "production_batch_enabled") if sim else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, sim.target_policy, "live_posting_allowed") if sim else 0
    guard_after = guardrails()
    policy_enabled_after = get_flag(POLICY_DOCTYPE, sim.target_policy, "production_batch_enabled") if sim else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, sim.target_policy, "live_posting_allowed") if sim else 0

    issues = validate_source(sim, source_items, guard_before, guard_after, policy_enabled_before, policy_enabled_after, policy_live_before, policy_live_after, config)
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
    evidence = build_evidence(sim, guard_before, guard_after, policy_enabled_before, policy_enabled_after, policy_live_before, policy_live_after)
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
    items = build_freeze_items(sim, source_items, issues, ack_ok)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    allowed = int(ack_ok and item_summary["blocker_count"] == 0 and bool(sim) and all_blocked_verified and no_new_movement and policy_preserved)
    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Frozen" if allowed else "Needs Review",
        "freeze_status": "Runtime Watch Violation Simulation Evidence Frozen" if allowed else "Needs Review",
        "freeze_completed": allowed,
        "simulation_evidence_frozen": allowed,
        "all_runtime_violations_blocked_verified": all_blocked_verified,
        "ready_for_runtime_watch_governance_closeout": allowed,
        "simulation_only_verified": 1,
        "no_new_accounting_movement_verified": no_new_movement,
        "policy_state_preserved_verified": policy_preserved,
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": 0,
        "phase10p_simulation_verified": 1 if sim else 0,
        "phase10o_runtime_watch_verified": 1 if sim else 0,
        "phase10n_baseline_verified": 1 if sim else 0,
        "phase10m_closeout_verified": 1 if sim else 0,
        "controlled_policy_enabled_verified": int(policy_enabled_after == 1),
        "live_posting_blocked_verified": int(policy_live_after == 0),
        **evidence,
        "freeze_score": score,
        **item_summary,
        "items": items,
        "source_items": source_items,
        "issues": issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "required_acknowledgement": FREEZE_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 10Q freezes Phase 10P runtime watch violation simulation evidence only. No accounting movement or policy mutation is performed.",
    }

    if int(dry_run or 0):
        result.update({"status": "Needs Review", "freeze_status": "Needs Review", "freeze_completed": 0, "simulation_evidence_frozen": 0, "ready_for_runtime_watch_governance_closeout": 0})
        return result

    doc = frappe.new_doc(FREEZE_DOCTYPE)
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
    doc.scenario_json = safe_json(source_items)
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    create_items(doc, items)
    frappe.db.commit()
    return {**result, "created": True, "freeze": doc.name, "freeze_id": doc.freeze_id, "guardrails_after": guardrails()}


@frappe.whitelist()
def cancel_runtime_watch_violation_simulation_freeze_audit(freeze, reason=None):
    assert_action("cancel_runtime_watch_violation_simulation_freeze_audit")
    if not frappe.db.exists(FREEZE_DOCTYPE, freeze):
        frappe.throw(_("Runtime watch violation simulation freeze audit not found: {0}").format(freeze))
    doc = frappe.get_doc(FREEZE_DOCTYPE, freeze)
    if doc.status == "Cancelled":
        return {"freeze": freeze, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.freeze_completed or 0):
        frappe.throw(_("Cannot cancel a completed Phase 10Q freeze record."))
    frappe.db.set_value(
        FREEZE_DOCTYPE,
        freeze,
        {
            "status": "Cancelled",
            "freeze_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 10Q no-ack freeze audit cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{FREEZE_ITEM_DOCTYPE}` SET status = 'Cancelled' WHERE freeze = %(freeze)s", {"freeze": freeze})
    frappe.db.commit()
    return {"freeze": freeze, "status": "Cancelled", "note": "No-ack freeze audit cancelled only. No accounting or policy movement occurred."}


@frappe.whitelist()
def quick_runtime_watch_violation_simulation_freeze_summary(limit=20):
    freezes = frappe.get_all(
        FREEZE_DOCTYPE,
        fields=[
            "name",
            "freeze_id",
            "status",
            "freeze_status",
            "freeze_completed",
            "simulation_evidence_frozen",
            "all_runtime_violations_blocked_verified",
            "ready_for_runtime_watch_governance_closeout",
            "simulation",
            "runtime_watch",
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
            "freeze_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(
        FREEZE_ITEM_DOCTYPE,
        fields=["name", "freeze", "status", "severity", "category", "check_key", "check_label", "detail", "source_doctype", "source_name"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "freezes": freezes,
        "items": items,
        "required_acknowledgement": FREEZE_ACK,
        "guardrails": guardrails(),
        "note": "Phase 10Q freeze summary. Frozen evidence proves all Phase 10P violation simulations were blocked.",
    }


def execute_freeze_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("status"):
        conditions.append("f.status = %(status)s")
        params["status"] = filters.get("status")
    data = frappe.db.sql(
        f"""
        SELECT
            f.name AS freeze, f.freeze_id, f.status, f.freeze_status,
            f.freeze_completed, f.simulation_evidence_frozen,
            f.all_runtime_violations_blocked_verified,
            f.ready_for_runtime_watch_governance_closeout,
            f.simulation, f.runtime_watch, f.baseline,
            f.violation_simulation_count, f.blocked_violation_count,
            f.failed_violation_count, f.over_line_violation_blocked,
            f.over_amount_violation_blocked, f.over_payment_entry_violation_blocked,
            f.live_posting_violation_blocked,
            f.journal_entry_side_effect_violation_blocked,
            f.purchase_invoice_side_effect_violation_blocked,
            f.production_batch_enabled_policy_count_after,
            f.live_posting_allowed_policy_count_after,
            f.payment_entry_count_before, f.payment_entry_count_after,
            f.payment_entry_gl_count_before, f.payment_entry_gl_count_after,
            f.submitted_journal_entry_count_today, f.purchase_invoice_count_today,
            f.freeze_score, f.checked_on
        FROM `tab{FREEZE_DOCTYPE}` f
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
                {"name": "Blocked Violations", "values": [int(row.blocked_violation_count or 0) for row in data[:20]]},
                {"name": "Failed Violations", "values": [int(row.failed_violation_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Freezes"), "datatype": "Int"},
        {"value": sum(int(row.freeze_completed or 0) for row in data), "indicator": "Green", "label": _("Frozen"), "datatype": "Int"},
        {"value": sum(int(row.blocked_violation_count or 0) for row in data), "indicator": "Green", "label": _("Blocked Violations"), "datatype": "Int"},
        {"value": sum(int(row.failed_violation_count or 0) for row in data), "indicator": "Red", "label": _("Failed Violations"), "datatype": "Int"},
    ]
    return freeze_columns(), data, None, chart, summary


def freeze_columns():
    return [
        {"fieldname": "freeze", "label": _("Freeze"), "fieldtype": "Link", "options": FREEZE_DOCTYPE, "width": 220},
        {"fieldname": "freeze_id", "label": _("Freeze ID"), "fieldtype": "Data", "width": 410},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "freeze_status", "label": _("Freeze Status"), "fieldtype": "Data", "width": 360},
        {"fieldname": "freeze_completed", "label": _("Frozen"), "fieldtype": "Check", "width": 80},
        {"fieldname": "simulation_evidence_frozen", "label": _("Evidence Frozen"), "fieldtype": "Check", "width": 115},
        {"fieldname": "all_runtime_violations_blocked_verified", "label": _("All Blocked"), "fieldtype": "Check", "width": 95},
        {"fieldname": "ready_for_runtime_watch_governance_closeout", "label": _("Ready Closeout"), "fieldtype": "Check", "width": 115},
        {"fieldname": "simulation", "label": _("Simulation"), "fieldtype": "Link", "options": SIM_DOCTYPE, "width": 220},
        {"fieldname": "runtime_watch", "label": _("Runtime Watch"), "fieldtype": "Link", "options": "NDIS Controlled Limited Ops Runtime Watch", "width": 220},
        {"fieldname": "baseline", "label": _("Baseline"), "fieldtype": "Link", "options": "NDIS Controlled Limited Ops Baseline", "width": 220},
        {"fieldname": "violation_simulation_count", "label": _("Scenarios"), "fieldtype": "Int", "width": 90},
        {"fieldname": "blocked_violation_count", "label": _("Blocked"), "fieldtype": "Int", "width": 90},
        {"fieldname": "failed_violation_count", "label": _("Failed"), "fieldtype": "Int", "width": 90},
        {"fieldname": "over_line_violation_blocked", "label": _("Over Line"), "fieldtype": "Check", "width": 90},
        {"fieldname": "over_amount_violation_blocked", "label": _("Over Amount"), "fieldtype": "Check", "width": 105},
        {"fieldname": "over_payment_entry_violation_blocked", "label": _("Over PE"), "fieldtype": "Check", "width": 90},
        {"fieldname": "live_posting_violation_blocked", "label": _("Live"), "fieldtype": "Check", "width": 70},
        {"fieldname": "journal_entry_side_effect_violation_blocked", "label": _("JE Side"), "fieldtype": "Check", "width": 90},
        {"fieldname": "purchase_invoice_side_effect_violation_blocked", "label": _("PI Side"), "fieldtype": "Check", "width": 90},
        {"fieldname": "production_batch_enabled_policy_count_after", "label": _("Enabled Policies"), "fieldtype": "Int", "width": 125},
        {"fieldname": "live_posting_allowed_policy_count_after", "label": _("Live Policies"), "fieldtype": "Int", "width": 105},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 110},
        {"fieldname": "submitted_journal_entry_count_today", "label": _("JE Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "purchase_invoice_count_today", "label": _("PI Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "freeze_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("freeze"):
        conditions.append("i.freeze = %(freeze)s")
        params["freeze"] = filters.get("freeze")
    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")
    data = frappe.db.sql(
        f"""
        SELECT i.name AS item, i.freeze, i.status, i.severity, i.category,
               i.check_key, i.check_label, i.detail, i.source_doctype,
               i.source_name, i.checked_on
        FROM `tab{FREEZE_ITEM_DOCTYPE}` i
        {build_where(conditions)}
        ORDER BY CASE i.status WHEN 'Blocker' THEN 1 WHEN 'Warning' THEN 2 WHEN 'Pass' THEN 3 WHEN 'Info' THEN 4 ELSE 5 END, i.creation DESC
        """,
        params,
        as_dict=True,
    )
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": FREEZE_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "freeze", "label": _("Freeze"), "fieldtype": "Link", "options": FREEZE_DOCTYPE, "width": 220},
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
        {"value": len([row for row in data if row.category == "Frozen Violation"]), "indicator": "Green", "label": _("Frozen Violations"), "datatype": "Int"},
    ]
    return columns, data, None, {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Items", "values": list(chart_map.values())}]}, "type": "bar"}, summary


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
