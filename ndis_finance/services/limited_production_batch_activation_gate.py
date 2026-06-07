import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


ACTIVATION_ACK = "I_CONFIRM_PHASE9E_ACTIVATE_LIMITED_PRODUCTION_BATCH_SMOKE_ONLY_NO_POSTING"


def make_activation_gate_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-LIMITED-PROD-BATCH-ACT-GATE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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
        "production_batch_enabled_policy_count": count_dt("NDIS Controlled Production Batch Posting Policy", {"production_batch_enabled": 1}),
        "live_posting_allowed_policy_count": count_dt("NDIS Controlled Production Batch Posting Policy", {"live_posting_allowed": 1}),
    }


def latest_adapter_run():
    rows = frappe.get_all(
        "NDIS Limited Production Batch Adapter Run",
        filters={
            "status": "Hard Blocked",
            "limited_adapter_approved_for_activation_gate": 1,
            "ready_for_limited_activation_gate": 1,
            "direct_live_creation_blocked": 1,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
        },
        fields=[
            "name",
            "adapter_run_id",
            "policy_preview",
            "policy_design",
            "policy_review_gate",
            "phase8g_freeze",
            "source_preview",
            "activation_gate",
            "source_adapter_run",
            "design_gate",
            "company",
            "customer",
            "policy_mode",
            "max_batch_lines",
            "max_batch_amount",
            "max_payment_entry_count",
            "allowed_payment_type",
            "allowed_reference_doctype",
            "source_line_count",
            "eligible_line_count",
            "hard_blocked_line_count",
            "validation_blocked_line_count",
            "duplicate_blocked_line_count",
            "would_create_payment_entry_count",
            "would_create_reference_count",
            "would_create_payment_entry_amount",
            "direct_live_creation_blocked",
            "adapter_score",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )

    return rows[0] if rows else None


def existing_allowed_gate(adapter_run):
    rows = frappe.get_all(
        "NDIS Limited Production Batch Activation Gate",
        filters={
            "adapter_run": adapter_run,
            "status": "Activation Allowed",
            "limited_activation_allowed": 1,
            "ready_for_limited_batch_smoke": 1,
        },
        fields=["name", "activation_gate_id"],
        limit=1,
    )

    return rows[0] if rows else None


def get_adapter_lines(adapter_run):
    if not adapter_run:
        return []

    return frappe.get_all(
        "NDIS Limited Production Batch Adapter Run Line",
        filters={"adapter_run": adapter_run},
        fields=[
            "name",
            "line_no",
            "line_status",
            "policy_preview",
            "policy_preview_line",
            "sales_invoice",
            "claim_line",
            "remittance_line",
            "invoice_outstanding",
            "allocatable_amount",
            "would_create_payment_entry",
            "would_create_reference",
            "actual_payment_entry_created",
            "actual_gl_created",
            "policy_live_enabled",
            "hard_block_verified",
            "block_reason",
        ],
        order_by="line_no asc, creation asc",
    )


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


def validate_activation_source(adapter, adapter_lines, guard):
    issues = []

    if not adapter:
        issues.append("No completed Phase 9D hard-block adapter found.")
        return issues

    if existing_allowed_gate(adapter.name):
        issues.append("An allowed Phase 9E activation gate already exists for this Phase 9D adapter.")

    required_links = {
        "policy_preview": adapter.policy_preview,
        "policy_design": adapter.policy_design,
        "policy_review_gate": adapter.policy_review_gate,
        "phase8g_freeze": adapter.phase8g_freeze,
        "source_preview": adapter.source_preview,
    }

    for label, value in required_links.items():
        if not value:
            issues.append(f"Missing evidence link: {label}")

    if not int(adapter.direct_live_creation_blocked or 0):
        issues.append("Direct live creation block was not verified on the adapter.")

    if int(adapter.would_create_payment_entry_count or 0) != 1:
        issues.append("Adapter must would-create exactly one Payment Entry.")

    if int(adapter.would_create_reference_count or 0) != 2:
        issues.append("Adapter must would-create exactly two references.")

    if flt(adapter.would_create_payment_entry_amount or 0, 2) != 2:
        issues.append("Adapter would-create amount must be 2.00.")

    if int(adapter.hard_blocked_line_count or 0) != 2:
        issues.append("Adapter must have exactly two hard-blocked lines.")

    hard_lines = [row for row in adapter_lines if row.line_status == "Hard Blocked"]

    if len(hard_lines) != 2:
        issues.append("Adapter line evidence must include exactly two Hard Blocked lines.")

    for row in hard_lines:
        if not int(row.hard_block_verified or 0):
            issues.append(f"Adapter line {row.line_no} does not have hard_block_verified = 1.")
        if not int(row.would_create_payment_entry or 0):
            issues.append(f"Adapter line {row.line_no} is missing would_create_payment_entry = 1.")
        if not int(row.would_create_reference or 0):
            issues.append(f"Adapter line {row.line_no} is missing would_create_reference = 1.")
        if int(row.actual_payment_entry_created or 0):
            issues.append(f"Adapter line {row.line_no} has actual_payment_entry_created = 1.")
        if int(row.actual_gl_created or 0):
            issues.append(f"Adapter line {row.line_no} has actual_gl_created = 1.")
        if int(row.policy_live_enabled or 0):
            issues.append(f"Adapter line {row.line_no} has policy_live_enabled = 1.")
        if flt(row.allocatable_amount or 0, 2) <= 0:
            issues.append(f"Adapter line {row.line_no} has non-positive allocatable amount.")

    if guard["production_batch_enabled_policy_count"] != 0:
        issues.append("Controlled production batch enabled policy count is not zero.")

    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count is not zero.")

    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today is not zero.")

    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today is not zero.")

    return issues


def build_items(adapter, config, guard, issues, ack_ok):
    items = []

    if adapter:
        add_item(
            items,
            "Pass",
            "Low",
            "Adapter",
            "phase9d_adapter_exists",
            "Phase 9D hard-block adapter exists",
            f"Adapter found: {adapter.adapter_run_id}.",
            "NDIS Limited Production Batch Adapter Run",
            adapter.name,
        )
    else:
        add_item(items, "Blocker", "Critical", "Adapter", "phase9d_adapter_exists", "Phase 9D hard-block adapter exists", "No completed Phase 9D adapter found.")

    if not issues:
        add_item(items, "Pass", "Low", "Activation Source", "activation_source_valid", "Activation source valid", "Phase 9D hard-block adapter is valid for limited activation gate.")
    else:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Activation Source", "activation_source_valid", "Activation source valid", issue)

    if adapter and int(adapter.direct_live_creation_blocked or 0):
        add_item(items, "Pass", "Low", "Hard Block", "adapter_hard_block_verified", "Adapter hard block verified", "Adapter confirms direct live creation is blocked.")
    else:
        add_item(items, "Blocker", "Critical", "Hard Block", "adapter_hard_block_verified", "Adapter hard block verified", "Adapter hard block evidence missing.")

    if adapter and int(adapter.would_create_payment_entry_count or 0) == 1:
        add_item(items, "Pass", "Low", "Would-create Evidence", "would_create_pe", "Would-create Payment Entry", "Would-create count is exactly 1.")
    else:
        add_item(items, "Blocker", "Critical", "Would-create Evidence", "would_create_pe", "Would-create Payment Entry", "Would-create Payment Entry count is not 1.")

    if adapter and int(adapter.would_create_reference_count or 0) == 2:
        add_item(items, "Pass", "Low", "Would-create Evidence", "would_create_refs", "Would-create references", "Would-create reference count is exactly 2.")
    else:
        add_item(items, "Blocker", "Critical", "Would-create Evidence", "would_create_refs", "Would-create references", "Would-create reference count is not 2.")

    if adapter and flt(adapter.would_create_payment_entry_amount or 0, 2) == 2:
        add_item(items, "Pass", "Low", "Would-create Evidence", "would_create_amount", "Would-create amount", "Would-create amount is 2.00.")
    else:
        add_item(items, "Blocker", "Critical", "Would-create Evidence", "would_create_amount", "Would-create amount", "Would-create amount is not 2.00.")

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
        add_item(items, "Pass", "Low", "Acknowledgement", "activation_ack", "Activation acknowledgement", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "activation_ack", "Activation acknowledgement", f"Required acknowledgement not supplied: {ACTIVATION_ACK}")

    return items


def create_gate_items(doc, items):
    for item in items:
        row = frappe.new_doc("NDIS Limited Production Batch Activation Gate Item")
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
def run_limited_production_batch_activation_gate(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_limited_production_batch_activation_gate")

    adapter = latest_adapter_run()
    adapter_lines = get_adapter_lines(adapter.name) if adapter else []

    config = config_state()
    guard_before = guardrails()
    ack_ok = acknowledgement == ACTIVATION_ACK

    issues = validate_activation_source(adapter, adapter_lines, guard_before)
    items = build_items(adapter, config, guard_before, issues, ack_ok)

    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    allowed = int(ack_ok and item_summary["blocker_count"] == 0 and adapter is not None)

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Activation Allowed" if allowed else "Needs Review",
        "activation_status": "Ready For Limited Controlled Batch Smoke" if allowed else "Needs Review",
        "limited_activation_allowed": allowed,
        "ready_for_limited_batch_smoke": allowed,
        "adapter_hard_block_verified": int(adapter.direct_live_creation_blocked or 0) if adapter else 0,
        "production_batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "policy_live_enabled": 0,
        "adapter_run": adapter.name if adapter else None,
        "policy_preview": adapter.policy_preview if adapter else None,
        "policy_design": adapter.policy_design if adapter else None,
        "policy_review_gate": adapter.policy_review_gate if adapter else None,
        "phase8g_freeze": adapter.phase8g_freeze if adapter else None,
        "source_preview": adapter.source_preview if adapter else None,
        "source_adapter_run": adapter.source_adapter_run if adapter else None,
        "design_gate": adapter.design_gate if adapter else None,
        "company": adapter.company if adapter else None,
        "customer": adapter.customer if adapter else None,
        "policy_mode": adapter.policy_mode if adapter else "Limited Controlled Production Batch",
        "max_batch_lines": int(adapter.max_batch_lines or 0) if adapter else 0,
        "max_batch_amount": flt(adapter.max_batch_amount or 0) if adapter else 0,
        "max_payment_entry_count": int(adapter.max_payment_entry_count or 0) if adapter else 0,
        "allowed_payment_type": adapter.allowed_payment_type if adapter else "Receive",
        "allowed_reference_doctype": adapter.allowed_reference_doctype if adapter else "Sales Invoice",
        "source_line_count": int(adapter.source_line_count or 0) if adapter else 0,
        "eligible_line_count": int(adapter.eligible_line_count or 0) if adapter else 0,
        "hard_blocked_line_count": int(adapter.hard_blocked_line_count or 0) if adapter else 0,
        "would_create_payment_entry_count": int(adapter.would_create_payment_entry_count or 0) if adapter else 0,
        "would_create_reference_count": int(adapter.would_create_reference_count or 0) if adapter else 0,
        "would_create_payment_entry_amount": flt(adapter.would_create_payment_entry_amount or 0) if adapter else 0,
        "allowed_smoke_payment_entry_count": 1,
        "allowed_smoke_reference_count": 2,
        "allowed_smoke_amount": 2,
        "rollback_required_after_smoke": 1,
        "freeze_required_after_rollback": 1,
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
        "note": "Phase 9E creates activation gate records only. It does not create Payment Entry or GL.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["activation_status"] = "Needs Review"
        result["limited_activation_allowed"] = 0
        result["ready_for_limited_batch_smoke"] = 0
        return result

    doc = frappe.new_doc("NDIS Limited Production Batch Activation Gate")
    doc.activation_gate_id = make_activation_gate_id()
    doc.status = result["status"]
    doc.activation_status = result["activation_status"]
    doc.limited_activation_allowed = allowed
    doc.ready_for_limited_batch_smoke = allowed
    doc.adapter_hard_block_verified = result["adapter_hard_block_verified"]
    doc.production_batch_posting_allowed = 0
    doc.real_posting_allowed = 0
    doc.policy_live_enabled = 0

    for fieldname in [
        "adapter_run",
        "policy_preview",
        "policy_design",
        "policy_review_gate",
        "phase8g_freeze",
        "source_preview",
        "source_adapter_run",
        "design_gate",
        "company",
        "customer",
        "policy_mode",
        "max_batch_lines",
        "max_batch_amount",
        "max_payment_entry_count",
        "allowed_payment_type",
        "allowed_reference_doctype",
        "source_line_count",
        "eligible_line_count",
        "hard_blocked_line_count",
        "would_create_payment_entry_count",
        "would_create_reference_count",
        "would_create_payment_entry_amount",
        "allowed_smoke_payment_entry_count",
        "allowed_smoke_reference_count",
        "allowed_smoke_amount",
        "rollback_required_after_smoke",
        "freeze_required_after_rollback",
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

    create_gate_items(doc, items)

    guard_after = guardrails()

    frappe.db.set_value(
        "NDIS Limited Production Batch Activation Gate",
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
def cancel_limited_production_batch_activation_gate(activation_gate, reason=None):
    assert_action("cancel_limited_production_batch_activation_gate")

    if not frappe.db.exists("NDIS Limited Production Batch Activation Gate", activation_gate):
        frappe.throw(_("Activation gate not found: {0}").format(activation_gate))

    doc = frappe.get_doc("NDIS Limited Production Batch Activation Gate", activation_gate)

    if doc.status == "Cancelled":
        return {"activation_gate": activation_gate, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.limited_activation_allowed or 0):
        frappe.throw(_("Cannot cancel an allowed activation gate. Create a superseding gate instead."))

    frappe.db.set_value(
        "NDIS Limited Production Batch Activation Gate",
        activation_gate,
        {
            "status": "Cancelled",
            "activation_status": "Cancelled",
            "limited_activation_allowed": 0,
            "ready_for_limited_batch_smoke": 0,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 9E activation gate audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        """
        UPDATE `tabNDIS Limited Production Batch Activation Gate Item`
        SET status = 'Cancelled'
        WHERE activation_gate = %(activation_gate)s
        """,
        {"activation_gate": activation_gate},
    )

    frappe.db.commit()

    return {
        "activation_gate": activation_gate,
        "status": "Cancelled",
        "note": "Activation gate audit record cancelled only. No accounting movement occurred.",
    }


@frappe.whitelist()
def quick_limited_production_batch_activation_gate_summary(limit=20):
    gates = frappe.get_all(
        "NDIS Limited Production Batch Activation Gate",
        fields=[
            "name",
            "activation_gate_id",
            "status",
            "activation_status",
            "limited_activation_allowed",
            "ready_for_limited_batch_smoke",
            "adapter_hard_block_verified",
            "production_batch_posting_allowed",
            "real_posting_allowed",
            "policy_live_enabled",
            "adapter_run",
            "policy_preview",
            "policy_design",
            "would_create_payment_entry_count",
            "would_create_reference_count",
            "would_create_payment_entry_amount",
            "allowed_smoke_payment_entry_count",
            "allowed_smoke_reference_count",
            "allowed_smoke_amount",
            "rollback_required_after_smoke",
            "freeze_required_after_rollback",
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
        "NDIS Limited Production Batch Activation Gate Item",
        fields=[
            "name",
            "activation_gate",
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
        "required_acknowledgement": ACTIVATION_ACK,
        "guardrails": guardrails(),
        "config": config_state(),
        "note": "Phase 9E limited production batch activation gate summary. No live posting enabled.",
    }


def execute_activation_gate_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("status"):
        conditions.append("g.status = %(status)s")
        params["status"] = filters.get("status")

    columns = activation_columns()

    data = frappe.db.sql(
        f"""
        SELECT
            g.name AS activation_gate,
            g.activation_gate_id,
            g.status,
            g.activation_status,
            g.limited_activation_allowed,
            g.ready_for_limited_batch_smoke,
            g.adapter_hard_block_verified,
            g.production_batch_posting_allowed,
            g.real_posting_allowed,
            g.policy_live_enabled,
            g.adapter_run,
            g.policy_preview,
            g.policy_design,
            g.would_create_payment_entry_count,
            g.would_create_reference_count,
            g.would_create_payment_entry_amount,
            g.allowed_smoke_payment_entry_count,
            g.allowed_smoke_reference_count,
            g.allowed_smoke_amount,
            g.rollback_required_after_smoke,
            g.freeze_required_after_rollback,
            g.actual_payment_entry_created_count,
            g.actual_gl_created_count,
            g.activation_score,
            g.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Limited Production Batch Activation Gate` g
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
                {"name": "Allowed", "values": [int(row.limited_activation_allowed or 0) for row in data[:20]]},
                {"name": "Actual PE", "values": [int(row.actual_payment_entry_created_count or 0) for row in data[:20]]},
                {"name": "Actual GL", "values": [int(row.actual_gl_created_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Activation Gates"), "datatype": "Int"},
        {"value": sum(int(row.limited_activation_allowed or 0) for row in data), "indicator": "Green", "label": _("Allowed"), "datatype": "Int"},
        {"value": sum(flt(row.would_create_payment_entry_amount or 0) for row in data), "indicator": "Blue", "label": _("Would-create Amount"), "datatype": "Currency", "currency": currency()},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PE"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def activation_columns():
    return [
        {"fieldname": "activation_gate", "label": _("Activation Gate"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Activation Gate", "width": 220},
        {"fieldname": "activation_gate_id", "label": _("Activation Gate ID"), "fieldtype": "Data", "width": 430},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 150},
        {"fieldname": "activation_status", "label": _("Activation Status"), "fieldtype": "Data", "width": 300},
        {"fieldname": "ready_for_limited_batch_smoke", "label": _("Ready Smoke"), "fieldtype": "Check", "width": 110},
        {"fieldname": "adapter_hard_block_verified", "label": _("Adapter Block"), "fieldtype": "Check", "width": 110},
        {"fieldname": "would_create_payment_entry_count", "label": _("Would PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "would_create_reference_count", "label": _("Would Refs"), "fieldtype": "Int", "width": 100},
        {"fieldname": "would_create_payment_entry_amount", "label": _("Would Amount"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "allowed_smoke_amount", "label": _("Smoke Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "policy_live_enabled", "label": _("Live Enabled"), "fieldtype": "Check", "width": 110},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "activation_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    if filters.get("activation_gate"):
        conditions.append("i.activation_gate = %(activation_gate)s")
        params["activation_gate"] = filters.get("activation_gate")

    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Activation Gate Item", "width": 220},
        {"fieldname": "activation_gate", "label": _("Activation Gate"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Activation Gate", "width": 220},
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
        FROM `tabNDIS Limited Production Batch Activation Gate Item` i
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
