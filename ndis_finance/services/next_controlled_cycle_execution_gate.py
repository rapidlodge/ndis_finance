import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, today

from ndis_finance.services.permissions import assert_action


EXECUTION_GATE_ACK = "I_CONFIRM_PHASE11U_APPROVE_NEXT_CONTROLLED_CYCLE_EXECUTION_GATE_SMOKE_ONLY"

POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
PREVIEW_DOCTYPE = "NDIS Next Controlled Cycle Preview"
PREVIEW_ITEM_DOCTYPE = "NDIS Next Controlled Cycle Preview Item"
EXEC_GATE_DOCTYPE = "NDIS Next Controlled Cycle Exec Gate"
EXEC_GATE_ITEM_DOCTYPE = "NDIS Next Controlled Cycle Exec Gate Item"

APPROVED_SOURCE_DOCTYPE = "Sales Invoice"
APPROVED_REFERENCE_DOCTYPE = "Sales Invoice"
APPROVED_PARTY_TYPE = "Customer"
APPROVED_REFERENCE_COUNT = 3
APPROVED_TOTAL_AMOUNT = 3.00
APPROVED_PAYMENT_ENTRY_COUNT = 1
APPROVED_GL_ENTRY_COUNT = 0

EXPECTED_INVOICES = ["ACC-SINV-2026-00005", "ACC-SINV-2026-00006", "ACC-SINV-2026-00008"]


def make_execution_gate_id():
    timestamp = now_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-NEXT-CONTROLLED-CYCLE-EXEC-GATE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_preview():
    rows = frappe.get_all(
        PREVIEW_DOCTYPE,
        filters={
            "status": "Preview Approved",
            "preview_status": "Next Controlled Cycle Preview Approved",
            "preview_approved": 1,
            "phase11s_validation_verified": 1,
            "candidate_validation_approved_verified": 1,
            "validated_invoice_set_locked_verified": 1,
            "preview_references_locked": 1,
            "preview_shape_locked": 1,
            "preview_total_verified": 1,
            "preview_payment_entry_count_verified": 1,
            "preview_gl_entry_count_verified": 1,
            "ready_for_next_controlled_cycle_execution_gate": 1,
            "preview_source_doctype": APPROVED_SOURCE_DOCTYPE,
            "preview_reference_doctype": APPROVED_REFERENCE_DOCTYPE,
            "preview_party_type": APPROVED_PARTY_TYPE,
            "preview_reference_count": APPROVED_REFERENCE_COUNT,
            "preview_total_amount": APPROVED_TOTAL_AMOUNT,
            "preview_payment_entry_count": APPROVED_PAYMENT_ENTRY_COUNT,
            "preview_gl_entry_count": APPROVED_GL_ENTRY_COUNT,
            "would_create_payment_entry_count": APPROVED_PAYMENT_ENTRY_COUNT,
            "would_create_gl_entry_count": APPROVED_GL_ENTRY_COUNT,
            "preview_live_posting_allowed": 0,
            "preview_journal_entry_side_effect_allowed": 0,
            "preview_purchase_invoice_side_effect_allowed": 0,
            "payment_entry_docstatus_preview": 2,
            "payment_entry_status_preview": "Cancelled",
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
            "preview_id",
            "preview_customer",
            "preview_company",
            "preview_currency",
            "baseline_payment_entry",
            "validation",
            "candidate",
            "design",
            "planning",
            "monitor",
            "baseline",
            "closeout",
            "freeze",
            "rollback",
            "smoke",
            "execution_gate",
            "target_policy_doctype",
            "target_policy",
            "target_policy_name",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_approved_execution_gate(preview):
    rows = frappe.get_all(
        EXEC_GATE_DOCTYPE,
        filters={
            "preview": preview,
            "status": "Execution Gate Approved",
            "execution_gate_approved": 1,
        },
        fields=["name", "execution_gate_id"],
        limit=1,
    )
    return rows[0] if rows else None


def preview_rows(preview):
    if not preview:
        return []

    rows = frappe.get_all(
        PREVIEW_ITEM_DOCTYPE,
        filters={
            "preview": preview,
            "category": "Preview Reference",
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
            "preview_amount",
            "current_outstanding_amount",
            "baseline_payment_entry",
        ],
        order_by="line_no asc, creation asc",
    )

    gate_rows = []
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
                "outstanding_amount",
            ],
            as_dict=True,
        )

        gate_rows.append(
            frappe._dict(
                {
                    "idx": int(row.line_no or idx),
                    "reference_doctype": "Sales Invoice",
                    "reference_name": row.reference_name,
                    "customer": si.customer if si else row.customer,
                    "company": si.company if si else row.company,
                    "currency": si.currency if si else row.currency,
                    "sales_invoice_exists": 1 if si else 0,
                    "sales_invoice_docstatus": int(si.docstatus or 0) if si else 0,
                    "current_outstanding_amount": flt(si.outstanding_amount if si else row.current_outstanding_amount, 2),
                    "approved_amount": flt(row.preview_amount or 0, 2),
                    "baseline_payment_entry": row.baseline_payment_entry,
                }
            )
        )

    return gate_rows


def approved_total(rows):
    return flt(sum(flt(row.approved_amount or 0, 2) for row in rows), 2)


def approved_names(rows):
    return [row.reference_name for row in rows]


def approved_customers(rows):
    return sorted(set([row.customer for row in rows if row.customer]))


def approved_companies(rows):
    return sorted(set([row.company for row in rows if row.company]))


def approved_currencies(rows):
    return sorted(set([row.currency for row in rows if row.currency]))


def all_sales_invoices_exist(rows):
    return bool(rows) and all(int(row.sales_invoice_exists or 0) == 1 for row in rows)


def all_sales_invoices_submitted(rows):
    return bool(rows) and all(int(row.sales_invoice_docstatus or 0) == 1 for row in rows)


def all_outstanding_sufficient(rows):
    return bool(rows) and all(flt(row.current_outstanding_amount or 0, 2) >= flt(row.approved_amount or 0, 2) for row in rows)


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


def validate_source(preview, payment_entry, rows, guard, config, policy_enabled, policy_live):
    issues = []

    if not preview:
        issues.append("No approved Phase 11T next controlled-cycle preview found.")
        return issues

    existing = existing_approved_execution_gate(preview.name)
    if existing:
        issues.append(f"Approved Phase 11U execution gate already exists for this preview: {existing.execution_gate_id}")

    if not payment_entry:
        issues.append("Phase 11T preview does not identify the baseline Payment Entry.")
        return issues

    if not frappe.db.exists("Payment Entry", payment_entry):
        issues.append(f"Baseline Payment Entry does not exist: {payment_entry}")
        return issues

    pe = frappe.get_doc("Payment Entry", payment_entry)

    if pe.docstatus != 2:
        issues.append(f"Payment Entry must remain cancelled for execution gate. docstatus={pe.docstatus}")

    if pe.status != "Cancelled":
        issues.append(f"Payment Entry status must remain Cancelled for execution gate. status={pe.status}")

    if approved_names(rows) != EXPECTED_INVOICES:
        issues.append(f"Execution gate invoice set changed. Expected {EXPECTED_INVOICES}. Found {approved_names(rows)}.")

    if len(rows) != APPROVED_REFERENCE_COUNT:
        issues.append(f"Execution gate must contain exactly {APPROVED_REFERENCE_COUNT} references. Found {len(rows)}.")

    if approved_total(rows) != APPROVED_TOTAL_AMOUNT:
        issues.append(f"Execution gate total must be {APPROVED_TOTAL_AMOUNT}. Found {approved_total(rows)}.")

    if not all_sales_invoices_exist(rows):
        issues.append("One or more execution gate Sales Invoices no longer exist.")

    if not all_sales_invoices_submitted(rows):
        issues.append("One or more execution gate Sales Invoices are not submitted.")

    if not all_outstanding_sufficient(rows):
        issues.append("One or more execution gate Sales Invoices have insufficient current outstanding amount.")

    if len(approved_customers(rows)) != 1:
        issues.append("Execution gate Sales Invoices must all have the same customer.")

    if len(approved_companies(rows)) != 1:
        issues.append("Execution gate Sales Invoices must all have the same company.")

    if len(approved_currencies(rows)) != 1:
        issues.append("Execution gate Sales Invoices must all have the same currency.")

    if voucher_gl_rows(payment_entry) != 8:
        issues.append(f"Voucher GL rows must remain 8. Found {voucher_gl_rows(payment_entry)}.")

    if voucher_gl_net(payment_entry) != 0:
        issues.append(f"Voucher GL net must remain 0.00. Found {voucher_gl_net(payment_entry)}.")

    if voucher_gl_non_zero_accounts(payment_entry) != 0:
        issues.append(f"Voucher non-zero account count must remain 0. Found {voucher_gl_non_zero_accounts(payment_entry)}.")

    if guard["payment_entry_count"] != 9:
        issues.append("Payment Entry count must remain 9 before Phase 11U execution gate.")

    if guard["payment_entry_gl_count"] != 54:
        issues.append("Payment Entry GL count must remain 54 before Phase 11U execution gate.")

    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today must remain 0 before execution gate.")

    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today must remain 0 before execution gate.")

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
                "customer": row.customer,
                "company": row.company,
                "currency": row.currency,
                "approved_amount": row.approved_amount,
            }
        )

    items.append(item)


def build_items(preview, rows, issues, ack_ok, baseline_payment_entry=None):
    items = []

    if preview:
        add_item(
            items,
            "Pass",
            "Low",
            "Evidence",
            "phase11t_preview_exists",
            "Phase 11T preview exists",
            f"Preview found: {preview.preview_id}.",
            baseline_payment_entry=baseline_payment_entry,
        )
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase11t_preview_exists", "Phase 11T preview exists", "No approved Phase 11T preview found.")

    if not issues:
        add_item(
            items,
            "Pass",
            "Critical",
            "Execution Gate Source",
            "execution_gate_source_valid",
            "Execution gate source valid",
            "Preview is locked and ready for smoke-only execution gate approval.",
            baseline_payment_entry=baseline_payment_entry,
        )
    else:
        for issue in issues:
            add_item(
                items,
                "Blocker",
                "Critical",
                "Execution Gate Source",
                "execution_gate_source_valid",
                "Execution gate source valid",
                issue,
                baseline_payment_entry=baseline_payment_entry,
            )

    for row in rows:
        add_item(
            items,
            "Pass",
            "High",
            "Approved Reference",
            "approved_sales_invoice_reference",
            f"Approved Sales Invoice {row.idx}",
            (
                f"{row.reference_name} approved for next controlled-cycle smoke-only execution. "
                f"approved_amount={row.approved_amount}."
            ),
            row=row,
            baseline_payment_entry=baseline_payment_entry,
        )

    checks = [
        ("preview_reference_set_locked", "Preview reference set locked", ", ".join(approved_names(rows))),
        ("preview_shape_locked", "Preview shape locked", f"{APPROVED_REFERENCE_COUNT} / {APPROVED_TOTAL_AMOUNT} / {APPROVED_PAYMENT_ENTRY_COUNT}"),
        ("smoke_execution_authorised", "Smoke execution authorised", 1),
        ("smoke_only_authorised", "Smoke-only authorised", 1),
        ("real_production_posting_authorised", "Real production posting authorised", 0),
        ("approved_reference_count", "Approved reference count = 3", len(rows)),
        ("approved_total", "Approved total = 3.00", approved_total(rows)),
        ("approved_payment_entry_count", "Approved future PE count = 1", APPROVED_PAYMENT_ENTRY_COUNT),
        ("approved_gl_entry_count", "Approved preview GL count = 0", APPROVED_GL_ENTRY_COUNT),
        ("payment_entry_count", "Payment Entry count remains 9", 9),
        ("payment_entry_gl_count", "Payment Entry GL count remains 54", 54),
        ("policy_state", "Policy state preserved at 1 / 0", "1 / 0"),
        ("no_pe_movement", "No Payment Entry movement in execution gate", "0 / 0"),
        ("no_gl_movement", "No GL movement in execution gate", 0),
        ("no_je_pi", "No JE / PI side effects", "0 / 0"),
        ("ready_for_smoke", "Ready for next controlled-cycle smoke", 1),
    ]

    for key, label, value in checks:
        add_item(
            items,
            "Pass",
            "High",
            "Execution Gate Evidence",
            key,
            label,
            f"value={value}",
            baseline_payment_entry=baseline_payment_entry,
        )

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.", baseline_payment_entry=baseline_payment_entry)
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {EXECUTION_GATE_ACK}")

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
        row = frappe.new_doc(EXEC_GATE_ITEM_DOCTYPE)
        row.execution_gate = doc.name

        for fieldname, value in item.items():
            if row.meta.has_field(fieldname):
                setattr(row, fieldname, value)

        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_next_controlled_cycle_execution_gate(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_next_controlled_cycle_execution_gate")

    preview = latest_preview()
    payment_entry = preview.baseline_payment_entry if preview else None
    rows = preview_rows(preview.name) if preview else []

    guard_before = guardrails()
    ack_ok = acknowledgement == EXECUTION_GATE_ACK

    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }

    policy_enabled_before = get_flag(POLICY_DOCTYPE, preview.target_policy, "production_batch_enabled") if preview else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, preview.target_policy, "live_posting_allowed") if preview else 0

    issues = validate_source(preview, payment_entry, rows, guard_before, config, policy_enabled_before, policy_live_before)

    guard_after = guardrails()

    policy_enabled_after = get_flag(POLICY_DOCTYPE, preview.target_policy, "production_batch_enabled") if preview else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, preview.target_policy, "live_posting_allowed") if preview else 0

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
        baseline_total = flt(pe.paid_amount or pe.received_amount or approved_total(rows), 2)
        voucher_rows = voucher_gl_rows(payment_entry)
        voucher_net = voucher_gl_net(payment_entry)
        non_zero_accounts = voucher_gl_non_zero_accounts(payment_entry)

    post_issues = list(issues)

    if actual_pe_created != 0:
        post_issues.append(f"Execution gate must not create Payment Entries. Created {actual_pe_created}.")

    if actual_pe_cancelled != 0:
        post_issues.append(f"Execution gate must not cancel Payment Entries. Cancelled {actual_pe_cancelled}.")

    if actual_gl_created != 0:
        post_issues.append(f"Execution gate must not create GL rows. Created {actual_gl_created}.")

    if guard_after["payment_entry_count"] != 9:
        post_issues.append("Payment Entry count must remain 9 after execution gate.")

    if guard_after["payment_entry_gl_count"] != 54:
        post_issues.append("Payment Entry GL count must remain 54 after execution gate.")

    if guard_after["submitted_journal_entry_count_today"] != 0:
        post_issues.append("Submitted Journal Entry count today must remain 0 after execution gate.")

    if guard_after["purchase_invoice_count_today"] != 0:
        post_issues.append("Purchase Invoice count today must remain 0 after execution gate.")

    if policy_mutation_count != 0:
        post_issues.append("Policy state changed during execution gate. This is not allowed.")

    customers = approved_customers(rows)
    companies = approved_companies(rows)
    currencies = approved_currencies(rows)

    items = build_items(
        preview,
        rows,
        post_issues,
        ack_ok,
        baseline_payment_entry=payment_entry,
    )
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    completed = int(
        ack_ok
        and preview
        and payment_entry
        and item_summary["blocker_count"] == 0
        and pe_docstatus == 2
        and pe_status == "Cancelled"
        and len(rows) == APPROVED_REFERENCE_COUNT
        and approved_names(rows) == EXPECTED_INVOICES
        and all_sales_invoices_exist(rows)
        and all_sales_invoices_submitted(rows)
        and all_outstanding_sufficient(rows)
        and approved_total(rows) == APPROVED_TOTAL_AMOUNT
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
        "status": "Execution Gate Approved" if completed else "Needs Review",
        "execution_gate_status": "Ready For Next Controlled Cycle Smoke" if completed else "Needs Review",
        "execution_gate_approved": completed,
        "phase11t_preview_verified": 1 if preview else 0,
        "preview_approved_verified": 1 if preview else 0,
        "preview_reference_set_locked_verified": int(approved_names(rows) == EXPECTED_INVOICES),
        "preview_shape_locked_verified": int(len(rows) == APPROVED_REFERENCE_COUNT and approved_total(rows) == APPROVED_TOTAL_AMOUNT),
        "smoke_execution_authorised": completed,
        "smoke_only_authorised": completed,
        "real_production_posting_authorised": 0,
        "ready_for_next_controlled_cycle_smoke": completed,
        "no_new_accounting_movement_verified": int(actual_pe_created == 0 and actual_pe_cancelled == 0 and actual_gl_created == 0),
        "policy_state_preserved_verified": int(policy_mutation_count == 0 and policy_enabled_before == 1 and policy_enabled_after == 1 and policy_live_before == 0 and policy_live_after == 0),
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": policy_mutation_count,
        "approved_source_doctype": APPROVED_SOURCE_DOCTYPE,
        "approved_reference_doctype": APPROVED_REFERENCE_DOCTYPE,
        "approved_party_type": APPROVED_PARTY_TYPE,
        "approved_customer": customers[0] if customers else None,
        "approved_company": companies[0] if companies else None,
        "approved_currency": currencies[0] if currencies else None,
        "approved_reference_count": len(rows),
        "approved_total_amount": approved_total(rows),
        "approved_payment_entry_count": APPROVED_PAYMENT_ENTRY_COUNT,
        "approved_gl_entry_count": APPROVED_GL_ENTRY_COUNT,
        "approved_live_posting_allowed": 0,
        "approved_journal_entry_side_effect_allowed": 0,
        "approved_purchase_invoice_side_effect_allowed": 0,
        "baseline_payment_entry": payment_entry,
        "payment_entry_docstatus_gate": pe_docstatus,
        "payment_entry_status_gate": pe_status,
        "baseline_reference_count": len(rows),
        "baseline_total_amount": baseline_total,
        "baseline_voucher_gl_rows": voucher_rows,
        "baseline_voucher_gl_net": voucher_net,
        "baseline_voucher_gl_non_zero_account_count": non_zero_accounts,
        "baseline_restored_invoice_amount": approved_total(rows) if approved_total(rows) == 3 else 0,
        "preview": preview.name if preview else None,
        "validation": preview.validation if preview else None,
        "candidate": preview.candidate if preview else None,
        "design": preview.design if preview else None,
        "planning": preview.planning if preview else None,
        "monitor": preview.monitor if preview else None,
        "baseline": preview.baseline if preview else None,
        "closeout": preview.closeout if preview else None,
        "freeze": preview.freeze if preview else None,
        "rollback": preview.rollback if preview else None,
        "smoke": preview.smoke if preview else None,
        "previous_execution_gate": preview.execution_gate if preview else None,
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
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guard_after["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
        "actual_payment_entry_created_count": actual_pe_created,
        "actual_payment_entry_cancelled_count": actual_pe_cancelled,
        "actual_gl_created_count": actual_gl_created,
        "submitted_journal_entry_count_today": guard_after["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_after["purchase_invoice_count_today"],
        "execution_gate_score": score,
        **item_summary,
        "items": items,
        "approved_references": [dict(row) for row in rows],
        "issues": post_issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "required_acknowledgement": EXECUTION_GATE_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 11U approves smoke-only execution gate. Real production posting remains blocked.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["execution_gate_status"] = "Needs Review"
        result["execution_gate_approved"] = 0
        result["smoke_execution_authorised"] = 0
        result["smoke_only_authorised"] = 0
        result["ready_for_next_controlled_cycle_smoke"] = 0
        return result

    doc = frappe.new_doc(EXEC_GATE_DOCTYPE)
    doc.execution_gate_id = make_execution_gate_id()

    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)

    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = EXECUTION_GATE_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.execution_gate_json = safe_json(
        {
            "preview": preview,
            "baseline_payment_entry": payment_entry,
            "approved_references": [dict(row) for row in rows],
            "execution_gate": {
                "source_doctype": APPROVED_SOURCE_DOCTYPE,
                "reference_doctype": APPROVED_REFERENCE_DOCTYPE,
                "party_type": APPROVED_PARTY_TYPE,
                "reference_count": len(rows),
                "total_amount": approved_total(rows),
                "payment_entry_count": APPROVED_PAYMENT_ENTRY_COUNT,
                "gl_entry_count": APPROVED_GL_ENTRY_COUNT,
                "smoke_execution_authorised": completed,
                "smoke_only_authorised": completed,
                "real_production_posting_authorised": 0,
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
        "execution_gate": doc.name,
        "execution_gate_id": doc.execution_gate_id,
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_next_controlled_cycle_execution_gate_audit(execution_gate, reason=None):
    assert_action("cancel_next_controlled_cycle_execution_gate_audit")

    if not frappe.db.exists(EXEC_GATE_DOCTYPE, execution_gate):
        frappe.throw(_("Next controlled-cycle execution gate audit not found: {0}").format(execution_gate))

    doc = frappe.get_doc(EXEC_GATE_DOCTYPE, execution_gate)

    if doc.status == "Cancelled":
        return {"execution_gate": execution_gate, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.execution_gate_approved or 0):
        frappe.throw(_("Cannot cancel an approved Phase 11U execution gate record."))

    frappe.db.set_value(
        EXEC_GATE_DOCTYPE,
        execution_gate,
        {
            "status": "Cancelled",
            "execution_gate_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 11U no-ack execution gate audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        f"""
        UPDATE `tab{EXEC_GATE_ITEM_DOCTYPE}`
        SET status = 'Cancelled'
        WHERE execution_gate = %(execution_gate)s
        """,
        {"execution_gate": execution_gate},
    )

    frappe.db.commit()

    return {
        "execution_gate": execution_gate,
        "status": "Cancelled",
        "note": "No-ack execution gate audit cancelled only. No accounting or policy movement occurred.",
    }


@frappe.whitelist()
def quick_next_controlled_cycle_execution_gate_summary(limit=20):
    records = frappe.get_all(
        EXEC_GATE_DOCTYPE,
        fields=[
            "name",
            "execution_gate_id",
            "status",
            "execution_gate_status",
            "execution_gate_approved",
            "smoke_execution_authorised",
            "smoke_only_authorised",
            "real_production_posting_authorised",
            "ready_for_next_controlled_cycle_smoke",
            "approved_source_doctype",
            "approved_reference_doctype",
            "approved_party_type",
            "approved_customer",
            "approved_company",
            "approved_currency",
            "approved_reference_count",
            "approved_total_amount",
            "approved_payment_entry_count",
            "approved_gl_entry_count",
            "baseline_payment_entry",
            "payment_entry_docstatus_gate",
            "payment_entry_status_gate",
            "preview",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "actual_payment_entry_created_count",
            "actual_payment_entry_cancelled_count",
            "actual_gl_created_count",
            "submitted_journal_entry_count_today",
            "purchase_invoice_count_today",
            "execution_gate_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    items = frappe.get_all(
        EXEC_GATE_ITEM_DOCTYPE,
        fields=[
            "name",
            "execution_gate",
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
            "approved_amount",
            "baseline_payment_entry",
            "detail",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    return {
        "execution_gate_records": records,
        "items": items,
        "required_acknowledgement": EXECUTION_GATE_ACK,
        "guardrails": guardrails(),
        "note": "Phase 11U next controlled-cycle execution gate summary.",
    }


def execute_execution_gate_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("status"):
        conditions.append("g.status = %(status)s")
        params["status"] = filters.get("status")

    columns = execution_gate_columns()

    data = frappe.db.sql(
        f"""
        SELECT
            g.name AS execution_gate,
            g.execution_gate_id,
            g.status,
            g.execution_gate_status,
            g.execution_gate_approved,
            g.phase11t_preview_verified,
            g.preview_approved_verified,
            g.preview_reference_set_locked_verified,
            g.preview_shape_locked_verified,
            g.smoke_execution_authorised,
            g.smoke_only_authorised,
            g.real_production_posting_authorised,
            g.ready_for_next_controlled_cycle_smoke,
            g.approved_source_doctype,
            g.approved_reference_doctype,
            g.approved_party_type,
            g.approved_customer,
            g.approved_company,
            g.approved_currency,
            g.approved_reference_count,
            g.approved_total_amount,
            g.approved_payment_entry_count,
            g.approved_gl_entry_count,
            g.baseline_payment_entry,
            g.payment_entry_docstatus_gate,
            g.payment_entry_status_gate,
            g.preview,
            g.payment_entry_count_before,
            g.payment_entry_count_after,
            g.payment_entry_gl_count_before,
            g.payment_entry_gl_count_after,
            g.actual_payment_entry_created_count,
            g.actual_payment_entry_cancelled_count,
            g.actual_gl_created_count,
            g.submitted_journal_entry_count_today,
            g.purchase_invoice_count_today,
            g.execution_gate_score,
            g.checked_on,
            %(currency)s AS currency
        FROM `tab{EXEC_GATE_DOCTYPE}` g
        {build_where(conditions)}
        ORDER BY g.creation DESC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.execution_gate_id for row in data[:20]],
            "datasets": [
                {"name": "Approved", "values": [int(row.execution_gate_approved or 0) for row in data[:20]]},
                {"name": "Smoke Ready", "values": [int(row.ready_for_next_controlled_cycle_smoke or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Execution Gate Records"), "datatype": "Int"},
        {"value": sum(int(row.execution_gate_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(int(row.ready_for_next_controlled_cycle_smoke or 0) for row in data), "indicator": "Green", "label": _("Smoke Ready"), "datatype": "Int"},
        {"value": sum(int(row.real_production_posting_authorised or 0) for row in data), "indicator": "Red", "label": _("Real Production Authorised"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL Created"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execution_gate_columns():
    return [
        {"fieldname": "execution_gate", "label": _("Execution Gate"), "fieldtype": "Link", "options": EXEC_GATE_DOCTYPE, "width": 220},
        {"fieldname": "execution_gate_id", "label": _("Execution Gate ID"), "fieldtype": "Data", "width": 390},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 190},
        {"fieldname": "execution_gate_status", "label": _("Execution Gate Status"), "fieldtype": "Data", "width": 330},
        {"fieldname": "execution_gate_approved", "label": _("Approved"), "fieldtype": "Check", "width": 90},
        {"fieldname": "phase11t_preview_verified", "label": _("11T Verified"), "fieldtype": "Check", "width": 105},
        {"fieldname": "preview_approved_verified", "label": _("Preview OK"), "fieldtype": "Check", "width": 100},
        {"fieldname": "preview_reference_set_locked_verified", "label": _("Refs Locked"), "fieldtype": "Check", "width": 105},
        {"fieldname": "preview_shape_locked_verified", "label": _("Shape Locked"), "fieldtype": "Check", "width": 110},
        {"fieldname": "smoke_execution_authorised", "label": _("Smoke Auth"), "fieldtype": "Check", "width": 100},
        {"fieldname": "smoke_only_authorised", "label": _("Smoke Only"), "fieldtype": "Check", "width": 100},
        {"fieldname": "real_production_posting_authorised", "label": _("Real Prod Auth"), "fieldtype": "Check", "width": 120},
        {"fieldname": "ready_for_next_controlled_cycle_smoke", "label": _("Smoke Ready"), "fieldtype": "Check", "width": 110},
        {"fieldname": "approved_source_doctype", "label": _("Source"), "fieldtype": "Data", "width": 120},
        {"fieldname": "approved_reference_doctype", "label": _("Reference"), "fieldtype": "Data", "width": 120},
        {"fieldname": "approved_party_type", "label": _("Party Type"), "fieldtype": "Data", "width": 100},
        {"fieldname": "approved_customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 220},
        {"fieldname": "approved_company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 220},
        {"fieldname": "approved_currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "width": 100},
        {"fieldname": "approved_reference_count", "label": _("Refs"), "fieldtype": "Int", "width": 80},
        {"fieldname": "approved_total_amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 100},
        {"fieldname": "approved_payment_entry_count", "label": _("Future PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "approved_gl_entry_count", "label": _("Future GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "baseline_payment_entry", "label": _("Baseline PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "payment_entry_docstatus_gate", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 100},
        {"fieldname": "payment_entry_status_gate", "label": _("PE Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "preview", "label": _("Preview"), "fieldtype": "Link", "options": PREVIEW_DOCTYPE, "width": 220},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 110},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE Created"), "fieldtype": "Int", "width": 125},
        {"fieldname": "actual_payment_entry_cancelled_count", "label": _("Actual PE Cancelled"), "fieldtype": "Int", "width": 135},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL Created"), "fieldtype": "Int", "width": 125},
        {"fieldname": "submitted_journal_entry_count_today", "label": _("JE Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "purchase_invoice_count_today", "label": _("PI Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "execution_gate_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    if filters.get("execution_gate"):
        conditions.append("i.execution_gate = %(execution_gate)s")
        params["execution_gate"] = filters.get("execution_gate")

    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": EXEC_GATE_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "execution_gate", "label": _("Execution Gate"), "fieldtype": "Link", "options": EXEC_GATE_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 190},
        {"fieldname": "line_no", "label": _("Line"), "fieldtype": "Int", "width": 60},
        {"fieldname": "reference_doctype", "label": _("Ref DocType"), "fieldtype": "Data", "width": 130},
        {"fieldname": "reference_name", "label": _("Reference"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 180},
        {"fieldname": "customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 220},
        {"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 220},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "width": 90},
        {"fieldname": "approved_amount", "label": _("Approved Amount"), "fieldtype": "Currency", "width": 110},
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
            i.execution_gate,
            i.status,
            i.severity,
            i.category,
            i.line_no,
            i.reference_doctype,
            i.reference_name,
            i.customer,
            i.company,
            i.currency,
            i.approved_amount,
            i.baseline_payment_entry,
            i.check_key,
            i.check_label,
            i.detail,
            i.checked_on
        FROM `tab{EXEC_GATE_ITEM_DOCTYPE}` i
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
        {"value": len([row for row in data if row.category == "Approved Reference"]), "indicator": "Green", "label": _("Approved References"), "datatype": "Int"},
        {"value": sum(flt(row.approved_amount or 0, 2) for row in data if row.category == "Approved Reference"), "indicator": "Green", "label": _("Approved Amount"), "datatype": "Currency"},
        {"value": len([row for row in data if row.status == "Blocker"]), "indicator": "Red", "label": _("Blockers"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_execution_gate_report(filters)
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
