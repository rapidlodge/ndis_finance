import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


PREVIEW_ACK = "I_CONFIRM_PHASE9L_PREVIEW_LIMITED_PRODUCTION_BATCH_ENABLEMENT_NO_POSTING"


def make_enablement_preview_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-LIMITED-PROD-BATCH-ENABLEMENT-PREVIEW-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_enablement_design_gate():
    rows = frappe.get_all(
        "NDIS Limited Production Batch Enablement Design Gate",
        filters={
            "status": "Approved",
            "enablement_design_approved": 1,
            "ready_for_limited_enablement_preview": 1,
            "phase9j_policy_lock_verified": 1,
            "phase9i_finalisation_verified": 1,
            "phase9h_freeze_verified": 1,
            "policy_caps_verified": 1,
            "no_accounting_movement_verified": 1,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
        },
        fields=[
            "name",
            "enablement_gate_id",
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
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
            "production_batch_enabled_policy_count",
            "live_posting_allowed_policy_count",
            "enablement_score",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )

    return rows[0] if rows else None


def existing_approved_preview(enablement_gate):
    rows = frappe.get_all(
        "NDIS Limited Production Batch Enablement Preview",
        filters={
            "enablement_gate": enablement_gate,
            "status": "Previewed",
            "enablement_preview_approved": 1,
            "ready_for_limited_enablement_adapter": 1,
        },
        fields=["name", "enablement_preview_id"],
        limit=1,
    )

    return rows[0] if rows else None


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


def validate_source(gate, guard):
    issues = []

    if not gate:
        issues.append("No approved Phase 9K enablement design gate found.")
        return issues

    if existing_approved_preview(gate.name):
        issues.append("An approved Phase 9L enablement preview already exists for this Phase 9K design gate.")

    required_links = {
        "policy_lock": gate.policy_lock,
        "finalisation_gate": gate.finalisation_gate,
        "phase9h_freeze": gate.phase9h_freeze,
        "rollback_run": gate.rollback_run,
        "smoke_run": gate.smoke_run,
        "activation_gate": gate.activation_gate,
        "adapter_run": gate.adapter_run,
        "policy_preview": gate.policy_preview,
        "policy_design": gate.policy_design,
        "policy_review_gate": gate.policy_review_gate,
    }

    for label, value in required_links.items():
        if not value:
            issues.append(f"Missing evidence link: {label}")

    if not gate.payment_entry or not frappe.db.exists("Payment Entry", gate.payment_entry):
        issues.append("Enablement design Payment Entry does not exist.")
    else:
        docstatus = int(frappe.db.get_value("Payment Entry", gate.payment_entry, "docstatus") or 0)
        if docstatus != 2:
            issues.append(f"Payment Entry must be cancelled. Found docstatus {docstatus}.")

        gl_count, gl_net = pe_gl_count_net(gate.payment_entry)

        if gl_count != int(gate.payment_entry_gl_count_after_rollback or 0):
            issues.append("Current PE GL row count does not match enablement design evidence.")

        if gl_count != 6:
            issues.append(f"Expected PE GL rows after rollback to be 6. Found {gl_count}.")

        if flt(gl_net, 2) != 0:
            issues.append(f"Expected PE GL net to be 0.00. Found {gl_net}.")

    if int(gate.max_batch_lines or 0) != 3:
        issues.append("Max batch lines must be 3.")

    if flt(gate.max_batch_amount or 0, 2) != 3:
        issues.append("Max batch amount must be 3.00.")

    if int(gate.max_payment_entry_count or 0) != 1:
        issues.append("Max Payment Entry count must be 1.")

    if int(gate.actual_payment_entry_created_count or 0) != 0:
        issues.append("Phase 9K actual Payment Entry created count must be 0.")

    if int(gate.actual_gl_created_count or 0) != 0:
        issues.append("Phase 9K actual GL created count must be 0.")

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


def build_items(gate, guard, issues, ack_ok):
    items = []

    if gate:
        add_item(
            items,
            "Pass",
            "Low",
            "Phase 9K Enablement Design",
            "phase9k_gate_exists",
            "Phase 9K enablement design exists",
            f"Enablement design gate found: {gate.enablement_gate_id}.",
            "NDIS Limited Production Batch Enablement Design Gate",
            gate.name,
        )
    else:
        add_item(items, "Blocker", "Critical", "Phase 9K Enablement Design", "phase9k_gate_exists", "Phase 9K enablement design exists", "No approved Phase 9K enablement design gate found.")

    if not issues:
        add_item(items, "Pass", "Low", "Enablement Preview Source", "source_valid", "Enablement preview source valid", "Phase 9K design and locked caps are valid for preview.")
    else:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Enablement Preview Source", "source_valid", "Enablement preview source valid", issue)

    if gate:
        add_item(items, "Pass", "Low", "Policy Preview", "would_enable_policy", "Would-enable policy preview", "One controlled limited production batch policy would be enabled in a later hard-blocked adapter.")
        add_item(items, "Pass", "Low", "Policy Caps", "caps_preserved", "Locked caps preserved", f"Lines {gate.max_batch_lines}, amount {gate.max_batch_amount}, PE count {gate.max_payment_entry_count}.")
        add_item(items, "Pass", "Low", "No Movement", "no_actual_movement", "No accounting movement", "Preview creates no Payment Entry, no GL, and enables no policy.")

    if guard["production_batch_enabled_policy_count"] == 0 and guard["live_posting_allowed_policy_count"] == 0:
        add_item(items, "Pass", "Low", "Policy Safety", "live_policies_zero", "Live policies disabled", "No controlled production batch policies are live-enabled.")
    else:
        add_item(items, "Blocker", "Critical", "Policy Safety", "live_policies_zero", "Live policies disabled", "Live-enabled policy found.")

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "preview_ack", "Preview acknowledgement", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "preview_ack", "Preview acknowledgement", f"Required acknowledgement not supplied: {PREVIEW_ACK}")

    return items


def create_preview_lines(doc):
    line = frappe.new_doc("NDIS Limited Production Batch Enablement Preview Line")
    line.enablement_preview = doc.name
    line.line_no = 1
    line.line_label = "Controlled Limited Production Batch Policy Enablement Preview"
    line.line_status = "Would Enable"
    line.policy_doctype = "NDIS Controlled Production Batch Posting Policy"
    line.policy_name = "LIMITED_CONTROLLED_PRODUCTION_BATCH"
    line.policy_action = "Preview enable only - no live flag changed"
    line.would_enable = 1
    line.actual_enabled = 0
    line.production_batch_posting_allowed = 0
    line.real_posting_allowed = 0
    line.policy_live_enabled = 0
    line.max_batch_lines = doc.max_batch_lines
    line.max_batch_amount = doc.max_batch_amount
    line.max_payment_entry_count = doc.max_payment_entry_count
    line.detail = "Phase 9L preview only. Actual enablement remains blocked until later controlled phases."
    line.checked_on = doc.checked_on
    line.insert(ignore_permissions=True)


@frappe.whitelist()
def run_limited_production_batch_enablement_preview(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_limited_production_batch_enablement_preview")

    gate = latest_enablement_design_gate()
    config = config_state()
    guard_before = guardrails()
    ack_ok = acknowledgement == PREVIEW_ACK

    issues = validate_source(gate, guard_before)
    items = build_items(gate, guard_before, issues, ack_ok)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    approved = int(ack_ok and item_summary["blocker_count"] == 0 and gate is not None)

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Previewed" if approved else "Needs Review",
        "enablement_preview_status": "Ready For Limited Enablement Hard-block Adapter" if approved else "Needs Review",
        "enablement_preview_approved": approved,
        "ready_for_limited_enablement_adapter": approved,
        "phase9k_enablement_design_verified": 1 if gate else 0,
        "phase9j_policy_lock_verified": 1 if gate else 0,
        "policy_caps_verified": 1 if gate and int(gate.max_batch_lines or 0) == 3 and flt(gate.max_batch_amount or 0, 2) == 3 and int(gate.max_payment_entry_count or 0) == 1 else 0,
        "preview_only_verified": 1,
        "production_batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "policy_live_enabled": 0,
        "enablement_gate": gate.name if gate else None,
        "policy_lock": gate.policy_lock if gate else None,
        "finalisation_gate": gate.finalisation_gate if gate else None,
        "phase9h_freeze": gate.phase9h_freeze if gate else None,
        "rollback_run": gate.rollback_run if gate else None,
        "smoke_run": gate.smoke_run if gate else None,
        "activation_gate": gate.activation_gate if gate else None,
        "adapter_run": gate.adapter_run if gate else None,
        "policy_preview": gate.policy_preview if gate else None,
        "policy_design": gate.policy_design if gate else None,
        "policy_review_gate": gate.policy_review_gate if gate else None,
        "phase8g_freeze": gate.phase8g_freeze if gate else None,
        "company": gate.company if gate else None,
        "customer": gate.customer if gate else None,
        "payment_entry": gate.payment_entry if gate else None,
        "payment_entry_docstatus_after_rollback": int(gate.payment_entry_docstatus_after_rollback or 0) if gate else 0,
        "payment_entry_amount": flt(gate.payment_entry_amount or 0) if gate else 0,
        "reference_count": int(gate.reference_count or 0) if gate else 0,
        "invoice_outstanding_after_rollback_total": flt(gate.invoice_outstanding_after_rollback_total or 0) if gate else 0,
        "payment_entry_gl_count_after_rollback": int(gate.payment_entry_gl_count_after_rollback or 0) if gate else 0,
        "payment_entry_gl_net_after_rollback": flt(gate.payment_entry_gl_net_after_rollback or 0) if gate else 0,
        "max_batch_lines": int(gate.max_batch_lines or 0) if gate else 0,
        "max_batch_amount": flt(gate.max_batch_amount or 0) if gate else 0,
        "max_payment_entry_count": int(gate.max_payment_entry_count or 0) if gate else 0,
        "allowed_payment_type": gate.allowed_payment_type if gate else "Receive",
        "allowed_reference_doctype": gate.allowed_reference_doctype if gate else "Sales Invoice",
        "locked_policy_mode": gate.locked_policy_mode if gate else "Limited Controlled Production Batch",
        "approved_next_step": "Limited Enablement Hard-block Adapter",
        "would_enable_policy_count": 1 if gate else 0,
        "actual_enabled_policy_count": 0,
        "would_enable_policy_name": "LIMITED_CONTROLLED_PRODUCTION_BATCH",
        "preview_policy_action": "Would enable controlled limited production batch policy in a later gated adapter only",
        "adapter_requirement": "Hard-block adapter must prove no enablement before live activation",
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
        "enablement_preview_score": score,
        **item_summary,
        "items": items,
        "guardrails_before": guard_before,
        "guardrails_after": guardrails(),
        "config": config,
        "required_acknowledgement": PREVIEW_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 9L previews enablement only. It creates no accounting movement and changes no policy flags.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["enablement_preview_status"] = "Needs Review"
        result["enablement_preview_approved"] = 0
        result["ready_for_limited_enablement_adapter"] = 0
        return result

    doc = frappe.new_doc("NDIS Limited Production Batch Enablement Preview")
    doc.enablement_preview_id = make_enablement_preview_id()
    doc.status = result["status"]
    doc.enablement_preview_status = result["enablement_preview_status"]

    for fieldname in [
        "enablement_preview_approved",
        "ready_for_limited_enablement_adapter",
        "phase9k_enablement_design_verified",
        "phase9j_policy_lock_verified",
        "policy_caps_verified",
        "preview_only_verified",
        "production_batch_posting_allowed",
        "real_posting_allowed",
        "policy_live_enabled",
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
        "enablement_preview_score",
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
    doc.required_acknowledgement = PREVIEW_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    create_preview_lines(doc)

    guard_after = guardrails()

    frappe.db.set_value(
        "NDIS Limited Production Batch Enablement Preview",
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
    result["enablement_preview"] = doc.name
    result["enablement_preview_id"] = doc.enablement_preview_id
    result["guardrails_after"] = guard_after

    return result


@frappe.whitelist()
def cancel_limited_production_batch_enablement_preview(enablement_preview, reason=None):
    assert_action("cancel_limited_production_batch_enablement_preview")

    if not frappe.db.exists("NDIS Limited Production Batch Enablement Preview", enablement_preview):
        frappe.throw(_("Enablement preview not found: {0}").format(enablement_preview))

    doc = frappe.get_doc("NDIS Limited Production Batch Enablement Preview", enablement_preview)

    if doc.status == "Cancelled":
        return {"enablement_preview": enablement_preview, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.enablement_preview_approved or 0):
        frappe.throw(_("Cannot cancel an approved enablement preview. Create a superseding preview instead."))

    frappe.db.set_value(
        "NDIS Limited Production Batch Enablement Preview",
        enablement_preview,
        {
            "status": "Cancelled",
            "enablement_preview_status": "Cancelled",
            "enablement_preview_approved": 0,
            "ready_for_limited_enablement_adapter": 0,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "actual_enabled_policy_count": 0,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 9L enablement preview audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        """
        UPDATE `tabNDIS Limited Production Batch Enablement Preview Line`
        SET line_status = 'Cancelled'
        WHERE enablement_preview = %(enablement_preview)s
        """,
        {"enablement_preview": enablement_preview},
    )

    frappe.db.commit()

    return {
        "enablement_preview": enablement_preview,
        "status": "Cancelled",
        "note": "Enablement preview audit record cancelled only. No accounting or policy movement occurred.",
    }


@frappe.whitelist()
def quick_limited_production_batch_enablement_preview_summary(limit=20):
    previews = frappe.get_all(
        "NDIS Limited Production Batch Enablement Preview",
        fields=[
            "name",
            "enablement_preview_id",
            "status",
            "enablement_preview_status",
            "enablement_preview_approved",
            "ready_for_limited_enablement_adapter",
            "phase9k_enablement_design_verified",
            "phase9j_policy_lock_verified",
            "policy_caps_verified",
            "preview_only_verified",
            "enablement_gate",
            "policy_lock",
            "payment_entry",
            "max_batch_lines",
            "max_batch_amount",
            "max_payment_entry_count",
            "would_enable_policy_count",
            "actual_enabled_policy_count",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
            "production_batch_enabled_policy_count",
            "live_posting_allowed_policy_count",
            "enablement_preview_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    lines = frappe.get_all(
        "NDIS Limited Production Batch Enablement Preview Line",
        fields=[
            "name",
            "enablement_preview",
            "line_no",
            "line_status",
            "policy_name",
            "policy_action",
            "would_enable",
            "actual_enabled",
            "max_batch_lines",
            "max_batch_amount",
            "max_payment_entry_count",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    return {
        "previews": previews,
        "lines": lines,
        "required_acknowledgement": PREVIEW_ACK,
        "guardrails": guardrails(),
        "config": config_state(),
        "note": "Phase 9L limited production batch enablement preview summary. No live posting enabled.",
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
            p.name AS enablement_preview,
            p.enablement_preview_id,
            p.status,
            p.enablement_preview_status,
            p.enablement_preview_approved,
            p.ready_for_limited_enablement_adapter,
            p.enablement_gate,
            p.policy_lock,
            p.payment_entry,
            p.max_batch_lines,
            p.max_batch_amount,
            p.max_payment_entry_count,
            p.would_enable_policy_count,
            p.actual_enabled_policy_count,
            p.actual_payment_entry_created_count,
            p.actual_gl_created_count,
            p.production_batch_enabled_policy_count,
            p.live_posting_allowed_policy_count,
            p.enablement_preview_score,
            p.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Limited Production Batch Enablement Preview` p
        {build_where(conditions)}
        ORDER BY p.creation DESC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.enablement_preview_id for row in data[:20]],
            "datasets": [
                {"name": "Would Enable Policies", "values": [int(row.would_enable_policy_count or 0) for row in data[:20]]},
                {"name": "Actually Enabled", "values": [int(row.actual_enabled_policy_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Enablement Previews"), "datatype": "Int"},
        {"value": sum(int(row.enablement_preview_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(int(row.would_enable_policy_count or 0) for row in data), "indicator": "Blue", "label": _("Would Enable Policies"), "datatype": "Int"},
        {"value": sum(int(row.actual_enabled_policy_count or 0) for row in data), "indicator": "Red", "label": _("Actual Enabled Policies"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def preview_columns():
    return [
        {"fieldname": "enablement_preview", "label": _("Enablement Preview"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Preview", "width": 220},
        {"fieldname": "enablement_preview_id", "label": _("Enablement Preview ID"), "fieldtype": "Data", "width": 460},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "enablement_preview_status", "label": _("Preview Status"), "fieldtype": "Data", "width": 330},
        {"fieldname": "ready_for_limited_enablement_adapter", "label": _("Ready Adapter"), "fieldtype": "Check", "width": 120},
        {"fieldname": "enablement_gate", "label": _("Enablement Gate"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Design Gate", "width": 220},
        {"fieldname": "policy_lock", "label": _("Policy Lock"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Policy Lock", "width": 220},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 170},
        {"fieldname": "max_batch_lines", "label": _("Max Lines"), "fieldtype": "Int", "width": 90},
        {"fieldname": "max_batch_amount", "label": _("Max Amount"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "max_payment_entry_count", "label": _("Max PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "would_enable_policy_count", "label": _("Would Enable"), "fieldtype": "Int", "width": 110},
        {"fieldname": "actual_enabled_policy_count", "label": _("Actual Enabled"), "fieldtype": "Int", "width": 120},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "enablement_preview_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_line_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("enablement_preview"):
        conditions.append("l.enablement_preview = %(enablement_preview)s")
        params["enablement_preview"] = filters.get("enablement_preview")

    if filters.get("line_status"):
        conditions.append("l.line_status = %(line_status)s")
        params["line_status"] = filters.get("line_status")

    columns = [
        {"fieldname": "line", "label": _("Line"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Preview Line", "width": 220},
        {"fieldname": "enablement_preview", "label": _("Enablement Preview"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Preview", "width": 220},
        {"fieldname": "line_no", "label": _("Line No"), "fieldtype": "Int", "width": 80},
        {"fieldname": "line_status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "policy_name", "label": _("Policy Name"), "fieldtype": "Data", "width": 250},
        {"fieldname": "policy_action", "label": _("Policy Action"), "fieldtype": "Data", "width": 330},
        {"fieldname": "would_enable", "label": _("Would Enable"), "fieldtype": "Check", "width": 110},
        {"fieldname": "actual_enabled", "label": _("Actual Enabled"), "fieldtype": "Check", "width": 110},
        {"fieldname": "max_batch_lines", "label": _("Max Lines"), "fieldtype": "Int", "width": 90},
        {"fieldname": "max_batch_amount", "label": _("Max Amount"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "max_payment_entry_count", "label": _("Max PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            l.name AS line,
            l.enablement_preview,
            l.line_no,
            l.line_status,
            l.policy_name,
            l.policy_action,
            l.would_enable,
            l.actual_enabled,
            l.max_batch_lines,
            l.max_batch_amount,
            l.max_payment_entry_count,
            l.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Limited Production Batch Enablement Preview Line` l
        {build_where(conditions)}
        ORDER BY l.enablement_preview DESC, l.line_no ASC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.policy_name for row in data[:20]],
            "datasets": [
                {"name": "Would Enable", "values": [int(row.would_enable or 0) for row in data[:20]]},
                {"name": "Actual Enabled", "values": [int(row.actual_enabled or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Preview Lines"), "datatype": "Int"},
        {"value": sum(int(row.would_enable or 0) for row in data), "indicator": "Blue", "label": _("Would Enable"), "datatype": "Int"},
        {"value": sum(int(row.actual_enabled or 0) for row in data), "indicator": "Red", "label": _("Actual Enabled"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_preview_report(filters)

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
