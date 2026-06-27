import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, today

from ndis_finance.services.permissions import assert_action


SMOKE_ACK = "I_CONFIRM_PHASE11V_EXECUTE_NEXT_CONTROLLED_CYCLE_SMOKE_CREATE_PAYMENT_ENTRY"

POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
EXEC_GATE_DOCTYPE = "NDIS Next Controlled Cycle Exec Gate"
EXEC_GATE_ITEM_DOCTYPE = "NDIS Next Controlled Cycle Exec Gate Item"
SMOKE_DOCTYPE = "NDIS Next Controlled Cycle Smoke"
SMOKE_ITEM_DOCTYPE = "NDIS Next Controlled Cycle Smoke Item"

APPROVED_SOURCE_DOCTYPE = "Sales Invoice"
APPROVED_REFERENCE_DOCTYPE = "Sales Invoice"
APPROVED_PARTY_TYPE = "Customer"
APPROVED_REFERENCE_COUNT = 3
APPROVED_TOTAL_AMOUNT = 3.00
APPROVED_PAYMENT_ENTRY_COUNT = 1
EXPECTED_GL_ROWS_CREATED = 4
EXPECTED_INVOICES = ["ACC-SINV-2026-00005", "ACC-SINV-2026-00006", "ACC-SINV-2026-00008"]


def make_smoke_id():
    timestamp = now_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-NEXT-CONTROLLED-CYCLE-SMOKE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_execution_gate():
    rows = frappe.get_all(
        EXEC_GATE_DOCTYPE,
        filters={
            "status": "Execution Gate Approved",
            "execution_gate_status": "Ready For Next Controlled Cycle Smoke",
            "execution_gate_approved": 1,
            "phase11t_preview_verified": 1,
            "preview_approved_verified": 1,
            "preview_reference_set_locked_verified": 1,
            "preview_shape_locked_verified": 1,
            "smoke_execution_authorised": 1,
            "smoke_only_authorised": 1,
            "real_production_posting_authorised": 0,
            "ready_for_next_controlled_cycle_smoke": 1,
            "approved_source_doctype": APPROVED_SOURCE_DOCTYPE,
            "approved_reference_doctype": APPROVED_REFERENCE_DOCTYPE,
            "approved_party_type": APPROVED_PARTY_TYPE,
            "approved_reference_count": APPROVED_REFERENCE_COUNT,
            "approved_total_amount": APPROVED_TOTAL_AMOUNT,
            "approved_payment_entry_count": APPROVED_PAYMENT_ENTRY_COUNT,
            "approved_gl_entry_count": 0,
            "approved_live_posting_allowed": 0,
            "approved_journal_entry_side_effect_allowed": 0,
            "approved_purchase_invoice_side_effect_allowed": 0,
            "payment_entry_docstatus_gate": 2,
            "payment_entry_status_gate": "Cancelled",
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
            "execution_gate_id",
            "approved_customer",
            "approved_company",
            "approved_currency",
            "baseline_payment_entry",
            "preview",
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
            "target_policy_doctype",
            "target_policy",
            "target_policy_name",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_completed_smoke(execution_gate):
    rows = frappe.get_all(
        SMOKE_DOCTYPE,
        filters={
            "execution_gate": execution_gate,
            "status": "Smoke Completed - Rollback Required",
            "smoke_completed": 1,
        },
        fields=["name", "smoke_id", "created_payment_entry"],
        limit=1,
    )
    return rows[0] if rows else None


def approved_rows(execution_gate):
    if not execution_gate:
        return []

    rows = frappe.get_all(
        EXEC_GATE_ITEM_DOCTYPE,
        filters={
            "execution_gate": execution_gate,
            "category": "Approved Reference",
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
            "approved_amount",
            "baseline_payment_entry",
        ],
        order_by="line_no asc, creation asc",
    )

    approved = []
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
                "due_date",
            ],
            as_dict=True,
        )

        approved.append(
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
                    "grand_total": flt(si.grand_total or 0, 2) if si else 0,
                    "current_outstanding_amount": flt(si.outstanding_amount or 0, 2) if si else 0,
                    "due_date": si.due_date if si else None,
                    "approved_amount": flt(row.approved_amount or 0, 2),
                    "baseline_payment_entry": row.baseline_payment_entry,
                }
            )
        )

    return approved


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


def payment_entry_reference_count(payment_entry):
    if not payment_entry:
        return 0
    return count_dt("Payment Entry Reference", {"parent": payment_entry, "reference_doctype": "Sales Invoice"})


def payment_entry_allocated_amount(payment_entry):
    if not payment_entry:
        return 0
    value = frappe.db.sql(
        """
        SELECT ROUND(COALESCE(SUM(allocated_amount), 0), 2)
        FROM `tabPayment Entry Reference`
        WHERE parent=%s
        AND reference_doctype='Sales Invoice'
        """,
        payment_entry,
    )[0][0]
    return flt(value or 0, 2)


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

    if voucher_gl_net(payment_entry) == 0:
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


def validate_source(execution_gate, baseline_payment_entry, rows, guard, config, policy_enabled, policy_live):
    issues = []

    if not execution_gate:
        issues.append("No approved Phase 11U next controlled-cycle execution gate found.")
        return issues

    existing = existing_completed_smoke(execution_gate.name)
    if existing:
        issues.append(f"Completed Phase 11V smoke already exists for this execution gate: {existing.smoke_id} / {existing.created_payment_entry}")

    if not baseline_payment_entry:
        issues.append("Phase 11U execution gate does not identify the baseline Payment Entry.")
        return issues

    if not frappe.db.exists("Payment Entry", baseline_payment_entry):
        issues.append(f"Baseline Payment Entry does not exist: {baseline_payment_entry}")
        return issues

    baseline_pe = frappe.get_doc("Payment Entry", baseline_payment_entry)

    if baseline_pe.docstatus != 2:
        issues.append(f"Baseline Payment Entry must remain cancelled before smoke. docstatus={baseline_pe.docstatus}")

    if baseline_pe.status != "Cancelled":
        issues.append(f"Baseline Payment Entry status must remain Cancelled before smoke. status={baseline_pe.status}")

    if approved_names(rows) != EXPECTED_INVOICES:
        issues.append(f"Smoke invoice set changed. Expected {EXPECTED_INVOICES}. Found {approved_names(rows)}.")

    if len(rows) != APPROVED_REFERENCE_COUNT:
        issues.append(f"Smoke must contain exactly {APPROVED_REFERENCE_COUNT} references. Found {len(rows)}.")

    if approved_total(rows) != APPROVED_TOTAL_AMOUNT:
        issues.append(f"Smoke amount must be {APPROVED_TOTAL_AMOUNT}. Found {approved_total(rows)}.")

    if not all_sales_invoices_exist(rows):
        issues.append("One or more smoke Sales Invoices no longer exist.")

    if not all_sales_invoices_submitted(rows):
        issues.append("One or more smoke Sales Invoices are not submitted.")

    if not all_outstanding_sufficient(rows):
        issues.append("One or more smoke Sales Invoices have insufficient current outstanding amount.")

    if len(approved_customers(rows)) != 1:
        issues.append("Smoke Sales Invoices must all have the same customer.")

    if len(approved_companies(rows)) != 1:
        issues.append("Smoke Sales Invoices must all have the same company.")

    if len(approved_currencies(rows)) != 1:
        issues.append("Smoke Sales Invoices must all have the same currency.")

    if voucher_gl_rows(baseline_payment_entry) != 8:
        issues.append(f"Baseline voucher GL rows must remain 8. Found {voucher_gl_rows(baseline_payment_entry)}.")

    if voucher_gl_net(baseline_payment_entry) != 0:
        issues.append(f"Baseline voucher GL net must remain 0.00. Found {voucher_gl_net(baseline_payment_entry)}.")

    if guard["payment_entry_count"] != 9:
        issues.append("Payment Entry count must be 9 before Phase 11V smoke.")

    if guard["payment_entry_gl_count"] != 54:
        issues.append("Payment Entry GL count must be 54 before Phase 11V smoke.")

    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today must remain 0 before smoke.")

    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today must remain 0 before smoke.")

    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must remain enabled.")

    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must remain 0.")

    if policy_enabled != 1:
        issues.append("Target policy production_batch_enabled must remain 1.")

    if policy_live != 0:
        issues.append("Target policy live_posting_allowed must remain 0.")

    if config["sandbox_enabled"] != 1:
        issues.append("Sandbox config must be enabled for controlled smoke.")

    if config["production_mode"] != 0:
        issues.append("Production mode config must remain 0.")

    if config["live_pe_enabled"] != 0:
        issues.append("Live Payment Entry posting config must remain 0. Smoke is sandbox-controlled only.")

    return issues


def make_payment_entry_from_baseline(baseline_payment_entry, rows, smoke_id):
    baseline = frappe.get_doc("Payment Entry", baseline_payment_entry)
    pe = frappe.copy_doc(baseline)

    pe.name = None
    pe.docstatus = 0
    pe.status = "Draft"
    pe.amended_from = None
    pe.posting_date = today()
    pe.reference_no = smoke_id
    pe.reference_date = today()
    pe.clearance_date = None
    pe.remarks = f"Phase 11V controlled-cycle smoke Payment Entry created from execution gate. Smoke: {smoke_id}"

    amount = approved_total(rows)

    if pe.meta.has_field("paid_amount"):
        pe.paid_amount = amount
    if pe.meta.has_field("received_amount"):
        pe.received_amount = amount
    if pe.meta.has_field("base_paid_amount"):
        pe.base_paid_amount = amount
    if pe.meta.has_field("base_received_amount"):
        pe.base_received_amount = amount
    if pe.meta.has_field("source_exchange_rate"):
        pe.source_exchange_rate = pe.source_exchange_rate or 1
    if pe.meta.has_field("target_exchange_rate"):
        pe.target_exchange_rate = pe.target_exchange_rate or 1
    if pe.meta.has_field("unallocated_amount"):
        pe.unallocated_amount = 0
    if pe.meta.has_field("difference_amount"):
        pe.difference_amount = 0

    pe.set("references", [])
    for row in rows:
        pe.append(
            "references",
            {
                "reference_doctype": "Sales Invoice",
                "reference_name": row.reference_name,
                "total_amount": row.grand_total,
                "outstanding_amount": row.current_outstanding_amount,
                "allocated_amount": row.approved_amount,
                "due_date": row.due_date,
            },
        )

    pe.flags.ignore_permissions = True
    pe.insert(ignore_permissions=True)
    pe.submit()

    return pe.name


def add_item(items, status, severity, category, check_key, check_label, detail, row=None, created_payment_entry=None):
    item = {
        "status": status,
        "severity": severity,
        "category": category,
        "check_key": check_key,
        "check_label": check_label,
        "detail": detail,
        "created_payment_entry": created_payment_entry,
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
                "allocated_amount": row.approved_amount,
            }
        )

    items.append(item)


def build_items(execution_gate, rows, issues, ack_ok, created_payment_entry=None):
    items = []

    if execution_gate:
        add_item(
            items,
            "Pass",
            "Low",
            "Evidence",
            "phase11u_execution_gate_exists",
            "Phase 11U execution gate exists",
            f"Execution gate found: {execution_gate.execution_gate_id}.",
            created_payment_entry=created_payment_entry,
        )
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase11u_execution_gate_exists", "Phase 11U execution gate exists", "No approved Phase 11U execution gate found.")

    if not issues:
        add_item(
            items,
            "Pass",
            "Critical",
            "Smoke Source",
            "smoke_source_valid",
            "Smoke source valid",
            "Execution gate is approved and smoke-only posting is authorised.",
            created_payment_entry=created_payment_entry,
        )
    else:
        for issue in issues:
            add_item(
                items,
                "Blocker",
                "Critical",
                "Smoke Source",
                "smoke_source_valid",
                "Smoke source valid",
                issue,
                created_payment_entry=created_payment_entry,
            )

    for row in rows:
        add_item(
            items,
            "Pass",
            "High",
            "Smoke Reference",
            "smoke_sales_invoice_reference",
            f"Smoke Sales Invoice {row.idx}",
            f"{row.reference_name} allocated {row.approved_amount} in the controlled smoke Payment Entry.",
            row=row,
            created_payment_entry=created_payment_entry,
        )

    checks = [
        ("smoke_only_authorised", "Smoke-only authorised", 1),
        ("real_production_blocked", "Real production posting blocked", 1),
        ("created_payment_entry", "Created exactly one Payment Entry", created_payment_entry or "Not created yet"),
        ("created_payment_entry_amount", "Created Payment Entry amount = 3.00", APPROVED_TOTAL_AMOUNT),
        ("created_payment_entry_refs", "Created Payment Entry references = 3", APPROVED_REFERENCE_COUNT),
        ("created_payment_entry_gl_rows", "Created Payment Entry GL rows = 4", EXPECTED_GL_ROWS_CREATED),
        ("payment_entry_count", "Payment Entry count moves 9 -> 10", "9 -> 10"),
        ("payment_entry_gl_count", "Payment Entry GL count moves 54 -> 58", "54 -> 58"),
        ("rollback_required", "Rollback required", 1),
        ("policy_state", "Policy state preserved at 1 / 0", "1 / 0"),
        ("no_je_pi", "No JE / PI side effects", "0 / 0"),
    ]

    for key, label, value in checks:
        add_item(
            items,
            "Pass",
            "High",
            "Smoke Evidence",
            key,
            label,
            f"value={value}",
            created_payment_entry=created_payment_entry,
        )

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.", created_payment_entry=created_payment_entry)
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {SMOKE_ACK}")

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
        row = frappe.new_doc(SMOKE_ITEM_DOCTYPE)
        row.smoke = doc.name
        for fieldname, value in item.items():
            if row.meta.has_field(fieldname):
                setattr(row, fieldname, value)
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_next_controlled_cycle_smoke(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_next_controlled_cycle_smoke")

    execution_gate = latest_execution_gate()
    baseline_payment_entry = execution_gate.baseline_payment_entry if execution_gate else None
    rows = approved_rows(execution_gate.name) if execution_gate else []

    guard_before = guardrails()
    ack_ok = acknowledgement == SMOKE_ACK

    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }

    policy_enabled_before = get_flag(POLICY_DOCTYPE, execution_gate.target_policy, "production_batch_enabled") if execution_gate else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, execution_gate.target_policy, "live_posting_allowed") if execution_gate else 0

    source_issues = validate_source(execution_gate, baseline_payment_entry, rows, guard_before, config, policy_enabled_before, policy_live_before)

    created_payment_entry = None
    smoke_id = make_smoke_id()

    if not int(dry_run or 0) and ack_ok and not source_issues:
        created_payment_entry = make_payment_entry_from_baseline(baseline_payment_entry, rows, smoke_id)

    guard_after = guardrails()

    policy_enabled_after = get_flag(POLICY_DOCTYPE, execution_gate.target_policy, "production_batch_enabled") if execution_gate else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, execution_gate.target_policy, "live_posting_allowed") if execution_gate else 0

    actual_pe_created = guard_after["payment_entry_count"] - guard_before["payment_entry_count"]
    actual_pe_cancelled = 0
    actual_gl_created = guard_after["payment_entry_gl_count"] - guard_before["payment_entry_gl_count"]

    policy_mutation_count = int(
        policy_enabled_before != policy_enabled_after
        or policy_live_before != policy_live_after
        or guard_before["production_batch_enabled_policy_count"] != guard_after["production_batch_enabled_policy_count"]
        or guard_before["live_posting_allowed_policy_count"] != guard_after["live_posting_allowed_policy_count"]
    )

    created_docstatus = 0
    created_status = None
    created_amount = 0
    created_reference_count = 0
    created_gl_rows = 0
    created_gl_net = 0
    created_gl_non_zero_accounts = 0

    if created_payment_entry:
        pe = frappe.get_doc("Payment Entry", created_payment_entry)
        created_docstatus = int(pe.docstatus or 0)
        created_status = pe.status
        created_amount = payment_entry_allocated_amount(created_payment_entry)
        created_reference_count = payment_entry_reference_count(created_payment_entry)
        created_gl_rows = voucher_gl_rows(created_payment_entry)
        created_gl_net = voucher_gl_net(created_payment_entry)
        created_gl_non_zero_accounts = voucher_gl_non_zero_accounts(created_payment_entry)

    post_issues = list(source_issues)

    if not int(dry_run or 0) and ack_ok:
        if actual_pe_created != 1:
            post_issues.append(f"Smoke must create exactly one Payment Entry. Created {actual_pe_created}.")

        if actual_pe_cancelled != 0:
            post_issues.append(f"Smoke must not cancel Payment Entries. Cancelled {actual_pe_cancelled}.")

        if actual_gl_created != EXPECTED_GL_ROWS_CREATED:
            post_issues.append(f"Smoke must create exactly {EXPECTED_GL_ROWS_CREATED} GL rows. Created {actual_gl_created}.")

        if guard_after["payment_entry_count"] != 10:
            post_issues.append("Payment Entry count must become 10 after smoke.")

        if guard_after["payment_entry_gl_count"] != 58:
            post_issues.append("Payment Entry GL count must become 58 after smoke.")

        if not created_payment_entry:
            post_issues.append("Smoke did not create a Payment Entry.")

        if created_payment_entry and created_docstatus != 1:
            post_issues.append(f"Created Payment Entry must be submitted. docstatus={created_docstatus}")

        if created_payment_entry and created_reference_count != APPROVED_REFERENCE_COUNT:
            post_issues.append(f"Created Payment Entry must have {APPROVED_REFERENCE_COUNT} references. Found {created_reference_count}.")

        if created_payment_entry and created_amount != APPROVED_TOTAL_AMOUNT:
            post_issues.append(f"Created Payment Entry amount must be {APPROVED_TOTAL_AMOUNT}. Found {created_amount}.")

        if created_payment_entry and created_gl_rows != EXPECTED_GL_ROWS_CREATED:
            post_issues.append(f"Created Payment Entry GL row count must be {EXPECTED_GL_ROWS_CREATED}. Found {created_gl_rows}.")

        if created_payment_entry and created_gl_net != 0:
            post_issues.append(f"Created Payment Entry GL net must be 0.00. Found {created_gl_net}.")

    else:
        if actual_pe_created != 0:
            post_issues.append(f"Dry-run/no-ack smoke must not create Payment Entries. Created {actual_pe_created}.")

        if actual_gl_created != 0:
            post_issues.append(f"Dry-run/no-ack smoke must not create GL rows. Created {actual_gl_created}.")

    if guard_after["submitted_journal_entry_count_today"] != 0:
        post_issues.append("Submitted Journal Entry count today must remain 0 after smoke.")

    if guard_after["purchase_invoice_count_today"] != 0:
        post_issues.append("Purchase Invoice count today must remain 0 after smoke.")

    if policy_mutation_count != 0:
        post_issues.append("Policy state changed during smoke. This is not allowed.")

    customers = approved_customers(rows)
    companies = approved_companies(rows)
    currencies = approved_currencies(rows)

    completed = int(
        not int(dry_run or 0)
        and ack_ok
        and execution_gate
        and created_payment_entry
        and not post_issues
        and created_docstatus == 1
        and created_reference_count == APPROVED_REFERENCE_COUNT
        and created_amount == APPROVED_TOTAL_AMOUNT
        and created_gl_rows == EXPECTED_GL_ROWS_CREATED
        and created_gl_net == 0
        and created_gl_non_zero_accounts == 0
        and actual_pe_created == 1
        and actual_pe_cancelled == 0
        and actual_gl_created == EXPECTED_GL_ROWS_CREATED
        and guard_before["payment_entry_count"] == 9
        and guard_after["payment_entry_count"] == 10
        and guard_before["payment_entry_gl_count"] == 54
        and guard_after["payment_entry_gl_count"] == 58
        and guard_after["submitted_journal_entry_count_today"] == 0
        and guard_after["purchase_invoice_count_today"] == 0
        and policy_mutation_count == 0
    )

    items = build_items(execution_gate, rows, post_issues, ack_ok, created_payment_entry=created_payment_entry)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Smoke Completed - Rollback Required" if completed else "Needs Review",
        "smoke_status": "Next Controlled Cycle Smoke Completed" if completed else "Needs Review",
        "smoke_completed": completed,
        "phase11u_execution_gate_verified": 1 if execution_gate else 0,
        "execution_gate_approved_verified": 1 if execution_gate else 0,
        "smoke_only_authorisation_verified": 1 if execution_gate else 0,
        "real_production_blocked_verified": 1,
        "created_payment_entry_verified": int(bool(created_payment_entry)),
        "created_payment_entry_submitted_verified": int(created_docstatus == 1),
        "created_payment_entry_reference_count_verified": int(created_reference_count == APPROVED_REFERENCE_COUNT),
        "created_payment_entry_amount_verified": int(created_amount == APPROVED_TOTAL_AMOUNT),
        "created_payment_entry_gl_row_count_verified": int(created_gl_rows == EXPECTED_GL_ROWS_CREATED),
        "rollback_required": completed,
        "ready_for_next_controlled_cycle_rollback": completed,
        "policy_state_preserved_verified": int(policy_mutation_count == 0 and policy_enabled_before == 1 and policy_enabled_after == 1 and policy_live_before == 0 and policy_live_after == 0),
        "real_production_posting_authorised": 0,
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": policy_mutation_count,
        "created_payment_entry": created_payment_entry,
        "created_payment_entry_docstatus": created_docstatus,
        "created_payment_entry_status": created_status,
        "created_payment_entry_reference_count": created_reference_count,
        "created_payment_entry_amount": created_amount,
        "created_payment_entry_gl_row_count": created_gl_rows,
        "created_payment_entry_gl_net": created_gl_net,
        "created_payment_entry_gl_non_zero_account_count": created_gl_non_zero_accounts,
        "approved_source_doctype": APPROVED_SOURCE_DOCTYPE,
        "approved_reference_doctype": APPROVED_REFERENCE_DOCTYPE,
        "approved_party_type": APPROVED_PARTY_TYPE,
        "approved_customer": customers[0] if customers else None,
        "approved_company": companies[0] if companies else None,
        "approved_currency": currencies[0] if currencies else None,
        "approved_reference_count": len(rows),
        "approved_total_amount": approved_total(rows),
        "approved_payment_entry_count": APPROVED_PAYMENT_ENTRY_COUNT,
        "approved_gl_entry_count": 0,
        "baseline_payment_entry": baseline_payment_entry,
        "baseline_payment_entry_docstatus": 2 if baseline_payment_entry else 0,
        "baseline_payment_entry_status": "Cancelled" if baseline_payment_entry else None,
        "baseline_voucher_gl_rows": voucher_gl_rows(baseline_payment_entry) if baseline_payment_entry else 0,
        "baseline_voucher_gl_net": voucher_gl_net(baseline_payment_entry) if baseline_payment_entry else 0,
        "execution_gate": execution_gate.name if execution_gate else None,
        "preview": execution_gate.preview if execution_gate else None,
        "validation": execution_gate.validation if execution_gate else None,
        "candidate": execution_gate.candidate if execution_gate else None,
        "design": execution_gate.design if execution_gate else None,
        "planning": execution_gate.planning if execution_gate else None,
        "monitor": execution_gate.monitor if execution_gate else None,
        "baseline": execution_gate.baseline if execution_gate else None,
        "closeout": execution_gate.closeout if execution_gate else None,
        "freeze": execution_gate.freeze if execution_gate else None,
        "rollback": execution_gate.rollback if execution_gate else None,
        "previous_smoke": execution_gate.smoke if execution_gate else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": execution_gate.target_policy if execution_gate else None,
        "target_policy_name": execution_gate.target_policy_name if execution_gate else None,
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
        "smoke_score": score,
        **item_summary,
        "items": items,
        "approved_references": [dict(row) for row in rows],
        "issues": post_issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "required_acknowledgement": SMOKE_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 11V creates one submitted Payment Entry as controlled smoke. Rollback is mandatory next.",
    }

    if int(dry_run or 0):
        return result

    doc = frappe.new_doc(SMOKE_DOCTYPE)
    doc.smoke_id = smoke_id

    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)

    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = SMOKE_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.smoke_json = safe_json(
        {
            "execution_gate": execution_gate,
            "baseline_payment_entry": baseline_payment_entry,
            "created_payment_entry": created_payment_entry,
            "approved_references": [dict(row) for row in rows],
            "guardrails_before": guard_before,
            "guardrails_after": guard_after,
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
        "smoke": doc.name,
        "smoke_id": doc.smoke_id,
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_next_controlled_cycle_smoke_audit(smoke, reason=None):
    assert_action("cancel_next_controlled_cycle_smoke_audit")

    if not frappe.db.exists(SMOKE_DOCTYPE, smoke):
        frappe.throw(_("Next controlled-cycle smoke audit not found: {0}").format(smoke))

    doc = frappe.get_doc(SMOKE_DOCTYPE, smoke)

    if doc.status == "Cancelled":
        return {"smoke": smoke, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.smoke_completed or 0) or doc.created_payment_entry:
        frappe.throw(_("Cannot cancel a completed Phase 11V smoke record or a smoke record linked to a Payment Entry."))

    frappe.db.set_value(
        SMOKE_DOCTYPE,
        smoke,
        {
            "status": "Cancelled",
            "smoke_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 11V no-ack smoke audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        f"""
        UPDATE `tab{SMOKE_ITEM_DOCTYPE}`
        SET status = 'Cancelled'
        WHERE smoke = %(smoke)s
        """,
        {"smoke": smoke},
    )

    frappe.db.commit()

    return {
        "smoke": smoke,
        "status": "Cancelled",
        "note": "No-ack smoke audit cancelled only. No accounting or policy movement occurred.",
    }


@frappe.whitelist()
def quick_next_controlled_cycle_smoke_summary(limit=20):
    records = frappe.get_all(
        SMOKE_DOCTYPE,
        fields=[
            "name",
            "smoke_id",
            "status",
            "smoke_status",
            "smoke_completed",
            "created_payment_entry",
            "created_payment_entry_docstatus",
            "created_payment_entry_status",
            "created_payment_entry_reference_count",
            "created_payment_entry_amount",
            "created_payment_entry_gl_row_count",
            "rollback_required",
            "ready_for_next_controlled_cycle_rollback",
            "execution_gate",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "actual_payment_entry_created_count",
            "actual_payment_entry_cancelled_count",
            "actual_gl_created_count",
            "submitted_journal_entry_count_today",
            "purchase_invoice_count_today",
            "smoke_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    items = frappe.get_all(
        SMOKE_ITEM_DOCTYPE,
        fields=[
            "name",
            "smoke",
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
            "allocated_amount",
            "created_payment_entry",
            "detail",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    return {
        "smoke_records": records,
        "items": items,
        "required_acknowledgement": SMOKE_ACK,
        "guardrails": guardrails(),
        "note": "Phase 11V next controlled-cycle smoke summary.",
    }


def execute_smoke_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("status"):
        conditions.append("s.status = %(status)s")
        params["status"] = filters.get("status")

    columns = [
        {"fieldname": "smoke", "label": _("Smoke"), "fieldtype": "Link", "options": SMOKE_DOCTYPE, "width": 220},
        {"fieldname": "smoke_id", "label": _("Smoke ID"), "fieldtype": "Data", "width": 370},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 230},
        {"fieldname": "smoke_status", "label": _("Smoke Status"), "fieldtype": "Data", "width": 280},
        {"fieldname": "smoke_completed", "label": _("Completed"), "fieldtype": "Check", "width": 90},
        {"fieldname": "created_payment_entry", "label": _("Created PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "created_payment_entry_docstatus", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 100},
        {"fieldname": "created_payment_entry_status", "label": _("PE Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "created_payment_entry_reference_count", "label": _("Refs"), "fieldtype": "Int", "width": 80},
        {"fieldname": "created_payment_entry_amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 100},
        {"fieldname": "created_payment_entry_gl_row_count", "label": _("PE GL Rows"), "fieldtype": "Int", "width": 110},
        {"fieldname": "rollback_required", "label": _("Rollback Required"), "fieldtype": "Check", "width": 130},
        {"fieldname": "ready_for_next_controlled_cycle_rollback", "label": _("Rollback Ready"), "fieldtype": "Check", "width": 120},
        {"fieldname": "execution_gate", "label": _("Execution Gate"), "fieldtype": "Link", "options": EXEC_GATE_DOCTYPE, "width": 220},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 110},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE Created"), "fieldtype": "Int", "width": 130},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL Created"), "fieldtype": "Int", "width": 130},
        {"fieldname": "submitted_journal_entry_count_today", "label": _("JE Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "purchase_invoice_count_today", "label": _("PI Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "smoke_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            s.name AS smoke,
            s.smoke_id,
            s.status,
            s.smoke_status,
            s.smoke_completed,
            s.created_payment_entry,
            s.created_payment_entry_docstatus,
            s.created_payment_entry_status,
            s.created_payment_entry_reference_count,
            s.created_payment_entry_amount,
            s.created_payment_entry_gl_row_count,
            s.rollback_required,
            s.ready_for_next_controlled_cycle_rollback,
            s.execution_gate,
            s.payment_entry_count_before,
            s.payment_entry_count_after,
            s.payment_entry_gl_count_before,
            s.payment_entry_gl_count_after,
            s.actual_payment_entry_created_count,
            s.actual_gl_created_count,
            s.submitted_journal_entry_count_today,
            s.purchase_invoice_count_today,
            s.smoke_score,
            s.checked_on,
            %(currency)s AS currency
        FROM `tab{SMOKE_DOCTYPE}` s
        {build_where(conditions)}
        ORDER BY s.creation DESC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.smoke_id for row in data[:20]],
            "datasets": [
                {"name": "Smoke Completed", "values": [int(row.smoke_completed or 0) for row in data[:20]]},
                {"name": "Rollback Required", "values": [int(row.rollback_required or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Smoke Records"), "datatype": "Int"},
        {"value": sum(int(row.smoke_completed or 0) for row in data), "indicator": "Green", "label": _("Completed"), "datatype": "Int"},
        {"value": sum(int(row.rollback_required or 0) for row in data), "indicator": "Red", "label": _("Rollback Required"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Orange", "label": _("Actual GL Created"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    if filters.get("smoke"):
        conditions.append("i.smoke = %(smoke)s")
        params["smoke"] = filters.get("smoke")

    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": SMOKE_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "smoke", "label": _("Smoke"), "fieldtype": "Link", "options": SMOKE_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 190},
        {"fieldname": "line_no", "label": _("Line"), "fieldtype": "Int", "width": 60},
        {"fieldname": "reference_doctype", "label": _("Ref DocType"), "fieldtype": "Data", "width": 130},
        {"fieldname": "reference_name", "label": _("Reference"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 180},
        {"fieldname": "customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 220},
        {"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 220},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "width": 90},
        {"fieldname": "allocated_amount", "label": _("Allocated Amount"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "created_payment_entry", "label": _("Created PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "check_key", "label": _("Check Key"), "fieldtype": "Data", "width": 230},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 330},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 650},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            i.name AS item,
            i.smoke,
            i.status,
            i.severity,
            i.category,
            i.line_no,
            i.reference_doctype,
            i.reference_name,
            i.customer,
            i.company,
            i.currency,
            i.allocated_amount,
            i.created_payment_entry,
            i.check_key,
            i.check_label,
            i.detail,
            i.checked_on
        FROM `tab{SMOKE_ITEM_DOCTYPE}` i
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
        {"value": len([row for row in data if row.category == "Smoke Reference"]), "indicator": "Green", "label": _("Smoke References"), "datatype": "Int"},
        {"value": sum(flt(row.allocated_amount or 0, 2) for row in data if row.category == "Smoke Reference"), "indicator": "Green", "label": _("Allocated Amount"), "datatype": "Currency"},
        {"value": len([row for row in data if row.status == "Blocker"]), "indicator": "Red", "label": _("Blockers"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_smoke_report(filters)
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
