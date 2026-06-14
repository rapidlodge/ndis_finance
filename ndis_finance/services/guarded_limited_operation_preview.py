import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


PREVIEW_ACK = "I_CONFIRM_PHASE10H_PREVIEW_SINGLE_GUARDED_LIMITED_OPERATION_NO_POSTING"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"


def make_preview_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-GUARDED-LIMITED-OP-PREVIEW-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def has_column(doctype, fieldname):
    try:
        return bool(frappe.db.has_column(doctype, fieldname))
    except Exception:
        return False


def get_flag(doctype, name, fieldname, default=0):
    if not name or not has_column(doctype, fieldname):
        return default
    return int(frappe.db.get_value(doctype, name, fieldname) or 0)


def production_batch_enabled_policy_count():
    if not frappe.db.exists("DocType", POLICY_DOCTYPE):
        return 0
    if not has_column(POLICY_DOCTYPE, "production_batch_enabled"):
        return 0
    return count_dt(POLICY_DOCTYPE, {"production_batch_enabled": 1})


def live_posting_allowed_policy_count():
    if not frappe.db.exists("DocType", POLICY_DOCTYPE):
        return 0
    if not has_column(POLICY_DOCTYPE, "live_posting_allowed"):
        return 0
    return count_dt(POLICY_DOCTYPE, {"live_posting_allowed": 1})


def guardrails():
    return {
        "payment_entry_count": count_dt("Payment Entry"),
        "payment_entry_gl_count": count_dt("GL Entry", {"voucher_type": "Payment Entry"}),
        "submitted_journal_entry_count_today": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}),
        "purchase_invoice_count_today": count_dt("Purchase Invoice", {"creation": [">=", today()]}),
        "production_batch_enabled_policy_count": production_batch_enabled_policy_count(),
        "live_posting_allowed_policy_count": live_posting_allowed_policy_count(),
    }


def latest_pre_check():
    rows = frappe.get_all(
        "NDIS Controlled Limited Operation Pre Check",
        filters={
            "status": "Approved",
            "check_status": "Ready For One Guarded Limited Operation",
            "pre_operation_check_approved": 1,
            "ready_for_single_guarded_operation_preview": 1,
            "operation_shape_validated": 1,
            "one_operation_only": 1,
            "policy_state_preserved_verified": 1,
            "policy_mutation_performed": 0,
            "actual_policy_mutation_count": 0,
            "phase10f_register_verified": 1,
            "phase10e_decision_verified": 1,
            "phase10d_review_verified": 1,
            "phase10c_freeze_verified": 1,
            "payment_entry_cancelled_verified": 1,
            "no_new_accounting_movement_verified": 1,
            "controlled_policy_enabled_verified": 1,
            "live_posting_blocked_verified": 1,
            "target_policy_enabled_after": 1,
            "target_policy_live_after": 0,
            "production_batch_enabled_policy_count_after": 1,
            "live_posting_allowed_policy_count_after": 0,
            "requested_batch_line_count": 3,
            "requested_payment_entry_count": 1,
            "live_posting_requested": 0,
            "journal_entry_side_effect_requested": 0,
            "purchase_invoice_side_effect_requested": 0,
            "batch_line_count_within_limit": 1,
            "batch_amount_within_limit": 1,
            "payment_entry_count_within_limit": 1,
            "live_posting_request_blocked": 1,
            "journal_entry_side_effect_blocked": 1,
            "purchase_invoice_side_effect_blocked": 1,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
            "submitted_journal_entry_count_today": 0,
            "purchase_invoice_count_today": 0,
        },
        fields=[
            "name",
            "pre_check_id",
            "monitoring_register",
            "decision",
            "review",
            "freeze",
            "rollback",
            "smoke",
            "runtime_guard",
            "target_policy_doctype",
            "target_policy",
            "target_policy_name",
            "target_policy_enabled_before",
            "target_policy_enabled_after",
            "target_policy_live_before",
            "target_policy_live_after",
            "production_batch_enabled_policy_count_before",
            "production_batch_enabled_policy_count_after",
            "live_posting_allowed_policy_count_before",
            "live_posting_allowed_policy_count_after",
            "max_batch_line_count",
            "max_batch_amount",
            "max_payment_entry_count",
            "live_posting_allowed",
            "journal_entry_side_effect_allowed",
            "purchase_invoice_side_effect_allowed",
            "requested_batch_line_count",
            "requested_batch_amount",
            "requested_payment_entry_count",
            "live_posting_requested",
            "journal_entry_side_effect_requested",
            "purchase_invoice_side_effect_requested",
            "payment_entry",
            "payment_entry_docstatus",
            "payment_entry_status",
            "pre_check_score",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )

    return rows[0] if rows else None


def existing_preview(pre_check):
    rows = frappe.get_all(
        "NDIS Guarded Limited Operation Preview",
        filters={
            "pre_check": pre_check,
            "status": "Previewed",
            "operation_previewed": 1,
            "ready_for_single_guarded_operation_execution_gate": 1,
        },
        fields=["name", "preview_id"],
        limit=1,
    )
    return rows[0] if rows else None


def validate_source(pre_check, guard, policy_enabled_before, policy_live_before, pe_docstatus, pe_status):
    issues = []

    if not pre_check:
        issues.append("No approved Phase 10G pre-check found.")
        return issues

    existing = existing_preview(pre_check.name)
    if existing:
        issues.append(f"Phase 10H preview already exists for this pre-check: {existing.preview_id}")

    required_links = {
        "pre_check": ("NDIS Controlled Limited Operation Pre Check", pre_check.name),
        "monitoring_register": ("NDIS Controlled Limited Operations Monitoring Register", pre_check.monitoring_register),
        "decision": ("NDIS Guarded Adapter Final Policy Decision", pre_check.decision),
        "payment_entry": ("Payment Entry", pre_check.payment_entry),
        "target_policy": (POLICY_DOCTYPE, pre_check.target_policy),
    }

    for label, pair in required_links.items():
        doctype, name = pair
        if not name:
            issues.append(f"Missing evidence link: {label}")
        elif not frappe.db.exists(doctype, name):
            issues.append(f"Linked evidence does not exist: {doctype} {name}")

    if pe_docstatus != 2:
        issues.append(f"Historical smoke Payment Entry must remain cancelled docstatus 2. Current: {pe_docstatus}")

    if pe_status != "Cancelled":
        issues.append(f"Historical smoke Payment Entry status must remain Cancelled. Current: {pe_status}")

    if policy_enabled_before != 1:
        issues.append("Target policy production_batch_enabled must be 1.")

    if policy_live_before != 0:
        issues.append("Target policy live_posting_allowed must be 0.")

    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must remain enabled.")

    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must remain 0.")

    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today must be 0.")

    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today must be 0.")

    if int(pre_check.requested_batch_line_count or 0) != 3:
        issues.append("Preview must use exactly 3 approved batch lines.")

    if flt(pre_check.requested_batch_amount or 0, 2) != 3:
        issues.append("Preview must use exactly $3.00 approved batch amount.")

    if int(pre_check.requested_payment_entry_count or 0) != 1:
        issues.append("Preview must use exactly 1 approved Payment Entry count.")

    if int(pre_check.live_posting_requested or 0) != 0:
        issues.append("Preview must not request live posting.")

    if int(pre_check.journal_entry_side_effect_requested or 0) != 0:
        issues.append("Preview must not request Journal Entry side effect.")

    if int(pre_check.purchase_invoice_side_effect_requested or 0) != 0:
        issues.append("Preview must not request Purchase Invoice side effect.")

    return issues


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


def build_items(pre_check, issues, ack_ok):
    items = []

    if pre_check:
        add_item(
            items,
            "Pass",
            "Low",
            "Evidence",
            "phase10g_pre_check_exists",
            "Phase 10G pre-check exists",
            f"Pre-check found: {pre_check.pre_check_id}.",
            "NDIS Controlled Limited Operation Pre Check",
            pre_check.name,
        )
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase10g_pre_check_exists", "Phase 10G pre-check exists", "No approved Phase 10G pre-check found.")

    if not issues:
        add_item(items, "Pass", "Low", "Preview Source", "preview_source_valid", "Preview source valid", "Phase 10G pre-check is valid for guarded limited operation preview.")
    else:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Preview Source", "preview_source_valid", "Preview source valid", issue)

    if pre_check:
        checks = [
            ("preview_shape_line_count", "Preview uses approved 3-line shape", f"{int(pre_check.requested_batch_line_count or 0)} lines"),
            ("preview_shape_amount", "Preview uses approved $3.00 shape", f"{flt(pre_check.requested_batch_amount or 0, 2)} amount"),
            ("preview_shape_payment_entry_count", "Preview uses approved 1 Payment Entry shape", f"{int(pre_check.requested_payment_entry_count or 0)} Payment Entry"),
            ("preview_live_posting_blocked", "Preview keeps live posting blocked", f"live_posting_requested = {int(pre_check.live_posting_requested or 0)}"),
            ("preview_je_side_effect_blocked", "Preview blocks Journal Entry side effect", f"journal_entry_side_effect_requested = {int(pre_check.journal_entry_side_effect_requested or 0)}"),
            ("preview_pi_side_effect_blocked", "Preview blocks Purchase Invoice side effect", f"purchase_invoice_side_effect_requested = {int(pre_check.purchase_invoice_side_effect_requested or 0)}"),
        ]

        for key, label, detail in checks:
            add_item(items, "Pass", "Low", "Preview Shape", key, label, detail)

    add_item(
        items,
        "Info",
        "Low",
        "Scope",
        "preview_only_no_execution",
        "Preview only, no execution",
        "Phase 10H prepares the execution gate only. It must not create Payment Entry or GL.",
    )

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {PREVIEW_ACK}")

    return items


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
        row = frappe.new_doc("NDIS Guarded Limited Operation Preview Item")
        row.preview = doc.name
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
def run_guarded_limited_operation_preview(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_guarded_limited_operation_preview")

    pre_check = latest_pre_check()

    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }

    guard_before = guardrails()
    ack_ok = acknowledgement == PREVIEW_ACK

    policy_enabled_before = get_flag(POLICY_DOCTYPE, pre_check.target_policy, "production_batch_enabled") if pre_check else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, pre_check.target_policy, "live_posting_allowed") if pre_check else 0

    pe_docstatus = 0
    pe_status = None

    if pre_check and pre_check.payment_entry and frappe.db.exists("Payment Entry", pre_check.payment_entry):
        pe_doc = frappe.get_doc("Payment Entry", pre_check.payment_entry)
        pe_docstatus = int(pe_doc.docstatus or 0)
        pe_status = pe_doc.status

    issues = validate_source(pre_check, guard_before, policy_enabled_before, policy_live_before, pe_docstatus, pe_status)
    items = build_items(pre_check, issues, ack_ok)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    allowed = int(ack_ok and item_summary["blocker_count"] == 0 and bool(pre_check))

    policy_enabled_after = get_flag(POLICY_DOCTYPE, pre_check.target_policy, "production_batch_enabled") if pre_check else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, pre_check.target_policy, "live_posting_allowed") if pre_check else 0
    guard_after = guardrails()

    no_new_movement = int(
        guard_before["payment_entry_count"] == guard_after["payment_entry_count"]
        and guard_before["payment_entry_gl_count"] == guard_after["payment_entry_gl_count"]
        and guard_before["submitted_journal_entry_count_today"] == guard_after["submitted_journal_entry_count_today"]
        and guard_before["purchase_invoice_count_today"] == guard_after["purchase_invoice_count_today"]
    )

    policy_preserved = int(
        policy_enabled_before == 1
        and policy_enabled_after == 1
        and policy_live_before == 0
        and policy_live_after == 0
        and guard_before["production_batch_enabled_policy_count"] == guard_after["production_batch_enabled_policy_count"]
        and guard_before["live_posting_allowed_policy_count"] == guard_after["live_posting_allowed_policy_count"]
    )

    line_ok = int(pre_check and int(pre_check.requested_batch_line_count or 0) <= int(pre_check.max_batch_line_count or 0))
    amount_ok = int(pre_check and flt(pre_check.requested_batch_amount or 0, 2) <= flt(pre_check.max_batch_amount or 0, 2))
    pe_count_ok = int(pre_check and int(pre_check.requested_payment_entry_count or 0) <= int(pre_check.max_payment_entry_count or 0))
    live_blocked = int(pre_check and int(pre_check.live_posting_requested or 0) == 0)
    je_blocked = int(pre_check and int(pre_check.journal_entry_side_effect_requested or 0) == 0)
    pi_blocked = int(pre_check and int(pre_check.purchase_invoice_side_effect_requested or 0) == 0)

    shape_valid = int(line_ok and amount_ok and pe_count_ok and live_blocked and je_blocked and pi_blocked and no_new_movement)

    shape = {
        "preview_batch_line_count": int(pre_check.requested_batch_line_count or 0) if pre_check else 0,
        "preview_batch_amount": flt(pre_check.requested_batch_amount or 0, 2) if pre_check else 0,
        "preview_payment_entry_count": int(pre_check.requested_payment_entry_count or 0) if pre_check else 0,
        "preview_live_posting_requested": int(pre_check.live_posting_requested or 0) if pre_check else 0,
        "preview_journal_entry_side_effect_requested": int(pre_check.journal_entry_side_effect_requested or 0) if pre_check else 0,
        "preview_purchase_invoice_side_effect_requested": int(pre_check.purchase_invoice_side_effect_requested or 0) if pre_check else 0,
    }

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Previewed" if allowed else "Needs Review",
        "preview_status": "Ready For Guarded Limited Operation Execution" if allowed else "Needs Review",
        "operation_previewed": allowed,
        "ready_for_single_guarded_operation_execution_gate": allowed,
        "preview_only": 1,
        "operation_shape_revalidated": shape_valid,
        "one_operation_only": 1 if pre_check else 0,
        "policy_state_preserved_verified": policy_preserved,
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": 0,
        "phase10g_pre_check_verified": 1 if pre_check else 0,
        "phase10f_register_verified": 1 if pre_check else 0,
        "phase10e_decision_verified": 1 if pre_check else 0,
        "phase10d_review_verified": 1 if pre_check else 0,
        "payment_entry_cancelled_verified": 1 if pe_docstatus == 2 else 0,
        "no_new_accounting_movement_verified": no_new_movement,
        "controlled_policy_enabled_verified": 1 if policy_enabled_after == 1 else 0,
        "live_posting_blocked_verified": 1 if policy_live_after == 0 else 0,
        "pre_check": pre_check.name if pre_check else None,
        "monitoring_register": pre_check.monitoring_register if pre_check else None,
        "decision": pre_check.decision if pre_check else None,
        "review": pre_check.review if pre_check else None,
        "freeze": pre_check.freeze if pre_check else None,
        "runtime_guard": pre_check.runtime_guard if pre_check else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": pre_check.target_policy if pre_check else None,
        "target_policy_name": pre_check.target_policy_name if pre_check else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_before": policy_live_before,
        "target_policy_live_after": policy_live_after,
        "production_batch_enabled_policy_count_before": guard_before["production_batch_enabled_policy_count"],
        "production_batch_enabled_policy_count_after": guard_after["production_batch_enabled_policy_count"],
        "live_posting_allowed_policy_count_before": guard_before["live_posting_allowed_policy_count"],
        "live_posting_allowed_policy_count_after": guard_after["live_posting_allowed_policy_count"],
        "max_batch_line_count": int(pre_check.max_batch_line_count or 0) if pre_check else 0,
        "max_batch_amount": flt(pre_check.max_batch_amount or 0, 2) if pre_check else 0,
        "max_payment_entry_count": int(pre_check.max_payment_entry_count or 0) if pre_check else 0,
        "live_posting_allowed": int(pre_check.live_posting_allowed or 0) if pre_check else 0,
        "journal_entry_side_effect_allowed": int(pre_check.journal_entry_side_effect_allowed or 0) if pre_check else 0,
        "purchase_invoice_side_effect_allowed": int(pre_check.purchase_invoice_side_effect_allowed or 0) if pre_check else 0,
        **shape,
        "batch_line_count_within_limit": line_ok,
        "batch_amount_within_limit": amount_ok,
        "payment_entry_count_within_limit": pe_count_ok,
        "live_posting_request_blocked": live_blocked,
        "journal_entry_side_effect_blocked": je_blocked,
        "purchase_invoice_side_effect_blocked": pi_blocked,
        "would_create_payment_entry_count": int(pre_check.requested_payment_entry_count or 0) if pre_check else 0,
        "would_create_gl_entry_count": 0,
        "would_post_live": 0,
        "would_create_journal_entry": 0,
        "would_create_purchase_invoice": 0,
        "payment_entry": pre_check.payment_entry if pre_check else None,
        "payment_entry_docstatus": pe_docstatus,
        "payment_entry_status": pe_status,
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guard_after["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
        "actual_payment_entry_created_count": 0,
        "actual_gl_created_count": 0,
        "submitted_journal_entry_count_today": guard_before["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_before["purchase_invoice_count_today"],
        "preview_score": score,
        **item_summary,
        "items": items,
        "issues": issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "operation_shape": shape,
        "config": config,
        "required_acknowledgement": PREVIEW_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 10H previews one guarded limited operation only. It creates no accounting movement and does not mutate policy flags.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["preview_status"] = "Needs Review"
        result["operation_previewed"] = 0
        result["ready_for_single_guarded_operation_execution_gate"] = 0
        return result

    doc = frappe.new_doc("NDIS Guarded Limited Operation Preview")
    doc.preview_id = make_preview_id()

    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)

    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = PREVIEW_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.operation_shape_json = safe_json(shape)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    create_items(doc, items)
    frappe.db.commit()

    return {
        **result,
        "created": True,
        "preview": doc.name,
        "preview_id": doc.preview_id,
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_guarded_limited_operation_preview_audit(preview, reason=None):
    assert_action("cancel_guarded_limited_operation_preview_audit")

    if not frappe.db.exists("NDIS Guarded Limited Operation Preview", preview):
        frappe.throw(_("Preview audit not found: {0}").format(preview))

    doc = frappe.get_doc("NDIS Guarded Limited Operation Preview", preview)

    if doc.status == "Cancelled":
        return {"preview": preview, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.operation_previewed or 0):
        frappe.throw(_("Cannot cancel a completed Phase 10H preview. Create a superseding governance record if required."))

    frappe.db.set_value(
        "NDIS Guarded Limited Operation Preview",
        preview,
        {
            "status": "Cancelled",
            "preview_status": "Cancelled",
            "operation_previewed": 0,
            "ready_for_single_guarded_operation_execution_gate": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 10H no-ack preview audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        """
        UPDATE `tabNDIS Guarded Limited Operation Preview Item`
        SET status = 'Cancelled'
        WHERE preview = %(preview)s
        """,
        {"preview": preview},
    )

    frappe.db.commit()

    return {
        "preview": preview,
        "status": "Cancelled",
        "note": "No-ack preview audit cancelled only. No accounting or policy movement occurred.",
    }


@frappe.whitelist()
def quick_guarded_limited_operation_preview_summary(limit=20):
    previews = frappe.get_all(
        "NDIS Guarded Limited Operation Preview",
        fields=[
            "name",
            "preview_id",
            "status",
            "preview_status",
            "operation_previewed",
            "ready_for_single_guarded_operation_execution_gate",
            "preview_only",
            "operation_shape_revalidated",
            "pre_check",
            "monitoring_register",
            "target_policy",
            "target_policy_enabled_before",
            "target_policy_enabled_after",
            "target_policy_live_before",
            "target_policy_live_after",
            "preview_batch_line_count",
            "preview_batch_amount",
            "preview_payment_entry_count",
            "would_create_payment_entry_count",
            "would_create_gl_entry_count",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
            "preview_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    items = frappe.get_all(
        "NDIS Guarded Limited Operation Preview Item",
        fields=[
            "name",
            "preview",
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
        "previews": previews,
        "items": items,
        "required_acknowledgement": PREVIEW_ACK,
        "guardrails": guardrails(),
        "note": "Phase 10H guarded limited operation preview summary. No policy mutation and no accounting movement.",
    }


def execute_preview_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("status"):
        conditions.append("p.status = %(status)s")
        params["status"] = filters.get("status")

    columns = preview_columns()

    data = frappe.db.sql(
        f"""
        SELECT
            p.name AS preview,
            p.preview_id,
            p.status,
            p.preview_status,
            p.operation_previewed,
            p.ready_for_single_guarded_operation_execution_gate,
            p.preview_only,
            p.operation_shape_revalidated,
            p.pre_check,
            p.monitoring_register,
            p.target_policy,
            p.target_policy_enabled_after,
            p.target_policy_live_after,
            p.preview_batch_line_count,
            p.preview_batch_amount,
            p.preview_payment_entry_count,
            p.would_create_payment_entry_count,
            p.would_create_gl_entry_count,
            p.actual_payment_entry_created_count,
            p.actual_gl_created_count,
            p.preview_score,
            p.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Guarded Limited Operation Preview` p
        {build_where(conditions)}
        ORDER BY p.creation DESC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.preview_id for row in data[:20]],
            "datasets": [
                {"name": "Previewed", "values": [int(row.operation_previewed or 0) for row in data[:20]]},
                {"name": "Actual PE Created", "values": [int(row.actual_payment_entry_created_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Previews"), "datatype": "Int"},
        {"value": sum(int(row.operation_previewed or 0) for row in data), "indicator": "Green", "label": _("Previewed"), "datatype": "Int"},
        {"value": sum(int(row.ready_for_single_guarded_operation_execution_gate or 0) for row in data), "indicator": "Green", "label": _("Ready Execution Gate"), "datatype": "Int"},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PE"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def preview_columns():
    return [
        {"fieldname": "preview", "label": _("Preview"), "fieldtype": "Link", "options": "NDIS Guarded Limited Operation Preview", "width": 220},
        {"fieldname": "preview_id", "label": _("Preview ID"), "fieldtype": "Data", "width": 390},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "preview_status", "label": _("Preview Status"), "fieldtype": "Data", "width": 310},
        {"fieldname": "operation_previewed", "label": _("Previewed"), "fieldtype": "Check", "width": 90},
        {"fieldname": "ready_for_single_guarded_operation_execution_gate", "label": _("Ready Gate"), "fieldtype": "Check", "width": 110},
        {"fieldname": "preview_only", "label": _("Preview Only"), "fieldtype": "Check", "width": 100},
        {"fieldname": "operation_shape_revalidated", "label": _("Shape Valid"), "fieldtype": "Check", "width": 105},
        {"fieldname": "pre_check", "label": _("Pre Check"), "fieldtype": "Link", "options": "NDIS Controlled Limited Operation Pre Check", "width": 220},
        {"fieldname": "target_policy", "label": _("Target Policy"), "fieldtype": "Data", "width": 260},
        {"fieldname": "target_policy_enabled_after", "label": _("Enabled"), "fieldtype": "Check", "width": 80},
        {"fieldname": "target_policy_live_after", "label": _("Live"), "fieldtype": "Check", "width": 70},
        {"fieldname": "preview_batch_line_count", "label": _("Lines"), "fieldtype": "Int", "width": 80},
        {"fieldname": "preview_batch_amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 100},
        {"fieldname": "preview_payment_entry_count", "label": _("PE Count"), "fieldtype": "Int", "width": 90},
        {"fieldname": "would_create_payment_entry_count", "label": _("Would PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "would_create_gl_entry_count", "label": _("Would GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "preview_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    if filters.get("preview"):
        conditions.append("i.preview = %(preview)s")
        params["preview"] = filters.get("preview")

    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": "NDIS Guarded Limited Operation Preview Item", "width": 220},
        {"fieldname": "preview", "label": _("Preview"), "fieldtype": "Link", "options": "NDIS Guarded Limited Operation Preview", "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 180},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 340},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 620},
        {"fieldname": "source_doctype", "label": _("Source DocType"), "fieldtype": "Data", "width": 220},
        {"fieldname": "source_name", "label": _("Source Name"), "fieldtype": "Data", "width": 240},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            i.name AS item,
            i.preview,
            i.status,
            i.severity,
            i.category,
            i.check_label,
            i.detail,
            i.source_doctype,
            i.source_name,
            i.checked_on
        FROM `tabNDIS Guarded Limited Operation Preview Item` i
        {build_where(conditions)}
        ORDER BY
            CASE i.status
                WHEN 'Blocker' THEN 1
                WHEN 'Warning' THEN 2
                WHEN 'Pass' THEN 3
                WHEN 'Info' THEN 4
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
        {"value": len([row for row in data if row.category == "Preview Shape"]), "indicator": "Blue", "label": _("Shape Checks"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_preview_report(filters)

    guard = guardrails()

    summary.append({"value": guard["payment_entry_count"], "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"})
    summary.append({"value": guard["payment_entry_gl_count"], "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"})
    summary.append({"value": guard["production_batch_enabled_policy_count"], "indicator": "Green", "label": _("Enabled Policies"), "datatype": "Int"})
    summary.append({"value": guard["live_posting_allowed_policy_count"], "indicator": "Red", "label": _("Live Policies"), "datatype": "Int"})
    summary.append({"value": guard["submitted_journal_entry_count_today"], "indicator": "Red", "label": _("Submitted JE Today"), "datatype": "Int"})
    summary.append({"value": guard["purchase_invoice_count_today"], "indicator": "Red", "label": _("Purchase Invoice Today"), "datatype": "Int"})

    return columns, data, message, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
