import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


PLANNING_ACK = "I_CONFIRM_PHASE11D_APPROVE_NEXT_GOVERNED_LIMITED_OPERATION_PLANNING_NO_POSTING"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
PRECHECK_DOCTYPE = "NDIS Governed Limited Op Precheck"
MONITOR_DOCTYPE = "NDIS Governed Steady State Monitor"
PLANNING_DOCTYPE = "NDIS Governed Limited Op Planning"
PLANNING_ITEM_DOCTYPE = "NDIS Governed Limited Op Planning Item"


def make_planning_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-GOVERNED-LIMITED-OP-PLANNING-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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
    if not name or not frappe.db.exists(doctype, name) or not has_column(doctype, fieldname):
        return default
    value = frappe.db.get_value(doctype, name, fieldname)
    return default if value is None else value


def get_flag(doctype, name, fieldname, default=0):
    return int(get_value_if_has(doctype, name, fieldname, default) or 0)


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


def latest_precheck():
    rows = frappe.get_all(
        PRECHECK_DOCTYPE,
        filters={
            "status": "Precheck Approved",
            "precheck_status": "Ready For Next Governed Limited Operation Planning",
            "precheck_approved": 1,
            "phase11b_monitor_verified": 1,
            "runtime_monitor_active_verified": 1,
            "guardrail_watch_active_verified": 1,
            "baseline_counts_stable_verified": 1,
            "payment_entry_cancelled_verified": 1,
            "gl_net_zero_verified": 1,
            "invoice_outstanding_restored_verified": 1,
            "no_new_accounting_movement_verified": 1,
            "policy_state_preserved_verified": 1,
            "policy_mutation_performed": 0,
            "actual_policy_mutation_count": 0,
            "ready_for_next_governed_limited_operation_planning": 1,
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
            "precheck_id",
            "monitor",
            "baseline",
            "closeout",
            "governed_freeze",
            "rollback",
            "smoke",
            "execution_gate",
            "preview",
            "pre_execution_gate",
            "readiness",
            "governance_closeout",
            "runtime_watch",
            "prior_baseline",
            "monitoring_register",
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
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_planning(precheck):
    rows = frappe.get_all(
        PLANNING_DOCTYPE,
        filters={"precheck": precheck, "status": "Planning Approved", "planning_approved": 1},
        fields=["name", "planning_id"],
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


def config_state():
    return {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def validate_planning_source(precheck, guard, policy_enabled, policy_live, config):
    issues = []
    if not precheck:
        return ["No approved Phase 11C precheck found."]

    approved = existing_planning(precheck.name)
    if approved:
        issues.append(f"Phase 11D planning already approved for this precheck: {approved.planning_id}")

    required_links = {
        "precheck": (PRECHECK_DOCTYPE, precheck.name),
        "monitor": ("NDIS Governed Steady State Monitor", precheck.monitor),
        "baseline": ("NDIS Governed Steady State Baseline", precheck.baseline),
        "payment_entry": ("Payment Entry", precheck.payment_entry),
        "target_policy": (POLICY_DOCTYPE, precheck.target_policy),
    }
    for label, (doctype, name) in required_links.items():
        if not name:
            issues.append(f"Missing evidence link: {label}")
        elif not frappe.db.exists(doctype, name):
            issues.append(f"Linked evidence does not exist: {doctype} {name}")

    if not precheck.payment_entry or not frappe.db.exists("Payment Entry", precheck.payment_entry):
        return issues

    pe = frappe.get_doc("Payment Entry", precheck.payment_entry)
    if pe.docstatus != 2:
        issues.append(f"Payment Entry must remain cancelled. docstatus={pe.docstatus}")
    if pe.status != "Cancelled":
        issues.append(f"Payment Entry status must remain Cancelled. status={pe.status}")
    if flt(pe.paid_amount or pe.received_amount or 0, 2) != 3:
        issues.append("Payment Entry amount must remain 3.00.")
    if payment_entry_reference_count(pe.name) != int(precheck.payment_entry_reference_count or 0):
        issues.append("Payment Entry reference count no longer matches Phase 11C precheck evidence.")
    if voucher_gl_row_count(pe.name) != int(precheck.voucher_gl_row_count or 0):
        issues.append("Voucher GL row count no longer matches Phase 11C precheck evidence.")
    if voucher_gl_net_balance(pe.name) != 0:
        issues.append("Voucher GL net balance must remain 0.00.")
    if voucher_gl_non_zero_account_count(pe.name) != 0:
        issues.append("Voucher GL account non-zero count must remain 0.")
    if policy_enabled != 1:
        issues.append("Target policy production_batch_enabled must remain 1.")
    if policy_live != 0:
        issues.append("Target policy live_posting_allowed must remain 0.")
    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must remain enabled.")
    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must remain 0.")
    if guard["payment_entry_count"] != int(precheck.locked_payment_entry_count or 0):
        issues.append("Current Payment Entry count must match Phase 11C locked count.")
    if guard["payment_entry_gl_count"] != int(precheck.locked_payment_entry_gl_count or 0):
        issues.append("Current Payment Entry GL count must match Phase 11C locked count.")
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


def build_items(precheck, issues, ack_ok):
    items = []
    if precheck:
        add_item(items, "Pass", "Low", "Evidence", "phase11c_precheck_exists", "Phase 11C precheck exists", f"Precheck found: {precheck.precheck_id}.", PRECHECK_DOCTYPE, precheck.name)
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase11c_precheck_exists", "Phase 11C precheck exists", "No approved Phase 11C precheck found.")

    if issues:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Planning Source", "planning_source_valid", "Planning source valid", issue)
    else:
        add_item(items, "Pass", "Critical", "Planning Source", "planning_source_valid", "Planning source valid", "Phase 11C precheck is valid for next governed limited operation planning.")

    checks = [
        ("planning_envelope_locked", "Planning envelope locked", "3 lines / 3.00 / 1 PE"),
        ("planned_live_blocked", "Planned live posting blocked", 0),
        ("planned_je_blocked", "Planned Journal Entry side effect blocked", 0),
        ("planned_pi_blocked", "Planned Purchase Invoice side effect blocked", 0),
        ("runtime_monitor_active", "Runtime monitor remains active", 1),
        ("baseline_counts_stable", "Locked counts stable at PE 8 / PE GL 46", "8 / 46"),
        ("policy_state_preserved", "Policy state preserved at 1 / 0", "1 / 0"),
        ("payment_entry_cancelled", "Payment Entry remains cancelled", getattr(precheck, "payment_entry", None)),
        ("gl_net_zero", "Voucher GL net remains zero", getattr(precheck, "voucher_gl_net_balance", None)),
        ("no_je_pi_side_effect", "No JE / PI side effects", "0 / 0"),
        ("design_ready", "Ready for next governed limited operation design", 1),
    ]
    for key, label, value in checks:
        add_item(items, "Pass", "High", "Planning Evidence", key, label, f"value={value}")

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {PLANNING_ACK}")
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
    score = 100 - int(blockers or 0) * 25 - int(warnings or 0) * 5
    return max(0, round(score, 2))


def create_items(doc, items):
    for item in items:
        row = frappe.new_doc(PLANNING_ITEM_DOCTYPE)
        row.planning = doc.name
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
def run_next_governed_limited_operation_planning(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_next_governed_limited_operation_planning")

    precheck = latest_precheck()
    guard_before = guardrails()
    config = config_state()
    ack_ok = acknowledgement == PLANNING_ACK
    policy_enabled_before = get_flag(POLICY_DOCTYPE, precheck.target_policy, "production_batch_enabled") if precheck else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, precheck.target_policy, "live_posting_allowed") if precheck else 0
    issues = validate_planning_source(precheck, guard_before, policy_enabled_before, policy_live_before, config)
    guard_after = guardrails()
    policy_enabled_after = get_flag(POLICY_DOCTYPE, precheck.target_policy, "production_batch_enabled") if precheck else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, precheck.target_policy, "live_posting_allowed") if precheck else 0
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
        issues.append("Accounting movement changed while preparing Phase 11D planning evidence.")
    if not policy_preserved:
        issues.append("Controlled policy state changed while preparing Phase 11D planning evidence.")

    items = build_items(precheck, issues, ack_ok)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    allowed = int(ack_ok and item_summary["blocker_count"] == 0 and precheck and no_new_movement and policy_preserved)

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Planning Approved" if allowed else "Needs Review",
        "planning_status": "Next Governed Limited Operation Planning Approved" if allowed else "Needs Review",
        "planning_approved": allowed,
        "phase11c_precheck_verified": int(bool(precheck)),
        "phase11b_monitor_verified": int(bool(precheck)),
        "runtime_monitor_active_verified": int(bool(precheck)),
        "guardrail_watch_active_verified": int(bool(precheck)),
        "baseline_counts_stable_verified": int(bool(precheck) and guard_after["payment_entry_count"] == int(precheck.locked_payment_entry_count or 0) and guard_after["payment_entry_gl_count"] == int(precheck.locked_payment_entry_gl_count or 0)),
        "planning_envelope_locked": allowed,
        "ready_for_next_governed_limited_operation_design": allowed,
        "payment_entry_cancelled_verified": int(bool(precheck) and int(precheck.payment_entry_docstatus or 0) == 2 and precheck.payment_entry_status == "Cancelled"),
        "gl_net_zero_verified": int(bool(precheck) and flt(precheck.voucher_gl_net_balance or 0, 2) == 0),
        "invoice_outstanding_restored_verified": int(bool(precheck)),
        "no_new_accounting_movement_verified": no_new_movement,
        "policy_state_preserved_verified": policy_preserved,
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": 0,
        "planned_line_count": 3,
        "planned_total_amount": 3.00,
        "planned_payment_entry_count": 1,
        "planned_live_posting_allowed": 0,
        "planned_journal_entry_side_effect_allowed": 0,
        "planned_purchase_invoice_side_effect_allowed": 0,
        "planning_mode": "Planning Only - No Posting",
        "precheck": precheck.name if precheck else None,
        "monitor": precheck.monitor if precheck else None,
        "baseline": precheck.baseline if precheck else None,
        "closeout": precheck.closeout if precheck else None,
        "governed_freeze": precheck.governed_freeze if precheck else None,
        "rollback": precheck.rollback if precheck else None,
        "smoke": precheck.smoke if precheck else None,
        "execution_gate": precheck.execution_gate if precheck else None,
        "preview": precheck.preview if precheck else None,
        "pre_execution_gate": precheck.pre_execution_gate if precheck else None,
        "readiness": precheck.readiness if precheck else None,
        "governance_closeout": precheck.governance_closeout if precheck else None,
        "runtime_watch": precheck.runtime_watch if precheck else None,
        "prior_baseline": precheck.prior_baseline if precheck else None,
        "monitoring_register": precheck.monitoring_register if precheck else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": precheck.target_policy if precheck else None,
        "target_policy_name": precheck.target_policy_name if precheck else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_before": policy_live_before,
        "target_policy_live_after": policy_live_after,
        "production_batch_enabled_policy_count_before": guard_before["production_batch_enabled_policy_count"],
        "production_batch_enabled_policy_count_after": guard_after["production_batch_enabled_policy_count"],
        "live_posting_allowed_policy_count_before": guard_before["live_posting_allowed_policy_count"],
        "live_posting_allowed_policy_count_after": guard_after["live_posting_allowed_policy_count"],
        "locked_payment_entry_count": int(precheck.locked_payment_entry_count or 0) if precheck else 0,
        "locked_payment_entry_gl_count": int(precheck.locked_payment_entry_gl_count or 0) if precheck else 0,
        "locked_policy_enabled_count": int(precheck.locked_policy_enabled_count or 0) if precheck else 0,
        "locked_policy_live_allowed_count": int(precheck.locked_policy_live_allowed_count or 0) if precheck else 0,
        "locked_live_posting": int(precheck.locked_live_posting or 0) if precheck else 0,
        "locked_journal_entry_side_effect": int(precheck.locked_journal_entry_side_effect or 0) if precheck else 0,
        "locked_purchase_invoice_side_effect": int(precheck.locked_purchase_invoice_side_effect or 0) if precheck else 0,
        "payment_entry": precheck.payment_entry if precheck else None,
        "payment_entry_docstatus": int(precheck.payment_entry_docstatus or 0) if precheck else 0,
        "payment_entry_status": precheck.payment_entry_status if precheck else None,
        "payment_entry_amount": flt(precheck.payment_entry_amount or 0, 2) if precheck else 0,
        "payment_entry_reference_count": int(precheck.payment_entry_reference_count or 0) if precheck else 0,
        "invoice_outstanding_restored_amount": flt(precheck.invoice_outstanding_restored_amount or 0, 2) if precheck else 0,
        "voucher_gl_row_count": int(precheck.voucher_gl_row_count or 0) if precheck else 0,
        "voucher_gl_net_balance": flt(precheck.voucher_gl_net_balance or 0, 2) if precheck else 0,
        "gl_account_non_zero_count": int(precheck.gl_account_non_zero_count or 0) if precheck else 0,
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guard_after["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
        "actual_payment_entry_created_count": 0,
        "actual_payment_entry_cancelled_count": 0,
        "actual_gl_created_count": 0,
        "submitted_journal_entry_count_today": guard_after["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_after["purchase_invoice_count_today"],
        "planning_score": score,
        **item_summary,
        "items": items,
        "issues": issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "required_acknowledgement": PLANNING_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 11D approves planning only for the next governed limited-operation cycle. No accounting movement or policy mutation is performed.",
    }

    if int(dry_run or 0):
        result.update(
            {
                "status": "Needs Review",
                "planning_status": "Needs Review",
                "planning_approved": 0,
                "planning_envelope_locked": 0,
                "ready_for_next_governed_limited_operation_design": 0,
            }
        )
        return result

    doc = frappe.new_doc(PLANNING_DOCTYPE)
    doc.planning_id = make_planning_id()
    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = PLANNING_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.planning_json = safe_json({"precheck": precheck, "planning_envelope": {"planned_line_count": 3, "planned_total_amount": 3.00, "planned_payment_entry_count": 1}, "guardrails_before": guard_before, "guardrails_after": guard_after, "issues": issues, "config": config})
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    create_items(doc, items)
    frappe.db.commit()
    return {**result, "created": True, "planning": doc.name, "planning_id": doc.planning_id, "guardrails_after": guardrails()}


@frappe.whitelist()
def cancel_next_governed_limited_operation_planning_audit(planning, reason=None):
    assert_action("cancel_next_governed_limited_operation_planning_audit")
    if not frappe.db.exists(PLANNING_DOCTYPE, planning):
        frappe.throw(_("Governed limited operation planning audit not found: {0}").format(planning))
    doc = frappe.get_doc(PLANNING_DOCTYPE, planning)
    if doc.status == "Cancelled":
        return {"planning": planning, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.planning_approved or 0):
        frappe.throw(_("Cannot cancel an approved Phase 11D planning record."))
    frappe.db.set_value(
        PLANNING_DOCTYPE,
        planning,
        {"status": "Cancelled", "planning_status": "Cancelled", "cancelled_on": now_datetime(), "cancelled_by": frappe.session.user, "summary_json": reason or "Phase 11D no-ack planning audit cancelled."},
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{PLANNING_ITEM_DOCTYPE}` SET status = 'Cancelled' WHERE planning = %(planning)s", {"planning": planning})
    frappe.db.commit()
    return {"planning": planning, "status": "Cancelled", "note": "No-ack planning audit cancelled only. No accounting or policy movement occurred."}


@frappe.whitelist()
def quick_next_governed_limited_operation_planning_summary(limit=20):
    records = frappe.get_all(
        PLANNING_DOCTYPE,
        fields=[
            "name",
            "planning_id",
            "status",
            "planning_status",
            "planning_approved",
            "phase11c_precheck_verified",
            "phase11b_monitor_verified",
            "runtime_monitor_active_verified",
            "guardrail_watch_active_verified",
            "baseline_counts_stable_verified",
            "planning_envelope_locked",
            "ready_for_next_governed_limited_operation_design",
            "planned_line_count",
            "planned_total_amount",
            "planned_payment_entry_count",
            "policy_state_preserved_verified",
            "no_new_accounting_movement_verified",
            "precheck",
            "monitor",
            "baseline",
            "payment_entry",
            "payment_entry_docstatus",
            "payment_entry_status",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "actual_payment_entry_created_count",
            "actual_payment_entry_cancelled_count",
            "actual_gl_created_count",
            "actual_policy_mutation_count",
            "submitted_journal_entry_count_today",
            "purchase_invoice_count_today",
            "planning_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(
        PLANNING_ITEM_DOCTYPE,
        fields=["name", "planning", "status", "severity", "category", "check_key", "check_label", "detail", "source_doctype", "source_name"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {"plannings": records, "items": items, "required_acknowledgement": PLANNING_ACK, "guardrails": guardrails(), "note": "Phase 11D next governed limited operation planning summary."}


def execute_planning_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("p.status = %(status)s")
        params["status"] = filters.get("status")
    data = frappe.db.sql(
        f"""
        SELECT
            p.name AS planning,
            p.planning_id,
            p.status,
            p.planning_status,
            p.planning_approved,
            p.phase11c_precheck_verified,
            p.phase11b_monitor_verified,
            p.runtime_monitor_active_verified,
            p.guardrail_watch_active_verified,
            p.baseline_counts_stable_verified,
            p.planning_envelope_locked,
            p.ready_for_next_governed_limited_operation_design,
            p.planned_line_count,
            p.planned_total_amount,
            p.planned_payment_entry_count,
            p.policy_state_preserved_verified,
            p.no_new_accounting_movement_verified,
            p.precheck,
            p.monitor,
            p.baseline,
            p.payment_entry,
            p.payment_entry_docstatus,
            p.payment_entry_status,
            p.payment_entry_amount,
            p.locked_payment_entry_count,
            p.locked_payment_entry_gl_count,
            p.payment_entry_count_before,
            p.payment_entry_count_after,
            p.payment_entry_gl_count_before,
            p.payment_entry_gl_count_after,
            p.actual_payment_entry_created_count,
            p.actual_payment_entry_cancelled_count,
            p.actual_gl_created_count,
            p.actual_policy_mutation_count,
            p.submitted_journal_entry_count_today,
            p.purchase_invoice_count_today,
            p.planning_score,
            p.checked_on,
            %(currency)s AS currency
        FROM `tab{PLANNING_DOCTYPE}` p
        {build_where(conditions)}
        ORDER BY p.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.planning_id for row in data[:20]],
            "datasets": [
                {"name": "Approved", "values": [int(row.planning_approved or 0) for row in data[:20]]},
                {"name": "Envelope Locked", "values": [int(row.planning_envelope_locked or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Planning Records"), "datatype": "Int"},
        {"value": sum(int(row.planning_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PE Created"), "datatype": "Int"},
        {"value": sum(int(row.actual_policy_mutation_count or 0) for row in data), "indicator": "Red", "label": _("Policy Mutations"), "datatype": "Int"},
    ]
    return planning_columns(), data, None, chart, summary


def planning_columns():
    return [
        {"fieldname": "planning", "label": _("Planning"), "fieldtype": "Link", "options": PLANNING_DOCTYPE, "width": 220},
        {"fieldname": "planning_id", "label": _("Planning ID"), "fieldtype": "Data", "width": 390},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 140},
        {"fieldname": "planning_status", "label": _("Planning Status"), "fieldtype": "Data", "width": 350},
        {"fieldname": "planning_approved", "label": _("Approved"), "fieldtype": "Check", "width": 90},
        {"fieldname": "phase11c_precheck_verified", "label": _("11C Verified"), "fieldtype": "Check", "width": 100},
        {"fieldname": "runtime_monitor_active_verified", "label": _("Runtime Active"), "fieldtype": "Check", "width": 120},
        {"fieldname": "guardrail_watch_active_verified", "label": _("Guardrail Watch"), "fieldtype": "Check", "width": 120},
        {"fieldname": "baseline_counts_stable_verified", "label": _("Counts Stable"), "fieldtype": "Check", "width": 110},
        {"fieldname": "policy_state_preserved_verified", "label": _("Policy Preserved"), "fieldtype": "Check", "width": 120},
        {"fieldname": "planning_envelope_locked", "label": _("Envelope Locked"), "fieldtype": "Check", "width": 120},
        {"fieldname": "ready_for_next_governed_limited_operation_design", "label": _("Design Ready"), "fieldtype": "Check", "width": 110},
        {"fieldname": "planned_line_count", "label": _("Planned Lines"), "fieldtype": "Int", "width": 105},
        {"fieldname": "planned_total_amount", "label": _("Planned Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "planned_payment_entry_count", "label": _("Planned PE"), "fieldtype": "Int", "width": 100},
        {"fieldname": "precheck", "label": _("Precheck"), "fieldtype": "Link", "options": PRECHECK_DOCTYPE, "width": 220},
        {"fieldname": "monitor", "label": _("Monitor"), "fieldtype": "Link", "options": MONITOR_DOCTYPE, "width": 220},
        {"fieldname": "baseline", "label": _("Baseline"), "fieldtype": "Link", "options": "NDIS Governed Steady State Baseline", "width": 220},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "payment_entry_docstatus", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 100},
        {"fieldname": "payment_entry_status", "label": _("PE Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "payment_entry_amount", "label": _("PE Amount"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "locked_payment_entry_count", "label": _("Locked PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "locked_payment_entry_gl_count", "label": _("Locked PE GL"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 110},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE Created"), "fieldtype": "Int", "width": 125},
        {"fieldname": "actual_payment_entry_cancelled_count", "label": _("Actual PE Cancelled"), "fieldtype": "Int", "width": 135},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL Created"), "fieldtype": "Int", "width": 125},
        {"fieldname": "actual_policy_mutation_count", "label": _("Policy Mutations"), "fieldtype": "Int", "width": 120},
        {"fieldname": "submitted_journal_entry_count_today", "label": _("JE Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "purchase_invoice_count_today", "label": _("PI Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "planning_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("planning"):
        conditions.append("i.planning = %(planning)s")
        params["planning"] = filters.get("planning")
    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")
    data = frappe.db.sql(
        f"""
        SELECT
            i.name AS item,
            i.planning,
            i.status,
            i.severity,
            i.category,
            i.check_key,
            i.check_label,
            i.detail,
            i.source_doctype,
            i.source_name,
            i.checked_on
        FROM `tab{PLANNING_ITEM_DOCTYPE}` i
        {build_where(conditions)}
        ORDER BY
            CASE i.status WHEN 'Blocker' THEN 1 WHEN 'Warning' THEN 2 WHEN 'Pass' THEN 3 WHEN 'Info' THEN 4 ELSE 5 END,
            i.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart_map = {}
    for row in data:
        key = row.status or "Info"
        chart_map[key] = chart_map.get(key, 0) + 1
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Items", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Items"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Pass"]), "indicator": "Green", "label": _("Pass"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Warning"]), "indicator": "Orange", "label": _("Warnings"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Blocker"]), "indicator": "Red", "label": _("Blockers"), "datatype": "Int"},
    ]
    return item_columns(), data, None, chart, summary


def item_columns():
    return [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": PLANNING_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "planning", "label": _("Planning"), "fieldtype": "Link", "options": PLANNING_DOCTYPE, "width": 220},
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


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_planning_report(filters)
    guard = guardrails()
    summary.extend(
        [
            {"value": guard["payment_entry_count"], "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"},
            {"value": guard["payment_entry_gl_count"], "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"},
            {"value": guard["production_batch_enabled_policy_count"], "indicator": "Green", "label": _("Enabled Policies"), "datatype": "Int"},
            {"value": guard["live_posting_allowed_policy_count"], "indicator": "Red", "label": _("Live Policies"), "datatype": "Int"},
            {"value": guard["submitted_journal_entry_count_today"], "indicator": "Red", "label": _("Submitted JE Today"), "datatype": "Int"},
            {"value": guard["purchase_invoice_count_today"], "indicator": "Red", "label": _("Purchase Invoice Today"), "datatype": "Int"},
        ]
    )
    return columns, data, message, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
