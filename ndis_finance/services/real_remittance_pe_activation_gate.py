import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


GATE_DOCTYPE = "NDIS Real Remittance PE Activation Gate"
ITEM_DOCTYPE = "NDIS Real Remittance PE Activation Gate Item"
ADAPTER_DOCTYPE = "NDIS Real Remittance PE Adapter Run"
ACTIVATION_ACK = "I_CONFIRM_PHASE6D_REAL_REMITTANCE_PE_ACTIVATION_GATE_NO_POSTING"


def make_activation_gate_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-REAL-REMITTANCE-PE-ACT-GATE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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
        "live_enabled_policy_count": count_dt("NDIS PE Production Posting Policy", {"production_posting_enabled": 1}),
    }


def latest_adapter_run():
    rows = frappe.get_all(
        ADAPTER_DOCTYPE,
        filters={
            "status": "Hard Blocked",
            "adapter_approved_for_activation_gate": 1,
            "real_posting_allowed": 0,
            "direct_live_creation_blocked": 1,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
        },
        fields=[
            "name",
            "adapter_run_id",
            "adapter_status",
            "design_gate",
            "preview",
            "source_remittance_import",
            "company",
            "bank_account",
            "receivable_account",
            "batch_line_cap",
            "batch_amount_cap",
            "source_preview_line_count",
            "eligible_preview_line_count",
            "blocked_preview_line_count",
            "hard_blocked_line_count",
            "validation_blocked_line_count",
            "would_create_payment_entry_count",
            "would_create_payment_entry_amount",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
            "source_eligible_pending",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


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
        add_item(
            items,
            "Blocker",
            "Critical",
            "Adapter Evidence",
            "phase6c_adapter",
            "Approved Phase 6C adapter",
            "No approved Phase 6C hard-block adapter run found.",
            "Complete Phase 6C first.",
        )
        return
    add_item(
        items,
        "Pass",
        "Low",
        "Adapter Evidence",
        "phase6c_adapter",
        "Approved Phase 6C adapter",
        f"Approved hard-block adapter found: {adapter.adapter_run_id}.",
        None,
        ADAPTER_DOCTYPE,
        adapter.name,
    )
    if int(adapter.actual_payment_entry_created_count or 0) == 0:
        add_item(items, "Pass", "Low", "Adapter Evidence", "actual_pe_zero", "Actual Payment Entry created", "Zero.")
    else:
        add_item(items, "Blocker", "Critical", "Adapter Evidence", "actual_pe_zero", "Actual Payment Entry created", f"{adapter.actual_payment_entry_created_count} Payment Entry record(s) found.")
    if int(adapter.actual_gl_created_count or 0) == 0:
        add_item(items, "Pass", "Low", "Adapter Evidence", "actual_gl_zero", "Actual GL created", "Zero.")
    else:
        add_item(items, "Blocker", "Critical", "Adapter Evidence", "actual_gl_zero", "Actual GL created", f"{adapter.actual_gl_created_count} GL row(s) found.")
    if int(adapter.source_eligible_pending or 0):
        add_item(
            items,
            "Warning",
            "Medium",
            "Source Readiness",
            "source_eligible_pending",
            "Source eligible pending",
            "No eligible remittance line exists yet. Structural readiness is allowed, but real smoke cannot proceed.",
            "Create a controlled eligible remittance source harness or import a real matched Paid/Short Paid remittance.",
        )
    else:
        add_item(items, "Pass", "Low", "Source Readiness", "eligible_source", "Eligible source exists", f"{adapter.eligible_preview_line_count} eligible preview line(s) found.")
    if int(adapter.would_create_payment_entry_count or 0) > 0:
        add_item(items, "Pass", "Low", "Source Readiness", "would_create_pe", "Would-create PE count", f"{adapter.would_create_payment_entry_count} structurally eligible line(s) found.")
    else:
        add_item(items, "Info", "Low", "Source Readiness", "would_create_pe", "Would-create PE count", "Zero would-create Payment Entry lines in current source.")


def evaluate_guardrails(items, guard):
    checks = [
        ("live_enabled_policy_count", "Live-enabled policy count"),
        ("submitted_journal_entry_count_today", "Submitted Journal Entry today"),
        ("sales_invoice_count_today", "Sales Invoice today"),
        ("purchase_invoice_count_today", "Purchase Invoice today"),
    ]
    for key, label in checks:
        value = int(guard.get(key) or 0)
        if value:
            add_item(items, "Blocker", "Critical", "Guardrail", key, label, f"{value} record(s) found.")
        else:
            add_item(items, "Pass", "Low", "Guardrail", key, label, "Zero.")


def summarise_items(items):
    return {
        "blocker_count": len([i for i in items if i["status"] == "Blocker"]),
        "warning_count": len([i for i in items if i["status"] == "Warning"]),
        "pass_count": len([i for i in items if i["status"] == "Pass"]),
        "info_count": len([i for i in items if i["status"] == "Info"]),
        "item_count": len(items),
    }


def calculate_score(blockers, warnings):
    score = 100 - int(blockers or 0) * 25 - int(warnings or 0) * 5
    return max(0, round(score, 2))


def compute_activation_status(blockers, source_eligible_pending, ready_for_real_smoke):
    if blockers:
        return "Blocked"
    if ready_for_real_smoke:
        return "Ready For Single Real Smoke"
    if source_eligible_pending:
        return "Source Eligible Pending"
    return "Structural Ready Only"


def create_gate_items(doc, items):
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
def run_real_remittance_pe_activation_gate(adapter_run=None, dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_real_remittance_pe_activation_gate")
    if adapter_run:
        if not frappe.db.exists(ADAPTER_DOCTYPE, adapter_run):
            frappe.throw(_("Adapter run not found: {0}").format(adapter_run))
        adapter = frappe.get_doc(ADAPTER_DOCTYPE, adapter_run)
    else:
        latest = latest_adapter_run()
        adapter = frappe.get_doc(ADAPTER_DOCTYPE, latest.name) if latest else None

    config = config_state()
    guard_before = guardrails()
    items = []
    evaluate_config(items, config)
    evaluate_adapter(items, adapter)
    evaluate_guardrails(items, guard_before)

    ack_ok = acknowledgement == ACTIVATION_ACK
    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "activation_ack", "Activation acknowledgement", "Exact acknowledgement supplied.")
    elif int(dry_run or 0):
        add_item(items, "Info", "Low", "Acknowledgement", "activation_ack", "Activation acknowledgement", f"Required acknowledgement for evidence: {ACTIVATION_ACK}")
    else:
        add_item(
            items,
            "Warning",
            "Medium",
            "Acknowledgement",
            "activation_ack",
            "Activation acknowledgement",
            f"Required acknowledgement not supplied. Required: {ACTIVATION_ACK}",
            "Provide exact acknowledgement to create activation gate evidence.",
        )

    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    source_eligible_pending = int(getattr(adapter, "source_eligible_pending", 1) or 0) if adapter else 1
    would_create_count = int(getattr(adapter, "would_create_payment_entry_count", 0) or 0) if adapter else 0
    structural_ready_allowed = int(ack_ok and item_summary["blocker_count"] == 0)
    ready_for_real_smoke = int(structural_ready_allowed and not source_eligible_pending and would_create_count > 0)
    activation_status_text = compute_activation_status(
        item_summary["blocker_count"], source_eligible_pending, ready_for_real_smoke
    )

    if item_summary["blocker_count"]:
        status_text = "Blocked"
    elif ready_for_real_smoke:
        status_text = "Activation Allowed"
    elif structural_ready_allowed and source_eligible_pending:
        status_text = "Source Pending"
    else:
        status_text = "Needs Review"

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": status_text,
        "activation_status": activation_status_text,
        "activation_score": score,
        "structural_ready_allowed": structural_ready_allowed,
        "ready_for_real_smoke": ready_for_real_smoke,
        "real_posting_allowed": 0,
        "source_eligible_pending": source_eligible_pending,
        "adapter_run": adapter.name if adapter else None,
        "adapter_run_id": adapter.adapter_run_id if adapter else None,
        "preview": adapter.preview if adapter else None,
        "design_gate": adapter.design_gate if adapter else None,
        "source_remittance_import": adapter.source_remittance_import if adapter else None,
        "company": adapter.company if adapter else None,
        "bank_account": adapter.bank_account if adapter else None,
        "receivable_account": adapter.receivable_account if adapter else None,
        "batch_line_cap": int(adapter.batch_line_cap or 0) if adapter else 0,
        "batch_amount_cap": flt(adapter.batch_amount_cap or 0) if adapter else 0,
        "source_preview_line_count": int(adapter.source_preview_line_count or 0) if adapter else 0,
        "eligible_preview_line_count": int(adapter.eligible_preview_line_count or 0) if adapter else 0,
        "blocked_preview_line_count": int(adapter.blocked_preview_line_count or 0) if adapter else 0,
        "hard_blocked_line_count": int(adapter.hard_blocked_line_count or 0) if adapter else 0,
        "validation_blocked_line_count": int(adapter.validation_blocked_line_count or 0) if adapter else 0,
        "would_create_payment_entry_count": would_create_count,
        "would_create_payment_entry_amount": flt(getattr(adapter, "would_create_payment_entry_amount", 0) or 0) if adapter else 0,
        "actual_payment_entry_created_count": int(getattr(adapter, "actual_payment_entry_created_count", 0) or 0) if adapter else 0,
        "actual_gl_created_count": int(getattr(adapter, "actual_gl_created_count", 0) or 0) if adapter else 0,
        "items": items,
        "summary": item_summary,
        "guardrails_before": guard_before,
        "guardrails_after": guardrails(),
        "config": config,
        "required_acknowledgement": ACTIVATION_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 6D activation gate only. It does not enable live posting and creates no Payment Entry or GL.",
    }
    if int(dry_run or 0):
        return result

    doc = frappe.new_doc(GATE_DOCTYPE)
    doc.activation_gate_id = make_activation_gate_id()
    doc.status = status_text
    doc.gate_type = "Real Remittance Payment Entry Activation"
    doc.structural_ready_allowed = structural_ready_allowed
    doc.ready_for_real_smoke = ready_for_real_smoke
    doc.real_posting_allowed = 0
    doc.source_eligible_pending = source_eligible_pending
    for fieldname in [
        "adapter_run",
        "preview",
        "design_gate",
        "source_remittance_import",
        "company",
        "bank_account",
        "receivable_account",
        "batch_line_cap",
        "batch_amount_cap",
        "source_preview_line_count",
        "eligible_preview_line_count",
        "blocked_preview_line_count",
        "hard_blocked_line_count",
        "validation_blocked_line_count",
        "would_create_payment_entry_count",
        "would_create_payment_entry_amount",
        "actual_payment_entry_created_count",
        "actual_gl_created_count",
    ]:
        setattr(doc, fieldname, result[fieldname])

    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.activation_score = score
    doc.activation_status = activation_status_text
    doc.blocker_count = item_summary["blocker_count"]
    doc.warning_count = item_summary["warning_count"]
    doc.pass_count = item_summary["pass_count"]
    doc.info_count = item_summary["info_count"]
    doc.item_count = item_summary["item_count"]
    doc.payment_entry_count_before = guard_before["payment_entry_count"]
    doc.payment_entry_count_after = guardrails()["payment_entry_count"]
    doc.payment_entry_gl_count_before = guard_before["payment_entry_gl_count"]
    doc.payment_entry_gl_count_after = guardrails()["payment_entry_gl_count"]
    doc.submitted_journal_entry_count_today = guard_before["submitted_journal_entry_count_today"]
    doc.sales_invoice_count_today = guard_before["sales_invoice_count_today"]
    doc.purchase_invoice_count_today = guard_before["purchase_invoice_count_today"]
    doc.live_enabled_policy_count = guard_before["live_enabled_policy_count"]
    doc.required_acknowledgement = ACTIVATION_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    create_gate_items(doc, items)

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
def cancel_real_remittance_pe_activation_gate(activation_gate, reason=None):
    assert_action("cancel_real_remittance_pe_activation_gate")
    if not frappe.db.exists(GATE_DOCTYPE, activation_gate):
        frappe.throw(_("Activation gate not found: {0}").format(activation_gate))
    doc = frappe.get_doc(GATE_DOCTYPE, activation_gate)
    if doc.status == "Cancelled":
        return {"activation_gate": activation_gate, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.ready_for_real_smoke or 0):
        frappe.throw(_("Cannot cancel a ready-for-real-smoke activation gate. Create a superseding gate instead."))
    frappe.db.set_value(
        GATE_DOCTYPE,
        activation_gate,
        {
            "status": "Cancelled",
            "structural_ready_allowed": 0,
            "ready_for_real_smoke": 0,
            "real_posting_allowed": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 6D activation gate cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(
        f"UPDATE `tab{ITEM_DOCTYPE}` SET status = 'Cancelled' WHERE activation_gate = %(activation_gate)s",
        {"activation_gate": activation_gate},
    )
    frappe.db.commit()
    return {
        "activation_gate": activation_gate,
        "status": "Cancelled",
        "note": "Activation gate audit record cancelled only. No accounting movement occurred.",
    }


@frappe.whitelist()
def quick_real_remittance_pe_activation_gate_summary(limit=20):
    gates = frappe.get_all(
        GATE_DOCTYPE,
        fields=[
            "name",
            "activation_gate_id",
            "status",
            "activation_status",
            "activation_score",
            "structural_ready_allowed",
            "ready_for_real_smoke",
            "real_posting_allowed",
            "source_eligible_pending",
            "adapter_run",
            "eligible_preview_line_count",
            "would_create_payment_entry_count",
            "would_create_payment_entry_amount",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
            "payment_entry_count_after",
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
        "note": "Phase 6D activation summary only. Real posting remains disabled.",
    }


def execute_gate_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("status"):
        conditions.append("g.status = %(status)s")
        params["status"] = filters.status
    if filters.get("from_date"):
        conditions.append("DATE(g.checked_on) >= %(from_date)s")
        params["from_date"] = filters.from_date
    if filters.get("to_date"):
        conditions.append("DATE(g.checked_on) <= %(to_date)s")
        params["to_date"] = filters.to_date
    columns = [
        {"fieldname": "activation_gate", "label": _("Activation Gate"), "fieldtype": "Link", "options": GATE_DOCTYPE, "width": 220},
        {"fieldname": "activation_gate_id", "label": _("Activation Gate ID"), "fieldtype": "Data", "width": 360},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 130},
        {"fieldname": "activation_status", "label": _("Activation Status"), "fieldtype": "Data", "width": 240},
        {"fieldname": "structural_ready_allowed", "label": _("Structural Ready"), "fieldtype": "Check", "width": 130},
        {"fieldname": "ready_for_real_smoke", "label": _("Ready Real Smoke"), "fieldtype": "Check", "width": 140},
        {"fieldname": "real_posting_allowed", "label": _("Real Posting Allowed"), "fieldtype": "Check", "width": 150},
        {"fieldname": "source_eligible_pending", "label": _("Source Pending"), "fieldtype": "Check", "width": 130},
        {"fieldname": "eligible_preview_line_count", "label": _("Eligible Lines"), "fieldtype": "Int", "width": 110},
        {"fieldname": "would_create_payment_entry_count", "label": _("Would Create PE"), "fieldtype": "Int", "width": 130},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE Created"), "fieldtype": "Int", "width": 140},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL Created"), "fieldtype": "Int", "width": 130},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            g.name AS activation_gate,
            g.activation_gate_id,
            g.status,
            g.activation_status,
            g.structural_ready_allowed,
            g.ready_for_real_smoke,
            g.real_posting_allowed,
            g.source_eligible_pending,
            g.eligible_preview_line_count,
            g.would_create_payment_entry_count,
            g.actual_payment_entry_created_count,
            g.actual_gl_created_count,
            g.checked_on
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
                {"name": "Structural Ready", "values": [int(row.structural_ready_allowed or 0) for row in data[:20]]},
                {"name": "Ready Real Smoke", "values": [int(row.ready_for_real_smoke or 0) for row in data[:20]]},
                {"name": "Real Posting Allowed", "values": [int(row.real_posting_allowed or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Activation Gates"), "datatype": "Int"},
        {"value": sum(int(row.structural_ready_allowed or 0) for row in data), "indicator": "Green", "label": _("Structural Ready"), "datatype": "Int"},
        {"value": sum(int(row.ready_for_real_smoke or 0) for row in data), "indicator": "Orange", "label": _("Ready For Real Smoke"), "datatype": "Int"},
        {"value": sum(int(row.real_posting_allowed or 0) for row in data), "indicator": "Red", "label": _("Real Posting Allowed"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_exception_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    for field in ["activation_gate", "status", "severity", "category"]:
        if filters.get(field):
            conditions.append(f"i.{field} = %({field})s")
            params[field] = filters.get(field)
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": ITEM_DOCTYPE, "width": 220},
        {"fieldname": "activation_gate", "label": _("Activation Gate"), "fieldtype": "Link", "options": GATE_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 180},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 320},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 460},
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
        chart_map[row.status or "Info"] = chart_map.get(row.status or "Info", 0) + 1
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


def execute_readiness_report(filters=None):
    columns = [
        {"fieldname": "adapter_run", "label": _("Adapter Run"), "fieldtype": "Link", "options": ADAPTER_DOCTYPE, "width": 220},
        {"fieldname": "adapter_run_id", "label": _("Adapter Run ID"), "fieldtype": "Data", "width": 360},
        {"fieldname": "adapter_status", "label": _("Adapter Status"), "fieldtype": "Data", "width": 260},
        {"fieldname": "source_preview_line_count", "label": _("Source Lines"), "fieldtype": "Int", "width": 110},
        {"fieldname": "eligible_preview_line_count", "label": _("Eligible Lines"), "fieldtype": "Int", "width": 110},
        {"fieldname": "source_eligible_pending", "label": _("Source Pending"), "fieldtype": "Check", "width": 120},
        {"fieldname": "would_create_payment_entry_count", "label": _("Would Create PE"), "fieldtype": "Int", "width": 130},
        {"fieldname": "would_create_payment_entry_amount", "label": _("Would Create Amount"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE Created"), "fieldtype": "Int", "width": 140},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL Created"), "fieldtype": "Int", "width": 130},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            r.name AS adapter_run,
            r.adapter_run_id,
            r.adapter_status,
            r.source_preview_line_count,
            r.eligible_preview_line_count,
            r.source_eligible_pending,
            r.would_create_payment_entry_count,
            r.would_create_payment_entry_amount,
            r.actual_payment_entry_created_count,
            r.actual_gl_created_count,
            %(currency)s AS currency
        FROM `tab{ADAPTER_DOCTYPE}` r
        ORDER BY r.creation DESC
        LIMIT 50
        """,
        {"currency": currency()},
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.adapter_run_id for row in data[:20]],
            "datasets": [
                {"name": "Eligible Lines", "values": [int(row.eligible_preview_line_count or 0) for row in data[:20]]},
                {"name": "Source Pending", "values": [int(row.source_eligible_pending or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Adapter Runs"), "datatype": "Int"},
        {"value": sum(int(row.eligible_preview_line_count or 0) for row in data), "indicator": "Green", "label": _("Eligible Lines"), "datatype": "Int"},
        {"value": sum(int(row.source_eligible_pending or 0) for row in data), "indicator": "Orange", "label": _("Source Pending Runs"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
