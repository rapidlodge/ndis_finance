import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


ACTIVATION_ACK = "I_CONFIRM_PHASE7D_REAL_REMITTANCE_BATCH_ACTIVATION_GATE_NO_POSTING"
GATE_DOCTYPE = "NDIS Real Remittance Batch Activation Gate"
ITEM_DOCTYPE = "NDIS Real Remittance Batch Activation Gate Item"
ADAPTER_DOCTYPE = "NDIS Real Remittance Batch Adapter Run"


def make_activation_gate_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-REAL-REMITTANCE-BATCH-ACT-GATE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def sales_invoice_today_guardrail_count():
    if frappe.db.has_column("Sales Invoice", "custom_ndis_real_remittance_pe_harness_invoice"):
        return frappe.db.sql(
            """
            SELECT COUNT(*)
            FROM `tabSales Invoice`
            WHERE creation >= %(today)s
            AND IFNULL(custom_ndis_real_remittance_pe_harness_invoice, 0) = 0
            """,
            {"today": today()},
        )[0][0]
    return count_dt("Sales Invoice", {"creation": [">=", today()]})


def guardrails():
    return {
        "payment_entry_count": count_dt("Payment Entry"),
        "payment_entry_gl_count": count_dt("GL Entry", {"voucher_type": "Payment Entry"}),
        "submitted_journal_entry_count_today": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}),
        "sales_invoice_count_today": sales_invoice_today_guardrail_count(),
        "purchase_invoice_count_today": count_dt("Purchase Invoice", {"creation": [">=", today()]}),
        "batch_live_enabled_policy_count": count_dt("NDIS Real Remittance Batch Posting Policy", {"batch_live_enabled": 1}),
        "production_live_enabled_policy_count": count_dt("NDIS PE Production Posting Policy", {"production_posting_enabled": 1}),
    }


def meta_has(doctype, fieldname):
    if not frappe.db.exists("DocType", doctype):
        return False
    return bool(frappe.get_meta(doctype).has_field(fieldname))


def existing_fields(doctype, fields):
    return [field for field in fields if field == "name" or meta_has(doctype, field)]


def latest_adapter_run():
    fields = existing_fields(
        ADAPTER_DOCTYPE,
        [
            "name",
            "adapter_run_id",
            "adapter_status",
            "adapter_score",
            "adapter_approved_for_activation_gate",
            "ready_for_activation_gate",
            "direct_live_creation_blocked",
            "batch_posting_allowed",
            "real_posting_allowed",
            "batch_preview",
            "design_gate",
            "evidence_freeze",
            "company",
            "bank_account",
            "receivable_account",
            "max_batch_lines",
            "max_batch_amount",
            "source_line_count",
            "eligible_preview_line_count",
            "hard_blocked_line_count",
            "would_create_payment_entry_count",
            "would_create_payment_entry_amount",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
        ],
    )
    if "name" not in fields:
        fields.insert(0, "name")

    rows = frappe.get_all(
        ADAPTER_DOCTYPE,
        filters={
            "status": "Hard Blocked",
            "adapter_approved_for_activation_gate": 1,
            "ready_for_activation_gate": 1,
            "direct_live_creation_blocked": 1,
            "batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
        },
        fields=fields,
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    if not rows:
        return None

    row = frappe._dict(rows[0])
    for fieldname in [
        "adapter_run_id",
        "adapter_status",
        "adapter_score",
        "adapter_approved_for_activation_gate",
        "ready_for_activation_gate",
        "direct_live_creation_blocked",
        "batch_posting_allowed",
        "real_posting_allowed",
        "batch_preview",
        "design_gate",
        "evidence_freeze",
        "company",
        "bank_account",
        "receivable_account",
        "max_batch_lines",
        "max_batch_amount",
        "source_line_count",
        "eligible_preview_line_count",
        "hard_blocked_line_count",
        "would_create_payment_entry_count",
        "would_create_payment_entry_amount",
        "actual_payment_entry_created_count",
        "actual_gl_created_count",
    ]:
        row.setdefault(fieldname, None)
    return row


def direct_hard_block_still_active():
    try:
        from ndis_finance.services.real_remittance_batch_adapter import create_real_remittance_batch_payment_entries

        create_real_remittance_batch_payment_entries()
    except Exception:
        return 1
    return 0


def add_item(items, status, severity, category, check_key, check_label, detail, recommendation=None, source_doctype=None, source_name=None):
    items.append(
        {
            "status": status,
            "severity": severity,
            "category": category,
            "check_key": check_key,
            "check_label": check_label,
            "detail": detail,
            "recommendation": recommendation,
            "source_doctype": source_doctype,
            "source_name": source_name,
        }
    )


def evaluate_config(items, config):
    if config["production_mode"]:
        add_item(items, "Blocker", "Critical", "Site Config", "production_mode", "Production mode", "Production mode is enabled.")
    else:
        add_item(items, "Pass", "Low", "Site Config", "production_mode", "Production mode", "Production mode remains disabled.")

    if config["live_pe_enabled"]:
        add_item(items, "Blocker", "Critical", "Site Config", "live_pe_enabled", "Live PE posting config", "Live Payment Entry posting config is enabled.")
    else:
        add_item(items, "Pass", "Low", "Site Config", "live_pe_enabled", "Live PE posting config", "Live Payment Entry posting remains disabled.")

    if config["sandbox_enabled"]:
        add_item(items, "Pass", "Low", "Site Config", "sandbox_enabled", "Sandbox config", "Sandbox config remains enabled.")
    else:
        add_item(items, "Warning", "Medium", "Site Config", "sandbox_enabled", "Sandbox config", "Sandbox config is not enabled.")


def evaluate_adapter(items, adapter):
    if not adapter:
        add_item(items, "Blocker", "Critical", "Phase 7C", "adapter_exists", "Phase 7C hard-block adapter", "No approved Phase 7C hard-block adapter run found.", "Complete Phase 7C first.")
        return

    add_item(items, "Pass", "Low", "Phase 7C", "adapter_exists", "Phase 7C hard-block adapter", f"Adapter run found: {adapter.adapter_run_id}.", None, ADAPTER_DOCTYPE, adapter.name)

    if int(adapter.direct_live_creation_blocked or 0) == 1:
        add_item(items, "Pass", "Low", "Hard Block", "direct_block", "Direct live creation blocked", "Adapter direct live creation path is blocked.")
    else:
        add_item(items, "Blocker", "Critical", "Hard Block", "direct_block", "Direct live creation blocked", "Adapter direct live creation path is not blocked.")

    if int(adapter.would_create_payment_entry_count or 0) >= 1 and flt(adapter.would_create_payment_entry_amount or 0) > 0:
        add_item(items, "Pass", "Low", "Source", "would_create", "Would-create source exists", f"Would-create PE count {adapter.would_create_payment_entry_count}, amount {flt(adapter.would_create_payment_entry_amount, 2)}.")
    else:
        add_item(items, "Blocker", "Critical", "Source", "would_create", "Would-create source exists", "No would-create batch line exists.")

    if int(adapter.actual_payment_entry_created_count or 0) == 0 and int(adapter.actual_gl_created_count or 0) == 0:
        add_item(items, "Pass", "Low", "Movement", "no_movement", "No adapter movement", "Adapter created no Payment Entry and no GL.")
    else:
        add_item(items, "Blocker", "Critical", "Movement", "no_movement", "No adapter movement", "Adapter shows actual accounting movement.")


def evaluate_guardrails(items, guard):
    guardrail_checks = [
        ("batch_live_enabled_policy_count", "Batch live policies"),
        ("production_live_enabled_policy_count", "Production PE live policies"),
        ("submitted_journal_entry_count_today", "Submitted JE today"),
        ("sales_invoice_count_today", "Non-harness Sales Invoice today"),
        ("purchase_invoice_count_today", "Purchase Invoice today"),
    ]
    for key, label in guardrail_checks:
        if guard[key] == 0:
            add_item(items, "Pass", "Low", "Guardrail", key, label, "Zero.")
        else:
            add_item(items, "Blocker", "Critical", "Guardrail", key, label, f"{guard[key]} record(s) found.")


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
        row = frappe.new_doc(ITEM_DOCTYPE)
        row.activation_gate = doc.name
        row.status = item["status"]
        row.severity = item["severity"]
        row.category = item["category"]
        row.check_key = item["check_key"]
        row.check_label = item["check_label"]
        row.detail = item["detail"]
        row.recommendation = item.get("recommendation")
        row.source_doctype = item.get("source_doctype")
        row.source_name = item.get("source_name")
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_real_remittance_batch_activation_gate(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_real_remittance_batch_activation_gate")

    config = config_state()
    guard_before = guardrails()
    adapter = latest_adapter_run()
    ack_ok = acknowledgement == ACTIVATION_ACK
    direct_blocked = direct_hard_block_still_active()

    items = []
    evaluate_config(items, config)
    evaluate_adapter(items, adapter)
    evaluate_guardrails(items, guard_before)

    if direct_blocked:
        add_item(items, "Pass", "Low", "Hard Block", "direct_block_retest", "Direct hard block retest", "Direct creation function still throws controlled block.")
    else:
        add_item(items, "Blocker", "Critical", "Hard Block", "direct_block_retest", "Direct hard block retest", "Direct creation function did not throw.")

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "activation_ack", "Activation acknowledgement", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "activation_ack", "Activation acknowledgement", f"Required acknowledgement not supplied. Required: {ACTIVATION_ACK}", "Provide exact acknowledgement to allow the next controlled batch smoke phase.")

    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    allowed = int(
        ack_ok
        and item_summary["blocker_count"] == 0
        and direct_blocked
        and adapter
        and int(adapter.would_create_payment_entry_count or 0) >= 1
        and flt(adapter.would_create_payment_entry_amount or 0) > 0
        and guard_before["batch_live_enabled_policy_count"] == 0
        and guard_before["production_live_enabled_policy_count"] == 0
    )

    if allowed:
        status = "Activation Allowed"
        activation_status = "Ready For Single Controlled Batch Smoke"
    elif adapter and int(adapter.would_create_payment_entry_count or 0) <= 0:
        status = "Source Pending"
        activation_status = "Structural Ready - Source Eligible Pending"
    else:
        status = "Blocked" if item_summary["blocker_count"] else "Needs Review"
        activation_status = "Blocked" if item_summary["blocker_count"] else "Needs Review"

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": status,
        "activation_status": activation_status,
        "activation_score": score,
        "activation_allowed_for_controlled_smoke": allowed,
        "ready_for_batch_smoke": allowed,
        "adapter_hard_block_verified": direct_blocked,
        "batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "adapter_run": adapter.name if adapter else None,
        "batch_preview": adapter.batch_preview if adapter else None,
        "design_gate": adapter.design_gate if adapter else None,
        "evidence_freeze": adapter.evidence_freeze if adapter else None,
        "company": adapter.company if adapter else None,
        "bank_account": adapter.bank_account if adapter else None,
        "receivable_account": adapter.receivable_account if adapter else None,
        "max_batch_lines": int(adapter.max_batch_lines or 0) if adapter else 0,
        "max_batch_amount": flt(adapter.max_batch_amount or 0) if adapter else 0,
        "source_line_count": int(adapter.source_line_count or 0) if adapter else 0,
        "eligible_preview_line_count": int(adapter.eligible_preview_line_count or 0) if adapter else 0,
        "hard_blocked_line_count": int(adapter.hard_blocked_line_count or 0) if adapter else 0,
        "would_create_payment_entry_count": int(adapter.would_create_payment_entry_count or 0) if adapter else 0,
        "would_create_payment_entry_amount": flt(adapter.would_create_payment_entry_amount or 0) if adapter else 0,
        "actual_payment_entry_created_count": 0,
        "actual_gl_created_count": 0,
        **item_summary,
        "items": items,
        "guardrails_before": guard_before,
        "guardrails_after": guardrails(),
        "config": config,
        "required_acknowledgement": ACTIVATION_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 7D is an activation gate only. It creates no Payment Entry or GL Entry and does not enable live posting.",
    }

    if int(dry_run or 0):
        return result

    doc = frappe.new_doc(GATE_DOCTYPE)
    doc.activation_gate_id = make_activation_gate_id()
    doc.status = status
    doc.activation_status = activation_status
    doc.activation_allowed_for_controlled_smoke = allowed
    doc.ready_for_batch_smoke = allowed
    doc.adapter_hard_block_verified = direct_blocked
    doc.batch_posting_allowed = 0
    doc.real_posting_allowed = 0

    for fieldname in [
        "adapter_run",
        "batch_preview",
        "design_gate",
        "evidence_freeze",
        "company",
        "bank_account",
        "receivable_account",
        "max_batch_lines",
        "max_batch_amount",
        "source_line_count",
        "eligible_preview_line_count",
        "hard_blocked_line_count",
        "would_create_payment_entry_count",
        "would_create_payment_entry_amount",
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

    doc.requires_single_controlled_smoke = 1
    doc.requires_rollback_after_smoke = 1
    doc.requires_freeze_after_rollback = 1
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
    doc.sales_invoice_count_today = guard_before["sales_invoice_count_today"]
    doc.purchase_invoice_count_today = guard_before["purchase_invoice_count_today"]
    doc.batch_live_enabled_policy_count = guard_before["batch_live_enabled_policy_count"]
    doc.production_live_enabled_policy_count = guard_before["production_live_enabled_policy_count"]
    doc.required_acknowledgement = ACTIVATION_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    create_items(doc, items)

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
def cancel_real_remittance_batch_activation_gate(activation_gate, reason=None):
    assert_action("cancel_real_remittance_batch_activation_gate")

    if not frappe.db.exists(GATE_DOCTYPE, activation_gate):
        frappe.throw(_("Activation gate not found: {0}").format(activation_gate))

    doc = frappe.get_doc(GATE_DOCTYPE, activation_gate)
    if doc.status == "Cancelled":
        return {"activation_gate": activation_gate, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.ready_for_batch_smoke or 0):
        frappe.throw(_("Cannot cancel an activation-allowed gate. Create a superseding gate instead."))

    frappe.db.set_value(
        GATE_DOCTYPE,
        activation_gate,
        {
            "status": "Cancelled",
            "activation_status": "Cancelled",
            "activation_allowed_for_controlled_smoke": 0,
            "ready_for_batch_smoke": 0,
            "batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 7D activation gate cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(
        f"""
        UPDATE `tab{ITEM_DOCTYPE}`
        SET status = 'Cancelled'
        WHERE activation_gate = %(activation_gate)s
        """,
        {"activation_gate": activation_gate},
    )
    frappe.db.commit()
    return {"activation_gate": activation_gate, "status": "Cancelled", "note": "Activation gate audit record cancelled only. No accounting movement occurred."}


@frappe.whitelist()
def quick_real_remittance_batch_activation_gate_summary(limit=20):
    gates = frappe.get_all(
        GATE_DOCTYPE,
        fields=[
            "name",
            "activation_gate_id",
            "status",
            "activation_status",
            "activation_score",
            "activation_allowed_for_controlled_smoke",
            "ready_for_batch_smoke",
            "adapter_hard_block_verified",
            "batch_posting_allowed",
            "real_posting_allowed",
            "adapter_run",
            "batch_preview",
            "company",
            "eligible_preview_line_count",
            "hard_blocked_line_count",
            "would_create_payment_entry_count",
            "would_create_payment_entry_amount",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(
        ITEM_DOCTYPE,
        fields=[
            "name",
            "activation_gate",
            "status",
            "severity",
            "category",
            "check_label",
            "detail",
            "recommendation",
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
        "note": "Phase 7D activation summary. No Payment Entry or GL Entry is created; posting remains disabled.",
    }


def activation_columns():
    return [
        {"fieldname": "activation_gate", "label": _("Activation Gate"), "fieldtype": "Link", "options": GATE_DOCTYPE, "width": 220},
        {"fieldname": "activation_gate_id", "label": _("Activation Gate ID"), "fieldtype": "Data", "width": 380},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 130},
        {"fieldname": "activation_status", "label": _("Activation Status"), "fieldtype": "Data", "width": 280},
        {"fieldname": "activation_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "ready_for_batch_smoke", "label": _("Ready Smoke"), "fieldtype": "Check", "width": 110},
        {"fieldname": "adapter_hard_block_verified", "label": _("Hard Block OK"), "fieldtype": "Check", "width": 120},
        {"fieldname": "batch_posting_allowed", "label": _("Batch Posting Allowed"), "fieldtype": "Check", "width": 160},
        {"fieldname": "real_posting_allowed", "label": _("Real Posting Allowed"), "fieldtype": "Check", "width": 150},
        {"fieldname": "would_create_payment_entry_count", "label": _("Would Create PE"), "fieldtype": "Int", "width": 130},
        {"fieldname": "would_create_payment_entry_amount", "label": _("Would Create Amount"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE"), "fieldtype": "Int", "width": 100},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL"), "fieldtype": "Int", "width": 100},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


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
            g.activation_score,
            g.ready_for_batch_smoke,
            g.adapter_hard_block_verified,
            g.batch_posting_allowed,
            g.real_posting_allowed,
            g.would_create_payment_entry_count,
            g.would_create_payment_entry_amount,
            g.actual_payment_entry_created_count,
            g.actual_gl_created_count,
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
                {"name": "Ready Smoke", "values": [int(row.ready_for_batch_smoke or 0) for row in data[:20]]},
                {"name": "Actual PE", "values": [int(row.actual_payment_entry_created_count or 0) for row in data[:20]]},
                {"name": "Actual GL", "values": [int(row.actual_gl_created_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Activation Gates"), "datatype": "Int"},
        {"value": sum(int(row.ready_for_batch_smoke or 0) for row in data), "indicator": "Green", "label": _("Ready For Batch Smoke"), "datatype": "Int"},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PE Created"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL Created"), "datatype": "Int"},
    ]
    return activation_columns(), data, None, chart, summary


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    for fieldname in ["activation_gate", "status", "severity", "category"]:
        if filters.get(fieldname):
            conditions.append(f"i.{fieldname} = %({fieldname})s")
            params[fieldname] = filters.get(fieldname)

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": ITEM_DOCTYPE, "width": 220},
        {"fieldname": "activation_gate", "label": _("Activation Gate"), "fieldtype": "Link", "options": GATE_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 180},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 320},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 520},
        {"fieldname": "recommendation", "label": _("Recommendation"), "fieldtype": "Small Text", "width": 420},
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
            i.recommendation,
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
    columns, data, message, chart, summary = execute_activation_gate_report(filters)
    summary.extend(
        [
            {"value": count_dt("Payment Entry"), "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"},
            {"value": count_dt("GL Entry", {"voucher_type": "Payment Entry"}), "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"},
            {"value": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}), "indicator": "Red", "label": _("Submitted JEs Today"), "datatype": "Int"},
            {"value": sales_invoice_today_guardrail_count(), "indicator": "Red", "label": _("Non-harness Sales Invoices Today"), "datatype": "Int"},
            {"value": count_dt("Purchase Invoice", {"creation": [">=", today()]}), "indicator": "Red", "label": _("Purchase Invoices Today"), "datatype": "Int"},
        ]
    )
    return columns, data, message, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
