import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


POLICY_REVIEW_ACK = "I_CONFIRM_PHASE9A_APPROVE_CONTROLLED_PRODUCTION_BATCH_POLICY_REVIEW_NO_POSTING"


def make_policy_review_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-CTRL-PROD-BATCH-POLICY-REVIEW-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def has_pe_phase8e_fields():
    return frappe.db.has_column("Payment Entry", "custom_ndis_controlled_prod_batch_smoke")


def submitted_phase8e_smoke_pe_count():
    if not has_pe_phase8e_fields():
        return 0

    return count_dt(
        "Payment Entry",
        {
            "docstatus": 1,
            "custom_ndis_controlled_prod_batch_smoke": 1,
        },
    )


def cancelled_phase8e_smoke_pe_count():
    if not has_pe_phase8e_fields():
        return 0

    return count_dt(
        "Payment Entry",
        {
            "docstatus": 2,
            "custom_ndis_controlled_prod_batch_smoke": 1,
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
        "submitted_journal_entry_count_today": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}),
        "purchase_invoice_count_today": count_dt("Purchase Invoice", {"creation": [">=", today()]}),
        "production_batch_enabled_policy_count": count_dt("NDIS Controlled Production Batch Posting Policy", {"production_batch_enabled": 1}),
        "live_posting_allowed_policy_count": count_dt("NDIS Controlled Production Batch Posting Policy", {"live_posting_allowed": 1}),
        "submitted_phase8e_smoke_pe_count": submitted_phase8e_smoke_pe_count(),
        "cancelled_phase8e_smoke_pe_count": cancelled_phase8e_smoke_pe_count(),
    }


def latest_freeze():
    rows = frappe.get_all(
        "NDIS Controlled Production Batch Smoke Evidence Freeze",
        filters={
            "status": "Frozen",
            "evidence_freeze_allowed": 1,
            "ready_for_next_phase": 1,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "payment_entry_docstatus_after_rollback": 2,
            "submitted_phase8e_smoke_pe_count": 0,
        },
        fields=[
            "name",
            "freeze_id",
            "rollback_run",
            "smoke_run",
            "activation_gate",
            "adapter_run",
            "preview",
            "design_gate",
            "phase7h_freeze",
            "source_run",
            "company",
            "customer",
            "payment_entry",
            "evidence_freeze_allowed",
            "rollback_completed",
            "controlled_payment_entry_cancelled",
            "payment_entry_docstatus_after_rollback",
            "payment_entry_amount",
            "invoice_count",
            "invoice_outstanding_after_rollback_total",
            "payment_entry_gl_count_after_rollback",
            "payment_entry_gl_net_after_rollback",
            "submitted_phase8e_smoke_pe_count",
            "cancelled_phase8e_smoke_pe_count",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )

    return rows[0] if rows else None


def existing_approved_review(phase8g_freeze):
    rows = frappe.get_all(
        "NDIS Controlled Production Batch Policy Review Gate",
        filters={
            "phase8g_freeze": phase8g_freeze,
            "status": "Approved For Limited Policy Design",
            "policy_review_approved": 1,
            "ready_for_limited_policy_design": 1,
        },
        fields=["name", "policy_review_id"],
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


def validate_policy_review(freeze, guard):
    issues = []

    if not freeze:
        issues.append("No approved Phase 8G evidence freeze found.")
        return issues

    if existing_approved_review(freeze.name):
        issues.append("An approved Phase 9A policy review already exists for this Phase 8G freeze.")

    required_links = {
        "rollback_run": freeze.rollback_run,
        "smoke_run": freeze.smoke_run,
        "activation_gate": freeze.activation_gate,
        "adapter_run": freeze.adapter_run,
        "preview": freeze.preview,
        "design_gate": freeze.design_gate,
    }

    for label, value in required_links.items():
        if not value:
            issues.append(f"Missing evidence link: {label}")

    if not int(freeze.evidence_freeze_allowed or 0):
        issues.append("Phase 8G evidence freeze is not allowed.")

    if not int(freeze.rollback_completed or 0):
        issues.append("Rollback completion evidence missing.")

    if not int(freeze.controlled_payment_entry_cancelled or 0):
        issues.append("Controlled Payment Entry cancellation evidence missing.")

    if int(freeze.payment_entry_docstatus_after_rollback or 0) != 2:
        issues.append("Payment Entry is not frozen as cancelled docstatus 2.")

    if flt(freeze.payment_entry_amount or 0, 2) != 2:
        issues.append("Expected frozen controlled smoke amount 2.00.")

    if int(freeze.invoice_count or 0) != 2:
        issues.append("Expected frozen controlled smoke invoice count 2.")

    if flt(freeze.invoice_outstanding_after_rollback_total or 0, 2) != 2:
        issues.append("Expected restored invoice outstanding total 2.00.")

    if int(freeze.payment_entry_gl_count_after_rollback or 0) != 6:
        issues.append("Expected Payment Entry GL rows after rollback to be 6.")

    if flt(freeze.payment_entry_gl_net_after_rollback or 0, 2) != 0:
        issues.append("Payment Entry GL net after rollback is not zero.")

    if freeze.payment_entry:
        current_gl_count, current_gl_net = pe_gl_count_net(freeze.payment_entry)

        if current_gl_count != int(freeze.payment_entry_gl_count_after_rollback or 0):
            issues.append("Current Payment Entry GL count does not match frozen evidence.")

        if flt(current_gl_net, 2) != 0:
            issues.append("Current Payment Entry GL net is not zero.")

        if frappe.db.exists("Payment Entry", freeze.payment_entry):
            docstatus = int(frappe.db.get_value("Payment Entry", freeze.payment_entry, "docstatus") or 0)
            if docstatus != 2:
                issues.append(f"Payment Entry current docstatus is not 2. Found {docstatus}.")
        else:
            issues.append("Frozen Payment Entry no longer exists.")

    if guard["submitted_phase8e_smoke_pe_count"] != 0:
        issues.append(f"Submitted Phase 8E smoke PE count must be 0. Found {guard['submitted_phase8e_smoke_pe_count']}.")

    if guard["cancelled_phase8e_smoke_pe_count"] < 1:
        issues.append("Cancelled Phase 8E smoke PE count must be at least 1.")

    if guard["production_batch_enabled_policy_count"] != 0:
        issues.append("Controlled production batch enabled policy count is not zero.")

    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count is not zero.")

    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today is not zero.")

    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today is not zero.")

    return issues


def build_items(freeze, config, guard, issues, ack_ok):
    items = []

    if freeze:
        add_item(
            items,
            "Pass",
            "Low",
            "Evidence Freeze",
            "phase8g_freeze_exists",
            "Phase 8G evidence freeze exists",
            f"Freeze found: {freeze.freeze_id}.",
            "NDIS Controlled Production Batch Smoke Evidence Freeze",
            freeze.name,
        )
    else:
        add_item(items, "Blocker", "Critical", "Evidence Freeze", "phase8g_freeze_exists", "Phase 8G evidence freeze exists", "No approved Phase 8G freeze found.")

    if not issues:
        add_item(items, "Pass", "Low", "Evidence Chain", "policy_review_chain_valid", "Policy review evidence chain valid", "Phase 8A through Phase 8G evidence is valid for limited policy design.")
    else:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Evidence Chain", "policy_review_chain_valid", "Policy review evidence chain valid", issue)

    if freeze and freeze.payment_entry:
        add_item(
            items,
            "Pass",
            "Low",
            "Controlled Smoke",
            "smoke_pe_cancelled",
            "Controlled smoke Payment Entry cancelled",
            f"Payment Entry {freeze.payment_entry} is cancelled and rollback evidence is frozen.",
            "Payment Entry",
            freeze.payment_entry,
        )

    if config["production_mode"]:
        add_item(items, "Blocker", "Critical", "Site Config", "production_mode", "Production mode", "Production mode is enabled.")
    else:
        add_item(items, "Pass", "Low", "Site Config", "production_mode", "Production mode", "Production mode remains disabled.")

    if config["live_pe_enabled"]:
        add_item(items, "Blocker", "Critical", "Site Config", "live_pe_enabled", "Live PE posting config", "Live PE posting config is enabled.")
    else:
        add_item(items, "Pass", "Low", "Site Config", "live_pe_enabled", "Live PE posting config", "Live PE posting config remains disabled.")

    if guard["production_batch_enabled_policy_count"] == 0 and guard["live_posting_allowed_policy_count"] == 0:
        add_item(items, "Pass", "Low", "Policy Safety", "live_policies_zero", "Live policies", "No controlled production live-enabled policies.")
    else:
        add_item(items, "Blocker", "Critical", "Policy Safety", "live_policies_zero", "Live policies", "Live-enabled controlled production policy found.")

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "policy_review_ack", "Policy review acknowledgement", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "policy_review_ack", "Policy review acknowledgement", f"Required acknowledgement not supplied: {POLICY_REVIEW_ACK}")

    return items


def create_review_items(doc, items):
    for item in items:
        row = frappe.new_doc("NDIS Controlled Production Batch Policy Review Gate Item")
        row.policy_review_gate = doc.name
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
def run_controlled_production_batch_policy_review_gate(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_controlled_production_batch_policy_review_gate")

    freeze = latest_freeze()
    config = config_state()
    guard_before = guardrails()
    ack_ok = acknowledgement == POLICY_REVIEW_ACK

    issues = validate_policy_review(freeze, guard_before)
    items = build_items(freeze, config, guard_before, issues, ack_ok)

    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    approved = int(ack_ok and item_summary["blocker_count"] == 0 and freeze is not None)

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Approved For Limited Policy Design" if approved else "Needs Review",
        "policy_review_status": "Ready For Limited Production Batch Policy Design" if approved else "Needs Review",
        "policy_review_approved": approved,
        "ready_for_limited_policy_design": approved,
        "production_batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "phase8g_freeze": freeze.name if freeze else None,
        "rollback_run": freeze.rollback_run if freeze else None,
        "smoke_run": freeze.smoke_run if freeze else None,
        "activation_gate": freeze.activation_gate if freeze else None,
        "adapter_run": freeze.adapter_run if freeze else None,
        "preview": freeze.preview if freeze else None,
        "design_gate": freeze.design_gate if freeze else None,
        "phase7h_freeze": freeze.phase7h_freeze if freeze else None,
        "source_run": freeze.source_run if freeze else None,
        "company": freeze.company if freeze else None,
        "customer": freeze.customer if freeze else None,
        "payment_entry": freeze.payment_entry if freeze else None,
        "evidence_freeze_allowed": int(freeze.evidence_freeze_allowed or 0) if freeze else 0,
        "rollback_completed": int(freeze.rollback_completed or 0) if freeze else 0,
        "controlled_payment_entry_cancelled": int(freeze.controlled_payment_entry_cancelled or 0) if freeze else 0,
        "payment_entry_docstatus_after_rollback": int(freeze.payment_entry_docstatus_after_rollback or 0) if freeze else 0,
        "payment_entry_amount": flt(freeze.payment_entry_amount or 0) if freeze else 0,
        "invoice_count": int(freeze.invoice_count or 0) if freeze else 0,
        "invoice_outstanding_after_rollback_total": flt(freeze.invoice_outstanding_after_rollback_total or 0) if freeze else 0,
        "payment_entry_gl_count_after_rollback": int(freeze.payment_entry_gl_count_after_rollback or 0) if freeze else 0,
        "payment_entry_gl_net_after_rollback": flt(freeze.payment_entry_gl_net_after_rollback or 0) if freeze else 0,
        "submitted_phase8e_smoke_pe_count": guard_before["submitted_phase8e_smoke_pe_count"],
        "cancelled_phase8e_smoke_pe_count": guard_before["cancelled_phase8e_smoke_pe_count"],
        "recommended_policy_mode": "Limited Controlled Production Batch",
        "recommended_max_batch_lines": 3,
        "recommended_max_batch_amount": 3,
        "recommended_payment_entry_count": 1,
        "actual_payment_entry_created_count": 0,
        "actual_gl_created_count": 0,
        "policy_review_score": score,
        **item_summary,
        "items": items,
        "guardrails_before": guard_before,
        "guardrails_after": guardrails(),
        "config": config,
        "required_acknowledgement": POLICY_REVIEW_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 9A is policy-review only. It creates no accounting movement and enables no live policy.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["policy_review_status"] = "Needs Review"
        result["policy_review_approved"] = 0
        result["ready_for_limited_policy_design"] = 0
        return result

    doc = frappe.new_doc("NDIS Controlled Production Batch Policy Review Gate")
    doc.policy_review_id = make_policy_review_id()
    doc.status = result["status"]
    doc.policy_review_status = result["policy_review_status"]
    doc.policy_review_approved = approved
    doc.ready_for_limited_policy_design = approved
    doc.production_batch_posting_allowed = 0
    doc.real_posting_allowed = 0

    for fieldname in [
        "phase8g_freeze",
        "rollback_run",
        "smoke_run",
        "activation_gate",
        "adapter_run",
        "preview",
        "design_gate",
        "phase7h_freeze",
        "source_run",
        "company",
        "customer",
        "payment_entry",
        "evidence_freeze_allowed",
        "rollback_completed",
        "controlled_payment_entry_cancelled",
        "payment_entry_docstatus_after_rollback",
        "payment_entry_amount",
        "invoice_count",
        "invoice_outstanding_after_rollback_total",
        "payment_entry_gl_count_after_rollback",
        "payment_entry_gl_net_after_rollback",
        "submitted_phase8e_smoke_pe_count",
        "cancelled_phase8e_smoke_pe_count",
        "recommended_policy_mode",
        "recommended_max_batch_lines",
        "recommended_max_batch_amount",
        "recommended_payment_entry_count",
        "actual_payment_entry_created_count",
        "actual_gl_created_count",
        "policy_review_score",
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

    doc.payment_entry_count_before = guard_before["payment_entry_count"]
    doc.payment_entry_count_after = guardrails()["payment_entry_count"]
    doc.payment_entry_gl_count_before = guard_before["payment_entry_gl_count"]
    doc.payment_entry_gl_count_after = guardrails()["payment_entry_gl_count"]
    doc.submitted_journal_entry_count_today = guard_before["submitted_journal_entry_count_today"]
    doc.purchase_invoice_count_today = guard_before["purchase_invoice_count_today"]
    doc.production_batch_enabled_policy_count = guard_before["production_batch_enabled_policy_count"]
    doc.live_posting_allowed_policy_count = guard_before["live_posting_allowed_policy_count"]

    doc.required_acknowledgement = POLICY_REVIEW_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    create_review_items(doc, items)

    guard_after = guardrails()

    frappe.db.set_value(
        "NDIS Controlled Production Batch Policy Review Gate",
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
    result["policy_review_gate"] = doc.name
    result["policy_review_id"] = doc.policy_review_id
    result["guardrails_after"] = guard_after

    return result


@frappe.whitelist()
def cancel_controlled_production_batch_policy_review_gate(policy_review_gate, reason=None):
    assert_action("cancel_controlled_production_batch_policy_review_gate")

    if not frappe.db.exists("NDIS Controlled Production Batch Policy Review Gate", policy_review_gate):
        frappe.throw(_("Policy review gate not found: {0}").format(policy_review_gate))

    doc = frappe.get_doc("NDIS Controlled Production Batch Policy Review Gate", policy_review_gate)

    if doc.status == "Cancelled":
        return {"policy_review_gate": policy_review_gate, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.policy_review_approved or 0):
        frappe.throw(_("Cannot cancel an approved policy review gate. Create a superseding review instead."))

    frappe.db.set_value(
        "NDIS Controlled Production Batch Policy Review Gate",
        policy_review_gate,
        {
            "status": "Cancelled",
            "policy_review_status": "Cancelled",
            "policy_review_approved": 0,
            "ready_for_limited_policy_design": 0,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 9A policy review gate audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        """
        UPDATE `tabNDIS Controlled Production Batch Policy Review Gate Item`
        SET status = 'Cancelled'
        WHERE policy_review_gate = %(policy_review_gate)s
        """,
        {"policy_review_gate": policy_review_gate},
    )

    frappe.db.commit()

    return {
        "policy_review_gate": policy_review_gate,
        "status": "Cancelled",
        "note": "Policy review audit record cancelled only. No accounting movement occurred.",
    }


@frappe.whitelist()
def quick_controlled_production_batch_policy_review_summary(limit=20):
    gates = frappe.get_all(
        "NDIS Controlled Production Batch Policy Review Gate",
        fields=[
            "name",
            "policy_review_id",
            "status",
            "policy_review_status",
            "policy_review_approved",
            "ready_for_limited_policy_design",
            "production_batch_posting_allowed",
            "real_posting_allowed",
            "phase8g_freeze",
            "rollback_run",
            "smoke_run",
            "payment_entry",
            "payment_entry_docstatus_after_rollback",
            "payment_entry_amount",
            "invoice_count",
            "invoice_outstanding_after_rollback_total",
            "payment_entry_gl_count_after_rollback",
            "payment_entry_gl_net_after_rollback",
            "submitted_phase8e_smoke_pe_count",
            "cancelled_phase8e_smoke_pe_count",
            "recommended_policy_mode",
            "recommended_max_batch_lines",
            "recommended_max_batch_amount",
            "recommended_payment_entry_count",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
            "policy_review_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    items = frappe.get_all(
        "NDIS Controlled Production Batch Policy Review Gate Item",
        fields=[
            "name",
            "policy_review_gate",
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
        "required_acknowledgement": POLICY_REVIEW_ACK,
        "guardrails": guardrails(),
        "config": config_state(),
        "note": "Phase 9A policy review summary. Review-only; no accounting movement.",
    }


def execute_policy_review_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("status"):
        conditions.append("g.status = %(status)s")
        params["status"] = filters.get("status")

    columns = policy_review_columns()

    data = frappe.db.sql(
        f"""
        SELECT
            g.name AS policy_review_gate,
            g.policy_review_id,
            g.status,
            g.policy_review_status,
            g.policy_review_approved,
            g.ready_for_limited_policy_design,
            g.production_batch_posting_allowed,
            g.real_posting_allowed,
            g.phase8g_freeze,
            g.payment_entry,
            g.payment_entry_docstatus_after_rollback,
            g.payment_entry_amount,
            g.invoice_count,
            g.invoice_outstanding_after_rollback_total,
            g.payment_entry_gl_count_after_rollback,
            g.payment_entry_gl_net_after_rollback,
            g.recommended_policy_mode,
            g.recommended_max_batch_lines,
            g.recommended_max_batch_amount,
            g.actual_payment_entry_created_count,
            g.actual_gl_created_count,
            g.policy_review_score,
            g.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Controlled Production Batch Policy Review Gate` g
        {build_where(conditions)}
        ORDER BY g.creation DESC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.policy_review_id for row in data[:20]],
            "datasets": [
                {"name": "Approved", "values": [int(row.policy_review_approved or 0) for row in data[:20]]},
                {"name": "Actual PE", "values": [int(row.actual_payment_entry_created_count or 0) for row in data[:20]]},
                {"name": "Actual GL", "values": [int(row.actual_gl_created_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Policy Reviews"), "datatype": "Int"},
        {"value": sum(int(row.policy_review_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(flt(row.recommended_max_batch_amount or 0) for row in data), "indicator": "Blue", "label": _("Recommended Batch Cap"), "datatype": "Currency", "currency": currency()},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PE Created"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def policy_review_columns():
    return [
        {"fieldname": "policy_review_gate", "label": _("Policy Review Gate"), "fieldtype": "Link", "options": "NDIS Controlled Production Batch Policy Review Gate", "width": 220},
        {"fieldname": "policy_review_id", "label": _("Policy Review ID"), "fieldtype": "Data", "width": 420},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 230},
        {"fieldname": "policy_review_status", "label": _("Policy Review Status"), "fieldtype": "Data", "width": 320},
        {"fieldname": "ready_for_limited_policy_design", "label": _("Ready Design"), "fieldtype": "Check", "width": 110},
        {"fieldname": "phase8g_freeze", "label": _("Phase 8G Freeze"), "fieldtype": "Link", "options": "NDIS Controlled Production Batch Smoke Evidence Freeze", "width": 220},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 170},
        {"fieldname": "payment_entry_docstatus_after_rollback", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_amount", "label": _("PE Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "invoice_outstanding_after_rollback_total", "label": _("Outstanding Restored"), "fieldtype": "Currency", "options": "currency", "width": 160},
        {"fieldname": "recommended_policy_mode", "label": _("Recommended Mode"), "fieldtype": "Data", "width": 240},
        {"fieldname": "recommended_max_batch_lines", "label": _("Max Lines"), "fieldtype": "Int", "width": 90},
        {"fieldname": "recommended_max_batch_amount", "label": _("Max Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "policy_review_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_exception_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    if filters.get("policy_review_gate"):
        conditions.append("i.policy_review_gate = %(policy_review_gate)s")
        params["policy_review_gate"] = filters.get("policy_review_gate")

    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": "NDIS Controlled Production Batch Policy Review Gate Item", "width": 220},
        {"fieldname": "policy_review_gate", "label": _("Policy Review Gate"), "fieldtype": "Link", "options": "NDIS Controlled Production Batch Policy Review Gate", "width": 220},
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
            i.policy_review_gate,
            i.status,
            i.severity,
            i.category,
            i.check_label,
            i.detail,
            i.source_doctype,
            i.source_name,
            i.checked_on
        FROM `tabNDIS Controlled Production Batch Policy Review Gate Item` i
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
    columns, data, message, chart, summary = execute_policy_review_report(filters)

    guard = guardrails()

    summary.append({"value": guard["payment_entry_count"], "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"})
    summary.append({"value": guard["payment_entry_gl_count"], "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"})
    summary.append({"value": guard["submitted_phase8e_smoke_pe_count"], "indicator": "Green", "label": _("Submitted Phase 8E Smoke PE"), "datatype": "Int"})
    summary.append({"value": guard["cancelled_phase8e_smoke_pe_count"], "indicator": "Orange", "label": _("Cancelled Phase 8E Smoke PE"), "datatype": "Int"})
    summary.append({"value": guard["submitted_journal_entry_count_today"], "indicator": "Red", "label": _("Submitted JE Today"), "datatype": "Int"})
    summary.append({"value": guard["purchase_invoice_count_today"], "indicator": "Red", "label": _("Purchase Invoice Today"), "datatype": "Int"})
    summary.append({"value": guard["production_batch_enabled_policy_count"], "indicator": "Red", "label": _("Production Batch Enabled Policies"), "datatype": "Int"})
    summary.append({"value": guard["live_posting_allowed_policy_count"], "indicator": "Red", "label": _("Live Posting Allowed Policies"), "datatype": "Int"})

    return columns, data, message, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
