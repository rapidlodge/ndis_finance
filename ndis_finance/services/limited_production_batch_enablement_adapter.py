import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


ADAPTER_ACK = "I_CONFIRM_PHASE9M_HARD_BLOCK_LIMITED_PRODUCTION_BATCH_ENABLEMENT_NO_POSTING"
HARD_BLOCK_MESSAGE = "Phase 9M hard block: limited production batch policy enablement is not allowed in this adapter phase."


def make_enablement_adapter_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-LIMITED-PROD-BATCH-ENABLEMENT-ADAPTER-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_enablement_preview():
    rows = frappe.get_all(
        "NDIS Limited Production Batch Enablement Preview",
        filters={
            "status": "Previewed",
            "enablement_preview_approved": 1,
            "ready_for_limited_enablement_adapter": 1,
            "phase9k_enablement_design_verified": 1,
            "phase9j_policy_lock_verified": 1,
            "policy_caps_verified": 1,
            "preview_only_verified": 1,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "would_enable_policy_count": 1,
            "actual_enabled_policy_count": 0,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
        },
        fields=[
            "name",
            "enablement_preview_id",
            "enablement_gate",
            "policy_lock",
            "finalisation_gate",
            "phase9h_freeze",
            "rollback_run",
            "smoke_run",
            "activation_gate",
            "adapter_run",
            "policy_preview",
            "policy_design",
            "policy_review_gate",
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
            "actual_enabled_policy_count",
            "would_enable_policy_name",
            "preview_policy_action",
            "adapter_requirement",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
            "production_batch_enabled_policy_count",
            "live_posting_allowed_policy_count",
            "enablement_preview_score",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )

    return rows[0] if rows else None


def existing_approved_adapter(enablement_preview):
    rows = frappe.get_all(
        "NDIS Limited Production Batch Enablement Adapter Run",
        filters={
            "enablement_preview": enablement_preview,
            "status": "Hard Blocked",
            "enablement_adapter_approved": 1,
            "ready_for_limited_enablement_activation_gate": 1,
        },
        fields=["name", "enablement_adapter_id"],
        limit=1,
    )

    return rows[0] if rows else None


@frappe.whitelist()
def direct_limited_production_batch_policy_enablement():
    assert_action("direct_limited_production_batch_policy_enablement")

    frappe.throw(_(HARD_BLOCK_MESSAGE), frappe.ValidationError)


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


def validate_source(preview, guard, direct_blocked):
    issues = []

    if not preview:
        issues.append("No approved Phase 9L enablement preview found.")
        return issues

    if existing_approved_adapter(preview.name):
        issues.append("An approved Phase 9M enablement adapter already exists for this Phase 9L preview.")

    required_links = {
        "enablement_gate": preview.enablement_gate,
        "policy_lock": preview.policy_lock,
        "finalisation_gate": preview.finalisation_gate,
        "phase9h_freeze": preview.phase9h_freeze,
        "rollback_run": preview.rollback_run,
        "smoke_run": preview.smoke_run,
        "activation_gate": preview.activation_gate,
        "adapter_run": preview.adapter_run,
        "policy_preview": preview.policy_preview,
        "policy_design": preview.policy_design,
        "policy_review_gate": preview.policy_review_gate,
    }

    for label, value in required_links.items():
        if not value:
            issues.append(f"Missing evidence link: {label}")

    if not preview.payment_entry or not frappe.db.exists("Payment Entry", preview.payment_entry):
        issues.append("Preview Payment Entry evidence does not exist.")
    else:
        docstatus = int(frappe.db.get_value("Payment Entry", preview.payment_entry, "docstatus") or 0)
        if docstatus != 2:
            issues.append(f"Payment Entry must be cancelled. Found docstatus {docstatus}.")

        gl_count, gl_net = pe_gl_count_net(preview.payment_entry)

        if gl_count != int(preview.payment_entry_gl_count_after_rollback or 0):
            issues.append("Current PE GL row count does not match preview evidence.")

        if gl_count != 6:
            issues.append(f"Expected PE GL rows after rollback to be 6. Found {gl_count}.")

        if flt(gl_net, 2) != 0:
            issues.append(f"Expected PE GL net to be 0.00. Found {gl_net}.")

    if int(preview.max_batch_lines or 0) != 3:
        issues.append("Max batch lines must be 3.")

    if flt(preview.max_batch_amount or 0, 2) != 3:
        issues.append("Max batch amount must be 3.00.")

    if int(preview.max_payment_entry_count or 0) != 1:
        issues.append("Max Payment Entry count must be 1.")

    if int(preview.would_enable_policy_count or 0) != 1:
        issues.append("Phase 9L would_enable_policy_count must be 1.")

    if int(preview.actual_enabled_policy_count or 0) != 0:
        issues.append("Phase 9L actual_enabled_policy_count must be 0.")

    if int(preview.actual_payment_entry_created_count or 0) != 0:
        issues.append("Phase 9L actual Payment Entry created count must be 0.")

    if int(preview.actual_gl_created_count or 0) != 0:
        issues.append("Phase 9L actual GL created count must be 0.")

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


def build_items(preview, guard, issues, ack_ok, direct_blocked):
    items = []

    if preview:
        add_item(
            items,
            "Pass",
            "Low",
            "Phase 9L Preview",
            "phase9l_preview_exists",
            "Phase 9L enablement preview exists",
            f"Enablement preview found: {preview.enablement_preview_id}.",
            "NDIS Limited Production Batch Enablement Preview",
            preview.name,
        )
    else:
        add_item(items, "Blocker", "Critical", "Phase 9L Preview", "phase9l_preview_exists", "Phase 9L enablement preview exists", "No approved Phase 9L enablement preview found.")

    if not issues:
        add_item(items, "Pass", "Low", "Hard Block Source", "source_valid", "Adapter source valid", "Phase 9L preview is valid for hard-block adapter.")
    else:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Hard Block Source", "source_valid", "Adapter source valid", issue)

    if direct_blocked:
        add_item(items, "Pass", "Low", "Direct Block", "direct_enablement_blocked", "Direct enablement blocked", HARD_BLOCK_MESSAGE)
    else:
        add_item(items, "Blocker", "Critical", "Direct Block", "direct_enablement_blocked", "Direct enablement blocked", "Direct enablement was not blocked.")

    if preview:
        add_item(items, "Pass", "Low", "Policy Adapter", "policy_hard_blocked", "Would-enable policy hard-blocked", "One policy would be enabled later, but this adapter hard-blocks it.")
        add_item(items, "Pass", "Low", "Policy Caps", "caps_preserved", "Locked caps preserved", f"Lines {preview.max_batch_lines}, amount {preview.max_batch_amount}, PE count {preview.max_payment_entry_count}.")
        add_item(items, "Pass", "Low", "No Movement", "no_actual_movement", "No accounting/policy movement", "Adapter creates no Payment Entry, no GL, and enables no policy.")

    if guard["production_batch_enabled_policy_count"] == 0 and guard["live_posting_allowed_policy_count"] == 0:
        add_item(items, "Pass", "Low", "Policy Safety", "live_policies_zero", "Live policies disabled", "No controlled production batch policies are live-enabled.")
    else:
        add_item(items, "Blocker", "Critical", "Policy Safety", "live_policies_zero", "Live policies disabled", "Live-enabled policy found.")

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "adapter_ack", "Adapter acknowledgement", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "adapter_ack", "Adapter acknowledgement", f"Required acknowledgement not supplied: {ADAPTER_ACK}")

    return items


def create_adapter_lines(doc):
    line = frappe.new_doc("NDIS Limited Production Batch Enablement Adapter Line")
    line.enablement_adapter = doc.name
    line.line_no = 1
    line.line_label = "Controlled Limited Production Batch Policy Enablement Hard-block"
    line.line_status = "Hard Blocked"
    line.policy_doctype = "NDIS Controlled Production Batch Posting Policy"
    line.policy_name = doc.would_enable_policy_name or "LIMITED_CONTROLLED_PRODUCTION_BATCH"
    line.policy_action = "Hard-blocked enablement - no live flag changed"
    line.would_enable = 1
    line.hard_blocked = 1
    line.actual_enabled = 0
    line.direct_enablement_blocked = 1
    line.production_batch_posting_allowed = 0
    line.real_posting_allowed = 0
    line.policy_live_enabled = 0
    line.max_batch_lines = doc.max_batch_lines
    line.max_batch_amount = doc.max_batch_amount
    line.max_payment_entry_count = doc.max_payment_entry_count
    line.block_reason = HARD_BLOCK_MESSAGE
    line.checked_on = doc.checked_on
    line.insert(ignore_permissions=True)


@frappe.whitelist()
def run_limited_production_batch_enablement_adapter(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_limited_production_batch_enablement_adapter")

    preview = latest_enablement_preview()
    config = config_state()
    guard_before = guardrails()
    ack_ok = acknowledgement == ADAPTER_ACK
    direct_blocked = verify_direct_enablement_block()

    issues = validate_source(preview, guard_before, direct_blocked)
    items = build_items(preview, guard_before, issues, ack_ok, direct_blocked)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    approved = int(ack_ok and item_summary["blocker_count"] == 0 and preview is not None)

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Hard Blocked" if approved else "Needs Review",
        "enablement_adapter_status": "Ready For Limited Enablement Activation Gate" if approved else "Needs Review",
        "enablement_adapter_approved": approved,
        "ready_for_limited_enablement_activation_gate": approved,
        "phase9l_preview_verified": 1 if preview else 0,
        "phase9k_enablement_design_verified": 1 if preview else 0,
        "phase9j_policy_lock_verified": 1 if preview else 0,
        "policy_caps_verified": 1 if preview and int(preview.max_batch_lines or 0) == 3 and flt(preview.max_batch_amount or 0, 2) == 3 and int(preview.max_payment_entry_count or 0) == 1 else 0,
        "direct_enablement_blocked": int(direct_blocked or 0),
        "hard_block_verified": int(direct_blocked or 0),
        "production_batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "policy_live_enabled": 0,
        "enablement_preview": preview.name if preview else None,
        "enablement_gate": preview.enablement_gate if preview else None,
        "policy_lock": preview.policy_lock if preview else None,
        "finalisation_gate": preview.finalisation_gate if preview else None,
        "phase9h_freeze": preview.phase9h_freeze if preview else None,
        "rollback_run": preview.rollback_run if preview else None,
        "smoke_run": preview.smoke_run if preview else None,
        "activation_gate": preview.activation_gate if preview else None,
        "adapter_run": preview.adapter_run if preview else None,
        "policy_preview": preview.policy_preview if preview else None,
        "policy_design": preview.policy_design if preview else None,
        "policy_review_gate": preview.policy_review_gate if preview else None,
        "phase8g_freeze": preview.phase8g_freeze if preview else None,
        "company": preview.company if preview else None,
        "customer": preview.customer if preview else None,
        "payment_entry": preview.payment_entry if preview else None,
        "payment_entry_docstatus_after_rollback": int(preview.payment_entry_docstatus_after_rollback or 0) if preview else 0,
        "payment_entry_amount": flt(preview.payment_entry_amount or 0) if preview else 0,
        "reference_count": int(preview.reference_count or 0) if preview else 0,
        "invoice_outstanding_after_rollback_total": flt(preview.invoice_outstanding_after_rollback_total or 0) if preview else 0,
        "payment_entry_gl_count_after_rollback": int(preview.payment_entry_gl_count_after_rollback or 0) if preview else 0,
        "payment_entry_gl_net_after_rollback": flt(preview.payment_entry_gl_net_after_rollback or 0) if preview else 0,
        "max_batch_lines": int(preview.max_batch_lines or 0) if preview else 0,
        "max_batch_amount": flt(preview.max_batch_amount or 0) if preview else 0,
        "max_payment_entry_count": int(preview.max_payment_entry_count or 0) if preview else 0,
        "allowed_payment_type": preview.allowed_payment_type if preview else "Receive",
        "allowed_reference_doctype": preview.allowed_reference_doctype if preview else "Sales Invoice",
        "locked_policy_mode": preview.locked_policy_mode if preview else "Limited Controlled Production Batch",
        "approved_next_step": "Limited Enablement Activation Gate",
        "would_enable_policy_count": int(preview.would_enable_policy_count or 0) if preview else 0,
        "hard_blocked_policy_count": int(preview.would_enable_policy_count or 0) if preview else 0,
        "actual_enabled_policy_count": 0,
        "would_enable_policy_name": preview.would_enable_policy_name if preview else "LIMITED_CONTROLLED_PRODUCTION_BATCH",
        "hard_block_reason": HARD_BLOCK_MESSAGE,
        "adapter_next_step": "Limited Enablement Activation Gate",
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
        "enablement_adapter_score": score,
        **item_summary,
        "items": items,
        "guardrails_before": guard_before,
        "guardrails_after": guardrails(),
        "config": config,
        "required_acknowledgement": ADAPTER_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 9M hard-blocks enablement only. It creates no accounting movement and changes no policy flags.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["enablement_adapter_status"] = "Needs Review"
        result["enablement_adapter_approved"] = 0
        result["ready_for_limited_enablement_activation_gate"] = 0
        return result

    doc = frappe.new_doc("NDIS Limited Production Batch Enablement Adapter Run")
    doc.enablement_adapter_id = make_enablement_adapter_id()
    doc.status = result["status"]
    doc.enablement_adapter_status = result["enablement_adapter_status"]

    for fieldname in [
        "enablement_adapter_approved",
        "ready_for_limited_enablement_activation_gate",
        "phase9l_preview_verified",
        "phase9k_enablement_design_verified",
        "phase9j_policy_lock_verified",
        "policy_caps_verified",
        "direct_enablement_blocked",
        "hard_block_verified",
        "production_batch_posting_allowed",
        "real_posting_allowed",
        "policy_live_enabled",
        "enablement_preview",
        "enablement_gate",
        "policy_lock",
        "finalisation_gate",
        "phase9h_freeze",
        "rollback_run",
        "smoke_run",
        "activation_gate",
        "adapter_run",
        "policy_preview",
        "policy_design",
        "policy_review_gate",
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
        "enablement_adapter_score",
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
    doc.required_acknowledgement = ADAPTER_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    create_adapter_lines(doc)

    guard_after = guardrails()

    frappe.db.set_value(
        "NDIS Limited Production Batch Enablement Adapter Run",
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
    result["enablement_adapter"] = doc.name
    result["enablement_adapter_id"] = doc.enablement_adapter_id
    result["guardrails_after"] = guard_after

    return result


@frappe.whitelist()
def cancel_limited_production_batch_enablement_adapter(enablement_adapter, reason=None):
    assert_action("cancel_limited_production_batch_enablement_adapter")

    if not frappe.db.exists("NDIS Limited Production Batch Enablement Adapter Run", enablement_adapter):
        frappe.throw(_("Enablement adapter not found: {0}").format(enablement_adapter))

    doc = frappe.get_doc("NDIS Limited Production Batch Enablement Adapter Run", enablement_adapter)

    if doc.status == "Cancelled":
        return {"enablement_adapter": enablement_adapter, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.enablement_adapter_approved or 0):
        frappe.throw(_("Cannot cancel an approved hard-block adapter. Create a superseding adapter instead."))

    frappe.db.set_value(
        "NDIS Limited Production Batch Enablement Adapter Run",
        enablement_adapter,
        {
            "status": "Cancelled",
            "enablement_adapter_status": "Cancelled",
            "enablement_adapter_approved": 0,
            "ready_for_limited_enablement_activation_gate": 0,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "actual_enabled_policy_count": 0,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 9M enablement adapter audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        """
        UPDATE `tabNDIS Limited Production Batch Enablement Adapter Line`
        SET line_status = 'Cancelled'
        WHERE enablement_adapter = %(enablement_adapter)s
        """,
        {"enablement_adapter": enablement_adapter},
    )

    frappe.db.commit()

    return {
        "enablement_adapter": enablement_adapter,
        "status": "Cancelled",
        "note": "Enablement adapter audit record cancelled only. No accounting or policy movement occurred.",
    }


@frappe.whitelist()
def quick_limited_production_batch_enablement_adapter_summary(limit=20):
    runs = frappe.get_all(
        "NDIS Limited Production Batch Enablement Adapter Run",
        fields=[
            "name",
            "enablement_adapter_id",
            "status",
            "enablement_adapter_status",
            "enablement_adapter_approved",
            "ready_for_limited_enablement_activation_gate",
            "phase9l_preview_verified",
            "phase9k_enablement_design_verified",
            "phase9j_policy_lock_verified",
            "policy_caps_verified",
            "direct_enablement_blocked",
            "hard_block_verified",
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
            "enablement_adapter_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    lines = frappe.get_all(
        "NDIS Limited Production Batch Enablement Adapter Line",
        fields=[
            "name",
            "enablement_adapter",
            "line_no",
            "line_status",
            "policy_name",
            "policy_action",
            "would_enable",
            "hard_blocked",
            "actual_enabled",
            "direct_enablement_blocked",
            "max_batch_lines",
            "max_batch_amount",
            "max_payment_entry_count",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    return {
        "runs": runs,
        "lines": lines,
        "required_acknowledgement": ADAPTER_ACK,
        "guardrails": guardrails(),
        "config": config_state(),
        "note": "Phase 9M limited production batch enablement adapter summary. Hard-block only, no live posting enabled.",
    }


def execute_adapter_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("status"):
        conditions.append("a.status = %(status)s")
        params["status"] = filters.get("status")

    columns = adapter_columns()

    data = frappe.db.sql(
        f"""
        SELECT
            a.name AS enablement_adapter,
            a.enablement_adapter_id,
            a.status,
            a.enablement_adapter_status,
            a.enablement_adapter_approved,
            a.ready_for_limited_enablement_activation_gate,
            a.direct_enablement_blocked,
            a.hard_block_verified,
            a.enablement_preview,
            a.enablement_gate,
            a.policy_lock,
            a.payment_entry,
            a.max_batch_lines,
            a.max_batch_amount,
            a.max_payment_entry_count,
            a.would_enable_policy_count,
            a.hard_blocked_policy_count,
            a.actual_enabled_policy_count,
            a.actual_payment_entry_created_count,
            a.actual_gl_created_count,
            a.production_batch_enabled_policy_count,
            a.live_posting_allowed_policy_count,
            a.enablement_adapter_score,
            a.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Limited Production Batch Enablement Adapter Run` a
        {build_where(conditions)}
        ORDER BY a.creation DESC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.enablement_adapter_id for row in data[:20]],
            "datasets": [
                {"name": "Hard Blocked", "values": [int(row.hard_blocked_policy_count or 0) for row in data[:20]]},
                {"name": "Actually Enabled", "values": [int(row.actual_enabled_policy_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Adapter Runs"), "datatype": "Int"},
        {"value": sum(int(row.enablement_adapter_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(int(row.hard_blocked_policy_count or 0) for row in data), "indicator": "Green", "label": _("Hard Blocked Policies"), "datatype": "Int"},
        {"value": sum(int(row.actual_enabled_policy_count or 0) for row in data), "indicator": "Red", "label": _("Actual Enabled Policies"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def adapter_columns():
    return [
        {"fieldname": "enablement_adapter", "label": _("Enablement Adapter"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Adapter Run", "width": 220},
        {"fieldname": "enablement_adapter_id", "label": _("Enablement Adapter ID"), "fieldtype": "Data", "width": 460},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "enablement_adapter_status", "label": _("Adapter Status"), "fieldtype": "Data", "width": 330},
        {"fieldname": "ready_for_limited_enablement_activation_gate", "label": _("Ready Gate"), "fieldtype": "Check", "width": 110},
        {"fieldname": "direct_enablement_blocked", "label": _("Direct Blocked"), "fieldtype": "Check", "width": 110},
        {"fieldname": "enablement_preview", "label": _("Enablement Preview"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Preview", "width": 220},
        {"fieldname": "policy_lock", "label": _("Policy Lock"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Policy Lock", "width": 220},
        {"fieldname": "max_batch_lines", "label": _("Max Lines"), "fieldtype": "Int", "width": 90},
        {"fieldname": "max_batch_amount", "label": _("Max Amount"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "max_payment_entry_count", "label": _("Max PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "would_enable_policy_count", "label": _("Would Enable"), "fieldtype": "Int", "width": 110},
        {"fieldname": "hard_blocked_policy_count", "label": _("Hard Blocked"), "fieldtype": "Int", "width": 110},
        {"fieldname": "actual_enabled_policy_count", "label": _("Actual Enabled"), "fieldtype": "Int", "width": 120},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "enablement_adapter_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_line_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("enablement_adapter"):
        conditions.append("l.enablement_adapter = %(enablement_adapter)s")
        params["enablement_adapter"] = filters.get("enablement_adapter")

    if filters.get("line_status"):
        conditions.append("l.line_status = %(line_status)s")
        params["line_status"] = filters.get("line_status")

    columns = [
        {"fieldname": "line", "label": _("Line"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Adapter Line", "width": 220},
        {"fieldname": "enablement_adapter", "label": _("Enablement Adapter"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Adapter Run", "width": 220},
        {"fieldname": "line_no", "label": _("Line No"), "fieldtype": "Int", "width": 80},
        {"fieldname": "line_status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "policy_name", "label": _("Policy Name"), "fieldtype": "Data", "width": 260},
        {"fieldname": "policy_action", "label": _("Policy Action"), "fieldtype": "Data", "width": 330},
        {"fieldname": "would_enable", "label": _("Would Enable"), "fieldtype": "Check", "width": 110},
        {"fieldname": "hard_blocked", "label": _("Hard Blocked"), "fieldtype": "Check", "width": 110},
        {"fieldname": "actual_enabled", "label": _("Actual Enabled"), "fieldtype": "Check", "width": 110},
        {"fieldname": "direct_enablement_blocked", "label": _("Direct Blocked"), "fieldtype": "Check", "width": 110},
        {"fieldname": "max_batch_lines", "label": _("Max Lines"), "fieldtype": "Int", "width": 90},
        {"fieldname": "max_batch_amount", "label": _("Max Amount"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "max_payment_entry_count", "label": _("Max PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "block_reason", "label": _("Block Reason"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            l.name AS line,
            l.enablement_adapter,
            l.line_no,
            l.line_status,
            l.policy_name,
            l.policy_action,
            l.would_enable,
            l.hard_blocked,
            l.actual_enabled,
            l.direct_enablement_blocked,
            l.max_batch_lines,
            l.max_batch_amount,
            l.max_payment_entry_count,
            l.block_reason,
            l.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Limited Production Batch Enablement Adapter Line` l
        {build_where(conditions)}
        ORDER BY l.enablement_adapter DESC, l.line_no ASC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.policy_name for row in data[:20]],
            "datasets": [
                {"name": "Would Enable", "values": [int(row.would_enable or 0) for row in data[:20]]},
                {"name": "Hard Blocked", "values": [int(row.hard_blocked or 0) for row in data[:20]]},
                {"name": "Actual Enabled", "values": [int(row.actual_enabled or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Adapter Lines"), "datatype": "Int"},
        {"value": sum(int(row.would_enable or 0) for row in data), "indicator": "Blue", "label": _("Would Enable"), "datatype": "Int"},
        {"value": sum(int(row.hard_blocked or 0) for row in data), "indicator": "Green", "label": _("Hard Blocked"), "datatype": "Int"},
        {"value": sum(int(row.actual_enabled or 0) for row in data), "indicator": "Red", "label": _("Actual Enabled"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_adapter_report(filters)

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
