import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, today

from ndis_finance.services.permissions import assert_action


SMOKE_ACK = "I_CONFIRM_PHASE14D_RUN_NEXT_GOVERNED_LIMITED_OPERATION_SMOKE_NO_POSTING"

POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
EXECUTION_GATE_DOCTYPE = "NDIS Next Governed Limited Op Execution Gate"
EXECUTION_GATE_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Execution Gate Item"
SMOKE_DOCTYPE = "NDIS Next Governed Limited Op Smoke"
SMOKE_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Smoke Item"

EXECUTION_GATE_READY_FIELD = "ready_for_next_governed_limited_op_smoke"
SMOKE_READY_FIELD = "ready_for_next_governed_limited_op_smoke_rollback"

GATED_PAYMENT_ENTRY = "ACC-PAY-2026-00015"
PREVIOUS_GATED_PAYMENT_ENTRY = "ACC-PAY-2026-00014"
EXPECTED_SMOKE_PAYMENT_ENTRY = "ACC-PAY-2026-00016"
EXPECTED_INVOICES = ["ACC-SINV-2026-00005", "ACC-SINV-2026-00006", "ACC-SINV-2026-00008"]

EXPECTED_PAYMENT_ENTRY_COUNT_BEFORE = 14
EXPECTED_PAYMENT_ENTRY_COUNT_AFTER = 15
EXPECTED_PAYMENT_ENTRY_GL_COUNT_BEFORE = 94
EXPECTED_PAYMENT_ENTRY_GL_COUNT_AFTER = 98
EXPECTED_TOTAL_AMOUNT = 3.00
EXPECTED_INVOICE_COUNT = 3
EXPECTED_INVOICE_OUTSTANDING_BEFORE = 3.00
EXPECTED_INVOICE_OUTSTANDING_AFTER = 0.00
EXPECTED_SMOKE_GL_ROWS = 4
EXPECTED_SMOKE_GL_NET = 0.00

SMOKE_SOURCE_DOCTYPE = "Sales Invoice"
SMOKE_REFERENCE_DOCTYPE = "Sales Invoice"
SMOKE_PARTY_TYPE = "Customer"
SMOKE_PAYMENT_TYPE = "Receive"


def make_smoke_id():
    timestamp = now_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-NEXT-GOVERNED-LIMITED-OP-SMOKE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def row_get(row, fieldname, default=None):
    try:
        return row.get(fieldname, default)
    except Exception:
        return getattr(row, fieldname, default)


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


def payment_entry_state(payment_entry):
    if not payment_entry or not frappe.db.exists("Payment Entry", payment_entry):
        return frappe._dict({"docstatus": 0, "status": None})
    pe = frappe.get_doc("Payment Entry", payment_entry)
    return frappe._dict({"docstatus": int(pe.docstatus or 0), "status": pe.status})


def payment_entry_gl_rows(payment_entry):
    return count_dt("GL Entry", {"voucher_type": "Payment Entry", "voucher_no": payment_entry})


def payment_entry_gl_net(payment_entry):
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


def payment_entry_cancelled_gl_rows(payment_entry):
    return frappe.db.sql(
        """
        SELECT COALESCE(SUM(CASE WHEN is_cancelled=1 THEN 1 ELSE 0 END), 0)
        FROM `tabGL Entry`
        WHERE voucher_type='Payment Entry'
        AND voucher_no=%s
        """,
        payment_entry,
    )[0][0] or 0


def outstanding_total(invoice_names):
    if not invoice_names:
        return 0
    value = frappe.db.sql(
        """
        SELECT ROUND(COALESCE(SUM(outstanding_amount), 0), 2)
        FROM `tabSales Invoice`
        WHERE name IN %(names)s
        """,
        {"names": tuple(invoice_names)},
    )[0][0]
    return flt(value or 0, 2)


def latest_execution_gate():
    filters = {
        "status": "Execution Gate Approved",
        "execution_gate_status": "Next Governed Limited Operation Execution Gate Approved",
        "execution_gate_approved": 1,
        "phase14b_preview_verified": 1,
        "preview_approved_verified": 1,
        "preview_payment_entry_verified": 1,
        "preview_payment_entry_cancelled_verified": 1,
        "preview_gl_rows_verified": 1,
        "preview_reversal_gl_rows_verified": 1,
        "preview_gl_net_zero_verified": 1,
        "preview_restored_invoice_amount_verified": 1,
        "policy_state_preserved_verified": 1,
        "no_new_accounting_movement_verified": 1,
        "gated_payment_entry": GATED_PAYMENT_ENTRY,
        "gated_payment_entry_docstatus": 2,
        "gated_payment_entry_status": "Cancelled",
        "previous_gated_payment_entry": PREVIOUS_GATED_PAYMENT_ENTRY,
        "previous_gated_payment_entry_docstatus": 2,
        "previous_gated_payment_entry_status": "Cancelled",
        "execution_gate_source_doctype": SMOKE_SOURCE_DOCTYPE,
        "execution_gate_reference_doctype": SMOKE_REFERENCE_DOCTYPE,
        "execution_gate_party_type": SMOKE_PARTY_TYPE,
        "execution_gate_invoice_count": EXPECTED_INVOICE_COUNT,
        "execution_gate_total_amount": EXPECTED_TOTAL_AMOUNT,
        "execution_gate_restored_invoice_amount": EXPECTED_TOTAL_AMOUNT,
        "execution_gate_gl_rows": 8,
        "execution_gate_reversal_gl_rows": 4,
        "execution_gate_gl_net": 0,
        "payment_entry_count_after": EXPECTED_PAYMENT_ENTRY_COUNT_BEFORE,
        "payment_entry_gl_count_after": EXPECTED_PAYMENT_ENTRY_GL_COUNT_BEFORE,
        "actual_payment_entry_created_count": 0,
        "actual_payment_entry_cancelled_count": 0,
        "actual_gl_created_count": 0,
        "submitted_journal_entry_count_today": 0,
        "purchase_invoice_count_today": 0,
        "target_policy_enabled_after": 1,
        "target_policy_live_after": 0,
        "actual_policy_mutation_count": 0,
        "blocker_count": 0,
        "warning_count": 0,
    }

    if has_column(EXECUTION_GATE_DOCTYPE, EXECUTION_GATE_READY_FIELD):
        filters[EXECUTION_GATE_READY_FIELD] = 1

    rows = frappe.get_all(
        EXECUTION_GATE_DOCTYPE,
        filters=filters,
        fields=[
            "name",
            "execution_gate_id",
            "execution_gate_source_doctype",
            "execution_gate_reference_doctype",
            "execution_gate_party_type",
            "execution_gate_customer",
            "execution_gate_company",
            "execution_gate_currency",
            "execution_gate_invoice_names",
            "execution_gate_invoice_count",
            "execution_gate_total_amount",
            "execution_gate_restored_invoice_amount",
            "execution_gate_gl_rows",
            "execution_gate_reversal_gl_rows",
            "execution_gate_gl_net",
            "gated_payment_entry",
            "gated_payment_entry_docstatus",
            "gated_payment_entry_status",
            "previous_gated_payment_entry",
            "previous_gated_payment_entry_docstatus",
            "previous_gated_payment_entry_status",
            "execution_gate_payment_entry",
            "execution_gate_payment_entry_docstatus",
            "execution_gate_payment_entry_status",
            "preview",
            "candidate_validation",
            "candidate_selection",
            "design",
            "planning",
            "monitor",
            "baseline",
            "closeout",
            "freeze",
            "rollback",
            "smoke",
            "target_policy",
            "target_policy_name",
            EXECUTION_GATE_READY_FIELD,
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
            "status": "Smoke Completed",
            "smoke_completed": 1,
            "smoke_payment_entry": EXPECTED_SMOKE_PAYMENT_ENTRY,
        },
        fields=["name", "smoke_id", "smoke_payment_entry"],
        limit=1,
    )
    return rows[0] if rows else None


def execution_gate_rows(execution_gate):
    rows = frappe.get_all(
        EXECUTION_GATE_ITEM_DOCTYPE,
        filters={
            "execution_gate": execution_gate,
            "category": "Execution Gate Reference",
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
            "execution_gate_amount",
            "outstanding_amount",
            "execution_gate_payment_entry",
        ],
        order_by="line_no asc, creation asc",
    )

    result = []
    for idx, row in enumerate(rows, start=1):
        si = frappe.db.get_value(
            "Sales Invoice",
            row.reference_name,
            ["docstatus", "customer", "company", "currency", "outstanding_amount", "grand_total", "rounded_total", "due_date"],
            as_dict=True,
        ) if frappe.db.exists("Sales Invoice", row.reference_name) else None

        amount = flt(row.execution_gate_amount or 0, 2)
        outstanding = flt((si.outstanding_amount if si else row.outstanding_amount) or 0, 2)

        result.append(
            frappe._dict(
                {
                    "idx": int(row.line_no or idx),
                    "reference_doctype": row.reference_doctype,
                    "reference_name": row.reference_name,
                    "smoke_amount": amount,
                    "allocated_amount": amount,
                    "current_outstanding_amount": outstanding,
                    "customer": si.customer if si else row.customer,
                    "company": si.company if si else row.company,
                    "currency": si.currency if si else row.currency,
                    "invoice_docstatus": int(si.docstatus or 0) if si else 0,
                    "outstanding_sufficient": int(outstanding >= amount and amount > 0),
                    "outstanding_before": outstanding,
                    "grand_total": flt((si.grand_total if si else amount) or amount, 2),
                    "due_date": si.due_date if si else None,
                    "gated_payment_entry": GATED_PAYMENT_ENTRY,
                }
            )
        )

    return result


def reference_names(rows):
    return [row.reference_name for row in rows]


def smoke_total(rows):
    return flt(sum(flt(row.smoke_amount or 0, 2) for row in rows), 2)


def unique_value(rows, fieldname):
    values = sorted(set([getattr(row, fieldname, None) for row in rows if getattr(row, fieldname, None)]))
    return values[0] if len(values) == 1 else None


def same_value_verified(rows, fieldname):
    values = set([getattr(row, fieldname, None) for row in rows if getattr(row, fieldname, None)])
    return int(len(rows) == EXPECTED_INVOICE_COUNT and len(values) == 1)


def invoices_submitted(rows):
    return int(len(rows) == EXPECTED_INVOICE_COUNT and all(int(row.invoice_docstatus or 0) == 1 for row in rows))


def invoices_outstanding_sufficient(rows):
    return int(len(rows) == EXPECTED_INVOICE_COUNT and all(int(row.outstanding_sufficient or 0) == 1 for row in rows))


def validate_source(execution_gate, rows, guard, config, policy_enabled, policy_live):
    issues = []

    if not execution_gate:
        issues.append("No approved Phase 14C execution gate found for smoke.")
        return issues

    existing = existing_completed_smoke(execution_gate.name)
    if existing:
        issues.append(f"Completed Phase 14D smoke already exists for this execution gate: {existing.smoke_id} / {existing.smoke_payment_entry}")

    gated_state = payment_entry_state(GATED_PAYMENT_ENTRY)
    previous_gated_state = payment_entry_state(PREVIOUS_GATED_PAYMENT_ENTRY)

    if gated_state.docstatus != 2 or gated_state.status != "Cancelled":
        issues.append(f"Gated Payment Entry {GATED_PAYMENT_ENTRY} must remain Cancelled before smoke.")

    if previous_gated_state.docstatus != 2 or previous_gated_state.status != "Cancelled":
        issues.append(f"Previous gated Payment Entry {PREVIOUS_GATED_PAYMENT_ENTRY} must remain Cancelled before smoke.")

    if frappe.db.exists("Payment Entry", EXPECTED_SMOKE_PAYMENT_ENTRY):
        issues.append(f"{EXPECTED_SMOKE_PAYMENT_ENTRY} already exists before Phase 14D smoke.")

    if reference_names(rows) != EXPECTED_INVOICES:
        issues.append(f"Smoke invoice set changed. Expected {EXPECTED_INVOICES}. Found {reference_names(rows)}.")

    if len(rows) != EXPECTED_INVOICE_COUNT:
        issues.append(f"Smoke invoice count must be {EXPECTED_INVOICE_COUNT}. Found {len(rows)}.")

    if smoke_total(rows) != EXPECTED_TOTAL_AMOUNT:
        issues.append(f"Smoke total amount must be {EXPECTED_TOTAL_AMOUNT}. Found {smoke_total(rows)}.")

    if not same_value_verified(rows, "customer"):
        issues.append("Smoke Sales Invoices must share the same customer.")

    if not same_value_verified(rows, "company"):
        issues.append("Smoke Sales Invoices must share the same company.")

    if not same_value_verified(rows, "currency"):
        issues.append("Smoke Sales Invoices must share the same currency.")

    if not invoices_submitted(rows):
        issues.append("All smoke Sales Invoices must remain submitted.")

    if not invoices_outstanding_sufficient(rows):
        issues.append("All smoke Sales Invoices must have sufficient outstanding amount.")

    if outstanding_total(EXPECTED_INVOICES) != EXPECTED_INVOICE_OUTSTANDING_BEFORE:
        issues.append(
            f"Invoice outstanding before smoke must be exactly {EXPECTED_INVOICE_OUTSTANDING_BEFORE:.2f}. "
            f"Found {outstanding_total(EXPECTED_INVOICES):.2f}."
        )

    if guard["payment_entry_count"] != EXPECTED_PAYMENT_ENTRY_COUNT_BEFORE:
        issues.append("Payment Entry count must be 14 before smoke.")

    if guard["payment_entry_gl_count"] != EXPECTED_PAYMENT_ENTRY_GL_COUNT_BEFORE:
        issues.append("Payment Entry GL count must be 94 before smoke.")

    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today must remain 0 before smoke.")

    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today must remain 0 before smoke.")

    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must remain enabled before smoke.")

    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must remain 0 before smoke.")

    if policy_enabled != 1:
        issues.append("Target policy production_batch_enabled must remain 1.")

    if policy_live != 0:
        issues.append("Target policy live_posting_allowed must remain 0.")

    if config["sandbox_enabled"] != 1:
        issues.append("Sandbox config must be enabled for governed smoke.")

    if config["production_mode"] != 0:
        issues.append("Production mode config must remain 0 for governed smoke.")

    if config["live_pe_enabled"] != 0:
        issues.append("Live Payment Entry posting config must remain 0 for governed smoke.")

    return issues


def create_smoke_payment_entry(rows):
    template = frappe.get_doc("Payment Entry", GATED_PAYMENT_ENTRY)

    total = smoke_total(rows)
    customer = unique_value(rows, "customer")
    company = unique_value(rows, "company")

    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = SMOKE_PAYMENT_TYPE
    pe.company = company
    pe.party_type = SMOKE_PARTY_TYPE
    pe.party = customer
    pe.posting_date = template.posting_date

    for fieldname in [
        "mode_of_payment",
        "bank_account",
        "paid_from",
        "paid_to",
        "paid_from_account_currency",
        "paid_to_account_currency",
        "source_exchange_rate",
        "target_exchange_rate",
        "paid_from_account_type",
        "paid_to_account_type",
        "cost_center",
        "project",
    ]:
        if pe.meta.has_field(fieldname) and getattr(template, fieldname, None):
            setattr(pe, fieldname, getattr(template, fieldname))

    pe.paid_amount = total
    pe.received_amount = total
    pe.reference_no = f"PHASE14D-{now_datetime().strftime('%Y%m%d%H%M%S')}"
    pe.reference_date = template.reference_date or template.posting_date

    for row in rows:
        pe.append(
            "references",
            {
                "reference_doctype": "Sales Invoice",
                "reference_name": row.reference_name,
                "total_amount": row.grand_total,
                "outstanding_amount": row.outstanding_before,
                "allocated_amount": row.allocated_amount,
                "due_date": row.due_date,
            },
        )

    if hasattr(pe, "setup_party_account_field"):
        pe.setup_party_account_field()
    if hasattr(pe, "set_missing_values"):
        pe.set_missing_values()
    if hasattr(pe, "set_exchange_rate"):
        pe.set_exchange_rate()
    if hasattr(pe, "set_amounts"):
        pe.set_amounts()

    pe.insert(ignore_permissions=True)
    pe.submit()

    if pe.name != EXPECTED_SMOKE_PAYMENT_ENTRY:
        frappe.throw(
            _("Phase 14D expected {0} but created {1}. Stop and investigate naming sequence before continuing.").format(
                EXPECTED_SMOKE_PAYMENT_ENTRY,
                pe.name,
            )
        )

    return pe


def build_items(rows, issues, ack_ok, completed=0, payment_entry=None):
    items = []

    if not issues:
        items.append({
            "status": "Pass",
            "severity": "Critical",
            "category": "Smoke Source",
            "check_key": "smoke_source_valid",
            "check_label": "Smoke source valid",
            "detail": "Phase 14C execution gate is stable and smoke can create exactly one governed Payment Entry.",
            "smoke_payment_entry": payment_entry or EXPECTED_SMOKE_PAYMENT_ENTRY,
        })
    else:
        for issue in issues:
            items.append({
                "status": "Blocker",
                "severity": "Critical",
                "category": "Smoke Source",
                "check_key": "smoke_source_valid",
                "check_label": "Smoke source valid",
                "detail": issue,
                "smoke_payment_entry": payment_entry or EXPECTED_SMOKE_PAYMENT_ENTRY,
            })

    for row in rows:
        outstanding_after = frappe.db.get_value("Sales Invoice", row.reference_name, "outstanding_amount") if completed else row.outstanding_before
        items.append({
            "status": "Pass",
            "severity": "High",
            "category": "Smoke Reference",
            "check_key": "smoke_sales_invoice_reference",
            "check_label": f"Smoke Sales Invoice {row.idx}",
            "detail": f"{row.reference_name} smoke amount={row.smoke_amount}, before={row.outstanding_before}, after={flt(outstanding_after or 0, 2)}.",
            "line_no": row.idx,
            "reference_doctype": row.reference_doctype,
            "reference_name": row.reference_name,
            "customer": row.customer,
            "company": row.company,
            "currency": row.currency,
            "smoke_amount": row.smoke_amount,
            "allocated_amount": row.allocated_amount,
            "invoice_docstatus": row.invoice_docstatus,
            "outstanding_before": row.outstanding_before,
            "outstanding_after": flt(outstanding_after or 0, 2),
            "gated_payment_entry": GATED_PAYMENT_ENTRY,
            "smoke_payment_entry": payment_entry or EXPECTED_SMOKE_PAYMENT_ENTRY,
        })

    items.append({
        "status": "Pass" if ack_ok else "Warning",
        "severity": "Low" if ack_ok else "Medium",
        "category": "Acknowledgement",
        "check_key": "ack_ok",
        "check_label": "Acknowledgement supplied",
        "detail": "Exact acknowledgement supplied." if ack_ok else f"Required acknowledgement not supplied: {SMOKE_ACK}",
        "smoke_payment_entry": payment_entry or EXPECTED_SMOKE_PAYMENT_ENTRY,
    })

    return items


def summarise_items(items):
    return {
        "blocker_count": len([i for i in items if i["status"] == "Blocker"]),
        "warning_count": len([i for i in items if i["status"] == "Warning"]),
        "pass_count": len([i for i in items if i["status"] == "Pass"]),
        "info_count": len([i for i in items if i["status"] == "Info"]),
        "item_count": len(items),
    }


def create_items(doc, items):
    for item in items:
        row = frappe.new_doc(SMOKE_ITEM_DOCTYPE)
        row.smoke = doc.name
        row.flags.ignore_links = True
        for fieldname, value in item.items():
            if row.meta.has_field(fieldname):
                setattr(row, fieldname, value)
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_next_governed_limited_operation_smoke_phase14d(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_next_governed_limited_operation_smoke_phase14d")

    execution_gate = latest_execution_gate()
    rows = execution_gate_rows(execution_gate.name) if execution_gate else []

    guard_before = guardrails()
    ack_ok = acknowledgement == SMOKE_ACK

    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }

    policy_enabled_before = get_flag(POLICY_DOCTYPE, execution_gate.target_policy, "production_batch_enabled") if execution_gate else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, execution_gate.target_policy, "live_posting_allowed") if execution_gate else 0

    source_issues = validate_source(execution_gate, rows, guard_before, config, policy_enabled_before, policy_live_before)

    payment_entry_name = None

    if not int(dry_run or 0) and ack_ok and not source_issues:
        pe = create_smoke_payment_entry(rows)
        payment_entry_name = pe.name

    guard_after = guardrails()

    policy_enabled_after = get_flag(POLICY_DOCTYPE, execution_gate.target_policy, "production_batch_enabled") if execution_gate else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, execution_gate.target_policy, "live_posting_allowed") if execution_gate else 0

    pe_state = payment_entry_state(payment_entry_name or EXPECTED_SMOKE_PAYMENT_ENTRY)
    gated_state = payment_entry_state(GATED_PAYMENT_ENTRY)
    previous_gated_state = payment_entry_state(PREVIOUS_GATED_PAYMENT_ENTRY)
    smoke_gl_rows = payment_entry_gl_rows(payment_entry_name or EXPECTED_SMOKE_PAYMENT_ENTRY)
    smoke_gl_net = payment_entry_gl_net(payment_entry_name or EXPECTED_SMOKE_PAYMENT_ENTRY)
    smoke_direct_cancelled_gl_rows = payment_entry_cancelled_gl_rows(payment_entry_name or EXPECTED_SMOKE_PAYMENT_ENTRY)
    invoice_outstanding_before_smoke = flt(sum(flt(row.outstanding_before or 0, 2) for row in rows), 2)
    invoice_outstanding_after_smoke = outstanding_total(EXPECTED_INVOICES)

    actual_pe_created = guard_after["payment_entry_count"] - guard_before["payment_entry_count"]
    actual_pe_cancelled = 0
    actual_gl_created = guard_after["payment_entry_gl_count"] - guard_before["payment_entry_gl_count"]

    policy_mutation_count = int(
        policy_enabled_before != policy_enabled_after
        or policy_live_before != policy_live_after
        or guard_before["production_batch_enabled_policy_count"] != guard_after["production_batch_enabled_policy_count"]
        or guard_before["live_posting_allowed_policy_count"] != guard_after["live_posting_allowed_policy_count"]
    )

    post_issues = list(source_issues)

    if not int(dry_run or 0) and ack_ok and not source_issues:
        if payment_entry_name != EXPECTED_SMOKE_PAYMENT_ENTRY:
            post_issues.append(f"Expected Payment Entry {EXPECTED_SMOKE_PAYMENT_ENTRY}, created {payment_entry_name}.")
        if pe_state.docstatus != 1:
            post_issues.append("Smoke Payment Entry must be submitted.")
        if pe_state.status != "Submitted":
            post_issues.append(f"Smoke Payment Entry status must be Submitted. Found {pe_state.status}.")
        if smoke_gl_rows != EXPECTED_SMOKE_GL_ROWS:
            post_issues.append(f"Smoke GL rows must be {EXPECTED_SMOKE_GL_ROWS}. Found {smoke_gl_rows}.")
        if smoke_gl_net != EXPECTED_SMOKE_GL_NET:
            post_issues.append(f"Smoke GL net must be {EXPECTED_SMOKE_GL_NET}. Found {smoke_gl_net}.")
        if actual_pe_created != 1:
            post_issues.append(f"Smoke must create exactly 1 Payment Entry. Created {actual_pe_created}.")
        if actual_gl_created != 4:
            post_issues.append(f"Smoke must create exactly 4 Payment Entry GL rows. Created {actual_gl_created}.")
        if guard_after["payment_entry_count"] != EXPECTED_PAYMENT_ENTRY_COUNT_AFTER:
            post_issues.append("Payment Entry count must be 15 after smoke.")
        if guard_after["payment_entry_gl_count"] != EXPECTED_PAYMENT_ENTRY_GL_COUNT_AFTER:
            post_issues.append("Payment Entry GL count must be 98 after smoke.")
        if invoice_outstanding_before_smoke != EXPECTED_INVOICE_OUTSTANDING_BEFORE:
            post_issues.append(f"Invoice outstanding before smoke must be 3.00. Found {invoice_outstanding_before_smoke}.")
        if invoice_outstanding_after_smoke != EXPECTED_INVOICE_OUTSTANDING_AFTER:
            post_issues.append(f"Invoice outstanding after smoke must be 0.00. Found {invoice_outstanding_after_smoke}.")

    if actual_pe_cancelled != 0:
        post_issues.append(f"Smoke must cancel 0 Payment Entries. Cancelled {actual_pe_cancelled}.")
    if guard_after["submitted_journal_entry_count_today"] != 0:
        post_issues.append("Submitted Journal Entry today must remain 0 after smoke.")
    if guard_after["purchase_invoice_count_today"] != 0:
        post_issues.append("Purchase Invoice today must remain 0 after smoke.")
    if policy_mutation_count != 0:
        post_issues.append("Policy state changed during smoke. This is not allowed.")

    completed = int(
        not int(dry_run or 0)
        and ack_ok
        and execution_gate
        and payment_entry_name == EXPECTED_SMOKE_PAYMENT_ENTRY
        and not post_issues
        and pe_state.docstatus == 1
        and pe_state.status == "Submitted"
        and smoke_gl_rows == EXPECTED_SMOKE_GL_ROWS
        and smoke_gl_net == EXPECTED_SMOKE_GL_NET
        and actual_pe_created == 1
        and actual_pe_cancelled == 0
        and actual_gl_created == 4
        and guard_before["payment_entry_count"] == EXPECTED_PAYMENT_ENTRY_COUNT_BEFORE
        and guard_after["payment_entry_count"] == EXPECTED_PAYMENT_ENTRY_COUNT_AFTER
        and guard_before["payment_entry_gl_count"] == EXPECTED_PAYMENT_ENTRY_GL_COUNT_BEFORE
        and guard_after["payment_entry_gl_count"] == EXPECTED_PAYMENT_ENTRY_GL_COUNT_AFTER
        and invoice_outstanding_before_smoke == EXPECTED_INVOICE_OUTSTANDING_BEFORE
        and invoice_outstanding_after_smoke == EXPECTED_INVOICE_OUTSTANDING_AFTER
        and guard_after["submitted_journal_entry_count_today"] == 0
        and guard_after["purchase_invoice_count_today"] == 0
        and policy_mutation_count == 0
    )

    items = build_items(rows, post_issues, ack_ok, completed=completed, payment_entry=payment_entry_name)
    item_summary = summarise_items(items)

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Smoke Completed" if completed else "Needs Review",
        "smoke_status": "Next Governed Limited Operation Smoke Completed" if completed else "Needs Review",
        "smoke_completed": completed,

        "phase14c_execution_gate_verified": 1 if execution_gate else 0,
        "execution_gate_approved_verified": 1 if execution_gate else 0,
        "execution_gate_payment_entry_verified": int(execution_gate and execution_gate.gated_payment_entry == GATED_PAYMENT_ENTRY),
        "execution_gate_payment_entry_cancelled_verified": int(gated_state.docstatus == 2 and gated_state.status == "Cancelled"),
        "execution_gate_gl_rows_verified": int(execution_gate and int(execution_gate.execution_gate_gl_rows or 0) == 8),
        "execution_gate_reversal_gl_rows_verified": int(execution_gate and int(execution_gate.execution_gate_reversal_gl_rows or 0) == 4),
        "execution_gate_gl_net_zero_verified": int(execution_gate and flt(execution_gate.execution_gate_gl_net or 0, 2) == 0),
        "execution_gate_restored_invoice_amount_verified": int(execution_gate and flt(execution_gate.execution_gate_restored_invoice_amount or 0, 2) == EXPECTED_TOTAL_AMOUNT),
        "policy_state_preserved_verified": int(policy_mutation_count == 0 and policy_enabled_before == 1 and policy_enabled_after == 1 and policy_live_before == 0 and policy_live_after == 0),

        "gated_payment_entry": GATED_PAYMENT_ENTRY,
        "gated_payment_entry_docstatus": gated_state.docstatus,
        "gated_payment_entry_status": gated_state.status,
        "previous_gated_payment_entry": PREVIOUS_GATED_PAYMENT_ENTRY,
        "previous_gated_payment_entry_docstatus": previous_gated_state.docstatus,
        "previous_gated_payment_entry_status": previous_gated_state.status,
        "smoke_source_doctype": SMOKE_SOURCE_DOCTYPE,
        "smoke_reference_doctype": SMOKE_REFERENCE_DOCTYPE,
        "smoke_party_type": SMOKE_PARTY_TYPE,
        "smoke_customer": unique_value(rows, "customer"),
        "smoke_company": unique_value(rows, "company"),
        "smoke_currency": unique_value(rows, "currency"),
        "smoke_invoice_names": ", ".join(reference_names(rows)),
        "smoke_invoice_count": len(rows),
        "smoke_total_amount": smoke_total(rows),
        "smoke_payment_entry": payment_entry_name or EXPECTED_SMOKE_PAYMENT_ENTRY,
        "smoke_payment_entry_docstatus": pe_state.docstatus,
        "smoke_payment_entry_status": pe_state.status,
        "smoke_payment_type": SMOKE_PAYMENT_TYPE,
        "smoke_party": unique_value(rows, "customer"),
        "smoke_gl_rows": smoke_gl_rows,
        "smoke_gl_net": smoke_gl_net,
        "smoke_direct_cancelled_gl_rows": smoke_direct_cancelled_gl_rows,

        "invoice_outstanding_before_smoke": invoice_outstanding_before_smoke,
        "invoice_outstanding_after_smoke": invoice_outstanding_after_smoke,

        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guard_after["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
        "actual_payment_entry_created_count": actual_pe_created,
        "actual_payment_entry_cancelled_count": actual_pe_cancelled,
        "actual_gl_created_count": actual_gl_created,

        "submitted_journal_entry_count_today": guard_after["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_after["purchase_invoice_count_today"],

        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": execution_gate.target_policy if execution_gate else None,
        "target_policy_name": execution_gate.target_policy_name if execution_gate else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_before": policy_live_before,
        "target_policy_live_after": policy_live_after,
        "actual_policy_mutation_count": policy_mutation_count,

        SMOKE_READY_FIELD: completed,

        "execution_gate": execution_gate.name if execution_gate else None,
        "preview": execution_gate.preview if execution_gate else None,
        "candidate_validation": execution_gate.candidate_validation if execution_gate else None,
        "candidate_selection": execution_gate.candidate_selection if execution_gate else None,
        "design": execution_gate.design if execution_gate else None,
        "planning": execution_gate.planning if execution_gate else None,
        "monitor": execution_gate.monitor if execution_gate else None,
        "baseline": execution_gate.baseline if execution_gate else None,
        "closeout": execution_gate.closeout if execution_gate else None,
        "freeze": execution_gate.freeze if execution_gate else None,
        "rollback": execution_gate.rollback if execution_gate else None,
        "previous_smoke": execution_gate.smoke if execution_gate else None,

        **item_summary,
        "items": items,
        "issues": post_issues,
        "required_acknowledgement": SMOKE_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 14D performs the next governed limited-operation smoke. Exactly one Payment Entry and four GL rows are expected.",
    }

    if int(dry_run or 0):
        return result

    doc = frappe.new_doc(SMOKE_DOCTYPE)
    doc.smoke_id = make_smoke_id()
    doc.flags.ignore_links = True

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
    doc.smoke_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    create_items(doc, items)
    frappe.db.commit()

    return {
        **result,
        "created": True,
        "smoke": doc.name,
        "smoke_id": doc.smoke_id,
        "smoke_payment_entry": payment_entry_name or EXPECTED_SMOKE_PAYMENT_ENTRY,
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_next_governed_limited_operation_smoke_phase14d_audit(smoke, reason=None):
    assert_action("cancel_next_governed_limited_operation_smoke_phase14d_audit")

    if not frappe.db.exists(SMOKE_DOCTYPE, smoke):
        frappe.throw(_("Next governed limited-operation smoke audit not found: {0}").format(smoke))

    doc = frappe.get_doc(SMOKE_DOCTYPE, smoke)

    if doc.status == "Cancelled":
        return {"smoke": smoke, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.smoke_completed or 0):
        frappe.throw(_("Cannot cancel a completed Phase 14D smoke record."))

    frappe.db.set_value(
        SMOKE_DOCTYPE,
        smoke,
        {
            "status": "Cancelled",
            "smoke_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 14D no-ack smoke audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        f"""
        UPDATE `tab{SMOKE_ITEM_DOCTYPE}`
        SET status='Cancelled'
        WHERE smoke=%(smoke)s
        """,
        {"smoke": smoke},
    )

    frappe.db.commit()

    return {
        "smoke": smoke,
        "status": "Cancelled",
        "note": "No-ack smoke audit cancelled only. No accounting movement occurred.",
    }


@frappe.whitelist()
def quick_next_governed_limited_operation_smoke_phase14d_summary(limit=20):
    return {
        "smoke_records": frappe.get_all(
            SMOKE_DOCTYPE,
            filters={"smoke_payment_entry": EXPECTED_SMOKE_PAYMENT_ENTRY},
            fields=[
                "name",
                "smoke_id",
                "status",
                "smoke_status",
                "smoke_completed",
                "gated_payment_entry",
                "gated_payment_entry_docstatus",
                "gated_payment_entry_status",
                "previous_gated_payment_entry",
                "previous_gated_payment_entry_docstatus",
                "previous_gated_payment_entry_status",
                "smoke_payment_entry",
                "smoke_payment_entry_docstatus",
                "smoke_payment_entry_status",
                "smoke_invoice_names",
                "smoke_invoice_count",
                "smoke_total_amount",
                "invoice_outstanding_before_smoke",
                "invoice_outstanding_after_smoke",
                "smoke_gl_rows",
                "smoke_gl_net",
                "smoke_direct_cancelled_gl_rows",
                "payment_entry_count_before",
                "payment_entry_count_after",
                "payment_entry_gl_count_before",
                "payment_entry_gl_count_after",
                "actual_payment_entry_created_count",
                "actual_payment_entry_cancelled_count",
                "actual_gl_created_count",
                "submitted_journal_entry_count_today",
                "purchase_invoice_count_today",
                SMOKE_READY_FIELD,
                "checked_on",
                "checked_by",
            ],
            order_by="creation desc",
            limit=int(limit or 20),
        ),
        "items": frappe.get_all(
            SMOKE_ITEM_DOCTYPE,
            filters={"smoke_payment_entry": EXPECTED_SMOKE_PAYMENT_ENTRY},
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
                "smoke_amount",
                "outstanding_before",
                "outstanding_after",
                "gated_payment_entry",
                "smoke_payment_entry",
                "detail",
            ],
            order_by="creation desc",
            limit=int(limit or 20),
        ),
        "required_acknowledgement": SMOKE_ACK,
        "guardrails": guardrails(),
        "note": "Phase 14D next governed limited-operation smoke summary.",
    }


def execute_smoke_phase14d_report(filters=None):
    columns = [
        {"fieldname": "smoke", "label": _("Smoke"), "fieldtype": "Link", "options": SMOKE_DOCTYPE, "width": 220},
        {"fieldname": "smoke_id", "label": _("Smoke ID"), "fieldtype": "Data", "width": 520},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 140},
        {"fieldname": "smoke_status", "label": _("Smoke Status"), "fieldtype": "Data", "width": 390},
        {"fieldname": "smoke_completed", "label": _("Completed"), "fieldtype": "Check", "width": 100},
        {"fieldname": "gated_payment_entry", "label": _("Gated PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "smoke_payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "smoke_payment_entry_docstatus", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 115},
        {"fieldname": "smoke_payment_entry_status", "label": _("PE Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "smoke_invoice_names", "label": _("Invoices"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "smoke_total_amount", "label": _("Amount"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "invoice_outstanding_before_smoke", "label": _("Outstanding Before"), "fieldtype": "Currency", "width": 145},
        {"fieldname": "invoice_outstanding_after_smoke", "label": _("Outstanding After"), "fieldtype": "Currency", "width": 140},
        {"fieldname": "smoke_gl_rows", "label": _("GL Rows"), "fieldtype": "Int", "width": 90},
        {"fieldname": "smoke_gl_net", "label": _("GL Net"), "fieldtype": "Currency", "width": 100},
        {"fieldname": SMOKE_READY_FIELD, "label": _("Rollback Ready"), "fieldtype": "Check", "width": 130},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 115},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 115},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL Created"), "fieldtype": "Int", "width": 135},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            name AS smoke,
            smoke_id,
            status,
            smoke_status,
            smoke_completed,
            gated_payment_entry,
            smoke_payment_entry,
            smoke_payment_entry_docstatus,
            smoke_payment_entry_status,
            smoke_invoice_names,
            smoke_total_amount,
            invoice_outstanding_before_smoke,
            invoice_outstanding_after_smoke,
            smoke_gl_rows,
            smoke_gl_net,
            `{SMOKE_READY_FIELD}` AS `{SMOKE_READY_FIELD}`,
            payment_entry_count_before,
            payment_entry_count_after,
            payment_entry_gl_count_before,
            payment_entry_gl_count_after,
            actual_gl_created_count,
            checked_on
        FROM `tab{SMOKE_DOCTYPE}`
        WHERE smoke_payment_entry=%(payment_entry)s
        ORDER BY creation DESC
        """,
        {"payment_entry": EXPECTED_SMOKE_PAYMENT_ENTRY},
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.smoke_id for row in data[:20]],
            "datasets": [
                {"name": "Completed", "values": [int(row.smoke_completed or 0) for row in data[:20]]},
                {"name": "Rollback Ready", "values": [int(row.get(SMOKE_READY_FIELD) or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Smoke Records"), "datatype": "Int"},
        {"value": sum(int(row.smoke_completed or 0) for row in data), "indicator": "Green", "label": _("Completed"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Orange", "label": _("Actual GL Created"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_item_report(filters=None):
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": SMOKE_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "smoke", "label": _("Smoke"), "fieldtype": "Link", "options": SMOKE_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 190},
        {"fieldname": "line_no", "label": _("Line"), "fieldtype": "Int", "width": 60},
        {"fieldname": "reference_doctype", "label": _("Ref DocType"), "fieldtype": "Data", "width": 130},
        {"fieldname": "reference_name", "label": _("Reference"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 180},
        {"fieldname": "smoke_amount", "label": _("Smoke Amount"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "allocated_amount", "label": _("Allocated"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "outstanding_before", "label": _("Outstanding Before"), "fieldtype": "Currency", "width": 145},
        {"fieldname": "outstanding_after", "label": _("Outstanding After"), "fieldtype": "Currency", "width": 140},
        {"fieldname": "gated_payment_entry", "label": _("Gated PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "smoke_payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 650},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            name AS item,
            smoke,
            status,
            category,
            line_no,
            reference_doctype,
            reference_name,
            smoke_amount,
            allocated_amount,
            outstanding_before,
            outstanding_after,
            gated_payment_entry,
            smoke_payment_entry,
            detail
        FROM `tab{SMOKE_ITEM_DOCTYPE}`
        WHERE smoke_payment_entry=%(payment_entry)s
        ORDER BY creation DESC
        """,
        {"payment_entry": EXPECTED_SMOKE_PAYMENT_ENTRY},
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": ["Pass", "Warning", "Blocker", "Info"],
            "datasets": [{
                "name": "Items",
                "values": [
                    len([row for row in data if row.status == "Pass"]),
                    len([row for row in data if row.status == "Warning"]),
                    len([row for row in data if row.status == "Blocker"]),
                    len([row for row in data if row.status == "Info"]),
                ],
            }],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Items"), "datatype": "Int"},
        {"value": len([row for row in data if row.category == "Smoke Reference"]), "indicator": "Green", "label": _("Smoke References"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_smoke_phase14d_report(filters)
    guard = guardrails()
    summary.append({"value": guard["payment_entry_count"], "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"})
    summary.append({"value": guard["payment_entry_gl_count"], "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"})
    summary.append({"value": guard["submitted_journal_entry_count_today"], "indicator": "Red", "label": _("Submitted JE Today"), "datatype": "Int"})
    summary.append({"value": guard["purchase_invoice_count_today"], "indicator": "Red", "label": _("Purchase Invoice Today"), "datatype": "Int"})
    summary.append({"value": guard["production_batch_enabled_policy_count"], "indicator": "Green", "label": _("Enabled Policies"), "datatype": "Int"})
    summary.append({"value": guard["live_posting_allowed_policy_count"], "indicator": "Red", "label": _("Live Policies"), "datatype": "Int"})
    return columns, data, message, chart, summary
