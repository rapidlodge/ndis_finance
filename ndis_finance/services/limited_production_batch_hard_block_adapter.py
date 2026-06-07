import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


ADAPTER_ACK = "I_CONFIRM_PHASE9D_HARD_BLOCK_LIMITED_PRODUCTION_BATCH_ADAPTER_NO_POSTING"


def make_adapter_run_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-LIMITED-PROD-BATCH-ADAPTER-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_policy_preview():
    rows = frappe.get_all(
        "NDIS Limited Production Batch Policy Preview",
        filters={
            "status": "Previewed",
            "limited_policy_preview_complete": 1,
            "ready_for_limited_hard_block_adapter": 1,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
        },
        fields=[
            "name",
            "policy_preview_id",
            "policy_design",
            "policy_review_gate",
            "phase8g_freeze",
            "source_preview",
            "activation_gate",
            "adapter_run",
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
            "blocked_line_count",
            "duplicate_line_count",
            "would_create_payment_entry_count",
            "would_create_reference_count",
            "preview_amount",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )

    return rows[0] if rows else None


def existing_completed_adapter(policy_preview):
    rows = frappe.get_all(
        "NDIS Limited Production Batch Adapter Run",
        filters={
            "policy_preview": policy_preview,
            "status": "Hard Blocked",
            "limited_adapter_approved_for_activation_gate": 1,
            "ready_for_limited_activation_gate": 1,
        },
        fields=["name", "adapter_run_id"],
        limit=1,
    )

    return rows[0] if rows else None


def get_preview_lines(policy_preview):
    if not policy_preview:
        return []

    return frappe.get_all(
        "NDIS Limited Production Batch Policy Preview Line",
        filters={"policy_preview": policy_preview},
        fields=[
            "name",
            "line_no",
            "line_status",
            "sales_invoice",
            "claim_line",
            "remittance_line",
            "invoice_outstanding",
            "allocatable_amount",
            "would_create_payment_entry",
            "would_create_reference",
            "block_reason",
            "policy_live_enabled",
        ],
        order_by="line_no asc, creation asc",
    )


@frappe.whitelist()
def attempt_limited_production_batch_live_creation():
    assert_action("attempt_limited_production_batch_live_creation")
    frappe.throw(
        _("Phase 9D hard block: limited production batch live Payment Entry creation is disabled. Use preview, adapter, activation, smoke, rollback, and freeze gates only."),
        title=_("Limited Production Batch Live Creation Blocked"),
    )


def direct_hard_block_proof():
    before = guardrails()

    try:
        attempt_limited_production_batch_live_creation()
    except Exception as exc:
        after = guardrails()

        no_movement = (
            before["payment_entry_count"] == after["payment_entry_count"]
            and before["payment_entry_gl_count"] == after["payment_entry_gl_count"]
        )

        return {
            "blocked": 1,
            "message": str(exc),
            "no_movement": 1 if no_movement else 0,
            "before": before,
            "after": after,
        }

    return {
        "blocked": 0,
        "message": "Direct live creation did not block.",
        "no_movement": 0,
        "before": before,
        "after": guardrails(),
    }


def add_item(items, status, severity, category, check_key, check_label, detail):
    items.append(
        {
            "status": status,
            "severity": severity,
            "category": category,
            "check_key": check_key,
            "check_label": check_label,
            "detail": detail,
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


def validate_adapter_source(preview, preview_lines, guard, hard_block):
    issues = []

    if not preview:
        issues.append("No completed Phase 9C policy preview found.")
        return issues

    if existing_completed_adapter(preview.name):
        issues.append("A completed Phase 9D adapter already exists for this Phase 9C preview.")

    if int(preview.eligible_line_count or 0) <= 0:
        issues.append("Phase 9C preview has no eligible lines.")

    if int(preview.would_create_payment_entry_count or 0) != 1:
        issues.append("Phase 9C preview must would-create exactly one Payment Entry.")

    if int(preview.would_create_reference_count or 0) != 2:
        issues.append("Phase 9C preview must would-create exactly two references.")

    if flt(preview.preview_amount or 0, 2) != 2:
        issues.append("Phase 9C preview amount must be 2.00.")

    eligible_lines = [row for row in preview_lines if row.line_status == "Eligible"]

    if len(eligible_lines) != int(preview.eligible_line_count or 0):
        issues.append("Eligible preview line count does not match Phase 9C preview header.")

    for row in eligible_lines:
        if int(row.policy_live_enabled or 0):
            issues.append(f"Preview line {row.line_no} is live enabled.")
        if not int(row.would_create_payment_entry or 0):
            issues.append(f"Preview line {row.line_no} is missing would_create_payment_entry.")
        if not int(row.would_create_reference or 0):
            issues.append(f"Preview line {row.line_no} is missing would_create_reference.")
        if flt(row.allocatable_amount or 0, 2) <= 0:
            issues.append(f"Preview line {row.line_no} has non-positive allocatable amount.")

    if not int(hard_block.get("blocked") or 0):
        issues.append("Direct live creation hard block did not fire.")

    if not int(hard_block.get("no_movement") or 0):
        issues.append("Direct live creation hard block did not preserve movement guardrails.")

    if guard["production_batch_enabled_policy_count"] != 0:
        issues.append("Controlled production batch enabled policy count is not zero.")

    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count is not zero.")

    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today is not zero.")

    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today is not zero.")

    return issues


def adapter_line_rows(preview, preview_lines):
    rows = []

    for row in preview_lines:
        status = "Validation Blocked"
        hard_block_verified = 0
        block_reason = row.block_reason or "Preview line is not eligible."

        if row.line_status == "Eligible":
            status = "Hard Blocked"
            hard_block_verified = 1
            block_reason = "Would-create line deliberately hard-blocked by Phase 9D adapter."

        elif row.line_status == "Duplicate":
            status = "Duplicate Blocked"
            block_reason = row.block_reason or "Duplicate line blocked by Phase 9D adapter."

        rows.append(
            frappe._dict(
                {
                    "line_no": row.line_no,
                    "line_label": f"Phase 9D Adapter Line {row.line_no}",
                    "line_status": status,
                    "block_reason": block_reason,
                    "policy_preview": preview.name if preview else None,
                    "policy_preview_line": row.name,
                    "sales_invoice": row.sales_invoice,
                    "claim_line": row.claim_line,
                    "remittance_line": row.remittance_line,
                    "invoice_outstanding": flt(row.invoice_outstanding or 0, 2),
                    "allocatable_amount": flt(row.allocatable_amount or 0, 2),
                    "would_create_payment_entry": int(row.would_create_payment_entry or 0),
                    "would_create_reference": int(row.would_create_reference or 0),
                    "actual_payment_entry_created": 0,
                    "actual_gl_created": 0,
                    "policy_live_enabled": 0,
                    "hard_block_verified": hard_block_verified,
                }
            )
        )

    return rows


def summarise_adapter_lines(lines):
    hard = [row for row in lines if row.line_status == "Hard Blocked"]
    validation = [row for row in lines if row.line_status == "Validation Blocked"]
    duplicate = [row for row in lines if row.line_status == "Duplicate Blocked"]

    return {
        "source_line_count": len(lines),
        "eligible_line_count": len(hard),
        "hard_blocked_line_count": len(hard),
        "validation_blocked_line_count": len(validation),
        "duplicate_blocked_line_count": len(duplicate),
        "would_create_payment_entry_count": 1 if hard else 0,
        "would_create_reference_count": len([row for row in hard if int(row.would_create_reference or 0)]),
        "would_create_payment_entry_amount": flt(sum(flt(row.allocatable_amount or 0) for row in hard), 2),
    }


def build_items(preview, config, guard, issues, summary, hard_block, ack_ok):
    items = []

    if preview:
        add_item(items, "Pass", "Low", "Policy Preview", "phase9c_preview_exists", "Phase 9C preview exists", f"Preview found: {preview.policy_preview_id}.")
    else:
        add_item(items, "Blocker", "Critical", "Policy Preview", "phase9c_preview_exists", "Phase 9C preview exists", "No completed Phase 9C preview found.")

    if not issues:
        add_item(items, "Pass", "Low", "Adapter Source", "adapter_source_valid", "Adapter source valid", "Phase 9C preview is valid for hard-block adapter.")
    else:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Adapter Source", "adapter_source_valid", "Adapter source valid", issue)

    if int(hard_block.get("blocked") or 0):
        add_item(items, "Pass", "Low", "Hard Block", "direct_live_creation_blocked", "Direct live creation blocked", "Direct live creation function throws controlled hard-block.")
    else:
        add_item(items, "Blocker", "Critical", "Hard Block", "direct_live_creation_blocked", "Direct live creation blocked", "Direct live creation was not blocked.")

    if summary["would_create_payment_entry_count"] == 1:
        add_item(items, "Pass", "Low", "Adapter Evidence", "would_create_pe_count", "Would-create PE count", "Adapter would-create evidence shows exactly one Payment Entry.")
    else:
        add_item(items, "Blocker", "Critical", "Adapter Evidence", "would_create_pe_count", "Would-create PE count", f"Adapter would-create evidence shows {summary['would_create_payment_entry_count']} Payment Entries.")

    if summary["would_create_reference_count"] == 2:
        add_item(items, "Pass", "Low", "Adapter Evidence", "would_create_reference_count", "Would-create reference count", "Adapter would-create evidence shows two references.")
    else:
        add_item(items, "Blocker", "Critical", "Adapter Evidence", "would_create_reference_count", "Would-create reference count", f"Adapter would-create reference count is {summary['would_create_reference_count']}.")

    if flt(summary["would_create_payment_entry_amount"], 2) == 2:
        add_item(items, "Pass", "Low", "Adapter Evidence", "would_create_amount", "Would-create amount", "Adapter would-create amount is 2.00.")
    else:
        add_item(items, "Blocker", "Critical", "Adapter Evidence", "would_create_amount", "Would-create amount", f"Adapter would-create amount is {summary['would_create_payment_entry_amount']}.")

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
        add_item(items, "Pass", "Low", "Acknowledgement", "adapter_ack", "Adapter acknowledgement", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "adapter_ack", "Adapter acknowledgement", f"Required acknowledgement not supplied: {ADAPTER_ACK}")

    return items


def create_adapter_lines(doc, lines):
    for row in lines:
        line = frappe.new_doc("NDIS Limited Production Batch Adapter Run Line")
        line.adapter_run = doc.name
        line.line_no = row.line_no
        line.line_label = row.line_label
        line.line_status = row.line_status
        line.block_reason = row.block_reason
        line.policy_preview = row.policy_preview
        line.policy_preview_line = row.policy_preview_line
        line.sales_invoice = row.sales_invoice
        line.claim_line = row.claim_line
        line.remittance_line = row.remittance_line
        line.invoice_outstanding = row.invoice_outstanding
        line.allocatable_amount = row.allocatable_amount
        line.would_create_payment_entry = row.would_create_payment_entry
        line.would_create_reference = row.would_create_reference
        line.actual_payment_entry_created = 0
        line.actual_gl_created = 0
        line.policy_live_enabled = 0
        line.hard_block_verified = row.hard_block_verified
        line.checked_on = doc.checked_on
        line.insert(ignore_permissions=True)


@frappe.whitelist()
def run_limited_production_batch_hard_block_adapter(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_limited_production_batch_hard_block_adapter")

    preview = latest_policy_preview()
    preview_lines = get_preview_lines(preview.name) if preview else []
    adapter_lines = adapter_line_rows(preview, preview_lines) if preview else []
    adapter_summary = summarise_adapter_lines(adapter_lines)

    config = config_state()
    guard_before = guardrails()
    hard_block = direct_hard_block_proof()
    ack_ok = acknowledgement == ADAPTER_ACK

    source_issues = validate_adapter_source(preview, preview_lines, guard_before, hard_block)
    items = build_items(preview, config, guard_before, source_issues, adapter_summary, hard_block, ack_ok)

    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    approved = int(ack_ok and item_summary["blocker_count"] == 0 and preview is not None)

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Hard Blocked" if approved else "Needs Review",
        "adapter_status": "Ready For Limited Activation Gate" if approved else "Needs Review",
        "limited_adapter_approved_for_activation_gate": approved,
        "ready_for_limited_activation_gate": approved,
        "direct_live_creation_blocked": int(hard_block.get("blocked") or 0),
        "production_batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "policy_live_enabled": 0,
        "policy_preview": preview.name if preview else None,
        "policy_design": preview.policy_design if preview else None,
        "policy_review_gate": preview.policy_review_gate if preview else None,
        "phase8g_freeze": preview.phase8g_freeze if preview else None,
        "source_preview": preview.source_preview if preview else None,
        "activation_gate": preview.activation_gate if preview else None,
        "source_adapter_run": preview.adapter_run if preview else None,
        "design_gate": preview.design_gate if preview else None,
        "company": preview.company if preview else None,
        "customer": preview.customer if preview else None,
        "policy_mode": preview.policy_mode if preview else "Limited Controlled Production Batch",
        "max_batch_lines": int(preview.max_batch_lines or 0) if preview else 0,
        "max_batch_amount": flt(preview.max_batch_amount or 0) if preview else 0,
        "max_payment_entry_count": int(preview.max_payment_entry_count or 0) if preview else 0,
        "allowed_payment_type": preview.allowed_payment_type if preview else "Receive",
        "allowed_reference_doctype": preview.allowed_reference_doctype if preview else "Sales Invoice",
        **adapter_summary,
        "actual_payment_entry_created_count": 0,
        "actual_gl_created_count": 0,
        "adapter_score": score,
        **item_summary,
        "items": items,
        "adapter_lines": adapter_lines,
        "hard_block": hard_block,
        "guardrails_before": guard_before,
        "guardrails_after": guardrails(),
        "config": config,
        "required_acknowledgement": ADAPTER_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 9D creates hard-block adapter evidence only. It creates no Payment Entry and no GL.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["adapter_status"] = "Needs Review"
        result["limited_adapter_approved_for_activation_gate"] = 0
        result["ready_for_limited_activation_gate"] = 0
        return result

    doc = frappe.new_doc("NDIS Limited Production Batch Adapter Run")
    doc.adapter_run_id = make_adapter_run_id()
    doc.status = result["status"]
    doc.adapter_status = result["adapter_status"]
    doc.limited_adapter_approved_for_activation_gate = approved
    doc.ready_for_limited_activation_gate = approved
    doc.direct_live_creation_blocked = result["direct_live_creation_blocked"]
    doc.production_batch_posting_allowed = 0
    doc.real_posting_allowed = 0
    doc.policy_live_enabled = 0

    for fieldname in [
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
        "actual_payment_entry_created_count",
        "actual_gl_created_count",
        "adapter_score",
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

    doc.required_acknowledgement = ADAPTER_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    if approved:
        create_adapter_lines(doc, adapter_lines)

    guard_after = guardrails()

    frappe.db.set_value(
        "NDIS Limited Production Batch Adapter Run",
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
def cancel_limited_production_batch_hard_block_adapter(adapter_run, reason=None):
    assert_action("cancel_limited_production_batch_hard_block_adapter")

    if not frappe.db.exists("NDIS Limited Production Batch Adapter Run", adapter_run):
        frappe.throw(_("Adapter run not found: {0}").format(adapter_run))

    doc = frappe.get_doc("NDIS Limited Production Batch Adapter Run", adapter_run)

    if doc.status == "Cancelled":
        return {"adapter_run": adapter_run, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.limited_adapter_approved_for_activation_gate or 0):
        frappe.throw(_("Cannot cancel an approved hard-block adapter. Create a superseding adapter instead."))

    frappe.db.set_value(
        "NDIS Limited Production Batch Adapter Run",
        adapter_run,
        {
            "status": "Cancelled",
            "adapter_status": "Cancelled",
            "limited_adapter_approved_for_activation_gate": 0,
            "ready_for_limited_activation_gate": 0,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 9D adapter audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        """
        UPDATE `tabNDIS Limited Production Batch Adapter Run Line`
        SET line_status = 'Cancelled'
        WHERE adapter_run = %(adapter_run)s
        """,
        {"adapter_run": adapter_run},
    )

    frappe.db.commit()

    return {
        "adapter_run": adapter_run,
        "status": "Cancelled",
        "note": "Adapter audit record cancelled only. No accounting movement occurred.",
    }


@frappe.whitelist()
def quick_limited_production_batch_adapter_summary(limit=20):
    runs = frappe.get_all(
        "NDIS Limited Production Batch Adapter Run",
        fields=[
            "name",
            "adapter_run_id",
            "status",
            "adapter_status",
            "limited_adapter_approved_for_activation_gate",
            "ready_for_limited_activation_gate",
            "direct_live_creation_blocked",
            "production_batch_posting_allowed",
            "real_posting_allowed",
            "policy_live_enabled",
            "policy_preview",
            "policy_design",
            "source_line_count",
            "eligible_line_count",
            "hard_blocked_line_count",
            "validation_blocked_line_count",
            "duplicate_blocked_line_count",
            "would_create_payment_entry_count",
            "would_create_reference_count",
            "would_create_payment_entry_amount",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
            "adapter_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    lines = frappe.get_all(
        "NDIS Limited Production Batch Adapter Run Line",
        fields=[
            "name",
            "adapter_run",
            "line_no",
            "line_status",
            "sales_invoice",
            "allocatable_amount",
            "would_create_payment_entry",
            "would_create_reference",
            "actual_payment_entry_created",
            "actual_gl_created",
            "hard_block_verified",
            "block_reason",
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
        "note": "Phase 9D limited production batch hard-block adapter summary. No live posting enabled.",
    }


def execute_adapter_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("status"):
        conditions.append("a.status = %(status)s")
        params["status"] = filters.get("status")

    columns = adapter_columns()

    data = frappe.db.sql(
        f"""
        SELECT
            a.name AS adapter_run,
            a.adapter_run_id,
            a.status,
            a.adapter_status,
            a.limited_adapter_approved_for_activation_gate,
            a.ready_for_limited_activation_gate,
            a.direct_live_creation_blocked,
            a.production_batch_posting_allowed,
            a.real_posting_allowed,
            a.policy_live_enabled,
            a.policy_preview,
            a.policy_design,
            a.source_line_count,
            a.eligible_line_count,
            a.hard_blocked_line_count,
            a.validation_blocked_line_count,
            a.duplicate_blocked_line_count,
            a.would_create_payment_entry_count,
            a.would_create_reference_count,
            a.would_create_payment_entry_amount,
            a.actual_payment_entry_created_count,
            a.actual_gl_created_count,
            a.adapter_score,
            a.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Limited Production Batch Adapter Run` a
        {build_where(conditions)}
        ORDER BY a.creation DESC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.adapter_run_id for row in data[:20]],
            "datasets": [
                {"name": "Hard Blocked", "values": [int(row.hard_blocked_line_count or 0) for row in data[:20]]},
                {"name": "Actual PE", "values": [int(row.actual_payment_entry_created_count or 0) for row in data[:20]]},
                {"name": "Actual GL", "values": [int(row.actual_gl_created_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Adapter Runs"), "datatype": "Int"},
        {"value": sum(int(row.limited_adapter_approved_for_activation_gate or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(flt(row.would_create_payment_entry_amount or 0) for row in data), "indicator": "Blue", "label": _("Would-create Amount"), "datatype": "Currency", "currency": currency()},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PE"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def adapter_columns():
    return [
        {"fieldname": "adapter_run", "label": _("Adapter Run"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Adapter Run", "width": 220},
        {"fieldname": "adapter_run_id", "label": _("Adapter Run ID"), "fieldtype": "Data", "width": 430},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "adapter_status", "label": _("Adapter Status"), "fieldtype": "Data", "width": 260},
        {"fieldname": "ready_for_limited_activation_gate", "label": _("Ready Gate"), "fieldtype": "Check", "width": 110},
        {"fieldname": "direct_live_creation_blocked", "label": _("Direct Block"), "fieldtype": "Check", "width": 110},
        {"fieldname": "hard_blocked_line_count", "label": _("Hard Blocked"), "fieldtype": "Int", "width": 110},
        {"fieldname": "would_create_payment_entry_count", "label": _("Would PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "would_create_reference_count", "label": _("Would Refs"), "fieldtype": "Int", "width": 100},
        {"fieldname": "would_create_payment_entry_amount", "label": _("Would Amount"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "policy_live_enabled", "label": _("Live Enabled"), "fieldtype": "Check", "width": 110},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "adapter_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_line_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("adapter_run"):
        conditions.append("l.adapter_run = %(adapter_run)s")
        params["adapter_run"] = filters.get("adapter_run")

    if filters.get("line_status"):
        conditions.append("l.line_status = %(line_status)s")
        params["line_status"] = filters.get("line_status")

    columns = [
        {"fieldname": "line", "label": _("Line"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Adapter Run Line", "width": 220},
        {"fieldname": "adapter_run", "label": _("Adapter Run"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Adapter Run", "width": 220},
        {"fieldname": "line_no", "label": _("Line No"), "fieldtype": "Int", "width": 80},
        {"fieldname": "line_status", "label": _("Status"), "fieldtype": "Data", "width": 140},
        {"fieldname": "sales_invoice", "label": _("Sales Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 170},
        {"fieldname": "allocatable_amount", "label": _("Allocatable"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "would_create_payment_entry", "label": _("Would Create PE"), "fieldtype": "Check", "width": 120},
        {"fieldname": "would_create_reference", "label": _("Would Create Ref"), "fieldtype": "Check", "width": 120},
        {"fieldname": "actual_payment_entry_created", "label": _("Actual PE"), "fieldtype": "Check", "width": 90},
        {"fieldname": "actual_gl_created", "label": _("Actual GL"), "fieldtype": "Check", "width": 90},
        {"fieldname": "hard_block_verified", "label": _("Hard Block"), "fieldtype": "Check", "width": 100},
        {"fieldname": "block_reason", "label": _("Block Reason"), "fieldtype": "Small Text", "width": 440},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            l.name AS line,
            l.adapter_run,
            l.line_no,
            l.line_status,
            l.sales_invoice,
            l.allocatable_amount,
            l.would_create_payment_entry,
            l.would_create_reference,
            l.actual_payment_entry_created,
            l.actual_gl_created,
            l.hard_block_verified,
            l.block_reason,
            l.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Limited Production Batch Adapter Run Line` l
        {build_where(conditions)}
        ORDER BY l.adapter_run DESC, l.line_no ASC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [str(row.line_no) for row in data[:20]],
            "datasets": [{"name": "Hard Blocked", "values": [int(row.hard_block_verified or 0) for row in data[:20]]}],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Lines"), "datatype": "Int"},
        {"value": len([row for row in data if row.line_status == "Hard Blocked"]), "indicator": "Green", "label": _("Hard Blocked"), "datatype": "Int"},
        {"value": sum(flt(row.allocatable_amount or 0) for row in data if row.line_status == "Hard Blocked"), "indicator": "Blue", "label": _("Would Amount"), "datatype": "Currency", "currency": currency()},
        {"value": sum(int(row.actual_payment_entry_created or 0) for row in data), "indicator": "Red", "label": _("Actual PE"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_adapter_report(filters)

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
