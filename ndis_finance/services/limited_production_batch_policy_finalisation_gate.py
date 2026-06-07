import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


FINALISATION_ACK = "I_CONFIRM_PHASE9I_APPROVE_LIMITED_PRODUCTION_BATCH_POLICY_FINALISATION_NO_POSTING"


def make_finalisation_gate_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-LIMITED-PROD-BATCH-FINALISATION-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_phase9h_freeze():
    rows = frappe.get_all(
        "NDIS Limited Production Batch Smoke Evidence Freeze",
        filters={
            "status": "Frozen",
            "evidence_freeze_allowed": 1,
            "ready_for_next_phase": 1,
            "rollback_verified": 1,
            "controlled_payment_entry_cancelled": 1,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "payment_entry_docstatus_after_rollback": 2,
            "submitted_phase9f_smoke_pe_count": 0,
            "cancelled_phase9f_smoke_pe_count": 1,
        },
        fields=[
            "name",
            "evidence_freeze_id",
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
            "submitted_phase9f_smoke_pe_count",
            "cancelled_phase9f_smoke_pe_count",
            "freeze_score",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )

    return rows[0] if rows else None


def existing_approved_gate(phase9h_freeze):
    rows = frappe.get_all(
        "NDIS Limited Production Batch Policy Finalisation Gate",
        filters={
            "phase9h_freeze": phase9h_freeze,
            "status": "Approved",
            "policy_finalisation_approved": 1,
            "ready_for_limited_policy_lock": 1,
        },
        fields=["name", "finalisation_gate_id"],
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


def validate_source(freeze, guard):
    issues = []

    if not freeze:
        issues.append("No Frozen Phase 9H evidence freeze found.")
        return issues

    if existing_approved_gate(freeze.name):
        issues.append("An approved Phase 9I finalisation gate already exists for this Phase 9H freeze.")

    required_links = {
        "rollback_run": freeze.rollback_run,
        "smoke_run": freeze.smoke_run,
        "activation_gate": freeze.activation_gate,
        "adapter_run": freeze.adapter_run,
        "policy_preview": freeze.policy_preview,
        "policy_design": freeze.policy_design,
        "policy_review_gate": freeze.policy_review_gate,
    }

    for label, value in required_links.items():
        if not value:
            issues.append(f"Missing evidence link: {label}")

    if not freeze.payment_entry or not frappe.db.exists("Payment Entry", freeze.payment_entry):
        issues.append("Frozen Payment Entry does not exist.")
    else:
        docstatus = int(frappe.db.get_value("Payment Entry", freeze.payment_entry, "docstatus") or 0)
        if docstatus != 2:
            issues.append(f"Frozen Payment Entry must be cancelled. Found docstatus {docstatus}.")

        gl_count, gl_net = pe_gl_count_net(freeze.payment_entry)

        if gl_count != int(freeze.payment_entry_gl_count_after_rollback or 0):
            issues.append("Current PE GL row count does not match Phase 9H frozen evidence.")

        if gl_count != 6:
            issues.append(f"Expected PE GL rows after rollback to be 6. Found {gl_count}.")

        if flt(gl_net, 2) != 0:
            issues.append(f"Expected PE GL net to be 0.00. Found {gl_net}.")

    if int(freeze.payment_entry_docstatus_after_rollback or 0) != 2:
        issues.append("Phase 9H freeze must show Payment Entry docstatus after rollback = 2.")

    if flt(freeze.invoice_outstanding_after_rollback_total or 0, 2) != 2:
        issues.append("Phase 9H freeze must show invoice outstanding after rollback = 2.00.")

    if int(freeze.payment_entry_gl_count_after_rollback or 0) != 6:
        issues.append("Phase 9H freeze must show PE GL rows after rollback = 6.")

    if flt(freeze.payment_entry_gl_net_after_rollback or 0, 2) != 0:
        issues.append("Phase 9H freeze must show PE GL net after rollback = 0.00.")

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


def build_items(freeze, guard, issues, ack_ok):
    items = []

    if freeze:
        add_item(
            items,
            "Pass",
            "Low",
            "Phase 9H Freeze",
            "phase9h_freeze_exists",
            "Phase 9H evidence freeze exists",
            f"Freeze found: {freeze.evidence_freeze_id}.",
            "NDIS Limited Production Batch Smoke Evidence Freeze",
            freeze.name,
        )
    else:
        add_item(items, "Blocker", "Critical", "Phase 9H Freeze", "phase9h_freeze_exists", "Phase 9H evidence freeze exists", "No Frozen Phase 9H evidence freeze found.")

    if not issues:
        add_item(items, "Pass", "Low", "Finalisation Source", "source_valid", "Finalisation source valid", "Phase 9H freeze evidence is valid for policy finalisation.")
    else:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Finalisation Source", "source_valid", "Finalisation source valid", issue)

    if freeze and freeze.payment_entry:
        add_item(
            items,
            "Pass",
            "Low",
            "Payment Entry",
            "pe_cancelled",
            "Payment Entry cancelled",
            f"{freeze.payment_entry} docstatus after rollback = {freeze.payment_entry_docstatus_after_rollback}.",
            "Payment Entry",
            freeze.payment_entry,
        )

    if freeze:
        add_item(items, "Pass", "Low", "Invoice Evidence", "invoice_restored", "Invoice restoration proved", f"Outstanding restored to {freeze.invoice_outstanding_after_rollback_total}.")
        add_item(items, "Pass", "Low", "GL Evidence", "gl_net_zero", "GL net-zero proved", f"Rows {freeze.payment_entry_gl_count_after_rollback}, net {freeze.payment_entry_gl_net_after_rollback}.")

    if guard["production_batch_enabled_policy_count"] == 0 and guard["live_posting_allowed_policy_count"] == 0:
        add_item(items, "Pass", "Low", "Policy Safety", "live_policies_zero", "Live policies disabled", "No controlled production batch policies are live-enabled.")
    else:
        add_item(items, "Blocker", "Critical", "Policy Safety", "live_policies_zero", "Live policies disabled", "Live-enabled policy found.")

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "finalisation_ack", "Finalisation acknowledgement", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "finalisation_ack", "Finalisation acknowledgement", f"Required acknowledgement not supplied: {FINALISATION_ACK}")

    return items


def create_items(doc, items):
    for item in items:
        row = frappe.new_doc("NDIS Limited Production Batch Policy Finalisation Gate Item")
        row.finalisation_gate = doc.name
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
def run_limited_production_batch_policy_finalisation_gate(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_limited_production_batch_policy_finalisation_gate")

    freeze = latest_phase9h_freeze()
    config = config_state()
    guard_before = guardrails()
    ack_ok = acknowledgement == FINALISATION_ACK

    issues = validate_source(freeze, guard_before)
    items = build_items(freeze, guard_before, issues, ack_ok)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    approved = int(ack_ok and item_summary["blocker_count"] == 0 and freeze is not None)

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Approved" if approved else "Needs Review",
        "finalisation_status": "Ready For Limited Production Batch Policy Lock" if approved else "Needs Review",
        "policy_finalisation_approved": approved,
        "ready_for_limited_policy_lock": approved,
        "phase9h_freeze_verified": 1 if freeze else 0,
        "smoke_rollback_verified": 1 if freeze else 0,
        "gl_net_zero_verified": 1 if freeze and flt(freeze.payment_entry_gl_net_after_rollback or 0, 2) == 0 else 0,
        "invoice_restoration_verified": 1 if freeze and flt(freeze.invoice_outstanding_after_rollback_total or 0, 2) == 2 else 0,
        "production_batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "policy_live_enabled": 0,
        "phase9h_freeze": freeze.name if freeze else None,
        "rollback_run": freeze.rollback_run if freeze else None,
        "smoke_run": freeze.smoke_run if freeze else None,
        "activation_gate": freeze.activation_gate if freeze else None,
        "adapter_run": freeze.adapter_run if freeze else None,
        "policy_preview": freeze.policy_preview if freeze else None,
        "policy_design": freeze.policy_design if freeze else None,
        "policy_review_gate": freeze.policy_review_gate if freeze else None,
        "phase8g_freeze": freeze.phase8g_freeze if freeze else None,
        "company": freeze.company if freeze else None,
        "customer": freeze.customer if freeze else None,
        "payment_entry": freeze.payment_entry if freeze else None,
        "payment_entry_docstatus_after_rollback": int(freeze.payment_entry_docstatus_after_rollback or 0) if freeze else 0,
        "payment_entry_amount": flt(freeze.payment_entry_amount or 0) if freeze else 0,
        "reference_count": int(freeze.reference_count or 0) if freeze else 0,
        "invoice_outstanding_after_rollback_total": flt(freeze.invoice_outstanding_after_rollback_total or 0) if freeze else 0,
        "payment_entry_gl_count_after_rollback": int(freeze.payment_entry_gl_count_after_rollback or 0) if freeze else 0,
        "payment_entry_gl_net_after_rollback": flt(freeze.payment_entry_gl_net_after_rollback or 0) if freeze else 0,
        "limited_batch_line_cap": 3,
        "limited_batch_amount_cap": 3,
        "limited_payment_entry_cap": 1,
        "approved_next_step": "Limited Production Batch Policy Lock",
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
        "finalisation_score": score,
        **item_summary,
        "items": items,
        "guardrails_before": guard_before,
        "guardrails_after": guardrails(),
        "config": config,
        "required_acknowledgement": FINALISATION_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 9I is a finalisation gate only. It creates no accounting movement and enables no live policies.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["finalisation_status"] = "Needs Review"
        result["policy_finalisation_approved"] = 0
        result["ready_for_limited_policy_lock"] = 0
        return result

    doc = frappe.new_doc("NDIS Limited Production Batch Policy Finalisation Gate")
    doc.finalisation_gate_id = make_finalisation_gate_id()
    doc.status = result["status"]
    doc.finalisation_status = result["finalisation_status"]

    for fieldname in [
        "policy_finalisation_approved",
        "ready_for_limited_policy_lock",
        "phase9h_freeze_verified",
        "smoke_rollback_verified",
        "gl_net_zero_verified",
        "invoice_restoration_verified",
        "production_batch_posting_allowed",
        "real_posting_allowed",
        "policy_live_enabled",
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
        "submitted_journal_entry_count_today",
        "purchase_invoice_count_today",
        "production_batch_enabled_policy_count",
        "live_posting_allowed_policy_count",
        "payment_entry_count_before",
        "payment_entry_count_after",
        "payment_entry_gl_count_before",
        "payment_entry_gl_count_after",
        "finalisation_score",
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
    doc.required_acknowledgement = FINALISATION_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    create_items(doc, items)

    guard_after = guardrails()

    frappe.db.set_value(
        "NDIS Limited Production Batch Policy Finalisation Gate",
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
    result["finalisation_gate"] = doc.name
    result["finalisation_gate_id"] = doc.finalisation_gate_id
    result["guardrails_after"] = guard_after

    return result


@frappe.whitelist()
def cancel_limited_production_batch_policy_finalisation_gate(finalisation_gate, reason=None):
    assert_action("cancel_limited_production_batch_policy_finalisation_gate")

    if not frappe.db.exists("NDIS Limited Production Batch Policy Finalisation Gate", finalisation_gate):
        frappe.throw(_("Finalisation gate not found: {0}").format(finalisation_gate))

    doc = frappe.get_doc("NDIS Limited Production Batch Policy Finalisation Gate", finalisation_gate)

    if doc.status == "Cancelled":
        return {"finalisation_gate": finalisation_gate, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.policy_finalisation_approved or 0):
        frappe.throw(_("Cannot cancel an approved finalisation gate. Create a superseding gate instead."))

    frappe.db.set_value(
        "NDIS Limited Production Batch Policy Finalisation Gate",
        finalisation_gate,
        {
            "status": "Cancelled",
            "finalisation_status": "Cancelled",
            "policy_finalisation_approved": 0,
            "ready_for_limited_policy_lock": 0,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 9I finalisation gate audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        """
        UPDATE `tabNDIS Limited Production Batch Policy Finalisation Gate Item`
        SET status = 'Cancelled'
        WHERE finalisation_gate = %(finalisation_gate)s
        """,
        {"finalisation_gate": finalisation_gate},
    )

    frappe.db.commit()

    return {
        "finalisation_gate": finalisation_gate,
        "status": "Cancelled",
        "note": "Finalisation gate audit record cancelled only. No accounting movement occurred.",
    }


@frappe.whitelist()
def quick_limited_production_batch_policy_finalisation_summary(limit=20):
    gates = frappe.get_all(
        "NDIS Limited Production Batch Policy Finalisation Gate",
        fields=[
            "name",
            "finalisation_gate_id",
            "status",
            "finalisation_status",
            "policy_finalisation_approved",
            "ready_for_limited_policy_lock",
            "phase9h_freeze_verified",
            "smoke_rollback_verified",
            "gl_net_zero_verified",
            "invoice_restoration_verified",
            "phase9h_freeze",
            "rollback_run",
            "smoke_run",
            "payment_entry",
            "payment_entry_docstatus_after_rollback",
            "invoice_outstanding_after_rollback_total",
            "payment_entry_gl_count_after_rollback",
            "payment_entry_gl_net_after_rollback",
            "submitted_phase9f_smoke_pe_count",
            "cancelled_phase9f_smoke_pe_count",
            "production_batch_enabled_policy_count",
            "live_posting_allowed_policy_count",
            "finalisation_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    items = frappe.get_all(
        "NDIS Limited Production Batch Policy Finalisation Gate Item",
        fields=[
            "name",
            "finalisation_gate",
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
        "required_acknowledgement": FINALISATION_ACK,
        "guardrails": guardrails(),
        "config": config_state(),
        "note": "Phase 9I limited production batch policy finalisation gate summary. No live posting enabled.",
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
            g.name AS finalisation_gate,
            g.finalisation_gate_id,
            g.status,
            g.finalisation_status,
            g.policy_finalisation_approved,
            g.ready_for_limited_policy_lock,
            g.phase9h_freeze_verified,
            g.smoke_rollback_verified,
            g.gl_net_zero_verified,
            g.invoice_restoration_verified,
            g.phase9h_freeze,
            g.rollback_run,
            g.smoke_run,
            g.payment_entry,
            g.payment_entry_docstatus_after_rollback,
            g.invoice_outstanding_after_rollback_total,
            g.payment_entry_gl_count_after_rollback,
            g.payment_entry_gl_net_after_rollback,
            g.submitted_phase9f_smoke_pe_count,
            g.cancelled_phase9f_smoke_pe_count,
            g.production_batch_enabled_policy_count,
            g.live_posting_allowed_policy_count,
            g.finalisation_score,
            g.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Limited Production Batch Policy Finalisation Gate` g
        {build_where(conditions)}
        ORDER BY g.creation DESC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.finalisation_gate_id for row in data[:20]],
            "datasets": [
                {"name": "Approved", "values": [int(row.policy_finalisation_approved or 0) for row in data[:20]]},
                {"name": "Live Policies", "values": [int(row.live_posting_allowed_policy_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Finalisation Gates"), "datatype": "Int"},
        {"value": sum(int(row.policy_finalisation_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(int(row.cancelled_phase9f_smoke_pe_count or 0) for row in data), "indicator": "Green", "label": _("Cancelled Smoke PE"), "datatype": "Int"},
        {"value": sum(int(row.live_posting_allowed_policy_count or 0) for row in data), "indicator": "Red", "label": _("Live Policies"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def gate_columns():
    return [
        {"fieldname": "finalisation_gate", "label": _("Finalisation Gate"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Policy Finalisation Gate", "width": 220},
        {"fieldname": "finalisation_gate_id", "label": _("Finalisation Gate ID"), "fieldtype": "Data", "width": 430},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "finalisation_status", "label": _("Finalisation Status"), "fieldtype": "Data", "width": 310},
        {"fieldname": "ready_for_limited_policy_lock", "label": _("Ready Lock"), "fieldtype": "Check", "width": 100},
        {"fieldname": "phase9h_freeze", "label": _("Phase 9H Freeze"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Smoke Evidence Freeze", "width": 220},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 170},
        {"fieldname": "payment_entry_docstatus_after_rollback", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 110},
        {"fieldname": "invoice_outstanding_after_rollback_total", "label": _("Outstanding Restored"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "payment_entry_gl_count_after_rollback", "label": _("PE GL Rows"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_net_after_rollback", "label": _("PE GL Net"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "submitted_phase9f_smoke_pe_count", "label": _("Submitted PE"), "fieldtype": "Int", "width": 100},
        {"fieldname": "cancelled_phase9f_smoke_pe_count", "label": _("Cancelled PE"), "fieldtype": "Int", "width": 100},
        {"fieldname": "finalisation_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    if filters.get("finalisation_gate"):
        conditions.append("i.finalisation_gate = %(finalisation_gate)s")
        params["finalisation_gate"] = filters.get("finalisation_gate")

    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Policy Finalisation Gate Item", "width": 220},
        {"fieldname": "finalisation_gate", "label": _("Finalisation Gate"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Policy Finalisation Gate", "width": 220},
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
            i.finalisation_gate,
            i.status,
            i.severity,
            i.category,
            i.check_label,
            i.detail,
            i.source_doctype,
            i.source_name,
            i.checked_on
        FROM `tabNDIS Limited Production Batch Policy Finalisation Gate Item` i
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