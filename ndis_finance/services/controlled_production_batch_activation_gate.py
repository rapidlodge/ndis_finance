import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


ACTIVATION_ACK = "I_CONFIRM_PHASE8D_CONTROLLED_PRODUCTION_BATCH_ACTIVATION_GATE_NO_POSTING"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
ADAPTER_DOCTYPE = "NDIS Controlled Production Batch Adapter Run"
GATE_DOCTYPE = "NDIS Controlled Production Batch Activation Gate"
ITEM_DOCTYPE = "NDIS Controlled Production Batch Activation Gate Item"


def make_activation_gate_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-CTRL-PROD-BATCH-ACT-GATE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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
        "production_batch_enabled_policy_count": count_dt(POLICY_DOCTYPE, {"production_batch_enabled": 1}),
        "live_posting_allowed_policy_count": count_dt(POLICY_DOCTYPE, {"live_posting_allowed": 1}),
    }


def latest_adapter_run():
    rows = frappe.get_all(
        ADAPTER_DOCTYPE,
        filters={
            "status": "Hard Blocked",
            "adapter_approved_for_activation_gate": 1,
            "ready_for_activation_gate": 1,
            "direct_live_creation_blocked": 1,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
        },
        fields=[
            "name",
            "adapter_run_id",
            "preview",
            "design_gate",
            "phase7h_freeze",
            "source_run",
            "company",
            "customer",
            "bank_account",
            "receivable_account",
            "max_batch_lines",
            "max_batch_amount",
            "source_preview_line_count",
            "eligible_preview_line_count",
            "blocked_preview_line_count",
            "would_create_payment_entry_count",
            "would_create_payment_entry_amount",
            "would_create_reference_count",
            "hard_blocked_line_count",
            "validation_blocked_line_count",
            "direct_live_creation_blocked",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return frappe._dict(rows[0]) if rows else None


def existing_activation_for_adapter(adapter_run):
    rows = frappe.get_all(
        GATE_DOCTYPE,
        filters={
            "adapter_run": adapter_run,
            "status": "Activation Allowed",
            "activation_allowed_for_controlled_smoke": 1,
        },
        fields=["name", "activation_gate_id"],
        limit=1,
    )
    return rows[0] if rows else None


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


def evaluate_activation(adapter, config, guard, ack_ok):
    items = []
    if not adapter:
        add_item(items, "Blocker", "Critical", "Adapter Evidence", "adapter_exists", "Phase 8C adapter exists", "No approved Phase 8C hard-block adapter found.")
        return items

    duplicate = existing_activation_for_adapter(adapter.name)
    if duplicate:
        add_item(items, "Blocker", "Critical", "Duplicate", "duplicate_activation", "Duplicate activation gate", f"Approved activation already exists: {duplicate.activation_gate_id}.")
    else:
        add_item(items, "Pass", "Low", "Duplicate", "duplicate_activation", "Duplicate activation gate", "No approved activation gate exists for this adapter run.")

    add_item(items, "Pass", "Low", "Adapter Evidence", "adapter_exists", "Phase 8C adapter exists", f"Adapter run found: {adapter.adapter_run_id}.", ADAPTER_DOCTYPE, adapter.name)

    if int(adapter.direct_live_creation_blocked or 0):
        add_item(items, "Pass", "Low", "Adapter Safety", "direct_live_creation_blocked", "Direct live creation blocked", "Adapter hard-block proof is present.")
    else:
        add_item(items, "Blocker", "Critical", "Adapter Safety", "direct_live_creation_blocked", "Direct live creation blocked", "Adapter did not prove direct live creation block.")

    if int(adapter.would_create_payment_entry_count or 0) == 1 and flt(adapter.would_create_payment_entry_amount or 0) > 0:
        add_item(items, "Pass", "Low", "Adapter Evidence", "would_create_pe", "Would-create PE evidence", f"Would create {adapter.would_create_payment_entry_count} PE for {flt(adapter.would_create_payment_entry_amount):.2f}.")
    else:
        add_item(items, "Blocker", "Critical", "Adapter Evidence", "would_create_pe", "Would-create PE evidence", "Would-create PE evidence is missing.")

    if int(adapter.would_create_reference_count or 0) == int(adapter.hard_blocked_line_count or 0) and int(adapter.would_create_reference_count or 0) > 0:
        add_item(items, "Pass", "Low", "Adapter Evidence", "would_create_refs", "Would-create references", f"{adapter.would_create_reference_count} would-create references proved.")
    else:
        add_item(items, "Blocker", "Critical", "Adapter Evidence", "would_create_refs", "Would-create references", "Would-create reference evidence is incomplete.")

    if flt(adapter.would_create_payment_entry_amount or 0) <= flt(adapter.max_batch_amount or 0) and int(adapter.hard_blocked_line_count or 0) <= int(adapter.max_batch_lines or 0):
        add_item(items, "Pass", "Low", "Cap", "batch_cap", "Batch cap", f"Would-create result is within cap: {adapter.hard_blocked_line_count} lines / {flt(adapter.would_create_payment_entry_amount):.2f}.")
    else:
        add_item(items, "Blocker", "Critical", "Cap", "batch_cap", "Batch cap", "Would-create evidence exceeds controlled cap.")

    if int(adapter.actual_payment_entry_created_count or 0) == 0 and int(adapter.actual_gl_created_count or 0) == 0:
        add_item(items, "Pass", "Low", "No Movement", "adapter_no_movement", "Adapter created no PE/GL", "Adapter actual PE and GL counts are zero.")
    else:
        add_item(items, "Blocker", "Critical", "No Movement", "adapter_no_movement", "Adapter created no PE/GL", "Adapter movement counters are not zero.")

    add_item(items, "Blocker" if config["production_mode"] else "Pass", "Critical" if config["production_mode"] else "Low", "Site Config", "production_mode", "Production mode", "Production mode is enabled." if config["production_mode"] else "Production mode remains disabled.")
    add_item(items, "Blocker" if config["live_pe_enabled"] else "Pass", "Critical" if config["live_pe_enabled"] else "Low", "Site Config", "live_pe_enabled", "Live PE posting config", "Live PE posting config is enabled." if config["live_pe_enabled"] else "Live PE posting config remains disabled.")

    if guard["production_batch_enabled_policy_count"] == 0 and guard["live_posting_allowed_policy_count"] == 0:
        add_item(items, "Pass", "Low", "Policy Safety", "live_policies_zero", "Live policies", "No controlled production live-enabled policies.")
    else:
        add_item(items, "Blocker", "Critical", "Policy Safety", "live_policies_zero", "Live policies", "Live-enabled controlled production policy found.")

    add_item(items, "Pass" if guard["submitted_journal_entry_count_today"] == 0 else "Blocker", "Low" if guard["submitted_journal_entry_count_today"] == 0 else "Critical", "Movement Guardrail", "je_zero", "Submitted JE today", "Zero." if guard["submitted_journal_entry_count_today"] == 0 else str(guard["submitted_journal_entry_count_today"]))
    add_item(items, "Pass" if guard["purchase_invoice_count_today"] == 0 else "Blocker", "Low" if guard["purchase_invoice_count_today"] == 0 else "Critical", "Movement Guardrail", "pi_zero", "Purchase Invoice today", "Zero." if guard["purchase_invoice_count_today"] == 0 else str(guard["purchase_invoice_count_today"]))
    add_item(items, "Pass" if ack_ok else "Warning", "Low" if ack_ok else "Medium", "Acknowledgement", "activation_ack", "Activation acknowledgement", "Exact acknowledgement supplied." if ack_ok else f"Required acknowledgement not supplied: {ACTIVATION_ACK}")
    return items


def create_activation_items(doc, items):
    for item in items:
        row = frappe.new_doc(ITEM_DOCTYPE)
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
def run_controlled_production_batch_activation_gate(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_controlled_production_batch_activation_gate")
    adapter = latest_adapter_run()
    config = config_state()
    guard_before = guardrails()
    ack_ok = acknowledgement == ACTIVATION_ACK
    items = evaluate_activation(adapter, config, guard_before, ack_ok)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    allowed = int(ack_ok and item_summary["blocker_count"] == 0 and bool(adapter))

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Activation Allowed" if allowed else "Needs Review",
        "activation_status": "Ready For Single Controlled Production Batch Smoke" if allowed else "Needs Review",
        "activation_allowed_for_controlled_smoke": allowed,
        "ready_for_controlled_batch_smoke": allowed,
        "production_batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "adapter_run": adapter.name if adapter else None,
        "preview": adapter.preview if adapter else None,
        "design_gate": adapter.design_gate if adapter else None,
        "phase7h_freeze": adapter.phase7h_freeze if adapter else None,
        "source_run": adapter.source_run if adapter else None,
        "company": adapter.company if adapter else None,
        "customer": adapter.customer if adapter else None,
        "bank_account": adapter.bank_account if adapter else None,
        "receivable_account": adapter.receivable_account if adapter else None,
        "max_batch_lines": int(adapter.max_batch_lines or 0) if adapter else 0,
        "max_batch_amount": flt(adapter.max_batch_amount or 0) if adapter else 0,
        "adapter_direct_live_creation_blocked": int(adapter.direct_live_creation_blocked or 0) if adapter else 0,
        "adapter_hard_blocked": 1 if adapter else 0,
        "source_preview_line_count": int(adapter.source_preview_line_count or 0) if adapter else 0,
        "eligible_preview_line_count": int(adapter.eligible_preview_line_count or 0) if adapter else 0,
        "would_create_payment_entry_count": int(adapter.would_create_payment_entry_count or 0) if adapter else 0,
        "would_create_payment_entry_amount": flt(adapter.would_create_payment_entry_amount or 0) if adapter else 0,
        "would_create_reference_count": int(adapter.would_create_reference_count or 0) if adapter else 0,
        "hard_blocked_line_count": int(adapter.hard_blocked_line_count or 0) if adapter else 0,
        "validation_blocked_line_count": int(adapter.validation_blocked_line_count or 0) if adapter else 0,
        "actual_payment_entry_created_count": 0,
        "actual_gl_created_count": 0,
        "activation_score": score,
        **item_summary,
        "items": items,
        "guardrails_before": guard_before,
        "guardrails_after": guardrails(),
        "config": config,
        "required_acknowledgement": ACTIVATION_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 8D is activation-gate only. It creates no Payment Entry, GL Entry, Journal Entry, Purchase Invoice, or live policy.",
    }
    if int(dry_run or 0):
        return result

    doc = frappe.new_doc(GATE_DOCTYPE)
    doc.activation_gate_id = make_activation_gate_id()
    for fieldname in [
        "status",
        "activation_status",
        "activation_allowed_for_controlled_smoke",
        "ready_for_controlled_batch_smoke",
        "production_batch_posting_allowed",
        "real_posting_allowed",
        "adapter_run",
        "preview",
        "design_gate",
        "phase7h_freeze",
        "source_run",
        "company",
        "customer",
        "bank_account",
        "receivable_account",
        "max_batch_lines",
        "max_batch_amount",
        "adapter_direct_live_creation_blocked",
        "adapter_hard_blocked",
        "source_preview_line_count",
        "eligible_preview_line_count",
        "would_create_payment_entry_count",
        "would_create_payment_entry_amount",
        "would_create_reference_count",
        "hard_blocked_line_count",
        "validation_blocked_line_count",
        "actual_payment_entry_created_count",
        "actual_gl_created_count",
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
    doc.payment_entry_count_before = guard_before["payment_entry_count"]
    doc.payment_entry_count_after = guardrails()["payment_entry_count"]
    doc.payment_entry_gl_count_before = guard_before["payment_entry_gl_count"]
    doc.payment_entry_gl_count_after = guardrails()["payment_entry_gl_count"]
    doc.submitted_journal_entry_count_today = guard_before["submitted_journal_entry_count_today"]
    doc.purchase_invoice_count_today = guard_before["purchase_invoice_count_today"]
    doc.production_batch_enabled_policy_count = guard_before["production_batch_enabled_policy_count"]
    doc.live_posting_allowed_policy_count = guard_before["live_posting_allowed_policy_count"]
    doc.required_acknowledgement = ACTIVATION_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    create_activation_items(doc, items)
    guard_after = guardrails()
    frappe.db.set_value(
        GATE_DOCTYPE,
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
def cancel_controlled_production_batch_activation_gate(activation_gate, reason=None):
    assert_action("cancel_controlled_production_batch_activation_gate")
    if not frappe.db.exists(GATE_DOCTYPE, activation_gate):
        frappe.throw(_("Activation gate not found: {0}").format(activation_gate))
    doc = frappe.get_doc(GATE_DOCTYPE, activation_gate)
    if doc.status == "Cancelled":
        return {"activation_gate": activation_gate, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.activation_allowed_for_controlled_smoke or 0):
        frappe.throw(_("Cannot cancel an approved activation gate. Create a superseding activation gate instead."))
    frappe.db.set_value(
        GATE_DOCTYPE,
        activation_gate,
        {
            "status": "Cancelled",
            "activation_status": "Cancelled",
            "activation_allowed_for_controlled_smoke": 0,
            "ready_for_controlled_batch_smoke": 0,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 8D activation gate audit cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{ITEM_DOCTYPE}` SET status = 'Cancelled' WHERE activation_gate = %(activation_gate)s", {"activation_gate": activation_gate})
    frappe.db.commit()
    return {"activation_gate": activation_gate, "status": "Cancelled", "note": "Activation gate audit record cancelled only. No accounting movement occurred."}


@frappe.whitelist()
def quick_controlled_production_batch_activation_summary(limit=20):
    gates = frappe.get_all(
        GATE_DOCTYPE,
        fields=[
            "name",
            "activation_gate_id",
            "status",
            "activation_status",
            "activation_allowed_for_controlled_smoke",
            "ready_for_controlled_batch_smoke",
            "production_batch_posting_allowed",
            "real_posting_allowed",
            "adapter_run",
            "preview",
            "design_gate",
            "company",
            "customer",
            "would_create_payment_entry_count",
            "would_create_payment_entry_amount",
            "would_create_reference_count",
            "hard_blocked_line_count",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
            "activation_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(
        ITEM_DOCTYPE,
        fields=["name", "activation_gate", "status", "severity", "category", "check_label", "detail", "source_doctype", "source_name"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "gates": gates,
        "items": items,
        "required_acknowledgement": ACTIVATION_ACK,
        "guardrails": guardrails(),
        "config": config_state(),
        "note": "Phase 8D activation summary. Activation-gate only; no accounting movement.",
    }


def execute_activation_gate_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("g.status = %(status)s")
        params["status"] = filters.get("status")
    if filters.get("from_date"):
        conditions.append("DATE(g.checked_on) >= %(from_date)s")
        params["from_date"] = filters.get("from_date")
    if filters.get("to_date"):
        conditions.append("DATE(g.checked_on) <= %(to_date)s")
        params["to_date"] = filters.get("to_date")

    data = frappe.db.sql(
        f"""
        SELECT
            g.name AS activation_gate,
            g.activation_gate_id,
            g.status,
            g.activation_status,
            g.activation_allowed_for_controlled_smoke,
            g.ready_for_controlled_batch_smoke,
            g.production_batch_posting_allowed,
            g.real_posting_allowed,
            g.adapter_run,
            g.preview,
            g.design_gate,
            g.company,
            g.source_preview_line_count,
            g.eligible_preview_line_count,
            g.would_create_payment_entry_count,
            g.would_create_payment_entry_amount,
            g.would_create_reference_count,
            g.hard_blocked_line_count,
            g.actual_payment_entry_created_count,
            g.actual_gl_created_count,
            g.activation_score,
            g.checked_on,
            %(currency)s AS currency
        FROM `tab{GATE_DOCTYPE}` g
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
                {"name": "Ready Smoke", "values": [int(row.ready_for_controlled_batch_smoke or 0) for row in data[:20]]},
                {"name": "Actual PE", "values": [int(row.actual_payment_entry_created_count or 0) for row in data[:20]]},
                {"name": "Actual GL", "values": [int(row.actual_gl_created_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Activation Gates"), "datatype": "Int"},
        {"value": sum(int(row.ready_for_controlled_batch_smoke or 0) for row in data), "indicator": "Green", "label": _("Ready Smoke"), "datatype": "Int"},
        {"value": sum(flt(row.would_create_payment_entry_amount or 0) for row in data), "indicator": "Blue", "label": _("Would Create Amount"), "datatype": "Currency", "currency": currency()},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PE"), "datatype": "Int"},
    ]
    return activation_columns(), data, None, chart, summary


def activation_columns():
    return [
        {"fieldname": "activation_gate", "label": _("Activation Gate"), "fieldtype": "Link", "options": GATE_DOCTYPE, "width": 220},
        {"fieldname": "activation_gate_id", "label": _("Activation Gate ID"), "fieldtype": "Data", "width": 400},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 130},
        {"fieldname": "activation_status", "label": _("Activation Status"), "fieldtype": "Data", "width": 320},
        {"fieldname": "ready_for_controlled_batch_smoke", "label": _("Ready Smoke"), "fieldtype": "Check", "width": 120},
        {"fieldname": "adapter_run", "label": _("Adapter Run"), "fieldtype": "Link", "options": ADAPTER_DOCTYPE, "width": 220},
        {"fieldname": "would_create_payment_entry_count", "label": _("Would PE"), "fieldtype": "Int", "width": 100},
        {"fieldname": "would_create_payment_entry_amount", "label": _("Would Amount"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "would_create_reference_count", "label": _("Would Refs"), "fieldtype": "Int", "width": 110},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE"), "fieldtype": "Int", "width": 100},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL"), "fieldtype": "Int", "width": 100},
        {"fieldname": "activation_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_activation_exception_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("activation_gate"):
        conditions.append("i.activation_gate = %(activation_gate)s")
        params["activation_gate"] = filters.get("activation_gate")
    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")
    if filters.get("severity"):
        conditions.append("i.severity = %(severity)s")
        params["severity"] = filters.get("severity")
    if filters.get("category"):
        conditions.append("i.category = %(category)s")
        params["category"] = filters.get("category")

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": ITEM_DOCTYPE, "width": 220},
        {"fieldname": "activation_gate", "label": _("Activation Gate"), "fieldtype": "Link", "options": GATE_DOCTYPE, "width": 220},
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
            i.activation_gate,
            i.status,
            i.severity,
            i.category,
            i.check_label,
            i.detail,
            i.source_doctype,
            i.source_name,
            i.checked_on
        FROM `tab{ITEM_DOCTYPE}` i
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
        chart_map[row.status or "Info"] = chart_map.get(row.status or "Info", 0) + 1
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Items", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Items"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Pass"]), "indicator": "Green", "label": _("Pass"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Warning"]), "indicator": "Orange", "label": _("Warnings"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Blocker"]), "indicator": "Red", "label": _("Blockers"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_activation_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_activation_gate_report(filters)
    guard = guardrails()
    summary.append({"value": guard["payment_entry_count"], "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"})
    summary.append({"value": guard["payment_entry_gl_count"], "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"})
    summary.append({"value": guard["submitted_journal_entry_count_today"], "indicator": "Red", "label": _("Submitted JE Today"), "datatype": "Int"})
    summary.append({"value": guard["purchase_invoice_count_today"], "indicator": "Red", "label": _("Purchase Invoice Today"), "datatype": "Int"})
    summary.append({"value": guard["production_batch_enabled_policy_count"], "indicator": "Red", "label": _("Production Batch Enabled Policies"), "datatype": "Int"})
    summary.append({"value": guard["live_posting_allowed_policy_count"], "indicator": "Red", "label": _("Live Posting Allowed Policies"), "datatype": "Int"})
    return columns, data, message, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
