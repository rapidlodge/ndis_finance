import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


FREEZE_ACK = "I_CONFIRM_PHASE9W_FREEZE_LIMITED_BATCH_RUNTIME_GUARD_EVIDENCE_NO_POSTING"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"


def make_freeze_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-LIMITED-BATCH-RUNTIME-GUARD-FREEZE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_runtime_guard():
    rows = frappe.get_all(
        "NDIS Limited Batch Runtime Guard",
        filters={
            "status": "Guarded",
            "runtime_guard_active": 1,
            "ready_for_guarded_limited_batch_runtime": 1,
            "runtime_validation_ready": 1,
            "phase9u_monitor_gate_verified": 1,
            "phase9t_freeze_verified": 1,
            "phase9s_enablement_verified": 1,
            "phase9r_readiness_gate_verified": 1,
            "policy_caps_verified": 1,
            "controlled_policy_enabled_verified": 1,
            "live_posting_blocked_verified": 1,
            "no_accounting_movement_verified": 1,
            "current_target_policy_enabled": 1,
            "current_target_policy_live": 0,
            "actual_enabled_policy_count": 1,
            "max_batch_lines": 3,
            "max_payment_entry_count": 1,
            "runtime_guard_allows_line_count_check": 1,
            "runtime_guard_allows_amount_check": 1,
            "runtime_guard_allows_payment_entry_count_check": 1,
            "runtime_guard_blocks_live_posting": 1,
            "runtime_guard_blocks_je_pi_side_effects": 1,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
            "production_batch_enabled_policy_count": 1,
            "live_posting_allowed_policy_count": 0,
        },
        fields=[
            "name",
            "runtime_guard_id",
            "monitor_gate",
            "policy_enablement_freeze",
            "enablement_run",
            "readiness_gate",
            "target_policy_doctype",
            "target_policy",
            "target_policy_name",
            "enablement_field",
            "live_field",
            "current_target_policy_enabled",
            "current_target_policy_live",
            "actual_enabled_policy_count",
            "max_batch_lines",
            "max_batch_amount",
            "max_payment_entry_count",
            "runtime_guard_allows_line_count_check",
            "runtime_guard_allows_amount_check",
            "runtime_guard_allows_payment_entry_count_check",
            "runtime_guard_blocks_live_posting",
            "runtime_guard_blocks_je_pi_side_effects",
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
            "guard_score",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )

    if not rows:
        return None

    runtime_guard = rows[0]
    if flt(runtime_guard.max_batch_amount or 0, 2) != 3:
        return None

    return runtime_guard


def existing_frozen_record(runtime_guard):
    rows = frappe.get_all(
        "NDIS Limited Batch Runtime Guard Evidence Freeze",
        filters={
            "runtime_guard": runtime_guard,
            "status": "Frozen",
            "runtime_guard_freeze_allowed": 1,
            "ready_for_guarded_runtime_monitoring": 1,
        },
        fields=["name", "freeze_id"],
        limit=1,
    )
    return rows[0] if rows else None


def validate_source(runtime_guard, guard, config):
    issues = []

    if config["production_mode"]:
        issues.append("Production mode config must remain disabled for Phase 9W.")

    if config["live_pe_enabled"]:
        issues.append("Live Payment Entry posting config must remain disabled for Phase 9W.")

    if not runtime_guard:
        issues.append("No active Phase 9V runtime guard found.")
        return issues

    existing = existing_frozen_record(runtime_guard.name)
    if existing:
        issues.append(f"Phase 9W runtime guard evidence freeze already exists: {existing.freeze_id}")

    required_links = {
        "monitor_gate": runtime_guard.monitor_gate,
        "policy_enablement_freeze": runtime_guard.policy_enablement_freeze,
        "enablement_run": runtime_guard.enablement_run,
        "readiness_gate": runtime_guard.readiness_gate,
    }

    for label, value in required_links.items():
        if not value:
            issues.append(f"Missing evidence link: {label}")

    if runtime_guard.monitor_gate and not frappe.db.exists("NDIS Limited Production Batch Use Monitor Gate", runtime_guard.monitor_gate):
        issues.append("Linked Phase 9U monitor gate does not exist.")

    if runtime_guard.policy_enablement_freeze and not frappe.db.exists("NDIS Limited Production Batch Policy Enablement Freeze", runtime_guard.policy_enablement_freeze):
        issues.append("Linked Phase 9T policy enablement freeze does not exist.")

    if runtime_guard.enablement_run and not frappe.db.exists("NDIS Limited Production Batch Policy Enablement Run", runtime_guard.enablement_run):
        issues.append("Linked Phase 9S enablement run does not exist.")

    if runtime_guard.readiness_gate and not frappe.db.exists("NDIS Limited Production Batch Enablement Readiness Gate", runtime_guard.readiness_gate):
        issues.append("Linked Phase 9R readiness gate does not exist.")

    if not runtime_guard.target_policy:
        issues.append("Runtime guard has no target policy.")
    elif not frappe.db.exists(POLICY_DOCTYPE, runtime_guard.target_policy):
        issues.append(f"Target policy does not exist: {runtime_guard.target_policy}")
    else:
        current_enabled = get_flag(POLICY_DOCTYPE, runtime_guard.target_policy, "production_batch_enabled")
        current_live = get_flag(POLICY_DOCTYPE, runtime_guard.target_policy, "live_posting_allowed")

        if current_enabled != 1:
            issues.append("Current target policy production_batch_enabled must be 1 before Phase 9W freeze.")

        if current_live != 0:
            issues.append("Current target policy live_posting_allowed must be 0 before Phase 9W freeze.")

    if int(runtime_guard.current_target_policy_enabled or 0) != 1:
        issues.append("Runtime guard current_target_policy_enabled must be 1.")

    if int(runtime_guard.current_target_policy_live or 0) != 0:
        issues.append("Runtime guard current_target_policy_live must be 0.")

    if int(runtime_guard.actual_enabled_policy_count or 0) != 1:
        issues.append("Runtime guard actual_enabled_policy_count must be 1.")

    if int(runtime_guard.max_batch_lines or 0) != 3:
        issues.append("Runtime guard max_batch_lines must be 3.")

    if flt(runtime_guard.max_batch_amount or 0, 2) != 3:
        issues.append("Runtime guard max_batch_amount must be 3.00.")

    if int(runtime_guard.max_payment_entry_count or 0) != 1:
        issues.append("Runtime guard max_payment_entry_count must be 1.")

    required_guard_flags = {
        "runtime_guard_allows_line_count_check": runtime_guard.runtime_guard_allows_line_count_check,
        "runtime_guard_allows_amount_check": runtime_guard.runtime_guard_allows_amount_check,
        "runtime_guard_allows_payment_entry_count_check": runtime_guard.runtime_guard_allows_payment_entry_count_check,
        "runtime_guard_blocks_live_posting": runtime_guard.runtime_guard_blocks_live_posting,
        "runtime_guard_blocks_je_pi_side_effects": runtime_guard.runtime_guard_blocks_je_pi_side_effects,
    }

    for label, value in required_guard_flags.items():
        if int(value or 0) != 1:
            issues.append(f"Runtime guard flag must be 1: {label}")

    if int(runtime_guard.actual_payment_entry_created_count or 0) != 0:
        issues.append("Runtime guard actual Payment Entry created count must be 0.")

    if int(runtime_guard.actual_gl_created_count or 0) != 0:
        issues.append("Runtime guard actual GL created count must be 0.")

    if int(runtime_guard.payment_entry_count_before or 0) != int(runtime_guard.payment_entry_count_after or 0):
        issues.append("Runtime guard Payment Entry count changed.")

    if int(runtime_guard.payment_entry_gl_count_before or 0) != int(runtime_guard.payment_entry_gl_count_after or 0):
        issues.append("Runtime guard Payment Entry GL count changed.")

    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must be enabled before Phase 9W freeze.")

    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must be 0 before Phase 9W freeze.")

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


def build_items(runtime_guard, issues, ack_ok, guard):
    items = []

    if runtime_guard:
        add_item(
            items,
            "Pass",
            "Low",
            "Runtime Guard",
            "phase9v_runtime_guard_exists",
            "Phase 9V runtime guard exists",
            f"Runtime guard found: {runtime_guard.runtime_guard_id}.",
            "NDIS Limited Batch Runtime Guard",
            runtime_guard.name,
        )
    else:
        add_item(items, "Blocker", "Critical", "Runtime Guard", "phase9v_runtime_guard_exists", "Phase 9V runtime guard exists", "No active Phase 9V runtime guard found.")

    if not issues:
        add_item(items, "Pass", "Low", "Freeze Source", "freeze_source_valid", "Freeze source valid", "Runtime guard evidence is valid for freeze.")
    else:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Freeze Source", "freeze_source_valid", "Freeze source valid", issue)

    if guard["production_batch_enabled_policy_count"] == 1 and guard["live_posting_allowed_policy_count"] == 0:
        add_item(items, "Pass", "Low", "Policy Guardrail", "policy_state", "Policy state correct", "Exactly one controlled policy is enabled and live posting remains blocked.")
    else:
        add_item(items, "Blocker", "Critical", "Policy Guardrail", "policy_state", "Policy state correct", "Policy state is not 1 enabled / 0 live.")

    if runtime_guard:
        add_item(items, "Pass", "Low", "Frozen Cap", "max_lines", "Max lines frozen", f"Frozen line cap: {runtime_guard.max_batch_lines}.")
        add_item(items, "Pass", "Low", "Frozen Cap", "max_amount", "Max amount frozen", f"Frozen amount cap: {flt(runtime_guard.max_batch_amount or 0, 2):.2f}.")
        add_item(items, "Pass", "Low", "Frozen Cap", "max_payment_entry_count", "Max Payment Entry count frozen", f"Frozen Payment Entry cap: {runtime_guard.max_payment_entry_count}.")
        add_item(items, "Pass", "Low", "Runtime Flags", "runtime_guard_flags", "Runtime guard flags frozen", "Line, amount, PE count, live-posting block, and JE/PI side-effect block flags are frozen.")
        add_item(items, "Pass", "Low", "Accounting Guardrail", "no_accounting_movement", "No accounting movement", "Payment Entry and Payment Entry GL counts stayed unchanged.")

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
    score = 100
    score -= int(blockers or 0) * 25
    score -= int(warnings or 0) * 5
    return max(0, round(score, 2))


def create_items(doc, items):
    for item in items:
        row = frappe.new_doc("NDIS Limited Batch Runtime Guard Evidence Item")
        row.evidence_freeze = doc.name
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
def run_limited_batch_runtime_guard_evidence_freeze(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_limited_batch_runtime_guard_evidence_freeze")

    runtime_guard = latest_runtime_guard()
    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }
    guard_before = guardrails()
    ack_ok = acknowledgement == FREEZE_ACK
    issues = validate_source(runtime_guard, guard_before, config)
    items = build_items(runtime_guard, issues, ack_ok, guard_before)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    allowed = int(ack_ok and item_summary["blocker_count"] == 0 and bool(runtime_guard))
    guard_now = guardrails()

    current_enabled = get_flag(POLICY_DOCTYPE, runtime_guard.target_policy, "production_batch_enabled") if runtime_guard else 0
    current_live = get_flag(POLICY_DOCTYPE, runtime_guard.target_policy, "live_posting_allowed") if runtime_guard else 0

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Frozen" if allowed else "Needs Review",
        "freeze_status": "Runtime Guard Evidence Frozen" if allowed else "Needs Review",
        "runtime_guard_freeze_allowed": allowed,
        "ready_for_guarded_runtime_monitoring": allowed,
        "phase9v_runtime_guard_verified": 1 if runtime_guard else 0,
        "phase9u_monitor_gate_verified": 1 if runtime_guard and runtime_guard.monitor_gate else 0,
        "phase9t_freeze_verified": 1 if runtime_guard and runtime_guard.policy_enablement_freeze else 0,
        "phase9s_enablement_verified": 1 if runtime_guard and runtime_guard.enablement_run else 0,
        "phase9r_readiness_gate_verified": 1 if runtime_guard and runtime_guard.readiness_gate else 0,
        "policy_caps_verified": 1 if runtime_guard and int(runtime_guard.max_batch_lines or 0) == 3 and flt(runtime_guard.max_batch_amount or 0, 2) == 3 and int(runtime_guard.max_payment_entry_count or 0) == 1 else 0,
        "controlled_policy_enabled_verified": 1 if current_enabled == 1 else 0,
        "live_posting_blocked_verified": 1 if current_live == 0 else 0,
        "runtime_guard_active_verified": 1 if runtime_guard else 0,
        "runtime_validation_ready_verified": 1 if runtime_guard else 0,
        "no_accounting_movement_verified": 1 if runtime_guard and int(runtime_guard.payment_entry_count_before or 0) == int(runtime_guard.payment_entry_count_after or 0) and int(runtime_guard.payment_entry_gl_count_before or 0) == int(runtime_guard.payment_entry_gl_count_after or 0) else 0,
        "production_batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "policy_live_enabled": 0,
        "runtime_guard": runtime_guard.name if runtime_guard else None,
        "monitor_gate": runtime_guard.monitor_gate if runtime_guard else None,
        "policy_enablement_freeze": runtime_guard.policy_enablement_freeze if runtime_guard else None,
        "enablement_run": runtime_guard.enablement_run if runtime_guard else None,
        "readiness_gate": runtime_guard.readiness_gate if runtime_guard else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": runtime_guard.target_policy if runtime_guard else None,
        "target_policy_name": runtime_guard.target_policy_name if runtime_guard else None,
        "enablement_field": "production_batch_enabled",
        "live_field": "live_posting_allowed",
        "current_target_policy_enabled": current_enabled,
        "current_target_policy_live": current_live,
        "actual_enabled_policy_count": int(runtime_guard.actual_enabled_policy_count or 0) if runtime_guard else 0,
        "max_batch_lines": int(runtime_guard.max_batch_lines or 0) if runtime_guard else 0,
        "max_batch_amount": flt(runtime_guard.max_batch_amount or 0) if runtime_guard else 0,
        "max_payment_entry_count": int(runtime_guard.max_payment_entry_count or 0) if runtime_guard else 0,
        "runtime_guard_allows_line_count_check": int(runtime_guard.runtime_guard_allows_line_count_check or 0) if runtime_guard else 0,
        "runtime_guard_allows_amount_check": int(runtime_guard.runtime_guard_allows_amount_check or 0) if runtime_guard else 0,
        "runtime_guard_allows_payment_entry_count_check": int(runtime_guard.runtime_guard_allows_payment_entry_count_check or 0) if runtime_guard else 0,
        "runtime_guard_blocks_live_posting": int(runtime_guard.runtime_guard_blocks_live_posting or 0) if runtime_guard else 0,
        "runtime_guard_blocks_je_pi_side_effects": int(runtime_guard.runtime_guard_blocks_je_pi_side_effects or 0) if runtime_guard else 0,
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
        "freeze_score": score,
        **item_summary,
        "items": items,
        "issues": issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_now,
        "config": config,
        "required_acknowledgement": FREEZE_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 9W freezes Phase 9V runtime guard evidence only. It creates no PE/GL and does not change policy flags.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["freeze_status"] = "Needs Review"
        result["runtime_guard_freeze_allowed"] = 0
        result["ready_for_guarded_runtime_monitoring"] = 0
        return result

    doc = frappe.new_doc("NDIS Limited Batch Runtime Guard Evidence Freeze")
    doc.freeze_id = make_freeze_id()
    doc.status = result["status"]
    doc.freeze_status = result["freeze_status"]

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

    create_items(doc, items)
    frappe.db.commit()

    return {
        **result,
        "created": True,
        "runtime_guard_evidence_freeze": doc.name,
        "freeze_id": doc.freeze_id,
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_limited_batch_runtime_guard_evidence_freeze(runtime_guard_evidence_freeze, reason=None):
    assert_action("cancel_limited_batch_runtime_guard_evidence_freeze")

    if not frappe.db.exists("NDIS Limited Batch Runtime Guard Evidence Freeze", runtime_guard_evidence_freeze):
        frappe.throw(_("Runtime guard evidence freeze not found: {0}").format(runtime_guard_evidence_freeze))

    doc = frappe.get_doc("NDIS Limited Batch Runtime Guard Evidence Freeze", runtime_guard_evidence_freeze)

    if doc.status == "Cancelled":
        return {"runtime_guard_evidence_freeze": runtime_guard_evidence_freeze, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.runtime_guard_freeze_allowed or 0):
        frappe.throw(_("Cannot cancel a frozen Phase 9W evidence record. Create a superseding freeze instead."))

    frappe.db.set_value(
        "NDIS Limited Batch Runtime Guard Evidence Freeze",
        runtime_guard_evidence_freeze,
        {
            "status": "Cancelled",
            "freeze_status": "Cancelled",
            "runtime_guard_freeze_allowed": 0,
            "ready_for_guarded_runtime_monitoring": 0,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 9W no-ack runtime guard evidence freeze audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        """
        UPDATE `tabNDIS Limited Batch Runtime Guard Evidence Item`
        SET status = 'Cancelled'
        WHERE evidence_freeze = %(runtime_guard_evidence_freeze)s
        """,
        {"runtime_guard_evidence_freeze": runtime_guard_evidence_freeze},
    )
    frappe.db.commit()

    return {
        "runtime_guard_evidence_freeze": runtime_guard_evidence_freeze,
        "status": "Cancelled",
        "note": "No-ack freeze audit cancelled only. No policy or accounting movement occurred.",
    }


@frappe.whitelist()
def quick_limited_batch_runtime_guard_evidence_freeze_summary(limit=20):
    freezes = frappe.get_all(
        "NDIS Limited Batch Runtime Guard Evidence Freeze",
        fields=[
            "name",
            "freeze_id",
            "status",
            "freeze_status",
            "runtime_guard_freeze_allowed",
            "ready_for_guarded_runtime_monitoring",
            "runtime_guard",
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
            "runtime_guard_allows_line_count_check",
            "runtime_guard_allows_amount_check",
            "runtime_guard_allows_payment_entry_count_check",
            "runtime_guard_blocks_live_posting",
            "runtime_guard_blocks_je_pi_side_effects",
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

    items = frappe.get_all(
        "NDIS Limited Batch Runtime Guard Evidence Item",
        fields=[
            "name",
            "evidence_freeze",
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
        "freezes": freezes,
        "items": items,
        "required_acknowledgement": FREEZE_ACK,
        "guardrails": guardrails(),
        "note": "Phase 9W runtime guard evidence freeze summary. No PE/GL or policy movement.",
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
            f.runtime_guard_freeze_allowed,
            f.ready_for_guarded_runtime_monitoring,
            f.runtime_guard,
            f.monitor_gate,
            f.policy_enablement_freeze,
            f.target_policy,
            f.current_target_policy_enabled,
            f.current_target_policy_live,
            f.actual_enabled_policy_count,
            f.max_batch_lines,
            f.max_batch_amount,
            f.max_payment_entry_count,
            f.runtime_guard_allows_line_count_check,
            f.runtime_guard_allows_amount_check,
            f.runtime_guard_allows_payment_entry_count_check,
            f.runtime_guard_blocks_live_posting,
            f.runtime_guard_blocks_je_pi_side_effects,
            f.actual_payment_entry_created_count,
            f.actual_gl_created_count,
            f.production_batch_enabled_policy_count,
            f.live_posting_allowed_policy_count,
            f.freeze_score,
            f.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Limited Batch Runtime Guard Evidence Freeze` f
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
                {"name": "Frozen", "values": [int(row.runtime_guard_freeze_allowed or 0) for row in data[:20]]},
                {"name": "Live Policies", "values": [int(row.live_posting_allowed_policy_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Runtime Guard Freezes"), "datatype": "Int"},
        {"value": sum(int(row.runtime_guard_freeze_allowed or 0) for row in data), "indicator": "Green", "label": _("Frozen"), "datatype": "Int"},
        {"value": sum(int(row.production_batch_enabled_policy_count or 0) for row in data), "indicator": "Green", "label": _("Enabled Policies"), "datatype": "Int"},
        {"value": sum(int(row.live_posting_allowed_policy_count or 0) for row in data), "indicator": "Red", "label": _("Live Policies"), "datatype": "Int"},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PE"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def freeze_columns():
    return [
        {"fieldname": "evidence_freeze", "label": _("Evidence Freeze"), "fieldtype": "Link", "options": "NDIS Limited Batch Runtime Guard Evidence Freeze", "width": 220},
        {"fieldname": "freeze_id", "label": _("Freeze ID"), "fieldtype": "Data", "width": 430},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "freeze_status", "label": _("Freeze Status"), "fieldtype": "Data", "width": 300},
        {"fieldname": "runtime_guard_freeze_allowed", "label": _("Frozen"), "fieldtype": "Check", "width": 80},
        {"fieldname": "ready_for_guarded_runtime_monitoring", "label": _("Ready Monitoring"), "fieldtype": "Check", "width": 130},
        {"fieldname": "runtime_guard", "label": _("Runtime Guard"), "fieldtype": "Link", "options": "NDIS Limited Batch Runtime Guard", "width": 220},
        {"fieldname": "monitor_gate", "label": _("Monitor Gate"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Use Monitor Gate", "width": 220},
        {"fieldname": "target_policy", "label": _("Target Policy"), "fieldtype": "Data", "width": 260},
        {"fieldname": "current_target_policy_enabled", "label": _("Current Enabled"), "fieldtype": "Check", "width": 120},
        {"fieldname": "current_target_policy_live", "label": _("Current Live"), "fieldtype": "Check", "width": 110},
        {"fieldname": "max_batch_lines", "label": _("Max Lines"), "fieldtype": "Int", "width": 90},
        {"fieldname": "max_batch_amount", "label": _("Max Amount"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "max_payment_entry_count", "label": _("Max PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "runtime_guard_allows_line_count_check", "label": _("Line Check"), "fieldtype": "Check", "width": 90},
        {"fieldname": "runtime_guard_allows_amount_check", "label": _("Amount Check"), "fieldtype": "Check", "width": 105},
        {"fieldname": "runtime_guard_allows_payment_entry_count_check", "label": _("PE Check"), "fieldtype": "Check", "width": 90},
        {"fieldname": "runtime_guard_blocks_live_posting", "label": _("Block Live"), "fieldtype": "Check", "width": 90},
        {"fieldname": "runtime_guard_blocks_je_pi_side_effects", "label": _("Block JE/PI"), "fieldtype": "Check", "width": 100},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "production_batch_enabled_policy_count", "label": _("Enabled Policies"), "fieldtype": "Int", "width": 120},
        {"fieldname": "live_posting_allowed_policy_count", "label": _("Live Policies"), "fieldtype": "Int", "width": 110},
        {"fieldname": "freeze_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    if filters.get("evidence_freeze"):
        conditions.append("i.evidence_freeze = %(evidence_freeze)s")
        params["evidence_freeze"] = filters.get("evidence_freeze")

    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": "NDIS Limited Batch Runtime Guard Evidence Item", "width": 220},
        {"fieldname": "evidence_freeze", "label": _("Evidence Freeze"), "fieldtype": "Link", "options": "NDIS Limited Batch Runtime Guard Evidence Freeze", "width": 220},
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
            i.evidence_freeze,
            i.status,
            i.severity,
            i.category,
            i.check_label,
            i.detail,
            i.source_doctype,
            i.source_name,
            i.checked_on
        FROM `tabNDIS Limited Batch Runtime Guard Evidence Item` i
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
