import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.limited_batch_runtime_guard import assert_limited_batch_runtime_guard
from ndis_finance.services.permissions import assert_action


PREVIEW_ACK = "I_CONFIRM_PHASE9X_PREVIEW_GUARDED_LIMITED_BATCH_POSTING_ADAPTER_NO_POSTING"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"


def make_adapter_preview_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-LIMITED-BATCH-POSTING-ADAPTER-PREVIEW-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_runtime_guard_freeze():
    rows = frappe.get_all(
        "NDIS Limited Batch Runtime Guard Evidence Freeze",
        filters={
            "status": "Frozen",
            "runtime_guard_freeze_allowed": 1,
            "ready_for_guarded_runtime_monitoring": 1,
            "phase9v_runtime_guard_verified": 1,
            "phase9u_monitor_gate_verified": 1,
            "phase9t_freeze_verified": 1,
            "phase9s_enablement_verified": 1,
            "policy_caps_verified": 1,
            "controlled_policy_enabled_verified": 1,
            "live_posting_blocked_verified": 1,
            "runtime_guard_active_verified": 1,
            "runtime_validation_ready_verified": 1,
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
            "freeze_id",
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
            "freeze_score",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    if not rows:
        return None
    freeze = rows[0]
    if flt(freeze.max_batch_amount or 0, 2) != 3:
        return None
    return freeze


def existing_preview(runtime_guard_evidence_freeze):
    rows = frappe.get_all(
        "NDIS Limited Batch Posting Adapter Preview",
        filters={
            "runtime_guard_evidence_freeze": runtime_guard_evidence_freeze,
            "status": "Previewed",
            "adapter_preview_approved": 1,
            "ready_for_guarded_limited_posting_adapter": 1,
        },
        fields=["name", "adapter_preview_id"],
        limit=1,
    )
    return rows[0] if rows else None


def validate_source(freeze, guard, config):
    issues = []
    if config["production_mode"]:
        issues.append("Production mode config must remain disabled for Phase 9X.")
    if config["live_pe_enabled"]:
        issues.append("Live Payment Entry posting config must remain disabled for Phase 9X.")
    if not freeze:
        issues.append("No frozen Phase 9W runtime guard evidence found.")
        return issues
    existing = existing_preview(freeze.name)
    if existing:
        issues.append(f"Phase 9X posting adapter preview already exists: {existing.adapter_preview_id}")
    required_links = {
        "runtime_guard": freeze.runtime_guard,
        "monitor_gate": freeze.monitor_gate,
        "policy_enablement_freeze": freeze.policy_enablement_freeze,
        "enablement_run": freeze.enablement_run,
    }
    for label, value in required_links.items():
        if not value:
            issues.append(f"Missing evidence link: {label}")
    if freeze.runtime_guard and not frappe.db.exists("NDIS Limited Batch Runtime Guard", freeze.runtime_guard):
        issues.append("Linked Phase 9V runtime guard does not exist.")
    if freeze.monitor_gate and not frappe.db.exists("NDIS Limited Production Batch Use Monitor Gate", freeze.monitor_gate):
        issues.append("Linked Phase 9U monitor gate does not exist.")
    if freeze.policy_enablement_freeze and not frappe.db.exists("NDIS Limited Production Batch Policy Enablement Freeze", freeze.policy_enablement_freeze):
        issues.append("Linked Phase 9T policy enablement freeze does not exist.")
    if freeze.enablement_run and not frappe.db.exists("NDIS Limited Production Batch Policy Enablement Run", freeze.enablement_run):
        issues.append("Linked Phase 9S enablement run does not exist.")
    if not freeze.target_policy:
        issues.append("Runtime guard freeze has no target policy.")
    elif not frappe.db.exists(POLICY_DOCTYPE, freeze.target_policy):
        issues.append(f"Target policy does not exist: {freeze.target_policy}")
    else:
        current_enabled = get_flag(POLICY_DOCTYPE, freeze.target_policy, "production_batch_enabled")
        current_live = get_flag(POLICY_DOCTYPE, freeze.target_policy, "live_posting_allowed")
        if current_enabled != 1:
            issues.append("Current target policy production_batch_enabled must be 1 before adapter preview.")
        if current_live != 0:
            issues.append("Current target policy live_posting_allowed must be 0 before adapter preview.")
    expected = {
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
    }
    for fieldname, value in expected.items():
        if int(freeze.get(fieldname) or 0) != value:
            issues.append(f"Frozen {fieldname} must be {value}.")
    if flt(freeze.max_batch_amount or 0, 2) != 3:
        issues.append("Frozen max_batch_amount must be 3.00.")
    if int(freeze.payment_entry_count_before or 0) != int(freeze.payment_entry_count_after or 0):
        issues.append("Frozen Payment Entry count changed.")
    if int(freeze.payment_entry_gl_count_before or 0) != int(freeze.payment_entry_gl_count_after or 0):
        issues.append("Frozen Payment Entry GL count changed.")
    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must be enabled before adapter preview.")
    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must be 0 before adapter preview.")
    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today is not zero.")
    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today is not zero.")
    return issues


def runtime_guard_preview_check():
    return assert_limited_batch_runtime_guard(
        batch_line_count=3,
        batch_amount=3,
        payment_entry_count=1,
        live_posting_requested=0,
        allow_journal_entry_side_effect=0,
        allow_purchase_invoice_side_effect=0,
        context="Phase 9X guarded posting adapter preview",
    )


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


def build_items(freeze, issues, ack_ok, guard, runtime_guard_passed):
    items = []
    if freeze:
        add_item(
            items,
            "Pass",
            "Low",
            "Evidence",
            "phase9w_freeze_exists",
            "Phase 9W runtime guard evidence freeze exists",
            f"Runtime guard evidence freeze found: {freeze.freeze_id}.",
            "NDIS Limited Batch Runtime Guard Evidence Freeze",
            freeze.name,
        )
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase9w_freeze_exists", "Phase 9W runtime guard evidence freeze exists", "No frozen Phase 9W evidence found.")
    if not issues:
        add_item(items, "Pass", "Low", "Preview Source", "preview_source_valid", "Preview source valid", "Frozen runtime guard evidence is valid for adapter preview.")
    else:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Preview Source", "preview_source_valid", "Preview source valid", issue)
    if runtime_guard_passed:
        add_item(items, "Pass", "Low", "Runtime Guard", "runtime_guard_passed", "Runtime guard accepts preview shape", "Preview shape passed runtime guard: 3 lines, 3.00 amount, 1 Payment Entry, no live posting, no JE/PI side effects.")
    else:
        add_item(items, "Blocker", "Critical", "Runtime Guard", "runtime_guard_passed", "Runtime guard accepts preview shape", "Runtime guard did not accept preview shape.")
    if guard["production_batch_enabled_policy_count"] == 1 and guard["live_posting_allowed_policy_count"] == 0:
        add_item(items, "Pass", "Low", "Policy Guardrail", "policy_state", "Policy state correct", "Exactly one controlled policy is enabled and live posting remains blocked.")
    else:
        add_item(items, "Blocker", "Critical", "Policy Guardrail", "policy_state", "Policy state correct", "Policy state is not 1 enabled / 0 live.")
    if freeze:
        add_item(items, "Pass", "Low", "Adapter Preview", "would_create_payment_entry", "Would create max one Payment Entry", "Future adapter shape would create at most one Payment Entry.")
        add_item(items, "Pass", "Low", "Adapter Preview", "would_use_three_lines", "Would use max three lines", "Preview shape is capped at three reference lines.")
        add_item(items, "Pass", "Low", "Adapter Preview", "would_cap_amount", "Would cap amount at 3.00", "Preview batch amount is capped at 3.00.")
        add_item(items, "Pass", "Low", "Adapter Preview", "would_not_post_live", "Would not use live posting", "Preview confirms live posting remains blocked.")
        add_item(items, "Pass", "Low", "Accounting Guardrail", "no_actual_movement", "No actual movement", "Preview created no Payment Entry and no GL Entry.")
    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {PREVIEW_ACK}")
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
        row = frappe.new_doc("NDIS Limited Batch Posting Adapter Preview Item")
        row.adapter_preview = doc.name
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
def run_limited_batch_posting_adapter_preview(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_limited_batch_posting_adapter_preview")
    freeze = latest_runtime_guard_freeze()
    config = config_state()
    guard_before = guardrails()
    ack_ok = acknowledgement == PREVIEW_ACK
    issues = validate_source(freeze, guard_before, config)
    runtime_guard_result = None
    runtime_guard_passed = False
    if freeze and not issues:
        try:
            runtime_guard_result = runtime_guard_preview_check()
            runtime_guard_passed = runtime_guard_result.get("status") == "Passed"
        except Exception as exc:
            runtime_guard_result = {"status": "Failed", "error": str(exc)}
    items = build_items(freeze, issues, ack_ok, guard_before, runtime_guard_passed)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    allowed = int(ack_ok and item_summary["blocker_count"] == 0 and bool(freeze) and runtime_guard_passed)
    guard_now = guardrails()
    current_enabled = get_flag(POLICY_DOCTYPE, freeze.target_policy, "production_batch_enabled") if freeze else 0
    current_live = get_flag(POLICY_DOCTYPE, freeze.target_policy, "live_posting_allowed") if freeze else 0

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Previewed" if allowed else "Needs Review",
        "adapter_preview_status": "Ready For Guarded Limited Posting Adapter" if allowed else "Needs Review",
        "adapter_preview_approved": allowed,
        "ready_for_guarded_limited_posting_adapter": allowed,
        "preview_only": 1,
        "phase9w_runtime_guard_freeze_verified": 1 if freeze else 0,
        "phase9v_runtime_guard_verified": 1 if freeze else 0,
        "phase9u_monitor_gate_verified": 1 if freeze else 0,
        "phase9t_freeze_verified": 1 if freeze else 0,
        "phase9s_enablement_verified": 1 if freeze else 0,
        "policy_caps_verified": 1 if freeze and int(freeze.max_batch_lines or 0) == 3 and flt(freeze.max_batch_amount or 0, 2) == 3 and int(freeze.max_payment_entry_count or 0) == 1 else 0,
        "controlled_policy_enabled_verified": 1 if current_enabled == 1 else 0,
        "live_posting_blocked_verified": 1 if current_live == 0 else 0,
        "runtime_guard_active_verified": 1 if freeze else 0,
        "runtime_validation_ready_verified": 1 if freeze else 0,
        "no_accounting_movement_verified": 1 if guard_before["payment_entry_count"] == guard_now["payment_entry_count"] and guard_before["payment_entry_gl_count"] == guard_now["payment_entry_gl_count"] else 0,
        "adapter_preview_runtime_guard_passed": 1 if runtime_guard_passed else 0,
        "production_batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "policy_live_enabled": 0,
        "runtime_guard_evidence_freeze": freeze.name if freeze else None,
        "runtime_guard": freeze.runtime_guard if freeze else None,
        "monitor_gate": freeze.monitor_gate if freeze else None,
        "policy_enablement_freeze": freeze.policy_enablement_freeze if freeze else None,
        "enablement_run": freeze.enablement_run if freeze else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": freeze.target_policy if freeze else None,
        "target_policy_name": freeze.target_policy_name if freeze else None,
        "current_target_policy_enabled": current_enabled,
        "current_target_policy_live": current_live,
        "actual_enabled_policy_count": int(freeze.actual_enabled_policy_count or 0) if freeze else 0,
        "preview_batch_line_count": 3,
        "preview_batch_amount": 3,
        "preview_payment_entry_count": 1,
        "would_create_payment_entry_count": 1,
        "would_create_gl_entry_count": 0,
        "would_use_live_posting": 0,
        "would_create_journal_entry": 0,
        "would_create_purchase_invoice": 0,
        "max_batch_lines": int(freeze.max_batch_lines or 0) if freeze else 0,
        "max_batch_amount": flt(freeze.max_batch_amount or 0) if freeze else 0,
        "max_payment_entry_count": int(freeze.max_payment_entry_count or 0) if freeze else 0,
        "runtime_guard_allows_line_count_check": int(freeze.runtime_guard_allows_line_count_check or 0) if freeze else 0,
        "runtime_guard_allows_amount_check": int(freeze.runtime_guard_allows_amount_check or 0) if freeze else 0,
        "runtime_guard_allows_payment_entry_count_check": int(freeze.runtime_guard_allows_payment_entry_count_check or 0) if freeze else 0,
        "runtime_guard_blocks_live_posting": int(freeze.runtime_guard_blocks_live_posting or 0) if freeze else 0,
        "runtime_guard_blocks_je_pi_side_effects": int(freeze.runtime_guard_blocks_je_pi_side_effects or 0) if freeze else 0,
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
        "preview_score": score,
        **item_summary,
        "items": items,
        "issues": issues,
        "runtime_guard_result": runtime_guard_result,
        "guardrails_before": guard_before,
        "guardrails_after": guard_now,
        "config": config,
        "required_acknowledgement": PREVIEW_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 9X previews the guarded posting adapter only. It creates no PE/GL and does not change policy flags.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["adapter_preview_status"] = "Needs Review"
        result["adapter_preview_approved"] = 0
        result["ready_for_guarded_limited_posting_adapter"] = 0
        return result

    doc = frappe.new_doc("NDIS Limited Batch Posting Adapter Preview")
    doc.adapter_preview_id = make_adapter_preview_id()
    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = PREVIEW_ACK
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
        "adapter_preview": doc.name,
        "adapter_preview_id": doc.adapter_preview_id,
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_limited_batch_posting_adapter_preview(adapter_preview, reason=None):
    assert_action("cancel_limited_batch_posting_adapter_preview")
    if not frappe.db.exists("NDIS Limited Batch Posting Adapter Preview", adapter_preview):
        frappe.throw(_("Adapter preview not found: {0}").format(adapter_preview))
    doc = frappe.get_doc("NDIS Limited Batch Posting Adapter Preview", adapter_preview)
    if doc.status == "Cancelled":
        return {"adapter_preview": adapter_preview, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.adapter_preview_approved or 0):
        frappe.throw(_("Cannot cancel an approved Phase 9X adapter preview. Create a superseding preview instead."))
    frappe.db.set_value(
        "NDIS Limited Batch Posting Adapter Preview",
        adapter_preview,
        {
            "status": "Cancelled",
            "adapter_preview_status": "Cancelled",
            "adapter_preview_approved": 0,
            "ready_for_guarded_limited_posting_adapter": 0,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 9X no-ack adapter preview audit cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(
        """
        UPDATE `tabNDIS Limited Batch Posting Adapter Preview Item`
        SET status = 'Cancelled'
        WHERE adapter_preview = %(adapter_preview)s
        """,
        {"adapter_preview": adapter_preview},
    )
    frappe.db.commit()
    return {
        "adapter_preview": adapter_preview,
        "status": "Cancelled",
        "note": "No-ack adapter preview cancelled only. No policy or accounting movement occurred.",
    }


@frappe.whitelist()
def quick_limited_batch_posting_adapter_preview_summary(limit=20):
    previews = frappe.get_all(
        "NDIS Limited Batch Posting Adapter Preview",
        fields=[
            "name",
            "adapter_preview_id",
            "status",
            "adapter_preview_status",
            "adapter_preview_approved",
            "ready_for_guarded_limited_posting_adapter",
            "preview_only",
            "runtime_guard_evidence_freeze",
            "runtime_guard",
            "monitor_gate",
            "target_policy",
            "current_target_policy_enabled",
            "current_target_policy_live",
            "preview_batch_line_count",
            "preview_batch_amount",
            "preview_payment_entry_count",
            "would_create_payment_entry_count",
            "would_create_gl_entry_count",
            "would_use_live_posting",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
            "production_batch_enabled_policy_count",
            "live_posting_allowed_policy_count",
            "preview_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(
        "NDIS Limited Batch Posting Adapter Preview Item",
        fields=[
            "name",
            "adapter_preview",
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
        "previews": previews,
        "items": items,
        "required_acknowledgement": PREVIEW_ACK,
        "guardrails": guardrails(),
        "note": "Phase 9X guarded posting adapter preview summary. No PE/GL or policy movement.",
    }


def execute_preview_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("p.status = %(status)s")
        params["status"] = filters.get("status")
    columns = preview_columns()
    data = frappe.db.sql(
        f"""
        SELECT
            p.name AS adapter_preview,
            p.adapter_preview_id,
            p.status,
            p.adapter_preview_status,
            p.adapter_preview_approved,
            p.ready_for_guarded_limited_posting_adapter,
            p.preview_only,
            p.runtime_guard_evidence_freeze,
            p.runtime_guard,
            p.monitor_gate,
            p.target_policy,
            p.current_target_policy_enabled,
            p.current_target_policy_live,
            p.preview_batch_line_count,
            p.preview_batch_amount,
            p.preview_payment_entry_count,
            p.would_create_payment_entry_count,
            p.would_create_gl_entry_count,
            p.would_use_live_posting,
            p.actual_payment_entry_created_count,
            p.actual_gl_created_count,
            p.production_batch_enabled_policy_count,
            p.live_posting_allowed_policy_count,
            p.preview_score,
            p.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Limited Batch Posting Adapter Preview` p
        {build_where(conditions)}
        ORDER BY p.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.adapter_preview_id for row in data[:20]],
            "datasets": [
                {"name": "Preview Approved", "values": [int(row.adapter_preview_approved or 0) for row in data[:20]]},
                {"name": "Actual PE Created", "values": [int(row.actual_payment_entry_created_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Adapter Previews"), "datatype": "Int"},
        {"value": sum(int(row.adapter_preview_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(int(row.would_create_payment_entry_count or 0) for row in data), "indicator": "Orange", "label": _("Would PE"), "datatype": "Int"},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PE"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def preview_columns():
    return [
        {"fieldname": "adapter_preview", "label": _("Adapter Preview"), "fieldtype": "Link", "options": "NDIS Limited Batch Posting Adapter Preview", "width": 220},
        {"fieldname": "adapter_preview_id", "label": _("Adapter Preview ID"), "fieldtype": "Data", "width": 450},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "adapter_preview_status", "label": _("Preview Status"), "fieldtype": "Data", "width": 320},
        {"fieldname": "adapter_preview_approved", "label": _("Approved"), "fieldtype": "Check", "width": 90},
        {"fieldname": "preview_only", "label": _("Preview Only"), "fieldtype": "Check", "width": 100},
        {"fieldname": "runtime_guard_evidence_freeze", "label": _("Phase 9W Freeze"), "fieldtype": "Link", "options": "NDIS Limited Batch Runtime Guard Evidence Freeze", "width": 220},
        {"fieldname": "runtime_guard", "label": _("Runtime Guard"), "fieldtype": "Link", "options": "NDIS Limited Batch Runtime Guard", "width": 220},
        {"fieldname": "target_policy", "label": _("Target Policy"), "fieldtype": "Data", "width": 260},
        {"fieldname": "current_target_policy_enabled", "label": _("Current Enabled"), "fieldtype": "Check", "width": 120},
        {"fieldname": "current_target_policy_live", "label": _("Current Live"), "fieldtype": "Check", "width": 110},
        {"fieldname": "preview_batch_line_count", "label": _("Preview Lines"), "fieldtype": "Int", "width": 105},
        {"fieldname": "preview_batch_amount", "label": _("Preview Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "preview_payment_entry_count", "label": _("Preview PE"), "fieldtype": "Int", "width": 100},
        {"fieldname": "would_create_payment_entry_count", "label": _("Would PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "would_create_gl_entry_count", "label": _("Would GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "would_use_live_posting", "label": _("Would Live"), "fieldtype": "Check", "width": 90},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "production_batch_enabled_policy_count", "label": _("Enabled Policies"), "fieldtype": "Int", "width": 120},
        {"fieldname": "live_posting_allowed_policy_count", "label": _("Live Policies"), "fieldtype": "Int", "width": 110},
        {"fieldname": "preview_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("adapter_preview"):
        conditions.append("i.adapter_preview = %(adapter_preview)s")
        params["adapter_preview"] = filters.get("adapter_preview")
    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": "NDIS Limited Batch Posting Adapter Preview Item", "width": 220},
        {"fieldname": "adapter_preview", "label": _("Adapter Preview"), "fieldtype": "Link", "options": "NDIS Limited Batch Posting Adapter Preview", "width": 220},
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
            i.adapter_preview,
            i.status,
            i.severity,
            i.category,
            i.check_label,
            i.detail,
            i.source_doctype,
            i.source_name,
            i.checked_on
        FROM `tabNDIS Limited Batch Posting Adapter Preview Item` i
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
    columns, data, message, chart, summary = execute_preview_report(filters)
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
