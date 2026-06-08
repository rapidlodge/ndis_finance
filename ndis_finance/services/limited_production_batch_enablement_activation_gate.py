import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action
from ndis_finance.services.limited_production_batch_enablement_adapter import (
    direct_limited_production_batch_policy_enablement,
)


ACTIVATION_ACK = "I_CONFIRM_PHASE9N_ALLOW_LIMITED_ENABLEMENT_ACTIVATION_GATE_NO_POSTING"


def make_activation_gate_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-LIMITED-PROD-BATCH-ENABLEMENT-ACT-GATE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def has_pe_smoke_field():
    return frappe.db.has_column("Payment Entry", "custom_ndis_limited_prod_batch_smoke")


def submitted_phase9f_smoke_pe_count():
    if not has_pe_smoke_field():
        return 0

    return count_dt(
        "Payment Entry",
        {
            "docstatus": 1,
            "custom_ndis_limited_prod_batch_smoke": 1,
        },
    )


def cancelled_phase9f_smoke_pe_count():
    if not has_pe_smoke_field():
        return 0

    return count_dt(
        "Payment Entry",
        {
            "docstatus": 2,
            "custom_ndis_limited_prod_batch_smoke": 1,
        },
    )


def config_state():
    return {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def guardrails():
    return {
        "payment_entry_count": count_dt("Payment Entry"),
        "payment_entry_gl_count": count_dt("GL Entry", {"voucher_type": "Payment Entry"}),
        "submitted_phase9f_smoke_pe_count": submitted_phase9f_smoke_pe_count(),
        "cancelled_phase9f_smoke_pe_count": cancelled_phase9f_smoke_pe_count(),
        "submitted_journal_entry_count_today": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}),
        "purchase_invoice_count_today": count_dt("Purchase Invoice", {"creation": [">=", today()]}),
        "production_batch_enabled_policy_count": count_dt("NDIS Controlled Production Batch Posting Policy", {"production_batch_enabled": 1}),
        "live_posting_allowed_policy_count": count_dt("NDIS Controlled Production Batch Posting Policy", {"live_posting_allowed": 1}),
    }


def latest_enablement_adapter():
    rows = frappe.get_all(
        "NDIS Limited Production Batch Enablement Adapter Run",
        filters={
            "status": "Hard Blocked",
            "enablement_adapter_approved": 1,
            "ready_for_limited_enablement_activation_gate": 1,
            "phase9l_preview_verified": 1,
            "phase9k_enablement_design_verified": 1,
            "phase9j_policy_lock_verified": 1,
            "policy_caps_verified": 1,
            "direct_enablement_blocked": 1,
            "hard_block_verified": 1,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "would_enable_policy_count": 1,
            "hard_blocked_policy_count": 1,
            "actual_enabled_policy_count": 0,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
        },
        fields=[
            "name",
            "enablement_adapter_id",
            "enablement_preview",
            "enablement_gate",
            "policy_lock",
            "finalisation_gate",
            "phase9h_freeze",
            "rollback_run",
            "smoke_run",
            "phase8g_freeze",
            "company",
            "customer",
            "payment_entry",
            "payment_entry_docstatus_after_rollback",
            "payment_entry_amount",
            "reference_count",
            "invoice_outstanding_after_rollback_total",
            "payment_entry_gl_count_after_rollback",
            "payment_entry_gl_net_after_rollback",
            "max_batch_lines",
            "max_batch_amount",
            "max_payment_entry_count",
            "allowed_payment_type",
            "allowed_reference_doctype",
            "locked_policy_mode",
            "approved_next_step",
            "would_enable_policy_count",
            "hard_blocked_policy_count",
            "actual_enabled_policy_count",
            "would_enable_policy_name",
            "hard_block_reason",
            "adapter_next_step",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
            "production_batch_enabled_policy_count",
            "live_posting_allowed_policy_count",
            "enablement_adapter_score",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )

    return rows[0] if rows else None


def existing_approved_gate(enablement_adapter):
    rows = frappe.get_all(
        "NDIS Limited Production Batch Enablement Activation Gate",
        filters={
            "enablement_adapter": enablement_adapter,
            "status": "Activation Allowed",
            "limited_enablement_activation_allowed": 1,
            "ready_for_limited_enablement_smoke": 1,
        },
        fields=["name", "activation_gate_id"],
        limit=1,
    )

    return rows[0] if rows else None


def verify_direct_enablement_block():
    try:
        direct_limited_production_batch_policy_enablement()
    except frappe.ValidationError:
        return 1
    except Exception:
        return 0

    return 0


def pe_gl_count_net(payment_entry):
    rows = frappe.db.sql(
        """
        SELECT COUNT(*) AS gl_count, COALESCE(SUM(debit - credit), 0) AS gl_net
        FROM `tabGL Entry`
        WHERE voucher_type='Payment Entry'
        AND voucher_no=%(payment_entry)s
        """,
        {"payment_entry": payment_entry},
        as_dict=True,
    )

    return int(rows[0].gl_count or 0), flt(rows[0].gl_net or 0, 2)


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


def validate_source(adapter, guard, direct_blocked):
    issues = []

    if not adapter:
        issues.append("No approved Phase 9M hard-block adapter found.")
        return issues

    if existing_approved_gate(adapter.name):
        issues.append("An approved Phase 9N activation gate already exists for this Phase 9M adapter.")

    required_links = {
        "enablement_preview": adapter.enablement_preview,
        "enablement_gate": adapter.enablement_gate,
        "policy_lock": adapter.policy_lock,
        "finalisation_gate": adapter.finalisation_gate,
        "phase9h_freeze": adapter.phase9h_freeze,
        "rollback_run": adapter.rollback_run,
        "smoke_run": adapter.smoke_run,
    }

    for label, value in required_links.items():
        if not value:
            issues.append(f"Missing evidence link: {label}")

    if not adapter.payment_entry or not frappe.db.exists("Payment Entry", adapter.payment_entry):
        issues.append("Adapter Payment Entry evidence does not exist.")
    else:
        docstatus = int(frappe.db.get_value("Payment Entry", adapter.payment_entry, "docstatus") or 0)
        if docstatus != 2:
            issues.append(f"Payment Entry must be cancelled. Found docstatus {docstatus}.")

        gl_count, gl_net = pe_gl_count_net(adapter.payment_entry)

        if gl_count != int(adapter.payment_entry_gl_count_after_rollback or 0):
            issues.append("Current PE GL row count does not match adapter evidence.")

        if gl_count != 6:
            issues.append(f"Expected PE GL rows after rollback to be 6. Found {gl_count}.")

        if flt(gl_net, 2) != 0:
            issues.append(f"Expected PE GL net to be 0.00. Found {gl_net}.")

    if int(adapter.max_batch_lines or 0) != 3:
        issues.append("Max batch lines must be 3.")

    if flt(adapter.max_batch_amount or 0, 2) != 3:
        issues.append("Max batch amount must be 3.00.")

    if int(adapter.max_payment_entry_count or 0) != 1:
        issues.append("Max Payment Entry count must be 1.")

    if int(adapter.would_enable_policy_count or 0) != 1:
        issues.append("Phase 9M would_enable_policy_count must be 1.")

    if int(adapter.hard_blocked_policy_count or 0) != 1:
        issues.append("Phase 9M hard_blocked_policy_count must be 1.")

    if int(adapter.actual_enabled_policy_count or 0) != 0:
        issues.append("Phase 9M actual_enabled_policy_count must be 0.")

    if int(adapter.actual_payment_entry_created_count or 0) != 0:
        issues.append("Phase 9M actual Payment Entry created count must be 0.")

    if int(adapter.actual_gl_created_count or 0) != 0:
        issues.append("Phase 9M actual GL created count must be 0.")

    if not direct_blocked:
        issues.append("Direct policy enablement hard block did not fire.")

    if guard["submitted_phase9f_smoke_pe_count"] != 0:
        issues.append("Submitted Phase 9F smoke PE count must be 0.")

    if guard["cancelled_phase9f_smoke_pe_count"] != 1:
        issues.append("Cancelled Phase 9F smoke PE count must be 1.")

    if guard["production_batch_enabled_policy_count"] != 0:
        issues.append("Controlled production batch enabled policy count is not zero.")

    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count is not zero.")

    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today is not zero.")

    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today is not zero.")

    return issues


def build_items(adapter, guard, issues, ack_ok, direct_blocked):
    items = []

    if adapter:
        add_item(
            items,
            "Pass",
            "Low",
            "Phase 9M Adapter",
            "phase9m_adapter_exists",
            "Phase 9M hard-block adapter exists",
            f"Hard-block adapter found: {adapter.enablement_adapter_id}.",
            "NDIS Limited Production Batch Enablement Adapter Run",
            adapter.name,
        )
    else:
        add_item(items, "Blocker", "Critical", "Phase 9M Adapter", "phase9m_adapter_exists", "Phase 9M hard-block adapter exists", "No approved Phase 9M hard-block adapter found.")

    if not issues:
        add_item(items, "Pass", "Low", "Activation Source", "source_valid", "Activation gate source valid", "Phase 9M hard-block evidence is valid for activation gate.")
    else:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Activation Source", "source_valid", "Activation gate source valid", issue)

    if direct_blocked:
        add_item(items, "Pass", "Low", "Direct Block", "direct_enablement_blocked", "Direct enablement still blocked", "Direct enablement hard-block is still active.")
    else:
        add_item(items, "Blocker", "Critical", "Direct Block", "direct_enablement_blocked", "Direct enablement still blocked", "Direct enablement was not blocked.")

    if adapter:
        add_item(items, "Pass", "Low", "Policy Evidence", "policy_hard_blocked", "Policy hard-block verified", "One would-enable policy was hard-blocked; no policy was enabled.")
        add_item(items, "Pass", "Low", "Policy Caps", "caps_preserved", "Locked caps preserved", f"Lines {adapter.max_batch_lines}, amount {adapter.max_batch_amount}, PE count {adapter.max_payment_entry_count}.")
        add_item(items, "Pass", "Low", "No Movement", "no_actual_movement", "No accounting/policy movement", "Activation gate creates no Payment Entry, no GL, and enables no policy.")

    if guard["production_batch_enabled_policy_count"] == 0 and guard["live_posting_allowed_policy_count"] == 0:
        add_item(items, "Pass", "Low", "Policy Safety", "live_policies_zero", "Live policies disabled", "No controlled production batch policies are live-enabled.")
    else:
        add_item(items, "Blocker", "Critical", "Policy Safety", "live_policies_zero", "Live policies disabled", "Live-enabled policy found.")

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "activation_ack", "Activation acknowledgement", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "activation_ack", "Activation acknowledgement", f"Required acknowledgement not supplied: {ACTIVATION_ACK}")

    return items


def create_items(doc, items):
    for item in items:
        row = frappe.new_doc("NDIS Limited Production Batch Enablement Activation Gate Item")
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
def run_limited_production_batch_enablement_activation_gate(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_limited_production_batch_enablement_activation_gate")

    adapter = latest_enablement_adapter()
    config = config_state()
    guard_before = guardrails()
    ack_ok = acknowledgement == ACTIVATION_ACK
    direct_blocked = verify_direct_enablement_block()

    issues = validate_source(adapter, guard_before, direct_blocked)
    items = build_items(adapter, guard_before, issues, ack_ok, direct_blocked)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    allowed = int(ack_ok and item_summary["blocker_count"] == 0 and adapter is not None)

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Activation Allowed" if allowed else "Needs Review",
        "activation_status": "Ready For Limited Controlled Enablement Smoke" if allowed else "Needs Review",
        "limited_enablement_activation_allowed": allowed,
        "ready_for_limited_enablement_smoke": allowed,
        "phase9m_adapter_verified": 1 if adapter else 0,
        "phase9l_preview_verified": 1 if adapter else 0,
        "phase9k_enablement_design_verified": 1 if adapter else 0,
        "phase9j_policy_lock_verified": 1 if adapter else 0,
        "policy_caps_verified": 1 if adapter and int(adapter.max_batch_lines or 0) == 3 and flt(adapter.max_batch_amount or 0, 2) == 3 and int(adapter.max_payment_entry_count or 0) == 1 else 0,
        "direct_enablement_blocked": int(direct_blocked or 0),
        "hard_block_verified": int(direct_blocked or 0),
        "production_batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "policy_live_enabled": 0,
        "enablement_adapter": adapter.name if adapter else None,
        "enablement_preview": adapter.enablement_preview if adapter else None,
        "enablement_gate": adapter.enablement_gate if adapter else None,
        "policy_lock": adapter.policy_lock if adapter else None,
        "finalisation_gate": adapter.finalisation_gate if adapter else None,
        "phase9h_freeze": adapter.phase9h_freeze if adapter else None,
        "rollback_run": adapter.rollback_run if adapter else None,
        "smoke_run": adapter.smoke_run if adapter else None,
        "phase8g_freeze": adapter.phase8g_freeze if adapter else None,
        "company": adapter.company if adapter else None,
        "customer": adapter.customer if adapter else None,
        "payment_entry": adapter.payment_entry if adapter else None,
        "payment_entry_docstatus_after_rollback": int(adapter.payment_entry_docstatus_after_rollback or 0) if adapter else 0,
        "payment_entry_amount": flt(adapter.payment_entry_amount or 0) if adapter else 0,
        "reference_count": int(adapter.reference_count or 0) if adapter else 0,
        "invoice_outstanding_after_rollback_total": flt(adapter.invoice_outstanding_after_rollback_total or 0) if adapter else 0,
        "payment_entry_gl_count_after_rollback": int(adapter.payment_entry_gl_count_after_rollback or 0) if adapter else 0,
        "payment_entry_gl_net_after_rollback": flt(adapter.payment_entry_gl_net_after_rollback or 0) if adapter else 0,
        "max_batch_lines": int(adapter.max_batch_lines or 0) if adapter else 0,
        "max_batch_amount": flt(adapter.max_batch_amount or 0) if adapter else 0,
        "max_payment_entry_count": int(adapter.max_payment_entry_count or 0) if adapter else 0,
        "allowed_payment_type": adapter.allowed_payment_type if adapter else "Receive",
        "allowed_reference_doctype": adapter.allowed_reference_doctype if adapter else "Sales Invoice",
        "locked_policy_mode": adapter.locked_policy_mode if adapter else "Limited Controlled Production Batch",
        "approved_next_step": "Limited Controlled Enablement Smoke",
        "would_enable_policy_count": int(adapter.would_enable_policy_count or 0) if adapter else 0,
        "hard_blocked_policy_count": int(adapter.hard_blocked_policy_count or 0) if adapter else 0,
        "actual_enabled_policy_count": 0,
        "would_enable_policy_name": adapter.would_enable_policy_name if adapter else "LIMITED_CONTROLLED_PRODUCTION_BATCH",
        "activation_gate_reason": "Phase 9N allows only the next controlled enablement smoke. It does not enable policy.",
        "activation_next_step": "Limited Controlled Enablement Smoke",
        "actual_payment_entry_created_count": 0,
        "actual_gl_created_count": 0,
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guardrails()["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guardrails()["payment_entry_gl_count"],
        "submitted_phase9f_smoke_pe_count": guard_before["submitted_phase9f_smoke_pe_count"],
        "cancelled_phase9f_smoke_pe_count": guard_before["cancelled_phase9f_smoke_pe_count"],
        "submitted_journal_entry_count_today": guard_before["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_before["purchase_invoice_count_today"],
        "production_batch_enabled_policy_count": guard_before["production_batch_enabled_policy_count"],
        "live_posting_allowed_policy_count": guard_before["live_posting_allowed_policy_count"],
        "activation_score": score,
        **item_summary,
        "items": items,
        "guardrails_before": guard_before,
        "guardrails_after": guardrails(),
        "config": config,
        "required_acknowledgement": ACTIVATION_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 9N activation gate only. It creates no accounting movement and changes no policy flags.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["activation_status"] = "Needs Review"
        result["limited_enablement_activation_allowed"] = 0
        result["ready_for_limited_enablement_smoke"] = 0
        return result

    doc = frappe.new_doc("NDIS Limited Production Batch Enablement Activation Gate")
    doc.activation_gate_id = make_activation_gate_id()
    doc.status = result["status"]
    doc.activation_status = result["activation_status"]

    for fieldname in [
        "limited_enablement_activation_allowed",
        "ready_for_limited_enablement_smoke",
        "phase9m_adapter_verified",
        "phase9l_preview_verified",
        "phase9k_enablement_design_verified",
        "phase9j_policy_lock_verified",
        "policy_caps_verified",
        "direct_enablement_blocked",
        "hard_block_verified",
        "production_batch_posting_allowed",
        "real_posting_allowed",
        "policy_live_enabled",
        "enablement_adapter",
        "enablement_preview",
        "enablement_gate",
        "policy_lock",
        "finalisation_gate",
        "phase9h_freeze",
        "rollback_run",
        "smoke_run",
        "phase8g_freeze",
        "company",
        "customer",
        "payment_entry",
        "payment_entry_docstatus_after_rollback",
        "payment_entry_amount",
        "reference_count",
        "invoice_outstanding_after_rollback_total",
        "payment_entry_gl_count_after_rollback",
        "payment_entry_gl_net_after_rollback",
        "max_batch_lines",
        "max_batch_amount",
        "max_payment_entry_count",
        "allowed_payment_type",
        "allowed_reference_doctype",
        "locked_policy_mode",
        "approved_next_step",
        "would_enable_policy_count",
        "hard_blocked_policy_count",
        "actual_enabled_policy_count",
        "would_enable_policy_name",
        "activation_gate_reason",
        "activation_next_step",
        "actual_payment_entry_created_count",
        "actual_gl_created_count",
        "payment_entry_count_before",
        "payment_entry_count_after",
        "payment_entry_gl_count_before",
        "payment_entry_gl_count_after",
        "submitted_phase9f_smoke_pe_count",
        "cancelled_phase9f_smoke_pe_count",
        "submitted_journal_entry_count_today",
        "purchase_invoice_count_today",
        "production_batch_enabled_policy_count",
        "live_posting_allowed_policy_count",
        "activation_score",
        "blocker_count",
        "warning_count",
        "pass_count",
        "info_count",
        "item_count",
    ]:
        setattr(doc, fieldname, result.get(fieldname))

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

    guard_after = guardrails()

    frappe.db.set_value(
        "NDIS Limited Production Batch Enablement Activation Gate",
        doc.name,
        {
            "payment_entry_count_after": guard_after["payment_entry_count"],
            "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
            "summary_json": safe_json({**result, "guardrails_after": guard_after}),
        },
        update_modified=False,
    )

    frappe.db.commit()

    result["created"] = True
    result["activation_gate"] = doc.name
    result["activation_gate_id"] = doc.activation_gate_id
    result["guardrails_after"] = guard_after

    return result


@frappe.whitelist()
def cancel_limited_production_batch_enablement_activation_gate(activation_gate, reason=None):
    assert_action("cancel_limited_production_batch_enablement_activation_gate")

    if not frappe.db.exists("NDIS Limited Production Batch Enablement Activation Gate", activation_gate):
        frappe.throw(_("Activation gate not found: {0}").format(activation_gate))

    doc = frappe.get_doc("NDIS Limited Production Batch Enablement Activation Gate", activation_gate)

    if doc.status == "Cancelled":
        return {"activation_gate": activation_gate, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.limited_enablement_activation_allowed or 0):
        frappe.throw(_("Cannot cancel an approved activation gate. Create a superseding gate instead."))

    frappe.db.set_value(
        "NDIS Limited Production Batch Enablement Activation Gate",
        activation_gate,
        {
            "status": "Cancelled",
            "activation_status": "Cancelled",
            "limited_enablement_activation_allowed": 0,
            "ready_for_limited_enablement_smoke": 0,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "actual_enabled_policy_count": 0,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 9N activation gate audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        """
        UPDATE `tabNDIS Limited Production Batch Enablement Activation Gate Item`
        SET status = 'Cancelled'
        WHERE activation_gate = %(activation_gate)s
        """,
        {"activation_gate": activation_gate},
    )

    frappe.db.commit()

    return {
        "activation_gate": activation_gate,
        "status": "Cancelled",
        "note": "Activation gate audit record cancelled only. No accounting or policy movement occurred.",
    }


@frappe.whitelist()
def quick_limited_production_batch_enablement_activation_gate_summary(limit=20):
    gates = frappe.get_all(
        "NDIS Limited Production Batch Enablement Activation Gate",
        fields=[
            "name",
            "activation_gate_id",
            "status",
            "activation_status",
            "limited_enablement_activation_allowed",
            "ready_for_limited_enablement_smoke",
            "phase9m_adapter_verified",
            "phase9l_preview_verified",
            "phase9k_enablement_design_verified",
            "phase9j_policy_lock_verified",
            "policy_caps_verified",
            "direct_enablement_blocked",
            "hard_block_verified",
            "enablement_adapter",
            "enablement_preview",
            "enablement_gate",
            "policy_lock",
            "payment_entry",
            "max_batch_lines",
            "max_batch_amount",
            "max_payment_entry_count",
            "would_enable_policy_count",
            "hard_blocked_policy_count",
            "actual_enabled_policy_count",
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
        "NDIS Limited Production Batch Enablement Activation Gate Item",
        fields=[
            "name",
            "activation_gate",
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
        "gates": gates,
        "items": items,
        "required_acknowledgement": ACTIVATION_ACK,
        "guardrails": guardrails(),
        "config": config_state(),
        "note": "Phase 9N limited production batch enablement activation gate summary. No live posting enabled.",
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
            g.limited_enablement_activation_allowed,
            g.ready_for_limited_enablement_smoke,
            g.direct_enablement_blocked,
            g.hard_block_verified,
            g.enablement_adapter,
            g.enablement_preview,
            g.enablement_gate,
            g.policy_lock,
            g.payment_entry,
            g.max_batch_lines,
            g.max_batch_amount,
            g.max_payment_entry_count,
            g.would_enable_policy_count,
            g.hard_blocked_policy_count,
            g.actual_enabled_policy_count,
            g.actual_payment_entry_created_count,
            g.actual_gl_created_count,
            g.production_batch_enabled_policy_count,
            g.live_posting_allowed_policy_count,
            g.activation_score,
            g.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Limited Production Batch Enablement Activation Gate` g
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
                {"name": "Activation Allowed", "values": [int(row.limited_enablement_activation_allowed or 0) for row in data[:20]]},
                {"name": "Actual Enabled", "values": [int(row.actual_enabled_policy_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Activation Gates"), "datatype": "Int"},
        {"value": sum(int(row.limited_enablement_activation_allowed or 0) for row in data), "indicator": "Green", "label": _("Allowed"), "datatype": "Int"},
        {"value": sum(int(row.hard_blocked_policy_count or 0) for row in data), "indicator": "Green", "label": _("Hard Blocked Policies"), "datatype": "Int"},
        {"value": sum(int(row.actual_enabled_policy_count or 0) for row in data), "indicator": "Red", "label": _("Actual Enabled Policies"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def gate_columns():
    return [
        {"fieldname": "activation_gate", "label": _("Activation Gate"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Activation Gate", "width": 220},
        {"fieldname": "activation_gate_id", "label": _("Activation Gate ID"), "fieldtype": "Data", "width": 460},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 140},
        {"fieldname": "activation_status", "label": _("Activation Status"), "fieldtype": "Data", "width": 330},
        {"fieldname": "ready_for_limited_enablement_smoke", "label": _("Ready Smoke"), "fieldtype": "Check", "width": 110},
        {"fieldname": "direct_enablement_blocked", "label": _("Direct Blocked"), "fieldtype": "Check", "width": 110},
        {"fieldname": "enablement_adapter", "label": _("Enablement Adapter"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Adapter Run", "width": 220},
        {"fieldname": "policy_lock", "label": _("Policy Lock"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Policy Lock", "width": 220},
        {"fieldname": "max_batch_lines", "label": _("Max Lines"), "fieldtype": "Int", "width": 90},
        {"fieldname": "max_batch_amount", "label": _("Max Amount"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "max_payment_entry_count", "label": _("Max PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "would_enable_policy_count", "label": _("Would Enable"), "fieldtype": "Int", "width": 110},
        {"fieldname": "hard_blocked_policy_count", "label": _("Hard Blocked"), "fieldtype": "Int", "width": 110},
        {"fieldname": "actual_enabled_policy_count", "label": _("Actual Enabled"), "fieldtype": "Int", "width": 120},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL"), "fieldtype": "Int", "width": 90},
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
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Activation Gate Item", "width": 220},
        {"fieldname": "activation_gate", "label": _("Activation Gate"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Activation Gate", "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 170},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 300},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 520},
        {"fieldname": "source_doctype", "label": _("Source DocType"), "fieldtype": "Data", "width": 200},
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
        FROM `tabNDIS Limited Production Batch Enablement Activation Gate Item` i
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
    columns, data, message, chart, summary = execute_gate_report(filters)

    guard = guardrails()

    summary.append({"value": guard["payment_entry_count"], "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"})
    summary.append({"value": guard["payment_entry_gl_count"], "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"})
    summary.append({"value": guard["submitted_phase9f_smoke_pe_count"], "indicator": "Red", "label": _("Submitted Phase 9F PE"), "datatype": "Int"})
    summary.append({"value": guard["cancelled_phase9f_smoke_pe_count"], "indicator": "Green", "label": _("Cancelled Phase 9F PE"), "datatype": "Int"})
    summary.append({"value": guard["submitted_journal_entry_count_today"], "indicator": "Red", "label": _("Submitted JE Today"), "datatype": "Int"})
    summary.append({"value": guard["purchase_invoice_count_today"], "indicator": "Red", "label": _("Purchase Invoice Today"), "datatype": "Int"})
    summary.append({"value": guard["production_batch_enabled_policy_count"], "indicator": "Red", "label": _("Production Batch Enabled Policies"), "datatype": "Int"})
    summary.append({"value": guard["live_posting_allowed_policy_count"], "indicator": "Red", "label": _("Live Posting Allowed Policies"), "datatype": "Int"})

    return columns, data, message, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
