import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


HARD_BLOCK_ACK = "I_CONFIRM_PHASE9Y_HARD_BLOCK_GUARDED_LIMITED_BATCH_POSTING_ADAPTER_NO_POSTING"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"


def make_hard_block_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-LIMITED-BATCH-POSTING-ADAPTER-HARD-BLOCK-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


@frappe.whitelist()
def direct_guarded_limited_batch_posting_adapter(*args, **kwargs):
    frappe.throw(
        _(
            "Guarded limited batch posting adapter is hard-blocked. "
            "Phase 9Y only proves the block. No Payment Entry or GL creation is allowed."
        ),
        frappe.ValidationError,
    )


def latest_adapter_preview():
    rows = frappe.get_all(
        "NDIS Limited Batch Posting Adapter Preview",
        filters={
            "status": "Previewed",
            "adapter_preview_approved": 1,
            "ready_for_guarded_limited_posting_adapter": 1,
            "preview_only": 1,
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
            "preview_batch_line_count": 3,
            "preview_payment_entry_count": 1,
            "would_create_payment_entry_count": 1,
            "would_create_gl_entry_count": 0,
            "would_use_live_posting": 0,
            "would_create_journal_entry": 0,
            "would_create_purchase_invoice": 0,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
            "production_batch_enabled_policy_count": 1,
            "live_posting_allowed_policy_count": 0,
        },
        fields=[
            "name",
            "adapter_preview_id",
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
            "preview_score",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    if not rows:
        return None
    preview = rows[0]
    if flt(preview.preview_batch_amount or 0, 2) != 3:
        return None
    if flt(preview.max_batch_amount or 0, 2) != 3:
        return None
    return preview


def existing_hard_block(adapter_preview):
    rows = frappe.get_all(
        "NDIS Limited Batch Posting Adapter Hard Block",
        filters={
            "adapter_preview": adapter_preview,
            "status": "Hard Blocked",
            "adapter_hard_blocked": 1,
            "direct_adapter_execution_blocked": 1,
            "ready_for_guarded_adapter_activation_gate": 1,
        },
        fields=["name", "hard_block_id"],
        limit=1,
    )
    return rows[0] if rows else None


def validate_source(preview, guard, config):
    issues = []
    if config["production_mode"]:
        issues.append("Production mode config must remain disabled for Phase 9Y.")
    if config["live_pe_enabled"]:
        issues.append("Live Payment Entry posting config must remain disabled for Phase 9Y.")
    if not preview:
        issues.append("No approved Phase 9X guarded adapter preview found.")
        return issues
    existing = existing_hard_block(preview.name)
    if existing:
        issues.append(f"Phase 9Y hard block already exists for this adapter preview: {existing.hard_block_id}")
    required_links = {
        "runtime_guard_evidence_freeze": preview.runtime_guard_evidence_freeze,
        "runtime_guard": preview.runtime_guard,
        "monitor_gate": preview.monitor_gate,
        "policy_enablement_freeze": preview.policy_enablement_freeze,
        "enablement_run": preview.enablement_run,
    }
    for label, value in required_links.items():
        if not value:
            issues.append(f"Missing evidence link: {label}")
    if preview.runtime_guard_evidence_freeze and not frappe.db.exists("NDIS Limited Batch Runtime Guard Evidence Freeze", preview.runtime_guard_evidence_freeze):
        issues.append("Linked Phase 9W runtime guard freeze does not exist.")
    if preview.runtime_guard and not frappe.db.exists("NDIS Limited Batch Runtime Guard", preview.runtime_guard):
        issues.append("Linked Phase 9V runtime guard does not exist.")
    if preview.monitor_gate and not frappe.db.exists("NDIS Limited Production Batch Use Monitor Gate", preview.monitor_gate):
        issues.append("Linked Phase 9U monitor gate does not exist.")
    if preview.target_policy and not frappe.db.exists(POLICY_DOCTYPE, preview.target_policy):
        issues.append(f"Target policy does not exist: {preview.target_policy}")
    if preview.target_policy:
        current_enabled = get_flag(POLICY_DOCTYPE, preview.target_policy, "production_batch_enabled")
        current_live = get_flag(POLICY_DOCTYPE, preview.target_policy, "live_posting_allowed")
        if current_enabled != 1:
            issues.append("Current target policy production_batch_enabled must be 1 before hard-block proof.")
        if current_live != 0:
            issues.append("Current target policy live_posting_allowed must be 0 before hard-block proof.")
    required_ints = {
        "preview_batch_line_count": (preview.preview_batch_line_count, 3),
        "preview_payment_entry_count": (preview.preview_payment_entry_count, 1),
        "would_create_payment_entry_count": (preview.would_create_payment_entry_count, 1),
        "would_create_gl_entry_count": (preview.would_create_gl_entry_count, 0),
        "actual_payment_entry_created_count": (preview.actual_payment_entry_created_count, 0),
        "actual_gl_created_count": (preview.actual_gl_created_count, 0),
        "max_batch_lines": (preview.max_batch_lines, 3),
        "max_payment_entry_count": (preview.max_payment_entry_count, 1),
    }
    for label, pair in required_ints.items():
        value, expected = pair
        if int(value or 0) != expected:
            issues.append(f"{label} must be {expected}.")
    if flt(preview.preview_batch_amount or 0, 2) != 3:
        issues.append("preview_batch_amount must be 3.00.")
    if flt(preview.max_batch_amount or 0, 2) != 3:
        issues.append("max_batch_amount must be 3.00.")
    for label in ["would_use_live_posting", "would_create_journal_entry", "would_create_purchase_invoice"]:
        if int(preview.get(label) or 0) != 0:
            issues.append(f"{label} must be 0.")
    if int(preview.current_target_policy_enabled or 0) != 1:
        issues.append("current_target_policy_enabled must be 1.")
    if int(preview.current_target_policy_live or 0) != 0:
        issues.append("current_target_policy_live must be 0.")
    if int(preview.actual_enabled_policy_count or 0) != 1:
        issues.append("actual_enabled_policy_count must be 1.")
    if int(preview.payment_entry_count_before or 0) != int(preview.payment_entry_count_after or 0):
        issues.append("Phase 9X Payment Entry count changed.")
    if int(preview.payment_entry_gl_count_before or 0) != int(preview.payment_entry_gl_count_after or 0):
        issues.append("Phase 9X Payment Entry GL count changed.")
    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must be enabled before hard-block proof.")
    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must be 0 before hard-block proof.")
    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today is not zero.")
    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today is not zero.")
    return issues


def prove_direct_adapter_blocked():
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


def build_items(preview, issues, ack_ok, guard, block_result):
    items = []
    if preview:
        add_item(
            items,
            "Pass",
            "Low",
            "Evidence",
            "phase9x_preview_exists",
            "Phase 9X adapter preview exists",
            f"Adapter preview found: {preview.adapter_preview_id}.",
            "NDIS Limited Batch Posting Adapter Preview",
            preview.name,
        )
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase9x_preview_exists", "Phase 9X adapter preview exists", "No approved Phase 9X adapter preview found.")
    if not issues:
        add_item(items, "Pass", "Low", "Preview Source", "preview_source_valid", "Preview source valid", "Phase 9X preview evidence is valid for hard-block proof.")
    else:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Preview Source", "preview_source_valid", "Preview source valid", issue)
    if block_result.get("blocked"):
        add_item(items, "Pass", "Low", "Hard Block", "direct_adapter_blocked", "Direct adapter execution blocked", block_result.get("error_message"))
    else:
        add_item(items, "Blocker", "Critical", "Hard Block", "direct_adapter_blocked", "Direct adapter execution blocked", block_result.get("error_message"))
    if guard["production_batch_enabled_policy_count"] == 1 and guard["live_posting_allowed_policy_count"] == 0:
        add_item(items, "Pass", "Low", "Policy Guardrail", "policy_state", "Policy state correct", "Exactly one controlled policy is enabled and live posting remains blocked.")
    else:
        add_item(items, "Blocker", "Critical", "Policy Guardrail", "policy_state", "Policy state correct", "Policy state is not 1 enabled / 0 live.")
    if preview:
        add_item(items, "Pass", "Low", "Adapter Guardrail", "no_actual_payment_entry", "No actual Payment Entry created", "Hard-block phase created no Payment Entry.")
        add_item(items, "Pass", "Low", "Adapter Guardrail", "no_actual_gl", "No actual GL created", "Hard-block phase created no GL Entry.")
        add_item(items, "Pass", "Low", "Adapter Guardrail", "no_live_posting", "Live posting blocked", "Adapter hard-block keeps live posting blocked.")
        add_item(items, "Pass", "Low", "Adapter Guardrail", "no_je_pi", "No JE/PI side effects", "Adapter hard-block keeps JE/PI side effects blocked.")
    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {HARD_BLOCK_ACK}")
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
        row = frappe.new_doc("NDIS Limited Batch Posting Adapter Hard Block Item")
        row.hard_block = doc.name
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
def run_limited_batch_posting_adapter_hard_block(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_limited_batch_posting_adapter_hard_block")
    preview = latest_adapter_preview()
    config = config_state()
    guard_before = guardrails()
    ack_ok = acknowledgement == HARD_BLOCK_ACK
    issues = validate_source(preview, guard_before, config)
    block_result = prove_direct_adapter_blocked()
    direct_blocked = int(block_result.get("blocked") or 0)
    items = build_items(preview, issues, ack_ok, guard_before, block_result)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    allowed = int(ack_ok and item_summary["blocker_count"] == 0 and bool(preview) and direct_blocked)
    guard_now = guardrails()
    current_enabled = get_flag(POLICY_DOCTYPE, preview.target_policy, "production_batch_enabled") if preview else 0
    current_live = get_flag(POLICY_DOCTYPE, preview.target_policy, "live_posting_allowed") if preview else 0
    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Hard Blocked" if allowed else "Needs Review",
        "adapter_status": "Guarded Posting Adapter Hard-Blocked" if allowed else "Needs Review",
        "adapter_hard_blocked": allowed,
        "direct_adapter_execution_blocked": direct_blocked,
        "ready_for_guarded_adapter_activation_gate": allowed,
        "preview_only_evidence_verified": 1 if preview else 0,
        "phase9x_adapter_preview_verified": 1 if preview else 0,
        "phase9w_runtime_guard_freeze_verified": 1 if preview else 0,
        "phase9v_runtime_guard_verified": 1 if preview else 0,
        "phase9u_monitor_gate_verified": 1 if preview else 0,
        "phase9t_freeze_verified": 1 if preview else 0,
        "phase9s_enablement_verified": 1 if preview else 0,
        "policy_caps_verified": 1 if preview and int(preview.max_batch_lines or 0) == 3 and flt(preview.max_batch_amount or 0, 2) == 3 and int(preview.max_payment_entry_count or 0) == 1 else 0,
        "controlled_policy_enabled_verified": 1 if current_enabled == 1 else 0,
        "live_posting_blocked_verified": 1 if current_live == 0 else 0,
        "runtime_guard_active_verified": 1 if preview else 0,
        "runtime_validation_ready_verified": 1 if preview else 0,
        "adapter_preview_runtime_guard_passed": 1 if preview else 0,
        "no_accounting_movement_verified": 1 if guard_before["payment_entry_count"] == guard_now["payment_entry_count"] and guard_before["payment_entry_gl_count"] == guard_now["payment_entry_gl_count"] else 0,
        "production_batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "policy_live_enabled": 0,
        "adapter_preview": preview.name if preview else None,
        "runtime_guard_evidence_freeze": preview.runtime_guard_evidence_freeze if preview else None,
        "runtime_guard": preview.runtime_guard if preview else None,
        "monitor_gate": preview.monitor_gate if preview else None,
        "policy_enablement_freeze": preview.policy_enablement_freeze if preview else None,
        "enablement_run": preview.enablement_run if preview else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": preview.target_policy if preview else None,
        "target_policy_name": preview.target_policy_name if preview else None,
        "current_target_policy_enabled": current_enabled,
        "current_target_policy_live": current_live,
        "actual_enabled_policy_count": int(preview.actual_enabled_policy_count or 0) if preview else 0,
        "preview_batch_line_count": int(preview.preview_batch_line_count or 0) if preview else 0,
        "preview_batch_amount": flt(preview.preview_batch_amount or 0) if preview else 0,
        "preview_payment_entry_count": int(preview.preview_payment_entry_count or 0) if preview else 0,
        "would_create_payment_entry_count": int(preview.would_create_payment_entry_count or 0) if preview else 0,
        "would_create_gl_entry_count": int(preview.would_create_gl_entry_count or 0) if preview else 0,
        "would_use_live_posting": int(preview.would_use_live_posting or 0) if preview else 0,
        "would_create_journal_entry": int(preview.would_create_journal_entry or 0) if preview else 0,
        "would_create_purchase_invoice": int(preview.would_create_purchase_invoice or 0) if preview else 0,
        "max_batch_lines": int(preview.max_batch_lines or 0) if preview else 0,
        "max_batch_amount": flt(preview.max_batch_amount or 0) if preview else 0,
        "max_payment_entry_count": int(preview.max_payment_entry_count or 0) if preview else 0,
        "runtime_guard_blocks_live_posting": int(preview.runtime_guard_blocks_live_posting or 0) if preview else 0,
        "runtime_guard_blocks_je_pi_side_effects": int(preview.runtime_guard_blocks_je_pi_side_effects or 0) if preview else 0,
        "direct_adapter_attempted": 1,
        "direct_adapter_error_type": block_result.get("error_type"),
        "direct_adapter_error_message": block_result.get("error_message"),
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
        "hard_block_score": score,
        **item_summary,
        "items": items,
        "issues": issues,
        "block_result": block_result,
        "guardrails_before": guard_before,
        "guardrails_after": guard_now,
        "config": config,
        "required_acknowledgement": HARD_BLOCK_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 9Y proves direct guarded posting adapter execution is hard-blocked. It creates no PE/GL and does not change policy flags.",
    }
    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["adapter_status"] = "Needs Review"
        result["adapter_hard_blocked"] = 0
        result["ready_for_guarded_adapter_activation_gate"] = 0
        return result
    doc = frappe.new_doc("NDIS Limited Batch Posting Adapter Hard Block")
    doc.hard_block_id = make_hard_block_id()
    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = HARD_BLOCK_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    create_items(doc, items)
    frappe.db.commit()
    return {**result, "created": True, "hard_block": doc.name, "hard_block_id": doc.hard_block_id, "guardrails_after": guardrails()}


@frappe.whitelist()
def cancel_limited_batch_posting_adapter_hard_block(hard_block, reason=None):
    assert_action("cancel_limited_batch_posting_adapter_hard_block")
    if not frappe.db.exists("NDIS Limited Batch Posting Adapter Hard Block", hard_block):
        frappe.throw(_("Adapter hard block not found: {0}").format(hard_block))
    doc = frappe.get_doc("NDIS Limited Batch Posting Adapter Hard Block", hard_block)
    if doc.status == "Cancelled":
        return {"hard_block": hard_block, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.adapter_hard_blocked or 0):
        frappe.throw(_("Cannot cancel an approved Phase 9Y hard-block proof. Create a superseding hard-block record instead."))
    frappe.db.set_value(
        "NDIS Limited Batch Posting Adapter Hard Block",
        hard_block,
        {
            "status": "Cancelled",
            "adapter_status": "Cancelled",
            "adapter_hard_blocked": 0,
            "ready_for_guarded_adapter_activation_gate": 0,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 9Y no-ack adapter hard-block audit cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(
        """
        UPDATE `tabNDIS Limited Batch Posting Adapter Hard Block Item`
        SET status = 'Cancelled'
        WHERE hard_block = %(hard_block)s
        """,
        {"hard_block": hard_block},
    )
    frappe.db.commit()
    return {"hard_block": hard_block, "status": "Cancelled", "note": "No-ack hard-block audit cancelled only. No policy or accounting movement occurred."}


@frappe.whitelist()
def quick_limited_batch_posting_adapter_hard_block_summary(limit=20):
    hard_blocks = frappe.get_all(
        "NDIS Limited Batch Posting Adapter Hard Block",
        fields=[
            "name",
            "hard_block_id",
            "status",
            "adapter_status",
            "adapter_hard_blocked",
            "direct_adapter_execution_blocked",
            "ready_for_guarded_adapter_activation_gate",
            "adapter_preview",
            "runtime_guard_evidence_freeze",
            "runtime_guard",
            "target_policy",
            "current_target_policy_enabled",
            "current_target_policy_live",
            "would_create_payment_entry_count",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
            "production_batch_enabled_policy_count",
            "live_posting_allowed_policy_count",
            "hard_block_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(
        "NDIS Limited Batch Posting Adapter Hard Block Item",
        fields=["name", "hard_block", "status", "severity", "category", "check_label", "detail", "source_doctype", "source_name"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "hard_blocks": hard_blocks,
        "items": items,
        "required_acknowledgement": HARD_BLOCK_ACK,
        "guardrails": guardrails(),
        "note": "Phase 9Y guarded posting adapter hard-block summary. No PE/GL or policy movement.",
    }


def execute_hard_block_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("h.status = %(status)s")
        params["status"] = filters.get("status")
    columns = hard_block_columns()
    data = frappe.db.sql(
        f"""
        SELECT
            h.name AS hard_block,
            h.hard_block_id,
            h.status,
            h.adapter_status,
            h.adapter_hard_blocked,
            h.direct_adapter_execution_blocked,
            h.ready_for_guarded_adapter_activation_gate,
            h.adapter_preview,
            h.runtime_guard_evidence_freeze,
            h.runtime_guard,
            h.target_policy,
            h.current_target_policy_enabled,
            h.current_target_policy_live,
            h.preview_batch_line_count,
            h.preview_batch_amount,
            h.preview_payment_entry_count,
            h.would_create_payment_entry_count,
            h.actual_payment_entry_created_count,
            h.actual_gl_created_count,
            h.production_batch_enabled_policy_count,
            h.live_posting_allowed_policy_count,
            h.hard_block_score,
            h.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Limited Batch Posting Adapter Hard Block` h
        {build_where(conditions)}
        ORDER BY h.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.hard_block_id for row in data[:20]],
            "datasets": [
                {"name": "Hard Blocked", "values": [int(row.adapter_hard_blocked or 0) for row in data[:20]]},
                {"name": "Actual PE Created", "values": [int(row.actual_payment_entry_created_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Hard Blocks"), "datatype": "Int"},
        {"value": sum(int(row.adapter_hard_blocked or 0) for row in data), "indicator": "Green", "label": _("Hard Blocked"), "datatype": "Int"},
        {"value": sum(int(row.direct_adapter_execution_blocked or 0) for row in data), "indicator": "Green", "label": _("Direct Blocked"), "datatype": "Int"},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PE"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def hard_block_columns():
    return [
        {"fieldname": "hard_block", "label": _("Hard Block"), "fieldtype": "Link", "options": "NDIS Limited Batch Posting Adapter Hard Block", "width": 220},
        {"fieldname": "hard_block_id", "label": _("Hard Block ID"), "fieldtype": "Data", "width": 460},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "adapter_status", "label": _("Adapter Status"), "fieldtype": "Data", "width": 300},
        {"fieldname": "adapter_hard_blocked", "label": _("Hard Blocked"), "fieldtype": "Check", "width": 110},
        {"fieldname": "direct_adapter_execution_blocked", "label": _("Direct Blocked"), "fieldtype": "Check", "width": 120},
        {"fieldname": "ready_for_guarded_adapter_activation_gate", "label": _("Ready Gate"), "fieldtype": "Check", "width": 100},
        {"fieldname": "adapter_preview", "label": _("Phase 9X Preview"), "fieldtype": "Link", "options": "NDIS Limited Batch Posting Adapter Preview", "width": 220},
        {"fieldname": "runtime_guard", "label": _("Runtime Guard"), "fieldtype": "Link", "options": "NDIS Limited Batch Runtime Guard", "width": 220},
        {"fieldname": "target_policy", "label": _("Target Policy"), "fieldtype": "Data", "width": 260},
        {"fieldname": "current_target_policy_enabled", "label": _("Current Enabled"), "fieldtype": "Check", "width": 120},
        {"fieldname": "current_target_policy_live", "label": _("Current Live"), "fieldtype": "Check", "width": 110},
        {"fieldname": "preview_batch_line_count", "label": _("Preview Lines"), "fieldtype": "Int", "width": 105},
        {"fieldname": "preview_batch_amount", "label": _("Preview Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "preview_payment_entry_count", "label": _("Preview PE"), "fieldtype": "Int", "width": 100},
        {"fieldname": "would_create_payment_entry_count", "label": _("Would PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "production_batch_enabled_policy_count", "label": _("Enabled Policies"), "fieldtype": "Int", "width": 120},
        {"fieldname": "live_posting_allowed_policy_count", "label": _("Live Policies"), "fieldtype": "Int", "width": 110},
        {"fieldname": "hard_block_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("hard_block"):
        conditions.append("i.hard_block = %(hard_block)s")
        params["hard_block"] = filters.get("hard_block")
    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": "NDIS Limited Batch Posting Adapter Hard Block Item", "width": 220},
        {"fieldname": "hard_block", "label": _("Hard Block"), "fieldtype": "Link", "options": "NDIS Limited Batch Posting Adapter Hard Block", "width": 220},
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
            i.hard_block,
            i.status,
            i.severity,
            i.category,
            i.check_label,
            i.detail,
            i.source_doctype,
            i.source_name,
            i.checked_on
        FROM `tabNDIS Limited Batch Posting Adapter Hard Block Item` i
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
    columns, data, message, chart, summary = execute_hard_block_report(filters)
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
