import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


FREEZE_ACK = "I_CONFIRM_PHASE8G_FREEZE_CONTROLLED_PRODUCTION_BATCH_SMOKE_EVIDENCE"


def make_freeze_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-CTRL-PROD-BATCH-FREEZE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_rollback_run():
    rows = frappe.get_all(
        "NDIS Controlled Production Batch Smoke Rollback Run",
        filters={
            "status": "Rolled Back",
            "rollback_completed": 1,
            "ready_for_freeze": 1,
            "controlled_payment_entry_cancelled": 1,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "payment_entry_docstatus_after": 2,
            "submitted_phase8e_smoke_pe_count_after": 0,
        },
        fields=[
            "name",
            "rollback_run_id",
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
            "rollback_completed",
            "controlled_payment_entry_cancelled",
            "payment_entry_docstatus_after",
            "payment_entry_amount",
            "invoice_count",
            "invoice_outstanding_after_rollback_total",
            "payment_entry_gl_count_after_rollback",
            "payment_entry_gl_net_after_rollback",
            "submitted_phase8e_smoke_pe_count_after",
            "cancelled_phase8e_smoke_pe_count_after",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )

    return rows[0] if rows else None


def existing_frozen_evidence(rollback_run):
    rows = frappe.get_all(
        "NDIS Controlled Production Batch Smoke Evidence Freeze",
        filters={
            "rollback_run": rollback_run,
            "status": "Frozen",
            "evidence_freeze_allowed": 1,
            "ready_for_next_phase": 1,
        },
        fields=["name", "freeze_id"],
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


def validate_evidence_chain(rollback, guard):
    issues = []

    if not rollback:
        issues.append("No completed Phase 8F rollback run found.")
        return issues

    if existing_frozen_evidence(rollback.name):
        issues.append("A frozen Phase 8G evidence record already exists for this rollback run.")

    required_links = {
        "smoke_run": rollback.smoke_run,
        "activation_gate": rollback.activation_gate,
        "adapter_run": rollback.adapter_run,
        "preview": rollback.preview,
        "design_gate": rollback.design_gate,
    }

    for label, value in required_links.items():
        if not value:
            issues.append(f"Missing evidence link: {label}")

    if not rollback.payment_entry:
        issues.append("Rollback run has no Payment Entry linked.")
    elif not frappe.db.exists("Payment Entry", rollback.payment_entry):
        issues.append(f"Payment Entry does not exist: {rollback.payment_entry}")
    else:
        pe = frappe.get_doc("Payment Entry", rollback.payment_entry)

        if pe.docstatus != 2:
            issues.append(f"Payment Entry is not cancelled. Current docstatus: {pe.docstatus}")

        if pe.meta.has_field("custom_ndis_controlled_prod_batch_smoke") and not int(pe.custom_ndis_controlled_prod_batch_smoke or 0):
            issues.append("Payment Entry is not tagged as Phase 8E controlled production batch smoke.")

        if pe.meta.has_field("custom_ndis_controlled_prod_batch_smoke_run") and pe.custom_ndis_controlled_prod_batch_smoke_run != rollback.smoke_run:
            issues.append("Payment Entry smoke run tag does not match rollback smoke run.")

    if not int(rollback.rollback_completed or 0):
        issues.append("Rollback completed flag is not set.")

    if not int(rollback.controlled_payment_entry_cancelled or 0):
        issues.append("Controlled Payment Entry cancelled flag is not set.")

    if int(rollback.payment_entry_docstatus_after or 0) != 2:
        issues.append("Rollback evidence does not show Payment Entry docstatus 2.")

    if flt(rollback.invoice_outstanding_after_rollback_total or 0, 2) != flt(rollback.payment_entry_amount or 0, 2):
        issues.append("Invoice outstanding after rollback does not equal Payment Entry amount.")

    if flt(rollback.invoice_outstanding_after_rollback_total or 0, 2) <= 0:
        issues.append("Invoice outstanding after rollback was not restored.")

    pe_gl_count, pe_gl_net = pe_gl_count_net(rollback.payment_entry) if rollback.payment_entry else (0, 0)

    if pe_gl_count != int(rollback.payment_entry_gl_count_after_rollback or 0):
        issues.append(
            f"Payment Entry GL row count mismatch. Rollback says {rollback.payment_entry_gl_count_after_rollback}, current is {pe_gl_count}."
        )

    if flt(pe_gl_net, 2) != 0:
        issues.append(f"Payment Entry GL net is not zero: {pe_gl_net}")

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


def build_items(rollback, config, guard, issues, ack_ok):
    items = []

    if rollback:
        add_item(
            items,
            "Pass",
            "Low",
            "Rollback",
            "rollback_exists",
            "Phase 8F rollback exists",
            f"Rollback run found: {rollback.rollback_run_id}.",
            "NDIS Controlled Production Batch Smoke Rollback Run",
            rollback.name,
        )
    else:
        add_item(items, "Blocker", "Critical", "Rollback", "rollback_exists", "Phase 8F rollback exists", "No completed rollback found.")

    if not issues:
        add_item(items, "Pass", "Low", "Evidence Chain", "evidence_chain_valid", "Evidence chain valid", "Phase 8A through Phase 8F evidence chain is valid.")
    else:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Evidence Chain", "evidence_chain_valid", "Evidence chain valid", issue)

    if rollback and rollback.payment_entry:
        add_item(
            items,
            "Pass",
            "Low",
            "Payment Entry",
            "payment_entry_cancelled",
            "Payment Entry cancelled",
            f"Payment Entry {rollback.payment_entry} is cancelled with docstatus {rollback.payment_entry_docstatus_after}.",
            "Payment Entry",
            rollback.payment_entry,
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
        add_item(items, "Pass", "Low", "Acknowledgement", "freeze_ack", "Freeze acknowledgement", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "freeze_ack", "Freeze acknowledgement", f"Required acknowledgement not supplied: {FREEZE_ACK}")

    return items


def create_freeze_items(doc, items):
    for item in items:
        row = frappe.new_doc("NDIS Controlled Production Batch Smoke Evidence Freeze Item")
        row.evidence_freeze = doc.name
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
def run_controlled_production_batch_smoke_evidence_freeze(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_controlled_production_batch_smoke_evidence_freeze")

    rollback = latest_rollback_run()
    config = config_state()
    guard_before = guardrails()
    ack_ok = acknowledgement == FREEZE_ACK

    issues = validate_evidence_chain(rollback, guard_before)
    items = build_items(rollback, config, guard_before, issues, ack_ok)

    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    allowed = int(ack_ok and item_summary["blocker_count"] == 0 and rollback is not None)

    pe_gl_count, pe_gl_net = pe_gl_count_net(rollback.payment_entry) if rollback and rollback.payment_entry else (0, 0)

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Frozen" if allowed else "Needs Review",
        "freeze_status": "Ready For Controlled Production Policy Review" if allowed else "Needs Review",
        "evidence_freeze_allowed": allowed,
        "ready_for_next_phase": allowed,
        "production_batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "rollback_run": rollback.name if rollback else None,
        "smoke_run": rollback.smoke_run if rollback else None,
        "activation_gate": rollback.activation_gate if rollback else None,
        "adapter_run": rollback.adapter_run if rollback else None,
        "preview": rollback.preview if rollback else None,
        "design_gate": rollback.design_gate if rollback else None,
        "phase7h_freeze": rollback.phase7h_freeze if rollback else None,
        "source_run": rollback.source_run if rollback else None,
        "company": rollback.company if rollback else None,
        "customer": rollback.customer if rollback else None,
        "payment_entry": rollback.payment_entry if rollback else None,
        "rollback_completed": int(rollback.rollback_completed or 0) if rollback else 0,
        "controlled_payment_entry_cancelled": int(rollback.controlled_payment_entry_cancelled or 0) if rollback else 0,
        "payment_entry_docstatus_after_rollback": int(rollback.payment_entry_docstatus_after or 0) if rollback else 0,
        "payment_entry_amount": flt(rollback.payment_entry_amount or 0) if rollback else 0,
        "invoice_count": int(rollback.invoice_count or 0) if rollback else 0,
        "invoice_outstanding_after_rollback_total": flt(rollback.invoice_outstanding_after_rollback_total or 0) if rollback else 0,
        "payment_entry_gl_count_after_rollback": pe_gl_count,
        "payment_entry_gl_net_after_rollback": pe_gl_net,
        "submitted_phase8e_smoke_pe_count": guard_before["submitted_phase8e_smoke_pe_count"],
        "cancelled_phase8e_smoke_pe_count": guard_before["cancelled_phase8e_smoke_pe_count"],
        "freeze_score": score,
        **item_summary,
        "items": items,
        "guardrails_before": guard_before,
        "guardrails_after": guardrails(),
        "config": config,
        "required_acknowledgement": FREEZE_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 8G freezes Phase 8A through 8F evidence. It creates no accounting movement.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["freeze_status"] = "Needs Review"
        result["evidence_freeze_allowed"] = 0
        result["ready_for_next_phase"] = 0
        return result

    doc = frappe.new_doc("NDIS Controlled Production Batch Smoke Evidence Freeze")
    doc.freeze_id = make_freeze_id()
    doc.status = result["status"]
    doc.freeze_status = result["freeze_status"]
    doc.evidence_freeze_allowed = allowed
    doc.ready_for_next_phase = allowed
    doc.production_batch_posting_allowed = 0
    doc.real_posting_allowed = 0

    for fieldname in [
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
        "freeze_score",
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

    doc.required_acknowledgement = FREEZE_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    create_freeze_items(doc, items)

    guard_after = guardrails()

    frappe.db.set_value(
        "NDIS Controlled Production Batch Smoke Evidence Freeze",
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
    result["evidence_freeze"] = doc.name
    result["freeze_id"] = doc.freeze_id
    result["guardrails_after"] = guard_after

    return result


@frappe.whitelist()
def cancel_controlled_production_batch_smoke_evidence_freeze(evidence_freeze, reason=None):
    assert_action("cancel_controlled_production_batch_smoke_evidence_freeze")

    if not frappe.db.exists("NDIS Controlled Production Batch Smoke Evidence Freeze", evidence_freeze):
        frappe.throw(_("Evidence freeze not found: {0}").format(evidence_freeze))

    doc = frappe.get_doc("NDIS Controlled Production Batch Smoke Evidence Freeze", evidence_freeze)

    if doc.status == "Cancelled":
        return {"evidence_freeze": evidence_freeze, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.evidence_freeze_allowed or 0):
        frappe.throw(_("Cannot cancel a frozen evidence record. Create a superseding freeze instead."))

    frappe.db.set_value(
        "NDIS Controlled Production Batch Smoke Evidence Freeze",
        evidence_freeze,
        {
            "status": "Cancelled",
            "freeze_status": "Cancelled",
            "evidence_freeze_allowed": 0,
            "ready_for_next_phase": 0,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 8G evidence freeze audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        """
        UPDATE `tabNDIS Controlled Production Batch Smoke Evidence Freeze Item`
        SET status = 'Cancelled'
        WHERE evidence_freeze = %(evidence_freeze)s
        """,
        {"evidence_freeze": evidence_freeze},
    )

    frappe.db.commit()

    return {
        "evidence_freeze": evidence_freeze,
        "status": "Cancelled",
        "note": "Evidence freeze audit record cancelled only. No accounting movement occurred.",
    }


@frappe.whitelist()
def quick_controlled_production_batch_smoke_evidence_freeze_summary(limit=20):
    freezes = frappe.get_all(
        "NDIS Controlled Production Batch Smoke Evidence Freeze",
        fields=[
            "name",
            "freeze_id",
            "status",
            "freeze_status",
            "evidence_freeze_allowed",
            "ready_for_next_phase",
            "production_batch_posting_allowed",
            "real_posting_allowed",
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
            "freeze_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    items = frappe.get_all(
        "NDIS Controlled Production Batch Smoke Evidence Freeze Item",
        fields=[
            "name",
            "evidence_freeze",
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
        "freezes": freezes,
        "items": items,
        "required_acknowledgement": FREEZE_ACK,
        "guardrails": guardrails(),
        "config": config_state(),
        "note": "Phase 8G evidence freeze summary. Read-only freeze; no accounting movement.",
    }


def execute_freeze_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("status"):
        conditions.append("f.status = %(status)s")
        params["status"] = filters.get("status")

    columns = freeze_columns()

    data = frappe.db.sql(
        f"""
        SELECT
            f.name AS evidence_freeze,
            f.freeze_id,
            f.status,
            f.freeze_status,
            f.evidence_freeze_allowed,
            f.ready_for_next_phase,
            f.production_batch_posting_allowed,
            f.real_posting_allowed,
            f.rollback_run,
            f.smoke_run,
            f.payment_entry,
            f.payment_entry_docstatus_after_rollback,
            f.payment_entry_amount,
            f.invoice_count,
            f.invoice_outstanding_after_rollback_total,
            f.payment_entry_gl_count_after_rollback,
            f.payment_entry_gl_net_after_rollback,
            f.submitted_phase8e_smoke_pe_count,
            f.cancelled_phase8e_smoke_pe_count,
            f.freeze_score,
            f.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Controlled Production Batch Smoke Evidence Freeze` f
        {build_where(conditions)}
        ORDER BY f.creation DESC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.freeze_id for row in data[:20]],
            "datasets": [
                {"name": "Frozen", "values": [int(row.evidence_freeze_allowed or 0) for row in data[:20]]},
                {"name": "Ready Next", "values": [int(row.ready_for_next_phase or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Freezes"), "datatype": "Int"},
        {"value": sum(int(row.evidence_freeze_allowed or 0) for row in data), "indicator": "Green", "label": _("Frozen"), "datatype": "Int"},
        {"value": sum(flt(row.payment_entry_amount or 0) for row in data), "indicator": "Blue", "label": _("Frozen PE Amount"), "datatype": "Currency", "currency": currency()},
        {"value": sum(int(row.ready_for_next_phase or 0) for row in data), "indicator": "Green", "label": _("Ready Next Phase"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def freeze_columns():
    return [
        {"fieldname": "evidence_freeze", "label": _("Evidence Freeze"), "fieldtype": "Link", "options": "NDIS Controlled Production Batch Smoke Evidence Freeze", "width": 220},
        {"fieldname": "freeze_id", "label": _("Freeze ID"), "fieldtype": "Data", "width": 410},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "freeze_status", "label": _("Freeze Status"), "fieldtype": "Data", "width": 320},
        {"fieldname": "ready_for_next_phase", "label": _("Ready Next"), "fieldtype": "Check", "width": 110},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 170},
        {"fieldname": "payment_entry_docstatus_after_rollback", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_amount", "label": _("PE Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "invoice_outstanding_after_rollback_total", "label": _("Outstanding Restored"), "fieldtype": "Currency", "options": "currency", "width": 160},
        {"fieldname": "payment_entry_gl_count_after_rollback", "label": _("PE GL Rows"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_net_after_rollback", "label": _("PE GL Net"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "submitted_phase8e_smoke_pe_count", "label": _("Submitted Smoke PE"), "fieldtype": "Int", "width": 140},
        {"fieldname": "cancelled_phase8e_smoke_pe_count", "label": _("Cancelled Smoke PE"), "fieldtype": "Int", "width": 140},
        {"fieldname": "freeze_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_exception_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    if filters.get("evidence_freeze"):
        conditions.append("i.evidence_freeze = %(evidence_freeze)s")
        params["evidence_freeze"] = filters.get("evidence_freeze")

    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": "NDIS Controlled Production Batch Smoke Evidence Freeze Item", "width": 220},
        {"fieldname": "evidence_freeze", "label": _("Evidence Freeze"), "fieldtype": "Link", "options": "NDIS Controlled Production Batch Smoke Evidence Freeze", "width": 220},
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
            i.evidence_freeze,
            i.status,
            i.severity,
            i.category,
            i.check_label,
            i.detail,
            i.source_doctype,
            i.source_name,
            i.checked_on
        FROM `tabNDIS Controlled Production Batch Smoke Evidence Freeze Item` i
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
    columns, data, message, chart, summary = execute_freeze_report(filters)

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
