import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


POLICY_LOCK_ACK = "I_CONFIRM_PHASE9J_LOCK_LIMITED_PRODUCTION_BATCH_POLICY_NO_POSTING"


def make_policy_lock_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-LIMITED-PROD-BATCH-POLICY-LOCK-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_finalisation_gate():
    rows = frappe.get_all(
        "NDIS Limited Production Batch Policy Finalisation Gate",
        filters={
            "status": "Approved",
            "policy_finalisation_approved": 1,
            "ready_for_limited_policy_lock": 1,
            "phase9h_freeze_verified": 1,
            "smoke_rollback_verified": 1,
            "gl_net_zero_verified": 1,
            "invoice_restoration_verified": 1,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "submitted_phase9f_smoke_pe_count": 0,
            "cancelled_phase9f_smoke_pe_count": 1,
        },
        fields=[
            "name",
            "finalisation_gate_id",
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
            "limited_batch_line_cap",
            "limited_batch_amount_cap",
            "limited_payment_entry_cap",
            "approved_next_step",
            "submitted_phase9f_smoke_pe_count",
            "cancelled_phase9f_smoke_pe_count",
            "finalisation_score",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )

    return rows[0] if rows else None


def existing_locked_policy(finalisation_gate):
    rows = frappe.get_all(
        "NDIS Limited Production Batch Policy Lock",
        filters={
            "finalisation_gate": finalisation_gate,
            "status": "Locked",
            "policy_lock_allowed": 1,
            "ready_for_limited_enablement_design": 1,
        },
        fields=["name", "policy_lock_id"],
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


def validate_source(finalisation, guard):
    issues = []

    if not finalisation:
        issues.append("No approved Phase 9I finalisation gate found.")
        return issues

    if existing_locked_policy(finalisation.name):
        issues.append("A locked Phase 9J policy lock already exists for this Phase 9I finalisation gate.")

    required_links = {
        "phase9h_freeze": finalisation.phase9h_freeze,
        "rollback_run": finalisation.rollback_run,
        "smoke_run": finalisation.smoke_run,
        "activation_gate": finalisation.activation_gate,
        "adapter_run": finalisation.adapter_run,
        "policy_preview": finalisation.policy_preview,
        "policy_design": finalisation.policy_design,
        "policy_review_gate": finalisation.policy_review_gate,
    }

    for label, value in required_links.items():
        if not value:
            issues.append(f"Missing evidence link: {label}")

    if not finalisation.payment_entry or not frappe.db.exists("Payment Entry", finalisation.payment_entry):
        issues.append("Finalisation Payment Entry does not exist.")
    else:
        docstatus = int(frappe.db.get_value("Payment Entry", finalisation.payment_entry, "docstatus") or 0)
        if docstatus != 2:
            issues.append(f"Payment Entry must be cancelled. Found docstatus {docstatus}.")

        gl_count, gl_net = pe_gl_count_net(finalisation.payment_entry)

        if gl_count != int(finalisation.payment_entry_gl_count_after_rollback or 0):
            issues.append("Current PE GL row count does not match finalisation evidence.")

        if gl_count != 6:
            issues.append(f"Expected PE GL rows after rollback to be 6. Found {gl_count}.")

        if flt(gl_net, 2) != 0:
            issues.append(f"Expected PE GL net to be 0.00. Found {gl_net}.")

    if int(finalisation.payment_entry_docstatus_after_rollback or 0) != 2:
        issues.append("Payment Entry docstatus after rollback must be 2.")

    if flt(finalisation.invoice_outstanding_after_rollback_total or 0, 2) != 2:
        issues.append("Invoice outstanding after rollback must be 2.00.")

    if int(finalisation.payment_entry_gl_count_after_rollback or 0) != 6:
        issues.append("PE GL rows after rollback must be 6.")

    if flt(finalisation.payment_entry_gl_net_after_rollback or 0, 2) != 0:
        issues.append("PE GL net after rollback must be 0.00.")

    if int(finalisation.limited_batch_line_cap or 0) != 3:
        issues.append("Limited batch line cap must be 3.")

    if flt(finalisation.limited_batch_amount_cap or 0, 2) != 3:
        issues.append("Limited batch amount cap must be 3.00.")

    if int(finalisation.limited_payment_entry_cap or 0) != 1:
        issues.append("Limited Payment Entry cap must be 1.")

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


def build_items(finalisation, guard, issues, ack_ok):
    items = []

    if finalisation:
        add_item(
            items,
            "Pass",
            "Low",
            "Phase 9I Finalisation",
            "phase9i_finalisation_exists",
            "Phase 9I finalisation gate exists",
            f"Finalisation gate found: {finalisation.finalisation_gate_id}.",
            "NDIS Limited Production Batch Policy Finalisation Gate",
            finalisation.name,
        )
    else:
        add_item(items, "Blocker", "Critical", "Phase 9I Finalisation", "phase9i_finalisation_exists", "Phase 9I finalisation gate exists", "No approved Phase 9I finalisation gate found.")

    if not issues:
        add_item(items, "Pass", "Low", "Policy Lock Source", "source_valid", "Policy lock source valid", "Phase 9I evidence and caps are valid for policy lock.")
    else:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Policy Lock Source", "source_valid", "Policy lock source valid", issue)

    if finalisation and finalisation.payment_entry:
        add_item(
            items,
            "Pass",
            "Low",
            "Payment Entry",
            "pe_cancelled",
            "Payment Entry cancelled",
            f"{finalisation.payment_entry} docstatus after rollback = {finalisation.payment_entry_docstatus_after_rollback}.",
            "Payment Entry",
            finalisation.payment_entry,
        )

    if finalisation:
        add_item(items, "Pass", "Low", "Policy Caps", "caps_locked", "Policy caps locked", f"Lines {finalisation.limited_batch_line_cap}, amount {finalisation.limited_batch_amount_cap}, PE count {finalisation.limited_payment_entry_cap}.")
        add_item(items, "Pass", "Low", "Invoice Evidence", "invoice_restored", "Invoice restoration locked", f"Outstanding restored to {finalisation.invoice_outstanding_after_rollback_total}.")
        add_item(items, "Pass", "Low", "GL Evidence", "gl_net_zero", "GL net-zero locked", f"Rows {finalisation.payment_entry_gl_count_after_rollback}, net {finalisation.payment_entry_gl_net_after_rollback}.")

    if guard["production_batch_enabled_policy_count"] == 0 and guard["live_posting_allowed_policy_count"] == 0:
        add_item(items, "Pass", "Low", "Policy Safety", "live_policies_zero", "Live policies disabled", "No controlled production batch policies are live-enabled.")
    else:
        add_item(items, "Blocker", "Critical", "Policy Safety", "live_policies_zero", "Live policies disabled", "Live-enabled policy found.")

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "policy_lock_ack", "Policy lock acknowledgement", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "policy_lock_ack", "Policy lock acknowledgement", f"Required acknowledgement not supplied: {POLICY_LOCK_ACK}")

    return items


def create_items(doc, items):
    for item in items:
        row = frappe.new_doc("NDIS Limited Production Batch Policy Lock Item")
        row.policy_lock = doc.name
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
def run_limited_production_batch_policy_lock(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_limited_production_batch_policy_lock")

    finalisation = latest_finalisation_gate()
    config = config_state()
    guard_before = guardrails()
    ack_ok = acknowledgement == POLICY_LOCK_ACK

    issues = validate_source(finalisation, guard_before)
    items = build_items(finalisation, guard_before, issues, ack_ok)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    locked = int(ack_ok and item_summary["blocker_count"] == 0 and finalisation is not None)

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Locked" if locked else "Needs Review",
        "policy_lock_status": "Locked For Controlled Limited Production Use" if locked else "Needs Review",
        "policy_lock_allowed": locked,
        "ready_for_limited_enablement_design": locked,
        "phase9i_finalisation_verified": 1 if finalisation else 0,
        "phase9h_freeze_verified": 1 if finalisation else 0,
        "smoke_rollback_verified": 1 if finalisation else 0,
        "gl_net_zero_verified": 1 if finalisation and flt(finalisation.payment_entry_gl_net_after_rollback or 0, 2) == 0 else 0,
        "invoice_restoration_verified": 1 if finalisation and flt(finalisation.invoice_outstanding_after_rollback_total or 0, 2) == 2 else 0,
        "policy_caps_locked": 1 if finalisation and int(finalisation.limited_batch_line_cap or 0) == 3 and flt(finalisation.limited_batch_amount_cap or 0, 2) == 3 and int(finalisation.limited_payment_entry_cap or 0) == 1 else 0,
        "production_batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "policy_live_enabled": 0,
        "finalisation_gate": finalisation.name if finalisation else None,
        "phase9h_freeze": finalisation.phase9h_freeze if finalisation else None,
        "rollback_run": finalisation.rollback_run if finalisation else None,
        "smoke_run": finalisation.smoke_run if finalisation else None,
        "activation_gate": finalisation.activation_gate if finalisation else None,
        "adapter_run": finalisation.adapter_run if finalisation else None,
        "policy_preview": finalisation.policy_preview if finalisation else None,
        "policy_design": finalisation.policy_design if finalisation else None,
        "policy_review_gate": finalisation.policy_review_gate if finalisation else None,
        "phase8g_freeze": finalisation.phase8g_freeze if finalisation else None,
        "company": finalisation.company if finalisation else None,
        "customer": finalisation.customer if finalisation else None,
        "payment_entry": finalisation.payment_entry if finalisation else None,
        "payment_entry_docstatus_after_rollback": int(finalisation.payment_entry_docstatus_after_rollback or 0) if finalisation else 0,
        "payment_entry_amount": flt(finalisation.payment_entry_amount or 0) if finalisation else 0,
        "reference_count": int(finalisation.reference_count or 0) if finalisation else 0,
        "invoice_outstanding_after_rollback_total": flt(finalisation.invoice_outstanding_after_rollback_total or 0) if finalisation else 0,
        "payment_entry_gl_count_after_rollback": int(finalisation.payment_entry_gl_count_after_rollback or 0) if finalisation else 0,
        "payment_entry_gl_net_after_rollback": flt(finalisation.payment_entry_gl_net_after_rollback or 0) if finalisation else 0,
        "max_batch_lines": int(finalisation.limited_batch_line_cap or 0) if finalisation else 0,
        "max_batch_amount": flt(finalisation.limited_batch_amount_cap or 0) if finalisation else 0,
        "max_payment_entry_count": int(finalisation.limited_payment_entry_cap or 0) if finalisation else 0,
        "allowed_payment_type": "Receive",
        "allowed_reference_doctype": "Sales Invoice",
        "locked_policy_mode": "Limited Controlled Production Batch",
        "approved_next_step": "Limited Production Batch Enablement Design",
        "submitted_phase9f_smoke_pe_count": guard_before["submitted_phase9f_smoke_pe_count"],
        "cancelled_phase9f_smoke_pe_count": guard_before["cancelled_phase9f_smoke_pe_count"],
        "submitted_journal_entry_count_today": guard_before["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_before["purchase_invoice_count_today"],
        "production_batch_enabled_policy_count": guard_before["production_batch_enabled_policy_count"],
        "live_posting_allowed_policy_count": guard_before["live_posting_allowed_policy_count"],
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guardrails()["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guardrails()["payment_entry_gl_count"],
        "policy_lock_score": score,
        **item_summary,
        "items": items,
        "guardrails_before": guard_before,
        "guardrails_after": guardrails(),
        "config": config,
        "required_acknowledgement": POLICY_LOCK_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 9J locks the limited production batch policy evidence only. It creates no accounting movement and enables no live policies.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["policy_lock_status"] = "Needs Review"
        result["policy_lock_allowed"] = 0
        result["ready_for_limited_enablement_design"] = 0
        return result

    doc = frappe.new_doc("NDIS Limited Production Batch Policy Lock")
    doc.policy_lock_id = make_policy_lock_id()
    doc.status = result["status"]
    doc.policy_lock_status = result["policy_lock_status"]

    for fieldname in [
        "policy_lock_allowed",
        "ready_for_limited_enablement_design",
        "phase9i_finalisation_verified",
        "phase9h_freeze_verified",
        "smoke_rollback_verified",
        "gl_net_zero_verified",
        "invoice_restoration_verified",
        "policy_caps_locked",
        "production_batch_posting_allowed",
        "real_posting_allowed",
        "policy_live_enabled",
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
        "submitted_phase9f_smoke_pe_count",
        "cancelled_phase9f_smoke_pe_count",
        "submitted_journal_entry_count_today",
        "purchase_invoice_count_today",
        "production_batch_enabled_policy_count",
        "live_posting_allowed_policy_count",
        "payment_entry_count_before",
        "payment_entry_count_after",
        "payment_entry_gl_count_before",
        "payment_entry_gl_count_after",
        "policy_lock_score",
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
    doc.required_acknowledgement = POLICY_LOCK_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    create_items(doc, items)

    guard_after = guardrails()

    frappe.db.set_value(
        "NDIS Limited Production Batch Policy Lock",
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
    result["policy_lock"] = doc.name
    result["policy_lock_id"] = doc.policy_lock_id
    result["guardrails_after"] = guard_after

    return result


@frappe.whitelist()
def cancel_limited_production_batch_policy_lock(policy_lock, reason=None):
    assert_action("cancel_limited_production_batch_policy_lock")

    if not frappe.db.exists("NDIS Limited Production Batch Policy Lock", policy_lock):
        frappe.throw(_("Policy lock not found: {0}").format(policy_lock))

    doc = frappe.get_doc("NDIS Limited Production Batch Policy Lock", policy_lock)

    if doc.status == "Cancelled":
        return {"policy_lock": policy_lock, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.policy_lock_allowed or 0):
        frappe.throw(_("Cannot cancel a locked policy record. Create a superseding lock instead."))

    frappe.db.set_value(
        "NDIS Limited Production Batch Policy Lock",
        policy_lock,
        {
            "status": "Cancelled",
            "policy_lock_status": "Cancelled",
            "policy_lock_allowed": 0,
            "ready_for_limited_enablement_design": 0,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 9J policy lock audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        """
        UPDATE `tabNDIS Limited Production Batch Policy Lock Item`
        SET status = 'Cancelled'
        WHERE policy_lock = %(policy_lock)s
        """,
        {"policy_lock": policy_lock},
    )

    frappe.db.commit()

    return {
        "policy_lock": policy_lock,
        "status": "Cancelled",
        "note": "Policy lock audit record cancelled only. No accounting movement occurred.",
    }


@frappe.whitelist()
def quick_limited_production_batch_policy_lock_summary(limit=20):
    locks = frappe.get_all(
        "NDIS Limited Production Batch Policy Lock",
        fields=[
            "name",
            "policy_lock_id",
            "status",
            "policy_lock_status",
            "policy_lock_allowed",
            "ready_for_limited_enablement_design",
            "phase9i_finalisation_verified",
            "phase9h_freeze_verified",
            "smoke_rollback_verified",
            "gl_net_zero_verified",
            "invoice_restoration_verified",
            "policy_caps_locked",
            "finalisation_gate",
            "phase9h_freeze",
            "rollback_run",
            "smoke_run",
            "payment_entry",
            "payment_entry_docstatus_after_rollback",
            "invoice_outstanding_after_rollback_total",
            "payment_entry_gl_count_after_rollback",
            "payment_entry_gl_net_after_rollback",
            "max_batch_lines",
            "max_batch_amount",
            "max_payment_entry_count",
            "submitted_phase9f_smoke_pe_count",
            "cancelled_phase9f_smoke_pe_count",
            "production_batch_enabled_policy_count",
            "live_posting_allowed_policy_count",
            "policy_lock_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    items = frappe.get_all(
        "NDIS Limited Production Batch Policy Lock Item",
        fields=[
            "name",
            "policy_lock",
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
        "locks": locks,
        "items": items,
        "required_acknowledgement": POLICY_LOCK_ACK,
        "guardrails": guardrails(),
        "config": config_state(),
        "note": "Phase 9J limited production batch policy lock summary. No live posting enabled.",
    }


def execute_lock_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("status"):
        conditions.append("l.status = %(status)s")
        params["status"] = filters.get("status")

    columns = lock_columns()

    data = frappe.db.sql(
        f"""
        SELECT
            l.name AS policy_lock,
            l.policy_lock_id,
            l.status,
            l.policy_lock_status,
            l.policy_lock_allowed,
            l.ready_for_limited_enablement_design,
            l.phase9i_finalisation_verified,
            l.phase9h_freeze_verified,
            l.smoke_rollback_verified,
            l.gl_net_zero_verified,
            l.invoice_restoration_verified,
            l.policy_caps_locked,
            l.finalisation_gate,
            l.phase9h_freeze,
            l.rollback_run,
            l.payment_entry,
            l.payment_entry_docstatus_after_rollback,
            l.invoice_outstanding_after_rollback_total,
            l.payment_entry_gl_count_after_rollback,
            l.payment_entry_gl_net_after_rollback,
            l.max_batch_lines,
            l.max_batch_amount,
            l.max_payment_entry_count,
            l.submitted_phase9f_smoke_pe_count,
            l.cancelled_phase9f_smoke_pe_count,
            l.production_batch_enabled_policy_count,
            l.live_posting_allowed_policy_count,
            l.policy_lock_score,
            l.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Limited Production Batch Policy Lock` l
        {build_where(conditions)}
        ORDER BY l.creation DESC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.policy_lock_id for row in data[:20]],
            "datasets": [
                {"name": "Locked", "values": [int(row.policy_lock_allowed or 0) for row in data[:20]]},
                {"name": "Live Policies", "values": [int(row.live_posting_allowed_policy_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Policy Locks"), "datatype": "Int"},
        {"value": sum(int(row.policy_lock_allowed or 0) for row in data), "indicator": "Green", "label": _("Locked"), "datatype": "Int"},
        {"value": sum(int(row.max_batch_lines or 0) for row in data), "indicator": "Blue", "label": _("Locked Line Cap Total"), "datatype": "Int"},
        {"value": sum(int(row.live_posting_allowed_policy_count or 0) for row in data), "indicator": "Red", "label": _("Live Policies"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def lock_columns():
    return [
        {"fieldname": "policy_lock", "label": _("Policy Lock"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Policy Lock", "width": 220},
        {"fieldname": "policy_lock_id", "label": _("Policy Lock ID"), "fieldtype": "Data", "width": 430},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "policy_lock_status", "label": _("Policy Lock Status"), "fieldtype": "Data", "width": 310},
        {"fieldname": "ready_for_limited_enablement_design", "label": _("Ready Enablement"), "fieldtype": "Check", "width": 130},
        {"fieldname": "finalisation_gate", "label": _("Finalisation Gate"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Policy Finalisation Gate", "width": 220},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 170},
        {"fieldname": "payment_entry_docstatus_after_rollback", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 110},
        {"fieldname": "invoice_outstanding_after_rollback_total", "label": _("Outstanding Restored"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "payment_entry_gl_count_after_rollback", "label": _("PE GL Rows"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_net_after_rollback", "label": _("PE GL Net"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "max_batch_lines", "label": _("Max Lines"), "fieldtype": "Int", "width": 90},
        {"fieldname": "max_batch_amount", "label": _("Max Amount"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "max_payment_entry_count", "label": _("Max PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "policy_lock_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    if filters.get("policy_lock"):
        conditions.append("i.policy_lock = %(policy_lock)s")
        params["policy_lock"] = filters.get("policy_lock")

    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Policy Lock Item", "width": 220},
        {"fieldname": "policy_lock", "label": _("Policy Lock"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Policy Lock", "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 170},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 300},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 520},
        {"fieldname": "source_doctype", "label": _("Source DocType"), "fieldtype": "Data", "width": 180},
        {"fieldname": "source_name", "label": _("Source Name"), "fieldtype": "Data", "width": 220},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            i.name AS item,
            i.policy_lock,
            i.status,
            i.severity,
            i.category,
            i.check_label,
            i.detail,
            i.source_doctype,
            i.source_name,
            i.checked_on
        FROM `tabNDIS Limited Production Batch Policy Lock Item` i
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
    columns, data, message, chart, summary = execute_lock_report(filters)

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
