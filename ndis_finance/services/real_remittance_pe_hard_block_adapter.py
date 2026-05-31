import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


RUN_DOCTYPE = "NDIS Real Remittance PE Adapter Run"
LINE_DOCTYPE = "NDIS Real Remittance PE Adapter Run Line"
PREVIEW_DOCTYPE = "NDIS Real Remittance PE Preview"
PREVIEW_LINE_DOCTYPE = "NDIS Real Remittance PE Preview Line"
ADAPTER_ACK = "I_CONFIRM_PHASE6C_REAL_REMITTANCE_PE_ADAPTER_HARD_BLOCK_NO_POSTING"


def make_adapter_run_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-REAL-REMITTANCE-PE-ADAPTER-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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
        "sales_invoice_count_today": count_dt("Sales Invoice", {"creation": [">=", today()]}),
        "purchase_invoice_count_today": count_dt("Purchase Invoice", {"creation": [">=", today()]}),
        "live_enabled_policy_count": count_dt("NDIS PE Production Posting Policy", {"production_posting_enabled": 1}),
    }


def latest_preview():
    rows = frappe.get_all(
        PREVIEW_DOCTYPE,
        filters={
            "status": "Previewed",
            "preview_approved_for_adapter_phase": 1,
            "real_posting_allowed": 0,
            "actual_payment_entry_created_count": 0,
        },
        fields=[
            "name",
            "preview_id",
            "design_gate",
            "company",
            "bank_account",
            "receivable_account",
            "source_remittance_import",
            "batch_line_cap",
            "batch_amount_cap",
            "eligible_line_count",
            "blocked_line_count",
            "review_line_count",
            "eligible_amount",
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


def get_preview_lines(preview):
    if not preview:
        return []
    return frappe.get_all(
        PREVIEW_LINE_DOCTYPE,
        filters={"preview": preview},
        fields=[
            "name",
            "preview",
            "source_remittance_import",
            "source_remittance_line",
            "classification",
            "preview_status",
            "block_reason",
            "claim_line",
            "sales_invoice",
            "company",
            "customer",
            "source_amount",
            "allocatable_amount",
            "invoice_outstanding_amount",
            "would_create_payment_entry",
            "payment_entry_created",
        ],
        order_by="creation asc",
        limit=5000,
    )


def classify_adapter_line(row):
    result = {
        "preview_line": row.name,
        "preview": row.preview,
        "source_remittance_line": row.source_remittance_line,
        "source_classification": row.classification,
        "source_preview_status": row.preview_status,
        "adapter_decision": "Validation Blocked",
        "adapter_status": "Validation Blocked",
        "decision_reason": row.block_reason or "Preview line is not eligible.",
        "claim_line": row.claim_line,
        "sales_invoice": row.sales_invoice,
        "company": row.company,
        "customer": row.customer,
        "source_amount": flt(row.source_amount),
        "allocatable_amount": flt(row.allocatable_amount),
        "invoice_outstanding_amount": flt(row.invoice_outstanding_amount),
        "would_create_payment_entry": 0,
        "payment_entry_created": 0,
        "gl_created": 0,
        "hard_block_applied": 1,
    }

    if row.preview_status == "Eligible" and int(row.would_create_payment_entry or 0) and flt(row.allocatable_amount) > 0:
        result.update(
            {
                "adapter_decision": "Would Create PE - Hard Blocked",
                "adapter_status": "Hard Blocked",
                "decision_reason": "Line is structurally eligible, but Phase 6C hard-block prevents actual Payment Entry creation.",
                "would_create_payment_entry": 1,
            }
        )
    elif row.preview_status == "Review":
        result.update(
            {
                "adapter_decision": "Review Blocked",
                "adapter_status": "Review Blocked",
                "decision_reason": row.block_reason or "Preview line requires review and is blocked by adapter.",
            }
        )
    elif row.preview_status == "Cancelled":
        result.update(
            {
                "adapter_decision": "Cancelled",
                "adapter_status": "Cancelled",
                "decision_reason": "Preview line is cancelled.",
            }
        )

    return result


def summarise_adapter_lines(lines):
    summary = {
        "source_preview_line_count": len(lines),
        "eligible_preview_line_count": 0,
        "blocked_preview_line_count": 0,
        "review_preview_line_count": 0,
        "hard_blocked_line_count": 0,
        "validation_blocked_line_count": 0,
        "review_blocked_line_count": 0,
        "would_create_payment_entry_count": 0,
        "would_create_payment_entry_amount": 0,
        "actual_payment_entry_created_count": 0,
        "actual_gl_created_count": 0,
        "group_count": 0,
        "source_eligible_pending": 0,
    }
    groups = set()

    for line in lines:
        source_status = line.get("source_preview_status")
        decision = line.get("adapter_decision")
        if source_status == "Eligible":
            summary["eligible_preview_line_count"] += 1
        elif source_status == "Blocked":
            summary["blocked_preview_line_count"] += 1
        elif source_status == "Review":
            summary["review_preview_line_count"] += 1

        if decision == "Would Create PE - Hard Blocked":
            summary["hard_blocked_line_count"] += 1
            summary["would_create_payment_entry_count"] += 1
            summary["would_create_payment_entry_amount"] += flt(line.get("allocatable_amount") or 0)
            groups.add((line.get("company"), line.get("customer")))
        elif decision == "Review Blocked":
            summary["review_blocked_line_count"] += 1
        elif decision == "Validation Blocked":
            summary["validation_blocked_line_count"] += 1

        summary["actual_payment_entry_created_count"] += int(line.get("payment_entry_created") or 0)
        summary["actual_gl_created_count"] += int(line.get("gl_created") or 0)

    summary["group_count"] = len(groups)
    summary["source_eligible_pending"] = int(summary["eligible_preview_line_count"] == 0)
    return summary


def evaluate_preconditions(items, preview_doc, config, guard_before):
    if config["production_mode"]:
        add_item(items, "Blocker", "Critical", "Site Config", "production_mode", "Production mode", "Production mode is enabled.")
    else:
        add_item(items, "Pass", "Low", "Site Config", "production_mode", "Production mode", "Production mode remains disabled.")

    if config["live_pe_enabled"]:
        add_item(items, "Blocker", "Critical", "Site Config", "live_pe_enabled", "Live PE posting config", "Live Payment Entry posting config is enabled.")
    else:
        add_item(items, "Pass", "Low", "Site Config", "live_pe_enabled", "Live PE posting config", "Live Payment Entry posting remains disabled.")

    if guard_before["live_enabled_policy_count"]:
        add_item(items, "Blocker", "Critical", "Policy", "live_enabled_policy", "Live-enabled PE policy", f"{guard_before['live_enabled_policy_count']} live-enabled policy record(s) found.")
    else:
        add_item(items, "Pass", "Low", "Policy", "live_enabled_policy", "Live-enabled PE policy", "Zero live-enabled policy records.")

    if preview_doc:
        add_item(
            items,
            "Pass",
            "Low",
            "Preview Evidence",
            "phase6b_preview",
            "Approved Phase 6B preview",
            f"Approved preview found: {preview_doc.preview_id}.",
            None,
            PREVIEW_DOCTYPE,
            preview_doc.name,
        )
    else:
        add_item(
            items,
            "Blocker",
            "Critical",
            "Preview Evidence",
            "phase6b_preview",
            "Approved Phase 6B preview",
            "No approved Phase 6B preview found.",
            "Complete Phase 6B before Phase 6C.",
        )


def evaluate_adapter_summary(items, adapter_summary):
    if adapter_summary["source_preview_line_count"] > 0:
        add_item(items, "Pass", "Low", "Adapter Input", "preview_lines", "Preview lines loaded", f"{adapter_summary['source_preview_line_count']} preview line(s) loaded.")
    else:
        add_item(items, "Warning", "Medium", "Adapter Input", "preview_lines", "Preview lines loaded", "No preview lines found.")

    if adapter_summary["hard_blocked_line_count"] > 0:
        add_item(items, "Pass", "Low", "Hard Block", "hard_blocked_lines", "Eligible lines hard-blocked", f"{adapter_summary['hard_blocked_line_count']} eligible line(s) were hard-blocked.")
    else:
        add_item(items, "Info", "Low", "Hard Block", "source_eligible_pending", "Eligible source pending", "No eligible preview lines exist yet; adapter is structurally ready but source eligibility is pending.")

    if adapter_summary["validation_blocked_line_count"] > 0:
        add_item(items, "Info", "Low", "Validation Block", "validation_blocked", "Validation-blocked lines", f"{adapter_summary['validation_blocked_line_count']} line(s) blocked from Phase 6B validation.")

    if adapter_summary["review_blocked_line_count"] > 0:
        add_item(items, "Info", "Low", "Review Block", "review_blocked", "Review-blocked lines", f"{adapter_summary['review_blocked_line_count']} line(s) require review and were blocked.")

    if adapter_summary["actual_payment_entry_created_count"] > 0:
        add_item(items, "Blocker", "Critical", "Movement Guardrail", "actual_pe_created", "Actual Payment Entry created", f"{adapter_summary['actual_payment_entry_created_count']} Payment Entry record(s) created.")
    else:
        add_item(items, "Pass", "Low", "Movement Guardrail", "actual_pe_created", "Actual Payment Entry created", "Zero.")

    if adapter_summary["actual_gl_created_count"] > 0:
        add_item(items, "Blocker", "Critical", "Movement Guardrail", "actual_gl_created", "Actual GL created", f"{adapter_summary['actual_gl_created_count']} GL row(s) created.")
    else:
        add_item(items, "Pass", "Low", "Movement Guardrail", "actual_gl_created", "Zero actual GL created", "Zero.")


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


def adapter_status(score, blockers, warnings, hard_blocked_count, source_eligible_pending):
    if blockers:
        return "Blocked"
    if source_eligible_pending:
        return "Structural Ready - Source Eligible Pending"
    if hard_blocked_count > 0:
        return "Ready For Activation Gate"
    if warnings:
        return "Hard Block Verified"
    if score >= 95:
        return "Hard Block Verified"
    return "Needs Review"


def create_adapter_lines(doc, adapter_lines):
    for line in adapter_lines:
        row = frappe.new_doc(LINE_DOCTYPE)
        row.adapter_run = doc.name
        row.preview = doc.preview
        row.preview_line = line.get("preview_line")
        row.source_remittance_line = line.get("source_remittance_line")
        row.source_classification = line.get("source_classification")
        row.source_preview_status = line.get("source_preview_status")
        row.adapter_decision = line.get("adapter_decision")
        row.adapter_status = line.get("adapter_status")
        row.decision_reason = line.get("decision_reason")
        row.claim_line = line.get("claim_line")
        row.sales_invoice = line.get("sales_invoice")
        row.company = line.get("company")
        row.customer = line.get("customer")
        row.source_amount = flt(line.get("source_amount") or 0)
        row.allocatable_amount = flt(line.get("allocatable_amount") or 0)
        row.invoice_outstanding_amount = flt(line.get("invoice_outstanding_amount") or 0)
        row.would_create_payment_entry = int(line.get("would_create_payment_entry") or 0)
        row.payment_entry_created = 0
        row.gl_created = 0
        row.hard_block_applied = int(line.get("hard_block_applied") or 0)
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def create_real_remittance_payment_entries(*args, **kwargs):
    assert_action("create_real_remittance_payment_entries")
    frappe.throw(
        _("Phase 6C hard block: real remittance Payment Entry creation is disabled. No Payment Entry was created.")
    )


@frappe.whitelist()
def run_real_remittance_pe_hard_block_adapter(preview=None, dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_real_remittance_pe_hard_block_adapter")

    if preview:
        if not frappe.db.exists(PREVIEW_DOCTYPE, preview):
            frappe.throw(_("Preview not found: {0}").format(preview))
        preview_doc = frappe.get_doc(PREVIEW_DOCTYPE, preview)
    else:
        latest = latest_preview()
        preview_doc = frappe.get_doc(PREVIEW_DOCTYPE, latest.name) if latest else None

    config = config_state()
    guard_before = guardrails()
    source_lines = get_preview_lines(preview_doc.name if preview_doc else None)
    adapter_lines = [classify_adapter_line(row) for row in source_lines]
    adapter_summary = summarise_adapter_lines(adapter_lines)

    items = []
    evaluate_preconditions(items, preview_doc, config, guard_before)
    evaluate_adapter_summary(items, adapter_summary)

    ack_ok = acknowledgement == ADAPTER_ACK
    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "adapter_ack", "Adapter acknowledgement", "Exact acknowledgement supplied.")
    elif int(dry_run or 0):
        add_item(items, "Info", "Low", "Acknowledgement", "adapter_ack", "Adapter acknowledgement", f"Required acknowledgement for approval: {ADAPTER_ACK}")
    else:
        add_item(
            items,
            "Warning",
            "Medium",
            "Acknowledgement",
            "adapter_ack",
            "Adapter acknowledgement",
            f"Required acknowledgement not supplied. Required: {ADAPTER_ACK}",
            "Provide exact acknowledgement to create approved Phase 6C adapter audit records.",
        )

    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    adapter_status_text = adapter_status(
        score,
        item_summary["blocker_count"],
        item_summary["warning_count"],
        adapter_summary["hard_blocked_line_count"],
        adapter_summary["source_eligible_pending"],
    )
    status_text = "Hard Blocked" if ack_ok and item_summary["blocker_count"] == 0 else ("Blocked" if item_summary["blocker_count"] else "Needs Review")
    approved = int(ack_ok and item_summary["blocker_count"] == 0)

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": status_text,
        "adapter_status": adapter_status_text,
        "adapter_score": score,
        "adapter_approved_for_activation_gate": approved,
        "real_posting_allowed": 0,
        "direct_live_creation_blocked": 1,
        "preview": preview_doc.name if preview_doc else None,
        "preview_id": preview_doc.preview_id if preview_doc else None,
        "design_gate": preview_doc.design_gate if preview_doc else None,
        "source_remittance_import": preview_doc.source_remittance_import if preview_doc else None,
        "company": preview_doc.company if preview_doc else None,
        "bank_account": preview_doc.bank_account if preview_doc else None,
        "receivable_account": preview_doc.receivable_account if preview_doc else None,
        "batch_line_cap": int(preview_doc.batch_line_cap or 0) if preview_doc else 0,
        "batch_amount_cap": flt(preview_doc.batch_amount_cap or 0) if preview_doc else 0,
        "adapter_summary": adapter_summary,
        "summary": item_summary,
        "items": items,
        "guardrails_before": guard_before,
        "guardrails_after": guardrails(),
        "config": config,
        "required_acknowledgement": ADAPTER_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 6C hard-block adapter only. No Payment Entry, GL Entry, invoice, allocation, Xero, ABA, STP, payroll, or email movement is created.",
    }

    if int(dry_run or 0):
        result["adapter_lines"] = adapter_lines[:50]
        return result

    doc = frappe.new_doc(RUN_DOCTYPE)
    doc.adapter_run_id = make_adapter_run_id()
    doc.status = status_text
    doc.adapter_type = "Limited Real Remittance To Payment Entry"
    doc.adapter_approved_for_activation_gate = approved
    doc.real_posting_allowed = 0
    doc.direct_live_creation_blocked = 1
    doc.design_gate = result["design_gate"]
    doc.preview = result["preview"]
    doc.source_remittance_import = result["source_remittance_import"]
    doc.company = result["company"]
    doc.bank_account = result["bank_account"]
    doc.receivable_account = result["receivable_account"]
    doc.batch_line_cap = result["batch_line_cap"]
    doc.batch_amount_cap = result["batch_amount_cap"]

    for key, value in adapter_summary.items():
        if doc.meta.has_field(key):
            setattr(doc, key, value)

    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.adapter_score = score
    doc.adapter_status = adapter_status_text
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
    doc.required_acknowledgement = ADAPTER_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    create_adapter_lines(doc, adapter_lines)

    guard_after = guardrails()
    frappe.db.set_value(
        RUN_DOCTYPE,
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
    result["adapter_run"] = doc.name
    result["adapter_run_id"] = doc.adapter_run_id
    result["guardrails_after"] = guard_after
    return result


@frappe.whitelist()
def cancel_real_remittance_pe_hard_block_adapter(adapter_run, reason=None):
    assert_action("cancel_real_remittance_pe_hard_block_adapter")
    if not frappe.db.exists(RUN_DOCTYPE, adapter_run):
        frappe.throw(_("Adapter run not found: {0}").format(adapter_run))

    doc = frappe.get_doc(RUN_DOCTYPE, adapter_run)
    if doc.status == "Cancelled":
        return {"adapter_run": adapter_run, "status": "Cancelled", "note": "Already cancelled."}

    frappe.db.set_value(
        RUN_DOCTYPE,
        adapter_run,
        {
            "status": "Cancelled",
            "adapter_approved_for_activation_gate": 0,
            "real_posting_allowed": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 6C adapter run cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(
        f"""
        UPDATE `tab{LINE_DOCTYPE}`
        SET adapter_status = 'Cancelled',
            adapter_decision = 'Cancelled'
        WHERE adapter_run = %(adapter_run)s
        """,
        {"adapter_run": adapter_run},
    )
    frappe.db.commit()
    return {
        "adapter_run": adapter_run,
        "status": "Cancelled",
        "note": "Adapter audit run cancelled only. No accounting movement occurred.",
    }


@frappe.whitelist()
def quick_real_remittance_pe_adapter_summary(limit=20):
    runs = frappe.get_all(
        RUN_DOCTYPE,
        fields=[
            "name",
            "adapter_run_id",
            "status",
            "adapter_status",
            "adapter_score",
            "adapter_approved_for_activation_gate",
            "real_posting_allowed",
            "preview",
            "source_preview_line_count",
            "eligible_preview_line_count",
            "hard_blocked_line_count",
            "validation_blocked_line_count",
            "source_eligible_pending",
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
    lines = frappe.get_all(
        LINE_DOCTYPE,
        fields=[
            "name",
            "adapter_run",
            "preview_line",
            "source_classification",
            "adapter_decision",
            "adapter_status",
            "decision_reason",
            "sales_invoice",
            "allocatable_amount",
            "would_create_payment_entry",
            "payment_entry_created",
            "gl_created",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "runs": runs,
        "lines": lines,
        "required_acknowledgement": ADAPTER_ACK,
        "guardrails": guardrails(),
        "config": config_state(),
        "note": "Phase 6C adapter summary only. Real Payment Entry creation remains hard-blocked.",
    }


def execute_run_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("status"):
        conditions.append("r.status = %(status)s")
        params["status"] = filters.status
    if filters.get("from_date"):
        conditions.append("DATE(r.checked_on) >= %(from_date)s")
        params["from_date"] = filters.from_date
    if filters.get("to_date"):
        conditions.append("DATE(r.checked_on) <= %(to_date)s")
        params["to_date"] = filters.to_date

    columns = [
        {"fieldname": "adapter_run", "label": _("Adapter Run"), "fieldtype": "Link", "options": RUN_DOCTYPE, "width": 220},
        {"fieldname": "adapter_run_id", "label": _("Adapter Run ID"), "fieldtype": "Data", "width": 360},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 130},
        {"fieldname": "adapter_status", "label": _("Adapter Status"), "fieldtype": "Data", "width": 260},
        {"fieldname": "adapter_approved_for_activation_gate", "label": _("Approved For Gate"), "fieldtype": "Check", "width": 130},
        {"fieldname": "real_posting_allowed", "label": _("Real Posting Allowed"), "fieldtype": "Check", "width": 150},
        {"fieldname": "source_preview_line_count", "label": _("Source Lines"), "fieldtype": "Int", "width": 100},
        {"fieldname": "hard_blocked_line_count", "label": _("Hard-blocked"), "fieldtype": "Int", "width": 110},
        {"fieldname": "validation_blocked_line_count", "label": _("Validation Blocked"), "fieldtype": "Int", "width": 140},
        {"fieldname": "source_eligible_pending", "label": _("Source Pending"), "fieldtype": "Check", "width": 120},
        {"fieldname": "would_create_payment_entry_count", "label": _("Would Create PE"), "fieldtype": "Int", "width": 130},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE Created"), "fieldtype": "Int", "width": 140},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL Created"), "fieldtype": "Int", "width": 130},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            r.name AS adapter_run,
            r.adapter_run_id,
            r.status,
            r.adapter_status,
            r.adapter_approved_for_activation_gate,
            r.real_posting_allowed,
            r.source_preview_line_count,
            r.hard_blocked_line_count,
            r.validation_blocked_line_count,
            r.source_eligible_pending,
            r.would_create_payment_entry_count,
            r.actual_payment_entry_created_count,
            r.actual_gl_created_count,
            r.checked_on
        FROM `tab{RUN_DOCTYPE}` r
        {build_where(conditions)}
        ORDER BY r.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.adapter_run_id for row in data[:20]],
            "datasets": [
                {"name": "Hard-blocked", "values": [int(row.hard_blocked_line_count or 0) for row in data[:20]]},
                {"name": "Validation Blocked", "values": [int(row.validation_blocked_line_count or 0) for row in data[:20]]},
                {"name": "Actual PE Created", "values": [int(row.actual_payment_entry_created_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Adapter Runs"), "datatype": "Int"},
        {"value": sum(int(row.adapter_approved_for_activation_gate or 0) for row in data), "indicator": "Green", "label": _("Approved For Gate"), "datatype": "Int"},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PE Created"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL Created"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_line_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("adapter_run"):
        conditions.append("l.adapter_run = %(adapter_run)s")
        params["adapter_run"] = filters.adapter_run
    if filters.get("adapter_status"):
        conditions.append("l.adapter_status = %(adapter_status)s")
        params["adapter_status"] = filters.adapter_status
    if filters.get("adapter_decision"):
        conditions.append("l.adapter_decision = %(adapter_decision)s")
        params["adapter_decision"] = filters.adapter_decision

    columns = [
        {"fieldname": "line", "label": _("Adapter Line"), "fieldtype": "Link", "options": LINE_DOCTYPE, "width": 220},
        {"fieldname": "adapter_run", "label": _("Adapter Run"), "fieldtype": "Link", "options": RUN_DOCTYPE, "width": 220},
        {"fieldname": "preview_line", "label": _("Preview Line"), "fieldtype": "Link", "options": PREVIEW_LINE_DOCTYPE, "width": 220},
        {"fieldname": "source_classification", "label": _("Source Classification"), "fieldtype": "Data", "width": 220},
        {"fieldname": "adapter_decision", "label": _("Adapter Decision"), "fieldtype": "Data", "width": 240},
        {"fieldname": "adapter_status", "label": _("Adapter Status"), "fieldtype": "Data", "width": 160},
        {"fieldname": "sales_invoice", "label": _("Sales Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 170},
        {"fieldname": "allocatable_amount", "label": _("Allocatable"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "would_create_payment_entry", "label": _("Would Create PE"), "fieldtype": "Check", "width": 120},
        {"fieldname": "payment_entry_created", "label": _("PE Created"), "fieldtype": "Check", "width": 100},
        {"fieldname": "gl_created", "label": _("GL Created"), "fieldtype": "Check", "width": 100},
        {"fieldname": "decision_reason", "label": _("Decision Reason"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            l.name AS line,
            l.adapter_run,
            l.preview_line,
            l.source_classification,
            l.adapter_decision,
            l.adapter_status,
            l.sales_invoice,
            l.allocatable_amount,
            l.would_create_payment_entry,
            l.payment_entry_created,
            l.gl_created,
            l.decision_reason,
            %(currency)s AS currency
        FROM `tab{LINE_DOCTYPE}` l
        {build_where(conditions)}
        ORDER BY l.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart_map = {}
    for row in data:
        key = row.adapter_decision or "Unknown"
        chart_map[key] = chart_map.get(key, 0) + 1
    chart = {
        "data": {
            "labels": list(chart_map.keys()),
            "datasets": [{"name": "Lines", "values": list(chart_map.values())}],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Lines"), "datatype": "Int"},
        {"value": len([row for row in data if row.adapter_status == "Hard Blocked"]), "indicator": "Green", "label": _("Hard-blocked"), "datatype": "Int"},
        {"value": len([row for row in data if row.adapter_status == "Validation Blocked"]), "indicator": "Orange", "label": _("Validation Blocked"), "datatype": "Int"},
        {"value": sum(int(row.payment_entry_created or 0) for row in data), "indicator": "Red", "label": _("Actual PE Created"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_exception_report(filters=None):
    filters = frappe._dict(filters or {})
    filters["adapter_status"] = filters.get("adapter_status") or "Validation Blocked"
    return execute_line_report(filters)


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
