import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


ADAPTER_ACK = "I_CONFIRM_RUN_PE_PRODUCTION_ADAPTER_HARD_BLOCK_NO_PAYMENT_ENTRY"


def make_adapter_run_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-PE-PROD-ADAPTER-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_doc(doctype, filters=None, fields=None, order_by="creation desc"):
    rows = frappe.get_all(doctype, filters=filters or {}, fields=fields or ["name"], order_by=order_by, limit=1)
    return rows[0] if rows else None


def guardrails():
    return {
        "payment_entry_count": count_dt("Payment Entry"),
        "submitted_payment_entry_count_today": count_dt("Payment Entry", {"creation": [">=", today()], "docstatus": 1}),
        "payment_entry_gl_count": count_dt("GL Entry", {"voucher_type": "Payment Entry"}),
        "payment_entry_gl_count_today": count_dt("GL Entry", {"creation": [">=", today()], "voucher_type": "Payment Entry"}),
        "submitted_journal_entry_count_today": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}),
        "purchase_invoice_count_today": count_dt("Purchase Invoice", {"creation": [">=", today()]}),
    }


def config_state():
    return {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def config_errors(config):
    errors = []
    if int(config.get("production_mode") or 0):
        errors.append("Production mode config is enabled.")
    if int(config.get("live_pe_enabled") or 0):
        errors.append("Live Payment Entry posting config is enabled. Phase 5D requires it disabled.")
    return errors


def prior_counts():
    return {
        "phase5c_preview_count": count_dt(
            "NDIS PE Production Posting Preview",
            {"status": "Previewed", "acknowledgement_ok": 1, "payment_entry_created": 0, "live_posting_allowed": 0},
        ),
        "phase5b_hardened_gate_count": count_dt(
            "NDIS PE Production Account Mapping Gate",
            {"account_mapping_hardened": 1, "ready_for_preview_phase": 1, "live_posting_allowed": 0, "blocker_count": 0},
        ),
        "phase5a_approved_gate_count": count_dt(
            "NDIS PE Production Design Gate",
            {"design_approved_for_next_phase": 1, "live_posting_allowed": 0, "blocker_count": 0},
        ),
        "phase4d_ready_freeze_count": count_dt(
            "NDIS PE Sandbox Readiness Freeze",
            {"readiness_allowed": 1, "ready_for_next_design_phase": 1, "blocker_count": 0},
        ),
    }


def get_source_preview(source_preview=None):
    if source_preview:
        if not frappe.db.exists("NDIS PE Production Posting Preview", source_preview):
            frappe.throw(_("Source preview not found: {0}").format(source_preview))
        return frappe.get_doc("NDIS PE Production Posting Preview", source_preview)

    row = latest_doc(
        "NDIS PE Production Posting Preview",
        {"status": "Previewed", "acknowledgement_ok": 1, "payment_entry_created": 0, "live_posting_allowed": 0},
        ["name"],
        "previewed_on desc, creation desc",
    )
    if not row:
        frappe.throw(_("No acknowledged Phase 5C production posting preview found."))
    return frappe.get_doc("NDIS PE Production Posting Preview", row.name)


def get_preview_lines(source_preview):
    return frappe.get_all(
        "NDIS PE Production Posting Preview Line",
        filters={"posting_preview": source_preview},
        fields=[
            "name",
            "status",
            "scenario_key",
            "event_type",
            "claim_outcome",
            "source_reference",
            "sales_invoice",
            "posting_policy",
            "mapping_rule",
            "policy_company",
            "allowed_bank_account",
            "allowed_receivable_account",
            "preview_payment_amount",
            "shortfall_amount",
            "would_create_payment_entry",
            "actual_payment_entry_created",
            "duplicate_detected",
            "cross_company_blocked",
            "overpayment_blocked",
            "negative_receipt_blocked",
            "rejected_claim_blocked",
            "block_reason",
            "preview_note",
        ],
        order_by="creation asc",
        limit=10000,
    )


def hard_block_live_payment_entry_creation(reason=None):
    assert_action("attempt_live_payment_entry_creation")
    frappe.throw(
        _(
            reason
            or "Phase 5D hard block: production Payment Entry creation is disabled until a future activation gate is implemented and passed."
        )
    )


@frappe.whitelist()
def attempt_live_payment_entry_creation(source_preview_line=None):
    hard_block_live_payment_entry_creation(
        "Phase 5D hard block confirmed: live Payment Entry creation is not available until Phase 5E activation gate is implemented and passed."
    )


def evaluate_adapter_line(row):
    reason = row.block_reason or ""
    future_activation_blocked = 0
    if int(row.actual_payment_entry_created or 0):
        status = "Validation Blocked"
        severity = "Critical"
        note = "Source preview line incorrectly indicates an actual Payment Entry was created."
    elif row.status == "Preview Eligible" and int(row.would_create_payment_entry or 0):
        status = "Hard Blocked"
        severity = "Low"
        future_activation_blocked = 1
        reason = "Future activation gate not implemented or not passed. Live Payment Entry adapter is intentionally hard-blocked."
        note = "This line would be eligible in preview, but Phase 5D correctly blocks live Payment Entry creation."
    elif int(row.rejected_claim_blocked or 0):
        status = "Rejected Blocked"
        severity = "Low"
        note = "Rejected claim remains blocked. No Payment Entry allowed."
    elif int(row.duplicate_detected or 0):
        status = "Duplicate Blocked"
        severity = "Low"
        note = "Duplicate remains blocked. No Payment Entry allowed."
    elif int(row.cross_company_blocked or 0) or int(row.overpayment_blocked or 0) or int(row.negative_receipt_blocked or 0):
        status = "Validation Blocked"
        severity = "Low"
        note = "Validation failure remains blocked. No Payment Entry allowed."
    elif row.status in ["Blocked", "Duplicate", "Warning"]:
        status = "Validation Blocked"
        severity = "Medium"
        note = "Source preview line is not eligible for live adapter processing."
    else:
        status = "Info"
        severity = "Low"
        note = "No live adapter action required."

    return {
        "source_preview_line": row.name,
        "status": status,
        "severity": severity,
        "scenario_key": row.scenario_key,
        "event_type": row.event_type,
        "claim_outcome": row.claim_outcome,
        "source_reference": row.source_reference,
        "sales_invoice": row.sales_invoice,
        "posting_policy": row.posting_policy,
        "mapping_rule": row.mapping_rule,
        "policy_company": row.policy_company,
        "allowed_bank_account": row.allowed_bank_account,
        "allowed_receivable_account": row.allowed_receivable_account,
        "preview_payment_amount": flt(row.preview_payment_amount),
        "shortfall_amount": flt(row.shortfall_amount),
        "adapter_blocked_amount": flt(row.preview_payment_amount) if status == "Hard Blocked" else 0,
        "would_create_payment_entry": int(row.would_create_payment_entry or 0),
        "actual_payment_entry_created": 0,
        "attempted_payment_entry_name": None,
        "duplicate_detected": int(row.duplicate_detected or 0),
        "cross_company_blocked": int(row.cross_company_blocked or 0),
        "overpayment_blocked": int(row.overpayment_blocked or 0),
        "negative_receipt_blocked": int(row.negative_receipt_blocked or 0),
        "rejected_claim_blocked": int(row.rejected_claim_blocked or 0),
        "future_activation_blocked": future_activation_blocked,
        "block_reason": reason,
        "adapter_note": note,
    }


def summarise_lines(lines):
    hard_blocked = [line for line in lines if line["status"] == "Hard Blocked"]
    validation_blocked = [line for line in lines if line["status"] == "Validation Blocked"]
    duplicate_blocked = [line for line in lines if line["status"] == "Duplicate Blocked"]
    rejected_blocked = [line for line in lines if line["status"] == "Rejected Blocked"]
    critical_blockers = [line for line in validation_blocked if line["severity"] == "Critical"]
    return {
        "line_count": len(lines),
        "hard_blocked_line_count": len(hard_blocked),
        "validation_blocked_line_count": len(validation_blocked),
        "duplicate_blocked_line_count": len(duplicate_blocked),
        "rejected_blocked_line_count": len(rejected_blocked),
        "would_create_payment_entry_count": len([line for line in lines if int(line["would_create_payment_entry"] or 0)]),
        "actual_payment_entry_created_count": len([line for line in lines if int(line["actual_payment_entry_created"] or 0)]),
        "preview_total_amount": sum(flt(line["preview_payment_amount"]) for line in lines if int(line["would_create_payment_entry"] or 0)),
        "adapter_blocked_amount": sum(flt(line["adapter_blocked_amount"]) for line in lines),
        "pass_count": len(hard_blocked) + len(duplicate_blocked) + len(rejected_blocked) + len([line for line in validation_blocked if line["severity"] != "Critical"]),
        "warning_count": len([line for line in lines if line["status"] == "Warning"]),
        "blocker_count": len(critical_blockers),
        "info_count": len([line for line in lines if line["status"] == "Info"]),
    }


def calculate_score(blockers, warnings):
    return max(0, round(100 - int(blockers or 0) * 25 - int(warnings or 0) * 5, 2))


def adapter_status(score, blockers, warnings):
    if blockers:
        return "Blocked"
    if warnings:
        return "Ready With Warnings"
    if score >= 95:
        return "Ready For Activation Gate Design"
    return "Needs Review"


@frappe.whitelist()
def run_pe_production_adapter_hard_block(source_preview=None, acknowledgement=None, dry_run=1, notes=None):
    assert_action("run_pe_production_adapter_hard_block")
    config = config_state()
    errors = config_errors(config)
    prior = prior_counts()
    guard_before = guardrails()
    preview = get_source_preview(source_preview)
    lines = [evaluate_adapter_line(row) for row in get_preview_lines(preview.name)]
    summary = summarise_lines(lines)
    summary["blocker_count"] += len(errors)
    for key in ["phase5c_preview_count", "phase5b_hardened_gate_count", "phase5a_approved_gate_count", "phase4d_ready_freeze_count"]:
        if prior[key] < 1:
            summary["blocker_count"] += 1
    ack_ok = acknowledgement == ADAPTER_ACK
    if not ack_ok:
        summary["warning_count"] += 1
    score = calculate_score(summary["blocker_count"], summary["warning_count"])
    final_adapter_status = adapter_status(score, summary["blocker_count"], summary["warning_count"])
    status = "Blocked" if summary["blocker_count"] else ("Needs Review" if not ack_ok or summary["warning_count"] else "Hard Blocked")
    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": status,
        "adapter_status": final_adapter_status,
        "adapter_score": score,
        "source_preview": preview.name,
        "source_preview_id": preview.preview_id,
        "company": preview.company,
        "allowed_bank_account": preview.allowed_bank_account,
        "allowed_receivable_account": preview.allowed_receivable_account,
        "mapping_gate": preview.mapping_gate,
        "design_gate": preview.design_gate,
        "live_posting_allowed": 0,
        "future_activation_required": 1,
        "payment_entry_created": 0,
        "required_acknowledgement": ADAPTER_ACK,
        "acknowledgement_ok": ack_ok,
        "config": config,
        "config_errors": errors,
        "prior": prior,
        "guardrails_before": guard_before,
        "summary": summary,
        "lines": lines,
        "note": "Production adapter shell only. All live Payment Entry creation is hard-blocked.",
    }
    if int(dry_run or 0):
        return result

    doc = frappe.new_doc("NDIS PE Production Adapter Run")
    doc.adapter_run_id = make_adapter_run_id()
    doc.status = status
    doc.adapter_mode = "Hard Block Shell"
    doc.source_preview = preview.name
    doc.live_posting_allowed = 0
    doc.future_activation_required = 1
    doc.payment_entry_created = 0
    doc.company = preview.company
    doc.allowed_bank_account = preview.allowed_bank_account
    doc.allowed_receivable_account = preview.allowed_receivable_account
    doc.mapping_gate = preview.mapping_gate
    doc.design_gate = preview.design_gate
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.executed_on = now_datetime()
    doc.executed_by = frappe.session.user
    doc.adapter_score = score
    doc.adapter_status = final_adapter_status
    for fieldname in [
        "blocker_count",
        "warning_count",
        "pass_count",
        "info_count",
        "line_count",
        "hard_blocked_line_count",
        "validation_blocked_line_count",
        "duplicate_blocked_line_count",
        "rejected_blocked_line_count",
        "would_create_payment_entry_count",
        "actual_payment_entry_created_count",
        "preview_total_amount",
        "adapter_blocked_amount",
    ]:
        setattr(doc, fieldname, summary[fieldname])
    for fieldname, value in prior.items():
        setattr(doc, fieldname, value)
    doc.payment_entry_count_before = guard_before["payment_entry_count"]
    doc.payment_entry_count_after = count_dt("Payment Entry")
    doc.submitted_payment_entry_count_today = guard_before["submitted_payment_entry_count_today"]
    doc.payment_entry_gl_count = guard_before["payment_entry_gl_count"]
    doc.payment_entry_gl_count_today = guard_before["payment_entry_gl_count_today"]
    doc.submitted_journal_entry_count_today = guard_before["submitted_journal_entry_count_today"]
    doc.purchase_invoice_count_today = guard_before["purchase_invoice_count_today"]
    doc.required_acknowledgement = ADAPTER_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    for line in lines:
        row = frappe.new_doc("NDIS PE Production Adapter Run Line")
        row.adapter_run = doc.name
        for fieldname, value in line.items():
            setattr(row, fieldname, value)
        row.checked_on = doc.executed_on
        row.insert(ignore_permissions=True)

    guard_after = guardrails()
    frappe.db.set_value(
        "NDIS PE Production Adapter Run",
        doc.name,
        {
            "payment_entry_count_after": guard_after["payment_entry_count"],
            "submitted_payment_entry_count_today": guard_after["submitted_payment_entry_count_today"],
            "payment_entry_gl_count": guard_after["payment_entry_gl_count"],
            "payment_entry_gl_count_today": guard_after["payment_entry_gl_count_today"],
            "submitted_journal_entry_count_today": guard_after["submitted_journal_entry_count_today"],
            "purchase_invoice_count_today": guard_after["purchase_invoice_count_today"],
            "summary_json": safe_json({**result, "guardrails_after": guard_after}),
        },
        update_modified=False,
    )
    frappe.db.commit()
    result.update({"created": True, "adapter_run": doc.name, "adapter_run_id": doc.adapter_run_id, "guardrails_after": guard_after})
    return result


@frappe.whitelist()
def cancel_pe_production_adapter_run(adapter_run, reason=None):
    assert_action("cancel_pe_production_adapter_run")
    if not frappe.db.exists("NDIS PE Production Adapter Run", adapter_run):
        frappe.throw(_("PE Production Adapter Run not found: {0}").format(adapter_run))
    frappe.db.set_value(
        "NDIS PE Production Adapter Run",
        adapter_run,
        {
            "status": "Cancelled",
            "live_posting_allowed": 0,
            "payment_entry_created": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Production PE adapter run cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql("UPDATE `tabNDIS PE Production Adapter Run Line` SET status = 'Cancelled' WHERE adapter_run = %(adapter_run)s", {"adapter_run": adapter_run})
    frappe.db.commit()
    return {"adapter_run": adapter_run, "status": "Cancelled", "note": "Adapter run cancelled only. No accounting/payment records were changed."}


@frappe.whitelist()
def quick_pe_production_adapter_summary(limit=20):
    return {
        "runs": frappe.get_all(
            "NDIS PE Production Adapter Run",
            fields=[
                "name",
                "adapter_run_id",
                "status",
                "adapter_status",
                "adapter_score",
                "source_preview",
                "company",
                "hard_blocked_line_count",
                "validation_blocked_line_count",
                "duplicate_blocked_line_count",
                "rejected_blocked_line_count",
                "payment_entry_created",
                "payment_entry_gl_count",
                "live_posting_allowed",
                "executed_on",
                "executed_by",
            ],
            order_by="creation desc",
            limit=int(limit or 20),
        ),
        "lines": frappe.get_all(
            "NDIS PE Production Adapter Run Line",
            fields=[
                "name",
                "adapter_run",
                "status",
                "severity",
                "scenario_key",
                "event_type",
                "claim_outcome",
                "source_reference",
                "preview_payment_amount",
                "adapter_blocked_amount",
                "future_activation_blocked",
                "actual_payment_entry_created",
                "block_reason",
                "adapter_note",
            ],
            order_by="creation desc",
            limit=int(limit or 20),
        ),
        "required_acknowledgement": ADAPTER_ACK,
        "guardrails": guardrails(),
        "note": "Production PE adapter summary only. Live posting remains hard-blocked.",
    }


def execute_adapter_run_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    for field in ["status", "adapter_status"]:
        if filters.get(field):
            conditions.append(f"r.{field} = %({field})s")
            params[field] = filters.get(field)
    if filters.get("from_date"):
        conditions.append("DATE(r.executed_on) >= %(from_date)s")
        params["from_date"] = filters.get("from_date")
    if filters.get("to_date"):
        conditions.append("DATE(r.executed_on) <= %(to_date)s")
        params["to_date"] = filters.get("to_date")
    columns = [
        {"fieldname": "adapter_run", "label": _("Adapter Run"), "fieldtype": "Link", "options": "NDIS PE Production Adapter Run", "width": 220},
        {"fieldname": "adapter_run_id", "label": _("Adapter Run ID"), "fieldtype": "Data", "width": 330},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "adapter_status", "label": _("Adapter Status"), "fieldtype": "Data", "width": 240},
        {"fieldname": "adapter_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "source_preview", "label": _("Source Preview"), "fieldtype": "Link", "options": "NDIS PE Production Posting Preview", "width": 220},
        {"fieldname": "hard_blocked_line_count", "label": _("Hard Blocked"), "fieldtype": "Int", "width": 110},
        {"fieldname": "validation_blocked_line_count", "label": _("Validation Blocked"), "fieldtype": "Int", "width": 130},
        {"fieldname": "duplicate_blocked_line_count", "label": _("Duplicate Blocked"), "fieldtype": "Int", "width": 130},
        {"fieldname": "rejected_blocked_line_count", "label": _("Rejected Blocked"), "fieldtype": "Int", "width": 130},
        {"fieldname": "adapter_blocked_amount", "label": _("Adapter Blocked Amount"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "payment_entry_created", "label": _("PE Created"), "fieldtype": "Check", "width": 100},
        {"fieldname": "payment_entry_gl_count", "label": _("PE GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "live_posting_allowed", "label": _("Live Allowed"), "fieldtype": "Check", "width": 100},
        {"fieldname": "executed_on", "label": _("Executed On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT r.name AS adapter_run, r.adapter_run_id, r.status, r.adapter_status, r.adapter_score,
            r.source_preview, r.hard_blocked_line_count, r.validation_blocked_line_count,
            r.duplicate_blocked_line_count, r.rejected_blocked_line_count, r.adapter_blocked_amount,
            r.payment_entry_created, r.payment_entry_gl_count, r.live_posting_allowed, r.executed_on,
            %(currency)s AS currency
        FROM `tabNDIS PE Production Adapter Run` r
        {build_where(conditions)}
        ORDER BY r.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {"data": {"labels": [row.adapter_run_id for row in data[:20]], "datasets": [
        {"name": "Hard Blocked", "values": [int(row.hard_blocked_line_count or 0) for row in data[:20]]},
        {"name": "Validation Blocked", "values": [int(row.validation_blocked_line_count or 0) for row in data[:20]]},
        {"name": "Duplicate Blocked", "values": [int(row.duplicate_blocked_line_count or 0) for row in data[:20]]},
    ]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Adapter Runs"), "datatype": "Int"},
        {"value": sum(int(row.hard_blocked_line_count or 0) for row in data), "indicator": "Green", "label": _("Hard Blocked Lines"), "datatype": "Int"},
        {"value": sum(int(row.payment_entry_created or 0) for row in data), "indicator": "Red", "label": _("Payment Entries Created"), "datatype": "Int"},
        {"value": sum(int(row.payment_entry_gl_count or 0) for row in data), "indicator": "Red", "label": _("Payment Entry GL"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_adapter_line_report(filters=None, exceptions_only=0):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    for field in ["adapter_run", "status", "event_type"]:
        if filters.get(field):
            conditions.append(f"l.{field} = %({field})s")
            params[field] = filters.get(field)
    if exceptions_only:
        conditions.append("l.status IN ('Validation Blocked', 'Duplicate Blocked', 'Rejected Blocked', 'Warning')")
    columns = [
        {"fieldname": "line", "label": _("Line"), "fieldtype": "Link", "options": "NDIS PE Production Adapter Run Line", "width": 220},
        {"fieldname": "adapter_run", "label": _("Adapter Run"), "fieldtype": "Link", "options": "NDIS PE Production Adapter Run", "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 130},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "scenario_key", "label": _("Scenario"), "fieldtype": "Data", "width": 230},
        {"fieldname": "event_type", "label": _("Event Type"), "fieldtype": "Data", "width": 150},
        {"fieldname": "claim_outcome", "label": _("Outcome"), "fieldtype": "Data", "width": 130},
        {"fieldname": "source_reference", "label": _("Source Reference"), "fieldtype": "Data", "width": 220},
        {"fieldname": "preview_payment_amount", "label": _("Preview Payment"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "adapter_blocked_amount", "label": _("Blocked Amount"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "future_activation_blocked", "label": _("Activation Blocked"), "fieldtype": "Check", "width": 130},
        {"fieldname": "actual_payment_entry_created", "label": _("Actual PE Created"), "fieldtype": "Check", "width": 120},
        {"fieldname": "block_reason", "label": _("Block Reason"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "adapter_note", "label": _("Adapter Note"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT l.name AS line, l.adapter_run, l.status, l.severity, l.scenario_key, l.event_type,
            l.claim_outcome, l.source_reference, l.preview_payment_amount, l.adapter_blocked_amount,
            l.future_activation_blocked, l.actual_payment_entry_created, l.block_reason, l.adapter_note,
            %(currency)s AS currency
        FROM `tabNDIS PE Production Adapter Run Line` l
        {build_where(conditions)}
        ORDER BY CASE l.status WHEN 'Validation Blocked' THEN 1 WHEN 'Duplicate Blocked' THEN 2
            WHEN 'Rejected Blocked' THEN 3 WHEN 'Hard Blocked' THEN 4 ELSE 5 END, l.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart_map = {}
    for row in data:
        chart_map[row.status or "Info"] = chart_map.get(row.status or "Info", 0) + 1
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Lines", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Lines"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Hard Blocked"]), "indicator": "Green", "label": _("Hard Blocked"), "datatype": "Int"},
        {"value": len([row for row in data if row.future_activation_blocked]), "indicator": "Green", "label": _("Activation Blocked"), "datatype": "Int"},
        {"value": len([row for row in data if row.actual_payment_entry_created]), "indicator": "Red", "label": _("Actual PE Created"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_adapter_exception_report(filters=None):
    return execute_adapter_line_report(filters, exceptions_only=1)


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
