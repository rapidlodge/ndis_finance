import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


EXEC_GATE_ACK = "I_CONFIRM_PHASE10V_APPROVE_GOVERNED_LIMITED_OPERATION_EXECUTION_GATE_NO_POSTING"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
PREVIEW_DOCTYPE = "NDIS Governed Limited Op Preview"
PREVIEW_ITEM_DOCTYPE = "NDIS Governed Limited Op Preview Item"
GATE_DOCTYPE = "NDIS Governed Limited Op Exec Gate"
GATE_ITEM_DOCTYPE = "NDIS Governed Limited Op Exec Gate Item"


def make_execution_gate_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-GOVERNED-LIMITED-OP-EXEC-GATE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_preview():
    rows = frappe.get_all(
        PREVIEW_DOCTYPE,
        filters={
            "status": "Previewed",
            "preview_status": "Governed Limited Operation Preview Ready",
            "preview_completed": 1,
            "operation_previewed": 1,
            "operation_shape_verified": 1,
            "operation_preview_locked": 1,
            "ready_for_governed_limited_operation_execution_gate": 1,
            "pre_execution_gate_verified": 1,
            "preview_only_verified": 1,
            "no_new_accounting_movement_verified": 1,
            "policy_state_preserved_verified": 1,
            "policy_mutation_performed": 0,
            "actual_policy_mutation_count": 0,
            "phase10t_pre_execution_verified": 1,
            "phase10s_readiness_verified": 1,
            "phase10r_governance_closeout_verified": 1,
            "phase10q_freeze_verified": 1,
            "phase10p_simulation_verified": 1,
            "phase10o_runtime_watch_verified": 1,
            "phase10n_baseline_verified": 1,
            "controlled_policy_enabled_verified": 1,
            "live_posting_blocked_verified": 1,
            "target_policy_enabled_after": 1,
            "target_policy_live_after": 0,
            "requested_batch_line_count": 3,
            "requested_payment_entry_count": 1,
            "requested_live_posting": 0,
            "requested_journal_entry_side_effect": 0,
            "requested_purchase_invoice_side_effect": 0,
            "preview_line_count": 3,
            "would_create_payment_entry_count": 1,
            "would_create_gl_entry_count": 0,
            "actual_payment_entry_created_count": 0,
            "actual_payment_entry_cancelled_count": 0,
            "actual_gl_created_count": 0,
            "submitted_journal_entry_count_today": 0,
            "purchase_invoice_count_today": 0,
        },
        fields=[
            "name",
            "preview_id",
            "pre_execution_gate",
            "readiness",
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
            "requested_batch_line_count",
            "requested_batch_amount",
            "requested_payment_entry_count",
            "requested_live_posting",
            "requested_journal_entry_side_effect",
            "requested_purchase_invoice_side_effect",
            "preview_line_count",
            "preview_total_amount",
            "preview_customer",
            "preview_company",
            "source_payment_entry",
            "would_create_payment_entry_count",
            "would_create_gl_entry_count",
            "payment_entry_count_after",
            "payment_entry_gl_count_after",
            "preview_score",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_execution_gate(preview):
    if not preview:
        return None
    rows = frappe.get_all(
        GATE_DOCTYPE,
        filters={"preview": preview, "status": "Execution Gate Approved", "execution_gate_approved": 1},
        fields=["name", "execution_gate_id"],
        limit=1,
    )
    return rows[0] if rows else None


def preview_items(preview):
    if not preview:
        return []
    return frappe.get_all(
        PREVIEW_ITEM_DOCTYPE,
        filters={"preview": preview},
        fields=[
            "name",
            "line_no",
            "status",
            "reference_doctype",
            "reference_name",
            "customer",
            "company",
            "outstanding_amount",
            "allocated_amount",
            "preview_decision",
            "detail",
        ],
        order_by="line_no asc, creation asc",
    )


def validate_preview(preview, items):
    if not preview:
        return ["No completed Phase 10U governed limited operation preview found."]
    issues = []
    existing = existing_execution_gate(preview.name)
    if existing:
        issues.append(f"Phase 10V execution gate already exists for this preview: {existing.execution_gate_id}")
    required_links = {
        "preview": (PREVIEW_DOCTYPE, preview.name),
        "pre_execution_gate": ("NDIS Governed Limited Op Pre Exec", preview.pre_execution_gate),
        "readiness": ("NDIS Governed Limited Ops Readiness", preview.readiness),
        "governance_closeout": ("NDIS Runtime Watch Governance Closeout", preview.governance_closeout),
        "freeze": ("NDIS Runtime Watch Violation Sim Freeze", preview.freeze),
        "simulation": ("NDIS Runtime Watch Violation Sim", preview.simulation),
        "runtime_watch": ("NDIS Controlled Limited Ops Runtime Watch", preview.runtime_watch),
        "baseline": ("NDIS Controlled Limited Ops Baseline", preview.baseline),
        "target_policy": (POLICY_DOCTYPE, preview.target_policy),
        "source_payment_entry": ("Payment Entry", preview.source_payment_entry),
    }
    for label, (doctype, name) in required_links.items():
        if not name:
            issues.append(f"Missing evidence link: {label}")
        elif not frappe.db.exists(doctype, name):
            issues.append(f"Linked evidence does not exist: {doctype} {name}")
    if len(items) != 3:
        issues.append(f"Preview must contain exactly 3 preview item rows. Found {len(items)}.")
    if [row for row in items if row.status == "Blocker"]:
        issues.append(f"Preview item blocker rows exist: {len([row for row in items if row.status == 'Blocker'])}")
    if [row for row in items if row.status == "Warning"]:
        issues.append(f"Preview item warning rows exist: {len([row for row in items if row.status == 'Warning'])}")
    if [row for row in items if row.status != "Pass"]:
        issues.append(f"All preview items must be Pass. Non-pass rows: {len([row for row in items if row.status != 'Pass'])}")
    if [row for row in items if row.preview_decision != "Included"]:
        issues.append(f"All preview items must be Included. Non-included rows: {len([row for row in items if row.preview_decision != 'Included'])}")
    ref_types = sorted(set(row.reference_doctype for row in items))
    if ref_types != ["Sales Invoice"]:
        issues.append(f"All preview references must be Sales Invoice. Found: {ref_types}")
    allocated_total = flt(sum(flt(row.allocated_amount or 0, 2) for row in items), 2)
    if allocated_total != 3:
        issues.append(f"Preview item allocated total must be 3.00. Found {allocated_total}.")
    customers = sorted(set(row.customer for row in items if row.customer))
    companies = sorted(set(row.company for row in items if row.company))
    if len(customers) != 1:
        issues.append(f"Preview items must use exactly one customer. Found: {customers}")
    if len(companies) != 1:
        issues.append(f"Preview items must use exactly one company. Found: {companies}")
    checks = [
        (int(preview.preview_line_count or 0) == 3, "Preview line count must be 3."),
        (flt(preview.preview_total_amount or 0, 2) == 3, "Preview total amount must be 3.00."),
        (int(preview.would_create_payment_entry_count or 0) == 1, "Preview would-create Payment Entry count must be 1."),
        (int(preview.would_create_gl_entry_count or 0) == 0, "Preview would-create GL count must be 0."),
        (int(preview.requested_live_posting or 0) == 0, "Requested live posting must be 0."),
        (int(preview.requested_journal_entry_side_effect or 0) == 0, "Requested Journal Entry side effect must be 0."),
        (int(preview.requested_purchase_invoice_side_effect or 0) == 0, "Requested Purchase Invoice side effect must be 0."),
    ]
    issues.extend(message for ok, message in checks if not ok)
    return issues


def validate_environment(preview, guard, policy_enabled, policy_live, config):
    if not preview:
        return []
    checks = [
        (policy_enabled == 1, "Target policy production_batch_enabled must be 1 before Phase 10V. Phase 10V must not repair this."),
        (policy_live == 0, "Target policy live_posting_allowed must be 0 before Phase 10V. Phase 10V must not repair this."),
        (guard["production_batch_enabled_policy_count"] == 1, "Exactly one controlled production batch policy must remain enabled."),
        (guard["live_posting_allowed_policy_count"] == 0, "Controlled production live allowed policy count must remain 0."),
        (guard["submitted_journal_entry_count_today"] == 0, "Submitted Journal Entry count today must remain 0."),
        (guard["purchase_invoice_count_today"] == 0, "Purchase Invoice count today must remain 0."),
        (int(config["production_mode"]) == 0, "Production mode config must remain 0."),
        (int(config["live_pe_enabled"]) == 0, "Live Payment Entry posting config must remain 0."),
    ]
    return [message for ok, message in checks if not ok]


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


def build_gate_items(preview, preview_item_rows, issues, ack_ok):
    items = []
    if preview:
        add_item(items, "Pass", "Low", "Evidence", "phase10u_preview_exists", "Phase 10U preview exists", f"Preview found: {preview.preview_id}.", PREVIEW_DOCTYPE, preview.name)
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase10u_preview_exists", "Phase 10U preview exists", "No completed Phase 10U preview found.")
    if issues:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Execution Gate Source", "execution_gate_source_valid", "Execution gate source valid", issue)
    else:
        add_item(items, "Pass", "High", "Execution Gate Source", "execution_gate_source_valid", "Execution gate source valid", "Phase 10U preview is valid for execution gate.")
    checks = [
        ("preview_line_count", "Preview has exactly 3 lines", getattr(preview, "preview_line_count", None)),
        ("preview_total_amount", "Preview amount is 3.00", getattr(preview, "preview_total_amount", None)),
        ("would_create_payment_entry_count", "Would create exactly 1 Payment Entry", getattr(preview, "would_create_payment_entry_count", None)),
        ("would_create_gl_entry_count", "Would create 0 GL rows during preview", getattr(preview, "would_create_gl_entry_count", None)),
        ("smoke_only_allowed", "Only governed smoke is allowed by this gate", 1),
        ("real_posting_allowed", "Real posting remains blocked by this gate", 0),
    ]
    for key, label, value in checks:
        add_item(items, "Pass", "High", "Execution Gate Check", key, label, f"value={value}")
    for row in preview_item_rows:
        add_item(
            items,
            "Pass" if row.status == "Pass" else "Blocker",
            "High",
            "Preview Reference",
            f"preview_line_{row.line_no}",
            f"Preview line {row.line_no}",
            f"{row.reference_doctype} {row.reference_name}; allocated={flt(row.allocated_amount or 0, 2)}; decision={row.preview_decision}",
            row.reference_doctype,
            row.reference_name,
        )
    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {EXEC_GATE_ACK}")
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
        row.execution_gate = doc.name
        for key, value in item.items():
            if row.meta.has_field(key):
                setattr(row, key, value)
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_governed_limited_operation_execution_gate(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_governed_limited_operation_execution_gate")
    preview = latest_preview()
    preview_item_rows = preview_items(preview.name) if preview else []
    guard_before = guardrails()
    ack_ok = acknowledgement == EXEC_GATE_ACK
    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }
    policy_enabled_before = get_flag(POLICY_DOCTYPE, preview.target_policy, "production_batch_enabled") if preview else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, preview.target_policy, "live_posting_allowed") if preview else 0
    preview_issues = validate_preview(preview, preview_item_rows)
    environment_issues = validate_environment(preview, guard_before, policy_enabled_before, policy_live_before, config)
    guard_after = guardrails()
    policy_enabled_after = get_flag(POLICY_DOCTYPE, preview.target_policy, "production_batch_enabled") if preview else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, preview.target_policy, "live_posting_allowed") if preview else 0
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
        environment_issues.append("Accounting movement changed while preparing Phase 10V execution gate evidence.")
    issues = preview_issues + environment_issues
    operation_shape_verified = int(
        preview
        and not preview_issues
        and int(preview.preview_line_count or 0) == 3
        and flt(preview.preview_total_amount or 0, 2) == 3
        and int(preview.would_create_payment_entry_count or 0) == 1
        and int(preview.would_create_gl_entry_count or 0) == 0
    )
    items = build_gate_items(preview, preview_item_rows, issues, ack_ok)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    allowed = int(ack_ok and item_summary["blocker_count"] == 0 and preview and operation_shape_verified and no_new_movement and policy_preserved)
    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Execution Gate Approved" if allowed else "Needs Review",
        "execution_gate_status": "Ready For Governed Limited Operation Smoke" if allowed else "Needs Review",
        "execution_gate_approved": allowed,
        "ready_for_governed_limited_operation_smoke": allowed,
        "ready_for_single_governed_operation_smoke": allowed,
        "smoke_only_allowed": allowed,
        "real_posting_allowed": 0,
        "preview_verified": 1 if preview else 0,
        "operation_shape_verified": operation_shape_verified,
        "execution_gate_only_verified": 1,
        "no_new_accounting_movement_verified": no_new_movement,
        "policy_state_preserved_verified": policy_preserved,
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": 0,
        "phase10u_preview_verified": 1 if preview else 0,
        "phase10t_pre_execution_verified": 1 if preview else 0,
        "phase10s_readiness_verified": 1 if preview else 0,
        "phase10r_governance_closeout_verified": 1 if preview else 0,
        "phase10q_freeze_verified": 1 if preview else 0,
        "phase10p_simulation_verified": 1 if preview else 0,
        "phase10o_runtime_watch_verified": 1 if preview else 0,
        "phase10n_baseline_verified": 1 if preview else 0,
        "controlled_policy_enabled_verified": int(policy_enabled_after == 1),
        "live_posting_blocked_verified": int(policy_live_after == 0),
        "preview": preview.name if preview else None,
        "pre_execution_gate": preview.pre_execution_gate if preview else None,
        "readiness": preview.readiness if preview else None,
        "governance_closeout": preview.governance_closeout if preview else None,
        "freeze": preview.freeze if preview else None,
        "simulation": preview.simulation if preview else None,
        "runtime_watch": preview.runtime_watch if preview else None,
        "baseline": preview.baseline if preview else None,
        "monitoring_register": preview.monitoring_register if preview else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": preview.target_policy if preview else None,
        "target_policy_name": preview.target_policy_name if preview else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_before": policy_live_before,
        "target_policy_live_after": policy_live_after,
        "production_batch_enabled_policy_count_before": guard_before["production_batch_enabled_policy_count"],
        "production_batch_enabled_policy_count_after": guard_after["production_batch_enabled_policy_count"],
        "live_posting_allowed_policy_count_before": guard_before["live_posting_allowed_policy_count"],
        "live_posting_allowed_policy_count_after": guard_after["live_posting_allowed_policy_count"],
        "preview_line_count": int(preview.preview_line_count or 0) if preview else 0,
        "preview_total_amount": flt(preview.preview_total_amount or 0, 2) if preview else 0,
        "preview_customer": preview.preview_customer if preview else None,
        "preview_company": preview.preview_company if preview else None,
        "source_payment_entry": preview.source_payment_entry if preview else None,
        "would_create_payment_entry_count": int(preview.would_create_payment_entry_count or 0) if preview else 0,
        "would_create_gl_entry_count": int(preview.would_create_gl_entry_count or 0) if preview else 0,
        "locked_batch_line_count": 3 if operation_shape_verified else 0,
        "locked_batch_amount": 3 if operation_shape_verified else 0,
        "locked_payment_entry_count": 1 if operation_shape_verified else 0,
        "locked_live_posting": 0,
        "locked_journal_entry_side_effect": 0,
        "locked_purchase_invoice_side_effect": 0,
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guard_after["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
        "actual_payment_entry_created_count": 0,
        "actual_payment_entry_cancelled_count": 0,
        "actual_gl_created_count": 0,
        "submitted_journal_entry_count_today": guard_after["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_after["purchase_invoice_count_today"],
        "execution_gate_score": score,
        **item_summary,
        "items": items,
        "preview_items": preview_item_rows,
        "issues": issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "required_acknowledgement": EXEC_GATE_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 10V approves the execution gate for one governed smoke only. No Payment Entry, GL Entry, Journal Entry, Purchase Invoice, or policy mutation is performed.",
    }
    if int(dry_run or 0):
        result.update({"status": "Needs Review", "execution_gate_status": "Needs Review", "execution_gate_approved": 0, "ready_for_governed_limited_operation_smoke": 0, "ready_for_single_governed_operation_smoke": 0, "smoke_only_allowed": 0})
        return result
    doc = frappe.new_doc(GATE_DOCTYPE)
    doc.execution_gate_id = make_execution_gate_id()
    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = EXEC_GATE_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.execution_gate_json = safe_json({"preview_items": preview_item_rows, "guardrails_before": guard_before, "guardrails_after": guard_after, "config": config, "issues": issues})
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    create_items(doc, items)
    frappe.db.commit()
    return {**result, "created": True, "execution_gate": doc.name, "execution_gate_id": doc.execution_gate_id, "guardrails_after": guardrails()}


@frappe.whitelist()
def cancel_governed_limited_operation_execution_gate_audit(execution_gate, reason=None):
    assert_action("cancel_governed_limited_operation_execution_gate_audit")
    if not frappe.db.exists(GATE_DOCTYPE, execution_gate):
        frappe.throw(_("Governed limited operation execution gate audit not found: {0}").format(execution_gate))
    doc = frappe.get_doc(GATE_DOCTYPE, execution_gate)
    if doc.status == "Cancelled":
        return {"execution_gate": execution_gate, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.execution_gate_approved or 0):
        frappe.throw(_("Cannot cancel an approved Phase 10V execution gate record."))
    frappe.db.set_value(
        GATE_DOCTYPE,
        execution_gate,
        {"status": "Cancelled", "execution_gate_status": "Cancelled", "cancelled_on": now_datetime(), "cancelled_by": frappe.session.user, "summary_json": reason or "Phase 10V no-ack execution gate audit cancelled."},
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{GATE_ITEM_DOCTYPE}` SET status = 'Cancelled' WHERE execution_gate = %(execution_gate)s", {"execution_gate": execution_gate})
    frappe.db.commit()
    return {"execution_gate": execution_gate, "status": "Cancelled", "note": "No-ack execution gate audit cancelled only. No accounting or policy movement occurred."}


@frappe.whitelist()
def quick_governed_limited_operation_execution_gate_summary(limit=20):
    records = frappe.get_all(
        GATE_DOCTYPE,
        fields=[
            "name",
            "execution_gate_id",
            "status",
            "execution_gate_status",
            "execution_gate_approved",
            "ready_for_governed_limited_operation_smoke",
            "ready_for_single_governed_operation_smoke",
            "smoke_only_allowed",
            "real_posting_allowed",
            "preview",
            "pre_execution_gate",
            "readiness",
            "runtime_watch",
            "preview_line_count",
            "preview_total_amount",
            "preview_customer",
            "preview_company",
            "source_payment_entry",
            "would_create_payment_entry_count",
            "would_create_gl_entry_count",
            "production_batch_enabled_policy_count_after",
            "live_posting_allowed_policy_count_after",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "submitted_journal_entry_count_today",
            "purchase_invoice_count_today",
            "execution_gate_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(GATE_ITEM_DOCTYPE, fields=["name", "execution_gate", "status", "severity", "category", "check_key", "check_label", "detail", "source_doctype", "source_name"], order_by="creation desc", limit=int(limit or 20))
    return {"execution_gates": records, "items": items, "required_acknowledgement": EXEC_GATE_ACK, "guardrails": guardrails(), "note": "Phase 10V execution gate summary. Approved gate allows the next governed smoke only."}


def execute_gate_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("g.status = %(status)s")
        params["status"] = filters.get("status")
    data = frappe.db.sql(
        f"""
        SELECT
            g.name AS execution_gate,
            g.execution_gate_id,
            g.status,
            g.execution_gate_status,
            g.execution_gate_approved,
            g.ready_for_governed_limited_operation_smoke,
            g.ready_for_single_governed_operation_smoke,
            g.smoke_only_allowed,
            g.real_posting_allowed,
            g.preview,
            g.pre_execution_gate,
            g.readiness,
            g.runtime_watch,
            g.preview_line_count,
            g.preview_total_amount,
            g.preview_customer,
            g.preview_company,
            g.source_payment_entry,
            g.would_create_payment_entry_count,
            g.would_create_gl_entry_count,
            g.production_batch_enabled_policy_count_after,
            g.live_posting_allowed_policy_count_after,
            g.payment_entry_count_before,
            g.payment_entry_count_after,
            g.payment_entry_gl_count_before,
            g.payment_entry_gl_count_after,
            g.submitted_journal_entry_count_today,
            g.purchase_invoice_count_today,
            g.execution_gate_score,
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
            "labels": [row.execution_gate_id for row in data[:20]],
            "datasets": [
                {"name": "Approved", "values": [int(row.execution_gate_approved or 0) for row in data[:20]]},
                {"name": "Smoke Ready", "values": [int(row.ready_for_governed_limited_operation_smoke or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Execution Gates"), "datatype": "Int"},
        {"value": sum(int(row.execution_gate_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(int(row.ready_for_governed_limited_operation_smoke or 0) for row in data), "indicator": "Green", "label": _("Smoke Ready"), "datatype": "Int"},
        {"value": sum(int(row.real_posting_allowed or 0) for row in data), "indicator": "Red", "label": _("Real Posting Allowed"), "datatype": "Int"},
    ]
    return gate_columns(), data, None, chart, summary


def gate_columns():
    return [
        {"fieldname": "execution_gate", "label": _("Execution Gate"), "fieldtype": "Link", "options": GATE_DOCTYPE, "width": 220},
        {"fieldname": "execution_gate_id", "label": _("Execution Gate ID"), "fieldtype": "Data", "width": 400},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 170},
        {"fieldname": "execution_gate_status", "label": _("Execution Gate Status"), "fieldtype": "Data", "width": 320},
        {"fieldname": "execution_gate_approved", "label": _("Approved"), "fieldtype": "Check", "width": 90},
        {"fieldname": "ready_for_governed_limited_operation_smoke", "label": _("Smoke Ready"), "fieldtype": "Check", "width": 110},
        {"fieldname": "ready_for_single_governed_operation_smoke", "label": _("Single Smoke"), "fieldtype": "Check", "width": 110},
        {"fieldname": "smoke_only_allowed", "label": _("Smoke Only"), "fieldtype": "Check", "width": 95},
        {"fieldname": "real_posting_allowed", "label": _("Real Posting"), "fieldtype": "Check", "width": 100},
        {"fieldname": "preview", "label": _("Preview"), "fieldtype": "Link", "options": PREVIEW_DOCTYPE, "width": 220},
        {"fieldname": "pre_execution_gate", "label": _("Pre-Execution Gate"), "fieldtype": "Link", "options": "NDIS Governed Limited Op Pre Exec", "width": 220},
        {"fieldname": "readiness", "label": _("Readiness"), "fieldtype": "Link", "options": "NDIS Governed Limited Ops Readiness", "width": 220},
        {"fieldname": "runtime_watch", "label": _("Runtime Watch"), "fieldtype": "Link", "options": "NDIS Controlled Limited Ops Runtime Watch", "width": 220},
        {"fieldname": "preview_line_count", "label": _("Lines"), "fieldtype": "Int", "width": 75},
        {"fieldname": "preview_total_amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 105},
        {"fieldname": "preview_customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 180},
        {"fieldname": "preview_company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 180},
        {"fieldname": "source_payment_entry", "label": _("Source PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "would_create_payment_entry_count", "label": _("Would PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "would_create_gl_entry_count", "label": _("Would GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "production_batch_enabled_policy_count_after", "label": _("Enabled Policies"), "fieldtype": "Int", "width": 125},
        {"fieldname": "live_posting_allowed_policy_count_after", "label": _("Live Policies"), "fieldtype": "Int", "width": 105},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 110},
        {"fieldname": "submitted_journal_entry_count_today", "label": _("JE Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "purchase_invoice_count_today", "label": _("PI Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "execution_gate_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("execution_gate"):
        conditions.append("i.execution_gate = %(execution_gate)s")
        params["execution_gate"] = filters.get("execution_gate")
    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")
    data = frappe.db.sql(
        f"""
        SELECT i.name AS item, i.execution_gate, i.status, i.severity, i.category, i.check_key, i.check_label, i.detail, i.source_doctype, i.source_name, i.checked_on
        FROM `tab{GATE_ITEM_DOCTYPE}` i
        {build_where(conditions)}
        ORDER BY CASE i.status WHEN 'Blocker' THEN 1 WHEN 'Warning' THEN 2 WHEN 'Pass' THEN 3 WHEN 'Info' THEN 4 ELSE 5 END, i.creation DESC
        """,
        params,
        as_dict=True,
    )
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": GATE_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "execution_gate", "label": _("Execution Gate"), "fieldtype": "Link", "options": GATE_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 210},
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
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Items", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Items"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Pass"]), "indicator": "Green", "label": _("Pass"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Warning"]), "indicator": "Orange", "label": _("Warnings"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Blocker"]), "indicator": "Red", "label": _("Blockers"), "datatype": "Int"},
        {"value": len([row for row in data if row.category == "Preview Reference"]), "indicator": "Green", "label": _("Preview Reference Rows"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_gate_report(filters)
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
