import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


READINESS_ACK = "I_CONFIRM_PHASE9R_APPROVE_LIMITED_BATCH_ENABLEMENT_READINESS_NO_POSTING"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"


def make_readiness_gate_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-LIMITED-PROD-BATCH-ENABLEMENT-READINESS-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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
    if not frappe.db.exists("DocType", POLICY_DOCTYPE) or not has_column(POLICY_DOCTYPE, "production_batch_enabled"):
        return 0
    return count_dt(POLICY_DOCTYPE, {"production_batch_enabled": 1})


def live_posting_allowed_policy_count():
    if not frappe.db.exists("DocType", POLICY_DOCTYPE) or not has_column(POLICY_DOCTYPE, "live_posting_allowed"):
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


def latest_freeze():
    rows = frappe.get_all(
        "NDIS Limited Production Batch Enablement Evidence Freeze",
        filters={
            "status": "Frozen",
            "evidence_freeze_allowed": 1,
            "ready_for_next_phase": 1,
            "phase9p_rollback_verified": 1,
            "phase9o_smoke_verified": 1,
            "phase9n_activation_gate_verified": 1,
            "phase9m_adapter_verified": 1,
            "phase9l_preview_verified": 1,
            "policy_caps_verified": 1,
            "rollback_verified": 1,
            "no_accounting_movement_verified": 1,
            "target_policy_enabled_before_rollback": 1,
            "target_policy_enabled_after_rollback": 0,
            "target_policy_live_before_rollback": 0,
            "target_policy_live_after_rollback": 0,
            "policy_enabled_before_count": 1,
            "policy_enabled_after_count": 0,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
            "production_batch_enabled_policy_count": 0,
            "live_posting_allowed_policy_count": 0,
        },
        fields=[
            "name",
            "freeze_id",
            "rollback_run",
            "enablement_smoke",
            "activation_gate",
            "enablement_adapter",
            "enablement_preview",
            "enablement_gate",
            "policy_lock",
            "target_policy_doctype",
            "target_policy",
            "target_policy_name",
            "enablement_field",
            "live_field",
            "target_policy_enabled_before_rollback",
            "target_policy_enabled_after_rollback",
            "target_policy_live_before_rollback",
            "target_policy_live_after_rollback",
            "policy_enabled_before_count",
            "policy_enabled_after_count",
            "actual_enabled_policy_count_before",
            "actual_enabled_policy_count_after",
            "max_batch_lines",
            "max_batch_amount",
            "max_payment_entry_count",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "submitted_journal_entry_count_today",
            "purchase_invoice_count_today",
            "production_batch_enabled_policy_count",
            "live_posting_allowed_policy_count",
            "freeze_score",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_approved_gate(evidence_freeze):
    if not evidence_freeze:
        return None
    rows = frappe.get_all(
        "NDIS Limited Production Batch Enablement Readiness Gate",
        filters={
            "evidence_freeze": evidence_freeze,
            "status": "Approved",
            "limited_enablement_readiness_approved": 1,
            "ready_for_controlled_policy_enablement": 1,
        },
        fields=["name", "readiness_gate_id"],
        limit=1,
    )
    return rows[0] if rows else None


def validate_source(freeze, guard, config):
    issues = []
    if config["production_mode"]:
        issues.append("Production mode must remain disabled for Phase 9R readiness approval.")
    if config["live_pe_enabled"]:
        issues.append("Live Payment Entry posting config must remain disabled for Phase 9R readiness approval.")
    if not freeze:
        issues.append("No approved Phase 9Q evidence freeze found.")
        return issues

    existing = existing_approved_gate(freeze.name)
    if existing:
        issues.append(f"Phase 9R readiness gate already exists for this freeze: {existing.readiness_gate_id}")

    required_links = {
        "rollback_run": freeze.rollback_run,
        "enablement_smoke": freeze.enablement_smoke,
        "activation_gate": freeze.activation_gate,
        "enablement_adapter": freeze.enablement_adapter,
        "enablement_preview": freeze.enablement_preview,
    }
    for label, value in required_links.items():
        if not value:
            issues.append(f"Missing evidence link: {label}")

    if freeze.rollback_run and not frappe.db.exists("NDIS Limited Production Batch Enablement Rollback Run", freeze.rollback_run):
        issues.append("Linked Phase 9P rollback run does not exist.")
    if freeze.enablement_smoke and not frappe.db.exists("NDIS Limited Production Batch Enablement Smoke Run", freeze.enablement_smoke):
        issues.append("Linked Phase 9O smoke run does not exist.")
    if freeze.target_policy and not frappe.db.exists(POLICY_DOCTYPE, freeze.target_policy):
        issues.append(f"Target policy does not exist: {freeze.target_policy}")

    expected = {
        "target_policy_enabled_before_rollback": 1,
        "target_policy_enabled_after_rollback": 0,
        "target_policy_live_before_rollback": 0,
        "target_policy_live_after_rollback": 0,
        "policy_enabled_before_count": 1,
        "policy_enabled_after_count": 0,
        "actual_payment_entry_created_count": 0,
        "actual_gl_created_count": 0,
    }
    for fieldname, expected_value in expected.items():
        if int(freeze.get(fieldname) or 0) != expected_value:
            issues.append(f"Frozen {fieldname} must be {expected_value}.")

    if freeze.target_policy:
        if get_flag(POLICY_DOCTYPE, freeze.target_policy, "production_batch_enabled") != 0:
            issues.append("Current target policy production_batch_enabled must be 0 before readiness approval.")
        if get_flag(POLICY_DOCTYPE, freeze.target_policy, "live_posting_allowed") != 0:
            issues.append("Current target policy live_posting_allowed must be 0 before readiness approval.")

    if int(freeze.payment_entry_count_before or 0) != int(freeze.payment_entry_count_after or 0):
        issues.append("Frozen evidence shows Payment Entry count changed.")
    if int(freeze.payment_entry_gl_count_before or 0) != int(freeze.payment_entry_gl_count_after or 0):
        issues.append("Frozen evidence shows Payment Entry GL count changed.")
    if int(freeze.max_batch_lines or 0) != 3:
        issues.append("Max batch lines must remain 3.")
    if flt(freeze.max_batch_amount or 0, 2) != 3:
        issues.append("Max batch amount must remain 3.00.")
    if int(freeze.max_payment_entry_count or 0) != 1:
        issues.append("Max Payment Entry count must remain 1.")
    if guard["production_batch_enabled_policy_count"] != 0:
        issues.append("Controlled production batch enabled policy count must be 0 before readiness approval.")
    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must be 0 before readiness approval.")
    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today is not zero.")
    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today is not zero.")
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


def build_items(freeze, issues, ack_ok, guard):
    items = []
    if freeze:
        add_item(
            items,
            "Pass",
            "Low",
            "Evidence Freeze",
            "phase9q_freeze_exists",
            "Phase 9Q freeze exists",
            f"Evidence freeze found: {freeze.freeze_id}.",
            "NDIS Limited Production Batch Enablement Evidence Freeze",
            freeze.name,
        )
    else:
        add_item(items, "Blocker", "Critical", "Evidence Freeze", "phase9q_freeze_exists", "Phase 9Q freeze exists", "No approved Phase 9Q freeze found.")

    if issues:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Readiness", "source_valid", "Readiness source valid", issue)
    else:
        add_item(items, "Pass", "Low", "Readiness", "source_valid", "Readiness source valid", "Frozen evidence chain is valid for controlled policy enablement readiness.")

    if guard["production_batch_enabled_policy_count"] == 0 and guard["live_posting_allowed_policy_count"] == 0:
        add_item(items, "Pass", "Low", "Policy Guardrail", "policy_flags_zero", "Policy flags are zero", "Enabled and live policy counts are zero.")
    else:
        add_item(items, "Blocker", "Critical", "Policy Guardrail", "policy_flags_zero", "Policy flags are zero", "Enabled/live policy count is not zero.")

    if freeze:
        add_item(items, "Pass", "Low", "Rollback Evidence", "rollback_verified", "Rollback verified", "Phase 9P rollback evidence is frozen and policy is disabled.")
        add_item(items, "Pass", "Low", "Accounting Guardrail", "no_accounting_movement", "No accounting movement", "Payment Entry and Payment Entry GL counts remained unchanged.")
        add_item(items, "Pass", "Low", "Caps", "caps_verified", "Caps verified", f"Caps: {freeze.max_batch_lines} lines, {freeze.max_batch_amount}, {freeze.max_payment_entry_count} Payment Entry.")
        add_item(items, "Info", "Low", "Next Step", "next_phase", "Next phase", "Approved readiness allows controlled limited production policy enablement phase only.")

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {READINESS_ACK}")
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
    return max(0, round(100 - int(blockers or 0) * 25 - int(warnings or 0) * 5, 2))


def create_items(doc, items):
    for item in items:
        row = frappe.new_doc("NDIS Limited Production Batch Enablement Readiness Gate Item")
        row.readiness_gate = doc.name
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
def run_limited_production_batch_enablement_readiness_gate(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_limited_production_batch_enablement_readiness_gate")

    freeze = latest_freeze()
    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }
    guard_before = guardrails()
    ack_ok = acknowledgement == READINESS_ACK
    issues = validate_source(freeze, guard_before, config)
    items = build_items(freeze, issues, ack_ok, guard_before)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    allowed = int(ack_ok and item_summary["blocker_count"] == 0 and freeze is not None)
    guard_now = guardrails()

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Approved" if allowed else "Needs Review",
        "readiness_status": "Ready For Controlled Limited Production Policy Enablement" if allowed else "Needs Review",
        "limited_enablement_readiness_approved": allowed,
        "ready_for_controlled_policy_enablement": allowed,
        "phase9q_freeze_verified": 1 if freeze else 0,
        "phase9p_rollback_verified": 1 if freeze else 0,
        "phase9o_smoke_verified": 1 if freeze else 0,
        "phase9n_activation_gate_verified": 1 if freeze else 0,
        "phase9m_adapter_verified": 1 if freeze else 0,
        "phase9l_preview_verified": 1 if freeze else 0,
        "policy_caps_verified": 1 if freeze and int(freeze.max_batch_lines or 0) == 3 and flt(freeze.max_batch_amount or 0, 2) == 3 and int(freeze.max_payment_entry_count or 0) == 1 else 0,
        "rollback_verified": 1 if freeze else 0,
        "freeze_verified": 1 if freeze else 0,
        "no_accounting_movement_verified": 1 if freeze and int(freeze.payment_entry_count_before or 0) == int(freeze.payment_entry_count_after or 0) and int(freeze.payment_entry_gl_count_before or 0) == int(freeze.payment_entry_gl_count_after or 0) else 0,
        "production_batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "policy_live_enabled": 0,
        "evidence_freeze": freeze.name if freeze else None,
        "rollback_run": freeze.rollback_run if freeze else None,
        "enablement_smoke": freeze.enablement_smoke if freeze else None,
        "activation_gate": freeze.activation_gate if freeze else None,
        "enablement_adapter": freeze.enablement_adapter if freeze else None,
        "enablement_preview": freeze.enablement_preview if freeze else None,
        "enablement_gate": freeze.enablement_gate if freeze else None,
        "policy_lock": freeze.policy_lock if freeze else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": freeze.target_policy if freeze else None,
        "target_policy_name": freeze.target_policy_name if freeze else None,
        "enablement_field": "production_batch_enabled",
        "live_field": "live_posting_allowed",
        "target_policy_enabled_before_rollback": int(freeze.target_policy_enabled_before_rollback or 0) if freeze else 0,
        "target_policy_enabled_after_rollback": int(freeze.target_policy_enabled_after_rollback or 0) if freeze else 0,
        "target_policy_live_before_rollback": int(freeze.target_policy_live_before_rollback or 0) if freeze else 0,
        "target_policy_live_after_rollback": int(freeze.target_policy_live_after_rollback or 0) if freeze else 0,
        "current_target_policy_enabled": get_flag(POLICY_DOCTYPE, freeze.target_policy, "production_batch_enabled") if freeze else 0,
        "current_target_policy_live": get_flag(POLICY_DOCTYPE, freeze.target_policy, "live_posting_allowed") if freeze else 0,
        "policy_enabled_before_count": int(freeze.policy_enabled_before_count or 0) if freeze else 0,
        "policy_enabled_after_count": int(freeze.policy_enabled_after_count or 0) if freeze else 0,
        "actual_enabled_policy_count_before": int(freeze.actual_enabled_policy_count_before or 0) if freeze else 0,
        "actual_enabled_policy_count_after": int(freeze.actual_enabled_policy_count_after or 0) if freeze else 0,
        "max_batch_lines": int(freeze.max_batch_lines or 0) if freeze else 0,
        "max_batch_amount": flt(freeze.max_batch_amount or 0) if freeze else 0,
        "max_payment_entry_count": int(freeze.max_payment_entry_count or 0) if freeze else 0,
        "actual_payment_entry_created_count": 0,
        "actual_gl_created_count": 0,
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guard_now["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guard_now["payment_entry_gl_count"],
        "submitted_journal_entry_count_today": guard_before["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_before["purchase_invoice_count_today"],
        "production_batch_enabled_policy_count": guard_before["production_batch_enabled_policy_count"],
        "live_posting_allowed_policy_count": guard_before["live_posting_allowed_policy_count"],
        "readiness_score": score,
        **item_summary,
        "items": items,
        "issues": issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_now,
        "config": config,
        "required_acknowledgement": READINESS_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 9R readiness gate only. It approves readiness for controlled limited policy enablement and creates no accounting or policy movement.",
    }

    if int(dry_run or 0):
        result.update(
            {
                "status": "Needs Review",
                "readiness_status": "Needs Review",
                "limited_enablement_readiness_approved": 0,
                "ready_for_controlled_policy_enablement": 0,
            }
        )
        return result

    doc = frappe.new_doc("NDIS Limited Production Batch Enablement Readiness Gate")
    doc.readiness_gate_id = make_readiness_gate_id()
    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = READINESS_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    create_items(doc, items)
    frappe.db.commit()

    final_doc = frappe.get_doc("NDIS Limited Production Batch Enablement Readiness Gate", doc.name)
    return {
        **result,
        "created": True,
        "readiness_gate": final_doc.name,
        "readiness_gate_id": final_doc.readiness_gate_id,
        "status": final_doc.status,
        "readiness_status": final_doc.readiness_status,
        "limited_enablement_readiness_approved": int(final_doc.limited_enablement_readiness_approved or 0),
        "ready_for_controlled_policy_enablement": int(final_doc.ready_for_controlled_policy_enablement or 0),
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_limited_production_batch_enablement_readiness_gate(readiness_gate, reason=None):
    assert_action("cancel_limited_production_batch_enablement_readiness_gate")
    if not frappe.db.exists("NDIS Limited Production Batch Enablement Readiness Gate", readiness_gate):
        frappe.throw(_("Readiness gate not found: {0}").format(readiness_gate))
    doc = frappe.get_doc("NDIS Limited Production Batch Enablement Readiness Gate", readiness_gate)
    if doc.status == "Cancelled":
        return {"readiness_gate": readiness_gate, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.limited_enablement_readiness_approved or 0):
        frappe.throw(_("Cannot cancel an approved Phase 9R readiness gate. Create a superseding gate instead."))
    frappe.db.set_value(
        "NDIS Limited Production Batch Enablement Readiness Gate",
        readiness_gate,
        {
            "status": "Cancelled",
            "readiness_status": "Cancelled",
            "limited_enablement_readiness_approved": 0,
            "ready_for_controlled_policy_enablement": 0,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 9R no-ack readiness audit cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(
        """
        UPDATE `tabNDIS Limited Production Batch Enablement Readiness Gate Item`
        SET status = 'Cancelled'
        WHERE readiness_gate = %(readiness_gate)s
        """,
        {"readiness_gate": readiness_gate},
    )
    frappe.db.commit()
    return {
        "readiness_gate": readiness_gate,
        "status": "Cancelled",
        "note": "No-ack readiness audit cancelled only. No policy or accounting movement occurred.",
    }


@frappe.whitelist()
def quick_limited_production_batch_enablement_readiness_summary(limit=20):
    gates = frappe.get_all(
        "NDIS Limited Production Batch Enablement Readiness Gate",
        fields=[
            "name",
            "readiness_gate_id",
            "status",
            "readiness_status",
            "limited_enablement_readiness_approved",
            "ready_for_controlled_policy_enablement",
            "evidence_freeze",
            "rollback_run",
            "enablement_smoke",
            "activation_gate",
            "target_policy",
            "current_target_policy_enabled",
            "current_target_policy_live",
            "policy_enabled_before_count",
            "policy_enabled_after_count",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
            "production_batch_enabled_policy_count",
            "live_posting_allowed_policy_count",
            "readiness_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(
        "NDIS Limited Production Batch Enablement Readiness Gate Item",
        fields=[
            "name",
            "readiness_gate",
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
        "required_acknowledgement": READINESS_ACK,
        "guardrails": guardrails(),
        "note": "Phase 9R readiness summary. Read-only approval, no policy or accounting movement.",
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
            g.name AS readiness_gate,
            g.readiness_gate_id,
            g.status,
            g.readiness_status,
            g.limited_enablement_readiness_approved,
            g.ready_for_controlled_policy_enablement,
            g.evidence_freeze,
            g.rollback_run,
            g.enablement_smoke,
            g.activation_gate,
            g.target_policy,
            g.current_target_policy_enabled,
            g.current_target_policy_live,
            g.policy_enabled_before_count,
            g.policy_enabled_after_count,
            g.max_batch_lines,
            g.max_batch_amount,
            g.max_payment_entry_count,
            g.actual_payment_entry_created_count,
            g.actual_gl_created_count,
            g.production_batch_enabled_policy_count,
            g.live_posting_allowed_policy_count,
            g.readiness_score,
            g.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Limited Production Batch Enablement Readiness Gate` g
        {build_where(conditions)}
        ORDER BY g.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.readiness_gate_id for row in data[:20]],
            "datasets": [
                {"name": "Approved", "values": [int(row.limited_enablement_readiness_approved or 0) for row in data[:20]]},
                {"name": "Enabled Policies", "values": [int(row.production_batch_enabled_policy_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Readiness Gates"), "datatype": "Int"},
        {"value": sum(int(row.limited_enablement_readiness_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(int(row.production_batch_enabled_policy_count or 0) for row in data), "indicator": "Red", "label": _("Enabled Policies"), "datatype": "Int"},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PE"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def gate_columns():
    return [
        {"fieldname": "readiness_gate", "label": _("Readiness Gate"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Readiness Gate", "width": 220},
        {"fieldname": "readiness_gate_id", "label": _("Readiness Gate ID"), "fieldtype": "Data", "width": 470},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "readiness_status", "label": _("Readiness Status"), "fieldtype": "Data", "width": 360},
        {"fieldname": "limited_enablement_readiness_approved", "label": _("Approved"), "fieldtype": "Check", "width": 90},
        {"fieldname": "ready_for_controlled_policy_enablement", "label": _("Ready"), "fieldtype": "Check", "width": 90},
        {"fieldname": "evidence_freeze", "label": _("Evidence Freeze"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Evidence Freeze", "width": 220},
        {"fieldname": "rollback_run", "label": _("Rollback Run"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Rollback Run", "width": 220},
        {"fieldname": "target_policy", "label": _("Target Policy"), "fieldtype": "Data", "width": 260},
        {"fieldname": "current_target_policy_enabled", "label": _("Current Enabled"), "fieldtype": "Check", "width": 120},
        {"fieldname": "current_target_policy_live", "label": _("Current Live"), "fieldtype": "Check", "width": 110},
        {"fieldname": "policy_enabled_before_count", "label": _("Enabled Before"), "fieldtype": "Int", "width": 120},
        {"fieldname": "policy_enabled_after_count", "label": _("Enabled After"), "fieldtype": "Int", "width": 120},
        {"fieldname": "max_batch_lines", "label": _("Max Lines"), "fieldtype": "Int", "width": 90},
        {"fieldname": "max_batch_amount", "label": _("Max Amount"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "max_payment_entry_count", "label": _("Max PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "production_batch_enabled_policy_count", "label": _("Enabled Policies"), "fieldtype": "Int", "width": 120},
        {"fieldname": "live_posting_allowed_policy_count", "label": _("Live Policies"), "fieldtype": "Int", "width": 110},
        {"fieldname": "readiness_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("readiness_gate"):
        conditions.append("i.readiness_gate = %(readiness_gate)s")
        params["readiness_gate"] = filters.get("readiness_gate")
    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Readiness Gate Item", "width": 220},
        {"fieldname": "readiness_gate", "label": _("Readiness Gate"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Readiness Gate", "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 170},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 300},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 520},
        {"fieldname": "source_doctype", "label": _("Source DocType"), "fieldtype": "Data", "width": 220},
        {"fieldname": "source_name", "label": _("Source Name"), "fieldtype": "Data", "width": 240},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            i.name AS item,
            i.readiness_gate,
            i.status,
            i.severity,
            i.category,
            i.check_label,
            i.detail,
            i.source_doctype,
            i.source_name,
            i.checked_on
        FROM `tabNDIS Limited Production Batch Enablement Readiness Gate Item` i
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
