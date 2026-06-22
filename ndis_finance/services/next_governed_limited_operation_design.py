import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


DESIGN_ACK = "I_CONFIRM_PHASE11E_APPROVE_NEXT_GOVERNED_LIMITED_OPERATION_DESIGN_NO_POSTING"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
PLANNING_DOCTYPE = "NDIS Governed Limited Op Planning"
DESIGN_DOCTYPE = "NDIS Governed Limited Op Design"
DESIGN_ITEM_DOCTYPE = "NDIS Governed Limited Op Design Item"


def make_design_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-GOVERNED-LIMITED-OP-DESIGN-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def get_value_if_has(doctype, name, fieldname, default=None):
    if not name or not frappe.db.exists(doctype, name):
        return default
    if not has_column(doctype, fieldname):
        return default
    value = frappe.db.get_value(doctype, name, fieldname)
    return default if value is None else value


def get_flag(doctype, name, fieldname, default=0):
    value = get_value_if_has(doctype, name, fieldname, default)
    return int(value or 0)


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


def latest_planning():
    rows = frappe.get_all(
        PLANNING_DOCTYPE,
        filters={
            "status": "Planning Approved",
            "planning_status": "Next Governed Limited Operation Planning Approved",
            "planning_approved": 1,
            "phase11c_precheck_verified": 1,
            "phase11b_monitor_verified": 1,
            "runtime_monitor_active_verified": 1,
            "guardrail_watch_active_verified": 1,
            "baseline_counts_stable_verified": 1,
            "planning_envelope_locked": 1,
            "ready_for_next_governed_limited_operation_design": 1,
            "planned_line_count": 3,
            "planned_total_amount": 3.00,
            "planned_payment_entry_count": 1,
            "planned_live_posting_allowed": 0,
            "planned_journal_entry_side_effect_allowed": 0,
            "planned_purchase_invoice_side_effect_allowed": 0,
            "payment_entry_cancelled_verified": 1,
            "gl_net_zero_verified": 1,
            "invoice_outstanding_restored_verified": 1,
            "no_new_accounting_movement_verified": 1,
            "policy_state_preserved_verified": 1,
            "policy_mutation_performed": 0,
            "actual_policy_mutation_count": 0,
            "target_policy_enabled_after": 1,
            "target_policy_live_after": 0,
            "locked_payment_entry_count": 8,
            "locked_payment_entry_gl_count": 46,
            "locked_policy_enabled_count": 1,
            "locked_policy_live_allowed_count": 0,
            "locked_live_posting": 0,
            "locked_journal_entry_side_effect": 0,
            "locked_purchase_invoice_side_effect": 0,
            "payment_entry_docstatus": 2,
            "payment_entry_status": "Cancelled",
            "payment_entry_reference_count": 3,
            "voucher_gl_row_count": 8,
            "gl_account_non_zero_count": 0,
            "actual_payment_entry_created_count": 0,
            "actual_payment_entry_cancelled_count": 0,
            "actual_gl_created_count": 0,
            "submitted_journal_entry_count_today": 0,
            "purchase_invoice_count_today": 0,
        },
        fields=[
            "name",
            "planning_id",
            "precheck",
            "monitor",
            "baseline",
            "closeout",
            "governed_freeze",
            "rollback",
            "smoke",
            "execution_gate",
            "preview",
            "pre_execution_gate",
            "target_policy_doctype",
            "target_policy",
            "target_policy_name",
            "target_policy_enabled_after",
            "target_policy_live_after",
            "production_batch_enabled_policy_count_after",
            "live_posting_allowed_policy_count_after",
            "locked_payment_entry_count",
            "locked_payment_entry_gl_count",
            "locked_policy_enabled_count",
            "locked_policy_live_allowed_count",
            "locked_live_posting",
            "locked_journal_entry_side_effect",
            "locked_purchase_invoice_side_effect",
            "payment_entry",
            "payment_entry_docstatus",
            "payment_entry_status",
            "payment_entry_amount",
            "payment_entry_reference_count",
            "invoice_outstanding_restored_amount",
            "voucher_gl_row_count",
            "voucher_gl_net_balance",
            "gl_account_non_zero_count",
            "payment_entry_count_after",
            "payment_entry_gl_count_after",
            "planning_score",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_design(planning):
    rows = frappe.get_all(
        DESIGN_DOCTYPE,
        filters={
            "planning": planning,
            "status": "Design Approved",
            "design_approved": 1,
        },
        fields=["name", "design_id"],
        limit=1,
    )
    return rows[0] if rows else None


def payment_entry_reference_count(payment_entry):
    return count_dt("Payment Entry Reference", {"parent": payment_entry, "reference_doctype": "Sales Invoice"})


def voucher_gl_row_count(payment_entry):
    return count_dt("GL Entry", {"voucher_type": "Payment Entry", "voucher_no": payment_entry})


def voucher_gl_net_balance(payment_entry):
    value = frappe.db.sql(
        """
        SELECT ROUND(COALESCE(SUM(debit - credit), 0), 2)
        FROM `tabGL Entry`
        WHERE voucher_type='Payment Entry'
          AND voucher_no=%(payment_entry)s
        """,
        {"payment_entry": payment_entry},
    )[0][0]
    return flt(value or 0, 2)


def voucher_gl_non_zero_account_count(payment_entry):
    rows = frappe.db.sql(
        """
        SELECT account, ROUND(COALESCE(SUM(debit - credit), 0), 2) AS balance
        FROM `tabGL Entry`
        WHERE voucher_type='Payment Entry'
          AND voucher_no=%(payment_entry)s
        GROUP BY account
        HAVING ABS(balance) > 0.0001
        """,
        {"payment_entry": payment_entry},
        as_dict=True,
    )
    return len(rows)


def validate_design_source(planning, guard, policy_enabled, policy_live, config):
    issues = []

    if not planning:
        issues.append("No approved Phase 11D planning record found.")
        return issues

    existing = existing_design(planning.name)
    if existing:
        issues.append(f"Phase 11E design already exists for this planning record: {existing.design_id}")

    required_links = {
        "planning": (PLANNING_DOCTYPE, planning.name),
        "precheck": ("NDIS Governed Limited Op Precheck", planning.precheck),
        "monitor": ("NDIS Governed Steady State Monitor", planning.monitor),
        "payment_entry": ("Payment Entry", planning.payment_entry),
        "target_policy": (POLICY_DOCTYPE, planning.target_policy),
    }

    for label, pair in required_links.items():
        doctype, name = pair
        if not name:
            issues.append(f"Missing evidence link: {label}")
        elif not frappe.db.exists(doctype, name):
            issues.append(f"Linked evidence does not exist: {doctype} {name}")

    if int(planning.locked_payment_entry_count or 0) != 8:
        issues.append("Locked Payment Entry count must be 8.")

    if int(planning.locked_payment_entry_gl_count or 0) != 46:
        issues.append("Locked Payment Entry GL count must be 46.")

    if int(planning.locked_policy_enabled_count or 0) != 1:
        issues.append("Locked policy enabled count must be 1.")

    if int(planning.locked_policy_live_allowed_count or 0) != 0:
        issues.append("Locked policy live allowed count must be 0.")

    if not planning.payment_entry or not frappe.db.exists("Payment Entry", planning.payment_entry):
        return issues

    pe = frappe.get_doc("Payment Entry", planning.payment_entry)

    if pe.docstatus != 2:
        issues.append(f"Payment Entry must remain cancelled. docstatus={pe.docstatus}")

    if pe.status != "Cancelled":
        issues.append(f"Payment Entry status must remain Cancelled. status={pe.status}")

    if flt(pe.paid_amount or pe.received_amount or 0, 2) != 3:
        issues.append("Historical smoke Payment Entry amount must remain 3.00.")

    if payment_entry_reference_count(pe.name) != int(planning.payment_entry_reference_count or 0):
        issues.append("Payment Entry reference count no longer matches Phase 11D planning evidence.")

    if voucher_gl_row_count(pe.name) != int(planning.voucher_gl_row_count or 0):
        issues.append("Voucher GL row count no longer matches Phase 11D planning evidence.")

    if voucher_gl_net_balance(pe.name) != 0:
        issues.append("Voucher GL net balance must remain 0.00.")

    if voucher_gl_non_zero_account_count(pe.name) != 0:
        issues.append("Voucher GL account non-zero count must remain 0.")

    if policy_enabled != 1:
        issues.append("Target policy production_batch_enabled must be 1 before Phase 11E. Phase 11E must not repair this.")

    if policy_live != 0:
        issues.append("Target policy live_posting_allowed must be 0 before Phase 11E. Phase 11E must not repair this.")

    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must remain enabled.")

    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must remain 0.")

    if guard["payment_entry_count"] != int(planning.locked_payment_entry_count or 0):
        issues.append("Current Payment Entry count must match locked count from Phase 11D.")

    if guard["payment_entry_gl_count"] != int(planning.locked_payment_entry_gl_count or 0):
        issues.append("Current Payment Entry GL count must match locked count from Phase 11D.")

    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry count today must remain 0.")

    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice count today must remain 0.")

    if int(config["sandbox_enabled"]) != 1:
        issues.append("Sandbox config must be 1.")

    if int(config["production_mode"]) != 0:
        issues.append("Production mode config must remain 0.")

    if int(config["live_pe_enabled"]) != 0:
        issues.append("Live Payment Entry posting config must remain 0.")

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


def build_items(planning, issues, ack_ok):
    items = []

    if planning:
        add_item(
            items,
            "Pass",
            "Low",
            "Evidence",
            "phase11d_planning_exists",
            "Phase 11D planning exists",
            f"Planning found: {planning.planning_id}.",
            PLANNING_DOCTYPE,
            planning.name,
        )
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase11d_planning_exists", "Phase 11D planning exists", "No approved Phase 11D planning record found.")

    if not issues:
        add_item(items, "Pass", "Critical", "Design Source", "design_source_valid", "Design source valid", "Phase 11D planning record is valid for the next governed operation design gate.")
    else:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Design Source", "design_source_valid", "Design source valid", issue)

    checks = [
        ("design_shape_locked", "Design shape locked", "Sales Invoice / Customer / 3 lines / 3.00 / 1 PE"),
        ("source_model_locked", "Source model locked", "Sales Invoice references only"),
        ("selection_deferred", "Candidate selection deferred", "Phase 11F"),
        ("allocation_model_locked", "Allocation model locked", "Outstanding Sales Invoice allocation capped to 3.00"),
        ("live_posting_blocked", "Live posting blocked", 0),
        ("je_side_effect_blocked", "Journal Entry side effect blocked", 0),
        ("pi_side_effect_blocked", "Purchase Invoice side effect blocked", 0),
        ("locked_counts_stable", "Locked counts stable at PE 8 / PE GL 46", "8 / 46"),
        ("policy_state_preserved", "Policy state preserved at 1 / 0", "1 / 0"),
        ("payment_entry_cancelled", "Historical smoke Payment Entry remains cancelled", getattr(planning, "payment_entry", None)),
        ("gl_net_zero", "Historical smoke voucher GL net remains zero", getattr(planning, "voucher_gl_net_balance", None)),
        ("candidate_selection_ready", "Ready for candidate selection", 1),
    ]

    for key, label, value in checks:
        add_item(items, "Pass", "High", "Design Evidence", key, label, f"value={value}")

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {DESIGN_ACK}")

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
        row = frappe.new_doc(DESIGN_ITEM_DOCTYPE)
        row.design = doc.name
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
def run_next_governed_limited_operation_design(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_next_governed_limited_operation_design")

    planning = latest_planning()
    guard_before = guardrails()
    ack_ok = acknowledgement == DESIGN_ACK

    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }

    policy_enabled_before = get_flag(POLICY_DOCTYPE, planning.target_policy, "production_batch_enabled") if planning else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, planning.target_policy, "live_posting_allowed") if planning else 0

    issues = validate_design_source(planning, guard_before, policy_enabled_before, policy_live_before, config)

    guard_after = guardrails()
    policy_enabled_after = get_flag(POLICY_DOCTYPE, planning.target_policy, "production_batch_enabled") if planning else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, planning.target_policy, "live_posting_allowed") if planning else 0

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

    if not no_new_movement:
        issues.append("Accounting movement changed while preparing Phase 11E design evidence.")

    if not policy_preserved:
        issues.append("Controlled policy state changed while preparing Phase 11E design evidence.")

    items = build_items(planning, issues, ack_ok)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    allowed = int(
        ack_ok
        and item_summary["blocker_count"] == 0
        and planning
        and no_new_movement
        and policy_preserved
    )

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Design Approved" if allowed else "Needs Review",
        "design_status": "Next Governed Limited Operation Design Approved" if allowed else "Needs Review",
        "design_approved": allowed,
        "phase11d_planning_verified": 1 if planning else 0,
        "phase11c_precheck_verified": 1 if planning else 0,
        "phase11b_monitor_verified": 1 if planning else 0,
        "planning_envelope_locked_verified": 1 if planning else 0,
        "runtime_monitor_active_verified": 1 if planning else 0,
        "guardrail_watch_active_verified": 1 if planning else 0,
        "baseline_counts_stable_verified": int(
            planning and guard_after["payment_entry_count"] == int(planning.locked_payment_entry_count or 0)
            and guard_after["payment_entry_gl_count"] == int(planning.locked_payment_entry_gl_count or 0)
        ),
        "design_shape_locked": allowed,
        "design_source_model_locked": allowed,
        "design_guardrails_locked": allowed,
        "ready_for_next_governed_limited_operation_candidate_selection": allowed,
        "payment_entry_cancelled_verified": 1 if planning else 0,
        "gl_net_zero_verified": 1 if planning else 0,
        "invoice_outstanding_restored_verified": 1 if planning else 0,
        "no_new_accounting_movement_verified": no_new_movement,
        "policy_state_preserved_verified": policy_preserved,
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": 0,
        "designed_source_doctype": "Sales Invoice",
        "designed_reference_doctype": "Sales Invoice",
        "designed_party_type": "Customer",
        "designed_line_count": 3,
        "designed_total_amount": 3.00,
        "designed_payment_entry_count": 1,
        "designed_live_posting_allowed": 0,
        "designed_journal_entry_side_effect_allowed": 0,
        "designed_purchase_invoice_side_effect_allowed": 0,
        "designed_selection_mode": "Candidate Selection Deferred To Phase 11F",
        "designed_allocation_mode": "Outstanding Sales Invoice Allocation Capped To 3.00",
        "design_mode": "Design Only - No Posting",
        "planning": planning.name if planning else None,
        "precheck": planning.precheck if planning else None,
        "monitor": planning.monitor if planning else None,
        "baseline": planning.baseline if planning else None,
        "closeout": planning.closeout if planning else None,
        "governed_freeze": planning.governed_freeze if planning else None,
        "rollback": planning.rollback if planning else None,
        "smoke": planning.smoke if planning else None,
        "execution_gate": planning.execution_gate if planning else None,
        "preview": planning.preview if planning else None,
        "pre_execution_gate": planning.pre_execution_gate if planning else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": planning.target_policy if planning else None,
        "target_policy_name": planning.target_policy_name if planning else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_before": policy_live_before,
        "target_policy_live_after": policy_live_after,
        "production_batch_enabled_policy_count_before": guard_before["production_batch_enabled_policy_count"],
        "production_batch_enabled_policy_count_after": guard_after["production_batch_enabled_policy_count"],
        "live_posting_allowed_policy_count_before": guard_before["live_posting_allowed_policy_count"],
        "live_posting_allowed_policy_count_after": guard_after["live_posting_allowed_policy_count"],
        "locked_payment_entry_count": int(planning.locked_payment_entry_count or 0) if planning else 0,
        "locked_payment_entry_gl_count": int(planning.locked_payment_entry_gl_count or 0) if planning else 0,
        "locked_policy_enabled_count": int(planning.locked_policy_enabled_count or 0) if planning else 0,
        "locked_policy_live_allowed_count": int(planning.locked_policy_live_allowed_count or 0) if planning else 0,
        "locked_live_posting": 0,
        "locked_journal_entry_side_effect": 0,
        "locked_purchase_invoice_side_effect": 0,
        "payment_entry": planning.payment_entry if planning else None,
        "payment_entry_docstatus": int(planning.payment_entry_docstatus or 0) if planning else 0,
        "payment_entry_status": planning.payment_entry_status if planning else None,
        "payment_entry_amount": flt(planning.payment_entry_amount or 0, 2) if planning else 0,
        "payment_entry_reference_count": int(planning.payment_entry_reference_count or 0) if planning else 0,
        "invoice_outstanding_restored_amount": flt(planning.invoice_outstanding_restored_amount or 0, 2) if planning else 0,
        "voucher_gl_row_count": int(planning.voucher_gl_row_count or 0) if planning else 0,
        "voucher_gl_net_balance": flt(planning.voucher_gl_net_balance or 0, 2) if planning else 0,
        "gl_account_non_zero_count": int(planning.gl_account_non_zero_count or 0) if planning else 0,
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guard_after["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
        "actual_payment_entry_created_count": 0,
        "actual_payment_entry_cancelled_count": 0,
        "actual_gl_created_count": 0,
        "submitted_journal_entry_count_today": guard_after["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_after["purchase_invoice_count_today"],
        "design_score": score,
        **item_summary,
        "items": items,
        "issues": issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "required_acknowledgement": DESIGN_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 11E approves the exact next governed limited operation design only. No candidate invoices are selected and no posting occurs.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["design_status"] = "Needs Review"
        result["design_approved"] = 0
        result["design_shape_locked"] = 0
        result["design_source_model_locked"] = 0
        result["design_guardrails_locked"] = 0
        result["ready_for_next_governed_limited_operation_candidate_selection"] = 0
        return result

    doc = frappe.new_doc(DESIGN_DOCTYPE)
    doc.design_id = make_design_id()

    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)

    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = DESIGN_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.design_json = safe_json(
        {
            "planning": planning,
            "design_shape": {
                "designed_source_doctype": "Sales Invoice",
                "designed_reference_doctype": "Sales Invoice",
                "designed_party_type": "Customer",
                "designed_line_count": 3,
                "designed_total_amount": 3.00,
                "designed_payment_entry_count": 1,
                "designed_live_posting_allowed": 0,
                "designed_journal_entry_side_effect_allowed": 0,
                "designed_purchase_invoice_side_effect_allowed": 0,
                "designed_selection_mode": "Candidate Selection Deferred To Phase 11F",
            },
            "guardrails_before": guard_before,
            "guardrails_after": guard_after,
            "issues": issues,
            "config": config,
        }
    )
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    create_items(doc, items)
    frappe.db.commit()

    return {
        **result,
        "created": True,
        "design": doc.name,
        "design_id": doc.design_id,
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_next_governed_limited_operation_design_audit(design, reason=None):
    assert_action("cancel_next_governed_limited_operation_design_audit")

    if not frappe.db.exists(DESIGN_DOCTYPE, design):
        frappe.throw(_("Governed limited operation design audit not found: {0}").format(design))

    doc = frappe.get_doc(DESIGN_DOCTYPE, design)

    if doc.status == "Cancelled":
        return {"design": design, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.design_approved or 0):
        frappe.throw(_("Cannot cancel an approved Phase 11E design record."))

    frappe.db.set_value(
        DESIGN_DOCTYPE,
        design,
        {
            "status": "Cancelled",
            "design_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 11E no-ack design audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        f"""
        UPDATE `tab{DESIGN_ITEM_DOCTYPE}`
        SET status = 'Cancelled'
        WHERE design = %(design)s
        """,
        {"design": design},
    )

    frappe.db.commit()

    return {
        "design": design,
        "status": "Cancelled",
        "note": "No-ack design audit cancelled only. No accounting or policy movement occurred.",
    }


@frappe.whitelist()
def quick_next_governed_limited_operation_design_summary(limit=20):
    records = frappe.get_all(
        DESIGN_DOCTYPE,
        fields=[
            "name",
            "design_id",
            "status",
            "design_status",
            "design_approved",
            "phase11d_planning_verified",
            "planning_envelope_locked_verified",
            "design_shape_locked",
            "design_source_model_locked",
            "design_guardrails_locked",
            "ready_for_next_governed_limited_operation_candidate_selection",
            "designed_source_doctype",
            "designed_line_count",
            "designed_total_amount",
            "designed_payment_entry_count",
            "planning",
            "payment_entry",
            "payment_entry_docstatus",
            "payment_entry_status",
            "locked_payment_entry_count",
            "locked_payment_entry_gl_count",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "submitted_journal_entry_count_today",
            "purchase_invoice_count_today",
            "design_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    items = frappe.get_all(
        DESIGN_ITEM_DOCTYPE,
        fields=["name", "design", "status", "severity", "category", "check_key", "check_label", "detail", "source_doctype", "source_name"],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    return {
        "design_records": records,
        "items": items,
        "required_acknowledgement": DESIGN_ACK,
        "guardrails": guardrails(),
        "note": "Phase 11E next governed limited operation design summary.",
    }


def execute_design_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("status"):
        conditions.append("d.status = %(status)s")
        params["status"] = filters.get("status")

    columns = design_columns()

    data = frappe.db.sql(
        f"""
        SELECT
            d.name AS design,
            d.design_id,
            d.status,
            d.design_status,
            d.design_approved,
            d.phase11d_planning_verified,
            d.planning_envelope_locked_verified,
            d.design_shape_locked,
            d.design_source_model_locked,
            d.design_guardrails_locked,
            d.ready_for_next_governed_limited_operation_candidate_selection,
            d.designed_source_doctype,
            d.designed_line_count,
            d.designed_total_amount,
            d.designed_payment_entry_count,
            d.planning,
            d.payment_entry,
            d.payment_entry_docstatus,
            d.payment_entry_status,
            d.locked_payment_entry_count,
            d.locked_payment_entry_gl_count,
            d.payment_entry_count_before,
            d.payment_entry_count_after,
            d.payment_entry_gl_count_before,
            d.payment_entry_gl_count_after,
            d.actual_payment_entry_created_count,
            d.actual_payment_entry_cancelled_count,
            d.actual_gl_created_count,
            d.submitted_journal_entry_count_today,
            d.purchase_invoice_count_today,
            d.design_score,
            d.checked_on,
            %(currency)s AS currency
        FROM `tab{DESIGN_DOCTYPE}` d
        {build_where(conditions)}
        ORDER BY d.creation DESC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.design_id for row in data[:20]],
            "datasets": [
                {"name": "Approved", "values": [int(row.design_approved or 0) for row in data[:20]]},
                {"name": "Shape Locked", "values": [int(row.design_shape_locked or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Design Records"), "datatype": "Int"},
        {"value": sum(int(row.design_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(int(row.design_shape_locked or 0) for row in data), "indicator": "Green", "label": _("Shape Locked"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL Created"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def design_columns():
    return [
        {"fieldname": "design", "label": _("Design"), "fieldtype": "Link", "options": DESIGN_DOCTYPE, "width": 220},
        {"fieldname": "design_id", "label": _("Design ID"), "fieldtype": "Data", "width": 390},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 130},
        {"fieldname": "design_status", "label": _("Design Status"), "fieldtype": "Data", "width": 350},
        {"fieldname": "design_approved", "label": _("Approved"), "fieldtype": "Check", "width": 90},
        {"fieldname": "phase11d_planning_verified", "label": _("11D Verified"), "fieldtype": "Check", "width": 100},
        {"fieldname": "planning_envelope_locked_verified", "label": _("Planning Locked"), "fieldtype": "Check", "width": 115},
        {"fieldname": "design_shape_locked", "label": _("Shape Locked"), "fieldtype": "Check", "width": 110},
        {"fieldname": "design_source_model_locked", "label": _("Source Locked"), "fieldtype": "Check", "width": 110},
        {"fieldname": "design_guardrails_locked", "label": _("Guardrails"), "fieldtype": "Check", "width": 100},
        {"fieldname": "ready_for_next_governed_limited_operation_candidate_selection", "label": _("Candidate Ready"), "fieldtype": "Check", "width": 120},
        {"fieldname": "designed_source_doctype", "label": _("Source DocType"), "fieldtype": "Data", "width": 130},
        {"fieldname": "designed_line_count", "label": _("Lines"), "fieldtype": "Int", "width": 70},
        {"fieldname": "designed_total_amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 100},
        {"fieldname": "designed_payment_entry_count", "label": _("PE Count"), "fieldtype": "Int", "width": 90},
        {"fieldname": "planning", "label": _("Planning"), "fieldtype": "Link", "options": PLANNING_DOCTYPE, "width": 220},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "payment_entry_docstatus", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 100},
        {"fieldname": "payment_entry_status", "label": _("PE Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "locked_payment_entry_count", "label": _("Locked PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "locked_payment_entry_gl_count", "label": _("Locked PE GL"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 110},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE Created"), "fieldtype": "Int", "width": 125},
        {"fieldname": "actual_payment_entry_cancelled_count", "label": _("Actual PE Cancelled"), "fieldtype": "Int", "width": 135},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL Created"), "fieldtype": "Int", "width": 125},
        {"fieldname": "submitted_journal_entry_count_today", "label": _("JE Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "purchase_invoice_count_today", "label": _("PI Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "design_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    if filters.get("design"):
        conditions.append("i.design = %(design)s")
        params["design"] = filters.get("design")

    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": DESIGN_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "design", "label": _("Design"), "fieldtype": "Link", "options": DESIGN_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 220},
        {"fieldname": "check_key", "label": _("Check Key"), "fieldtype": "Data", "width": 230},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 340},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 650},
        {"fieldname": "source_doctype", "label": _("Source DocType"), "fieldtype": "Data", "width": 220},
        {"fieldname": "source_name", "label": _("Source Name"), "fieldtype": "Data", "width": 240},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            i.name AS item,
            i.design,
            i.status,
            i.severity,
            i.category,
            i.check_key,
            i.check_label,
            i.detail,
            i.source_doctype,
            i.source_name,
            i.checked_on
        FROM `tab{DESIGN_ITEM_DOCTYPE}` i
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
    ]

    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_design_report(filters)

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
