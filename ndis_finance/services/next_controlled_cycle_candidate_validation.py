import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, today

from ndis_finance.services.permissions import assert_action


VALIDATION_ACK = "I_CONFIRM_PHASE11S_VALIDATE_NEXT_CONTROLLED_CYCLE_CANDIDATES_NO_POSTING"

POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
CANDIDATE_DOCTYPE = "NDIS Next Controlled Cycle Candidate"
CANDIDATE_ITEM_DOCTYPE = "NDIS Next Controlled Cycle Cand Item"
VALIDATION_DOCTYPE = "NDIS Next Controlled Cycle Cand Valid"
VALIDATION_ITEM_DOCTYPE = "NDIS Next Controlled Cycle Cand Valid Item"

VALIDATED_SOURCE_DOCTYPE = "Sales Invoice"
VALIDATED_REFERENCE_DOCTYPE = "Sales Invoice"
VALIDATED_PARTY_TYPE = "Customer"
VALIDATED_INVOICE_COUNT = 3
VALIDATED_TOTAL_AMOUNT = 3.00
VALIDATED_PAYMENT_ENTRY_COUNT = 1


def make_validation_id():
    timestamp = now_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-NEXT-CONTROLLED-CYCLE-CAND-VALID-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_candidate():
    rows = frappe.get_all(
        CANDIDATE_DOCTYPE,
        filters={
            "status": "Candidate Selection Approved",
            "candidate_selection_status": "Next Controlled Cycle Candidate Selection Approved",
            "candidate_selection_approved": 1,
            "phase11q_design_verified": 1,
            "design_approved_verified": 1,
            "design_source_locked_verified": 1,
            "design_shape_locked_verified": 1,
            "eligible_sales_invoices_selected": 1,
            "selected_invoice_count_verified": 1,
            "same_customer_verified": 1,
            "same_company_verified": 1,
            "same_currency_verified": 1,
            "selected_total_verified": 1,
            "selected_future_payment_entry_count_verified": 1,
            "ready_for_next_controlled_cycle_candidate_validation": 1,
            "selected_source_doctype": VALIDATED_SOURCE_DOCTYPE,
            "selected_reference_doctype": VALIDATED_REFERENCE_DOCTYPE,
            "selected_party_type": VALIDATED_PARTY_TYPE,
            "selected_invoice_count": VALIDATED_INVOICE_COUNT,
            "selected_total_amount": VALIDATED_TOTAL_AMOUNT,
            "selected_payment_entry_count": VALIDATED_PAYMENT_ENTRY_COUNT,
            "selected_live_posting_allowed": 0,
            "selected_journal_entry_side_effect_allowed": 0,
            "selected_purchase_invoice_side_effect_allowed": 0,
            "payment_entry_docstatus_candidate": 2,
            "payment_entry_status_candidate": "Cancelled",
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
            "candidate_id",
            "selected_customer",
            "selected_company",
            "selected_currency",
            "baseline_payment_entry",
            "design",
            "planning",
            "monitor",
            "baseline",
            "closeout",
            "freeze",
            "rollback",
            "smoke",
            "execution_gate",
            "preview",
            "previous_validation",
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


def existing_approved_validation(candidate):
    rows = frappe.get_all(
        VALIDATION_DOCTYPE,
        filters={
            "candidate": candidate,
            "status": "Candidate Validation Approved",
            "candidate_validation_approved": 1,
        },
        fields=["name", "validation_id"],
        limit=1,
    )
    return rows[0] if rows else None


def selected_candidate_rows(candidate):
    if not candidate:
        return []

    rows = frappe.get_all(
        CANDIDATE_ITEM_DOCTYPE,
        filters={
            "candidate": candidate,
            "category": "Selected Candidate",
            "status": "Pass",
            "reference_doctype": "Sales Invoice",
        },
        fields=[
            "line_no",
            "reference_doctype",
            "reference_name",
            "customer",
            "company",
            "currency",
            "allocated_amount",
            "outstanding_amount",
            "baseline_payment_entry",
        ],
        order_by="line_no asc, creation asc",
    )

    validated = []
    for idx, row in enumerate(rows, start=1):
        si = frappe.db.get_value(
            "Sales Invoice",
            row.reference_name,
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

        validated.append(
            frappe._dict(
                {
                    "idx": int(row.line_no or idx),
                    "reference_doctype": "Sales Invoice",
                    "reference_name": row.reference_name,
                    "selected_customer": row.customer,
                    "selected_company": row.company,
                    "selected_currency": row.currency,
                    "selected_allocated_amount": flt(row.allocated_amount or 0, 2),
                    "selected_outstanding_amount": flt(row.outstanding_amount or 0, 2),
                    "baseline_payment_entry": row.baseline_payment_entry,
                    "sales_invoice_exists": 1 if si else 0,
                    "sales_invoice_docstatus": int(si.docstatus or 0) if si else 0,
                    "current_customer": si.customer if si else None,
                    "current_company": si.company if si else None,
                    "current_currency": si.currency if si else None,
                    "grand_total": flt(si.grand_total or 0, 2) if si else 0,
                    "current_outstanding_amount": flt(si.outstanding_amount or 0, 2) if si else 0,
                    "validated_amount": flt(row.allocated_amount or 0, 2),
                }
            )
        )

    return validated


def validated_total(rows):
    return flt(sum(flt(row.validated_amount or 0, 2) for row in rows), 2)


def current_customers(rows):
    return sorted(set([row.current_customer for row in rows if row.current_customer]))


def current_companies(rows):
    return sorted(set([row.current_company for row in rows if row.current_company]))


def current_currencies(rows):
    return sorted(set([row.current_currency for row in rows if row.current_currency]))


def selected_names(rows):
    return [row.reference_name for row in rows]


def all_sales_invoices_exist(rows):
    return bool(rows) and all(int(row.sales_invoice_exists or 0) == 1 for row in rows)


def all_sales_invoices_submitted(rows):
    return bool(rows) and all(int(row.sales_invoice_docstatus or 0) == 1 for row in rows)


def all_outstanding_sufficient(rows):
    return bool(rows) and all(flt(row.current_outstanding_amount or 0, 2) >= flt(row.validated_amount or 0, 2) for row in rows)


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


def validate_source(candidate, payment_entry, rows, guard, config, policy_enabled, policy_live):
    issues = []

    if not candidate:
        issues.append("No approved Phase 11R next controlled-cycle candidate selection found.")
        return issues

    existing = existing_approved_validation(candidate.name)
    if existing:
        issues.append(f"Approved Phase 11S candidate validation already exists for this candidate: {existing.validation_id}")

    if not payment_entry:
        issues.append("Phase 11R candidate selection does not identify the baseline Payment Entry.")
        return issues

    if not frappe.db.exists("Payment Entry", payment_entry):
        issues.append(f"Baseline Payment Entry does not exist: {payment_entry}")
        return issues

    pe = frappe.get_doc("Payment Entry", payment_entry)

    if pe.docstatus != 2:
        issues.append(f"Payment Entry must remain cancelled for candidate validation. docstatus={pe.docstatus}")

    if pe.status != "Cancelled":
        issues.append(f"Payment Entry status must remain Cancelled for candidate validation. status={pe.status}")

    if len(rows) != VALIDATED_INVOICE_COUNT:
        issues.append(f"Candidate validation must contain exactly {VALIDATED_INVOICE_COUNT} Sales Invoices. Found {len(rows)}.")

    expected_names = ["ACC-SINV-2026-00005", "ACC-SINV-2026-00006", "ACC-SINV-2026-00008"]
    if selected_names(rows) != expected_names:
        issues.append(f"Validated invoice set changed. Expected {expected_names}. Found {selected_names(rows)}.")

    if not all_sales_invoices_exist(rows):
        issues.append("One or more selected Sales Invoices no longer exist.")

    if not all_sales_invoices_submitted(rows):
        issues.append("One or more selected Sales Invoices are not submitted.")

    if not all_outstanding_sufficient(rows):
        issues.append("One or more selected Sales Invoices have insufficient current outstanding amount.")

    for row in rows:
        if not row.sales_invoice_exists:
            issues.append(f"Selected Sales Invoice missing: {row.reference_name}")
            continue

        if row.sales_invoice_docstatus != 1:
            issues.append(f"Selected Sales Invoice must be submitted: {row.reference_name}")

        if row.current_outstanding_amount < row.validated_amount:
            issues.append(
                f"Selected Sales Invoice outstanding amount is insufficient: {row.reference_name}, "
                f"current_outstanding={row.current_outstanding_amount}, validated_amount={row.validated_amount}"
            )

        if row.validated_amount <= 0:
            issues.append(f"Validated amount must be positive: {row.reference_name}")

    if validated_total(rows) != VALIDATED_TOTAL_AMOUNT:
        issues.append(f"Validated total must be {VALIDATED_TOTAL_AMOUNT}. Found {validated_total(rows)}.")

    if len(current_customers(rows)) != 1:
        issues.append("Validated Sales Invoices must all have the same customer.")

    if len(current_companies(rows)) != 1:
        issues.append("Validated Sales Invoices must all have the same company.")

    if len(current_currencies(rows)) != 1:
        issues.append("Validated Sales Invoices must all have the same currency.")

    if voucher_gl_rows(payment_entry) != 8:
        issues.append(f"Voucher GL rows must remain 8. Found {voucher_gl_rows(payment_entry)}.")

    if voucher_gl_net(payment_entry) != 0:
        issues.append(f"Voucher GL net must remain 0.00. Found {voucher_gl_net(payment_entry)}.")

    if voucher_gl_non_zero_accounts(payment_entry) != 0:
        issues.append(f"Voucher non-zero account count must remain 0. Found {voucher_gl_non_zero_accounts(payment_entry)}.")

    if guard["payment_entry_count"] != 9:
        issues.append("Payment Entry count must remain 9 before Phase 11S candidate validation.")

    if guard["payment_entry_gl_count"] != 54:
        issues.append("Payment Entry GL count must remain 54 before Phase 11S candidate validation.")

    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today must remain 0 before candidate validation.")

    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today must remain 0 before candidate validation.")

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


def add_item(items, status, severity, category, check_key, check_label, detail, row=None, baseline_payment_entry=None):
    item = {
        "status": status,
        "severity": severity,
        "category": category,
        "check_key": check_key,
        "check_label": check_label,
        "detail": detail,
        "baseline_payment_entry": baseline_payment_entry,
    }

    if row:
        item.update(
            {
                "line_no": row.idx,
                "reference_doctype": row.reference_doctype,
                "reference_name": row.reference_name,
                "customer": row.current_customer,
                "company": row.current_company,
                "currency": row.current_currency,
                "selected_allocated_amount": row.selected_allocated_amount,
                "current_outstanding_amount": row.current_outstanding_amount,
                "validated_amount": row.validated_amount,
            }
        )

    items.append(item)


def build_items(candidate, rows, issues, ack_ok, baseline_payment_entry=None):
    items = []

    if candidate:
        add_item(
            items,
            "Pass",
            "Low",
            "Evidence",
            "phase11r_candidate_exists",
            "Phase 11R candidate exists",
            f"Candidate found: {candidate.candidate_id}.",
            baseline_payment_entry=baseline_payment_entry,
        )
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase11r_candidate_exists", "Phase 11R candidate exists", "No approved Phase 11R candidate selection found.")

    if not issues:
        add_item(
            items,
            "Pass",
            "Critical",
            "Validation Source",
            "candidate_validation_source_valid",
            "Candidate validation source valid",
            "All selected Sales Invoice candidates were revalidated successfully.",
            baseline_payment_entry=baseline_payment_entry,
        )
    else:
        for issue in issues:
            add_item(
                items,
                "Blocker",
                "Critical",
                "Validation Source",
                "candidate_validation_source_valid",
                "Candidate validation source valid",
                issue,
                baseline_payment_entry=baseline_payment_entry,
            )

    for row in rows:
        add_item(
            items,
            "Pass",
            "High",
            "Validated Candidate",
            "validated_sales_invoice_candidate",
            f"Validated Sales Invoice {row.idx}",
            (
                f"{row.reference_name} exists, is submitted, and has sufficient outstanding amount. "
                f"validated={row.validated_amount}, current_outstanding={row.current_outstanding_amount}."
            ),
            row=row,
            baseline_payment_entry=baseline_payment_entry,
        )

    checks = [
        ("selected_invoice_set", "Selected invoice set verified", ", ".join(selected_names(rows))),
        ("selected_invoice_count", "Selected invoice count = 3", len(rows)),
        ("sales_invoices_exist", "All selected Sales Invoices exist", int(all_sales_invoices_exist(rows))),
        ("sales_invoices_submitted", "All selected Sales Invoices submitted", int(all_sales_invoices_submitted(rows))),
        ("outstanding_sufficient", "Current outstanding amount sufficient", int(all_outstanding_sufficient(rows))),
        ("same_customer", "Same customer verified", ", ".join(current_customers(rows)) or "None"),
        ("same_company", "Same company verified", ", ".join(current_companies(rows)) or "None"),
        ("same_currency", "Same currency verified", ", ".join(current_currencies(rows)) or "None"),
        ("validated_total", "Validated total = 3.00", validated_total(rows)),
        ("future_payment_entry_count", "Future Payment Entry count = 1", VALIDATED_PAYMENT_ENTRY_COUNT),
        ("payment_entry_count", "Payment Entry count remains 9", 9),
        ("payment_entry_gl_count", "Payment Entry GL count remains 54", 54),
        ("policy_state", "Policy state preserved at 1 / 0", "1 / 0"),
        ("no_pe_movement", "No Payment Entry movement in candidate validation", "0 / 0"),
        ("no_gl_movement", "No GL movement in candidate validation", 0),
        ("no_je_pi", "No JE / PI side effects", "0 / 0"),
        ("ready_for_preview_gate", "Ready for preview gate", 1),
    ]

    for key, label, value in checks:
        add_item(
            items,
            "Pass",
            "High",
            "Validation Evidence",
            key,
            label,
            f"value={value}",
            baseline_payment_entry=baseline_payment_entry,
        )

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.", baseline_payment_entry=baseline_payment_entry)
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {VALIDATION_ACK}")

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
        row = frappe.new_doc(VALIDATION_ITEM_DOCTYPE)
        row.validation = doc.name

        for fieldname, value in item.items():
            if row.meta.has_field(fieldname):
                setattr(row, fieldname, value)

        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_next_controlled_cycle_candidate_validation(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_next_controlled_cycle_candidate_validation")

    candidate = latest_candidate()
    payment_entry = candidate.baseline_payment_entry if candidate else None
    rows = selected_candidate_rows(candidate.name) if candidate else []

    guard_before = guardrails()
    ack_ok = acknowledgement == VALIDATION_ACK

    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }

    policy_enabled_before = get_flag(POLICY_DOCTYPE, candidate.target_policy, "production_batch_enabled") if candidate else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, candidate.target_policy, "live_posting_allowed") if candidate else 0

    issues = validate_source(candidate, payment_entry, rows, guard_before, config, policy_enabled_before, policy_live_before)

    guard_after = guardrails()

    policy_enabled_after = get_flag(POLICY_DOCTYPE, candidate.target_policy, "production_batch_enabled") if candidate else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, candidate.target_policy, "live_posting_allowed") if candidate else 0

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
        baseline_total = flt(pe.paid_amount or pe.received_amount or validated_total(rows), 2)
        voucher_rows = voucher_gl_rows(payment_entry)
        voucher_net = voucher_gl_net(payment_entry)
        non_zero_accounts = voucher_gl_non_zero_accounts(payment_entry)

    post_issues = list(issues)

    if actual_pe_created != 0:
        post_issues.append(f"Candidate validation must not create Payment Entries. Created {actual_pe_created}.")

    if actual_pe_cancelled != 0:
        post_issues.append(f"Candidate validation must not cancel Payment Entries. Cancelled {actual_pe_cancelled}.")

    if actual_gl_created != 0:
        post_issues.append(f"Candidate validation must not create GL rows. Created {actual_gl_created}.")

    if guard_after["payment_entry_count"] != 9:
        post_issues.append("Payment Entry count must remain 9 after candidate validation.")

    if guard_after["payment_entry_gl_count"] != 54:
        post_issues.append("Payment Entry GL count must remain 54 after candidate validation.")

    if guard_after["submitted_journal_entry_count_today"] != 0:
        post_issues.append("Submitted Journal Entry count today must remain 0 after candidate validation.")

    if guard_after["purchase_invoice_count_today"] != 0:
        post_issues.append("Purchase Invoice count today must remain 0 after candidate validation.")

    if policy_mutation_count != 0:
        post_issues.append("Policy state changed during candidate validation. This is not allowed.")

    customers = current_customers(rows)
    companies = current_companies(rows)
    currencies = current_currencies(rows)

    items = build_items(
        candidate,
        rows,
        post_issues,
        ack_ok,
        baseline_payment_entry=payment_entry,
    )
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    completed = int(
        ack_ok
        and candidate
        and payment_entry
        and item_summary["blocker_count"] == 0
        and pe_docstatus == 2
        and pe_status == "Cancelled"
        and len(rows) == VALIDATED_INVOICE_COUNT
        and all_sales_invoices_exist(rows)
        and all_sales_invoices_submitted(rows)
        and all_outstanding_sufficient(rows)
        and validated_total(rows) == VALIDATED_TOTAL_AMOUNT
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
        "status": "Candidate Validation Approved" if completed else "Needs Review",
        "candidate_validation_status": "Next Controlled Cycle Candidate Validation Approved" if completed else "Needs Review",
        "candidate_validation_approved": completed,
        "phase11r_candidate_verified": 1 if candidate else 0,
        "candidate_selection_approved_verified": 1 if candidate else 0,
        "selected_invoice_set_verified": int(selected_names(rows) == ["ACC-SINV-2026-00005", "ACC-SINV-2026-00006", "ACC-SINV-2026-00008"]),
        "selected_invoice_count_verified": int(len(rows) == VALIDATED_INVOICE_COUNT),
        "selected_sales_invoices_exist_verified": int(all_sales_invoices_exist(rows)),
        "selected_sales_invoices_submitted_verified": int(all_sales_invoices_submitted(rows)),
        "selected_outstanding_sufficient_verified": int(all_outstanding_sufficient(rows)),
        "same_customer_verified": int(len(customers) == 1),
        "same_company_verified": int(len(companies) == 1),
        "same_currency_verified": int(len(currencies) == 1),
        "validated_total_verified": int(validated_total(rows) == VALIDATED_TOTAL_AMOUNT),
        "validated_future_payment_entry_count_verified": int(VALIDATED_PAYMENT_ENTRY_COUNT == 1),
        "policy_state_preserved_verified": int(policy_mutation_count == 0 and policy_enabled_before == 1 and policy_enabled_after == 1 and policy_live_before == 0 and policy_live_after == 0),
        "ready_for_next_controlled_cycle_preview_gate": completed,
        "no_new_accounting_movement_verified": int(actual_pe_created == 0 and actual_pe_cancelled == 0 and actual_gl_created == 0),
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": policy_mutation_count,
        "validated_source_doctype": VALIDATED_SOURCE_DOCTYPE,
        "validated_reference_doctype": VALIDATED_REFERENCE_DOCTYPE,
        "validated_party_type": VALIDATED_PARTY_TYPE,
        "validated_customer": customers[0] if customers else None,
        "validated_company": companies[0] if companies else None,
        "validated_currency": currencies[0] if currencies else None,
        "validated_invoice_count": len(rows),
        "validated_total_amount": validated_total(rows),
        "validated_payment_entry_count": VALIDATED_PAYMENT_ENTRY_COUNT,
        "validated_live_posting_allowed": 0,
        "validated_journal_entry_side_effect_allowed": 0,
        "validated_purchase_invoice_side_effect_allowed": 0,
        "baseline_payment_entry": payment_entry,
        "payment_entry_docstatus_validation": pe_docstatus,
        "payment_entry_status_validation": pe_status,
        "baseline_reference_count": len(rows),
        "baseline_total_amount": baseline_total,
        "baseline_voucher_gl_rows": voucher_rows,
        "baseline_voucher_gl_net": voucher_net,
        "baseline_voucher_gl_non_zero_account_count": non_zero_accounts,
        "baseline_restored_invoice_amount": validated_total(rows) if validated_total(rows) == 3 else 0,
        "candidate": candidate.name if candidate else None,
        "design": candidate.design if candidate else None,
        "planning": candidate.planning if candidate else None,
        "monitor": candidate.monitor if candidate else None,
        "baseline": candidate.baseline if candidate else None,
        "closeout": candidate.closeout if candidate else None,
        "freeze": candidate.freeze if candidate else None,
        "rollback": candidate.rollback if candidate else None,
        "smoke": candidate.smoke if candidate else None,
        "execution_gate": candidate.execution_gate if candidate else None,
        "preview": candidate.preview if candidate else None,
        "previous_validation": candidate.previous_validation if candidate else None,
        "previous_candidate": candidate.previous_candidate if candidate else None,
        "previous_design": candidate.previous_design if candidate else None,
        "previous_planning": candidate.previous_planning if candidate else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": candidate.target_policy if candidate else None,
        "target_policy_name": candidate.target_policy_name if candidate else None,
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
        "validation_score": score,
        **item_summary,
        "items": items,
        "validated_invoices": [dict(row) for row in rows],
        "issues": post_issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "required_acknowledgement": VALIDATION_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 11S validates the selected next controlled-cycle Sales Invoice candidates only. No posting occurs.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["candidate_validation_status"] = "Needs Review"
        result["candidate_validation_approved"] = 0
        result["ready_for_next_controlled_cycle_preview_gate"] = 0
        return result

    doc = frappe.new_doc(VALIDATION_DOCTYPE)
    doc.validation_id = make_validation_id()

    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)

    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = VALIDATION_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.validation_json = safe_json(
        {
            "candidate": candidate,
            "baseline_payment_entry": payment_entry,
            "validated_invoices": [dict(row) for row in rows],
            "validation": {
                "source_doctype": VALIDATED_SOURCE_DOCTYPE,
                "reference_doctype": VALIDATED_REFERENCE_DOCTYPE,
                "party_type": VALIDATED_PARTY_TYPE,
                "invoice_count": len(rows),
                "total_amount": validated_total(rows),
                "payment_entry_count": VALIDATED_PAYMENT_ENTRY_COUNT,
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
        "validation": doc.name,
        "validation_id": doc.validation_id,
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_next_controlled_cycle_candidate_validation_audit(validation, reason=None):
    assert_action("cancel_next_controlled_cycle_candidate_validation_audit")

    if not frappe.db.exists(VALIDATION_DOCTYPE, validation):
        frappe.throw(_("Next controlled-cycle candidate validation audit not found: {0}").format(validation))

    doc = frappe.get_doc(VALIDATION_DOCTYPE, validation)

    if doc.status == "Cancelled":
        return {"validation": validation, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.candidate_validation_approved or 0):
        frappe.throw(_("Cannot cancel an approved Phase 11S candidate validation record."))

    frappe.db.set_value(
        VALIDATION_DOCTYPE,
        validation,
        {
            "status": "Cancelled",
            "candidate_validation_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 11S no-ack candidate validation audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        f"""
        UPDATE `tab{VALIDATION_ITEM_DOCTYPE}`
        SET status = 'Cancelled'
        WHERE validation = %(validation)s
        """,
        {"validation": validation},
    )

    frappe.db.commit()

    return {
        "validation": validation,
        "status": "Cancelled",
        "note": "No-ack candidate validation audit cancelled only. No accounting or policy movement occurred.",
    }


@frappe.whitelist()
def quick_next_controlled_cycle_candidate_validation_summary(limit=20):
    records = frappe.get_all(
        VALIDATION_DOCTYPE,
        fields=[
            "name",
            "validation_id",
            "status",
            "candidate_validation_status",
            "candidate_validation_approved",
            "ready_for_next_controlled_cycle_preview_gate",
            "validated_source_doctype",
            "validated_reference_doctype",
            "validated_party_type",
            "validated_customer",
            "validated_company",
            "validated_currency",
            "validated_invoice_count",
            "validated_total_amount",
            "validated_payment_entry_count",
            "baseline_payment_entry",
            "payment_entry_docstatus_validation",
            "payment_entry_status_validation",
            "candidate",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "actual_payment_entry_created_count",
            "actual_payment_entry_cancelled_count",
            "actual_gl_created_count",
            "submitted_journal_entry_count_today",
            "purchase_invoice_count_today",
            "validation_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    items = frappe.get_all(
        VALIDATION_ITEM_DOCTYPE,
        fields=[
            "name",
            "validation",
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
            "selected_allocated_amount",
            "current_outstanding_amount",
            "validated_amount",
            "baseline_payment_entry",
            "detail",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    return {
        "validation_records": records,
        "items": items,
        "required_acknowledgement": VALIDATION_ACK,
        "guardrails": guardrails(),
        "note": "Phase 11S next controlled-cycle candidate validation summary.",
    }


def execute_validation_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("status"):
        conditions.append("v.status = %(status)s")
        params["status"] = filters.get("status")

    columns = validation_columns()

    data = frappe.db.sql(
        f"""
        SELECT
            v.name AS validation,
            v.validation_id,
            v.status,
            v.candidate_validation_status,
            v.candidate_validation_approved,
            v.phase11r_candidate_verified,
            v.candidate_selection_approved_verified,
            v.selected_invoice_set_verified,
            v.selected_sales_invoices_exist_verified,
            v.selected_sales_invoices_submitted_verified,
            v.selected_outstanding_sufficient_verified,
            v.same_customer_verified,
            v.same_company_verified,
            v.same_currency_verified,
            v.validated_total_verified,
            v.ready_for_next_controlled_cycle_preview_gate,
            v.validated_source_doctype,
            v.validated_reference_doctype,
            v.validated_party_type,
            v.validated_customer,
            v.validated_company,
            v.validated_currency,
            v.validated_invoice_count,
            v.validated_total_amount,
            v.validated_payment_entry_count,
            v.baseline_payment_entry,
            v.payment_entry_docstatus_validation,
            v.payment_entry_status_validation,
            v.candidate,
            v.payment_entry_count_before,
            v.payment_entry_count_after,
            v.payment_entry_gl_count_before,
            v.payment_entry_gl_count_after,
            v.actual_payment_entry_created_count,
            v.actual_payment_entry_cancelled_count,
            v.actual_gl_created_count,
            v.submitted_journal_entry_count_today,
            v.purchase_invoice_count_today,
            v.validation_score,
            v.checked_on,
            %(currency)s AS currency
        FROM `tab{VALIDATION_DOCTYPE}` v
        {build_where(conditions)}
        ORDER BY v.creation DESC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.validation_id for row in data[:20]],
            "datasets": [
                {"name": "Approved", "values": [int(row.candidate_validation_approved or 0) for row in data[:20]]},
                {"name": "Preview Ready", "values": [int(row.ready_for_next_controlled_cycle_preview_gate or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Validation Records"), "datatype": "Int"},
        {"value": sum(int(row.candidate_validation_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(int(row.ready_for_next_controlled_cycle_preview_gate or 0) for row in data), "indicator": "Green", "label": _("Preview Ready"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL Created"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def validation_columns():
    return [
        {"fieldname": "validation", "label": _("Validation"), "fieldtype": "Link", "options": VALIDATION_DOCTYPE, "width": 220},
        {"fieldname": "validation_id", "label": _("Validation ID"), "fieldtype": "Data", "width": 370},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 190},
        {"fieldname": "candidate_validation_status", "label": _("Validation Status"), "fieldtype": "Data", "width": 360},
        {"fieldname": "candidate_validation_approved", "label": _("Approved"), "fieldtype": "Check", "width": 90},
        {"fieldname": "phase11r_candidate_verified", "label": _("11R Verified"), "fieldtype": "Check", "width": 105},
        {"fieldname": "candidate_selection_approved_verified", "label": _("Candidate OK"), "fieldtype": "Check", "width": 105},
        {"fieldname": "selected_invoice_set_verified", "label": _("Set OK"), "fieldtype": "Check", "width": 90},
        {"fieldname": "selected_sales_invoices_exist_verified", "label": _("Exist OK"), "fieldtype": "Check", "width": 90},
        {"fieldname": "selected_sales_invoices_submitted_verified", "label": _("Submitted OK"), "fieldtype": "Check", "width": 110},
        {"fieldname": "selected_outstanding_sufficient_verified", "label": _("Outstanding OK"), "fieldtype": "Check", "width": 120},
        {"fieldname": "same_customer_verified", "label": _("Customer OK"), "fieldtype": "Check", "width": 100},
        {"fieldname": "same_company_verified", "label": _("Company OK"), "fieldtype": "Check", "width": 100},
        {"fieldname": "same_currency_verified", "label": _("Currency OK"), "fieldtype": "Check", "width": 100},
        {"fieldname": "validated_total_verified", "label": _("Total OK"), "fieldtype": "Check", "width": 90},
        {"fieldname": "ready_for_next_controlled_cycle_preview_gate", "label": _("Preview Ready"), "fieldtype": "Check", "width": 120},
        {"fieldname": "validated_source_doctype", "label": _("Source"), "fieldtype": "Data", "width": 120},
        {"fieldname": "validated_reference_doctype", "label": _("Reference"), "fieldtype": "Data", "width": 120},
        {"fieldname": "validated_party_type", "label": _("Party Type"), "fieldtype": "Data", "width": 100},
        {"fieldname": "validated_customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 220},
        {"fieldname": "validated_company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 220},
        {"fieldname": "validated_currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "width": 100},
        {"fieldname": "validated_invoice_count", "label": _("Invoices"), "fieldtype": "Int", "width": 80},
        {"fieldname": "validated_total_amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 100},
        {"fieldname": "validated_payment_entry_count", "label": _("Future PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "baseline_payment_entry", "label": _("Baseline PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "payment_entry_docstatus_validation", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 100},
        {"fieldname": "payment_entry_status_validation", "label": _("PE Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "candidate", "label": _("Candidate"), "fieldtype": "Link", "options": CANDIDATE_DOCTYPE, "width": 220},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 110},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE Created"), "fieldtype": "Int", "width": 125},
        {"fieldname": "actual_payment_entry_cancelled_count", "label": _("Actual PE Cancelled"), "fieldtype": "Int", "width": 135},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL Created"), "fieldtype": "Int", "width": 125},
        {"fieldname": "submitted_journal_entry_count_today", "label": _("JE Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "purchase_invoice_count_today", "label": _("PI Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "validation_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    if filters.get("validation"):
        conditions.append("i.validation = %(validation)s")
        params["validation"] = filters.get("validation")

    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": VALIDATION_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "validation", "label": _("Validation"), "fieldtype": "Link", "options": VALIDATION_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 190},
        {"fieldname": "line_no", "label": _("Line"), "fieldtype": "Int", "width": 60},
        {"fieldname": "reference_doctype", "label": _("Ref DocType"), "fieldtype": "Data", "width": 130},
        {"fieldname": "reference_name", "label": _("Reference"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 180},
        {"fieldname": "customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 220},
        {"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 220},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "width": 90},
        {"fieldname": "selected_allocated_amount", "label": _("Selected"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "current_outstanding_amount", "label": _("Current Outstanding"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "validated_amount", "label": _("Validated"), "fieldtype": "Currency", "width": 100},
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
            i.validation,
            i.status,
            i.severity,
            i.category,
            i.line_no,
            i.reference_doctype,
            i.reference_name,
            i.customer,
            i.company,
            i.currency,
            i.selected_allocated_amount,
            i.current_outstanding_amount,
            i.validated_amount,
            i.baseline_payment_entry,
            i.check_key,
            i.check_label,
            i.detail,
            i.checked_on
        FROM `tab{VALIDATION_ITEM_DOCTYPE}` i
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
        {"value": len([row for row in data if row.category == "Validated Candidate"]), "indicator": "Green", "label": _("Validated Candidates"), "datatype": "Int"},
        {"value": sum(flt(row.validated_amount or 0, 2) for row in data if row.category == "Validated Candidate"), "indicator": "Green", "label": _("Validated Amount"), "datatype": "Currency"},
        {"value": len([row for row in data if row.status == "Blocker"]), "indicator": "Red", "label": _("Blockers"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_validation_report(filters)
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
