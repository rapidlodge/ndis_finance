import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


PRE_EXEC_ACK = "I_CONFIRM_PHASE10T_APPROVE_ONE_GOVERNED_LIMITED_OPERATION_PRE_EXECUTION_GATE_NO_POSTING"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
READINESS_DOCTYPE = "NDIS Governed Limited Ops Readiness"
GATE_DOCTYPE = "NDIS Governed Limited Op Pre Exec"
GATE_ITEM_DOCTYPE = "NDIS Governed Limited Op Pre Exec Item"


def make_pre_execution_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-GOVERNED-LIMITED-OP-PRE-EXEC-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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
    return count_dt(POLICY_DOCTYPE, {"production_batch_enabled": 1}) if has_column(POLICY_DOCTYPE, "production_batch_enabled") else 0


def live_posting_allowed_policy_count():
    return count_dt(POLICY_DOCTYPE, {"live_posting_allowed": 1}) if has_column(POLICY_DOCTYPE, "live_posting_allowed") else 0


def guardrails():
    return {
        "payment_entry_count": count_dt("Payment Entry"),
        "payment_entry_gl_count": count_dt("GL Entry", {"voucher_type": "Payment Entry"}),
        "submitted_journal_entry_count_today": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}),
        "purchase_invoice_count_today": count_dt("Purchase Invoice", {"creation": [">=", today()]}),
        "production_batch_enabled_policy_count": production_batch_enabled_policy_count(),
        "live_posting_allowed_policy_count": live_posting_allowed_policy_count(),
    }


def latest_readiness():
    rows = frappe.get_all(
        READINESS_DOCTYPE,
        filters={
            "status": "Readiness Approved",
            "readiness_status": "Governed Controlled Limited Operations Ready",
            "readiness_approved": 1,
            "governed_controlled_limited_operations_ready": 1,
            "ready_for_governed_limited_operation_pre_execution_gate": 1,
            "runtime_watch_governance_closeout_verified": 1,
            "locked_runtime_limits_verified": 1,
            "live_posting_remains_blocked": 1,
            "journal_entry_side_effect_remains_blocked": 1,
            "purchase_invoice_side_effect_remains_blocked": 1,
            "policy_mutation_performed": 0,
            "actual_policy_mutation_count": 0,
            "target_policy_enabled_after": 1,
            "target_policy_live_after": 0,
            "max_batch_line_count": 3,
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
            "readiness_id",
            "governance_closeout",
            "freeze",
            "simulation",
            "runtime_watch",
            "baseline",
            "monitoring_register",
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
            "payment_entry_count_after",
            "payment_entry_gl_count_after",
            "readiness_score",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_pre_execution_gate(readiness):
    if not readiness:
        return None
    rows = frappe.get_all(
        GATE_DOCTYPE,
        filters={"readiness": readiness, "status": "Pre-Execution Approved", "pre_execution_approved": 1},
        fields=["name", "pre_execution_id"],
        limit=1,
    )
    return rows[0] if rows else None


def readiness_items(readiness):
    if not readiness:
        return []
    return frappe.get_all(
        "NDIS Governed Limited Ops Readiness Item",
        filters={"readiness": readiness},
        fields=["name", "status", "severity", "category", "check_key", "check_label", "detail", "source_doctype", "source_name"],
        order_by="creation asc",
    )


def build_requested_shape(readiness):
    return {
        "requested_batch_line_count": int(readiness.max_batch_line_count or 0) if readiness else 0,
        "requested_batch_amount": flt(readiness.max_batch_amount or 0, 2) if readiness else 0,
        "requested_payment_entry_count": int(readiness.max_payment_entry_count or 0) if readiness else 0,
        "requested_live_posting": 0,
        "requested_journal_entry_side_effect": 0,
        "requested_purchase_invoice_side_effect": 0,
    }


def validate_operation_shape(readiness, shape):
    issues = []
    if not readiness:
        return ["No Phase 10S readiness record available for operation shape validation."]
    checks = [
        (int(shape["requested_batch_line_count"] or 0) <= int(readiness.max_batch_line_count or 0), "Requested batch line count exceeds governed locked limit."),
        (flt(shape["requested_batch_amount"] or 0, 2) <= flt(readiness.max_batch_amount or 0, 2), "Requested batch amount exceeds governed locked limit."),
        (int(shape["requested_payment_entry_count"] or 0) <= int(readiness.max_payment_entry_count or 0), "Requested Payment Entry count exceeds governed locked limit."),
        (not int(shape["requested_live_posting"] or 0), "Requested live posting is not allowed."),
        (not int(shape["requested_journal_entry_side_effect"] or 0), "Requested Journal Entry side effect is not allowed."),
        (not int(shape["requested_purchase_invoice_side_effect"] or 0), "Requested Purchase Invoice side effect is not allowed."),
        (not int(readiness.live_posting_allowed or 0), "Readiness source has live posting allowed, which is invalid."),
        (not int(readiness.journal_entry_side_effect_allowed or 0), "Readiness source has Journal Entry side effect allowed, which is invalid."),
        (not int(readiness.purchase_invoice_side_effect_allowed or 0), "Readiness source has Purchase Invoice side effect allowed, which is invalid."),
    ]
    return [message for ok, message in checks if not ok]


def validate_source(readiness, source_items, guard, policy_enabled, policy_live, config):
    if not readiness:
        return ["No approved Phase 10S governed readiness found."]
    issues = []
    existing = existing_pre_execution_gate(readiness.name)
    if existing:
        issues.append(f"Phase 10T pre-execution gate already exists for this readiness record: {existing.pre_execution_id}")
    required_links = {
        "readiness": (READINESS_DOCTYPE, readiness.name),
        "governance_closeout": ("NDIS Runtime Watch Governance Closeout", readiness.governance_closeout),
        "freeze": ("NDIS Runtime Watch Violation Sim Freeze", readiness.freeze),
        "simulation": ("NDIS Runtime Watch Violation Sim", readiness.simulation),
        "runtime_watch": ("NDIS Controlled Limited Ops Runtime Watch", readiness.runtime_watch),
        "baseline": ("NDIS Controlled Limited Ops Baseline", readiness.baseline),
        "target_policy": (POLICY_DOCTYPE, readiness.target_policy),
    }
    for label, (doctype, name) in required_links.items():
        if not name:
            issues.append(f"Missing evidence link: {label}")
        elif not frappe.db.exists(doctype, name):
            issues.append(f"Linked evidence does not exist: {doctype} {name}")
    blockers = [row for row in source_items if row.status == "Blocker"]
    warnings = [row for row in source_items if row.status == "Warning"]
    if blockers:
        issues.append(f"Phase 10S readiness item blocker rows exist: {len(blockers)}")
    if warnings:
        issues.append(f"Phase 10S readiness item warning rows exist: {len(warnings)}")
    checks = [
        (int(readiness.max_batch_line_count or 0) == 3, "Readiness max batch line count must be 3."),
        (flt(readiness.max_batch_amount or 0, 2) == 3, "Readiness max batch amount must be 3.00."),
        (int(readiness.max_payment_entry_count or 0) == 1, "Readiness max Payment Entry count must be 1."),
        (policy_enabled == 1, "Target policy production_batch_enabled must be 1 before Phase 10T. Phase 10T must not repair this."),
        (policy_live == 0, "Target policy live_posting_allowed must be 0 before Phase 10T. Phase 10T must not repair this."),
        (guard["production_batch_enabled_policy_count"] == 1, "Exactly one controlled production batch policy must remain enabled."),
        (guard["live_posting_allowed_policy_count"] == 0, "Controlled production live allowed policy count must remain 0."),
        (guard["submitted_journal_entry_count_today"] == 0, "Submitted Journal Entry count today must remain 0."),
        (guard["purchase_invoice_count_today"] == 0, "Purchase Invoice count today must remain 0."),
        (int(config["production_mode"]) == 0, "Production mode config must remain 0."),
        (int(config["live_pe_enabled"]) == 0, "Live Payment Entry posting config must remain 0."),
    ]
    issues.extend(message for ok, message in checks if not ok)
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


def build_gate_items(readiness, source_items, source_issues, shape_issues, ack_ok, shape):
    items = []
    if readiness:
        add_item(items, "Pass", "Low", "Evidence", "phase10s_readiness_exists", "Phase 10S readiness exists", f"Readiness found: {readiness.readiness_id}.", READINESS_DOCTYPE, readiness.name)
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase10s_readiness_exists", "Phase 10S readiness exists", "No approved Phase 10S readiness found.")
    if source_issues:
        for issue in source_issues:
            add_item(items, "Blocker", "Critical", "Pre-Execution Source", "pre_execution_source_valid", "Pre-execution source valid", issue)
    else:
        add_item(items, "Pass", "Low", "Pre-Execution Source", "pre_execution_source_valid", "Pre-execution source valid", "Phase 10S readiness is valid for pre-execution gate.")
    if shape_issues:
        for issue in shape_issues:
            add_item(items, "Blocker", "Critical", "Operation Shape", "operation_shape_valid", "Operation shape valid", issue)
    else:
        add_item(items, "Pass", "High", "Operation Shape", "operation_shape_valid", "Operation shape valid", f"Shape validated: {shape['requested_batch_line_count']} lines / {shape['requested_batch_amount']} / {shape['requested_payment_entry_count']} Payment Entry.")
    for key, label, value in [
        ("live_posting_blocked", "Live posting remains blocked", shape["requested_live_posting"]),
        ("je_side_effect_blocked", "Journal Entry side effect remains blocked", shape["requested_journal_entry_side_effect"]),
        ("pi_side_effect_blocked", "Purchase Invoice side effect remains blocked", shape["requested_purchase_invoice_side_effect"]),
        ("pre_execution_only", "Pre-execution only: no posting", 0),
    ]:
        add_item(items, "Pass", "High", "Execution Blocks", key, label, f"value={value}")
    for row in source_items:
        if row.category in {"Readiness Chain", "Inherited Governance Evidence"}:
            add_item(items, "Pass", "Low", "Inherited Readiness Evidence", row.check_key, row.check_label, row.detail, row.source_doctype, row.source_name)
    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {PRE_EXEC_ACK}")
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
        row = frappe.new_doc(GATE_ITEM_DOCTYPE)
        row.pre_execution_gate = doc.name
        for key, value in item.items():
            if row.meta.has_field(key):
                setattr(row, key, value)
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


def build_evidence(readiness, guard_before, guard_after, policy_enabled_before, policy_enabled_after, policy_live_before, policy_live_after, shape):
    return {
        "readiness": readiness.name if readiness else None,
        "governance_closeout": readiness.governance_closeout if readiness else None,
        "freeze": readiness.freeze if readiness else None,
        "simulation": readiness.simulation if readiness else None,
        "runtime_watch": readiness.runtime_watch if readiness else None,
        "baseline": readiness.baseline if readiness else None,
        "monitoring_register": readiness.monitoring_register if readiness else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": readiness.target_policy if readiness else None,
        "target_policy_name": readiness.target_policy_name if readiness else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_before": policy_live_before,
        "target_policy_live_after": policy_live_after,
        "production_batch_enabled_policy_count_before": guard_before["production_batch_enabled_policy_count"],
        "production_batch_enabled_policy_count_after": guard_after["production_batch_enabled_policy_count"],
        "live_posting_allowed_policy_count_before": guard_before["live_posting_allowed_policy_count"],
        "live_posting_allowed_policy_count_after": guard_after["live_posting_allowed_policy_count"],
        "max_batch_line_count": int(readiness.max_batch_line_count or 0) if readiness else 0,
        "max_batch_amount": flt(readiness.max_batch_amount or 0, 2) if readiness else 0,
        "max_payment_entry_count": int(readiness.max_payment_entry_count or 0) if readiness else 0,
        "live_posting_allowed": int(readiness.live_posting_allowed or 0) if readiness else 0,
        "journal_entry_side_effect_allowed": int(readiness.journal_entry_side_effect_allowed or 0) if readiness else 0,
        "purchase_invoice_side_effect_allowed": int(readiness.purchase_invoice_side_effect_allowed or 0) if readiness else 0,
        **shape,
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
def run_governed_limited_op_pre_execution_gate(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_governed_limited_op_pre_execution_gate")
    readiness = latest_readiness()
    source_items = readiness_items(readiness.name) if readiness else []
    shape = build_requested_shape(readiness)
    guard_before = guardrails()
    ack_ok = acknowledgement == PRE_EXEC_ACK
    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }
    policy_enabled_before = get_flag(POLICY_DOCTYPE, readiness.target_policy, "production_batch_enabled") if readiness else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, readiness.target_policy, "live_posting_allowed") if readiness else 0
    guard_after = guardrails()
    policy_enabled_after = get_flag(POLICY_DOCTYPE, readiness.target_policy, "production_batch_enabled") if readiness else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, readiness.target_policy, "live_posting_allowed") if readiness else 0
    source_issues = validate_source(readiness, source_items, guard_before, policy_enabled_before, policy_live_before, config)
    shape_issues = validate_operation_shape(readiness, shape)
    no_new_movement = int(
        guard_before["payment_entry_count"] == guard_after["payment_entry_count"]
        and guard_before["payment_entry_gl_count"] == guard_after["payment_entry_gl_count"]
        and guard_before["submitted_journal_entry_count_today"] == guard_after["submitted_journal_entry_count_today"]
        and guard_before["purchase_invoice_count_today"] == guard_after["purchase_invoice_count_today"]
    )
    policy_preserved = int(
        policy_enabled_before == 1
        and policy_enabled_after == 1
        and policy_live_before == 0
        and policy_live_after == 0
        and guard_before["production_batch_enabled_policy_count"] == guard_after["production_batch_enabled_policy_count"]
        and guard_before["live_posting_allowed_policy_count"] == guard_after["live_posting_allowed_policy_count"]
    )
    if not no_new_movement:
        source_issues.append("Accounting movement changed while preparing Phase 10T pre-execution evidence.")
    evidence = build_evidence(readiness, guard_before, guard_after, policy_enabled_before, policy_enabled_after, policy_live_before, policy_live_after, shape)
    locked_limits_verified = int(
        evidence["max_batch_line_count"] == 3
        and flt(evidence["max_batch_amount"], 2) == 3
        and evidence["max_payment_entry_count"] == 1
        and evidence["live_posting_allowed"] == 0
        and evidence["journal_entry_side_effect_allowed"] == 0
        and evidence["purchase_invoice_side_effect_allowed"] == 0
    )
    shape_validated = int(not shape_issues and locked_limits_verified)
    items = build_gate_items(readiness, source_items, source_issues, shape_issues, ack_ok, shape)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    allowed = int(ack_ok and item_summary["blocker_count"] == 0 and readiness and shape_validated and no_new_movement and policy_preserved)
    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Pre-Execution Approved" if allowed else "Needs Review",
        "pre_execution_status": "Ready For One Governed Limited Operation" if allowed else "Needs Review",
        "pre_execution_approved": allowed,
        "ready_for_one_governed_limited_operation": allowed,
        "ready_for_governed_limited_operation_preview": allowed,
        "operation_shape_validated": shape_validated,
        "operation_shape_locked": allowed,
        "readiness_verified": 1 if readiness else 0,
        "locked_runtime_limits_verified": locked_limits_verified,
        "live_posting_remains_blocked": int(evidence["live_posting_allowed"] == 0 and shape["requested_live_posting"] == 0),
        "journal_entry_side_effect_remains_blocked": int(evidence["journal_entry_side_effect_allowed"] == 0 and shape["requested_journal_entry_side_effect"] == 0),
        "purchase_invoice_side_effect_remains_blocked": int(evidence["purchase_invoice_side_effect_allowed"] == 0 and shape["requested_purchase_invoice_side_effect"] == 0),
        "pre_execution_only_verified": 1,
        "no_new_accounting_movement_verified": no_new_movement,
        "policy_state_preserved_verified": policy_preserved,
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": 0,
        "phase10s_readiness_verified": 1 if readiness else 0,
        "phase10r_governance_closeout_verified": 1 if readiness else 0,
        "phase10q_freeze_verified": 1 if readiness else 0,
        "phase10p_simulation_verified": 1 if readiness else 0,
        "phase10o_runtime_watch_verified": 1 if readiness else 0,
        "phase10n_baseline_verified": 1 if readiness else 0,
        "controlled_policy_enabled_verified": int(policy_enabled_after == 1),
        "live_posting_blocked_verified": int(policy_live_after == 0),
        **evidence,
        "pre_execution_score": score,
        **item_summary,
        "items": items,
        "source_items": source_items,
        "source_issues": source_issues,
        "shape_issues": shape_issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "required_acknowledgement": PRE_EXEC_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 10T approves one governed limited operation pre-execution gate only. No accounting movement or policy mutation is performed.",
    }
    if int(dry_run or 0):
        result.update(
            {
                "status": "Needs Review",
                "pre_execution_status": "Needs Review",
                "pre_execution_approved": 0,
                "ready_for_one_governed_limited_operation": 0,
                "ready_for_governed_limited_operation_preview": 0,
                "operation_shape_locked": 0,
            }
        )
        return result
    doc = frappe.new_doc(GATE_DOCTYPE)
    doc.pre_execution_id = make_pre_execution_id()
    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = PRE_EXEC_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.evidence_json = safe_json({"evidence": evidence, "shape": shape, "source_items": source_items, "guardrails_before": guard_before, "guardrails_after": guard_after, "config": config})
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    create_items(doc, items)
    frappe.db.commit()
    return {**result, "created": True, "pre_execution_gate": doc.name, "pre_execution_id": doc.pre_execution_id, "guardrails_after": guardrails()}


@frappe.whitelist()
def cancel_governed_limited_op_pre_execution_gate_audit(pre_execution_gate, reason=None):
    assert_action("cancel_governed_limited_op_pre_execution_gate_audit")
    if not frappe.db.exists(GATE_DOCTYPE, pre_execution_gate):
        frappe.throw(_("Governed limited operation pre-execution gate audit not found: {0}").format(pre_execution_gate))
    doc = frappe.get_doc(GATE_DOCTYPE, pre_execution_gate)
    if doc.status == "Cancelled":
        return {"pre_execution_gate": pre_execution_gate, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.pre_execution_approved or 0):
        frappe.throw(_("Cannot cancel an approved Phase 10T pre-execution gate record."))
    frappe.db.set_value(
        GATE_DOCTYPE,
        pre_execution_gate,
        {"status": "Cancelled", "pre_execution_status": "Cancelled", "cancelled_on": now_datetime(), "cancelled_by": frappe.session.user, "summary_json": reason or "Phase 10T no-ack pre-execution audit cancelled."},
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{GATE_ITEM_DOCTYPE}` SET status = 'Cancelled' WHERE pre_execution_gate = %(pre_execution_gate)s", {"pre_execution_gate": pre_execution_gate})
    frappe.db.commit()
    return {"pre_execution_gate": pre_execution_gate, "status": "Cancelled", "note": "No-ack pre-execution audit cancelled only. No accounting or policy movement occurred."}


@frappe.whitelist()
def quick_governed_limited_op_pre_execution_gate_summary(limit=20):
    records = frappe.get_all(
        GATE_DOCTYPE,
        fields=[
            "name",
            "pre_execution_id",
            "status",
            "pre_execution_status",
            "pre_execution_approved",
            "ready_for_one_governed_limited_operation",
            "ready_for_governed_limited_operation_preview",
            "readiness",
            "governance_closeout",
            "runtime_watch",
            "baseline",
            "requested_batch_line_count",
            "requested_batch_amount",
            "requested_payment_entry_count",
            "requested_live_posting",
            "requested_journal_entry_side_effect",
            "requested_purchase_invoice_side_effect",
            "production_batch_enabled_policy_count_after",
            "live_posting_allowed_policy_count_after",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "submitted_journal_entry_count_today",
            "purchase_invoice_count_today",
            "pre_execution_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(GATE_ITEM_DOCTYPE, fields=["name", "pre_execution_gate", "status", "severity", "category", "check_key", "check_label", "detail", "source_doctype", "source_name"], order_by="creation desc", limit=int(limit or 20))
    return {
        "pre_execution_gates": records,
        "items": items,
        "required_acknowledgement": PRE_EXEC_ACK,
        "guardrails": guardrails(),
        "note": "Phase 10T pre-execution gate summary. Approved gate allows the next governed operation preview only.",
    }


def execute_pre_exec_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("g.status = %(status)s")
        params["status"] = filters.get("status")
    data = frappe.db.sql(
        f"""
        SELECT
            g.name AS pre_execution_gate,
            g.pre_execution_id,
            g.status,
            g.pre_execution_status,
            g.pre_execution_approved,
            g.ready_for_one_governed_limited_operation,
            g.ready_for_governed_limited_operation_preview,
            g.readiness,
            g.governance_closeout,
            g.runtime_watch,
            g.baseline,
            g.requested_batch_line_count,
            g.requested_batch_amount,
            g.requested_payment_entry_count,
            g.requested_live_posting,
            g.requested_journal_entry_side_effect,
            g.requested_purchase_invoice_side_effect,
            g.production_batch_enabled_policy_count_after,
            g.live_posting_allowed_policy_count_after,
            g.payment_entry_count_before,
            g.payment_entry_count_after,
            g.payment_entry_gl_count_before,
            g.payment_entry_gl_count_after,
            g.submitted_journal_entry_count_today,
            g.purchase_invoice_count_today,
            g.pre_execution_score,
            g.checked_on,
            %(currency)s AS currency
        FROM `tab{GATE_DOCTYPE}` g
        {build_where(conditions)}
        ORDER BY g.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.pre_execution_id for row in data[:20]],
            "datasets": [
                {"name": "Approved", "values": [int(row.pre_execution_approved or 0) for row in data[:20]]},
                {"name": "Ready", "values": [int(row.ready_for_one_governed_limited_operation or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Pre-Execution Gates"), "datatype": "Int"},
        {"value": sum(int(row.pre_execution_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(int(row.ready_for_one_governed_limited_operation or 0) for row in data), "indicator": "Green", "label": _("Ready"), "datatype": "Int"},
        {"value": sum(int(row.requested_live_posting or 0) for row in data), "indicator": "Red", "label": _("Requested Live"), "datatype": "Int"},
    ]
    return pre_exec_columns(), data, None, chart, summary


def pre_exec_columns():
    return [
        {"fieldname": "pre_execution_gate", "label": _("Pre-Execution Gate"), "fieldtype": "Link", "options": GATE_DOCTYPE, "width": 220},
        {"fieldname": "pre_execution_id", "label": _("Pre-Execution ID"), "fieldtype": "Data", "width": 390},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 160},
        {"fieldname": "pre_execution_status", "label": _("Pre-Execution Status"), "fieldtype": "Data", "width": 300},
        {"fieldname": "pre_execution_approved", "label": _("Approved"), "fieldtype": "Check", "width": 90},
        {"fieldname": "ready_for_one_governed_limited_operation", "label": _("Ready One Op"), "fieldtype": "Check", "width": 110},
        {"fieldname": "ready_for_governed_limited_operation_preview", "label": _("Ready Preview"), "fieldtype": "Check", "width": 115},
        {"fieldname": "readiness", "label": _("Readiness"), "fieldtype": "Link", "options": READINESS_DOCTYPE, "width": 220},
        {"fieldname": "governance_closeout", "label": _("Governance Closeout"), "fieldtype": "Link", "options": "NDIS Runtime Watch Governance Closeout", "width": 220},
        {"fieldname": "runtime_watch", "label": _("Runtime Watch"), "fieldtype": "Link", "options": "NDIS Controlled Limited Ops Runtime Watch", "width": 220},
        {"fieldname": "baseline", "label": _("Baseline"), "fieldtype": "Link", "options": "NDIS Controlled Limited Ops Baseline", "width": 220},
        {"fieldname": "requested_batch_line_count", "label": _("Req Lines"), "fieldtype": "Int", "width": 90},
        {"fieldname": "requested_batch_amount", "label": _("Req Amount"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "requested_payment_entry_count", "label": _("Req PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "requested_live_posting", "label": _("Req Live"), "fieldtype": "Check", "width": 90},
        {"fieldname": "requested_journal_entry_side_effect", "label": _("Req JE"), "fieldtype": "Check", "width": 90},
        {"fieldname": "requested_purchase_invoice_side_effect", "label": _("Req PI"), "fieldtype": "Check", "width": 90},
        {"fieldname": "production_batch_enabled_policy_count_after", "label": _("Enabled Policies"), "fieldtype": "Int", "width": 125},
        {"fieldname": "live_posting_allowed_policy_count_after", "label": _("Live Policies"), "fieldtype": "Int", "width": 105},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 110},
        {"fieldname": "submitted_journal_entry_count_today", "label": _("JE Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "purchase_invoice_count_today", "label": _("PI Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "pre_execution_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("pre_execution_gate"):
        conditions.append("i.pre_execution_gate = %(pre_execution_gate)s")
        params["pre_execution_gate"] = filters.get("pre_execution_gate")
    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": GATE_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "pre_execution_gate", "label": _("Pre-Execution Gate"), "fieldtype": "Link", "options": GATE_DOCTYPE, "width": 220},
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
    data = frappe.db.sql(
        f"""
        SELECT i.name AS item, i.pre_execution_gate, i.status, i.severity, i.category, i.check_key, i.check_label, i.detail, i.source_doctype, i.source_name, i.checked_on
        FROM `tab{GATE_ITEM_DOCTYPE}` i
        {build_where(conditions)}
        ORDER BY CASE i.status WHEN 'Blocker' THEN 1 WHEN 'Warning' THEN 2 WHEN 'Pass' THEN 3 WHEN 'Info' THEN 4 ELSE 5 END, i.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart_map = {}
    for row in data:
        chart_map[row.status or "Info"] = chart_map.get(row.status or "Info", 0) + 1
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Items", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Items"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Pass"]), "indicator": "Green", "label": _("Pass"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Warning"]), "indicator": "Orange", "label": _("Warnings"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Blocker"]), "indicator": "Red", "label": _("Blockers"), "datatype": "Int"},
        {"value": len([row for row in data if row.category == "Operation Shape"]), "indicator": "Green", "label": _("Shape Checks"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_pre_exec_report(filters)
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
