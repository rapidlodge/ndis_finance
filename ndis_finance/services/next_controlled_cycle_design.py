import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, today

from ndis_finance.services.permissions import assert_action


DESIGN_ACK = "I_CONFIRM_PHASE11Q_APPROVE_NEXT_CONTROLLED_CYCLE_DESIGN_NO_POSTING"

POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
PLANNING_DOCTYPE = "NDIS Next Controlled Cycle Planning"
DESIGN_DOCTYPE = "NDIS Next Controlled Cycle Design"
DESIGN_ITEM_DOCTYPE = "NDIS Next Controlled Cycle Design Item"

DESIGN_SOURCE_DOCTYPE = "Sales Invoice"
DESIGN_REFERENCE_DOCTYPE = "Sales Invoice"
DESIGN_PARTY_TYPE = "Customer"
DESIGN_LINE_COUNT = 3
DESIGN_TOTAL_AMOUNT = 3.00
DESIGN_PAYMENT_ENTRY_COUNT = 1


def make_design_id():
    timestamp = now_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-NEXT-CONTROLLED-CYCLE-DESIGN-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_planning():
    rows = frappe.get_all(
        PLANNING_DOCTYPE,
        filters={
            "status": "Planning Approved",
            "planning_status": "Next Controlled Cycle Planning Approved",
            "planning_approved": 1,
            "phase11o_monitor_verified": 1,
            "runtime_monitor_active_verified": 1,
            "baseline_stable_verified": 1,
            "baseline_payment_entry_verified": 1,
            "payment_entry_cancelled_still_verified": 1,
            "planning_envelope_locked": 1,
            "candidate_selection_not_started": 1,
            "policy_state_preserved_verified": 1,
            "ready_for_next_controlled_cycle_design_gate": 1,
            "planned_source_doctype": DESIGN_SOURCE_DOCTYPE,
            "planned_reference_doctype": DESIGN_REFERENCE_DOCTYPE,
            "planned_party_type": DESIGN_PARTY_TYPE,
            "planned_line_count": DESIGN_LINE_COUNT,
            "planned_total_amount": DESIGN_TOTAL_AMOUNT,
            "planned_payment_entry_count": DESIGN_PAYMENT_ENTRY_COUNT,
            "planned_live_posting_allowed": 0,
            "planned_journal_entry_side_effect_allowed": 0,
            "planned_purchase_invoice_side_effect_allowed": 0,
            "payment_entry_docstatus_planning": 2,
            "payment_entry_status_planning": "Cancelled",
            "baseline_reference_count": 3,
            "baseline_total_amount": 3.00,
            "baseline_voucher_gl_rows": 8,
            "baseline_voucher_gl_net": 0.00,
            "baseline_voucher_gl_non_zero_account_count": 0,
            "baseline_restored_invoice_amount": 3.00,
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
            "planning_id",
            "baseline_payment_entry",
            "baseline_reference_count",
            "baseline_total_amount",
            "baseline_restored_invoice_amount",
            "monitor",
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
            "previous_planning",
            "target_policy_doctype",
            "target_policy",
            "target_policy_name",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_approved_design(planning):
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


def validate_source(planning, payment_entry, references, guard, config, policy_enabled, policy_live):
    issues = []

    if not planning:
        issues.append("No approved Phase 11P next controlled-cycle planning found.")
        return issues

    existing = existing_approved_design(planning.name)
    if existing:
        issues.append(f"Approved Phase 11Q design already exists for this planning: {existing.design_id}")

    if not payment_entry:
        issues.append("Phase 11P planning does not identify the baseline Payment Entry.")
        return issues

    if not frappe.db.exists("Payment Entry", payment_entry):
        issues.append(f"Baseline Payment Entry does not exist: {payment_entry}")
        return issues

    pe = frappe.get_doc("Payment Entry", payment_entry)

    if pe.docstatus != 2:
        issues.append(f"Payment Entry must remain cancelled for design. docstatus={pe.docstatus}")

    if pe.status != "Cancelled":
        issues.append(f"Payment Entry status must remain Cancelled for design. status={pe.status}")

    if len(references) != 3:
        issues.append(f"Design baseline must still show 3 references. Found {len(references)}.")

    if allocated_total(payment_entry) != 3:
        issues.append(f"Design baseline amount must remain 3.00. Found {allocated_total(payment_entry)}.")

    if voucher_gl_rows(payment_entry) != 8:
        issues.append(f"Voucher GL rows must remain 8. Found {voucher_gl_rows(payment_entry)}.")

    if voucher_gl_net(payment_entry) != 0:
        issues.append(f"Voucher GL net must remain 0.00. Found {voucher_gl_net(payment_entry)}.")

    if voucher_gl_non_zero_accounts(payment_entry) != 0:
        issues.append(f"Voucher non-zero account count must remain 0. Found {voucher_gl_non_zero_accounts(payment_entry)}.")

    if guard["payment_entry_count"] != 9:
        issues.append("Payment Entry count must remain 9 before Phase 11Q design.")

    if guard["payment_entry_gl_count"] != 54:
        issues.append("Payment Entry GL count must remain 54 before Phase 11Q design.")

    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today must remain 0 before design.")

    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today must remain 0 before design.")

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


def add_item(items, status, severity, category, check_key, check_label, detail, line_no=None, design_amount=None, baseline_payment_entry=None):
    items.append({
        "status": status,
        "severity": severity,
        "category": category,
        "check_key": check_key,
        "check_label": check_label,
        "detail": detail,
        "line_no": line_no,
        "design_source_doctype": DESIGN_SOURCE_DOCTYPE if category == "Design Shape" else None,
        "design_reference_doctype": DESIGN_REFERENCE_DOCTYPE if category == "Design Shape" else None,
        "design_amount": design_amount,
        "baseline_payment_entry": baseline_payment_entry,
    })


def build_items(planning, issues, ack_ok, baseline_payment_entry=None):
    items = []

    if planning:
        add_item(
            items,
            "Pass",
            "Low",
            "Evidence",
            "phase11p_planning_exists",
            "Phase 11P planning exists",
            f"Planning found: {planning.planning_id}.",
            baseline_payment_entry=baseline_payment_entry,
        )
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase11p_planning_exists", "Phase 11P planning exists", "No approved Phase 11P planning found.")

    if not issues:
        add_item(
            items,
            "Pass",
            "Critical",
            "Design Source",
            "design_source_valid",
            "Design source valid",
            "Planning envelope is stable and ready to become the next controlled-cycle design.",
            baseline_payment_entry=baseline_payment_entry,
        )
    else:
        for issue in issues:
            add_item(
                items,
                "Blocker",
                "Critical",
                "Design Source",
                "design_source_valid",
                "Design source valid",
                issue,
                baseline_payment_entry=baseline_payment_entry,
            )

    for line_no in range(1, DESIGN_LINE_COUNT + 1):
        add_item(
            items,
            "Pass",
            "High",
            "Design Shape",
            f"design_shape_line_{line_no}",
            f"Design Shape Line {line_no}",
            "Design shape only. Candidate invoice selection has not started.",
            line_no=line_no,
            design_amount=1.00,
            baseline_payment_entry=baseline_payment_entry,
        )

    checks = [
        ("planning_envelope_locked", "Planning envelope locked", 1),
        ("candidate_selection_not_started", "Candidate selection not started", 1),
        ("design_source_locked", "Design source locked", f"{DESIGN_SOURCE_DOCTYPE} / {DESIGN_REFERENCE_DOCTYPE} / {DESIGN_PARTY_TYPE}"),
        ("design_shape_locked", "Design shape locked", f"{DESIGN_LINE_COUNT} / {DESIGN_TOTAL_AMOUNT} / {DESIGN_PAYMENT_ENTRY_COUNT}"),
        ("payment_entry_cancelled_still", "Baseline Payment Entry still cancelled", baseline_payment_entry),
        ("payment_entry_count", "Payment Entry count remains 9", 9),
        ("payment_entry_gl_count", "Payment Entry GL count remains 54", 54),
        ("voucher_gl_rows", "Voucher GL rows remain 8", 8),
        ("voucher_gl_net_zero", "Voucher GL net remains 0.00", "0.00"),
        ("policy_state", "Policy state preserved at 1 / 0", "1 / 0"),
        ("no_pe_movement", "No Payment Entry movement in design", "0 / 0"),
        ("no_gl_movement", "No GL movement in design", 0),
        ("no_je_pi", "No JE / PI side effects", "0 / 0"),
        ("ready_for_candidate_selection", "Ready for next controlled-cycle candidate selection", 1),
    ]

    for key, label, value in checks:
        add_item(
            items,
            "Pass",
            "High",
            "Design Evidence",
            key,
            label,
            f"value={value}",
            baseline_payment_entry=baseline_payment_entry,
        )

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.", baseline_payment_entry=baseline_payment_entry)
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

        for fieldname, value in item.items():
            if row.meta.has_field(fieldname):
                setattr(row, fieldname, value)

        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_next_controlled_cycle_design(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_next_controlled_cycle_design")

    planning = latest_planning()
    payment_entry = planning.baseline_payment_entry if planning else None
    references = payment_entry_reference_rows(payment_entry) if payment_entry else []

    guard_before = guardrails()
    ack_ok = acknowledgement == DESIGN_ACK

    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }

    policy_enabled_before = get_flag(POLICY_DOCTYPE, planning.target_policy, "production_batch_enabled") if planning else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, planning.target_policy, "live_posting_allowed") if planning else 0

    issues = validate_source(planning, payment_entry, references, guard_before, config, policy_enabled_before, policy_live_before)

    guard_after = guardrails()

    policy_enabled_after = get_flag(POLICY_DOCTYPE, planning.target_policy, "production_batch_enabled") if planning else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, planning.target_policy, "live_posting_allowed") if planning else 0

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
        post_issues.append(f"Design must not create Payment Entries. Created {actual_pe_created}.")

    if actual_pe_cancelled != 0:
        post_issues.append(f"Design must not cancel Payment Entries. Cancelled {actual_pe_cancelled}.")

    if actual_gl_created != 0:
        post_issues.append(f"Design must not create GL rows. Created {actual_gl_created}.")

    if guard_after["payment_entry_count"] != 9:
        post_issues.append("Payment Entry count must remain 9 after design.")

    if guard_after["payment_entry_gl_count"] != 54:
        post_issues.append("Payment Entry GL count must remain 54 after design.")

    if guard_after["submitted_journal_entry_count_today"] != 0:
        post_issues.append("Submitted Journal Entry count today must remain 0 after design.")

    if guard_after["purchase_invoice_count_today"] != 0:
        post_issues.append("Purchase Invoice count today must remain 0 after design.")

    if policy_mutation_count != 0:
        post_issues.append("Policy state changed during design. This is not allowed.")

    items = build_items(
        planning,
        post_issues,
        ack_ok,
        baseline_payment_entry=payment_entry,
    )
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    completed = int(
        ack_ok
        and planning
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
        "status": "Design Approved" if completed else "Needs Review",
        "design_status": "Next Controlled Cycle Design Approved" if completed else "Needs Review",
        "design_approved": completed,
        "phase11p_planning_verified": 1 if planning else 0,
        "planning_approved_verified": 1 if planning else 0,
        "planning_envelope_locked_verified": 1 if planning else 0,
        "candidate_selection_not_started_verified": 1 if planning else 0,
        "design_source_locked": completed,
        "design_shape_locked": completed,
        "baseline_payment_entry_verified": 1 if payment_entry else 0,
        "payment_entry_cancelled_still_verified": int(pe_docstatus == 2 and pe_status == "Cancelled"),
        "policy_state_preserved_verified": int(policy_mutation_count == 0 and policy_enabled_before == 1 and policy_enabled_after == 1 and policy_live_before == 0 and policy_live_after == 0),
        "ready_for_next_controlled_cycle_candidate_selection": completed,
        "no_new_accounting_movement_verified": int(actual_pe_created == 0 and actual_pe_cancelled == 0 and actual_gl_created == 0),
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": policy_mutation_count,
        "design_source_doctype": DESIGN_SOURCE_DOCTYPE,
        "design_reference_doctype": DESIGN_REFERENCE_DOCTYPE,
        "design_party_type": DESIGN_PARTY_TYPE,
        "design_line_count": DESIGN_LINE_COUNT,
        "design_total_amount": DESIGN_TOTAL_AMOUNT,
        "design_payment_entry_count": DESIGN_PAYMENT_ENTRY_COUNT,
        "design_live_posting_allowed": 0,
        "design_journal_entry_side_effect_allowed": 0,
        "design_purchase_invoice_side_effect_allowed": 0,
        "baseline_payment_entry": payment_entry,
        "payment_entry_docstatus_design": pe_docstatus,
        "payment_entry_status_design": pe_status,
        "baseline_reference_count": len(references),
        "baseline_total_amount": baseline_total,
        "baseline_voucher_gl_rows": voucher_rows,
        "baseline_voucher_gl_net": voucher_net,
        "baseline_voucher_gl_non_zero_account_count": non_zero_accounts,
        "baseline_restored_invoice_amount": baseline_total if baseline_total == 3 else 0,
        "planning": planning.name if planning else None,
        "monitor": planning.monitor if planning else None,
        "baseline": planning.baseline if planning else None,
        "closeout": planning.closeout if planning else None,
        "freeze": planning.freeze if planning else None,
        "rollback": planning.rollback if planning else None,
        "smoke": planning.smoke if planning else None,
        "execution_gate": planning.execution_gate if planning else None,
        "preview": planning.preview if planning else None,
        "validation": planning.validation if planning else None,
        "previous_candidate": planning.candidate if planning else None,
        "previous_design": planning.design if planning else None,
        "previous_planning": planning.previous_planning if planning else None,
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
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guard_after["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
        "actual_payment_entry_created_count": actual_pe_created,
        "actual_payment_entry_cancelled_count": actual_pe_cancelled,
        "actual_gl_created_count": actual_gl_created,
        "submitted_journal_entry_count_today": guard_after["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_after["purchase_invoice_count_today"],
        "design_score": score,
        **item_summary,
        "items": items,
        "issues": post_issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "required_acknowledgement": DESIGN_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 11Q locks the next controlled-cycle design only. Candidate selection has not started.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["design_status"] = "Needs Review"
        result["design_approved"] = 0
        result["design_source_locked"] = 0
        result["design_shape_locked"] = 0
        result["ready_for_next_controlled_cycle_candidate_selection"] = 0
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
            "baseline_payment_entry": payment_entry,
            "design": {
                "source_doctype": DESIGN_SOURCE_DOCTYPE,
                "reference_doctype": DESIGN_REFERENCE_DOCTYPE,
                "party_type": DESIGN_PARTY_TYPE,
                "line_count": DESIGN_LINE_COUNT,
                "total_amount": DESIGN_TOTAL_AMOUNT,
                "payment_entry_count": DESIGN_PAYMENT_ENTRY_COUNT,
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
        "design": doc.name,
        "design_id": doc.design_id,
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_next_controlled_cycle_design_audit(design, reason=None):
    assert_action("cancel_next_controlled_cycle_design_audit")

    if not frappe.db.exists(DESIGN_DOCTYPE, design):
        frappe.throw(_("Next controlled-cycle design audit not found: {0}").format(design))

    doc = frappe.get_doc(DESIGN_DOCTYPE, design)

    if doc.status == "Cancelled":
        return {"design": design, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.design_approved or 0):
        frappe.throw(_("Cannot cancel an approved Phase 11Q design record."))

    frappe.db.set_value(
        DESIGN_DOCTYPE,
        design,
        {
            "status": "Cancelled",
            "design_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 11Q no-ack design audit cancelled.",
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
def quick_next_controlled_cycle_design_summary(limit=20):
    records = frappe.get_all(
        DESIGN_DOCTYPE,
        fields=[
            "name",
            "design_id",
            "status",
            "design_status",
            "design_approved",
            "design_source_locked",
            "design_shape_locked",
            "ready_for_next_controlled_cycle_candidate_selection",
            "design_source_doctype",
            "design_reference_doctype",
            "design_party_type",
            "design_line_count",
            "design_total_amount",
            "design_payment_entry_count",
            "baseline_payment_entry",
            "payment_entry_docstatus_design",
            "payment_entry_status_design",
            "planning",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "actual_payment_entry_created_count",
            "actual_payment_entry_cancelled_count",
            "actual_gl_created_count",
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
        fields=[
            "name",
            "design",
            "status",
            "severity",
            "category",
            "check_key",
            "check_label",
            "line_no",
            "design_source_doctype",
            "design_reference_doctype",
            "design_amount",
            "baseline_payment_entry",
            "detail",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    return {
        "design_records": records,
        "items": items,
        "required_acknowledgement": DESIGN_ACK,
        "guardrails": guardrails(),
        "note": "Phase 11Q next controlled-cycle design summary.",
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
            d.phase11p_planning_verified,
            d.planning_approved_verified,
            d.planning_envelope_locked_verified,
            d.candidate_selection_not_started_verified,
            d.design_source_locked,
            d.design_shape_locked,
            d.ready_for_next_controlled_cycle_candidate_selection,
            d.design_source_doctype,
            d.design_reference_doctype,
            d.design_party_type,
            d.design_line_count,
            d.design_total_amount,
            d.design_payment_entry_count,
            d.baseline_payment_entry,
            d.payment_entry_docstatus_design,
            d.payment_entry_status_design,
            d.baseline_voucher_gl_rows,
            d.baseline_voucher_gl_net,
            d.baseline_restored_invoice_amount,
            d.planning,
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
                {"name": "Candidate Ready", "values": [int(row.ready_for_next_controlled_cycle_candidate_selection or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Design Records"), "datatype": "Int"},
        {"value": sum(int(row.design_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(int(row.ready_for_next_controlled_cycle_candidate_selection or 0) for row in data), "indicator": "Green", "label": _("Candidate Ready"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL Created"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def design_columns():
    return [
        {"fieldname": "design", "label": _("Design"), "fieldtype": "Link", "options": DESIGN_DOCTYPE, "width": 220},
        {"fieldname": "design_id", "label": _("Design ID"), "fieldtype": "Data", "width": 360},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 140},
        {"fieldname": "design_status", "label": _("Design Status"), "fieldtype": "Data", "width": 320},
        {"fieldname": "design_approved", "label": _("Approved"), "fieldtype": "Check", "width": 90},
        {"fieldname": "phase11p_planning_verified", "label": _("11P Verified"), "fieldtype": "Check", "width": 105},
        {"fieldname": "planning_approved_verified", "label": _("Planning OK"), "fieldtype": "Check", "width": 105},
        {"fieldname": "planning_envelope_locked_verified", "label": _("Envelope OK"), "fieldtype": "Check", "width": 105},
        {"fieldname": "candidate_selection_not_started_verified", "label": _("No Candidate"), "fieldtype": "Check", "width": 105},
        {"fieldname": "design_source_locked", "label": _("Source Locked"), "fieldtype": "Check", "width": 110},
        {"fieldname": "design_shape_locked", "label": _("Shape Locked"), "fieldtype": "Check", "width": 110},
        {"fieldname": "ready_for_next_controlled_cycle_candidate_selection", "label": _("Candidate Ready"), "fieldtype": "Check", "width": 125},
        {"fieldname": "design_source_doctype", "label": _("Source"), "fieldtype": "Data", "width": 120},
        {"fieldname": "design_reference_doctype", "label": _("Reference"), "fieldtype": "Data", "width": 120},
        {"fieldname": "design_party_type", "label": _("Party Type"), "fieldtype": "Data", "width": 100},
        {"fieldname": "design_line_count", "label": _("Lines"), "fieldtype": "Int", "width": 70},
        {"fieldname": "design_total_amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 100},
        {"fieldname": "design_payment_entry_count", "label": _("Future PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "baseline_payment_entry", "label": _("Baseline PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "payment_entry_docstatus_design", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 100},
        {"fieldname": "payment_entry_status_design", "label": _("PE Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "baseline_voucher_gl_rows", "label": _("Voucher GL Rows"), "fieldtype": "Int", "width": 120},
        {"fieldname": "baseline_voucher_gl_net", "label": _("Voucher Net"), "fieldtype": "Currency", "options": "currency", "width": 100},
        {"fieldname": "baseline_restored_invoice_amount", "label": _("Restored Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "planning", "label": _("Planning"), "fieldtype": "Link", "options": PLANNING_DOCTYPE, "width": 220},
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
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 190},
        {"fieldname": "line_no", "label": _("Line"), "fieldtype": "Int", "width": 60},
        {"fieldname": "design_source_doctype", "label": _("Design Source"), "fieldtype": "Data", "width": 130},
        {"fieldname": "design_reference_doctype", "label": _("Design Reference"), "fieldtype": "Data", "width": 140},
        {"fieldname": "design_amount", "label": _("Design Amount"), "fieldtype": "Currency", "width": 120},
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
            i.design,
            i.status,
            i.severity,
            i.category,
            i.line_no,
            i.design_source_doctype,
            i.design_reference_doctype,
            i.design_amount,
            i.baseline_payment_entry,
            i.check_key,
            i.check_label,
            i.detail,
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
        {"value": len([row for row in data if row.category == "Design Shape"]), "indicator": "Green", "label": _("Design Lines"), "datatype": "Int"},
        {"value": sum(flt(row.design_amount or 0, 2) for row in data if row.category == "Design Shape"), "indicator": "Green", "label": _("Design Amount"), "datatype": "Currency"},
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
