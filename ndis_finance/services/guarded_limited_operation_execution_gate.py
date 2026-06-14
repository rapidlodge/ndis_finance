import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


GATE_ACK = "I_CONFIRM_PHASE10I_ALLOW_SINGLE_GUARDED_LIMITED_OPERATION_EXECUTION_GATE_NO_POSTING"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"


def make_gate_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-GUARDED-LIMITED-OP-EXEC-GATE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_preview():
    rows = frappe.get_all(
        "NDIS Guarded Limited Operation Preview",
        filters={
            "status": "Previewed",
            "preview_status": "Ready For Guarded Limited Operation Execution",
            "operation_previewed": 1,
            "ready_for_single_guarded_operation_execution_gate": 1,
            "preview_only": 1,
            "operation_shape_revalidated": 1,
            "one_operation_only": 1,
            "policy_state_preserved_verified": 1,
            "policy_mutation_performed": 0,
            "actual_policy_mutation_count": 0,
            "phase10g_pre_check_verified": 1,
            "phase10f_register_verified": 1,
            "phase10e_decision_verified": 1,
            "payment_entry_cancelled_verified": 1,
            "no_new_accounting_movement_verified": 1,
            "controlled_policy_enabled_verified": 1,
            "live_posting_blocked_verified": 1,
            "target_policy_enabled_after": 1,
            "target_policy_live_after": 0,
            "production_batch_enabled_policy_count_after": 1,
            "live_posting_allowed_policy_count_after": 0,
            "preview_batch_line_count": 3,
            "preview_payment_entry_count": 1,
            "preview_live_posting_requested": 0,
            "preview_journal_entry_side_effect_requested": 0,
            "preview_purchase_invoice_side_effect_requested": 0,
            "would_create_payment_entry_count": 1,
            "would_create_gl_entry_count": 0,
            "would_post_live": 0,
            "would_create_journal_entry": 0,
            "would_create_purchase_invoice": 0,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
            "submitted_journal_entry_count_today": 0,
            "purchase_invoice_count_today": 0,
        },
        fields=[
            "name",
            "preview_id",
            "pre_check",
            "monitoring_register",
            "decision",
            "review",
            "freeze",
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
            "preview_batch_line_count",
            "preview_batch_amount",
            "preview_payment_entry_count",
            "preview_live_posting_requested",
            "preview_journal_entry_side_effect_requested",
            "preview_purchase_invoice_side_effect_requested",
            "would_create_payment_entry_count",
            "would_create_gl_entry_count",
            "would_post_live",
            "would_create_journal_entry",
            "would_create_purchase_invoice",
            "payment_entry",
            "payment_entry_docstatus",
            "payment_entry_status",
            "preview_score",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )

    return rows[0] if rows else None


def existing_gate(preview):
    rows = frappe.get_all(
        "NDIS Guarded Limited Operation Execution Gate",
        filters={
            "preview": preview,
            "status": "Execution Allowed",
            "execution_gate_allowed": 1,
            "ready_for_single_guarded_operation_smoke": 1,
        },
        fields=["name", "gate_id"],
        limit=1,
    )
    return rows[0] if rows else None


def validate_source(preview, guard, policy_enabled_before, policy_live_before, pe_docstatus, pe_status):
    issues = []

    if not preview:
        issues.append("No completed Phase 10H guarded limited operation preview found.")
        return issues

    existing = existing_gate(preview.name)
    if existing:
        issues.append(f"Phase 10I execution gate already exists for this preview: {existing.gate_id}")

    required_links = {
        "preview": ("NDIS Guarded Limited Operation Preview", preview.name),
        "pre_check": ("NDIS Controlled Limited Operation Pre Check", preview.pre_check),
        "monitoring_register": ("NDIS Controlled Limited Operations Monitoring Register", preview.monitoring_register),
        "decision": ("NDIS Guarded Adapter Final Policy Decision", preview.decision),
        "payment_entry": ("Payment Entry", preview.payment_entry),
        "target_policy": (POLICY_DOCTYPE, preview.target_policy),
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
        issues.append("Submitted Journal Entry today must be 0 before execution gate.")

    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today must be 0 before execution gate.")

    if int(preview.preview_batch_line_count or 0) != 3:
        issues.append("Execution gate must lock exactly 3 previewed batch lines.")

    if flt(preview.preview_batch_amount or 0, 2) != 3:
        issues.append("Execution gate must lock exactly $3.00 previewed batch amount.")

    if int(preview.preview_payment_entry_count or 0) != 1:
        issues.append("Execution gate must lock exactly 1 previewed Payment Entry count.")

    if int(preview.preview_live_posting_requested or 0) != 0:
        issues.append("Execution gate must not allow live posting.")

    if int(preview.would_create_gl_entry_count or 0) != 0:
        issues.append("Phase 10I gate preview must show would_create_gl_entry_count = 0.")

    if int(preview.actual_payment_entry_created_count or 0) != 0:
        issues.append("Phase 10H preview must not have created Payment Entry.")

    if int(preview.actual_gl_created_count or 0) != 0:
        issues.append("Phase 10H preview must not have created GL.")

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


def build_items(preview, issues, ack_ok):
    items = []

    if preview:
        add_item(
            items,
            "Pass",
            "Low",
            "Evidence",
            "phase10h_preview_exists",
            "Phase 10H preview exists",
            f"Preview found: {preview.preview_id}.",
            "NDIS Guarded Limited Operation Preview",
            preview.name,
        )
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase10h_preview_exists", "Phase 10H preview exists", "No completed Phase 10H preview found.")

    if not issues:
        add_item(items, "Pass", "Low", "Gate Source", "gate_source_valid", "Gate source valid", "Phase 10H preview is valid for single guarded operation execution gate.")
    else:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Gate Source", "gate_source_valid", "Gate source valid", issue)

    if preview:
        checks = [
            ("execution_shape_locked", "Execution shape locked", f"{int(preview.preview_batch_line_count or 0)} lines / {flt(preview.preview_batch_amount or 0, 2)} / {int(preview.preview_payment_entry_count or 0)} PE"),
            ("smoke_only_allowed", "Smoke-only execution allowed", "Phase 10I allows Phase 10J smoke execution only."),
            ("real_posting_blocked", "Real posting blocked", "real_posting_allowed = 0"),
            ("live_posting_blocked", "Live posting remains blocked", f"preview_live_posting_requested = {int(preview.preview_live_posting_requested or 0)}"),
            ("no_execution_this_phase", "No execution in this phase", "Phase 10I creates no Payment Entry and no GL."),
        ]

        for key, label, detail in checks:
            add_item(items, "Pass", "Low", "Execution Gate", key, label, detail)

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {GATE_ACK}")

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
        row = frappe.new_doc("NDIS Guarded Limited Operation Execution Gate Item")
        row.gate = doc.name
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
def run_guarded_limited_operation_execution_gate(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_guarded_limited_operation_execution_gate")

    preview = latest_preview()

    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }

    guard_before = guardrails()
    ack_ok = acknowledgement == GATE_ACK

    policy_enabled_before = get_flag(POLICY_DOCTYPE, preview.target_policy, "production_batch_enabled") if preview else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, preview.target_policy, "live_posting_allowed") if preview else 0

    pe_docstatus = 0
    pe_status = None

    if preview and preview.payment_entry and frappe.db.exists("Payment Entry", preview.payment_entry):
        pe_doc = frappe.get_doc("Payment Entry", preview.payment_entry)
        pe_docstatus = int(pe_doc.docstatus or 0)
        pe_status = pe_doc.status

    issues = validate_source(preview, guard_before, policy_enabled_before, policy_live_before, pe_docstatus, pe_status)
    items = build_items(preview, issues, ack_ok)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    allowed = int(ack_ok and item_summary["blocker_count"] == 0 and bool(preview))

    policy_enabled_after = get_flag(POLICY_DOCTYPE, preview.target_policy, "production_batch_enabled") if preview else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, preview.target_policy, "live_posting_allowed") if preview else 0
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

    scope = {
        "locked_batch_line_count": int(preview.preview_batch_line_count or 0) if preview else 0,
        "locked_batch_amount": flt(preview.preview_batch_amount or 0, 2) if preview else 0,
        "locked_payment_entry_count": int(preview.preview_payment_entry_count or 0) if preview else 0,
        "locked_live_posting_requested": int(preview.preview_live_posting_requested or 0) if preview else 0,
        "locked_journal_entry_side_effect_requested": int(preview.preview_journal_entry_side_effect_requested or 0) if preview else 0,
        "locked_purchase_invoice_side_effect_requested": int(preview.preview_purchase_invoice_side_effect_requested or 0) if preview else 0,
        "would_create_payment_entry_count": int(preview.would_create_payment_entry_count or 0) if preview else 0,
        "would_create_gl_entry_count": int(preview.would_create_gl_entry_count or 0) if preview else 0,
        "would_post_live": int(preview.would_post_live or 0) if preview else 0,
        "would_create_journal_entry": int(preview.would_create_journal_entry or 0) if preview else 0,
        "would_create_purchase_invoice": int(preview.would_create_purchase_invoice or 0) if preview else 0,
        "actual_execution_performed": 0,
    }

    shape_locked = int(
        scope["locked_batch_line_count"] == 3
        and flt(scope["locked_batch_amount"], 2) == 3
        and scope["locked_payment_entry_count"] == 1
        and scope["locked_live_posting_requested"] == 0
        and scope["locked_journal_entry_side_effect_requested"] == 0
        and scope["locked_purchase_invoice_side_effect_requested"] == 0
    )

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Execution Allowed" if allowed else "Needs Review",
        "execution_status": "Ready For One Guarded Limited Operation Smoke Execution" if allowed else "Needs Review",
        "execution_gate_allowed": allowed,
        "ready_for_single_guarded_operation_smoke": allowed,
        "smoke_only_allowed": allowed,
        "real_posting_allowed": 0,
        "execution_not_performed": 1,
        "operation_shape_locked": shape_locked,
        "one_operation_only": 1 if preview else 0,
        "policy_state_preserved_verified": policy_preserved,
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": 0,
        "phase10h_preview_verified": 1 if preview else 0,
        "phase10g_pre_check_verified": 1 if preview else 0,
        "phase10f_register_verified": 1 if preview else 0,
        "phase10e_decision_verified": 1 if preview else 0,
        "payment_entry_cancelled_verified": 1 if pe_docstatus == 2 else 0,
        "no_new_accounting_movement_verified": no_new_movement,
        "controlled_policy_enabled_verified": 1 if policy_enabled_after == 1 else 0,
        "live_posting_blocked_verified": 1 if policy_live_after == 0 else 0,
        "preview": preview.name if preview else None,
        "pre_check": preview.pre_check if preview else None,
        "monitoring_register": preview.monitoring_register if preview else None,
        "decision": preview.decision if preview else None,
        "review": preview.review if preview else None,
        "runtime_guard": preview.runtime_guard if preview else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": preview.target_policy if preview else None,
        "target_policy_name": preview.target_policy_name if preview else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_before": policy_live_before,
        "target_policy_live_after": policy_live_after,
        "production_batch_enabled_policy_count_before": guard_before["production_batch_enabled_policy_count"],
        "production_batch_enabled_policy_count_after": guard_after["production_batch_enabled_policy_count"],
        "live_posting_allowed_policy_count_before": guard_before["live_posting_allowed_policy_count"],
        "live_posting_allowed_policy_count_after": guard_after["live_posting_allowed_policy_count"],
        **scope,
        "payment_entry": preview.payment_entry if preview else None,
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
        "gate_score": score,
        **item_summary,
        "items": items,
        "issues": issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "execution_scope": scope,
        "config": config,
        "required_acknowledgement": GATE_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 10I allows the next Phase 10J smoke execution only. It creates no accounting movement and does not mutate policy flags.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["execution_status"] = "Needs Review"
        result["execution_gate_allowed"] = 0
        result["ready_for_single_guarded_operation_smoke"] = 0
        result["smoke_only_allowed"] = 0
        return result

    doc = frappe.new_doc("NDIS Guarded Limited Operation Execution Gate")
    doc.gate_id = make_gate_id()

    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)

    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = GATE_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.execution_scope_json = safe_json(scope)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    create_items(doc, items)
    frappe.db.commit()

    return {
        **result,
        "created": True,
        "gate": doc.name,
        "gate_id": doc.gate_id,
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_guarded_limited_operation_execution_gate_audit(gate, reason=None):
    assert_action("cancel_guarded_limited_operation_execution_gate_audit")

    if not frappe.db.exists("NDIS Guarded Limited Operation Execution Gate", gate):
        frappe.throw(_("Execution gate audit not found: {0}").format(gate))

    doc = frappe.get_doc("NDIS Guarded Limited Operation Execution Gate", gate)

    if doc.status == "Cancelled":
        return {"gate": gate, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.execution_gate_allowed or 0):
        frappe.throw(_("Cannot cancel an allowed Phase 10I execution gate. Create a superseding governance record if required."))

    frappe.db.set_value(
        "NDIS Guarded Limited Operation Execution Gate",
        gate,
        {
            "status": "Cancelled",
            "execution_status": "Cancelled",
            "execution_gate_allowed": 0,
            "ready_for_single_guarded_operation_smoke": 0,
            "smoke_only_allowed": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 10I no-ack execution gate audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        """
        UPDATE `tabNDIS Guarded Limited Operation Execution Gate Item`
        SET status = 'Cancelled'
        WHERE gate = %(gate)s
        """,
        {"gate": gate},
    )

    frappe.db.commit()

    return {
        "gate": gate,
        "status": "Cancelled",
        "note": "No-ack execution gate audit cancelled only. No accounting or policy movement occurred.",
    }


@frappe.whitelist()
def quick_guarded_limited_operation_execution_gate_summary(limit=20):
    gates = frappe.get_all(
        "NDIS Guarded Limited Operation Execution Gate",
        fields=[
            "name",
            "gate_id",
            "status",
            "execution_status",
            "execution_gate_allowed",
            "ready_for_single_guarded_operation_smoke",
            "smoke_only_allowed",
            "real_posting_allowed",
            "execution_not_performed",
            "operation_shape_locked",
            "preview",
            "pre_check",
            "monitoring_register",
            "target_policy",
            "target_policy_enabled_before",
            "target_policy_enabled_after",
            "target_policy_live_before",
            "target_policy_live_after",
            "locked_batch_line_count",
            "locked_batch_amount",
            "locked_payment_entry_count",
            "would_create_payment_entry_count",
            "would_create_gl_entry_count",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
            "gate_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    items = frappe.get_all(
        "NDIS Guarded Limited Operation Execution Gate Item",
        fields=[
            "name",
            "gate",
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
        "required_acknowledgement": GATE_ACK,
        "guardrails": guardrails(),
        "note": "Phase 10I execution gate summary. Gate only; no policy mutation and no accounting movement.",
    }


def execute_gate_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("status"):
        conditions.append("g.status = %(status)s")
        params["status"] = filters.get("status")

    columns = gate_columns()

    data = frappe.db.sql(
        f"""
        SELECT
            g.name AS gate,
            g.gate_id,
            g.status,
            g.execution_status,
            g.execution_gate_allowed,
            g.ready_for_single_guarded_operation_smoke,
            g.smoke_only_allowed,
            g.real_posting_allowed,
            g.execution_not_performed,
            g.operation_shape_locked,
            g.preview,
            g.pre_check,
            g.monitoring_register,
            g.target_policy,
            g.target_policy_enabled_after,
            g.target_policy_live_after,
            g.locked_batch_line_count,
            g.locked_batch_amount,
            g.locked_payment_entry_count,
            g.would_create_payment_entry_count,
            g.would_create_gl_entry_count,
            g.actual_payment_entry_created_count,
            g.actual_gl_created_count,
            g.gate_score,
            g.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Guarded Limited Operation Execution Gate` g
        {build_where(conditions)}
        ORDER BY g.creation DESC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.gate_id for row in data[:20]],
            "datasets": [
                {"name": "Gate Allowed", "values": [int(row.execution_gate_allowed or 0) for row in data[:20]]},
                {"name": "Actual PE Created", "values": [int(row.actual_payment_entry_created_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Execution Gates"), "datatype": "Int"},
        {"value": sum(int(row.execution_gate_allowed or 0) for row in data), "indicator": "Green", "label": _("Allowed"), "datatype": "Int"},
        {"value": sum(int(row.ready_for_single_guarded_operation_smoke or 0) for row in data), "indicator": "Green", "label": _("Ready Smoke"), "datatype": "Int"},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PE"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def gate_columns():
    return [
        {"fieldname": "gate", "label": _("Gate"), "fieldtype": "Link", "options": "NDIS Guarded Limited Operation Execution Gate", "width": 220},
        {"fieldname": "gate_id", "label": _("Gate ID"), "fieldtype": "Data", "width": 390},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 130},
        {"fieldname": "execution_status", "label": _("Execution Status"), "fieldtype": "Data", "width": 330},
        {"fieldname": "execution_gate_allowed", "label": _("Gate Allowed"), "fieldtype": "Check", "width": 110},
        {"fieldname": "ready_for_single_guarded_operation_smoke", "label": _("Ready Smoke"), "fieldtype": "Check", "width": 110},
        {"fieldname": "smoke_only_allowed", "label": _("Smoke Only"), "fieldtype": "Check", "width": 100},
        {"fieldname": "real_posting_allowed", "label": _("Real Posting"), "fieldtype": "Check", "width": 110},
        {"fieldname": "execution_not_performed", "label": _("No Execution"), "fieldtype": "Check", "width": 110},
        {"fieldname": "operation_shape_locked", "label": _("Shape Locked"), "fieldtype": "Check", "width": 110},
        {"fieldname": "preview", "label": _("Phase 10H Preview"), "fieldtype": "Link", "options": "NDIS Guarded Limited Operation Preview", "width": 220},
        {"fieldname": "target_policy", "label": _("Target Policy"), "fieldtype": "Data", "width": 260},
        {"fieldname": "target_policy_enabled_after", "label": _("Enabled"), "fieldtype": "Check", "width": 80},
        {"fieldname": "target_policy_live_after", "label": _("Live"), "fieldtype": "Check", "width": 70},
        {"fieldname": "locked_batch_line_count", "label": _("Lines"), "fieldtype": "Int", "width": 80},
        {"fieldname": "locked_batch_amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 100},
        {"fieldname": "locked_payment_entry_count", "label": _("PE Count"), "fieldtype": "Int", "width": 90},
        {"fieldname": "would_create_payment_entry_count", "label": _("Would PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "would_create_gl_entry_count", "label": _("Would GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "gate_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    if filters.get("gate"):
        conditions.append("i.gate = %(gate)s")
        params["gate"] = filters.get("gate")

    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": "NDIS Guarded Limited Operation Execution Gate Item", "width": 220},
        {"fieldname": "gate", "label": _("Gate"), "fieldtype": "Link", "options": "NDIS Guarded Limited Operation Execution Gate", "width": 220},
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
            i.gate,
            i.status,
            i.severity,
            i.category,
            i.check_label,
            i.detail,
            i.source_doctype,
            i.source_name,
            i.checked_on
        FROM `tabNDIS Guarded Limited Operation Execution Gate Item` i
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
        {"value": len([row for row in data if row.category == "Execution Gate"]), "indicator": "Blue", "label": _("Gate Checks"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_gate_report(filters)

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
