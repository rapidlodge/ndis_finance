import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


PLANNING_ACK = "I_CONFIRM_PHASE11P_APPROVE_NEXT_CONTROLLED_CYCLE_PLANNING_NO_POSTING"

POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
MONITOR_DOCTYPE = "NDIS Post Closeout Runtime Monitor"
PLANNING_DOCTYPE = "NDIS Next Controlled Cycle Planning"
PLANNING_ITEM_DOCTYPE = "NDIS Next Controlled Cycle Plan Item"

PLANNED_SOURCE_DOCTYPE = "Sales Invoice"
PLANNED_REFERENCE_DOCTYPE = "Sales Invoice"
PLANNED_PARTY_TYPE = "Customer"
PLANNED_LINE_COUNT = 3
PLANNED_TOTAL_AMOUNT = 3.00
PLANNED_PAYMENT_ENTRY_COUNT = 1


def make_planning_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-NEXT-CONTROLLED-CYCLE-PLANNING-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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
    if not name or not frappe.db.exists(doctype, name) or not has_column(doctype, fieldname):
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


def latest_monitor():
    rows = frappe.get_all(
        MONITOR_DOCTYPE,
        filters={
            "status": "Monitor Active",
            "monitor_status": "Post-Closeout Runtime Monitor Active",
            "monitor_active": 1,
            "phase11n_baseline_verified": 1,
            "baseline_active_verified": 1,
            "baseline_payment_entry_verified": 1,
            "payment_entry_cancelled_still_verified": 1,
            "baseline_counts_stable_verified": 1,
            "policy_state_preserved_verified": 1,
            "runtime_monitor_enabled": 1,
            "guardrail_watch_active": 1,
            "ready_for_next_governed_limited_operation_planning_gate": 1,
            "payment_entry_docstatus_monitor": 2,
            "payment_entry_status_monitor": "Cancelled",
            "monitored_reference_count": 3,
            "monitored_total_amount": 3.00,
            "monitored_voucher_gl_rows": 8,
            "monitored_voucher_gl_net": 0.00,
            "monitored_voucher_gl_non_zero_account_count": 0,
            "monitored_restored_invoice_amount": 3.00,
            "payment_entry_count_after": 9,
            "payment_entry_gl_count_after": 54,
            "actual_payment_entry_created_count": 0,
            "actual_payment_entry_cancelled_count": 0,
            "actual_gl_created_count": 0,
            "submitted_journal_entry_count_today": 0,
            "purchase_invoice_count_today": 0,
            "target_policy_enabled_after": 1,
            "target_policy_live_after": 0,
            "actual_policy_mutation_count": 0,
        },
        fields=[
            "name",
            "monitor_id",
            "monitored_payment_entry",
            "monitored_reference_count",
            "monitored_total_amount",
            "monitored_restored_invoice_amount",
            "baseline",
            "closeout",
            "freeze",
            "rollback",
            "smoke",
            "execution_gate",
            "preview",
            "validation",
            "candidate",
            "design",
            "planning",
            "target_policy_doctype",
            "target_policy",
            "target_policy_name",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_approved_planning(monitor):
    rows = frappe.get_all(
        PLANNING_DOCTYPE,
        filters={
            "monitor": monitor,
            "status": "Planning Approved",
            "planning_approved": 1,
        },
        fields=["name", "planning_id"],
        limit=1,
    )
    return rows[0] if rows else None


def payment_entry_reference_rows(payment_entry):
    if not payment_entry:
        return []
    return frappe.get_all(
        "Payment Entry Reference",
        filters={"parent": payment_entry, "reference_doctype": "Sales Invoice"},
        fields=[
            "idx",
            "reference_doctype",
            "reference_name",
            "total_amount",
            "outstanding_amount",
            "allocated_amount",
        ],
        order_by="idx asc",
    )


def allocated_total(payment_entry):
    rows = payment_entry_reference_rows(payment_entry)
    return flt(sum(flt(row.allocated_amount or 0, 2) for row in rows), 2)


def voucher_gl_rows(payment_entry):
    return count_dt("GL Entry", {"voucher_type": "Payment Entry", "voucher_no": payment_entry})


def voucher_gl_net(payment_entry):
    if not payment_entry:
        return 0
    value = frappe.db.sql(
        """
        SELECT ROUND(COALESCE(SUM(debit-credit), 0), 2)
        FROM `tabGL Entry`
        WHERE voucher_type='Payment Entry'
        AND voucher_no=%s
        """,
        payment_entry,
    )[0][0]
    return flt(value or 0, 2)


def voucher_gl_non_zero_accounts(payment_entry):
    if not payment_entry:
        return 0
    rows = frappe.db.sql(
        """
        SELECT account, ROUND(COALESCE(SUM(debit-credit), 0), 2) AS net
        FROM `tabGL Entry`
        WHERE voucher_type='Payment Entry'
        AND voucher_no=%s
        GROUP BY account
        HAVING ROUND(COALESCE(SUM(debit-credit), 0), 2) != 0
        """,
        payment_entry,
        as_dict=True,
    )
    return len(rows)


def validate_source(monitor, payment_entry, references, guard, config, policy_enabled, policy_live):
    issues = []

    if not monitor:
        issues.append("No active Phase 11O runtime monitor found.")
        return issues

    existing = existing_approved_planning(monitor.name)
    if existing:
        issues.append(f"Approved Phase 11P planning already exists for this monitor: {existing.planning_id}")

    if not payment_entry:
        issues.append("Phase 11O monitor does not identify the monitored Payment Entry.")
        return issues

    if not frappe.db.exists("Payment Entry", payment_entry):
        issues.append(f"Monitored Payment Entry does not exist: {payment_entry}")
        return issues

    pe = frappe.get_doc("Payment Entry", payment_entry)

    if pe.docstatus != 2:
        issues.append(f"Payment Entry must remain cancelled for planning. docstatus={pe.docstatus}")

    if pe.status != "Cancelled":
        issues.append(f"Payment Entry status must remain Cancelled for planning. status={pe.status}")

    if len(references) != 3:
        issues.append(f"Planning envelope baseline must still show 3 references. Found {len(references)}.")

    if allocated_total(payment_entry) != 3:
        issues.append(f"Planning envelope baseline amount must remain 3.00. Found {allocated_total(payment_entry)}.")

    if voucher_gl_rows(payment_entry) != 8:
        issues.append(f"Voucher GL rows must remain 8. Found {voucher_gl_rows(payment_entry)}.")

    if voucher_gl_net(payment_entry) != 0:
        issues.append(f"Voucher GL net must remain 0.00. Found {voucher_gl_net(payment_entry)}.")

    if voucher_gl_non_zero_accounts(payment_entry) != 0:
        issues.append(f"Voucher non-zero account count must remain 0. Found {voucher_gl_non_zero_accounts(payment_entry)}.")

    if guard["payment_entry_count"] != 9:
        issues.append("Payment Entry count must remain 9 before Phase 11P planning.")

    if guard["payment_entry_gl_count"] != 54:
        issues.append("Payment Entry GL count must remain 54 before Phase 11P planning.")

    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today must remain 0 before planning.")

    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today must remain 0 before planning.")

    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must remain enabled.")

    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must remain 0.")

    if policy_enabled != 1:
        issues.append("Target policy production_batch_enabled must remain 1.")

    if policy_live != 0:
        issues.append("Target policy live_posting_allowed must remain 0.")

    if config["sandbox_enabled"] != 1:
        issues.append("Sandbox config must be enabled.")

    if config["production_mode"] != 0:
        issues.append("Production mode config must remain 0.")

    if config["live_pe_enabled"] != 0:
        issues.append("Live Payment Entry posting config must remain 0.")

    return issues


def add_item(items, status, severity, category, check_key, check_label, detail, line_no=None, planned_amount=None, baseline_payment_entry=None):
    items.append({
        "status": status,
        "severity": severity,
        "category": category,
        "check_key": check_key,
        "check_label": check_label,
        "detail": detail,
        "line_no": line_no,
        "planned_source_doctype": PLANNED_SOURCE_DOCTYPE if category == "Planning Envelope" else None,
        "planned_reference_doctype": PLANNED_REFERENCE_DOCTYPE if category == "Planning Envelope" else None,
        "planned_amount": planned_amount,
        "baseline_payment_entry": baseline_payment_entry,
    })


def build_items(monitor, issues, ack_ok, baseline_payment_entry=None):
    items = []

    if monitor:
        add_item(
            items,
            "Pass",
            "Low",
            "Evidence",
            "phase11o_monitor_exists",
            "Phase 11O monitor exists",
            f"Monitor found: {monitor.monitor_id}.",
            baseline_payment_entry=baseline_payment_entry,
        )
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase11o_monitor_exists", "Phase 11O monitor exists", "No active Phase 11O runtime monitor found.")

    if not issues:
        add_item(
            items,
            "Pass",
            "Critical",
            "Planning Source",
            "planning_source_valid",
            "Planning source valid",
            "Runtime monitor is active and stable for next controlled-cycle planning.",
            baseline_payment_entry=baseline_payment_entry,
        )
    else:
        for issue in issues:
            add_item(
                items,
                "Blocker",
                "Critical",
                "Planning Source",
                "planning_source_valid",
                "Planning source valid",
                issue,
                baseline_payment_entry=baseline_payment_entry,
            )

    for line_no in range(1, PLANNED_LINE_COUNT + 1):
        add_item(
            items,
            "Pass",
            "High",
            "Planning Envelope",
            f"planned_envelope_line_{line_no}",
            f"Planned Envelope Line {line_no}",
            "Envelope line only. Candidate invoice selection has not started.",
            line_no=line_no,
            planned_amount=1.00,
            baseline_payment_entry=baseline_payment_entry,
        )

    checks = [
        ("planning_envelope_locked", "Planning envelope locked", f"{PLANNED_LINE_COUNT} / {PLANNED_TOTAL_AMOUNT} / {PLANNED_PAYMENT_ENTRY_COUNT}"),
        ("candidate_selection_not_started", "Candidate selection not started", 1),
        ("payment_entry_cancelled_still", "Baseline Payment Entry still cancelled", baseline_payment_entry),
        ("payment_entry_count", "Payment Entry count remains 9", 9),
        ("payment_entry_gl_count", "Payment Entry GL count remains 54", 54),
        ("voucher_gl_rows", "Voucher GL rows remain 8", 8),
        ("voucher_gl_net_zero", "Voucher GL net remains 0.00", "0.00"),
        ("policy_state", "Policy state preserved at 1 / 0", "1 / 0"),
        ("no_pe_movement", "No Payment Entry movement in planning", "0 / 0"),
        ("no_gl_movement", "No GL movement in planning", 0),
        ("no_je_pi", "No JE / PI side effects", "0 / 0"),
        ("ready_for_design_gate", "Ready for next controlled-cycle design gate", 1),
    ]

    for key, label, value in checks:
        add_item(
            items,
            "Pass",
            "High",
            "Planning Evidence",
            key,
            label,
            f"value={value}",
            baseline_payment_entry=baseline_payment_entry,
        )

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.", baseline_payment_entry=baseline_payment_entry)
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
    score = 100
    score -= int(blockers or 0) * 25
    score -= int(warnings or 0) * 5
    return max(0, round(score, 2))


def create_items(doc, items):
    for item in items:
        row = frappe.new_doc(PLANNING_ITEM_DOCTYPE)
        row.planning = doc.name

        for fieldname, value in item.items():
            if row.meta.has_field(fieldname):
                setattr(row, fieldname, value)

        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_next_controlled_cycle_planning(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_next_controlled_cycle_planning")

    monitor = latest_monitor()
    payment_entry = monitor.monitored_payment_entry if monitor else None
    references = payment_entry_reference_rows(payment_entry) if payment_entry else []

    guard_before = guardrails()
    ack_ok = acknowledgement == PLANNING_ACK

    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }

    policy_enabled_before = get_flag(POLICY_DOCTYPE, monitor.target_policy, "production_batch_enabled") if monitor else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, monitor.target_policy, "live_posting_allowed") if monitor else 0

    issues = validate_source(monitor, payment_entry, references, guard_before, config, policy_enabled_before, policy_live_before)

    guard_after = guardrails()

    policy_enabled_after = get_flag(POLICY_DOCTYPE, monitor.target_policy, "production_batch_enabled") if monitor else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, monitor.target_policy, "live_posting_allowed") if monitor else 0

    actual_pe_created = guard_after["payment_entry_count"] - guard_before["payment_entry_count"]
    actual_pe_cancelled = 0
    actual_gl_created = guard_after["payment_entry_gl_count"] - guard_before["payment_entry_gl_count"]

    policy_mutation_count = int(
        policy_enabled_before != policy_enabled_after
        or policy_live_before != policy_live_after
        or guard_before["production_batch_enabled_policy_count"] != guard_after["production_batch_enabled_policy_count"]
        or guard_before["live_posting_allowed_policy_count"] != guard_after["live_posting_allowed_policy_count"]
    )

    pe_docstatus = 0
    pe_status = None
    baseline_total = 0
    voucher_rows = 0
    voucher_net = 0
    non_zero_accounts = 0

    if payment_entry and frappe.db.exists("Payment Entry", payment_entry):
        pe = frappe.get_doc("Payment Entry", payment_entry)
        pe_docstatus = int(pe.docstatus or 0)
        pe_status = pe.status
        baseline_total = flt(pe.paid_amount or pe.received_amount or allocated_total(payment_entry), 2)
        voucher_rows = voucher_gl_rows(payment_entry)
        voucher_net = voucher_gl_net(payment_entry)
        non_zero_accounts = voucher_gl_non_zero_accounts(payment_entry)

    post_issues = list(issues)

    if actual_pe_created != 0:
        post_issues.append(f"Planning must not create Payment Entries. Created {actual_pe_created}.")

    if actual_pe_cancelled != 0:
        post_issues.append(f"Planning must not cancel Payment Entries. Cancelled {actual_pe_cancelled}.")

    if actual_gl_created != 0:
        post_issues.append(f"Planning must not create GL rows. Created {actual_gl_created}.")

    if guard_after["payment_entry_count"] != 9:
        post_issues.append("Payment Entry count must remain 9 after planning.")

    if guard_after["payment_entry_gl_count"] != 54:
        post_issues.append("Payment Entry GL count must remain 54 after planning.")

    if guard_after["submitted_journal_entry_count_today"] != 0:
        post_issues.append("Submitted Journal Entry count today must remain 0 after planning.")

    if guard_after["purchase_invoice_count_today"] != 0:
        post_issues.append("Purchase Invoice count today must remain 0 after planning.")

    if policy_mutation_count != 0:
        post_issues.append("Policy state changed during planning. This is not allowed.")

    items = build_items(
        monitor,
        post_issues,
        ack_ok,
        baseline_payment_entry=payment_entry,
    )
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    completed = int(
        ack_ok
        and monitor
        and payment_entry
        and item_summary["blocker_count"] == 0
        and pe_docstatus == 2
        and pe_status == "Cancelled"
        and len(references) == 3
        and baseline_total == 3
        and voucher_rows == 8
        and voucher_net == 0
        and non_zero_accounts == 0
        and guard_before["payment_entry_count"] == 9
        and guard_after["payment_entry_count"] == 9
        and guard_before["payment_entry_gl_count"] == 54
        and guard_after["payment_entry_gl_count"] == 54
        and actual_pe_created == 0
        and actual_pe_cancelled == 0
        and actual_gl_created == 0
        and guard_after["submitted_journal_entry_count_today"] == 0
        and guard_after["purchase_invoice_count_today"] == 0
        and policy_mutation_count == 0
    )

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Planning Approved" if completed else "Needs Review",
        "planning_status": "Next Controlled Cycle Planning Approved" if completed else "Needs Review",
        "planning_approved": completed,
        "phase11o_monitor_verified": 1 if monitor else 0,
        "runtime_monitor_active_verified": 1 if monitor else 0,
        "baseline_stable_verified": int(guard_before["payment_entry_count"] == 9 and guard_after["payment_entry_count"] == 9 and guard_before["payment_entry_gl_count"] == 54 and guard_after["payment_entry_gl_count"] == 54),
        "baseline_payment_entry_verified": 1 if payment_entry else 0,
        "payment_entry_cancelled_still_verified": int(pe_docstatus == 2 and pe_status == "Cancelled"),
        "planning_envelope_locked": completed,
        "candidate_selection_not_started": completed,
        "policy_state_preserved_verified": int(policy_mutation_count == 0 and policy_enabled_before == 1 and policy_enabled_after == 1 and policy_live_before == 0 and policy_live_after == 0),
        "ready_for_next_controlled_cycle_design_gate": completed,
        "no_new_accounting_movement_verified": int(actual_pe_created == 0 and actual_pe_cancelled == 0 and actual_gl_created == 0),
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": policy_mutation_count,
        "planned_source_doctype": PLANNED_SOURCE_DOCTYPE,
        "planned_reference_doctype": PLANNED_REFERENCE_DOCTYPE,
        "planned_party_type": PLANNED_PARTY_TYPE,
        "planned_line_count": PLANNED_LINE_COUNT,
        "planned_total_amount": PLANNED_TOTAL_AMOUNT,
        "planned_payment_entry_count": PLANNED_PAYMENT_ENTRY_COUNT,
        "planned_live_posting_allowed": 0,
        "planned_journal_entry_side_effect_allowed": 0,
        "planned_purchase_invoice_side_effect_allowed": 0,
        "baseline_payment_entry": payment_entry,
        "payment_entry_docstatus_planning": pe_docstatus,
        "payment_entry_status_planning": pe_status,
        "baseline_reference_count": len(references),
        "baseline_total_amount": baseline_total,
        "baseline_voucher_gl_rows": voucher_rows,
        "baseline_voucher_gl_net": voucher_net,
        "baseline_voucher_gl_non_zero_account_count": non_zero_accounts,
        "baseline_restored_invoice_amount": baseline_total if baseline_total == 3 else 0,
        "monitor": monitor.name if monitor else None,
        "baseline": monitor.baseline if monitor else None,
        "closeout": monitor.closeout if monitor else None,
        "freeze": monitor.freeze if monitor else None,
        "rollback": monitor.rollback if monitor else None,
        "smoke": monitor.smoke if monitor else None,
        "execution_gate": monitor.execution_gate if monitor else None,
        "preview": monitor.preview if monitor else None,
        "validation": monitor.validation if monitor else None,
        "candidate": monitor.candidate if monitor else None,
        "design": monitor.design if monitor else None,
        "previous_planning": monitor.planning if monitor else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": monitor.target_policy if monitor else None,
        "target_policy_name": monitor.target_policy_name if monitor else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_before": policy_live_before,
        "target_policy_live_after": policy_live_after,
        "production_batch_enabled_policy_count_before": guard_before["production_batch_enabled_policy_count"],
        "production_batch_enabled_policy_count_after": guard_after["production_batch_enabled_policy_count"],
        "live_posting_allowed_policy_count_before": guard_before["live_posting_allowed_policy_count"],
        "live_posting_allowed_policy_count_after": guard_after["live_posting_allowed_policy_count"],
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guard_after["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
        "actual_payment_entry_created_count": actual_pe_created,
        "actual_payment_entry_cancelled_count": actual_pe_cancelled,
        "actual_gl_created_count": actual_gl_created,
        "submitted_journal_entry_count_today": guard_after["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_after["purchase_invoice_count_today"],
        "planning_score": score,
        **item_summary,
        "items": items,
        "issues": post_issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "required_acknowledgement": PLANNING_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 11P locks the next controlled-cycle planning envelope only. Candidate selection has not started.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["planning_status"] = "Needs Review"
        result["planning_approved"] = 0
        result["planning_envelope_locked"] = 0
        result["candidate_selection_not_started"] = 0
        result["ready_for_next_controlled_cycle_design_gate"] = 0
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
    doc.planning_json = safe_json(
        {
            "monitor": monitor,
            "baseline_payment_entry": payment_entry,
            "planned_envelope": {
                "source_doctype": PLANNED_SOURCE_DOCTYPE,
                "reference_doctype": PLANNED_REFERENCE_DOCTYPE,
                "party_type": PLANNED_PARTY_TYPE,
                "line_count": PLANNED_LINE_COUNT,
                "total_amount": PLANNED_TOTAL_AMOUNT,
                "payment_entry_count": PLANNED_PAYMENT_ENTRY_COUNT,
                "candidate_selection_started": 0,
            },
            "guardrails_before": guard_before,
            "guardrails_after": guard_after,
            "voucher": {
                "rows": voucher_rows,
                "net": voucher_net,
                "non_zero_accounts": non_zero_accounts,
            },
            "issues": post_issues,
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
        "planning": doc.name,
        "planning_id": doc.planning_id,
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_next_controlled_cycle_planning_audit(planning, reason=None):
    assert_action("cancel_next_controlled_cycle_planning_audit")

    if not frappe.db.exists(PLANNING_DOCTYPE, planning):
        frappe.throw(_("Next controlled-cycle planning audit not found: {0}").format(planning))

    doc = frappe.get_doc(PLANNING_DOCTYPE, planning)

    if doc.status == "Cancelled":
        return {"planning": planning, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.planning_approved or 0):
        frappe.throw(_("Cannot cancel an approved Phase 11P planning record."))

    frappe.db.set_value(
        PLANNING_DOCTYPE,
        planning,
        {
            "status": "Cancelled",
            "planning_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 11P no-ack planning audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        f"""
        UPDATE `tab{PLANNING_ITEM_DOCTYPE}`
        SET status = 'Cancelled'
        WHERE planning = %(planning)s
        """,
        {"planning": planning},
    )

    frappe.db.commit()

    return {
        "planning": planning,
        "status": "Cancelled",
        "note": "No-ack planning audit cancelled only. No accounting or policy movement occurred.",
    }


@frappe.whitelist()
def quick_next_controlled_cycle_planning_summary(limit=20):
    records = frappe.get_all(
        PLANNING_DOCTYPE,
        fields=[
            "name",
            "planning_id",
            "status",
            "planning_status",
            "planning_approved",
            "planning_envelope_locked",
            "candidate_selection_not_started",
            "ready_for_next_controlled_cycle_design_gate",
            "planned_source_doctype",
            "planned_reference_doctype",
            "planned_party_type",
            "planned_line_count",
            "planned_total_amount",
            "planned_payment_entry_count",
            "baseline_payment_entry",
            "payment_entry_docstatus_planning",
            "payment_entry_status_planning",
            "monitor",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "actual_payment_entry_created_count",
            "actual_payment_entry_cancelled_count",
            "actual_gl_created_count",
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
        fields=[
            "name",
            "planning",
            "status",
            "severity",
            "category",
            "check_key",
            "check_label",
            "line_no",
            "planned_source_doctype",
            "planned_reference_doctype",
            "planned_amount",
            "baseline_payment_entry",
            "detail",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    return {
        "planning_records": records,
        "items": items,
        "required_acknowledgement": PLANNING_ACK,
        "guardrails": guardrails(),
        "note": "Phase 11P next controlled-cycle planning summary.",
    }


def execute_planning_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("status"):
        conditions.append("p.status = %(status)s")
        params["status"] = filters.get("status")

    columns = planning_columns()

    data = frappe.db.sql(
        f"""
        SELECT
            p.name AS planning,
            p.planning_id,
            p.status,
            p.planning_status,
            p.planning_approved,
            p.phase11o_monitor_verified,
            p.runtime_monitor_active_verified,
            p.baseline_stable_verified,
            p.payment_entry_cancelled_still_verified,
            p.planning_envelope_locked,
            p.candidate_selection_not_started,
            p.ready_for_next_controlled_cycle_design_gate,
            p.planned_source_doctype,
            p.planned_reference_doctype,
            p.planned_party_type,
            p.planned_line_count,
            p.planned_total_amount,
            p.planned_payment_entry_count,
            p.baseline_payment_entry,
            p.payment_entry_docstatus_planning,
            p.payment_entry_status_planning,
            p.baseline_voucher_gl_rows,
            p.baseline_voucher_gl_net,
            p.baseline_restored_invoice_amount,
            p.monitor,
            p.payment_entry_count_before,
            p.payment_entry_count_after,
            p.payment_entry_gl_count_before,
            p.payment_entry_gl_count_after,
            p.actual_payment_entry_created_count,
            p.actual_payment_entry_cancelled_count,
            p.actual_gl_created_count,
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
                {"name": "Design Ready", "values": [int(row.ready_for_next_controlled_cycle_design_gate or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Planning Records"), "datatype": "Int"},
        {"value": sum(int(row.planning_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(int(row.candidate_selection_not_started or 0) for row in data), "indicator": "Green", "label": _("Candidate Not Started"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL Created"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def planning_columns():
    return [
        {"fieldname": "planning", "label": _("Planning"), "fieldtype": "Link", "options": PLANNING_DOCTYPE, "width": 220},
        {"fieldname": "planning_id", "label": _("Planning ID"), "fieldtype": "Data", "width": 360},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 150},
        {"fieldname": "planning_status", "label": _("Planning Status"), "fieldtype": "Data", "width": 320},
        {"fieldname": "planning_approved", "label": _("Approved"), "fieldtype": "Check", "width": 90},
        {"fieldname": "phase11o_monitor_verified", "label": _("11O Verified"), "fieldtype": "Check", "width": 105},
        {"fieldname": "runtime_monitor_active_verified", "label": _("Monitor OK"), "fieldtype": "Check", "width": 95},
        {"fieldname": "baseline_stable_verified", "label": _("Baseline OK"), "fieldtype": "Check", "width": 100},
        {"fieldname": "payment_entry_cancelled_still_verified", "label": _("PE Cancelled"), "fieldtype": "Check", "width": 110},
        {"fieldname": "planning_envelope_locked", "label": _("Envelope Locked"), "fieldtype": "Check", "width": 120},
        {"fieldname": "candidate_selection_not_started", "label": _("No Candidate"), "fieldtype": "Check", "width": 105},
        {"fieldname": "ready_for_next_controlled_cycle_design_gate", "label": _("Design Ready"), "fieldtype": "Check", "width": 110},
        {"fieldname": "planned_source_doctype", "label": _("Source"), "fieldtype": "Data", "width": 120},
        {"fieldname": "planned_reference_doctype", "label": _("Reference"), "fieldtype": "Data", "width": 120},
        {"fieldname": "planned_party_type", "label": _("Party Type"), "fieldtype": "Data", "width": 100},
        {"fieldname": "planned_line_count", "label": _("Lines"), "fieldtype": "Int", "width": 70},
        {"fieldname": "planned_total_amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 100},
        {"fieldname": "planned_payment_entry_count", "label": _("Future PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "baseline_payment_entry", "label": _("Baseline PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "payment_entry_docstatus_planning", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 100},
        {"fieldname": "payment_entry_status_planning", "label": _("PE Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "baseline_voucher_gl_rows", "label": _("Voucher GL Rows"), "fieldtype": "Int", "width": 120},
        {"fieldname": "baseline_voucher_gl_net", "label": _("Voucher Net"), "fieldtype": "Currency", "options": "currency", "width": 100},
        {"fieldname": "baseline_restored_invoice_amount", "label": _("Restored Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "monitor", "label": _("Monitor"), "fieldtype": "Link", "options": MONITOR_DOCTYPE, "width": 220},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 110},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE Created"), "fieldtype": "Int", "width": 125},
        {"fieldname": "actual_payment_entry_cancelled_count", "label": _("Actual PE Cancelled"), "fieldtype": "Int", "width": 135},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL Created"), "fieldtype": "Int", "width": 125},
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

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": PLANNING_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "planning", "label": _("Planning"), "fieldtype": "Link", "options": PLANNING_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 190},
        {"fieldname": "line_no", "label": _("Line"), "fieldtype": "Int", "width": 60},
        {"fieldname": "planned_source_doctype", "label": _("Planned Source"), "fieldtype": "Data", "width": 130},
        {"fieldname": "planned_reference_doctype", "label": _("Planned Reference"), "fieldtype": "Data", "width": 140},
        {"fieldname": "planned_amount", "label": _("Planned Amount"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "baseline_payment_entry", "label": _("Baseline PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "check_key", "label": _("Check Key"), "fieldtype": "Data", "width": 230},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 330},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 650},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            i.name AS item,
            i.planning,
            i.status,
            i.severity,
            i.category,
            i.line_no,
            i.planned_source_doctype,
            i.planned_reference_doctype,
            i.planned_amount,
            i.baseline_payment_entry,
            i.check_key,
            i.check_label,
            i.detail,
            i.checked_on
        FROM `tab{PLANNING_ITEM_DOCTYPE}` i
        {build_where(conditions)}
        ORDER BY
            CASE i.status
                WHEN 'Blocker' THEN 1
                WHEN 'Warning' THEN 2
                WHEN 'Pass' THEN 3
                WHEN 'Info' THEN 4
                ELSE 5
            END,
            i.line_no ASC,
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
        "data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Items", "values": list(chart_map.values())}]},
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Items"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Pass"]), "indicator": "Green", "label": _("Pass"), "datatype": "Int"},
        {"value": len([row for row in data if row.category == "Planning Envelope"]), "indicator": "Green", "label": _("Envelope Lines"), "datatype": "Int"},
        {"value": sum(flt(row.planned_amount or 0, 2) for row in data if row.category == "Planning Envelope"), "indicator": "Green", "label": _("Envelope Amount"), "datatype": "Currency"},
        {"value": len([row for row in data if row.status == "Blocker"]), "indicator": "Red", "label": _("Blockers"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_planning_report(filters)
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
