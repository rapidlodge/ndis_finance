import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


SMOKE_ACK = "I_CONFIRM_PHASE9O_ENABLE_ONE_LIMITED_PRODUCTION_BATCH_POLICY_ROLLBACK_REQUIRED"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
DEFAULT_POLICY_NAME = "LIMITED_CONTROLLED_PRODUCTION_BATCH"


def make_enablement_smoke_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-LIMITED-PROD-BATCH-ENABLEMENT-SMOKE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def has_pe_smoke_field():
    return frappe.db.has_column("Payment Entry", "custom_ndis_limited_prod_batch_smoke")


def submitted_phase9f_smoke_pe_count():
    if not has_pe_smoke_field():
        return 0

    return count_dt(
        "Payment Entry",
        {
            "docstatus": 1,
            "custom_ndis_limited_prod_batch_smoke": 1,
        },
    )


def cancelled_phase9f_smoke_pe_count():
    if not has_pe_smoke_field():
        return 0

    return count_dt(
        "Payment Entry",
        {
            "docstatus": 2,
            "custom_ndis_limited_prod_batch_smoke": 1,
        },
    )


def config_state():
    return {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


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
        "submitted_phase9f_smoke_pe_count": submitted_phase9f_smoke_pe_count(),
        "cancelled_phase9f_smoke_pe_count": cancelled_phase9f_smoke_pe_count(),
        "submitted_journal_entry_count_today": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}),
        "purchase_invoice_count_today": count_dt("Purchase Invoice", {"creation": [">=", today()]}),
        "production_batch_enabled_policy_count": production_batch_enabled_policy_count(),
        "live_posting_allowed_policy_count": live_posting_allowed_policy_count(),
    }


def latest_activation_gate():
    rows = frappe.get_all(
        "NDIS Limited Production Batch Enablement Activation Gate",
        filters={
            "status": "Activation Allowed",
            "limited_enablement_activation_allowed": 1,
            "ready_for_limited_enablement_smoke": 1,
            "phase9m_adapter_verified": 1,
            "phase9l_preview_verified": 1,
            "phase9k_enablement_design_verified": 1,
            "phase9j_policy_lock_verified": 1,
            "policy_caps_verified": 1,
            "direct_enablement_blocked": 1,
            "hard_block_verified": 1,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "would_enable_policy_count": 1,
            "hard_blocked_policy_count": 1,
            "actual_enabled_policy_count": 0,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
        },
        fields=[
            "name",
            "activation_gate_id",
            "enablement_adapter",
            "enablement_preview",
            "enablement_gate",
            "policy_lock",
            "finalisation_gate",
            "phase9h_freeze",
            "rollback_run",
            "smoke_run",
            "phase8g_freeze",
            "company",
            "customer",
            "payment_entry",
            "payment_entry_docstatus_after_rollback",
            "payment_entry_amount",
            "reference_count",
            "invoice_outstanding_after_rollback_total",
            "payment_entry_gl_count_after_rollback",
            "payment_entry_gl_net_after_rollback",
            "max_batch_lines",
            "max_batch_amount",
            "max_payment_entry_count",
            "allowed_payment_type",
            "allowed_reference_doctype",
            "locked_policy_mode",
            "approved_next_step",
            "would_enable_policy_count",
            "hard_blocked_policy_count",
            "actual_enabled_policy_count",
            "would_enable_policy_name",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
            "production_batch_enabled_policy_count",
            "live_posting_allowed_policy_count",
            "activation_score",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )

    return rows[0] if rows else None


def existing_unrolled_smoke():
    rows = frappe.get_all(
        "NDIS Limited Production Batch Enablement Smoke Run",
        filters={
            "status": "Enabled - Rollback Required",
            "limited_policy_enabled": 1,
            "rollback_required": 1,
        },
        fields=["name", "enablement_smoke_id"],
        limit=1,
    )
    return rows[0] if rows else None


def pe_gl_count_net(payment_entry):
    rows = frappe.db.sql(
        """
        SELECT COUNT(*) AS gl_count, COALESCE(SUM(debit - credit), 0) AS gl_net
        FROM `tabGL Entry`
        WHERE voucher_type='Payment Entry'
        AND voucher_no=%(payment_entry)s
        """,
        {"payment_entry": payment_entry},
        as_dict=True,
    )

    return int(rows[0].gl_count or 0), flt(rows[0].gl_net or 0, 2)


def resolve_policy_by_value(value):
    if not value or not frappe.db.exists("DocType", POLICY_DOCTYPE):
        return None

    if frappe.db.exists(POLICY_DOCTYPE, value):
        return value

    candidate_fields = [
        "policy_name",
        "policy_code",
        "policy_key",
        "posting_policy",
        "rule_name",
        "title",
    ]

    for fieldname in candidate_fields:
        if not has_column(POLICY_DOCTYPE, fieldname):
            continue

        rows = frappe.get_all(
            POLICY_DOCTYPE,
            filters={fieldname: value},
            fields=["name"],
            limit=1,
        )

        if rows:
            return rows[0].name

    return None


def resolve_target_policy(gate):
    candidates = []

    if gate:
        candidates.append(gate.would_enable_policy_name)

    candidates.append(DEFAULT_POLICY_NAME)

    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue

        seen.add(candidate)
        resolved = resolve_policy_by_value(candidate)

        if resolved:
            return resolved

    if not frappe.db.exists("DocType", POLICY_DOCTYPE):
        return None

    filters = {}

    if has_column(POLICY_DOCTYPE, "production_batch_enabled"):
        filters["production_batch_enabled"] = 0

    if has_column(POLICY_DOCTYPE, "live_posting_allowed"):
        filters["live_posting_allowed"] = 0

    rows = frappe.get_all(POLICY_DOCTYPE, filters=filters, fields=["name"], order_by="modified desc", limit=50)

    limited_rows = [
        row.name for row in rows
        if "LIMITED" in row.name.upper() or "BATCH" in row.name.upper()
    ]

    if len(limited_rows) == 1:
        return limited_rows[0]

    if len(rows) == 1:
        return rows[0].name

    return None


def validate_policy_schema():
    if not frappe.db.exists("DocType", POLICY_DOCTYPE):
        return [f"Missing DocType: {POLICY_DOCTYPE}"]

    issues = []

    if not has_column(POLICY_DOCTYPE, "production_batch_enabled"):
        issues.append("Policy DocType is missing required field production_batch_enabled.")

    if not has_column(POLICY_DOCTYPE, "live_posting_allowed"):
        issues.append("Policy DocType is missing required field live_posting_allowed.")

    return issues


def validate_source(gate, target_policy, guard):
    issues = []

    if not gate:
        issues.append("No approved Phase 9N activation gate found.")
        return issues

    if existing_unrolled_smoke():
        existing = existing_unrolled_smoke()
        issues.append(f"An unrolled Phase 9O enablement smoke already exists: {existing.enablement_smoke_id}")

    schema_issues = validate_policy_schema()
    issues.extend(schema_issues)

    required_links = {
        "enablement_adapter": gate.enablement_adapter,
        "enablement_preview": gate.enablement_preview,
        "enablement_gate": gate.enablement_gate,
        "policy_lock": gate.policy_lock,
        "phase9h_freeze": gate.phase9h_freeze,
        "rollback_run": gate.rollback_run,
        "smoke_run": gate.smoke_run,
    }

    for label, value in required_links.items():
        if not value:
            issues.append(f"Missing evidence link: {label}")

    if not gate.payment_entry or not frappe.db.exists("Payment Entry", gate.payment_entry):
        issues.append("Activation gate Payment Entry evidence does not exist.")
    else:
        docstatus = int(frappe.db.get_value("Payment Entry", gate.payment_entry, "docstatus") or 0)
        if docstatus != 2:
            issues.append(f"Payment Entry must be cancelled. Found docstatus {docstatus}.")

        gl_count, gl_net = pe_gl_count_net(gate.payment_entry)

        if gl_count != int(gate.payment_entry_gl_count_after_rollback or 0):
            issues.append("Current PE GL row count does not match activation gate evidence.")

        if gl_count != 6:
            issues.append(f"Expected PE GL rows after rollback to be 6. Found {gl_count}.")

        if flt(gl_net, 2) != 0:
            issues.append(f"Expected PE GL net to be 0.00. Found {gl_net}.")

    if int(gate.max_batch_lines or 0) != 3:
        issues.append("Max batch lines must be 3.")

    if flt(gate.max_batch_amount or 0, 2) != 3:
        issues.append("Max batch amount must be 3.00.")

    if int(gate.max_payment_entry_count or 0) != 1:
        issues.append("Max Payment Entry count must be 1.")

    if int(gate.would_enable_policy_count or 0) != 1:
        issues.append("Phase 9N would_enable_policy_count must be 1.")

    if int(gate.hard_blocked_policy_count or 0) != 1:
        issues.append("Phase 9N hard_blocked_policy_count must be 1.")

    if int(gate.actual_enabled_policy_count or 0) != 0:
        issues.append("Phase 9N actual_enabled_policy_count must be 0.")

    if int(gate.actual_payment_entry_created_count or 0) != 0:
        issues.append("Phase 9N actual Payment Entry created count must be 0.")

    if int(gate.actual_gl_created_count or 0) != 0:
        issues.append("Phase 9N actual GL created count must be 0.")

    if not target_policy:
        issues.append("Could not resolve target controlled production batch posting policy.")

    if target_policy:
        if get_flag(POLICY_DOCTYPE, target_policy, "production_batch_enabled") != 0:
            issues.append(f"Target policy is already enabled before smoke: {target_policy}")

        if get_flag(POLICY_DOCTYPE, target_policy, "live_posting_allowed") != 0:
            issues.append(f"Target policy live_posting_allowed is already enabled before smoke: {target_policy}")

    if guard["production_batch_enabled_policy_count"] != 0:
        issues.append("Controlled production batch enabled policy count must be 0 before Phase 9O smoke.")

    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must be 0 before Phase 9O smoke.")

    if guard["submitted_phase9f_smoke_pe_count"] != 0:
        issues.append("Submitted Phase 9F smoke PE count must be 0.")

    if guard["cancelled_phase9f_smoke_pe_count"] != 1:
        issues.append("Cancelled Phase 9F smoke PE count must be 1.")

    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today is not zero.")

    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today is not zero.")

    return issues


def count_status(issues, ack_ok, enabled=False):
    blockers = len(issues)
    warnings = 0 if ack_ok else 1
    passes = 8 if not blockers else 0
    infos = 2
    score = max(0, 100 - blockers * 25 - warnings * 5)

    return {
        "blocker_count": blockers,
        "warning_count": warnings,
        "pass_count": passes,
        "info_count": infos,
        "line_count": 1 if enabled else 0,
        "smoke_score": score,
    }


def enable_target_policy(target_policy):
    if not target_policy:
        frappe.throw(_("Target policy is required for Phase 9O enablement smoke."))

    if not has_column(POLICY_DOCTYPE, "production_batch_enabled"):
        frappe.throw(_("Target policy DocType is missing production_batch_enabled field."))

    if not has_column(POLICY_DOCTYPE, "live_posting_allowed"):
        frappe.throw(_("Target policy DocType is missing live_posting_allowed field."))

    before_enabled = get_flag(POLICY_DOCTYPE, target_policy, "production_batch_enabled")
    before_live = get_flag(POLICY_DOCTYPE, target_policy, "live_posting_allowed")

    if before_enabled:
        frappe.throw(_("Target policy is already enabled before Phase 9O smoke: {0}").format(target_policy))

    if before_live:
        frappe.throw(_("Target policy live flag is already enabled before Phase 9O smoke: {0}").format(target_policy))

    updates = {
        "production_batch_enabled": 1,
        "live_posting_allowed": 0,
    }

    if has_column(POLICY_DOCTYPE, "production_batch_posting_allowed"):
        updates["production_batch_posting_allowed"] = 0

    if has_column(POLICY_DOCTYPE, "real_posting_allowed"):
        updates["real_posting_allowed"] = 0

    if has_column(POLICY_DOCTYPE, "policy_live_enabled"):
        updates["policy_live_enabled"] = 0

    frappe.db.set_value(POLICY_DOCTYPE, target_policy, updates, update_modified=True)

    after_enabled = get_flag(POLICY_DOCTYPE, target_policy, "production_batch_enabled")
    after_live = get_flag(POLICY_DOCTYPE, target_policy, "live_posting_allowed")

    if after_enabled != 1:
        frappe.throw(_("Phase 9O failed to enable target policy."))

    if after_live != 0:
        frappe.throw(_("Phase 9O safety violation: live_posting_allowed changed to enabled."))

    return {
        "target_policy_enabled_before": before_enabled,
        "target_policy_enabled_after": after_enabled,
        "target_policy_live_before": before_live,
        "target_policy_live_after": after_live,
    }


def create_smoke_line(doc):
    line = frappe.new_doc("NDIS Limited Production Batch Enablement Smoke Line")
    line.enablement_smoke = doc.name
    line.line_no = 1
    line.line_label = "Controlled Limited Production Batch Policy Enabled - Rollback Required"
    line.line_status = "Enabled - Rollback Required" if int(doc.limited_policy_enabled or 0) else "Blocked"
    line.policy_doctype = doc.target_policy_doctype
    line.policy_name = doc.target_policy
    line.policy_action = "Enabled production_batch_enabled only; live posting remains blocked"
    line.would_enable = 1
    line.actual_enabled = int(doc.limited_policy_enabled or 0)
    line.rollback_required = int(doc.rollback_required or 0)
    line.enabled_before = int(doc.target_policy_enabled_before or 0)
    line.enabled_after = int(doc.target_policy_enabled_after or 0)
    line.live_before = int(doc.target_policy_live_before or 0)
    line.live_after = int(doc.target_policy_live_after or 0)
    line.production_batch_posting_allowed = 0
    line.real_posting_allowed = 0
    line.policy_live_enabled = 0
    line.max_batch_lines = doc.max_batch_lines
    line.max_batch_amount = doc.max_batch_amount
    line.max_payment_entry_count = doc.max_payment_entry_count
    line.detail = "Phase 9O controlled smoke enabled one policy flag only. Rollback is required before freeze."
    line.checked_on = doc.checked_on
    line.insert(ignore_permissions=True)


@frappe.whitelist()
def run_limited_production_batch_enablement_smoke(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_limited_production_batch_enablement_smoke")

    gate = latest_activation_gate()
    target_policy = resolve_target_policy(gate)
    config = config_state()
    guard_before = guardrails()
    ack_ok = acknowledgement == SMOKE_ACK

    issues = validate_source(gate, target_policy, guard_before)
    allowed = int(ack_ok and not issues and gate is not None and bool(target_policy))

    counts = count_status(issues, ack_ok, enabled=bool(allowed))

    base_result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Enabled - Rollback Required" if allowed else "Needs Review",
        "enablement_smoke_status": "Limited Policy Enabled - Rollback Required" if allowed else "Needs Review",
        "limited_policy_enabled": allowed,
        "rollback_required": allowed,
        "freeze_required_after_rollback": allowed,
        "phase9n_activation_gate_verified": 1 if gate else 0,
        "phase9m_adapter_verified": 1 if gate else 0,
        "phase9l_preview_verified": 1 if gate else 0,
        "phase9k_enablement_design_verified": 1 if gate else 0,
        "phase9j_policy_lock_verified": 1 if gate else 0,
        "policy_caps_verified": 1 if gate and int(gate.max_batch_lines or 0) == 3 and flt(gate.max_batch_amount or 0, 2) == 3 and int(gate.max_payment_entry_count or 0) == 1 else 0,
        "production_batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "policy_live_enabled": 0,
        "activation_gate": gate.name if gate else None,
        "enablement_adapter": gate.enablement_adapter if gate else None,
        "enablement_preview": gate.enablement_preview if gate else None,
        "enablement_gate": gate.enablement_gate if gate else None,
        "policy_lock": gate.policy_lock if gate else None,
        "phase9h_freeze": gate.phase9h_freeze if gate else None,
        "rollback_run": gate.rollback_run if gate else None,
        "smoke_run": gate.smoke_run if gate else None,
        "company": gate.company if gate else None,
        "customer": gate.customer if gate else None,
        "payment_entry": gate.payment_entry if gate else None,
        "payment_entry_docstatus_after_rollback": int(gate.payment_entry_docstatus_after_rollback or 0) if gate else 0,
        "payment_entry_amount": flt(gate.payment_entry_amount or 0) if gate else 0,
        "reference_count": int(gate.reference_count or 0) if gate else 0,
        "invoice_outstanding_after_rollback_total": flt(gate.invoice_outstanding_after_rollback_total or 0) if gate else 0,
        "payment_entry_gl_count_after_rollback": int(gate.payment_entry_gl_count_after_rollback or 0) if gate else 0,
        "payment_entry_gl_net_after_rollback": flt(gate.payment_entry_gl_net_after_rollback or 0) if gate else 0,
        "max_batch_lines": int(gate.max_batch_lines or 0) if gate else 0,
        "max_batch_amount": flt(gate.max_batch_amount or 0) if gate else 0,
        "max_payment_entry_count": int(gate.max_payment_entry_count or 0) if gate else 0,
        "allowed_payment_type": gate.allowed_payment_type if gate else "Receive",
        "allowed_reference_doctype": gate.allowed_reference_doctype if gate else "Sales Invoice",
        "locked_policy_mode": gate.locked_policy_mode if gate else "Limited Controlled Production Batch",
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": target_policy,
        "target_policy_name": target_policy or DEFAULT_POLICY_NAME,
        "would_enable_policy_count": 1 if gate else 0,
        "policy_enabled_before_count": guard_before["production_batch_enabled_policy_count"],
        "policy_enabled_after_count": guard_before["production_batch_enabled_policy_count"],
        "actual_enabled_policy_count": 0,
        "target_policy_enabled_before": get_flag(POLICY_DOCTYPE, target_policy, "production_batch_enabled") if target_policy else 0,
        "target_policy_enabled_after": get_flag(POLICY_DOCTYPE, target_policy, "production_batch_enabled") if target_policy else 0,
        "target_policy_live_before": get_flag(POLICY_DOCTYPE, target_policy, "live_posting_allowed") if target_policy else 0,
        "target_policy_live_after": get_flag(POLICY_DOCTYPE, target_policy, "live_posting_allowed") if target_policy else 0,
        "enablement_field": "production_batch_enabled",
        "live_field": "live_posting_allowed",
        "smoke_next_step": "Rollback Required",
        "actual_payment_entry_created_count": 0,
        "actual_gl_created_count": 0,
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guardrails()["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guardrails()["payment_entry_gl_count"],
        "submitted_phase9f_smoke_pe_count": guard_before["submitted_phase9f_smoke_pe_count"],
        "cancelled_phase9f_smoke_pe_count": guard_before["cancelled_phase9f_smoke_pe_count"],
        "submitted_journal_entry_count_today": guard_before["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_before["purchase_invoice_count_today"],
        "live_posting_allowed_policy_count": guard_before["live_posting_allowed_policy_count"],
        **counts,
        "issues": issues,
        "guardrails_before": guard_before,
        "guardrails_after": guardrails(),
        "config": config,
        "required_acknowledgement": SMOKE_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 9O enables exactly one controlled policy flag. It creates no Payment Entry and no GL. Rollback is required.",
    }

    if int(dry_run or 0):
        base_result["status"] = "Needs Review"
        base_result["enablement_smoke_status"] = "Needs Review"
        base_result["limited_policy_enabled"] = 0
        base_result["rollback_required"] = 0
        base_result["freeze_required_after_rollback"] = 0
        return base_result

    doc = frappe.new_doc("NDIS Limited Production Batch Enablement Smoke Run")
    doc.enablement_smoke_id = make_enablement_smoke_id()
    doc.status = base_result["status"]
    doc.enablement_smoke_status = base_result["enablement_smoke_status"]

    for fieldname in [
        "limited_policy_enabled",
        "rollback_required",
        "freeze_required_after_rollback",
        "phase9n_activation_gate_verified",
        "phase9m_adapter_verified",
        "phase9l_preview_verified",
        "phase9k_enablement_design_verified",
        "phase9j_policy_lock_verified",
        "policy_caps_verified",
        "production_batch_posting_allowed",
        "real_posting_allowed",
        "policy_live_enabled",
        "activation_gate",
        "enablement_adapter",
        "enablement_preview",
        "enablement_gate",
        "policy_lock",
        "phase9h_freeze",
        "rollback_run",
        "smoke_run",
        "company",
        "customer",
        "payment_entry",
        "payment_entry_docstatus_after_rollback",
        "payment_entry_amount",
        "reference_count",
        "invoice_outstanding_after_rollback_total",
        "payment_entry_gl_count_after_rollback",
        "payment_entry_gl_net_after_rollback",
        "max_batch_lines",
        "max_batch_amount",
        "max_payment_entry_count",
        "allowed_payment_type",
        "allowed_reference_doctype",
        "locked_policy_mode",
        "target_policy_doctype",
        "target_policy",
        "target_policy_name",
        "would_enable_policy_count",
        "policy_enabled_before_count",
        "policy_enabled_after_count",
        "actual_enabled_policy_count",
        "target_policy_enabled_before",
        "target_policy_enabled_after",
        "target_policy_live_before",
        "target_policy_live_after",
        "enablement_field",
        "live_field",
        "smoke_next_step",
        "actual_payment_entry_created_count",
        "actual_gl_created_count",
        "payment_entry_count_before",
        "payment_entry_count_after",
        "payment_entry_gl_count_before",
        "payment_entry_gl_count_after",
        "submitted_phase9f_smoke_pe_count",
        "cancelled_phase9f_smoke_pe_count",
        "submitted_journal_entry_count_today",
        "purchase_invoice_count_today",
        "live_posting_allowed_policy_count",
        "smoke_score",
        "blocker_count",
        "warning_count",
        "pass_count",
        "info_count",
        "line_count",
    ]:
        setattr(doc, fieldname, base_result.get(fieldname))

    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = SMOKE_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(base_result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    if allowed:
        flag_result = enable_target_policy(target_policy)
        guard_after = guardrails()

        updates = {
            "limited_policy_enabled": 1,
            "rollback_required": 1,
            "freeze_required_after_rollback": 1,
            "policy_enabled_after_count": guard_after["production_batch_enabled_policy_count"],
            "actual_enabled_policy_count": 1,
            "target_policy_enabled_before": flag_result["target_policy_enabled_before"],
            "target_policy_enabled_after": flag_result["target_policy_enabled_after"],
            "target_policy_live_before": flag_result["target_policy_live_before"],
            "target_policy_live_after": flag_result["target_policy_live_after"],
            "payment_entry_count_after": guard_after["payment_entry_count"],
            "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
            "live_posting_allowed_policy_count": guard_after["live_posting_allowed_policy_count"],
            "line_count": 1,
        }

        for fieldname, value in updates.items():
            setattr(doc, fieldname, value)

        doc.summary_json = safe_json({**base_result, **updates, "guardrails_after": guard_after})
        doc.save(ignore_permissions=True)
        create_smoke_line(doc)
    else:
        guard_after = guardrails()
        frappe.db.set_value(
            "NDIS Limited Production Batch Enablement Smoke Run",
            doc.name,
            {
                "payment_entry_count_after": guard_after["payment_entry_count"],
                "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
                "summary_json": safe_json({**base_result, "guardrails_after": guard_after}),
            },
            update_modified=False,
        )

    frappe.db.commit()

    final_doc = frappe.get_doc("NDIS Limited Production Batch Enablement Smoke Run", doc.name)

    result = {
        **base_result,
        "created": True,
        "enablement_smoke": final_doc.name,
        "enablement_smoke_id": final_doc.enablement_smoke_id,
        "status": final_doc.status,
        "enablement_smoke_status": final_doc.enablement_smoke_status,
        "limited_policy_enabled": int(final_doc.limited_policy_enabled or 0),
        "rollback_required": int(final_doc.rollback_required or 0),
        "freeze_required_after_rollback": int(final_doc.freeze_required_after_rollback or 0),
        "policy_enabled_after_count": int(final_doc.policy_enabled_after_count or 0),
        "actual_enabled_policy_count": int(final_doc.actual_enabled_policy_count or 0),
        "target_policy_enabled_before": int(final_doc.target_policy_enabled_before or 0),
        "target_policy_enabled_after": int(final_doc.target_policy_enabled_after or 0),
        "target_policy_live_before": int(final_doc.target_policy_live_before or 0),
        "target_policy_live_after": int(final_doc.target_policy_live_after or 0),
        "guardrails_after": guardrails(),
    }

    return result


@frappe.whitelist()
def cancel_limited_production_batch_enablement_smoke(enablement_smoke, reason=None):
    assert_action("cancel_limited_production_batch_enablement_smoke")

    if not frappe.db.exists("NDIS Limited Production Batch Enablement Smoke Run", enablement_smoke):
        frappe.throw(_("Enablement smoke not found: {0}").format(enablement_smoke))

    doc = frappe.get_doc("NDIS Limited Production Batch Enablement Smoke Run", enablement_smoke)

    if doc.status == "Cancelled":
        return {"enablement_smoke": enablement_smoke, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.limited_policy_enabled or 0):
        frappe.throw(_("Cannot cancel an enabled Phase 9O smoke. Use Phase 9P rollback instead."))

    frappe.db.set_value(
        "NDIS Limited Production Batch Enablement Smoke Run",
        enablement_smoke,
        {
            "status": "Cancelled",
            "enablement_smoke_status": "Cancelled",
            "limited_policy_enabled": 0,
            "rollback_required": 0,
            "freeze_required_after_rollback": 0,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "actual_enabled_policy_count": 0,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 9O no-ack smoke audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        """
        UPDATE `tabNDIS Limited Production Batch Enablement Smoke Line`
        SET line_status = 'Cancelled'
        WHERE enablement_smoke = %(enablement_smoke)s
        """,
        {"enablement_smoke": enablement_smoke},
    )

    frappe.db.commit()

    return {
        "enablement_smoke": enablement_smoke,
        "status": "Cancelled",
        "note": "No-ack smoke audit record cancelled only. No policy or accounting movement occurred.",
    }


@frappe.whitelist()
def quick_limited_production_batch_enablement_smoke_summary(limit=20):
    runs = frappe.get_all(
        "NDIS Limited Production Batch Enablement Smoke Run",
        fields=[
            "name",
            "enablement_smoke_id",
            "status",
            "enablement_smoke_status",
            "limited_policy_enabled",
            "rollback_required",
            "freeze_required_after_rollback",
            "phase9n_activation_gate_verified",
            "phase9m_adapter_verified",
            "phase9l_preview_verified",
            "activation_gate",
            "enablement_adapter",
            "target_policy",
            "target_policy_enabled_before",
            "target_policy_enabled_after",
            "target_policy_live_before",
            "target_policy_live_after",
            "policy_enabled_before_count",
            "policy_enabled_after_count",
            "actual_enabled_policy_count",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
            "live_posting_allowed_policy_count",
            "smoke_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    lines = frappe.get_all(
        "NDIS Limited Production Batch Enablement Smoke Line",
        fields=[
            "name",
            "enablement_smoke",
            "line_no",
            "line_status",
            "policy_name",
            "policy_action",
            "actual_enabled",
            "rollback_required",
            "enabled_before",
            "enabled_after",
            "live_before",
            "live_after",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    return {
        "runs": runs,
        "lines": lines,
        "required_acknowledgement": SMOKE_ACK,
        "guardrails": guardrails(),
        "config": config_state(),
        "note": "Phase 9O limited controlled enablement smoke summary. Rollback is required before freeze.",
    }


def execute_smoke_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("status"):
        conditions.append("s.status = %(status)s")
        params["status"] = filters.get("status")

    columns = smoke_columns()

    data = frappe.db.sql(
        f"""
        SELECT
            s.name AS enablement_smoke,
            s.enablement_smoke_id,
            s.status,
            s.enablement_smoke_status,
            s.limited_policy_enabled,
            s.rollback_required,
            s.freeze_required_after_rollback,
            s.activation_gate,
            s.enablement_adapter,
            s.target_policy_doctype,
            s.target_policy,
            s.max_batch_lines,
            s.max_batch_amount,
            s.max_payment_entry_count,
            s.policy_enabled_before_count,
            s.policy_enabled_after_count,
            s.actual_enabled_policy_count,
            s.target_policy_enabled_before,
            s.target_policy_enabled_after,
            s.target_policy_live_before,
            s.target_policy_live_after,
            s.actual_payment_entry_created_count,
            s.actual_gl_created_count,
            s.live_posting_allowed_policy_count,
            s.smoke_score,
            s.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Limited Production Batch Enablement Smoke Run` s
        {build_where(conditions)}
        ORDER BY s.creation DESC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.enablement_smoke_id for row in data[:20]],
            "datasets": [
                {"name": "Policy Enabled", "values": [int(row.limited_policy_enabled or 0) for row in data[:20]]},
                {"name": "Live Policies", "values": [int(row.live_posting_allowed_policy_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Smoke Runs"), "datatype": "Int"},
        {"value": sum(int(row.limited_policy_enabled or 0) for row in data), "indicator": "Orange", "label": _("Policies Enabled"), "datatype": "Int"},
        {"value": sum(int(row.rollback_required or 0) for row in data), "indicator": "Orange", "label": _("Rollback Required"), "datatype": "Int"},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PE"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def smoke_columns():
    return [
        {"fieldname": "enablement_smoke", "label": _("Enablement Smoke"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Smoke Run", "width": 220},
        {"fieldname": "enablement_smoke_id", "label": _("Smoke ID"), "fieldtype": "Data", "width": 450},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 180},
        {"fieldname": "enablement_smoke_status", "label": _("Smoke Status"), "fieldtype": "Data", "width": 330},
        {"fieldname": "limited_policy_enabled", "label": _("Enabled"), "fieldtype": "Check", "width": 90},
        {"fieldname": "rollback_required", "label": _("Rollback"), "fieldtype": "Check", "width": 90},
        {"fieldname": "freeze_required_after_rollback", "label": _("Freeze"), "fieldtype": "Check", "width": 90},
        {"fieldname": "activation_gate", "label": _("Activation Gate"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Activation Gate", "width": 220},
        {"fieldname": "target_policy_doctype", "label": _("Target Policy DocType"), "fieldtype": "Link", "options": "DocType", "hidden": 1},
        {"fieldname": "target_policy", "label": _("Target Policy"), "fieldtype": "Dynamic Link", "options": "target_policy_doctype", "width": 220},
        {"fieldname": "max_batch_lines", "label": _("Max Lines"), "fieldtype": "Int", "width": 90},
        {"fieldname": "max_batch_amount", "label": _("Max Amount"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "max_payment_entry_count", "label": _("Max PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "policy_enabled_before_count", "label": _("Enabled Before"), "fieldtype": "Int", "width": 120},
        {"fieldname": "policy_enabled_after_count", "label": _("Enabled After"), "fieldtype": "Int", "width": 120},
        {"fieldname": "actual_enabled_policy_count", "label": _("Actual Enabled"), "fieldtype": "Int", "width": 120},
        {"fieldname": "target_policy_live_after", "label": _("Live After"), "fieldtype": "Check", "width": 90},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "smoke_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_line_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("enablement_smoke"):
        conditions.append("l.enablement_smoke = %(enablement_smoke)s")
        params["enablement_smoke"] = filters.get("enablement_smoke")

    if filters.get("line_status"):
        conditions.append("l.line_status = %(line_status)s")
        params["line_status"] = filters.get("line_status")

    columns = [
        {"fieldname": "line", "label": _("Line"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Smoke Line", "width": 220},
        {"fieldname": "enablement_smoke", "label": _("Smoke Run"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Enablement Smoke Run", "width": 220},
        {"fieldname": "line_no", "label": _("Line No"), "fieldtype": "Int", "width": 80},
        {"fieldname": "line_status", "label": _("Status"), "fieldtype": "Data", "width": 180},
        {"fieldname": "policy_name", "label": _("Policy"), "fieldtype": "Data", "width": 240},
        {"fieldname": "policy_action", "label": _("Action"), "fieldtype": "Data", "width": 340},
        {"fieldname": "actual_enabled", "label": _("Enabled"), "fieldtype": "Check", "width": 90},
        {"fieldname": "rollback_required", "label": _("Rollback"), "fieldtype": "Check", "width": 90},
        {"fieldname": "enabled_before", "label": _("Enabled Before"), "fieldtype": "Check", "width": 110},
        {"fieldname": "enabled_after", "label": _("Enabled After"), "fieldtype": "Check", "width": 110},
        {"fieldname": "live_before", "label": _("Live Before"), "fieldtype": "Check", "width": 100},
        {"fieldname": "live_after", "label": _("Live After"), "fieldtype": "Check", "width": 100},
        {"fieldname": "max_batch_lines", "label": _("Max Lines"), "fieldtype": "Int", "width": 90},
        {"fieldname": "max_batch_amount", "label": _("Max Amount"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "max_payment_entry_count", "label": _("Max PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            l.name AS line,
            l.enablement_smoke,
            l.line_no,
            l.line_status,
            l.policy_name,
            l.policy_action,
            l.actual_enabled,
            l.rollback_required,
            l.enabled_before,
            l.enabled_after,
            l.live_before,
            l.live_after,
            l.max_batch_lines,
            l.max_batch_amount,
            l.max_payment_entry_count,
            l.detail,
            l.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Limited Production Batch Enablement Smoke Line` l
        {build_where(conditions)}
        ORDER BY l.enablement_smoke DESC, l.line_no ASC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.policy_name for row in data[:20]],
            "datasets": [
                {"name": "Enabled", "values": [int(row.actual_enabled or 0) for row in data[:20]]},
                {"name": "Live", "values": [int(row.live_after or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Lines"), "datatype": "Int"},
        {"value": sum(int(row.actual_enabled or 0) for row in data), "indicator": "Orange", "label": _("Enabled"), "datatype": "Int"},
        {"value": sum(int(row.live_after or 0) for row in data), "indicator": "Red", "label": _("Live After"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_smoke_report(filters)

    guard = guardrails()

    summary.append({"value": guard["payment_entry_count"], "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"})
    summary.append({"value": guard["payment_entry_gl_count"], "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"})
    summary.append({"value": guard["production_batch_enabled_policy_count"], "indicator": "Orange", "label": _("Enabled Policies"), "datatype": "Int"})
    summary.append({"value": guard["live_posting_allowed_policy_count"], "indicator": "Red", "label": _("Live Policies"), "datatype": "Int"})
    summary.append({"value": guard["submitted_journal_entry_count_today"], "indicator": "Red", "label": _("Submitted JE Today"), "datatype": "Int"})
    summary.append({"value": guard["purchase_invoice_count_today"], "indicator": "Red", "label": _("Purchase Invoice Today"), "datatype": "Int"})

    return columns, data, message, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
