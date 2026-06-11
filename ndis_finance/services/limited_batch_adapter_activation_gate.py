import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.limited_batch_posting_adapter_hard_block import direct_guarded_limited_batch_posting_adapter
from ndis_finance.services.permissions import assert_action


ACTIVATION_ACK = "I_CONFIRM_PHASE9Z_ALLOW_GUARDED_LIMITED_ADAPTER_SMOKE_NO_POSTING"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"


def make_activation_gate_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-LIMITED-BATCH-ADAPTER-ACTIVATION-GATE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def config_state():
    return {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


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


def latest_hard_block():
    rows = frappe.get_all(
        "NDIS Limited Batch Posting Adapter Hard Block",
        filters={
            "status": "Hard Blocked",
            "adapter_hard_blocked": 1,
            "direct_adapter_execution_blocked": 1,
            "ready_for_guarded_adapter_activation_gate": 1,
            "preview_only_evidence_verified": 1,
            "phase9x_adapter_preview_verified": 1,
            "phase9w_runtime_guard_freeze_verified": 1,
            "phase9v_runtime_guard_verified": 1,
            "phase9u_monitor_gate_verified": 1,
            "phase9t_freeze_verified": 1,
            "phase9s_enablement_verified": 1,
            "policy_caps_verified": 1,
            "controlled_policy_enabled_verified": 1,
            "live_posting_blocked_verified": 1,
            "runtime_guard_active_verified": 1,
            "runtime_validation_ready_verified": 1,
            "adapter_preview_runtime_guard_passed": 1,
            "no_accounting_movement_verified": 1,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "current_target_policy_enabled": 1,
            "current_target_policy_live": 0,
            "preview_batch_line_count": 3,
            "preview_payment_entry_count": 1,
            "would_create_payment_entry_count": 1,
            "would_create_gl_entry_count": 0,
            "would_use_live_posting": 0,
            "would_create_journal_entry": 0,
            "would_create_purchase_invoice": 0,
            "actual_adapter_execution_count": 0,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
            "production_batch_enabled_policy_count": 1,
            "live_posting_allowed_policy_count": 0,
        },
        fields=[
            "name",
            "hard_block_id",
            "adapter_preview",
            "runtime_guard_evidence_freeze",
            "runtime_guard",
            "monitor_gate",
            "policy_enablement_freeze",
            "enablement_run",
            "target_policy_doctype",
            "target_policy",
            "target_policy_name",
            "current_target_policy_enabled",
            "current_target_policy_live",
            "actual_enabled_policy_count",
            "preview_batch_line_count",
            "preview_batch_amount",
            "preview_payment_entry_count",
            "would_create_payment_entry_count",
            "would_create_gl_entry_count",
            "would_use_live_posting",
            "would_create_journal_entry",
            "would_create_purchase_invoice",
            "max_batch_lines",
            "max_batch_amount",
            "max_payment_entry_count",
            "actual_adapter_execution_count",
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
            "hard_block_score",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    if not rows:
        return None
    hard_block = rows[0]
    if flt(hard_block.preview_batch_amount or 0, 2) != 3:
        return None
    if flt(hard_block.max_batch_amount or 0, 2) != 3:
        return None
    return hard_block


def existing_activation_gate(hard_block):
    rows = frappe.get_all(
        "NDIS Limited Batch Adapter Activation Gate",
        filters={
            "hard_block": hard_block,
            "status": "Activation Allowed",
            "adapter_activation_allowed": 1,
            "ready_for_guarded_limited_adapter_smoke": 1,
            "smoke_only_allowed": 1,
        },
        fields=["name", "activation_gate_id"],
        limit=1,
    )
    return rows[0] if rows else None


def prove_direct_adapter_still_blocked():
    try:
        direct_guarded_limited_batch_posting_adapter(
            preview_batch_line_count=3,
            preview_batch_amount=3,
            preview_payment_entry_count=1,
        )
    except frappe.ValidationError as exc:
        return {"blocked": 1, "error_type": exc.__class__.__name__, "error_message": str(exc)}
    except Exception as exc:
        return {"blocked": 0, "error_type": exc.__class__.__name__, "error_message": str(exc)}
    return {"blocked": 0, "error_type": "None", "error_message": "Direct adapter execution did not raise a blocking error."}


def validate_source(hard_block, guard, block_result, config):
    issues = []
    if config["production_mode"]:
        issues.append("Production mode config must remain disabled for Phase 9Z.")
    if config["live_pe_enabled"]:
        issues.append("Live Payment Entry posting config must remain disabled for Phase 9Z.")
    if not hard_block:
        issues.append("No completed Phase 9Y hard-block proof found.")
        return issues
    existing = existing_activation_gate(hard_block.name)
    if existing:
        issues.append(f"Phase 9Z activation gate already exists for this hard-block proof: {existing.activation_gate_id}")
    required_links = {
        "adapter_preview": hard_block.adapter_preview,
        "runtime_guard_evidence_freeze": hard_block.runtime_guard_evidence_freeze,
        "runtime_guard": hard_block.runtime_guard,
        "monitor_gate": hard_block.monitor_gate,
        "policy_enablement_freeze": hard_block.policy_enablement_freeze,
        "enablement_run": hard_block.enablement_run,
    }
    for label, value in required_links.items():
        if not value:
            issues.append(f"Missing evidence link: {label}")
    link_checks = {
        "NDIS Limited Batch Posting Adapter Preview": hard_block.adapter_preview,
        "NDIS Limited Batch Runtime Guard Evidence Freeze": hard_block.runtime_guard_evidence_freeze,
        "NDIS Limited Batch Runtime Guard": hard_block.runtime_guard,
        "NDIS Limited Production Batch Use Monitor Gate": hard_block.monitor_gate,
        "NDIS Limited Production Batch Policy Enablement Freeze": hard_block.policy_enablement_freeze,
        "NDIS Limited Production Batch Policy Enablement Run": hard_block.enablement_run,
    }
    for doctype, name in link_checks.items():
        if name and not frappe.db.exists(doctype, name):
            issues.append(f"Linked evidence does not exist: {doctype} {name}")
    if not hard_block.target_policy:
        issues.append("Hard-block proof has no target policy.")
    if hard_block.target_policy and not frappe.db.exists(POLICY_DOCTYPE, hard_block.target_policy):
        issues.append(f"Target policy does not exist: {hard_block.target_policy}")
    if hard_block.target_policy:
        current_enabled = get_flag(POLICY_DOCTYPE, hard_block.target_policy, "production_batch_enabled")
        current_live = get_flag(POLICY_DOCTYPE, hard_block.target_policy, "live_posting_allowed")
        if current_enabled != 1:
            issues.append("Current target policy production_batch_enabled must be 1 before activation gate.")
        if current_live != 0:
            issues.append("Current target policy live_posting_allowed must be 0 before activation gate.")
    required_ints = {
        "preview_batch_line_count": (hard_block.preview_batch_line_count, 3),
        "preview_payment_entry_count": (hard_block.preview_payment_entry_count, 1),
        "would_create_payment_entry_count": (hard_block.would_create_payment_entry_count, 1),
        "would_create_gl_entry_count": (hard_block.would_create_gl_entry_count, 0),
        "actual_adapter_execution_count": (hard_block.actual_adapter_execution_count, 0),
        "actual_payment_entry_created_count": (hard_block.actual_payment_entry_created_count, 0),
        "actual_gl_created_count": (hard_block.actual_gl_created_count, 0),
        "max_batch_lines": (hard_block.max_batch_lines, 3),
        "max_payment_entry_count": (hard_block.max_payment_entry_count, 1),
    }
    for label, pair in required_ints.items():
        value, expected = pair
        if int(value or 0) != expected:
            issues.append(f"{label} must be {expected}.")
    if flt(hard_block.preview_batch_amount or 0, 2) != 3:
        issues.append("preview_batch_amount must be 3.00.")
    if flt(hard_block.max_batch_amount or 0, 2) != 3:
        issues.append("max_batch_amount must be 3.00.")
    for label in ["would_use_live_posting", "would_create_journal_entry", "would_create_purchase_invoice"]:
        if int(hard_block.get(label) or 0) != 0:
            issues.append(f"{label} must be 0.")
    if int(hard_block.current_target_policy_enabled or 0) != 1:
        issues.append("current_target_policy_enabled must be 1.")
    if int(hard_block.current_target_policy_live or 0) != 0:
        issues.append("current_target_policy_live must be 0.")
    if int(hard_block.actual_enabled_policy_count or 0) != 1:
        issues.append("actual_enabled_policy_count must be 1.")
    if int(hard_block.payment_entry_count_before or 0) != int(hard_block.payment_entry_count_after or 0):
        issues.append("Phase 9Y Payment Entry count changed.")
    if int(hard_block.payment_entry_gl_count_before or 0) != int(hard_block.payment_entry_gl_count_after or 0):
        issues.append("Phase 9Y Payment Entry GL count changed.")
    if not int(block_result.get("blocked") or 0):
        issues.append("Direct adapter is not currently hard-blocked.")
    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must be enabled before activation gate.")
    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must be 0 before activation gate.")
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


def build_items(hard_block, issues, ack_ok, guard, block_result):
    items = []
    if hard_block:
        add_item(
            items,
            "Pass",
            "Low",
            "Evidence",
            "phase9y_hard_block_exists",
            "Phase 9Y hard-block exists",
            f"Hard-block proof found: {hard_block.hard_block_id}.",
            "NDIS Limited Batch Posting Adapter Hard Block",
            hard_block.name,
        )
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase9y_hard_block_exists", "Phase 9Y hard-block exists", "No completed Phase 9Y hard-block proof found.")
    if not issues:
        add_item(items, "Pass", "Low", "Activation Source", "activation_source_valid", "Activation source valid", "Phase 9Y hard-block evidence is valid for activation gate.")
    else:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Activation Source", "activation_source_valid", "Activation source valid", issue)
    if block_result.get("blocked"):
        add_item(items, "Pass", "Low", "Direct Adapter", "direct_adapter_still_blocked", "Direct adapter still hard-blocked", block_result.get("error_message"))
    else:
        add_item(items, "Blocker", "Critical", "Direct Adapter", "direct_adapter_still_blocked", "Direct adapter still hard-blocked", block_result.get("error_message"))
    if guard["production_batch_enabled_policy_count"] == 1 and guard["live_posting_allowed_policy_count"] == 0:
        add_item(items, "Pass", "Low", "Policy Guardrail", "policy_state", "Policy state correct", "Exactly one controlled policy is enabled and live posting remains blocked.")
    else:
        add_item(items, "Blocker", "Critical", "Policy Guardrail", "policy_state", "Policy state correct", "Policy state is not 1 enabled / 0 live.")
    if hard_block:
        add_item(items, "Pass", "Low", "Smoke Gate", "smoke_only", "Smoke only allowed", "Activation gate allows next guarded smoke phase only, not direct adapter execution.")
        add_item(items, "Pass", "Low", "Smoke Gate", "allowed_smoke_shape", "Allowed smoke shape is capped", "Allowed smoke shape is max 3 lines, $3.00, and 1 Payment Entry.")
        add_item(items, "Pass", "Low", "Accounting Guardrail", "no_actual_payment_entry", "No actual Payment Entry created", "Activation gate created no Payment Entry.")
        add_item(items, "Pass", "Low", "Accounting Guardrail", "no_actual_gl", "No actual GL created", "Activation gate created no GL Entry.")
        add_item(items, "Pass", "Low", "Live Guardrail", "live_posting_blocked", "Live posting blocked", "Live posting remains blocked.")
    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {ACTIVATION_ACK}")
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
        row = frappe.new_doc("NDIS Limited Batch Adapter Activation Gate Item")
        row.activation_gate = doc.name
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
def run_limited_batch_adapter_activation_gate(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_limited_batch_adapter_activation_gate")

    hard_block = latest_hard_block()
    config = config_state()
    guard_before = guardrails()
    ack_ok = acknowledgement == ACTIVATION_ACK
    block_result = prove_direct_adapter_still_blocked()
    issues = validate_source(hard_block, guard_before, block_result, config)
    items = build_items(hard_block, issues, ack_ok, guard_before, block_result)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    allowed = int(ack_ok and item_summary["blocker_count"] == 0 and bool(hard_block) and int(block_result.get("blocked") or 0))
    guard_now = guardrails()
    current_enabled = get_flag(POLICY_DOCTYPE, hard_block.target_policy, "production_batch_enabled") if hard_block else 0
    current_live = get_flag(POLICY_DOCTYPE, hard_block.target_policy, "live_posting_allowed") if hard_block else 0

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Activation Allowed" if allowed else "Needs Review",
        "activation_status": "Ready For Guarded Limited Adapter Smoke" if allowed else "Needs Review",
        "adapter_activation_allowed": allowed,
        "ready_for_guarded_limited_adapter_smoke": allowed,
        "smoke_only_allowed": allowed,
        "phase9y_hard_block_verified": 1 if hard_block else 0,
        "phase9x_adapter_preview_verified": 1 if hard_block else 0,
        "phase9w_runtime_guard_freeze_verified": 1 if hard_block else 0,
        "phase9v_runtime_guard_verified": 1 if hard_block else 0,
        "phase9u_monitor_gate_verified": 1 if hard_block else 0,
        "phase9t_freeze_verified": 1 if hard_block else 0,
        "phase9s_enablement_verified": 1 if hard_block else 0,
        "policy_caps_verified": 1 if hard_block and int(hard_block.max_batch_lines or 0) == 3 and flt(hard_block.max_batch_amount or 0, 2) == 3 and int(hard_block.max_payment_entry_count or 0) == 1 else 0,
        "controlled_policy_enabled_verified": 1 if current_enabled == 1 else 0,
        "live_posting_blocked_verified": 1 if current_live == 0 else 0,
        "runtime_guard_active_verified": 1 if hard_block else 0,
        "runtime_validation_ready_verified": 1 if hard_block else 0,
        "direct_adapter_hard_block_verified": 1 if block_result.get("blocked") else 0,
        "adapter_preview_runtime_guard_passed": 1 if hard_block else 0,
        "no_accounting_movement_verified": 1 if hard_block and int(hard_block.payment_entry_count_before or 0) == int(hard_block.payment_entry_count_after or 0) and int(hard_block.payment_entry_gl_count_before or 0) == int(hard_block.payment_entry_gl_count_after or 0) else 0,
        "production_batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "policy_live_enabled": 0,
        "hard_block": hard_block.name if hard_block else None,
        "adapter_preview": hard_block.adapter_preview if hard_block else None,
        "runtime_guard_evidence_freeze": hard_block.runtime_guard_evidence_freeze if hard_block else None,
        "runtime_guard": hard_block.runtime_guard if hard_block else None,
        "monitor_gate": hard_block.monitor_gate if hard_block else None,
        "policy_enablement_freeze": hard_block.policy_enablement_freeze if hard_block else None,
        "enablement_run": hard_block.enablement_run if hard_block else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": hard_block.target_policy if hard_block else None,
        "target_policy_name": hard_block.target_policy_name if hard_block else None,
        "current_target_policy_enabled": current_enabled,
        "current_target_policy_live": current_live,
        "actual_enabled_policy_count": int(hard_block.actual_enabled_policy_count or 0) if hard_block else 0,
        "allowed_smoke_batch_line_count": 3,
        "allowed_smoke_batch_amount": 3,
        "allowed_smoke_payment_entry_count": 1,
        "allowed_smoke_live_posting": 0,
        "allowed_smoke_journal_entry": 0,
        "allowed_smoke_purchase_invoice": 0,
        "preview_batch_line_count": int(hard_block.preview_batch_line_count or 0) if hard_block else 0,
        "preview_batch_amount": flt(hard_block.preview_batch_amount or 0) if hard_block else 0,
        "preview_payment_entry_count": int(hard_block.preview_payment_entry_count or 0) if hard_block else 0,
        "would_create_payment_entry_count": int(hard_block.would_create_payment_entry_count or 0) if hard_block else 0,
        "would_create_gl_entry_count": int(hard_block.would_create_gl_entry_count or 0) if hard_block else 0,
        "would_use_live_posting": int(hard_block.would_use_live_posting or 0) if hard_block else 0,
        "would_create_journal_entry": int(hard_block.would_create_journal_entry or 0) if hard_block else 0,
        "would_create_purchase_invoice": int(hard_block.would_create_purchase_invoice or 0) if hard_block else 0,
        "max_batch_lines": int(hard_block.max_batch_lines or 0) if hard_block else 0,
        "max_batch_amount": flt(hard_block.max_batch_amount or 0) if hard_block else 0,
        "max_payment_entry_count": int(hard_block.max_payment_entry_count or 0) if hard_block else 0,
        "actual_adapter_execution_count": 0,
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
        "activation_score": score,
        **item_summary,
        "items": items,
        "issues": issues,
        "direct_adapter_block_result": block_result,
        "guardrails_before": guard_before,
        "guardrails_after": guard_now,
        "config": config,
        "required_acknowledgement": ACTIVATION_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 9Z allows the next guarded limited adapter smoke only. It creates no PE/GL and does not change policy flags.",
    }
    if int(dry_run or 0):
        result.update(
            {
                "status": "Needs Review",
                "activation_status": "Needs Review",
                "adapter_activation_allowed": 0,
                "ready_for_guarded_limited_adapter_smoke": 0,
                "smoke_only_allowed": 0,
            }
        )
        return result

    doc = frappe.new_doc("NDIS Limited Batch Adapter Activation Gate")
    doc.activation_gate_id = make_activation_gate_id()
    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = ACTIVATION_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    create_items(doc, items)
    frappe.db.commit()
    return {**result, "created": True, "activation_gate": doc.name, "activation_gate_id": doc.activation_gate_id, "guardrails_after": guardrails()}


@frappe.whitelist()
def cancel_limited_batch_adapter_activation_gate(activation_gate, reason=None):
    assert_action("cancel_limited_batch_adapter_activation_gate")
    if not frappe.db.exists("NDIS Limited Batch Adapter Activation Gate", activation_gate):
        frappe.throw(_("Activation gate not found: {0}").format(activation_gate))
    doc = frappe.get_doc("NDIS Limited Batch Adapter Activation Gate", activation_gate)
    if doc.status == "Cancelled":
        return {"activation_gate": activation_gate, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.adapter_activation_allowed or 0):
        frappe.throw(_("Cannot cancel an approved Phase 9Z activation gate. Create a superseding gate instead."))
    frappe.db.set_value(
        "NDIS Limited Batch Adapter Activation Gate",
        activation_gate,
        {
            "status": "Cancelled",
            "activation_status": "Cancelled",
            "adapter_activation_allowed": 0,
            "ready_for_guarded_limited_adapter_smoke": 0,
            "smoke_only_allowed": 0,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 9Z no-ack activation gate audit cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(
        """
        UPDATE `tabNDIS Limited Batch Adapter Activation Gate Item`
        SET status = 'Cancelled'
        WHERE activation_gate = %(activation_gate)s
        """,
        {"activation_gate": activation_gate},
    )
    frappe.db.commit()
    return {"activation_gate": activation_gate, "status": "Cancelled", "note": "No-ack activation gate audit cancelled only. No policy or accounting movement occurred."}


@frappe.whitelist()
def quick_limited_batch_adapter_activation_gate_summary(limit=20):
    gates = frappe.get_all(
        "NDIS Limited Batch Adapter Activation Gate",
        fields=[
            "name",
            "activation_gate_id",
            "status",
            "activation_status",
            "adapter_activation_allowed",
            "ready_for_guarded_limited_adapter_smoke",
            "smoke_only_allowed",
            "hard_block",
            "adapter_preview",
            "runtime_guard_evidence_freeze",
            "runtime_guard",
            "target_policy",
            "current_target_policy_enabled",
            "current_target_policy_live",
            "allowed_smoke_batch_line_count",
            "allowed_smoke_batch_amount",
            "allowed_smoke_payment_entry_count",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
            "production_batch_enabled_policy_count",
            "live_posting_allowed_policy_count",
            "activation_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(
        "NDIS Limited Batch Adapter Activation Gate Item",
        fields=["name", "activation_gate", "status", "severity", "category", "check_label", "detail", "source_doctype", "source_name"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "gates": gates,
        "items": items,
        "required_acknowledgement": ACTIVATION_ACK,
        "guardrails": guardrails(),
        "note": "Phase 9Z guarded limited adapter activation gate summary. No PE/GL or policy movement.",
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
            g.name AS activation_gate,
            g.activation_gate_id,
            g.status,
            g.activation_status,
            g.adapter_activation_allowed,
            g.ready_for_guarded_limited_adapter_smoke,
            g.smoke_only_allowed,
            g.hard_block,
            g.adapter_preview,
            g.runtime_guard,
            g.target_policy,
            g.current_target_policy_enabled,
            g.current_target_policy_live,
            g.allowed_smoke_batch_line_count,
            g.allowed_smoke_batch_amount,
            g.allowed_smoke_payment_entry_count,
            g.actual_payment_entry_created_count,
            g.actual_gl_created_count,
            g.production_batch_enabled_policy_count,
            g.live_posting_allowed_policy_count,
            g.activation_score,
            g.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Limited Batch Adapter Activation Gate` g
        {build_where(conditions)}
        ORDER BY g.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.activation_gate_id for row in data[:20]],
            "datasets": [
                {"name": "Activation Allowed", "values": [int(row.adapter_activation_allowed or 0) for row in data[:20]]},
                {"name": "Actual PE Created", "values": [int(row.actual_payment_entry_created_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Activation Gates"), "datatype": "Int"},
        {"value": sum(int(row.adapter_activation_allowed or 0) for row in data), "indicator": "Green", "label": _("Allowed"), "datatype": "Int"},
        {"value": sum(int(row.smoke_only_allowed or 0) for row in data), "indicator": "Green", "label": _("Smoke Only"), "datatype": "Int"},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PE"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def gate_columns():
    return [
        {"fieldname": "activation_gate", "label": _("Activation Gate"), "fieldtype": "Link", "options": "NDIS Limited Batch Adapter Activation Gate", "width": 220},
        {"fieldname": "activation_gate_id", "label": _("Activation Gate ID"), "fieldtype": "Data", "width": 440},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 140},
        {"fieldname": "activation_status", "label": _("Activation Status"), "fieldtype": "Data", "width": 320},
        {"fieldname": "adapter_activation_allowed", "label": _("Allowed"), "fieldtype": "Check", "width": 90},
        {"fieldname": "ready_for_guarded_limited_adapter_smoke", "label": _("Ready Smoke"), "fieldtype": "Check", "width": 110},
        {"fieldname": "smoke_only_allowed", "label": _("Smoke Only"), "fieldtype": "Check", "width": 100},
        {"fieldname": "hard_block", "label": _("Phase 9Y Hard Block"), "fieldtype": "Link", "options": "NDIS Limited Batch Posting Adapter Hard Block", "width": 220},
        {"fieldname": "adapter_preview", "label": _("Phase 9X Preview"), "fieldtype": "Link", "options": "NDIS Limited Batch Posting Adapter Preview", "width": 220},
        {"fieldname": "runtime_guard", "label": _("Runtime Guard"), "fieldtype": "Link", "options": "NDIS Limited Batch Runtime Guard", "width": 220},
        {"fieldname": "target_policy", "label": _("Target Policy"), "fieldtype": "Data", "width": 260},
        {"fieldname": "current_target_policy_enabled", "label": _("Current Enabled"), "fieldtype": "Check", "width": 120},
        {"fieldname": "current_target_policy_live", "label": _("Current Live"), "fieldtype": "Check", "width": 110},
        {"fieldname": "allowed_smoke_batch_line_count", "label": _("Smoke Lines"), "fieldtype": "Int", "width": 100},
        {"fieldname": "allowed_smoke_batch_amount", "label": _("Smoke Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "allowed_smoke_payment_entry_count", "label": _("Smoke PE"), "fieldtype": "Int", "width": 95},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "production_batch_enabled_policy_count", "label": _("Enabled Policies"), "fieldtype": "Int", "width": 120},
        {"fieldname": "live_posting_allowed_policy_count", "label": _("Live Policies"), "fieldtype": "Int", "width": 110},
        {"fieldname": "activation_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("activation_gate"):
        conditions.append("i.activation_gate = %(activation_gate)s")
        params["activation_gate"] = filters.get("activation_gate")
    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": "NDIS Limited Batch Adapter Activation Gate Item", "width": 220},
        {"fieldname": "activation_gate", "label": _("Activation Gate"), "fieldtype": "Link", "options": "NDIS Limited Batch Adapter Activation Gate", "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 170},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 320},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 560},
        {"fieldname": "source_doctype", "label": _("Source DocType"), "fieldtype": "Data", "width": 220},
        {"fieldname": "source_name", "label": _("Source Name"), "fieldtype": "Data", "width": 240},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            i.name AS item,
            i.activation_gate,
            i.status,
            i.severity,
            i.category,
            i.check_label,
            i.detail,
            i.source_doctype,
            i.source_name,
            i.checked_on
        FROM `tabNDIS Limited Batch Adapter Activation Gate Item` i
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
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Items", "values": list(chart_map.values())}]}, "type": "bar"}
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
