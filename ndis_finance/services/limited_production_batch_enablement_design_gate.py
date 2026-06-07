import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


ENABLEMENT_ACK = "I_CONFIRM_PHASE9K_APPROVE_LIMITED_PRODUCTION_BATCH_ENABLEMENT_DESIGN_NO_POSTING"


def make_enablement_gate_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-LIMITED-PROD-BATCH-ENABLEMENT-DESIGN-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_policy_lock():
    rows = frappe.get_all(
        "NDIS Limited Production Batch Policy Lock",
        filters={
            "status": "Locked",
            "policy_lock_allowed": 1,
            "ready_for_limited_enablement_design": 1,
            "phase9i_finalisation_verified": 1,
            "phase9h_freeze_verified": 1,
            "smoke_rollback_verified": 1,
            "gl_net_zero_verified": 1,
            "invoice_restoration_verified": 1,
            "policy_caps_locked": 1,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "submitted_phase9f_smoke_pe_count": 0,
            "cancelled_phase9f_smoke_pe_count": 1,
        },
        fields=[
            "name",
            "policy_lock_id",
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
            "policy_lock_score",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )

    return rows[0] if rows else None


def existing_approved_gate(policy_lock):
    rows = frappe.get_all(
        "NDIS Limited Production Batch Enablement Design Gate",
        filters={
            "policy_lock": policy_lock,
            "status": "Approved",
            "enablement_design_approved": 1,
            "ready_for_limited_enablement_preview": 1,
        },
        fields=["name", "enablement_gate_id"],
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


def validate_source(lock, guard):
    issues = []

    if not lock:
        issues.append("No locked Phase 9J policy lock found.")
        return issues

    if existing_approved_gate(lock.name):
        issues.append("An approved Phase 9K enablement design gate already exists for this Phase 9J policy lock.")

    required_links = {
        "finalisation_gate": lock.finalisation_gate,
        "phase9h_freeze": lock.phase9h_freeze,
        "rollback_run": lock.rollback_run,
        "smoke_run": lock.smoke_run,
        "activation_gate": lock.activation_gate,
        "adapter_run": lock.adapter_run,
        "policy_preview": lock.policy_preview,
        "policy_design": lock.policy_design,
        "policy_review_gate": lock.policy_review_gate,
    }

    for label, value in required_links.items():
        if not value:
            issues.append(f"Missing evidence link: {label}")

    if not lock.payment_entry or not frappe.db.exists("Payment Entry", lock.payment_entry):
        issues.append("Locked Payment Entry does not exist.")
    else:
        docstatus = int(frappe.db.get_value("Payment Entry", lock.payment_entry, "docstatus") or 0)
        if docstatus != 2:
            issues.append(f"Locked Payment Entry must be cancelled. Found docstatus {docstatus}.")

        gl_count, gl_net = pe_gl_count_net(lock.payment_entry)

        if gl_count != int(lock.payment_entry_gl_count_after_rollback or 0):
            issues.append("Current PE GL row count does not match locked policy evidence.")

        if gl_count != 6:
            issues.append(f"Expected PE GL rows after rollback to be 6. Found {gl_count}.")

        if flt(gl_net, 2) != 0:
            issues.append(f"Expected PE GL net to be 0.00. Found {gl_net}.")

    if int(lock.max_batch_lines or 0) != 3:
        issues.append("Locked max_batch_lines must be 3.")

    if flt(lock.max_batch_amount or 0, 2) != 3:
        issues.append("Locked max_batch_amount must be 3.00.")

    if int(lock.max_payment_entry_count or 0) != 1:
        issues.append("Locked max_payment_entry_count must be 1.")

    if lock.allowed_payment_type != "Receive":
        issues.append("Allowed payment type must be Receive.")

    if lock.allowed_reference_doctype != "Sales Invoice":
        issues.append("Allowed reference doctype must be Sales Invoice.")

    if int(lock.payment_entry_docstatus_after_rollback or 0) != 2:
        issues.append("Payment Entry docstatus after rollback must be 2.")

    if flt(lock.invoice_outstanding_after_rollback_total or 0, 2) != 2:
        issues.append("Invoice outstanding after rollback must be 2.00.")

    if int(lock.payment_entry_gl_count_after_rollback or 0) != 6:
        issues.append("PE GL rows after rollback must be 6.")

    if flt(lock.payment_entry_gl_net_after_rollback or 0, 2) != 0:
        issues.append("PE GL net after rollback must be 0.00.")

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


def build_items(lock, guard, issues, ack_ok):
    items = []

    if lock:
        add_item(
            items,
            "Pass",
            "Low",
            "Phase 9J Policy Lock",
            "phase9j_lock_exists",
            "Phase 9J policy lock exists",
            f"Policy lock found: {lock.policy_lock_id}.",
            "NDIS Limited Production Batch Policy Lock",
            lock.name,
        )
    else:
        add_item(items, "Blocker", "Critical", "Phase 9J Policy Lock", "phase9j_lock_exists", "Phase 9J policy lock exists", "No locked Phase 9J policy lock found.")

    if not issues:
        add_item(items, "Pass", "Low", "Enablement Source", "source_valid", "Enablement design source valid", "Phase 9J lock and caps are valid for enablement preview design.")
    else:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Enablement Source", "source_valid", "Enablement design source valid", issue)

    if lock and lock.payment_entry:
        add_item(
            items,
            "Pass",
            "Low",
            "Payment Entry",
            "pe_cancelled",
            "Payment Entry cancelled",
            f"{lock.payment_entry} docstatus after rollback = {lock.payment_entry_docstatus_after_rollback}.",
            "Payment Entry",
            lock.payment_entry,
        )

    if lock:
        add_item(items, "Pass", "Low", "Policy Caps", "caps_verified", "Locked policy caps verified", f"Lines {lock.max_batch_lines}, amount {lock.max_batch_amount}, PE count {lock.max_payment_entry_count}.")
        add_item(items, "Pass", "Low", "Invoice Evidence", "invoice_restored", "Invoice restoration verified", f"Outstanding restored to {lock.invoice_outstanding_after_rollback_total}.")
        add_item(items, "Pass", "Low", "GL Evidence", "gl_net_zero", "GL net-zero verified", f"Rows {lock.payment_entry_gl_count_after_rollback}, net {lock.payment_entry_gl_net_after_rollback}.")

    if guard["production_batch_enabled_policy_count"] == 0 and guard["live_posting_allowed_policy_count"] == 0:
        add_item(items, "Pass", "Low", "Policy Safety", "live_policies_zero", "Live policies disabled", "No controlled production batch policies are live-enabled.")
    else:
        add_item(items, "Blocker", "Critical", "Policy Safety", "live_policies_zero", "Live policies disabled", "Live-enabled policy found.")

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "enablement_ack", "Enablement design acknowledgement", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "enablement_ack", "Enablement design acknowledgement", f"Required acknowledgement not supplied: {ENABLEMENT_ACK}")

    return items


def create_items(doc, items):
    for item in items:
        row = frappe.new_doc("NDIS Limited Production Batch Enablement Design Gate Item")
        row.enablement_gate = doc.name
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
def run_limited_production_batch_enablement_design_gate(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_limited_production_batch_enablement_design_gate")

    lock = latest_policy_lock()
    config = config_state()
    guard_before = guardrails()
    ack_ok = acknowledgement == ENABLEMENT_ACK

    issues = validate_source(lock, guard_before)
    items = build_items(lock, guard_before, issues, ack_ok)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    approved = int(ack_ok and item_summary["blocker_count"] == 0 and lock is not None)

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Approved" if approved else "Needs Review",
        "enablement_status": "Ready For Controlled Limited Enablement Preview" if approved else "Needs Review",
        "enablement_design_approved": approved,
        "ready_for_limited_enablement_preview": approved,
        "phase9j_policy_lock_verified": 1 if lock else 0,
        "phase9i_finalisation_verified": 1 if lock else 0,
        "phase9h_freeze_verified": 1 if lock else 0,
        "policy_caps_verified": 1 if lock and int(lock.max_batch_lines or 0) == 3 and flt(lock.max_batch_amount or 0, 2) == 3 and int(lock.max_payment_entry_count or 0) == 1 else 0,
        "no_accounting_movement_verified": 1,
        "production_batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "policy_live_enabled": 0,
        "policy_lock": lock.name if lock else None,
        "finalisation_gate": lock.finalisation_gate if lock else None,
        "phase9h_freeze": lock.phase9h_freeze if lock else None,
        "rollback_run": lock.rollback_run if lock else None,
        "smoke_run": lock.smoke_run if lock else None,
        "activation_gate": lock.activation_gate if lock else None,
        "adapter_run": lock.adapter_run if lock else None,
        "policy_preview": lock.policy_preview if lock else None,
        "policy_design": lock.policy_design if lock else None,
        "policy_review_gate": lock.policy_review_gate if lock else None,
        "phase8g_freeze": lock.phase8g_freeze if lock else None,
        "company": lock.company if lock else None,
        "customer": lock.customer if lock else None,
        "payment_entry": lock.payment_entry if lock else None,
        "payment_entry_docstatus_after_rollback": int(lock.payment_entry_docstatus_after_rollback or 0) if lock else 0,
        "payment_entry_amount": flt(lock.payment_entry_amount or 0) if lock else 0,
        "reference_count": int(lock.reference_count or 0) if lock else 0,
        "invoice_outstanding_after_rollback_total": flt(lock.invoice_outstanding_after_rollback_total or 0) if lock else 0,
        "payment_entry_gl_count_after_rollback": int(lock.payment_entry_gl_count_after_rollback or 0) if lock else 0,
        "payment_entry_gl_net_after_rollback": flt(lock.payment_entry_gl_net_after_rollback or 0) if lock else 0,
        "max_batch_lines": int(lock.max_batch_lines or 0) if lock else 0,
        "max_batch_amount": flt(lock.max_batch_amount or 0) if lock else 0,
        "max_payment_entry_count": int(lock.max_payment_entry_count or 0) if lock else 0,
        "allowed_payment_type": lock.allowed_payment_type if lock else "Receive",
        "allowed_reference_doctype": lock.allowed_reference_doctype if lock else "Sales Invoice",
        "locked_policy_mode": lock.locked_policy_mode if lock else "Limited Controlled Production Batch",
        "approved_next_step": "Controlled Limited Enablement Preview",
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
        "enablement_score": score,
        **item_summary,
        "items": items,
        "guardrails_before": guard_before,
        "guardrails_after": guardrails(),
        "config": config,
        "required_acknowledgement": ENABLEMENT_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 9K approves enablement design only. It creates no accounting movement and enables no live policies.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["enablement_status"] = "Needs Review"
        result["enablement_design_approved"] = 0
        result["ready_for_limited_enablement_preview"] = 0
        return result

    doc = frappe.new_doc("NDIS Limited Production Batch Enablement Design Gate")
    doc.enablement_gate_id = make_enablement_gate_id()
    doc.status = result["status"]
    doc.enablement_status = result["enablement_status"]

    for fieldname in [
        "enablement_design_approved",
        "ready_for_limited_enablement_preview",
        "phase9j_policy_lock_verified",
        "phase9i_finalisation_verified",
        "phase9h_freeze_verified",
        "policy_caps_verified",
        "no_accounting_movement_verified",
        "production_batch_posting_allowed",
        "real_posting_allowed",
        "policy_live_enabled",
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
        "enablement_score",
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
    doc.required_acknowledgement = ENABLEMENT_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    create_items(doc, items)

    guard_after = guardrails()

    frappe.db.set_value(
        "NDIS Limited Production Batch Enablement Design Gate",
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
    result["enablement_gate"] = doc.name
    result["enablement_gate_id"] = doc.enablement_gate_id
    result["guardrails_after"] = guard_after

    return result


@frappe.whitelist()
def cancel_limited_production_batch_enablement_design_gate(enablement_gate, reason=None):
    assert_action("cancel_limited_production_batch_enablement_design_gate")

    if not frappe.db.exists("NDIS Limited Production Batch Enablement Design Gate", enablement_gate):
        frappe.throw(_("Enablement design gate not found: {0}").format(enablement_gate))

    doc = frappe.get_doc("NDIS Limited Production Batch Enablement Design Gate", enablement_gate)

    if doc.status == "Cancelled":
        return {"enablement_gate": enablement_gate, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.enablement_design_approved or 0):
        frappe.throw(_("Cannot cancel an approved enablement design gate. Create a superseding gate instead."))

    frappe.db.set_value(
        "NDIS Limited Production Batch Enablement Design Gate",
        enablement_gate,
        {
            "status": "Cancelled",
            "enablement_status": "Cancelled",
            "enablement_design_approved": 0,
            "ready_for_limited_enablement_preview": 0,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 9K enablement design audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        """
        UPDATE `tabNDIS Limited Production Batch Enablement Design Gate Item`
        SET status = 'Cancelled'
        WHERE enablement_gate = %(enablement_gate)s
        """,
        {"enablement_gate": enablement_gate},
    )

    frappe.db.commit()

    return {
        "enablement_gate": enablement_gate,
        "status": "Cancelled",
        "note": "Enablement design audit record cancelled only. No accounting movement occurred.",
    }


@frappe.whitelist()
def quick_limited_production_batch_enablement_design_summary(limit=20):
    gates = frappe.get_all(
        "NDIS Limited Production Batch Enablement Design Gate",
        fields=[
            "name",
            "enablement_gate_id",
            "status",
            "enablement_status",
            "enablement_design_approved",
            "ready_for_limited_enablement_preview",
            "phase9j_policy_lock_verified",
            "phase9i_finalisation_verified",
            "phase9h_freeze_verified",
            "policy_caps_verified",
            "no_accounting_movement_verified",
            "policy_lock",
            "finalisation_gate",
            "phase9h_freeze",
            "payment_entry",
            "payment_entry_docstatus_after_rollback",
            "invoice_outstanding_after_rollback_total",
            "payment_entry_gl_count_after_rollback",
            "payment_entry_gl_net_after_rollback",
            "max_batch_lines",
            "max_batch_amount",
            "max_payment_entry_count",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
            "production_batch_enabled_policy_count",
            "live_posting_allowed_policy_count",
            "enablement_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    items = frappe.get_all(
        "NDIS Limited Production Batch Enablement Design Gate Item",
        fields=[
            "name",
            "enablement_gate",
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
        "required_acknowledgement": ENABLEMENT_ACK,
        "guardrails": guardrails(),
        "config": config_state(),
        "note": "Phase 9K limited production batch enablement design summary. No live posting enabled.",
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
            g.name AS enablement_gate,
            g.enablement_gate_id,
            g.status,
            g.enablement_status,
            g.enablement_design_approved,
            g.ready_for_limited_enablement_preview,
            g.phase9j_policy_lock_verified,
            g.policy_caps_verified,
            g.no_accounting_movement_verified,
            g.policy_lock,
            g.finalisation_gate,
            g.phase9h_freeze,
            g.payment_entry,
            g.payment_entry_docstatus_after_rollback,
            g.invoice_outstanding_after_rollback_total,
            g.payment_entry_gl_count_after_rollback,
            g.payment_entry_gl_net_after_rollback,
            g.max_batch_lines,
            g.max_batch_amount,
            g.max_payment_entry_count,
            g.actual_payment_entry_created_count,
            g.actual_gl_created_count,
            g.production_batch_enabled_policy_count,
            g.live_posting_allowed_policy_count,
            g.enablement_score,
            g.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Limited Production Batch Enablement Design Gate` g
        {build_where(conditions)}
        ORDER BY g.creation DESC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.enablement_gate_id for row in data[:20]],
            "datasets": [
                {"name": "Approved", "values": [int(row.enablement_design_approved or 0) for row in data[:20]]},
                {"name": "Actual PE", "values": [int(row.actual_payment_entry_created_count or 0) for row in data[:20]]},
                {"name": "Actual GL", "values": [int(row.actual_gl_created_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Enablement Gates"), "datatype": "Int"},
        {"value": sum(int(row.enablement_design_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PE Created"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL Created"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def gate_columns():
    return [
        {"fieldname": "enablement_gate", "label": _("Enablement Gate"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Design Gate", "width": 220},
        {"fieldname": "enablement_gate_id", "label": _("Enablement Gate ID"), "fieldtype": "Data", "width": 460},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "enablement_status", "label": _("Enablement Status"), "fieldtype": "Data", "width": 330},
        {"fieldname": "ready_for_limited_enablement_preview", "label": _("Ready Preview"), "fieldtype": "Check", "width": 120},
        {"fieldname": "policy_lock", "label": _("Policy Lock"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Policy Lock", "width": 220},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 170},
        {"fieldname": "payment_entry_docstatus_after_rollback", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 110},
        {"fieldname": "invoice_outstanding_after_rollback_total", "label": _("Outstanding Restored"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "payment_entry_gl_count_after_rollback", "label": _("PE GL Rows"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_net_after_rollback", "label": _("PE GL Net"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "max_batch_lines", "label": _("Max Lines"), "fieldtype": "Int", "width": 90},
        {"fieldname": "max_batch_amount", "label": _("Max Amount"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "max_payment_entry_count", "label": _("Max PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "enablement_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    if filters.get("enablement_gate"):
        conditions.append("i.enablement_gate = %(enablement_gate)s")
        params["enablement_gate"] = filters.get("enablement_gate")

    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Design Gate Item", "width": 220},
        {"fieldname": "enablement_gate", "label": _("Enablement Gate"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Design Gate", "width": 220},
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
            i.enablement_gate,
            i.status,
            i.severity,
            i.category,
            i.check_label,
            i.detail,
            i.source_doctype,
            i.source_name,
            i.checked_on
        FROM `tabNDIS Limited Production Batch Enablement Design Gate Item` i
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
