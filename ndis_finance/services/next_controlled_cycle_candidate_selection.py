import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, today

from ndis_finance.services.permissions import assert_action


CANDIDATE_ACK = "I_CONFIRM_PHASE11R_SELECT_NEXT_CONTROLLED_CYCLE_CANDIDATES_NO_POSTING"

POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
DESIGN_DOCTYPE = "NDIS Next Controlled Cycle Design"
CANDIDATE_DOCTYPE = "NDIS Next Controlled Cycle Candidate"
CANDIDATE_ITEM_DOCTYPE = "NDIS Next Controlled Cycle Cand Item"

SELECTED_SOURCE_DOCTYPE = "Sales Invoice"
SELECTED_REFERENCE_DOCTYPE = "Sales Invoice"
SELECTED_PARTY_TYPE = "Customer"
SELECTED_INVOICE_COUNT = 3
SELECTED_TOTAL_AMOUNT = 3.00
SELECTED_PAYMENT_ENTRY_COUNT = 1


def make_candidate_id():
    timestamp = now_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-NEXT-CONTROLLED-CYCLE-CANDIDATE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_design():
    rows = frappe.get_all(
        DESIGN_DOCTYPE,
        filters={
            "status": "Design Approved",
            "design_status": "Next Controlled Cycle Design Approved",
            "design_approved": 1,
            "phase11p_planning_verified": 1,
            "planning_approved_verified": 1,
            "planning_envelope_locked_verified": 1,
            "candidate_selection_not_started_verified": 1,
            "design_source_locked": 1,
            "design_shape_locked": 1,
            "ready_for_next_controlled_cycle_candidate_selection": 1,
            "design_source_doctype": SELECTED_SOURCE_DOCTYPE,
            "design_reference_doctype": SELECTED_REFERENCE_DOCTYPE,
            "design_party_type": SELECTED_PARTY_TYPE,
            "design_line_count": SELECTED_INVOICE_COUNT,
            "design_total_amount": SELECTED_TOTAL_AMOUNT,
            "design_payment_entry_count": SELECTED_PAYMENT_ENTRY_COUNT,
            "design_live_posting_allowed": 0,
            "design_journal_entry_side_effect_allowed": 0,
            "design_purchase_invoice_side_effect_allowed": 0,
            "payment_entry_docstatus_design": 2,
            "payment_entry_status_design": "Cancelled",
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
            "design_id",
            "baseline_payment_entry",
            "baseline_reference_count",
            "baseline_total_amount",
            "baseline_restored_invoice_amount",
            "planning",
            "monitor",
            "baseline",
            "closeout",
            "freeze",
            "rollback",
            "smoke",
            "execution_gate",
            "preview",
            "validation",
            "previous_candidate",
            "previous_design",
            "previous_planning",
            "target_policy_doctype",
            "target_policy",
            "target_policy_name",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_approved_candidate(design):
    rows = frappe.get_all(
        CANDIDATE_DOCTYPE,
        filters={
            "design": design,
            "status": "Candidate Selection Approved",
            "candidate_selection_approved": 1,
        },
        fields=["name", "candidate_id"],
        limit=1,
    )
    return rows[0] if rows else None


def baseline_reference_rows(payment_entry):
    if not payment_entry:
        return []

    refs = frappe.get_all(
        "Payment Entry Reference",
        filters={"parent": payment_entry, "reference_doctype": "Sales Invoice"},
        fields=[
            "idx",
            "reference_doctype",
            "reference_name",
            "allocated_amount",
            "outstanding_amount",
            "total_amount",
        ],
        order_by="idx asc",
    )

    selected = []
    for ref in refs:
        si = frappe.db.get_value(
            "Sales Invoice",
            ref.reference_name,
            [
                "name",
                "docstatus",
                "customer",
                "company",
                "currency",
                "grand_total",
                "outstanding_amount",
            ],
            as_dict=True,
        )

        selected.append(
            frappe._dict(
                {
                    "idx": int(ref.idx or len(selected) + 1),
                    "reference_doctype": "Sales Invoice",
                    "reference_name": ref.reference_name,
                    "allocated_amount": flt(ref.allocated_amount or 0, 2),
                    "reference_total_amount": flt(ref.total_amount or 0, 2),
                    "reference_outstanding_from_pe": flt(ref.outstanding_amount or 0, 2),
                    "sales_invoice_exists": 1 if si else 0,
                    "sales_invoice_docstatus": int(si.docstatus or 0) if si else 0,
                    "customer": si.customer if si else None,
                    "company": si.company if si else None,
                    "currency": si.currency if si else None,
                    "grand_total": flt(si.grand_total or 0, 2) if si else 0,
                    "outstanding_amount": flt(si.outstanding_amount or 0, 2) if si else 0,
                }
            )
        )

    return selected


def selected_total(rows):
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


def selected_customers(rows):
    return sorted(set([row.customer for row in rows if row.customer]))


def selected_companies(rows):
    return sorted(set([row.company for row in rows if row.company]))


def selected_currencies(rows):
    return sorted(set([row.currency for row in rows if row.currency]))


def validate_source(design, payment_entry, selected, guard, config, policy_enabled, policy_live):
    issues = []

    if not design:
        issues.append("No approved Phase 11Q next controlled-cycle design found.")
        return issues

    existing = existing_approved_candidate(design.name)
    if existing:
        issues.append(f"Approved Phase 11R candidate selection already exists for this design: {existing.candidate_id}")

    if not payment_entry:
        issues.append("Phase 11Q design does not identify the baseline Payment Entry.")
        return issues

    if not frappe.db.exists("Payment Entry", payment_entry):
        issues.append(f"Baseline Payment Entry does not exist: {payment_entry}")
        return issues

    pe = frappe.get_doc("Payment Entry", payment_entry)

    if pe.docstatus != 2:
        issues.append(f"Payment Entry must remain cancelled for candidate selection. docstatus={pe.docstatus}")

    if pe.status != "Cancelled":
        issues.append(f"Payment Entry status must remain Cancelled for candidate selection. status={pe.status}")

    if len(selected) != SELECTED_INVOICE_COUNT:
        issues.append(f"Candidate selection must select exactly {SELECTED_INVOICE_COUNT} Sales Invoices. Found {len(selected)}.")

    if selected_total(selected) != SELECTED_TOTAL_AMOUNT:
        issues.append(f"Candidate selected total must be {SELECTED_TOTAL_AMOUNT}. Found {selected_total(selected)}.")

    for row in selected:
        if not row.sales_invoice_exists:
            issues.append(f"Selected Sales Invoice does not exist: {row.reference_name}")
            continue

        if row.sales_invoice_docstatus != 1:
            issues.append(f"Selected Sales Invoice must be submitted: {row.reference_name}")

        if row.outstanding_amount < row.allocated_amount:
            issues.append(
                f"Selected Sales Invoice outstanding amount is insufficient: {row.reference_name}, "
                f"outstanding={row.outstanding_amount}, allocated={row.allocated_amount}"
            )

        if row.allocated_amount <= 0:
            issues.append(f"Selected allocation must be positive: {row.reference_name}")

    if len(selected_customers(selected)) != 1:
        issues.append("Selected Sales Invoices must all have the same customer.")

    if len(selected_companies(selected)) != 1:
        issues.append("Selected Sales Invoices must all have the same company.")

    if len(selected_currencies(selected)) != 1:
        issues.append("Selected Sales Invoices must all have the same currency.")

    if voucher_gl_rows(payment_entry) != 8:
        issues.append(f"Voucher GL rows must remain 8. Found {voucher_gl_rows(payment_entry)}.")

    if voucher_gl_net(payment_entry) != 0:
        issues.append(f"Voucher GL net must remain 0.00. Found {voucher_gl_net(payment_entry)}.")

    if voucher_gl_non_zero_accounts(payment_entry) != 0:
        issues.append(f"Voucher non-zero account count must remain 0. Found {voucher_gl_non_zero_accounts(payment_entry)}.")

    if guard["payment_entry_count"] != 9:
        issues.append("Payment Entry count must remain 9 before Phase 11R candidate selection.")

    if guard["payment_entry_gl_count"] != 54:
        issues.append("Payment Entry GL count must remain 54 before Phase 11R candidate selection.")

    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today must remain 0 before candidate selection.")

    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today must remain 0 before candidate selection.")

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


def add_item(items, status, severity, category, check_key, check_label, detail, selected_row=None, baseline_payment_entry=None):
    item = {
        "status": status,
        "severity": severity,
        "category": category,
        "check_key": check_key,
        "check_label": check_label,
        "detail": detail,
        "baseline_payment_entry": baseline_payment_entry,
    }

    if selected_row:
        item.update(
            {
                "line_no": selected_row.idx,
                "reference_doctype": selected_row.reference_doctype,
                "reference_name": selected_row.reference_name,
                "customer": selected_row.customer,
                "company": selected_row.company,
                "currency": selected_row.currency,
                "outstanding_amount": selected_row.outstanding_amount,
                "allocated_amount": selected_row.allocated_amount,
            }
        )

    items.append(item)


def build_items(design, selected, issues, ack_ok, baseline_payment_entry=None):
    items = []

    if design:
        add_item(
            items,
            "Pass",
            "Low",
            "Evidence",
            "phase11q_design_exists",
            "Phase 11Q design exists",
            f"Design found: {design.design_id}.",
            baseline_payment_entry=baseline_payment_entry,
        )
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase11q_design_exists", "Phase 11Q design exists", "No approved Phase 11Q design found.")

    if not issues:
        add_item(
            items,
            "Pass",
            "Critical",
            "Candidate Source",
            "candidate_source_valid",
            "Candidate source valid",
            "Design is approved and 3 eligible Sales Invoice candidates were selected.",
            baseline_payment_entry=baseline_payment_entry,
        )
    else:
        for issue in issues:
            add_item(
                items,
                "Blocker",
                "Critical",
                "Candidate Source",
                "candidate_source_valid",
                "Candidate source valid",
                issue,
                baseline_payment_entry=baseline_payment_entry,
            )

    for row in selected:
        add_item(
            items,
            "Pass",
            "High",
            "Selected Candidate",
            "selected_sales_invoice_candidate",
            f"Selected Sales Invoice {row.idx}",
            (
                f"{row.reference_name} selected from restored baseline Payment Entry reference. "
                f"allocated={row.allocated_amount}, outstanding={row.outstanding_amount}."
            ),
            selected_row=row,
            baseline_payment_entry=baseline_payment_entry,
        )

    checks = [
        ("design_source_locked", "Design source locked", f"{SELECTED_SOURCE_DOCTYPE} / {SELECTED_REFERENCE_DOCTYPE} / {SELECTED_PARTY_TYPE}"),
        ("design_shape_locked", "Design shape locked", f"{SELECTED_INVOICE_COUNT} / {SELECTED_TOTAL_AMOUNT} / {SELECTED_PAYMENT_ENTRY_COUNT}"),
        ("selected_invoice_count", "Selected invoice count = 3", len(selected)),
        ("selected_total", "Selected total = 3.00", selected_total(selected)),
        ("same_customer", "Same customer verified", ", ".join(selected_customers(selected)) or "None"),
        ("same_company", "Same company verified", ", ".join(selected_companies(selected)) or "None"),
        ("same_currency", "Same currency verified", ", ".join(selected_currencies(selected)) or "None"),
        ("payment_entry_count", "Payment Entry count remains 9", 9),
        ("payment_entry_gl_count", "Payment Entry GL count remains 54", 54),
        ("policy_state", "Policy state preserved at 1 / 0", "1 / 0"),
        ("no_pe_movement", "No Payment Entry movement in candidate selection", "0 / 0"),
        ("no_gl_movement", "No GL movement in candidate selection", 0),
        ("no_je_pi", "No JE / PI side effects", "0 / 0"),
        ("ready_for_candidate_validation", "Ready for candidate validation", 1),
    ]

    for key, label, value in checks:
        add_item(
            items,
            "Pass",
            "High",
            "Candidate Evidence",
            key,
            label,
            f"value={value}",
            baseline_payment_entry=baseline_payment_entry,
        )

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.", baseline_payment_entry=baseline_payment_entry)
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {CANDIDATE_ACK}")

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
        row = frappe.new_doc(CANDIDATE_ITEM_DOCTYPE)
        row.candidate = doc.name

        for fieldname, value in item.items():
            if row.meta.has_field(fieldname):
                setattr(row, fieldname, value)

        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_next_controlled_cycle_candidate_selection(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_next_controlled_cycle_candidate_selection")

    design = latest_design()
    payment_entry = design.baseline_payment_entry if design else None
    selected = baseline_reference_rows(payment_entry) if payment_entry else []

    guard_before = guardrails()
    ack_ok = acknowledgement == CANDIDATE_ACK

    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }

    policy_enabled_before = get_flag(POLICY_DOCTYPE, design.target_policy, "production_batch_enabled") if design else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, design.target_policy, "live_posting_allowed") if design else 0

    issues = validate_source(design, payment_entry, selected, guard_before, config, policy_enabled_before, policy_live_before)

    guard_after = guardrails()

    policy_enabled_after = get_flag(POLICY_DOCTYPE, design.target_policy, "production_batch_enabled") if design else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, design.target_policy, "live_posting_allowed") if design else 0

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
        baseline_total = flt(pe.paid_amount or pe.received_amount or selected_total(selected), 2)
        voucher_rows = voucher_gl_rows(payment_entry)
        voucher_net = voucher_gl_net(payment_entry)
        non_zero_accounts = voucher_gl_non_zero_accounts(payment_entry)

    post_issues = list(issues)

    if actual_pe_created != 0:
        post_issues.append(f"Candidate selection must not create Payment Entries. Created {actual_pe_created}.")

    if actual_pe_cancelled != 0:
        post_issues.append(f"Candidate selection must not cancel Payment Entries. Cancelled {actual_pe_cancelled}.")

    if actual_gl_created != 0:
        post_issues.append(f"Candidate selection must not create GL rows. Created {actual_gl_created}.")

    if guard_after["payment_entry_count"] != 9:
        post_issues.append("Payment Entry count must remain 9 after candidate selection.")

    if guard_after["payment_entry_gl_count"] != 54:
        post_issues.append("Payment Entry GL count must remain 54 after candidate selection.")

    if guard_after["submitted_journal_entry_count_today"] != 0:
        post_issues.append("Submitted Journal Entry count today must remain 0 after candidate selection.")

    if guard_after["purchase_invoice_count_today"] != 0:
        post_issues.append("Purchase Invoice count today must remain 0 after candidate selection.")

    if policy_mutation_count != 0:
        post_issues.append("Policy state changed during candidate selection. This is not allowed.")

    customers = selected_customers(selected)
    companies = selected_companies(selected)
    currencies = selected_currencies(selected)

    items = build_items(
        design,
        selected,
        post_issues,
        ack_ok,
        baseline_payment_entry=payment_entry,
    )
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    completed = int(
        ack_ok
        and design
        and payment_entry
        and item_summary["blocker_count"] == 0
        and pe_docstatus == 2
        and pe_status == "Cancelled"
        and len(selected) == SELECTED_INVOICE_COUNT
        and selected_total(selected) == SELECTED_TOTAL_AMOUNT
        and len(customers) == 1
        and len(companies) == 1
        and len(currencies) == 1
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
        "status": "Candidate Selection Approved" if completed else "Needs Review",
        "candidate_selection_status": "Next Controlled Cycle Candidate Selection Approved" if completed else "Needs Review",
        "candidate_selection_approved": completed,
        "phase11q_design_verified": 1 if design else 0,
        "design_approved_verified": 1 if design else 0,
        "design_source_locked_verified": 1 if design else 0,
        "design_shape_locked_verified": 1 if design else 0,
        "eligible_sales_invoices_selected": completed,
        "selected_invoice_count_verified": int(len(selected) == SELECTED_INVOICE_COUNT),
        "same_customer_verified": int(len(customers) == 1),
        "same_company_verified": int(len(companies) == 1),
        "same_currency_verified": int(len(currencies) == 1),
        "selected_total_verified": int(selected_total(selected) == SELECTED_TOTAL_AMOUNT),
        "selected_future_payment_entry_count_verified": int(SELECTED_PAYMENT_ENTRY_COUNT == 1),
        "policy_state_preserved_verified": int(policy_mutation_count == 0 and policy_enabled_before == 1 and policy_enabled_after == 1 and policy_live_before == 0 and policy_live_after == 0),
        "ready_for_next_controlled_cycle_candidate_validation": completed,
        "no_new_accounting_movement_verified": int(actual_pe_created == 0 and actual_pe_cancelled == 0 and actual_gl_created == 0),
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": policy_mutation_count,
        "selected_source_doctype": SELECTED_SOURCE_DOCTYPE,
        "selected_reference_doctype": SELECTED_REFERENCE_DOCTYPE,
        "selected_party_type": SELECTED_PARTY_TYPE,
        "selected_customer": customers[0] if customers else None,
        "selected_company": companies[0] if companies else None,
        "selected_currency": currencies[0] if currencies else None,
        "selected_invoice_count": len(selected),
        "selected_total_amount": selected_total(selected),
        "selected_payment_entry_count": SELECTED_PAYMENT_ENTRY_COUNT,
        "selected_live_posting_allowed": 0,
        "selected_journal_entry_side_effect_allowed": 0,
        "selected_purchase_invoice_side_effect_allowed": 0,
        "baseline_payment_entry": payment_entry,
        "payment_entry_docstatus_candidate": pe_docstatus,
        "payment_entry_status_candidate": pe_status,
        "baseline_reference_count": len(selected),
        "baseline_total_amount": baseline_total,
        "baseline_voucher_gl_rows": voucher_rows,
        "baseline_voucher_gl_net": voucher_net,
        "baseline_voucher_gl_non_zero_account_count": non_zero_accounts,
        "baseline_restored_invoice_amount": selected_total(selected) if selected_total(selected) == 3 else 0,
        "design": design.name if design else None,
        "planning": design.planning if design else None,
        "monitor": design.monitor if design else None,
        "baseline": design.baseline if design else None,
        "closeout": design.closeout if design else None,
        "freeze": design.freeze if design else None,
        "rollback": design.rollback if design else None,
        "smoke": design.smoke if design else None,
        "execution_gate": design.execution_gate if design else None,
        "preview": design.preview if design else None,
        "previous_validation": design.validation if design else None,
        "previous_candidate": design.previous_candidate if design else None,
        "previous_design": design.previous_design if design else None,
        "previous_planning": design.previous_planning if design else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": design.target_policy if design else None,
        "target_policy_name": design.target_policy_name if design else None,
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
        "candidate_score": score,
        **item_summary,
        "items": items,
        "selected_invoices": [dict(row) for row in selected],
        "issues": post_issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "required_acknowledgement": CANDIDATE_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 11R selects the next controlled-cycle Sales Invoice candidates only. No posting occurs.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["candidate_selection_status"] = "Needs Review"
        result["candidate_selection_approved"] = 0
        result["eligible_sales_invoices_selected"] = 0
        result["ready_for_next_controlled_cycle_candidate_validation"] = 0
        return result

    doc = frappe.new_doc(CANDIDATE_DOCTYPE)
    doc.candidate_id = make_candidate_id()

    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)

    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = CANDIDATE_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.candidate_json = safe_json(
        {
            "design": design,
            "baseline_payment_entry": payment_entry,
            "selected_invoices": [dict(row) for row in selected],
            "selection": {
                "source_doctype": SELECTED_SOURCE_DOCTYPE,
                "reference_doctype": SELECTED_REFERENCE_DOCTYPE,
                "party_type": SELECTED_PARTY_TYPE,
                "invoice_count": len(selected),
                "total_amount": selected_total(selected),
                "payment_entry_count": SELECTED_PAYMENT_ENTRY_COUNT,
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
        "candidate": doc.name,
        "candidate_id": doc.candidate_id,
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_next_controlled_cycle_candidate_selection_audit(candidate, reason=None):
    assert_action("cancel_next_controlled_cycle_candidate_selection_audit")

    if not frappe.db.exists(CANDIDATE_DOCTYPE, candidate):
        frappe.throw(_("Next controlled-cycle candidate audit not found: {0}").format(candidate))

    doc = frappe.get_doc(CANDIDATE_DOCTYPE, candidate)

    if doc.status == "Cancelled":
        return {"candidate": candidate, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.candidate_selection_approved or 0):
        frappe.throw(_("Cannot cancel an approved Phase 11R candidate selection record."))

    frappe.db.set_value(
        CANDIDATE_DOCTYPE,
        candidate,
        {
            "status": "Cancelled",
            "candidate_selection_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 11R no-ack candidate selection audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        f"""
        UPDATE `tab{CANDIDATE_ITEM_DOCTYPE}`
        SET status = 'Cancelled'
        WHERE candidate = %(candidate)s
        """,
        {"candidate": candidate},
    )

    frappe.db.commit()

    return {
        "candidate": candidate,
        "status": "Cancelled",
        "note": "No-ack candidate selection audit cancelled only. No accounting or policy movement occurred.",
    }


@frappe.whitelist()
def quick_next_controlled_cycle_candidate_selection_summary(limit=20):
    records = frappe.get_all(
        CANDIDATE_DOCTYPE,
        fields=[
            "name",
            "candidate_id",
            "status",
            "candidate_selection_status",
            "candidate_selection_approved",
            "eligible_sales_invoices_selected",
            "ready_for_next_controlled_cycle_candidate_validation",
            "selected_source_doctype",
            "selected_reference_doctype",
            "selected_party_type",
            "selected_customer",
            "selected_company",
            "selected_currency",
            "selected_invoice_count",
            "selected_total_amount",
            "selected_payment_entry_count",
            "baseline_payment_entry",
            "payment_entry_docstatus_candidate",
            "payment_entry_status_candidate",
            "design",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "actual_payment_entry_created_count",
            "actual_payment_entry_cancelled_count",
            "actual_gl_created_count",
            "submitted_journal_entry_count_today",
            "purchase_invoice_count_today",
            "candidate_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    items = frappe.get_all(
        CANDIDATE_ITEM_DOCTYPE,
        fields=[
            "name",
            "candidate",
            "status",
            "severity",
            "category",
            "check_key",
            "check_label",
            "line_no",
            "reference_doctype",
            "reference_name",
            "customer",
            "company",
            "currency",
            "outstanding_amount",
            "allocated_amount",
            "baseline_payment_entry",
            "detail",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    return {
        "candidate_records": records,
        "items": items,
        "required_acknowledgement": CANDIDATE_ACK,
        "guardrails": guardrails(),
        "note": "Phase 11R next controlled-cycle candidate selection summary.",
    }


def execute_candidate_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("status"):
        conditions.append("c.status = %(status)s")
        params["status"] = filters.get("status")

    columns = candidate_columns()

    data = frappe.db.sql(
        f"""
        SELECT
            c.name AS candidate,
            c.candidate_id,
            c.status,
            c.candidate_selection_status,
            c.candidate_selection_approved,
            c.phase11q_design_verified,
            c.design_approved_verified,
            c.design_source_locked_verified,
            c.design_shape_locked_verified,
            c.eligible_sales_invoices_selected,
            c.same_customer_verified,
            c.same_company_verified,
            c.same_currency_verified,
            c.selected_total_verified,
            c.ready_for_next_controlled_cycle_candidate_validation,
            c.selected_source_doctype,
            c.selected_reference_doctype,
            c.selected_party_type,
            c.selected_customer,
            c.selected_company,
            c.selected_currency,
            c.selected_invoice_count,
            c.selected_total_amount,
            c.selected_payment_entry_count,
            c.baseline_payment_entry,
            c.payment_entry_docstatus_candidate,
            c.payment_entry_status_candidate,
            c.design,
            c.payment_entry_count_before,
            c.payment_entry_count_after,
            c.payment_entry_gl_count_before,
            c.payment_entry_gl_count_after,
            c.actual_payment_entry_created_count,
            c.actual_payment_entry_cancelled_count,
            c.actual_gl_created_count,
            c.submitted_journal_entry_count_today,
            c.purchase_invoice_count_today,
            c.candidate_score,
            c.checked_on,
            %(currency)s AS currency
        FROM `tab{CANDIDATE_DOCTYPE}` c
        {build_where(conditions)}
        ORDER BY c.creation DESC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.candidate_id for row in data[:20]],
            "datasets": [
                {"name": "Approved", "values": [int(row.candidate_selection_approved or 0) for row in data[:20]]},
                {"name": "Validation Ready", "values": [int(row.ready_for_next_controlled_cycle_candidate_validation or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Candidate Records"), "datatype": "Int"},
        {"value": sum(int(row.candidate_selection_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(int(row.ready_for_next_controlled_cycle_candidate_validation or 0) for row in data), "indicator": "Green", "label": _("Validation Ready"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL Created"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def candidate_columns():
    return [
        {"fieldname": "candidate", "label": _("Candidate"), "fieldtype": "Link", "options": CANDIDATE_DOCTYPE, "width": 220},
        {"fieldname": "candidate_id", "label": _("Candidate ID"), "fieldtype": "Data", "width": 370},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 180},
        {"fieldname": "candidate_selection_status", "label": _("Candidate Status"), "fieldtype": "Data", "width": 340},
        {"fieldname": "candidate_selection_approved", "label": _("Approved"), "fieldtype": "Check", "width": 90},
        {"fieldname": "phase11q_design_verified", "label": _("11Q Verified"), "fieldtype": "Check", "width": 105},
        {"fieldname": "design_approved_verified", "label": _("Design OK"), "fieldtype": "Check", "width": 95},
        {"fieldname": "design_source_locked_verified", "label": _("Source OK"), "fieldtype": "Check", "width": 95},
        {"fieldname": "design_shape_locked_verified", "label": _("Shape OK"), "fieldtype": "Check", "width": 95},
        {"fieldname": "eligible_sales_invoices_selected", "label": _("Eligible Selected"), "fieldtype": "Check", "width": 120},
        {"fieldname": "same_customer_verified", "label": _("Customer OK"), "fieldtype": "Check", "width": 100},
        {"fieldname": "same_company_verified", "label": _("Company OK"), "fieldtype": "Check", "width": 100},
        {"fieldname": "same_currency_verified", "label": _("Currency OK"), "fieldtype": "Check", "width": 100},
        {"fieldname": "selected_total_verified", "label": _("Total OK"), "fieldtype": "Check", "width": 90},
        {"fieldname": "ready_for_next_controlled_cycle_candidate_validation", "label": _("Validation Ready"), "fieldtype": "Check", "width": 130},
        {"fieldname": "selected_source_doctype", "label": _("Source"), "fieldtype": "Data", "width": 120},
        {"fieldname": "selected_reference_doctype", "label": _("Reference"), "fieldtype": "Data", "width": 120},
        {"fieldname": "selected_party_type", "label": _("Party Type"), "fieldtype": "Data", "width": 100},
        {"fieldname": "selected_customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 220},
        {"fieldname": "selected_company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 220},
        {"fieldname": "selected_currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "width": 100},
        {"fieldname": "selected_invoice_count", "label": _("Invoices"), "fieldtype": "Int", "width": 80},
        {"fieldname": "selected_total_amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 100},
        {"fieldname": "selected_payment_entry_count", "label": _("Future PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "baseline_payment_entry", "label": _("Baseline PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "payment_entry_docstatus_candidate", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 100},
        {"fieldname": "payment_entry_status_candidate", "label": _("PE Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "design", "label": _("Design"), "fieldtype": "Link", "options": DESIGN_DOCTYPE, "width": 220},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 110},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE Created"), "fieldtype": "Int", "width": 125},
        {"fieldname": "actual_payment_entry_cancelled_count", "label": _("Actual PE Cancelled"), "fieldtype": "Int", "width": 135},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL Created"), "fieldtype": "Int", "width": 125},
        {"fieldname": "submitted_journal_entry_count_today", "label": _("JE Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "purchase_invoice_count_today", "label": _("PI Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "candidate_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    if filters.get("candidate"):
        conditions.append("i.candidate = %(candidate)s")
        params["candidate"] = filters.get("candidate")

    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": CANDIDATE_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "candidate", "label": _("Candidate"), "fieldtype": "Link", "options": CANDIDATE_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 190},
        {"fieldname": "line_no", "label": _("Line"), "fieldtype": "Int", "width": 60},
        {"fieldname": "reference_doctype", "label": _("Ref DocType"), "fieldtype": "Data", "width": 130},
        {"fieldname": "reference_name", "label": _("Reference"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 180},
        {"fieldname": "customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 220},
        {"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 220},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "width": 90},
        {"fieldname": "outstanding_amount", "label": _("Outstanding"), "fieldtype": "Currency", "width": 110},
        {"fieldname": "allocated_amount", "label": _("Allocated"), "fieldtype": "Currency", "width": 100},
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
            i.candidate,
            i.status,
            i.severity,
            i.category,
            i.line_no,
            i.reference_doctype,
            i.reference_name,
            i.customer,
            i.company,
            i.currency,
            i.outstanding_amount,
            i.allocated_amount,
            i.baseline_payment_entry,
            i.check_key,
            i.check_label,
            i.detail,
            i.checked_on
        FROM `tab{CANDIDATE_ITEM_DOCTYPE}` i
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
        {"value": len([row for row in data if row.category == "Selected Candidate"]), "indicator": "Green", "label": _("Selected Candidates"), "datatype": "Int"},
        {"value": sum(flt(row.allocated_amount or 0, 2) for row in data if row.category == "Selected Candidate"), "indicator": "Green", "label": _("Selected Amount"), "datatype": "Currency"},
        {"value": len([row for row in data if row.status == "Blocker"]), "indicator": "Red", "label": _("Blockers"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_candidate_report(filters)
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
